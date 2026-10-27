# claude-skills

A public plugin marketplace (`.claude-plugin/marketplace.json`) on GitHub at HackerAndy/claude-skills. Each plugin lives in `plugins/<name>/` and has an entry in the marketplace file.

## session-files mod

`plugins/session-files/` is the only copy of the session-files mod. Edit it here, never in `~/.claude/dev-mods/`. `~/.claude/settings.json` loads this folder through `CLAUDE_CODE_PLUGIN_DIRS`, so saved edits reload in running sessions.

After changing it:

1. `claude plugin validate plugins/session-files` and `claude plugin test plugins/session-files`
2. Bump `version` in `plugins/session-files/.claude-plugin/plugin.json` so installed copies see an update
3. Commit, and push to `main` when the user asks
