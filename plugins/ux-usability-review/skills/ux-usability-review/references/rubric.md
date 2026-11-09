# Rubric (first-time user, no prior knowledge)

## Wording clarity
- Plain, task-oriented verbs ("Create report"), not internal jargon, unexplained acronyms, or generic text ("Submit", "Click here", "OK").
- A heading states the page's purpose; a newcomer understands it in 5 seconds.
- Instructional copy at grade <= 8 (Flesch-Kincaid heuristic).
- Buttons say what will happen; destructive actions name what is destroyed.
- Same thing, same name everywhere.
- Deduct: icon-only controls without names, placeholder used as label.

## Screen complexity
- One clear primary action; <= ~7 competing choices per group.
- <=15 visible interactive elements is comfortable; >30 is heavy.
- Dense tables/forms chunked with headings, defaults, inline help.
- Deduct: walls of text, many equal-weight buttons, essential actions hidden.

## Next-step obviousness
- Primary action visually dominant, above the fold.
- Empty states say what to do first.
- Required fields marked; multi-step tasks show progress.

## Flow coherence
- Steps/clicks to goal vs. a reasonable minimum.
- Information scent: the next page's heading matches the label that led there.
- No dead ends; back/cancel always possible; context (title, breadcrumbs) persists.
- Deduct: surprise navigation, lost data, unexplained redirects.

## Feedback & errors
- Actions confirm visibly; loading states exist.
- Errors say what happened and how to fix it, beside the field.

## Accessibility basics
- Inputs labelled; icon buttons and images named; heading order sane; contrast judged from screenshot (low confidence).

## Severity
Blocker: newcomer cannot finish the goal. Major: likely hesitation or error. Minor: polish.
