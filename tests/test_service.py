"""サービス層の単体テスト（REST/MCP/MCP Apps/WebMCP が共有するロジック）。"""

import concurrent.futures

import pytest

from stapy_shop.products import CATEGORIES, PRODUCTS, PRODUCTS_BY_ID
from stapy_shop.service import DEMO_SESSION_ID, ShopError


class TestCatalog:
    def test_20_products(self):
        assert len(PRODUCTS) == 20
        assert len({p["id"] for p in PRODUCTS}) == 20

    def test_required_products_exist(self):
        for pid in ("sticker-set", "lt-timer"):
            assert pid in PRODUCTS_BY_ID
        assert PRODUCTS_BY_ID["sticker-set"]["price"] == 400
        assert PRODUCTS_BY_ID["lt-timer"]["price"] == 2300

    def test_categories(self):
        assert len(CATEGORIES) == 7
        assert "デスク周り" in CATEGORIES

    def test_product_fields_and_images(self, service):
        for p in service.list_products():
            for key in ("id", "name", "price", "category", "image", "desc", "stock"):
                assert key in p, f"{p['id']} lacks {key}"
            assert p["image"].startswith("/images/")
            assert p["price"] > 0


class TestSearch:
    def test_all(self, service):
        assert service.search_products()["count"] == 20

    def test_keyword_lt(self, service):
        r = service.search_products(q="LT", max_price=3000)
        ids = {p["id"] for p in r["products"]}
        assert "lt-timer" in ids
        assert r["count"] >= 1

    def test_max_price(self, service):
        r = service.search_products(max_price=3000)
        assert all(p["price"] <= 3000 for p in r["products"])

    def test_category(self, service):
        r = service.search_products(categories=["デスク周り"])
        assert r["count"] >= 1
        assert all(p["category"] == "デスク周り" for p in r["products"])

    def test_sort_price(self, service):
        prices = [p["price"] for p in service.search_products(sort="price-asc")["products"]]
        assert prices == sorted(prices)

    def test_no_match(self, service):
        assert service.search_products(q="存在しない商品xyz")["count"] == 0

    def test_negative_max_price(self, service):
        with pytest.raises(ShopError):
            service.search_products(max_price=-1)


class TestCart:
    def test_add_and_total(self, service):
        cart = service.add_to_cart("lt-timer", 1)
        cart = service.add_to_cart("sticker-set", 1)
        assert cart["count"] == 2
        assert cart["total"] == 2700  # LTタイマー2300 + ステッカー400（デモシナリオ）

    def test_price_is_server_side(self, service):
        """クライアントが価格を送信する経路は存在しない。
        add_to_cart の戻り値の price/subtotal は商品マスター由来であることを確認。"""
        cart = service.add_to_cart("sticker-set", 2)
        item = next(i for i in cart["items"] if i["product_id"] == "sticker-set")
        assert item["price"] == 400  # マスターの価格
        assert item["subtotal"] == 800

    def test_qty_accumulates(self, service):
        service.add_to_cart("sticker-set", 1)
        cart = service.add_to_cart("sticker-set", 2)
        item = next(i for i in cart["items"] if i["product_id"] == "sticker-set")
        assert item["qty"] == 3

    def test_invalid_product(self, service):
        with pytest.raises(ShopError) as e:
            service.add_to_cart("no-such-product", 1)
        assert e.value.code == "product_not_found"

    @pytest.mark.parametrize("qty", [0, -1, -100])
    def test_invalid_qty(self, service, qty):
        with pytest.raises(ShopError) as e:
            service.add_to_cart("sticker-set", qty)
        assert e.value.code == "invalid_input"

    def test_qty_over_stock(self, service):
        stock = PRODUCTS_BY_ID["lt-timer"]["stock"]
        with pytest.raises(ShopError) as e:
            service.add_to_cart("lt-timer", stock + 1)
        assert e.value.code == "out_of_stock"

    def test_qty_accumulated_over_stock(self, service):
        stock = PRODUCTS_BY_ID["lt-timer"]["stock"]
        service.add_to_cart("lt-timer", stock)
        with pytest.raises(ShopError) as e:
            service.add_to_cart("lt-timer", 1)
        assert e.value.code == "out_of_stock"

    def test_invalid_variant(self, service):
        with pytest.raises(ShopError):
            service.add_to_cart("sticker-set", 1, variant="M")  # ステッカーにサイズはない

    def test_variant_cart_separate(self, service):
        p = next(p for p in PRODUCTS if p.get("variants"))
        v = p["variants"][0]
        cart = service.add_to_cart(p["id"], 1, variant=v)
        assert cart["items"][0]["key"] == f"{p['id']}|{v}"

    def test_update_cart(self, service):
        service.add_to_cart("sticker-set", 1)
        cart = service.update_cart("sticker-set|", 3)
        item = next(i for i in cart["items"] if i["key"] == "sticker-set|")
        assert item["qty"] == 3

    def test_update_cart_zero_removes(self, service):
        service.add_to_cart("sticker-set", 1)
        cart = service.update_cart("sticker-set|", 0)
        assert cart["items"] == []

    def test_update_cart_missing_item(self, service):
        with pytest.raises(ShopError) as e:
            service.update_cart("sticker-set|", 2)
        assert e.value.code == "item_not_found"

    def test_remove_from_cart(self, service):
        service.add_to_cart("sticker-set", 1)
        cart = service.remove_from_cart("sticker-set|")
        assert cart["items"] == []

    def test_remove_missing(self, service):
        with pytest.raises(ShopError) as e:
            service.remove_from_cart("sticker-set|")
        assert e.value.code == "item_not_found"

    def test_sessions_are_isolated(self, service):
        service.add_to_cart("sticker-set", 1, session_id="demo")
        assert service.get_cart("other")["items"] == []

    def test_reset(self, service):
        service.add_to_cart("lt-timer", 1)
        result = service.reset_demo(DEMO_SESSION_ID)
        assert result["ok"] and result["cart"]["items"] == []
        assert service.get_cart()["items"] == []


class TestOrders:
    def test_preview_then_confirm(self, service):
        """2段階: preview で提示 → confirm で確定＋カート空化。"""
        service.add_to_cart("lt-timer", 1)
        service.add_to_cart("sticker-set", 2)
        p = service.preview_order(DEMO_SESSION_ID, channel="MCP")
        assert p["status"] == "pending"
        assert p["order_no"].startswith("STAPY-DEMO-")
        assert p["total"] == 3100 and p["count"] == 3
        # preview 時点ではカートは残る・何も確定されない
        assert service.get_cart()["count"] == 3
        o = service.confirm_order(DEMO_SESSION_ID, channel="MCP")
        assert o["order_no"] == p["order_no"] and o["status"] == "confirmed"
        assert o["total"] == 3100 and o["count"] == 3 and o["demo"] is True
        assert service.get_cart()["items"] == []
        got = service.get_order(o["order_no"])
        assert got["total"] == 3100 and got["channel"] == "MCP" and got["status"] == "confirmed"

    def test_confirm_without_preview(self, service):
        """preview なしの confirm はエラー（承認なしでは確定しない）。"""
        service.add_to_cart("lt-timer", 1)
        with pytest.raises(ShopError) as e:
            service.confirm_order()
        assert e.value.code == "no_pending_order"

    def test_cart_mutation_cancels_pending(self, service):
        """提示後にカートを変更すると pending は無効化される。"""
        service.add_to_cart("lt-timer", 1)
        service.preview_order()
        service.add_to_cart("sticker-set", 1)  # 提示後のカート変更
        with pytest.raises(ShopError) as e:
            service.confirm_order()
        assert e.value.code == "no_pending_order"
        # 再提示すれば新しい内容で確定できる
        p2 = service.preview_order()
        assert p2["total"] == 2700
        o = service.confirm_order()
        assert o["total"] == 2700 and o["status"] == "confirmed"

    def test_reset_cancels_pending(self, service):
        service.add_to_cart("mug", 1)
        service.preview_order()
        service.reset_demo()
        with pytest.raises(ShopError) as e:
            service.confirm_order()
        assert e.value.code == "no_pending_order"

    def test_preview_empty_cart(self, service):
        with pytest.raises(ShopError) as e:
            service.preview_order()
        assert e.value.code == "cart_empty"

    def test_repreview_replaces_pending(self, service):
        """再 preview は古い pending を置き換え、確定は新しい方になる。"""
        service.add_to_cart("mug", 1)
        p1 = service.preview_order()
        p2 = service.preview_order()
        assert p1["order_no"] != p2["order_no"]
        o = service.confirm_order()
        assert o["order_no"] == p2["order_no"]

    def test_order_price_from_master(self, service):
        """注文の価格・合計は提示時点の商品マスターから計算される。"""
        service.add_to_cart("sticker-set", 1)
        service.preview_order()
        o = service.confirm_order()
        item = o["items"][0]
        assert item["price"] == 400 and item["subtotal"] == 400 and o["total"] == 400

    def test_order_logged(self, service):
        service.add_to_cart("mug", 1)
        p = service.preview_order(DEMO_SESSION_ID, channel="WEBMCP")
        o = service.confirm_order(DEMO_SESSION_ID, channel="WEBMCP")
        logs = service.operation_logs(10)
        assert any(l["action"] == "preview_order" and l["channel"] == "WEBMCP" for l in logs)
        assert any(l["action"] == "confirm_order" and l["channel"] == "WEBMCP"
                   and o["order_no"] in l["detail"] for l in logs)

    def test_order_not_found(self, service):
        with pytest.raises(ShopError) as e:
            service.get_order("STAPY-DEMO-99999")
        assert e.value.code == "order_not_found"


class TestLogs:
    def test_channels(self, service):
        for ch in ("WEB", "MCP", "MCP_APPS", "WEBMCP"):
            service.add_to_cart("sticker-set", 1, session_id=f"s-{ch}", channel=ch)
        logs = service.operation_logs(50)
        channels = {l["channel"] for l in logs if l["action"] == "add_to_cart"}
        assert {"WEB", "MCP", "MCP_APPS", "WEBMCP"} <= channels

    def test_log_fields(self, service):
        service.add_to_cart("sticker-set", 1, channel="MCP")
        log = service.operation_logs(1)[0]
        for key in ("ts", "channel", "action", "detail", "session_id"):
            assert key in log
        assert log["channel"] == "MCP" and log["action"] == "add_to_cart"


class TestConcurrency:
    def test_parallel_adds(self, service):
        """同時に add_to_cart しても数量・合計が正しく保たれる。"""
        service.reset_demo()
        n = 10
        with concurrent.futures.ThreadPoolExecutor(max_workers=n) as ex:
            list(ex.map(lambda _: service.add_to_cart("sticker-set", 1), range(n)))
        cart = service.get_cart()
        item = next(i for i in cart["items"] if i["product_id"] == "sticker-set")
        assert item["qty"] == n
        assert cart["total"] == 400 * n
