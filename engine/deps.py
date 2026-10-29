#!/usr/bin/env python3
"""Keep the outside libraries current on their own: HyperFrames (the renderer) and the Python packages.

  deps.py check [--now]     look for newer versions, test each on this Mac, stage the ones that pass
  deps.py apply             switch to a staged, tested update (bin/kit does this itself at the start of a new edit)
  deps.py status            what's installed, what's staged, the last check
  deps.py rollback          go back to the versions before the last update
  deps.py floor             make sure nothing is older than the kit's tested versions (kit update runs this)

How an update happens, with no one asking:
1. Once a day, any bin/kit command starts `deps.py check` in the background.
2. It asks npm and PyPI for the newest versions inside the same release line (HyperFrames 0.8.x, faster-whisper 1.x ...).
   A new line can change how the library works, so those come with a kit update.
3. A newer version is set up next to the current one (.cache/deps/next/ for Python; npx keeps HyperFrames versions apart).
4. The test: a short generated clip (Mac voice + test picture) goes through transcribe, render and QA with the current
   libraries and with the new ones. The new ones pass only if they hear the same words, draw the same frames, play the same
   audio and get the same QA verdict.
5. A pass is switched in at the start of the next edit (instant). A fail is logged and that exact version is skipped.
   The previous versions stay in .cache/deps/prev/ for `kit deps rollback`.
The tracked engine/hyperframes.json and requirements.txt are the floor: the versions the kit was tested with. They're
never edited here, so `git pull` stays clean. The HyperFrames version in use is .cache/deps/hyperframes.json.
"""
import argparse, difflib, fcntl, json, os, re, shutil, subprocess, sys, tempfile, time

ENGINE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(ENGINE)
VENV = os.path.join(KIT, ".venv")
D = os.path.join(KIT, ".cache", "deps")
NEXT, PREV = os.path.join(D, "next"), os.path.join(D, "prev")
STATE, LOG = os.path.join(D, "state.json"), os.path.join(D, "log.txt")
EVERY_S = 20 * 3600
HF_FLOOR = os.path.join(ENGINE, "hyperframes.json")
HF_LIVE = os.path.join(D, "hyperframes.json")
SAY = "Okay, so this is a quick test of the edit kit. [[slnc 700]] I post on YouTube and Instagram every single day."


def log(msg):
    os.makedirs(D, exist_ok=True)
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    with open(LOG, "a") as f: f.write(line + "\n")


def load_state():
    try: return json.load(open(STATE))
    except Exception: return {}


def save_state(s):
    os.makedirs(D, exist_ok=True)
    json.dump(s, open(STATE + ".tmp", "w"), indent=2); os.replace(STATE + ".tmp", STATE)


def vkey(v):
    return tuple(int(x) for x in re.findall(r"\d+", v.split("+")[0])[:4])


def major(v):
    return vkey(v)[0] if vkey(v) else 0


def env(**extra):
    e = dict(os.environ)
    for prefix in ("/opt/homebrew/opt/ffmpeg-full/bin", "/usr/local/opt/ffmpeg-full/bin", "/opt/homebrew/bin", "/usr/local/bin"):
        if os.path.isdir(prefix): e["PATH"] = e.get("PATH", "") + os.pathsep + prefix
    for prefix in ("/opt/homebrew/opt/ffmpeg-full/bin", "/usr/local/opt/ffmpeg-full/bin"):
        if os.path.exists(os.path.join(prefix, "ffmpeg")): e["PATH"] = prefix + os.pathsep + e["PATH"]; break
    e["KIT_NO_AUTO_UPDATE"] = "1"
    try:   # the same sandbox-safe home HyperFrames gets everywhere else (render_hf.env)
        sys.path.insert(0, ENGINE); import render_hf
        h = render_hf.env()
        for k in ("HOME", "HYPERFRAMES_BROWSER_PATH", "HYPERFRAMES_SKIP_SKILLS"):
            if k in h: e[k] = h[k]
    except Exception:
        pass
    e.update(extra)
    return e


def run(cmd, cwd=None, timeout=1800, **extra):
    r = subprocess.run(cmd, cwd=cwd, env=env(**extra), capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=timeout)
    if r.returncode: raise RuntimeError(f"{' '.join(map(str, cmd[:4]))} failed: {(r.stderr or r.stdout)[-600:]}")
    return r.stdout


def npm():
    node = shutil.which("node", path=env()["PATH"])
    for c in ([os.path.join(os.path.dirname(node), "npm")] if node else []) + [shutil.which("npm", path=env()["PATH"])]:
        if c and os.path.exists(c): return c
    raise RuntimeError("npm not found (brew install node)")


# ---------------------------------------------------------------- what's installed, what's newer
def hf_floor():
    return json.load(open(HF_FLOOR))["version"]


def hf_installed():
    try: return json.load(open(HF_LIVE))["version"]
    except Exception: return hf_floor()


def line(v):
    """Release line: 0.8.x for a 0.x version (each 0.minor can break), else the major."""
    k = vkey(v)
    return f"{k[0]}.{k[1]}" if k and k[0] == 0 else str(k[0] if k else 0)


def hf_newest():
    vs = json.loads(run([npm(), "view", f"hyperframes@~{line(hf_installed())}.0", "version", "--json"], timeout=120) or "null")
    vs = [vs] if isinstance(vs, str) else (vs or [])
    vs = [v for v in vs if "-" not in v]   # no betas
    return max(vs, key=vkey) if vs else hf_installed()


def hf_ready(v):
    """Fetch that version (npx caches it next to the others) and its Chrome. Raises if it can't run."""
    run(["npx", "--yes", f"hyperframes@{v}", "--version"], timeout=600, HYPERFRAMES_SKIP_SKILLS="1")
    run(["npx", "--yes", f"hyperframes@{v}", "browser", "ensure"], timeout=900, HYPERFRAMES_SKIP_SKILLS="1")


def requirements():
    """requirements.txt lines as (name, pinned version, marker)."""
    out = []
    for line in open(os.path.join(KIT, "requirements.txt")):
        line = line.split("#")[0].strip()
        m = re.match(r"([A-Za-z0-9_.\-]+)==([^;\s]+)\s*(;.*)?$", line)
        if m: out.append((m.group(1), m.group(2), m.group(3) or ""))
    return out


def py_spec(path):
    """Same packages, any newer version inside the pinned major."""
    with open(path, "w") as f:
        for name, v, marker in requirements():
            f.write(f"{name}>={v},<{major(v) + 1}{marker}\n")


def py_installed(python):
    out = run([python, "-m", "pip", "list", "--format", "json", "--disable-pip-version-check"], timeout=120)
    return {p["name"].lower(): p["version"] for p in json.loads(out)}


def py_newer():
    """What pip would upgrade (all packages, including the ones ours depend on), without installing anything."""
    spec = os.path.join(D, "py-spec.txt"); py_spec(spec)
    rep = os.path.join(D, "py-report.json")
    run([os.path.join(VENV, "bin", "python"), "-m", "pip", "install", "--dry-run", "--upgrade", "--upgrade-strategy", "eager",
         "--disable-pip-version-check", "-q", "--report", rep, "-r", spec], timeout=600)
    have = py_installed(os.path.join(VENV, "bin", "python"))
    new = {}
    for it in json.load(open(rep)).get("install", []):
        n, v = it["metadata"]["name"].lower(), it["metadata"]["version"]
        if have.get(n) != v: new[n] = v
    return new


# ---------------------------------------------------------------- the test
def fixture():
    """A short clip made on this Mac: the Mac's voice saying a line with a pause (so there's a cut) and both logo
    words (so a template is drawn), over a moving test picture."""
    fx = os.path.join(D, "fixture"); clip = os.path.join(fx, "clip.mp4")
    if os.path.exists(clip): return clip
    os.makedirs(fx, exist_ok=True)
    aiff = os.path.join(fx, "say.aiff")
    run(["say", "-o", aiff, SAY], timeout=120)
    run(["ffmpeg", "-y", "-v", "error", "-nostdin", "-f", "lavfi", "-i", "testsrc2=s=1080x1920:r=30", "-i", aiff, "-shortest",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "48000", "-ac", "2", clip + ".tmp.mp4"])
    os.replace(clip + ".tmp.mp4", clip)
    return clip


def make_edl(words_json, clip, out_dir):
    """The fixture's edit plan, made the way kit draft makes one (cuts, keywords, logo pops)."""
    sys.path.insert(0, ENGINE)
    import kit
    words = kit.load_words(words_json)
    inputs = os.path.join(out_dir, "inputs"); os.makedirs(inputs, exist_ok=True)
    shutil.copy2(words_json, os.path.join(inputs, "words.json"))
    edl = {"name": "deps-test", "style_name": "matthew", "source": clip, "words": "inputs/words.json",
           "cuts": kit.draft_cuts(words), "keywords": kit.draft_keywords(words), "caption_breaks": [], "overlays": [],
           "caption_hide": [], "broll": [], "sfx": [], "output": {"w": 1080, "h": 1920, "fps": 30}}
    st = json.load(open(kit.style_dir("matthew") / "style.json"))
    if (st.get("logos") or {}).get("enabled"): kit.add_logo_overlays(edl, words, st, None)
    kit.place_logos(edl)
    p = os.path.join(out_dir, "edl.json"); json.dump(edl, open(p, "w"), indent=2)
    return p


def side(name, python, hf_version, clip, edl=None):
    """One pass of the fixture through transcribe, render and QA with the given Python and HyperFrames."""
    out = os.path.join(D, "test", f"_deps-{name}")
    shutil.rmtree(out, ignore_errors=True); os.makedirs(out)
    words_dir = os.path.join(out, "words")
    run([python, os.path.join(ENGINE, "quick_edit.py"), "transcribe", clip], KIT_WORDS_CACHE=words_dir)
    words_json = os.path.join(words_dir, os.listdir(words_dir)[0])
    edl_p = make_edl(words_json, clip, out)
    if edl:   # render the reference's plan, so a changed word timing can't hide (or fake) a drawing difference
        shutil.copy2(edl, edl_p); shutil.copy2(os.path.join(os.path.dirname(edl), "inputs", "words.json"), os.path.join(out, "inputs", "words.json"))
    mp4 = os.path.join(out, "out", "deps-test.mp4")
    run([python, os.path.join(ENGINE, "render_hf.py"), "render", edl_p, "--out", mp4], KIT_HF_VERSION=hf_version, timeout=1200)
    run([python, os.path.join(ENGINE, "qa.py"), mp4, "--out", os.path.join(out, "qa"), "--model", "small.en"], timeout=900)
    verdict = json.load(open(os.path.join(out, "qa", "qa.json"))).get("verdict")
    return {"words": [w["w"] for w in json.load(open(words_json))["words"]], "edl": edl_p, "mp4": mp4, "qa": verdict}


def frames(mp4):
    return int(run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets", "-show_entries", "stream=nb_read_packets",
                    "-of", "csv=p=0", mp4]).strip())


def min_psnr(a, b):
    stats = os.path.join(D, "test", "psnr.txt")
    os.makedirs(os.path.dirname(stats), exist_ok=True)
    # frame N against frame N: renderers stamp frame times a hair differently, and pairing by time would compare a frame
    # with its neighbour (about 16 dB at every cut)
    run(["ffmpeg", "-v", "error", "-nostdin", "-i", a, "-i", b, "-lavfi", f"[0:v]setpts=N[x];[1:v]setpts=N[y];[x][y]psnr=stats_file={stats}",
         "-f", "null", "-"])
    vals = [float(m) if m != "inf" else 99.0 for m in re.findall(r"psnr_avg:(\S+)", open(stats).read())]
    return min(vals) if vals else 0.0


def audio_corr(a, b):
    import numpy as np
    pcm = lambda f: np.frombuffer(subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-i", f, "-ac", "1", "-ar", "16000", "-f", "f32le", "-"],
                                                 capture_output=True, env=env()).stdout, np.float32)
    x, y = pcm(a), pcm(b); n = min(len(x), len(y))
    if n == 0: return 0.0
    x, y = x[:n] - x[:n].mean(), y[:n] - y[:n].mean()
    d = float(np.sqrt((x * x).sum() * (y * y).sum()))
    return float((x * y).sum() / d) if d else 0.0


def compare(ref, new):
    """Every reason the new libraries don't behave like the current ones (empty = pass)."""
    bad = []
    if ref is None:   # the current install doesn't work: judge the candidate on its own
        return [] if new["qa"] in ("PASS", "WARN") or frames(new["mp4"]) > 0 else [f"QA {new['qa']}"]
    sim = difflib.SequenceMatcher(None, [w.lower() for w in ref["words"]], [w.lower() for w in new["words"]]).ratio()
    if sim < 0.9: bad.append(f"heard different words ({sim:.2f} alike)")
    fa, fb = frames(ref["mp4"]), frames(new["mp4"])
    if fa != fb: bad.append(f"{fb} frames, current makes {fa}")
    else:
        p = min_psnr(ref["mp4"], new["mp4"])
        if p < 30: bad.append(f"frames look different (worst frame {p:.1f} dB, needs 30)")
    c = audio_corr(ref["mp4"], new["mp4"])
    if c < 0.99: bad.append(f"audio differs (correlation {c:.3f}, needs 0.99)")
    if new["qa"] != ref["qa"] and new["qa"] != "PASS": bad.append(f"QA {new['qa']}, current gets {ref['qa']}")
    return bad


# ---------------------------------------------------------------- staging
def stage_python():
    nv = os.path.join(NEXT, "venv")
    shutil.rmtree(nv, ignore_errors=True)
    base = run([os.path.join(VENV, "bin", "python"), "-c", "import sys; print(sys._base_executable)"]).strip()
    run([base, "-m", "venv", nv])
    spec = os.path.join(D, "py-spec.txt"); py_spec(spec)
    run([os.path.join(nv, "bin", "python"), "-m", "pip", "install", "-q", "--disable-pip-version-check", "-r", spec])
    return os.path.join(nv, "bin", "python")


def sig(d):
    return ",".join(f"{k}=={v}" for k, v in sorted(d.items()))


def check(now=False):
    os.makedirs(D, exist_ok=True)
    lock = open(os.path.join(D, "check.lock"), "w")
    try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError: print("a check is already running"); return 0
    st = load_state()
    if not now and time.time() - st.get("last_check", 0) < EVERY_S: return 0
    ready = json.load(open(os.path.join(NEXT, "READY.json"))) if os.path.exists(os.path.join(NEXT, "READY.json")) else {}
    cands = {}
    try:
        want = {"hyperframes": hf_newest()}; have = hf_installed()
        if vkey(want["hyperframes"]) > vkey(have):
            if sig(want) in st.get("bad", []): log(f"hyperframes: {sig(want)} failed its test before, skipping")
            elif ready.get("hyperframes", {}).get("versions") == want: log("hyperframes: already tested and staged")
            else: cands["hyperframes"] = want
        newer = py_newer()
        if newer:
            if sig(newer) in st.get("bad", []): log(f"python: {sig(newer)} failed its test before, skipping")
            elif ready.get("python", {}).get("versions") == newer: log("python: already tested and staged")
            else: cands["python"] = newer
    except Exception as e:
        log(f"couldn't look for updates (offline?): {e}"); return 0
    if not cands:
        st["last_check"] = time.time(); save_state(st); log("everything is current"); return 0
    log("new versions: " + "; ".join(f"{k}: {sig(v)}" for k, v in cands.items()))
    cur_py = os.path.join(VENV, "bin", "python")
    try:
        clip = fixture()
        ref = side("current", cur_py, hf_installed(), clip)
    except Exception as e:
        log(f"the current install failed the test clip, judging the update on its own: {e}"); ref = None
    for comp, versions in cands.items():
        try:
            if comp == "hyperframes":
                hf_ready(versions["hyperframes"])
                new = side(comp, cur_py, versions["hyperframes"], fixture(), ref and ref["edl"])
            else: new = side(comp, stage_python(), hf_installed(), fixture(), ref and ref["edl"])
            bad = compare(ref, new)
        except Exception as e:
            bad = [str(e)]
        if bad:
            log(f"{comp}: update FAILED its test, staying on the current version: {'; '.join(bad)}")
            st.setdefault("bad", []).append(sig(versions))
            if comp == "python": shutil.rmtree(os.path.join(NEXT, "venv"), ignore_errors=True)
        else:
            log(f"{comp}: update passed its test ({sig(versions)}); it switches in at the next edit")
            ready[comp] = {"versions": versions, "tested": time.strftime("%Y-%m-%d %H:%M")}
    os.makedirs(NEXT, exist_ok=True)
    json.dump(ready, open(os.path.join(NEXT, "READY.json"), "w"), indent=2)
    st["last_check"] = time.time(); save_state(st)
    return 0


# ---------------------------------------------------------------- switching
def others_busy():
    busy = os.path.join(D, "busy")
    for f in os.listdir(busy) if os.path.isdir(busy) else []:
        pid = int(f) if f.isdigit() else 0
        if pid == os.getpid() or pid == os.getppid(): continue
        try: os.kill(pid, 0); return True
        except OSError: os.remove(os.path.join(busy, f))
    return False


def apply(quiet=False):
    rp = os.path.join(NEXT, "READY.json")
    if not os.path.exists(rp): return 0
    ready = json.load(open(rp))
    if not ready: return 0
    lock = open(os.path.join(D, "check.lock"), "w")
    try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError: return 0   # a check is running: switch next time
    if others_busy(): return 0   # another kit command is using the libraries right now
    os.makedirs(PREV, exist_ok=True)
    st = load_state()
    for comp, info in list(ready.items()):
        if comp == "hyperframes":
            before, after = hf_installed(), info["versions"]["hyperframes"]
            st["hf_prev"] = before
            json.dump({"version": after}, open(HF_LIVE + ".tmp", "w")); os.replace(HF_LIVE + ".tmp", HF_LIVE)
            ready.pop(comp)
            st.setdefault("history", []).append({"when": time.strftime("%Y-%m-%d %H:%M"), comp: info["versions"]})
            log(f"kit: updated HyperFrames {before} -> {after} (tested on this Mac first)")
            continue
        else:
            src, live, old = os.path.join(NEXT, "venv"), VENV, os.path.join(PREV, "venv")
            before = "previous packages"
        if not os.path.isdir(src): ready.pop(comp); continue
        shutil.rmtree(old, ignore_errors=True)
        if os.path.isdir(live): os.rename(live, old)
        os.rename(src, live)
        ready.pop(comp)
        after = ", ".join(f"{k} {v}" for k, v in sorted(info["versions"].items()))
        st.setdefault("history", []).append({"when": time.strftime("%Y-%m-%d %H:%M"), comp: info["versions"]})
        log(f"kit: updated Python packages: {after} (tested on this Mac first)")
    json.dump(ready, open(rp, "w"))
    save_state(st)
    return 0


def rollback():
    st = load_state(); done = False
    if os.path.exists(HF_LIVE):
        cur = hf_installed(); prev = st.pop("hf_prev", None)
        st.setdefault("bad", []).append(sig({"hyperframes": cur}))
        if prev and prev != hf_floor(): json.dump({"version": prev}, open(HF_LIVE, "w"))
        else: os.remove(HF_LIVE)
        log(f"rolled back HyperFrames {cur} -> {hf_installed()}"); done = True
    old = os.path.join(PREV, "venv")
    if os.path.isdir(old):
        tmp = VENV + ".rollback"
        os.rename(VENV, tmp); os.rename(old, VENV); shutil.rmtree(tmp, ignore_errors=True)
        last = [h["python"] for h in st.get("history", []) if "python" in h]
        if last: st.setdefault("bad", []).append(sig(last[-1]))   # don't stage the same packages again
        log("rolled back the Python packages"); done = True
    save_state(st)
    print("rolled back" if done else "nothing to roll back")
    return 0


def floor():
    """After a kit update: anything older than the kit's tested versions (or missing) is brought up to them."""
    if os.path.exists(HF_LIVE) and (vkey(hf_installed()) < vkey(hf_floor()) or line(hf_installed()) != line(hf_floor())):
        os.remove(HF_LIVE)   # the new kit release was tested with a newer HyperFrames line
    log(f"making sure HyperFrames {hf_installed()} and its Chrome are here")
    hf_ready(hf_installed())
    python = os.path.join(VENV, "bin", "python")
    inst = py_installed(python)
    need = [f"{n}=={v}" for n, v, m in requirements() if (not m or sys.platform in m) and
            (n.lower() not in inst or vkey(inst[n.lower()]) < vkey(v) or major(inst[n.lower()]) != major(v))]
    if need:
        log(f"installing the kit's tested Python packages: {' '.join(need)}")
        run([python, "-m", "pip", "install", "-q", "--disable-pip-version-check", *need])
    return 0


def status():
    st = load_state()
    print(f"HyperFrames {hf_installed()} (kit tested {hf_floor()})")
    try:
        inst = py_installed(os.path.join(VENV, "bin", "python"))
        print("Python: " + ", ".join(f"{n} {inst.get(n.lower(), 'missing')}" for n, v, m in requirements() if not m or sys.platform in m))
    except Exception as e:
        print(f"Python: can't read ({e})")
    last = st.get("last_check")
    print(f"last check: {time.strftime('%Y-%m-%d %H:%M', time.localtime(last)) if last else 'never'} (checks once a day on its own)")
    rp = os.path.join(NEXT, "READY.json")
    ready = json.load(open(rp)) if os.path.exists(rp) else {}
    for comp, info in ready.items():
        print(f"staged, tested, switches in at the next edit: {comp} {sig(info['versions'])}")
    for h in st.get("history", [])[-3:]:
        print(f"updated {h}")
    if os.path.exists(LOG):
        print("recent log:"); print("".join(open(LOG).readlines()[-5:]), end="")
    return 0


def auto():
    """Called by bin/kit at the start of every command: start the daily check in the background when it's due."""
    if os.environ.get("KIT_NO_AUTO_UPDATE"): return
    if time.time() - load_state().get("last_check", 0) < EVERY_S: return
    os.makedirs(D, exist_ok=True)
    subprocess.Popen([sys.executable, os.path.abspath(__file__), "check"], stdin=subprocess.DEVNULL, stdout=open(os.path.join(D, "last-run.txt"), "w"),
                     stderr=subprocess.STDOUT, start_new_session=True, env=env())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    c = sp.add_parser("check"); c.add_argument("--now", action="store_true")
    for n in ("apply", "status", "rollback", "floor"): sp.add_parser(n)
    a = ap.parse_args()
    return {"check": lambda: check(a.now), "apply": apply, "status": status, "rollback": rollback, "floor": floor}[a.cmd]()


if __name__ == "__main__":
    sys.exit(main())
