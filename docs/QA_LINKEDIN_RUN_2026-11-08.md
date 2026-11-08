# QA run: LinkedIn Profile Review (8 November 2026)

A rigorous test of the LinkedIn section: the screenshot review, the 30-day post plan and the quick text check.

**Verdict: ready to ship.** The QA found 6 defects, all now fixed (section 2). Every check passes:
- **Backend:** 437 tests pass. Of these, 51 are new QA checks on this section and 9 are earlier tests of the feature.
- **AI failures:** 239 checks pass, 14 of them on the two LinkedIn endpoints.
- **Browser:** 35 checks pass on a phone, a 320 px phone and a computer.

What can only be tested with the live AI is listed in section 4.

---

## 1. What was tested

| Area | Checks | Covers |
|---|---|---|
| What the member uploads | 21 | Text, PDF, corrupt and fake-PNG files refused (415). One bad file refuses the whole upload. Over 8 MB refused (413). Over-sized "bomb" images refused unread. 0 and 6+ files refused. Tiny images refused. JPEG, WebP, PNG with transparency, grayscale, palette, 16-bit and GIF all read. Phone shots cut into readable pieces. Photo rotation honoured. At most 8 images reach the AI. Screenshots never stored. **No refused upload uses up a go.** |
| Who the review is for | 3 | Falls back to the niche from Starting Point. A typed client wins. Long text trimmed. The member's own proof (stories, Offer Card) reaches the AI. |
| Allowances | 7 | The allowance on each plan. Free: one review and one plan, then the upgrade prompt. The quick check has its own allowance. Two taps at the same instant use one go. |
| Who can see what | 2 | Logged-out visitors refused. Member B can't open, tick or reuse member A's review or plan. |
| 30-day plan | 11 | Without a review, the plan uses the niche or a typed client. Day bounds (0, 31, -1, "abc"). Ticks can be undone and survive a reload. Day 1 is tomorrow in India: checked at 23:59 IST, at 00:01 IST and over New Year. |
| What the AI sends back | 7 | The shapes a live model really writes are read correctly: scores as "72/100", sections named differently, headlines as plain strings, About as a list of paragraphs, lists as lines. Over-long headlines trimmed and About capped at LinkedIn's 2,600 characters. Scores clamped to 0–100. AI company names never shown. A "not LinkedIn" answer gives the go back. A plan with a broken post drops that post. |
| The rest of the hub | 3 | Home, My Consulting File, the Progress Report and the admin webinar report all count a screenshot review |
| AI failures (fault server) | 14 | Review and plan under: cut-off answer, overloaded, timeout, queue full, not JSON, and fenced JSON. Each shows the busy message, gives the go back and logs the reason |
| Browser (`scripts/qa/linkedin_ui.js`) | 35 | Wrong file, too big, too many, remove a screenshot, missing client, missing screenshots. Keyboard focus. A full review, reload, copy to clipboard, "Review again" and back. AI failure mid-review keeps the screenshots and the typed client, then works on retry. Plan weeks, ticks surviving a reload, untick. Free account limits. Home and File updated. 320 px phone. The quick check still works |

---

## 2. Defects found and fixed

| # | What | Impact | Fix |
|---|---|---|---|
| 1 | An image with huge dimensions but a tiny file size (for example 9,000 × 9,000 of one colour) passed the size check. It was fully decoded, using about 240 MB of memory each. | Five such files could crash a server worker. | The image size is read from the header before decoding; anything over 30 megapixels is refused unread. |
| 2 | A score written as "72/100" became 50. | Wrong client-fit score whenever the model writes it that way. | Scores are read from text ("72/100", "Score: 72"). |
| 3 | Home, My Consulting File, the Progress Report and the admin webinar report only knew the old quick check. | A member who did the screenshot review still saw "LinkedIn: Not checked yet". It didn't count in their Progress Report or the webinar funnel. | One helper gives the latest LinkedIn result, review or quick check. Home shows "Client fit", the File shows "LinkedIn client fit", and the Progress Report and admin count reviews. |
| 4 | Picking a text file, or more than 5 screenshots, set a message and wiped it in the same moment. | The member got no explanation. | The message is set after the picked files update. |
| 5 | The screenshot picker showed no focus for keyboard users. | Not accessible by keyboard. | A visible focus ring on the picker. |
| 6 | A test-only mistake: the double-tap test accepted almost any result. | A real double-spend would not have been caught. | Rewritten to send two truly simultaneous requests, and to require exactly one review and one go used. |

---

## 3. Behaviour confirmed

- **A failed review costs nothing**, whatever the cause: bad file, AI failure or a non-LinkedIn image.
- **After an AI failure** the member's screenshots and typed client are still on the form, and pressing again works.
- **Screenshots are never stored.** The saved review is text only (under 20 KB).
- **Privacy between members holds:** IDs from another member's review or plan give "not found", and a plan request quoting someone else's review ID uses the member's own review instead.

---

## 4. Not covered here (needs the live AI key)

- **How well the live vision model reads real LinkedIn screenshots:** small fonts, dark mode, non-English text. All tests used the tools' own simulated answers. The first real reviews should be read by the team.
- **Time and cost** of a real review: up to 8 images on the vision model, 150 s timeout. Also the real plan time (about 30 posts, 170 s timeout).

## 5. Re-running
```bash
cd backend && python -m pytest -q tests/test_linkedin_review.py tests/test_linkedin_qa.py
python scripts/qa/ai_fault_server.py 8002 > fault.log 2>&1 &
python scripts/qa/ai_busy_qa.py http://127.0.0.1:8002 fault.log
HUB_URL=http://127.0.0.1:8002 node scripts/qa/linkedin_ui.js <dir with test files> <shots dir>
```
The browser script needs a folder with `notes.txt`, `big.png` (over 9 MB) and `s0.png`…`s6.png` (1080×900 PNGs).
