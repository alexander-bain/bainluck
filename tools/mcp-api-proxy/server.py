#!/usr/bin/env python3
"""
MCP server that proxies requests to the OddsTracker production API.

Runs locally on your machine so it has full network access.
Claude Code calls this server's tools to query the production API.

Usage:
    pip install mcp httpx
    python server.py
"""

import json
import sys

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

API_BASE = "https://what-are-the-odds-0283511a7d93.herokuapp.com"

server = Server("odds-tracker-api")


@server.list_tools()
async def list_tools():
    return [
        Tool(
            name="odds_api",
            description=(
                "Make a request to the OddsTracker production API. "
                "Common paths: "
                "/api/events (list events, ?sport=americanfootball_nfl&status=live), "
                "/api/events/search?q=super+bowl (search), "
                "/api/events/{id} (event detail), "
                "/api/events/{id}/history?hours=48 (odds history), "
                "/api/events/{id}/props (player props), "
                "/api/events/{id}/debug (debug info), "
                "/api/events/highlights (highlighted events), "
                "/api/events/pulse-rankings (top Pulse games), "
                "/api/futures (futures markets), "
                "/api/futures/{id} (futures detail), "
                "/api/sports (list sports), "
                "/api/admin/pulse/status (Pulse calculation status), "
                "/api/admin/pulse/distributions (score distributions), "
                "/api/admin/espn/teams-status (ESPN team sync status), "
                "/api/admin/futures/categorization-status (categorization status). "
                "Returns JSON response body."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "API path starting with / (e.g., '/api/events/search?q=chiefs')",
                    },
                    "method": {
                        "type": "string",
                        "description": "HTTP method (default: GET)",
                        "enum": ["GET", "POST"],
                        "default": "GET",
                    },
                },
                "required": ["path"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    if name != "odds_api":
        return [TextContent(type="text", text=f"Unknown tool: {name}")]

    path = arguments.get("path", "")
    method = arguments.get("method", "GET").upper()

    if not path.startswith("/"):
        path = "/" + path

    url = f"{API_BASE}{path}"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            if method == "POST":
                response = await client.post(url)
            else:
                response = await client.get(url)

            # Try to pretty-print JSON, fall back to raw text
            try:
                data = response.json()
                body = json.dumps(data, indent=2, default=str)
            except Exception:
                body = response.text

            result = f"HTTP {response.status_code}\n{body}"

            # Truncate very large responses to avoid overwhelming context
            if len(result) > 50000:
                result = result[:50000] + f"\n\n... (truncated, {len(body)} total chars)"

            return [TextContent(type="text", text=result)]

    except httpx.TimeoutException:
        return [TextContent(type="text", text=f"Request timed out: {url}")]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {type(e).__name__}: {e}")]


async def main():
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
