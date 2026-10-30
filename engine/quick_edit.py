#!/usr/bin/env python3
"""Quick-edit (QE) lane, fix 1 (Oct 26 2026, Mitchell approved 3:20 PM ET): one short client test edit = one EDL = one
ffmpeg pass. No plugin code, no heavy ASR/OCR. See templates/quick_edit/README.md.

  quick_edit.py render <edl.json> [--out DIR] [--full] [--check]   render ONLY the Short the EDL describes
  quick_edit.py check  <out_dir | qe_report.json>                  cheap fixed checks (ffprobe duration/res, audio, loudness, sheet)
  quick_edit.py transcribe <clip> [--model small.en]               opt-in, once per clip (cached by sha256)

Idempotent: render overwrites its own outputs in --out only; transcribe reuses the cache; new refuses an existing folder.
Plugin build: any clip path is allowed as the source; B-roll, SFX and overlays must come from the kit (assets/, graphics/,
library/) or the job folder. Originally: the source had to be under /workspace/clients/<project>/raw/; every media input is checked against Mitchell's footage
list (bin/mitchell_footage_sha.json) and refused if it matches; B-roll/SFX must come from the project's raw/ or
approved_assets/, or a path listed in the EDL's approved_assets with stock_broll_allowed true.
"""
import math, argparse, hashlib, json, os, re, shutil, subprocess, sys, time

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # plugin: the kit folder (engine/..)
ROOT = os.environ.get("WORKERS_ROOT", os.path.join(KIT, ".work"))
CLIENTS = os.environ.get("QE_CLIENTS")          # box mode only; unset in the plugin (any clip path is allowed)
FONTS = os.path.join(KIT, "assets", "fonts")
CACHE = os.environ.get("KIT_WORDS_CACHE") or os.path.join(KIT, ".cache", "words")
STYLES = os.path.join(KIT, "styles")
MITCHELL_SHA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mitchell_footage_sha.json")
MITCHELL_NAME_RX = re.compile(r"mitchell|mitch_|_mitch|/mm_|selfie_mm|my_recording", re.I)

STYLE_DEFAULTS = {   # Matthew's "Clean" preset (MS-BUILD-001 plugin styles/cold_approach.json), as plain knobs
    "font": "Montserrat ExtraBold", "font_size_frac": 0.093, "color": "#FFFFFF", "highlight_color": "#DC143C",
    "stroke_color": "#000000", "stroke": 7, "shadow": 2, "center_y_frac": 0.64, "uppercase": False,
    "keyword_scale": 1.08, "pop_scale": 1.06, "pop_ms": 150, "max_words": 3, "max_chars": 18, "gap_break_s": 0.35,
    "punch": {"every_s": 2.8, "zoom_wide": 1.0, "zoom_tight": 1.17, "min_piece_s": 0.6},
    "graphic": {"size_frac": 0.062, "y_frac": 0.22, "box_color": "#DC143C", "text_color": "#FFFFFF"},
    "loudness": {"I": -14, "TP": -1.5, "LRA": 11},
}

def die(msg): sys.exit(f"quick_edit: {msg}")

def load_style(name):
    """styles/<name>/style.json (the look). Empty when no style is named."""
    if not name: return {}
    mine = os.path.join(KIT, "my-styles", name, "style.json")   # his saved styles win over the built-in ones
    p = mine if os.path.isfile(mine) else os.path.join(STYLES, name, "style.json")
    if not os.path.isfile(p): die(f"style {name!r} not found (looked for {p})")
    d = json.load(open(p)); d.pop("_about", None); d["_style_dir"] = os.path.dirname(p); return d

def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest()

def mitchell_shas():
    try: d = json.load(open(MITCHELL_SHA))
    except Exception: return set()
    s = d.get("sha256") if isinstance(d, dict) else d
    return set(s if isinstance(s, (list, dict)) else [])

def guard_media(p, project, kind, edl, shas):
    rp = os.path.realpath(p)
    if not os.path.isfile(rp): die(f"{kind} {p} does not exist")
    if sha256(rp) in shas: die(f"{kind} {p} is on the blocked footage list (sha256 match): refused")
    if kind == "source":
        return rp
    # B-roll, SFX and overlays: from the kit (assets/, graphics/, library/), the job folder, or an approved path
    roots = [os.path.realpath(os.path.join(KIT, d)) + "/" for d in ("assets", "graphics", "library", ".work")]
    roots += [os.path.realpath(x).rstrip("/") + "/" for x in edl.get("approved_assets") or []]
    if edl.get("_dir"): roots.append(os.path.realpath(edl["_dir"]) + "/")
    if any(rp.startswith(r) for r in roots): return rp
    die(f"{kind} {p} is not a kit asset (put it under assets/, graphics/ or library/, or list its folder in approved_assets)")

def ffprobe(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", p], capture_output=True, text=True)
    if r.returncode: die(f"ffprobe failed on {p}: {r.stderr[-300:]}")
    return json.loads(r.stdout)

# ------------------------------------------------------------------ timeline
def load_words(path):
    if not path: return []
    d = json.load(open(path))
    ws = d.get("words") if isinstance(d, dict) else d
    out = []
    for w in ws or []:
        t = (w.get("w") or w.get("word") or w.get("text") or "").strip()
        if t and w.get("start") is not None and w.get("end") is not None: out.append({"w": t, "s": float(w["start"]), "e": float(w["end"])})
    return out

def build_pieces(edl, words, st, fps=30):
    """Cuts (source seconds) -> pieces [(src_in, src_out, zoom)]. Snap punch-ins: zoom alternates at every cut, and a cut
    longer than punch.every_s is split at the word gap nearest each every_s mark (never mid-word)."""
    pu = st["punch"]; every = float(pu.get("every_s") or 0); minp = float(pu.get("min_piece_s", 0.6))
    zooms = (float(pu.get("zoom_wide", 1.0)), float(pu.get("zoom_tight", 1.17)))
    pieces, k = [], 0
    for c in edl["cuts"]:
        a, b = float(c["in"]), float(c["out"])
        if b - a < 0.05: die(f"cut {c} is too short")
        marks = [a]
        if pu.get("even") and not c.get("no_punch"):
            # even split: the fewest pieces that keep each <= max_s, each split on the word boundary nearest its even mark,
            # so a cut never leaves a short leftover piece (QE-MS-001 review: changes should mostly be 2-3 s apart)
            mx = float(pu.get("max_s", 3.0)); n = max(1, math.ceil((b - a) / mx - 1e-9))
            gaps = [(w1["e"] + w2["s"]) / 2 for w1, w2 in zip(words, words[1:]) if a < w1["e"] and w2["s"] < b and w2["s"] - w1["e"] >= -0.005]
            for j in range(1, n):
                t = a + j * (b - a) / n
                near = [g for g in gaps if abs(g - t) <= 0.6 and g - marks[-1] >= minp and b - g >= minp]
                if near: marks.append(min(near, key=lambda g: abs(g - t)))
                elif not any(w["s"] < t < w["e"] for w in words): marks.append(t)
        elif every and not c.get("no_punch"):
            gaps = [(w1["e"] + w2["s"]) / 2 for w1, w2 in zip(words, words[1:]) if a < w1["e"] and w2["s"] < b and w2["s"] - w1["e"] >= -0.005]   # any word boundary (snapped words touch)
            t = a + every
            while b - t >= minp:
                near = [g for g in gaps if abs(g - t) <= 0.8 and g - marks[-1] >= minp and b - g >= minp]
                if near: marks.append(min(near, key=lambda g: abs(g - t)))
                elif t - marks[-1] >= minp and not any(w["s"] < t < w["e"] for w in words): marks.append(t)
                t = marks[-1] + every if marks[-1] >= t - 0.8 else t + every
        marks.append(b)
        # whole-frame pieces: concat pads each piece's audio to its (frame-rounded) video length, so a non-integer-frame piece
        # inserts up to 1 frame of silence and drifts later audio; snapping every mark onto a.. a+k/fps keeps audio contiguous
        marks = sorted(set(round(a + round((m - a) * fps) / fps, 4) for m in marks))
        for i, (x, y) in enumerate(zip(marks, marks[1:])):
            z = float(c["zoom"]) if c.get("zoom") and len(marks) == 2 else zooms[k % 2]
            # fade flags: only at real cuts; a punch split inside a cut is sample-continuous, so no fade (no dip/click)
            pieces.append((round(x, 3), round(y, 3), z, i == 0, i == len(marks) - 2)); k += 1
    return pieces

def map_words(words, pieces):
    out, off = [], 0.0
    for a, b, *_ in pieces:
        for w in words:
            m = (w["s"] + w["e"]) / 2
            if a <= m < b: out.append({"w": w["w"], "ss": w["s"], "s": off + max(0.0, w["s"] - a), "e": off + min(b - a, w["e"] - a), "piece_end": off + b - a})
        off += b - a
    return out, off

# ------------------------------------------------------------------ ASS captions + graphics
def ass_color(hexc, alpha=0):
    h = hexc.lstrip("#"); return f"&H{alpha:02X}{h[4:6]}{h[2:4]}{h[0:2]}".upper()

def ass_time(t):
    t = max(0.0, t); h = int(t // 3600); m = int(t % 3600 // 60); s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"

def norm(w): return re.sub(r"[^a-z0-9']", "", w.lower())

def _lines(chunk, st):
    """Split a caption into its stacked lines (style: lines, words_per_line). One line unless lines > 1."""
    n = int(st.get("lines", 1) or 1); per = int(st.get("words_per_line") or st["max_words"])
    if n <= 1: return [chunk]
    return [chunk[i:i + per] for i in range(0, len(chunk), per)]


def _fit_one_line(chunk, st, fs, W):
    """Scale factor so the caption's widest line (at its keyword pop size) fits W minus the 6% margins."""
    try:
        from PIL import ImageFont
        font = ImageFont.truetype(_font_path(st), fs)
    except Exception:
        return 1.0
    wide = 0.0
    for line in _lines(chunk, st):
        text = " ".join((w["w"].upper() if st["uppercase"] else w["w"]) for w in line)
        wide = max(wide, font.getlength(text) * (1 + int(st.get("kw_pop_pct", 14)) / 100.0))
    room = W - 2 * round(W * .06)
    return min(1.0, room / wide) if wide > 0 else 1.0


def _font_path(st):
    """A style may ship its own font (styles/<name>/fonts/); else the kit's assets/fonts/."""
    f = st.get("font_file", "Montserrat-ExtraBold.ttf")
    for d in [os.path.join(st.get("_style_dir", ""), "fonts"), FONTS]:
        if d and os.path.isfile(os.path.join(d, f)): return os.path.join(d, f)
    return os.path.join(FONTS, f)


def _cap_style(st, fs, sc, W):
    """The Cap style line. style.box = {color, opacity 0-1, pad} puts a solid box behind each caption."""
    box = st.get("box") or {}
    if box.get("enabled", bool(box)):
        a = 255 - int(round(255 * float(box.get("opacity", 1.0))))
        return (f"Style: Cap,{st['font']},{fs},{ass_color(st['color'])},{ass_color(st['color'])},{ass_color(box.get('color', '#000000'), a)},"
                f"{ass_color(box.get('color', '#000000'), a)},0,0,0,0,100,100,0,0,3,{float(box.get('pad', 14)) * sc:.1f},0,5,"
                f"{round(W * .06)},{round(W * .06)},0,1\n")
    return (f"Style: Cap,{st['font']},{fs},{ass_color(st['color'])},{ass_color(st['color'])},{ass_color(st['stroke_color'])},&H80000000,"
            f"0,0,0,0,100,100,0,0,1,{st['stroke'] * sc:.1f},{st['shadow'] * sc:.1f},5,{round(W * .06)},{round(W * .06)},0,1\n")


def highlight_set(words, edl, st):
    mode = st.get("highlight_mode", "keywords")   # keywords | every_word | none
    return {norm(k) for k in edl.get("keywords") or []} if mode == "keywords" else (
        {norm(w["w"]) for w in words} if mode == "every_word" else set())


def caption_chunks(words, total, edl, st):
    """Output words -> caption chunks [(words, start, end)], after caption_breaks, min on-screen time and caption_hide.
    Shared by the ASS writer and the timeline, so both show exactly the same captions."""
    chunks, cur = [], []
    # caption_breaks: source start times of words that must open a new caption chunk; caption_text: {source start: shown text}
    brk = [float(t) for t in edl.get("caption_breaks") or []]
    ctext = {round(float(k), 2): v for k, v in (edl.get("caption_text") or {}).items()}
    for w in words:
        if round(w.get("ss", -1), 2) in ctext: w = dict(w, w=ctext[round(w["ss"], 2)])
        if cur and any(abs(w.get("ss", -9) - t) <= 0.03 for t in brk): chunks.append(cur); cur = []
        nl = max(1, int(st.get("lines", 1) or 1)); per = int(st.get("words_per_line") or st["max_words"])
        cap_words = per * nl if nl > 1 else st["max_words"]
        if cur and (len(cur) >= cap_words or sum(len(x["w"]) + 1 for x in cur) + len(w["w"]) > st["max_chars"] * nl
                    or w["s"] - cur[-1]["e"] > st["gap_break_s"] or cur[-1]["piece_end"] <= w["s"] + 1e-6 and w["s"] - cur[-1]["e"] > 0.12):
            chunks.append(cur); cur = []
        cur.append(w)
    if cur: chunks.append(cur)
    # minimum on-screen time (QE-MS-001c): a chunk shown < min_chunk_s joins the next chunk (else the previous one)
    mn = float(st.get("min_chunk_s", 0.3)); i = 0
    while i < len(chunks):
        nxt = chunks[i + 1][0]["s"] if i + 1 < len(chunks) else total
        if len(chunks) > 1 and min(nxt, chunks[i][-1]["e"] + 0.6) - chunks[i][0]["s"] < mn - 1e-6:
            j = i + 1 if i + 1 < len(chunks) else i - 1
            lo, hi_ = min(i, j), max(i, j); chunks[lo:hi_ + 1] = [chunks[lo] + chunks[hi_]]; i = max(0, lo - 1); continue
        i += 1
    out = []
    for i, c in enumerate(chunks):
        s = c[0]["s"]; e = min(chunks[i + 1][0]["s"] if i + 1 < len(chunks) else c[-1]["e"] + 0.3, c[-1]["e"] + 0.6, total)
        # QE-MS-001g: caption_hide [[a, b], ...] output windows where a graphic carries the words: trim/drop the caption there
        for ha, hb in edl.get("caption_hide") or []:
            if s >= ha and e <= hb: s = e
            elif ha <= s < hb: s = hb
            elif ha < e <= hb: e = ha
        if e - s < 0.15: continue  # drop slivers left by caption_hide (min 0.15 s)
        out.append((c, s, e))
    return out, len(chunks)


def write_ass(path, words, total, edl, st, W, H):
    kws = highlight_set(words, edl, st)
    fs = round(st["font_size_frac"] * H); sc = H / 1920.0
    g = st["graphic"]; gfs = round(g["size_frac"] * H)
    hdr = (f"[Script Info]\nScriptType: v4.00+\nPlayResX: {W}\nPlayResY: {H}\nWrapStyle: {2 if st.get("one_line") or int(st.get("lines", 1) or 1) > 1 else 0}\nScaledBorderAndShadow: yes\n\n"
           "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
           "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
           + _cap_style(st, fs, sc, W) +
           f"Style: Gfx,{st['font']},{gfs},{ass_color(g['text_color'])},{ass_color(g['text_color'])},{ass_color(g['box_color'])},"
           f"{ass_color(g['box_color'])},0,0,0,0,100,100,0,0,3,{round(18 * sc)},0,5,{round(W * .08)},{round(W * .08)},0,1\n\n"
           "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    ev = []
    shown, nchunks = caption_chunks(words, total, edl, st)
    chunks = [c for c, _, _ in shown]
    x, y = W // 2, round(st["center_y_frac"] * H)
    hi = ass_color(st["highlight_color"]); ks = round(st["keyword_scale"] * 100); ps = round(st["pop_scale"] * 100)
    for c, s, e in shown:
        # one_line (Mac port): shrink this caption's font size so it fits on one line; \\r below keeps that size
        fsz = f"\\fs{round(fs * _fit_one_line(c, st, fs, W))}" if st.get("one_line") else ""
        parts = []
        for w in c:
            t = w["w"].upper() if st["uppercase"] else w["w"]
            t = t.replace("{", "(").replace("}", ")")
            if norm(w["w"]) in kws and st.get("kw_sync_pop"):
                # QE-MS-001f: the keyword turns crimson and pops on the frame it is spoken (white until then)
                o = max(0, int((w["s"] - s) * 1000)); kp = ks + int(st.get("kw_pop_pct", 14))
                parts.append(f"{{\\fscx100\\fscy100\\t({o},{o + 70},\\c{hi}\\fscx{kp}\\fscy{kp})\\t({o + 70},{o + 150},\\fscx{ks}\\fscy{ks})}}{t}{{\\r{fsz}}}")
            elif st.get("word_pop") and norm(w["w"]) not in kws and int((w["s"] - s) * 1000) > 0:
                # QE-MS-001h: every non-keyword word pops 100 -> word_pop % -> 100 on the frame it is spoken
                o = int((w["s"] - s) * 1000); wp = int(st["word_pop"])
                parts.append(f"{{\\t({o},{o + 60},\\fscx{wp}\\fscy{wp})\\t({o + 60},{o + 140},\\fscx100\\fscy100)}}{t}{{\\r{fsz}}}")
            else:
                parts.append(f"{{\\c{hi}\\fscx{ks}\\fscy{ks}}}{t}{{\\r{fsz}}}" if norm(w["w"]) in kws else t)
        per = int(st.get("words_per_line") or st["max_words"]); stacked = int(st.get("lines", 1) or 1) > 1
        body = "".join(("" if k == 0 else ("\\N" if stacked and k % per == 0 else " ")) + p for k, p in enumerate(parts))
        txt = f"{{\\pos({x},{y}){fsz}\\fscx{ps}\\fscy{ps}\\t(0,{st['pop_ms']},\\fscx100\\fscy100)}}" + body
        ev.append(f"Dialogue: {int(st.get('caption_layer', 0))},{ass_time(s)},{ass_time(e)},Cap,,0,0,0,,{txt}")
    for gr in edl.get("graphics") or []:
        a = float(gr["at"]); b = a + float(gr.get("dur", 1.2))
        # pop 35 -> 110 -> 100 %, box border scaled with it, transparent on its first frame: scale 0 left the opaque box's
        # unscaled border visible as a speck before the pop (QE-MS-001 review)
        # QE-MS-001c: the 40 ms alpha ramp left one faint 35 % ghost frame; now alpha is 0 until 34 ms (all of the first frame),
        # then the box appears fully opaque at 70 % and pops 110 -> 100 %
        bd = 18 * sc
        ev.append(f"Dialogue: 1,{ass_time(a)},{ass_time(min(b, total))},Gfx,,0,0,0,,{{\\pos({x},{round(g['y_frac'] * H)})\\fad(0,120)"
                  f"\\alpha&HFF&\\fscx70\\fscy70\\bord{bd * .7:.1f}\\t(34,35,\\alpha&H00&)\\t(35,120,\\fscx110\\fscy110\\bord{bd * 1.1:.1f})"
                  f"\\t(120,210,\\fscx100\\fscy100\\bord{bd:.1f})}}{gr['text']}")
    # QE-MS-001f: raw kinetic motion-graphic events (already-built ASS override text), each {start, end, layer, text[, style]}
    for rw in edl.get("ass_raw") or []:
        ev.append(f"Dialogue: {int(rw.get('layer', 1))},{ass_time(float(rw['start']))},{ass_time(min(float(rw['end']), total))},{rw.get('style', 'Cap')},,0,0,0,,{rw['text']}")
    tpl = st.get("caption_template")
    if tpl:
        # styles/<name>/<caption_template>.py defines events(chunks, st, W, H, hi, kws) -> (extra_style_lines, dialogue_lines)
        import importlib.util
        tp = tpl if os.path.isabs(tpl) else os.path.join(st.get("_style_dir", ""), tpl)
        spec = importlib.util.spec_from_file_location("caption_template", tp); mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        styles, cap_ev = mod.events(chunks, st, W, H, hi, kws)
        hdr = hdr.replace("\n\n[Events]", "\n" + "".join(l.rstrip("\n") + "\n" for l in styles) + "\n[Events]", 1)
        ev = [e for e in ev if ",Cap,," not in e] + list(cap_ev)
    open(path, "w").write(hdr + "\n".join(ev) + "\n")
    return nchunks

# ------------------------------------------------------------------ render
def measure_loud(p):
    e = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", p, "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True).stderr
    return float(re.findall(r"I:\s+(-?[\d.]+) LUFS", e)[-1]), float(re.findall(r"Peak:\s+(-?[\d.]+) dBFS", e)[-1])

def loud_trim(mp4, target, tp):
    """Single-pass loudnorm lands within ~1 LU; trim the integrated level onto the target (audio-only re-encode, video copied).
    The gain is solved on a lossless copy first (the true-peak limiter can eat part of it), then applied in ONE encode.
    alimiter runs with latency=1 so it adds no delay (it used to shift the audio late by its 2 ms attack)."""
    I, peak = measure_loud(mp4)
    if abs(target - I) < 0.3: return 0.0
    lim = 10 ** (tp / 20); wav = mp4 + ".lt.wav"; tst = mp4 + ".lt2.wav"
    af = lambda g: f"volume={g:.2f}dB,alimiter=limit={lim:.4f}:attack=2:release=50:level=disabled:latency=1"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-nostdin", "-i", mp4, "-vn", "-c:a", "pcm_f32le", wav], check=True)
    g = target - I
    for _ in range(4):
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-nostdin", "-i", wav, "-af", af(g), "-c:a", "pcm_f32le", tst], check=True)
        I2, _ = measure_loud(tst)
        if abs(target - I2) < 0.15: break
        g += target - I2
    for f in (wav, tst): os.path.exists(f) and os.remove(f)
    tmp = mp4 + ".trim.mp4"
    r = subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-nostdin", "-i", mp4, "-c:v", "copy",
                        "-af", af(g), "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-movflags", "+faststart", tmp], capture_output=True, text=True)
    if r.returncode: die(f"loudness trim failed: {r.stderr[-800:]}")
    os.replace(tmp, mp4); return round(g, 2)

def crop_916(W, H, z, cx=0.5, cy=0.5):
    # cx/cy: where the 9:16 window sits in the spare width/height (0 = left/top edge, 1 = right/bottom); 0.5 = centred.
    # A punch-in with cy < 0.5 keeps more headroom (the window rides up with the head instead of cutting the hair).
    return (f"crop='trunc(min(iw,ih*9/16)/{z}/2)*2':'trunc(min(ih,iw*16/9)/{z}/2)*2':'(iw-ow)*{float(cx):.3f}':'(ih-oh)*{float(cy):.3f}',"
            f"scale={W}:{H}:flags=lanczos,setsar=1")

def resolve_style(edl):
    """STYLE_DEFAULTS, then the named style, then any per-edit overrides in edl.style."""
    st = json.loads(json.dumps(STYLE_DEFAULTS))
    for k, v in list(load_style(edl.get("style_name")).items()) + list((edl.get("style") or {}).items()):
        if isinstance(v, dict) and isinstance(st.get(k), dict): st[k].update(v)
        else: st[k] = v
    return st

def cmd_render(a):
    t0 = time.time()
    edl = json.load(open(a.edl)); edl_dir = os.path.dirname(os.path.abspath(a.edl))
    rel = lambda p: p if not p or os.path.isabs(p) else os.path.join(edl_dir, p)
    st = resolve_style(edl)
    edl["_dir"] = edl_dir
    project = edl.get("project") or "plugin"
    shas = mitchell_shas()
    src = guard_media(rel(edl["source"]), project, "source", edl, shas)
    broll = [dict(b, file=guard_media(rel(b["file"]), project, "broll", edl, shas)) for b in edl.get("broll") or []]
    sfx = [dict(s, file=guard_media(rel(s["file"]), project, "sfx", edl, shas)) for s in edl.get("sfx") or []]
    o = edl.get("output") or {}
    W, H = (int(o.get("w", 1080)), int(o.get("h", 1920))) if a.full else (int(o.get("proxy_w", 540)), int(o.get("proxy_h", 960)))
    fps = int(o.get("fps", 30))
    out = os.path.abspath(a.out or os.path.join(edl_dir, "out")); os.makedirs(out, exist_ok=True)
    name = edl.get("name") or os.path.splitext(os.path.basename(a.edl))[0]
    mp4 = os.path.join(out, f"{name}{'' if a.full else '_proxy'}.mp4")
    words = load_words(rel(edl.get("words")))
    pieces = build_pieces(edl, words, st, fps)
    owords, total = map_words(words, pieces)
    ass = os.path.join(out, f"{name}.ass")
    nchunks = write_ass(ass, owords, total, edl, st, W, H)
    if not any(s["codec_type"] == "audio" for s in ffprobe(src)["streams"]): die(f"source {src} has no audio")

    dthr = str(int(os.environ.get("QE_DEC_THREADS", 2)))
    # audio override: {"file": WAV of a processed stretch of the take (job folder only), "offset": source time of its first
    # sample, "pre": ffmpeg filters before the level is set}. Video still comes from the guarded raw source.
    aud = edl.get("audio") or {}
    afile = rel(aud["file"]) if aud.get("file") else None
    if afile:
        jd = os.path.realpath(edl_dir)
        if not os.path.realpath(afile).startswith(jd + "/"): die(f"audio.file {afile} must live in the job folder {jd}")
        aoff = float(aud.get("offset", 0.0))
    cx_a = float(st.get("crop_x", 0.5))
    args, fc = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-nostdin"], []
    for i, (x, y, z, fin, fout) in enumerate(pieces):
        d = y - x
        args += ["-threads", dthr, "-ss", f"{x:.3f}", "-t", f"{d:.3f}", "-i", src]   # per-input decoder threads: default = all cores x 15 inputs ran the box out of memory
        # QE-MS-001h: slow drift zoom (style.drift {min_s, amount}) on holds >= min_s: scale grows 1 -> 1+amount over the piece
        dr = st.get("drift") or {}
        dz = (f",scale=w='trunc({W}*(1+{float(dr['amount'])}*t/{d:.3f})/2)*2':h=-2:eval=frame:flags=lanczos,crop={W}:{H}"
              if dr and d >= float(dr.get("min_s", 1.9)) else "")
        fc.append(f"[{i}:v:0]fps={fps},trim=duration={d:.3f},setpts=PTS-STARTPTS,{crop_916(W, H, z, cx_a, float(st['punch'].get('anchor_y', 0.5)) if z > 1.0 else 0.5)}{dz},format=yuv420p,setpts=PTS-STARTPTS[v{i}]")
        fade = min(0.008, d / 4)
        fades = (f",afade=t=in:d={fade:.3f}" if fin else "") + (f",afade=t=out:st={d - fade:.3f}:d={fade:.3f}" if fout else "")
    n = len(pieces)
    # audio: one segment per cut (punch splits are sample-continuous), each extended by h on the joined sides and mixed at its
    # output position with linear fades, so every cut is a 2h equal-gain crossfade (QE-MS-001c: 10-15 ms, no clicks)
    xf = float(st.get("xfade_ms", 12)) / 1000.0; h = xf / 2
    segs, o = [], 0.0
    for x, y, z, fin, fout in pieces:
        if fin: segs.append([x, y, o])
        else: segs[-1][1] = y
        o += y - x
    asrc, aofs = (afile, aoff) if afile else (src, 0.0)
    ai0 = len(pieces)
    for j, (x, y, oo) in enumerate(segs):
        pre = h if j > 0 else 0.0; post = h if j < len(segs) - 1 else 0.0
        if x - pre - aofs < -1e-6: die(f"audio source starts at {aofs} s, after segment start {x - pre}")
        args += ["-ss", f"{x - pre - aofs:.4f}", "-t", f"{y - x + pre + post:.4f}", "-i", asrc]
        L_ = y - x + pre + post
        fd = (f",afade=t=in:d={2 * pre:.4f}" if pre else "") + (f",afade=t=out:st={L_ - 2 * post:.4f}:d={2 * post:.4f}" if post else "")
        dl = int(round((oo - pre) * 48000))
        fc.append(f"[{ai0 + j}:a:0]aresample=48000,aformat=channel_layouts=stereo,atrim=duration={L_:.4f},asetpts=PTS-STARTPTS{fd},adelay={dl}S|{dl}S[a{j}]")
    fc.append("".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[vc]")
    fc.append("".join(f"[a{j}]" for j in range(len(segs))) + (f"amix=inputs={len(segs)}:normalize=0:duration=longest," if len(segs) > 1 else "")
              + f"apad,atrim=duration={total:.4f}[ac]")
    vlast, k = "vc", n + len(segs)
    for j, b in enumerate(broll):
        at, dur = float(b["at"]), float(b.get("dur", 1.5))
        args += ["-threads", dthr, "-ss", f"{float(b.get('from', 0)):.3f}", "-t", f"{dur:.3f}", "-i", b["file"]]
        fc.append(f"[{k}:v:0]fps={fps},{crop_916(W, H, float(b.get('zoom', 1.0)), b.get('crop_x', 0.5))},format=yuv420p,setpts=PTS-STARTPTS+{at:.3f}/TB[b{j}]")
        fc.append(f"[{vlast}][b{j}]overlay=enable='between(t,{at:.3f},{at + dur:.3f})':eof_action=pass[vo{j}]"); vlast = f"vo{j}"; k += 1
    fdir = FONTS
    sfd = os.path.join(st.get("_style_dir", ""), "fonts")
    if st.get("_style_dir") and os.path.isdir(sfd):   # the style ships fonts: merge them with the kit's for libass
        fdir = os.path.join(out, "_fonts"); os.makedirs(fdir, exist_ok=True)
        for d in (FONTS, sfd):
            for f in os.listdir(d):
                if f.lower().endswith((".ttf", ".otf")): shutil.copy2(os.path.join(d, f), os.path.join(fdir, f))
    fc.append(f"[{vlast}]subtitles=filename='{os.path.basename(ass)}':fontsdir='{fdir}'[vsub]"); vlast = "vsub"
    # QE-MS-001h: pre-animated alpha overlays (e.g. logo pops built from approved_assets/logos), {file, at, dur, x, y} = centre
    # in full-res px; the file must live in the job folder or approved_assets
    for j, ov in enumerate(edl.get("overlays") or []):
        of = guard_media(rel(ov["file"]), project, "overlay", edl, set())
        at, dur, sx = float(ov["at"]), float(ov["dur"]), W / 1080.0
        args += ["-i", of]
        fc.append(f"[{k}:v:0]fps={fps},scale=iw*{sx:.4f}:-1,format=rgba,setpts=PTS-STARTPTS+{at:.3f}/TB[ol{j}]")
        fc.append(f"[{vlast}][ol{j}]overlay=x={float(ov['x']) * sx:.1f}-w/2:y={float(ov['y']) * sx:.1f}-h/2:enable='between(t,{at:.3f},{at + dur - 0.001:.3f})':eof_action=pass:format=auto[vov{j}]")
        vlast = f"vov{j}"; k += 1
    for j, fx in enumerate(edl.get("fx") or []):
        a_, b_ = float(fx["at"]), float(fx["at"]) + float(fx.get("dur", 0.1)); A_ = max(2, int(round(float(fx.get("amp", 8)) * W / 1080)))
        en = f"between(t,{a_:.3f},{b_:.3f})"
        if fx["type"] == "shake":
            fc.append(f"[{vlast}]split[fxa{j}][fxb{j}]")
            fc.append(f"[fxb{j}]crop={W - 2 * A_}:{H - 2 * A_}:x='{A_}+{A_}*sin(2*PI*t*31)':y='{A_}+{A_}*cos(2*PI*t*23)',scale={W}:{H}:flags=lanczos[fxs{j}]")
            fc.append(f"[fxa{j}][fxs{j}]overlay=enable='{en}'[fx{j}]")
        elif fx["type"] == "rgb":
            fc.append(f"[{vlast}]rgbashift=rh={-A_}:bh={A_}:enable='{en}'[fx{j}]")
        else: die(f"unknown fx {fx['type']}")
        vlast = f"fx{j}"
    fc.append(f"[{vlast}]null[vout]")
    alast = "ac"
    if aud.get("pre"):
        fc.append(f"[ac]{aud['pre']}[acp]"); alast = "acp"
    if sfx:
        for j, s in enumerate(sfx):
            ms = int(float(s["at"]) * 1000)
            args += ["-i", s["file"]]
            fc.append(f"[{k}:a:0]aresample=48000,aformat=channel_layouts=stereo,adelay={ms}|{ms},volume={float(s.get('gain_db', -6))}dB[s{j}]"); k += 1
        fc.append(f"[{alast}]" + "".join(f"[s{j}]" for j in range(len(sfx))) + f"amix=inputs={len(sfx) + 1}:normalize=0:duration=first[am]"); alast = "am"
    L = st["loudness"]
    ef = float(st.get("end_fade_s", 0.15))
    fc.append(f"[{alast}]loudnorm=I={L['I']}:TP={L['TP']}:LRA={L['LRA']},aresample=48000,atrim=duration={total:.4f}"
              + (f",afade=t=out:st={total - ef:.4f}:d={ef:.4f}:curve=cub" if ef else "") + "[aout]")
    threads = str(int(os.environ.get("QE_THREADS", 4)))
    args += ["-filter_complex", ";".join(fc), "-map", "[vout]", "-map", "[aout]", "-t", f"{total:.3f}",
             "-c:v", "libx264", "-preset", "medium" if a.full else "veryfast", "-crf", "20" if a.full else "23", "-pix_fmt", "yuv420p",
             "-r", str(fps), "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-movflags", "+faststart", "-threads", threads, mp4]
    open(os.path.join(out, "render_cmd.txt"), "w").write(" ".join(json.dumps(x) if " " in x or ";" in x else x for x in args) + "\n")
    t1 = time.time()
    r = subprocess.run(list(args), cwd=out, capture_output=True, text=True)
    if r.returncode: die(f"ffmpeg failed (rc {r.returncode}): {r.stderr[-1500:]}")
    gain = loud_trim(mp4, float(st["loudness"]["I"]), float(st["loudness"]["TP"]))
    rep = {"name": name, "edl": os.path.abspath(a.edl), "source": src, "source_sha256": sha256(src), "output": mp4,
           "full": bool(a.full), "w": W, "h": H, "fps": fps, "expected_duration_s": round(total, 3), "pieces": len(pieces), "loudness_trim_db": gain,
           "pieces_list": [{"out_in": round(sum(q[1] - q[0] for q in pieces[:i]), 3), "out_out": round(sum(q[1] - q[0] for q in pieces[:i + 1]), 3),
                            "src_in": p_[0], "src_out": p_[1], "zoom": p_[2]} for i, p_ in enumerate(pieces)],
           "cuts": len(edl["cuts"]), "caption_chunks": nchunks, "words_on_screen": len(owords), "broll": len(broll),
           "graphics": len(edl.get("graphics") or []), "sfx": len(sfx),
           "audio_override": ({"file": afile, "sha256": sha256(afile), "offset": aoff, "pre": aud.get("pre")} if afile else None),
           "timing_s": {"prep": round(t1 - t0, 2), "ffmpeg": round(time.time() - t1, 2), "render_total": round(time.time() - t0, 2)}}
    json.dump(rep, open(os.path.join(out, "qe_report.json"), "w"), indent=2)
    print(f"rendered {mp4} ({total:.2f} s, {len(pieces)} pieces, {nchunks} caption chunks) in {rep['timing_s']['render_total']} s")
    if a.check: return cmd_check(argparse.Namespace(target=out))
    return 0

# ------------------------------------------------------------------ check (cheap, fixed)
def cmd_check(a):
    t0 = time.time()
    rp = a.target if a.target.endswith(".json") else os.path.join(a.target, "qe_report.json")
    rep = json.load(open(rp)); mp4 = rep["output"]; out = os.path.dirname(rp)
    pr = ffprobe(mp4)
    v = next((s for s in pr["streams"] if s["codec_type"] == "video"), None)
    au = next((s for s in pr["streams"] if s["codec_type"] == "audio"), None)
    dur = float(pr["format"].get("duration") or 0)
    checks = []
    def add(name, ok, got, want): checks.append({"check": name, "pass": bool(ok), "got": got, "want": want})
    add("resolution", v and int(v["width"]) == rep["w"] and int(v["height"]) == rep["h"], f"{v and v['width']}x{v and v['height']}", f"{rep['w']}x{rep['h']}")
    tol = 0.1 + 2.0 / rep["fps"]
    add("duration_s", abs(dur - rep["expected_duration_s"]) <= tol, round(dur, 3), f"{rep['expected_duration_s']} +/- {tol:.2f}")
    add("audio_present", au is not None, au and au.get("codec_name"), "an audio stream")
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-i", mp4, "-map", "0:a:0", "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True)
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr); lufs = float(m[-1]) if m else None
    add("audio_not_silent", lufs is not None and lufs > -40, lufs, "> -40 LUFS")
    want = (STYLE_DEFAULTS["loudness"]["I"])
    add("loudness_LUFS", lufs is not None and abs(lufs - want) <= 2.0, lufs, f"{want} +/- 2")
    sheet = os.path.join(out, f"{rep['name']}_sheet.jpg")
    step = max(1.0, dur / 24)
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-nostdin", "-i", mp4, "-vf",
                    f"fps=1/{step:.3f},scale=180:-2,tile=6x4:padding=4:color=black", "-frames:v", "1", "-q:v", "4", sheet], capture_output=True)
    add("contact_sheet", os.path.isfile(sheet), os.path.basename(sheet), "written (1 frame / %.1f s)" % step)
    rep["checks"] = checks; rep["checks_pass"] = all(c["pass"] for c in checks); rep["contact_sheet"] = sheet
    rep.setdefault("timing_s", {})["check"] = round(time.time() - t0, 2)
    json.dump(rep, open(rp, "w"), indent=2)
    for c in checks: print(f"{'PASS' if c['pass'] else 'FAIL'} {c['check']}: got {c['got']} (want {c['want']})")
    print("RESULT:", "PASS" if rep["checks_pass"] else "FAIL", f"(checks {rep['timing_s']['check']} s)")
    return 0 if rep["checks_pass"] else 1

# ------------------------------------------------------------------ transcribe (opt-in, once)
def cmd_transcribe(a):
    h = sha256(a.clip); os.makedirs(CACHE, exist_ok=True)
    dst = os.path.join(CACHE, f"{h}.{a.model}.words.json")
    if os.path.exists(dst): print(dst, "(cached)"); return 0
    if a.model not in ("tiny.en", "base.en", "small.en"): die("QE transcribe allows tiny.en/base.en/small.en only (heavy ASR is a full-job tool)")
    from faster_whisper import WhisperModel
    t0 = time.time()
    m = WhisperModel(a.model, device="cpu", compute_type="int8", cpu_threads=int(os.environ.get("QE_THREADS", 4)))
    import numpy as np   # decode with ffmpeg (16 kHz mono f32): the box's PyAV build breaks faster-whisper's own decoder
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-i", a.clip, "-vn", "-ac", "1", "-ar", "16000", "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    segs, info = m.transcribe(np.frombuffer(pcm, np.float32), language="en", word_timestamps=True, vad_filter=True)
    words = [{"w": w.word.strip(), "start": round(w.start, 3), "end": round(w.end, 3), "p": round(w.probability, 3)} for s in segs for w in s.words]
    json.dump({"source": os.path.realpath(a.clip), "sha256": h, "model": a.model, "duration": info.duration, "words": words,
               "seconds": round(time.time() - t0, 1)}, open(dst + ".tmp", "w"))
    os.replace(dst + ".tmp", dst); print(dst, f"({len(words)} words, {time.time() - t0:.1f} s)"); return 0

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    r = sp.add_parser("render"); r.add_argument("edl"); r.add_argument("--out"); r.add_argument("--full", action="store_true"); r.add_argument("--check", action="store_true")
    c = sp.add_parser("check"); c.add_argument("target")
    t = sp.add_parser("transcribe"); t.add_argument("clip"); t.add_argument("--model", default="small.en")
    a = ap.parse_args()
    sys.exit({"render": cmd_render, "check": cmd_check, "transcribe": cmd_transcribe}[a.cmd](a))

if __name__ == "__main__":
    main()
