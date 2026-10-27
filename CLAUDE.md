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
