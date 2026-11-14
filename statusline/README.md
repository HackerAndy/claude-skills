# statusline

A Claude Code status line: the folder name in bold, the git branch in blue and the model in violet, for example **claude-skills** · main · Opus 5.5. The branch is left out outside a git repository.

It isn't a plugin, because plugins can't set the status line. To use it, point `statusLine` in `~/.claude/settings.json` at the script:

```json
"statusLine": { "type": "command", "command": "/path/to/claude-skills/statusline/statusline.sh" }
```

Colors are 256-color codes in the script: `75` for the branch, `177` for the model. It needs `bash`, `git` and `python3`.
