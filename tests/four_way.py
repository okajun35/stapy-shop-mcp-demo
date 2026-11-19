#!/usr/bin/env python3
"""4方式統合テスト。

同じデモシナリオ「予算3,000円以内でLT登壇者へのプレゼントを探してカートへ」
を4経路すべてで実行し、カート結果が一致することを確認する。

  1. WEB      : REST API（ブラウザ shop.js と同じ呼び出し）
  2. MCP      : 公式MCPクライアント（Streamable HTTP）
  3. MCP_APPS : Apps拡張ネゴシエーション済みクライアント経由の ui_* ツール
  4. WEBMCP   : Chromium + document.modelContext.getTools/executeTool

各方式で lt-timer(¥2,300)×1 + sticker-set(¥400)×1 = ¥2,700 になることを確認し、
続けて各方式の「注文確定（デモ）」操作で注文が記録されること、
ログの channel が WEB / MCP / MCP_APPS / WEBMCP で区別されることを確認する。
"""

from __future__ import annotations

import json
import sys
import urllib.request

BASE = "http://127.0.0.1:8000"


def api(path, method="GET", body=None, headers=None):
    req = urllib.request.Request(
        BASE + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def reset():
    api("/api/demo/reset", "POST")


def cart_sig(cart):
    items = sorted((i["product_id"], i["qty"]) for i in cart["items"])
    return {"items": items, "total": cart["total"], "count": cart["count"]}


EXPECTED = {"items": [("lt-timer", 1), ("sticker-set", 1)], "total": 2700, "count": 2}
results = {}


# --- 1. WEB (REST) -----------------------------------------------------------
def via_web():
    reset()
    api("/api/products?q=LT&max_price=3000")
    api("/api/cart/items", "POST", {"product_id": "lt-timer", "qty": 1})
    cart = api("/api/cart/items", "POST", {"product_id": "sticker-set", "qty": 1})
    api("/api/orders/preview", "POST")
    order = api("/api/orders/confirm", "POST")
    return cart_sig(cart), order


# --- 2. MCP ------------------------------------------------------------------
async def via_mcp():
    from mcp import Client

    reset()
    async with Client(BASE + "/mcp") as client:
        await client.call_tool("search_products", {"q": "LT", "max_price": 3000})
        await client.call_tool("add_to_cart", {"product_id": "lt-timer", "qty": 1})
        await client.call_tool("add_to_cart", {"product_id": "sticker-set", "qty": 1})
        r = await client.call_tool("get_cart", {})
        sig = cart_sig(r.structured_content)
        p = await client.call_tool("preview_order", {})
        assert not p.is_error, p.content[0].text
        o = await client.call_tool("confirm_order", {})
        assert not o.is_error, o.content[0].text
        return sig, o.structured_content


# --- 3. MCP_APPS -------------------------------------------------------------
async def via_mcp_apps():
    from mcp import Client
    from mcp.client import advertise
    from mcp.server.apps import APP_MIME_TYPE, EXTENSION_ID

    reset()
    ext = advertise(EXTENSION_ID, {"mimeTypes": [APP_MIME_TYPE]})
    async with Client(BASE + "/mcp-apps", extensions=[ext]) as client:
        await client.call_tool("ui_search_products", {"q": "LT", "max_price": 3000})
        await client.call_tool("ui_add_to_cart", {"product_id": "lt-timer", "qty": 1})
        await client.call_tool("ui_add_to_cart", {"product_id": "sticker-set", "qty": 1})
        r = await client.call_tool("ui_get_cart", {})
        sig = cart_sig(r.structured_content)
        p = await client.call_tool("ui_preview_order", {})
        assert not p.is_error, p.content[0].text
        o = await client.call_tool("ui_confirm_order", {})
        assert not o.is_error, o.content[0].text
        return sig, o.structured_content


# --- 4. WEBMCP ---------------------------------------------------------------
def via_webmcp():
    from playwright.sync_api import sync_playwright

    reset()
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            executable_path="/snap/bin/chromium",
            args=["--no-sandbox", "--disable-gpu", "--enable-experimental-web-platform-features"],
        )
        page = browser.new_page()
        page.goto(BASE + "/", wait_until="domcontentloaded")
        page.wait_for_timeout(2500)
        page.evaluate("""async () => {
            const ts = await document.modelContext.getTools();
            const t = ts.find(t => t.name === 'search_products');
            await document.modelContext.executeTool(t, {query: 'LT', max_price: 3000});
        }""")
        for pid in ("lt-timer", "sticker-set"):
            page.evaluate(
                """async (pid) => {
                    const ts = await document.modelContext.getTools();
                    const t = ts.find(t => t.name === 'add_to_cart');
                    await document.modelContext.executeTool(t, {product_id: pid, qty: 1});
                }""",
                pid,
            )
        out = page.evaluate("""async () => {
            const ts = await document.modelContext.getTools();
            const t = ts.find(t => t.name === 'get_cart');
            return await document.modelContext.executeTool(t, {});
        }""")
        sig = cart_sig(json.loads(out))
        # preview → confirm の2段階（confirm は画面を確定ページへ遷移させる）
        out = page.evaluate("""async () => {
            const ts = await document.modelContext.getTools();
            const t = ts.find(t => t.name === 'preview_order');
            return await document.modelContext.executeTool(t, {});
        }""")
        assert json.loads(out)["status"] == "pending"
        out = page.evaluate("""async () => {
            const ts = await document.modelContext.getTools();
            const t = ts.find(t => t.name === 'confirm_order');
            return await document.modelContext.executeTool(t, {});
        }""")
        order = json.loads(out)
        browser.close()
    return sig, order


def main() -> int:
    import anyio

    results["WEB"] = via_web()
    results["MCP"] = anyio.run(via_mcp)
    results["MCP_APPS"] = anyio.run(via_mcp_apps)
    results["WEBMCP"] = via_webmcp()

    print("\n=== 4方式のカート結果 ===")
    ok = True
    for name, (sig, _order) in results.items():
        match = sig == EXPECTED
        ok &= match
        print(f"  {name:8s} {sig}  {'== 期待値' if match else '!! 不一致'}")

    print("\n=== 4方式の注文確定（デモ） ===")
    for name, (_sig, order) in results.items():
        good = (order["order_no"].startswith("STAPY-DEMO-")
                and order["total"] == 2700 and order["demo"] is True)
        ok &= good
        print(f"  {name:8s} {order['order_no']} ¥{order['total']} demo={order['demo']}  {'OK' if good else '!! NG'}")

    # 各経路のログチャネル確認
    print("\n=== 操作ログ（channel 別） ===")
    logs = api("/api/demo/logs?limit=60")["logs"]
    for ch in ("WEBMCP", "MCP_APPS", "MCP", "WEB"):
        n = sum(1 for l in logs if l["channel"] == ch)
        n_order = sum(1 for l in logs if l["channel"] == ch and l["action"] == "confirm_order")
        print(f"  {ch:8s} {n}件（confirm_order {n_order}件）")
        ok &= n > 0 and n_order > 0

    reset()
    print(f"\n{'=== 4方式一致: PASS ===' if ok else '=== 不一致: FAIL ==='}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
