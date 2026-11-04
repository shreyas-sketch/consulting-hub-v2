# Backend design

Short notes for the developer. Code comments carry the detail.

## Plans (`plans.py`)

- Four levels: `free` → `member` (₹1,999) → `l1` → `l2`. Higher includes lower.
- Effective plan = the highest of: a live paid subscription, an admin grant, team role (= l2). No trial.
- Usage is counted with one atomic database write, so two clicks at once can't get two goes.
- `require()` → 403 locked. `consume()` → 402 limit. `features/common.run_metered()` gives the use back if the work fails.
- Free accounts count once for life (`usage` doc `<uid>:life`); paid plans count per IST month (`<uid>:YYYY-MM`).

## Billing (`billing/`)

- Razorpay Subscriptions. `subscriptions` stores plan + period (monthly/yearly).
- Upgrading starts a new subscription and stops the old one renewing. Moving down (the ₹1,999 offer) or switching
  monthly/yearly starts the new plan when the paid period ends (Razorpay `start_at`), so nobody pays twice.
- `/billing/verify` only confirms a subscription that is still new and refuses a reused payment.
- Webhooks are de-duplicated by event id and ignored when older than the last one applied.
- Cancelling L1 offers the ₹1,999 plan once per account (`users.downsell_offered_at`).
- L2 (`billing/l2.py`): admin "Start L2" → 183-day L2 grant, L1 paused (`paused_for_l2`, `resume_at`). Hourly job `l2_resume` restarts it. If Razorpay refuses the pause, L1 is cancelled at the end of its month and the member restarts L1 in the app.

## Webinar tools (`features/`)

| Tool | AI? | Follows the current hub's GPT |
|---|---|---|
| Readiness Score | No (rules) | — six skills from Akshat's sessions |
| Niche Snapshot | Yes (fast model) | Define Your Niche |
| Goal Map | No (arithmetic) | — |
| Cases | Yes (fast model) | Strategy Thinking Framework (six steps) |
| Meeting Brief | Web search + AI | — |
| LinkedIn Score | Score: no. Rewrites: yes (paid) | LinkedIn Optimizer |
| My Consulting File | No | Knowledge Base (5 fields) + Niche Blueprint |

`features/knowledge.py` turns the chosen niche + goal into the current hub's Knowledge Base fields and the FINALIZED NICHE package, ready for the L1/L2 GPTs.

## AI (`llm.py`)

- `complete_json()` for structured answers, `complete_chat()` for chats. Each has a fake for tests.
- `complete_with_tools()` for web search and page reading (Anthropic server tools).
- A queue: `LLM_MAX_CONCURRENCY` (48) calls at once per worker. Others wait up to 15 s (45 s for the webinar tools),
  then get a clear "busy" message and their go back. The pages retry once by themselves after 2–6 s.
- Time limit `LLM_TIMEOUT_S` (45 s); long answers get 120–150 s.
- Every prompt says never to name the AI providers.

## Vendors (`core/vendors.py`)

One switch per vendor: `live`, `fake` (tests, never production) or `off` (the tool shows "paused").
Vendors: razorpay, msg91, aisensy, anthropic, search (Anthropic web search/fetch tools), gemini (video + audio).

## Stages 2–4 (`features/`, one file per tool)

| Area | Files | Notes |
|---|---|---|
| ₹1,999 plan | `weekly`, `decks`, `visuals`, `website` (+ `site_*`), `listen`, `docs`, `progress`, `support` | Decks are our own engine: the AI writes slide JSON, `deck_layout.py` fits the text, `deck_render.py` draws PowerPoint and PDF. Websites are served at `/s/<name>`, `<name>.SITES_DOMAIN` or the member's own domain. |
| L1 | `program`, `calls`, `library`, `recaps`, `gpts`, `akshat_ai`, `offer_card`, `stories`, `insights`, `portfolio`, `pitch` + `pitch_video`, `notebook` | `gpts` runs the 52 prompts in `backend/gpts/` (18 Action Hub for L1, 34 Mentorship for L2). Akshat AI answers only from the knowledge base. |
| L2 | `network`, `outreach`, `radar`, `call_prep`, `proposals`, `diagnostic`, `social`, `bootcamps` | The diagnostic has a public link the client fills without logging in. |

Shared pieces:

- `media.py`: files (images, audio, decks) in Mongo, served at `/api/blobs/{id}`, 15 MB each.
- `audio/tts.py`, `audio/stt.py`: text to speech and speech to text.
- `features/kb.py`: search over the knowledge base (Akshat AI, recaps).
- `features/knowledge.py`: what the app knows about the member (niche, audience, goal), added to every tool's prompt.

Modules plug themselves in at import: events, indexes, jobs and inbox message kinds each have a `register()`.

## Admin (`admin/routes.py`)

Pulse, live (last 15 minutes), webinar report + group-session CSV, members (grant, start L2, disable), settings (live case, group session), switches, vendors, jobs, knowledge base uploads. Each tool's own admin endpoints sit in its module under `/admin/<tool>`: support inbox, Akshat AI questions, program, calls, recaps, library, bootcamps, weekly case, website domains.
