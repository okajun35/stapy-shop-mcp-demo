-- D1 スキーマ（db.py と同一構造 + MCP セッション管理）
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
    ts         TEXT NOT NULL DEFAULT (datetime('now')),
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
    status     TEXT NOT NULL DEFAULT 'confirmed',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
-- MCP Streamable HTTP のセッション（Apps拡張ネゴシエーション結果を保持）
CREATE TABLE IF NOT EXISTS mcp_sessions (
    session_id  TEXT PRIMARY KEY,
    supports_ui INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
