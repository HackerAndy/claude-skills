# backend-viz

Build backends the way you build frontends: **contract = wireframe, mock server = mock data, live map = the screen.** For FastAPI and Node (Express/Fastify).

| Plugin | What you get |
|---|---|
| `backend-viz` | `/backend-viz` skill (contract-first rules for Claude), drift hook after every edit, visual dashboard |
| [`backend-viz-live`](../backend-viz-live) | Mod: live **Backend map** pane + status line inside Claude Code (`/backend-live`) |

## Install

At the prompt of a Claude Code terminal session:

```
/plugin install backend-viz --marketplace HackerAndy/claude-skills
/plugin install backend-viz-live --marketplace HackerAndy/claude-skills
```

Answer `y` to add the marketplace, then pick a scope (user scope = every project). In the Claude desktop app: click **+** next to the prompt box → **Plugins** → **Add marketplace** with `HackerAndy/claude-skills`, then add both plugins.

Requires Python 3 and `pip3 install pyyaml`.

Optional CLI, from a clone of this repo: `ln -s "$(pwd)/plugins/backend-viz/bin/backend-viz" ~/.local/bin/backend-viz`

A project opts in by having a `design/` folder (`/backend-viz init`). Per project you keep only `design/openapi.yaml`, `design/architecture.yaml` and, if you trace, `app/trace/`.

## Use

| Where | Type | What happens |
|---|---|---|
| Claude Code (CLI or desktop) | `/backend-viz` | Sets up the project if needed (contract + layer files, tracer, middleware, `@traced` everywhere), then shows the map and what's broken |
| Terminal | `backend-viz live` | Live dashboard at http://localhost:8765: run your API, use the app, watch requests flow |

Everything else is automatic: after every edit Claude is told about layer breaks, endpoints missing from the contract and untraced functions, and fixes them. More: `/backend-viz traces 3`, `/backend-live` (in-app pane).

## Dashboard

One screen, built for someone seeing the backend for the first time:

- **User actions** (left): each click or form submit that reached the backend, newest first; failed ones in red. Send an `X-User-Action: Clicked Place order` header from the frontend and the list uses that name instead of the endpoint.
- **The map** (right): every file in its layer column. The selected action lights up the files it ran, with numbered arrows in the order they ran; files it did not use stay grey. Red dashed = an import that breaks a layer rule.
- **Step by step** (under the map): the same numbers as the arrows, with timing; click a step for its inputs, result and error.
- **All endpoints** tab: built / not built yet / not in contract; pick one that has not run to see the files its code imports.
- **Things to fix** (bottom): rule breaks, failed actions, off-contract and missing endpoints, untraced functions.

Try it on the demos: `bin/backend-viz --root examples/fastapi-demo --open`

Opt-in per project: nothing runs unless the project has a `design/` folder (monorepos work: the hook walks up from the edited file).
