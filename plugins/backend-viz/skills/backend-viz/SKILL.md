---
name: backend-viz
description: Contract-first, visual backend development for FastAPI and Node (Express/Fastify). Use when the user wants to design, build, review or visualize a backend or API; asks to "init backend-viz", "show the backend map", "mock the API", "check drift", "trace requests"; or when working in a project that has a design/ folder with openapi.yaml + architecture.yaml. Also use whenever adding, changing or removing an API endpoint in such a project.
---

# backend-viz

The user is a visual thinker. The backend is built like a frontend:
**contract = wireframe, mock server = mock data, map + traces = the running UI.**
`design/` is the source of truth for *what* is built; code is checked against it after every edit.

Script: `scripts/backend_map.py` in this skill's base directory (call it `$BV` below).
Run it with `python3` (or `python` on Windows). Requires PyYAML for YAML files.

## Commands (the user may type `/backend-viz <action>`)

The user should only ever need two things: `/backend-viz` here and `backend-viz live` in a terminal. Do the rest for them.

| Action | Do |
|---|---|
| *(none)* / `map` | Run `python3 $BV` in the project (or monorepo) root. It sets up whatever is missing (design/ files, tracer, middleware, `@traced` on existing functions, sub-folder skills) and prints a summary. Then `python3 $BV --open`, and report in 3 lines: what setup did (if anything), coverage, what's broken. If `design/` was just created, read the project, adjust the layer globs in `design/architecture.yaml` to its real folders and confirm them with the user; draft `design/openapi.yaml` from existing endpoints. If the computer is remote, send `.backend-viz/dashboard.html` as a file. |
| `live` | Start `python3 $BV live` in the background (it serves http://localhost:8765 and updates every 2s) and give the user the link. Remind them to run their API and use the app. |
| `traces [n]` | `python3 $BV traces n`: the last n requests as call trees (layer, ms, data ids, errors). Use it yourself to verify what actually ran after building or changing something. |
| `mock` | Tell the user to run `npx @stoplight/prism-cli mock design/openapi.yaml` (fake responses on :4010 from the contract's examples). Add `example:` blocks where missing. |
| `rules` | Show/edit `design/architecture.yaml` with the user. |

## Workflow rules (always, in a project with `design/`)

1. **Contract first.** Before writing a new endpoint, add it to `design/openapi.yaml` (path, method, summary, tag, request/response schemas, one `example`). If the design is ambiguous, ask; don't invent API shape silently.
2. **Respect layers.** Each file belongs to the first layer in `design/architecture.yaml` whose glob matches. A layer may import only itself + its `may_depend_on`. Put new files in the folder of the right layer; create the folder if missing.
3. **Drift feedback.** A PostToolUse hook runs `$BV --hook` after every Write/Edit. If it reports layer violations or off-contract endpoints, fix them before moving on (move logic down a layer, or update the contract after confirming with the user). Never weaken `architecture.yaml` rules to silence the hook without the user's OK.
4. **Build in vertical slices.** One endpoint at a time: contract → schema → repository → service → route → test. After each slice, run `$BV` and report the new coverage in one line.
5. Keep schemas (Pydantic / zod) mirroring the contract's components.

## Runtime tracing (built in)

Every public function in the layers listed under `tracing.required_in` must be traced; the drift hook lists the ones that aren't.

```python
from app.trace import traced, data, link

@traced                       # one span per call: layer, args, result, ms, errors
def organize(source_id): ...  # args ending in _id/_ids are tagged as data ids automatically

@traced
class OrganizeService: ...    # traces every public method

data("payment:p1")                       # tag the current call with a data id ("kind:id")
link("payment:p1", "row:r1", "tidied")   # lineage: this became that (use at every tier boundary)
```

- One trace per HTTP request (`TraceMiddleware`); background jobs/event handlers open one with `with span("job name"):`.
- Spans go to `.backend-viz/traces/spans.jsonl`. Vault modules and secret-looking args are redacted automatically. `BACKEND_VIZ_TRACE=0` turns it off.
- Dashboard: **Traces** (waterfall per request, click a bar for args/result/data), **Data journey** (one id across layers and what it became), **Functions** (traced?, calls, avg ms, errors, never ran), call counts on the endpoint list and architecture map.
- After building a slice: exercise it (test or curl), run `--traces 3`, and check the tree matches the intended path through the layers.

## External tracing (optional)

Run Jaeger locally: `docker run -d --name jaeger -p 16686:16686 -p 4317:4317 -p 4318:4318 jaegertracing/all-in-one`

- FastAPI: `pip install opentelemetry-distro opentelemetry-exporter-otlp && opentelemetry-bootstrap -a install`, then run
  `OTEL_SERVICE_NAME=<api> OTEL_TRACES_EXPORTER=otlp opentelemetry-instrument uvicorn app.main:app`
- Node: `npm i @opentelemetry/api @opentelemetry/auto-instrumentations-node`, then run
  `OTEL_SERVICE_NAME=<api> OTEL_TRACES_EXPORTER=otlp node --require @opentelemetry/auto-instrumentations-node/register src/server.js`

Only needed for production-style tracing; the built-in tracer covers development. Open http://localhost:16686 → each request shows as a waterfall: route → service → DB calls. Compare it with the dashboard's request-flow view for the same endpoint.

## Limits

Runtime tracing is Python only for now (Node would need a matching tracer writing the same spans.jsonl). Static analysis, best effort: FastAPI `APIRouter`/`include_router` prefixes and Express/Fastify `Router()` + `app.use('/prefix', router)` mounts are resolved one or two levels deep. Dynamic route registration isn't seen. Tell the user when an endpoint they expect is missing from the map rather than guessing.
