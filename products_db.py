"""
products_db.py — SQLite-backed product catalog with full CRUD.

Both the website (app.py) and the MCP server (mcp_server.py) read from
this same source. Anything you add on the website is instantly visible
to a connected AI agent too — same catalog, two front doors.
"""

import sqlite3
import json
from pathlib import Path

DB_PATH = Path(__file__).parent / "logs" / "products.db"
SEED_JSON = Path(__file__).parent / "data" / "products.json"


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = _connect()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS products (
            seq INTEGER PRIMARY KEY AUTOINCREMENT,
            id TEXT UNIQUE,
            name TEXT NOT NULL,
            price REAL NOT NULL,
            currency TEXT DEFAULT 'INR',
            stock INTEGER NOT NULL DEFAULT 0,
            category TEXT DEFAULT 'general',
            description TEXT DEFAULT ''
        )
    """)
    conn.commit()

    # Seed from the original products.json only the first time the table
    # is empty, so your already-tested demo products (p001, p003, p005...)
    # keep working exactly as before.
    count = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    if count == 0 and SEED_JSON.exists():
        with open(SEED_JSON) as f:
            seed = json.load(f)
        for p in seed:
            conn.execute(
                "INSERT INTO products (id, name, price, currency, stock, category, description) "
                "VALUES (?,?,?,?,?,?,?)",
                (p["id"], p["name"], p["price"], p.get("currency", "INR"),
                 p["stock"], p.get("category", "general"), p.get("description", ""))
            )
        conn.commit()
    conn.close()


def get_all_products():
    init_db()
    conn = _connect()
    rows = conn.execute("SELECT * FROM products ORDER BY seq").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_product(product_id):
    init_db()
    conn = _connect()
    row = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def add_product(name, price, stock, category="general", description=""):
    """Adds a product and auto-generates its id (p009, p010, ...)."""
    init_db()
    conn = _connect()
    cur = conn.execute(
        "INSERT INTO products (name, price, currency, stock, category, description) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (name, price, "INR", stock, category, description)
    )
    new_seq = cur.lastrowid
    new_id = f"p{new_seq:03d}"
    conn.execute("UPDATE products SET id = ? WHERE seq = ?", (new_id, new_seq))
    conn.commit()
    conn.close()
    return new_id


def update_product(product_id, name=None, price=None, stock=None, category=None, description=None):
    init_db()
    conn = _connect()
    existing = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    if not existing:
        conn.close()
        return False
    conn.execute(
        "UPDATE products SET name=?, price=?, stock=?, category=?, description=? WHERE id=?",
        (
            name if name is not None else existing["name"],
            price if price is not None else existing["price"],
            stock if stock is not None else existing["stock"],
            category if category is not None else existing["category"],
            description if description is not None else existing["description"],
            product_id,
        )
    )
    conn.commit()
    conn.close()
    return True


def delete_product(product_id):
    init_db()
    conn = _connect()
    conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
    conn.commit()
    conn.close()
