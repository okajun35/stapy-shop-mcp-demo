"""FastAPI アプリケーション。

静的ファイル（既存EC画面）・REST API・MCP（Streamable HTTP /mcp）を
1つの uvicorn プロセスで提供する。カートはサーバー側 SQLite で管理し、
localStorage は使わない（MCP 経由との状態共有のため）。
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Header, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .db import Database
from .mcp_server import build_mcp_server
from .service import DEMO_SESSION_ID, ShopError, ShopService

STATIC_DIR = Path(__file__).parent / "static"

BASE_URL = os.environ.get("STAPY_BASE_URL", "http://127.0.0.1:8000")
DB_PATH = os.environ.get("STAPY_DB", str(Path(__file__).parent.parent / "stapy_shop.db"))

db = Database(DB_PATH)
service = ShopService(db)
mcp_server = build_mcp_server(service, BASE_URL)
mcp_asgi = mcp_server.streamable_http_app()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # マウントした MCP アプリの lifespan は Starlette が実行しないため、
    # session_manager をここで起動する（SDK 公式のマウント手順）。
    async with mcp_server.session_manager.run():
        yield


app = FastAPI(title="stapy商店 MCPデモ", lifespan=lifespan)


# ---------------------------------------------------------------------------
# エラーハンドリング / セッション / チャネル識別
# ---------------------------------------------------------------------------

_STATUS = {
    "product_not_found": 404,
    "item_not_found": 404,
    "order_not_found": 404,
    "invalid_input": 400,
    "cart_empty": 409,
    "out_of_stock": 409,
    "no_pending_order": 409,
}


@app.exception_handler(ShopError)
async def shop_error_handler(_: Request, e: ShopError) -> JSONResponse:
    return JSONResponse(
        status_code=_STATUS.get(e.code, 400),
        content={"error": {"code": e.code, "message": e.message}},
    )


def _session(request: Request) -> str:
    """デモセッション。共通の "demo" を既定とし、?session= かヘッダで変更可。

    ローカルデモ専用の単純な識別子。外部公開する場合は認証付きの
    セッション発行に置き換えること（README 参照）。
    """
    return (
        request.query_params.get("session")
        or request.headers.get("x-stapy-session")
        or DEMO_SESSION_ID
    )


def _channel(request: Request) -> Literal["WEB", "WEBMCP"]:
    """ブラウザからの呼び出し経路の識別（デモ用のベストエフォート）。

    WebMCP ツールの execute コールバックだけが X-Stapy-Channel: webmcp を
    付ける。ブラウザ送信値なので監査上の事実ではなくデモ用の目印。
    MCP / MCP_APPS はサーバー側で確定的に識別される。
    """
    return "WEBMCP" if request.headers.get("x-stapy-channel") == "webmcp" else "WEB"


# ---------------------------------------------------------------------------
# REST API
# ---------------------------------------------------------------------------


@app.get("/api/products")
def api_products(
    request: Request,
    q: str = "",
    category: str | None = None,
    max_price: int | None = None,
    in_stock: bool = False,
    featured: bool = False,
    sort: Literal["recommended", "price-asc", "price-desc", "name"] = "recommended",
):
    return service.search_products(
        q=q,
        categories=[category] if category else None,
        max_price=max_price,
        in_stock_only=in_stock,
        featured_only=featured,
        sort=sort,
    )


@app.get("/api/categories")
def api_categories():
    return {"categories": service.list_categories()}


@app.get("/api/products/{product_id}")
def api_product(product_id: str):
    return service.get_product(product_id)


@app.get("/api/cart")
def api_cart(request: Request):
    return service.get_cart(_session(request))


class AddToCartBody(BaseModel):
    product_id: str
    qty: int = Field(default=1, ge=1, le=99)
    variant: str = ""


@app.post("/api/cart/items")
def api_cart_add(body: AddToCartBody, request: Request):
    return service.add_to_cart(
        body.product_id, body.qty, body.variant, _session(request), channel=_channel(request)
    )


class UpdateCartBody(BaseModel):
    qty: int = Field(ge=0, le=99)


@app.patch("/api/cart/items/{item_key}")
def api_cart_update(item_key: str, body: UpdateCartBody, request: Request):
    return service.update_cart(item_key, body.qty, _session(request), channel=_channel(request))


@app.delete("/api/cart/items/{item_key}")
def api_cart_remove(item_key: str, request: Request):
    return service.remove_from_cart(item_key, _session(request), channel=_channel(request))


@app.post("/api/demo/reset")
def api_demo_reset(request: Request):
    return service.reset_demo(_session(request), channel=_channel(request))


@app.get("/api/demo/logs")
def api_demo_logs(limit: int = Query(default=100, ge=1, le=500)):
    return {"logs": service.operation_logs(limit)}


# デモ注文の2段階フロー。実際の決済・発送・在庫確定は行われない（記録のみ）。
# preview で内容を提示（pending 保存）→ confirm で確定＋カート空化。
# カート変更で pending は自動キャンセルされる。
@app.post("/api/orders/preview")
def api_order_preview(request: Request):
    return service.preview_order(_session(request), channel=_channel(request))


@app.post("/api/orders/confirm")
def api_order_confirm(request: Request):
    return service.confirm_order(_session(request), channel=_channel(request))


@app.get("/api/orders/{order_no}")
def api_order_get(order_no: str):
    return service.get_order(order_no)


# ---------------------------------------------------------------------------
# 画面（既存HTML + ログビューア）
# ---------------------------------------------------------------------------


def _page(name: str) -> FileResponse:
    return FileResponse(STATIC_DIR / name, media_type="text/html")


@app.get("/", include_in_schema=False)
def page_index():
    return _page("index.html")


@app.get("/index.html", include_in_schema=False)
def page_index_html():
    return _page("index.html")


@app.get("/detail.html", include_in_schema=False)
def page_detail():
    return _page("detail.html")


@app.get("/logs.html", include_in_schema=False)
def page_logs():
    return _page("logs.html")


@app.get("/order_complete.html", include_in_schema=False)
def page_order_complete():
    return _page("order_complete.html")


# 旧ファイル名からのリダイレクト相当（直接ファイルを返す）
@app.get("/stapy_shop_一覧.html", include_in_schema=False)
def page_legacy_index():
    return _page("index.html")


@app.get("/stapy_shop_詳細.html", include_in_schema=False)
def page_legacy_detail():
    return _page("detail.html")


app.mount("/images", StaticFiles(directory=STATIC_DIR / "images"), name="images")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# MCP（Streamable HTTP）。内部ルートは /mcp。最後にマウントし、
# /api/*・/images/* などを先のルートで処理させる。
app.mount("/", mcp_asgi, name="mcp")


def main() -> None:
    import uvicorn

    # WSL から Windows 側ブラウザへ届かせるため既定は 0.0.0.0。
    # ローカルのみに閉じたい場合は HOST=127.0.0.1 を指定。
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("stapy_shop.api:app", host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
