"""SQLite 永続化層。

カートと操作ログだけを保持する。商品マスターは products.py が正本で、
DB には商品スナップショットを持たない（価格は常にマスターから引く）。
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS cart_items (
    session_id  TEXT NOT NULL,
    item_key    TEXT NOT NULL,
    product_id  TEXT NOT NULL,
    variant     TEXT NOT NULL DEFAULT '',
    qty         INTEGER NOT NULL CHECK (qty > 0),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (session_id, item_key)
);
CREATE TABLE IF NOT EXISTS op_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    channel    TEXT NOT NULL,
    action     TEXT NOT NULL,
    detail     TEXT NOT NULL DEFAULT '',
    session_id TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_op_log_id ON op_log(id);
CREATE TABLE IF NOT EXISTS orders (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    order_no   TEXT NOT NULL UNIQUE,
    session_id TEXT NOT NULL,
    items_json TEXT NOT NULL,
    total      INTEGER NOT NULL,
    channel    TEXT NOT NULL DEFAULT 'WEB',
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
"""


class Database:
    def __init__(self, path: str | Path = "stapy_shop.db") -> None:
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(SCHEMA)
        self._conn.commit()
        # RLock: add_to_cart がロック保持中に upsert_item 等を呼ぶため再入可能にする
        self._lock = threading.RLock()

    def close(self) -> None:
        self._conn.close()

    # --- cart -----------------------------------------------------------
    def get_cart_items(self, session_id: str) -> list[dict]:
        cur = self._conn.execute(
            "SELECT item_key, product_id, variant, qty FROM cart_items "
            "WHERE session_id = ? ORDER BY updated_at, item_key",
            (session_id,),
        )
        return [dict(r) for r in cur.fetchall()]

    def upsert_item(self, session_id: str, item_key: str, product_id: str, variant: str, qty: int) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO cart_items (session_id, item_key, product_id, variant, qty, updated_at) "
                "VALUES (?, ?, ?, ?, ?, datetime('now')) "
                "ON CONFLICT (session_id, item_key) "
                "DO UPDATE SET qty = excluded.qty, updated_at = excluded.updated_at",
                (session_id, item_key, product_id, variant, qty),
            )
            self._conn.commit()

    def get_item_qty(self, session_id: str, item_key: str) -> int:
        cur = self._conn.execute(
            "SELECT qty FROM cart_items WHERE session_id = ? AND item_key = ?",
            (session_id, item_key),
        )
        row = cur.fetchone()
        return int(row["qty"]) if row else 0

    def delete_item(self, session_id: str, item_key: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM cart_items WHERE session_id = ? AND item_key = ?",
                (session_id, item_key),
            )
            self._conn.commit()
            return cur.rowcount > 0

    def clear_cart(self, session_id: str | None = None) -> int:
        with self._lock:
            if session_id is None:
                cur = self._conn.execute("DELETE FROM cart_items")
            else:
                cur = self._conn.execute("DELETE FROM cart_items WHERE session_id = ?", (session_id,))
            self._conn.commit()
            return cur.rowcount

    # --- operation log ----------------------------------------------------
    def log(self, channel: str, action: str, detail: str = "", session_id: str = "") -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO op_log (channel, action, detail, session_id) VALUES (?, ?, ?, ?)",
                (channel, action, detail, session_id),
            )
            self._conn.commit()

    def recent_logs(self, limit: int = 100) -> list[dict]:
        cur = self._conn.execute(
            "SELECT id, ts, channel, action, detail, session_id FROM op_log "
            "ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        return [dict(r) for r in cur.fetchall()]

    # --- orders（デモ注文。実決済・発送は行われない）------------------------
    def create_order(self, session_id: str, items_json: str, total: int, channel: str) -> str:
        """注文レコードを作成し order_no を返す。番号は STAPY-DEMO-xxxxx 連番。"""
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO orders (order_no, session_id, items_json, total, channel) "
                "VALUES ('', ?, ?, ?, ?)",
                (session_id, items_json, total, channel),
            )
            order_no = f"STAPY-DEMO-{cur.lastrowid:05d}"
            self._conn.execute(
                "UPDATE orders SET order_no = ? WHERE id = ?", (order_no, cur.lastrowid)
            )
            self._conn.commit()
            return order_no

    def get_order(self, order_no: str) -> dict | None:
        cur = self._conn.execute(
            "SELECT order_no, session_id, items_json, total, channel, created_at "
            "FROM orders WHERE order_no = ?",
            (order_no,),
        )
        row = cur.fetchone()
        return dict(row) if row else None
