/* stapy商店 WebMCP ツール登録。
   公式 WebMCP API（document.modelContext.registerTool）で、
   ECサイトの検索・詳細・カート操作をブラウザエージェントへ公開する。

   - API 非対応ブラウザでは何もせず、通常のEC機能はそのまま動く
   - ツールの実行は既存の画面ロジック（window.__stapy）と共通REST APIを使い、
     AIの操作結果がそのまま画面（検索結果・カートバッジ）に反映される
   - ツール呼び出しは X-Stapy-Channel: webmcp を付けて REST API を呼び、
     操作ログでは WEBMCP として記録される（デモ用のベストエフォート識別） */
(() => {
'use strict';
if (!('modelContext' in document)) return;  // WebMCP 非対応: 通常サイトとして継続
if (window.__stapyWebMcp) return;             // 二重読み込み防止
window.__stapyWebMcp = true;

// ページ遷移で Document が破棄されるとツールも消えるが、
// 明示的なライフサイクル管理として pagehide で登録解除する
const lifecycle = new AbortController();
window.addEventListener('pagehide', () => lifecycle.abort());

function whenReady() {
  if (window.__stapy) return Promise.resolve(window.__stapy);
  return new Promise(resolve =>
    document.addEventListener('stapy:ready', () => resolve(window.__stapy), {once: true}));
}

const agentApi = (path, opts = {}) =>
  window.__stapy.api(path, {...opts, channel: 'webmcp'});

const tools = [
  {
    name: 'search_products',
    title: '商品を検索',
    description: 'stapy商店の商品を検索します。キーワード・価格上限を指定でき、検索結果は画面上の商品一覧にも反映されます。',
    inputSchema: {
      type: 'object',
      properties: {
        query: {type: 'string', description: '検索キーワード（例: "LT", "タイマー", "ステッカー"）。空文字で全件。'},
        max_price: {type: 'integer', minimum: 0, maximum: 10000, description: '価格上限（円）。省略時は上限なし。'},
      },
    },
    annotations: {readOnlyHint: true},
    execute: async ({query = '', max_price} = {}) => {
      const params = new URLSearchParams();
      if (query) params.set('q', query);
      if (max_price != null) params.set('max_price', String(max_price));
      const data = await agentApi('/api/products?' + params);
      // サーバー側の検索結果を既存の画面にも反映（人間の検索操作と同じ見え方）
      const shown = window.__stapy.applySearch(query, max_price);
      return {
        count: data.count,
        products: data.products.map(p => ({id: p.id, name: p.name, price: p.price, stock: p.stock})),
        displayed_on_page: shown ? shown.length : null,
      };
    },
  },
  {
    name: 'get_product',
    title: '商品詳細を取得',
    description: '商品IDから詳細情報（価格・在庫・説明・特徴）を取得します。open_in_browser=true で画面に商品ページを表示します。',
    inputSchema: {
      type: 'object',
      properties: {
        product_id: {type: 'string', description: '商品ID（例: "lt-timer", "sticker-set"）'},
        open_in_browser: {type: 'boolean', description: 'true にするとブラウザ画面を商品詳細ページへ遷移させる', default: false},
      },
      required: ['product_id'],
    },
    annotations: {readOnlyHint: true},
    execute: async ({product_id, open_in_browser = false} = {}) => {
      const product = await agentApi('/api/products/' + encodeURIComponent(product_id));
      const cardEl = document.querySelector(`[data-product-id="${CSS.escape(product_id)}"]`);
      if (cardEl) cardEl.scrollIntoView({behavior: 'smooth', block: 'center'});
      if (open_in_browser) window.__stapy.openProduct(product_id);
      return product;
    },
  },
  {
    name: 'get_cart',
    title: 'カート内容を確認・表示',
    description: '共有デモカートの内容（明細・数量・合計金額）を取得し、画面上のカートパネルも開いて内容を表示します。',
    inputSchema: {
      type: 'object',
      properties: {
        show_in_browser: {type: 'boolean', description: 'true で画面上のカートパネルを開く（既定: true）', default: true},
      },
    },
    annotations: {readOnlyHint: true},
    execute: async ({show_in_browser = true} = {}) => {
      const cart = await agentApi('/api/cart');
      await window.__stapy.refreshCart();  // 画面上のバッジも最新に
      if (show_in_browser) window.__stapy.openCart();
      return cart;
    },
  },
  {
    name: 'add_to_cart',
    title: 'カートに追加',
    description: '商品を共有デモカートに追加します。画面上のカートパネルが開き、追加された商品が見えます。',
    inputSchema: {
      type: 'object',
      properties: {
        product_id: {type: 'string', description: '商品ID（例: "lt-timer"）'},
        qty: {type: 'integer', minimum: 1, maximum: 99, description: '数量（1-99）', default: 1},
        variant: {type: 'string', description: 'サイズ等のバリアント（Tシャツ・フーディーのみ。例: "M"）', default: ''},
      },
      required: ['product_id'],
    },
    annotations: {readOnlyHint: false, consequentialHint: true},
    execute: async ({product_id, qty = 1, variant = ''} = {}) => {
      const cart = await agentApi('/api/cart/items', {
        method: 'POST',
        body: {product_id, qty, variant},
      });
      await window.__stapy.refreshCart();
      window.__stapy.openCart();  // 追加結果が見えるようカートパネルを開く
      const p = window.__stapy.byId[product_id];
      window.__stapy.toast(`AIが「${p ? p.name : product_id}」をカートに追加しました`);
      return cart;
    },
  },
  {
    name: 'update_cart',
    title: 'カート数量を変更',
    description: 'カート内商品の数量を変更します。qty=0 で削除と同等です。画面上のカートパネルが開きます。',
    inputSchema: {
      type: 'object',
      properties: {
        item_key: {type: 'string', description: 'カート内商品キー（get_cart が返す key。例: "lt-timer|"）'},
        qty: {type: 'integer', minimum: 0, maximum: 99, description: '新しい数量（0で削除）'},
      },
      required: ['item_key', 'qty'],
    },
    annotations: {readOnlyHint: false, consequentialHint: true},
    execute: async ({item_key, qty} = {}) => {
      const cart = await agentApi('/api/cart/items/' + encodeURIComponent(item_key), {
        method: 'PATCH',
        body: {qty},
      });
      await window.__stapy.refreshCart();
      window.__stapy.openCart();
      return cart;
    },
  },
  {
    name: 'remove_from_cart',
    title: 'カートから削除',
    description: 'カートから商品を削除します。画面上のカートパネルが開きます。',
    inputSchema: {
      type: 'object',
      properties: {
        item_key: {type: 'string', description: 'カート内商品キー（get_cart が返す key）'},
      },
      required: ['item_key'],
    },
    annotations: {readOnlyHint: false, consequentialHint: true},
    execute: async ({item_key} = {}) => {
      const cart = await agentApi('/api/cart/items/' + encodeURIComponent(item_key), {
        method: 'DELETE',
      });
      await window.__stapy.refreshCart();
      window.__stapy.openCart();
      return cart;
    },
  },
  {
    name: 'preview_order',
    title: '注文内容を確認（デモ）',
    description: 'カート内容を「注文内容の確認」として提示します（まだ確定しません）。画面に確認モーダルも表示されます。実際の決済・発送は行われません。',
    inputSchema: {type: 'object', properties: {}},
    annotations: {readOnlyHint: false, consequentialHint: false},
    execute: async () => {
      const preview = await agentApi('/api/orders/preview', {method: 'POST'});
      // AIが提示した内容が画面にも見えるよう、既存の確認モーダルを開く
      window.__stapy.showOrderConfirm?.(preview);
      return preview;
    },
  },
  {
    name: 'confirm_order',
    title: '注文を確定（デモ）',
    description: 'preview_order で提示した内容をデモ注文として確定します（先に preview_order が必要）。確定後カートは空になり、画面は注文確定ページへ遷移します。実際の決済・発送は行われません。',
    inputSchema: {type: 'object', properties: {}},
    annotations: {readOnlyHint: false, consequentialHint: true},
    execute: async () => {
      const order = await agentApi('/api/orders/confirm', {method: 'POST'});
      // AIの確定結果が画面にも見えるよう、既存の確定ページへ遷移する
      location.href = '/order_complete.html?order=' + encodeURIComponent(order.order_no);
      return order;
    },
  },
];

async function register() {
  await whenReady();
  let registered = 0;
  for (const tool of tools) {
    try {
      await document.modelContext.registerTool(tool, {signal: lifecycle.signal});
      registered++;
    } catch (e) {
      // InvalidStateError = 同名ツール登録済み。重複は無視して継続。
      if (e && e.name !== 'InvalidStateError') console.warn('[webmcp]', e);
    }
  }
  // 画面上に WebMCP 有効を表示（デモ用の目印）
  const banner = document.querySelector('.demo-banner');
  if (banner && registered) {
    const badge = document.createElement('span');
    badge.className = 'webmcp-badge';
    badge.textContent = `WebMCP: ${registered}ツール公開中`;
    banner.appendChild(badge);
  }
  document.dispatchEvent(new CustomEvent('stapy:webmcp-registered', {detail: {count: registered}}));
}

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', register);
else register();
})();
