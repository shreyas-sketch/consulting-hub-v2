"""WhatsApp templates the developer submits to Meta through AiSensy (one per message kind), in one place.

The app sends every alert the same way (notify/channels.py): body variable {{1}} = "<title> — <text>", and a URL
button whose {{1}} is the page path (e.g. "app/calls"). So every alert template has the same shape; only the name,
the fixed words and the sample change. The login code uses Meta's fixed Authentication template.

Shown in Admin › WhatsApp templates (GET /api/admin/whatsapp-templates) and in docs/WHATSAPP_TEMPLATES.md.
Meta's rules followed: the body doesn't start or end with a variable, has more fixed words than variables, no
emojis, no newlines inside a variable (channels._one_line strips them).
"""
from __future__ import annotations

import os

from notify.channels import campaign_for

BRAND = lambda: os.environ.get("BRAND_NAME", "Consultation Hub")  # noqa: E731

# kind → (template name, when it's sent, the fixed opening words, sample {{1}}, sample button path, category)
ALERTS: list[tuple[str, str, str, str, str, str, str]] = [
    ("weekly_case", "hub_weekly_case", "Every Monday morning, when the new weekly case is published (₹1,999 plan and up).",
     "A new practice case is ready for you", "This week's case is ready — Growing fast, earning less: a Pune food "
     "company's sales are up 30% but profit fell. Solve it and get your score.", "app/cases", "UTILITY"),
    ("call", "hub_call_reminder", "24 hours and 1 hour before a group call or event the member can join.",
     "Reminder about your group call", "Group call with Akshat tomorrow at 7:00 pm — Pricing your first project. "
     "The joining link is on the Calls page.", "app/calls", "UTILITY"),
    ("recap", "hub_session_recap", "When the team publishes a session recap.",
     "Your session recap is ready", "Session recap: Bootcamp Day 1 — the summary, your action list and the audio "
     "are ready.", "app/recaps", "UTILITY"),
    ("bootcamp", "hub_bootcamp_review", "When the team reviews a member's bootcamp task (L2).",
     "An update on your bootcamp task", "The team reviewed your bootcamp task — Build your offer: two changes "
     "suggested before you share it.", "app/bootcamps", "UTILITY"),
    ("support", "hub_support_reply", "When the support team replies to a member's question.",
     "The support team has replied to you", "The team replied: Can't find my workbook — It's in Recordings and "
     "workbooks under Day 2.", "app/support", "UTILITY"),
    ("akshat_ai", "hub_akshat_answer", "When the team answers a question Akshat AI sent to them (L1).",
     "Your question has an answer", "Akshat answered your question — How do I price my first project?",
     "app/akshat-ai", "UTILITY"),
    ("progress", "hub_progress_ready", "On the 1st of each month: the Progress Report is ready to make.",
     "Your monthly update is ready", "Your Progress Report is ready to make — see how far you came in the last "
     "30 days.", "app/progress", "UTILITY"),
    ("proposal", "hub_proposal_followup", "On the day a proposal follow-up is due (L2).",
     "A follow-up is due today", "Follow up with Rakesh Shah today — proposal for Shreeji Foods, follow-up 2 of 3. "
     "Your message is drafted.", "app/proposals", "UTILITY"),
    ("diagnostic", "hub_diagnostic_answer", "When a prospect fills in the member's Client Diagnostic link (L2).",
     "You have a new diagnostic answer", "New diagnostic answer from Neha Mehta — score 42 of 100, her report "
     "is ready.", "app/diagnostic", "UTILITY"),
    ("site_lead", "hub_website_lead", "When someone sends a message through the member's website (at most one "
     "WhatsApp a site per hour; all messages are in the inbox).",
     "Someone wrote to you through your website", "New message from your website — Amit Shah, Head of Operations, "
     "asked about a cost review.", "app/website", "UTILITY"),
]


def _body(opening: str) -> str:
    return f"{opening}.\n\n{{{{1}}}}\n\nTap the button to open it in {BRAND()}."


def catalogue(base_url: str = "") -> dict:
    base = (base_url or os.environ.get("PUBLIC_BASE_URL") or "https://<your app address>").rstrip("/")
    items = [{
        "kind": "otp", "template": "hub_login_code", "campaign": os.environ.get("AISENSY_OTP_CAMPAIGN", "otp"),
        "category": "AUTHENTICATION", "language": "English (en)",
        "when": "Every login code sent on WhatsApp (needs Admin › Switches › WhatsApp OTP on).",
        "body": "Meta writes this one: \"{{1}} is your verification code.\" Tick \"Add security recommendation\" and "
                "set the code to expire in 10 minutes.",
        "button": "Copy code", "button_url": "", "sample": "482913", "sample_path": "",
        "notes": "Authentication templates can't be edited. Choose the Copy code button.",
    }]
    for kind, template, when, opening, sample, path, category in ALERTS:
        items.append({
            "kind": kind, "template": template, "campaign": campaign_for(kind), "category": category,
            "language": "English (en)", "when": when, "body": _body(opening),
            "button": f"Open in {BRAND()}"[:25], "button_url": f"{base}/{{{{1}}}}",
            "sample": sample, "sample_path": path,
            "notes": "Body variable {{1}} = title and text of the message. Button URL is dynamic: its {{1}} is the page.",
        })
    return {
        "items": items,
        "steps": [
            "In AiSensy, create each template below: same name, category and language, body and button exactly as "
            "shown. Use the sample values when Meta asks for examples.",
            "When Meta approves a template, create an API campaign in AiSensy on it, named exactly as the "
            "'API campaign' column. The app sends to that name.",
            "Press 'Send me a test' next to each one: it goes to your own admin mobile number. When the tests "
            "arrive, turn on Admin › Switches › Alerts on WhatsApp.",
            "A message type with no live campaign is simply skipped on WhatsApp; the member still gets it in the "
            "app's inbox.",
        ],
        "not_sent_yet": ["group_session", "l2", "billing", "system"],
    }
