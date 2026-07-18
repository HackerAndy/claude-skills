---
name: bpmn-mapper
description: >-
  Turn any described business process into a standards-compliant BPMN 2.0
  diagram rendered as a clean SVG image (with pools, swimlanes, events, tasks,
  and gateways). Use this skill whenever the user wants to map, model, diagram,
  or document a business process, workflow, or procedure — including phrases
  like "map this process", "create a process flow", "draw a swimlane diagram",
  "model our approval workflow", "turn this SOP into a diagram", "BPMN", "process
  map", "as-is / to-be process", or when they describe a sequence of steps with
  handoffs, decisions, or approvals and want it visualized. Also trigger when a
  user uploads or pastes a procedure/SOP and asks to diagram it, or asks for a
  cross-functional flowchart of who does what. Prefer this skill over a generic
  flowchart whenever the process involves multiple roles, decisions, or
  handoffs, so the output follows real BPMN conventions rather than ad-hoc boxes.
---

# BPMN Mapper

Convert a described business process into a **standards-compliant BPMN 2.0
diagram**, output as a self-contained SVG image (rasterizable to PNG for slides
and docs). The goal is a model that anyone fluent in BPMN reads correctly — the
right symbol for each step, roles as swimlanes, decisions as gateways with
labelled branches — not a generic boxes-and-arrows flowchart.

## When to reach for this

Any time someone wants to see a process visually: approval workflows, onboarding,
order-to-cash, incident handling, an SOP, an "as-is vs to-be" comparison, or
just "how does this actually work step by step". If they mention BPMN, swimlanes,
process maps, or describe steps with handoffs and decisions, this is the tool.

## The workflow

Producing a *correct* model is mostly about disciplined translation from prose to
notation. Follow these steps in order.

### 1. Facilitate the intake — be a mentor, not a form

Most people know their own work cold but don't know BPMN, and they almost never
volunteer everything a model needs in the shape it needs. So your first job is
not to transcribe — it's to *facilitate*: draw out a complete, correctly-scoped
picture through conversation, and actively judge the *quality* of each answer as
it comes in. A good facilitator makes the user feel guided and understood, and
quietly does the modeling thinking on their behalf.

Read `references/elicitation-playbook.md` for the full question bank, the
BPMN-completeness checklist, and worked examples. The core stance:

**Open by reflecting, not interrogating.** Start from whatever the user gave you
and play it back as a short numbered skeleton ("Here's what I've got so far —
tell me where I'm wrong"). This anchors the conversation, feels collaborative,
and surfaces gaps far more cheaply than a wall of questions. Then ask in small,
focused rounds — one theme at a time, prioritizing the questions that actually
change the diagram's structure (roles, triggers, decisions, end states). Prefer
concrete questions over abstract ones: "When the manager rejects it, where does
it go — back to the employee, or somewhere else?" beats "Any exceptions?"

**Diagnose every answer against these four failure modes** — this is what makes
the skill a mentor rather than a transcriptionist:

1. **Gaps / incomplete.** Watch for a decision with only one named outcome, a
   step whose actor is unnamed, a process with no clear trigger or no end state,
   a handoff to a role that then disappears, or a document nobody produces or
   consumes. Don't quietly invent the missing piece — name the specific gap and
   ask the pinpoint question ("You said it's reviewed — reviewed by whom?" /
   "What happens when it's *not* approved?"). A model with silent gaps is worse
   than one with an honest open question.

2. **Doesn't apply / off-target.** Sometimes the user offers things that aren't
   process structure — tool brand names, org history, internal politics, a
   wish-list of improvements. Acknowledge it warmly, then park it: note it as an
   annotation or "out of scope for the diagram" and steer back to the flow.
   Forcing irrelevant input into boxes clutters the model and confuses readers.

3. **Needs a deeper dive.** Vague verbs ("it gets processed", "we handle it",
   "the system does its thing") and passive voice that hides the actor are
   signals that a single phrase is concealing multiple steps or a hidden
   decision. Probe one level down: who does it, what triggers the next step,
   what can go wrong. If it's genuinely a large chunk of work, offer to model it
   as a **sub-process** — collapse it to one box now, and optionally expand it
   into its own diagram later.

4. **Too much detail.** The opposite problem: keystroke- or field-level
   description, UI navigation, validation minutiae — steps that don't change who
   is acting or branch the flow. Gently abstract up to the altitude a reader
   actually needs, collapsing a run of micro-steps into one meaningful task (or
   a sub-process). Reassure the user the detail isn't lost — it just lives a
   level down. Keep the top-level map at "a new manager could follow this"
   granularity.

**Find the right altitude.** A reliable rule of thumb: one task = one meaningful
state change performed by one actor. If two adjacent steps are the same person
with no decision and no handoff between them, they're probably one task. If one
"step" spans multiple actors or hides an "if", it's probably several.

**Confirm before you draw.** Once the picture feels complete, reflect the final
structure back as a compact skeleton — roles, trigger, happy path, each decision
with its branches, and the end state(s) — and get a yes. Correcting text is
cheap; redrawing is not.

**Adapt to the user.** If they say "just draft something reasonable, I'll fix
it," don't force an interview — make sensible assumptions, draw it, and call out
each assumption so they can correct fast. Match their pace: a detailed SOP needs
mostly trimming and confirmation; a two-line description needs patient drawing-out.
The mentoring should feel like help, never like a gate.

### 2. Map prose to the correct BPMN elements

This is the core skill. Read `references/bpmn-notation.md` for full semantics;
the essentials:

- A unit of **work** → task (rounded rectangle), labelled **verb-object**. Tag
  `task_type` (`user`/`service`/`manual`/etc.) when who-does-it matters.
- A **decision / branch** → gateway (diamond). Everyday either/or is
  `exclusive`; simultaneous work is `parallel`; race-between-events is `event`.
  Phrase exclusive gateways as a question and **label every outgoing branch**.
- Something that **happens** → event (circle): one `start`, distinct `end`
  events per outcome, `intermediate` for waits/messages/timers mid-flow.
- Each **role** → a lane; each step goes in its performer's lane so **handoffs
  are visible**. An external participant that only exchanges messages → a
  separate pool joined by `message` flows.

Don't reduce everything to plain tasks and yes/no diamonds — using the right
specialized symbol is what makes it BPMN and not a flowchart.

### 3. Write the process definition JSON

Author a JSON definition matching the schema in `references/bpmn-notation.md`
(§ "JSON schema for render_bpmn.py"). Practical tips:

- Order steps left-to-right by assigning increasing `col` values.
- Put each node in the correct `lane`; list lanes top-to-bottom in reading order.
- Give branch flows a `label` (the condition). Converge branches at a later
  `col`, ideally via a merge gateway of the same type as the split.
- Keep the happy path as a straight horizontal spine; dip exceptions above/below
  using different lanes or a `row` offset.

Save it to the working directory, e.g. `process.json`.

### 4. Render the SVG (and PNG)

Use the bundled renderer — it handles all geometry, lane sizing, arrow routing,
and branch-label placement, so you never hand-write SVG coordinates:

```bash
python3 scripts/render_bpmn.py process.json -o process.svg
```

Then rasterize to PNG so it drops cleanly into decks and Word docs (and so you
can view it to check quality):

```bash
python3 -c "import cairosvg; cairosvg.svg2png(url='process.svg', write_to='process.png', output_width=1600)"
```

If `cairosvg` isn't installed: `pip install cairosvg --break-system-packages -q`.
Fallbacks if that's unavailable: `rsvg-convert process.svg -o process.png` or
`inkscape process.svg --export-filename=process.png`.

### 5. Verify the model, not just that it rendered

Always view the PNG and check it as a *model*, not just an image:

- Every decision branch is labelled; the happy path reads clearly left-to-right.
- Splits and merges use matching gateway types; parallel forks rejoin.
- Each step sits in the right role's lane; handoffs land on lane boundaries.
- No sequence flow crosses a pool boundary (that must be a message flow).
- Labels are verb-object and not truncated (raise `lane_height` or shorten
  labels if text is cramped).

Fix the JSON and re-render rather than editing the SVG by hand. If the user
wanted it inside a deliverable, embed the PNG in the docx/pptx (use those skills)
after the diagram is right.

## Output

Deliver the SVG (crisp at any scale, editable) plus a PNG (for pasting), and a
one-line note of any assumptions you made. Offer the process.json too — it's the
editable source, so revisions are a JSON tweak and a re-render, not a redraw.

## Reference

- `references/elicitation-playbook.md` — how to run the intake as a mentor: the
  BPMN-completeness checklist, a probing-question bank, worked examples of the
  four answer-quality diagnostics (gap / off-target / deeper-dive / over-detail),
  and a sample facilitation dialogue. Read it when gathering requirements.
- `references/bpmn-notation.md` — full BPMN 2.0 symbol semantics, the JSON
  schema, layout guidance, common mistakes, and a worked prose→JSON example.
  Read it before writing your first definition.
- `scripts/render_bpmn.py` — the JSON→SVG renderer. Don't reinvent it; extend it
  only if a genuinely new element type is needed.
