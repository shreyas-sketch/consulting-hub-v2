# API

All routes are under `/api`. Login sets httpOnly cookies. Errors come back as `{detail: {code, msg}}`.

- `403 {code: locked, feature, plan_needed}`: the plan doesn't include this tool
- `402 {code: limit, feature, used, limit, plan_needed, once}`: the free go or this month's limit is used
- `503 {code: ai_busy}` (or a tool's own 503): the AI or a vendor didn't answer; the go is given back
- `429`: too many requests (login codes, public pages, fair-use caps)

Full schema with request and reply shapes: `/api/swagger` on any running copy (`/api/openapi.json` for the raw file).
Public pages outside `/api`: `/s/{slug}` and `/s/{slug}/{page}` (member websites), `/d/{id}` (shared diagnostic, served by the app).

270 routes, grouped by area.

## admin · akshat-questions

- `POST /api/admin/akshat-questions/{qid}/answer`
- `GET /api/admin/akshat-questions`

## admin · bootcamps

- `POST /api/admin/bootcamps/submissions/{sub_id}/review`
- `GET /api/admin/bootcamps/{bootcamp_id}/submissions`
- `DELETE /api/admin/bootcamps/{bootcamp_id}`
- `PUT /api/admin/bootcamps/{bootcamp_id}`
- `GET /api/admin/bootcamps`
- `POST /api/admin/bootcamps`

## admin · calls

- `DELETE /api/admin/calls/{call_id}`
- `PUT /api/admin/calls/{call_id}`
- `GET /api/admin/calls`
- `POST /api/admin/calls`

## admin · cases

- `GET /api/admin/cases`

## admin · flags

- `GET /api/admin/flags`
- `POST /api/admin/flags`

## admin · gpts

- `GET /api/admin/gpts/conversations/{conv_id}`
- `GET /api/admin/gpts/conversations`

## admin · jobs

- `POST /api/admin/jobs/{name}/run`
- `GET /api/admin/jobs`

## admin · kb

- `DELETE /api/admin/kb/{doc_id}`
- `GET /api/admin/kb`
- `POST /api/admin/kb`

## admin · library

- `DELETE /api/admin/library/{item_id}/file`
- `POST /api/admin/library/{item_id}/file`
- `DELETE /api/admin/library/{item_id}`
- `PUT /api/admin/library/{item_id}`
- `GET /api/admin/library`
- `POST /api/admin/library`

## admin · live

- `GET /api/admin/live`

## admin · program

- `PUT /api/admin/program/cohorts/{cid}/coach`
- `DELETE /api/admin/program/cohorts/{cid}/days/{n}`
- `PUT /api/admin/program/cohorts/{cid}/days/{n}`
- `DELETE /api/admin/program/cohorts/{cid}`
- `GET /api/admin/program/cohorts/{cid}`
- `PUT /api/admin/program/cohorts/{cid}`
- `GET /api/admin/program/cohorts`
- `POST /api/admin/program/cohorts`
- `PUT /api/admin/program/enrollments/{eid}/coach`
- `POST /api/admin/program/enrollments/{eid}/move`
- `GET /api/admin/program/enrollments`

## admin · pulse

- `GET /api/admin/pulse`

## admin · recaps

- `POST /api/admin/recaps/{recap_id}/audio`
- `POST /api/admin/recaps/{recap_id}/publish`
- `POST /api/admin/recaps/{recap_id}/unpublish`
- `DELETE /api/admin/recaps/{recap_id}`
- `GET /api/admin/recaps/{recap_id}`
- `PUT /api/admin/recaps/{recap_id}`
- `GET /api/admin/recaps`
- `POST /api/admin/recaps`

## admin · settings

- `GET /api/admin/settings`
- `POST /api/admin/settings`

## admin · support

- `POST /api/admin/support/{ticket_id}/close`
- `POST /api/admin/support/{ticket_id}/reply`
- `GET /api/admin/support/{ticket_id}`
- `GET /api/admin/support`

## admin · users

- `POST /api/admin/users/{user_id}/grant`
- `POST /api/admin/users/{user_id}/start-l2`
- `POST /api/admin/users/{user_id}/status`
- `GET /api/admin/users/{user_id}`
- `GET /api/admin/users`

## admin · vendors

- `GET /api/admin/vendors`

## admin · webinar

- `GET /api/admin/webinar/group-session.csv`
- `GET /api/admin/webinar`

## admin · website

- `POST /api/admin/website/domains/{site_id}/check`
- `POST /api/admin/website/domains/{site_id}`
- `GET /api/admin/website/domains`

## admin · weekly

- `POST /api/admin/weekly/generate`
- `POST /api/admin/weekly/{case_id}/active`
- `GET /api/admin/weekly`

## admin · whatsapp-templates

- `POST /api/admin/whatsapp-templates/test`
- `GET /api/admin/whatsapp-templates`

## akshat-ai

- `POST /api/akshat-ai/ask`
- `GET /api/akshat-ai/questions`
- `GET /api/akshat-ai/threads/{thread_id}`
- `GET /api/akshat-ai/threads`

## auth

- `POST /api/auth/logout`
- `GET /api/auth/me`
- `POST /api/auth/otp/request`
- `POST /api/auth/otp/verify`
- `PATCH /api/auth/profile`
- `POST /api/auth/refresh`
- `POST /api/auth/staff/login`

## billing

- `POST /api/billing/cancel`
- `POST /api/billing/checkout`
- `POST /api/billing/razorpay/webhook`
- `POST /api/billing/verify`

## blobs

- `GET /api/blobs/{blob_id}`

## bootcamps

- `POST /api/bootcamps/{bootcamp_id}/tasks/{task_id}`
- `GET /api/bootcamps/{bootcamp_id}`
- `GET /api/bootcamps`

## briefs

- `GET /api/briefs/{brief_id}`
- `GET /api/briefs`
- `POST /api/briefs`

## call-prep

- `DELETE /api/call-prep/{pid}`
- `GET /api/call-prep/{pid}`
- `GET /api/call-prep`
- `POST /api/call-prep`

## calls

- `GET /api/calls/{call_id}.ics`
- `GET /api/calls/{call_id}`
- `GET /api/calls`

## cases

- `POST /api/cases/{case_id}/answer`
- `GET /api/cases/{case_id}`
- `GET /api/cases`

## config

- `GET /api/config`

## decks

- `GET /api/decks/options`
- `GET /api/decks/sources`
- `GET /api/decks/{deck_id}/file`
- `DELETE /api/decks/{deck_id}`
- `GET /api/decks/{deck_id}`
- `PATCH /api/decks/{deck_id}`
- `GET /api/decks`
- `POST /api/decks`

## diagnostic

- `POST /api/diagnostic/public/{pid}/responses`
- `GET /api/diagnostic/public/{pid}`
- `POST /api/diagnostic/{did}/publish`
- `GET /api/diagnostic/{did}/responses/{rid}`
- `POST /api/diagnostic/{did}/unpublish`
- `DELETE /api/diagnostic/{did}`
- `GET /api/diagnostic/{did}`
- `PUT /api/diagnostic/{did}`
- `GET /api/diagnostic`
- `POST /api/diagnostic`

## docs

- `POST /api/docs/ask`
- `GET /api/docs/list`
- `POST /api/docs/{doc_id}/summary`
- `DELETE /api/docs/{doc_id}`
- `GET /api/docs/{doc_id}`
- `GET /api/docs`
- `POST /api/docs`

## events

- `POST /api/events`

## file

- `POST /api/file/viewed`
- `GET /api/file`

## gpts

- `POST /api/gpts/conversations/{conv_id}/messages`
- `DELETE /api/gpts/conversations/{conv_id}`
- `GET /api/gpts/conversations/{conv_id}`
- `GET /api/gpts/{slug}/conversations`
- `POST /api/gpts/{slug}/conversations`
- `GET /api/gpts/{slug}`
- `GET /api/gpts`

## health

- `GET /api/health/ready`
- `GET /api/health`

## inbox

- `POST /api/inbox/read-all`
- `GET /api/inbox`

## insights

- `POST /api/insights/{pack_id}/audio`
- `GET /api/insights/{pack_id}`
- `GET /api/insights`
- `POST /api/insights`

## jobs

- `POST /api/jobs/tick`

## library

- `GET /api/library/{item_id}/file`
- `GET /api/library`

## linkedin

- `POST /api/linkedin/check`
- `GET /api/linkedin/{check_id}`
- `GET /api/linkedin`

## listen

- `GET /api/listen/sources`
- `GET /api/listen`
- `POST /api/listen`

## me

- `GET /api/me/home`
- `GET /api/me/plan`

## network

- `POST /api/network/import`
- `POST /api/network/paste`
- `POST /api/network/score`
- `DELETE /api/network/{cid}`
- `GET /api/network/{cid}`
- `PATCH /api/network/{cid}`
- `DELETE /api/network`
- `GET /api/network`

## notebook

- `POST /api/notebook/{pid}/ask`
- `POST /api/notebook/{pid}/audio`
- `POST /api/notebook/{pid}/generate`
- `DELETE /api/notebook/{pid}/notes/{nid}`
- `PATCH /api/notebook/{pid}/notes/{nid}`
- `POST /api/notebook/{pid}/notes`
- `POST /api/notebook/{pid}/sources/doc`
- `POST /api/notebook/{pid}/sources/file`
- `POST /api/notebook/{pid}/sources/text`
- `POST /api/notebook/{pid}/sources/url`
- `DELETE /api/notebook/{pid}/sources/{sid}`
- `DELETE /api/notebook/{pid}`
- `GET /api/notebook/{pid}`
- `PATCH /api/notebook/{pid}`
- `GET /api/notebook`
- `POST /api/notebook`

## offer-card

- `GET /api/offer-card/{card_id}`
- `PUT /api/offer-card/{card_id}`
- `GET /api/offer-card`
- `POST /api/offer-card`

## outreach

- `DELETE /api/outreach/{oid}`
- `GET /api/outreach/{oid}`
- `PATCH /api/outreach/{oid}`
- `GET /api/outreach`
- `POST /api/outreach`

## pitch

- `POST /api/pitch/{tid}/chat`
- `POST /api/pitch/{tid}/take`
- `DELETE /api/pitch/{tid}`
- `GET /api/pitch/{tid}`
- `GET /api/pitch`
- `POST /api/pitch`

## plans

- `GET /api/plans/catalog`

## portfolio

- `POST /api/portfolio/{pid}/answer`
- `POST /api/portfolio/{pid}/review`
- `GET /api/portfolio/{pid}`
- `GET /api/portfolio`
- `POST /api/portfolio`

## program

- `POST /api/program/tasks/{task_id}`
- `GET /api/program`

## progress

- `GET /api/progress/{report_id}`
- `GET /api/progress`
- `POST /api/progress`

## proposals

- `DELETE /api/proposals/{pid}`
- `GET /api/proposals/{pid}`
- `PATCH /api/proposals/{pid}`
- `GET /api/proposals`
- `POST /api/proposals`

## qa

- `POST /api/qa/login`

## radar

- `POST /api/radar/run`
- `PATCH /api/radar/{cid}`
- `GET /api/radar`

## readiness

- `GET /api/readiness/skills`
- `GET /api/readiness`
- `POST /api/readiness`

## recaps

- `GET /api/recaps/{recap_id}/audio`
- `GET /api/recaps/{recap_id}`
- `GET /api/recaps`

## social

- `POST /api/social/generate`
- `DELETE /api/social/{pid}`
- `PATCH /api/social/{pid}`
- `GET /api/social`

## start

- `POST /api/start/goal/preview`
- `PUT /api/start/goal`
- `POST /api/start/snapshot/{snap_id}/choose`
- `POST /api/start/snapshot`
- `GET /api/start`

## stories

- `POST /api/stories/text`
- `POST /api/stories/voice`
- `DELETE /api/stories/{story_id}`
- `GET /api/stories/{story_id}`
- `PUT /api/stories/{story_id}`
- `GET /api/stories`

## support

- `POST /api/support/tickets/{ticket_id}/close`
- `POST /api/support/tickets/{ticket_id}/reply`
- `GET /api/support/tickets/{ticket_id}`
- `GET /api/support/tickets`
- `POST /api/support/tickets`

## visuals

- `POST /api/visuals/{vid}/duplicate`
- `DELETE /api/visuals/{vid}`
- `GET /api/visuals/{vid}`
- `PUT /api/visuals/{vid}`
- `GET /api/visuals`
- `POST /api/visuals`

## website

- `POST /api/website/build`
- `POST /api/website/domain/check`
- `DELETE /api/website/domain`
- `PUT /api/website/domain`
- `DELETE /api/website/images/{kind}`
- `POST /api/website/images/{kind}`
- `GET /api/website/leads`
- `PUT /api/website/pages/{key}/order`
- `POST /api/website/pages/{key}/sections`
- `DELETE /api/website/pages/{key}`
- `POST /api/website/pages`
- `POST /api/website/proposal/apply`
- `POST /api/website/proposal/discard`
- `POST /api/website/public/{slug}/leads`
- `POST /api/website/publish`
- `POST /api/website/sections/{sid}/ai`
- `DELETE /api/website/sections/{sid}`
- `PUT /api/website/sections/{sid}`
- `PUT /api/website/settings`
- `POST /api/website/undo`
- `GET /api/website`
