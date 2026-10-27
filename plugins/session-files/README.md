# session-files

A Claude Code mod that adds a **Files** pane beside the chat. It shows your project's file tree and highlights:

- **●** files Claude edited in this session (bold, in Claude's color)
- git status for each file: **M** modified · **U** new · **A** added · **R** renamed · **D** deleted · **!** conflict
- a dot on any folder with changes inside

The pane opens when a session starts and refreshes every few seconds and after each edit or shell command. Press **v** to show only changed files, **r** to refresh, and click a folder to collapse it. `/files` reopens the pane if you close it. Outside a git repo it lists the folder's files and highlights only Claude's edits.

## Install

At the prompt of a Claude Code terminal session:

```
/plugin install session-files --marketplace HackerAndy/claude-skills
```

Answer `y` to add the marketplace, then pick a scope (user scope loads it in every session).

From a shell:

```bash
claude plugin install session-files --marketplace HackerAndy/claude-skills
```

In the Claude desktop app, where `/plugin` doesn't run: click **+** next to the prompt box, then **Plugins** → **Add marketplace** with `HackerAndy/claude-skills`, then **Add plugin**. A mod installed at user scope from a terminal also loads in the desktop app.

## Develop

```bash
claude plugin validate plugins/session-files
claude plugin test plugins/session-files
```
