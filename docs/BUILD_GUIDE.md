# Build guide — how every tool in this app is written

Read this before adding a tool. Copy the patterns of the stage-1 tools; don't invent new ones.

## Who it's for

Members are experienced Indian professionals (mostly 40+, 15–35 years in jobs) getting ready to launch as consultants with
Akshat Dani. Plans: `free` (webinar account) → `member` (₹1,999 plan) → `l1` (₹5,000 + 4-3-2-1) → `l2` (6-month mentorship).
Higher plans include everything below them. Money in ₹ with Indian grouping (₹1,50,000). Dates in IST.

Never name, hint at or describe the AI providers or models anywhere a member can see it (screens, AI replies, errors,
PDFs): every tool presents as the hub's own. Say "AI" at most. Put the same rule in every system prompt you write.

Copy on screens: plain, short, spoken English. One idea per sentence. No buzzwords, no hype, no emojis. Never promise income;
label estimates as estimates. Say what a button does ("Make my deck", not "Submit").

## Backend (FastAPI + Motor/Mongo)

Reference files: `features/brief.py`, `features/cases.py`, `features/linkedin.py`, `features/start.py`, `plans.py`.

- One module per tool in `backend/features/<name>.py` exposing `router = APIRouter(prefix="/<name>", tags=[...])`.
  It is already listed in `server.py`; just replace the stub. Admin endpoints for the tool live in the same module under
  `/admin/<name>...` with `Depends(admin_dep())` (`core.deps`). A page outside `/api` (public website) goes on `public_router`.
- Database: `from state import db` then `db()`. Ids are `uuid.uuid4().hex` strings; `user_id` is `str(user["_id"])`.
  Return plain dicts; datetimes through `util.iso()`; never return raw Mongo docs.
- Access and metering (do not edit `plans.py`; all features, limits and caps already exist there):
  - `plans.require(db, user, "<feature>")` → 403 locked when the plan doesn't include it.
  - `features.common.run_metered(db, user, "<meter>", work, access="<feature>")` → counts one use, runs `work(plan)`,
    gives the use back if the work raises (AI/network). 402 when the month's limit is used.
  - Stored-item caps: `plans.cap("docs", plan)` etc.
- AI output guards in `features.common`: put `NO_VENDOR` in every system prompt; run member-visible text through
  `strip_providers`; use `as_list`/`as_dict` before slicing AI fields; `strip_links` on free text (links only from search).
- AI: `llm.complete_json(task=..., system=..., prompt=..., fake=lambda: {...}, model="fast"|"strong")` or
  `llm.complete_chat(task=..., system=..., messages=[...], fake=lambda: "...")`. Always pass a deterministic `fake`
  built from the inputs (tests and QA run without keys). Validate every AI field (`features.common.text`, `clamp_int`,
  `text_list`); if the shape is wrong raise `llm.LLMError` so the use is refunded. Never let the AI invent links:
  links come only from search results, picked by index (see `features/brief.py`).
- What the app knows about the member: `features.knowledge.knowledge(db, user)` → niche, value proposition, industry,
  audience, goal, consultant title, `blueprint` (FINALIZED NICHE text). `knowledge.system_block(k)` for prompts.
- Akshat's original GPT prompts are in `backend/gpts/prompts/<slug>.md` (catalogue: `backend/gpts/catalog.json`).
  Where a tool matches one, follow its structure and rules.
- Web search: `research.search.news(query, max_results)` → `[{title, url, source, published, snippet, test}]` (Anthropic web search; cached 6 hours per query). Page text: `research.search.extract(urls)`.
- Audio: `audio.tts.speak(text)` → `(bytes, content_type)`; `audio.stt.transcribe(bytes, filename=, content_type=)` → text.
  Errors: `audio.tts.TTSError`, `audio.stt.STTError` → answer 503 with a plain message and refund.
- Files: `media.save_blob(db, user_id=, kind=, content_type=, data=, name=, public=)` → id; `media.blob_url(id)`;
  `media.TooLarge`. Served at `/api/blobs/{id}` to the owner/admin, or anyone when `public=True`.
  Never keep member video: Pitch Practice deletes it from the server and the vendor right after analysis.
- Plug-ins at import time (don't edit the shared files):
  `growth.events.register("name", "description", client=False)` then `events.track(db, "name", user_id=..., props=...)`;
  `indexes.register("coll", [("field", 1)])`; `jobs.registry.register("name", "label", ("daily", h, m) | ("weekly", weekday, h, m) | ("every", minutes), "features.x:job_fn")`
  where `async def job_fn(ctx)` gets `ctx.db`, `ctx.now` and returns a small dict;
  `notify.service.register_kind("kind")` then `notify.service.alert(...)` / `alert_many(...)` for inbox messages.
- Uploads: `UploadFile`; read with a size cap; accept only the listed types; plain error messages.

## Tests (pytest + mongomock, no network)

- Add `backend/tests/test_<area>.py`. Use fixtures from `tests/conftest.py`: `seeded_client`, `client`, `mdb`;
  helpers `qa_login(client, plan="member"|"l1"|"l2"|"free")`, `login(...)`, `run(coro)`. Don't edit `conftest.py`.
- Cover for each tool: the happy path, a lower plan gets 403 `locked`, the limit gives 402 `limit`, and (for one AI call)
  an `llm.LLMError` refunds the use.
- Run `cd backend && python3 -m pytest -q tests/test_<area>.py` and then the whole suite before you finish.

## Frontend (React 19, Tailwind, Akshat Dani design system, dark only)

Reference files: `src/app/components/ui.jsx`, `common.jsx`, `Markdown.jsx`; pages `Brief.jsx`, `LinkedIn.jsx`,
`CaseView.jsx`, `Start.jsx`, `File.jsx`.

- One page file per route, already stubbed in `src/app/pages/` (and `src/app/admin/`); replace the stub, keep the default
  export. Routes `/app/<path>` and `/app/<path>/:id` both open your page (use `useParams().id`).
- Wrap the page body in `<Gate feature="...">` (common.jsx) so lower plans see the lock card with the upgrade button.
- Look: `PageHeader` (kicker + headline with one key phrase in gold, or teal on AI screens via `ai`), `Card`,
  `Button` (`primary` = gold pill, one per screen; `secondary`; `ai` = teal, only for buttons that call AI), `AiFrame`
  around anything the AI wrote, `Thinking` while AI works, `Stat` for numbers, `Step` for numbered steps, `Chip`, `Field`,
  `Input`, `Textarea`, `Select`, `Segmented`, `Meter`, `Loadable`, `Empty`, `ErrorLine`, `OkLine`, `Note`.
  Gold = the signal (₹ figures, key phrase, primary action). Teal = AI only. Red = errors/destructive only.
  Manrope only (JetBrains Mono for code/prompts). No new colours, no light mode, no emojis.
- `Markdown` (components/Markdown.jsx) renders AI Markdown with copy cards. `UsageLine` shows the plan limit.
  After a metered action call `refreshMe()` from `useAuth()` so limits update.
- API: `api` / `get` from `@/lib/api`, React Query (`useQuery`, `useQueryClient`), errors through `apiError(e)`.
  402/403 open the global upgrade sheet automatically; don't show your own error for those.
- Formats: `inr()`, `hdate()`, `ago()` from `@/lib/format`.
- Phone first (390 px): no sideways scroll, tap targets ≥ 44 px, inputs 16 px. Tables scroll inside their own box.
- Print-friendly where a member will keep the result: `window.print()` button with class `no-print` on controls.
- Put `data-testid` on the main inputs and buttons.
- Build check without disturbing others: `cd frontend && BUILD_PATH=/tmp/claude-0/-home-claude/dd6a8dbd-3037-51f1-b932-6d033eda22b4/scratchpad/build-<you> CI=true npx craco build`
  (CI=true turns warnings into errors; fix them all).

## Rules for parallel work

- Only edit the files you own. Shared files (`plans.py`, `server.py`, `llm.py`, `media.py`, `audio/*`, `conftest.py`,
  `App.js`, `AppShell.jsx`, `ui.jsx`, `common.jsx`, `features.js`, `index.css`) are read-only for you. If you need a
  change there, say so in your final report.
- Don't start servers, don't run Playwright, don't run `git` commands.
- Vendor APIs (Anthropic, Gemini, Razorpay, AiSensy, MSG91): check the official docs with web search before writing the live client;
  always keep a fake for tests/QA.
