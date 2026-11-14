#!/bin/bash
# Status line: folder · branch · model. Claude Code pipes session JSON on stdin.
input=$(cat)
dir=$(echo "$input" | python3 -c 'import json,sys; print(json.load(sys.stdin)["workspace"]["current_dir"])')
model=$(echo "$input" | python3 -c 'import json,sys; print(json.load(sys.stdin)["model"]["display_name"])')
branch=$(git -C "$dir" --no-optional-locks branch --show-current 2>/dev/null)

sep=$'\e[2m · \e[0m'
line=$'\e[1m'"${dir##*/}"$'\e[0m'
[ -n "$branch" ] && line+="${sep}"$'\e[38;5;75m'"${branch}"$'\e[0m'
line+="${sep}"$'\e[38;5;177m'"${model}"$'\e[0m'
printf '%s' "$line"
