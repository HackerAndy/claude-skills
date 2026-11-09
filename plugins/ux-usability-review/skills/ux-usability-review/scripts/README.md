# ux-usability-review scripts

Run from the root of the project being audited. First run installs everything (and falls back to installed Edge if the Chromium download is blocked).

```sh
node <skill-dir>/scripts/cli.mjs login  <url>                           # sign in once; saved to .ux-auth/ (git-ignored)
node <skill-dir>/scripts/cli.mjs record <url> --name task --goal "..."  # click through a task; close the window to save
node <skill-dir>/scripts/cli.mjs audit  [flow files] [--min-score 60]   # runs ux-flows/*.flow.json -> ux-audit-out/
```

Normally you don't type these: ask Claude for a "UX review" and it drafts flows from your code and docs, runs login/record/audit, and writes the report.

Flow files (`ux-flows/*.flow.json`): `name`, `baseUrl`, `goal`, `auth` (saved session path or null), `viewport`, `steps[]`.
Step actions: `goto`, `click`, `fill` ({selector, value}), `press` ({selector, key}); `snapshot: false` performs the step without scoring it.

Heuristic flags include: missing headings/labels, generic or jargon button text, placeholder-as-label, unnamed icon buttons, too many controls, no primary action above the fold, visible error text, disabled actions with no explanation, dead ends, no feedback after an action, `auth-expired`, `step-failed`. Exit code is non-zero on any blocker or when a step is under `--min-score`.

Saved sessions include sessionStorage (MSAL tokens) and expire with the tokens; re-run `login` when needed. Never commit `.ux-auth/`.
