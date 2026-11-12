# Plan: push code-quality 0.10.0, then benchmark code-quality against CodeScene

## Context
`plugins/code-quality` is modelled on CodeScene's Code Health. Its README admits the numbers are "comparable in spirit, not identical", and nothing has checked that claim. This plan pushes the pending commit, then runs both tools on the same code to find what to tighten.

Findings so far:
- Local `main` (3443b65, code-quality 0.10.0) is 1 commit ahead of `origin/main` (30a0e52).
- `gh` has two accounts: `akaminski_Borgcopi` is active and `HackerAndy` is inactive. The remote is `https://github.com/HackerAndy/claude-skills.git`.
- CodeScene has no token-free mode. Both `cs` and the MCP server need `CS_ACCESS_TOKEN`. The only free route is a 30-day trial that asks for payment details and auto-converts (about $9/month) unless cancelled.
- Podman and WSL are not installed. The `codescene/codescene-mcp` image only runs the MCP stdio server (no `cs review`), and it is retired after 2026-12-31. Native Windows binaries exist (`cs` CLI zip, `cs-mcp-windows-amd64.exe`, `npm i -g @codescene/codehealth-mcp`).

## Step 1: push (needs the right account)
1. `gh auth switch --user HackerAndy`, then confirm with `gh auth status` that HackerAndy is active.
2. `git push origin main`, which sends 3443b65 only.
3. Check with `git ls-remote origin refs/heads/main`.
4. Switch back with `gh auth switch --user akaminski_Borgcopi` if wanted.

## Step 2: get CodeScene running (blocked on you)
- You are sorting out Podman. If it works, pull `codescene/codescene-mcp` with `CS_ACCESS_TOKEN` and `CS_MOUNT_PATH` set. That route gives MCP only.
- The native `cs` CLI is better for scripting, because `cs review --output-format json` and `cs delta --output-format json` give per-file scores and smells.
- A token is needed either way.

## Step 3: build the comparison corpus
- Use `plugins/code-quality/examples/demo/` (`legacy_price` is the known bad function).
- Add 6-10 small fixtures in Python and TS, one per smell: Nested Complexity, Complex Conditional, Bumpy Road, Complex Method, Large Method, Brain Method, DRY violations, Primitive Obsession, Excess Function Arguments, and one clean control.
- Add 2-3 real files from this repo (`qg_checks.py`, `quality_gate.py`, `backend_map.py`).
- Keep fixtures out of the plugin's own checks, for example under `plugins/code-quality/tests/parity/`.

## Step 4: run both and compare
- Run `cs review` and `cs rules-config list-thresholds --language Python --format json` to get the real default thresholds.
- Run `quality-gate score FILE --symbol NAME` and `quality-gate check --json` on the same files.
- Compare per-file score (1-10), per-function smell set (hits, misses, extras) and score ordering across files.
- Write the findings as a table in the repo, for example `plugins/code-quality/docs/codescene-parity.md`.

## Step 5: turn the gaps into changes
Likely areas, to be confirmed by the data:
- Bumpy Road ignores bump size.
- Complex Conditional counts operators, not clauses.
- The score is a per-function worst-metric heuristic, where CodeScene uses a file-level model.
- Duplication is a flat 5-point penalty.
- Large Method and Brain Method have no direct equivalent.
- The default thresholds may differ from CodeScene's.

Then:
- Add parity tests to `tests/test_quality_gate.py`.
- Soften the README's claims where the data doesn't support them.
- Bump `version` in `plugin.json`, run `claude plugin validate` and `claude plugin test`, and commit. Push only when you ask.

## Verification
- Step 1: `git status -sb` shows no "ahead", and `ls-remote` matches local HEAD.
- Steps 3-5: every fixture has a recorded CodeScene result and a recorded code-quality result, the parity doc exists, and `python3 -m unittest discover tests` passes.
