# ux-usability-review

A Claude skill that reviews a web page or user flow as a first-time user with zero knowledge of the app. It asks the questions a newcomer would: where am I, what can I do here, what happens if I do it, and how do I get back?

## Use

Ask Claude for a "UX review" of your app. It finds the app URL, signs in once through a browser window if the app needs it, and drafts test flows from your routes, navigation and docs. You can accept them or record a task yourself by clicking through it. Claude then runs each flow, captures text and screenshots at every step, and writes `ux-audit-out/report.md`.

## What you get

Scores from 0 to 100, each with a confidence rating, for wording clarity, screen complexity, next-step obviousness, flow coherence, feedback and accessibility. Every finding cites the step, quotes the exact on-screen text and suggests a concrete rewrite. Anything that wasn't captured is listed as not assessed.

## Setup

Requires Node. Playwright installs itself on first run, and it falls back to an installed Edge if the Chromium download is blocked. Flows live in `ux-flows/`; saved logins in `.ux-auth/` stay out of git.

See `skills/ux-usability-review/SKILL.md` for the full workflow and `skills/ux-usability-review/scripts/README.md` for the command-line options.
