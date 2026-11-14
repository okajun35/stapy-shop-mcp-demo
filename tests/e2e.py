#!/usr/bin/env python3
"""stapy商店 E2E テスト（Playwright）。

使い方:
    python3 tests/e2e.py [--headed]

前提:
    - サーバーが http://127.0.0.1:8000 で起動中（python -m stapy_shop）
    - システム python3 に playwright が入っている
    - /usr/bin/google-chrome（通常Web確認・WebMCP非対応確認）
    - /snap/bin/chromium（WebMCP対応確認, --enable-experimental-web-platform-features）

検証内容:
    WEB      : 商品一覧20件・検索・詳細遷移・カート追加/変更/削除・リロード永続化・リセット
    WEBMCP   : document.modelContext が有効なブラウザで getTools/executeTool による
               実ツール呼び出しと画面反映（公式API経路のみ使用）
    FALLBACK : WebMCP非対応ブラウザで通常機能が壊れないこと
"""

from __future__ import annotations

import json
import sys
import urllib.request

BASE = "http://127.0.0.1:8000"
CHROME = "/usr/bin/google-chrome"
CHROMIUM = "/snap/bin/chromium"

PASS, FAIL = "PASS", "FAIL"
results: list[tuple[str, str, str]] = []


def report(name: str, ok: bool, note: str = "") -> None:
    results.append(("OK" if ok else "NG", name, note))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {note}" if note else ""))


def api(path: str, method: str = "GET", body: dict | None = None):
    req = urllib.request.Request(
        BASE + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def launch(p, executable, extra_args=()):
    return p.chromium.launch(
        headless=True,
        executable_path=executable,
        args=["--no-sandbox", "--disable-gpu", *extra_args],
    )


def test_web(p):
    print("\n=== WEB: 通常ブラウザ操作 ===")
    api("/api/demo/reset", "POST")
    browser = launch(p, CHROME)
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))

    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_timeout(1500)
    report("一覧: 20件表示", page.locator(".product-card").count() == 20,
           f"{page.locator('.product-card').count()}件")
    imgs = page.locator(".product-card img")
    ok_imgs = all(
        page.evaluate("(el) => el.complete && el.naturalWidth > 0", imgs.nth(i).element_handle())
        for i in range(min(20, imgs.count()))
    )
    report("一覧: 商品画像読み込み", ok_imgs)
    report("一覧: WebMCPバッジなし(非対応)", page.locator(".webmcp-badge").count() == 0)

    # 検索（LT + 価格上限）
    page.fill("#site-search", "LT")
    page.evaluate("document.getElementById('price-filter').value = 3000")
    page.evaluate("document.getElementById('price-filter').dispatchEvent(new Event('input'))")
    page.wait_for_timeout(600)
    n = page.locator(".product-card").count()
    names = page.locator(".product-card h3").all_inner_texts()
    report("検索: LT+¥3000以下", n >= 1 and any("タイマー" in t for t in names), f"{n}件 {names}")

    # 詳細遷移
    page.locator(".product-card a.image-link").first.click()
    page.wait_for_timeout(1200)
    report("詳細: 商品ページ遷移", "/detail.html" in page.url and page.locator("h1").count() >= 1,
           page.url)
    report("詳細: 価格表示", "¥" in page.locator(".detail-price").inner_text())

    # 一覧に戻ってカート追加
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_timeout(1200)
    page.locator("[data-add='lt-timer']").click()
    page.wait_for_timeout(800)
    report("カート: バッジ1", page.locator(".cart-count").first.inner_text() == "1")
    page.locator("[data-add='sticker-set']").click()
    page.wait_for_timeout(800)
    report("カート: バッジ2", page.locator(".cart-count").first.inner_text() == "2")

    # ドロワーで合計確認（2300+400=2700 デモシナリオ）
    page.locator("#cart-button").click()
    page.wait_for_timeout(800)
    total = page.locator("#cart-total").inner_text()
    report("カート: 合計¥2,700", "2,700" in total, total)
    report("サーバー側も¥2700", api("/api/cart")["total"] == 2700)

    # 数量変更（＋ボタン）
    page.locator("[data-cart-op='plus']").first.click()
    page.wait_for_timeout(800)
    report("カート: 数量+1", api("/api/cart")["count"] == 3)
    # 削除
    page.locator("[data-cart-op='remove']").first.click()
    page.wait_for_timeout(800)

    # リロード永続化
    page.reload(wait_until="domcontentloaded")
    page.wait_for_timeout(1500)
    report("リロード後もカート維持", api("/api/cart")["count"] >= 1,
           f"{api('/api/cart')['count']}点")

    # 注文確定（デモ）→ 確定画面へ遷移
    page.locator("#cart-button").click()
    page.wait_for_timeout(600)
    page.locator("#mock-checkout").click()
    page.wait_for_url("**/order_complete.html**", timeout=8000)
    page.wait_for_timeout(800)
    report("注文確定: 確定画面へ遷移", "order=" in page.url, page.url)
    report("注文確定: デモ明記", "実際の注文・決済・発送・在庫確定は一切行われません" in page.locator(".demo-warning").inner_text())
    report("注文確定: 明細表示", page.locator(".oitem").count() >= 1)
    report("注文確定: サーバーカート空", api("/api/cart")["items"] == [])

    # デモリセット（ヘッダのボタンは確定ページにもある）
    page.locator("#demo-reset").click()
    page.wait_for_timeout(800)
    report("デモリセット", api("/api/cart")["items"] == [])

    # お気に入りはlocalStorage（UI限定機能でカートではない）
    report("JSエラーなし", not errors, "; ".join(errors[:3]))
    page.screenshot(path="/tmp/e2e_web.png", full_page=False)
    browser.close()


def test_webmcp(p):
    print("\n=== WEBMCP: 対応ブラウザでのツール呼び出し ===")
    api("/api/demo/reset", "POST")
    browser = launch(p, CHROMIUM, ["--enable-experimental-web-platform-features"])
    page = browser.new_page(viewport={"width": 1300, "height": 900})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_timeout(2500)

    report("WebMCP API存在", page.evaluate("typeof document.modelContext") == "object")
    tools = page.evaluate("async () => (await document.modelContext.getTools()).map(t => t.name)")
    expect = {"search_products", "get_product", "get_cart", "add_to_cart",
              "update_cart", "remove_from_cart", "confirm_order"}
    report("7ツール登録", expect <= set(tools), str(sorted(tools)))
    report("WebMCPバッジ表示", page.locator(".webmcp-badge").count() == 1)

    # AIがツールを実行 → 画面に反映
    out = page.evaluate("""async () => {
        const ts = await document.modelContext.getTools();
        const t = ts.find(t => t.name === 'search_products');
        return await document.modelContext.executeTool(t, {query: 'LT', max_price: 3000});
    }""")
    data = json.loads(out)
    report("AI検索→結果3件", data["count"] == 3, str(data["count"]))
    page.wait_for_timeout(1200)
    report("AI検索→画面も3件に絞込", page.locator(".product-card").count() == 3,
           f"{page.locator('.product-card').count()}枚")

    out = page.evaluate("""async () => {
        const ts = await document.modelContext.getTools();
        const t = ts.find(t => t.name === 'add_to_cart');
        return await document.modelContext.executeTool(t, {product_id: 'lt-timer', qty: 1});
    }""")
    cart = json.loads(out)
    report("AIカート追加", any(i["product_id"] == "lt-timer" for i in cart["items"]))
    page.wait_for_timeout(1200)
    report("画面バッジ更新", page.locator(".cart-count").first.inner_text() == "1")
    report("サーバーカート一致", api("/api/cart")["total"] == 2300)

    out = page.evaluate("""async () => {
        const ts = await document.modelContext.getTools();
        const t = ts.find(t => t.name === 'get_cart');
        return await document.modelContext.executeTool(t, {});
    }""")
    report("AIカート確認", json.loads(out)["total"] == 2300)

    # AIが注文確定 → 画面も確定ページへ遷移
    out = page.evaluate("""async () => {
        const ts = await document.modelContext.getTools();
        const t = ts.find(t => t.name === 'confirm_order');
        return await document.modelContext.executeTool(t, {});
    }""")
    order = json.loads(out)
    report("AI注文確定", order["order_no"].startswith("STAPY-DEMO-") and order["demo"] is True,
           order.get("order_no", ""))
    page.wait_for_url("**/order_complete.html**", timeout=8000)
    page.wait_for_timeout(800)
    report("AI確定→画面も確定ページ", "order=" in page.url)
    report("確定後カート空", api("/api/cart")["items"] == [])

    # ログに WEBMCP で記録されているか
    logs = api("/api/demo/logs?limit=10")["logs"]
    report("ログにWEBMCP記録", any(l["channel"] == "WEBMCP" for l in logs))
    report("ログにconfirm_order記録", any(l["action"] == "confirm_order" for l in logs))
    report("JSエラーなし", not errors, "; ".join(errors[:3]))
    page.screenshot(path="/tmp/e2e_webmcp.png", full_page=False)
    browser.close()


def test_fallback(p):
    print("\n=== FALLBACK: WebMCP非対応ブラウザ ===")
    api("/api/demo/reset", "POST")
    browser = launch(p, CHROME)  # Chrome144: document.modelContext なし
    page = browser.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_timeout(1500)
    report("modelContext未定義", page.evaluate("typeof document.modelContext") == "undefined")
    page.locator("[data-add='mug']").click()
    page.wait_for_timeout(800)
    report("通常カート操作可能", api("/api/cart")["count"] == 1)
    report("JSエラーなし", not errors, "; ".join(errors[:3]))
    browser.close()


def main() -> int:
    from playwright.sync_api import sync_playwright

    try:
        api("/api/products")
    except Exception:
        print("サーバーが http://127.0.0.1:8000 で起動していません。python -m stapy_shop を先に実行してください。")
        return 2

    with sync_playwright() as p:
        test_web(p)
        test_webmcp(p)
        test_fallback(p)

    fails = [r for r in results if r[0] == "NG"]
    print(f"\n=== E2E結果: {len(results) - len(fails)}/{len(results)} PASS ===")
    api("/api/demo/reset", "POST")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
