"""
test_agent.py — Simulates an AI agent talking to mcp_server.py directly,
using the fastmcp Client. This bypasses Claude Desktop and MCP Inspector
entirely, so it's a reliable way to test (and demo) the whole flow.

Run with: python test_agent.py
(Make sure mcp_server.py itself is NOT already running separately —
this script launches it as a subprocess automatically.)
"""

import asyncio
import json
from fastmcp import Client

SERVER_SCRIPT = "mcp_server.py"


def show(label: str, result):
    """Print a tool result readably, however the Client happens to shape it."""
    print(f"\n--- {label} ---")
    text = None
    # fastmcp Client results commonly expose .content as a list of blocks
    # with a .text attribute. Fall back to raw printing if the shape differs.
    try:
        content = getattr(result, "content", None)
        if content and hasattr(content[0], "text"):
            text = content[0].text
    except Exception:
        pass

    if text is not None:
        try:
            parsed = json.loads(text)
            print(json.dumps(parsed, indent=2))
        except json.JSONDecodeError:
            print(text)
    else:
        print(result)


async def main():
    async with Client(SERVER_SCRIPT) as client:
        tools = await client.list_tools()
        print("Connected. Available tools:", [t.name for t in tools])

        result = await client.call_tool("browse_products", {})
        show("Browse catalog", result)

        result = await client.call_tool("request_purchase", {
            "product_id": "p001",
            "quantity": 1,
            "reason": "User asked for wireless earbuds under 2000 rupees.",
        })
        show("Purchase attempt: cheap item (expect approved)", result)

        result = await client.call_tool("request_purchase", {
            "product_id": "p003",
            "quantity": 1,
            "reason": "User asked for a compact mechanical keyboard for their desk setup.",
        })
        show("Purchase attempt: mid-price item (expect pending_human_approval)", result)

        result = await client.call_tool("request_purchase", {
            "product_id": "p005",
            "quantity": 1,
            "reason": "User wants a webcam for streaming.",
        })
        show("Purchase attempt: out-of-stock item (expect rejected, graceful)", result)

        result = await client.call_tool("get_audit_trail", {})
        show("Full audit trail", result)


if __name__ == "__main__":
    asyncio.run(main())
