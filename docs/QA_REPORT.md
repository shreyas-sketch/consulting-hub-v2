# QA report (4 Nov 2026)

## Automated tests

- `pytest`: **234 passed** (measured)
- For every tool: it works, a lower plan is locked, the monthly limit stops it, and an AI failure gives the go back.
- Billing: OTP sign-up (no trial), free = once for life, paid = monthly, monthly/yearly checkout with GST, upgrade stops the old renewal, L1 cancel shows the ₹1,999 offer once, webhook signatures, L2 pauses L1, L1 restarts after 6 months, pause-refused fallback, a late charge can't wake a paused L1.
- Links: Meeting Brief, Radar and Research only show links that search really returned.
- Public pages: a member website stays hidden until it is published; its lead form and the client diagnostic link have rate limits.

## Screen walk (Playwright, test mode, measured)

Two scripted walks, each run on a phone (390 px) and a computer (1280 px):

1. Webinar flow: visitor page → OTP sign-up → the six tools → My Consulting File → plans → buy L1 → LinkedIn rewrites → cancel L1 and see the offer → admin pages → start L2.
2. Every ₹1,999, L1 and L2 tool, each used once, plus the public diagnostic page and the admin pages for support, questions, weekly case, program, calls, recaps, library and bootcamps.

- No sideways scrolling on any screen (one found on the Website Builder on a phone; fixed)
- No browser errors, except the YouTube video, which can't load inside the test machine
- Frontend build: no warnings

## Not tested yet

- Real vendors: Razorpay, MSG91, AiSensy, Anthropic, Tavily, Gamma, OpenAI audio, Gemini video. Each live client follows the vendor's public docs, but none has run against a real account. Test each on staging with keys.
- Pitch Practice with a real 8-minute video (upload time and analysis time on a phone network).
- Load with a real database (see `LOAD_TEST.md`).
- Own domains for member websites (needs a real domain and Railway).
