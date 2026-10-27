#!/usr/bin/env bash
# SessionStart hook: name any mod still under ~/.claude/dev-mods that hasn't
# been adopted into this repo. Prints nothing when there are none.
dev="${DEV_MODS:-$HOME/.claude/dev-mods}"
repo="$(cd "$(dirname "$0")/.." && pwd)"

pending=()
for manifest in "$dev"/*/*/.claude-plugin/plugin.json; do
  [ -f "$manifest" ] || continue
  pending+=("$(dirname "$(dirname "$manifest")")")
done
[ ${#pending[@]} -eq 0 ] && exit 0

echo "Mods not yet in the claude-skills repo (see ~/.claude/CLAUDE.md, Mods):"
for mod in "${pending[@]}"; do echo "  $mod"; done
echo "Once a mod works, adopt it with: $repo/scripts/adopt-mod.sh <mod folder>"
