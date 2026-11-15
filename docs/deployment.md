# Cloudflare Workers へのデプロイ（`deploy/cloudflare` ブランチ）

FastAPI + SQLite のローカル版を、**Cloudflare Workers + D1 + Workers Static Assets**
に移植した公開バリアント。無料枠の範囲で動作する。

## 公開 URL

- Web UI: `https://stapy.studiooverdrive.com/`
- MCP（Streamable HTTP）: `https://stapy.studiooverdrive.com/mcp`

購入済みドメイン `studiooverdrive.com`（同一アカウントで DNS 管理済みゾーン）の
サブドメインを **Worker Custom Domain** として紐付け
（`wrangler.toml` の `routes`）。DNS レコード・TLS 証明書は自動発行される。
`workers.dev` のデフォルトルートは無効化済み（アカウント名を含むサブドメインを
公開しないため）。workers.dev で再公開したい場合は `workers_dev = true` を
wrangler.toml に追記してデプロイする。

## アーキテクチャの対応

| ローカル版 | Workers 版 |
|-----------|-----------|
| `uvicorn` 常駐プロセス | `worker/src/index.ts`（fetch ハンドラ） |
| `stapy_shop/static/` | Workers Static Assets（`ASSETS` binding） |
| SQLite（`stapy_shop.db`） | D1 `stapy-shop-db`（同一スキーマ + `mcp_sessions`） |
| `service.py` | `worker/src/service.ts`（同等ロジック移植） |
| `mcp_server.py`（python-mcp SDK） | `index.ts` 内の JSON-RPC 実装（`tools/list` 等は Python 側から生成したものを返す） |
| `app.mount("/mcp")` | `/mcp` ルートを自前実装（initialize/tools/resources/ping + SSE 応答） |

## ファイル構成

```
worker/
  wrangler.toml     # name/assets/d1 バインディング
  schema.sql        # D1 スキーマ（db.py と同一 + mcp_sessions）
  build.py          # Python 正本から generated/* を生成
  src/
    index.ts        # ルーティング + REST + MCP + 静的
    service.ts      # D1 サービス層
    generated/      # build.py の出力（products/tools_list/uiHtml）
```

**ビルドは Python 側が正本のまま**:
`build.py` が `products.py` → `products.ts`、実 MCP サーバー（stdio）の
`tools/list`/`resources/list` → `tools.ts`、`shop_app.html + ext_apps.js` → `uiHtml.ts`
を生成する。ツール定義・UI HTML の手動転記はしない。

## デプロイ手順

```bash
cd worker
npm install
../.venv/bin/python build.py          # generated/* 生成
npx wrangler d1 execute stapy-shop-db --remote --file schema.sql  # 初回のみ
npx wrangler deploy
```

ローカル検証: `npm run dev` → `http://localhost:8788`（D1 はローカル SQLite にエミュレート）。

## ローカル版との違い（正直な記録）

- **別インスタンス・別DB**: デプロイ版は公開 D1 を使う独立デモ。ローカルの
  `stapy_shop.db` とはカート・ログ・注文を共有しない。
- **MCP 実装は自前の JSON-RPC**: `initialize`/`tools/list`/`tools/call`/
  `resources/*`/`ping`/`notifications/*` を実装。応答は SSE フレーム1発
  （Streamable HTTP 仕様の範囲内）。GET /mcp のサーバー→クライアント
  listen ストリームは未提供（仕様上 optional）。stdio モードはなし。
- **`mcp_sessions` テーブル**: Apps 拡張ネゴシエーション結果を D1 に保存し
  `ui_*` の `_require_apps` 相当を再現（非Appsクライアントは `[forbidden]`）。
- **`/static/*` のリライト**: Assets は `stapy_shop/static` 直下を `/` に
  マップするため `/static/shop.js` → `/shop.js` に内部書き換え。
- **排他制御の差異**: SQLite RLock → D1 batch（原子的実行）に変更。
  confirm は `WHERE status='pending'` 条件付き UPDATE で二重確定を防止。
  add_to_cart の読み取り→書込みは非原子的（デモ用途では実害なし）。
- **同時実行**: Workers は分離された isolate で動くため「同じカートを同時に
  触る」競合は D1 の逐次性に依存。テスト用の完全な直列化は行っていない。

## セキュリティ上の注意（デモ用途）

- 認証なし・共通セッション `demo` が **公開インターネット上**で動く。
  URL を知る人は誰でもカート/注文/リセット/ログ閲覧が可能。デモ用途に限定すること。
- 価格・在庫・注文はすべて架空データ。決済エンドポイントは存在しない。
- `Python-urllib` 等の UA は Cloudflare の Bot 対策で 403 になることがある
  （ブラウザ・MCP Inspector は問題なし）。

## 検証済み

- `wrangler dev`（local D1）: REST・2段階注文・MCP init/tools/list/
  tools/call（ui_* の Apps ガード含む）・resources/read（530KB UI HTML）・静的ページ
- 公開 URL: REST 全経路・MCP（initialize→tools/call）・静的ページ
- 公開 URL Web UI（Playwright）: 検索→追加→カート¥2,700→確認モーダル→確定→
  確定ページ（デモ警告）9/9 PASS。証跡 `docs/screenshots/deployed_order.png`
