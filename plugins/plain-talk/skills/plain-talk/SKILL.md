---
name: plain-talk
description: Re-explain something so the user actually understands it. Use when the user says or implies "what did you mean", "simplify that", "explain like I know nothing", "help me see the bigger picture", "I have no idea what context you're coming from", "walk me through the flow", "I'm lost", or otherwise signals your last reply was unclear, too dense, or assumed knowledge they don't have. Also use when explaining an unfamiliar topic, architecture, or multi-step process to them from scratch.
---

# Plain talk

The user is not inside your head. They haven't read the files you read, seen the errors you saw, or followed your reasoning. When they ask for clarity, the problem is almost never that they need *more* words. It's that they're missing the **starting point** (what is this, why are we here) or the **shape** (how the pieces connect).

## First: figure out what's missing

Match what they asked to one of these, and answer that, not all of them. If it's ambiguous, pick the most likely one and go. Don't ask.

| They say | What's missing | Do this |
|---|---|---|
| "What did you mean by that?" | A specific term or sentence | Quote the confusing bit, then say it again in plain words. Define every term in it. |
| "Simplify that" | Too much at once | Cut to the core in 3–5 short sentences. Drop caveats, edge cases, and side notes. Offer the detail in one line at the end. |
| "Bigger picture" / "why are we doing this" | The goal | Use the **Zoom out** shape below. |
| "No idea what context you're coming from" | Your assumptions | Say what you were looking at and what you assumed, then explain from there. |
| "Write as if I know nothing" | Background knowledge | Use the **From zero** shape below. |
| "Help me understand the flow" | Order and connections | Use the **Flow** shape below. |

## Shapes

### Zoom out
1. **The goal:** what we're ultimately trying to achieve, in one sentence, in the user's terms (not code terms).
2. **The pieces:** the 2–5 main parts involved, one line each on what it does.
3. **Where we are:** which piece we're working on and why it matters to the goal.
4. **What's next:** the next step and what "done" looks like.

### From zero
1. **What it is** in one sentence, with no jargon.
2. **An everyday analogy** (a restaurant, a post office, a recipe), if one honestly fits. Say where the analogy breaks if that matters.
3. **Why it exists:** the problem it solves.
4. **The few terms they'll keep seeing**, each defined in a few words.
5. **How it applies here:** connect it back to what we're actually doing.

Build up from what they know. Never use a term before you've defined it.

### Flow
Show the sequence as numbered steps, one action per step, naming who or what does it:

```
1. You click "Save"            → the browser sends the form to the server
2. The server checks the data  → rejects it if a field is missing
3. The server writes to the DB → the record now exists
4. The page reloads            → you see the saved item
```

For branching or several moving parts, draw a small ASCII diagram or use the `archify` skill when a real diagram would help. End with one sentence on the most important handoff or the step most likely to go wrong.

## Writing rules (for every re-explanation)

- **Answer first.** The first sentence should be useful on its own.
- **One idea per sentence.** Short sentences. Short paragraphs.
- **Name things concretely.** "The login page" beats "the auth layer"; "the file that lists the API routes (`routes.py`)" beats "routes.py".
- **Define on first use.** "A webhook (a URL another service calls to tell us something happened)."
- **Use their words.** If they called it "the dashboard", don't switch to "the reporting view".
- **One example beats three abstractions.**
- **Don't apologize or pad.** No "Great question!", no "To put it simply…" preamble. Just say it simply.
- **Check the length.** A re-explanation should usually be *shorter* than the original reply.

Finish with at most one line offering the next level: deeper detail, a diagram, or the bigger picture. Not a menu.

## Keep it up

Once the user has asked for plainer language, keep writing that way for the rest of the conversation. Don't drift back to dense replies after one clear answer.
