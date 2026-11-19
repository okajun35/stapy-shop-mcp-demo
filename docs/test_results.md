# テスト実行結果

実行環境: Python 3.12.3 / mcp 2.3.0 / FastAPI 0.162.7 /
MCP Inspector 2.15.0 / Chromium 156.0.8078.47 / Google Chrome 144.0.7559.59 / Playwright 1.60.0

## 1. pytest — バックエンド 72件

```
$ .venv/bin/python -m pytest tests/ -q
........................................................................  [100%]
72 passed in 2.01s
```

| 領域 | 内容 |
|------|------|
| TestCatalog | 商品20件・ID一意・必須商品（sticker-set/lt-timer）・カテゴリ7・全商品画像URL |
| TestSearch | キーワードLT・価格上限・カテゴリ・並び替え・0件・負の上限エラー |
| TestCart | 追加・合計¥2,700・**サーバー側価格の使用**・数量累積・不正ID・qty 0/負数・在庫超過・バリアント・更新・削除・セッション分離・リセット |
| TestOrders | **2段階注文**: preview→confirm・previewでは未確定・confirmなしで確定不可（no_pending_order）・カート変更でpending自動キャンセル・リセットでキャンセル・再previewで置換・確定後カート空・価格はマスター由来・preview/confirmログ・order_not_found |
| TestLogs | WEB/MCP/MCP_APPS/WEBMCP 4チャネル記録・ログ項目 |
| TestConcurrency | 10スレッド同時 add_to_cart → qty=10・合計¥4,000 の整合性 |
| TestCatalogApi | REST /api/products /detail /categories /検索・404 |
| TestCartApi | REST カート CRUD・永続化・qty=0/-1→422・在庫超過→409・セッション分離 |
| TestOrdersApi | POST /api/orders/preview→confirm・previewなしconfirm→409・空カート→409・カート変更で無効化・GET /api/orders/{no}・404・決済系エンドポイント非存在 |
| TestDemoApi | リセット・WEBログ・WEBMCPチャネルヘッダ |
| TestPages | `/` `/index.html` `/detail.html` `/logs.html` `/order_complete.html` 旧ファイル名・静的JS・画像 |

## 2. Playwright E2E — 43/43 PASS

```
$ .venv/bin/python tests/e2e.py

=== WEB: 通常ブラウザ操作 === (Google Chrome 144)
[PASS] 一覧: 20件表示
[PASS] 一覧: 商品画像読み込み
[PASS] 一覧: WebMCPバッジなし(非対応)
[PASS] 検索: LT+¥3000以下 — 3件
[PASS] 詳細: 商品ページ遷移
[PASS] 詳細: 価格表示
[PASS] カート: バッジ1 / バッジ2
[PASS] カート: 合計¥2,700（デモシナリオ）
[PASS] サーバー側も¥2700（共有状態）
[PASS] カート: 数量+1
[PASS] リロード後もカート維持（サーバー永続化）
[PASS] 注文確認: モーダル表示（preview → 確認モーダル）
[PASS] 注文確認: デモ明記（実際の注文・決済・発送は一切行われません）
[PASS] 注文確定: 確定画面へ遷移（order_complete.html?order=STAPY-DEMO-xxxxx）
[PASS] 注文確定: デモ明記（実際の注文・決済・発送・在庫確定は一切行われません）
[PASS] 注文確定: 明細表示
[PASS] 注文確定: サーバーカート空
[PASS] デモリセット
[PASS] JSエラーなし

=== WEBMCP: 対応ブラウザ === (Chromium 156 + --enable-experimental-web-platform-features)
[PASS] document.modelContext 存在
[PASS] 8ツール登録（getTools() — 公式API）
[PASS] WebMCPバッジ表示
[PASS] AI検索→結果3件（executeTool — 公式API）
[PASS] AI検索→画面も3件に絞込（画面への反映）
[PASS] AIカート追加（lt-timer）
[PASS] 画面バッジ更新
[PASS] AI追加→カートパネル開く（body.cart-open）
[PASS] パネル内に追加商品表示
[PASS] サーバーカート一致（共有状態）
[PASS] AIカート確認
[PASS] get_cart→カートパネル再表示（閉じた状態から再び開く）
[PASS] AI注文提示（preview_order → pending）
[PASS] AI提示→画面に確認モーダル表示
[PASS] AI注文確定（confirm_order → STAPY-DEMO-xxxxx・demo=True）
[PASS] AI確定→画面も確定ページへ遷移
[PASS] 確定後カート空
[PASS] ログにWEBMCP記録
[PASS] ログにpreview_order/confirm_order記録
[PASS] JSエラーなし

=== FALLBACK: 非対応ブラウザ === (Google Chrome 144)
[PASS] modelContext未定義
[PASS] 通常カート操作可能（非対応でも動く）
[PASS] JSエラーなし

=== E2E結果: 43/43 PASS ===
```

## 3. 4方式統合テスト — PASS

```
$ .venv/bin/python tests/four_way.py

=== 4方式のカート結果 ===
  WEB      {'items': [('lt-timer', 1), ('sticker-set', 1)], 'total': 2700, 'count': 2}  == 期待値
  MCP      {'items': [('lt-timer', 1), ('sticker-set', 1)], 'total': 2700, 'count': 2}  == 期待値
  MCP_APPS {'items': [('lt-timer', 1), ('sticker-set', 1)], 'total': 2700, 'count': 2}  == 期待値
  WEBMCP   {'items': [('lt-timer', 1), ('sticker-set', 1)], 'total': 2700, 'count': 2}  == 期待値

=== 4方式の注文確定（デモ） ===
  WEB      STAPY-DEMO-xxxxx ¥2700 demo=True  OK
  MCP      STAPY-DEMO-xxxxx ¥2700 demo=True  OK
  MCP_APPS STAPY-DEMO-xxxxx ¥2700 demo=True  OK
  WEBMCP   STAPY-DEMO-xxxxx ¥2700 demo=True  OK

=== 操作ログ（channel 別） ===
  WEBMCP   N件（confirm_order あり）
  MCP_APPS N件（confirm_order あり）
  MCP      N件（confirm_order あり）
  WEB      N件（confirm_order あり）

=== 4方式一致: PASS ===
```

## 4. MCP プロトコル手動検証（Python Client）

Streamable HTTP（接続単位で2エンドポイントに分離）:

`/mcp`（通常接続・UIなし）:
- `tools/list`: 通常9ツールのみ（`_meta.ui` 付きツール0件）
- `resources/list`: 空、`resources/read ui://stapy/shop.html` → `Resource not found`
- `tools/call apps_search_products` / `ui_get_cart` → `Unknown tool`（公開外は呼び出し不可）
- `search_products {q:"LT",max_price:3000}` → text「検索結果 3件…」+ structuredContent `{count:3,...}`
- `add_to_cart` → 「カートに追加しました。現在N点・合計¥Xです」+ structured
- `get_cart` → 共有カート内容
- `preview_order` → `content`「注文内容の確認（未確定）: STAPY-DEMO-xxxxx…」+
  structuredContent `{order_no, status:"pending", items, total, demo:true}`
- `confirm_order` → structuredContent `{order_no, status:"confirmed", ...}`＋カート空化
- `confirm_order`（previewなし）→ `isError` `[no_pending_order]`、previewは空カートで `[cart_empty]`
- エラーケース: `product_not_found` / qty 0・999・-1 バリデーション
- プロトコルバージョン: `2026-07-28`（Client）/ `2025-11-25`（Inspector Legacy）両対応

`/mcp-apps`（MCP Apps 接続・全ツールUI連携）:
- `tools/list`: 18ツール（`apps_*` 10 + `ui_*` 8、全件 `_meta.ui.resourceUri` 付き）
- `resources/list` / `resources/read` → `ui://stapy/shop.html` `text/html;profile=mcp-app`
- `tools/call search_products`（通常ツール名）→ `Unknown tool`
- `apps_search_products {q:"LT"}` → 検索3件、`ui_get_cart` → カート取得（Apps拡張ネゴシエーション済み）
- `ui_*` ツール: 非Appsクライアントからは `[forbidden]` で拒否
- 操作ログは channel=`MCP_APPS`・action=`apps_*`/`ui_*` 名で記録

stdio（`.venv/bin/python -m stapy_shop --stdio`）:
- 全27ツールを統合公開（検証・`worker/build.py` 生成用）・同一の共有カート

## 5. MCP Apps 実描画検証（公式ホスト）

**ホスト**: MCP Inspector 2.15.0（公式）— `/mcp-apps` 接続
- 「Apps」タブ → `apps_browse_shop` 選択
- ネットワークログ: `RESOURCES/READ ui://stapy/shop.html` OK、`TOOLS/CALL apps_browse_shop` OK
- iframe 内にショップUI が **実際に描画**（商品カード20件・画像・価格・検索バー・カートチップ）

**全画面フロー実測（Inspector iframe 内操作、15/15 PASS）**:

1. 検索欄に「タイマー」→ `ui_search_products` → 絞り込み表示
2. 商品カードクリック → `ui_get_product` → 詳細モーダル（数量コントロール ＋− 動作確認）
3. 「＋ カートに追加」→ `ui_add_to_cart` → サーバーカート反映（lt-timer ×1）
4. 同様にステッカーセット追加 → 計2点・**合計¥2,700**（`/api/cart` で一致）
5. 「注文を確定する（デモ）」→ `ui_preview_order` → **UI内確認モーダル表示**
   （明細・合計¥2,700・「実際の注文・決済・発送は一切行われません」明記）
6. 「この内容で確定する」→ `ui_confirm_order` → UI内に
   「デモ注文を確定しました: STAPY-DEMO-00027（合計¥2,700）」表示、カート空に
7. 操作ログ: `channel=MCP_APPS` で `add_to_cart` / `preview_order` / `confirm_order` を確認

- 証跡: `docs/screenshots/mcp_apps_inspector.png`, `mcp_apps_2phase_modal.png`,
  `mcp_apps_2phase_done.png`

## 6. WebMCP 実検証（対応ブラウザ）

- Chromium 156 + フラグで `document.modelContext` が公開され、
  `getTools()` → 8ツール、`executeTool()` → 実実行・画面反映・WEBMCPログを確認
- カート系ツール実行で画面のカートパネル（ドロワー）が開くことを確認
  （`add_to_cart`/`update_cart`/`remove_from_cart` 実行後、`get_cart` は
  閉じた状態からも再表示。`show_in_browser:false` で抑止可）
- `preview_order` 実行 → 画面に確認モーダル表示、`confirm_order` → 画面は `order_complete.html` へ遷移
- Google Chrome 144 では `document.modelContext` 未定義 → 通常UIは動作（プログレッシブ）
- 証跡: `docs/screenshots/webmcp.png`

## 7. 注文確定（デモ）の仕様 — 2段階フロー

- `preview_order`（提示）→ `confirm_order`（確定）の2段階。
  REST `POST /api/orders/preview` + `/confirm`、MCP `preview_order`/`confirm_order`、
  Apps `ui_preview_order`/`ui_confirm_order`、WebMCP `preview_order`/`confirm_order`
  の4経路はすべて `service.preview_order()`/`confirm_order()` に集約（ロジック重複なし）。
- `preview_order` は提示時点の明細・合計を `status='pending'` で保存（価格はマスター由来）。
  **この時点では何も確定されない**。`confirm_order` は pending を原子的に
  `confirmed` + カート空化（1トランザクション。二重確定・明細不一致なし）。
- **カート変更（add/update/remove/reset）で pending は自動キャンセル**され、
  提示と違う内容は確定できない。
- `confirm_order` 単独実行は `[no_pending_order]` エラー（承認なしでは確定しない）。
- 注文番号 `STAPY-DEMO-xxxxx`。`confirm_order`/`preview_order` が操作ログに channel 付きで記録。
- 確定画面 `/order_complete.html?order=<no>` は `GET /api/orders/{no}` で明細を復元表示し、
  「実際の注文・決済・発送・在庫確定は一切行われません」を警告バナーで明示。
  `status != confirmed` の注文は「未確定」と表示。
- 証跡: `docs/screenshots/order_complete.png`, `web_checkout_flow.png`

## 8. 未検証・残課題（正直な記録）

- `basic-host`（ext-apps リポジトリの別ホスト実装）での描画は未検証。
  公式 Inspector で実確認済みのため代替とする。
- Inspector での stdio 接続はコード経路で動作確認済みだが、Inspector UI からの
  登録〜接続は未実施（Streamable HTTP を推奨）。
- 複数同時ブラウザでの競合（同時更新の画面通知）は仕様外（ポーリングなし）。
- WebMCP の今後のブラウザ変更（Chrome stable への展開時期等）は未定。
