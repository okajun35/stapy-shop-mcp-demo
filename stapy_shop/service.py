"""共通サービス層。

REST API・MCP・MCP Apps・WebMCP（REST 経由）のすべてがこの層を通る。
価格は必ずサーバー側の商品マスター（products.py）から取得し、
クライアント送信の価格は一切信用しない。
"""

from __future__ import annotations

import json
import unicodedata
from typing import Any, Literal

from .db import Database
from .products import CATEGORIES, PRODUCTS, PRODUCTS_BY_ID

Channel = Literal["WEB", "MCP", "MCP_APPS", "WEBMCP"]

DEMO_SESSION_ID = "demo"
MAX_QTY_PER_ITEM = 99


class ShopError(Exception):
    """業務エラー。code は API エラー応答と MCP エラーメッセージで共有する。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _norm(text: str) -> str:
    return unicodedata.normalize("NFKC", text).lower()


def public_product(p: dict) -> dict:
    """商品マスターを外部向け表現に整形（image はファイル名→/images/ URL）。"""
    return {
        "id": p["id"],
        "name": p["name"],
        "price": p["price"],
        "category": p["category"],
        "tag": p["tag"],
        "image": f"/images/{p['image']}",
        "desc": p["desc"],
        "stock": p["stock"],
        "variants": p.get("variants"),
        "keywords": p["keywords"],
        "features": p["features"],
        **({"gallery": [f"/images/{g}" for g in p["gallery"]]} if "gallery" in p else {}),
        **({"specs": p["specs"]} if "specs" in p else {}),
        **({"note": p["note"]} if "note" in p else {}),
    }


class ShopService:
    def __init__(self, db: Database) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # products
    # ------------------------------------------------------------------
    def list_products(self) -> list[dict]:
        return [public_product(p) for p in PRODUCTS]

    def list_categories(self) -> list[dict]:
        return [
            {"name": c, "count": sum(1 for p in PRODUCTS if p["category"] == c)}
            for c in CATEGORIES
        ]

    def get_product(self, product_id: str) -> dict:
        p = PRODUCTS_BY_ID.get(product_id)
        if p is None:
            raise ShopError("product_not_found", f"商品が見つかりません: {product_id}")
        return public_product(p)

    def search_products(
        self,
        q: str = "",
        categories: list[str] | None = None,
        max_price: int | None = None,
        in_stock_only: bool = False,
        featured_only: bool = False,
        sort: Literal["recommended", "price-asc", "price-desc", "name"] = "recommended",
        channel: Channel | None = None,
        session_id: str = DEMO_SESSION_ID,
    ) -> dict:
        if max_price is not None and max_price < 0:
            raise ShopError("invalid_input", "max_price は 0 以上を指定してください")
        rows = PRODUCTS
        if categories:
            rows = [p for p in rows if p["category"] in categories]
        if max_price is not None:
            rows = [p for p in rows if p["price"] <= max_price]
        if in_stock_only:
            rows = [p for p in rows if p["stock"] > 0]
        if featured_only:
            rows = [p for p in rows if p["tag"] in ("おすすめ", "人気")]
        if q:
            nq = _norm(q.strip())
            rows = [
                p
                for p in rows
                if nq in _norm(f"{p['name']} {p['desc']} {p['keywords']} {p['category']}")
            ]
        rows = list(rows)
        if sort == "price-asc":
            rows.sort(key=lambda p: p["price"])
        elif sort == "price-desc":
            rows.sort(key=lambda p: -p["price"])
        elif sort == "name":
            rows.sort(key=lambda p: p["name"])
        result = {"count": len(rows), "products": [public_product(p) for p in rows]}
        if channel:
            self.db.log(
                channel,
                "search_products",
                f"q={q!r} categories={categories} max_price={max_price} → {len(rows)}件",
                session_id,
            )
        return result

    # ------------------------------------------------------------------
    # cart
    # ------------------------------------------------------------------
    @staticmethod
    def item_key(product_id: str, variant: str = "") -> str:
        return f"{product_id}|{variant}"

    def get_cart(self, session_id: str = DEMO_SESSION_ID, channel: Channel | None = None) -> dict:
        items = []
        total = 0
        for row in self.db.get_cart_items(session_id):
            p = PRODUCTS_BY_ID.get(row["product_id"])
            if p is None:
                continue  # マスターから消えた商品は表示しない
            subtotal = p["price"] * row["qty"]
            total += subtotal
            items.append(
                {
                    "key": row["item_key"],
                    "product_id": row["product_id"],
                    "variant": row["variant"],
                    "qty": row["qty"],
                    "name": p["name"],
                    "price": p["price"],
                    "image": f"/images/{p['image']}",
                    "subtotal": subtotal,
                }
            )
        cart = {"session_id": session_id, "items": items, "total": total, "count": sum(i["qty"] for i in items)}
        if channel:
            self.db.log(channel, "get_cart", f"{len(items)}種 {cart['count']}点 合計¥{total}", session_id)
        return cart

    def _validate_qty(self, qty: Any) -> int:
        if isinstance(qty, bool) or not isinstance(qty, int):
            raise ShopError("invalid_input", "qty は整数で指定してください")
        if qty <= 0:
            raise ShopError("invalid_input", "qty は 1 以上を指定してください")
        if qty > MAX_QTY_PER_ITEM:
            raise ShopError("invalid_input", f"qty は {MAX_QTY_PER_ITEM} 以下を指定してください")
        return qty

    def _validate_variant(self, product: dict, variant: str) -> str:
        variant = variant or ""
        choices = product.get("variants")
        if choices and variant not in choices:
            raise ShopError(
                "invalid_input",
                f"バリアントが不正です: {variant!r}（選択肢: {', '.join(choices)}）",
            )
        if not choices and variant:
            raise ShopError("invalid_input", f"商品 {product['id']} にバリアントはありません")
        return variant

    def add_to_cart(
        self,
        product_id: str,
        qty: int = 1,
        variant: str = "",
        session_id: str = DEMO_SESSION_ID,
        channel: Channel = "WEB",
    ) -> dict:
        product = self.get_product(product_id)  # raises product_not_found
        qty = self._validate_qty(qty)
        variant = self._validate_variant(PRODUCTS_BY_ID[product_id], variant)
        key = self.item_key(product_id, variant)
        with self.db._lock:
            existing = self.db.get_item_qty(session_id, key)
            new_qty = existing + qty
            if new_qty > product["stock"]:
                raise ShopError(
                    "out_of_stock",
                    f"在庫が足りません: {product['name']}（在庫{product['stock']}、"
                    f"カート内{existing}＋追加{qty}）",
                )
            self.db.upsert_item(session_id, key, product_id, variant, new_qty)
            self.db.cancel_pending_orders(session_id)  # 提示済み内容とカートが乖離しないよう pending を無効化
        self.db.log(
            channel,
            "add_to_cart",
            f"{product['name']} ×{qty}" + (f"（{variant}）" if variant else ""),
            session_id,
        )
        return self.get_cart(session_id)

    def update_cart(
        self,
        item_key: str,
        qty: int,
        session_id: str = DEMO_SESSION_ID,
        channel: Channel = "WEB",
    ) -> dict:
        """item_key（"product_id|variant"）の数量を絶対値で変更。0 なら削除。"""
        product_id, _, variant = item_key.partition("|")
        if product_id not in PRODUCTS_BY_ID:
            raise ShopError("product_not_found", f"商品が見つかりません: {product_id}")
        if isinstance(qty, bool) or not isinstance(qty, int):
            raise ShopError("invalid_input", "qty は整数で指定してください")
        if qty < 0:
            raise ShopError("invalid_input", "qty は 0 以上を指定してください")
        if qty == 0:
            return self.remove_from_cart(item_key, session_id=session_id, channel=channel)
        product = self.get_product(product_id)
        if qty > product["stock"]:
            raise ShopError(
                "out_of_stock",
                f"在庫が足りません: {product['name']}（在庫{product['stock']}、指定{qty}）",
            )
        with self.db._lock:
            if self.db.get_item_qty(session_id, item_key) == 0:
                raise ShopError("item_not_found", f"カートに商品がありません: {item_key}")
            self.db.upsert_item(session_id, item_key, product_id, variant, qty)
            self.db.cancel_pending_orders(session_id)
        self.db.log(channel, "update_cart", f"{product['name']} → ×{qty}", session_id)
        return self.get_cart(session_id)

    def remove_from_cart(
        self,
        item_key: str,
        session_id: str = DEMO_SESSION_ID,
        channel: Channel = "WEB",
    ) -> dict:
        with self.db._lock:
            if not self.db.delete_item(session_id, item_key):
                raise ShopError("item_not_found", f"カートに商品がありません: {item_key}")
            self.db.cancel_pending_orders(session_id)
        name = PRODUCTS_BY_ID.get(item_key.partition("|")[0], {}).get("name", item_key)
        self.db.log(channel, "remove_from_cart", f"{name} を削除", session_id)
        return self.get_cart(session_id)

    # ------------------------------------------------------------------
    # demo
    # ------------------------------------------------------------------
    def reset_demo(self, session_id: str = DEMO_SESSION_ID, channel: Channel = "WEB") -> dict:
        with self.db._lock:
            removed = self.db.clear_cart(session_id)
            self.db.cancel_pending_orders(session_id)
        self.db.log(channel, "reset_demo", f"カート {removed}件をクリア", session_id)
        return {"ok": True, "removed_items": removed, "cart": self.get_cart(session_id)}

    def operation_logs(self, limit: int = 100) -> list[dict]:
        return self.db.recent_logs(limit)

    # ------------------------------------------------------------------
    # orders（デモ注文。実際の決済・発送・在庫確定は行われない）
    #
    # 2段階フロー: preview_order（内容提示・pending 保存）
    #            → confirm_order（pending を原子的に確定＋カート空化）
    # カートを変更すると pending は自動キャンセルされ、
    # 「提示した内容と違うものが確定される」ことを防ぐ。
    # ------------------------------------------------------------------
    def preview_order(self, session_id: str = DEMO_SESSION_ID, channel: Channel = "WEB") -> dict:
        """カート内容を「注文内容の確認」として提示する（pending 注文を保存）。

        - 明細・合計は提示時点の商品マスターからスナップショット（改ざん防止）
        - この時点では何も確定されない。confirm_order で初めて確定する
        - 実在の注文ではなく記録のみ。決済・発送・在庫引当は一切行わない
        """
        with self.db._lock:
            cart = self.get_cart(session_id)
            if not cart["items"]:
                raise ShopError("cart_empty", "カートが空です。商品を追加してから確認してください")
            order_no = self.db.create_pending_order(
                session_id, json.dumps(cart["items"], ensure_ascii=False), cart["total"], channel
            )
        self.db.log(
            channel,
            "preview_order",
            f"{order_no}: {cart['count']}点 合計¥{cart['total']}（注文内容を提示）",
            session_id,
        )
        return {
            "order_no": order_no,
            "status": "pending",
            "items": cart["items"],
            "total": cart["total"],
            "count": cart["count"],
            "demo": True,
            "message": (
                "注文内容を確認してください（デモ。実際の決済・発送は行われません）。"
                "この内容でよければ confirm_order で確定します。"
            ),
        }

    def confirm_order(self, session_id: str = DEMO_SESSION_ID, channel: Channel = "WEB") -> dict:
        """preview_order で提示した内容を「デモ注文」として確定する。

        - preview_order で保存したスナップショットがそのまま確定される
        - pending 確定とカート空化は1トランザクション（二重確定・明細不一致なし）
        - 実在の注文ではなく記録のみ。決済・発送・在庫引当は一切行わない
        """
        row = self.db.confirm_pending_order(session_id)
        if row is None:
            raise ShopError(
                "no_pending_order",
                "確定できる注文がありません。先に preview_order で注文内容を提示してください"
                "（カート変更で提示はキャンセルされます）",
            )
        items = json.loads(row["items_json"])
        count = sum(i["qty"] for i in items)
        self.db.log(
            channel,
            "confirm_order",
            f"{row['order_no']}: {count}点 合計¥{row['total']}（デモ注文を確定）",
            session_id,
        )
        return {
            "order_no": row["order_no"],
            "status": "confirmed",
            "items": items,
            "total": row["total"],
            "count": count,
            "demo": True,
            "message": "デモ注文を確定しました（実際の決済・発送は行われません）",
        }

    def get_order(self, order_no: str) -> dict:
        row = self.db.get_order(order_no)
        if row is None:
            raise ShopError("order_not_found", f"注文が見つかりません: {order_no}")
        items = json.loads(row["items_json"])
        return {
            "order_no": row["order_no"],
            "status": row["status"],
            "items": items,
            "total": row["total"],
            "count": sum(i["qty"] for i in items),
            "channel": row["channel"],
            "created_at": row["created_at"],
            "demo": True,
        }
