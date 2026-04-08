#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
HOOKS_SRC="$REPO_ROOT/.scripts/git-hooks"
HOOKS_DST="$REPO_ROOT/.git/hooks"

if [ ! -d "$HOOKS_SRC" ]; then
    echo "ERROR: $HOOKS_SRC not found"
    exit 1
fi

mkdir -p "$HOOKS_DST"

for hook in "$HOOKS_SRC"/*; do
    name="$(basename "$hook")"
    target="$HOOKS_DST/$name"
    if [ -L "$target" ] && [ "$(readlink "$target")" = "$hook" ]; then
        echo "  $name already linked"
        continue
    fi
    if [ -e "$target" ]; then
        echo "  $name exists (not a symlink) — backing up to $name.bak"
        mv "$target" "$target.bak"
    fi
    ln -s "$hook" "$target"
    chmod +x "$hook"
    echo "  $name installed"
done

echo ""
echo "Hooks installed. Re-run any time after cloning."
