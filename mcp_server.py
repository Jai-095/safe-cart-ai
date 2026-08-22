"""
mcp_server.py — Exposes the shared catalog + gated purchase flow as MCP
tools, so a real AI agent (Claude Desktop, etc.) can act on your behalf
directly — going through the exact same Safe-Cart-AI policy as the website.

Purchases made here aren't tied to a specific logged-in website account
(there's no login concept over MCP), so they show up in the Admin
Overview's global activity, not in any one user's personal dashboard.

Run with: python mcp_server.py
"""

import json
import uuid

from fastmcp import FastMCP
import products_db
import policy
import purchase_flow

mcp = FastMCP("safe-cart-ai")

# One session id per server run, for simplicity in the demo.
SESSION_ID = str(uuid.uuid4())[:8]
AGENT_USER_ID = None  # not tied to a specific website account


@mcp.tool()
def browse_products() -> str:
    """Browse the full catalog of items you're allowed to buy. Returns
    id, name, price, stock and description for every item currently listed."""
    return json.dumps(products_db.get_all_products(), indent=2)


@mcp.tool()
def get_product_details(product_id: str) -> str:
    """Get full details for a single item by its id (e.g. 'p001')."""
    product = products_db.get_product(product_id)
    if not product:
        return json.dumps({"error": f"No item with id '{product_id}'"})
    return json.dumps(product, indent=2)


@mcp.tool()
def request_purchase(product_id: str, quantity: int, reason: str) -> str:
    """
    Request to purchase an item on behalf of the user. You MUST provide a
    clear 'reason' explaining why this purchase matches what the user
    asked for — vague or missing reasons will be rejected.

    This is NOT guaranteed to succeed immediately: under ₹2000 it's
    auto-approved, ₹2000-5000 needs the user's approval, above ₹5000 it's
    blocked by default and needs an explicit override. Always report the
    actual decision back to the user, don't assume success.
    """
    result = purchase_flow.process_purchase(AGENT_USER_ID, SESSION_ID, product_id, quantity, reason)
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
def get_audit_trail() -> str:
    """Return the full log of every purchase attempt in this session:
    what was requested, why, and what was decided."""
    logs = policy.get_audit_log(user_id=AGENT_USER_ID)
    logs = [l for l in logs if l["session_id"] == SESSION_ID]
    return json.dumps(logs, indent=2, default=str)


if __name__ == "__main__":
    products_db.init_db()
    policy.init_db()
    mcp.run()
