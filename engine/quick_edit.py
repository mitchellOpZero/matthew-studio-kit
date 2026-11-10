#!/usr/bin/env python3
"""The kit's shared Python core: cut pieces, caption chunks and keyword timing, loudness trim, and transcription.
engine/timeline.py and engine/render_hf.py build on it; HyperFrames draws and renders every video (bin/kit render).

  quick_edit.py transcribe <clip> [--model small.en]               word timings, once per clip (cached by sha256)
"""
import math, argparse, hashlib, json, os, re, shutil, subprocess, sys, time

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # plugin: the kit folder (engine/..)
FONTS = os.path.join(KIT, "assets", "fonts")
CACHE = os.environ.get("KIT_WORDS_CACHE") or os.path.join(KIT, ".cache", "words")
STYLES = os.path.join(KIT, "styles")

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
        grow = max(1 + float(st.get("kw_pop_pct", 14)) / 100.0, float(st.get("keyword_scale", 1.0)))   # keywords drawn bigger
        wide = max(wide, font.getlength(text) * grow)
    room = W - 2 * round(W * .06)
    return min(1.0, room / wide) if wide > 0 else 1.0


def _font_path(st):
    """A style may ship its own font (styles/<name>/fonts/); else the kit's assets/fonts/."""
    f = st.get("font_file", "Montserrat-ExtraBold.ttf")
    for d in [os.path.join(st.get("_style_dir", ""), "fonts"), FONTS]:
        if d and os.path.isfile(os.path.join(d, f)): return os.path.join(d, f)
    return os.path.join(FONTS, f)


def highlight_set(words, edl, st):
    mode = st.get("highlight_mode", "keywords")   # keywords | every_word | none
    return {norm(k) for k in edl.get("keywords") or []} if mode == "keywords" else (
        {norm(w["w"]) for w in words} if mode == "every_word" else set())


def _binds_left(text):
    """A percent sign or a punctuation-only token stays with the word before it.

    Otherwise a 2-word line break turns "50 %" into its own next caption ("% more").
    """
    t = str(text).strip()
    return t in {"%", "‰"} or (bool(t) and not any(ch.isalnum() for ch in t))


_CLAUSE_START = {"and", "but", "so", "or", "because"}


def _ends_clause(text):
    """A word that closes a clause: sentence end or a comma, semicolon, or colon."""
    t = str(text).rstrip().rstrip("\"'”’)")
    return t.endswith((".", "!", "?", ",", ";", ":"))


def _starts_clause(text):
    n = re.sub(r"[^a-z']", "", str(text).lower())
    return n in _CLAUSE_START


def _clause_wall(left, right):
    """True when these two chunks meet on a clause edge and must not be glued back together."""
    return bool(left and right) and (_ends_clause(left[-1]["w"]) or _starts_clause(right[0]["w"]))


def caption_chunks(words, total, edl, st):
    """Output words -> caption chunks [(words, start, end)], after caption_breaks, min on-screen time and caption_hide.
    Shared by the ASS writer and the timeline, so both show exactly the same captions."""
    chunks, cur = [], []
    # caption_breaks: source start times of words that must open a new caption chunk; caption_text: {source start: shown text}
    brk = [float(t) for t in edl.get("caption_breaks") or []]
    ctext = {round(float(k), 2): v for k, v in (edl.get("caption_text") or {}).items()}
    for w in words:
        if round(w.get("ss", -1), 2) in ctext: w = dict(w, w=ctext[round(w["ss"], 2)])
        stick = bool(cur) and _binds_left(w["w"])
        nl = max(1, int(st.get("lines", 1) or 1)); per = int(st.get("words_per_line") or st["max_words"])
        cap_words = per * nl if nl > 1 else st["max_words"]
        forced = bool(cur) and any(abs(w.get("ss", -9) - t) <= 0.03 for t in brk)
        full = bool(cur) and (len(cur) >= cap_words or sum(len(x["w"]) + 1 for x in cur) + len(w["w"]) > st["max_chars"] * nl
                    or w["s"] - cur[-1]["e"] > st["gap_break_s"] or cur[-1]["piece_end"] <= w["s"] + 1e-6 and w["s"] - cur[-1]["e"] > 0.12)
        # Clause edge: after . ! ? , ; : and before and/but/so/or/because. A % still sticks to its number.
        clause = bool(cur) and not stick and (_ends_clause(cur[-1]["w"]) or _starts_clause(w["w"]))
        if stick and (forced or full):
            last = cur.pop()
            if cur:
                chunks.append(cur)
            cur = [last]
        elif forced or full or clause:
            chunks.append(cur); cur = []
        cur.append(w)
    if cur: chunks.append(cur)
    # minimum on-screen time (QE-MS-001c): a chunk shown < min_chunk_s joins the next chunk (else the previous one)
    mn = float(st.get("min_chunk_s", 0.3)); i = 0
    while i < len(chunks):
        nxt = chunks[i + 1][0]["s"] if i + 1 < len(chunks) else total
        if len(chunks) > 1 and min(nxt, chunks[i][-1]["e"] + 0.6) - chunks[i][0]["s"] < mn - 1e-6:
            j = i + 1 if i + 1 < len(chunks) else i - 1
            lo, hi_ = min(i, j), max(i, j)
            if _clause_wall(chunks[lo], chunks[hi_]):
                i += 1
                continue
            chunks[lo:hi_ + 1] = [chunks[lo] + chunks[hi_]]; i = max(0, lo - 1); continue
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


# ------------------------------------------------------------------ render
def measure_loud(p):
    e = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", p, "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True).stderr
    return float(re.findall(r"I:\s+(-?(?:[\d.]+|inf)) LUFS", e)[-1]), float(re.findall(r"Peak:\s+(-?(?:[\d.]+|inf)) dBFS", e)[-1])

def loud_trim(mp4, target, tp):
    """Trim the rendered mix onto the style target after mixing (audio-only re-encode, video copied).
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

def resolve_style(edl):
    """STYLE_DEFAULTS, then the named style, then any per-edit overrides in edl.style."""
    st = json.loads(json.dumps(STYLE_DEFAULTS))
    for k, v in list(load_style(edl.get("style_name")).items()) + list((edl.get("style") or {}).items()):
        if isinstance(v, dict) and isinstance(st.get(k), dict): st[k].update(v)
        else: st[k] = v
    return st

# ------------------------------------------------------------------ check (cheap, fixed)
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
    t = sp.add_parser("transcribe"); t.add_argument("clip"); t.add_argument("--model", default="small.en")
    a = ap.parse_args()
    sys.exit({"transcribe": cmd_transcribe}[a.cmd](a))

if __name__ == "__main__":
    main()
