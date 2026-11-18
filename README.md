# stapy商店 — 人間UI / MCP / MCP Apps / WebMCP 4方式比較デモ

既存の架空ECサイト「stapy商店」を拡張し、**同じ商品検索・商品詳細・カート操作**を
次の4方式で実行できるようにした技術デモです。

| # | 方式 | 実行経路 | ログチャネル |
|---|------|----------|-------------|
| 1 | 人間の通常Web操作 | ブラウザ → REST API | `WEB` |
| 2 | AI の通常MCPツール呼び出し | MCPクライアント → Streamable HTTP `/mcp` | `MCP` |
| 3 | MCP Apps（チャット内対話UI） | ホスト iframe → `callServerTool` → `ui_*` ツール | `MCP_APPS` |
| 4 | WebMCP（ブラウザ内ツール公開） | ページ内 `document.modelContext` → `execute` → REST API | `WEBMCP` |

**4方式すべて同じ商品マスター・サービス層・SQLiteカートを共有します。**
ビジネスロジックの重複実装はありません（インターフェースの違いを見せることが目的）。

> 商用ECサイトではなく、15分で4方式の違いが分かる再現性のあるデモです。
> 「注文確定」は**提示（preview）→ 確定（confirm）の2段階**で、記録のみ。
> 実際の決済・配送・在庫確定・顧客登録は一切行われません
> （確認モーダル・確定画面にもその旨を明記しています）。

---

## 1. 起動

### 必要環境

- Python 3.11 以上（検証は 3.12）
- `uv` または `pip` + `venv`
- （E2E検証のみ）Google Chrome 144+ または Chromium 156+、Playwright

### セットアップ

```bash
cd mcp-for-stapy

# uv の場合（推奨）
uv venv && uv pip install -r requirements.txt

# または pip
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

### サーバー起動（Web + REST + MCP を1プロセスで）

```bash
.venv/bin/python -m stapy_shop
# → http://0.0.0.0:8000（WSLからWindows側ブラウザにも届く）
```

| URL | 内容 |
|-----|------|
| `http://localhost:8000/` または `http://<WSLのIP>:8000/` | 商品一覧（既存UI） |
| `http://localhost:8000/detail.html?product=lt-timer` | 商品詳細（既存UI） |
| `http://localhost:8000/order_complete.html?order=<注文番号>` | 注文確定画面（デモ明記） |
| `http://localhost:8000/logs.html` | 操作ログビューア（4チャネル色分け） |
| `http://localhost:8000/mcp` | MCP エンドポイント（Streamable HTTP） |
| `http://localhost:8000/api/products` `/api/cart` `/api/orders` `/api/demo/logs` `/api/demo/reset` | REST API |

#### 環境変数

| 変数 | 既定 | 用途 |
|------|------|------|
| `HOST` | `0.0.0.0` | バインドアドレス。ローカルのみなら `HOST=127.0.0.1` |
| `PORT` | `8000` | ポート |
| `STAPY_BASE_URL` | `http://127.0.0.1:8000` | MCP Apps UI が画像を読むURL＋CSP resourceDomains。**WSLのIP直アクセス時（localhostフォワードを通らない場合）は `STAPY_BASE_URL=http://172.x.x.x:8000` に合わせる**（Inspector等がWindows側で動くとき必須） |
| `STAPY_DB` | `./stapy_shop.db` | SQLite の保存先 |

> WSL2 の localhost フォワーディングが効く場合は、Windows 側ブラウザから
> `http://localhost:8000/` でそのまま開けます（この場合 `STAPY_BASE_URL` の
> 既定値のままで画像も届きます）。WSLのIPで直接開くときだけ上記の設定が要ります。

### MCP stdio モード（ローカル検証用）

```bash
.venv/bin/python -m stapy_shop --stdio
```

HTTP サーバーを立てず標準入出力で MCP を話します。MCP Inspector の
「stdio (local process)」に `.venv/bin/python -m stapy_shop --stdio`
（working directory = プロジェクトルート）を登録すれば使えます。
カートは同じ `stapy_shop.db` を見るため HTTP 側と状態が共有されます。

---

## 2. アーキテクチャ

```
                 ┌────────────────────────────────────────────┐
                 │           stapy_shop.service.ShopService    │
                 │  検索/詳細/カート/合計/リセット/ログ        │
                 │  （価格は products.py マスターのみから取得） │
                 └───────┬──────────┬──────────┬───────┬──────┘
                         │          │          │       │
   人間のブラウザ ───────┤          │          │       │ document.modelContext
   REST /api/*      (WEB)│          │          │       │ 登録ツール execute
                         │          │          │       │   ↓ 内部で REST 呼出
   MCPクライアント ──────┤          │          │       │ (WEBMCP)
   tools/call       (MCP)│          │          │
                         │          │          │
   MCP Apps iframe ──────┤          │          │
   app.callServerTool────┘          │          │
   ui_* ツール          (MCP_APPS)  │          │
                                    │          │
                 ┌──────────────────┴──┐   ┌───┴───────────┐
                 │  db.py (SQLite WAL) │   │ products.py   │
                 │cart_items,op_log,orders│ 商品マスタ20件 │
                 └─────────────────────┘   └───────────────┘
```

| ファイル | 役割 |
|----------|------|
| `stapy_shop/products.py` | 商品マスター20件＋7カテゴリ（products.js から移行。唯一の正本） |
| `stapy_shop/service.py` | 共通サービス層。価格は常にマスターから取得 |
| `stapy_shop/db.py` | SQLite（`cart_items`・`op_log`・`orders`）。RLock＋注文確定は1トランザクション |
| `stapy_shop/api.py` | FastAPI。REST `/api/*`、静的ページ、MCP `/mcp` マウント |
| `stapy_shop/mcp_server.py` | MCPツール18個 + Apps拡張 + `ui://stapy/shop.html` |
| `stapy_shop/mcp_app/shop_app.html` | MCP Apps UI（ext-apps SDK v2.0.4 バンドル埋込） |
| `stapy_shop/static/index.html` `detail.html` `logs.html` | 既存画面＋ログビューア |
| `stapy_shop/static/shop.js` | 既存ロジックをREST化（localStorage廃止） |
| `stapy_shop/static/webmcp.js` | WebMCPツール登録（`document.modelContext`） |
| `stapy_shop/__main__.py` | `python -m stapy_shop [--stdio]` エントリ |

### カート・セッション設計

- カートはサーバー側 SQLite（`session_id` + `item_key` 主キー）で管理。
  localStorage は使わないため **4方式で状態が共有され、リロードにも耐えます**。
- デモセッションは共通 ID `demo`（`?session=` or `X-Stapy-Session` で分離可能）。
- **共通IDは認証なし・ローカル専用です。** 外部公開する場合は認証付きセッション
  発行に置き換えてください（`_session()` が差し替えポイント）。
- 価格・小計・合計は常に `products.py` のマスターから計算。
  クライアントが価格を送信する経路は存在しません。

### 操作ログのチャネル識別

| チャネル | 識別方法 | 信頼度 |
|---------|---------|--------|
| `MCP` | MCPツール関数が明示的に指定 | サーバー確定 |
| `MCP_APPS` | `visibility=["app"]` の `ui_*` ツール + `_require_apps` で Apps拡張ネゴシエーション済みクライアントのみ許可 | ネゴシエーション検証済（※iframe内操作の証明ではない） |
| `WEB` / `WEBMCP` | WebMCPツールの execute だけが付ける `X-Stapy-Channel: webmcp` ヘッダで分岐 | ブラウザ送信値（監査上の事実ではなくデモ用目印。README「制約」参照） |

---

## 3. MCP ツール定義一覧

エンドポイント: `POST http://127.0.0.1:8000/mcp`（Streamable HTTP）
または `python -m stapy_shop --stdio`

### モデル向けツール（channel=MCP）— 通常版（UI連携なし）

どのクライアントでも呼べて **UIは絶対に表示されない**（`_meta.ui` なし）純粋MCPツール。

| ツール | 機能 | 注釈 |
|--------|------|------|
| `search_products` | キーワード・カテゴリ・価格上限・並び替えで検索 | readOnly |
| `get_product` | 商品IDから詳細（価格・在庫・特徴・仕様） | readOnly |
| `get_cart` | 共有カートの明細・合計取得 | readOnly |
| `add_to_cart` | 商品をカートへ（価格はサーバーマスター） | 非readOnly・非idempotent |
| `update_cart` | 数量変更（`qty=0` で削除） | 非readOnly・idempotent |
| `remove_from_cart` | カートから削除 | 非readOnly・destructive・idempotent |
| `preview_order` | カート内容を「注文内容の確認」として提示（pending。まだ確定しない） | 非readOnly・非idempotent |
| `confirm_order` | preview で提示した内容をデモ注文として確定（確定後カートは空に） | 非readOnly・destructive・非idempotent |
| `reset_demo` | カートを空にして初期状態へ | destructive・idempotent |

### モデル向けツール（channel=MCP）— `apps_*` 版（UI連携あり）

全操作に `apps_` プレフィックス版を用意。`_meta.ui.resourceUri` 付きのため、
**MCP Apps 対応ホストでは呼び出し結果が対話UIに自動表示**される。
実装・返り値は同名の通常ツールと同一（ログの action 名だけ `apps_*` になる）。

| ツール | 対応する通常ツール |
|--------|------------------|
| `apps_browse_shop` | 対話ショップUIを開く入口（通常版なし・UI専用） |
| `apps_search_products` | `search_products` |
| `apps_get_product` | `get_product` |
| `apps_get_cart` | `get_cart` |
| `apps_add_to_cart` | `add_to_cart` |
| `apps_update_cart` | `update_cart` |
| `apps_remove_from_cart` | `remove_from_cart` |
| `apps_preview_order` | `preview_order` |
| `apps_confirm_order` | `confirm_order` |
| `apps_reset_demo` | `reset_demo` |

注文確定は**2段階**です：`preview_order` が提示時点の明細・合計を pending
注文として保存し、`confirm_order` がそのスナップショットを原子的に確定
（pending確定＋カート空化は1トランザクション）。**preview 後にカートを
変更すると pending は自動キャンセル**され、提示と違う内容は確定できません。

全ツール `CallToolResult` で `content`（日本語テキスト＝モデル向け）と
`structuredContent`（構造化データ＝UI向け）の両方を返すため、
**テキストのみのクライアントでも検索〜カート更新が完結**します。

### MCP Apps UI専用ツール（`visibility=["app"]`、channel=MCP_APPS）

`ui_search_products` / `ui_get_product` / `ui_get_cart` / `ui_add_to_cart` /
`ui_update_cart` / `ui_remove_from_cart` / `ui_preview_order` / `ui_confirm_order`

- 仕様上ホストはこれらをモデルのツール一覧に含めず、UI iframe からのみ呼ぶ想定。
- サーバー側でも `client_supports_apps()` を検査し、Apps 拡張をネゴシエートした
  クライアント以外からの呼び出しを `[forbidden]` で拒否しています。
- 正確には `MCP_APPS` ログは「**Apps対応をネゴシエートしたクライアント経由**」を
  意味します。iframe 内からの操作であることの証明ではありません（宣言だけで
  呼べるため）。`visibility` は表示制御でありアクセス制御ではないため、
  経路識別の信頼性をサーバー側のネゴシエーション検査で補強しています。

### MCP Apps リソース

| 項目 | 値 |
|------|-----|
| URI | `ui://stapy/shop.html` |
| MIME | `text/html;profile=mcp-app` |
| UI SDK | `@modelcontextprotocol/ext-apps` v2.0.4（`mcp_app/ext_apps.js` にベンダリング、外部CDN非依存） |
| CSP | `resourceDomains`: `http://127.0.0.1:8000`・`http://localhost:8000`（商品画像のため） |
| 関連ツール | `_meta.ui.resourceUri` で `apps_*` 系ツール（`apps_browse_shop`/`apps_search_products` 等）および `ui_*` 系と結合 |

---

## 4. 検証済み環境

| 項目 | バージョン | 状態 |
|------|-----------|------|
| Python | 3.12.3 | ✅ |
| mcp (Python SDK) | 2.3.0 | ✅ Streamable HTTP + stdio |
| FastAPI / uvicorn | 0.162.7 / 0.54.0 | ✅ |
| MCP Inspector | 2.15.0 | ✅ **MCP Apps 実描画・実操作を確認** |
| Chromium（snap） | 156.0.8078.47 | ✅ **WebMCP 登録・executeTool 実呼出を確認** |
| Google Chrome | 144.0.7559.59 | ✅ 通常Web + WebMCP非対応フォールバック確認 |
| Playwright | 1.60.0 | ✅ E2E 43項目 PASS |

### MCP Apps 対応ホスト

- **検証済**: MCP Inspector 2.15.0（`npx -y @modelcontextprotocol/inspector@2.15.0`）。
  手順は `docs/demo_runbook.md`。接続 → 上部「Apps」タブ → `apps_browse_shop` で
  `ui://stapy/shop.html` が iframe 内に描画され、UIのボタンが `callServerTool` 経由で
  `ui_*` ツールを呼びカートが更新されます（スクリーンショット: `docs/screenshots/`）。
- ext-apps リポジトリの `basic-host` 等でも動くはずですが、本環境では Inspector で検証済み。
- **非対応クライアント**（拡張未ネゴシエーション）でも `content` の日本語テキストが
  返るため検索〜カート操作は成立します（フォールバック確認済）。

### WebMCP 対応ブラウザ

- **検証済**: Chromium 156.0.8078.47（snap）+ フラグ
  `--enable-experimental-web-platform-features`（`WebMCPTesting,WebMCP` のみでも可）。
  `document.modelContext.getTools()` で8ツール、`executeTool()` で実呼出・画面反映を確認。
  カート系ツール（`add_to_cart` / `update_cart` / `remove_from_cart` / `get_cart`）は
  実行時に画面上のカートパネルを開き、AIの操作がそのまま見えます
  （`get_cart` は `show_in_browser:false` でパネルを開かない呼び出しも可）。
- **非対応**: Google Chrome 144（上記フラグでも `document.modelContext` は未定義）。
  非対応でも通常のEC機能はそのまま動きます（プログレッシブエンハンスメント、E2E確認済）。
- WebMCP は **ドラフト仕様（W3C Community Group Report）** であり、API・対応ブラウザは
  変わる可能性があります。検証時点の公式実装 `document.modelContext.registerTool` /
  `getTools` / `executeTool` をそのまま使用しています（自動操作等での代替はなし）。
- Permissions Policy の `tools` ディレクティブで無効化可能（仕様上）。

---

## 5. デモシナリオ（15分）

シナリオ：**「LTに登壇する人に、予算3,000円以内でプレゼントを探してカートに入れてください」**

期待結果（4方式すべて共通）：LT専用5分タイマー ¥2,300 ×1 ＋ ステッカーセット ¥400 ×1
＝ **合計 ¥2,700**

詳しいタイムライン・接続手順・バックアップ手順は
**`docs/demo_runbook.md`** を参照してください。

---

## 6. テスト

```bash
# バックエンド（72件: カタログ/検索/カート/注文2段階/バリデーション/同時実行/ログ/REST/ページ）
.venv/bin/python -m pytest tests/ -q

# ブラウザE2E（43件: WEB / WEBMCP実呼出 / 注文2段階フロー / 非対応フォールバック）
.venv/bin/python tests/e2e.py        # サーバー起動中に実行

# 4方式統合（同一シナリオが全経路で同一カート＋同一注文確定になること）
.venv/bin/python tests/four_way.py   # サーバー起動中に実行
```

最新の実行結果（この環境での実測）：

- `pytest`: **72 passed**
- `tests/e2e.py`: **43/43 PASS**
- `tests/four_way.py`: **4方式とも ¥2,700 で一致 + 注文確定（STAPY-DEMO-xxxxx）も4経路で記録 + 4チャネルのログ記録を確認**
- MCP Inspector 2.15.0 での MCP Apps 実描画・UI操作を確認
- 詳細は `docs/test_results.md`

---

## 7. 制約・既知の限界（正直な報告）

- **共通デモセッション `demo` は認証なしのローカル専用**です。外部公開不可。
- **WEBMCP ログチャネルはベストエフォート**です。`X-Stapy-Channel` はブラウザ
  送信値であり、仕組み上 REST 経由の操作を完全には区別できません
  （WEB操作をWEBMCPに偽装可能）。監査上の事実としては使わないでください。
  `MCP`/`MCP_APPS` はサーバー側で確定的に識別しています。
- **`visibility=["app"]` は仕様上「ホストによる表示制御」**であり強制力は
  ホスト依存です。本実装はサーバー側の Apps ネゴシエーション検査で補強していますが、
  拡張を名乗る悪意あるクライアントまでは排除できません（ローカルデモ用途として許容）。
- **WebMCP はドラフト**です。Chrome 144 では未提供、Chromium 156 では実験フラグで
  有効。将来のブラウザでAPIが変わる可能性があります。非対応では通常UIに無害フォールバック。
- **MCP Apps UI 内のカートはホストiframe内でのみ見えます**。Inspector の Apps タブ
  相当の対応ホストがない環境ではテキストフォールバックでのデモになります。
- 「注文確定」は `orders` テーブルへの**デモ注文の記録のみ**です。
  実際の決済・在庫確定・発送・顧客情報の取り扱いは一切ありません
  （確定画面・ツール説明・ログいずれにもデモである旨を明記）。
- `products.py` の商品画像は既存HTML内の data URI から `static/images/*.webp` に
  展開したものです（オリジナルデザインを維持）。

---

## 8. ディレクトリ

```
mcp-for-stapy/
├── pyproject.toml            # 依存固定（mcp 2.3.0 等）
├── requirements.txt
├── README.md                 # 本ファイル
├── docs/
│   ├── demo_runbook.md       # 15分デモ手順書
│   ├── test_results.md       # テスト実行結果
│   └── screenshots/          # 検証証跡（失敗時の見せ物にも）
├── stapy_shop/               # Pythonパッケージ
│   ├── __main__.py           # 起動エントリ（--stdio 対応）
│   ├── api.py                # FastAPI: REST + 静的 + MCPマウント
│   ├── mcp_server.py         # MCPツール + Apps拡張 + ui://リソース
│   ├── service.py            # 共通サービス層
│   ├── db.py                 # SQLite（カート/ログ、RLock）
│   ├── products.py           # 商品マスター20件（唯一の正本）
│   ├── mcp_app/              # MCP Apps UI（shop_app.html + ベンダSDK）
│   └── static/               # 既存EC画面（index/detail/logs.html, js, css, images）
├── tests/
│   ├── test_service.py       # サービス層テスト
│   ├── test_api.py           # REST APIテスト
│   ├── e2e.py                # Playwright E2E（43項目）
│   └── four_way.py           # 4方式統合テスト
└── stapy_shop_*.html         # 元の単体HTML（参照用に残置）
```
