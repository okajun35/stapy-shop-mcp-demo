# 15分デモ手順書 — stapy商店 4方式比較

シナリオ：**「LTに登壇する人に、予算3,000円以内でプレゼントを探してカートに入れてください」**

期待結果（4方式すべて共通）：

| 商品 | 価格 |
|------|------|
| LT専用5分タイマー ×1 | ¥2,300 |
| ステッカーセット ×1 | ¥400 |
| **合計** | **¥2,700** |

見せたい核心：**インターフェースが違っても、同じサービス層・同じ共有カートに辿り着く。**

---

## 0. 事前準備（発表前に必ず）

```bash
cd mcp-for-stapy
.venv/bin/python -m stapy_shop          # サーバー起動（http://127.0.0.1:8000）
npx -y @modelcontextprotocol/inspector@2.15.0   # Inspector 起動（http://127.0.0.1:6274）
```

ブラウザで確認：
- `http://127.0.0.1:8000/` → 商品一覧20件が表示される
- `http://127.0.0.1:8000/logs.html` → 操作ログページが開く
- Inspector の stapy-shop カード（`/mcp` 接続）のスイッチを ON → `Connected` になる。
  同様に stapy-shop-apps カード（`/mcp-apps` 接続）も ON にする
  （2サーバー登録は §2「Inspector 接続手順」参照）

**デモ直前に必ず**: `↺ デモリセット` ボタン（ページ上部バナー）か
`curl -X POST http://127.0.0.1:8000/api/demo/reset` でカートを空にする。

失敗したときの見せ物：`docs/screenshots/` に成功時の画面がある。

---

## 1. タイムライン（15分）

### 0:00–1:30 導入 — 「同じECを4つの入口から操作する」

- `http://127.0.0.1:8000/` を見せる：「普通のECサイトです」
- 「今日はこれに人間・AI×2・ブラウザ内AIの4入口を作り、**同じカートに繋ぐ**デモです」
- アーキテクチャ図（README§2）を1画面で：「重複実装なし、1つのサービス層」

### 1:30–4:30 方式① WEB — 人間の通常操作

1. `↺ デモリセット`
2. 検索欄に `LT` → 価格スライダーを ¥3,000 へ
   → LT専用5分タイマー等に絞り込まれる
3. LT専用5分タイマーのカード → 詳細ページを開く（既存UI維持を見せる）
4. 「＋ カートに追加」×1 → バッジ 1
5. 一覧に戻りステッカーセットも追加 → バッジ 2、🛒 で **¥2,700**
6. ページをリロード → **カートが残る**（サーバー側管理の証拠）
7. 🛒 →「注文を確認する（デモ）」→ **確認モーダル**（明細・合計・デモ明記）
   →「この内容で確定する」→ **注文確定画面へ遷移**
   （`STAPY-DEMO-xxxxx`、デモ明記の警告バナー、確定後カートは空）
   → 「提示→確定の2段階です。確定ツールが呼ばれても即実行されません」

**言いポイント**: 「カートはもう localStorage ではありません。
サーバー SQLite なので、これから他の3方式が同じカートを触ります」

### 4:30–7:00 方式② MCP — AIのツール呼び出し（UIなし）

Inspector（`http://127.0.0.1:6274`）で **stapy-shop（`/mcp` 接続）** → 「Tools」タブ
（この接続には `apps_*`/`ui_*`/`ui://` リソースが一切存在しない）：

1. `reset_demo` を実行（または共有カートであることを示すため `get_cart` から）
   → 「先ほどの人間が入れた2点が見えます（共有状態）」
2. `search_products` `{q:"LT", max_price:3000}` 実行
   → **テキストで3件返る**（UIがなくても検索できる）
3. `add_to_cart` `{product_id:"lt-timer",qty:1}` → `add_to_cart` `{product_id:"sticker-set",qty:1}`
4. `get_cart` → **「カート: 2点 合計 ¥2700」**
5. `preview_order` → 明細・合計・「この内容でよければ confirm_order」が返る（まだ未確定）
6. `confirm_order` → 注文番号 `STAPY-DEMO-xxxxx` で確定（デモ注文の記録のみ）
   → 「**提示→確定の2段階**です。preview 後にカートを変えると提示はキャンセルされます」
7. `logs.html` で channel=MCP の行を見せる

**言いポイント**: 「UIはゼロ。JSONと日本語テキストだけで買い物が完結します」

### 7:00–10:00 方式③ MCP Apps — チャット内の対話UI

Inspector で **stapy-shop-apps（`/mcp-apps` 接続）** に切り替え、「**Apps**」タブ：

1. `apps_browse_shop` を選択 → **`ui://stapy/shop.html` が iframe に描画される**
   → 「RESOURCES/READ でHTMLを取得、ツール結果で初期化されています」
2. UIの検索欄に `タイマー` または価格上限 `3000` → 検索ボタン
   → iframe内で `ui_search_products` が走りカードが絞り込まれる
3. 商品カード → 詳細モーダル → 数量「＋」→「＋ カートに追加」
   → iframe内のカートパネルが即更新（**合計¥2,700になるまで操作**）
4. カートパネル下の「注文を確定する（デモ）」→ `ui_preview_order` →
   UI内に確認モーダル →「この内容で確定する」→ `ui_confirm_order` で
   注文番号がUI内に表示される（カートは空に）
5. 通常MCP側 stapy-shop（`/mcp`）の `get_cart` でカートが空になったことを確認
   → 「**同じカート**です」
6. `logs.html` で channel=MCP_APPS の行を見せる
   → 「/mcp-apps 接続の操作は `apps_*` 名・MCP_APPS で記録されます」

**言いポイント**: 「見た目は普通のECですが、**MCPプロトコルで**ツールを呼んでいます。
iframeに普通のページを置いたわけではありません」

### 10:00–12:30 方式④ WebMCP — ブラウザ上のサイト操作

Chromium を WebMCP 有効で起動（発表用の手順）：

```bash
/snap/bin/chromium --enable-experimental-web-platform-features http://127.0.0.1:8000/
```

ヘッダーバナーに `WebMCP: 8ツール公開中` のバッジが出る。

1. DevTools コンソールでエージェント相当の呼び出しを実演：

```js
const tools = await document.modelContext.getTools();
const s = tools.find(t => t.name === 'search_products');
JSON.parse(await document.modelContext.executeTool(s, {query:'LT', max_price:3000}));
// → 商品一覧がその場で3件に絞り込まれる（画面に反映！）
const a = tools.find(t => t.name === 'add_to_cart');
await document.modelContext.executeTool(a, {product_id:'lt-timer', qty:1});
await document.modelContext.executeTool(a, {product_id:'sticker-set', qty:1});
// → カートパネルが開き、追加された商品がその場で見える（バッジ 1→2、トースト表示）
const c = tools.find(t => t.name === 'get_cart');
await document.modelContext.executeTool(c, {});
// → total: 2700。パネルが閉じていても開いて内容を表示（show_in_browser 既定 true）
const pv = tools.find(t => t.name === 'preview_order');
await document.modelContext.executeTool(pv, {});
// → 画面に注文確認モーダルが開く（AIの提示が人間の画面にも出る）
const o = tools.find(t => t.name === 'confirm_order');
await document.modelContext.executeTool(o, {});
// → 注文番号が返り、画面は自動で注文確定ページ（デモ明記）へ遷移
```

2. その後 **人間が同じ画面をマウスで続けて操作できる**（共存の実演）
3. `logs.html` で channel=WEBMCP の行を見せる

**言いポイント**: 「MCPと違い、サーバーは建てません。**ページ自身がツールを登録**し、
ブラウザ内のエージェントが既存ロジックを呼びます。だから結果が画面に出る」

### 12:30–14:00 まとめ — 4方式の比較表

| | 人間 | MCP | MCP Apps | WebMCP |
|--|------|-----|----------|--------|
| 実行主体 | 人間 | 外部AI | 外部AI | ブラウザ内AI |
| UI | 既存EC画面 | なし（テキスト） | チャット内UI | 既存EC画面 |
| ツール提供者 | — | サーバー | サーバー | ページ自身 |
| 画面に結果 | 当然 | 別途更新が必要 | iframe内 | 自動的に反映 |
| 共通するもの | **サービス層・商品マスター・SQLiteカート・ログ** | | | |

- `logs.html` で4チャネルが混在する画面が一番のまとめ画像
- `↺ デモリセット` で巻き戻せること、4方式で全く同じ ¥2,700 になったことを確認

### 14:00–15:00 質疑

---

## 2. Inspector 接続手順（控え用）

1. `npx -y @modelcontextprotocol/inspector@2.15.0` を起動
2. `http://127.0.0.1:6274?MCP_INSPECTOR_API_TOKEN=<起動時に表示されたトークン>` を開く
3. 「Add Servers」→「Add manually」で **2件登録**：
   - Server ID: `stapy-shop`、Transport: `streamable-http`、URL: `http://127.0.0.1:8000/mcp`
     （通常MCP。UI連携なし9ツールのみ）
   - Server ID: `stapy-shop-apps`、Transport: `streamable-http`、URL: `http://127.0.0.1:8000/mcp-apps`
     （MCP Apps。`apps_*` 10 + `ui_*` 8、UIリソースあり）
4. 各カード右上の **接続スイッチを ON** → `Connected` / `MCP 2025-11-25`
5. stapy-shop（/mcp）: **Tools** タブのみ／ stapy-shop-apps（/mcp-apps）: **Tools** + **Apps** タブ

stdio で接続する場合（全27ツールが1接続に見える統合モード）：
- Transport: `stdio (local process)`、Command: `<project>/.venv/bin/python`、
  Arguments: `-m` `stapy_shop` `--stdio`、Working directory: `<project>`

---

## 3. WebMCP ブラウザの控え

| ブラウザ | 結果 |
|---------|------|
| `/snap/bin/chromium`（156.0.8078.47）+ `--enable-experimental-web-platform-features` | ✅ 動作検証済 |
| `/snap/bin/chromium` + `--enable-features=WebMCPTesting,WebMCP` | ✅ 動作検証済 |
| Google Chrome 144 | ❌ `document.modelContext` 未定義（通常UIは動く） |

**バックアップ**: WebMCPが動かない環境では `docs/screenshots/webmcp.png` と
`tests/e2e.py` の PASS 出力を見せて「この環境ではAPIが未提供」と正直に説明。

---

## 4. トラブルシューティング

| 症状 | 対処 |
|------|------|
| Inspector が `Connected` にならない | サーバーが起動しているか（`curl http://127.0.0.1:8000/api/products`）、URL が `/mcp` か `/mcp-apps` か（末尾スラッシュは両方許容） |
| Apps タブにツールが出ない | `/mcp` 側接続にはUI連携ツールがない。**`/mcp-apps` 接続**に切り替える |
| `Unknown tool` が返る | 接続先のエンドポイントにそのツールが公開されていない（`/mcp` は通常ツールのみ、`/mcp-apps` は `apps_*`/`ui_*` のみ） |
| Apps が真っ白 | Inspector を一度リロード。Messages で `RESOURCES/READ ui://stapy/shop.html` が OK か確認 |
| WebMCP バッジが出ない | Chromium 156 + フラグかを確認。Chrome 144 では現状非対応（仕様上の制約） |
| カートが変 | `curl -X POST http://127.0.0.1:8000/api/demo/reset` で初期化 |
| `resources/read` が Unknown | 旧コードのまま起動している可能性。`@apps.tool`/`add_html_resource` は `MCPServer(extensions=[apps])` より先に実行する必要あり（修正済） |

---

## 5. 質問への想定答え

- **Q. 4方式でロジックは別実装？** → A. いいえ。`service.py` 1つです。
  MCP Apps も WebMCP も最終的に同じ関数を呼びます。
- **Q. カートはどこに？** → A. サーバー SQLite。MCP Apps の iframe から
  追加した商品が、WebUI を開き直すとそのまま見えます。
- **Q. WebMCP と自動操作の違いは？** → A. ページ自身が `document.modelContext`
  に型付きツールを登録する公式APIです。DOM を這い回す自動操作ではありません。
- **Q. セキュリティは？** → A. デモはローカル専用・認証なし共通ID。
  価格は常にサーバーマスターから引き、ui_* は Apps ネゴシエーション済みのみ許可。
  WEBMCP の channel はブラウザ送信値なので監査上の事実ではありません（README制約）。
