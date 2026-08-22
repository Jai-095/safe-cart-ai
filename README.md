# Safe-Cart-AI

**The problem:** Soon, we'll casually tell an AI "buy me this" or "order me that" the way we'd ask a friend. That's convenient — but it also means the AI has standing permission to spend your money. What stops it from overspending, buying something you didn't really mean, or reordering the same thing twice without you noticing?

**Safe-Cart-AI is a bot that watches that AI.** Talk to it the way you'd talk to a shopping assistant. It decides — auto-approve, ask you first, block outright, or catch a likely accidental duplicate — instead of just spending blindly.

## Run it

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # then fill in your Razorpay TEST keys
python safecart_bot.py
```

Then just talk to it:

```
You: buy me wireless earbuds, mine just broke
Bot: ✅ Approved — Within your auto-approve limit (₹2000). Approved automatically.
     Real test-mode order created: order_xxxxx

You: buy me wireless earbuds again please
Bot: 🔁 You already have an approved order for 'Wireless Earbuds X1' within the
     last 24h. Blocking to avoid an accidental duplicate — confirm explicitly
     if you genuinely want it again.
     Type 'confirm' to buy it again anyway, or 'reject' to skip.
```

Other commands: `catalog` (see what's available), `history` (everything attempted), `alerts` (the full alert log), `help`, `quit`.

## Your spending policy

- **≤ ₹2,000** — auto-approved, no friction
- **₹2,000 – ₹5,000** — needs your explicit approval (`approve` / `reject`)
- **> ₹5,000** — blocked by default; you review the AI's stated reason and must deliberately `override` it
- **Same item bought again within 24h** — blocked by default as a likely accidental duplicate; you `confirm` if you genuinely meant to reorder

**Why the high-value tier isn't "approve if the reason sounds good enough":** scoring whether a typed reason is "hard enough" is unreliable and easy to game — padding text with urgency words would sail through. Instead, above the threshold, it's *always* blocked until a human actually reads the reason and decides. That's a stronger control than trusting text-quality heuristics.

## The watcher, not just the gate

Beyond judging each purchase alone, `alerts.py` watches for patterns across many purchases:
- **Rapid-fire attempts** — 3+ purchase attempts in 15 minutes gets flagged
- **Cumulative overspending** — total approved spend crossing a daily threshold gets flagged even if each individual purchase looked fine alone
- **Every escalation, duplicate, or rejection** raises an immediate alert

## Why simple keyword matching, not an LLM call

`match_product()` matches your typed request against the catalog by keyword overlap, not by calling an actual language model. This is deliberate: the whole point of this project is an auditable, explainable safety layer — a black-box LLM guess about what you meant would undermine that. The matching is simple enough to read in one glance and reason about exactly why it picked what it picked.

## Architecture

```
   You, typing        Claude/an AI agent
   (safecart_bot.py)   (mcp_server.py, over MCP)
          │                    │
          └─────────┬──────────┘
                     ▼
            products_db.py (shared catalog)
                     │
                     ▼
             policy.py (the gate: tiers + duplicate check)
                     │
                     ▼
             alerts.py (pattern watcher)
                     │  (approved only)
                     ▼
       purchase_flow.py → Razorpay Test-Mode Orders API
```

## Paying for real (test mode)

Approved purchases create an actual Razorpay test-mode order. No checkout UI here (no website) — the order is created and its ID is shown; wiring up an actual payment capture would be the natural next step if you want a fuller demo.

## Project files

| File | What it does |
|---|---|
| `safecart_bot.py` | **The bot** — the conversational interface, run this |
| `products_db.py` | SQLite-backed catalog |
| `policy.py` | The spending gate — tiers, duplicate detection, per-user audit log |
| `alerts.py` | Pattern detection across purchases |
| `purchase_flow.py` | Orchestration: policy check → real Razorpay order → approve/override/confirm actions |
| `mcp_server.py` | Lets a real AI agent (Claude, etc.) connect over MCP and buy through the same policy |
| `test_agent.py` | Standalone script exercising the MCP flow directly |

## What broke, and how it was solved

*(Real issues hit while building this — adapt honestly for the form's "What broke" field:)*

- The `mcp` Python package had a breaking major-version change mid-build, breaking the original import path. Migrated to the actively-maintained `fastmcp` library.
- An early "add item" function had a SQL column/value misalignment that silently corrupted the price field — caught only by testing each field immediately after insertion, since an end-to-end test had accidentally masked it.
- Built a full website with logins first, then realized the actual goal was a personal watcher bot, not a multi-user storefront — rewrote the interface layer entirely (dropped the website and accounts, built a conversational CLI) while keeping the tested safety core (`policy.py`, `alerts.py`) intact underneath, since that logic didn't need to change, only how you talk to it.

## Limitations / what's next

- Product matching is simple keyword overlap, not true NLU — "get me something for my ears" wouldn't match "Wireless Earbuds X1"; a real version might add fuzzy matching or an LLM-assisted parser while keeping the actual policy gate deterministic
- Single local user by default — no multi-account system
- Policy thresholds (₹2000 / ₹5000 / 24h duplicate window) are constants, not user-configurable yet
