# テスト実行結果

実行環境: Python 3.12.3 / mcp 2.3.0 / FastAPI 0.162.7 /
MCP Inspector 2.15.0 / Chromium 156.0.8078.47 / Google Chrome 144.0.7559.59 / Playwright 1.60.0

## 1. pytest — バックエンド 66件

```
$ .venv/bin/python -m pytest tests/ -q
..................................................................  [100%]
66 passed in 1.76s
```

| 領域 | 内容 |
|------|------|
| TestCatalog | 商品20件・ID一意・必須商品（sticker-set/lt-timer）・カテゴリ7・全商品画像URL |
| TestSearch | キーワードLT・価格上限・カテゴリ・並び替え・0件・負の上限エラー |
| TestCart | 追加・合計¥2,700・**サーバー側価格の使用**・数量累積・不正ID・qty 0/負数・在庫超過・バリアント・更新・削除・セッション分離・リセット |
| TestOrders | 注文確定（明細スナップショット・注文番号 STAPY-DEMO-xxxxx・合計一致・確定後カート空・参照API）・空カート→cart_empty・価格はマスター由来・confirm_orderログ・order_not_found |
| TestLogs | WEB/MCP/MCP_APPS/WEBMCP 4チャネル記録・ログ項目 |
| TestConcurrency | 10スレッド同時 add_to_cart → qty=10・合計¥4,000 の整合性 |
| TestCatalogApi | REST /api/products /detail /categories /検索・404 |
| TestCartApi | REST カート CRUD・永続化・qty=0/-1→422・在庫超過→409・セッション分離 |
| TestOrdersApi | POST /api/orders（明細・カート空化）・空カート→409・GET /api/orders/{no}・404・決済系エンドポイント非存在 |
| TestDemoApi | リセット・WEBログ・WEBMCPチャネルヘッダ |
| TestPages | `/` `/index.html` `/detail.html` `/logs.html` `/order_complete.html` 旧ファイル名・静的JS・画像 |

## 2. Playwright E2E — 36/36 PASS

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
[PASS] 注文確定: 確定画面へ遷移（order_complete.html?order=STAPY-DEMO-xxxxx）
[PASS] 注文確定: デモ明記（実際の注文・決済・発送・在庫確定は一切行われません）
[PASS] 注文確定: 明細表示
[PASS] 注文確定: サーバーカート空
[PASS] デモリセット
[PASS] JSエラーなし

=== WEBMCP: 対応ブラウザ === (Chromium 156 + --enable-experimental-web-platform-features)
[PASS] document.modelContext 存在
[PASS] 7ツール登録（getTools() — 公式API）
[PASS] WebMCPバッジ表示
[PASS] AI検索→結果3件（executeTool — 公式API）
[PASS] AI検索→画面も3件に絞込（画面への反映）
[PASS] AIカート追加（lt-timer）
[PASS] 画面バッジ更新
[PASS] サーバーカート一致（共有状態）
[PASS] AIカート確認
[PASS] AI注文確定（confirm_order → STAPY-DEMO-xxxxx・demo=True）
[PASS] AI確定→画面も確定ページへ遷移
[PASS] 確定後カート空
[PASS] ログにWEBMCP記録
[PASS] ログにconfirm_order記録
[PASS] JSエラーなし

=== FALLBACK: 非対応ブラウザ === (Google Chrome 144)
[PASS] modelContext未定義
[PASS] 通常カート操作可能（非対応でも動く）
[PASS] JSエラーなし

=== E2E結果: 36/36 PASS ===
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

Streamable HTTP（`http://127.0.0.1:8000/mcp`）:

- `tools/list`: 16ツール（モデル向け9 + ui_*7）
- `search_products {q:"LT",max_price:3000}` → text「検索結果 3件…」+ structuredContent `{count:3,...}`
- `add_to_cart` → 「カートに追加しました。現在N点・合計¥Xです」+ structured
- `get_cart` → 共有カート内容
- `confirm_order` → `content`「デモ注文を確定しました: STAPY-DEMO-xxxxx…」+
  structuredContent `{order_no, items, total, demo:true}`
- `confirm_order`（空カート）→ `isError` `[cart_empty]`
- `ui_confirm_order`（非Appsクライアント）→ `isError` `[forbidden]`
- `resources/list` / `resources/read` → `ui://stapy/shop.html` `text/html;profile=mcp-app`（Appsネゴシエーション済みクライアント）
- `ui_*` ツール: 非Appsクライアントからは `[forbidden]` で拒否
- エラーケース: `product_not_found` / qty 0・999・-1 バリデーション
- プロトコルバージョン: `2026-07-28`（Client）/ `2025-11-25`（Inspector Legacy）両対応

stdio（`.venv/bin/python -m stapy_shop --stdio`）:
- 同一の16ツール・同一の共有カート（HTTP 側で追加した商品が見える）

## 5. MCP Apps 実描画検証（公式ホスト）

**ホスト**: MCP Inspector 2.15.0（公式）
- 「Apps」タブ → `browse_shop` 選択
- ネットワークログ: `RESOURCES/READ ui://stapy/shop.html` OK、`TOOLS/CALL browse_shop` OK
- iframe 内にショップUI が **実際に描画**（商品カード20件・画像・価格・検索バー・カートチップ）
- iframe 内の「＋ カートに追加」クリック → `ui_add_to_cart` が走り
  カートチップ 3点→4点、`/api/cart` でも同じ合計（共有状態確認）
- カートパネルに「注文を確定する（デモ）」ボタン → `ui_confirm_order` →
  注文番号がUI内に表示、カートは空に（コード経路・`four_way.py` の Apps経路で検証）
- 操作ログ `channel=MCP_APPS` に記録
- 証跡: `docs/screenshots/mcp_apps_inspector.png`, `mcp_apps_interact.png`

## 6. WebMCP 実検証（対応ブラウザ）

- Chromium 156 + フラグで `document.modelContext` が公開され、
  `getTools()` → 7ツール、`executeTool()` → 実実行・画面反映・WEBMCPログを確認
- `confirm_order` 実行 → 注文番号が返り画面は `order_complete.html` へ遷移
- Google Chrome 144 では `document.modelContext` 未定義 → 通常UIは動作（プログレッシブ）
- 証跡: `docs/screenshots/webmcp.png`

## 7. 注文確定（デモ）の仕様

- `POST /api/orders` / MCP `confirm_order` / Apps `ui_confirm_order` / WebMCP `confirm_order`
  の4経路はすべて `service.confirm_order()` に集約（ロジック重複なし）。
- 注文番号 `STAPY-DEMO-xxxxx`、明細は確定時点のスナップショットを保存（価格はマスター由来）。
- 確定後カートは空になり、`confirm_order` が操作ログに channel 付きで記録される。
- 確定画面 `/order_complete.html?order=<no>` は `GET /api/orders/{no}` で明細を復元表示し、
  「実際の注文・決済・発送・在庫確定は一切行われません」を警告バナーで明示。
- 証跡: `docs/screenshots/order_complete.png`, `web_checkout_flow.png`

## 8. 未検証・残課題（正直な記録）

- `basic-host`（ext-apps リポジトリの別ホスト実装）での描画は未検証。
  公式 Inspector で実確認済みのため代替とする。
- Inspector での stdio 接続はコード経路で動作確認済みだが、Inspector UI からの
  登録〜接続は未実施（Streamable HTTP を推奨）。
- 複数同時ブラウザでの競合（同時更新の画面通知）は仕様外（ポーリングなし）。
- WebMCP の今後のブラウザ変更（Chrome stable への展開時期等）は未定。
