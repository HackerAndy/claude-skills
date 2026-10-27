# claude-skills

A public plugin marketplace (`.claude-plugin/marketplace.json`) on GitHub at HackerAndy/claude-skills. Each plugin lives in `plugins/<name>/` and has an entry in the marketplace file.

## Mods

`plugins/<name>/` is the only copy of each mod. Edit it here, never in `~/.claude/dev-mods/`. `~/.claude/settings.json` loads each mod folder through `CLAUDE_CODE_PLUGIN_DIRS`, so saved edits reload in running sessions.

- `scripts/adopt-mod.sh <mod folder>` brings a new mod in from `~/.claude/dev-mods/`: copies it to `plugins/<name>/`, adds the marketplace entry, adds the folder to `CLAUDE_CODE_PLUGIN_DIRS`, validates and tests it, commits, and moves the dev-mods copy to the Trash.
- `scripts/check-dev-mods.sh` runs as a SessionStart hook and names any mod still in `dev-mods`.

After changing a mod:

1. `claude plugin validate plugins/<name>` and `claude plugin test plugins/<name>`
2. Bump `version` in `plugins/<name>/.claude-plugin/plugin.json` so installed copies see an update
3. Commit, and push to `main` only when the user asks

## backend-viz

`plugins/backend-viz/` (skill, analyzer `skills/backend-viz/scripts/backend_map.py`, dashboard template, tracer templates in `templates/trace/`, PostToolUse drift hook, CLI in `bin/backend-viz`, demos in `examples/`) and its mod `plugins/backend-viz-live/` (the "Backend map" pane, which reads the `.backend-viz/report.json` the analyzer writes). This repo is their one source; projects install the plugins, they don't copy them. Both are loaded from here through `CLAUDE_CODE_PLUGIN_DIRS`.

Test changes on the demos (from `plugins/backend-viz/`):

- `bin/backend-viz --root examples/fastapi-demo` (expect 1 undocumented endpoint, 2 untraced functions)
- hook: `echo '{"cwd":"<demo>","tool_input":{"file_path":"<demo>/app/routers/orders.py"}}' | python3 skills/backend-viz/scripts/backend_map.py --hook` (exit 2 + feedback)
- mod: `claude plugin validate ../backend-viz-live && claude plugin test ../backend-viz-live`
- dashboard: open `examples/fastapi-demo/.backend-viz/dashboard.html` in light and dark; no console errors

Design rules:

- Opt-in per project: nothing happens unless a `design/` folder exists (found by walking up from the edited file, so monorepos work).
- The analyzer has no dependencies but PyYAML; the dashboard is one self-contained HTML file.
- The tracer (`templates/trace/`) is copied into each project by `--init-tracing` because it is imported by app code; keep it dependency-free.
- Never log secrets: vault modules and secret-looking args are redacted.
