"""Safe-Cart-AI conversational bot.

The conversation layer guides the user through product selection, purchase
reason, budget, and explicit confirmation before handing the request to the
deterministic safety policy.
"""

import re

import products_db
import policy
import alerts
import purchase_flow

DEFAULT_USER_ID = 1
SESSION_ID = "cli-session"

HELP_TEXT = """
Commands:
  catalog   - see everything available to buy
  history   - see everything you've bought or attempted
  alerts    - see the full alert log
  help      - show this message
  quit      - exit

Otherwise, describe what you need, for example:
  "I need earbuds because mine broke"
  "order a mechanical keyboard for my desk, budget 3000"
  "buy earbuds again, it's a gift for my brother"

Safe-Cart-AI will:
  1. Identify the product
  2. Ask why you want to buy it
  3. Ask your budget if you haven't provided one
  4. Show you the purchase summary
  5. Require your explicit confirmation before purchasing
  6. Run the request through the safety policy
""".strip()

GREETING_PATTERN = re.compile(
    r"^(?:hi+|hello+|hey+|hii+|namaste|good\s+(?:morning|afternoon|evening))[\s!,.?]*$",
    re.IGNORECASE,
)

BUDGET_PATTERN = re.compile(
    r"(?:under|below|within|less than|budget(?:\s*of)?|around|upto|up to)"
    r"\s*(?:₹|rs\.?|inr)?\s*(\d{2,6})",
    re.IGNORECASE,
)

REASON_MARKERS = re.compile(
    r"\b(?:because|since|as|reason(?:\s+is)?|for\s+(?:my|the)\s+"
    r"(?:studies|study|desk|work|office|travel|trip|home|college|"
    r"school|gaming|streaming)|mine\s+(?:broke|broke down|stopped|"
    r"is broken|doesn't work|does not work)|my\s+(?:old|current|existing))\b",
    re.IGNORECASE,
)

POSITIVE_CONTINUE = {
    "go with that",
    "go with that anyway",
    "buy it anyway",
    "yes buy it",
    "that's fine",
    "thats fine",
    "that's okay",
    "thats okay",
    "okay",
    "ok",
    "proceed",
    "continue",
    "yes",
    "y",
}

BUY_WORDS = {"buy", "purchase", "order", "get", "need", "want"}


def is_greeting(text: str) -> bool:
    return bool(GREETING_PATTERN.fullmatch(text.strip()))


def find_candidates(text: str):
    """Simple transparent catalog matching; deliberately not an LLM call."""
    text_lower = text.lower()
    scored = []

    for p in products_db.get_all_products():
        score = 0

        if p["name"].lower() in text_lower:
            score += 10

        score += sum(
            1
            for w in p["name"].lower().split()
            if len(w) > 2 and w in text_lower
        )

        category = (p.get("category") or "").lower()
        if category and category in text_lower:
            score += 5

        if score > 0:
            scored.append((score, p))

    scored.sort(key=lambda sp: (-sp[0], sp[1]["price"]))
    return [p for _, p in scored]


def extract_quantity(text: str) -> int:
    # Only treat a number as quantity when it is explicitly followed
    # by x/items/units, so budget numbers are not mistaken for quantity.
    m = re.search(
        r"\b(\d+)\s*(?:x|items?|units?)\b",
        text,
        re.IGNORECASE,
    )
    return int(m.group(1)) if m else 1


def extract_budget(text: str):
    m = BUDGET_PATTERN.search(text)
    return float(m.group(1)) if m else None


def parse_plain_number(text: str):
    stripped = text.strip().replace("₹", "").replace(",", "")
    m = re.fullmatch(r"\d+(?:\.\d+)?", stripped)
    return float(stripped) if m else None


def extract_any_number(text: str):
    m = re.search(r"(\d{2,6})", text.replace(",", ""))
    return float(m.group(1)) if m else None


def extract_reason(text: str):
    """Find whether the initial request already contains a useful reason."""
    cleaned = text.strip()

    if REASON_MARKERS.search(cleaned) and len(cleaned) >= policy.MIN_REASON_LENGTH:
        return cleaned

    lowered = cleaned.lower()
    has_purchase_context = any(
        word in lowered.split()
        for word in BUY_WORDS
    )

    if has_purchase_context and len(cleaned) >= policy.MIN_REASON_LENGTH:
        return cleaned

    return None


def reason_is_sufficient(reason):
    return bool(
        reason and len(reason.strip()) >= policy.MIN_REASON_LENGTH
    )


def explain_reason_needed(product_name):
    print()
    print(
        f"Bot: 📝 Before I can purchase {product_name} for you, "
        "I need to know why you want it."
    )
    print(
        "     This reason is part of Safe-Cart-AI's safety check."
    )
    print("     For example:")
    print('       • "My current earbuds broke."')
    print('       • "I need them for my online classes."')
    print("     Why do you want to buy this product?")


def explain_budget_needed(product_name):
    print()
    print(
        f"Bot: 💰 Now I need your budget for {product_name}."
    )
    print("     How much are you willing to spend?")
    print(
        '     Example: "1500" or "my budget is ₹1500".'
    )


def show_purchase_summary(awaiting):
    product = awaiting["chosen"]
    budget = awaiting.get("budget")
    reason = awaiting.get("reason")
    quantity = awaiting.get("quantity", 1)
    total = product["price"] * quantity

    print()
    print("Bot: 🛒 Purchase summary")
    print(f"     Product: {product['name']}")
    print(f"     Quantity: {quantity}")
    print(f"     Price: ₹{product['price']:.0f} each")
    print(f"     Total: ₹{total:.0f}")

    if budget is not None:
        print(f"     Your budget: ₹{budget:.0f}")

    print(f"     Reason: {reason}")

    if awaiting.get("budget_override"):
        print(
            f"     ⚠️ This is above your stated budget of "
            f"₹{budget:.0f}, and you explicitly chose to continue."
        )

    print()
    print("     Everything is ready.")
    print(
        "     Type 'buy' to send this purchase to the safety check,"
    )
    print("     or 'cancel' to stop.")


def present_options(awaiting):
    candidates = awaiting["candidates"]
    budget = awaiting.get("budget")

    # No budget supplied yet.
    if budget is None:
        print()
        print("Bot: 🔎 Here's what I found in the catalog:")

        for p in candidates[:3]:
            desc = p.get("description") or ""
            print(
                f"     • {p['name']} — ₹{p['price']:.0f}  "
                f"{desc}".rstrip()
            )

        if not reason_is_sufficient(awaiting.get("reason")):
            explain_reason_needed(candidates[0]["name"])

        explain_budget_needed(candidates[0]["name"])

        if not reason_is_sufficient(awaiting.get("reason")):
            awaiting["stage"] = "need_reason"
        else:
            awaiting["stage"] = "need_budget"

        return

    # Find products that fit the stated budget.
    affordable = [
        p for p in candidates
        if p["price"] <= budget
    ]

    if affordable:
        pick = max(
            affordable,
            key=lambda p: p["price"]
        )

        awaiting["chosen"] = pick

        print()
        print(
            f"Bot: 💰 With a budget of ₹{budget:.0f}, "
            f"the best fit I found is {pick['name']} — "
            f"₹{pick['price']:.0f}."
        )

        desc = pick.get("description") or ""

        if desc:
            print(f"     {desc}")

        if not reason_is_sufficient(awaiting.get("reason")):
            awaiting["stage"] = "need_reason"
            explain_reason_needed(pick["name"])
        else:
            awaiting["stage"] = "confirm"
            show_purchase_summary(awaiting)

        return

    # Nothing fits the budget.
    cheapest = min(
        candidates,
        key=lambda p: p["price"]
    )

    awaiting["chosen"] = cheapest
    awaiting["stage"] = "over_budget"

    print()
    print(
        f"Bot: 💸 Your budget is ₹{budget:.0f}, but the cheapest "
        f"matching product is {cheapest['name']} at "
        f"₹{cheapest['price']:.0f}."
    )

    print("     You have two choices:")
    print("     • Give me a higher budget.")
    print(
        "     • Say 'go with that anyway' if you deliberately "
        "want this product."
    )

    if not reason_is_sufficient(awaiting.get("reason")):
        print()
        explain_reason_needed(cheapest["name"])


def handle_awaiting(awaiting, user_input):
    text = user_input.strip()
    lower = text.lower()

    if lower in ("cancel", "no", "n", "never mind", "nevermind"):
        print("Bot: 👍 No problem. I cancelled that purchase request.")
        return "CANCEL", None

    # If the bot is asking for the reason, allow the user to give
    # the budget first without crashing or losing the budget.
    if awaiting.get("stage") == "need_reason":
        budget = extract_budget(text)

        if budget is None:
            budget = parse_plain_number(text)

        if budget is not None:
            awaiting["budget"] = budget
            print()
            print(f"Bot: 💰 Got it — your budget is ₹{budget:.0f}.")
            print("     I still need to know why you want to buy this product.")
            print('     Example: "My current earbuds broke."')
            print("     Why do you want to buy this product?")
            return "CONTINUE", None

        if len(text) < policy.MIN_REASON_LENGTH:
            print()
            print("Bot: 📝 I need a little more detail about why you want this product.")
            print(
                f"     Please give a reason of at least "
                f"{policy.MIN_REASON_LENGTH} characters."
            )
            print('     Example: "My current earbuds broke."')
            return "CONTINUE", None

        awaiting["reason"] = text

        print()
        print(f"Bot: ✅ Got it. Reason: {text}")

        if awaiting.get("budget") is not None:
            affordable = [
                p for p in awaiting["candidates"]
                if p["price"] <= awaiting["budget"]
            ]

            if affordable:
                awaiting["chosen"] = max(
                    affordable,
                    key=lambda p: p["price"]
                )
                awaiting["stage"] = "confirm"
                show_purchase_summary(awaiting)
            else:
                cheapest = min(
                    awaiting["candidates"],
                    key=lambda p: p["price"]
                )
                awaiting["chosen"] = cheapest
                awaiting["stage"] = "over_budget"

                print()
                print(
                    f"Bot: 💸 Your budget is ₹{awaiting['budget']:.0f}, "
                    f"but the cheapest matching product is "
                    f"{cheapest['name']} at ₹{cheapest['price']:.0f}."
                )
                print(
                    "     Say 'go with that anyway' if you deliberately "
                    "want this product, or give me a higher budget."
                )
        else:
            awaiting["stage"] = "need_budget"
            explain_budget_needed(awaiting["candidates"][0]["name"])

        return "CONTINUE", None

    # Budget handling.
    budget = extract_budget(text)

    if budget is None:
        budget = parse_plain_number(text)

    if (
        budget is None
        and awaiting.get("stage") in ("need_budget", "over_budget")
    ):
        budget = extract_any_number(text)

    if budget is not None:
        awaiting["budget"] = budget
        present_options(awaiting)
        return "CONTINUE", None

    # User deliberately chooses an option above their budget.
    if (
        awaiting.get("stage") == "over_budget"
        and lower in POSITIVE_CONTINUE
    ):
        cheapest = min(
            awaiting["candidates"],
            key=lambda p: p["price"]
        )
        awaiting["chosen"] = cheapest
        awaiting["budget_override"] = True

        print()
        print(
            f"Bot: 👍 Okay. You chose {cheapest['name']} at "
            f"₹{cheapest['price']:.0f}, even though your stated "
            f"budget is ₹{awaiting['budget']:.0f}."
        )

        if not reason_is_sufficient(awaiting.get("reason")):
            awaiting["stage"] = "need_reason"
            explain_reason_needed(cheapest["name"])
        else:
            awaiting["stage"] = "confirm"
            show_purchase_summary(awaiting)

        return "CONTINUE", None

    # User selects a different candidate.
    for p in awaiting["candidates"]:
        if p["name"].lower() in lower or p["id"].lower() == lower:
            awaiting["chosen"] = p

            print()
            print(
                f"Bot: 👍 You selected {p['name']} — ₹{p['price']:.0f}."
            )

            if not reason_is_sufficient(awaiting.get("reason")):
                awaiting["stage"] = "need_reason"
                explain_reason_needed(p["name"])
            elif awaiting.get("budget") is None:
                awaiting["stage"] = "need_budget"
                explain_budget_needed(p["name"])
            else:
                awaiting["stage"] = "confirm"
                show_purchase_summary(awaiting)

            return "CONTINUE", None

    # A detailed message can be a reason.
    reason = extract_reason(text)

    if reason:
        awaiting["reason"] = reason

        print()
        print(f"Bot: ✅ Got it. Reason: {reason}")

        if (
            awaiting.get("chosen")
            and awaiting.get("budget") is not None
        ):
            awaiting["stage"] = "confirm"
            show_purchase_summary(awaiting)
        elif awaiting.get("chosen"):
            awaiting["stage"] = "need_budget"
            explain_budget_needed(awaiting["chosen"]["name"])
        else:
            awaiting["stage"] = "need_budget"
            explain_budget_needed(awaiting["candidates"][0]["name"])

        return "CONTINUE", None

    # Final buy confirmation.
    if (
        awaiting.get("chosen")
        and lower in (
            "buy",
            "yes",
            "y",
            "confirm",
            "go ahead",
            "proceed",
        )
    ):
        if not reason_is_sufficient(awaiting.get("reason")):
            awaiting["stage"] = "need_reason"
            explain_reason_needed(awaiting["chosen"]["name"])
            return "CONTINUE", None

        if awaiting.get("budget") is None:
            awaiting["stage"] = "need_budget"
            explain_budget_needed(awaiting["chosen"]["name"])
            return "CONTINUE", None

        return "BUY", awaiting["chosen"]

    print()
    print("Bot: 🤔 I'm not sure what that means.")
    print("     You can:")
    print("     • Give me your reason for buying the product")
    print("     • Give me your budget")
    print("     • Name a different product")
    print("     • Type 'buy' after the summary is shown")
    print("     • Type 'cancel' to stop")

    return "CONTINUE", None

def print_catalog():
    print()

    for p in products_db.get_all_products():
        stock = (
            f"{p['stock']} in stock"
            if p["stock"] > 0
            else "OUT OF STOCK"
        )

        print(
            f"  {p['id']}  "
            f"{p['name']:<28} "
            f"₹{p['price']:<8.0f} "
            f"{stock}"
        )

    print()


def print_history():
    logs = policy.get_audit_log(
        user_id=DEFAULT_USER_ID
    )

    if not logs:
        print("\n  Nothing yet.\n")
        return

    print()

    for log in logs:
        paid = (
            " [PAID]"
            if log.get("payment_status") == "paid"
            else ""
        )

        print(
            f"  #{log['id']:<4} "
            f"{log['product_name']:<28} "
            f"₹{log['price']:<8.0f} "
            f"{log['decision']:<22}"
            f"{paid}"
        )

    print()


def print_alerts():
    all_alerts = alerts.get_alerts_for_user(
        DEFAULT_USER_ID
    )

    if not all_alerts:
        print("\n  No alerts yet.\n")
        return

    print()

    for alert in all_alerts:
        icon = (
            "⚠️ "
            if alert["severity"] == "warning"
            else "ℹ️ "
        )

        print(
            f"  {icon}{alert['message']}"
        )

    print()


def show_new_alerts():
    unread = alerts.get_alerts_for_user(
        DEFAULT_USER_ID,
        unread_only=True,
    )

    for alert in unread:
        icon = (
            "⚠️ "
            if alert["severity"] == "warning"
            else "ℹ️ "
        )

        print(
            f"{icon} ALERT: {alert['message']}"
        )

        alerts.mark_read(alert["id"])


def respond_to_result(result):
    decision = result["decision"]

    # Normal automatic approval.
    if decision == "approved":

        print(
            f"Bot: ✅ Approved — {result['reason']}"
        )

        product = result.get("product")

        if product:
            qty = result.get("quantity", 1)

            print(
                f"     {product['name']} x{qty} — "
                f"₹{product['price']:.0f} each, "
                f"₹{result.get('total_price', product['price'] * qty):.0f} total"
            )

        if result.get("razorpay_order_id"):

            print(
                f"     Test-mode payment order: "
                f"{result['razorpay_order_id']}"
            )

            print(
                "     (Test mode only — no real money moves, "
                "no shipment/tracking or refund flow exists yet.)"
            )

        return None

    # Mid-price purchase.
    if decision == "pending_user_approval":

        print()
        print(
            "Bot: ⏳ This purchase needs your approval."
        )

        print(
            f"     {result['reason']}"
        )

        print(
            "     Type 'approve' to continue "
            "or 'reject' to cancel."
        )

        return {
            "log_id": result["log_id"],
            "kind": "pending",
        }

    # High-value purchase.
    if decision == "high_value_review":

        print()
        print(
            "Bot: 🚫 This purchase is above the "
            "high-value limit."
        )

        print(
            f"     {result['reason']}"
        )

        print(
            "     Type 'override' only if you have "
            "reviewed the reason and want to continue."
        )

        print(
            "     Otherwise type 'reject'."
        )

        return {
            "log_id": result["log_id"],
            "kind": "high_value",
        }

    # Duplicate purchase.
    if decision == "duplicate_flagged":

        print()

        if result.get("is_probable_gift"):

            print(
                "Bot: 🎁 I found a recent purchase "
                "of this same product."
            )

            print(
                f"     {result['reason']}"
            )

            print(
                "     If this is intentionally a gift/"
                "reorder, type 'confirm'."
            )

        else:

            print(
                "Bot: 🔁 I found a recent purchase "
                "of this same product."
            )

            print(
                f"     {result['reason']}"
            )

            print(
                "     I'm stopping it because it may "
                "be an accidental duplicate."
            )

            print(
                "     Type 'confirm' if you genuinely "
                "want to buy it again."
            )

        print(
            "     Type 'reject' to cancel."
        )

        return {
            "log_id": result["log_id"],
            "kind": "duplicate",
        }

    # Rejected by policy.
    if decision == "rejected":

        print()
        print(
            "Bot: ❌ I couldn't approve this purchase."
        )

        print(
            f"     {result['reason']}"
        )

        return None

    # Payment creation failure.
    if decision == "payment_error":

        print()
        print(
            "Bot: ⚠️ The safety check approved this "
            "purchase, but the test payment order "
            "could not be created."
        )

        print(
            f"     {result['reason']}"
        )

        return None

    return None


def handle_confirmation(pending, user_input):
    action = user_input.strip().lower()

    log_id = pending["log_id"]
    kind = pending["kind"]

    if action in (
        "reject",
        "no",
        "n",
    ):
        policy.reject_pending(log_id)

        print(
            "Bot: 👍 Cancelled. No purchase was made."
        )

        return True

    if (
        action in (
            "approve",
            "yes",
            "y",
        )
        and kind == "pending"
    ):
        order_id = purchase_flow.approve_pending_purchase(
            log_id
        )

        print(
            f"Bot: ✅ Approved."
            f"{' Order: ' + order_id if order_id else ''}"
        )

        return True

    if (
        action == "override"
        and kind == "high_value"
    ):
        order_id = purchase_flow.override_high_value_purchase(
            log_id
        )

        print(
            f"Bot: ✅ Overridden and approved."
            f"{' Order: ' + order_id if order_id else ''}"
        )

        return True

    if (
        action == "confirm"
        and kind == "duplicate"
    ):
        order_id = purchase_flow.confirm_duplicate_purchase(
            log_id
        )

        print(
            f"Bot: ✅ Confirmed."
            f"{' Order: ' + order_id if order_id else ''}"
        )

        return True

    print()
    print(
        "Bot: I need one of: 'approve', "
        "'override', 'confirm', or 'reject'."
    )

    return False


def main():
    products_db.init_db()
    policy.init_db()
    alerts.init_db()

    print(
        "Safe-Cart-AI — watching your AI agent so it doesn't "
        "overspend or"
    )

    print(
        "buy things you didn't really want. "
        "Type 'help' for commands.\n"
    )

    pending = None
    awaiting = None

    while True:

        try:
            user_input = input("You: ").strip()

        except (
            EOFError,
            KeyboardInterrupt,
        ):
            print("\nBye!")
            break

        if not user_input:
            continue

        cmd = user_input.lower()

        # Greetings.
        if is_greeting(user_input):

            print(
                "Bot: 👋 Hi! I'm Safe-Cart-AI — "
                "your AI purchase safety watcher."
            )

            print(
                "     Tell me what you'd like to buy. "
                "I'll identify the product, ask why you "
                "want it, check your budget, and show you "
                "a summary before anything reaches the "
                "purchase safety gate."
            )

            print(
                '     Example: "I need earbuds because '
                'mine broke, budget 1500."'
            )

            print()
            continue

        # Exit.
        if cmd in (
            "quit",
            "exit",
        ):
            print("Bye!")
            break

        # Help.
        if cmd == "help":
            print(HELP_TEXT)
            continue

        # Catalog.
        if cmd == "catalog":
            print_catalog()
            continue

        # History.
        if cmd == "history":
            print_history()
            continue

        # Alerts.
        if cmd == "alerts":
            print_alerts()
            continue

        # Waiting for policy-level approval/override/duplicate confirmation.
        if pending:

            resolved = handle_confirmation(
                pending,
                user_input,
            )

            if resolved:
                pending = None
                show_new_alerts()

            print()
            continue

        # Waiting for product reason/budget/confirmation.
        if awaiting:

            action, chosen = handle_awaiting(
                awaiting,
                user_input,
            )

            if action == "CANCEL":
                awaiting = None

            elif action == "BUY":

                result = purchase_flow.process_purchase(
                    DEFAULT_USER_ID,
                    SESSION_ID,
                    chosen["id"],
                    awaiting["quantity"],
                    awaiting["reason"],
                )

                pending = respond_to_result(result)

                awaiting = None

                show_new_alerts()

            print()
            continue

        # New request.
        candidates = find_candidates(
            user_input
        )

        if not candidates:

            print()
            print(
                "Bot: 🤔 I couldn't identify a product "
                "from that request."
            )

            print(
                "     Please tell me the product name, "
                "such as:"
            )

            print(
                '       • "wireless earbuds"'
            )

            print(
                '       • "mechanical keyboard"'
            )

            print(
                "     Or type 'catalog' to see all "
                "available products."
            )

            print()
            continue

        reason = extract_reason(
            user_input
        )

        awaiting = {
            "need_text": user_input,
            "reason": reason,
            "quantity": extract_quantity(user_input),
            "candidates": candidates,
            "budget": extract_budget(user_input),
            "chosen": None,
            "stage": None,
            "budget_override": False,
        }

        present_options(
            awaiting
        )

        print()


if __name__ == "__main__":
    main()