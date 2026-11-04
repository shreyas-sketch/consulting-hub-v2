# API — stage 1

All routes are under `/api`. Login sets httpOnly cookies. Errors come back as `{detail: {code, msg}}`.

- `403 {code: locked, feature, plan_needed}` — the plan doesn't include this tool
- `402 {code: limit, feature, used, limit, plan_needed, once}` — the free go or this month's limit is used
- `503 {code: ai_busy}` — the AI didn't answer; the go is given back

Full schema: `/api/docs` on any running copy.

## admin

- `GET /api/admin/cases`
- `GET /api/admin/flags`
- `POST /api/admin/flags`
- `GET /api/admin/jobs`
- `POST /api/admin/jobs/{name}/run`
- `GET /api/admin/kb`
- `POST /api/admin/kb`
- `DELETE /api/admin/kb/{doc_id}`
- `GET /api/admin/live`
- `GET /api/admin/pulse`
- `GET /api/admin/settings`
- `POST /api/admin/settings`
- `GET /api/admin/users`
- `GET /api/admin/users/{user_id}`
- `POST /api/admin/users/{user_id}/grant`
- `POST /api/admin/users/{user_id}/start-l2`
- `POST /api/admin/users/{user_id}/status`
- `GET /api/admin/vendors`
- `GET /api/admin/webinar`
- `GET /api/admin/webinar/group-session.csv`

## auth

- `POST /api/auth/logout`
- `GET /api/auth/me`
- `POST /api/auth/refresh`
- `POST /api/auth/staff/login`

## auth-otp

- `POST /api/auth/otp/request`
- `POST /api/auth/otp/verify`
- `PATCH /api/auth/profile`

## billing

- `POST /api/billing/cancel`
- `POST /api/billing/checkout`
- `POST /api/billing/razorpay/webhook`
- `POST /api/billing/verify`

## meeting-brief

- `GET /api/briefs`
- `POST /api/briefs`
- `GET /api/briefs/{brief_id}`

## cases

- `GET /api/cases`
- `GET /api/cases/{case_id}`
- `POST /api/cases/{case_id}/answer`

## misc

- `GET /api/config`
- `GET /api/me/home`
- `GET /api/me/plan`
- `GET /api/plans/catalog`
- `POST /api/qa/login`

## events

- `POST /api/events`

## consulting-file

- `GET /api/file`

## health

- `GET /api/health`
- `GET /api/health/ready`

## inbox

- `GET /api/inbox`
- `POST /api/inbox/read-all`

## jobs

- `POST /api/jobs/tick`

## linkedin

- `GET /api/linkedin`
- `POST /api/linkedin/check`
- `GET /api/linkedin/{check_id}`

## readiness

- `GET /api/readiness`
- `POST /api/readiness`
- `GET /api/readiness/skills`

## starting-point

- `GET /api/start`
- `PUT /api/start/goal`
- `POST /api/start/goal/preview`
- `POST /api/start/snapshot`
- `POST /api/start/snapshot/{snap_id}/choose`

