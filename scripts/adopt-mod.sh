#!/usr/bin/env bash
# Move a mod Claude wrote under ~/.claude/dev-mods into this repo's plugins/,
# list it in the marketplace, load it from here in every session, and commit.
# Pushing is left to you.
#
#   scripts/adopt-mod.sh ~/.claude/dev-mods/<session-id>/<mod-name>
set -euo pipefail

src="${1:?usage: adopt-mod.sh <mod folder>}"
src="$(cd "$src" && pwd)"
repo="$(cd "$(dirname "$0")/.." && pwd)"
settings="${CLAUDE_SETTINGS:-$HOME/.claude/settings.json}"
trash="${MOD_TRASH:-$HOME/.Trash}"

manifest="$src/.claude-plugin/plugin.json"
[ -f "$manifest" ] || { echo "No .claude-plugin/plugin.json in $src" >&2; exit 1; }
name="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["name"])' "$manifest")"
dest="$repo/plugins/$name"
if [ -e "$dest" ]; then
  echo "plugins/$name already exists. Edit it there instead of in $src." >&2
  exit 1
fi

mkdir -p "$repo/plugins"
rsync -a --exclude .git --exclude .claude-plugin/types --exclude .DS_Store "$src/" "$dest/"

python3 - "$repo" "$name" "$dest" "$settings" <<'EOF'
import json, sys
repo, name, dest, settings = sys.argv[1:]

market_path = f"{repo}/.claude-plugin/marketplace.json"
market = json.load(open(market_path))
desc = json.load(open(f"{dest}/.claude-plugin/plugin.json")).get("description", "")
if not any(p["name"] == name for p in market["plugins"]):
    market["plugins"].append({"name": name, "source": f"./plugins/{name}", "description": desc})
    open(market_path, "w").write(json.dumps(market, indent=2, ensure_ascii=False) + "\n")

conf = json.load(open(settings))
env = conf.setdefault("env", {})
dirs = [d for d in env.get("CLAUDE_CODE_PLUGIN_DIRS", "").split(":") if d]
if dest not in dirs:
    dirs.append(dest)
env["CLAUDE_CODE_PLUGIN_DIRS"] = ":".join(dirs)
env["CLAUDE_CODE_PLUGIN_DIR_WATCH"] = "1"
open(settings, "w").write(json.dumps(conf, indent=2, ensure_ascii=False) + "\n")
EOF

claude plugin validate "$dest"
if find "$dest" -name '*.test.ts' -o -name '*.test.tsx' | grep -q .; then
  claude plugin test "$dest"
fi

git -C "$repo" add "plugins/$name" .claude-plugin/marketplace.json
git -C "$repo" commit -q -m "Add $name mod"

# Out of dev-mods so it doesn't load twice; recoverable from the Trash.
mkdir -p "$trash"
mv "$src" "$trash/$name-devmods-$(date +%Y%m%d-%H%M%S)"

echo "Adopted $name into plugins/$name and committed it (not pushed)."
echo "New sessions load it from $dest."
