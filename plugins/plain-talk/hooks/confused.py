"""UserPromptSubmit hook: when the prompt asks for a clearer explanation, tell Claude to use plain-talk."""
import json
import re
import sys

PATTERNS = {
    "meaning": r"what (do|did) you mean|what does that mean|i don'?t (get|follow|understand)|confus|huh\?",
    "simplify": r"simplif|simpler|plain (english|terms|language)|eli5|explain like|too (long|technical|dense)|tl;?dr",
    "big picture": r"big(ger)? picture|zoom out|why (are|do) we|how does this fit|what'?s the point",
    "no context": r"no (idea|clue) what (context|you)|what context|where (are|is) (you|this) coming from|lost me|catch me up",
    "beginner": r"no (prior )?knowledge|know nothing|(i'?m|as) a beginner|new to (this|it)|from scratch|from zero",
    "flow": r"\bflow\b|step by step|walk me through|what happens (when|first|next)|in what order|sequence",
}


def main():
    try:
        prompt = json.load(sys.stdin).get("prompt", "")
    except (json.JSONDecodeError, AttributeError):
        return
    asks = [name for name, pat in PATTERNS.items() if re.search(pat, prompt, re.I)]
    if not asks:
        return
    print(
        "plain-talk: the user is asking for a clearer explanation "
        f"({', '.join(asks)}). Load the plain-talk skill and follow it for this reply."
    )


if __name__ == "__main__":
    main()
