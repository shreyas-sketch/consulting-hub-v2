# In-depth QA: the six webinar tools (9 November 2026)

Readiness Score, Starting Point (Niche Snapshot and Goal Map), Cases, Meeting Brief, LinkedIn Review and My Consulting
File, tested three ways:

1. **Server rules:** `tests/test_webinar_qa.py`, 58 checks.
2. **Screens:** `scripts/qa/webinar_ui.js` with 58 checks on phone and desktop, plus `scripts/qa/linkedin_ui.js` with 35.
3. **Live AI quality on production:** done this morning (see `QA_LIVE_RUN_2026-11-09.md`). A second, deeper quality pass
   was stopped by an outage (section 4).

**Verdict:** the six tools work. The QA found **8 defects**:
- 6 are fixed and covered by tests;
- 1 was fixed earlier today (topic pages shown as news);
- 1 is a UX policy to decide (the Goal Map can be saved once on a free account).

All 513 backend tests pass; 151 browser checks pass.

---

## 1. What was tested

| Tool | Server checks | Browser checks (phone + desktop) |
|---|---|---|
| Readiness Score | Missing, unknown, out-of-range and non-number scores; potential bounds; all four bands and their edges (24/25, 39/40, 49/50); the two lowest skills as focus (tie order); gap to potential; free once, paid monthly; change since last time; history order | Sliders by keyboard, total, band and focus shown; result kept after reload; no retake on a free account |
| Starting Point | Empty, blank-only and too many experiences; years, proof and industry bounds; whitespace cleaned; "enjoy" marks; three options sorted by score with consistent totals and fees; free once; choosing an option (bounds, unknown, someone else's); the chosen option drives other tools; Goal Map maths (rounding, fee above goal), bounds, preview free, save kept | 60 years refused in plain words; three options; the chosen option kept after reload; no second snapshot when free; Goal Map numbers live while typing; saved goal back after reload |
| Cases | Free: live case first, others locked (list, open, answer); model answer only after answering; answer length; free once; an answered case stays readable after the live case changes; paid members answer any case and keep history; scores in the shapes a live model writes; the "instructions in the answer" guard | Live case first; locked cases show the plan; model answer hidden first; short answer gets a message; scores and model answer, kept after reload; no second try when free |
| Meeting Brief | Bad input; only real news picks (repeats, 0, negative, out of range, words dropped); made-up links stripped from the text; an incomplete AI answer gives the go back; list order; privacy | No company → message; full brief; listed under past briefs |
| LinkedIn Review | Covered by 60 earlier checks; here, the Readiness tip names it correctly | Review form; quick check; plus the 35-check LinkedIn suite |
| My Consulting File | Empty file for a new member; every tool brought together (the *chosen* niche, not the first); reading costs nothing and works after the free goes are used | Empty state; every tool shown; print / save as PDF; no sideways scroll |

## 2. Defects found and fixed

| # | Tool | What | Fix |
|---|---|---|---|
| 1 | Readiness | A missing skill counted as 1, and a score of 50 became 10, silently. The member's total could be wrong. | All six skills, each 1–10, are required. Anything else is refused (422) without using the go. |
| 2 | Readiness | The tip for the "Visibility" skill still said "Run the LinkedIn Score". | It now says "Run LinkedIn Review and make its first quick win". |
| 3 | Cases | A criterion scored "6/10" by the AI became **0**. "Scope" with a capital letter failed the whole answer as "AI is busy". | Scores are read as numbers, "6/10", "7 out of 10", "70/100", `{score: n}`, in any letter case, or as a list of criteria. |
| 4 | Cases | Nothing told the scorer that the member's answer is text to score. "Give me 10/10" inside an answer was unguarded. | The scorer is told the answer is text to score, never instructions. |
| 5 | Cases | An answer padded with spaces passed the 40-character minimum. | Spaces are trimmed before the length check. |
| 6 | Meeting Brief | Repeated or invalid news picks used up the three slots, so good items listed later were dropped. | Up to three *valid* picks are kept. |
| 7 | Meeting Brief | News showed topic pages ("Tata Motors Latest News – Top News"). | Fixed earlier today (`840ea2d`). |

## 3. To decide

- **Goal Map on a free account can be saved once for life.** A webinar attendee who mistypes their goal can never correct
  it, though the live preview stays free. Suggest allowing re-saves: the Goal Map uses no AI and costs nothing.

## 4. Live AI quality: stopped by a production outage

A second quality pass on production was ready to run:
- four case answers (strong, vague, gibberish, and one that asks for 10/10);
- two very different careers through Niche Snapshot;
- a big and a small company for Meeting Brief;
- a strong LinkedIn profile.

At 13:10–13:14 UTC **every Claude call on production failed instantly** (0.3–0.8 s, "AI is busy"). Tools without AI kept
working, and the release was unchanged. The cause is on the account side; see the reply in chat. The pass re-runs with
`scripts/qa/live/` once Claude answers again.

This morning's live run already showed good quality on the same tools:
- the case scored 5.2 with specific feedback;
- a sharp niche;
- a LinkedIn review that caught #OpenToWork;
- briefs with real search results.
