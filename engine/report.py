"""Problem reports: a local log of every kit command, and `kit report`, which files a GitHub issue for Mitchell.

The log (.cache/log/events.jsonl) holds the command, how long it took and the error it ended with. A report carries
that, the kit and HyperFrames versions and his one-line note: never a video, a transcript or a secret. Mitchell's agents
pick the issue up on GitHub, and the fix reaches him through `kit update`.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import time
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
LOG = KIT / ".cache" / "log" / "events.jsonl"
SENT = KIT / ".cache" / "reports" / "sent.json"
REPO = "mitchellOpZero/matthew-studio-kit"   # used when the clone's origin isn't on GitHub
LABEL = "kit-report"
KEEP = 2000        # log lines kept
PER_DAY = 5        # reports filed per day at most; the rest are saved locally

SECRETS = re.compile(r"(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|secret_[A-Za-z0-9]{20,}|ntn_[A-Za-z0-9]{20,}"
                     r"|sk-[A-Za-z0-9_-]{20,}|(?i:bearer)\s+[A-Za-z0-9._-]{20,}|(?i:(token|password|secret)\s*[=:]\s*)\S+)")


def scrub(text: str) -> str:
    """No secrets, and his home folder as ~."""
    return SECRETS.sub("[removed]", str(text)).replace(str(Path.home()), "~")


def log_event(cmd: str, argv: list[str], code: int, secs: float, error: str = "") -> None:
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        ev = {"t": dt.datetime.now().isoformat(timespec="seconds"), "cmd": cmd, "args": scrub(" ".join(argv))[:300],
              "code": code, "secs": round(secs, 1)}
        if error:
            ev["error"] = scrub(error)[-4000:]
        with open(LOG, "a") as f:
            f.write(json.dumps(ev) + "\n")
        lines = LOG.read_text().splitlines()
        if len(lines) > KEEP * 1.2:
            LOG.write_text("\n".join(lines[-KEEP:]) + "\n")
    except OSError:
        pass   # the log never stops an edit


def events(n: int = 15) -> list[dict]:
    try:
        return [json.loads(x) for x in LOG.read_text().splitlines()[-n:] if x.strip()]
    except (OSError, ValueError):
        return []


def repo() -> str:
    url = subprocess.run(["git", "-C", str(KIT), "remote", "get-url", "origin"], capture_output=True, text=True).stdout.strip()
    m = re.search(r"github\.com[:/]([^/]+/[^/]+?)(\.git)?$", url)
    return m.group(1) if m else REPO


def body(note: str, version: str, hf_version: str) -> tuple[str, str, str]:
    """(title, markdown body, signature of the failure)."""
    evs = events(15)
    recent = (dt.datetime.now() - dt.timedelta(hours=3)).isoformat(timespec="seconds")
    fail = next((e for e in reversed(evs) if e.get("code") and e.get("t", "") >= recent), None)   # an old failure isn't this problem
    first = (fail.get("error", "").strip().splitlines() or [f"exit {fail['code']}"])[-1] if fail else ""
    sig = hashlib.sha1(re.sub(r"[0-9]+", "#", f"{fail['cmd']} {first}" if fail else note).encode()).hexdigest()[:10]
    what = f"{fail['cmd']} failed: {first}" if fail else "problem report"
    title = scrub(f"kit report: {what}")[:110]
    rows = "\n".join(f"| {e['t']} | `{e['cmd']} {e.get('args', '')[:80]}` | {e['code']} | {e['secs']} s |" for e in evs)
    try:
        dlog = (KIT / ".cache" / "deps" / "log.txt").read_text().splitlines()[-5:]
    except OSError:
        dlog = []
    md = [f"**What he was doing:** {scrub(note) or '(no note)'}", "",
          f"- kit: `{version}`", f"- HyperFrames: `{hf_version}`",
          f"- Mac: macOS {platform.mac_ver()[0] or platform.platform()} ({platform.machine()})", f"- signature: `{sig}`", ""]
    if fail:
        md += [f"### Last failure: `{fail['cmd']} {fail.get('args', '')}` at {fail['t']} (exit {fail['code']})",
               "```", fail.get("error", "(no message)")[-3000:], "```", ""]
    md += ["### Last commands", "| time | command | exit | took |", "|---|---|---|---|", rows or "| | (no log yet) | | |", ""]
    if dlog:
        md += ["### Updater log", "```", scrub("\n".join(dlog)), "```", ""]
    md += ["### For the fixing agent",
           "Reproduce on the same kit commit with one of your own clips (his footage isn't attached). Fix it clip-agnostically, "
           "ship it as a PR on this repo, and he gets it with `kit update`. Close this issue with the PR.",
           "", "_Filed by `bin/kit report`. No video, transcript or secrets are included._"]
    return title, scrub("\n".join(md)), sig


def send(note: str, version: str, hf_version: str, dry: bool = False) -> int:
    title, md, sig = body(note, version, hf_version)
    if dry:
        print(f"{title}\n\n{md}")
        return 0
    out = KIT / ".cache" / "reports" / f"{dt.datetime.now():%Y-%m-%d_%H%M%S}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(f"# {title}\n\n{md}\n")
    try:
        sent = json.loads(SENT.read_text())
    except (OSError, ValueError):
        sent = {}
    now = time.time()
    sent = {k: v for k, v in sent.items() if now - v["at"] < 86400}
    if sig in sent:
        print(f"already reported today: {sent[sig]['url']} (saved again at {scrub(out)})")
        return 0
    if len(sent) >= PER_DAY:
        print(f"{PER_DAY} reports went to Mitchell today already; this one is saved at {scrub(out)}. Send him that file.")
        return 1
    gh = shutil.which("gh") or shutil.which("gh", path="/opt/homebrew/bin:/usr/local/bin")
    if not gh:
        print(f"GitHub's gh tool isn't installed, so the report is saved at {scrub(out)}. Send Mitchell that file.")
        return 1
    base = [gh, "issue", "create", "-R", repo(), "--title", title, "--body", md]
    r = subprocess.run(base + ["--label", LABEL], capture_output=True, text=True)
    if r.returncode and "label" in (r.stderr + r.stdout).lower():
        r = subprocess.run(base, capture_output=True, text=True)
    url = r.stdout.strip().splitlines()[-1] if r.returncode == 0 and r.stdout.strip() else ""
    if not url:
        print(f"couldn't file it on GitHub ({scrub(r.stderr.strip()[-300:]) or 'no answer'}). "
              f"The report is saved at {scrub(out)}: send Mitchell that file. (`gh auth login` fixes most of these.)")
        return 1
    sent[sig] = {"at": now, "url": url}
    SENT.write_text(json.dumps(sent, indent=1))
    print(f"sent to Mitchell: {url}")
    return 0
