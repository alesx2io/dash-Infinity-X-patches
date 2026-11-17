#!/usr/bin/env python3
"""Check upstream updates for the dash Infinity-X tree and judge whether to merge them.

Read-only with respect to the source tree: it only runs `git fetch` (which moves the
remote-tracking refs) and test-applies our local commits in throw-away worktrees.
It never merges, rebases or checks out anything in the real projects.

Usage:
  check-updates.py [--src /media/SATA_CACHY/infinity] [--projects p1,p2] [--no-fetch]
                   [--report-dir DIR]

Exit code: 0 if nothing needs attention, 1 if some project needs review or has conflicts.
"""

import argparse
import datetime
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

KERNEL_PREFIX = "kernel/platform/"
# Projects from the main Infinity manifest that carry our patches.
EXTRA_PROJECTS = ["frameworks/base", "build/soong"]
# Branches with our work, per project. Default: "infinity".
LOCAL_BRANCHES = {"device/xiaomi/dash": ["infinity", "infinity-kleaf"]}
# Upstream changes to these paths are worth a careful look even if they apply cleanly.
RISKY = re.compile(
    r"(BoardConfig\.mk|device\.mk|AndroidProducts\.mk|\.rc$|fstab|sepolicy|manifest.*\.xml|"
    r"compatibility_matrix|proprietary-files|extract-files|modules\.load|Android\.bp$|"
    r"overlay/.*/config\.xml|vendor\.prop|system\.prop)"
)
UPSTREAM_MANIFEST = "https://github.com/oss-dash/android_local_manifests"
LFS_OFF = ["-c", "filter.lfs.smudge=", "-c", "filter.lfs.process=", "-c", "filter.lfs.required=false",
           "-c", "filter.lfs.clean="]


def git(path, *args, check=False, env_extra=None):
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_LFS_SKIP_SMUDGE="1")
    if env_extra:
        env.update(env_extra)
    r = subprocess.run(["git", *LFS_OFF, "-C", path, *args], capture_output=True, text=True, env=env)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} in {path}: {r.stderr.strip()}")
    return r


def out(path, *args):
    r = git(path, *args)
    return r.stdout.strip() if r.returncode == 0 else ""


def local_manifest_projects(src):
    projects = []
    lm = os.path.join(src, ".repo", "local_manifests")
    for name in sorted(os.listdir(lm)):
        if not name.endswith(".xml"):
            continue
        root = ET.parse(os.path.join(lm, name)).getroot()
        for p in root.iter("project"):
            projects.append({"path": p.get("path"), "name": p.get("name")})
    return projects


def upstream_ref(path):
    """remote/branch that the manifest revision follows, or None for pinned SHAs."""
    r = git(path, "symbolic-ref", "refs/remotes/m/17")
    if r.returncode != 0:
        return None, None
    ref = r.stdout.strip().removeprefix("refs/remotes/")
    remote, _, branch = ref.partition("/")
    return remote, branch


def test_apply(path, new, commits):
    """Replay our commits on top of the new upstream with merge-tree (no checkout, no worktree)."""
    head = new
    ident = {"GIT_AUTHOR_NAME": "check", "GIT_AUTHOR_EMAIL": "check@localhost",
             "GIT_COMMITTER_NAME": "check", "GIT_COMMITTER_EMAIL": "check@localhost"}
    for c in commits:
        parent = out(path, "rev-parse", f"{c}^")
        r = git(path, "merge-tree", "--write-tree", "--name-only", f"--merge-base={parent}", head, c)
        if r.returncode == 1:
            lines = r.stdout.strip().splitlines()
            files = [l for l in lines[1:] if l and not l.startswith(("Auto-merging", "CONFLICT"))]
            subj = out(path, "log", "-1", "--format=%s", c)
            return "conflict", f"{c[:9]} {subj} -> {', '.join(files[:8]) or '?'}"
        if r.returncode != 0:
            return "error", r.stderr.strip()[:200]
        tree = r.stdout.strip().splitlines()[0]
        r = git(path, "commit-tree", tree, "-p", head, "-m", "check", env_extra=ident)
        if r.returncode != 0:
            return "error", r.stderr.strip()[:200]
        head = r.stdout.strip()
    return "clean", ""


def check_project(src, path, do_fetch):
    full = os.path.join(src, path)
    res = {"path": path, "status": "", "notes": [], "new_commits": [], "files": [], "local": {}}
    if not os.path.isdir(full):
        res["status"] = "MISSING"
        res["notes"].append("not synced in this tree")
        return res
    remote, branch = upstream_ref(full)
    if not remote:
        res["status"] = "PINNED"
        res["notes"].append("manifest pins a fixed revision, nothing to fetch")
        return res
    tracking = f"refs/remotes/{remote}/{branch}"
    old = out(full, "rev-parse", tracking)
    if do_fetch:
        # Cheap check first: only fetch when the remote tip actually moved.
        r = git(full, "ls-remote", remote, f"refs/heads/{branch}")
        if r.returncode != 0 or not r.stdout.strip():
            res["status"] = "FETCH-FAILED"
            res["notes"].append((r.stderr.strip().splitlines() or ["ls-remote failed"])[-1][:200])
            return res
        remote_tip = r.stdout.split()[0]
        do_fetch = remote_tip != old
    if do_fetch:
        fetch = ["fetch", "-q"]
        if out(full, "rev-parse", "--is-shallow-repository") == "true":
            # Never pull full history into shallow clones (prebuilts are many GB).
            fetch.append("--depth=1" if "/prebuilts/" in path else "--depth=200")
        r = git(full, *fetch, remote, f"+refs/heads/{branch}:{tracking}")
        if r.returncode != 0:
            res["status"] = "FETCH-FAILED"
            res["notes"].append(r.stderr.strip().splitlines()[-1][:200] if r.stderr.strip() else "fetch failed")
            return res
    new = out(full, "rev-parse", tracking)
    res["old"], res["new"] = old[:9], new[:9]

    # Our work: commits on the local branches that upstream (old) does not have.
    branches = LOCAL_BRANCHES.get(path, ["infinity"])
    for b in branches:
        if git(full, "rev-parse", "--verify", "-q", f"refs/heads/{b}").returncode != 0:
            continue
        base = old if git(full, "merge-base", "--is-ancestor", old, b).returncode == 0 else None
        if base is None:
            # Branch is not based on the previous upstream (e.g. rebased on a newer one).
            base = new if git(full, "merge-base", "--is-ancestor", new, b).returncode == 0 else None
        if base is None:
            res["notes"].append(f"branch {b} is not based on the upstream ref, local commits unknown")
            continue
        commits = out(full, "rev-list", "--reverse", f"{base}..{b}").split()
        res["local"][b] = {"base": base, "commits": commits}

    if old == new:
        res["status"] = "UP-TO-DATE"
        return res

    rewritten = git(full, "merge-base", "--is-ancestor", old, new).returncode != 0
    if rewritten:
        res["notes"].append("upstream history was rewritten (force push or shallow history): "
                            "commit list below may include old commits")
    res["new_commits"] = out(full, "log", "--format=%h %ad %an | %s", "--date=short",
                             f"{old}..{new}").splitlines()[:60]
    res["files"] = out(full, "diff", "--name-only", old, new).splitlines()

    if path.startswith(KERNEL_PREFIX):
        own = sum(len(v["commits"]) for v in res["local"].values())
        res["status"] = "KERNEL-UPDATE"
        res["notes"].append("oss kernel: maintained by its developers, take it as is (repo sync), "
                            "never patch it here")
        if own:
            res["notes"].append(f"WARNING: {own} local commits found on a kernel project")
        return res

    ours = set()
    verdicts = []
    for b, info in res["local"].items():
        if not info["commits"]:
            continue
        ours |= set(out(full, "diff", "--name-only", info["base"], b).splitlines())
        if info["base"] == new:
            verdicts.append((b, "clean", "already based on the new upstream"))
            continue
        verdicts.append((b, *test_apply(full, new, info["commits"])))
    overlap = sorted(ours & set(res["files"]))
    risky = sorted(f for f in res["files"] if RISKY.search(f))
    res["overlap"], res["risky"], res["verdicts"] = overlap, risky, verdicts

    if any(v[1] in ("conflict", "error") for v in verdicts):
        res["status"] = "CONFLICT"
    elif overlap or risky or rewritten:
        res["status"] = "REVIEW"
    else:
        res["status"] = "SAFE"
    return res


def manifest_drift(src, tmpdir):
    """Compare our local manifest with oss-dash's upstream local manifest."""
    dest = os.path.join(tmpdir, "lm")
    r = subprocess.run(["git", "clone", "-q", "--depth=1", UPSTREAM_MANIFEST, dest],
                       capture_output=True, text=True, env=dict(os.environ, GIT_TERMINAL_PROMPT="0"))
    if r.returncode != 0:
        return None
    up = {}
    for name in os.listdir(dest):
        if name.endswith(".xml"):
            for p in ET.parse(os.path.join(dest, name)).getroot().iter("project"):
                up[p.get("path")] = p.get("name")
    ours = {p["path"]: p["name"] for p in local_manifest_projects(src)}
    last = subprocess.run(["git", "-C", dest, "log", "-1", "--format=%h %ad %s", "--date=short"],
                          capture_output=True, text=True).stdout.strip()
    return {
        "last": last,
        "added": sorted(p for p in up if p not in ours),
        "removed": sorted(p for p in ours if p not in up),
        "renamed": sorted(p for p in up if p in ours and up[p] != ours[p]),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", default=os.environ.get("AOSP_SRC", "/media/SATA_CACHY/infinity"))
    ap.add_argument("--projects", help="comma-separated paths (default: local manifest + patched projects)")
    ap.add_argument("--no-fetch", action="store_true", help="use the refs already fetched")
    ap.add_argument("--report-dir", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                         "..", "reports"))
    args = ap.parse_args()

    src = os.path.abspath(args.src)
    if args.projects:
        paths = [p.strip() for p in args.projects.split(",") if p.strip()]
    else:
        paths = [p["path"] for p in local_manifest_projects(src)] + EXTRA_PROJECTS

    results = []
    for path in paths:
        print(f"checking {path} ...", file=sys.stderr, flush=True)
        try:
            results.append(check_project(src, path, not args.no_fetch))
        except Exception as e:  # keep going on unexpected git errors
            results.append({"path": path, "status": "ERROR", "notes": [str(e)[:300]],
                            "new_commits": [], "files": [], "local": {}})

    with tempfile.TemporaryDirectory() as tmp:
        drift = manifest_drift(src, tmp)

    now = datetime.datetime.now()
    os.makedirs(args.report_dir, exist_ok=True)
    report = os.path.join(os.path.abspath(args.report_dir), f"updates-{now:%Y%m%d-%H%M}.md")
    order = ["CONFLICT", "REVIEW", "KERNEL-UPDATE", "SAFE", "FETCH-FAILED", "ERROR", "MISSING",
             "UP-TO-DATE", "PINNED"]
    results.sort(key=lambda r: (order.index(r["status"]) if r["status"] in order else 99, r["path"]))

    lines = [f"# Upstream update check — {now:%Y-%m-%d %H:%M}", "", f"Tree: `{src}`", ""]
    counts = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    lines.append("**Summary:** " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items(),
                 key=lambda kv: order.index(kv[0]) if kv[0] in order else 99)))
    lines += ["", "| Status | Project | Upstream | New commits | Our commits |", "|---|---|---|---|---|"]
    for r in results:
        ours = sum(len(v["commits"]) for v in r["local"].values())
        up = f"{r.get('old', '')} → {r.get('new', '')}" if r.get("old") != r.get("new") else r.get("new", "")
        lines.append(f"| {r['status']} | `{r['path']}` | {up} | {len(r['new_commits'])} | {ours} |")

    if drift is not None:
        lines += ["", "## oss-dash local manifest", "", f"Last upstream change: {drift['last']}", ""]
        if not (drift["added"] or drift["removed"] or drift["renamed"]):
            lines.append("Same projects as ours.")
        for key, label in (("added", "Upstream has, we do not"), ("removed", "We have, upstream does not"),
                           ("renamed", "Same path, different repo")):
            if drift[key]:
                lines.append(f"- **{label}:** " + ", ".join(f"`{p}`" for p in drift[key]))
    else:
        lines += ["", "## oss-dash local manifest", "", "Could not fetch the upstream local manifest."]

    for r in results:
        if r["status"] in ("UP-TO-DATE", "PINNED"):
            continue
        lines += ["", f"## {r['status']} — `{r['path']}`", ""]
        for n in r["notes"]:
            lines.append(f"- {n}")
        for b, verdict, detail in r.get("verdicts", []):
            lines.append(f"- our branch `{b}` on new upstream: **{verdict}**" + (f" ({detail})" if detail else ""))
        if r.get("overlap"):
            lines.append("- upstream also changed files we patch: " + ", ".join(f"`{f}`" for f in r["overlap"]))
        if r.get("risky"):
            lines.append("- sensitive files changed: " + ", ".join(f"`{f}`" for f in r["risky"][:25]))
        if r["new_commits"]:
            lines += ["", "```", *r["new_commits"], "```"]
        if r["files"]:
            lines.append(f"\n{len(r['files'])} files changed upstream.")

    lines += ["", "## Legend", "",
              "- **SAFE**: our commits apply cleanly on the new upstream and nothing sensitive changed.",
              "- **REVIEW**: applies, but upstream touched files we patch or sensitive build files.",
              "- **CONFLICT**: our commits do not apply on the new upstream as they are.",
              "- **KERNEL-UPDATE**: oss kernel moved; take it as is, no local changes.",
              "- Nothing was merged: the tree is unchanged apart from fetched remote refs."]

    with open(report, "w") as f:
        f.write("\n".join(lines) + "\n")
    latest = os.path.join(os.path.abspath(args.report_dir), "latest.md")
    shutil.copyfile(report, latest)

    print("\n".join(lines[:6 + len(results) + 3]))
    print(f"\nreport: {report}")
    return 1 if any(r["status"] in ("CONFLICT", "REVIEW") for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
