# QA report (4 Nov 2026)

## 1. Independent code review

Three separate reviewers read the code, one for each area: billing and security, the ₹1,999 and L1 tools, and the webinar and L2 tools. They hadn't seen it being built. Between them they found **52 real defects**. Most were proven with a test before being fixed.

All are fixed, and each now has a permanent test (`tests/test_fixes_core.py`, `test_fixes_l1.py`, `test_fixes_l2.py`).

The serious ones:

- `/billing/verify` could be replayed to get L1 back for free. It now accepts a payment only once.
- L2 edge cases:
  - starting a second L2, or the hours just after an L2 ended, could restart L1 billing or allow a second L1
  - a failed cancel was shown as cancelled
  - revoking an account didn't stop its billing
- Two clicks at the same moment could get a free account a second go, or push past monthly limits. Usage is now counted in one step.
- The IP address used for rate limits could be faked from the browser, which opened up SMS costs and diagnostic spam.
- A member could claim another person's website domain.
- The public diagnostic sent the member's private income goal to the AI next to a stranger's answers. It had no size limit either.
- The ₹1,999 offer and monthly↔yearly switches charged straight away while the old plan was still paid for. They now start when the paid period ends.
- AI providers were named inside two of Akshat's original prompts ("paste it into ChatGPT").
- The 8-minute pitch limit could be skipped with some video formats, and coach chat had no monthly cap.
- About 20 places where an odd AI answer gave a server error instead of "try again" (with the go given back).

## 2. Automated tests

- `pytest`: **361 passed** (measured, 5 Nov: 347 plus 14 for the architecture changes: settings, errors, request ids, module registry, the cases service), up from 234 before the review round
- Covers every tool: it works, a lower plan is locked, the limit stops it, an AI failure gives the go back
- Plus billing, L2, webhooks, public pages, the deck engine (PowerPoint and PDF open with the right slide count, and text never runs past its box), the search and audio clients (with mocked replies), and the WhatsApp templates

## 3. Screen walk (Playwright, test mode, measured)

Run on a phone (390 px) and a computer (1280 px):

- the webinar flow from sign-up to buying L1, cancelling, the ₹1,999 offer and starting L2
- every ₹1,999, L1 and L2 tool used once
- deck download (PowerPoint and PDF) and Present mode
- the public diagnostic page
- every admin page

Results:

- No sideways scrolling and no browser errors (the YouTube video can't load inside the test machine)
- Deck PDF and PowerPoint compared side by side: they match
- Frontend build: no warnings

## 4. Load test

10,000 accounts in a real MongoDB, then 500 webinar attendees at once, and separately 500 paid members at once: 0 failures. Details and limits are in `LOAD_TEST.md`.

## Not tested yet

- **Real vendor accounts:** Razorpay, MSG91, AiSensy, Anthropic (text + web search) and Gemini (video + audio). Each live client follows the vendor's current docs and is tested against mocked replies, but none has run with real keys.
- **Razorpay specifics:**
  - pausing a subscription for L2
  - a plan that starts later (`start_at`)
  - cancelling a paused subscription
- A real 8-minute pitch video uploaded over a phone network.
- Load on Railway + Atlas with real AI speed and rate limits.
- Members connecting their own domain to their website.
- The PowerPoint opened in real PowerPoint (checked in LibreOffice only).
