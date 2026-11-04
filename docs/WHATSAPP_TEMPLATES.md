# WhatsApp templates (AiSensy → Meta)

The same list, with copy buttons and a "Send me a test" button, is in the app: Admin › WhatsApp templates.

## Steps

1. In AiSensy, create each template below: same name, category and language, body and button exactly as shown. Use the sample values when Meta asks for examples.
2. When Meta approves a template, create an API campaign in AiSensy on it, named exactly as the 'API campaign' column. The app sends to that name.
3. Press 'Send me a test' next to each one: it goes to your own admin mobile number. When the tests arrive, turn on Admin › Switches › Alerts on WhatsApp.
4. A message type with no live campaign is simply skipped on WhatsApp; the member still gets it in the app's inbox.

All templates: language English (en). Meta may move a Utility template to Marketing (higher price); if it does, reword the fixed lines to sound like an account update, not a promotion.

## hub_login_code

- **When it's sent:** Every login code sent on WhatsApp (needs Admin › Switches › WhatsApp OTP on).
- **Category:** AUTHENTICATION
- **API campaign name in AiSensy:** `otp`

- **Body:** Meta writes this one: "{{1}} is your verification code." Tick "Add security recommendation" and set the code to expire in 10 minutes.
- **Button:** Copy code
- **Sample code:** 482913
- Authentication templates can't be edited. Choose the Copy code button.

## hub_weekly_case

- **When it's sent:** Every Monday morning, when the new weekly case is published (₹1,999 plan and up).
- **Category:** UTILITY
- **API campaign name in AiSensy:** `alert_weekly_case`

**Body**

```
A new practice case is ready for you.

{{1}}

Tap the button to open it in Consultation Hub.
```

- **Button:** URL button, text `Open in Consultation Hub`, dynamic URL `https://<your app address>/{{1}}`
- **Sample for body {{1}}:** This week's case is ready — Growing fast, earning less: a Pune food company's sales are up 30% but profit fell. Solve it and get your score.
- **Sample for button {{1}}:** `app/cases`

## hub_call_reminder

- **When it's sent:** 24 hours and 1 hour before a group call or event the member can join.
- **Category:** UTILITY
- **API campaign name in AiSensy:** `alert_call`

**Body**

```
Reminder about your group call.

{{1}}

Tap the button to open it in Consultation Hub.
```

- **Button:** URL button, text `Open in Consultation Hub`, dynamic URL `https://<your app address>/{{1}}`
- **Sample for body {{1}}:** Group call with Akshat tomorrow at 7:00 pm — Pricing your first project. The joining link is on the Calls page.
- **Sample for button {{1}}:** `app/calls`

## hub_session_recap

- **When it's sent:** When the team publishes a session recap.
- **Category:** UTILITY
- **API campaign name in AiSensy:** `alert_recap`

**Body**

```
Your session recap is ready.

{{1}}

Tap the button to open it in Consultation Hub.
```

- **Button:** URL button, text `Open in Consultation Hub`, dynamic URL `https://<your app address>/{{1}}`
- **Sample for body {{1}}:** Session recap: Bootcamp Day 1 — the summary, your action list and the audio are ready.
- **Sample for button {{1}}:** `app/recaps`

## hub_bootcamp_review

- **When it's sent:** When the team reviews a member's bootcamp task (L2).
- **Category:** UTILITY
- **API campaign name in AiSensy:** `alert_bootcamp`

**Body**

```
An update on your bootcamp task.

{{1}}

Tap the button to open it in Consultation Hub.
```

- **Button:** URL button, text `Open in Consultation Hub`, dynamic URL `https://<your app address>/{{1}}`
- **Sample for body {{1}}:** The team reviewed your bootcamp task — Build your offer: two changes suggested before you share it.
- **Sample for button {{1}}:** `app/bootcamps`

## hub_support_reply

- **When it's sent:** When the support team replies to a member's question.
- **Category:** UTILITY
- **API campaign name in AiSensy:** `alert_support`

**Body**

```
The support team has replied to you.

{{1}}

Tap the button to open it in Consultation Hub.
```

- **Button:** URL button, text `Open in Consultation Hub`, dynamic URL `https://<your app address>/{{1}}`
- **Sample for body {{1}}:** The team replied: Can't find my workbook — It's in Recordings and workbooks under Day 2.
- **Sample for button {{1}}:** `app/support`

## hub_akshat_answer

- **When it's sent:** When the team answers a question Akshat AI sent to them (L1).
- **Category:** UTILITY
- **API campaign name in AiSensy:** `alert_akshat_ai`

**Body**

```
Your question has an answer.

{{1}}

Tap the button to open it in Consultation Hub.
```

- **Button:** URL button, text `Open in Consultation Hub`, dynamic URL `https://<your app address>/{{1}}`
- **Sample for body {{1}}:** Akshat answered your question — How do I price my first project?
- **Sample for button {{1}}:** `app/akshat-ai`

## hub_progress_ready

- **When it's sent:** On the 1st of each month: the Progress Report is ready to make.
- **Category:** UTILITY
- **API campaign name in AiSensy:** `alert_progress`

**Body**

```
Your monthly update is ready.

{{1}}

Tap the button to open it in Consultation Hub.
```

- **Button:** URL button, text `Open in Consultation Hub`, dynamic URL `https://<your app address>/{{1}}`
- **Sample for body {{1}}:** Your Progress Report is ready to make — see how far you came in the last 30 days.
- **Sample for button {{1}}:** `app/progress`

## hub_proposal_followup

- **When it's sent:** On the day a proposal follow-up is due (L2).
- **Category:** UTILITY
- **API campaign name in AiSensy:** `alert_proposal`

**Body**

```
A follow-up is due today.

{{1}}

Tap the button to open it in Consultation Hub.
```

- **Button:** URL button, text `Open in Consultation Hub`, dynamic URL `https://<your app address>/{{1}}`
- **Sample for body {{1}}:** Follow up with Rakesh Shah today — proposal for Shreeji Foods, follow-up 2 of 3. Your message is drafted.
- **Sample for button {{1}}:** `app/proposals`

## hub_diagnostic_answer

- **When it's sent:** When a prospect fills in the member's Client Diagnostic link (L2).
- **Category:** UTILITY
- **API campaign name in AiSensy:** `alert_diagnostic`

**Body**

```
You have a new diagnostic answer.

{{1}}

Tap the button to open it in Consultation Hub.
```

- **Button:** URL button, text `Open in Consultation Hub`, dynamic URL `https://<your app address>/{{1}}`
- **Sample for body {{1}}:** New diagnostic answer from Neha Mehta — score 42 of 100, her report is ready.
- **Sample for button {{1}}:** `app/diagnostic`

## hub_website_lead

- **When it's sent:** When someone sends a message through the member's website (at most one WhatsApp a site per hour; all messages are in the inbox).
- **Category:** UTILITY
- **API campaign name in AiSensy:** `alert_site_lead`

**Body**

```
Someone wrote to you through your website.

{{1}}

Tap the button to open it in Consultation Hub.
```

- **Button:** URL button, text `Open in Consultation Hub`, dynamic URL `https://<your app address>/{{1}}`
- **Sample for body {{1}}:** New message from your website — Amit Shah, Head of Operations, asked about a cost review.
- **Sample for button {{1}}:** `app/website`

## Not needed yet

The app doesn't send these message types on WhatsApp today: group_session, l2, billing, system.
