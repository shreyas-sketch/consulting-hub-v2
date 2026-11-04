# Handover — stage 1

## What the developer needs to set up

Put every value in Railway settings. Never send keys on chat or email.

1. **GitHub repo** — an empty private repo; push this folder to it.

2. **Railway** — one service from the repo (Dockerfile build). Health check `/api/health`.

3. **MongoDB Atlas** — a new database for this app (not the current hub's). Set `MONGO_URL`, `DB_NAME=consultation_hub`.

4. **Domain** — e.g. `app.<domain>` pointed at Railway. Set `PUBLIC_BASE_URL`.

5. **Secrets** — `JWT_SECRET` (long random string).

6. **Team logins** — `ADMIN_PHONES` (team mobile numbers, comma-separated).

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
   - Webhook to `<PUBLIC_BASE_URL>/api/billing/razorpay/webhook` with events subscription.activated, charged, paused, resumed, cancelled, halted, completed → `RAZORPAY_WEBHOOK_SECRET`
   - Check with Razorpay that subscriptions can be **paused** for UPI AutoPay and cards (L1 pauses during L2). If a pause is refused, the app cancels L1 at the end of its month and asks the member to restart L1 after L2 — it still works, but pause is smoother.

9. **Anthropic** — `ANTHROPIC_API_KEY`. Check the account's rate limit; `LLM_MAX_CONCURRENCY` × workers must stay under it.

10. **Tavily** (web search for Meeting Brief news) — `SEARCH_API_KEY`.

11. **Existing members** — a CSV export from the current hub (name, mobile, email, programme) so L1/L2 members can be given their plan on day one. Mobile numbers are needed: this app logs in by OTP, not email + password.

## Before the first live webinar

- Admin › Live case & group session: pick the live case, add the group session time and Zoom link.
- Run the load test on staging with a real database (`docs/LOAD_TEST.md`).
- Put a QR code to `<PUBLIC_BASE_URL>/login?src=webinar` on the webinar slide.

## Decisions still open (defaults built in)

- Free accounts: each tool once, then view-only (switch: Admin › Switches › Webinar tools).
- Monthly limits as in the spec (marked "proposed" there).
- Who answers support: set the WhatsApp number in Admin.

## What's next

- Stage 2: rest of the ₹1,999 plan (weekly case from real news, Presentation Builder, Visual Builder, Website Builder from Owner Desk, Listen mode, Doc Reader, Progress Report)
- Stage 3: L1 (Action Hub tools from `backend/gpts/`, Akshat AI, Pitch Practice, Research Notebook, recaps, calls)
- Stage 4: L2 tools (from `backend/gpts/` mentorship prompts + the seven client-getting agents)
