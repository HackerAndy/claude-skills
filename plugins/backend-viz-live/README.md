# backend-viz-live

A Claude Code mod that adds a **Backend map** pane and a status line showing API contract coverage, endpoints still to build, off-contract endpoints, layer violations and untraced functions. It refreshes after every edit and links to the full dashboard.

It displays the report the [`backend-viz`](../backend-viz) plugin writes, so install both:

```
/plugin install backend-viz --marketplace HackerAndy/claude-skills
/plugin install backend-viz-live --marketplace HackerAndy/claude-skills
```

The pane opens by itself in a project that has a `.backend-viz/report.json`; `/backend-live` opens it any time. Run `/backend-viz` first in a new project.
