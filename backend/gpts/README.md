# GPT prompts from the current Consultation Hub

Copied verbatim from the current hub's working document (`docs/reference/current-hub-working.md`, exported 4 Nov 2026)
by `scripts/extract_gpts.py`. 52 GPTs: 18 Action Program (4-3-2-1) and 34 Mentorship.

- `catalog.json` — name, program (`action` | `mentorship`), starter button, description, slug, prompt size
- `prompts/<slug>.md` — the system prompt, exactly as the current hub sends it

Where they go in the new app:

- Action Program GPTs → **L1** "Action Hub tools" (stage 3)
- Mentorship GPTs → **L2** (stage 4)
- Webinar tools (stage 1) follow three of them instead of running them as chats:
  - Niche Snapshot → `define-your-niche` (finalized niche, consultant title, value proposition, INR fee ranges)
  - Cases → `strategy-thinking-framework` (scope · objective · framework/options/priority · implementation charter)
  - LinkedIn Score rewrites → `linkedin-optimizer` (3 headlines by angle, About 300–400 words, post ideas)

Do not edit the prompt files by hand; re-run the extract script on a fresh export.
