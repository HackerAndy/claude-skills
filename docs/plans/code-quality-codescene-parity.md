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

## Step 2: get CodeScene running (done 2026-11-12)
- Mac (arm64), so the Podman and Windows notes no longer apply.
- MCP: the `codescene@codescene` Claude Code plugin (1.5.20, user scope, from the `codescene-oss/codescene-mcp-server` marketplace) runs `npx -y @codescene/codehealth-mcp`.
- CLI: `cs` 1.0.58 in `~/.local/bin`, from `downloads.codescene.io/enterprise/cli/cs-macos-aarch64-latest.zip`, with the quarantine flag removed.
- Auth: `CS_ACCESS_TOKEN` in the `env` block of `~/.claude/settings.json`, used by both. `cs auth status` confirms it.
- CodeScene's defaults differ from ours: CC warns at 9 (ours 10), more than 4 arguments (ours 5), nesting 4 (ours 3), 70 LoC per function (ours 60), 2 bumps (ours 1), and file mean CC 4 (we have no equivalent). They are saved in `plugins/code-quality/tests/parity/results/`.

## Step 3: build the comparison corpus (done 2026-11-12)
- `plugins/code-quality/tests/parity/fixtures/{py,ts}/`: 10 Python and 7 TS fixtures, one smell each, plus a clean control. The manifest and first CodeScene results are in `tests/parity/README.md`.
- Real files: `examples/demo/app/orders.py`, `qg_checks.py`, `quality_gate.py`, `backend_map.py`.
- Found while building it:
  - `cs review` scores Python and TS the same.
  - It never reports Code Duplication or Brain Method.
  - It skips Primitive Obsession for Python.
  - Primitive Obsession needs about 15 primitive-argument functions in a file before it fires.
  - Step 4 checks whether `cs delta` reports duplication and Brain Method.

## Step 4: run both and compare (done 2026-11-12)
- `plugins/code-quality/tests/parity/run_parity.py` runs both tools on the corpus in a temporary git repo and writes `results/parity.json`.
- Findings are in `plugins/code-quality/docs/codescene-parity.md`:
  - 71% of CodeScene's function smells match ours, but the scores are 1.96 points apart on average, with rank correlation 0.42.
  - We're much harsher on single smells, and softer on files with many medium smells.
  - 13 of the 21 misses come from thresholds: CodeScene warns when a value reaches its threshold, we only above our limit.
  - `cs delta` doesn't report duplication or Brain Method either.

## Step 5: turn the gaps into changes (done 2026-11-12, code-quality 0.11.0)
You chose all three changes and to match CodeScene:
- **Thresholds:** CodeScene's defaults less one, because it warns at a threshold: cc 8, 69 lines, 4 parameters, 1 operator, and 599 / 999 lines per Python / JS-TS file.
- **Score:** each smell costs what it costs CodeScene, measured with generated samples, and the costs multiply. Nesting, parameters and bumps count once per file. Lint costs nothing. A function with findings stops at 94%, so approved still means no findings.
- **Bumps:** branches of a top-level fork that hold nested logic, and a loop counted as one bump.
- Result: mean file-score gap 1.96 → 0.17, rank correlation 0.42 → 0.74, smell match 71% → 87%. Details in `plugins/code-quality/docs/codescene-parity.md`.
- The `code-quality-live` pane now shows the cost breakdown instead of "worst measure".

## Verification
- Step 1: `git status -sb` shows no "ahead", and `ls-remote` matches local HEAD.
- Steps 3-5: every fixture has a recorded CodeScene result and a recorded code-quality result, the parity doc exists, and `python3 -m unittest discover tests` passes.
