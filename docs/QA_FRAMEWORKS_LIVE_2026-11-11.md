# Live QA: Work along with Akshat (11 November 2026)

The three frameworks on production (`consulting-hub-v2-production.up.railway.app`), as the QA member (L2, niche:
vendor cost reduction for Tier-2 auto component makers), with the real Claude.

1. **API, real AI:** `scripts/qa/live/frameworks.py`, **29 of 29** passed.
2. **Browser, phone and desktop:** `scripts/qa/live/frameworks_walk.js`, **31 of 32** passed; the one failure is
   defect 3 below.
3. **Local regression after the fixes:** `scripts/qa/frameworks_ui.js` **96 of 96**, `tests/test_frameworks.py` **47 of 47**.

**Verdict:** the frameworks work on production. Claude answers again, so the production AI outage of 9 November is over.

## What was tested

| Area | Result |
|---|---|
| Akshat's cases | All three saved and marked full, with Akshat's read; incomplete answers refused in plain words |
| Suggest a client from my niche | 3 of 3 in 4–7 s, all inside the niche (machining unit in Coimbatore, forging units near Pune); one `fw_case` each |
| Own case saved and checked by the rules | Market-Fit 2 of 3 circles hold; Concentration 7 of 7 on 5 sources (54%, red, wait); Compass 2 of 2 |
| Thin hand-written case | Refused: "Name or describe the client (at least 3 characters)." |
| Proposals (real AI) | 1 on Akshat's case, 3 on own clients, 20–28 s each; own proposals use only the member's client, with objective, phases and a fee in ₹ |
| Pages | Practice cases card gone; own clients listed on Cases; niche named; suggest in the page fills the editor (5 sources, 5 % boxes); no sideways scroll; no browser errors |

**Quality:** the own-client proposal is specific and usable. For example, the forging unit: "Tier-1 supplier A brings in
₹22.70 crore, which is 54% of revenue… hold the press order, bring supplier A down to about 35%". It has 4 phases with
outputs, a decision gate for the ₹9 crore press, and a ₹2.5–3.5 lakh fee.

## Defects found and fixed

| # | What | Fix |
|---|---|---|
| 1 | A suggested Growth Compass client was named "Bharat Forge Works (a made-up name for practice)", close to a real listed company | The AI is told never to name the business or anyone in it ("the unit", "the owner"); a "(made-up name)" note is removed |
| 2 | Market-Fit "product" was the consultant's own service, cut mid-word at 160 characters, so the title read "Will A vendor cost-reduction service … tool life tracking, succeed in …" | The product must be what the client sells, 3–8 words. Long text is cut on a word. The title reads "Will a …" |
| 3 | After "Suggest another client", the new client sat in the editor while the old client's marking and proposal showed below, unlabelled; "Generate again" would have written for the old client | A label now says these belong to the saved client and to save the new one to replace them. "Generate" is hidden until it is saved |
