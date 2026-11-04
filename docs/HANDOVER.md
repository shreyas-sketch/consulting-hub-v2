# Handover

The whole app, A to Z, in plain words: `docs/CONSULTATION_HUB_A_TO_Z.md`.

## What the developer needs to set up

Put every value in Railway settings. Never send keys on chat or email. Full list with notes: `backend/.env.example`.

1. **GitHub repo**: an empty private repo; push this folder to it.

2. **Railway**: one service from the repo (Dockerfile build). Health check `/api/health`.

3. **MongoDB Atlas**: a new database for this app (not the current hub's). Set `MONGO_URL`, `DB_NAME=consultation_hub`.

4. **Domain**: e.g. `app.<domain>` pointed at Railway. Set `PUBLIC_BASE_URL`.

5. **Secrets**: `JWT_SECRET` (long random string).

6. **Team logins**: `ADMIN_PHONES` (team mobile numbers, comma-separated).

7. **OTP**
   - MSG91: `MSG91_AUTH_KEY`, `MSG91_OTP_TEMPLATE_ID` (DLT-approved OTP template)
   - AiSensy: `AISENSY_API_KEY`, an approved Authentication template on campaign `otp`
   - Turn WhatsApp OTP on in Admin › Switches once AiSensy works

8. **Razorpay**
   - `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`
   - Create 3 plans in the dashboard, prices including GST:
     - ₹2,359 a month → `RAZORPAY_PLAN_MEMBER_MONTHLY`
     - ₹23,600 a year → `RAZORPAY_PLAN_MEMBER_YEARLY`
     - ₹5,900 a month → `RAZORPAY_PLAN_L1_MONTHLY`
   - Webhook to `<PUBLIC_BASE_URL>/api/billing/razorpay/webhook` with events subscription.authenticated, activated, charged, paused, resumed, cancelled, halted, completed → `RAZORPAY_WEBHOOK_SECRET`
   - Check with Razorpay that subscriptions can be **paused** for UPI AutoPay and cards (L1 pauses during L2). If a pause is refused, the app cancels L1 at the end of its month and asks the member to restart L1 after L2. It still works, but pause is smoother.

9. **Anthropic** (every text tool, and web search): `ANTHROPIC_API_KEY`.
   - Web search and page reading run on the same key (Anthropic's server-side web search and web fetch tools). No
     separate search vendor. Web search costs $10 per 1,000 searches plus tokens. Check it is not switched off for
     the organisation in the Anthropic Console.
   - Check the account's rate limits (Console › Limits). Each AI call takes about 6 seconds, so
     workers × `LLM_MAX_CONCURRENCY` × 10 ≈ requests a minute at a busy moment. Keep that under the limit.

10. **Google Gemini** (Pitch Practice video, and all audio: Listen mode, recaps and packs read aloud, Story Bank voice
    notes): `GEMINI_API_KEY`. Anthropic's API can't make or hear audio, so audio uses the same Gemini key as video.
    - Video `gemini-3.8-flash` (`GEMINI_MODEL`)
    - Text to speech `gemini-3.8-flash-tts` (`GEMINI_TTS_MODEL`), voice `Iapetus` (`GEMINI_TTS_VOICE`)
    - Speech to text `gemini-3.8-flash` (`GEMINI_STT_MODEL`)
    - Gemini prices are set to double from 1 Jan 2027 (per Google's pricing page in Nov 2026). Check before budgeting.

11. **Presentation Builder**: nothing to set. Decks are made by the app itself (PowerPoint and PDF, Akshat's design).

12. **Member websites**
    - Without anything extra, sites open at `<PUBLIC_BASE_URL>/s/<name>`.
    - For `<name>.sites.<domain>`: add a wildcard DNS record `*.sites.<domain>` to Railway, add the wildcard domain in Railway, and set `SITES_DOMAIN=sites.<domain>`.
    - Own domains (L1 and L2): the member asks for one in the Website Builder and points a CNAME to the app's address. Nothing shows on it until the team connects it: Admin › Website domains › Check record, add the domain in Railway (so it gets a certificate), then Connect.

13. **WhatsApp messages** (optional; the in-app inbox always works)
    - The exact template wording, sample values and campaign names are in Admin › WhatsApp templates (also `docs/WHATSAPP_TEMPLATES.md`): 1 login-code template + 10 message templates.
    - Submit each in AiSensy, then create an API campaign with the name shown. Use "Send me a test" on that page, then turn on Admin › Switches › Alerts on WhatsApp.

14. **Existing members**: a CSV export from the current hub (name, mobile, email, programme) so L1/L2 members can be given their plan on day one. Mobile numbers are needed: this app logs in by OTP, not email + password.

## Before the first live webinar

- Admin › Live case & group session: pick the live case, add the group session time and Zoom link.
- Admin › Program, Calls and events, Library: add the 4-3-2-1 content, the call times and the recordings.
- Admin › Knowledge base: upload Akshat's material for Akshat AI.
- Run the load test once more on staging (Railway + Atlas) with real AI keys, smaller first (`docs/LOAD_TEST.md`).
- Try each vendor once on staging with a real account (see "Not tested yet" in `QA_REPORT.md`).
- Put a QR code to `<PUBLIC_BASE_URL>/login?src=webinar` on the webinar slide.

## Scheduled jobs (run inside the app; see Admin › Jobs)

A failed run is retried every 15 minutes, up to 4 times.

- `weekly_case`: Monday 06:30 IST, a new case from the week's news
- `weekly_case_retry`: daily 10:30 IST, only if this week has no case yet
- `progress_nudge`: 1st of each month, tells members their Progress Report is ready
- `call_reminders`: every 30 minutes, reminds members 24 h and 1 h before group calls and events
- `proposal_followups`: daily 09:30 IST, follow-up reminders for sent proposals (L2)
- `l2_resume`: hourly, restarts L1 after L2 ends and retries any failed cancels
- `site_domains_release`: daily 04:20 IST, frees an own domain 30 days after the plan stops including it

## Decisions taken (all can be changed)

- Free accounts: each tool once, then view-only (Admin › Switches › Webinar tools).
- Monthly limits: the spec's proposed numbers (`backend/plans.py`, `LIMITS`).
- Support: members write in the app; the team answers from Admin › Support inbox.
- Pitch Practice follows the Leadership hub's Confidence Coach: video up to 8 minutes and 100 MB, 7-metric scorecard, a comparison on the next take, 30-minute wait between takes. The video is deleted right after analysis.
- No screen, reply or PDF names the AI providers.
