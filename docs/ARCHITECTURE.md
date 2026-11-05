# Architecture

How the Consultation Hub is put together, and the rules that keep it that way. For *what* the app does, read
`CONSULTATION_HUB_A_TO_Z.md`; for how to write a tool, `BUILD_GUIDE.md`.

---

## 1. Shape of the system

```
 Browser (React SPA, phone first)                       Outside services
 ─────────────────────────────────                      ─────────────────
  pages ─► services/ (hooks + HTTP) ─► lib/api.js ──┐    Razorpay  MSG91  AiSensy
                                                     │    Anthropic (text + web search)
 One Docker image on Railway                         │    Gemini (audio + video)
 ─────────────────────────────────                   ▼          ▲
  RequestContextMiddleware (request id, access log, security headers)
  SiteHostMiddleware (member websites on their own domain)
  /api routers  ─►  services  ─►  repositories  ─►  MongoDB (Atlas)
        │               │
        │               ├─► plans (access + metering) ─► usage
        │               ├─► llm / research / audio / billing clients ──────┘  (live | fake | off per vendor)
        │               └─► notify (inbox + WhatsApp), events, jobs
  SPA catch-all (built React app)        APScheduler jobs (Mongo lease per run)
```

One process serves the API, the member websites and the React build. Workers are stateless apart from short
in-process caches (feature flags 30 s, app settings 20 s, knowledge base); everything that must be shared lives in
Mongo, including scheduler and cap locks, so `WEB_CONCURRENCY > 1` is safe.

---

## 2. Backend layers

| Layer | Lives in | Knows about | Never does |
|---|---|---|---|
| **Composition root** | `server.py` | everything, once | business logic |
| **Kernel** | `core/` | settings, errors, middleware, logging, module registry, health, SPA | feature rules |
| **HTTP** | `features/<tool>/router.py` (or the router section of a single-file tool) | request parsing, auth dependency | queries, AI calls, plan rules |
| **Service** | `features/<tool>/service.py` | plan checks, metering, AI calls and validation of AI output, events | Motor queries, HTTP objects |
| **Repository** | `features/<tool>/repository.py`, base `core/repository.py` | collection names, fields, query shapes | plan rules, HTTP |
| **Platform services** | `plans.py`, `llm.py`, `research/`, `audio/`, `media.py`, `billing/`, `notify/`, `jobs/`, `growth/` | their own concern | feature specifics |

Dependencies point **down only**: router → service → repository → database. A service may call platform services;
platform services never import a feature.

### The reference tool

`features/cases/` is the reference layout. New tools copy it; existing single-file tools move to it when they are next
changed substantially (strangler pattern: no big-bang rewrite, every step keeps the suite green).

```
features/cases/
  __init__.py     public surface: router, CaseService, ensure_seed, get_case, SYSTEM
  router.py       HTTP only; gets CaseService via Depends(get_service)
  service.py      the rules (free = live case once; model answer only after answering; metered scoring)
  repository.py   the only code that queries `cases` and `case_answers`
  prompts.py      SYSTEM prompt, prompt builder, deterministic fake
  schemas.py      AnswerIn and the response mappers
```

`tests/test_cases_service.py` shows the payoff: the rules are tested against an in-memory repository, with no HTTP
and no database.

Status today: `cases` is migrated. The other 39 tools are still single files with the same rules applied inside (they
already use `run_metered`, `plans.require`, typed errors and settings). The largest, `website.py`, `pitch.py`,
`notebook.py` and `docs.py`, are the next candidates.

---

## 3. Cross-cutting rules

### Configuration: `core/settings.py`
- The **only** module that reads the environment. Everything else uses `settings.<section>.<name>`
  (`settings.llm.max_concurrency`, `settings.auth.admin_phones`, `settings.razorpay.plan_id(...)`).
- Values are read when they are accessed, so tests override them with `monkeypatch.setenv` and a bad value falls back
  to its default instead of crashing a request.
- `settings.problems()` lists unsafe production config. `create_app` **refuses to start** in production if the list is
  not empty (short `JWT_SECRET`, `QA_MODE` on, http `PUBLIC_BASE_URL`, insecure cookies, no admin, localhost Mongo,
  any vendor forced to `fake`).
- Feature switches the team changes at run time are not settings: they are `core/flags.py` (Admin › Switches).

### Errors: `core/errors.py`
- Code raises what went wrong: `NotFound("Case not found.")`, `InvalidInput("Pick a date.", code="start_date")`,
  `LimitReached(...)`, `Locked(...)`, `AIBusy()`, `UpstreamError(...)`. Never a bare `HTTPException`.
- Wire format is fixed and the frontend depends on it:
  `{"detail": {"code": "...", "msg": "plain sentence", ...extra}}`.
  - `402 limit` / `403 locked` open the upgrade sheet;
  - `503 ai_busy` makes the page retry a POST once (the use has already been given back);
  - `403 revoked` logs the member out.
- `AppError` subclasses `HTTPException`, so FastAPI renders it natively.
- Anything unexpected becomes a `500 server_error` with the request id and no internals.
- Validation of request *shape* stays with Pydantic (422 list); `InvalidInput` is for business rules.

### Database access
- One binding: `state.db()`, set by `create_app` (tests bind mongomock). No module keeps its own copy.
- Repositories take an optional explicit db (`CaseRepository(db)`) for jobs, scripts and tests.
- Ids are `uuid4().hex` strings (users use ObjectId). Datetimes are stored as UTC and returned through `util.iso`.
- Indexes are declared next to the code that needs them (`indexes.register`) and created at start-up.

### Request context and logging
- `core/middleware.py` gives every request an id (reusing a sane incoming `X-Request-ID`), returns it as
  `X-Request-ID`, writes one access line per API call and adds security headers (HSTS in production).
- `core/logging.py` puts the request id on every log line; JSON lines in production (`LOG_JSON`).
- Sentry (`core/observability.py`) scrubs OTPs, tokens, cookies and phone numbers.

### Modules: `core/modules.py`
- The explicit list of everything mounted, grouped by plan level. A module exposes `router` (mounted under `/api`)
  and optionally `public_router` (site root, e.g. `/s/<name>`).
- At import a module self-registers its indexes, jobs, analytics events and inbox message kinds.

### Plans and metering
- `plans.py` is the single source for features, limits and caps. `run_metered` counts one use atomically, runs the
  work and gives the use back on any failure. This is the only way a tool spends a member's allowance.

### Vendors
- Every outside service is `live | fake | off` (`core/vendors.py`), and every AI call passes a deterministic `fake`.
  Tests and `QA_MODE` run the whole app with no keys and no network. `fake` is refused in production.

---

## 4. Frontend layers

| Layer | Lives in | Role |
|---|---|---|
| Entry | `index.js`, `lib/queryClient.js` | providers, query defaults (no retry on 4xx, mutations never auto-retry) |
| Routing | `App.js` | public, member (`/app/*`, `RequireAuth` + `AppShell`), admin; every page lazy-loaded |
| Resilience | `app/components/ErrorBoundary.jsx` | one crashed screen never blanks the app; stale chunks after a deploy reload once |
| Domain services | `services/<domain>.js`, `services/queryKeys.js` | HTTP calls + React Query hooks that own their cache invalidation |
| HTTP client | `lib/api.js` | cookies, silent session renewal, the 402/403 upgrade sheet, one AI-busy retry, error sentences |
| Session | `context/AuthContext.jsx` | `/auth/me`, plan and limits, logout |
| UI kit | `app/components/ui.jsx`, `common.jsx` | Akshat Dani design system (dark only; gold = signal, teal = AI, red = errors) |
| Screens | `app/pages/*`, `app/admin/*` | compose hooks and UI; no URLs or query keys inline in migrated screens |

Rule for screens: use a hook from `services/` (`useCases()`, `useAnswerCase(id, { onDone })`). Adding a domain means
adding its keys to `queryKeys.js` and a `services/<domain>.js`. Migrated so far: cases, My Consulting File, home. Other
screens still call `api` directly and move over as they are touched, the same way as the backend.

---

## 5. Quality gates

- `backend`: `ruff check .` and `python -m pytest -q`. The suite has 361 tests on mongomock and fake vendors.
- `frontend`: `CI=true yarn build` (warnings are errors).
- `.github/workflows/ci.yml` runs all three on every push and pull request.
- What is *not* covered automatically (real vendor accounts, real AI latency, Railway/Atlas performance) is listed in
  `QA_REPORT.md` and section 15 of the A-to-Z guide.

---

## 6. Decisions

| Decision | Why |
|---|---|
| Modular monolith, one image | One team, one deploy, a webinar spike of about 500 people: a monolith with clear module edges is cheaper and safer than services. The edges (`core/modules.py`, layers) keep a later split possible. |
| MongoDB with atomic per-document counters | Metering and caps need "check and spend" in one write; Mongo's conditional `$inc` and leases cover it without transactions. |
| Settings read at access time | Testable without import-order tricks; still one declared, typed place per variable. |
| `AppError` subclasses `HTTPException` | Typed errors without changing the wire contract or breaking existing `except HTTPException`. |
| Strangler migration to layered tools | The 347 existing tests stay green at every step; no freeze while the structure improves. |
| Fakes for every vendor | The whole product can be demoed, tested and load-tested with no keys. |
