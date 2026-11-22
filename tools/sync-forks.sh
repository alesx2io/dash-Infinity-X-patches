#!/usr/bin/env bash
# Keep our forks in line with oss-dash / oss-dash-kernel.
#
#   tools/sync-forks.sh [--src /path/to/tree]               mirror forks: bring them to upstream
#   tools/sync-forks.sh [--src /path/to/tree] --push-ours   also push our fix branches (after a rebase)
#
# - GitHub forks that only mirror upstream: server-side "gh repo sync" (nothing is uploaded).
# - GitLab forks (vendor blobs, Git LFS): push the fetched upstream branch over SSH. Needs the
#   ssh-agent with the key loaded (see README) and must run where git-lfs is installed.
# - Forks with our fixes (branches infinity / infinity-kleaf) are never rebased here: review the
#   check-updates report, rebase the local branches by hand, then run with --push-ours.
#
# Nothing is pushed if a commit in the pushed range carries an address that is not a
# noreply one for us (protects the personal e-mail).
set -uo pipefail

SRC=/media/SATA_CACHY/infinity
PUSH_OURS=0
while [ $# -gt 0 ]; do
    case "$1" in
        --src) SRC="$2"; shift 2 ;;
        --push-ours) PUSH_OURS=1; shift ;;
        *) echo "usage: $0 [--src DIR] [--push-ours]" >&2; exit 2 ;;
    esac
done

GH_USER=alesx2io
GL_USER=alesx2io
BRANCH=lineage-24.0
NOREPLY="96351978+alesx2io@users.noreply.github.com"
export SSH_AUTH_SOCK="${SSH_AUTH_SOCK:-$XDG_RUNTIME_DIR/ssh-agent.socket}"
# The distrobox has its own HOME: always use the host known_hosts.
export GIT_SSH_COMMAND="ssh -o BatchMode=yes -o UserKnownHostsFile=/home/$USER/.ssh/known_hosts"
# Run on the host (gh). The GitLab part needs git-lfs, which only the aosp distrobox has.
if git lfs version >/dev/null 2>&1; then
    GIT_LFS=(git)
else
    GIT_LFS=(distrobox enter aosp -- env "SSH_AUTH_SOCK=$SSH_AUTH_SOCK" "GIT_SSH_COMMAND=$GIT_SSH_COMMAND" git)
fi

# path  github-fork-name  (mirror forks on GitHub)
GH_MIRRORS="
device/xiaomi/dash-miuicamera android_device_xiaomi_dash-miuicamera
device/xiaomi/dash-kernel android_device_xiaomi_dash-kernel
hardware/mediatek android_hardware_mediatek
hardware/xiaomi android_hardware_xiaomi
device/mediatek/sepolicy_vndr android_device_mediatek_sepolicy_vndr
packages/apps/LunarisDolby android_packages_apps_LunarisDolby
vendor/qcom/opensource/vibrator android_vendor_qcom_opensource_vibrator
kernel/platform/kernel-6.6/kernel-6.6 android_kernel
kernel/platform/kernel-6.6/kernel_device_modules-6.6 android_kernel_device_modules
kernel/platform/kernel-6.6/vendor/mediatek/kernel_modules android_kernel_vendor_mediatek_kernel_modules
kernel/platform/kernel-6.6/build/bazel_mgk_rules android_kernel_build_bazel_mgk_rules
"
# Forks that also carry the upstream branch untouched next to our fix branches.
GH_OURS="
device/xiaomi/dash android_device_xiaomi_dash infinity infinity-kleaf
"
# path  gitlab-fork-name  upstream-remote
GL_MIRRORS="
vendor/xiaomi/dash proprietary_vendor_xiaomi_dash ossgl
vendor/xiaomi/dash-miuicamera proprietary_vendor_xiaomi_dash-miuicamera ossgl
"

clean_range() {  # repo, range -> 0 if no commit in range carries one of our private addresses
    # Private addresses come from DASH_PRIVATE_EMAILS or ~/.config/dash/private-emails (one per
    # line, kept outside the repository), never from this file.
    local priv addr
    priv="${DASH_PRIVATE_EMAILS:-$(cat "$HOME/.config/dash/private-emails" 2>/dev/null)}"
    if [ -z "$priv" ]; then
        echo "no private address list (~/.config/dash/private-emails): refusing to push" >&2
        return 1
    fi
    # A range that does not resolve (remote branch not pushed yet) proves nothing.
    git -C "$1" rev-list "$2" >/dev/null 2>&1 || return 1
    for addr in $priv; do
        [ "$addr" = "$NOREPLY" ] && continue
        if git -C "$1" log --format='%ae%n%ce' "$2" 2>/dev/null | grep -qixF "$addr"; then
            return 1
        fi
    done
    return 0
}

echo "== GitHub mirror forks (server-side sync of $BRANCH)"
while read -r p n; do
    [ -n "$p" ] || continue
    printf '%-60s ' "$n"
    if r=$(gh repo sync "$GH_USER/$n" --branch "$BRANCH" </dev/null 2>&1); then echo "ok"; else echo "FAILED: $(echo "$r" | tail -1)"; fi
done <<< "$GH_MIRRORS"

echo "== GitHub forks with our fixes: upstream branch $BRANCH"
while read -r p n _; do
    [ -n "$p" ] || continue
    printf '%-60s ' "$n"
    if r=$(gh repo sync "$GH_USER/$n" --branch "$BRANCH" </dev/null 2>&1); then echo "ok"; else echo "FAILED: $(echo "$r" | tail -1)"; fi
done <<< "$GH_OURS"

echo "== GitLab forks (push of the fetched upstream $BRANCH over SSH)"
if ! ssh-add -l >/dev/null 2>&1; then
    echo "   skipped: no key in the ssh-agent (systemctl --user start ssh-agent.service; ssh-add -t 1h)"
else
    while read -r p n up; do
        [ -n "$p" ] || continue
        printf '%-60s ' "$n"
        "${GIT_LFS[@]}" -C "$SRC/$p" fetch -q "$up" "+refs/heads/$BRANCH:refs/remotes/$up/$BRANCH" </dev/null 2>&1 | tail -1
        if r=$("${GIT_LFS[@]}" -C "$SRC/$p" push -q "git@gitlab.com:$GL_USER/$n.git" \
                   "refs/remotes/$up/$BRANCH:refs/heads/$BRANCH" </dev/null 2>&1); then
            echo "ok ($(git -C "$SRC/$p" rev-parse --short "refs/remotes/$up/$BRANCH"))"
        else
            echo "FAILED: $(echo "$r" | grep -v '^\s*$' | head -1)"
        fi
    done <<< "$GL_MIRRORS"
fi

# path  gitlab-fork-name  branches with our fixes
GL_OURS="
vendor/xiaomi/dash proprietary_vendor_xiaomi_dash infinity
"

if [ "$PUSH_OURS" = 1 ]; then
    echo "== Our fix branches (force-with-lease after a rebase)"
    while read -r p n branches; do
        [ -n "$p" ] || continue
        for b in $branches; do
            printf '%-60s ' "$n:$b"
            if ! clean_range "$SRC/$p" "refs/remotes/dash/$b..$b"; then
                echo "REFUSED: personal e-mail in commits to push"; continue
            fi
            git -C "$SRC/$p" push -q --force-with-lease="$b:refs/remotes/dash/$b" dash "$b:refs/heads/$b" 2>&1 | tail -1
            echo "ok ($(git -C "$SRC/$p" rev-parse --short "$b"))"
        done
    done <<< "$GH_OURS"
    if ssh-add -l >/dev/null 2>&1; then
        while read -r p n branches; do
            [ -n "$p" ] || continue
            for b in $branches; do
                printf '%-60s ' "$n:$b (GitLab)"
                if ! clean_range "$SRC/$p" "refs/remotes/dashgl/$b..$b" \
                   && ! clean_range "$SRC/$p" "refs/remotes/ossgl/$BRANCH..$b"; then
                    echo "REFUSED: personal e-mail in commits to push"; continue
                fi
                if r=$("${GIT_LFS[@]}" -C "$SRC/$p" push -q --force "git@gitlab.com:$GL_USER/$n.git" \
                        "$b:refs/heads/$b" </dev/null 2>&1); then
                    echo "ok ($(git -C "$SRC/$p" rev-parse --short "$b"))"
                else
                    echo "FAILED: $(echo "$r" | grep -v '^\s*$' | head -1)"
                fi
            done
        done <<< "$GL_OURS"
    else
        echo "   GitLab fix branches skipped: no key in the ssh-agent"
    fi
fi
