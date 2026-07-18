# Elicitation Playbook — Facilitating the Intake Like a Mentor

The diagram is only as good as the conversation that produced it. This playbook
is the "how to interview" companion to the notation reference. Use it whenever
you're gathering a process from someone: it gives you the completeness checklist
to aim for, the questions that get there, and — most importantly — how to
*diagnose the quality of each answer* so you catch gaps, off-target input,
under-explained steps, and over-detailed steps in real time.

The mindset: **you are the modeling expert; the user is the domain expert.**
They know what happens; you know how to shape it into a correct, well-scoped
model. Carry that weight for them. They should feel guided, never quizzed.

## Table of contents
- [The completeness checklist](#the-completeness-checklist)
- [How to run the conversation](#how-to-run-the-conversation)
- [The question bank](#the-question-bank)
- [Diagnosing answer quality (the four modes)](#diagnosing-answer-quality-the-four-modes)
- [Finding the right altitude](#finding-the-right-altitude)
- [Confirming before you draw](#confirming-before-you-draw)
- [A sample facilitation dialogue](#a-sample-facilitation-dialogue)

## The completeness checklist

Before a process can be drawn correctly, you need clear answers to all of these.
Treat any that's still fuzzy as an open question to resolve — not a blank to
guess. This is your internal "definition of done" for intake.

- **Trigger** — what single event starts the process? (becomes the start event)
- **Participants & roles** — every distinct who/what that acts. (lanes, or pools
  for external parties that communicate with the org)
- **The happy path** — the ordered sequence of steps when everything goes right.
- **Decisions** — every branch point, *with every outcome named and labelled.* A
  decision with one outcome is not yet a decision.
- **Handoffs** — where work passes between roles (these are the lane crossings,
  and usually where the real risk lives).
- **Exceptions & rework** — what happens when something fails, is rejected, or
  loops back — *if* the user wants those shown.
- **End state(s)** — the distinct ways the process can finish. (distinct end
  events; don't funnel different outcomes into one)
- **Scope boundaries** — where this process starts and stops, and what's
  explicitly out of scope.

## How to run the conversation

1. **Reflect first.** Restate whatever you were given as a short numbered
   skeleton and invite correction. This feels collaborative and exposes gaps
   cheaply. Example: *"Here's what I've picked up — (1) a customer submits X,
   (2) someone reviews it, (3) it's either approved or sent back. Tell me where
   that's off."*
2. **Ask in small rounds.** One theme per round (first roles, then decisions,
   then exceptions), not a 20-question wall. Lead with structure-changing
   questions.
3. **Prefer concrete over abstract.** "Any exceptions?" gets a shrug; "What
   happens if the credit check fails?" gets an answer.
4. **Translate, don't jargon-dump.** Say "a decision point" not "an exclusive
   gateway." Introduce BPMN terms only if the user wants them.
5. **Explain the why when you probe.** "I'm asking because a decision needs at
   least two outcomes to draw — what happens when it's *not* approved?" People
   answer better when they see the point of the question.

## The question bank

Pull from these as needed — don't read them all out.

**Trigger & scope**
- "What kicks this off — what has to happen for the process to start?"
- "Where should the diagram stop? What's the last thing that happens?"
- "Is anything deliberately out of scope here?"

**Roles & handoffs**
- "Who actually does this step?" (for any step with an unnamed actor)
- "When it leaves [role], who picks it up next?"
- "Is [external party] inside your organization, or a separate company you send
  things to?" (decides lane vs. separate pool)

**Decisions**
- "You mentioned it depends on X — what are the possible answers, and what
  happens for each?"
- "Is that an either/or, or can several of these happen at once?" (exclusive vs.
  parallel)
- "Do those two paths ever come back together? Where?"

**Exceptions & rework**
- "What happens when that fails / is rejected / times out?"
- "Does it loop back somewhere, or end there?"
- "Do you want the diagram to show the exception paths, or just the normal flow?"

**Level of detail**
- "Is that one action, or a few smaller ones? Do we need to see the smaller
  ones, or is the summary enough?"
- "Would it help to show that as a single box now and detail it separately
  later?" (sub-process offer)

## Diagnosing answer quality (the four modes)

This is the heart of mentoring. As each answer arrives, silently classify it and
respond accordingly. Most answers are fine — but catching the ones that aren't,
in the moment, is what produces a correct, right-sized model.

### 1. Gap / incomplete — *name it, ask the pinpoint question*

**Signals:** a decision with only one outcome named; "it gets reviewed" with no
reviewer; no stated trigger or no end; a role that receives a handoff and then
never appears again; a mentioned artifact with no producer or consumer.

**Response:** point at the specific hole and ask one precise question. Never
paper over it with an assumption.

> User: "Finance approves the invoice and it gets paid."
> You: "Got it — and if Finance *doesn't* approve it, what happens to the
> invoice? Does it go back to the requester, or get cancelled?"

### 2. Off-target / doesn't apply — *acknowledge, park, redirect*

**Signals:** answers that aren't process structure — the name of the software
they use, why the process exists, who they dislike doing it, improvement ideas
("honestly we should automate this").

**Response:** validate it, capture it as a note or mark it out of scope, and
guide back to the flow. Don't manufacture a box for it.

> User: "We use SAP for this and honestly it's a nightmare, we've been asking
> for a new system for years."
> You: "Noted — I'll jot 'system: SAP' as context and we can flag the pain point
> separately. For the flow itself: once the order's in SAP, what's the next
> thing that happens, and who does it?"

### 3. Needs a deeper dive — *probe one level, or offer a sub-process*

**Signals:** vague verbs ("we process it," "the system handles it," "it gets
sorted out"); passive voice hiding the actor; a single step that clearly can't
be atomic.

**Response:** ask what's actually happening underneath — who, what next, what can
go wrong. If it's genuinely a big chunk, offer to collapse it into a sub-process
box and optionally model its interior separately.

> User: "Then the application just gets processed."
> You: "Let's unpack 'processed' a bit — what actually happens between it
> arriving and a decision coming out? For instance, does someone verify the
> documents, run a check, score it? If it's several steps, I can show it as one
> 'Process application' box now and we detail it in its own diagram later."

### 4. Too much detail — *abstract up, reassure*

**Signals:** keystroke- or field-level narration ("click Save, then tab to the
amount field, enter the value, click Submit"); UI navigation; validation minutiae;
a string of micro-steps by the same actor with no decision between them.

**Response:** roll them up to the altitude a reader needs, and reassure the user
the detail is captured, just a level down. A top-level map should read at "a new
manager could follow it," not "a data-entry script."

> User: "They open the record, click Edit, change the status dropdown to
> Approved, add a comment, click Save, then click Send Notification..."
> You: "That's all part of one meaningful action — I'll capture it as a single
> 'Approve and notify' task so the map stays readable. The click-by-click detail
> belongs in the work instruction, not the process diagram; nothing's lost. Does
> anything in that sequence *branch* — a point where it might go a different way?"

## Finding the right altitude

When you're unsure whether something is one step or several, apply: **one task =
one meaningful state change performed by one actor.**

- Same actor, no decision, no handoff between two steps → probably **one** task.
- A "step" that spans multiple actors, or contains an "if" → probably **several**
  (and maybe a gateway).
- A "step" that's really a whole workflow of its own → a **sub-process**.

Aim for a top-level map of roughly 5–15 activities. Fewer and it's probably too
abstract to be useful; many more and you're likely modeling detail that belongs
in sub-processes or work instructions.

## Confirming before you draw

Before generating JSON, play the whole thing back compactly and get a yes:

> "Here's the full picture I'll draw — stop me if anything's wrong:
> **Roles:** Requester, Manager, Finance.
> **Starts when:** an expense report is submitted.
> **Happy path:** submit → system checks amount → (under $100) auto-approve, or
> (≥$100) manager reviews → approve → Finance pays → employee notified.
> **Decisions:** amount threshold; manager approve/reject.
> **Rework:** rejected reports go back to the employee to revise and resubmit.
> **Ends when:** reimbursement is complete.
> Good to draw?"

Fixing a skeleton in text costs seconds; redrawing costs minutes and goodwill.

## A sample facilitation dialogue

This shows the diagnostics working together in a natural flow.

> **User:** "I need a diagram of our vendor onboarding. Basically a new vendor
> submits their info, we check it, and then they're set up in the system."
>
> **You (reflect + spot gaps):** "Nice, that's a clean starting point. Let me
> play it back: (1) vendor submits their info, (2) someone checks it, (3) they
> get set up. A few things I need to draw it properly — who does the checking,
> and what are they checking *for*? And is 'set up in the system' automatic, or
> does a person do it?"
>
> **User:** "Procurement checks it. They make sure the tax docs and banking info
> are valid. If something's missing they email the vendor to fix it. Setup is
> done by our finance team in SAP — they create the vendor master record, it's a
> whole thing with like twelve fields."
>
> **You (deeper-dive on the decision + rein in over-detail):** "That email-back
> is an important branch — so after Procurement checks, it's either 'all good →
> proceed' or 'something missing → back to the vendor to correct,' and the vendor
> resubmits. Good. On the SAP setup: the twelve fields are work-instruction
> detail, so I'll capture that as a single 'Create vendor master record' step to
> keep the map readable — sound right?"
>
> **User:** "Yeah exactly. Oh and SAP is such a pain, we've wanted to replace it
> forever."
>
> **You (park off-target, confirm):** "Ha — I'll note SAP as the system of record
> and leave the replace-it debate off the diagram. So the full picture: **Roles**
> Vendor, Procurement, Finance. **Starts:** vendor submits info. **Path:**
> submit → Procurement validates docs → if incomplete, back to vendor to correct
> and resubmit; if complete → Finance creates the vendor master record → vendor
> is active. **Ends:** vendor onboarded. Anything missing before I draw it?"

Every move there is deliberate: reflected the input, named the missing actors,
surfaced the hidden decision and rework loop, compressed the twelve-field detail,
parked the SAP gripe, and confirmed a complete skeleton — all in a warm,
plain-language register.
