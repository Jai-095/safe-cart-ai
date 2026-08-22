# Safe-Cart-AI

**A safety and monitoring layer for AI-powered commerce.**

## The problem

Soon, we'll casually tell an AI, "buy me this" or "order me that," the
way we'd ask a friend. That's convenient --- but it also means an AI
agent may have permission to spend your money.

What happens if it:

-   buys something you didn't really mean to purchase?
-   spends more than you intended?
-   repeats the same purchase accidentally?
-   makes several purchases in a short period?
-   gradually overspends even though each individual purchase looks
    reasonable?

**Safe-Cart-AI is a safety layer that watches AI-initiated purchases.**

Instead of allowing an AI agent to spend blindly, Safe-Cart-AI evaluates
each purchase against deterministic policies and can **auto-approve, ask
for human approval, block the purchase, detect likely duplicates, and
raise alerts when suspicious patterns appear.**

The goal is simple:

> **Let AI handle commerce, while keeping the human in control of
> spending.**

------------------------------------------------------------------------

## Run it

Create and activate a virtual environment, install the dependencies,
configure Razorpay test credentials, and start the bot:

``` bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # Windows PowerShell: copy .env.example .env
```

Then fill in your **Razorpay TEST keys** inside `.env` and run:

``` bash
python safecart_bot.py
```

> **Security:** Never commit `.env` to GitHub. Use `.env.example` as the
> safe template for required environment variables.

### Example

``` text
You: buy me wireless earbuds, mine just broke

Bot: ✅ Approved — Within your auto-approve limit (₹2000).
     Approved automatically.
     Razorpay test-mode order created: order_xxxxx

You: buy me wireless earbuds again please

Bot: 🔁 You already have an approved order for
     'Wireless Earbuds X1' within the last 24h.
     Blocking to avoid an accidental duplicate.

     Type 'confirm' to buy it again anyway,
     or 'reject' to skip.
```

Other commands:

``` text
catalog   → see available products
history   → see purchase attempts/history
alerts    → see the alert log
help      → see available commands
quit      → exit the bot
```

------------------------------------------------------------------------

## Your spending policy

SafeCart-AI uses deterministic rules to decide how much friction a
purchase should receive:

  -----------------------------------------------------------------------
  Purchase condition                  Decision
  ----------------------------------- -----------------------------------
  **≤ ₹2,000**                        Auto-approved

  **₹2,000 -- ₹5,000**                Requires explicit human approval

  **\> ₹5,000**                       Blocked by default; requires
                                      deliberate human override

  **Same item within 24 hours**       Blocked by default as a likely
                                      accidental duplicate; explicit
                                      confirmation can allow it
  -----------------------------------------------------------------------

### Why the high-value tier is always blocked by default

A typed reason should not be treated as proof that a high-value purchase
is safe.

Trying to score whether a reason sounds "good enough" is unreliable and
easy to manipulate --- adding urgency words or extra explanation could
potentially influence a text-based heuristic.

Instead, SafeCart-AI uses a stronger rule:

> **Above the high-value threshold, a human must deliberately review and
> override the block.**

This keeps the final decision under human control.

------------------------------------------------------------------------

## The watcher, not just the gate

SafeCart-AI does more than evaluate purchases one at a time.

`alerts.py` looks across purchase activity for patterns that may
indicate unusual or risky behavior:

-   **Rapid-fire attempts** --- 3 or more purchase attempts within 15
    minutes are flagged.
-   **Cumulative overspending** --- approved spending crossing the
    configured daily threshold is flagged, even when individual
    purchases were each allowed.
-   **Escalations** --- high-value purchase attempts that require an
    override raise an alert.
-   **Duplicates** --- likely accidental duplicate purchases raise an
    alert.
-   **Rejections** --- rejected purchase attempts are recorded and raise
    an alert.

This is the key difference between a simple payment gate and a
**commerce safety watcher**: it can reason about activity across
multiple purchase attempts rather than looking at only one transaction.

------------------------------------------------------------------------

## Why simple keyword matching instead of an LLM call?

`match_product()` matches a user's request against the product catalog
using keyword overlap rather than calling an external language model.

This is deliberate.

The core safety layer should be:

-   **Auditable** --- you can inspect why a product matched.
-   **Deterministic** --- the same input follows the same matching
    logic.
-   **Explainable** --- the system does not hide the product-selection
    decision behind a black-box model.
-   **Independent of an LLM** --- the safety gate should not depend on
    another model making the final spending decision.

For example, a request such as:

``` text
buy me wireless earbuds
```

can be matched against the catalog using straightforward, inspectable
logic.

A future version could add fuzzy matching or an LLM-assisted parser for
better natural-language understanding while keeping the **actual
spending policy deterministic**.

------------------------------------------------------------------------

## Architecture

``` text
                  User / AI Agent
                       │
             ┌─────────┴─────────┐
             │                   │
      safecart_bot.py      mcp_server.py
       CLI interface       MCP interface
             │                   │
             └─────────┬─────────┘
                       ▼
              products_db.py
             Shared product catalog
                       │
                       ▼
                  policy.py
             Spending + duplicate
                    safety gate
                       │
                       ▼
                  alerts.py
             Pattern / risk watcher
                       │
                       ▼
               purchase_flow.py
          Approval / override / confirm
                       │
                       ▼
          razorpay_client.py
                       │
                       ▼
             Razorpay Test Mode
```

The important design principle is that **different interfaces use the
same safety core**.

A user can interact through the conversational bot, while an external AI
agent can connect through MCP. Both paths are designed to pass through
the same policy and purchase-flow controls.

------------------------------------------------------------------------

## AI-agent integration through MCP

`mcp_server.py` exposes the commerce functionality through the **Model
Context Protocol (MCP)**.

This allows an AI agent such as Claude or another MCP-compatible agent
to interact with the same SafeCart-AI safety layer instead of bypassing
it.

The intended architecture is:

``` text
AI Agent
   │
   ▼
MCP Server
   │
   ▼
SafeCart-AI Policy
   │
   ├── Auto-approve
   ├── Ask for approval
   ├── Block
   ├── Detect duplicate
   └── Raise alerts
   │
   ▼
Razorpay Test Mode
```

This is important because the safety logic is not limited to the CLI
interface --- it is designed to sit between an AI agent and the commerce
action.

------------------------------------------------------------------------

## Razorpay Test Mode

Approved purchases can create an actual **Razorpay test-mode order**.

No real money is charged in test mode.

This project currently creates the test-mode order and displays its
order ID. It does **not** implement a complete checkout/payment-capture
flow.

A natural next step would be connecting the approved order to a checkout
UI and completing the payment lifecycle while keeping the same safety
controls in front of it.

------------------------------------------------------------------------

## Project files

  -----------------------------------------------------------------------
  File                                What it does
  ----------------------------------- -----------------------------------
  `safecart_bot.py`                   Conversational CLI interface ---
                                      run this to interact with
                                      SafeCart-AI

  `products_db.py`                    SQLite-backed product catalog and
                                      product lookup

  `policy.py`                         Spending gate, spending tiers,
                                      duplicate detection, and purchase
                                      audit logic

  `alerts.py`                         Detects suspicious patterns across
                                      purchase activity

  `purchase_flow.py`                  Coordinates policy checks,
                                      approval/override/confirmation
                                      actions, and order creation

  `razorpay_client.py`                Handles the Razorpay test-mode API
                                      integration

  `mcp_server.py`                     Allows an MCP-compatible AI agent
                                      to interact with the same safety
                                      layer

  `test_agent.py`                     Standalone script for exercising
                                      the MCP flow

  `data/products.json`                Product/catalog seed data

  `requirements.txt`                  Python dependencies

  `.env.example`                      Template for required environment
                                      variables

  `PITCH_SCRIPT.md`                   Project presentation/demo script

  `README.md`                         Project documentation
  -----------------------------------------------------------------------

------------------------------------------------------------------------

## What broke, and how it was solved

Real implementation issues were encountered during development:

-   The `mcp` Python package went through a breaking major-version
    change during development, which broke the original import path. The
    project was migrated to the actively maintained `fastmcp` library.
-   An early "add item" function had a SQL column/value misalignment
    that caused the price field to be stored incorrectly. The issue was
    found by checking database fields immediately after insertion.
-   The project originally started as a website with logins and a
    storefront-style interface. During development, it became clear that
    the core problem was not building another shopping website --- it
    was building a **personal safety watcher for AI-driven purchases**.
    The interface was therefore simplified into a conversational CLI
    while retaining the tested safety logic underneath.
-   The project evolved from evaluating individual purchases to also
    watching for patterns such as rapid-fire attempts, duplicates, and
    cumulative spending.

These iterations helped keep the final design focused on the actual
safety problem.

------------------------------------------------------------------------

## Limitations / What's next

SafeCart-AI is a working prototype, but several areas can be improved:

-   **Product matching** currently uses keyword overlap rather than full
    natural-language understanding. For example, "get me something for
    my ears" may not match "Wireless Earbuds X1."
-   **Single local user** is supported by default; there is no
    multi-account system yet.
-   **Policy thresholds** such as ₹2,000, ₹5,000, and the 24-hour
    duplicate window are currently constants rather than
    user-configurable settings.
-   **Razorpay integration** currently uses test mode and creates test
    orders; real payment capture and a checkout experience are not
    implemented.
-   **Natural-language product understanding** could be improved with
    fuzzy matching or an LLM-assisted parser while keeping the final
    safety policy deterministic.
-   **Persistent monitoring** could be expanded into a dashboard or
    notification system for real-world deployment.

------------------------------------------------------------------------

## Future vision

The long-term idea behind SafeCart-AI is bigger than one shopping bot.

As AI agents gain the ability to purchase products, book services,
subscribe to plans, and spend money on behalf of users, there should be
a **trusted safety layer between autonomous agents and real-world
financial actions**.

SafeCart-AI explores that idea with a simple principle:

> **AI can make the purchase request. A safety layer should make sure
> the purchase is actually safe.**
