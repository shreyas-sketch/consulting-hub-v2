# Backend design — stage 1

Short notes for the developer. Code comments carry the detail.

## Plans (`plans.py`)

- Four levels: `free` → `member` (₹1,999) → `l1` → `l2`. Higher includes lower.
- Effective plan = the highest of: a live paid subscription, an admin grant, team role (= l2). No trial.
- `require()` → 403 locked. `consume()` → 402 limit. `features/common.run_metered()` gives the use back if the work fails.
- Free accounts count once for life (`usage` doc `<uid>:life`); paid plans count per IST month (`<uid>:YYYY-MM`).

## Billing (`billing/`)

- Razorpay Subscriptions. `subscriptions` stores plan + period (monthly/yearly).
- Upgrading starts a new subscription and stops the old one renewing.
- Cancelling L1 offers the ₹1,999 plan once per account (`users.downsell_offered_at`).
- L2 (`billing/l2.py`): admin "Start L2" → 183-day L2 grant, L1 paused (`paused_for_l2`, `resume_at`). Daily job `l2_resume` restarts it. If Razorpay refuses the pause, L1 is cancelled at the end of its month and the member restarts L1 in the app.

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

One helper, a fake for tests, a queue (`LLM_MAX_CONCURRENCY` per worker, 15 s wait, then a clear "busy" message).

## Admin (`admin/routes.py`)

Pulse, live (last 15 minutes), webinar report + group-session CSV, members (grant, start L2, disable), settings (live case, group session, support number), switches, vendors, jobs, knowledge base uploads.
