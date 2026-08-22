"""
alerts.py — "The AI watching the AI."

After every purchase decision, this checks for overspending PATTERNS —
not just single transactions — and raises alerts the user sees on their
dashboard. This is what makes Safe-Cart-AI a watcher, not just a gate.
"""

import sqlite3
import time
from pathlib import Path

DB_PATH = Path(__file__).parent / "logs" / "audit.db"  # shares the audit_log db

# Pattern-detection thresholds — tune these for your demo
RAPID_FIRE_WINDOW_SECONDS = 15 * 60      # 15 minutes
RAPID_FIRE_COUNT_THRESHOLD = 3           # 3+ attempts in that window raises an alert
DAILY_SPEND_ALERT_THRESHOLD = 10000      # cumulative approved spend in 24h


def init_db():
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            timestamp REAL,
            severity TEXT,
            message TEXT,
            related_log_id INTEGER,
            is_read INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()


def _create_alert(user_id, severity, message, related_log_id=None):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO alerts (user_id, timestamp, severity, message, related_log_id) VALUES (?,?,?,?,?)",
        (user_id, time.time(), severity, message, related_log_id)
    )
    conn.commit()
    conn.close()


def evaluate_patterns(user_id, log_id, decision, total_price, product_name=None, is_gift=False):
    """Call this right after a purchase decision is logged. Looks both at
    THIS decision and at recent PATTERNS across this user's activity.

    product_name: pass the item's name where available, so alerts read like
    "spend ₹X on Y" instead of a bare number — it's easier to act on.
    is_gift: for duplicate_flagged only — True when the stated reason looks
    like it's for someone else, so the alert reads as a review, not a scold.
    """
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    item = product_name or "an item"

    if decision == "pending_user_approval":
        _create_alert(user_id, "info",
                       f"Your AI agent wants to spend ₹{total_price:.0f} on {item} — it needs "
                       f"your OK before that leaves your account.",
                       log_id)
    elif decision == "high_value_review":
        _create_alert(user_id, "warning",
                       f"Blocked to protect your money: your AI agent tried to spend "
                       f"₹{total_price:.0f} on {item}. Read its stated reason before deciding "
                       f"whether to override.",
                       log_id)
    elif decision == "duplicate_flagged":
        if is_gift:
            _create_alert(user_id, "info",
                           f"Your AI agent is buying {item} again (₹{total_price:.0f}) — the "
                           f"reason it gave suggests this one's for someone else, not a repeat "
                           f"mistake. Review it and confirm if that's right.",
                           log_id)
        else:
            _create_alert(user_id, "warning",
                           f"Your AI agent tried to reorder {item}, which you already bought "
                           f"recently (₹{total_price:.0f}). Blocked in case it's an accidental "
                           f"repeat.",
                           log_id)
    elif decision == "rejected":
        _create_alert(user_id, "info",
                       "Your AI agent's purchase attempt was rejected automatically.",
                       log_id)

    if user_id is not None:
        cutoff = time.time() - RAPID_FIRE_WINDOW_SECONDS
        recent_count = conn.execute(
            "SELECT COUNT(*) FROM audit_log "
            "WHERE user_id = ? AND timestamp >= ?"
            "AND decision IN ('approved','pending_user_approval'," "'high_value_review', 'duplicate_flagged')",
            (user_id, cutoff)
        ).fetchone()[0]
        if recent_count >= RAPID_FIRE_COUNT_THRESHOLD:
            _create_alert(
                user_id, "warning",
                f"Unusual activity: your AI agent has made {recent_count} purchase attempts "
                f"in the last 15 minutes. Worth checking what it's doing before it spends more "
                f"of your money.",
                log_id
            )

        day_cutoff = time.time() - 24 * 60 * 60
        daily_spend = conn.execute(
            "SELECT COALESCE(SUM(price * quantity), 0) FROM audit_log "
            "WHERE user_id = ? AND decision = 'approved' AND timestamp >= ?",
            (user_id, day_cutoff)
        ).fetchone()[0]
        if daily_spend >= DAILY_SPEND_ALERT_THRESHOLD:
            _create_alert(
                user_id, "warning",
                f"You've spent ₹{daily_spend:.0f} of your hard-earned money through your AI "
                f"agent in the last 24 hours — worth checking it isn't overspending on your "
                f"behalf.",
                log_id
            )

    conn.close()


def get_alerts_for_user(user_id, unread_only=False):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    if unread_only:
        rows = conn.execute(
            "SELECT * FROM alerts WHERE user_id = ? AND is_read = 0 ORDER BY id DESC", (user_id,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM alerts WHERE user_id = ? ORDER BY id DESC", (user_id,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_read(alert_id):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE alerts SET is_read = 1 WHERE id = ?", (alert_id,))
    conn.commit()
    conn.close()


def get_all_alerts():
    """Admin view — alerts across every user."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM alerts ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]
