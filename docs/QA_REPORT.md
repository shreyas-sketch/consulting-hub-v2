# QA report — stage 1 (4 Nov 2026)

## Automated tests

- `pytest`: **54 passed**
- Covers: OTP sign-up (free account, no trial), plans and limits (free = once for life, paid = monthly), webinar switch, checkout monthly/yearly with GST, upgrade ₹1,999 → L1 stops the old renewal, L1 cancel shows the ₹1,999 offer once, webhook signatures, L2 start pauses L1, L1 restarts after 6 months, pause-refused fallback, late charge can't wake a paused L1, every tool's happy path and limits, AI failure gives the go back, Meeting Brief only shows links that search really returned, admin reports skip team accounts and disabled accounts, all 52 GPT prompts present.

## Screen walk (Playwright, test mode)

Ran the full flow on a phone (390 px) and a computer (1280 px): visitor page → OTP sign-up → all six tools → My Consulting File → plans → buy L1 → LinkedIn rewrites → cancel L1 and see the offer → admin pulse, live, webinar, settings, member detail, start L2.

- No errors in the browser console
- No sideways scrolling on any screen
- Frontend build: no warnings

## Not tested yet

- Real vendors (Razorpay, MSG91, AiSensy, Anthropic, Tavily) — need keys on staging
- Load with a real database — see `LOAD_TEST.md`
