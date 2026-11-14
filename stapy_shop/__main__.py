"""stapy商店デモの起動エントリ。

    python -m stapy_shop           → Web + REST + MCP(Streamable HTTP /mcp)
    python -m stapy_shop --stdio   → MCP stdio モード（ローカル検証用）

stdio モードでは HTTP サーバーを立てず、標準入出力で MCP を話す。
Claude Code / MCP Inspector などの stdio 接続に対応する。
"""

import sys


def main() -> None:
    if "--stdio" in sys.argv[1:]:
        import anyio

        from .api import mcp_server  # サービス・商品マスター共有のため同じサーバー

        anyio.run(mcp_server.run_stdio_async)
        return

    from .api import main as http_main

    http_main()


if __name__ == "__main__":
    main()
