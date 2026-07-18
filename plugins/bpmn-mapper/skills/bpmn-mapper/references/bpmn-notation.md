# BPMN 2.0 Notation & Process Definition Schema

This reference is the authority for two things: (1) what the BPMN 2.0 symbols
*mean*, so the diagram is correct and not just pretty, and (2) the exact JSON
schema that `scripts/render_bpmn.py` consumes. Read the schema section before
writing a definition; skim the semantics section whenever you're unsure which
symbol a real-world step maps to.

## Table of contents
- [Why notation discipline matters](#why-notation-discipline-matters)
- [The four core symbol families](#the-four-core-symbol-families)
- [Events](#events)
- [Activities (tasks & sub-processes)](#activities-tasks--sub-processes)
- [Gateways](#gateways)
- [Connecting objects](#connecting-objects)
- [Pools & lanes](#pools--lanes)
- [Data objects](#data-objects)
- [JSON schema for render_bpmn.py](#json-schema-for-render_bpmnpy)
- [Layout guidance](#layout-guidance)
- [Common modeling mistakes to avoid](#common-modeling-mistakes-to-avoid)
- [Worked example](#worked-example)

## Why notation discipline matters

BPMN's value is that a controller in Stuttgart and an analyst in Ohio read the
same diagram the same way. That only holds if the symbols are used *by the
book*. A circle is not a decision; a diamond is not a step. When you convert a
prose description into a model, your main job is disciplined mapping: each
sentence becomes the *correct* element type, handoffs between people/systems
become lane changes, and every "if / whether / depending on" becomes a gateway
with labelled outgoing branches. Getting this right is what separates a real
process model from a generic flowchart.

## The four core symbol families

| Family | Shape | Represents |
|---|---|---|
| Event | Circle | Something that *happens* (start, intermediate, end) |
| Activity | Rounded rectangle | *Work* that is performed (task or sub-process) |
| Gateway | Diamond | A *branch or merge* in the flow (decision / parallelism) |
| Connecting | Arrow | The *order* of, or communication between, the above |

## Events

Events are circles. The border weight encodes *when in the lifecycle* the event
sits; an optional inner glyph encodes *what kind* of trigger it is.

- **Start event** — thin single border. Where a process instance begins. Every
  pool that does work should have exactly one obvious start (occasionally more
  when there are genuinely independent triggers).
- **Intermediate event** — double thin border. Something that happens *during*
  the flow: waiting for a message, a timer elapsing, catching an error.
- **End event** — thick single border. A terminal state of the process. Use
  distinct end events for distinct outcomes ("Order shipped" vs "Order
  cancelled") rather than funneling everything into one.

Optional `event_type` glyphs: `message` (envelope), `timer` (clock), `error`
(jagged bolt), `signal` (triangle). Use them when the trigger type is material
to understanding the process; leave blank for a plain (none) event.

## Activities (tasks & sub-processes)

A task is a rounded rectangle — a single unit of work. Give every task a
**verb-object** label ("Approve invoice", "Send confirmation"), never a bare
noun. The optional `task_type` marker (top-left glyph) tells the reader *who or
what* performs it:

- `user` — a human doing work with a system in the loop (person glyph)
- `manual` — a human doing work with no system (hand glyph)
- `service` — automated/system work, e.g. an API call (gears glyph)
- `script` — an engine runs a script (script glyph)
- `send` / `receive` — the task's purpose is to send/receive a message

A **sub-process** (`type: subprocess`) is a rounded rectangle with a small `+`
marker at the bottom — it stands for a whole nested process collapsed to one
box. Use it to keep a top-level map readable, then optionally model the interior
as its own diagram.

## Gateways

Gateways are diamonds. They control divergence and convergence of flow. The
inner marker is not decoration — it changes the execution meaning:

- **Exclusive (XOR)** — `X` marker. Exactly *one* outgoing path is taken. This
  is the everyday "decision". Every outgoing branch **must** carry a condition
  label ("Approved" / "Rejected"). Pose the gateway itself as a question
  ("Amount > $5k?").
- **Parallel (AND)** — `+` marker. *All* outgoing paths run concurrently; no
  conditions. Used to fork work that happens at the same time and to join it
  back (wait for all).
- **Inclusive (OR)** — `O` marker. One *or more* paths may run, each with its
  own condition. Powerful but easy to misuse — prefer exclusive or parallel
  unless the process genuinely needs "any subset".
- **Event-based** — double-circle marker. The path taken depends on *which
  event occurs first* (e.g. reply received vs timeout), not on data.

Golden rule: a gateway that splits should be matched by a gateway that merges
of the same type. Don't let a parallel fork be joined by an exclusive gateway.

## Connecting objects

- **Sequence flow** — solid line, solid arrowhead. Order of steps *within a
  single pool*. Never cross a pool boundary with a sequence flow.
- **Message flow** — dashed line, open circle at source and open arrowhead at
  target. Communication *between* pools (two participants). Use `type:
  "message"` in the flow.
- **Association** — dotted line (used to attach a data object to a step;
  handled implicitly here by placing data objects near their task).

## Pools & lanes

A **pool** is a participant — a whole organization or system boundary (e.g.
"Customer", "Our Company"). **Lanes** subdivide a pool by role, department, or
system ("Sales", "Warehouse", "Billing"). The single most useful modeling act
is putting each activity in the lane of whoever performs it: the lane crossings
then make every handoff visible, which is usually where delay and error live.

When there are two independent participants that *communicate* (you and an
external customer/vendor), model them as **two pools** connected by message
flows. When it's all one organization with internal roles, use **one pool with
lanes**.

## Data objects

A **data object** (`type: "data"`) is a dog-eared page representing an
information artifact a step reads or produces ("Signed contract", "Invoice
PDF"). Optional but valuable when a document is central to the process.

## JSON schema for render_bpmn.py

```jsonc
{
  "title": "string — diagram heading (optional)",
  "pool": "string — pool/participant label shown on the left (optional)",
  "lane_height": 130,          // px per lane; raise if labels wrap (optional, default 120)
  "lanes": [                   // top-to-bottom order = drawing order
    {"id": "sales", "label": "Sales"},
    {"id": "wh",    "label": "Warehouse"}
  ],
  "nodes": [
    {
      "id": "unique_id",       // referenced by flows
      "type": "event|task|subprocess|gateway|data",
      "lane": "sales",         // which lane id it sits in
      "col": 0,                // horizontal grid step (0,1,2...; fractions ok)
      "row": 0,                // optional vertical nudge within lane (±1, ±2...)
      "label": "Verb object",

      // event-only:
      "kind": "start|intermediate|end",
      "event_type": "message|timer|error|signal",   // optional glyph

      // task-only:
      "task_type": "user|manual|service|script|send|receive",  // optional glyph

      // gateway-only:
      "gateway_type": "exclusive|parallel|inclusive|event"
    }
  ],
  "flows": [
    {"from": "id1", "to": "id2", "label": "condition (optional)"},
    {"from": "id3", "to": "id4", "type": "message"},   // dashed, cross-pool
    {"from": "a", "to": "b", "waypoints": [[x,y],[x,y]]}  // manual routing (rare)
  ]
}
```

### Multi-pool collaborations (two or more participants)

When the process involves two participants that *communicate* — e.g. your
organization and an external customer or vendor — model them as **separate
pools** joined by message flows, not lanes. Supply a top-level `pools` array
instead of `pool`/`lanes`; each pool has its own `lanes`. The renderer stacks
the pools vertically with a gap and routes `type: "message"` flows between them.

```jsonc
{
  "title": "Order Fulfilment",
  "lane_height": 120,
  "pools": [
    {"id": "cust", "label": "Customer",
     "lanes": [{"id": "cust", "label": ""}]},
    {"id": "co", "label": "Our Company",
     "lanes": [
       {"id": "sales", "label": "Sales"},
       {"id": "wh",    "label": "Warehouse"}
     ]}
  ],
  "nodes": [ /* each node's "lane" is a lane id from either pool */ ],
  "flows": [
    {"from": "place_order", "to": "confirm", "type": "message", "label": "Order"},
    {"from": "confirm", "to": "pick", "type": "sequence"}
  ]
}
```

Rules that keep it valid: sequence flows stay *within* a pool; anything crossing
a pool boundary must be `type: "message"` (dashed). A pool with a single
unlabelled lane just shows the participant as one band. Single-pool definitions
keep using `pool`/`lanes` exactly as before — only reach for `pools` when there
are genuinely two-plus communicating participants.

Notes:
- `col` drives horizontal position; keep the flow generally left-to-right by
  giving each downstream node a higher `col`. It's fine for two branches to
  share a `col` in different lanes.
- A single actor with two independent triggers (e.g. a weekly timer *and* a
  monthly message) can be shown as two separate flows in one lane, each with its
  own start and end event — that's valid and often the honest picture.
- The renderer auto-routes flows with orthogonal elbows and auto-places branch
  labels on the longest segment. Only supply `waypoints` if a specific flow
  overlaps something.
- Increase `lane_height` (e.g. 150) if you have tall content or wrapping labels.

## Layout guidance

1. **Left to right, top to bottom.** Time flows rightward. Assign `col` in the
   order steps happen.
2. **One lane per role.** Decide the participants first, then drop each step in
   its performer's lane. Lane crossings = handoffs; that's the point.
3. **Give branches room.** When an exclusive gateway splits, put the two
   outcomes in different lanes or different `row` offsets so the paths don't sit
   on top of each other, then converge them at a later `col`.
4. **Label every exclusive/inclusive branch.** An unlabelled decision branch is
   a modeling error.
5. **Keep the happy path straight.** Route the normal/expected path as a clean
   horizontal spine; let exceptions dip above or below it.

## Common modeling mistakes to avoid

- Using a gateway as an activity (a diamond never "does" anything — it only
  routes). Work goes in a task; the decision that follows goes in a gateway.
- Sequence flow crossing a pool boundary (must be a message flow instead).
- Splitting with parallel `+` but merging with exclusive `X` (or vice-versa).
- Noun-only task labels ("Invoice" → should be "Issue invoice").
- One giant "end" for many different outcomes — model distinct end events.
- Decisions with unlabelled Yes/No branches.

## Worked example

Prose: *"When a support ticket arrives, an agent triages it. If it's a bug it
goes to Engineering to fix; otherwise the agent answers directly. Either way the
ticket is closed."*

```json
{
  "title": "Support Ticket Handling",
  "pool": "Support Org",
  "lanes": [
    {"id": "agent", "label": "Support Agent"},
    {"id": "eng",   "label": "Engineering"}
  ],
  "nodes": [
    {"id": "s",  "type": "event",   "kind": "start", "event_type": "message", "label": "Ticket received", "lane": "agent", "col": 0},
    {"id": "t1", "type": "task",    "task_type": "user", "label": "Triage ticket", "lane": "agent", "col": 1},
    {"id": "g",  "type": "gateway", "gateway_type": "exclusive", "label": "Is it a bug?", "lane": "agent", "col": 2},
    {"id": "t2", "type": "task",    "task_type": "user", "label": "Fix defect", "lane": "eng", "col": 3},
    {"id": "t3", "type": "task",    "task_type": "user", "label": "Answer customer", "lane": "agent", "col": 3},
    {"id": "m",  "type": "gateway", "gateway_type": "exclusive", "lane": "agent", "col": 4},
    {"id": "e",  "type": "event",   "kind": "end", "label": "Ticket closed", "lane": "agent", "col": 5}
  ],
  "flows": [
    {"from": "s",  "to": "t1"},
    {"from": "t1", "to": "g"},
    {"from": "g",  "to": "t2", "label": "Yes"},
    {"from": "g",  "to": "t3", "label": "No"},
    {"from": "t2", "to": "m"},
    {"from": "t3", "to": "m"},
    {"from": "m",  "to": "e"}
  ]
}
```

Note how "if it's a bug" became an exclusive gateway with labelled branches,
"Engineering" became its own lane so the handoff is visible, and the two paths
re-converge at a merge gateway before the single end event.
