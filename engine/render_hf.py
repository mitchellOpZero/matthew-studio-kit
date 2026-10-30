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

KIT = qe.KIT
ENGINE = os.path.join(KIT, "engine")
STUDIO = os.path.join(KIT, ".work", "_studio")
BLOCKS = os.path.join(KIT, ".cache", "blocks")             # library blocks, installed once, reused offline
FLOOR = os.path.join(ENGINE, "hyperframes.json")            # the HyperFrames version this kit release was tested with
LIVE = os.path.join(KIT, ".cache", "deps", "hyperframes.json")   # a newer version that passed its test (engine/deps.py)
GSAP = os.path.join(ENGINE, "vendor", "gsap.min.js")        # bundled: no internet needed to preview or render
LOGO_POP = [0.0, 0.35, 0.62, 0.86, 1.04, 1.1, 1.05, 1.0]   # logo tile: per-frame scale, frame 0 hidden
CARD_POP = [0.0, 0.7, 0.9, 1.04, 1.1, 1.06, 1.02, 1.0]     # picture card and text card: per-frame scale
MARK = ".kit-generated"                                    # hash of the index.html the kit wrote


def hf_version():
    if os.environ.get("KIT_HF_VERSION"): return os.environ["KIT_HF_VERSION"]
    for p in (LIVE, FLOOR):
        try: return json.load(open(p))["version"]
        except Exception: pass
    return "0.8.214"


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
        home = os.path.expanduser("~")
        if not all(writable(os.path.join(home, d)) for d in (".npm", os.path.join(".cache", "hyperframes"), os.path.join(".local", "state", "hyperframes"))):
            chrome = sorted(glob.glob(os.path.join(home, ".cache", "hyperframes", "chrome", "**", "chrome-headless-shell"), recursive=True))
            chrome = [c for c in chrome if os.path.isfile(c) and os.access(c, os.X_OK)]
            if chrome and "HYPERFRAMES_BROWSER_PATH" not in e: e["HYPERFRAMES_BROWSER_PATH"] = chrome[-1]
            e["HOME"] = os.path.join(KIT, ".cache", "home"); os.makedirs(e["HOME"], exist_ok=True)
        _ENV = e
    return dict(_ENV)


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
    """His voice: the sample-exact dialogue layer, loudness-normalized and end-faded."""
    st = tl["style"]; L = st["loudness"]; total = tl["frames"] / tl["fps"]; ef = float(st.get("end_fade_s", 0.15))
    af = (f"loudnorm=I={L['I']}:TP={L['TP']}:LRA={L['LRA']},aresample=48000,apad,atrim=duration={total:.4f}"
          + (f",afade=t=out:st={total - ef:.4f}:d={ef:.4f}:curve=cub" if ef else ""))
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-nostdin", "-i", tl["dialogue"], "-af", af, "-c:a", "pcm_s16le", out], check=True)


# ---------------------------------------------------------------- library blocks
def own_block(style_name, name):
    """A block he had built: <style>/templates/<name>/<name>.html (his copy first), or graphics/<name>/<name>.html."""
    for d in (os.path.join(KIT, "my-styles", style_name, "templates", name), os.path.join(KIT, "styles", style_name, "templates", name),
              os.path.join(KIT, "graphics", name)):
        if os.path.exists(os.path.join(d, f"{name}.html")): return d
    return None


def install_block(name, proj, style_name=""):
    """Copy a block into the project: one of his own (own_block), else a HyperFrames library block (from the kit's cache;
    the first use downloads it). Returns the block's {id, w, h, dur} read from its own file."""
    own = own_block(style_name, name)
    if own:
        os.makedirs(os.path.join(proj, "compositions"), exist_ok=True)
        shutil.copy2(os.path.join(own, f"{name}.html"), os.path.join(proj, "compositions", f"{name}.html"))
        if os.path.isdir(os.path.join(own, "assets")):
            shutil.copytree(os.path.join(own, "assets"), os.path.join(proj, "assets"), dirs_exist_ok=True)
        src = open(os.path.join(own, f"{name}.html")).read()
        get = lambda a, d: (re.search(rf'{a}="([^"]+)"', src) or [None, d])[1]
        return {"id": get("data-composition-id", name), "w": int(float(get("data-width", 1080))),
                "h": int(float(get("data-height", 1920))), "dur": float(get("data-duration", 9999))}
    cache = os.path.join(BLOCKS, name)
    if not os.path.exists(os.path.join(cache, "compositions", f"{name}.html")):
        tmp = cache + ".tmp"; shutil.rmtree(tmp, ignore_errors=True); os.makedirs(tmp)
        json.dump({"paths": {"blocks": "compositions", "components": "compositions/components", "assets": "assets"}},
                  open(os.path.join(tmp, "hyperframes.json"), "w"))
        r = subprocess.run(hf() + ["add", name, "--json", "--no-clipboard"], cwd=tmp, env=env(), capture_output=True, text=True, timeout=300)
        if r.returncode or not os.path.exists(os.path.join(tmp, "compositions", f"{name}.html")):
            qe.die(f"couldn't get library block {name!r} (is the name right? `bin/kit blocks search <words>`): {(r.stdout + r.stderr)[-400:]}")
        for f in ("hyperframes.json", "hyperframes.lock.json", "TEMPLATE.md"):
            if os.path.exists(os.path.join(tmp, f)): os.remove(os.path.join(tmp, f))
        shutil.rmtree(cache, ignore_errors=True); os.replace(tmp, cache)
    for f in glob.glob(os.path.join(cache, "**", "*"), recursive=True):
        if os.path.isfile(f):
            dst = os.path.join(proj, os.path.relpath(f, cache))
            if not os.path.exists(dst): os.makedirs(os.path.dirname(dst), exist_ok=True); shutil.copy2(f, dst)
    src = open(os.path.join(cache, "compositions", f"{name}.html")).read()
    get = lambda a, d: (re.search(rf'{a}="([^"]+)"', src) or [None, d])[1]
    return {"id": get("data-composition-id", name), "w": int(float(get("data-width", 1080))),
            "h": int(float(get("data-height", 1920))), "dur": float(get("data-duration", 9999))}


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
def write_html(tl, blocks_meta):
    fps, W, H = tl["fps"], tl["width"], tl["height"]
    st = tl["style"]; T = tl["frames"] / fps
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

    # camera: muted pieces of his clip, each cropped to its output-shaped window (punch-ins are tighter windows)
    for i, p in enumerate(tl["camera"]):
        n = p["frames"] + (1 if i < len(tl["camera"]) - 1 else 0)   # one frame under the next piece: never a gap
        body.append(framed(f"cam{i}", p["src"], p["start"], n, p["src_frame"], p["crop"], tl["src_w"], tl["src_h"], 1))
        if p.get("drift"):
            x, y, w, h = p["crop"]; k = W / w
            js.append(f'tl.fromTo("#cam{i}", {{scale: 1}}, {{scale: {1 + p["drift"]}, duration: {p["frames"] / fps:.4f}, ease: "none", '
                      f'transformOrigin: "{x * k + W / 2:.1f}px {y * k + H / 2:.1f}px"}}, {jt(p["start"])});')

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
    design = caption_design(tl)
    # during a split screen (b-roll top, his face bottom) captions sit on the seam between the two, off his face
    seams = [(b["start"], b["start"] + b["frames"]) for b in tl["broll"] if b.get("layout") == "split"]
    for i, c in enumerate(tl["captions"]):
        t0 = c.get("t0", c["start"])
        lines = []
        for li, line in enumerate(c["lines"]):
            ws = []
            for j, w in enumerate(line):
                wid = f"w{i}_{li}_{j}"
                col = hot if (w["hot"] and not st.get("kw_sync_pop") and not design) else white
                ws.append(f'<span id="{wid}" class="w{" kw" if w["hot"] else ""}" data-at="{jt(w["at"])}" '
                          f'style="color:{col}">{html.escape(w["text"])}</span>')
                if w["hot"] and st.get("kw_sync_pop") and not design:
                    js.append(f'tl.fromTo("#{wid}", {{color: "{white}"}}, {{color: "{hot}", duration: 0.07, ease: "none"}}, {jt(w["at"])});')
            lines.append("<div>" + " ".join(ws) + "</div>")
        px = c["size"] * st.get("font_css_scale", 0.82)
        seam = f' style="top:{H / 2:.0f}px"' if any(c["start"] < b and c["end"] > a for a, b in seams) else ""
        caps_html.append(f'<div id="cap{i}" class="clip" {span(c["start"], max(1, c["end"] - c["start"]))} '
                    f'data-track-index="2"><div class="cap"{seam}><div id="capin{i}" class="capin" data-t0="{jt(t0)}" style="font-size:{px:.2f}px;'
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

    # library blocks: HyperFrames sub-compositions, mounted full frame or in the plan's box [x, y, w, h]
    for i, b in enumerate(tl.get("blocks") or []):
        m = blocks_meta[b["name"]]
        n = min(b["frames"], int(m["dur"] * fps))
        x, y, w, h = b.get("box") or [0, 0, W, H]
        k = min(w / m["w"], h / m["h"])   # the block keeps its own canvas, scaled to fit the box and centred in it
        x, y = x + (w - m["w"] * k) / 2, y + (h - m["h"] * k) / 2
        vv = f" data-variable-values='{html.escape(json.dumps(b['vars']), quote=True)}'" if b.get("vars") else ""
        body.append(f'<div id="blk{i}" data-composition-id="{m["id"]}" data-composition-src="compositions/{b["name"]}.html" '
                    f'{span(b["start"], n)} data-track-index="{7 + i}" data-width="{m["w"]}" data-height="{m["h"]}"{vv} '
                    f'style="position:absolute;left:{x:.1f}px;top:{y:.1f}px;width:{m["w"]}px;height:{m["h"]}px;'
                    f'transform-origin:0 0;transform:scale({k:.5f});overflow:hidden;border-radius:{round(28 / k) if k < 1 else 0}px"></div>')

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
      <div id="frame" data-layout-allow-overflow style="position:absolute;inset:0;overflow:hidden">
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
    blocks_meta = {b["name"]: install_block(b["name"], proj, tl.get("style_name") or "") for b in tl.get("blocks") or []}
    voice_track(tl, os.path.join(a, "voice.wav"))
    idx = os.path.join(proj, "index.html")
    open(idx, "w").write(write_html(tl, blocks_meta))
    open(os.path.join(proj, MARK), "w").write(_sha(idx))
    json.dump(tl, open(os.path.join(proj, "timeline.json"), "w"), indent=1)
    json.dump({"paths": {"blocks": "compositions", "components": "compositions/components", "assets": "assets"}},
              open(os.path.join(proj, "hyperframes.json"), "w"), indent=2)
    json.dump({"id": job, "name": job}, open(os.path.join(proj, "meta.json"), "w"), indent=2)
    return proj, "built from the plan; " + tl.get("caption_place", "")


def check(proj):
    """HyperFrames' check, except that a caption word's colour against the footage behind it is a note, not a failure.
    Its contrast test ignores the caption outline and depends on what happens to be behind the word in the sampled
    frames, so it would block his approved keyword colour on one clip and pass it on the next. The colour is the style's
    call (skills/style: look at the still)."""
    r = subprocess.run(hf() + ["check", "--json", proj], capture_output=True, text=True, env=env())
    try:
        d = json.loads(r.stdout)
    except ValueError:
        return r.returncode, (r.stdout + r.stderr)
    errors, notes, total = [], [], 0
    for part, res in d.items():
        if not isinstance(res, dict) or not isinstance(res.get("findings"), list):
            continue
        total += res.get("errorCount") or 0
        for f in res["findings"]:
            sel = str(f.get("selector", ""))
            line = f"{part}: {f.get('code')} {sel} t={f.get('time', '')}: {f.get('message', '')} {f.get('fixHint', '')}".strip()
            if f.get("severity") != "error":
                continue
            if part == "contrast" and sel.startswith("#w"):
                notes.append(f"note, caption colour: \"{f.get('text', '')}\" {f.get('fg')} on {f.get('bg')} is {f.get('ratio')}:1 "
                             f"at {f.get('time')}s (outline not counted); a brighter option is {f.get('suggestedColor')}")
            else:
                errors.append(line)
    failed = bool(errors) or total > len(notes) or (not d.get("ok") and not notes)
    log = "\n".join(errors + notes) or "check passed"
    if failed and not errors:
        log = (r.stdout + r.stderr)[-3000:]
    return (1 if failed else 0), log


def running(proj):
    """The Studio URL of this project's preview server if one is already up, else None."""
    r = subprocess.run(hf() + ["preview", "--status", "--json"], cwd=proj, env=env(), capture_output=True, text=True, timeout=60)
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
    r = subprocess.run(hf() + ["preview", "--background", "--no-open", "--port", str(port)], cwd=proj, env=env(),
                       capture_output=True, text=True, timeout=180)
    for _ in range(60):   # only HyperFrames' own word that THIS project is up counts (a busy port can answer for another)
        url = running(proj)
        if url: return url, True
        time.sleep(1)
    qe.die(f"Studio didn't start for {os.path.basename(proj)}: {(r.stdout + r.stderr)[-600:]}")


def stop(proj):
    subprocess.run(hf() + ["preview", "--stop"], cwd=proj, env=env(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def render(proj, out_mp4):
    """Render the project as it stands (hand edits included), then trim loudness onto the style's target."""
    t0 = time.time()
    code, log = check(proj)
    if code: qe.die("hyperframes check failed:\n" + log[-3000:])
    os.makedirs(os.path.dirname(out_mp4), exist_ok=True)
    t1 = time.time()
    r = subprocess.run(hf() + ["render", proj, "--output", out_mp4], env=env(), capture_output=True, text=True)
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


def snapshot(proj, at):
    """Still frames of the project (no render): [png paths]."""
    r = subprocess.run(hf() + ["snapshot", "--at", ",".join(f"{x:.2f}" for x in at)], cwd=proj, env=env(), capture_output=True, text=True, timeout=300)
    return list(dict.fromkeys(re.findall(r"(/\S+/snapshots/\S+/frame-\d+\S*?\.png)", r.stdout + r.stderr)))


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
