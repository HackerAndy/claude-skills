---
name: ux-usability-review
description: Evaluate a web page or user flow for first-time-user usability. Drafts the test flows from the codebase and docs, lets the user record or refine them with clicks, then scores wording clarity, screen complexity, next-step obviousness and flow coherence with confidence ratings, assuming the user knows nothing about the app. Use when asked to review UX, usability, copy clarity, onboarding, or whether a page or flow is self-describing.
---

# UX Usability Review

Assume a **first-time user with zero knowledge of the app**. Every screen must answer:
*Where am I? What can I do here? What happens if I do it? How do I get back?*

**Design rule: the user should type almost nothing.** You (Claude) run every command, draft every file, and use `AskUserQuestion` with choices. The only human actions are: say which app, sign in once in a browser window, and optionally click through a task.

All commands run from the **root of the project being audited**:
`node <skill-dir>/scripts/cli.mjs <login|record|audit> ...` (first run installs the tool automatically and git-ignores `.ux-auth/` and `ux-audit-out/`).

## Step 0: Get the app URL

Use the URL the user gave. Otherwise look for a dev script, README, or docs (`vite.config`, `package.json`, `.env.example`) to find the local URL, start the dev server if it is not running, and confirm with `AskUserQuestion` (choices: the detected URL / a deployed URL). Do not make the user type what you can detect.

## Step 1: Sign in once, if the app needs it

Detect auth (MSAL/Entra, login routes, guards). If present, run `cli.mjs login <url>`. A browser opens; tell the user: "Sign in, wait for the app to load, then close the window." The session (including sessionStorage tokens) is saved locally and reused by recording and auditing. Tokens expire; if an audit reports `auth-expired`, re-run login.

## Step 2: Draft flows from the codebase and docs

If `ux-flows/` has no flows (or the user asked for new ones), **you write the first draft**; do not ask the user to author JSON.

1. Gather: route definitions (router config, pages folder), navigation/menu components, page titles and headings, role/permission gating, README and `docs/` (user guides, onboarding, personas).
2. Pick the 3-6 most important first-time tasks (what a new user came to do), e.g. "find something", "create something", "complete a pending task". Include the signed-out landing page if it exists.
3. For each, write `ux-flows/<task>.flow.json`:
   ```json
   { "name": "...", "baseUrl": "<url>", "goal": "<one sentence, from the user's view>",
     "auth": ".ux-auth/<host>.json or null", "steps": [
       { "name": "Landing", "goto": "/" },
       { "name": "Open Registry", "click": "a:text-is(\"Registry\")" },
       { "name": "Enter name", "fill": { "selector": "input[name=\"title\"]", "value": "Test" }, "snapshot": false } ] }
   ```
   Step actions: `goto`, `click`, `fill`, `press` ({selector,key}); `"snapshot": false` skips scoring for plumbing steps. Prefer visible-text selectors (`a:text-is("X")`, `button:text-is("X")`) or `[data-testid]`/`#id`; use `>> nth=N` for duplicates. Use only fixed, safe test values; never real data, never destructive actions (delete/submit-for-real) unless the user says so.
4. Show a one-line-per-flow summary, then `AskUserQuestion` with choices: "Run these now (Recommended)", "I'll record one myself", "Drop some flows".

## Step 3: Let the user record or correct a flow (clicks only)

When the user wants to do it themselves, or a drafted flow fails (`step-failed`), run
`cli.mjs record <url> --name <task> --goal "<goal>"`. A browser opens with a red REC badge; the user clicks through the task like a newcomer and **closes the window**. Clicks, typed text and Enter are saved as steps (passwords are masked as `<password>`, so rely on saved login). The result replaces/creates `ux-flows/<task>.flow.json`. Re-run audit to confirm.

## Step 4: Capture evidence

`cli.mjs audit` runs every flow in `ux-flows/` (or pass files; `--min-score N` makes it fail below N). For each flow it writes `ux-audit-out/<flow>/`: `evidence.json` (text, headings, controls), `heuristics.json` (metrics and flags), and one screenshot per step. A `step-failed` blocker usually means the drafted selector is wrong: fix the flow or re-record that task; do not score a flow that did not complete.

## Step 5: Judge and report

1. Read each `heuristics.json`, open every screenshot, and score with `references/rubric.md`. Heuristics are inputs, not verdicts; override them when the screenshot says otherwise and say so.
2. Score each dimension 0-100 with **confidence** 0.0-1.0: >=0.8 only when backed by captured text/screenshot AND a heuristic signal; 0.5-0.79 for visual/subjective judgment; <0.5 when state was not seen (auth, empty data, hover-only UI, error states).
3. Never score what was not captured; list it under "Not assessed".
4. Every finding cites the step, quotes the exact on-screen text, and gives a concrete rewrite or fix.
5. Overall = weighted mean (wording 25, complexity 20, next-step 20, flow 20, feedback 10, a11y 5); overall confidence is capped by the weakest heavily-weighted dimension.
6. Compare flow length to the minimum reasonable steps to the goal, and check information scent: does each page heading match the label that led there?
7. Save `ux-audit-out/report.md`:

```
# UX Usability Report: <app / flow>
Overall: <score>/100 (confidence <x>)
| Dimension | Score | Confidence | Top issue |
Per-step findings, severity blocker/major/minor:
  Step N <url>: [severity] "<quoted text>" - why a newcomer is confused - suggested rewrite
Flow findings: dead ends, unclear next action, backtracking, steps vs. minimum
Strengths
Not assessed: ...
Top 5 fixes ranked by impact/effort
```

Finish with `AskUserQuestion`: "Fix the top issues now" / "Re-run after changes" / "Done".

## Typical prompts that should trigger this skill
"UX review this app", "is this page clear to a first-time user?", "audit the onboarding flow", "check the wording on the registry page".
