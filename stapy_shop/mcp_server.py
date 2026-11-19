"""MCP サーバー（通常ツール + MCP Apps 拡張）。

ツール構成:
  モデル向けツール   search_products / get_product / get_cart /
                    add_to_cart / update_cart / remove_from_cart /
                    preview_order / confirm_order / reset_demo
                    （UI連携メタなし → 対応ホストでもUIは表示されない）
                    と apps_* 系全操作分（_meta.ui.resourceUri 付き →
                    MCP Apps 対応ホストで結果が対話UIに自動表示される。
                    apps_browse_shop はUIを開く入口）
                    @mcp.tool で登録し apps_* だけ meta= で _meta.ui を付与。
                    （Apps 拡張の tools() 経由だと拡張未ネゴシエーションの
                      クライアントにツール自体が見えなくなるため）
                    戻り値は CallToolResult で、content に日本語テキスト、
                    structuredContent に構造化データを両方載せる。
                    → 操作ログは "MCP" / apps_* は "MCP_APPS"
                    （action 名は実際に呼ばれたツール名）
  アプリ専用ツール   ui_search_products / ui_get_product / ui_get_cart /
                    ui_add_to_cart / ui_update_cart / ui_remove_from_cart
                    @apps.tool(visibility=["app"]) で登録。
                    ホストはモデルに見せず、MCP Apps の iframe からのみ呼ばれる想定。
                    サーバー側でも Apps 拡張ネゴシエーション済みクライアントかを検査する。
                    → 操作ログは "MCP_APPS"（サーバー側で検証した経路識別）

build_mcp_server の tool_set で公開ツールを絞る（api.py がエンドポイント別に構築）:
  "plain" — 通常ツールのみ（/mcp。UI関連は一切存在しない）
  "apps"  — apps_* + ui_* のみ（/mcp-apps。モデル向けは全てUI連携）
  "all"   — 全ツール（stdio / worker/build.py 生成用）

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


def _instructions(tool_set: str) -> str:
    """initialize で返す使い方ガイド。エンドポイントに存在するツールだけ言及する。"""
    head = (
        "stapy商店（Start Python Club の架空グッズEC）デモサーバー。"
        "商品検索・商品詳細・カート操作・デモ注文を提供する。実際の販売・決済・発送は行われない。\n"
        "使い方ガイド:\n"
        "- すべての操作はこのサーバーのツールで完結する。"
        "外部URLへの遷移やブラウザ操作ツールは使わないこと。\n"
    )
    if tool_set == "apps":
        return head + (
            "- 対話UIを開く: apps_browse_shop（この接続のモデル向けツールはすべて _meta.ui 付きで、"
            "MCP Apps 対応ホストでは結果が対話UIに自動表示される）\n"
            "- 商品を探す: apps_search_products（キーワード・カテゴリ・価格上限）\n"
            "- 商品詳細を見る: apps_get_product（価格・在庫・特徴）\n"
            "- カート: apps_add_to_cart / apps_update_cart / apps_remove_from_cart / apps_get_cart\n"
            "- 注文（デモ・2段階）: まず apps_preview_order で明細・合計を提示し、"
            "ユーザー確認後に apps_confirm_order で確定する。"
            "preview 後にカートを変更すると提示はキャンセルされる。\n"
            "- ui_* ツールは MCP Apps 対応UIの内部専用。モデルは呼ばないこと。"
        )
    if tool_set == "plain":
        return head + (
            "- 商品を探す: search_products（キーワード・カテゴリ・価格上限）\n"
            "- 商品詳細を見る: get_product（価格・在庫・特徴）。詳細ページへのURL遷移ではなくこのツールを使う\n"
            "- カート: add_to_cart / update_cart / remove_from_cart / get_cart\n"
            "- 注文（デモ・2段階）: まず preview_order で明細・合計を提示し、"
            "ユーザー確認後に confirm_order で確定する。"
            "preview 後にカートを変更すると提示はキャンセルされる。"
        )
    return head + (
        "- 商品を探す: search_products（キーワード・カテゴリ・価格上限）\n"
        "- 商品詳細を見る: get_product（価格・在庫・特徴）。詳細ページへのURL遷移ではなくこのツールを使う\n"
        "- カート: add_to_cart / update_cart / remove_from_cart / get_cart\n"
        "- 注文（デモ・2段階）: まず preview_order で明細・合計を提示し、"
        "ユーザー確認後に confirm_order で確定する。"
        "preview 後にカートを変更すると提示はキャンセルされる。\n"
        "- apps_* ツールは _meta.ui 付きで、MCP Apps 対応ホストでは結果が対話UIに表示される"
        "（apps_browse_shop でショップUIを開く）。UIを使わずテキストだけ欲しい場合は"
        "同名の通常ツールを使うこと。\n"
        "- ui_* ツールは MCP Apps 対応UIの内部専用。モデルは呼ばないこと。"
    )


def build_mcp_server(
    service: ShopService,
    base_url: str = "http://127.0.0.1:8000",
    tool_set: Literal["all", "plain", "apps"] = "all",
) -> MCPServer:
    show_plain = tool_set in ("all", "plain")
    show_apps = tool_set in ("all", "apps")

    # 注意: Apps 拡張の tools()/resources() は MCPServer 構築時に消費される。
    # そのため @apps.tool / add_html_resource は MCPServer() より先に実行する。
    apps = Apps() if show_apps else None

    if show_apps:
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

    # tool_set で登録対象を絞る。関数定義はすべて残し、登録だけ条件付きにする
    # （実装は impl で共有しているため、登録側だけ絞ればよい）
    def _ui_tool(**kwargs):
        """ui_* 登録ラッパー（tool_set=apps|all のときだけ apps.tool へ流す）"""
        def deco(fn):
            if apps is not None:
                apps.tool(**kwargs)(fn)
            return fn
        return deco

    def _plain_tool(**kwargs):
        """通常ツール登録ラッパー（tool_set=plain|all のときだけ登録）"""
        def deco(fn):
            if show_plain:
                mcp.tool(**kwargs)(fn)
            return fn
        return deco

    def _apps_tool(**kwargs):
        """apps_* 登録ラッパー（tool_set=apps|all のときだけ登録）"""
        def deco(fn):
            if show_apps:
                mcp.tool(**kwargs)(fn)
            return fn
        return deco

    # ------------------------------------------------------------------
    # アプリ専用ツール（visibility=["app"]、channel=MCP_APPS）
    # ------------------------------------------------------------------
    @_ui_tool(
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

    @_ui_tool(
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

    @_ui_tool(
        resource_uri=SHOP_UI_URI,
        visibility=["app"],
        description="[MCP Apps UI専用] カート内容を取得する。",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    def ui_get_cart(ctx: Context) -> dict[str, Any]:
        _require_apps(ctx)
        return service.get_cart(DEMO_SESSION_ID, channel="MCP_APPS")

    @_ui_tool(
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

    @_ui_tool(
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

    @_ui_tool(
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

    @_ui_tool(
        resource_uri=SHOP_UI_URI,
        visibility=["app"],
        description="[MCP Apps UI専用] カート内容を「注文内容の確認」として提示する（まだ確定しない）。",
        annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False),
    )
    def ui_preview_order(ctx: Context) -> dict[str, Any]:
        _require_apps(ctx)
        try:
            return service.preview_order(DEMO_SESSION_ID, channel="MCP_APPS")
        except ShopError as e:
            _raise(e)

    @_ui_tool(
        resource_uri=SHOP_UI_URI,
        visibility=["app"],
        description="[MCP Apps UI専用] ui_preview_order で提示した内容をデモ注文として確定する（実際の決済・発送は行われない）。",
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
        instructions=_instructions(tool_set),
        **({"extensions": [apps]} if apps else {}),
    )

    # ------------------------------------------------------------------
    # モデル向けツール（通常版 channel=MCP / apps_* 版 channel=MCP_APPS）
    # 本体は _<name>_impl に集約し、通常版（UIメタなし）と apps_* 版
    # （_meta.ui.resourceUri 付き＝対応ホストで結果が対話UIに自動表示）の
    # 2系統を同じ操作で用意する。操作ログの action 名は実際に呼ばれたツール名。
    # content に日本語テキスト、structuredContent に構造化データを両方載せる。
    # ------------------------------------------------------------------
    _UI_META = {"ui": {"resourceUri": SHOP_UI_URI, "visibility": ["model", "app"]}}

    def _search_products_impl(q, category, max_price, sort, action, channel="MCP"):
        try:
            result = service.search_products(
                q=q,
                categories=[category] if category else None,
                max_price=max_price,
                sort=sort,
                channel=channel,
                session_id=DEMO_SESSION_ID,
                action=action,
            )
        except ShopError as e:
            _raise(e)
        lines = [f"検索結果 {result['count']}件:"]
        lines += [f"- {p['name']}（{p['id']}）¥{p['price']} 在庫{p['stock']}" for p in result["products"]]
        return _result("\n".join(lines), result)

    def _get_product_impl(product_id, action, channel="MCP"):
        try:
            product = service.get_product(product_id)
        except ShopError as e:
            _raise(e)
        service.db.log(channel, action, product["name"], DEMO_SESSION_ID)
        return _result(
            f"{product['name']} ¥{product['price']} 在庫{product['stock']}\n{json.dumps(product, ensure_ascii=False)}",
            {"product": product},
        )

    def _get_cart_impl(action, channel="MCP"):
        cart = service.get_cart(DEMO_SESSION_ID, channel=channel, action=action)
        if not cart["items"]:
            text = "カートは空です。"
        else:
            lines = [f"カート: {cart['count']}点 合計 ¥{cart['total']}"]
            lines += [f"- {i['name']} ×{i['qty']} = ¥{i['subtotal']}（key: {i['key']}）" for i in cart["items"]]
            text = "\n".join(lines)
        return _result(text, cart)

    def _add_to_cart_impl(product_id, qty, variant, action, channel="MCP"):
        try:
            cart = service.add_to_cart(product_id, qty, variant, DEMO_SESSION_ID, channel=channel, action=action)
        except ShopError as e:
            _raise(e)
        return _result(
            f"カートに追加しました。現在 {cart['count']}点・合計 ¥{cart['total']} です。",
            {"added": {"product_id": product_id, "qty": qty, "variant": variant}, "cart": cart},
        )

    def _update_cart_impl(item_key, qty, action, channel="MCP"):
        try:
            cart = service.update_cart(item_key, qty, DEMO_SESSION_ID, channel=channel, action=action)
        except ShopError as e:
            _raise(e)
        return _result(f"数量を更新しました。現在 {cart['count']}点・合計 ¥{cart['total']} です。", cart)

    def _remove_from_cart_impl(item_key, action, channel="MCP"):
        try:
            cart = service.remove_from_cart(item_key, DEMO_SESSION_ID, channel=channel, action=action)
        except ShopError as e:
            _raise(e)
        return _result(f"削除しました。現在 {cart['count']}点・合計 ¥{cart['total']} です。", cart)

    def _browse_shop_impl(action, channel="MCP_APPS"):
        catalog = service.search_products(channel=channel, session_id=DEMO_SESSION_ID, action=action)
        cart = service.get_cart(DEMO_SESSION_ID)
        return _result(
            f"stapy商店: {catalog['count']}件の商品があります。対話UIを表示するか search_products で検索してください。",
            {"products": catalog["products"], "cart": cart},
        )

    def _preview_order_impl(action, channel="MCP"):
        try:
            order = service.preview_order(DEMO_SESSION_ID, channel=channel, action=action)
        except ShopError as e:
            _raise(e)
        lines = [f"注文内容の確認（未確定）: {order['order_no']}（{order['count']}点 合計 ¥{order['total']}）"]
        lines += [f"- {i['name']} ×{i['qty']} = ¥{i['subtotal']}" for i in order["items"]]
        lines.append("この内容でよければ confirm_order を実行してください（デモ。実際の決済・発送は行われません）")
        return _result("\n".join(lines), order)

    def _confirm_order_impl(action, channel="MCP"):
        try:
            order = service.confirm_order(DEMO_SESSION_ID, channel=channel, action=action)
        except ShopError as e:
            _raise(e)
        lines = [f"デモ注文を確定しました: {order['order_no']}（{order['count']}点 合計 ¥{order['total']}）"]
        lines += [f"- {i['name']} ×{i['qty']} = ¥{i['subtotal']}" for i in order["items"]]
        lines.append("※ 実際の決済・発送は行われません（デモ）")
        return _result("\n".join(lines), order)

    def _reset_demo_impl(action, channel="MCP"):
        result = service.reset_demo(DEMO_SESSION_ID, channel=channel, action=action)
        return _result("デモをリセットしました。カートは空です。", result)

    # --- 通常ツール（UI連携メタなし。Apps対応ホストでもUIは表示されない） -----

    @_plain_tool(
        description=(
            "stapy商店の商品を検索する。キーワード・カテゴリ・価格上限で絞り込める。"
            "対話UI表示が必要なら apps_search_products を使う。"
        ),
        annotations=ToolAnnotations(read_only_hint=True),
    )
    def search_products(
        q: Annotated[str, Field(description="検索キーワード（商品名・説明・キーワードを対象）")] = "",
        category: Annotated[str | None, Field(description="カテゴリ名で絞り込み（例: 'デスク周り'）")] = None,
        max_price: Annotated[int | None, Field(ge=0, description="価格上限（円）")] = None,
        sort: SortKey = "recommended",
    ) -> CallToolResult:
        return _search_products_impl(q, category, max_price, sort, "search_products")

    @_plain_tool(
        description="商品IDから商品の詳細情報（価格・在庫・特徴・仕様）を取得する。詳細ページへのURL遷移ではなくこのツールを使う。対話UI表示が必要なら apps_get_product。",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    def get_product(product_id: ProductId) -> CallToolResult:
        return _get_product_impl(product_id, "get_product")

    @_plain_tool(
        description="共有デモカートの内容（明細・数量・合計金額）を取得する。対話UI表示が必要なら apps_get_cart。",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    def get_cart() -> CallToolResult:
        return _get_cart_impl("get_cart")

    @_plain_tool(
        description="商品を共有デモカートに追加する。価格はサーバー側の商品マスターで計算される。対話UI表示が必要なら apps_add_to_cart。",
        annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False),
    )
    def add_to_cart(
        product_id: ProductId,
        qty: Qty = 1,
        variant: Annotated[str, Field(description="サイズ等のバリアント（該当商品のみ。例: 'M'）")] = "",
    ) -> CallToolResult:
        return _add_to_cart_impl(product_id, qty, variant, "add_to_cart")

    @_plain_tool(
        description="カート内商品の数量を変更する。qty=0 で削除と同等。対話UI表示が必要なら apps_update_cart。",
        annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True),
    )
    def update_cart(item_key: ItemKey, qty: QtyOrZero) -> CallToolResult:
        return _update_cart_impl(item_key, qty, "update_cart")

    @_plain_tool(
        description="カートから商品を削除する。対話UI表示が必要なら apps_remove_from_cart。",
        annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=True),
    )
    def remove_from_cart(item_key: ItemKey) -> CallToolResult:
        return _remove_from_cart_impl(item_key, "remove_from_cart")

    @_plain_tool(
        description=(
            "共有デモカートの内容を「注文内容の確認」として提示する（第1段階）。"
            "明細・合計をスナップショットした未確定注文（pending）を作り、内容を返す。"
            "ユーザーが内容を確認したら confirm_order で確定する。"
            "実際の決済・発送は行われない（勉強会デモ用）。対話UI表示が必要なら apps_preview_order。"
        ),
        annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False),
    )
    def preview_order() -> CallToolResult:
        return _preview_order_impl("preview_order")

    @_plain_tool(
        description=(
            "preview_order で提示した内容を「デモ注文」として確定する（第2段階）。"
            "提示と同じスナップショットが確定され、確定後カートは空になる。"
            "preview_order を先に実行すること。カートを変更すると提示はキャンセルされる。"
            "実際の決済・発送・在庫確定は一切行われない（勉強会デモ用の記録のみ）。対話UI表示が必要なら apps_confirm_order。"
        ),
        annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=False),
    )
    def confirm_order() -> CallToolResult:
        return _confirm_order_impl("confirm_order")

    @_plain_tool(
        description="デモ用に共有カートを空にして初期状態へ戻す。対話UI表示が必要なら apps_reset_demo。",
        annotations=ToolAnnotations(destructive_hint=True, idempotent_hint=True),
    )
    def reset_demo() -> CallToolResult:
        return _reset_demo_impl("reset_demo")

    # --- apps_* ツール（_meta.ui 付き。対応ホストでは結果が対話UIに表示される） ---

    @_apps_tool(
        description="stapy商店の対話ショップUIを開く（MCP Apps）。商品ブラウズ・カート操作・注文確定までUI上で行える。",
        annotations=ToolAnnotations(read_only_hint=True),
        meta=_UI_META,
    )
    def apps_browse_shop() -> CallToolResult:
        return _browse_shop_impl("apps_browse_shop", "MCP_APPS")

    @_apps_tool(
        description=(
            "stapy商店の商品を検索する。キーワード・カテゴリ・価格上限で絞り込める。"
            "対応ホストでは検索結果が対話UIで表示される。UI不要なら search_products。"
        ),
        annotations=ToolAnnotations(read_only_hint=True),
        meta=_UI_META,
    )
    def apps_search_products(
        q: Annotated[str, Field(description="検索キーワード（商品名・説明・キーワードを対象）")] = "",
        category: Annotated[str | None, Field(description="カテゴリ名で絞り込み（例: 'デスク周り'）")] = None,
        max_price: Annotated[int | None, Field(ge=0, description="価格上限（円）")] = None,
        sort: SortKey = "recommended",
    ) -> CallToolResult:
        return _search_products_impl(q, category, max_price, sort, "apps_search_products", "MCP_APPS")

    @_apps_tool(
        description="商品IDから商品の詳細情報（価格・在庫・特徴・仕様）を取得する。対応ホストでは詳細が対話UIで表示される。UI不要なら get_product。",
        annotations=ToolAnnotations(read_only_hint=True),
        meta=_UI_META,
    )
    def apps_get_product(product_id: ProductId) -> CallToolResult:
        return _get_product_impl(product_id, "apps_get_product", "MCP_APPS")

    @_apps_tool(
        description="共有デモカートの内容（明細・数量・合計金額）を取得する。対応ホストでは対話UIで表示される。UI不要なら get_cart。",
        annotations=ToolAnnotations(read_only_hint=True),
        meta=_UI_META,
    )
    def apps_get_cart() -> CallToolResult:
        return _get_cart_impl("apps_get_cart", "MCP_APPS")

    @_apps_tool(
        description="商品を共有デモカートに追加する。価格はサーバー側の商品マスターで計算される。対応ホストでは対話UIで表示される。UI不要なら add_to_cart。",
        annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False),
        meta=_UI_META,
    )
    def apps_add_to_cart(
        product_id: ProductId,
        qty: Qty = 1,
        variant: Annotated[str, Field(description="サイズ等のバリアント（該当商品のみ。例: 'M'）")] = "",
    ) -> CallToolResult:
        return _add_to_cart_impl(product_id, qty, variant, "apps_add_to_cart", "MCP_APPS")

    @_apps_tool(
        description="カート内商品の数量を変更する。qty=0 で削除と同等。対応ホストでは対話UIで表示される。UI不要なら update_cart。",
        annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True),
        meta=_UI_META,
    )
    def apps_update_cart(item_key: ItemKey, qty: QtyOrZero) -> CallToolResult:
        return _update_cart_impl(item_key, qty, "apps_update_cart", "MCP_APPS")

    @_apps_tool(
        description="カートから商品を削除する。対応ホストでは対話UIで表示される。UI不要なら remove_from_cart。",
        annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=True),
        meta=_UI_META,
    )
    def apps_remove_from_cart(item_key: ItemKey) -> CallToolResult:
        return _remove_from_cart_impl(item_key, "apps_remove_from_cart", "MCP_APPS")

    @_apps_tool(
        description=(
            "共有デモカートの内容を「注文内容の確認」として提示する（第1段階）。"
            "明細・合計をスナップショットした未確定注文（pending）を作り、内容を返す。"
            "対応ホストでは内容が対話UIで表示される。UI不要なら preview_order。"
            "実際の決済・発送は行われない（勉強会デモ用）。"
        ),
        annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False),
        meta=_UI_META,
    )
    def apps_preview_order() -> CallToolResult:
        return _preview_order_impl("apps_preview_order", "MCP_APPS")

    @_apps_tool(
        description=(
            "preview_order / apps_preview_order で提示した内容を「デモ注文」として確定する（第2段階）。"
            "提示と同じスナップショットが確定され、確定後カートは空になる。"
            "preview を先に実行すること。カートを変更すると提示はキャンセルされる。"
            "対応ホストでは対話UIで表示される。UI不要なら confirm_order。"
            "実際の決済・発送・在庫確定は一切行われない（勉強会デモ用の記録のみ）。"
        ),
        annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=False),
        meta=_UI_META,
    )
    def apps_confirm_order() -> CallToolResult:
        return _confirm_order_impl("apps_confirm_order", "MCP_APPS")

    @_apps_tool(
        description="デモ用に共有カートを空にして初期状態へ戻す。対応ホストでは対話UIで表示される。UI不要なら reset_demo。",
        annotations=ToolAnnotations(destructive_hint=True, idempotent_hint=True),
        meta=_UI_META,
    )
    def apps_reset_demo() -> CallToolResult:
        return _reset_demo_impl("apps_reset_demo", "MCP_APPS")

    return mcp
