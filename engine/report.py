"""Problem reports: a local log of every kit command, and `kit report`, which sends a report to Mitchell.

The log (.cache/log/events.jsonl) holds the command, how long it took and the error it ended with. A report carries
that, the kit and HyperFrames versions, a few facts about the job's plan and his own words about what was wrong: never
a video, a transcript or a secret. It goes to Mitchell's webhook when one is set on this Mac (~/.config/matthew-studio-kit/
report.json, or KIT_REPORT_WEBHOOK), else to GitHub as an issue on the official kit. Mitchell's agents pick it up, and the
fix reaches him when the kit updates itself (engine/selfupdate.py).
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
PER_DAY = 12       # reports sent per day at most; the rest are saved locally
WEBHOOK = Path.home() / ".config" / "matthew-studio-kit" / "report.json"   # {"url": "...", "bearer": "...", "format"?: "text"}: never in the kit folder
PREFS = KIT / "my-styles" / "preferences.json"

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
    """The official kit (`upstream` when this clone is a fork of it), where reports are read. A fork's own page may
    have issues switched off, and nobody reads them there."""
    for name in ("upstream", "origin"):
        url = subprocess.run(["git", "-C", str(KIT), "remote", "get-url", name], capture_output=True, text=True).stdout.strip()
        m = re.search(r"github\.com[:/]([^/]+/[^/]+?)(\.git)?$", url)
        if m:
            return m.group(1)
    return REPO


def webhook() -> dict:
    """Where reports go instead of GitHub, when Mitchell has set one on this Mac: {"url", "bearer"?}."""
    if os.environ.get("KIT_REPORT_WEBHOOK"):
        return {"url": os.environ["KIT_REPORT_WEBHOOK"], "bearer": os.environ.get("KIT_REPORT_BEARER", "")}
    try:
        d = json.loads(WEBHOOK.read_text())
        return d if isinstance(d, dict) and str(d.get("url", "")).startswith("https://") else {}
    except (OSError, ValueError):
        return {}


def post(hook: dict, title: str, md: str) -> str:
    """Send one report to the webhook. Returns "" when it went, else why it didn't.
    The body is JSON with the whole report under "context" (what a Cursor automation's webhook hands its agent) and
    under "text" (what chat webhooks read), plus "title". `"format": "text"` in the config sends plain text instead."""
    import urllib.error
    import urllib.request
    text = f"{title}\n\n{md}\n"
    if hook.get("format") == "text":
        data, kind = text.encode(), "text/plain; charset=utf-8"
    else:
        data, kind = json.dumps({"title": title, "context": text, "text": text}).encode(), "application/json"
    req = urllib.request.Request(hook["url"], data=data, method="POST",
                                 headers={"Content-Type": kind, "User-Agent": "matthew-studio-kit"})
    if hook.get("bearer"):
        req.add_header("Authorization", f"Bearer {hook['bearer']}")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return "" if 200 <= r.status < 300 else f"the webhook answered {r.status}"
    except urllib.error.HTTPError as e:
        return f"the webhook answered {e.code}"
    except (urllib.error.URLError, OSError, ValueError) as e:
        return f"couldn't reach the webhook ({getattr(e, 'reason', e)})"


def auto_on() -> bool:
    """He said yes, once, to problems being sent to Mitchell without asking each time."""
    try:
        return json.loads(PREFS.read_text()).get("feedback_auto") is True
    except (OSError, ValueError, AttributeError):
        return False


def set_auto(on: bool) -> None:
    try:
        d = json.loads(PREFS.read_text())
    except (OSError, ValueError):
        d = {}
    d["feedback_auto"] = bool(on)
    PREFS.parent.mkdir(parents=True, exist_ok=True)
    PREFS.write_text(json.dumps(d, indent=2))


def job_facts(job: str) -> list[str]:
    """A few facts about the job's plan, so the problem can be reproduced: never its words or its footage."""
    if not job:
        return []
    p = KIT / ".work" / job / "edl.json"
    if not p.is_file():
        hf = KIT / ".work" / "hf" / job
        return [f"- job: `{job}` ({'a standalone HyperFrames project, not built through bin/kit' if hf.is_dir() else 'no plan found'})"]
    try:
        e = json.loads(p.read_text())
    except (OSError, ValueError):
        return [f"- job: `{job}` (its plan could not be read)"]
    cuts = e.get("cuts") or []
    o = e.get("output") or {}
    names = sorted({str(b.get("name")) for b in e.get("blocks") or [] if b.get("name")})
    hacks = [k for k, on in (("audio.pre", bool((e.get("audio") or {}).get("pre"))),
                             ("end_fade_s 0", (e.get("style") or {}).get("end_fade_s") == 0),
                             ("keep_pauses", e.get("keep_pauses") is True), ("swipe off", e.get("swipe") is False),
                             ("sfx_auto off", e.get("sfx_auto") is False)) if on]
    return [f"- job: `{job}` ({o.get('w', '?')}x{o.get('h', '?')}, style `{e.get('style_name', '')}`, theme `{e.get('theme', '')}`)",
            f"- voice: audio_rev {e.get('audio_rev', 1)}, {len(cuts)} kept pieces, {sum(float(c['out']) - float(c['in']) for c in cuts):.1f} s",
            f"- in the plan: {len(e.get('blocks') or [])} graphics ({', '.join(names[:12]) or 'none'}), {len(e.get('broll') or [])} b-roll, "
            f"{len(e.get('sfx') or [])} sounds" + (f"; hand settings: {', '.join(hacks)}" if hacks else "")]


def body(note: str, version: str, hf_version: str, job: str = "") -> tuple[str, str, str]:
    """(title, markdown body, signature of the failure)."""
    evs = events(15)
    recent = (dt.datetime.now() - dt.timedelta(hours=3)).isoformat(timespec="seconds")
    fail = next((e for e in reversed(evs) if e.get("code") and e.get("t", "") >= recent), None)   # an old failure isn't this problem
    first = (fail.get("error", "").strip().splitlines() or [f"exit {fail['code']}"])[-1] if fail else ""
    said = re.sub(r"\s+", " ", note).strip()
    # what he said is the report; a command that failed earlier is context, not the headline
    sig = hashlib.sha1(re.sub(r"[0-9]+", "#", said or (f"{fail['cmd']} {first}" if fail else "")).encode()).hexdigest()[:10]
    what = said[:80] or (f"{fail['cmd']} failed: {first}" if fail else "problem report")
    title = scrub(f"kit report: {what}")[:110]
    rows = "\n".join(f"| {e['t']} | `{e['cmd']} {e.get('args', '')[:80]}` | {e['code']} | {e['secs']} s |" for e in evs)
    try:
        dlog = (KIT / ".cache" / "deps" / "log.txt").read_text().splitlines()[-5:]
    except OSError:
        dlog = []
    md = [f"**What he was doing:** {scrub(note) or '(no note)'}", "",
          f"- kit: `{version}`", f"- HyperFrames: `{hf_version}`",
          f"- Mac: macOS {platform.mac_ver()[0] or platform.platform()} ({platform.machine()})", f"- signature: `{sig}`",
          *job_facts(job), ""]
    if fail:
        md += [f"### Last failure: `{fail['cmd']} {fail.get('args', '')}` at {fail['t']} (exit {fail['code']})",
               "```", fail.get("error", "(no message)")[-3000:], "```", ""]
    md += ["### Last commands", "| time | command | exit | took |", "|---|---|---|---|", rows or "| | (no log yet) | | |", ""]
    if dlog:
        md += ["### Updater log", "```", scrub("\n".join(dlog)), "```", ""]
    md += ["### For the fixing agent",
           "Reproduce on the same kit commit with one of your own clips (his footage isn't attached). Fix it clip-agnostically, "
           "ship it as a PR on the kit's repo. His kit picks the fix up by itself within a day of the merge.",
           "", "_Sent by `bin/kit report`. No video, transcript or secrets are included._"]
    return title, scrub("\n".join(md)), sig


def send(note: str, version: str, hf_version: str, dry: bool = False, job: str = "") -> int:
    title, md, sig = body(note, version, hf_version, job)
    hook = webhook()
    if dry:
        print(f"TO: {'Mitchell (webhook set on this Mac)' if hook else 'GitHub issue on ' + repo()}\n\n{title}\n\n{md}")
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
    if hook:
        why = post(hook, title, md)
        if why:
            print(f"couldn't send it ({why}). The report is saved at {scrub(out)}.")
            return 1
        sent[sig] = {"at": now, "url": "webhook"}
        SENT.write_text(json.dumps(sent, indent=1))
        print("sent to Mitchell.")
        return 0
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
