# Consultation Hub: A to Z

What the app is, what's inside it, how it works, how it was built and tested, and what's left before launch.

Written for Harsh, the team and the developer. Plain words; the technical detail is in the other docs listed at the end.

Last updated: 4 November 2026.

---

## 1. What it is

The software for Akshat Dani's High Value Consulting funnel. Logo: AD × SK.

It's a new app, separate from the current hub (consultant.akshatdani.com). Nothing in the current hub changes.

Members open it on their phone or computer. They log in with their mobile number and a one-time code. There are no passwords.

---

## 2. The four levels

**Free account (webinar)**
- Made when someone scans the QR code on the ₹99 webinar.
- Each webinar tool once. After that, they can see what they made but not make more.
- No free trial of the paid plans.

**₹1,999 plan**
- ₹1,999 + GST a month (₹2,359 charged), or ₹20,000 + GST a year (₹23,600 charged).

**L1**
- ₹5,000 + GST a month (₹5,900 charged), with Akshat's 4-3-2-1 action program inside.

**L2 Mentorship**
- ₹1.5L, sold by the team, switched on by the team in Admin.
- Runs 6 months.
- While L2 runs, L1 billing is paused. L1 restarts by itself when L2 ends.

Each level includes everything in the levels below it.

---

## 3. What each level gets

Free counts are once for life. Paid counts are per month and reset on the 1st (Indian time).

### Free (webinar tools)

- **Readiness Score:** rate yourself on six consultant skills, get a score out of 60.
- **Starting Point:** Niche Snapshot (AI suggests your niche) and Goal Map (how many clients you need for your income goal).
- **Case:** solve a real business case and get a score with a model answer.
- **Meeting Brief:** type a company and get its recent news with real links, likely problems, questions to ask and an opening line.
- **LinkedIn Score:** score your profile out of 100.
- **My Consulting File:** everything you've made, on one page.

### ₹1,999 plan adds

- **Weekly Case:** a new case every Monday from real Indian business news (up to 8 cases a month).
- **LinkedIn rewrites:** AI rewrites of your headline and About section.
- **Presentation Builder:** turn a case, a brief or your notes into a deck. Download it as PowerPoint or PDF, or present it from the app. 2 decks a month.
- **Visual Builder:** frameworks, processes and charts as images. 10 a month.
- **Website Builder:** a consulting website written from your niche; 1 page on this plan. Edit it, publish it, get messages from visitors.
- **Listen mode:** hear the weekly case and your briefs as audio. 5 a month.
- **Doc Reader:** upload up to 5 documents and ask questions about them. 60 questions a month.
- **Progress Report:** your last 30 days compared with the 30 before.
- **Support:** write to the team inside the app; they answer from the admin panel.

### L1 adds

- **4-3-2-1 action program:** Akshat's program step by step, with what's done.
- **Group calls with Akshat:** times, links and reminders. Group calls only; there are no one-to-one calls.
- **Recordings and workbooks.**
- **Session Recap Pack:** after each session, a summary, actions and audio.
- **Action Hub:** Akshat's 18 tools as guided chats, starting with Define Your Niche. 300 messages a month.
- **Akshat AI:** answers only from Akshat's own sessions. If it doesn't know, the question goes to the team. 30 questions a month.
- **Offer Card:** your offer on one card. 10 a month.
- **Career Story Bank:** tell one story a week, by voice or typing, and get back a proof story, a pitch line and a LinkedIn post. 6 a month.
- **Industry Insight Pack:** news and trends on your industry to share with clients. 2 a month.
- **Portfolio Project:** a worked practice project to show clients how you think. 2 a month.
- **Pitch Practice:** upload a pitch video and get a scorecard. It follows the Leadership Hub's Confidence Coach:
  - up to 8 minutes and 100 MB
  - a 7-metric scorecard, and a comparison with your last take
  - 30 minutes between takes
  - the video is deleted straight after analysis
  - 4 analysed takes a month, plus 150 coach questions and 20 new practices
- **Research Notebook:** collect sources on a topic (up to 4 projects) and ask questions across them.
- Bigger limits on the ₹1,999 tools: 20 documents, 6 decks, 30 visuals, 5 website pages and your own domain.

### L2 adds

- **Mentorship tools:** 34 more of Akshat's tools, starting with Book Builder, Credibility Code and Document Builder. 600 messages a month.
- **Warm Network Finder:** upload your LinkedIn connections and see who's most likely to help.
- **Outreach Drafter:** messages to those people, in your voice. 100 a month.
- **Opportunity Radar:** news about companies that may need you now. 10 a month.
- **Discovery Call Prep:** what to ask and say on a first call. 20 a month.
- **Proposal Follow-through:** write the proposal, then get reminded to follow up. 20 a month.
- **Client Diagnostic:** a short questionnaire you send to a prospect. They fill it from a link without logging in, and you get their report. 20 a month.
- **Social Media Builder:** a month of posts. 30 a month.
- **Bootcamps:** tasks the team reviews.

All limits are in one place in the code (`backend/plans.py`) and can be changed. They're the spec's proposed numbers.

---

## 4. How money works (Razorpay)

**Buying**
- Every paid plan is a Razorpay subscription that renews by itself (UPI AutoPay or card).
- GST at 18% is added. The member sees the price with GST before paying.

**Moving up** (e.g. ₹1,999 → L1)
- The new plan starts now. The old one stops renewing.

**Moving down or switching** (the ₹1,999 offer after cancelling L1, or monthly ↔ yearly)
- The new plan starts when the current paid period ends, so nobody pays twice for the same days.

**Cancelling**
- The plan runs to the end of the paid period, then stops.
- When someone cancels L1, they're offered the ₹1,999 plan, once per person.

**L2**
- The team presses "Start L2" in Admin › Members.
- L1 billing is paused for 6 months and restarts by itself afterwards (checked every hour).
- If Razorpay refuses to pause, L1 is cancelled at the end of its month and the member is asked to restart L1 after L2.
- A member on L2 can also cancel their paused L1 so it never restarts.

**Safety checks**
- A payment can only be used once.
- Repeated or out-of-order messages from Razorpay are ignored.
- Revoking an account stops its billing.

---

## 5. Logging in

- Mobile number → a 6-digit code on WhatsApp (when switched on) or SMS. The code lasts 10 minutes.
- Limits so nobody can run up the SMS bill:
  - a few codes per number
  - 1,000 per network address an hour
  - 1,200 a minute across the whole app (enough for a 500-person QR rush)
- The team logs in the same way. Their mobile numbers are listed in the settings, which makes them admin.

---

## 6. How the AI works

- **Text:** every text tool uses Anthropic. A fast model handles quick tools; a stronger one handles decks, proposals and chats.
- **Web search:** uses Anthropic's own search, on the same account. Links shown to members only ever come from real search results; the AI can't make up a link. News for the same search is kept for 6 hours.
- **Audio** (read aloud, voice notes): uses Google Gemini, because Anthropic's API can't make or hear audio.
- **Pitch videos:** use Google Gemini.
- **Decks:** made by the app itself. The AI writes the slide text, and the app lays it out in Akshat's design and draws the PowerPoint and PDF. No outside deck service.
- **What the AI knows about the member:** their niche, audience, value proposition, goal and Niche Blueprint, from the webinar tools. Every tool uses this, so answers fit their niche.
- **Akshat's 52 original prompts** (18 Action Hub, 34 Mentorship) run as guided chats, kept as close to the originals as possible.
- **Never naming the AI companies:** every prompt says so, and replies are filtered too. Members only ever see "AI".
- **When the AI fails or is busy:** the member sees "try again", and the go is given back. The page also retries once by itself.

---

## 7. Outside services and what they cost

| Service | Used for | Cost notes |
|---|---|---|
| Razorpay | Payments | Razorpay's usual fees |
| MSG91 | SMS login codes | Per SMS; needs a DLT-approved template |
| AiSensy | WhatsApp login codes and messages | AiSensy plan + Meta's per-message charges |
| Anthropic | All AI text and web search | Per use. Web search is $10 per 1,000 searches plus the AI text cost |
| Google Gemini | Pitch videos and audio | About $0.14 per 10 minutes of audio made and $0.02 per 10 minutes of voice transcribed (estimate from Google's price page, Nov 2026; due to double from Jan 2027) |

Not used any more: Gamma (decks are our own now), Tavily (search is on Anthropic now) and OpenAI (audio is on Gemini now).

Estimated search cost per use (vendor price × searches per tool):
- Meeting Brief: about $0.01–0.02
- Insight Pack: about $0.03–0.06
- Radar run: about $0.05–0.10

Real AI costs per member aren't measured yet. Track them in the vendor dashboards in the first month.

---

## 8. The admin panel (`/admin`)

**Overview**
- **Pulse:** sign-ups, payments and activity at a glance.
- **Live now:** who's using it in the last 15 minutes (for the webinar).
- **Webinar:** how many used each webinar tool, plus the group-session list as CSV.

**People**
- **Members:** find a member; give a plan, start L2, revoke.
- **Support inbox:** answer members' questions.
- **Akshat AI questions:** questions Akshat AI couldn't answer, for the team to answer.

**Program**
- **4-3-2-1 program:** cohorts and their steps.
- **Calls and events:** add call times and links; reminders go out by themselves.
- **Session recaps:** upload a transcript; members get the recap pack, and Akshat AI learns from it.
- **Recordings and workbooks.**
- **Bootcamps:** add bootcamps and review tasks.

**Content**
- **Live case & group session:** pick the webinar's live case and the group-session time.
- **Weekly case:** see or remake this week's case.
- **Knowledge base:** Akshat's material that Akshat AI answers from.
- **Website domains:** members' own domains to connect.

**Control**
- **Switches:** turn things on or off (WhatsApp codes, WhatsApp alerts, webinar tools and more).
- **Vendors:** which outside services are live.
- **WhatsApp templates:** the exact wording to get approved, with a "Send me a test" button.
- **Jobs:** the scheduled tasks, their last run, and "Run now".

---

## 9. Messages to members

- Every message goes to the in-app inbox (the bell icon). That always works.
- The same message can also go on WhatsApp once the templates are approved and "Alerts on WhatsApp" is on.
- No WhatsApp between 10 pm and 8 am. Those messages stay in the inbox only.
- 10 message types plus the login code:
  - new weekly case
  - call reminder
  - session recap
  - bootcamp review
  - support reply
  - Akshat AI answer
  - progress report ready
  - proposal follow-up
  - diagnostic answer
  - website message
- The wording for each is in Admin › WhatsApp templates and `docs/WHATSAPP_TEMPLATES.md`.

---

## 10. Things the app does by itself (scheduled jobs)

- **Monday 6:30 am:** publishes the weekly case from the week's news. If that fails, it tries again at 10:30 am every day until there is one.
- **Every 30 minutes:** call reminders, 24 hours and 1 hour before.
- **9:00 am on the 1st:** "your Progress Report is ready."
- **9:30 am daily:** proposal follow-up reminders.
- **Every hour:** restarts L1 after L2 ends, and retries any failed cancels.
- **4:20 am daily:** frees a website domain 30 days after the plan stopped including it.
- A failed job is retried every 15 minutes, up to 4 times. Admin › Jobs shows every run.

---

## 11. How it's built (for the developer)

**Pieces**
- **Backend:** Python (FastAPI) with a MongoDB database. One file per tool in `backend/features/`.
- **Frontend:** React, in Akshat's design system: dark only, gold for the key thing, teal only for AI, red only for errors, Manrope font.
- **One Docker image** on Railway serves both. Health check `/api/health`.

**Folders**
- `backend/plans.py`: plans, limits, caps.
- `backend/billing/`: Razorpay and L2.
- `backend/features/`: the tools.
- `backend/gpts/`: Akshat's 52 prompts.
- `backend/notify/`: inbox, WhatsApp, templates.
- `frontend/src/app/pages/`: the screens.
- `frontend/src/app/admin/`: the admin panel.
- `scripts/`: the local test server and the load test.
- `docs/`: these documents.

**Settings**
- Every setting is in `backend/.env.example`, with a note on each.
- Keys go into Railway's settings, never into chat or email.

**Structure** (details in `docs/ARCHITECTURE.md`)
- Each tool splits into router (web requests), service (rules) and repository (database). `features/cases/` is the model; the other tools move to it as they are changed.
- All settings are read in one file (`backend/core/settings.py`). In production the app refuses to start if a setting is unsafe (for example a weak `JWT_SECRET` or test mode left on).
- Every error has a code and a plain message; every request has an id that appears in the logs.
- GitHub runs the tests and the build on every push (`.github/workflows/ci.yml`).

**Test mode**
- `QA_MODE=true` runs the whole app with fake outside services and sample data, so anyone can try every screen without keys.
- It's refused in production.

**Switches**
- Each outside service has a switch: `live`, `fake` (tests only) or `off` (the tool shows "paused").

---

## 12. Safety and privacy

- Members can only see their own things. Every lookup checks the owner.
- Admin pages need an admin login.
- Rate limits use the real client address from Railway's edge, so the browser can't fake it.
- **Public pages** (member websites, the client diagnostic link):
  - show nothing private
  - have size and rate limits
  - the diagnostic's AI never sees the member's income goal
- **Uploads:**
  - documents keep the text only
  - pitch videos are deleted right after analysis
  - voice notes keep the words, not the recording
- **CSV exports** are protected against spreadsheet formula tricks.
- **Website domains:** a member can only ask for one. The team connects it after checking.

---

## 13. How it was built

1. **Spec first:** the product spec for all four levels, from the webinar recordings, chats and the current hub's working document.
2. **Stage 1:** the webinar tools, login, plans and billing, and the admin panel.
3. **Stages 2–4:** the ₹1,999 plan, L1 and L2. Seven builders worked in parallel to one shared build guide (`docs/BUILD_GUIDE.md`), then everything was joined and tested together.
4. **Changes asked for on 4 Nov:**
   - our own deck engine instead of Gamma
   - web search on Anthropic instead of Tavily
   - audio on Gemini instead of OpenAI
   - WhatsApp templates inside the admin panel
5. **Independent review:** three reviewers who hadn't seen the build read all the code and found 52 real defects. All are fixed, each with a test so it can't come back.
6. **Load test:** 10,000 accounts in a real database, then 500 people at once. Problems it found were fixed and the test was run again.

---

## 14. How it was tested (measured)

- **Automated tests:** 362, all pass (`cd backend && pytest`). They cover every tool, billing, L2, public pages, decks, search, audio and messages.
- **Screen walk on a phone and a computer:** every screen and every admin page. No errors and no sideways scrolling.
- **Decks:** the PowerPoint and PDF were compared side by side, and they match.
- **Load test** (details in `docs/LOAD_TEST.md`), with 10,000 accounts in the database:
  - **500 webinar attendees at once:** 56,086 requests, 0 failed. Non-AI screens answered in about 0.05 s. AI answers took a median of 8–19 s, with each AI call set to 6 s.
  - **500 paid members at once:** 18,280 requests, 0 errors. Decks took about 6 s, downloads about 0.01 s.

---

## 15. Not tested yet (be clear about these)

- **Real accounts with every outside service:** Razorpay, MSG91, AiSensy, Anthropic and Gemini. The code follows each one's current docs and is tested against sample replies, but nothing has run with real keys.
- **Razorpay specifics:**
  - pausing for L2
  - plans that start later
  - cancelling a paused plan
- **Real AI speed and the Anthropic rate limit** at a 500-person moment. The load test used 6 seconds per AI call as an estimate.
- **Railway + Atlas performance.** The load test ran on a small test machine.
- **A real 8-minute pitch video** uploaded over a phone network.
- **Members' own website domains** end to end.
- **The PowerPoint in real Microsoft PowerPoint** (it was checked in LibreOffice).

---

## 16. Launch checklist

**Developer**
1. GitHub repo, Railway service (Dockerfile), new MongoDB Atlas database.
2. Domain → Railway; set `PUBLIC_BASE_URL`, `JWT_SECRET`, `ADMIN_PHONES`.
3. Razorpay:
   - keys
   - 3 plans (₹2,359/month, ₹23,600/year, ₹5,900/month)
   - the webhook
4. MSG91 SMS template and AiSensy key. Then the WhatsApp templates from Admin › WhatsApp templates.
5. Anthropic key (check web search is allowed and the rate limits).
6. Gemini key.
7. Optional: `SITES_DOMAIN` for member websites.
8. On staging with real keys: one payment of each kind, one L2 start, one of each AI tool, one pitch video, one deck. Then the load test.
9. Import existing members (CSV with mobile numbers).

**Team, before the first webinar**
1. Admin › Live case & group session: pick the case, add the group session time and link.
2. Admin › Program, Calls and events, Library: add the content, call times and recordings.
3. Admin › Knowledge base: upload Akshat's material for Akshat AI.
4. Put the QR code (`<PUBLIC_BASE_URL>/login?src=webinar`) on the webinar slide.

---

## 17. Where to find things

| Document | What's in it |
|---|---|
| `README.md` | Short overview and how to run it locally |
| `docs/HANDOVER.md` | Step-by-step set-up for the developer |
| `docs/WHATSAPP_TEMPLATES.md` | Every WhatsApp template, ready to submit |
| `docs/QA_REPORT.md` | What was reviewed and tested, and what wasn't |
| `docs/QA_RUN_2026-11-05.md` | Latest full QA and load test (5 Nov): results and launch recommendation |
| `docs/LOAD_TEST.md` | Load test results and how to run it again |
| `docs/ARCHITECTURE.md` | Layers, settings, errors, logging, module registry, quality gates |
| `docs/BACKEND_DESIGN.md` | How the backend works |
| `docs/BUILD_GUIDE.md` | Rules every tool follows (for anyone adding a tool) |
| `docs/API_CONTRACT.md` | Every API route |
| `backend/.env.example` | Every setting |
| `docs/reference/` | The current hub's and the Leadership hub's working documents |
