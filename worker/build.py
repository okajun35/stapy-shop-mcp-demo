#!/usr/bin/env python3
"""Worker 用コード生成。

Python 側を正本のまま保つため、以下を自動生成する:
  src/generated/products.ts  <- stapy_shop/products.py の商品マスター
  src/generated/tools.ts     <- MCP tools/list + resources/list の実レスポンス（stdio で取得）
  src/generated/uiHtml.ts    <- shop_app.html + ext_apps.js 組み立て済みHTML

使い方: リポジトリルートから `python3 worker/build.py`（.venv の mcp が必要）
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "worker" / "src" / "generated"
PY = ROOT / ".venv" / "bin" / "python"

# mcp SDK は .venv にある。システム python で起動されたら .venv に付け替える
if PY.exists() and Path(sys.executable) != PY:
    import importlib.util
    if importlib.util.find_spec("mcp") is None:
        os_exec = getattr(__import__("os"), "execv")
        os_exec(str(PY), [str(PY), str(Path(__file__).resolve())])

sys.path.insert(0, str(ROOT))


def ts_const(name: str, data, comment: str = "") -> str:
    body = json.dumps(data, ensure_ascii=False, indent=1)
    return (f"// 自動生成: {comment}（手編集しない。worker/build.py で再生成）\n"
            f"export const {name} = {body} as const;\n")


def gen_products() -> None:
    from stapy_shop.products import CATEGORIES, PRODUCTS
    (OUT / "products.ts").write_text(
        "// 自動生成: stapy_shop/products.py の正本を転記\n"
        "export const PRODUCTS = "
        + json.dumps(PRODUCTS, ensure_ascii=False, indent=1)
        + " as const;\n"
        "export const CATEGORIES = "
        + json.dumps(CATEGORIES, ensure_ascii=False, indent=1)
        + " as const;\n",
        encoding="utf-8",
    )
    print(f"products.ts: {len(PRODUCTS)} products / {len(CATEGORIES)} categories")


def _stdio_rpc(proc: subprocess.Popen, msgs: list[dict]) -> list[dict]:
    proc.stdin.write("".join(json.dumps(m) + "\n" for m in msgs))
    proc.stdin.flush()
    out = []
    # 応答があるのは id 付きリクエストのみ（notification は読まない）
    for m in msgs:
        if "id" not in m:
            continue
        line = proc.stdout.readline()
        if not line:
            break
        out.append(json.loads(line))
    return out


def gen_tools() -> None:
    """stdio MCP に initialize→tools/list→resources/list を送り、結果をそのまま保存。"""
    proc = subprocess.Popen(
        [str(PY), "-m", "stapy_shop", "--stdio"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, cwd=ROOT,
    )
    try:
        init = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-11-25",
            "capabilities": {"extensions": {"io.modelcontextprotocol/ui": {
                "mimeTypes": ["text/html;profile=mcp-app"]}}},
            "clientInfo": {"name": "build", "version": "0"}}}
        init_res = _stdio_rpc(proc, [init, {"jsonrpc": "2.0", "method": "notifications/initialized"}])
        res = _stdio_rpc(proc, [
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            {"jsonrpc": "2.0", "id": 3, "method": "resources/list", "params": {}},
        ])
        tools = res[0]["result"]
        resources = res[1]["result"]
        instructions = init_res[0]["result"].get("instructions", "")
        # エンドポイント別 instructions（/mcp は plain、/mcp-apps は apps）
        from stapy_shop.mcp_server import _instructions
        (OUT / "tools.ts").write_text(
            "// 自動生成: MCP initialize + tools/list + resources/list の実レスポンス\n"
            "export const TOOLS_LIST = " + json.dumps(tools, ensure_ascii=False, indent=1) + ";\n"
            "export const RESOURCES_LIST = " + json.dumps(resources, ensure_ascii=False, indent=1) + ";\n"
            "export const INSTRUCTIONS = " + json.dumps(instructions, ensure_ascii=False) + ";\n"
            "export const INSTRUCTIONS_PLAIN = " + json.dumps(_instructions("plain"), ensure_ascii=False) + ";\n"
            "export const INSTRUCTIONS_APPS = " + json.dumps(_instructions("apps"), ensure_ascii=False) + ";\n",
            encoding="utf-8",
        )
        print(f"tools.ts: {len(tools['tools'])} tools / {len(resources['resources'])} resources")
    finally:
        proc.kill()


def gen_ui_html() -> None:
    from stapy_shop.mcp_server import _load_shop_html
    # __STAPY_ORIGIN__ はリクエスト時に実オリジンへ置換するセンチネル
    html = _load_shop_html("__STAPY_ORIGIN__")
    (OUT / "uiHtml.ts").write_text(
        "// 自動生成: mcp_app/shop_app.html + ext_apps.js（__STAPY_ORIGIN__ は実行時置換）\n"
        "export const SHOP_HTML = " + json.dumps(html, ensure_ascii=False) + ";\n",
        encoding="utf-8",
    )
    print(f"uiHtml.ts: {len(html)} bytes")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    gen_products()
    gen_tools()
    gen_ui_html()
    print("OK")
