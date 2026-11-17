#!/usr/bin/env bash
# Apply the dash fixes to an Infinity-X source tree.
#
# Usage: ./apply-patches.sh /path/to/infinity [project ...]
#   With no project list, every directory under patches/ is applied.
#   Example: ./apply-patches.sh ~/infinity frameworks/base device/xiaomi/dash
#
# Each project gets its own "dash-fixes" branch (repo start), then the patches
# are applied with "git am --3way". If a patch does not apply, the script stops
# and leaves that project in the middle of "git am" so you can resolve it.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="${1:?usage: $0 /path/to/infinity [project ...]}"
shift || true

if [ ! -d "$SRC/.repo" ]; then
    echo "error: $SRC does not look like a repo checkout (.repo missing)" >&2
    exit 1
fi

if [ "$#" -gt 0 ]; then
    projects=("$@")
else
    mapfile -t projects < <(cd "$HERE/patches" && find . -name '*.patch' -printf '%h\n' | sed 's|^\./||' | sort -u)
fi

for project in "${projects[@]}"; do
    dir="$SRC/$project"
    patches=("$HERE/patches/$project"/*.patch)
    if [ ! -d "$dir" ]; then
        echo "skip  $project (not in this tree)"
        continue
    fi
    echo "apply $project (${#patches[@]} patches)"
    (cd "$SRC" && repo start dash-fixes "$project" >/dev/null 2>&1) || true
    git -C "$dir" am --3way --keep-cr "${patches[@]}"
done

echo "done"
