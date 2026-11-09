# code-quality-live

A pane in Claude Code beside the chat with the code-quality scores, plus the approved share in the status line. Needs the `code-quality` plugin and a project that has run `quality-gate report` once; every check after that keeps it current.

- **Overview:** share of functions approved, a green / yellow / red bar (90% and up, 70–89%, below 70%), whether the gate is clean, what to fix first, and the folders that need work.
- **Drill down:** press a folder, then a file, then a function. A function shows how its score was worked out, each issue in a line or two, and the lines causing it: the places that add a path in yellow (`+1` each), lint in red.
- `/quality-live` opens it; `/quality-live <path>` looks at another project. "Open the full report" opens `.quality/report.html`.

It refreshes after each edit Claude makes (the gate's hook rewrites `.quality/report.json`).

```
/plugin install code-quality-live --marketplace HackerAndy/claude-skills
```
