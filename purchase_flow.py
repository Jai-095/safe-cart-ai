"""
purchase_flow.py — Shared orchestration: evaluate a purchase through
policy.py, then create the real Razorpay test order if it goes through.

Used by both app.py (the website) and mcp_server.py (a connected AI
agent), so both paths behave identically and share one audit trail.
"""

import policy
import razorpay_client


def process_purchase(user_id, session_id, product_id, quantity, reason):
    """Runs a purchase request through the full pipeline: policy check,
    then real Razorpay test order creation if approved."""
    result = policy.evaluate_purchase(user_id, session_id, product_id, quantity, reason)

    if result["decision"] == "approved":
        try:
            order = razorpay_client.create_test_order(
                amount_inr=result["total_price"],
                receipt_id=f"{session_id}-{product_id}",
                notes={"reason": reason, "session_id": session_id},
            )
            result["razorpay_order_id"] = order["id"]
            result["razorpay_amount_paise"] = order["amount"]
            if result.get("log_id"):
                policy.attach_razorpay_order(result["log_id"], order["id"])
        except Exception as e:
            result["decision"] = "payment_error"
            result["reason"] = f"Approved by policy but payment creation failed: {e}"
            # Reflect the failure in the audit log itself, not just the
            # in-memory result — otherwise this purchase (which never
            # actually happened) still counts as 'approved' for future
            # duplicate-checking and daily-spend totals.
            if result.get("log_id"):
                policy.mark_payment_failed(result["log_id"], str(e))

    return result


def _create_order_for_log(log_row):
    """Shared helper: create the actual Razorpay order for a log row that
    was just approved (either via user approval or a high-value override)."""
    try:
        order = razorpay_client.create_test_order(
            amount_inr=log_row["price"] * log_row["quantity"],
            receipt_id=f"{log_row['session_id']}-{log_row['product_id']}-approved",
            notes={"reason": log_row["reason"], "session_id": log_row["session_id"]},
        )
        policy.attach_razorpay_order(log_row["id"], order["id"])
        return order["id"]
    except Exception as e:
        policy.append_note(log_row["id"], f"[payment creation failed: {e}]")
        return None


def approve_pending_purchase(log_id):
    """User approves a pending_user_approval row from their dashboard."""
    log_row = policy.get_log_by_id(log_id)
    if not log_row:
        return None
    policy.approve_pending(log_id)
    return _create_order_for_log(log_row)


def override_high_value_purchase(log_id):
    """User explicitly overrides a blocked high-value purchase after
    reviewing the AI's stated reason. Distinct from a normal approval —
    this is a deliberate, harder-to-reach action."""
    log_row = policy.get_log_by_id(log_id)
    if not log_row:
        return None
    policy.override_high_value(log_id)
    return _create_order_for_log(log_row)


def confirm_duplicate_purchase(log_id):
    """User explicitly confirms a purchase flagged as a likely accidental
    duplicate — they really do want to reorder it."""
    log_row = policy.get_log_by_id(log_id)
    if not log_row:
        return None
    policy.confirm_duplicate(log_id)
    return _create_order_for_log(log_row)
