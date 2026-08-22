# 5-Minute Pitch Video Script — Safe-Cart-AI

Format: screen recording of your terminal + voice-over. Zoom your
terminal font in before recording so it's readable on a phone screen.

---

## 0:00 – 0:30 — The problem

**Say (in your own words):**
> "Soon we'll casually tell an AI 'buy me this' or 'order me that,' the
> way we'd ask a friend. That's convenient — but it means the AI has
> standing permission to spend your money. What stops it from
> overspending, buying something you didn't really mean, or ordering
> the same thing twice because it forgot it already did?"

---

## 0:30 – 1:00 — The solution

**Say:**
> "Safe-Cart-AI is a bot that watches that AI. You talk to it like a
> shopping assistant, and it decides whether the purchase actually
> goes through — auto-approved under 2000 rupees, needs my OK between
> 2000 and 5000, blocked outright above that unless I explicitly
> override it, and blocked if it looks like an accidental repeat
> order — instead of just spending blindly."

---

## 1:00 – 3:30 — Live demo

**Show:** `python safecart_bot.py` running in your terminal.

**Step 1 — cheap item, auto-approved (~30 sec)**
Type: `buy me wireless earbuds, mine just broke`
> "Under my auto-approve limit, with a real reason given — approved
> instantly, and that's a real Razorpay test-mode order coming back."

**Step 2 — the duplicate catch (~45 sec) — your key differentiator**
Type: `buy me wireless earbuds again please`
> "Now watch this — I ask for the same thing again. Instead of just
> buying it a second time, it recognizes I already have a recent order
> for this exact item and blocks it as a likely accidental duplicate.
> This is the actual problem I set out to solve — an AI reordering
> things you already have."
Type `confirm` to show you can still go through with it deliberately.

**Step 3 — mid-price, needs approval (~40 sec)**
Type: `order the mechanical keyboard for my desk`
> "This one's above my auto-approve limit, so it stops and asks me
> directly instead of deciding on its own."
Type `approve`.

**Step 4 — high-value, blocked by default (~40 sec)**
Type: `purchase noise cancelling headphones for my flight`
> "This is above my high-value threshold, so it's blocked by default.
> I have to actually read the AI's reason and consciously override it
> — I didn't build an algorithm that guesses if a reason 'sounds good
> enough,' because that's gameable. A human deciding is the stronger
> control."
Type `override`.

**Step 5 — show the alert log (~20 sec)**
Type: `alerts`
> "Every one of those got logged as an alert, and it's also watching
> for patterns — too many attempts in a short window, or spending
> crossing a daily total — not just judging each purchase alone."

---

## 3:30 – 4:15 — Why this design (mention briefly)

> "The matching from what I type to an actual catalog item is
> deliberately simple keyword matching, not a black-box AI call —
> because the whole point of a safety layer is being auditable. I'd
> rather have something I can explain in one sentence than something
> that works most of the time for reasons I can't fully account for."

*(Optional: mention one real build issue — e.g. "I actually built this
as a full website with logins first, then realized that wasn't the
actual idea — a personal watcher, not a multi-user storefront — so I
rebuilt the whole interface, but kept the tested safety logic
underneath, since that part didn't need to change.")*

---

## 4:15 – 5:00 — What's next

> "Right now the matching is simple keyword overlap, and thresholds
> are fixed constants. With more time, I'd add smarter matching, and
> let each person tune their own limits. Thanks for watching."

---

## Quick reference: "Build Challenges" form answer

- The `mcp` Python package had a breaking major-version change mid-build, breaking the original import path — migrated to the actively-maintained `fastmcp` library instead.
- An early "add item" function had a SQL column/value misalignment that silently corrupted the price field — caught by testing each field immediately after insertion, since an end-to-end test had accidentally masked the bug.
- Realized partway through that a full website with logins didn't match the actual goal (a personal AI-watching bot, not a storefront) — rebuilt the interface layer as a conversational CLI while keeping the tested policy/alerts core unchanged underneath.
