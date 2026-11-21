# plain-talk

Makes Claude explain itself so you don't have to keep asking "what did you mean?"

- **Always on:** at session start, a short set of writing rules is added to Claude's context: lead with the answer, say where we are, define jargon, show the flow, cut the rest (`hooks/rules.md`).
- **When you're lost:** if your message asks for clarity ("simplify that", "bigger picture", "walk me through the flow", "assume I know nothing", "what did you mean"), a prompt hook (`hooks/confused.py`) tells Claude to load the `plain-talk` skill, which picks the right shape: plain restatement, zoom out, from zero, or step-by-step flow.

You can also invoke it directly: `/plain-talk:plain-talk`.
