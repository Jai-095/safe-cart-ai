"""
razorpay_client.py — Wraps Razorpay's test-mode Orders API.

Only ever called AFTER policy.evaluate_purchase() returns "approved".
This keeps money-movement code completely separate from decision code,
so the audit trail always shows WHY before WHAT.
"""

import os
import razorpay
from dotenv import load_dotenv

load_dotenv()

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")

_client = None


def get_client():
    global _client
    if _client is None:
        if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
            raise RuntimeError(
                "Razorpay test keys not found. Set RAZORPAY_KEY_ID and "
                "RAZORPAY_KEY_SECRET in your .env file (Test Mode keys from "
                "the Razorpay dashboard)."
            )
        _client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
    return _client


def create_test_order(amount_inr: float, receipt_id: str, notes: dict | None = None):
    """
    Creates a Razorpay order in test mode. Amount must be in paise (x100).
    Returns the order dict, including order['id'] used to build a checkout link.
    """
    client = get_client()
    amount_paise = int(round(amount_inr * 100))
    order = client.order.create({
        "amount": amount_paise,
        "currency": "INR",
        "receipt": receipt_id,
        "notes": notes or {},
    })
    return order
