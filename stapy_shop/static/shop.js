/* stapy商店 - fictional demo catalog. All prices, stock, reviews and products are fictional.
   商品マスター・カートはサーバー（/api/*）が正本。このファイルは描画と操作だけを担当する。 */
(() => {
'use strict';
const SESSION = new URLSearchParams(location.search).get('session') || 'demo';
const CHANNEL = 'web';
let products = [];
let byId = {};
let categories = [];
let currentCart = {items: [], total: 0, count: 0};
const asset = p => p.image;
const money = n => '¥' + Number(n).toLocaleString('ja-JP');
const favoriteKey = 'stapy-demo-favorites-v1';
let fallbackFavorites = [];
const icons = {
 search:'<circle cx="11" cy="11" r="7"/><path d="m16 16 5 5"/>',
 cart:'<path d="M3 4h2l2.4 11h11.2l2.4-8H6"/><circle cx="9" cy="20" r="1"/><circle cx="18" cy="20" r="1"/>',
 heart:'<path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 1 0-7.8 7.8L12 21.2l8.8-8.8a5.5 5.5 0 0 0 0-7.8Z"/>',
 user:'<circle cx="12" cy="7" r="4"/><path d="M4 22v-2c0-5 3-8 8-8s8 3 8 8v2"/>',
};
const svgIcon = (name) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[name]||''}</svg>`;
const snakeSvg = (classname='') => `<svg class="${classname}" viewBox="0 0 180 135" xmlns="http://www.w3.org/2000/svg" aria-hidden="true"><path d="M58 105c-13-2-29-11-29-30 0-17 18-22 30-16 17 8 15 26 0 28s-16-15-6-22" fill="none" stroke="#27496e" stroke-width="21" stroke-linecap="round"/><path d="M58 105c-13-2-29-11-29-30 0-17 18-22 30-16 17 8 15 26 0 28s-16-15-6-22" fill="none" stroke="#b6d747" stroke-width="16" stroke-linecap="round"/><path d="M61 55c-6-24 10-42 30-40 24 2 36 26 24 43-8 11-27 14-39 8" fill="#b9dd4c" stroke="#2d4c6d" stroke-width="4"/><ellipse cx="94" cy="37" rx="4" ry="6" fill="#203c54"/><circle cx="96" cy="35" r="1.5" fill="white"/><path d="M115 51q7 5 15 0" stroke="#29466a" stroke-width="3" fill="none"/><path d="M125 51l16 7-9 6" stroke="#f18588" stroke-width="5" fill="none" stroke-linejoin="round" stroke-linecap="round"/><path d="M65 109Q92 86 111 109T152 107" fill="none" stroke="#254769" stroke-width="20" stroke-linecap="round"/><path d="M65 109Q92 86 111 109T152 107" fill="none" stroke="#b9dc43" stroke-width="15" stroke-linecap="round"/><path d="m52 101 6 11m40-12 6 10m41-10 6 9" stroke="#e9f38f" stroke-width="7" stroke-linecap="round"/></svg>`;

// --- サーバー API ------------------------------------------------------
async function api(path, {method='GET', body, channel=CHANNEL} = {}) {
  const headers = {'X-Stapy-Session': SESSION};
  if (channel) headers['X-Stapy-Channel'] = channel;
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  const res = await fetch(path, {method, headers, body: body !== undefined ? JSON.stringify(body) : undefined});
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(data?.error?.message || `API error ${res.status}`);
    err.code = data?.error?.code;
    throw err;
  }
  return data;
}

function load(key, fallback){try{return JSON.parse(localStorage.getItem(key)) ?? fallback;}catch(_){return fallback;}}
function save(key,data){try{localStorage.setItem(key,JSON.stringify(data));}catch(_){}}
function favorites(){return load(favoriteKey, fallbackFavorites);}
function saveFavorites(arr){fallbackFavorites=arr;save(favoriteKey,arr);}
function updateCartCount(){document.querySelectorAll('.cart-count').forEach(el=>el.textContent=currentCart.count);}
function toast(message){const r=document.getElementById('toast-region');if(!r)return;r.replaceChildren();const e=document.createElement('div');e.className='toast';e.textContent=message;r.append(e);setTimeout(()=>{if(e.parentNode)e.remove();},2800);}

async function refreshCart() {
  currentCart = await api('/api/cart');
  updateCartCount();
  renderCart();
  return currentCart;
}
async function addToCart(id, qty=1, variant='') {
  const p = byId[id]; if (!p) return;
  try {
    await api('/api/cart/items', {method:'POST', body:{product_id:id, qty, variant}});
    await refreshCart();
    toast(`「${p.name}」をカートに追加しました`);
  } catch (e) { toast(e.message); }
}
async function removeCartItem(key) {
  try { await api('/api/cart/items/' + encodeURIComponent(key), {method:'DELETE'}); await refreshCart(); }
  catch (e) { toast(e.message); }
}
async function changeCartQty(key, delta) {
  const item = currentCart.items.find(i => i.key === key); if (!item) return;
  try {
    await api('/api/cart/items/' + encodeURIComponent(key), {method:'PATCH', body:{qty:item.qty + delta}});
    await refreshCart();
  } catch (e) { toast(e.message); }
}
function openCart(){document.body.classList.add('cart-open');document.getElementById('cart-close')?.focus();refreshCart();}
function closeCart(){document.body.classList.remove('cart-open');}

function makeHeader(){document.getElementById('site-header').innerHTML=`<header class="topbar"><div class="topbar-inner"><a href="/" class="brand" aria-label="stapy商店 トップ">${snakeSvg('brand-mark')}<div><div class="brand-name">stapy商店<span class="brand-spark">〰</span></div><div class="brand-sub">Start Python Club Shop</div></div></a><nav class="primary-nav" aria-label="メインナビ"><a class="active" href="/">商品一覧</a><a href="/#main">カテゴリ</a><a href="/?featured=1">人気商品</a><a href="/detail.html?product=starter-bundle">特集・セット</a><a href="/logs.html">操作ログ</a></nav><form class="header-search" action="/" method="get" role="search">${svgIcon('search')}<input type="search" id="site-search" name="q" placeholder="商品を検索（例：LT、Tシャツ）" aria-label="商品を検索" autocomplete="off"></form><div class="header-tools"><button type="button" class="header-tool" id="demo-login" title="デモのためログイン不要">${svgIcon('user')}<span class="tool-label">ログイン</span></button><button type="button" class="header-tool" id="favorite-button" title="お気に入り">${svgIcon('heart')}<span class="tool-label">お気に入り</span></button><button type="button" class="header-tool" id="cart-button" title="カートを開く">${svgIcon('cart')}<span class="tool-label">カート</span><span class="cart-count">0</span></button></div></div></header><div class="demo-banner">これは勉強会用の非公式・架空ECデモです。実際の商品販売・決済・発送はありません。<button type="button" id="demo-reset" class="demo-reset-btn">↺ デモリセット</button></div>`;
 const heroEl=document.getElementById('hero');if(heroEl)heroEl.innerHTML=`<section class="hero"><div class="hero-inner">${snakeSvg('hero-mascot')}<div class="hero-message"><h2 class="hero-title">Start Python Club <span class="highlight">グッズ商店</span></h2><p class="hero-subtitle">Pythonをもっと楽しく、もっとつながる。20種類の架空グッズをご紹介。</p><span class="hero-note">stapy商店 — コミュニティを題材にしたECデモ</span></div><div class="hero-badges"><div class="round-badge dark"><span><span class="badge-small">START PYTHON CLUB</span><span class="badge-glyph">♧</span>PyCon 2026<br><span class="badge-small">in Hiroshima</span></span></div><div class="round-badge pizza"><span>Start<br>Python<br>Club<br><span class="badge-small">2026</span></span></div></div></div></section>`;
 document.getElementById('site-footer').innerHTML=`<footer class="footer"><div class="footer-inner"><div class="footer-title">${snakeSvg('')}<div><strong>stapy商店</strong><small>Start Python Club Shop / 架空のオンラインショップ</small></div></div><div class="footer-blurb"><span class="footer-icon">♧</span>Python好きの<br>コミュニティ</div><div class="footer-blurb"><span class="footer-icon">▣</span>5,000円以上で<br>送料無料（架空）</div><div class="footer-blurb"><span class="footer-icon">🎁</span>勉強会デモ向け<br>模擬商品20点</div></div><div class="footer-disclaimer">※ 非公式のデモサイトです。商品・価格・在庫・レビュー・配送条件はすべて架空です。Start Python Clubによる販売ではありません。</div></footer>`;
 document.getElementById('cart-root').innerHTML=`<div class="cart-backdrop" id="cart-backdrop"></div><aside class="cart-drawer" role="dialog" aria-label="ショッピングカート" aria-modal="true"><div class="cart-top"><h2>🛒 カート <span class="cart-count">0</span></h2><button type="button" class="close-button" id="cart-close" aria-label="カートを閉じる">×</button></div><div id="cart-items" class="cart-items"></div><div class="cart-bottom"><div class="cart-total"><span>合計（税込・架空）</span><strong id="cart-total">¥0</strong></div><button class="button button-lime" id="mock-checkout" type="button">注文を確認する（デモ）</button><p style="font-size:11px;color:#65748b;margin:8px 0 0">実際の注文・決済は発生しません。</p></div></aside>`;
 document.getElementById('cart-button').addEventListener('click',openCart);
 document.getElementById('cart-backdrop').addEventListener('click',closeCart);
 document.getElementById('cart-close').addEventListener('click',closeCart);
 document.getElementById('mock-checkout').addEventListener('click',async()=>{
   try {
     const r = await api('/api/orders',{method:'POST'});
     location.href = '/order_complete.html?order=' + encodeURIComponent(r.order_no);
   } catch(e) {
     toast(e.code==='cart_empty' ? 'カートが空です。商品を追加してから確定してください' : ('注文確定に失敗しました: '+e.message));
   }
 });
 document.getElementById('demo-login').addEventListener('click',()=>toast('デモサイトのためログインは不要です'));
 document.getElementById('favorite-button').addEventListener('click',()=>toast(`お気に入り：${favorites().length}商品（デモ）`));
 document.getElementById('demo-reset').addEventListener('click',async()=>{await api('/api/demo/reset',{method:'POST'});await refreshCart();toast('デモをリセットしました（カートは空です）');});
 window.addEventListener('keydown',e=>{if(e.key==='Escape')closeCart();});
 document.querySelector('#cart-items').addEventListener('click',e=>{const b=e.target.closest('[data-cart-op]');if(!b)return;const k=b.dataset.key;switch(b.dataset.cartOp){case'plus':changeCartQty(k,1);break;case'minus':changeCartQty(k,-1);break;case'remove':removeCartItem(k);break;}});
}

function renderCart(){const wrap=document.getElementById('cart-items');if(!wrap)return;const items=currentCart.items||[];if(!items.length){wrap.innerHTML='<div class="cart-empty">カートは空です。<br>商品を選んで追加してみてください。</div>';document.getElementById('cart-total').textContent='¥0';return;}wrap.innerHTML=items.map(v=>{const p=byId[v.product_id]||{name:v.name,image:v.image};return `<div class="cart-item"><img src="${v.image}" alt=""><div class="cart-item-main"><strong>${v.name}</strong><small>${v.variant?'サイズ：'+v.variant+' / ':''}${money(v.price)} × ${v.qty}</small><div class="cart-item-tools"><div><button type="button" data-cart-op="minus" data-key="${v.key}" aria-label="${v.name}を1個減らす">−</button> <strong>${v.qty}</strong> <button type="button" data-cart-op="plus" data-key="${v.key}" aria-label="${v.name}を1個増やす">＋</button></div><button type="button" data-cart-op="remove" data-key="${v.key}">削除</button></div></div></div>`;}).join('');document.getElementById('cart-total').textContent=money(currentCart.total);}

function card(p){const tagClass = p.tag==='新着'?'new':p.tag==='セット'?'bundle':'';return `<article class="product-card" data-product-id="${p.id}"><a class="image-link" href="/detail.html?product=${p.id}" aria-label="${p.name}の詳細を見る"><img loading="lazy" src="${asset(p)}" alt="${p.name}の商品イメージ">${p.tag?`<span class="card-tag ${tagClass}">${p.tag}</span>`:''}</a><div class="card-body"><h3><a href="/detail.html?product=${p.id}">${p.name}</a></h3><p class="card-desc">${p.desc}</p><div class="card-price">${money(p.price)}</div><button type="button" class="card-cta" data-add="${p.id}" aria-label="${p.name}をカートに追加">＋ カートに追加</button></div></article>`;}
function resetFilters(){document.querySelectorAll('.category-check').forEach(x=>x.checked=false);document.getElementById('price-filter').value='10000';document.getElementById('stock-filter').checked=true;document.getElementById('featured-filter').checked=false;document.getElementById('site-search').value='';document.getElementById('sort-products').value='recommended';renderCatalog();}
function renderCatalog(){const q=document.getElementById('site-search').value.toLocaleLowerCase().normalize('NFKC').trim();const active=Array.from(document.querySelectorAll('.category-check:checked')).map(el=>el.value);const max=Number(document.getElementById('price-filter').value);document.getElementById('price-current').textContent=money(max);let rows=products.filter(p=>(!active.length||active.includes(p.category))&&p.price<=max&&(!document.getElementById('stock-filter').checked||p.stock>0)&&(!document.getElementById('featured-filter').checked||p.tag==='おすすめ'||p.tag==='人気')&&(!q||(`${p.name} ${p.desc} ${p.keywords} ${p.category}`).toLocaleLowerCase().normalize('NFKC').includes(q)));
 switch(document.getElementById('sort-products').value){case'price-asc':rows.sort((a,b)=>a.price-b.price);break;case'price-desc':rows.sort((a,b)=>b.price-a.price);break;case'name':rows.sort((a,b)=>a.name.localeCompare(b.name,'ja'));break;}
 document.getElementById('results-count').textContent=`（全${rows.length}件）`;document.getElementById('product-grid').innerHTML=rows.map(card).join('');document.getElementById('empty-results').hidden=!!rows.length;return rows;}
function initCatalog(){const categoryRoot=document.getElementById('category-filters');categoryRoot.innerHTML=categories.map(c=>{const count=products.filter(p=>p.category===c.name).length;return `<label class="checkline"><input class="category-check" type="checkbox" value="${c.name}"><span>${c.name} (${count})</span></label>`;}).join('');const params=new URLSearchParams(location.search);const q=params.get('q')||'';document.getElementById('site-search').value=q;document.getElementById('featured-filter').checked=params.get('featured')==='1';document.querySelector('.header-search').addEventListener('submit',e=>{e.preventDefault();renderCatalog();document.getElementById('main').scrollIntoView({behavior:'smooth'});});document.getElementById('site-search').addEventListener('input',renderCatalog);document.getElementById('price-filter').addEventListener('input',renderCatalog);document.getElementById('stock-filter').addEventListener('change',renderCatalog);document.getElementById('featured-filter').addEventListener('change',renderCatalog);document.getElementById('sort-products').addEventListener('change',renderCatalog);categoryRoot.addEventListener('change',renderCatalog);document.getElementById('reset-filters').addEventListener('click',resetFilters);document.getElementById('empty-reset').addEventListener('click',resetFilters);document.getElementById('product-grid').addEventListener('click',e=>{const b=e.target.closest('[data-add]');if(b)addToCart(b.dataset.add);});renderCatalog();}
const reviewData=[['LT登壇者さん','★★★★★','5.0','5分の時間管理に使いやすいデザインでした。'],['勉強会スタッフさん','★★★★★','5.0','残り時間をひと目で確認できるのが便利そうです。'],['Python学習中さん','★★★★☆','4.0','机の上に置いて使いたくなるサイズ感です。']];
function renderDetail(){const id=new URLSearchParams(location.search).get('product')||'lt-timer';const p=byId[id]||byId['lt-timer'];document.title=`${p.name} | stapy商店 — ECデモ`;document.getElementById('breadcrumb-name').textContent=p.name;const gallery=p.gallery||[p.image];const specs=p.specs||[['商品名',p.name],['カテゴリ',p.category],['価格',money(p.price)+'（架空）'],['在庫',`${p.stock}個（架空）`],['用途',p.desc],['注意','実物は存在しません']];let qty=1;const fav=favorites().includes(p.id);
 document.getElementById('product-detail').innerHTML=`<section class="detail-top"><div class="gallery"><div class="gallery-main"><img id="gallery-large" src="${gallery[0]}" alt="${p.name}の商品イメージ"><span class="gallery-overlay">${p.tag||'stapy商店'}</span></div><div class="gallery-thumbs">${gallery.map((im,i)=>`<button class="gallery-thumb ${i===0?'selected':''}" data-gallery="${im}" aria-label="画像${i+1}を表示" type="button"><img src="${im}" alt="${p.name}の画像${i+1}"></button>`).join('')}</div></div><div class="product-summary"><div class="product-pills"><span class="pill">${p.category}</span>${p.tag?`<span class="pill green">${p.tag}</span>`:''}</div><h1>${p.name}</h1><div class="detail-price">${money(p.price)} <span>（税込・架空）</span></div><p class="product-intro">${p.desc}<br>Start Python Clubを題材にした架空のオリジナルグッズです。</p><div class="features">${p.features.map((f,i)=>`<div class="feature"><div class="feature-icon">${['◴','◉','♧','▢'][i%4]}</div><div><strong>${f}</strong><span>${['使いやすさを意識したデモ用デザイン。','イベントや学習の日常に取り入れたくなる仕様。','stapyのモチーフをあしらっています。','ギフトとしてもイメージしやすいアイテムです。'][i%4]}</span></div></div>`).join('')}</div></div><aside class="purchase-panel"><div class="stock-line">✓ 在庫あり <small>（架空・残り${p.stock}点）</small></div>${p.variants?`<label class="variant-label">サイズ<select class="variant-select" id="product-variant">${p.variants.map(v=>`<option value="${v}">${v}</option>`).join('')}</select></label>`:''}<div class="qty-label">数量</div><div class="quantity-stepper"><button type="button" id="qty-minus" aria-label="数量を減らす">−</button><span id="qty-value">1</span><button type="button" id="qty-plus" aria-label="数量を増やす">＋</button></div><button type="button" class="button button-primary" id="detail-add">＋ カートに追加</button><button type="button" class="button button-lime" id="detail-buy">カートを確認する（デモ）</button><button type="button" class="text-action" id="detail-fav">${fav?'♥ お気に入りを解除':'♡ お気に入りに追加'}</button><p class="purchase-note">デモのため実際の決済・配送は行われません。</p></aside></section><section class="detail-specs"><h2>商品仕様</h2><table class="spec-table"><tbody>${specs.map(([k,v])=>`<tr><th>${k}</th><td>${v}</td></tr>`).join('')}</tbody></table>${p.note?`<p class="spec-note">※ ${p.note}</p>`:''}</section><section class="detail-reviews"><h2>レビュー（架空）</h2>${reviewData.map(([who,stars,score,text])=>`<div class="review"><div class="review-head"><strong>${who}</strong><span class="review-stars">${stars}</span><span class="review-score">${score}</span></div><p>${text}</p></div>`).join('')}</section>`;
 const thumbs=document.querySelector('.gallery-thumbs');thumbs.addEventListener('click',e=>{const b=e.target.closest('[data-gallery]');if(!b)return;document.getElementById('gallery-large').src=b.dataset.gallery;thumbs.querySelectorAll('.gallery-thumb').forEach(el=>el.classList.toggle('selected',el===b));});
 const refreshQty=()=>document.getElementById('qty-value').textContent=qty;
 document.getElementById('qty-minus').addEventListener('click',()=>{qty=Math.max(1,qty-1);refreshQty();});
 document.getElementById('qty-plus').addEventListener('click',()=>{qty=Math.min(p.stock,qty+1);refreshQty();});
 const doAdd=()=>addToCart(p.id,qty,document.getElementById('product-variant')?.value||'');
 document.getElementById('detail-add').addEventListener('click',doAdd);
 document.getElementById('detail-buy').addEventListener('click',()=>{doAdd();openCart();});
 document.getElementById('detail-fav').addEventListener('click',()=>{const arr=favorites();const on=arr.includes(p.id);saveFavorites(on?arr.filter(id=>id!==p.id):[...arr,p.id]);document.getElementById('detail-fav').textContent=on?'♡ お気に入りに追加':'♥ お気に入りを解除';toast(on?'お気に入りから解除しました':'お気に入りに追加しました');});
 const related=p.id==='lt-timer'?['sticker-set','navy-tshirt','event-badge','exception-game'].map(k=>byId[k]):products.filter(x=>x.id!==p.id).sort((a,b)=>(a.category===p.category?-1:0)-(b.category===p.category?-1:0)).slice(0,4);
 document.getElementById('related-products').innerHTML=related.map(x=>`<article class="related-card"><a href="/detail.html?product=${x.id}"><img loading="lazy" src="${x.image}" alt="${x.name}"></a><div class="related-copy"><h3><a href="/detail.html?product=${x.id}">${x.name}</a></h3><p>${x.desc}</p><strong>${money(x.price)}</strong></div></article>`).join('');
 document.querySelector('.header-search').addEventListener('submit',e=>{e.preventDefault();const val=document.getElementById('site-search').value.trim();location.href='/?q='+encodeURIComponent(val);});
}

// --- 起動 ---------------------------------------------------------------
async function boot(){
  const [prodData, catData] = await Promise.all([
    api('/api/products'),
    api('/api/categories'),
  ]);
  products = prodData.products;
  byId = Object.fromEntries(products.map(p => [p.id, p]));
  categories = catData.categories;
  makeHeader();
  if (document.body.dataset.page==='catalog') initCatalog();
  if (document.body.dataset.page==='detail') renderDetail();
  await refreshCart();
  // WebMCP ツールが画面ロジックを再利用するための公開フック
  window.__stapy = {
    session: SESSION,
    api,
    products,
    byId,
    renderCatalog,
    refreshCart,
    openCart,
    toast,
    applySearch(q, maxPrice){
      const s = document.getElementById('site-search');
      if (s) { s.value = q || ''; }
      const pf = document.getElementById('price-filter');
      if (pf && maxPrice != null) { pf.value = String(maxPrice); }
      if (document.body.dataset.page==='catalog') {
        const rows = renderCatalog();
        document.getElementById('main').scrollIntoView({behavior:'smooth'});
        return rows.map(p => ({id:p.id, name:p.name, price:p.price, stock:p.stock}));
      }
      return null;
    },
    openProduct(id){ location.href = '/detail.html?product=' + encodeURIComponent(id); },
  };
  document.dispatchEvent(new CustomEvent('stapy:ready'));
}
document.addEventListener('DOMContentLoaded',()=>{boot().catch(e=>{document.body.insertAdjacentHTML('beforeend',`<div style="position:fixed;inset:auto 0 0 0;background:#b91c1c;color:#fff;padding:12px 20px;font:13px/1.4 sans-serif;z-index:99">起動失敗: ${e.message}（サーバーが起動しているか確認してください）</div>`);});});
})();
