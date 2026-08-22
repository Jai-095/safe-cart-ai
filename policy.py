"""
policy.py — Safe-Cart-AI's core guardrail.

Every purchase your AI agent tries to make on your behalf passes through
here BEFORE any money moves. This decides: auto-approve, ask you first,
or block outright — and hands off to alerts.py to watch for patterns.
"""

import sqlite3
import time
from pathlib import Path

import products_db
import alerts

DB_PATH = Path(__file__).parent / "logs" / "audit.db"

# ---- Your spending policy ----
AUTO_APPROVE_LIMIT = 2000       # <= this: auto-approved, no questions asked
USER_APPROVAL_LIMIT = 5000      # between AUTO_APPROVE_LIMIT and this: needs YOUR approval
                                  # above this: blocked by default, needs an explicit override
SESSION_SPEND_CAP = 20000        # absolute daily ceiling regardless of tier
MIN_REASON_LENGTH = 15

# ---- Duplicate cooldown, per category ----
# A short window makes sense for consumables, but reordering the exact same
# earbuds/keyboard/etc. a day later is almost always a mistake, not intent —
# these categories get a cooldown closer to a typical warranty period instead.
# Adjust these strings to match whatever `category` values your catalog uses.
DEFAULT_DUPLICATE_WINDOW_HOURS = 24
LONG_COOLDOWN_CATEGORIES = {"electronics", "audio", "accessories", "computer", "computers", "gadgets"}
LONG_COOLDOWN_HOURS = 24 * 365   # ~1 year, like a warranty period

# Reason text suggesting the purchase is for someone else, not a repeat for
# the user themself — still requires human confirmation, but the alert/prompt
# should read as a review, not an accusation of a mistake.
# This must be precise: "for my studies" or "for my desk" is NOT a gift signal,
# only "for my <person>" is. A loose "for my " keyword was matching both.
import re as _re
_GIFT_PATTERN = _re.compile(
    r"\bgift(?:ing)?\b|present for|surprise for|as a gift|"
    r"for (?:my|her|him|our|their|someone(?:'s)?)\s+"
    r"(brother|sister|mom|mother|dad|father|friend|wife|husband|son|daughter|"
    r"colleague|boyfriend|girlfriend|partner|cousin|uncle|aunt|nephew|niece|"
    r"grandma|grandpa|grandmother|grandfather|teacher|boss|kid|kids|parents)\b",
    _re.IGNORECASE,
)


def _cooldown_hours_for(product: dict) -> int:
    category = (product.get("category") or "").strip().lower()
    if category in LONG_COOLDOWN_CATEGORIES:
        return LONG_COOLDOWN_HOURS
    return DEFAULT_DUPLICATE_WINDOW_HOURS


def _looks_like_gift(reason: str) -> bool:
    return bool(_GIFT_PATTERN.search(reason or ""))


def init_db():
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL,
            user_id INTEGER,
            session_id TEXT,
            product_id TEXT,
            product_name TEXT,
            price REAL,
            quantity INTEGER,
            reason TEXT,
            decision TEXT,
            decision_note TEXT,
            razorpay_order_id TEXT,
            payment_status TEXT
        )
    """)
    # Migrate older audit.db files so nothing you already created breaks.
    existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(audit_log)").fetchall()}
    for col, coltype in [("razorpay_order_id", "TEXT"), ("payment_status", "TEXT"), ("user_id", "INTEGER")]:
        if col not in existing_cols:
            conn.execute(f"ALTER TABLE audit_log ADD COLUMN {col} {coltype}")
    conn.commit()
    conn.close()


def _session_spend_so_far(session_id):
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT COALESCE(SUM(price * quantity), 0) FROM audit_log "
        "WHERE session_id = ? AND decision = 'approved'",
        (session_id,)
    ).fetchone()
    conn.close()
    return row[0] or 0


def _recent_duplicate(user_id, product_id, cooldown_hours):
    """Has this exact item already been approved for this user within
    cooldown_hours? Catches an AI agent re-ordering the same thing without
    being asked. cooldown_hours varies by category — see _cooldown_hours_for."""
    conn = sqlite3.connect(DB_PATH)
    cutoff = time.time() - cooldown_hours * 3600
    row = conn.execute(
        "SELECT id, timestamp FROM audit_log WHERE user_id = ? AND product_id = ? "
        "AND decision = 'approved' AND timestamp >= ? ORDER BY id DESC LIMIT 1",
        (user_id, product_id, cutoff)
    ).fetchone()
    conn.close()
    return row


def _log_decision(user_id, session_id, product_id, product_name, price, quantity, reason, decision, note):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute(
        "INSERT INTO audit_log (timestamp, user_id, session_id, product_id, product_name, "
        "price, quantity, reason, decision, decision_note) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (time.time(), user_id, session_id, product_id, product_name, price, quantity, reason, decision, note)
    )
    conn.commit()
    log_id = cur.lastrowid
    conn.close()
    return log_id


def evaluate_purchase(user_id, session_id: str, product_id: str, quantity: int, reason: str):
    """
    The core gate. decision is one of:
    "approved", "pending_user_approval", "high_value_review", "rejected"
    """
    init_db()
    product = products_db.get_product(product_id)

    if not product:
        note = f"Item '{product_id}' does not exist in the catalog."
        log_id = _log_decision(user_id, session_id, product_id, "UNKNOWN", 0, quantity, reason, "rejected", note)
        alerts.evaluate_patterns(user_id, log_id, "rejected", 0)
        return {"decision": "rejected", "reason": note, "log_id": log_id}

    if product["stock"] < quantity:
        note = (f"Requested {quantity}x '{product['name']}' but only "
                f"{product['stock']} available. Cannot fulfill.")
        log_id = _log_decision(user_id, session_id, product_id, product["name"], product["price"],
                                quantity, reason, "rejected", note)
        alerts.evaluate_patterns(user_id, log_id, "rejected", 0)
        return {"decision": "rejected", "reason": note, "available_stock": product["stock"], "log_id": log_id}

    if not reason or len(reason.strip()) < MIN_REASON_LENGTH:
        note = "Reason missing or too short. Your AI agent must justify every purchase attempt."
        log_id = _log_decision(user_id, session_id, product_id, product["name"], product["price"],
                                quantity, reason, "rejected", note)
        alerts.evaluate_patterns(user_id, log_id, "rejected", 0)
        return {"decision": "rejected", "reason": note, "log_id": log_id}

    # --- Check: has this exact item already been bought recently? ---
    # Catches an AI agent re-ordering the same thing without actually being asked.
    # The cooldown window depends on category (see _cooldown_hours_for), and a
    # gift-sounding reason changes the wording but NOT the requirement to confirm.
    cooldown_hours = _cooldown_hours_for(product)
    dup = _recent_duplicate(user_id, product_id, cooldown_hours)
    if dup:
        is_gift = _looks_like_gift(reason)
        if cooldown_hours >= 24:
            window_label = f"{cooldown_hours // 24} day(s)" if cooldown_hours < 24 * 30 else f"~{cooldown_hours // (24*30)} month(s)"
        else:
            window_label = f"{cooldown_hours}h"
        if is_gift:
            note = (f"You bought '{product['name']}' within the last {window_label} (order #{dup[0]}), "
                    f"but the reason given suggests this one's for someone else — not a repeat for "
                    f"yourself. Confirm to go ahead, or reject if that's not right.")
        else:
            note = (f"You already have an approved order for '{product['name']}' within "
                    f"the last {window_label} (order #{dup[0]}). Blocking to avoid "
                    f"an accidental duplicate — confirm explicitly if you genuinely want it again.")
        log_id = _log_decision(user_id, session_id, product_id, product["name"], product["price"],
                                quantity, reason, "duplicate_flagged", note)
        alerts.evaluate_patterns(user_id, log_id, "duplicate_flagged", product["price"] * quantity,
                                  product_name=product["name"], is_gift=is_gift)
        return {"decision": "duplicate_flagged", "reason": note, "product": product,
                "total_price": product["price"] * quantity, "log_id": log_id,
                "is_probable_gift": is_gift, "quantity": quantity}

    total_price = product["price"] * quantity

    spent_so_far = _session_spend_so_far(session_id)
    if spent_so_far + total_price > SESSION_SPEND_CAP:
        note = (f"Your spend cap of ₹{SESSION_SPEND_CAP} would be exceeded "
                f"(already spent ₹{spent_so_far}, this purchase is ₹{total_price}).")
        log_id = _log_decision(user_id, session_id, product_id, product["name"], product["price"],
                                quantity, reason, "rejected", note)
        alerts.evaluate_patterns(user_id, log_id, "rejected", total_price)
        return {"decision": "rejected", "reason": note, "log_id": log_id}

    if total_price <= AUTO_APPROVE_LIMIT:
        note = f"Within your auto-approve limit (₹{AUTO_APPROVE_LIMIT}). Approved automatically."
        log_id = _log_decision(user_id, session_id, product_id, product["name"], product["price"],
                                quantity, reason, "approved", note)
        alerts.evaluate_patterns(user_id, log_id, "approved", total_price, product_name=product["name"])
        return {"decision": "approved", "reason": note, "product": product,
                "total_price": total_price, "log_id": log_id, "quantity": quantity}

    elif total_price <= USER_APPROVAL_LIMIT:
        note = (f"Above your auto-approve limit (₹{AUTO_APPROVE_LIMIT}), within the range "
                f"that needs your approval (up to ₹{USER_APPROVAL_LIMIT}).")
        log_id = _log_decision(user_id, session_id, product_id, product["name"], product["price"],
                                quantity, reason, "pending_user_approval", note)
        alerts.evaluate_patterns(user_id, log_id, "pending_user_approval", total_price, product_name=product["name"])
        return {"decision": "pending_user_approval", "reason": note, "product": product,
                "total_price": total_price, "log_id": log_id, "quantity": quantity}

    else:
        note = (f"₹{total_price} is above your ₹{USER_APPROVAL_LIMIT} high-value threshold. "
                f"Blocked by default — review the stated reason and explicitly override "
                f"only if it's genuinely justified.")
        log_id = _log_decision(user_id, session_id, product_id, product["name"], product["price"],
                                quantity, reason, "high_value_review", note)
        alerts.evaluate_patterns(user_id, log_id, "high_value_review", total_price, product_name=product["name"])
        return {"decision": "high_value_review", "reason": note, "product": product,
                "total_price": total_price, "log_id": log_id, "quantity": quantity}


def get_audit_log(user_id=None):
    """Pass a user_id to see only that user's activity. Omit it (admin use)
    to see everyone's."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    if user_id is not None:
        rows = conn.execute(
            "SELECT * FROM audit_log WHERE user_id = ? ORDER BY id DESC", (user_id,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM audit_log ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_log_by_id(log_id):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM audit_log WHERE id = ?", (log_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def attach_razorpay_order(log_id, order_id):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE audit_log SET razorpay_order_id = ? WHERE id = ?", (order_id, log_id))
    conn.commit()
    conn.close()


def mark_payment_failed(log_id: int, error_note: str):
    """Payment creation failed AFTER policy approved the purchase. The audit
    row must stop counting as 'approved' — otherwise a purchase that never
    actually happened still blocks a real future attempt as a 'duplicate',
    and still counts toward the daily-spend total. This is what fixes that."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "UPDATE audit_log SET decision = 'payment_error', "
        "decision_note = decision_note || ' [payment failed: ' || ? || ']' WHERE id = ?",
        (error_note, log_id)
    )
    conn.commit()
    conn.close()


def mark_paid(razorpay_order_id, payment_id):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "UPDATE audit_log SET payment_status = 'paid', "
        "decision_note = decision_note || ' [payment captured: ' || ? || ']' "
        "WHERE razorpay_order_id = ?",
        (payment_id, razorpay_order_id)
    )
    conn.commit()
    conn.close()


def append_note(log_id, extra_text):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "UPDATE audit_log SET decision_note = decision_note || ' ' || ? WHERE id = ?",
        (extra_text, log_id)
    )
    conn.commit()
    conn.close()


def approve_pending(log_id: int):
    """User approves a pending_user_approval purchase."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE audit_log SET decision = 'approved', "
                 "decision_note = decision_note || ' [approved by you]' WHERE id = ?", (log_id,))
    conn.commit()
    conn.close()


def override_high_value(log_id: int):
    """User explicitly overrides a blocked high-value purchase after
    reviewing the AI's stated reason."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE audit_log SET decision = 'approved', "
                 "decision_note = decision_note || ' [manually overridden by you after review]' WHERE id = ?",
                 (log_id,))
    conn.commit()
    conn.close()


def confirm_duplicate(log_id: int):
    """User explicitly confirms they DO want to reorder something flagged
    as a likely accidental duplicate."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE audit_log SET decision = 'approved', "
                 "decision_note = decision_note || ' [confirmed as intentional reorder by you]' WHERE id = ?",
                 (log_id,))
    conn.commit()
    conn.close()


def reject_pending(log_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE audit_log SET decision = 'rejected', "
                 "decision_note = decision_note || ' [rejected by you]' WHERE id = ?", (log_id,))
    conn.commit()
    conn.close()
