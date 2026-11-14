"""REST API のテスト（FastAPI TestClient 経由）。"""

import os
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["STAPY_DB"] = tempfile.mktemp(suffix=".db")

from stapy_shop.api import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    # MCP session_manager.run() は1回しか起動できないため module スコープ
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _reset(client):
    client.post("/api/demo/reset")


class TestCatalogApi:
    def test_products(self, client):
        r = client.get("/api/products")
        assert r.status_code == 200
        assert r.json()["count"] == 20
        assert len(r.json()["products"]) == 20

    def test_product_detail(self, client):
        r = client.get("/api/products/lt-timer")
        assert r.status_code == 200
        p = r.json()
        assert p["name"] == "LT専用5分タイマー" and p["price"] == 2300

    def test_product_404(self, client):
        r = client.get("/api/products/nope")
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "product_not_found"

    def test_categories(self, client):
        r = client.get("/api/categories")
        assert r.status_code == 200
        assert len(r.json()["categories"]) == 7

    def test_search_filters(self, client):
        r = client.get("/api/products", params={"q": "LT", "max_price": 3000})
        ids = {p["id"] for p in r.json()["products"]}
        assert "lt-timer" in ids


class TestCartApi:
    def test_add_get(self, client):
        r = client.post("/api/cart/items", json={"product_id": "lt-timer", "qty": 1})
        assert r.status_code == 200
        cart = r.json()
        assert cart["total"] == 2300

    def test_cart_persists(self, client):
        client.post("/api/cart/items", json={"product_id": "sticker-set", "qty": 2})
        cart = client.get("/api/cart").json()
        assert cart["count"] == 2 and cart["total"] == 800

    def test_invalid_product(self, client):
        r = client.post("/api/cart/items", json={"product_id": "nope", "qty": 1})
        assert r.status_code == 404

    def test_qty_zero_rejected(self, client):
        r = client.post("/api/cart/items", json={"product_id": "lt-timer", "qty": 0})
        assert r.status_code == 422  # Pydantic ge=1

    def test_qty_negative_rejected(self, client):
        r = client.post("/api/cart/items", json={"product_id": "lt-timer", "qty": -1})
        assert r.status_code == 422

    def test_over_stock(self, client):
        r = client.post("/api/cart/items", json={"product_id": "lt-timer", "qty": 25})
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "out_of_stock"

    def test_update_and_remove(self, client):
        client.post("/api/cart/items", json={"product_id": "sticker-set", "qty": 1})
        r = client.patch("/api/cart/items/sticker-set|", json={"qty": 3})
        assert r.status_code == 200
        assert r.json()["total"] == 1200
        r = client.delete("/api/cart/items/sticker-set|")
        assert r.status_code == 200
        assert r.json()["items"] == []

    def test_order_confirm(self, client):
        """デモ注文確定: 明細スナップショット・注文番号・カート空化・GET参照。"""
        client.post("/api/cart/items", json={"product_id": "lt-timer", "qty": 1})
        client.post("/api/cart/items", json={"product_id": "sticker-set", "qty": 1})
        r = client.post("/api/orders")
        assert r.status_code == 200
        o = r.json()
        assert o["order_no"].startswith("STAPY-DEMO-")
        assert o["total"] == 2700 and o["count"] == 2 and o["demo"] is True
        assert len(o["items"]) == 2
        # 価格はサーバーマスター由来
        timer = next(i for i in o["items"] if i["product_id"] == "lt-timer")
        assert timer["price"] == 2300 and timer["subtotal"] == 2300
        # 確定後カートは空
        assert client.get("/api/cart").json()["items"] == []
        # 確定画面用の参照 API
        r2 = client.get(f"/api/orders/{o['order_no']}")
        assert r2.status_code == 200
        assert r2.json()["total"] == 2700 and r2.json()["channel"] == "WEB"

    def test_order_confirm_empty_cart(self, client):
        r = client.post("/api/orders")
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "cart_empty"

    def test_order_not_found(self, client):
        assert client.get("/api/orders/STAPY-DEMO-99999").status_code == 404

    def test_no_payment_endpoint(self, client):
        """実決済エンドポイントは存在しない（orders はデモ記録のみ）。"""
        for path in ("/api/checkout", "/api/pay", "/api/purchase", "/api/payment"):
            assert client.post(path, json={}).status_code == 404

    def test_session_isolation(self, client):
        client.post("/api/cart/items?session=a", json={"product_id": "sticker-set", "qty": 1})
        assert client.get("/api/cart?session=b").json()["items"] == []
        assert client.get("/api/cart?session=a").json()["count"] == 1
        client.post("/api/demo/reset?session=a")


class TestDemoApi:
    def test_reset(self, client):
        client.post("/api/cart/items", json={"product_id": "lt-timer", "qty": 1})
        r = client.post("/api/demo/reset")
        assert r.status_code == 200
        assert client.get("/api/cart").json()["items"] == []

    def test_logs(self, client):
        client.post("/api/cart/items", json={"product_id": "lt-timer", "qty": 1})
        logs = client.get("/api/demo/logs").json()["logs"]
        assert any(l["channel"] == "WEB" and l["action"] == "add_to_cart" for l in logs)

    def test_webmcp_channel(self, client):
        client.post(
            "/api/cart/items",
            json={"product_id": "mug", "qty": 1},
            headers={"x-stapy-channel": "webmcp"},
        )
        logs = client.get("/api/demo/logs").json()["logs"]
        assert any(l["channel"] == "WEBMCP" and l["action"] == "add_to_cart" for l in logs)


class TestPages:
    @pytest.mark.parametrize("path", ["/", "/index.html", "/detail.html", "/logs.html",
                                      "/order_complete.html",
                                      "/stapy_shop_一覧.html", "/stapy_shop_詳細.html"])
    def test_pages(self, client, path):
        assert client.get(path).status_code == 200

    def test_static_js(self, client):
        for js in ("/static/shop.js", "/static/webmcp.js"):
            assert client.get(js).status_code == 200

    def test_images(self, client):
        assert client.get("/images/sticker-set.webp").status_code == 200
        assert client.get("/images/lt-timer.webp").status_code == 200
