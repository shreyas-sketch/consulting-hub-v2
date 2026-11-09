# Live QA run: production (9 November 2026)

An end-to-end test on the live app (`consulting-hub-v2-production.up.railway.app`, release `2dcdae5`) with real outside
services: Anthropic, web search, Gemini, AiSensy and Razorpay all in live mode. It logged in with two test numbers that
receive nothing (`OTP_TEST_NUMBERS`). Member `…001` started free, and admin `…002` then switched it to L2.

**Verdict: the hub works on production.** 243 of 246 checks passed. Of the 3 that failed, 2 are one defect: Gemini
transcription and video analysis don't answer in time. The third is a test of mine with a field missing, not a defect. One
quality defect (topic pages shown as news) is fixed in code and waits for a deploy. One setup gap remains: the knowledge
base is empty.

---

## 1. Results

| Area | Checks | Result |
|---|---|---|
| Logged out: health, database, security headers, auth refusals, QA back door off, OTP input checks, 404s, app shell, caching, speed | 37 | 37 pass |
| Public screens in a browser (home, login, plans, terms, privacy) on phone and desktop, login message, redirect to login | 14 | 14 pass |
| Free webinar tools with real AI: Readiness, Niche Snapshot, Goal Map, live case scoring, Meeting Brief, LinkedIn quick check, **LinkedIn Profile Review (vision)**, 30-day plan, File, limits (402), paid lock (403) | 15 | 15 pass |
| Admin: 21 admin pages, find member, member detail, start L2, second start refused | 25 | 25 pass |
| ₹1,999 plan: LinkedIn rewrites, deck made and downloaded as PowerPoint and PDF, two visuals, Listen mode (real speech, 1.2 MB MP3), Doc Reader (upload, cited answer, summary), website build, AI edit, publish, public page, unpublish, Progress Report, support ticket with admin reply and close, inbox | 18 | 18 pass |
| L1: 11 page data loads, Action Hub chat, Akshat AI, Offer Card, story from text, **story from voice note**, Insight Pack, Portfolio client and feedback, Pitch coach chat, **Pitch video scorecard** | 22 | 20 pass, **2 fail** (both Gemini) |
| L2 and Notebook: notebook with text and web-page sources, cited answer, briefing, timeline, audio overview; Mentorship list; Warm Network import and AI scores; Outreach; Radar; Call Prep; Proposal; Client Diagnostic; Social posts; Bootcamps | 19 | 19 pass |
| Every logged-in screen in a browser (40 member + 19 admin, phone and desktop) | 118 | **118 clean**: no crashes, errors, failed requests or sideways scroll; median 1.5 s, slowest 3.1 s (Home) |

Speed with real AI (single user): Niche Snapshot 12 s, case scoring 7 s, Meeting Brief 22 s, LinkedIn review 77 s,
30-day plan 104 s, deck 20 s, Listen 49 s, website build 23 s, Insight Pack 30 s, Proposal 23 s, notebook audio 64 s.

## 2. Quality of the real AI output (read by hand)

- **LinkedIn Profile Review** read the phone screenshots exactly. It quoted the headline, spotted the
  "#OpenToWork – Operations Head roles" badge and wrote as the ideal client: "he is a job seeker, not someone who will fix
  my vendor costs". It gave five niche headlines, a full About rewrite, and correct quick wins (remove the badge first).
- **30-day plan:** 30 dated posts from tomorrow, with four pillars built on the niche (the price-down squeeze, buying
  smarter, plant-floor proof, working with me).
- **Niche Snapshot:** "Vendor cost reduction for Tier-2 auto component makers", with a sharp value proposition.
- **Case scoring:** 5.2/10 with specific feedback. **Doc Reader:** the right answer with citations. **Proposal:** six
  phases and three follow-ups. **Insight Pack:** six real news articles.

## 3. Defects and gaps

| # | What | Severity | Status |
|---|---|---|---|
| 1 | **Voice-note stories and Pitch video scorecard don't finish on production.** Twice each, the Gemini call didn't answer in time: 150 s for the voice note, over 200 s for the pitch video. The member sees "We couldn't…, this didn't use up your go". Gemini itself works: Listen mode and notebook audio use Gemini speech. | High | Needs the Railway log lines (section 5) to fix the real cause |
| 2 | **Meeting Brief "news" was three topic pages** ("Tata Motors Latest News – Top News on Tata Motors", zeebiz `/topics/`, businesstoday `/infopage/`, business-standard `/topic/`), not articles. | Medium | **Fixed in code** (`840ea2d`): index pages are dropped, the search is told to pick single dated stories, and the brief searches "*company* India news *Month YYYY*". Waits for a merge and deploy. |
| 3 | **Akshat AI's knowledge base is empty** on production. Every question is sent to the team ("I couldn't find this in Akshat's sessions yet"), and none is answered by the AI. | Medium (content) | Upload Akshat's session material in Admin › Knowledge base |
| 4 | Opportunity Radar found 0 companies on one run (2 searches) and 1 on another (4 searches). | Low | Plausible, since Radar only keeps companies with a clear signal for the niche. The search logs will confirm. |

Not defects:
- The login-code limit (5 codes an hour per number) also applies to test numbers. That's correct: it stops anyone guessing
  the fixed code.
- Call Prep without `search: true` makes no search. The page sends it by default.

## 4. Not tested (by choice)

- **Real payments:** checkout would create real Razorpay subscriptions.
- **Anything sent to real people:** WhatsApp alerts were confirmed off before testing, and outreach messages are drafted
  only.
- **Load on production:** see `QA_RUN_2026-11-05.md` for the load test.

## 5. To finish defect 1

In Railway, open the app service → Deploy Logs, and search for these two lines from 9 November, 06:58–07:16 UTC:
- `voice note transcription failed`
- `pitch video failed`

Each line names Gemini's own reason: for example `HTTP 503 … high demand`, `ReadTimeout`, or a model or quota error.

## 6. Test data left on production

Everything is on the two test accounts (`+91 99999 00001`, `+91 99999 00002`):
- briefs, reviews, a deck, visuals, a notebook, contacts, drafts;
- an unpublished website;
- one closed support ticket marked "QA test";
- one queued Akshat AI question ("How should I price my first consulting project?") in Admin › Akshat AI questions,
  which can be dismissed.

Remove `OTP_TEST_NUMBERS`, and `+919999900002` from `ADMIN_PHONES`, when testing is finished.
