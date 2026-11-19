// stapy商店 MCPデモ — Cloudflare Workers 版。
// FastAPI(api.py) + SQLite(db.py) → Workers fetch + D1 への移植。
// REST /api/*・MCP Streamable HTTP /mcp・静的アセットを同一Workerで提供。
// 実際の販売・決済・発送は行われない（勉強会デモ）。

import { TOOLS_LIST, RESOURCES_LIST, INSTRUCTIONS_PLAIN, INSTRUCTIONS_APPS } from "./generated/tools";
import { SHOP_HTML } from "./generated/uiHtml";
import * as svc from "./service";
import { ShopError, DEMO_SESSION_ID } from "./service";

export interface Env {
  DB: D1Database;
  ASSETS: Fetcher;
}

const SHOP_UI_URI = "ui://stapy/shop.html";
const APP_MIME = "text/html;profile=mcp-app";
const UI_EXT = "io.modelcontextprotocol/ui";

const ERR_STATUS: Record<string, number> = {
  product_not_found: 404, item_not_found: 404, order_not_found: 404,
  invalid_input: 400, cart_empty: 409, out_of_stock: 409, no_pending_order: 409,
};

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, PATCH, DELETE, OPTIONS",
  "Access-Control-Allow-Headers":
    "Content-Type, MCP-Session-Id, MCP-Protocol-Version, X-Stapy-Session, X-Stapy-Channel",
  "Access-Control-Expose-Headers": "MCP-Session-Id",
};

function json(data: unknown, status = 200, extra: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json", ...CORS, ...extra },
  });
}

function sse(payload: unknown, status = 200, extra: Record<string, string> = {}): Response {
  // Streamable HTTP: 単一応答も SSE フレームで返す（参照実装と同じ形式）
  const body = `event: message\ndata: ${JSON.stringify(payload)}\n\n`;
  return new Response(body, {
    status,
    headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache", ...CORS, ...extra },
  });
}

// クライアントが text/event-stream を受け付けない場合は application/json で返す。
// （仕様上は Accept: application/json, text/event-stream の両方必須だが、
//   JSONボディのみ処理するコネクタ向けの互換措置）
function mcpReply(req: Request, payload: unknown, status = 200, extra: Record<string, string> = {}): Response {
  const accept = req.headers.get("accept") ?? "";
  return accept.includes("text/event-stream") ? sse(payload, status, extra) : json(payload, status, extra);
}

const sessionOf = (req: Request) =>
  new URL(req.url).searchParams.get("session") || req.headers.get("x-stapy-session") || DEMO_SESSION_ID;

const channelOf = (req: Request) =>
  req.headers.get("x-stapy-channel") === "webmcp" ? "WEBMCP" : "WEB";

function shopErr(e: unknown): Response {
  if (e instanceof ShopError)
    return json({ error: { code: e.code, message: e.message } }, ERR_STATUS[e.code] ?? 400);
  throw e;
}

// ---------------------------------------------------------------------------
// MCP ツール実装（mcp_server.py と同じ応答テキストを再現）
// ---------------------------------------------------------------------------

// 第3引数 action には呼ばれたツール名、第4引数 channel にはエンドポイント由来の
// ログチャネルが入る（/mcp → "MCP"、/mcp-apps → "MCP_APPS"）。
// apps_* ツールは同名実装を共有しつつ、ログ上は apps_* 名・MCP_APPS で残る。
type ToolFn = (env: Env, args: any, action: string, channel: string) => Promise<{ text: string; data?: any }>;

const MODEL_TOOLS: Record<string, ToolFn> = {
  async search_products(env, a, action, channel) {
    const r = await svc.searchProducts(env.DB, {
      q: a?.q ?? "", categories: a?.category ? [a.category] : null,
      max_price: a?.max_price ?? null, sort: a?.sort ?? "recommended",
      channel: channel, session_id: DEMO_SESSION_ID, action,
    });
    const lines = [`検索結果 ${r.count}件:`,
      ...r.products.map((p: any) => `- ${p.name}（${p.id}）¥${p.price} 在庫${p.stock}`)];
    return { text: lines.join("\n"), data: r };
  },
  async get_product(env, a, action, channel) {
    const p = svc.getProduct(a?.product_id);
    await svc.log(env.DB, channel, action, p.name, DEMO_SESSION_ID);
    return { text: `${p.name} ¥${p.price} 在庫${p.stock}\n${JSON.stringify(p)}`, data: { product: p } };
  },
  async get_cart(env, _a, action, channel) {
    const cart = await svc.getCart(env.DB, DEMO_SESSION_ID, channel, action);
    const text = cart.items.length
      ? [`カート: ${cart.count}点 合計 ¥${cart.total}`,
        ...cart.items.map((i: any) => `- ${i.name} ×${i.qty} = ¥${i.subtotal}（key: ${i.key}）`)].join("\n")
      : "カートは空です。";
    return { text, data: cart };
  },
  async add_to_cart(env, a, action, channel) {
    const cart = await svc.addToCart(env.DB, a?.product_id, a?.qty ?? 1, a?.variant ?? "", DEMO_SESSION_ID, channel, action);
    return {
      text: `カートに追加しました。現在 ${cart.count}点・合計 ¥${cart.total} です。`,
      data: { added: { product_id: a?.product_id, qty: a?.qty ?? 1, variant: a?.variant ?? "" }, cart },
    };
  },
  async update_cart(env, a, action, channel) {
    const cart = await svc.updateCart(env.DB, a?.item_key, a?.qty, DEMO_SESSION_ID, channel, action);
    return { text: `数量を更新しました。現在 ${cart.count}点・合計 ¥${cart.total} です。`, data: cart };
  },
  async remove_from_cart(env, a, action, channel) {
    const cart = await svc.removeFromCart(env.DB, a?.item_key, DEMO_SESSION_ID, channel, action);
    return { text: `削除しました。現在 ${cart.count}点・合計 ¥${cart.total} です。`, data: cart };
  },
  async apps_browse_shop(env, _a, action, channel) {
    const catalog = await svc.searchProducts(env.DB, { channel: channel, session_id: DEMO_SESSION_ID, action });
    const cart = await svc.getCart(env.DB, DEMO_SESSION_ID);
    return {
      text: `stapy商店: ${catalog.count}件の商品があります。対話UIを表示するか search_products で検索してください。`,
      data: { products: catalog.products, cart },
    };
  },
  async preview_order(env, _a, action, channel) {
    const o = await svc.previewOrder(env.DB, DEMO_SESSION_ID, channel, action);
    const lines = [`注文内容の確認（未確定）: ${o.order_no}（${o.count}点 合計 ¥${o.total}）`,
      ...o.items.map((i: any) => `- ${i.name} ×${i.qty} = ¥${i.subtotal}`),
      "この内容でよければ confirm_order を実行してください（デモ。実際の決済・発送は行われません）"];
    return { text: lines.join("\n"), data: o };
  },
  async confirm_order(env, _a, action, channel) {
    const o = await svc.confirmOrder(env.DB, DEMO_SESSION_ID, channel, action);
    const lines = [`デモ注文を確定しました: ${o.order_no}（${o.count}点 合計 ¥${o.total}）`,
      ...o.items.map((i: any) => `- ${i.name} ×${i.qty} = ¥${i.subtotal}`),
      "※ 実際の決済・発送は行われません（デモ）"];
    return { text: lines.join("\n"), data: o };
  },
  async reset_demo(env, _a, action, channel) {
    await svc.resetDemo(env.DB, DEMO_SESSION_ID, channel, action);
    return { text: "デモをリセットしました。カートは空です。", data: { ok: true } };
  },
};

// apps_* ツール: 同名の通常実装を共有し、tools/list 側の _meta.ui だけが違う。
// 呼び出し時はツール名（apps_*）が action に入るためログも apps_* で残る。
// （apps_browse_shop は上で直接定義済み）
for (const base of [
  "search_products", "get_product", "get_cart", "add_to_cart", "update_cart",
  "remove_from_cart", "preview_order", "confirm_order", "reset_demo",
]) {
  MODEL_TOOLS[`apps_${base}`] = MODEL_TOOLS[base];
}

const UI_TOOLS: Record<string, (env: Env, args: any) => Promise<any>> = {
  ui_search_products: (env, a) => svc.searchProducts(env.DB, {
    q: a?.q ?? "", categories: a?.category ? [a.category] : null,
    max_price: a?.max_price ?? null, sort: a?.sort ?? "recommended",
    channel: "MCP_APPS", session_id: DEMO_SESSION_ID,
  }),
  ui_get_product: async (env, a) => {
    const p = svc.getProduct(a?.product_id);
    await svc.log(env.DB, "MCP_APPS", "get_product", p.name, DEMO_SESSION_ID);
    return { product: p };
  },
  ui_get_cart: (env) => svc.getCart(env.DB, DEMO_SESSION_ID, "MCP_APPS"),
  ui_add_to_cart: async (env, a) => ({
    added: { product_id: a?.product_id, qty: a?.qty ?? 1, variant: a?.variant ?? "" },
    cart: await svc.addToCart(env.DB, a?.product_id, a?.qty ?? 1, a?.variant ?? "", DEMO_SESSION_ID, "MCP_APPS"),
  }),
  ui_update_cart: (env, a) => svc.updateCart(env.DB, a?.item_key, a?.qty, DEMO_SESSION_ID, "MCP_APPS"),
  ui_remove_from_cart: (env, a) => svc.removeFromCart(env.DB, a?.item_key, DEMO_SESSION_ID, "MCP_APPS"),
  ui_preview_order: (env) => svc.previewOrder(env.DB, DEMO_SESSION_ID, "MCP_APPS"),
  ui_confirm_order: (env) => svc.confirmOrder(env.DB, DEMO_SESSION_ID, "MCP_APPS"),
};

// ---------------------------------------------------------------------------
// MCP Streamable HTTP
// ---------------------------------------------------------------------------

// TOOLS_LIST / INSTRUCTIONS_* は build.py が実サーバーから生成（mcp_server.py が正本）。
// エンドポイントで公開面を分離: /mcp はUI連携なし通常ツールのみ、
// /mcp-apps は _meta.ui 付きツール（apps_* + ui_*）のみ。
const PLAIN_TOOLS = { tools: TOOLS_LIST.tools.filter((t: any) => !t._meta?.ui) };
const APPS_TOOLS = { tools: TOOLS_LIST.tools.filter((t: any) => !!t._meta?.ui) };
const PLAIN_NAMES = new Set(PLAIN_TOOLS.tools.map((t: any) => t.name));
const APPS_NAMES = new Set(APPS_TOOLS.tools.map((t: any) => t.name));

const CAPABILITIES = {
  prompts: { listChanged: false },
  resources: { listChanged: false, subscribe: false },
  tools: { listChanged: false },
};

function rpcError(id: unknown, code: number, message: string) {
  return { jsonrpc: "2.0", id: id ?? null, error: { code, message } };
}

async function mcpSupportsUi(env: Env, sessionId: string | null): Promise<boolean> {
  if (!sessionId) return false;
  const row = await env.DB.prepare(
    "SELECT supports_ui FROM mcp_sessions WHERE session_id = ?"
  ).bind(sessionId).first<{ supports_ui: number }>();
  return !!row?.supports_ui;
}

// appsOnly: /mcp-apps 接続か。true なら UI連携ツールのみ公開、
// false（/mcp）ならUI連携なし通常ツールのみ公開し UI関連は一切返さない。
async function handleMcp(req: Request, env: Env, origin: string, appsOnly: boolean): Promise<Response> {
  if (req.method === "GET") {
    // サーバー→クライアントのlistenストリームは提供しない（仕様上optional）
    return new Response(": stapy-shop\n\n", {
      status: 200,
      headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache", ...CORS },
    });
  }
  if (req.method === "DELETE") return json({ ok: true });
  if (req.method !== "POST") return json({ error: "method not allowed" }, 405);

  let msg: any;
  try { msg = await req.json(); } catch { return mcpReply(req, rpcError(null, -32700, "Parse error"), 400); }
  const { id, method, params } = msg ?? {};
  const mcpSid = req.headers.get("Mcp-Session-Id");

  // デバッグ: 公開版でのクライアント挙動把握用（sid有無・Apps対応を記録）
  try {
    const uiCheck = method === "initialize"
      ? `ui-declared=${JSON.stringify(params?.capabilities?.extensions?.[UI_EXT] ?? null)}`
      : `ui=${mcpSid ? await mcpSupportsUi(env, mcpSid) : "no-sid"}`;
    await svc.log(env.DB, "MCP_DEBUG", method ?? "unknown",
      `sid=${mcpSid ? "yes" : "no"} ${uiCheck} tool=${params?.name ?? ""}`.slice(0, 500));
  } catch { /* ログ失敗は本処理を止めない */ }

  // notification（idなし）→ 202
  if (id === undefined && typeof method === "string" && method.startsWith("notifications/"))
    return new Response(null, { status: 202, headers: CORS });

  switch (method) {
    case "initialize": {
      const caps = params?.capabilities ?? {};
      const uiSettings = caps?.extensions?.[UI_EXT];
      const supportsUi = Array.isArray(uiSettings?.mimeTypes) && uiSettings.mimeTypes.includes(APP_MIME);
      const sessionId = crypto.randomUUID().replaceAll("-", "");
      await env.DB.prepare(
        "INSERT OR REPLACE INTO mcp_sessions (session_id, supports_ui) VALUES (?, ?)"
      ).bind(sessionId, supportsUi ? 1 : 0).run();
      return mcpReply(req, {
        jsonrpc: "2.0", id,
        result: {
          capabilities: CAPABILITIES,
          instructions: appsOnly ? INSTRUCTIONS_APPS : INSTRUCTIONS_PLAIN,
          protocolVersion: params?.protocolVersion ?? "2025-03-26",
          serverInfo: { name: "stapy-shop", version: appsOnly ? "0.3.0-apps" : "0.3.0-plain" },
        },
      }, 200, { "Mcp-Session-Id": sessionId });
    }
    case "ping":
      return mcpReply(req, { jsonrpc: "2.0", id, result: {} });
    case "tools/list":
      return mcpReply(req, { jsonrpc: "2.0", id, result: appsOnly ? APPS_TOOLS : PLAIN_TOOLS });
    case "prompts/list":
      return mcpReply(req, { jsonrpc: "2.0", id, result: { prompts: [] } });
    case "resources/list":
      // /mcp 側はUIリソースを一切公開しない
      return mcpReply(req, { jsonrpc: "2.0", id, result: appsOnly ? RESOURCES_LIST : { resources: [] } });
    case "resources/templates/list":
      return mcpReply(req, { jsonrpc: "2.0", id, result: { resourceTemplates: [] } });
    case "resources/read": {
      const uri = params?.uri;
      if (!appsOnly || uri !== SHOP_UI_URI)
        return mcpReply(req, rpcError(id, -32002, `Resource not found: ${uri}`));
      const html = SHOP_HTML.replaceAll("__STAPY_ORIGIN__", origin);
      return mcpReply(req, {
        jsonrpc: "2.0", id,
        result: {
          contents: [{
            uri, mimeType: APP_MIME, text: html,
            _meta: { ui: { csp: { resourceDomains: [origin] }, prefersBorder: true } },
          }],
        },
      });
    }
    case "tools/call": {
      const name = params?.name;
      const args = params?.arguments ?? {};
      // エンドポイントで公開されていないツールは呼び出しも不可（接続単位の分離を保証）
      const allowed = appsOnly ? APPS_NAMES : PLAIN_NAMES;
      if (!allowed.has(name))
        return mcpReply(req, rpcError(id, -32602, `Unknown tool: ${name}`));
      try {
        if (MODEL_TOOLS[name]) {
          const { text, data } = await MODEL_TOOLS[name](env, args, name, appsOnly ? "MCP_APPS" : "MCP");
          return mcpReply(req, {
            jsonrpc: "2.0", id,
            result: { content: [{ type: "text", text }], structuredContent: data ?? { message: text }, isError: false },
          });
        }
        if (UI_TOOLS[name]) {
          // _require_apps 相当: sid があればネゴシエーション結果を検証。
          // sid 無しはステートレスコネクタ（OpenAI系等）とみなし ui_* 呼出し自体を
          // Apps経路の証左として許可する（検証不可である旨はログに残す）。
          const supportsUi = mcpSid ? await mcpSupportsUi(env, mcpSid) : true;
          if (!supportsUi) {
            return mcpReply(req, {
              jsonrpc: "2.0", id,
              result: {
                content: [{ type: "text", text: `Error executing tool ${name}: [forbidden] このツールは MCP Apps 対応クライアントのUIからのみ呼び出せます` }],
                isError: true,
              },
            });
          }
          const data = await UI_TOOLS[name](env, args);
          return mcpReply(req, {
            jsonrpc: "2.0", id,
            result: { content: [{ type: "text", text: JSON.stringify(data) }], structuredContent: data, isError: false },
          });
        }
        return mcpReply(req, rpcError(id, -32602, `Unknown tool: ${name}`));
      } catch (e) {
        if (e instanceof ShopError) {
          return mcpReply(req, {
            jsonrpc: "2.0", id,
            result: {
              content: [{ type: "text", text: `Error executing tool ${name}: [${e.code}] ${e.message}` }],
              isError: true,
            },
          });
        }
        throw e;
      }
    }
    default:
      return mcpReply(req, rpcError(id, -32601, `Method not found: ${method}`));
  }
}

// ---------------------------------------------------------------------------
// REST API（api.py と同等）
// ---------------------------------------------------------------------------

async function handleApi(req: Request, env: Env, path: string): Promise<Response | null> {
  const url = new URL(req.url);
  const sp = url.searchParams;
  const method = req.method;
  const session = sessionOf(req);
  const channel = channelOf(req);
  const db = env.DB;

  const intOrNull = (v: string | null) => (v === null ? null : Number(v));

  try {
    if (method === "GET" && path === "/api/products")
      return json(await svc.searchProducts(db, {
        q: sp.get("q") ?? "",
        categories: sp.get("category") ? [sp.get("category")!] : null,
        max_price: intOrNull(sp.get("max_price")),
        in_stock_only: sp.get("in_stock") === "true",
        featured_only: sp.get("featured") === "true",
        sort: (sp.get("sort") as any) ?? "recommended",
      }));

    if (method === "GET" && path === "/api/categories")
      return json({ categories: svc.listCategories() });

    if (method === "GET" && path.startsWith("/api/products/"))
      return json(svc.getProduct(decodeURIComponent(path.slice("/api/products/".length))));

    if (method === "GET" && path === "/api/cart")
      return json(await svc.getCart(db, session));

    if (method === "POST" && path === "/api/cart/items") {
      const b = (await req.json().catch(() => ({}))) as any;
      return json(await svc.addToCart(db, b.product_id, b.qty ?? 1, b.variant ?? "", session, channel));
    }

    const itemMatch = path.match(/^\/api\/cart\/items\/(.+)$/);
    if (itemMatch) {
      const key = decodeURIComponent(itemMatch[1]);
      if (method === "PATCH") {
        const b = (await req.json().catch(() => ({}))) as any;
        return json(await svc.updateCart(db, key, b.qty, session, channel));
      }
      if (method === "DELETE")
        return json(await svc.removeFromCart(db, key, session, channel));
    }

    if (method === "POST" && path === "/api/demo/reset")
      return json(await svc.resetDemo(db, session, channel));

    if (method === "GET" && path === "/api/demo/logs")
      return json({ logs: await svc.operationLogs(db, Math.min(Number(sp.get("limit") ?? 100), 500)) });

    if (method === "POST" && path === "/api/orders/preview")
      return json(await svc.previewOrder(db, session, channel));

    if (method === "POST" && path === "/api/orders/confirm")
      return json(await svc.confirmOrder(db, session, channel));

    if (method === "GET" && path.startsWith("/api/orders/"))
      return json(await svc.getOrder(db, decodeURIComponent(path.slice("/api/orders/".length))));

    return null;
  } catch (e) {
    return shopErr(e);
  }
}

// ---------------------------------------------------------------------------
// エントリポイント
// ---------------------------------------------------------------------------

const LEGACY_PAGES: Record<string, string> = {
  "/stapy_shop_一覧.html": "/index.html",
  "/stapy_shop_詳細.html": "/detail.html",
};

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);
    const origin = url.origin;

    if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: CORS });

    // MCP: /mcp = 通常接続（UIなし）、/mcp-apps = MCP Apps 接続。末尾 / も受理。
    const mcpPath = url.pathname.replace(/\/$/, "");
    if (mcpPath === "/mcp") return handleMcp(req, env, origin, false);
    if (mcpPath === "/mcp-apps") return handleMcp(req, env, origin, true);

    const apiRes = await handleApi(req, env, url.pathname);
    if (apiRes) return apiRes;

    // 静的ページ・旧ファイル名
    // HTML/JS は /static/* を参照するが、Assets は stapy_shop/static 直下を / に
    // マップするため /static/ プレフィックスを剥がしてから渡す
    let pathname = url.pathname;
    if (pathname.startsWith("/static/")) pathname = pathname.slice("/static".length);
    const legacy = LEGACY_PAGES[pathname] ?? LEGACY_PAGES[url.pathname];
    const target = legacy ?? pathname;
    const assetReq =
      target !== url.pathname ? new Request(new URL(target, url.origin).toString(), req) : req;
    return env.ASSETS.fetch(assetReq);
  },
};
