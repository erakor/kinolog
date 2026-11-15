"""Run the stdio MCP server: python3 -m kinolog.interfaces.mcp (needs the ``mcp`` extra)."""

import asyncio

from mcp.server.stdio import stdio_server

from kinolog.interfaces.mcp.server import create_mcp_app


async def main():
    server = create_mcp_app()
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
