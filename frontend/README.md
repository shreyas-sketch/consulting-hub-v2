# Consultation Hub web (frontend)

React 19 (CRA + craco), Tailwind 3, react-router 7, TanStack Query 5. Built into the Docker image and served by FastAPI.

## Look

Akshat Dani design system, dark only:

- Background `#14151A` with a soft radial lift and a faint 48 px grid; panels `#1E2027`
- Text ivory `#F2EEE6`; gold `#C9A84C` = the signal (kickers, one key phrase per headline, ₹ figures, primary button)
- Teal `#2ED3B7` = AI only (AI buttons, AI result frames, "thinking" dots)
- Red `#E0533D` = errors and destructive actions only
- Manrope only (JetBrains Mono for prompts/code), bundled with `@fontsource-variable`
- Radius: cards 14, frames 18, inputs 12, buttons and pills fully round
- Logo: AD × SK (`src/app/components/Logo.jsx`, `public/logo.svg`)

Tokens live in `src/index.css` (`--bz-*` names) and `tailwind.config.js`. Shared pieces: `src/app/components/ui.jsx` and `common.jsx`.

## Screens

| Route | Screen |
|---|---|
| `/` | What's inside (logged-out visitors) |
| `/login` | Mobile OTP; new numbers get a free account |
| `/plans` | Public plans |
| `/app` | Home: group session invite, progress on the six tools, numbers so far |
| `/app/readiness` | Readiness Score |
| `/app/start` | Starting Point: Niche Snapshot · Goal Map |
| `/app/cases`, `/app/cases/:id` | Live case + practice cases, AI score, model answer |
| `/app/brief`, `/app/brief/:id` | Meeting Brief |
| `/app/linkedin` | LinkedIn Score (+ rewrites on paid plans) |
| `/app/file` | My Consulting File (print / save as PDF) |
| `/app/tools` | Every tool by plan |
| `/app/plans`, `/app/account`, `/app/inbox` | Plans, account (cancel + one-time offer), inbox |
| `/admin/*` | Admin panel |

Phone first: bottom bar Home · Cases · Brief · My File · Menu; sidebar on a computer.

## Commands

`yarn install` · `yarn build` · `yarn start` (dev server; set `REACT_APP_BACKEND_URL` if the API runs elsewhere)
