# QA run: "The AI is busy" (8 November 2026)

What happens to a member when the AI fails, tool by tool, measured on the current code.

**Verdict: every AI tool fails safely.** In all 225 server checks and 6 browser checks:
- the member gets the busy message, not a crash;
- the member never loses a go;
- the server log says why each call failed;
- the page retries once by itself.

Two defects were found and fixed (section 4). Tools also still work when the AI wraps its answer in extra text.

---

## 1. What "The AI is busy" means

Members see one sentence for every AI failure: "The AI is busy right now. Try again in a minute. This didn't use up
your go." The real cause is always one of the cases below, and each now leaves a log line that names it:

| Cause in production | Log line to search for in Railway |
|---|---|
| Anthropic overloaded or rate-limited, wrong key, no credit | `LLM task <tool> failed: <vendor error>` |
| Answer cut off at the output limit | `LLM reply cut at max_tokens=…` |
| No answer within the time limit | `LLM task <tool> timed out` |
| Too many AI calls at once in this worker | `LLM task <tool>: queue full` |
| The answer wasn't usable JSON, or failed the tool's own checks | `AI work failed: tool=<tool> … reason=<what>` |
| Gemini (voice notes, Pitch Practice) overloaded | `voice note transcription failed: …` / `pitch video failed: …` |

---

## 2. How it was tested

`scripts/qa/ai_fault_server.py` runs the whole hub with the AI switched to "live", but the vendor's reply comes from a
fault injector. So every call goes through the real code:
- the queue and the time limit;
- JSON parsing and each tool's own checks;
- metering, refunds and logging.

A healthy answer is built from the tool's own sample, so it is always valid.

`scripts/qa/ai_busy_qa.py` uses a fresh L2 member for each scenario. It first sets up with a healthy AI: a document,
a notebook with sources, LinkedIn contacts, a pitch thread, a portfolio project, a website, a coaching chat and the
knowledge base. Then it switches the AI to the scenario and calls every AI tool. For each call it records the status
and error code, the change in monthly usage, and the log lines.

| Scenario | What the AI does | Expected |
|---|---|---|
| ok | Right answer | Works; one use counted |
| fenced | JSON wrapped in ```` ```json ```` fences with a sentence before and after, as models often do | Works; one use counted |
| truncated | Answer cut off at the output limit | Busy message; use given back; logged |
| vendor_error | Anthropic "529 overloaded" | Busy message; use given back; logged |
| timeout | No answer within the time limit | Busy message; use given back; logged |
| queue_full | No free AI slot | Busy message; use given back; logged |
| not_json | A plain sentence instead of JSON | Busy message; use given back; logged |
| g_ok | Gemini answers | Voice note and pitch scorecard work |
| g_busy_once | Gemini 503 "high demand" twice, then answers | Works, after the automatic retries |
| g_busy | Gemini 503 on every try | Busy message; use given back; logged |
| g_fallback | Main Gemini model busy; the backup (`GEMINI_FALLBACK_MODEL`) answers | Works on the backup |

Tools covered (33):
- **Webinar tools:** Niche Snapshot, case scoring, Meeting Brief.
- **₹1,999 plan:** LinkedIn rewrites, Presentation Builder, Visual Builder, Listen mode, Doc Reader (question and summary), Website (build and section edit), Progress Report.
- **L1:** Action Hub chat, Akshat AI, Offer Card, story from text, Insight Pack, Portfolio (new client and feedback), Pitch coach chat, Research Notebook (question, briefing, timeline and audio overview).
- **L2:** Warm Network scoring, Outreach, Opportunity Radar, Discovery Call Prep, Proposal, Client Diagnostic, Social posts.
- **Gemini:** voice-note story, Pitch video scorecard.

---

## 3. Results

**Server: 225 checks, 225 passed.**

| Scenario | Tools | Result |
|---|---|---|
| ok, fenced | 31 | All worked; exactly one use counted each |
| truncated, vendor_error, timeout, queue_full, not_json | 31 each | 503 busy with the use given back and a log line naming the reason. The exceptions are the two chats, below |
| truncated, chats | 2 | The partial reply is kept and the cut is logged. A coaching reply is useful even if it stops early |
| not_json, chats | 2 | A plain-sentence reply is a valid chat answer |
| g_ok, g_busy_once, g_fallback | 2 each | Worked: on the first try, after 2 busy answers, or on the backup model |
| g_busy | 2 | Busy message after 4 tries (about 20 s in production; the test used shorter pauses); use given back; logged |

**Browser (phone, 390 px): 6 checks, 6 passed** (`scripts/qa/ai_busy_ui.js`), on case scoring and the Offer Card:
- **AI keeps failing:** the page sends the request, waits 2–6 s, retries once, then shows the busy message above the button. Usage stays at "0 of 10 used".
- **AI fails once:** the page's own retry recovers. The member sees the result and never sees an error.
- **AI healthy:** the result shows in about 0.5 s.

---

## 4. Defects found and fixed

| # | What | Who it hit | Fix |
|---|---|---|---|
| 1 | On the Offer Card (and other long forms) a failure re-rendered the form after the "thinking" state had shortened the page. The busy message landed about 270 px below the bottom of a phone screen, so the member saw the top of the page and nothing seemed to happen. | Phone users of long AI forms | The shared error line now scrolls itself into view when it appears. It does this only if it is off-screen, and without animation when the member asks for reduced motion. Verified on screen. |
| 2 | A coaching-chat reply cut off at the output limit was shown half-finished with no log line. | Action Hub, Mentorship and Pitch coach chats (rare at 15,000 tokens) | The chat keeps what was written and logs `LLM chat reply cut …`. Regression test `test_a_cut_chat_reply_is_kept_and_logged`. |

---

## 5. Not covered here (needs the real accounts)

- Anthropic's real overload and rate-limit behaviour at the webinar spike (see `QA_RUN_2026-11-05.md`, section 4).
- How often the live model's JSON still fails a tool's own checks. The "fenced" scenario covers the usual wrapping. If
  a tool still says busy in production, its `AI work failed: tool=… reason=…` line names the field to make tolerant,
  as was done for Portfolio.
- Gemini's real latency on an 8-minute video.

## 6. Re-running
```bash
python scripts/qa/ai_fault_server.py 8002 > fault.log 2>&1 &
python scripts/qa/ai_busy_qa.py http://127.0.0.1:8002 fault.log
HUB_URL=http://127.0.0.1:8002 node scripts/qa/ai_busy_ui.js ./shots
```
