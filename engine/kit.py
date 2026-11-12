#!/usr/bin/env python3
"""Matthew Studio Kit: the commands the Codex skills run. Same pipeline every time: draft (Python), Codex's choices,
preview in HyperFrames Studio (he watches the whole edit before anything renders), one render, QA (Python).

  kit version                                  the kit's version and exact commit
  kit doctor                                   check ffmpeg, Python packages, Node + HyperFrames, fonts, the speech model
  kit prepare                                  first run: fetch the tested HyperFrames and its Chrome (needs internet once)
  kit update                                   pull the newest kit, then bring HyperFrames and the Python packages up to date
  kit deps status | check | rollback           the outside libraries: they update on their own once a day, tested first (engine/deps.py)
  kit transcribe <clip>                        word timings (cached by the clip's sha256)
  kit draft <clip> [--style <name>] [--long]   make a job folder with a first edit plan (edl.json) + the transcript to review
                                               (default look: real-world UI replicas; --long is a 16:9 YouTube edit)
  kit preview <job> [<job> ...] [--rebuild]    open each job in its own Studio tab (live; nothing rendered until kit render)
  kit preview --stop                           close the Studio servers
  kit render <job>                             render the job as it stands in Studio, run QA; a PASS goes to done/
  kit qa <video> [--job <job>]                 run the QA gate on a video
  kit style list | show <name> | new <name> [--from <style>] | set <name> key=value ... [--as <new>]
  kit style snapshot <name> | test <name> | versions <name> | restore <name> <version> | preview <name> [--clip <clip>]
  kit style undo [<name>]                      undo the newest saved change (the style changed last if no name); again = further back
  kit style sheet <reel.mp4>                   a contact sheet of a reference reel (.work/_refs/) to build a style from
  kit style import <old kit folder>            copy his saved styles from the old Matthew Edit Kit
  kit graphics list | test <graphic>           the kit's own graphics (logo pop, picture card, text card)
  kit blocks search <words> | test <name>      HyperFrames library blocks (about 200: chat and app mock-ups, charts, titles ...)
  kit library list [<words>] [--type t]        local files in library/ (b-roll, pictures, sound effects)
  kit library add <file> --type broll|picture|sfx --name <name> [--tags a,b]
  kit library find <words> [--kind ...] [--origin ai|stock] [--aspect vertical|horizontal|square]
                                               search the Notion index built from his Content page
  kit library setup --input hub.json            plan the one-time Content page setup (tables + fields the kit needs)
  kit library detect|plan|index|override|workflow
                                               local Notion index commands (docs/NOTION-MCP.md)
  kit library upload <file> --role broll|pictures|styles --name <title> [--origin ai|stock|own|unknown]
                                               plan one create in the Content hub authorized this session
  kit library sort plan|frames|apply           look at b-roll frames and record what they show (local; --batch N to download)
  kit library sort writeback --input snapshot.json [--page-id a,b]
                                               plan reviewed B-roll titles and tags for his Notion B Roll table (prints a plan only)
  kit library sync|connect                     disabled; the Codex Notion connection is used instead
  kit support status|enable|disable|doctor|rules|compare|inspect|sync|remote
                                               opt-in GitHub diagnostics; never changes styles or grants tool permissions
  kit report [--note "<what he was doing>"] [--dry-run]
                                               file a problem report for Mitchell as a GitHub issue: the last error, recent
                                               commands, versions (never a video, transcript or secret). Every command is
                                               logged to .cache/log/events.jsonl for it.

Every job lives in .work/<job>/. Nothing outside the kit folder is written except done/.
"""
from __future__ import annotations

import argparse
import atexit
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import deps  # noqa: E402  (engine/deps.py: the outside libraries update themselves, tested first)
import report  # noqa: E402  (engine/report.py: the command log and problem reports)

KIT = Path(__file__).resolve().parent.parent
ENGINE = KIT / "engine"
NODE_MIN = 22                      # HyperFrames' own requirement (its package.json: engines.node >=22)
LAST_ERROR = ""                    # what the command died with, for the log (engine/report.py)
STYLES = KIT / "styles"            # built-in styles (ship with the kit, updated by git pull)
USER_STYLES = KIT / "my-styles"    # his saved styles and edits (never touched by updates; wins over built-in)
GRAPHICS = KIT / "graphics"
WORK = KIT / ".work"
DONE = KIT / "done"
CACHE = Path(os.environ.get("KIT_WORDS_CACHE") or KIT / ".cache" / "words")

# Words that are never the crimson keyword (helper verbs, pronouns, small words).
STOP = set("""a an the and or but so to of in on at for with from by is are was were be been being am do does did has have had
will would should can could may might must won't wouldn't can't don't doesn't didn't isn't aren't wasn't i me my you your he
him his she her it its we us our they them their this that these those what which who where when while why how then than
there here now not no just very really still also even only too much many more most some any all every each another other
such same like well about into over up down out if as because though yeah okay um uh i'm you're it's that's we're they're
we'll you'll i'll let's""".split())
FILLERS = {"um", "uh", "er", "erm", "hmm", "uhm", "umm"}
BRANDS = {"youtube": "youtube", "instagram": "instagram", "snapchat": "snapchat", "tiktok": "tiktok",
          "hinge": "hinge", "tinder": "tinder", "bumble": "bumble"}   # a logo pops only when assets/logos has its file


def style_dir(name: str) -> Path:
    """Where a style is read from: his saved copy first, else the built-in one."""
    u = USER_STYLES / name
    return u if (u / "style.json").exists() else STYLES / name


def own_style(name: str) -> Path:
    """Where a style is written: his copy. The first edit of a built-in style copies it over."""
    u = USER_STYLES / name
    if not (u / "style.json").exists() and (STYLES / name / "style.json").exists():
        shutil.copytree(STYLES / name, u, ignore=shutil.ignore_patterns("versions", "out", "__pycache__"), dirs_exist_ok=True)
    return u


def die(msg: str, code: int = 1):
    global LAST_ERROR
    LAST_ERROR = msg
    print(f"kit: {msg}", file=sys.stderr)
    sys.exit(code)


MODEL = "models--Systran--faster-whisper-small.en"


def speech_home() -> Path | None:
    """Where the speech model lives: the usual ~/.cache/huggingface, unless that can't be written (Codex's sandbox) and
    the model isn't there yet; then inside the kit."""
    home = Path.home() / ".cache" / "huggingface"
    if (home / "hub" / MODEL).exists():
        return None
    try:
        (home / "hub").mkdir(parents=True, exist_ok=True)
        t = home / "hub" / f".kit-write-test-{os.getpid()}"; t.touch(); t.unlink()
        return None
    except OSError:
        return KIT / ".cache" / "huggingface"


def env() -> dict:
    """Homebrew's ffmpeg-full first: the build the kit is tested with. The speech model's folder (speech_home)."""
    e = dict(os.environ)
    for prefix in ("/opt/homebrew/opt/ffmpeg-full/bin", "/usr/local/opt/ffmpeg-full/bin"):
        if Path(prefix, "ffmpeg").exists():
            e["PATH"] = prefix + os.pathsep + e.get("PATH", "")
            break
    sh = speech_home()
    if sh and "HF_HOME" not in e:
        e["HF_HOME"] = os.environ["HF_HOME"] = str(sh)   # also for the listener that runs in this process
    return e


def py() -> str:
    """The kit's own Python (.venv). Never the Mac's: its packages aren't the pinned, tested ones."""
    venv = KIT / ".venv" / "bin" / "python"
    if not venv.exists():
        die(f"the kit's Python isn't set up. In {KIT}: python3.12 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt")
    return str(venv)


# Codex also loads skills installed elsewhere on the Mac. Ones with these words could take over a video request.
CLASH = re.compile(r"video|edit|caption|short|reel|remotion|hyperframes|media|motion|episode|style|qa|render", re.I)


def other_skills() -> list[str]:
    """Video-related skills Codex can see outside this kit (user skill folders and installed plugins)."""
    found = []
    for d in (Path.home() / ".codex" / "skills", Path.home() / ".agents" / "skills"):
        if d.is_dir():
            found += [f"{p.name} ({d})" for p in sorted(d.iterdir()) if (p / "SKILL.md").exists() and CLASH.search(p.name)]
    cache = Path.home() / ".codex" / "plugins" / "cache"
    if cache.is_dir():
        found += [f"{p.parent.name} (plugin)" for p in sorted(cache.glob("*/*/skills/*/SKILL.md")) if CLASH.search(p.parent.name)
                  and "matthew-edit-kit" not in str(p) and "matthew-studio-kit" not in str(p)]
    return found


def norm(w: str) -> str:
    return re.sub(r"[^a-z0-9']", "", w.lower())


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def run_core(args: list[str]) -> int:
    """Transcribe and the cheap output checks (engine/quick_edit.py)."""
    return subprocess.call([py(), str(ENGINE / "quick_edit.py"), *args], env=env())


def hfm():
    """engine/render_hf.py (the HyperFrames renderer), imported with the kit's PATH."""
    sys.path.insert(0, str(ENGINE))
    os.environ["PATH"] = env()["PATH"]
    import render_hf
    return render_hf


# ---------------------------------------------------------------- doctor
def kit_version() -> str:
    """Version from plugin.json plus the exact git commit, e.g. 1.0.0 (v1.0.0, e5eaf60)."""
    ver = json.load(open(KIT / "plugin.json")).get("version", "?")
    try:
        desc = subprocess.run(["git", "-C", str(KIT), "describe", "--tags", "--always", "--dirty"],
                              capture_output=True, text=True).stdout.strip()
    except Exception:
        desc = ""
    return f"{ver} ({desc})" if desc else ver


def cmd_version(a) -> int:
    print(f"matthew-studio-kit {kit_version()}")
    return 0


def cmd_doctor(a) -> int:
    ok = True
    print(f"kit version: {kit_version()}")

    def line(good: bool, what: str, fix: str = ""):
        nonlocal ok
        ok = ok and good
        print(f"{'OK  ' if good else 'FIX '} {what}" + ("" if good else f"\n      -> {fix}"))

    e = env()
    ff = shutil.which("ffmpeg", path=e["PATH"])
    line(bool(ff), f"ffmpeg: {ff or 'missing'}", "brew install ffmpeg-full")
    if ff:
        enc = subprocess.run([ff, "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
        line("libx264" in enc, "ffmpeg has libx264", "brew install ffmpeg-full")
    venv = KIT / ".venv" / "bin" / "python"
    line(venv.exists(), f"the kit's own Python ({venv.relative_to(KIT)})", f"cd {KIT} && python3.12 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt")
    if venv.exists():
        for mod, pkg in [("faster_whisper", "faster-whisper"), ("numpy", "numpy"), ("PIL", "pillow")]:
            r = subprocess.run([str(venv), "-c", f"import {mod}"], capture_output=True)
            line(r.returncode == 0, f"python package {pkg}", f"cd {KIT} && .venv/bin/python -m pip install -r requirements.txt")
        if sys.platform == "darwin":
            r = subprocess.run([str(venv), "-c", "import Vision, Foundation"], capture_output=True)
            line(r.returncode == 0, "Apple Vision for QA (pyobjc)", f"cd {KIT} && .venv/bin/python -m pip install -r requirements.txt")
    nd = shutil.which("node", path=e["PATH"]) or shutil.which("node", path="/opt/homebrew/bin:/usr/local/bin")
    nv = subprocess.run([nd, "--version"], capture_output=True, text=True).stdout.strip() if nd else ""
    line(bool(nd) and int((nv.lstrip("v").split(".") or ["0"])[0] or 0) >= NODE_MIN, f"Node.js {nv or 'missing'} ({NODE_MIN} or newer, for HyperFrames)",
         "brew install node" if not nd else "brew upgrade node")
    hfr = hfm()
    want = json.load(open(hfr.FLOOR))["version"]
    got = subprocess.run(hfr.hf() + ["--version"], capture_output=True, text=True, env=hfr.env(), timeout=300).stdout.strip() if nd else ""
    line(bool(got), f"HyperFrames {got or 'missing'} (kit tested {want}; newer ones switch in on their own after passing a test)",
         f"cd {KIT} && bin/kit prepare   (needs internet once)")
    br = subprocess.run(hfr.hf() + ["browser", "path"], capture_output=True, text=True, env=hfr.env(), timeout=300).stdout.strip() if got else ""
    line(bool(br) and Path(br.splitlines()[-1]).exists(), "HyperFrames' Chrome (preview and render)", f"cd {KIT} && bin/kit prepare   (needs internet once)")
    line((ENGINE / "vendor/gsap.min.js").exists(), "animation library (engine/vendor/gsap.min.js)", "re-clone the kit")
    line((KIT / ".codex/rules/kit.rules").exists(), "Codex rule that lets previews and renders start Chrome (.codex/rules/kit.rules)", "re-clone the kit")
    line((KIT / "assets/fonts/Montserrat-ExtraBold.ttf").exists(), "caption font", "re-clone the kit")
    line((STYLES / "premium-motion/style.json").exists(), "default Short look", "re-clone the kit")
    gh = shutil.which("gh", path=e["PATH"]) or shutil.which("gh", path="/opt/homebrew/bin:/usr/local/bin")
    gha = gh and subprocess.run([gh, "auth", "status"], capture_output=True, text=True).returncode == 0
    line(bool(gha), "GitHub login (kit updates, and problem reports to Mitchell)", "brew install gh, then gh auth login" if not gh else "gh auth login")
    sm = [p / "hub" / MODEL for p in (Path.home() / ".cache/huggingface", KIT / ".cache/huggingface")]
    line(any(p.exists() for p in sm), "speech model small.en (464 MB)", "it downloads on the first transcribe; needs internet once")
    others = other_skills()
    if others:
        print(f"NOTE {len(others)} other video skill(s) on this Mac that Codex can see. The kit ignores them (AGENTS.md), "
              "but if one ever takes over an edit, move it aside (skills/setup step 8):")
        for o in others:
            print(f"       {o}")
    print("Ready to edit." if ok else "Fix the lines marked FIX, then run kit doctor again.")
    return 0 if ok else 1


def cmd_prepare(a) -> int:
    """First run: fetch the tested HyperFrames and its Chrome (once, about 200 MB)."""
    hfr = hfm()
    for args in (["--version"], ["browser", "ensure"]):
        if subprocess.call(hfr.hf() + args, env=hfr.env()) != 0:
            die(f"couldn't get HyperFrames ({' '.join(args)}). It needs the internet once.")
    print(f"HyperFrames {hfr.hf_version()} and its Chrome are ready.")
    return 0


def cmd_update(a) -> int:
    """New kit version from GitHub, then the outside libraries: never older than tested, newest that passes the test."""
    if subprocess.call(["git", "-C", str(KIT), "pull", "--ff-only"]) != 0:
        die("couldn't pull the update (see above). His styles in my-styles/ are safe either way.")
    deps.floor()
    deps.check(now=True)
    deps.apply()
    print(f"matthew-studio-kit {kit_version()}")
    return 0


def cmd_deps(a) -> int:
    return {"status": deps.status, "check": lambda: deps.check(now=True), "rollback": deps.rollback}[a.action]()


# ---------------------------------------------------------------- transcribe
def words_path(clip: Path) -> Path:
    return CACHE / f"{sha256(clip)}.small.en.words.json"


def cmd_transcribe(a) -> int:
    clip = Path(a.clip).expanduser().resolve()
    if not clip.is_file():
        die(f"clip not found: {clip}")
    rc = run_core(["transcribe", str(clip)])
    if rc == 0:
        print(words_path(clip))
    return rc


# ---------------------------------------------------------------- draft
def load_words(p: Path) -> list[dict]:
    d = json.load(open(p))
    return d["words"] if isinstance(d, dict) else d


def draft_cuts(words: list[dict], pause: float = 0.35, pad: float = 0.08) -> list[dict]:
    """Keep every word; drop pauses longer than `pause` and filler words. Retakes are Codex's call (see the skill).

    A filler always splits the cut, even when the words on either side are close. Padding
    stays outside the word and outside the filler, so a cut never starts or ends inside a word.
    """
    fillers = [w for w in words if norm(w["w"]) in FILLERS]
    keep = [w for w in words if norm(w["w"]) not in FILLERS]

    def filler_between(a: float, b: float) -> bool:
        return any(float(f["start"]) < b - 1e-4 and float(f["end"]) > a + 1e-4 for f in fillers)

    cuts, cur = [], None
    for w in keep:
        s, e = float(w["start"]), float(w["end"])
        if cur and not filler_between(cur["out"], s) and s - cur["out"] <= pause:
            cur["out"] = e
        else:
            if cur:
                cuts.append(cur)
            cur = {"in": s, "out": e}
    if cur:
        cuts.append(cur)
    out = []
    for c in cuts:
        lo, hi = c["in"] - pad, c["out"] + pad
        # padding never reaches into a removed filler, and never back into the word
        for f in fillers:
            fs, fe = float(f["start"]), float(f["end"])
            if fe <= c["in"] and fe > lo:
                lo = fe
            if fs < hi and fe > c["out"]:
                hi = min(hi, max(c["out"], fs))
        if out and lo < out[-1]["out"]:
            lo = out[-1]["out"]
        lo = min(lo, c["in"])
        hi = max(hi, c["out"])
        out.append({"in": round(max(0.0, lo), 3), "out": round(hi, 3)})
    return out


def _source_to_output(cuts, t):
    acc = 0.0
    for c in cuts:
        if t < c["in"]:
            return acc
        if t <= c["out"]:
            return acc + (t - c["in"])
        acc += c["out"] - c["in"]
    return acc


def cut_to_short(cuts, words, target=15.0):
    """About 15 seconds of an edit, snapped to word edges. The long cuts are not changed.

    A run that is already near the target is returned as it is. Otherwise the window of
    kept words whose output length is closest to 15s becomes the short.
    """
    if not cuts:
        return []
    total = _source_to_output(cuts, cuts[-1]["out"])
    if total <= target + 0.75:
        return [dict(c) for c in cuts]

    def inside(t):
        return any(c["in"] <= t <= c["out"] for c in cuts)

    kept = []
    for w in words:
        if norm(w.get("w") or "") in FILLERS:
            continue
        start, end = float(w.get("start", w.get("s", 0))), float(w.get("end", w.get("e", 0)))
        if inside((start + end) / 2):
            kept.append((start, end, w))
    if not kept:
        return [dict(c) for c in cuts]
    best = None
    for i in range(len(kept)):
        for j in range(i, len(kept)):
            dur = _source_to_output(cuts, kept[j][1]) - _source_to_output(cuts, kept[i][0])
            if dur < 8:
                continue
            if dur > target + 5:
                break
            err = abs(dur - target) - min(len(norm(kept[i][2].get("w") or "")), 12) * 0.01
            if best is None or err < best[0]:
                best = (err, i, j)
    if best is None:
        i = j = 0
        for j in range(len(kept)):
            if _source_to_output(cuts, kept[j][1]) - _source_to_output(cuts, kept[0][0]) >= target:
                break
        span = (0, j)
    else:
        span = (best[1], best[2])
    t0, t1 = kept[span[0]][0], kept[span[1]][1]
    short = []
    for c in cuts:
        a, b = max(c["in"], t0), min(c["out"], t1)
        if b - a >= 0.05:
            short.append({"in": round(a, 3), "out": round(b, 3)})
    return short or [dict(c) for c in cuts]


# Common verbs and fillers that read as noise in crimson.
WEAK = set("""give gave getting get got make made want going doing being enough thing things stuff something someone
really actually always never maybe think know knew said says saying look looking feel feeling kind sort""".split())


def draft_keywords(words: list[dict], window: int = 4) -> list[str]:
    """About one crimson word per `window` words: brand names, numbers, then the longest strong word (5+ letters)."""
    keys: list[str] = []
    for i in range(0, len(words), window):
        best = None
        for w in words[i : i + window]:
            n = norm(w["w"])
            if not n or n in STOP or n in FILLERS or n in WEAK:
                continue
            kind = 3 if n in BRANDS else 2 if any(ch.isdigit() for ch in n) else 1
            if kind == 1 and len(n) < 5:
                continue
            score = (kind, len(n))
            if best is None or score > best[0]:
                best = (score, w["w"])
        if best and norm(best[1]) not in {norm(k) for k in keys}:
            keys.append(best[1])
    return keys


def cmd_draft(a) -> int:
    clip = Path(a.clip).expanduser().resolve()
    if not clip.is_file():
        die(f"clip not found: {clip}")
    style = a.style or ("matthew-long" if a.long else "premium-motion")
    if not (style_dir(style) / "style.json").exists():
        die(f"style {style!r} not found. Styles: {', '.join(list_styles())}")
    wp = words_path(clip)
    if not wp.exists():
        if run_core(["transcribe", str(clip)]) != 0:
            die("transcription failed")
    words = load_words(wp)
    name = re.sub(r"-+", "-", re.sub(r"[^a-z0-9_-]+", "-", (a.name or clip.stem).lower())).strip("-")[:40] or "clip"
    job = WORK / name
    if (job / "edl.json").exists():
        if not a.replace:
            die(f"there's already a job called {name} (from {json.load(open(job / 'edl.json')).get('source', '?')}). "
                f"Pick another --name, or --replace to start it over (drops its plan and any hand edits in Studio).")
        shutil.rmtree(job)
        shutil.rmtree(WORK / "_studio" / name, ignore_errors=True)
    (job / "inputs").mkdir(parents=True, exist_ok=True)
    src_link = job / "inputs" / clip.name
    if src_link.is_symlink() or src_link.exists():
        src_link.unlink()
    src_link.symlink_to(clip)
    shutil.copy2(wp, job / "inputs" / "words.json")
    st = json.load(open(style_dir(style) / "style.json"))
    edl = {
        "name": name,
        "style_name": style,
        "source": f"inputs/{clip.name}",
        "words": "inputs/words.json",
        "cuts": draft_cuts(words),
        "keywords": draft_keywords(words),
        "caption_breaks": [],
        "overlays": [],
        "caption_hide": [],
        "broll": [],
        "sfx": [],
        "output": {"w": 1920, "h": 1080, "fps": 30} if (a.long or st.get("shape") == "16:9") else {"w": 1080, "h": 1920, "fps": 30},
        "blocks": [],
    }
    import library
    # B-roll goes in on its own only when his style says so ("broll": {"auto": true}); otherwise he asks for it.
    if (st.get("broll") or {}).get("auto"):
        edl["broll"] = library.select_broll(words, edl["keywords"], edl["cuts"])
    if (st.get("logos") or {}).get("enabled"):
        add_logo_overlays(edl, words, st, job)
    json.dump(edl, open(job / "edl.json", "w"), indent=2)
    short_note = _write_short_beside(name, edl, words, clip)
    # The transcript Codex reviews: restarts the listener heard first, then one line per word with its source time.
    hints = restart_hints(clip)
    with open(job / "TRANSCRIPT.txt", "w") as f:
        if hints:
            f.write("RESTARTS HEARD (the transcript below may show these only once). Cut the first take, keep the last:\n")
            for h in hints:
                f.write(f"  {h['first_start']:.2f}-{h['first_end']:.2f}  first take  \"{h['text']}\"   retake starts {h['retake_start']:.2f}\n")
            f.write("\n")
        for w in words:
            f.write(f"{float(w['start']):7.2f}-{float(w['end']):6.2f}  {w['w']}\n")
    print(f"job: {job}")
    print(f"plan: {job / 'edl.json'}  ({len(edl['cuts'])} kept pieces, {len(edl['keywords'])} keywords, style {style})")
    print(f"transcript: {job / 'TRANSCRIPT.txt'}" + (f"  ({len(hints)} restart(s) heard, listed at the top)" if hints else ""))
    print(f"Review the plan ({'skills/long-form' if a.long else 'skills/edit-short step 3'}), then: kit preview {name}")
    if edl["broll"]:
        print(f"b-roll: {len(edl['broll'])} clip(s) placed from the library on the keyword lines")
    if short_note:
        print(short_note)
    return 0


def _write_short_beside(name, edl, words, clip: Path) -> str:
    """When the edit runs long, write a ~15s vertical job next to it. The long plan is left as it is."""
    if name.endswith("-15s"):
        return ""
    full = sum(c["out"] - c["in"] for c in edl["cuts"])
    if full <= 16:
        return ""
    short_cuts = cut_to_short(edl["cuts"], words, 15.0)
    short_dur = sum(c["out"] - c["in"] for c in short_cuts)
    if short_dur > 17 or abs(short_dur - full) < 0.5:
        return ""
    short_name = (name[:36] + "-15s").strip("-")
    job = WORK / short_name
    if (job / "edl.json").exists():
        return f"15s short already at {job} (left as it is)"
    (job / "inputs").mkdir(parents=True, exist_ok=True)
    src_link = job / "inputs" / clip.name
    if not src_link.exists():
        src_link.symlink_to(clip)
    words_src = WORK / name / "inputs" / "words.json"
    if words_src.is_file():
        shutil.copy2(words_src, job / "inputs" / "words.json")
    style = edl.get("style_name") or "premium-motion"
    if style.endswith("-long"):
        short = style[: -len("-long")]
        if short == "matthew" or not (style_dir(short) / "style.json").exists():
            style = "premium-motion"
        else:
            style = short
    import library
    short = {
        "name": short_name,
        "style_name": style,
        "source": f"inputs/{clip.name}",
        "words": "inputs/words.json",
        "cuts": short_cuts,
        "keywords": edl.get("keywords") or [],
        "caption_breaks": [],
        "overlays": [],
        "caption_hide": [],
        "broll": library.select_broll(words, edl.get("keywords") or [], short_cuts) if edl.get("broll") else [],
        "sfx": [],
        "output": {"w": 1080, "h": 1920, "fps": 30},
        "blocks": [],
    }
    json.dump(short, open(job / "edl.json", "w"), indent=2)
    return f"15s short: {job}  ({short_dur:.1f} s beside the {full:.1f} s edit)"


def restart_hints(clip: Path) -> list[dict]:
    """Restarts heard by the short-piece listener (engine/listen.py), using QA's own repeat finder."""
    sys.path.insert(0, str(ENGINE))
    try:
        import listen
        import qa
    except ImportError:
        return []
    os.environ["PATH"] = env()["PATH"]
    heard = listen.chunk_words(listen.load_audio(str(clip)), listen.model())
    return listen.restarts(heard, qa.find_repeats)


def add_logo_overlays(edl: dict, words: list[dict], st: dict, job: Path) -> None:
    """Logo tiles once, the first time he names an app with a logo file (YouTube, Instagram, Snapchat, TikTok...) in the first 10 s."""
    hits = []
    for w in words:
        n = norm(w["w"])
        if n in BRANDS and float(w["start"]) <= 10 and n not in [h[0] for h in hits]:
            hits.append((n, float(w["start"])))
    logos = st.get("logos") or {}
    edl["_logo_hits"] = [{"brand": n, "source_t": t, "logo": logos.get(n, f"assets/logos/{n}.png")} for n, t in hits
                         if (KIT / logos.get(n, f"assets/logos/{n}.png")).is_file()]


def output_time(edl: dict, t: float) -> float | None:
    """Source time -> output time through the kept pieces (None if cut)."""
    acc = 0.0
    for c in edl["cuts"]:
        if c["in"] <= t <= c["out"]:
            return acc + (t - c["in"])
        acc += c["out"] - c["in"]
    return None


def place_logos(edl: dict) -> None:
    """Turn _logo_hits into overlays + a caption-hide window, after Codex has settled the cuts."""
    hits = edl.get("_logo_hits") or []
    if not hits:
        return
    o = edl.get("output") or {}
    wide = int(o.get("w", 1080)) > int(o.get("h", 1920))
    cx, y = (int(o.get("w", 1920)) / 2, int(o.get("h", 1080)) * 0.45) if wide else (540, 1180)   # px of a 1080-short-side frame
    xs = [cx] if len(hits) == 1 else [cx - 210, cx + 210]
    logos = json.load(open(style_dir(edl.get("style_name") or "premium-motion") / "style.json")).get("logos") or {}
    overlays, ats = [], []
    for h, x in zip(hits, xs):
        at = output_time(edl, h["source_t"])
        if at is None:
            continue
        ats.append(at)
        overlays.append({"template": "logo_pop", "props": {"logo": h.get("logo") or logos.get(h["brand"], f"assets/logos/{h['brand']}.png")},
                         "at": round(at, 3), "dur": 0, "x": x, "y": y})
    if not overlays:
        return
    end = max(ats) + 1.2
    for o in overlays:
        o["dur"] = round(end - o["at"], 3)
    edl["overlays"] = [o for o in edl.get("overlays") or [] if o.get("template") != "logo_pop" and "logo_pop" not in o.get("file", "")] + overlays
    hide = [w for w in edl.get("caption_hide") or [] if not w or w[0] > end or w[1] < min(ats)]
    edl["caption_hide"] = hide + [[round(min(ats), 3), round(end, 3)]]


# ---------------------------------------------------------------- render + qa
def cmd_render(a) -> int:
    job = resolve_job(a.job)
    edl_p = job / "edl.json"
    edl = json.load(open(edl_p))
    place_logos(edl)
    json.dump(edl, open(edl_p, "w"), indent=2)
    hfr = hfm()
    proj, status = hfr.build(edl_p)
    print(f"project: {proj} ({status})")
    name = edl.get("name") or job.name
    mp4 = hfr.render(proj, str(job / "out" / f"{name}.mp4"))
    return finish_render(Path(mp4), job)


def finish_render(mp4: Path, job: Path) -> int:
    verdict = run_qa(mp4, job)
    if verdict == "PASS":
        DONE.mkdir(exist_ok=True)
        dest = DONE / mp4.name
        shutil.copy2(mp4, dest)
        shutil.copy2(job / "out" / "qa" / "QA-REPORT.md", DONE / f"{mp4.stem}.QA-REPORT.md")
        print(f"PASS -> {dest}")
        return 0
    global LAST_ERROR
    try:
        items = json.load(open(job / "out" / "qa" / "qa.json"))["items"]
        fails = [f"{i['check']} at {i['start'] if i['start'] is not None else '-'}s: {i['msg']}" for i in items if i["sev"] == "FAIL"]
    except (OSError, ValueError, KeyError):
        fails = []
    LAST_ERROR = f"QA FAIL on {job.name}: " + (" | ".join(fails[:5]) or "see QA-REPORT.md")
    print(f"FAIL -> fix the flags in {job / 'out' / 'qa' / 'QA-REPORT.md'}, then kit render {job.name} again (max 2 rounds).")
    return 2


def cmd_preview(a) -> int:
    """Open each job in HyperFrames Studio (live preview, nothing rendered), one tab per job."""
    render_hf = hfm()
    if a.stop:   # the named jobs' Studio servers, or all of them
        for proj in [render_hf.project_dir(resolve_job(n).name) for n in a.jobs] or sorted(Path(render_hf.STUDIO).glob("*/")):
            render_hf.stop(str(proj))
        return 0
    if not a.jobs:
        die("name the job(s) to preview, e.g. kit preview coaching-gap-15s")
    for i, name in enumerate(a.jobs):
        job = resolve_job(name)
        edl_p = job / "edl.json"
        edl = json.load(open(edl_p))
        place_logos(edl)
        json.dump(edl, open(edl_p, "w"), indent=2)
        proj, status = render_hf.build(edl_p, force=a.rebuild)
        code, log = render_hf.check(proj)
        if code:
            print(log[-2000:])
            die(f"{job.name}: hyperframes check failed (above). Fix {proj}/index.html, then kit preview {job.name} again.")
        if "note, caption colour" in log:
            print(f"{job.name}: {log}")
        url, started = render_hf.preview(proj, a.port + i)
        print(f"{job.name}: {url}  ({status}; {'new Studio tab' if started else 'open tab reloads'})")
        if started and a.open:   # only a brand-new server gets a tab, and only when asked for
            subprocess.call(["open", url])
    print("Studio only: nothing is rendered. Notes update the open tab. Render when he says so: kit render <job>")
    return 0


def qa_extra_args(job: Path | None) -> list[str]:
    """Flags the QA gate already accepts: output-timed words, the voice stem, and the style's loudness target.

    Source-word times are not passed. They still sit on the raw clip's clock, so a cut would look like a missing word.
    The voice stem is the one HyperFrames mixed (`.work/_studio/<job>/assets/voice.wav`), written at render time.
    """
    if job is None or not (job / "edl.json").is_file():
        return []
    edl = json.load(open(job / "edl.json"))
    extra: list[str] = []
    words_rel = edl.get("words")
    if words_rel:
        src = Path(words_rel) if Path(words_rel).is_absolute() else job / words_rel
        if src.is_file():
            import quick_edit as qe
            raw = qe.load_words(str(src))
            st = qe.resolve_style(edl)
            fps = int((edl.get("output") or {}).get("fps", 30))
            pieces = qe.build_pieces(edl, raw, st, fps)
            mapped, _total = qe.map_words(raw, pieces)
            out_words = job / "out" / "qa-words.json"
            out_words.parent.mkdir(parents=True, exist_ok=True)
            payload = {"words": [{"w": w["w"], "s": round(w["s"], 3), "e": round(w["e"], 3)} for w in mapped]}
            if edl.get("sfx"):
                payload["sfx"] = [[s.get("file", ""), s.get("at", 0)] for s in edl["sfx"]]
            json.dump(payload, open(out_words, "w"))
            extra += ["--words", str(out_words)]
            target = (st.get("loudness") or {}).get("I")
            if target is not None:
                extra += ["--target-lufs", str(target)]
    voice = KIT / ".work" / "_studio" / job.name / "assets" / "voice.wav"
    if voice.is_file():
        extra += ["--dialogue", str(voice)]
    return extra


def run_qa(mp4: Path, job: Path | None) -> str:
    out = (job / "out" / "qa") if job else mp4.with_suffix("").parent / f"{mp4.stem}_qa"
    cmd = [py(), str(ENGINE / "qa.py"), str(mp4), "--out", str(out), "--model", "small.en", *qa_extra_args(job)]
    if job and (job / "edl.json").is_file():
        cmd += ["--edl", str(job / "edl.json")]
    subprocess.call(cmd, env=env())
    try:
        return json.load(open(out / "qa.json")).get("verdict", "FAIL")
    except Exception:
        return "FAIL"


def cmd_qa(a) -> int:
    v = run_qa(Path(a.video).resolve(), resolve_job(a.job) if a.job else None)
    print(v)
    return 0 if v == "PASS" else 2


def resolve_job(name: str) -> Path:
    p = Path(name)
    job = p if p.is_dir() else WORK / name
    if not (job / "edl.json").exists():
        die(f"no job {name!r} (looked in {job}). Start one with: kit draft <clip>")
    return job.resolve()


# ---------------------------------------------------------------- styles
def list_styles() -> list[str]:
    names = {p.parent.name for p in list(STYLES.glob("*/style.json")) + list(USER_STYLES.glob("*/style.json"))}
    return sorted(n for n in names if not n.startswith("_"))


def parse_value(v: str):
    try:
        return json.loads(v)
    except json.JSONDecodeError:
        return v


def set_dotted(d: dict, key: str, value) -> None:
    parts = key.split(".")
    for k in parts[:-1]:
        d = d.setdefault(k, {})
    d[parts[-1]] = value


def validate_style(st: dict, style_dir: Path | None = None) -> list[str]:
    """Only what would break a video. Taste is his call."""
    bad = []
    def colour(k, v):
        if not re.fullmatch(r"#[0-9A-Fa-f]{6}", str(v)):
            bad.append(f"{k} must be a colour like #DC143C (got {v!r})")
    for k in ("color", "highlight_color", "stroke_color"):
        if k in st:
            colour(k, st[k])
    if isinstance(st.get("box"), dict) and "color" in st["box"]:
        colour("box.color", st["box"]["color"])
    def within(k, v, lo, hi, kind, why):
        try:
            ok = lo <= kind(v) <= hi
        except (TypeError, ValueError):
            ok = False
        if not ok:
            bad.append(f"{k} {why} (got {v!r})")
    within("font_size_frac", st.get("font_size_frac", 0.093), 0.01, 0.30, float, "must be 0.01-0.30 of the frame height")
    within("center_y_frac", st.get("center_y_frac", 0.64), 0.05, 0.95, float, "must keep captions on screen (0.05-0.95)")
    within("lines", st.get("lines", 1) or 1, 1, 4, int, "must be 1-4")
    within("max_words", st.get("max_words", 2), 1, 12, int, "must be 1-12")
    pu = st.get("punch") or {}
    if pu:
        within("punch.zoom_tight", pu.get("zoom_tight", 1.17), 1.0, 2.0, float, "must be 1.0-2.0")
    font = st.get("font_file", "Montserrat-ExtraBold.ttf")
    if not any((d / font).exists() for d in [KIT / "assets/fonts"] + ([style_dir / "fonts"] if style_dir else [])):
        bad.append(f"font_file {font} is not in assets/fonts/ or the style's fonts/ folder")
    tpl = st.get("caption_template")
    if tpl and not any((d / "templates" / tpl / "captions.js").exists() or (d / "templates" / tpl / "captions.css").exists()
                       for d in ([style_dir] if style_dir else [])) and not (GRAPHICS / tpl / "captions.js").exists():
        bad.append(f"caption_template {tpl}: no templates/{tpl}/captions.js (or .css) in the style folder, or graphics/{tpl}/")
    return bad


def snapshot(name: str) -> Path:
    """Copy the whole style folder (settings, STYLE.md, templates, fonts) into versions/<time>/."""
    src = own_style(name)
    stamp = dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    dst, n = src / "versions" / stamp, 1
    while dst.exists():   # two saves in the same second (a rejected change restores right away)
        n += 1; dst = src / "versions" / f"{stamp}-{n}"
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("versions", "out", "__pycache__"))
    return dst


def restore(name: str, version: str, keep_current: bool = True) -> None:
    """Put a saved version back. keep_current saves the state it replaces as a version too (so that can be undone);
    rolling back a failed save doesn't, so a rejected change never becomes something "undo" brings back."""
    if not (USER_STYLES / name / "versions" / version).is_dir():
        die(f"no version {version} of {name}. See: kit style versions {name}")
    base = own_style(name)
    src = base / "versions" / version
    if keep_current:
        snapshot(name)
    for item in base.iterdir():
        if item.name != "versions":
            shutil.rmtree(item) if item.is_dir() else item.unlink()
    for item in src.iterdir():
        (shutil.copytree if item.is_dir() else shutil.copy2)(item, base / item.name)


CHANGES = "## Changes Matthew asked for"


def log_change(name: str, text: str) -> None:
    """A dated line under "Changes Matthew asked for" in the style's STYLE.md (undo in a new chat reads the newest one)."""
    p = own_style(name) / "STYLE.md"
    s = p.read_text() if p.exists() else ""
    if CHANGES not in s:
        s = s.rstrip("\n") + f"\n\n{CHANGES}\n"
    p.write_text(s.rstrip("\n") + f"\n{dt.date.today()}: {text}\n")


def last_change(name: str) -> str:
    """The newest change still in effect (its dated line), skipping "undid ..." lines."""
    p = style_dir(name) / "STYLE.md"
    s = p.read_text().split(CHANGES, 1) if p.exists() else []
    lines = [x.strip() for x in (s[1].splitlines() if len(s) > 1 else []) if re.match(r"\d{4}-\d{2}-\d{2}: (?!undid )", x.strip())]
    return lines[-1] if lines else ""


def get_dotted(d: dict, key: str):
    for k in key.split("."):
        d = d.get(k) if isinstance(d, dict) else None
    return d


def style_test(name: str, clip: str | None = None) -> tuple[bool, str]:
    """A save only stands if the style renders: 3 s preview, plus a still."""
    st = json.load(open(style_dir(name) / "style.json"))
    bad = validate_style(st, style_dir(name))
    if bad:
        return False, "; ".join(bad)
    try:
        rc = style_preview(name, clip, quiet=True)
    except SystemExit as e:
        return False, f"preview failed ({e})"
    return (rc == 0), ("ok" if rc == 0 else "preview render failed")


def _notion_layout() -> dict:
    path = Path(os.environ.get("KIT_NOTION_LAYOUT", Path.home() / ".matthew-studio-kit" / "notion_layout.json"))
    if not path.is_file():
        die("layout config missing; configure the authorized Content hub first (docs/NOTION-MCP.md)")
    return json.load(open(path))


def cmd_style(a) -> int:
    if a.action == "push":
        if not a.name:
            die("kit style push <name>")
        import notion_index
        try:
            plan = notion_index.push_style(_notion_layout(), style_dir(a.name) / "style.json", title=a.name)
        except ValueError as exc:
            die(str(exc))
        print(json.dumps(plan, indent=2, ensure_ascii=False))
        print("planned only: nothing was written to Notion")
        return 0
    if a.action == "pull":
        if not a.name or not a.as_name:
            die("kit style pull <page.json> --as <style name>")
        import notion_index
        try:
            page = json.load(open(Path(a.name).expanduser()))
            result = notion_index.import_style(_notion_layout(), page, USER_STYLES / a.as_name)
        except (ValueError, json.JSONDecodeError, OSError) as exc:
            die(str(exc))
        print(f"style written locally: {result['path']}")
        return 0
    if a.action == "list":
        for n in list_styles():
            mine = " (saved by you)" if (USER_STYLES / n / "style.json").exists() else ""
            about = json.load(open(style_dir(n) / "style.json")).get("_about", "")
            print(f"{n}{mine}: {about[:120]}")
            continue
            print(f"{n}: {about[:120]}")
        return 0
    if a.action == "undo":
        return style_undo(a.name)
    if a.action == "sheet":
        return contact_sheet(a.name)
    if not a.name:
        die("name a style")
    if a.action == "import":
        return style_import(Path(a.name).expanduser())
    folder = style_dir(a.name)
    path = folder / "style.json"
    if a.action != "new" and not path.exists():
        die(f"style {a.name!r} not found. Styles: {', '.join(list_styles())}")
    if a.action == "show":
        print(path.read_text())
        guide = folder / "STYLE.md"
        if guide.exists():
            print("\n--- STYLE.md ---\n" + guide.read_text())
        extra = sorted(p.parent.name for p in (folder / "templates").glob("*/manifest.json"))
        if extra:
            print("templates in this style:", ", ".join(extra))
        return 0
    if a.action == "versions":
        for v in sorted(p.name for p in (folder / "versions").iterdir() if p.is_dir() and not p.name.startswith(".")) if (folder / "versions").exists() else []:
            print(v)
        return 0
    if a.action == "restore":
        if not a.pairs:
            die(f"say which version: kit style versions {a.name}")
        undone = last_change(a.name)
        restore(a.name, a.pairs[0])
        remember_style(a.name, "changed")
        log_change(a.name, f"undid \"{undone.split(': ', 1)[-1]}\" (back to version {a.pairs[0]})" if undone else f"went back to version {a.pairs[0]}")
        print(f"restored {a.name} to {a.pairs[0]} (the state before this restore is saved as a version too)"
              + (f"\nundid: {undone}" if undone else ""))
        return 0
    if a.action == "snapshot":
        remember_style(a.name, "changed")
        print(f"saved version: {snapshot(a.name).relative_to(KIT)}  (undo: kit style restore {a.name} <version>)")
        return 0
    if a.action == "test":
        ok, msg = style_test(a.name, a.clip)
        print(("OK " if ok else "FAILED ") + f"{a.name}: {msg}")
        return 0 if ok else 2
    if a.action == "preview":
        return style_preview(a.name, a.clip)
    if a.action == "new":
        base = a.base or "premium-motion"
        if path.exists():
            die(f"style {a.name!r} already exists")
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,30}", a.name):
            die("style names: lowercase letters, numbers, hyphens")
        if not (style_dir(base) / "style.json").exists():
            die(f"no style {base!r} to start from")
        folder = USER_STYLES / a.name; path = folder / "style.json"
        shutil.copytree(style_dir(base), folder, ignore=shutil.ignore_patterns("versions", "out", "__pycache__"))
        st = json.load(open(path)); st["_about"] = f"Made from {base} on {dt.date.today()}."
        json.dump(st, open(path, "w"), indent=2)
        print(f"new style {a.name} (copy of {base}) at {folder.relative_to(KIT)}")
        return 0
    if a.action == "set":
        target = a.as_name or a.name
        for pair in a.pairs:   # before anything is copied or saved
            if "=" not in pair:
                die(f"use key=value (got {pair!r})")
        if not a.pairs:
            die(f"nothing to set: kit style set {a.name} key=value ...")
        if a.as_name:
            if (style_dir(target) / "style.json").exists():
                die(f"style {target!r} already exists; pick another name")
            if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,30}", target):
                die("style names: lowercase letters, numbers, hyphens")
            shutil.copytree(folder, USER_STYLES / target, ignore=shutil.ignore_patterns("versions", "out", "__pycache__"))
            before = None
        else:
            fresh = not (USER_STYLES / target / "style.json").exists()   # first save over a built-in style copies it here
            before = snapshot(target)
        tpath = own_style(target) / "style.json"
        st = json.load(open(tpath))
        was = {}
        for pair in a.pairs:
            k, v = pair.split("=", 1)
            was[k.strip()] = get_dotted(st, k.strip())
            set_dotted(st, k.strip(), parse_value(v.strip()))
        if a.as_name:
            st["_about"] = f"Made from {a.name} on {dt.date.today()}. " + st.get("_about", "")
        json.dump(st, open(tpath, "w"), indent=2)
        try:
            ok, msg = style_test(target, a.clip)
        except Exception as e:   # whatever goes wrong, the style goes back to how it was
            ok, msg = False, f"{type(e).__name__}: {e}"
        if not ok:
            if before and not fresh:
                restore(target, before.name, keep_current=False)
                shutil.rmtree(before)   # identical to what's back in place; undo goes to the change before
            else:   # a new style, or the copy of a built-in one this save made: gone again, so updates still reach it
                shutil.rmtree(USER_STYLES / target)
            die(f"not saved, the style didn't render: {msg}. Nothing changed.")
        remember_style(target, "made" if a.as_name else "changed")
        what = ", ".join(f"{k} {was[k]!r} -> {get_dotted(st, k)!r}" for k in was)
        log_change(target, (f"made from {a.name}; " if a.as_name else "") + (what or "saved"))
        print(f"saved style {target}" + (f" (previous version: {before.name})" if before else "") + f"\nstill: {WORK / ('_preview-' + target) / 'out' / ('preview-' + target + '.jpg')}"
              + f"\nwatch it: kit style preview {target}")
        return 0
    die(f"unknown style action {a.action}")


LAST_STYLE = KIT / ".cache" / "last-style.json"


def remember_style(name: str, how: str) -> None:
    """The style he changed last, so "undo that" in a new chat knows which one."""
    LAST_STYLE.parent.mkdir(parents=True, exist_ok=True)
    LAST_STYLE.write_text(json.dumps({"style": name, "how": how, "at": dt.datetime.now().isoformat(timespec="seconds")}))


def style_undo(name: str | None) -> int:
    """Undo the newest saved change: put the newest version back and use it up, so a second undo goes one further back."""
    last = {}
    try:
        last = json.loads(LAST_STYLE.read_text())
    except (OSError, ValueError):
        pass
    name = name or last.get("style") or "premium-motion"
    vdir = USER_STYLES / name / "versions"
    vs = sorted(p for p in vdir.iterdir() if p.is_dir() and not p.name.startswith(".")) if vdir.is_dir() else []
    if not vs:
        if last.get("style") == name and last.get("how") == "made":
            print(f"{name} is a new style with no changes since it was made; nothing to undo inside it. "
                  f"His other styles are untouched. (To remove {name}, ask him first.)")
        else:
            print(f"nothing to undo in {name}: no saved changes")
        return 0
    v = vs[-1]
    undone = last_change(name)
    restore(name, v.name, keep_current=False)
    stash = vdir / ".undone" / dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    stash.parent.mkdir(exist_ok=True)
    shutil.move(str(v), str(stash))   # out of the undo list; kept in case he wants it back
    bad = validate_style(json.load(open(USER_STYLES / name / "style.json")), USER_STYLES / name)
    log_change(name, f"undid \"{undone.split(': ', 1)[-1]}\"" if undone else f"undid the change saved {v.name}")
    remember_style(name, "changed")
    print(f"undid in {name}: {undone.split(': ', 1)[-1] if undone else 'the last saved change'} (back to version {v.name})"
          + (f"\nPROBLEM: {'; '.join(bad)}" if bad else ""))
    return 0


def contact_sheet(video: str | None) -> int:
    """One picture of a reference reel: 2 frames a second, 8 across, to read its captions, zooms and graphics from."""
    if not video:
        die("which video? kit style sheet <reel.mp4>")
    src = Path(video).expanduser().resolve()
    if not src.is_file():
        die(f"video not found: {src}")
    out = WORK / "_refs" / f"{re.sub(r'[^A-Za-z0-9_-]+', '-', src.stem)[:40]}_sheet.jpg"
    out.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vf", "fps=2,scale=270:-1,tile=8x4", "-frames:v", "1", str(out)],
                       env=env(), capture_output=True, text=True)
    if r.returncode or not out.exists():
        die(f"couldn't read that video: {r.stderr.strip()[-300:]}")
    print(f"sheet: {out}")
    return 0


def style_import(old: Path) -> int:
    """His saved styles from the old Matthew Edit Kit (its my-styles/), settings, STYLE.md, fonts and versions. Remotion
    templates (index.tsx) can't come along; they're listed so they can be rebuilt as library blocks."""
    src = old / "my-styles"
    if not src.is_dir():
        print(f"nothing to import: {old} has no saved styles (my-styles/)")
        return 0
    for d in sorted(p for p in src.iterdir() if (p / "style.json").exists()):
        dst = USER_STYLES / d.name
        if dst.exists():
            print(f"skip {d.name}: already here")
            continue
        shutil.copytree(d, dst, ignore=shutil.ignore_patterns("out", "__pycache__", "*.tsx"))
        tsx = sorted(str(p.relative_to(d)) for p in d.rglob("*.tsx"))
        st = json.load(open(dst / "style.json"))
        if st.get("caption_template") and (GRAPHICS / st["caption_template"] / "captions.js").exists():
            tsx = [t for t in tsx if f"templates/{st['caption_template']}/" not in t]   # this kit ships that design
            shutil.rmtree(dst / "templates" / st["caption_template"], ignore_errors=True)
        else:
            st.pop("caption_template", None)
        json.dump(st, open(dst / "style.json", "w"), indent=2)
        bad = validate_style(st, dst)
        print(f"imported {d.name}" + (f" (left behind, rebuild as blocks: {', '.join(tsx)})" if tsx else "") + (f" PROBLEM: {'; '.join(bad)}" if bad else ""))
    return 0


def style_preview(name: str, clip: str | None, quiet: bool = False) -> int:
    """A 3 s full-size render of the style on a clip (the last edited clip if none is given), plus one still."""
    if clip:
        src = Path(clip).expanduser().resolve()
    else:
        jobs = [p for p in sorted(WORK.glob("*/edl.json"), key=lambda p: p.stat().st_mtime, reverse=True)
                if (p.parent / json.load(open(p))["source"]).exists()]   # a clip on an ejected card can't be previewed
        if not jobs:
            die("no clip to preview on yet: give one with --clip")
        e = json.load(open(jobs[0]))
        src = (jobs[0].parent / e["source"]).resolve()
    wp = words_path(src)
    if not wp.exists() and run_core(["transcribe", str(src)]) != 0:
        die("transcription failed")
    words = load_words(wp)
    job = WORK / f"_preview-{name}"
    (job / "inputs").mkdir(parents=True, exist_ok=True)
    link = job / "inputs" / src.name
    if link.is_symlink() or link.exists():
        link.unlink()
    link.symlink_to(src)
    shutil.copy2(wp, job / "inputs" / "words.json")
    cuts = draft_cuts(words)
    acc, keep = 0.0, []
    for c in cuts:
        if acc >= 3.0:
            break
        take = min(c["out"] - c["in"], 3.0 - acc)
        keep.append({"in": c["in"], "out": round(c["in"] + take, 3)})
        acc += take
    st = json.load(open(style_dir(name) / "style.json"))
    wide = st.get("shape") == "16:9"
    edl = {"name": f"preview-{name}", "style_name": name, "source": f"inputs/{src.name}", "words": "inputs/words.json",
           "cuts": keep, "keywords": draft_keywords(words),
           "output": {"w": 1920, "h": 1080, "fps": 30} if wide else {"w": 1080, "h": 1920, "fps": 30}}
    json.dump(edl, open(job / "edl.json", "w"), indent=2)
    hfr = hfm()
    proj, _ = hfr.build(job / "edl.json", force=True)
    code, log = hfr.check(proj)
    if code:
        die(f"the style doesn't draw cleanly:\n{log[-1500:]}")
    if "note, caption colour" in log:
        print(log)
    shots = hfr.snapshot(proj, [1.5])
    (job / "out").mkdir(exist_ok=True)
    still = job / "out" / f"preview-{name}.jpg"
    if shots:
        subprocess.call(["ffmpeg", "-v", "error", "-y", "-i", shots[0], str(still)], env=env())
    if not shots or not still.exists():
        die("the style preview didn't produce a frame")
    if not quiet:
        url, _ = hfr.preview(proj, 3199)
        print(f"preview: {url}\nstill: {still}")
    return 0


# ---------------------------------------------------------------- graphics, library blocks, his library
def sample_job(tag: str, clip: str | None, seconds: float = 3.0, extra: dict | None = None) -> Path:
    """A few seconds of a real clip (the last edited one unless --clip) as a job, to try a style or a graphic on."""
    if clip:
        src = Path(clip).expanduser().resolve()
    else:
        jobs = [p for p in sorted(WORK.glob("*/edl.json"), key=lambda p: p.stat().st_mtime, reverse=True) if not p.parent.name.startswith("_")
                and (p.parent / json.load(open(p))["source"]).exists()]
        if not jobs:
            die("no clip to try it on yet: draft a clip first, or give one with --clip")
        src = (jobs[0].parent / json.load(open(jobs[0]))["source"]).resolve()
    wp = words_path(src)
    if not wp.exists() and run_core(["transcribe", str(src)]) != 0:
        die("transcription failed")
    words = load_words(wp)
    job = WORK / f"_{tag}"
    shutil.rmtree(job, ignore_errors=True)
    (job / "inputs").mkdir(parents=True)
    (job / "inputs" / src.name).symlink_to(src)
    shutil.copy2(wp, job / "inputs" / "words.json")
    acc, keep = 0.0, []
    for c in draft_cuts(words):
        if acc >= seconds:
            break
        take = min(c["out"] - c["in"], seconds - acc)
        keep.append({"in": c["in"], "out": round(c["in"] + take, 3)}); acc += take
    edl = {"name": tag, "style_name": "premium-motion", "source": f"inputs/{src.name}", "words": "inputs/words.json", "cuts": keep,
           "keywords": draft_keywords(words), "output": {"w": 1080, "h": 1920, "fps": 30}, "overlays": [], "blocks": []}
    edl.update(extra or {})
    json.dump(edl, open(job / "edl.json", "w"), indent=2)
    return job


def try_job(job: Path, at: list[float]) -> Path:
    """Build, check and photograph a job (no render). Returns the still."""
    hfr = hfm()
    proj, _ = hfr.build(job / "edl.json", force=True)
    code, log = hfr.check(proj)
    if code:
        die(f"it doesn't draw cleanly:\n{log[-1500:]}")
    shots = hfr.snapshot(proj, at)
    if not shots:
        die("no frame came out")
    still = job / f"{job.name.lstrip('_')}.jpg"
    if len(shots) > 1:
        args = sum((["-i", x] for x in shots), [])
        subprocess.call(["ffmpeg", "-v", "error", "-y", *args, "-filter_complex", f"hstack={len(shots)},scale=-2:960", str(still)], env=env())
    else:
        subprocess.call(["ffmpeg", "-v", "error", "-y", "-i", shots[0], str(still)], env=env())
    if not still.exists():
        die(f"the frames came out but couldn't be put together ({len(shots)} shots)")
    return still


def cmd_graphics(a) -> int:
    if a.action == "list":
        for p in sorted(GRAPHICS.glob("*/manifest.json")):
            m = json.load(open(p))
            print(f"{p.parent.name}: {m.get('description', '')}  plan: {m.get('plan', '')}")
        print("More: about 200 HyperFrames library blocks (kit blocks search <words>).")
        return 0
    if not a.name:
        die("name a graphic, e.g. kit graphics test picture")
    mp = GRAPHICS / a.name / "manifest.json"
    if not mp.exists():
        die(f"no graphic {a.name!r}: kit graphics list")
    m = json.load(open(mp))
    extra = json.loads(json.dumps(m.get("test", {})).replace("$KIT", str(KIT)))
    still = try_job(sample_job(f"graphics-{a.name}", a.clip, 3.0, extra), m.get("test_at", [0.9, 1.8]))
    print(f"OK {a.name}: still {still}")
    return 0


def cmd_blocks(a) -> int:
    hfr = hfm()
    if a.action == "search":
        r = subprocess.run(hfr.hf() + ["catalog", *a.words, "--type", "block", "--json"], capture_output=True, text=True, env=hfr.env(), timeout=300)
        try:
            res = json.loads(r.stdout).get("results", [])
        except json.JSONDecodeError:
            die(f"search failed: {(r.stdout + r.stderr)[-400:]}")
        for it in res:
            print(f"{it['name']}: {it.get('title', '')}. {it.get('description', '')[:160]}  [{', '.join(it.get('tags', [])[:4])}]")
        if not res:
            print("nothing matched; try other words")
        return 0
    if not a.words:
        die("name a block, e.g. kit blocks test ai-chat-reveal")
    name = a.words[0]
    extra = {"blocks": [{"name": name, "at": 0.3, "dur": 3.5}], "style_name": a.style or "premium-motion"}
    still = try_job(sample_job(f"block-{name}", a.clip, 4.0, extra), [1.0, 2.0, 3.2])
    print(f"OK {name}: still {still}\nplace it with the plan's \"blocks\" (skills/graphics)")
    return 0


def cmd_capcut(a) -> int:
    """Send the finished (rendered) edit to CapCut as a project he can open and change."""
    import capcut_export
    job = resolve_job(a.job)
    try:
        folder = capcut_export.export_job(job, KIT)
    except ValueError as exc:
        die(str(exc))
    print(f"CapCut project: {folder.name}")
    print("Open CapCut (quit and reopen it if it was already open): it's in the Projects list. "
          "The whole finished edit is one clip, captions and b-roll included, ready to trim or add to.")
    return 0


def cmd_library(a) -> int:
    sys.path.insert(0, str(ENGINE))
    import library
    if a.action in {"setup", "detect", "plan", "index", "attach", "find", "override", "workflow", "sort", "upload"}:
        import notion_index
        try:
            if a.action == "upload":
                return notion_index.upload_cli(a)
            return notion_index.run(a)
        except (ValueError, json.JSONDecodeError) as exc:
            die(str(exc))
    if a.action == "list":
        return library.list_items(" ".join(a.args), a.type)
    if a.action == "add":
        if not a.args or not a.type or not a.name:
            die("kit library add <file> --type broll|picture|sfx --name <name> [--tags a,b]")
        return library.add(Path(a.args[0]).expanduser(), a.type, a.name, a.tags or "")
    if a.action == "connect":
        if not a.args:
            die("kit library connect is disabled. See docs/NOTION-MCP.md.")
        return library.connect(a.args[0])
    if a.action == "sync":
        return library.sync()
    die(f"unknown library action {a.action}")


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "support":
        import support
        return support.main(sys.argv[2:])  # no renderer import or automatic dependency update
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("doctor"); sp.add_parser("version")
    t = sp.add_parser("transcribe"); t.add_argument("clip")
    d = sp.add_parser("draft"); d.add_argument("clip"); d.add_argument("--style"); d.add_argument("--name"); d.add_argument("--long", action="store_true")
    d.add_argument("--replace", action="store_true")
    r = sp.add_parser("render"); r.add_argument("job")
    pv = sp.add_parser("preview"); pv.add_argument("jobs", nargs="*"); pv.add_argument("--port", type=int, default=3101)
    pv.add_argument("--rebuild", action="store_true"); pv.add_argument("--open", action="store_true"); pv.add_argument("--stop", action="store_true")
    q = sp.add_parser("qa"); q.add_argument("video"); q.add_argument("--job")
    cc = sp.add_parser("capcut"); cc.add_argument("job")
    s = sp.add_parser("style"); s.add_argument("action", choices=["list", "show", "new", "set", "snapshot", "test", "versions", "restore", "undo", "preview", "import", "sheet", "push", "pull"])
    s.add_argument("name", nargs="?"); s.add_argument("pairs", nargs="*"); s.add_argument("--as", dest="as_name"); s.add_argument("--clip")
    s.add_argument("--from", dest="base")
    g = sp.add_parser("graphics"); g.add_argument("action", choices=["list", "test"]); g.add_argument("name", nargs="?"); g.add_argument("--clip")
    b = sp.add_parser("blocks"); b.add_argument("action", choices=["search", "test"]); b.add_argument("words", nargs="*"); b.add_argument("--clip"); b.add_argument("--style")
    lb = sp.add_parser("library")
    lb.add_argument("action", choices=["list", "add", "sync", "connect", "setup", "detect", "plan", "index", "attach", "find", "override", "workflow", "sort", "upload"])
    lb.add_argument("args", nargs="*")
    lb.add_argument("--type", choices=["broll", "picture", "sfx"]); lb.add_argument("--name"); lb.add_argument("--tags")
    lb.add_argument("--role"); lb.add_argument("--origin", choices=["ai", "stock", "own", "unknown"])
    lb.add_argument("--workspace-id", dest="workspace_id"); lb.add_argument("--hub-id", dest="hub_id")
    lb.add_argument("--input"); lb.add_argument("--layout"); lb.add_argument("--index"); lb.add_argument("--kind")
    lb.add_argument("--aspect", choices=["vertical", "horizontal", "square"]); lb.add_argument("--limit", type=int, default=10)
    lb.add_argument("--frames-dir"); lb.add_argument("--qa-report"); lb.add_argument("--requested-status")
    lb.add_argument("--phrase"); lb.add_argument("--page-id")
    lb.add_argument("--batch", type=int, default=10)
    lb.add_argument("--force", action="store_true"); lb.add_argument("--ignore-body", action="store_true")
    lb.add_argument("--human-posted", action="store_true"); lb.add_argument("--simulated", action="store_true")
    sp.add_parser("update"); sp.add_parser("prepare")
    u = sp.add_parser("deps"); u.add_argument("action", choices=["status", "check", "rollback"])
    rp = sp.add_parser("report"); rp.add_argument("--note", default=""); rp.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    os.environ["PATH"] = env()["PATH"]   # Homebrew's ffmpeg-full is keg-only: every module and helper must find it
    if a.cmd == "report":
        return report.send(a.note, kit_version(), hfm().hf_version(), dry=a.dry_run)
    if a.cmd not in ("version", "deps", "update", "prepare"):
        busy = KIT / ".cache" / "deps" / "busy" / str(os.getpid())   # a library switch waits while a command is running
        busy.parent.mkdir(parents=True, exist_ok=True); busy.touch()
        atexit.register(lambda: busy.unlink(missing_ok=True))
        if a.cmd in ("draft", "doctor"):   # a tested update switches in only at the start of a new edit, never mid-fix
            deps.apply()
        deps.auto()
    return {"version": cmd_version, "doctor": cmd_doctor, "update": cmd_update, "prepare": cmd_prepare, "deps": cmd_deps, "transcribe": cmd_transcribe, "draft": cmd_draft, "render": cmd_render, "preview": cmd_preview, "qa": cmd_qa,
            "style": cmd_style, "graphics": cmd_graphics, "blocks": cmd_blocks, "library": cmd_library, "capcut": cmd_capcut}[a.cmd](a)


def logged_main() -> int:
    """main(), with each command's outcome added to the log that kit report sends."""
    import time
    import traceback
    t0, argv = time.time(), sys.argv[1:]
    cmd = argv[0] if argv else ""
    if cmd in ("support", "report", "version", "-h", "--help", ""):
        return main()
    def log(code, error=""):
        report.log_event(cmd, argv[1:], code, time.time() - t0, error)
        try:
            import support
            support.kit_event(argv, code, time.time() - t0)
        except Exception:
            pass  # diagnostics must preserve the actual command's result
    try:
        code = main()
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
        if code and not LAST_ERROR and not isinstance(e.code, int):
            log(code, str(e.code))
        else:
            log(code, LAST_ERROR if code else "")
        raise
    except BaseException:
        log(1, traceback.format_exc())
        raise
    log(code or 0, LAST_ERROR if code else "")
    return code


if __name__ == "__main__":
    sys.exit(logged_main())
