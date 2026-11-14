"""MCP サーバー（通常ツール + MCP Apps 拡張）。

ツール構成:
  モデル向けツール   search_products / get_product / get_cart /
                    add_to_cart / update_cart / remove_from_cart /
                    browse_shop / reset_demo
                    @mcp.tool で登録し _meta.ui.resourceUri を meta= で付与。
                    （Apps 拡張の tools() 経由だと拡張未ネゴシエーションの
                      クライアントにツール自体が見えなくなるため）
                    戻り値は CallToolResult で、content に日本語テキスト、
                    structuredContent に構造化データを両方載せる。
                    → 操作ログは "MCP"
  アプリ専用ツール   ui_search_products / ui_get_product / ui_get_cart /
                    ui_add_to_cart / ui_update_cart / ui_remove_from_cart
                    @apps.tool(visibility=["app"]) で登録。
                    ホストはモデルに見せず、MCP Apps の iframe からのみ呼ばれる想定。
                    サーバー側でも Apps 拡張ネゴシエーション済みクライアントかを検査する。
                    → 操作ログは "MCP_APPS"（サーバー側で検証した経路識別）

いずれのツールも stapy_shop.service.ShopService に委譲し、
ビジネスロジックは重複実装しない。
"""

import json
import re
from pathlib import Path
from typing import Annotated, Any, Literal

from mcp.server.apps import Apps, ResourceCsp, client_supports_apps
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.context import Context
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from pydantic import Field

from .service import DEMO_SESSION_ID, ShopError, ShopService

SHOP_UI_URI = "ui://stapy/shop.html"

# ツール引数の共有型エイリアス（func_metadata がモジュール globals で評価するためトップレベルに置く）
SortKey = Literal["recommended", "price-asc", "price-desc", "name"]
ProductId = Annotated[str, Field(description="商品ID（例: 'lt-timer', 'sticker-set'）")]
ItemKey = Annotated[str, Field(description="カート内商品キー（'product_id|variant' 形式。get_cart の key 値）")]
Qty = Annotated[int, Field(ge=1, le=99, description="数量")]
QtyOrZero = Annotated[int, Field(ge=0, le=99, description="新しい数量（0で削除）")]

_MCP_APP_DIR = Path(__file__).parent / "mcp_app"


def _load_shop_html(base_url: str) -> str:
    """ui://stapy/shop.html のHTMLを組み立てる。

    @modelcontextprotocol/ext-apps のブラウザ向けバンドル（app-with-deps.js,
    npm v2.0.4 をベンダリング）を同一 module スクリプトにインラインし、
    export 名 App を window.__StapyExtApps に橋渡しする。
    外部CDNへ依存しないため CSP resourceDomains も最小限で済む。
    """
    template = (_MCP_APP_DIR / "shop_app.html").read_text(encoding="utf-8")
    sdk_js = (_MCP_APP_DIR / "ext_apps.js").read_text(encoding="utf-8")
    m = re.search(r"(\w+)\s+as\s+App\b", sdk_js)
    if not m:
        raise RuntimeError("ext_apps.js の App export が見つかりません")
    sdk_js += f"\n;window.__StapyExtApps={{App:{m.group(1)}}};\n"
    return template.replace("/*__EXT_APPS_SDK__*/", sdk_js).replace("__STAPY_BASE_URL__", base_url)


def _result(text: str, structured: dict[str, Any] | None = None) -> CallToolResult:
    """日本語テキスト（モデル用）と構造化データ（MCP Apps UI用）を両方返す。"""
    if structured is None:
        structured = {"message": text}
    return CallToolResult(content=[TextContent(type="text", text=text)], structuredContent=structured)


def _raise(e: ShopError) -> None:
    raise ToolError(f"[{e.code}] {e.message}")


def _require_apps(ctx: Context) -> None:
    """app 専用ツールのサーバー側ガード。

    visibility=["app"] はホスト側の表示制御であってアクセス制御ではないため、
    MCP_APPS ログの経路識別を信頼できるものにするために、
    Apps 拡張をネゴシエーションしたクライアントからの呼び出しのみ許可する。
    """
    if not client_supports_apps(ctx):
        raise ToolError("[forbidden] このツールは MCP Apps 対応クライアントのUIからのみ呼び出せます")


def build_mcp_server(service: ShopService, base_url: str = "http://127.0.0.1:8000") -> MCPServer:
    # 注意: Apps 拡張の tools()/resources() は MCPServer 構築時に消費される。
    # そのため @apps.tool / add_html_resource は MCPServer() より先に実行する。
    apps = Apps()

    shop_html = _load_shop_html(base_url)
    apps.add_html_resource(
        SHOP_UI_URI,
        shop_html,
        name="stapy-shop-ui",
        title="stapy商店ショップUI",
        description="商品カードの閲覧・検索・数量選択・カート操作ができる対話UI",
        csp=ResourceCsp(resource_domains=[base_url, base_url.replace("127.0.0.1", "localhost")]),
        prefers_border=True,
    )

    # ------------------------------------------------------------------
    # アプリ専用ツール（visibility=["app"]、channel=MCP_APPS）
    # ------------------------------------------------------------------
    @apps.tool(
        resource_uri=SHOP_UI_URI,
        visibility=["app"],
        description="[MCP Apps UI専用] 商品を検索する。",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    def ui_search_products(
        ctx: Context,
        q: Annotated[str, Field(description="検索キーワード")] = "",
        category: Annotated[str | None, Field(description="カテゴリ名")] = None,
        max_price: Annotated[int | None, Field(ge=0, description="価格上限（円）")] = None,
        sort: SortKey = "recommended",
    ) -> dict[str, Any]:
        _require_apps(ctx)
        try:
            return service.search_products(
                q=q,
                categories=[category] if category else None,
                max_price=max_price,
                sort=sort,
                channel="MCP_APPS",
                session_id=DEMO_SESSION_ID,
            )
        except ShopError as e:
            _raise(e)

    @apps.tool(
        resource_uri=SHOP_UI_URI,
        visibility=["app"],
        description="[MCP Apps UI専用] 商品詳細を取得する。",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    def ui_get_product(ctx: Context, product_id: ProductId) -> dict[str, Any]:
        _require_apps(ctx)
        try:
            product = service.get_product(product_id)
        except ShopError as e:
            _raise(e)
        service.db.log("MCP_APPS", "get_product", product["name"], DEMO_SESSION_ID)
        return {"product": product}

    @apps.tool(
        resource_uri=SHOP_UI_URI,
        visibility=["app"],
        description="[MCP Apps UI専用] カート内容を取得する。",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    def ui_get_cart(ctx: Context) -> dict[str, Any]:
        _require_apps(ctx)
        return service.get_cart(DEMO_SESSION_ID, channel="MCP_APPS")

    @apps.tool(
        resource_uri=SHOP_UI_URI,
        visibility=["app"],
        description="[MCP Apps UI専用] カートに商品を追加する。",
        annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False),
    )
    def ui_add_to_cart(ctx: Context, product_id: ProductId, qty: Qty = 1, variant: str = "") -> dict[str, Any]:
        _require_apps(ctx)
        try:
            cart = service.add_to_cart(product_id, qty, variant, DEMO_SESSION_ID, channel="MCP_APPS")
        except ShopError as e:
            _raise(e)
        return {"added": {"product_id": product_id, "qty": qty, "variant": variant}, "cart": cart}

    @apps.tool(
        resource_uri=SHOP_UI_URI,
        visibility=["app"],
        description="[MCP Apps UI専用] カート内商品の数量を変更する。",
        annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True),
    )
    def ui_update_cart(ctx: Context, item_key: ItemKey, qty: QtyOrZero) -> dict[str, Any]:
        _require_apps(ctx)
        try:
            return service.update_cart(item_key, qty, DEMO_SESSION_ID, channel="MCP_APPS")
        except ShopError as e:
            _raise(e)

    @apps.tool(
        resource_uri=SHOP_UI_URI,
        visibility=["app"],
        description="[MCP Apps UI専用] カートから商品を削除する。",
        annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=True),
    )
    def ui_remove_from_cart(ctx: Context, item_key: ItemKey) -> dict[str, Any]:
        _require_apps(ctx)
        try:
            return service.remove_from_cart(item_key, DEMO_SESSION_ID, channel="MCP_APPS")
        except ShopError as e:
            _raise(e)

    @apps.tool(
        resource_uri=SHOP_UI_URI,
        visibility=["app"],
        description="[MCP Apps UI専用] カート内容をデモ注文として確定する（実際の決済・発送は行われない）。",
        annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=False),
    )
    def ui_confirm_order(ctx: Context) -> dict[str, Any]:
        _require_apps(ctx)
        try:
            return service.confirm_order(DEMO_SESSION_ID, channel="MCP_APPS")
        except ShopError as e:
            _raise(e)

    mcp = MCPServer(
        "stapy-shop",
        instructions=(
            "stapy商店（Start Python Club の架空グッズEC）デモサーバー。"
            "商品検索・商品詳細・カート操作を提供する。実際の販売・決済は行われない。"
            "対応ホストでは search_products / browse_shop が対話UIを表示する。"
        ),
        extensions=[apps],
    )

    # ------------------------------------------------------------------
    # モデル向けツール（channel=MCP）
    # content に日本語テキスト、structuredContent に同じデータを載せるため、
    # Apps 非対応クライアントにも対応ホストにも意味のある応答になる。
    # ------------------------------------------------------------------
    _UI_META = {"ui": {"resourceUri": SHOP_UI_URI, "visibility": ["model", "app"]}}

    @mcp.tool(
        description=(
            "stapy商店の商品を検索する。キーワード・カテゴリ・価格上限で絞り込める。"
            "対応ホストでは検索結果が対話UIで表示される。"
        ),
        annotations=ToolAnnotations(read_only_hint=True),
        meta=_UI_META,
    )
    def search_products(
        q: Annotated[str, Field(description="検索キーワード（商品名・説明・キーワードを対象）")] = "",
        category: Annotated[str | None, Field(description="カテゴリ名で絞り込み（例: 'デスク周り'）")] = None,
        max_price: Annotated[int | None, Field(ge=0, description="価格上限（円）")] = None,
        sort: SortKey = "recommended",
    ) -> CallToolResult:
        try:
            result = service.search_products(
                q=q,
                categories=[category] if category else None,
                max_price=max_price,
                sort=sort,
                channel="MCP",
                session_id=DEMO_SESSION_ID,
            )
        except ShopError as e:
            _raise(e)
        lines = [f"検索結果 {result['count']}件:"]
        lines += [f"- {p['name']}（{p['id']}）¥{p['price']} 在庫{p['stock']}" for p in result["products"]]
        return _result("\n".join(lines), result)

    @mcp.tool(
        description="商品IDから商品の詳細情報（価格・在庫・特徴・仕様）を取得する。",
        annotations=ToolAnnotations(read_only_hint=True),
        meta=_UI_META,
    )
    def get_product(product_id: ProductId) -> CallToolResult:
        try:
            product = service.get_product(product_id)
        except ShopError as e:
            _raise(e)
        service.db.log("MCP", "get_product", product["name"], DEMO_SESSION_ID)
        return _result(
            f"{product['name']} ¥{product['price']} 在庫{product['stock']}\n{json.dumps(product, ensure_ascii=False)}",
            {"product": product},
        )

    @mcp.tool(
        description="共有デモカートの内容（明細・数量・合計金額）を取得する。",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    def get_cart() -> CallToolResult:
        cart = service.get_cart(DEMO_SESSION_ID, channel="MCP")
        if not cart["items"]:
            text = "カートは空です。"
        else:
            lines = [f"カート: {cart['count']}点 合計 ¥{cart['total']}"]
            lines += [f"- {i['name']} ×{i['qty']} = ¥{i['subtotal']}（key: {i['key']}）" for i in cart["items"]]
            text = "\n".join(lines)
        return _result(text, cart)

    @mcp.tool(
        description="商品を共有デモカートに追加する。価格はサーバー側の商品マスターで計算される。",
        annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False),
        meta=_UI_META,
    )
    def add_to_cart(
        product_id: ProductId,
        qty: Qty = 1,
        variant: Annotated[str, Field(description="サイズ等のバリアント（該当商品のみ。例: 'M'）")] = "",
    ) -> CallToolResult:
        try:
            cart = service.add_to_cart(product_id, qty, variant, DEMO_SESSION_ID, channel="MCP")
        except ShopError as e:
            _raise(e)
        return _result(
            f"カートに追加しました。現在 {cart['count']}点・合計 ¥{cart['total']} です。",
            {"added": {"product_id": product_id, "qty": qty, "variant": variant}, "cart": cart},
        )

    @mcp.tool(
        description="カート内商品の数量を変更する。qty=0 で削除と同等。",
        annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True),
    )
    def update_cart(item_key: ItemKey, qty: QtyOrZero) -> CallToolResult:
        try:
            cart = service.update_cart(item_key, qty, DEMO_SESSION_ID, channel="MCP")
        except ShopError as e:
            _raise(e)
        return _result(f"数量を更新しました。現在 {cart['count']}点・合計 ¥{cart['total']} です。", cart)

    @mcp.tool(
        description="カートから商品を削除する。",
        annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=True),
    )
    def remove_from_cart(item_key: ItemKey) -> CallToolResult:
        try:
            cart = service.remove_from_cart(item_key, DEMO_SESSION_ID, channel="MCP")
        except ShopError as e:
            _raise(e)
        return _result(f"削除しました。現在 {cart['count']}点・合計 ¥{cart['total']} です。", cart)

    @mcp.tool(
        description="stapy商店の対話ショップUIを開く。商品ブラウズからカート操作までUI上で行える。",
        annotations=ToolAnnotations(read_only_hint=True),
        meta=_UI_META,
    )
    def browse_shop() -> CallToolResult:
        catalog = service.search_products(channel="MCP", session_id=DEMO_SESSION_ID)
        cart = service.get_cart(DEMO_SESSION_ID)
        return _result(
            f"stapy商店: {catalog['count']}件の商品があります。対話UIを表示するか search_products で検索してください。",
            {"products": catalog["products"], "cart": cart},
        )

    @mcp.tool(
        description=(
            "共有デモカートの内容を「デモ注文」として確定する。"
            "確定後カートは空になり、注文番号（STAPY-DEMO-xxxxx）と明細を返す。"
            "実際の決済・発送・在庫確定は一切行われない（勉強会デモ用の記録のみ）。"
        ),
        annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=False),
        meta=_UI_META,
    )
    def confirm_order() -> CallToolResult:
        try:
            order = service.confirm_order(DEMO_SESSION_ID, channel="MCP")
        except ShopError as e:
            _raise(e)
        lines = [f"デモ注文を確定しました: {order['order_no']}（{order['count']}点 合計 ¥{order['total']}）"]
        lines += [f"- {i['name']} ×{i['qty']} = ¥{i['subtotal']}" for i in order["items"]]
        lines.append("※ 実際の決済・発送は行われません（デモ）")
        return _result("\n".join(lines), order)

    @mcp.tool(
        description="デモ用に共有カートを空にして初期状態へ戻す。",
        annotations=ToolAnnotations(destructive_hint=True, idempotent_hint=True),
    )
    def reset_demo() -> CallToolResult:
        result = service.reset_demo(DEMO_SESSION_ID, channel="MCP")
        return _result("デモをリセットしました。カートは空です。", result)

    return mcp
