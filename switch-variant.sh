#!/usr/bin/env bash
# Switch the dash device tree between the two kernel variants.
#
# Usage: ./switch-variant.sh /path/to/infinity prebuilt|kleaf
#
#   prebuilt  stock HyperOS kernel from device/xiaomi/dash-kernel (branch "infinity")
#   kleaf     kernel built from source by Kleaf, oss-dash-kernel repos under
#             kernel/platform/kernel-6.6 (branch "infinity-kleaf")
#
# Both branches carry the same fixes; they differ only in the upstream
# "Build kernel inline with Kleaf" commit. Build with the usual
# lunch/m bacon after switching: only kernel-related targets are rebuilt.

set -euo pipefail

SRC="${1:?usage: $0 /path/to/infinity prebuilt|kleaf}"
VARIANT="${2:?usage: $0 /path/to/infinity prebuilt|kleaf}"
TREE="$SRC/device/xiaomi/dash"

case "$VARIANT" in
    prebuilt) BRANCH=infinity ;;
    kleaf)
        BRANCH=infinity-kleaf
        if [ ! -e "$SRC/kernel/platform/kernel-6.6/build/bazel_mgk_rules/android/modules.mk" ]; then
            echo "error: kernel/platform/kernel-6.6 is not synced, run repo sync for the kernel projects first" >&2
            exit 1
        fi
        ;;
    *) echo "error: variant must be prebuilt or kleaf" >&2; exit 1 ;;
esac

if [ -n "$(git -C "$TREE" status --porcelain --untracked-files=no)" ]; then
    echo "error: $TREE has uncommitted changes, commit or stash them first" >&2
    exit 1
fi

git -C "$TREE" checkout -q "$BRANCH"
echo "device/xiaomi/dash -> $BRANCH ($VARIANT kernel)"
git -C "$TREE" log --oneline -1
