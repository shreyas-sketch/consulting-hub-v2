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

Read `docs/ARCHITECTURE.md` first. Reference: `features/cases/` (the layered layout every new tool copies), plus
`features/brief.py`, `features/linkedin.py`, `features/start.py`, `plans.py`.

- New tools are packages: `features/<name>/` with `router.py` (HTTP only), `service.py` (rules, metering, AI),
  `repository.py` (subclass `core.repository.Repository`; the only code that queries the tool's collections),
  `prompts.py` (system prompt, prompt builder, fake) and `schemas.py` (request bodies, response mappers).
  List the module in `core/modules.py` under its plan level. Single-file tools still work and move to this layout when
  they are next changed substantially.
- Errors: raise from `core.errors` (`NotFound`, `InvalidInput`, `Conflict`, `PayloadTooLarge`, `UnsupportedMedia`,
  `TooManyRequests`, `UpstreamError`, `ServiceUnavailable`, or `error(status, code, msg)`), always with a plain `msg`.
  Never a bare `HTTPException`. The wire shape `{detail: {code, msg}}` is fixed.
- Configuration: add new environment variables to `core/settings.py` (typed, with a default and a note) and to
  `backend/.env.example`. Never read `os.environ` anywhere else.

- One module per tool in `backend/features/<name>.py` exposing `router = APIRouter(prefix="/<name>", tags=[...])`.
  It is listed in `core/modules.py`. Admin endpoints for the tool live in the same module under
  `/admin/<name>...` with `Depends(admin_dep())` (`core.deps`). A page outside `/api` (public website) goes on `public_router`.
- Database: in a repository, `self.db`; elsewhere `from state import db` then `db()`. Ids are `uuid.uuid4().hex` strings; `user_id` is `str(user["_id"])`.
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

## Frontend (React 19, Tailwind, "the chamber" design: bottle green, brass, ivory, ink-blue)

Reference files: `src/app/components/ui.jsx`, `common.jsx`, `Markdown.jsx`; pages `Brief.jsx`, `LinkedIn.jsx`,
`CaseView.jsx`, `Start.jsx`, `File.jsx`.

- One page file per route, already stubbed in `src/app/pages/` (and `src/app/admin/`); replace the stub, keep the default
  export. Routes `/app/<path>` and `/app/<path>/:id` both open your page (use `useParams().id`).
- Wrap the page body in `<Gate feature="...">` (common.jsx) so lower plans see the lock card with the upgrade button.
- Look (tokens in `src/index.css`, names kept as `bz-*`): `PageHeader` (the tool's name, a serif headline in one colour,
  a short brass rule, a sub-line; ink-blue rule on AI screens via `ai`), `Card`, `Button` (`primary` = brass plate, one per
  screen; `secondary`; `ai` = ink-blue, only for buttons that call AI), `AiFrame` (ink-blue margin rule) around anything the
  AI wrote, `Thinking`, `Stat` (serif figure), `Step` (only for real sequences), `Chip`, `Field`, `Input`, `Textarea`,
  `Select`, `Segmented`, `Meter`, `Loadable`, `Empty`, `ErrorLine`, `OkLine`, `Note`.
  Brass (`bz-gold`) = the one signal (₹ figures, primary action, where you are). Ink-blue (`bz-teal`) = AI only.
  Sindoor (`bz-miss`) = errors/destructive only. Newsreader (`font-display`, and every h1/h2) for headlines, tool names and
  figures; Manrope for everything read and tapped. Labels in sentence case, never all caps or letter-spaced; no
  single-phrase colour accents in headlines. Radius follows role: `rounded-bzframe` 12, `rounded-bzcard` 8,
  `rounded-bzbtn` 6 (buttons, inputs), `rounded-bztag` 4 (chips); round only for dots, avatars and toggles.
  No new colours, no light mode, no emojis. Downloaded decks keep Akshat's deck design (`backend/features/deck_*`).
- `Markdown` (components/Markdown.jsx) renders AI Markdown with copy cards. `UsageLine` shows the plan limit.
  After a metered action call `refreshMe()` from `useAuth()` so limits update.
- API: for a domain that has a module in `src/services/` (cases, file), use its hooks and add keys to
  `services/queryKeys.js`; new domains get a service module. Otherwise `api` / `get` from `@/lib/api`, React Query (`useQuery`, `useQueryClient`), errors through `apiError(e)`.
  402/403 open the global upgrade sheet automatically; don't show your own error for those.
- Formats: `inr()`, `hdate()`, `ago()` from `@/lib/format`.
- Phone first (390 px): no sideways scroll, tap targets ≥ 44 px, inputs 16 px. Tables scroll inside their own box.
- Print-friendly where a member will keep the result: `window.print()` button with class `no-print` on controls.
- Put `data-testid` on the main inputs and buttons.
- Build check without disturbing others: `cd frontend && BUILD_PATH=/tmp/claude-0/-home-claude/dd6a8dbd-3037-51f1-b932-6d033eda22b4/scratchpad/build-<you> CI=true npx craco build`
  (CI=true turns warnings into errors; fix them all).

## Rules for parallel work

- Only edit the files you own. Shared files (`plans.py`, `server.py`, `core/*`, `llm.py`, `media.py`, `audio/*`, `conftest.py`,
  `App.js`, `AppShell.jsx`, `ui.jsx`, `common.jsx`, `features.js`, `index.css`) are read-only for you. If you need a
  change there, say so in your final report.
- Don't start servers, don't run Playwright, don't run `git` commands.
- Vendor APIs (Anthropic, Gemini, Razorpay, AiSensy, MSG91): check the official docs with web search before writing the live client;
  always keep a fake for tests/QA.
