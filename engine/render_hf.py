"""The renderer: the edit plan, drawn by HyperFrames.

1. engine/timeline.py turns the plan + style into a frame-exact timeline (camera windows, captions, overlays, b-roll,
   pictures, library blocks, sound effects, and his voice as ONE sample-exact track).
2. This file writes it as a HyperFrames project in .work/_studio/<job>/ (index.html + assets/ + compositions/).
3. `kit preview <job...>` opens each project in HyperFrames Studio: he watches the whole edit live, nothing rendered.
   Edits made there, or by the agent in index.html, are the project from then on: a later build never overwrites a
   hand-edited project.
4. `kit render <job>` renders the project as it stands, sets loudness, then the QA gate runs.
"""
import glob, hashlib, html, json, math, os, re, shutil, subprocess, sys, time, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import quick_edit as qe  # noqa: E402
import timeline as tlm  # noqa: E402
import audio_clean  # noqa: E402
import graphic_guard as gg  # noqa: E402

KIT = qe.KIT
ENGINE = os.path.join(KIT, "engine")
STUDIO = os.path.join(KIT, ".work", "_studio")
LOOKS = os.path.join(KIT, "graphics", "_looks")              # real-look restyles for library blocks (<name>.css)
BLOCKS = os.path.join(KIT, ".cache", "blocks")             # library blocks, installed once, reused offline
FLOOR = os.path.join(ENGINE, "hyperframes.json")            # the HyperFrames version this kit release was tested with
LIVE = os.path.join(KIT, ".cache", "deps", "hyperframes.json")   # a newer version that passed its test (engine/deps.py)
GSAP = os.path.join(ENGINE, "vendor", "gsap.min.js")        # bundled: no internet needed to preview or render
LOGO_POP = [0.0, 0.35, 0.62, 0.86, 1.04, 1.1, 1.05, 1.0]   # logo tile: per-frame scale, frame 0 hidden
CARD_POP = [0.0, 0.7, 0.9, 1.04, 1.1, 1.06, 1.02, 1.0]     # picture card and text card: per-frame scale
MARK = ".kit-generated"                                    # hash of the index.html the kit wrote


def _vkey(v):
    return tuple(int(x) for x in re.findall(r"\d+", str(v).split("-")[0])[:3])


def hf_version():
    """The tested floor, or a newer same-line version engine/deps.py switched in. A leftover from an older line
    (an 0.8.x left in .cache after the kit moved to 0.9) is ignored, so a kit update always gets the new HyperFrames."""
    if os.environ.get("KIT_HF_VERSION"): return os.environ["KIT_HF_VERSION"]
    try: floor = json.load(open(FLOOR))["version"]
    except Exception: floor = "0.9.39"
    try: live = json.load(open(LIVE))["version"]
    except Exception: return floor
    return live if _vkey(live)[:2] == _vkey(floor)[:2] and _vkey(live) > _vkey(floor) else floor


def hf():
    return ["npx", "--yes", f"hyperframes@{hf_version()}"]


def writable(d):
    """Really writable (Codex's sandbox lets the kit write only inside the kit folder, whatever os.access says)."""
    try:
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, f".kit-write-test-{os.getpid()}")
        open(p, "w").close(); os.remove(p)
        return True
    except OSError:
        return False


_ENV = None
def env():
    """HyperFrames keeps npm's cache, its Chrome, fonts and preview state under the home folder. Inside a sandbox that
    can't be written, it gets a home inside the kit (.cache/home) instead, and uses the Chrome already installed if any."""
    global _ENV
    if _ENV is None:
        e = dict(os.environ); e["HYPERFRAMES_SKIP_SKILLS"] = "1"; e.setdefault("HF_NO_TELEMETRY", "1")
        # npx would ask the npm registry about the pinned version every call; with no internet (Codex's sandbox) that
        # hangs until a timeout. The version is pinned, so the copy in npm's cache is the right one; a version that
        # isn't cached yet is still downloaded.
        e.setdefault("npm_config_prefer_offline", "true")
        home = os.path.expanduser("~")
        if not all(writable(os.path.join(home, d)) for d in (".npm", os.path.join(".cache", "hyperframes"), os.path.join(".local", "state", "hyperframes"))):
            chrome = sorted(glob.glob(os.path.join(home, ".cache", "hyperframes", "chrome", "**", "chrome-headless-shell"), recursive=True))
            chrome = [c for c in chrome if os.path.isfile(c) and os.access(c, os.X_OK)]
            if chrome and "HYPERFRAMES_BROWSER_PATH" not in e: e["HYPERFRAMES_BROWSER_PATH"] = chrome[-1]
            e["HOME"] = os.path.join(KIT, ".cache", "home"); os.makedirs(e["HOME"], exist_ok=True)
        _ENV = e
    return dict(_ENV)


def at(proj):
    """Environment for a HyperFrames call about one project. HyperFrames names the Studio project from $PWD, not the
    process's working folder, so a stale $PWD (the folder the agent's shell was in) showed the wrong project name."""
    e = env(); e["PWD"] = os.path.abspath(proj)
    return e


def project_dir(job_name):
    return os.path.join(STUDIO, job_name)


def _sha(p):
    """Hash of index.html, ignoring the element ids Studio stamps in when it opens a project (data-hf-id)."""
    if not os.path.exists(p): return ""
    return hashlib.sha256(re.sub(r' data-hf-id="[^"]*"', "", open(p).read()).encode()).hexdigest()


def hand_edited(proj):
    """True when index.html differs from what the kit generated (Studio or the agent changed it)."""
    idx, mark = os.path.join(proj, "index.html"), os.path.join(proj, MARK)
    return os.path.exists(idx) and os.path.exists(mark) and _sha(idx) != open(mark).read().strip()


def _link(src, dst):
    if os.path.exists(dst): return
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    try: os.link(src, dst)
    except OSError: shutil.copy2(src, dst)


def _unsupported(tl):
    st = tl["style"]
    miss = [f"graphic template {o['template']}" for o in tl["overlays"] if o.get("template") not in (None, "logo_pop")]
    miss += [f"style setting {k}" for k in ("box", "word_pop") if st.get(k)]
    if miss: qe.die("this kit doesn't draw these yet: " + ", ".join(miss) + ". Use a library block instead (skills/graphics).")


def voice_track(tl, out):
    """Cleaned, leveled dialogue mastered at the existing style's loudness target."""
    st = tl["style"]; L = st["loudness"]; total = tl["frames"] / tl["fps"]; ef = float(st.get("end_fade_s", 0.15))
    return audio_clean.master(tl['dialogue'], out, total, float(L['I']), float(L['TP']), ef)


# ---------------------------------------------------------------- library blocks
SAVED = "saved"   # manifest.json key: a graphic he asked to keep in his style (bin/kit graphics save)


def own_block(style_name, name, graphics_dirs=()):
    """A graphic built for this video (.work/<job>/graphics/<name>/<name>.html), else one he asked to keep in his style
    (my-styles/<style>/templates/<name>/, marked saved), else the style's built-in one, else graphics/<name>/.
    Returns (folder, where) or (None, None). A graphic an older video left in my-styles without being saved is refused:
    a new Short never inherits an old video's graphic or its text."""
    for g in graphics_dirs or ():
        d = os.path.join(g, name)
        if os.path.exists(os.path.join(d, f"{name}.html")): return d, "video"
    d = os.path.join(KIT, "my-styles", style_name, "templates", name)
    if os.path.exists(os.path.join(d, f"{name}.html")):
        try: saved = bool(json.load(open(os.path.join(d, "manifest.json"))).get(SAVED))
        except (OSError, ValueError): saved = False
        if not saved:
            qe.die(f"my-styles/{style_name}/templates/{name}/ was left there by an older video, not saved by him, so it isn't used "
                   f"(a new Short never inherits an old video's graphic or text). Build this video's own copy in "
                   f".work/<job>/graphics/{name}/{name}.html with this video's words. Only if he asked to keep it in his style: "
                   f"bin/kit graphics save {name} --style {style_name or 'default'}")
        return d, "style"
    for d, where in ((os.path.join(KIT, "styles", style_name, "templates", name), "style"), (os.path.join(KIT, "graphics", name), "kit")):
        if os.path.exists(os.path.join(d, f"{name}.html")): return d, where
    return None, None


def install_block(name, proj, style_name="", graphics_dirs=()):
    """Copy a block into the project: one of his own (own_block), else a HyperFrames library block (from the kit's cache;
    the first use downloads it). Returns the block's {id, w, h, dur, origin} read from its own file."""
    own, where = own_block(style_name, name, graphics_dirs)
    if own:
        os.makedirs(os.path.join(proj, "compositions"), exist_ok=True)
        shutil.copy2(os.path.join(own, f"{name}.html"), os.path.join(proj, "compositions", f"{name}.html"))
        if os.path.isdir(os.path.join(own, "assets")):
            shutil.copytree(os.path.join(own, "assets"), os.path.join(proj, "assets"), dirs_exist_ok=True)
        return dict(block_meta(os.path.join(own, f"{name}.html"), name), src=f"compositions/{name}.html", origin=where)
    cache = os.path.join(BLOCKS, name)
    if not library_file(cache, name):
        fetch_block(name)
    for f in glob.glob(os.path.join(cache, "**", "*"), recursive=True):
        if os.path.isfile(f):
            dst = os.path.join(proj, os.path.relpath(f, cache))
            if not os.path.exists(dst): os.makedirs(os.path.dirname(dst), exist_ok=True); shutil.copy2(f, dst)
    return dict(block_meta(library_file(cache, name), name), origin="library")


def library_file(cache, name):
    """Where `hyperframes add` put it: compositions/<name>.html (a block) or compositions/components/<name>.html."""
    for rel in (os.path.join("compositions", f"{name}.html"), os.path.join("compositions", "components", f"{name}.html")):
        if os.path.exists(os.path.join(cache, rel)): return os.path.join(cache, rel)
    return None


def fetch_block(name):
    """The supported registry intake: `hyperframes add <name> --json --no-clipboard` into a staging folder, kept in
    .cache/blocks/<name>/ and reused offline from then on. Blocks and components both work. Returns the cache folder."""
    cache = os.path.join(BLOCKS, name)
    tmp = cache + ".tmp"; shutil.rmtree(tmp, ignore_errors=True); os.makedirs(tmp)
    json.dump({"paths": {"blocks": "compositions", "components": "compositions/components", "assets": "assets"}},
              open(os.path.join(tmp, "hyperframes.json"), "w"))
    e = at(tmp); e.pop("npm_config_prefer_offline", None)   # a new block has to come from the registry
    r = subprocess.run(hf() + ["add", name, "--dir", tmp, "--json", "--no-clipboard"], cwd=tmp, env=e,
                       capture_output=True, text=True, timeout=300)
    if r.returncode or not library_file(tmp, name):
        shutil.rmtree(tmp, ignore_errors=True)
        qe.die(f"couldn't get library block {name!r} (is the name right? `bin/kit blocks search <words>`): {(r.stdout + r.stderr)[-400:]}")
    for f in ("hyperframes.json", "hyperframes.lock.json", "TEMPLATE.md"):
        if os.path.exists(os.path.join(tmp, f)): os.remove(os.path.join(tmp, f))
    shutil.rmtree(cache, ignore_errors=True); os.replace(tmp, cache)
    return cache


def block_meta(path, name):
    """{id, w, h, dur, src, fluid}. A component has no data-width/height: it fills whatever box it's mounted in."""
    src = open(path).read()
    get = lambda a, d: (re.search(rf'{a}="([^"]+)"', src) or [None, d])[1]
    fluid = re.search(r'data-width="', src) is None
    rel = "compositions/" + ("components/" if os.sep + "components" + os.sep in path else "") + f"{name}.html"
    dur = get("data-duration", None) or get("data-composition-duration", 9999)
    return {"id": get("data-composition-id", name), "w": int(float(get("data-width", 1080))), "h": int(float(get("data-height", 1920))),
            "dur": float(dur), "src": rel, "fluid": fluid}


BLUR = re.compile(r"(-webkit-)?backdrop-filter\s*:[^;}]*;?|filter\s*:\s*blur\([^)]*\)[^;}]*;?", re.I)


def real_look(html_text, name):
    """Library blocks are demos: soft blurred backdrops, see-through cards. On his video a graphic is a sharp, solid
    replica, so blur filters are stripped and the kit's real-look restyle for that block (graphics/_looks/<name>.css),
    if there is one, is added last inside the block's own <style>."""
    out = BLUR.sub("", html_text)
    look = os.path.join(LOOKS, f"{name}.css")
    if os.path.exists(look):
        css = open(look).read()
        i = out.rfind("</style>")
        out = out[:i] + "\n/* kit real look: graphics/_looks/" + name + ".css */\n" + css + "\n" + out[i:] if i >= 0 else out
    return out


def reflow(html_text, w0, h0, w, h):
    """A fixed-canvas block laid out at the box's own size instead of scaled into it: the canvas size on the root
    element and in its CSS becomes the box size, so text renders at its designed pixel size, sharp, with no scaling."""
    out = re.sub(rf'data-width="{w0}"', f'data-width="{w}"', html_text, count=1)
    out = re.sub(rf'data-height="{h0}"', f'data-height="{h}"', out, count=1)
    out = re.sub(rf"(?<![-\w])width:\s*{w0}px", f"width: {w}px", out)
    out = re.sub(rf"(?<![-\w])height:\s*{h0}px", f"height: {h}px", out)
    return out


def prepare_block(b, i, proj, meta):
    """This mount's own copy of the block, next to the installed one: the plan's data in place of the block's sample
    content, the real-look restyle, and (fit "native", the default) the canvas reflowed to the box. Returns (meta for
    this mount, the texts it shows)."""
    src_rel = meta.get("src") or f"compositions/{b['name']}.html"
    src = open(os.path.join(proj, src_rel)).read()
    data = gg.primitive_data(src)
    if b.get("data") is not None:
        if data is None and "data-hf-primitive-data" not in src:
            qe.die(f"block {b['name']} has no data to replace; set its text with vars, or build a replica")
        data = b["data"] if not isinstance(b["data"], dict) or not isinstance(data, dict) else {**data, **b["data"]}
        src = gg.set_primitive_data(src, data)
    texts = gg.strings_in(data) + gg.strings_in(b.get("vars") or {})
    b["message"] = gg.is_message(dict(b, data=data if b.get("data") is None else b["data"]))
    # a message graphic from the library or a saved style still showing the texts it came with: an old video's or a demo's
    b["needs_data"] = b["message"] and meta.get("origin") != "video" and b.get("data") is None and not b.get("vars")
    src = real_look(src, b["name"])
    b["html_texts"] = gg.html_texts(src)   # words typed straight into the graphic are checked too
    m = dict(meta)
    x, y, w, h = b["box"]
    if not m.get("fluid"):
        k = min(w / m["w"], h / m["h"])
        if b.get("fit") != "scale" or k < gg.MIN_SCALE:
            # laid out at the box size, or a little bigger and mounted at reflow_scale (a long thread, nothing cut off)
            rs = float(b.get("reflow_scale") or 1.0)
            src = reflow(src, m["w"], m["h"], round(w / rs), round(h / rs)); m["w"], m["h"] = round(w / rs), round(h / rs)
    base, ext = os.path.splitext(src_rel)
    m["src"] = f"{base}--{i}{ext}"
    open(os.path.join(proj, m["src"]), "w").write(src)
    return m, texts


# ---------------------------------------------------------------- caption designs
def design_dir(style_name, name):
    """A style's own caption design (my-styles or styles/<style>/templates/<name>/), else a shared one in graphics/<name>/."""
    for base in (os.path.join(KIT, "my-styles", style_name), os.path.join(KIT, "styles", style_name)):
        d = os.path.join(base, "templates", name)
        if os.path.isdir(d): return d
    d = os.path.join(KIT, "graphics", name)
    return d if os.path.isdir(d) else None


def caption_design(tl):
    name = tl["style"].get("caption_template")
    if not name: return None
    d = design_dir(tl.get("style_name") or "", name)
    if not d: qe.die(f"caption design {name!r} not found (templates/{name}/ in the style, or graphics/{name}/)")
    rd = lambda f: open(os.path.join(d, f)).read() if os.path.exists(os.path.join(d, f)) else ""
    return {"name": name, "css": rd("captions.css"), "js": rd("captions.js")}


# ---------------------------------------------------------------- the project
def split_windows(tl, lens=None):
    """The frame spans (start, end) a library block is on screen, merged when they touch: the panel's spans."""
    return [(w0, w1) for w0, w1, _ in panel_windows(tl, lens)]


def panel_windows(tl, lens=None):
    """[(start, end, panel height px)]: each span a panel block is on screen (merged when they touch), with the panel
    as tall as its tallest block, so it doesn't change size while it shows."""
    out, bl = [], tl.get("blocks") or []
    for i, b in sorted(enumerate(bl), key=lambda ib: ib[1]["start"]):
        if b.get("show") in ("overlay", "cutaway"): continue
        end = b["start"] + (lens[i] if lens else b["frames"])
        box = b.get("box") or gg.graphic_area(tl["width"], tl["height"])
        ph = int(round(box[1] + box[3]))
        if out and b["start"] <= out[-1][1]: out[-1][1] = max(out[-1][1], end); out[-1][2] = max(out[-1][2], ph)
        else: out.append([b["start"], end, ph])
    return [tuple(w) for w in out]


def face_pos(tl, top=None):
    """object-position y (%) for his face below a panel that ends at `top` (px; default half the frame): the face box
    centred between the panel and the caption line (his chin kept in when the face is tall), from the face found in
    the clip; 28% when none was found."""
    f = (tl.get("style") or {}).get("face_focus_y")
    W, H, sw, sh = tl["width"], tl["height"], tl.get("src_w") or 1080, tl.get("src_h") or 1920
    top = H // 2 if top is None else top
    ph = H - top; rh = sh * W / sw
    if not f or rh <= ph: return 28.0
    cap_top = ((tl.get("layout") or {}).get("cap_top")) or (top + ph * 0.96)
    room = max(ph * 0.3, min(ph, cap_top - top))   # where his face can be seen: from the panel down to the captions
    ft, fb = f["top"] * rh, f["bottom"] * rh
    off = (ft + fb) / 2 - room * 0.5
    off = min(off, ft - room * 0.06) if fb - ft > room * 0.85 else off   # a very tall face: keep from the forehead down
    off = max(0.0, min(rh - ph, max(off, fb + ph * 0.04 - ph)))           # never cut the chin
    return off / (rh - ph) * 100


def write_html(tl, blocks_meta):
    fps, W, H = tl["fps"], tl["width"], tl["height"]
    st = tl["style"]; T = tl["frames"] / fps
    frame_split = str(st.get("frame_layout") or "").strip().lower() in {"split", "panel", "top-panel"}
    panel_color = st.get("panel_color") or "#121417"
    # times are floored to the microsecond: a clip shows while start <= t < start + duration, and a rounded-up start
    # leaves one frame where neither neighbour shows (a black frame at the cut)
    t = lambda fr: math.floor(fr / fps * 1e6) / 1e6
    s = lambda fr: f"{t(fr):.6f}"
    span = lambda a, n: f'data-start="{s(a)}" data-duration="{math.floor((t(a + n) - t(a)) * 1e6) / 1e6:.6f}"'
    jt = lambda fr: f"{math.floor(fr / fps * 1e6) / 1e6:.6f}"   # animation times: floored too, or a step lands a frame late
    sc = min(W, H) / 1080          # graphics are designed 1080 px wide
    js, body, top, caps_html = [], [], [], []   # captions go last: always on top of b-roll, pictures and blocks

    def framed(id_, src, start, n, src_frame, crop, sw, sh, track):
        x, y, w, _ = crop; k = W / w
        return (f'<video id="{id_}" src="assets/{src}" muted playsinline {span(start, n)} data-media-start="{s(src_frame)}" '
                f'data-track-index="{track}" style="position:absolute;left:{-x * k:.2f}px;top:{-y * k:.2f}px;'
                f'width:{sw * k:.2f}px;height:{sh * k:.2f}px;max-width:none"></video>')

    def pop(sel, start, curve):
        for f, v in enumerate(curve):
            js.append(f'tl.set("{sel}", {{scale: {v}, opacity: {1 if v > 0 else 0}}}, {jt(start + f)});')

    # camera: muted pieces of his clip, each cropped to its output-shaped window (punch-ins are tighter windows), full frame.
    for i, p in enumerate(tl["camera"]):
        n = p["frames"] + (1 if i < len(tl["camera"]) - 1 else 0)   # one frame under the next piece: never a gap
        body.append(framed(f"cam{i}", p["src"], p["start"], n, p["src_frame"], p["crop"], tl["src_w"], tl["src_h"], 1))
        if p.get("drift"):
            x, y, w, h = p["crop"]; k = W / w
            js.append(f'tl.fromTo("#cam{i}", {{scale: 1}}, {{scale: {1 + p["drift"]}, duration: {p["frames"] / fps:.4f}, ease: "none", '
                      f'transformOrigin: "{x * k + W / 2:.1f}px {y * k + H / 2:.1f}px"}}, {jt(p["start"])});')

    # panel layout (frame_layout split): while a graphic is on screen, a panel on top as tall as that graphic (opaque)
    # and his face below it, framed between the panel and the captions; the rest of the time (the hook, between
    # graphics) his face is full frame. full layout: no panel; graphics pop in around his face or cut away full screen.
    lens = [min(b["frames"], int((blocks_meta.get(i) or blocks_meta.get(b["name"]) or {"dur": 9999})["dur"] * fps))
            for i, b in enumerate(tl.get("blocks") or [])]
    windows = panel_windows(tl, lens) if frame_split else []
    for wi, (w0, w1, ph) in enumerate(windows):
        head = (f"left:0;top:{ph}px;width:{W}px;height:{H - ph}px;object-fit:cover;object-position:50% {face_pos(tl, ph):.1f}%")
        body.append(f'<div id="panel{wi}" class="clip" {span(w0, w1 - w0)} data-track-index="20" style="position:absolute;left:0;top:0;'
                    f'width:{W}px;height:{ph}px;background:{panel_color}"></div>')
        pieces = [p for p in tl["camera"] if p["start"] < w1 and p["start"] + p["frames"] > w0]
        for j, p in enumerate(pieces):
            a0 = max(p["start"], w0); a1 = min(p["start"] + p["frames"] + (1 if j < len(pieces) - 1 else 0), w1)
            body.append(f'<video id="head{wi}_{j}" src="assets/{p["src"]}" muted playsinline {span(a0, a1 - a0)} '
                        f'data-media-start="{s(p["src_frame"] + a0 - p["start"])}" data-track-index="{21 + j % 2}" '
                        f'style="position:absolute;{head}"></video>')

    # b-roll: muted, over the camera. full = the whole frame (cropped to the output shape); pip = full frame with his face
    # in a corner box (screen recordings on long-form); split = b-roll on top, his face on the bottom half (vertical)
    for i, b in enumerate(tl["broll"]):
        lay = b.get("layout", "full")
        if lay == "full":
            body.append(framed(f"broll{i}", b["file"], b["start"], b["frames"], b["src_frame"], b["crop"], b["src_w"], b["src_h"], 4))
            continue
        bh = H // 2 if lay == "split" else H
        body.append(f'<video id="broll{i}" src="assets/{b["file"]}" muted playsinline {span(b["start"], b["frames"])} '
                    f'data-media-start="{s(b["src_frame"])}" data-track-index="4" style="position:absolute;left:0;top:0;width:{W}px;'
                    f'height:{bh}px;object-fit:cover"></video>')
        box = (f"left:0;top:{H // 2}px;width:{W}px;height:{H - H // 2}px;object-fit:cover;object-position:50% 35%" if lay == "split" else
               f"left:{W - round(W * 0.28) - round(W * 0.025)}px;top:{H - round(H * 0.28) - round(H * 0.045)}px;width:{round(W * 0.28)}px;"
               f"height:{round(H * 0.28)}px;object-fit:cover;object-position:50% 30%;border-radius:{round(min(W, H) * 0.02)}px;"
               f"box-shadow:0 10px 30px rgba(0,0,0,0.45)")
        for j, p in enumerate(tl["camera"]):   # his face during the b-roll: the same camera pieces, in the box
            a0, a1 = max(p["start"], b["start"]), min(p["start"] + p["frames"], b["start"] + b["frames"])
            if a1 <= a0: continue
            body.append(f'<video id="face{i}_{j}" src="assets/{p["src"]}" muted playsinline {span(a0, a1 - a0)} '
                        f'data-media-start="{s(p["src_frame"] + a0 - p["start"])}" data-track-index="4" style="position:absolute;{box}"></video>')

    # sound effects: root-level audio clips (HyperFrames mixes them with his voice)
    top += [f'<audio id="sfx{i}" src="assets/{x["file"]}" {span(x["start"], max(1, round(x["dur_s"] * fps)))} data-track-index="5" '
            f'data-volume="{10 ** (x["gain_db"] / 20):.4f}"></audio>' for i, x in enumerate(tl["sfx"])]

    # captions: chunks, size, stroke and keyword timing from the style. A style's own caption design
    # (caption_template: captions.css + captions.js) takes over the keyword treatment.
    stroke, shadow = st.get("stroke", 7) * H / 1920, st.get("shadow", 2) * H / 1920
    white, hot = st.get("color", "#FFFFFF"), st.get("highlight_color", "#DC143C")
    ks, kpop = float(st.get("keyword_scale", 1.0)), float(st.get("kw_pop_pct", 0)) / 100   # keyword size, and its pop as it's spoken
    design = caption_design(tl)
    # captions stay at one height for the whole video (style center_y_frac, set once per video): no jumping to a seam
    for i, c in enumerate(tl["captions"]):
        t0 = c.get("t0", c["start"])
        lines = []
        for li, line in enumerate(c["lines"]):
            ws = []
            for j, w in enumerate(line):
                wid = f"w{i}_{li}_{j}"
                col = hot if (w["hot"] and not st.get("kw_sync_pop") and not design) else white
                size = f";font-size:{ks:g}em" if w["hot"] and ks != 1 and not design else ""
                ws.append(f'<span id="{wid}" class="w{" kw" if w["hot"] else ""}" data-at="{jt(w["at"])}" '
                          f'style="color:{col}{size}">{html.escape(w["text"])}</span>')
                if w["hot"] and st.get("kw_sync_pop") and not design:
                    js.append(f'tl.fromTo("#{wid}", {{color: "{white}"}}, {{color: "{hot}", duration: 0.07, ease: "none"}}, {jt(w["at"])});')
                if w["hot"] and kpop > 0 and not design:
                    js.append(f'tl.fromTo("#{wid}", {{scale: {1 + kpop:g}}}, {{scale: 1, duration: {st.get("pop_ms", 150) / 1000}, ease: "none"}}, {jt(w["at"])});')
            lines.append("<div>" + " ".join(ws) + "</div>")
        px = c["size"] * st.get("font_css_scale", 0.82)
        caps_html.append(f'<div id="cap{i}" class="clip" {span(c["start"], max(1, c["end"] - c["start"]))} '
                    f'data-track-index="2"><div class="cap"><div id="capin{i}" class="capin" data-t0="{jt(t0)}" style="font-size:{px:.2f}px;'
                    f'line-height:{c["size"]:.2f}px">{"".join(lines)}</div></div></div>')
        js.append(f'tl.fromTo("#capin{i}", {{scale: {st.get("pop_scale", 1.06)}}}, {{scale: 1, duration: {st.get("pop_ms", 150) / 1000}, '
                  f'ease: "none"}}, {jt(t0)});')

    # overlays: app logo tiles and pictures (screenshots, photos) on a card, x/y = card centre in 1080-wide px
    for i, o in enumerate(tl["overlays"]):
        at = f'position:absolute;left:{o["x"] * sc:.1f}px;top:{o["y"] * sc:.1f}px;transform:translate(-50%,-50%) scale({sc:.4f})'
        if o.get("picture"):
            inner = (f'<div id="card{i}" class="card" style="border-radius:{o.get("round", 28)}px">'
                     f'<img src="assets/{o["picture"]}" style="width:{o.get("w", 620)}px;height:auto;display:block" alt=""></div>')
            pop(f"#card{i}", o["start"], CARD_POP)
        elif o.get("file"):   # a transparent video (WebM / ProRes 4444) at its own size
            body.append(f'<video id="ovv{i}" src="assets/{o["file"]}" muted playsinline {span(o["start"], o["frames"])} '
                        f'data-media-start="0" data-track-index="3" style="{at}"></video>')
            continue
        else:
            logo = o["props"]["logo"]
            g = o["props"].get("glyph") or (150 if "instagram" in logo.lower() else 160)
            inner = f'<div id="tile{i}" class="tile"><img src="assets/{logo}" style="width:{g}px;height:auto;display:block" alt=""></div>'
            pop(f"#tile{i}", o["start"], LOGO_POP)
        body.append(f'<div id="ov{i}" class="clip" {span(o["start"], o["frames"])} data-track-index="3"><div style="{at}">{inner}</div></div>')

    # text cards (plan "graphics"): a short line on the style's box colour, popped in, faded out
    gs = st.get("graphic") or {}
    for i, g in enumerate(tl["graphics"]):
        body.append(f'<div id="gfx{i}" class="clip" {span(g["start"], g["frames"])} data-track-index="6"><div class="gfx" '
                    f'style="top:{gs.get("y_frac", 0.22) * H:.1f}px"><span id="gfxin{i}" class="gfxin">{html.escape(g["text"])}</span></div></div>')
        pop(f"#gfxin{i}", g["start"], CARD_POP)
        js.append(f'tl.to("#gfxin{i}", {{opacity: 0, duration: 0.12, ease: "none"}}, {jt(g["start"] + g["frames"] - 0.12 * fps)});')

    # library blocks: HyperFrames sub-compositions, each in its box [x, y, w, h] (graphic_guard.place_blocks: a panel
    # sized to the block, an overlay around his face, or a full-screen cutaway). A block's own canvas is never scaled
    # up, and a block prepared at the box size (prepare_block) mounts at scale 1: sharp text, no soft upscaled card.
    for i, b in enumerate(tl.get("blocks") or []):
        m = blocks_meta.get(i) or blocks_meta[b["name"]]
        n = min(b["frames"], int(m["dur"] * fps))
        x, y, w, h = b.get("box") or [0, 0, W, H]
        if m.get("fluid"):   # a component fills the box it's given, at full resolution
            mw, mh, k = round(w), round(h), 1.0
        else:                # a block keeps its own canvas, fitted into the box (never enlarged) and centred in it
            mw, mh = m["w"], m["h"]; k = min(1.0, w / mw, h / mh)
            x, y = x + (w - mw * k) / 2, y + (h - mh * k) / 2
        vv = f" data-variable-values='{html.escape(json.dumps(b['vars']), quote=True)}'" if b.get("vars") else ""
        show = b.get("show") or ""
        # a panel or cutaway graphic is square-cornered, like a real screen; an overlay is a rounded card
        radius = 0 if show in ("panel", "cutaway") or not show and frame_split else (round(28 / k) if k < 1 else 28)
        lift = ";box-shadow:0 18px 50px rgba(0,0,0,0.45)" if show == "overlay" else ""
        tag = (f'<div id="blk{i}" data-composition-id="{m["id"]}" data-composition-src="{m.get("src") or f"compositions/{b['name']}.html"}" '
               f'{span(b["start"], n)} data-track-index="{7 + i}" data-width="{mw}" data-height="{mh}"{vv}'
               f'{f" data-kit-show={chr(34)}{show}{chr(34)}" if show else ""} '
               f'style="position:absolute;left:{x:.1f}px;top:{y:.1f}px;width:{mw}px;height:{mh}px;'
               f'transform-origin:0 0;transform:scale({k:.5f});overflow:hidden;border-radius:{radius}px{lift}"></div>')
        if show == "overlay":   # pops in around his face: a quick scale-up from its own centre
            cx, cy = x + mw * k / 2, y + mh * k / 2
            body.append(f'<div id="pop{i}" style="position:absolute;inset:0;transform-origin:{cx:.1f}px {cy:.1f}px">{tag}</div>')
            js.append(f'tl.fromTo("#pop{i}", {{scale: 0.9, opacity: 0}}, {{scale: 1, opacity: 1, duration: 0.2, ease: "power2.out"}}, {jt(b["start"])});')
        else:
            body.append(tag)

    body += caps_html
    margin = round(W * 0.06)
    css = f"""
      @font-face {{ font-family: "kitfont"; src: url("assets/{tl['font']}"); font-display: block; }}
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      html, body {{ width: {W}px; height: {H}px; overflow: hidden; background: {tl.get('background', '#000')}; }}
      .cap {{ position: absolute; left: {margin}px; right: {margin}px; top: {st.get('center_y_frac', 0.64) * H:.1f}px;
              transform: translateY(-50%); text-align: center; }}
      .capin {{ display: inline-block; font-family: "kitfont", sans-serif; white-space: {'nowrap' if st.get('one_line') else 'normal'};
                -webkit-text-stroke: {2 * stroke:.2f}px {st.get('stroke_color', '#000000')}; paint-order: stroke fill;
                filter: drop-shadow({shadow:.2f}px {shadow:.2f}px 0 rgba(0,0,0,0.5)); }}
      .w {{ display: inline-block; }}
      .tile {{ width: 230px; height: 230px; border-radius: 54px; background: white; display: flex; align-items: center;
               justify-content: center; box-shadow: 0 8px 28px rgba(0,0,0,0.35); opacity: 0; }}
      .card {{ overflow: hidden; background: white; box-shadow: 0 14px 40px rgba(0,0,0,0.38); opacity: 0; }}
      .gfx {{ position: absolute; left: 0; right: 0; transform: translateY(-50%); text-align: center; }}
      .gfxin {{ display: inline-block; opacity: 0; font-family: "kitfont", sans-serif; padding: {18 * sc:.0f}px;
                font-size: {gs.get('size_frac', 0.062) * H * st.get('font_css_scale', 0.82):.1f}px;
                background: {gs.get('box_color', st.get('highlight_color', '#DC143C'))}; color: {gs.get('text_color', '#FFFFFF')}; }}"""
    if design:
        css += "\n      /* caption design: " + design["name"] + " */\n" + design["css"]
        style_json = json.dumps({k: v for k, v in st.items() if isinstance(v, (int, float, str, bool))})
        js.append("// caption design: " + design["name"] + "\n      (function (tl, captions, style, scale) {\n" + design["js"]
                  + "\n      })(tl, Array.from(document.querySelectorAll('.capin')).map(function (el) { return {el: el, t0: +el.dataset.t0, "
                  + "words: Array.from(el.querySelectorAll('.w')).map(function (w) { return {el: w, at: +w.dataset.at, hot: w.classList.contains('kw'), "
                  + f"text: w.textContent}}; }})}}; }}), {style_json}, {H / 1920});")
    nl = "\n      "
    lay = tl.get("layout") or {}
    kit_attrs = ""
    if lay:   # what the kit's layout check needs to read back from index.html (hand edits included)
        face = gg.face_box(lay.get("face"), W, H)
        kit_attrs = (f' data-kit-layout="{lay.get("mode", "panel")}" data-kit-cap-top="{lay.get("cap_top", H / 2):.0f}"'
                     f' data-kit-face="{face[1]:.0f},{face[1] + face[3]:.0f}"')
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width={W}, height={H}" />
    <!-- Made by the Matthew Studio Kit from .work/{tl.get('job', '')}/edl.json. Edit freely: once this file is changed,
         the kit never overwrites it (kit preview --rebuild starts over from the plan). -->
    <script src="assets/gsap.min.js"></script>
    <style>{css}
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-duration="{T:.4f}" data-fps="{fps}" data-width="{W}" data-height="{H}">
      <audio id="voice" src="assets/voice.wav" data-start="0" data-duration="{T:.4f}" data-track-index="0" data-volume="1"></audio>
      {nl.join(top)}
      <div id="frame" data-layout-allow-overflow{kit_attrs} style="position:absolute;inset:0;overflow:hidden">
      {nl.join(body)}
      </div>
    </div>
    <script>
      const tl = gsap.timeline({{ paused: true }});
      {nl.join(js)}
      window.__timelines["main"] = tl;
    </script>
  </body>
</html>
"""


def build(edl_path, force=False):
    """Write (or keep) the HyperFrames project for this job. Returns (project dir, status line)."""
    edl_path = os.path.abspath(edl_path)
    job = os.path.basename(os.path.dirname(edl_path))
    proj = project_dir(job)
    if hand_edited(proj) and not force:
        return proj, "kept (hand-edited; kit preview <job> --rebuild starts over from the plan)"
    tl, media = tlm.build(edl_path, True)
    tl["job"] = job
    _unsupported(tl)
    a = os.path.join(proj, "assets"); os.makedirs(a, exist_ok=True)
    for key, src in media.items(): _link(src, os.path.join(a, key))
    _link(GSAP, os.path.join(a, "gsap.min.js"))
    for x in tl["sfx"]:
        x["dur_s"] = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                           media[x["file"]]], capture_output=True, text=True).stdout.strip() or 0.5)
    gd = tl.get("graphics_dirs") or []
    installed = {b["name"]: install_block(b["name"], proj, tl.get("style_name") or "", gd) for b in tl.get("blocks") or []}
    blocks_meta, W, H = {}, tl["width"], tl["height"]
    lay = tl.get("layout")
    if lay and tl.get("blocks"):
        # a vertical Short: each block's box from the layout (a panel sized to it, or an overlay / cutaway around his face)
        try:
            notes = gg.place_blocks(tl["blocks"], W, H, lay["mode"], lay["cap_top"], lay.get("face"),
                                    {i: installed[b["name"]] for i, b in enumerate(tl["blocks"])})
        except ValueError as e:
            qe.die(str(e))
        tl["caption_place"] = tl.get("caption_place", "") + "".join("; " + n for n in notes)
    for i, b in enumerate(tl.get("blocks") or []):
        if not b.get("box"): b["box"] = [0, 0, W, H]
        blocks_meta[i], b["texts"] = prepare_block(b, i, proj, installed[b["name"]])
    bad = gg.check_text(tl.get("blocks") or [], tl.get("graphics") or [], tl.get("words") or [], tl["fps"])
    if bad:
        qe.die("on-screen text problems:\n  " + "\n  ".join(bad)
               + "\nA normal graphic shows his words: put what he says at that moment in its \"data\" / \"vars\" / HTML (or the text card)."
               + " A message graphic (iMessage, DM, notification) shows made-up, realistic texts from her, never his script lines."
               + " Then preview again.")
    tl.setdefault('audio_processing', {}).update(voice_track(tl, os.path.join(a, "voice.wav")))
    idx = os.path.join(proj, "index.html")
    open(idx, "w").write(write_html(tl, blocks_meta))
    open(os.path.join(proj, MARK), "w").write(_sha(idx))
    json.dump(tl, open(os.path.join(proj, "timeline.json"), "w"), indent=1)
    json.dump({"paths": {"blocks": "compositions", "components": "compositions/components", "assets": "assets"}},
              open(os.path.join(proj, "hyperframes.json"), "w"), indent=2)
    json.dump({"id": job, "name": job}, open(os.path.join(proj, "meta.json"), "w"), indent=2)
    return proj, "built from the plan; " + tl.get("caption_place", "")


def layout_errors(proj):
    """The kit's own layout gate on index.html as it stands (hand edits included), on a vertical Short:
    panel layout: every mounted block sits in the top panel, above his face and the caption line;
    full layout: an overlay never covers his face or the captions, and a cutaway fills the whole frame;
    both: phone-readable size, never scaled up. Returns error lines."""
    idx = os.path.join(proj, "index.html")
    if not os.path.exists(idx): return []
    src = open(idx).read()
    root = re.search(r'data-composition-id="main"[^>]*?data-width="(\d+)"[^>]*?data-height="(\d+)"', src)
    if not root: return []
    W, H = int(root.group(1)), int(root.group(2))
    if not gg.is_vertical(W, H): return []
    fr = re.search(r'<div id="frame"[^>]*>', src)
    attr = lambda k, d=None: (lambda m: m.group(1) if m else d)(re.search(rf'{k}="([^"]*)"', fr.group(0) if fr else ""))
    mode = attr("data-kit-layout", "panel")
    cap_top = float(attr("data-kit-cap-top", H / 2))
    ft, fb = (float(v) for v in attr("data-kit-face", f"{H // 2},{H}").split(","))
    face = [0, ft, W, fb - ft]
    lim = max(gg.panel_max(H, cap_top), gg.graphic_area(W, H)[3])
    errs = []
    for tag in re.findall(r"<div\b[^>]*data-composition-src=[^>]*>", src):
        bid = (re.search(r'id="([^"]+)"', tag) or [None, "?"])[1]
        st = (re.search(r'style="([^"]*)"', tag) or [None, ""])[1]
        show = (re.search(r'data-kit-show="([^"]*)"', tag) or [None, "panel" if mode == "panel" else "overlay"])[1]
        num = lambda k: (lambda m: float(m.group(1)) if m else None)(re.search(rf"(?<![-\w]){k}:\s*(-?[\d.]+)px", st))
        x, y, w, h = num("left"), num("top"), num("width"), num("height")
        if None in (x, y, w, h):
            errs.append(f"layout: block #{bid} has no fixed box (left/top/width/height in px); mount it in the top panel [0, 0, {W}, <= {lim:.0f}]")
            continue
        k = (lambda m: float(m.group(1)) if m else 1.0)(re.search(r"scale\(([\d.]+)\)", st))
        box = [x, y, w * k, h * k]
        rb = [round(v) for v in box]
        if show == "cutaway":
            if not (box[0] <= 1 and box[1] <= 1 and box[2] >= W - 1 and box[3] >= H - 1):
                errs.append(f"layout: cutaway #{bid} at {rb} doesn't fill the frame, so it sits on his face; make it [0, 0, {W}, {H}] or an overlay beside his face")
        elif show == "overlay" or mode == "full":
            if gg.overlaps(box, face):
                errs.append(f"layout: block #{bid} at {rb} covers his face (rows {ft:.0f}-{fb:.0f}); move it above or below his face, or make it a full-screen cutaway")
            elif box[1] + box[3] > cap_top + 1:
                errs.append(f"layout: block #{bid} at {rb} runs into the captions (they start at y={cap_top:.0f})")
        elif box[1] + box[3] > lim + 1:
            errs.append(f"layout: block #{bid} at {rb} covers his face; keep it inside the top panel [0, 0, {W}, <= {lim:.0f}]")
        elif not gg.inside(box, [0, 0, W, lim]):
            errs.append(f"layout: block #{bid} at {rb} crosses the frame edge; keep it inside [0, 0, {W}, <= {lim:.0f}]")
        if show != "cutaway" and (box[2] < gg.MIN_BOX_W_FRAC * W or box[3] < gg.MIN_BOX_H * H / 1920):
            errs.append(f"layout: block #{bid} is {round(box[2])}x{round(box[3])} px, too small to read on a phone; make it at least "
                        f"{round(gg.MIN_BOX_W_FRAC * W)} px wide and {round(gg.MIN_BOX_H * H / 1920)} px tall")
        if k > 1.001:
            errs.append(f"layout: block #{bid} is scaled up {k:.2f}x, which makes it soft; lay it out at the box size instead")
    return errs


def _json_out(text):
    """The JSON object HyperFrames printed, even with a notice before it. None when there is none."""
    i = text.find("{")
    while i >= 0:
        try:
            return json.JSONDecoder().raw_decode(text[i:])[0]
        except ValueError:
            i = text.find("{", i + 1)
    return None


def check(proj):
    """The gate before Studio opens and before a render: HyperFrames' check (lint, runtime, layout, contrast) plus the
    kit's layout gate. Any error fails it, and output that can't be read fails it too (never "probably fine").
    One exception: a caption word's colour against the footage behind it is a note, not a failure. Its contrast test
    ignores the caption outline and depends on what happens to be behind the word in the sampled frames, so it would
    block his approved keyword colour on one clip and pass it on the next (skills/style: look at the still)."""
    r = subprocess.run(hf() + ["check", "--json", os.path.abspath(proj)], cwd=proj, capture_output=True, text=True, env=at(proj))
    d = _json_out(r.stdout)
    kit_errs = layout_errors(proj)
    if not isinstance(d, dict):
        return 1, "\n".join(kit_errs + ["hyperframes check gave no readable result (treated as failed):", (r.stdout + r.stderr)[-2500:]])
    errors, notes, total = [], [], 0
    for part, res in d.items():
        if not isinstance(res, dict) or not isinstance(res.get("findings"), list):
            continue
        total += res.get("errorCount") or 0
        for f in res["findings"]:
            sel = str(f.get("selector", "") or f.get("elementId", ""))
            where = f" ({os.path.basename(str(f['file']))}:{f.get('line', '')})" if f.get("file") else ""
            line = f"{part}: {f.get('code')} {sel}{where} t={f.get('time', '')}: {f.get('message', '')} {f.get('fixHint', '')}".strip()
            if f.get("severity") != "error":
                continue
            if part == "contrast" and sel.startswith("#w"):
                notes.append(f"note, caption colour: \"{f.get('text', '')}\" {f.get('fg')} on {f.get('bg')} is {f.get('ratio')}:1 "
                             f"at {f.get('time')}s (outline not counted); a brighter option is {f.get('suggestedColor')}")
            else:
                errors.append(line)
    errors += kit_errs
    failed = bool(errors) or total > len(notes) or (not d.get("ok") and not notes) or (r.returncode != 0 and not notes)
    if failed and not errors:
        errors = [f"hyperframes check failed ({total} errors):", (r.stdout + r.stderr)[-3000:]]
    head = [f"{len(errors)} error(s) to fix first:"] if errors else []
    log = "\n".join(head + errors + notes) or "check passed"
    return (1 if failed else 0), log


def running(proj):
    """The Studio URL of this project's preview server if one is already up, else None."""
    r = subprocess.run(hf() + ["preview", "--status", "--json", os.path.abspath(proj)], cwd=proj, env=at(proj), capture_output=True, text=True, timeout=60)
    try:
        res = json.loads(r.stdout)["result"]
        return res["studioUrl"].replace("127.0.0.1", "localhost") if res.get("state") == "running" and res.get("ready") else None
    except Exception:
        return None


def free_port(start):
    """The first port from `start` that nothing is listening on (another project's Studio, another app)."""
    import socket
    for p in range(start, start + 200):
        with socket.socket() as so:
            if so.connect_ex(("127.0.0.1", p)) != 0: return p
    qe.die("no free port for Studio")


def preview(proj, port):
    """Studio on this project (live, nothing rendered). Returns (url, started). A server that's already up is reused:
    Studio reloads the open tab when index.html changes, so an update never needs a new tab."""
    url = running(proj)
    if url: return url, False
    port = free_port(port)
    r = subprocess.run(hf() + ["preview", "--background", "--no-open", "--port", str(port), os.path.abspath(proj)], cwd=proj, env=at(proj),
                       capture_output=True, text=True, timeout=180)
    for _ in range(60):   # only HyperFrames' own word that THIS project is up counts (a busy port can answer for another)
        url = running(proj)
        if url: return url, True
        time.sleep(1)
    qe.die(f"Studio didn't start for {os.path.basename(proj)}: {(r.stdout + r.stderr)[-600:]}")


def stop(proj):
    subprocess.run(hf() + ["preview", "--stop", os.path.abspath(proj)], cwd=proj, env=at(proj), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def render(proj, out_mp4):
    """Render the project as it stands (hand edits included), then trim loudness onto the style's target."""
    t0 = time.time()
    code, log = check(proj)
    if code: qe.die("hyperframes check failed:\n" + log[-3000:])
    os.makedirs(os.path.dirname(out_mp4), exist_ok=True)
    t1 = time.time()
    r = subprocess.run(hf() + ["render", os.path.abspath(proj), "--output", out_mp4], cwd=proj, env=at(proj), capture_output=True, text=True)
    if r.returncode or not os.path.exists(out_mp4): qe.die("HyperFrames render failed:\n" + (r.stdout + r.stderr)[-3000:])
    t2 = time.time()
    tl = json.load(open(os.path.join(proj, "timeline.json")))
    L = tl["style"]["loudness"]
    gain = qe.loud_trim(out_mp4, float(L["I"]), float(L["TP"]))
    stage = next((l.strip() for l in (r.stdout + r.stderr).splitlines() if "capture" in l and "encode" in l), "")
    rep = {"engine": f"hyperframes {hf_version()}", "project": proj, "output": out_mp4, "hand_edited": hand_edited(proj),
           "w": tl["width"], "h": tl["height"], "fps": tl["fps"], "expected_duration_s": round(tl["frames"] / tl["fps"], 3),
           "loudness_trim_db": gain, "hf_stages": stage,
           "timing_s": {"check": round(t1 - t0, 2), "hyperframes": round(t2 - t1, 2), "finish": round(time.time() - t2, 2),
                        "render_total": round(time.time() - t0, 2)}}
    json.dump(rep, open(os.path.join(os.path.dirname(out_mp4), "qe_report.json"), "w"), indent=2)
    print(f"rendered {out_mp4} ({rep['expected_duration_s']} s) with HyperFrames {hf_version()} in {rep['timing_s']['render_total']} s")
    return out_mp4


def snapshot(proj, times):
    """Still frames of the project (no render): [png paths]."""
    t0 = time.time()
    r = subprocess.run(hf() + ["snapshot", "--no-end", "--at", ",".join(f"{x:.2f}" for x in times), os.path.abspath(proj)], cwd=proj, env=at(proj), capture_output=True, text=True, timeout=300)
    found = list(dict.fromkeys(m.strip() for m in re.findall(r"(/[^\n]*?/snapshots/[^\n]*?/frame-\d+[^\n]*?\.png)", r.stdout + r.stderr)))
    if found and all(os.path.exists(f) for f in found):
        return found
    # paths with spaces, or a CLI that prints them differently: the frames this call just wrote, in time order
    new = [f for f in glob.glob(os.path.join(proj, ".hyperframes", "**", "frame-*.png"), recursive=True) if os.path.getmtime(f) >= t0 - 1]
    return sorted(new)


def main():
    import argparse
    ap = argparse.ArgumentParser(description="build / preview / render a job's HyperFrames project")
    ap.add_argument("action", choices=["build", "render"]); ap.add_argument("edl"); ap.add_argument("--out")
    a = ap.parse_args()
    proj, status = build(a.edl)
    print(f"{proj}: {status}")
    if a.action == "render":
        render(proj, a.out or os.path.join(os.path.dirname(os.path.abspath(a.edl)), "out", "render.mp4"))


if __name__ == "__main__":
    main()
