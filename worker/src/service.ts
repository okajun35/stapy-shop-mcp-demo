// 共通サービス層の D1 移植（stapy_shop/service.py と同等のロジック）。
// 価格は必ずサーバー側の商品マスターから取得。クライアント送信の価格は信用しない。

import { CATEGORIES, PRODUCTS } from "./generated/products";

export const DEMO_SESSION_ID = "demo";
const MAX_QTY_PER_ITEM = 99;

export class ShopError extends Error {
  constructor(public code: string, message: string) {
    super(message);
    this.name = "ShopError";
  }
}

const norm = (s: string) => s.normalize("NFKC").toLowerCase();

type Product = (typeof PRODUCTS)[number];
const BY_ID = new Map<string, Product>(PRODUCTS.map((p) => [p.id, p]));

export function publicProduct(p: Product) {
  return {
    id: p.id,
    name: p.name,
    price: p.price,
    category: p.category,
    tag: p.tag,
    image: `/images/${p.image}`,
    desc: p.desc,
    stock: p.stock,
    variants: "variants" in p ? (p as any).variants : undefined,
    keywords: p.keywords,
    features: p.features,
    ...("gallery" in p ? { gallery: (p as any).gallery.map((g: string) => `/images/${g}`) } : {}),
    ...("specs" in p ? { specs: (p as any).specs } : {}),
    ...("note" in p ? { note: (p as any).note } : {}),
  };
}

export function listProducts() {
  return PRODUCTS.map(publicProduct);
}

export function listCategories() {
  return CATEGORIES.map((c) => ({
    name: c,
    count: PRODUCTS.filter((p) => p.category === c).length,
  }));
}

export function getProduct(productId: string) {
  const p = BY_ID.get(productId);
  if (!p) throw new ShopError("product_not_found", `商品が見つかりません: ${productId}`);
  return publicProduct(p);
}

export interface SearchParams {
  q?: string;
  categories?: string[] | null;
  max_price?: number | null;
  in_stock_only?: boolean;
  featured_only?: boolean;
  sort?: "recommended" | "price-asc" | "price-desc" | "name";
  channel?: string;
  session_id?: string;
}

export async function searchProducts(db: D1Database, params: SearchParams = {}) {
  const { q = "", categories = null, max_price = null, in_stock_only = false,
    featured_only = false, sort = "recommended", channel, session_id = DEMO_SESSION_ID } = params;
  if (max_price !== null && max_price < 0)
    throw new ShopError("invalid_input", "max_price は 0 以上を指定してください");
  let rows: Product[] = [...PRODUCTS];
  if (categories?.length) rows = rows.filter((p) => categories.includes(p.category));
  if (max_price !== null) rows = rows.filter((p) => p.price <= max_price);
  if (in_stock_only) rows = rows.filter((p) => p.stock > 0);
  if (featured_only) rows = rows.filter((p) => p.tag === "おすすめ" || p.tag === "人気");
  if (q) {
    const nq = norm(q.trim());
    rows = rows.filter((p) => norm(`${p.name} ${p.desc} ${p.keywords} ${p.category}`).includes(nq));
  }
  if (sort === "price-asc") rows.sort((a, b) => a.price - b.price);
  else if (sort === "price-desc") rows.sort((a, b) => b.price - a.price);
  else if (sort === "name") rows.sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
  if (channel)
    await log(db, channel, "search_products",
      `q='${q}' categories=${categories ? JSON.stringify(categories) : null} max_price=${max_price} → ${rows.length}件`,
      session_id);
  return { count: rows.length, products: rows.map(publicProduct) };
}

// --- cart ---------------------------------------------------------------

interface CartRow { item_key: string; product_id: string; variant: string; qty: number }

export async function getCart(db: D1Database, session_id = DEMO_SESSION_ID, channel?: string) {
  const { results } = await db.prepare(
    "SELECT item_key, product_id, variant, qty FROM cart_items WHERE session_id = ? ORDER BY updated_at, item_key"
  ).bind(session_id).all<CartRow>();
  const items = [];
  let total = 0;
  for (const r of results) {
    const p = BY_ID.get(r.product_id);
    if (!p) continue;
    const subtotal = p.price * r.qty;
    total += subtotal;
    items.push({
      key: r.item_key, product_id: r.product_id, variant: r.variant, qty: r.qty,
      name: p.name, price: p.price, image: `/images/${p.image}`, subtotal,
    });
  }
  const cart = { session_id, items, total, count: items.reduce((n, i) => n + i.qty, 0) };
  if (channel)
    await log(db, channel, "get_cart", `${items.length}種 ${cart.count}点 合計¥${total}`, session_id);
  return cart;
}

const itemKey = (productId: string, variant = "") => `${productId}|${variant}`;

function validateQty(qty: unknown, min: number): number {
  if (typeof qty !== "number" || !Number.isInteger(qty))
    throw new ShopError("invalid_input", "qty は整数で指定してください");
  if (qty < min) throw new ShopError("invalid_input", `qty は ${min} 以上を指定してください`);
  if (qty > MAX_QTY_PER_ITEM)
    throw new ShopError("invalid_input", `qty は ${MAX_QTY_PER_ITEM} 以下を指定してください`);
  return qty;
}

function validateVariant(product: Product, variant: string): string {
  const choices = "variants" in product ? (product as any).variants as string[] : undefined;
  if (choices?.length && !choices.includes(variant))
    throw new ShopError("invalid_input",
      `バリアントが不正です: '${variant}'（選択肢: ${choices.join(", ")}）`);
  if (!choices?.length && variant)
    throw new ShopError("invalid_input", `商品 ${product.id} にバリアントはありません`);
  return variant;
}

async function cancelPendingOrders(db: D1Database, session_id: string) {
  await db.prepare(
    "UPDATE orders SET status = 'cancelled' WHERE session_id = ? AND status = 'pending'"
  ).bind(session_id).run();
}

export async function addToCart(db: D1Database, product_id: string, qty = 1, variant = "",
  session_id = DEMO_SESSION_ID, channel = "WEB") {
  const product = getProduct(product_id);
  qty = validateQty(qty, 1);
  variant = validateVariant(BY_ID.get(product_id)!, variant || "");
  const key = itemKey(product_id, variant);
  const cur = await db.prepare(
    "SELECT qty FROM cart_items WHERE session_id = ? AND item_key = ?"
  ).bind(session_id, key).first<{ qty: number }>();
  const existing = cur?.qty ?? 0;
  const newQty = existing + qty;
  if (newQty > product.stock)
    throw new ShopError("out_of_stock",
      `在庫が足りません: ${product.name}（在庫${product.stock}、カート内${existing}＋追加${qty}）`);
  await db.batch([
    db.prepare(
      "INSERT INTO cart_items (session_id, item_key, product_id, variant, qty, updated_at) " +
      "VALUES (?, ?, ?, ?, ?, datetime('now')) " +
      "ON CONFLICT (session_id, item_key) DO UPDATE SET qty = excluded.qty, updated_at = excluded.updated_at"
    ).bind(session_id, key, product_id, variant, newQty),
    db.prepare("UPDATE orders SET status = 'cancelled' WHERE session_id = ? AND status = 'pending'").bind(session_id),
  ]);
  await log(db, channel, "add_to_cart",
    `${product.name} ×${qty}` + (variant ? `（${variant}）` : ""), session_id);
  return getCart(db, session_id);
}

export async function updateCart(db: D1Database, item_key: string, qty: number,
  session_id = DEMO_SESSION_ID, channel = "WEB") {
  const product_id = item_key.split("|")[0];
  const variant = item_key.split("|")[1] ?? "";
  const master = BY_ID.get(product_id);
  if (!master) throw new ShopError("product_not_found", `商品が見つかりません: ${product_id}`);
  qty = validateQty(qty, 0);
  if (qty === 0) return removeFromCart(db, item_key, session_id, channel);
  const product = getProduct(product_id);
  if (qty > product.stock)
    throw new ShopError("out_of_stock", `在庫が足りません: ${product.name}（在庫${product.stock}、指定${qty}）`);
  const cur = await db.prepare(
    "SELECT qty FROM cart_items WHERE session_id = ? AND item_key = ?"
  ).bind(session_id, item_key).first();
  if (!cur) throw new ShopError("item_not_found", `カートに商品がありません: ${item_key}`);
  await db.batch([
    db.prepare(
      "INSERT INTO cart_items (session_id, item_key, product_id, variant, qty, updated_at) " +
      "VALUES (?, ?, ?, ?, ?, datetime('now')) " +
      "ON CONFLICT (session_id, item_key) DO UPDATE SET qty = excluded.qty, updated_at = excluded.updated_at"
    ).bind(session_id, item_key, product_id, variant, qty),
    db.prepare("UPDATE orders SET status = 'cancelled' WHERE session_id = ? AND status = 'pending'").bind(session_id),
  ]);
  await log(db, channel, "update_cart", `${product.name} → ×${qty}`, session_id);
  return getCart(db, session_id);
}

export async function removeFromCart(db: D1Database, item_key: string,
  session_id = DEMO_SESSION_ID, channel = "WEB") {
  const del = await db.prepare(
    "DELETE FROM cart_items WHERE session_id = ? AND item_key = ?"
  ).bind(session_id, item_key).run();
  if (!del.meta.changes) throw new ShopError("item_not_found", `カートに商品がありません: ${item_key}`);
  await cancelPendingOrders(db, session_id);
  const name = BY_ID.get(item_key.split("|")[0])?.name ?? item_key;
  await log(db, channel, "remove_from_cart", `${name} を削除`, session_id);
  return getCart(db, session_id);
}

// --- demo / logs ---------------------------------------------------------

export async function resetDemo(db: D1Database, session_id = DEMO_SESSION_ID, channel = "WEB") {
  const del = await db.prepare("DELETE FROM cart_items WHERE session_id = ?").bind(session_id).run();
  await cancelPendingOrders(db, session_id);
  const removed = del.meta.changes ?? 0;
  await log(db, channel, "reset_demo", `カート ${removed}件をクリア`, session_id);
  return { ok: true, removed_items: removed, cart: await getCart(db, session_id) };
}

export async function log(db: D1Database, channel: string, action: string, detail = "", session_id = "") {
  await db.prepare(
    "INSERT INTO op_log (channel, action, detail, session_id) VALUES (?, ?, ?, ?)"
  ).bind(channel, action, detail, session_id).run();
}

export async function operationLogs(db: D1Database, limit = 100) {
  const { results } = await db.prepare(
    "SELECT id, ts, channel, action, detail, session_id FROM op_log ORDER BY id DESC LIMIT ?"
  ).bind(limit).all();
  return results;
}

// --- orders（2段階デモ注文。実際の決済・発送・在庫確定は行われない）---------

export async function previewOrder(db: D1Database, session_id = DEMO_SESSION_ID, channel = "WEB") {
  const cart = await getCart(db, session_id);
  if (!cart.items.length)
    throw new ShopError("cart_empty", "カートが空です。商品を追加してから確認してください");
  const itemsJson = JSON.stringify(cart.items);
  // 古い pending を cancelled + 新規 pending 作成を1バッチで
  const batch = await db.batch([
    db.prepare("UPDATE orders SET status = 'cancelled' WHERE session_id = ? AND status = 'pending'").bind(session_id),
    db.prepare(
      "INSERT INTO orders (order_no, session_id, items_json, total, channel, status) VALUES ('', ?, ?, ?, ?, 'pending')"
    ).bind(session_id, itemsJson, cart.total, channel),
  ]);
  const lastId = batch[1].meta.last_row_id as number;
  const order_no = `STAPY-DEMO-${String(lastId).padStart(5, "0")}`;
  await db.prepare("UPDATE orders SET order_no = ? WHERE id = ?").bind(order_no, lastId).run();
  await log(db, channel, "preview_order",
    `${order_no}: ${cart.count}点 合計¥${cart.total}（注文内容を提示）`, session_id);
  return {
    order_no, status: "pending", items: cart.items, total: cart.total, count: cart.count,
    demo: true,
    message: "注文内容を確認してください（デモ。実際の決済・発送は行われません）。この内容でよければ confirm_order で確定します。",
  };
}

export async function confirmOrder(db: D1Database, session_id = DEMO_SESSION_ID, channel = "WEB") {
  const pending = await db.prepare(
    "SELECT order_no, items_json, total, channel, status, created_at FROM orders " +
    "WHERE session_id = ? AND status = 'pending' ORDER BY id DESC LIMIT 1"
  ).bind(session_id).first<{ order_no: string; items_json: string; total: number }>();
  if (!pending)
    throw new ShopError("no_pending_order",
      "確定できる注文がありません。先に preview_order で注文内容を提示してください（カート変更で提示はキャンセルされます）");
  // pending→confirmed + カート空化を1バッチ（条件付きUPDATEで二重確定も防止）
  const res = await db.batch([
    db.prepare("UPDATE orders SET status = 'confirmed' WHERE order_no = ? AND status = 'pending'").bind(pending.order_no),
    db.prepare("DELETE FROM cart_items WHERE session_id = ?").bind(session_id),
  ]);
  if (!res[0].meta.changes)
    throw new ShopError("no_pending_order", "確定できる注文がありません。先に preview_order で注文内容を提示してください");
  const items = JSON.parse(pending.items_json) as { qty: number }[];
  const count = items.reduce((n, i) => n + i.qty, 0);
  await log(db, channel, "confirm_order",
    `${pending.order_no}: ${count}点 合計¥${pending.total}（デモ注文を確定）`, session_id);
  return {
    order_no: pending.order_no, status: "confirmed", items, total: pending.total, count,
    demo: true, message: "デモ注文を確定しました（実際の決済・発送は行われません）",
  };
}

export async function getOrder(db: D1Database, order_no: string) {
  const row = await db.prepare(
    "SELECT order_no, session_id, items_json, total, channel, status, created_at FROM orders WHERE order_no = ?"
  ).bind(order_no).first<{ order_no: string; items_json: string; total: number; channel: string; status: string; created_at: string }>();
  if (!row) throw new ShopError("order_not_found", `注文が見つかりません: ${order_no}`);
  const items = JSON.parse(row.items_json) as { qty: number }[];
  return {
    order_no: row.order_no, status: row.status, items, total: row.total,
    count: items.reduce((n, i) => n + i.qty, 0),
    channel: row.channel, created_at: row.created_at, demo: true,
  };
}
