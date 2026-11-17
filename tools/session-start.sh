#!/usr/bin/env bash
# SessionStart hook: start the upstream update check in the background and
# hand the latest finished report to the session as context.
#
# The check itself (check-updates.py) only fetches and test-applies; it never
# merges. A new check starts only if the last one is older than MAX_AGE_H hours.

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPORTS="$HERE/../reports"
LATEST="$REPORTS/latest.md"
LOCK="$REPORTS/.running"
MAX_AGE_H="${DASH_UPDATE_MAX_AGE_H:-6}"

mkdir -p "$REPORTS"

started=""
age_ok=0
if [ -f "$LATEST" ]; then
    age=$(( ($(date +%s) - $(stat -c %Y "$LATEST")) / 3600 ))
    [ "$age" -lt "$MAX_AGE_H" ] && age_ok=1
fi
if [ "$age_ok" -eq 0 ] && ! { [ -f "$LOCK" ] && kill -0 "$(cat "$LOCK")" 2>/dev/null; }; then
    nohup setsid bash -c "echo \$\$ > '$LOCK'; python3 '$HERE/check-updates.py' >'$REPORTS/last-run.log' 2>&1; rm -f '$LOCK'" \
        >/dev/null 2>&1 < /dev/null &
    started="A new upstream update check was started in the background; the next report will be at $LATEST (log: $REPORTS/last-run.log)."
fi

if [ -f "$LATEST" ]; then
    # Summary line, only the projects that moved, and the manifest comparison.
    summary=$(sed -n '1,/^## Legend/p' "$LATEST" | sed '/^## Legend/d; /^## [A-Z-]* — /,$d' \
        | grep -v -E '^\| (UP-TO-DATE|PINNED) \|')
    context="Latest dash upstream update check (from $LATEST, $(date -r "$LATEST" '+%Y-%m-%d %H:%M')):
$summary
Merge nothing automatically: present the projects marked REVIEW/CONFLICT/KERNEL-UPDATE to the user and let them decide. Never patch the oss kernel (kernel/platform)."
else
    context="No dash upstream update report yet."
fi
[ -n "$started" ] && context="$context
$started"

python3 -c 'import json,sys; print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": sys.argv[1]}}))' "$context"
