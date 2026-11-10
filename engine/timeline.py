#!/usr/bin/env python3
"""Edit plan (edl.json) + style -> timeline.json, the frame-exact layer list engine/render_hf.py turns into a
HyperFrames project. Same cuts, punch-ins and captions as quick_edit.py computes (it imports those functions).
Any output shape: 9:16 Shorts, 16:9 long-form (edl output w/h), every camera and b-roll window cropped to it.
"""
import hashlib, json, math, os, subprocess

import quick_edit as qe
import audio_clean

KIT = qe.KIT
CONFORM = os.path.join(KIT, ".cache", "conform")
MEDIA_EXT = {".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif", ".mp4", ".mov", ".webm", ".wav", ".mp3", ".m4a", ".ttf", ".otf"}


_SHA = {}
def sha_file(p):
    """sha256 of a file, cached by path, size and mtime (a long 4K source is hashed once, not on every render)."""
    p = os.path.realpath(p); st_ = os.stat(p); k = f"{p}|{st_.st_size}|{st_.st_mtime_ns}"
    db = os.path.join(KIT, ".cache", "sha.json")
    if not _SHA and os.path.exists(db):
        try: _SHA.update(json.load(open(db)))
        except Exception: pass
    if k not in _SHA:
        _SHA[k] = qe.sha256(p); os.makedirs(os.path.dirname(db), exist_ok=True); json.dump(_SHA, open(db, "w"))
    return _SHA[k]


def media_key(kind, p):
    """Public-folder name for a media file: named by its content, so every job can share one bundle."""
    return f"{kind}-{sha_file(p)[:20]}{os.path.splitext(p)[1].lower()}"


def probe_video(p):
    d = qe.ffprobe(p)
    v = next(s for s in d["streams"] if s["codec_type"] == "video")
    w, h = int(v["width"]), int(v["height"])
    rot = int(((v.get("tags") or {}).get("rotate")) or 0)
    for sd in v.get("side_data_list") or []:
        rot = int(sd.get("rotation", rot) or rot)
    if abs(rot) in (90, 270): w, h = h, w
    return w, h, float(d["format"].get("duration") or 0)


def conform(src, fps):
    """Constant-frame-rate H.264 copy of the source (cached by its sha256), so every frame lands exactly.
    Video and audio are picked by type, never by stream order. Audio stays PCM-clean (AAC 320k, 48 kHz)."""
    os.makedirs(CONFORM, exist_ok=True)
    h = sha_file(src)
    dst = os.path.join(CONFORM, f"{h}.{fps}fps.mp4")
    if os.path.exists(dst): return dst, h
    tmp = dst + ".tmp.mp4"
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-nostdin", "-i", src, "-map", "0:v:0", "-map", "0:a:0",
                        "-vf", f"fps={fps},format=yuv420p", "-c:v", "libx264", "-preset", "veryfast", "-crf", "14", "-g", str(fps),
                        "-c:a", "aac", "-b:a", "320k", "-ar", "48000", "-ac", "2", "-movflags", "+faststart", tmp],
                       capture_output=True, text=True)
    if r.returncode: qe.die(f"could not prepare the clip for rendering: {r.stderr[-600:]}")
    os.replace(tmp, dst)
    return dst, h


def crop_box(iw, ih, z, cx, cy, ar=9 / 16):
    """The output-shaped window (x, y, w, h) in source pixels: ar = output width / height (9:16 Short, 16:9 long-form)."""
    cw = int(min(iw, ih * ar) / z / 2) * 2
    ch = int(min(ih, iw / ar) / z / 2) * 2
    return (iw - cw) * cx, (ih - ch) * cy, cw, ch


def font_scale(st):
    """Factor that turns a caption size (libass Fontsize) into CSS px. libass sizes a font so its OS/2 usWinAscent +
    usWinDescent equals Fontsize; CSS sizes the em. Read from the font file, so any style font matches the old look."""
    import struct
    try:
        d = open(qe._font_path(st), "rb").read()
        n = struct.unpack(">H", d[4:6])[0]
        tab = {d[12 + 16 * i:16 + 16 * i]: struct.unpack(">I", d[20 + 16 * i:24 + 16 * i])[0] for i in range(n)}
        upem = struct.unpack(">H", d[tab[b"head"] + 18:tab[b"head"] + 20])[0]
        wa, wd = struct.unpack(">HH", d[tab[b"OS/2"] + 74:tab[b"OS/2"] + 78])
        if wa + wd: return upem / (wa + wd)
    except Exception:
        pass
    try:
        from PIL import ImageFont
        a, d_ = ImageFont.truetype(qe._font_path(st), 1000).getmetrics()
        return 1000.0 / (a + d_)
    except Exception:
        return 0.64


DLG = os.path.join(KIT, ".cache", "dialogue")
SR = 48000


def dialogue(edl, edl_dir, src, pieces, st, total):
    """His voice for the whole timeline as one 48 kHz WAV, cut to the exact sample like the approved edits:
    one segment per cut, each cut a 2h equal-gain crossfade (style xfade_ms), no clicks and no frame rounding.
    It plays as the project's one voice track. Cached by everything that shapes it."""
    aud = edl.get("audio") or {}
    afile = os.path.realpath(os.path.join(edl_dir, aud["file"])) if aud.get("file") else None
    asrc, aofs = (afile, float(aud.get("offset", 0.0))) if afile else (src, 0.0)
    xf = float(st.get("xfade_ms", 12)) / 1000.0; h = xf / 2
    segs, o = [], 0.0
    for x, y, z, fin, fout in pieces:
        if fin: segs.append([x, y, o])
        else: segs[-1][1] = y
        o += y - x
    cleanup = aud.get("cleanup", True)
    if not isinstance(cleanup, bool):
        qe.die('audio.cleanup must be true or false')
    key = hashlib.sha256(json.dumps([audio_clean.VERSION, sha_file(asrc), aofs, xf, segs, total, aud.get("pre"), cleanup]).encode()).hexdigest()[:20]
    os.makedirs(DLG, exist_ok=True)
    out = os.path.join(DLG, f"{key}.wav")
    if os.path.exists(out): return out
    args, fc = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-nostdin"], []
    levels = []
    for j, (x, y, oo) in enumerate(segs):
        pre = h if j > 0 else 0.0; post = h if j < len(segs) - 1 else 0.0
        args += ["-ss", f"{x - pre - aofs:.4f}", "-t", f"{y - x + pre + post:.4f}", "-i", asrc]
        L_ = y - x + pre + post
        fd = (f",afade=t=in:d={2 * pre:.4f}" if pre else "") + (f",afade=t=out:st={L_ - 2 * post:.4f}:d={2 * post:.4f}" if post else "")
        dl = int(round((oo - pre) * SR))
        level = audio_clean.piece_gain(asrc, x - aofs, y - x) if cleanup else {'gain_db': 0.0}
        levels.append({'cut': j, **level})
        clean = f",{audio_clean.CLEAN_FILTER},volume={level['gain_db']:.4f}dB" if cleanup else ''
        fc.append(f"[{j}:a:0]aresample={SR},aformat=channel_layouts=stereo,atrim=duration={L_:.4f},asetpts=PTS-STARTPTS{clean}{fd},adelay={dl}S|{dl}S[a{j}]")
    fc.append("".join(f"[a{j}]" for j in range(len(segs))) + (f"amix=inputs={len(segs)}:normalize=0:duration=longest," if len(segs) > 1 else "")
              + f"apad=whole_dur={total:.6f},atrim=duration={total:.6f}" + (f",{aud['pre']}" if aud.get("pre") else "") + "[ac]")
    # whole_dur and -t both cap the length: an open-ended pad can otherwise write without end
    r = subprocess.run(args + ["-filter_complex", ";".join(fc), "-map", "[ac]", "-t", f"{total:.6f}", "-c:a", "pcm_f32le", "-ar", str(SR), out + ".tmp.wav"],
                       capture_output=True, text=True)
    if r.returncode: qe.die(f"building the dialogue track failed: {r.stderr[-600:]}")
    os.replace(out + ".tmp.wav", out)
    with open(out + '.json', 'w') as report:
        json.dump({'pipeline': audio_clean.VERSION, 'cleanup': cleanup, 'cuts': levels}, report, indent=2)
    return out


def template_props(props, media, base=None):
    """Template inputs that name a media file (kit-relative, job-relative or absolute) become public-folder names."""
    out = {}
    for k, v in props.items():
        if isinstance(v, str) and os.path.splitext(v)[1].lower() in MEDIA_EXT:
            for cand in ([v] if os.path.isabs(v) else [os.path.join(base, v)] if base else []) + [os.path.join(KIT, v)]:
                if os.path.isfile(cand):
                    key = media_key("asset", cand); media[key] = os.path.realpath(cand); v = key
                    break
        out[k] = v
    return out


def build(edl_path, full=True):
    edl = json.load(open(edl_path)); edl_dir = os.path.dirname(os.path.abspath(edl_path))
    # a path in the plan: absolute, in the job folder, or in the kit (library/..., assets/...)
    rel = lambda p: p if not p or os.path.isabs(p) else next((c for c in (os.path.join(edl_dir, p), os.path.join(KIT, p)) if os.path.exists(c)),
                                                             os.path.join(edl_dir, p))
    st = qe.resolve_style(edl)
    o = edl.get("output") or {}
    W, H = (int(o.get("w", 1080)), int(o.get("h", 1920))) if full else (int(o.get("proxy_w", 540)), int(o.get("proxy_h", 960)))
    fps = int(o.get("fps", 30))
    src = os.path.realpath(rel(edl["source"]))
    if not os.path.isfile(src): qe.die(f"source {src} does not exist")
    words = qe.load_words(rel(edl.get("words")))
    pieces = qe.build_pieces(edl, words, st, fps)
    owords, total = qe.map_words(words, pieces)
    frames = int(round(total * fps))
    cfr, src_sha = conform(src, fps)
    iw, ih, _ = probe_video(cfr)
    SRC = f"src-{src_sha[:20]}-{fps}.mp4"
    media = {SRC: cfr}
    f = lambda t: int(round(t * fps))                 # cut points (already whole frames)
    fc = lambda t: int(math.ceil(t * fps - 1e-6))     # timed events: first frame at or after t, as ffmpeg/libass show them

    # camera: one layer per piece, cropped and punched exactly like quick_edit (crop_916 + drift)
    cam, acc = [], 0.0
    cx = float(st.get("crop_x", 0.5)); ay = float(st["punch"].get("anchor_y", 0.5))
    dr = st.get("drift") or {}
    for x, y, z, fin, fout in pieces:
        d = y - x
        bx, by, bw, bh = crop_box(iw, ih, z, cx, ay if z > 1.0 else 0.5, W / H)
        cam.append({"start": f(acc), "frames": f(acc + d) - f(acc), "src": SRC, "src_frame": f(x),
                    "crop": [round(bx, 3), round(by, 3), bw, bh], "fade_in": bool(fin), "fade_out": bool(fout),
                    "drift": float(dr["amount"]) if dr and d >= float(dr.get("min_s", 1.9)) else 0.0})
        acc += d

    # captions: the same chunks as the ASS writer, with each word's spoken frame
    kws = qe.highlight_set(owords, edl, st)
    shown, _ = qe.caption_chunks(owords, total, edl, st)
    fs = st["font_size_frac"] * H
    caps = []
    for c, s, e in shown:
        fit = qe._fit_one_line(c, st, round(fs), W) if st.get("one_line") else 1.0
        # t0 / at: exact times in frames (floats); the pop and each keyword's colour are timed from them, like libass
        lines = [[{"text": (w["w"].upper() if st["uppercase"] else w["w"]), "hot": qe.norm(w["w"]) in kws,
                   "at": round(s * fps + int((w["s"] - s) * 1000) / 1000 * fps, 4)} for w in line] for line in qe._lines(c, st)]
        caps.append({"start": fc(s), "end": fc(e), "t0": round(s * fps, 4), "size": round(fs) * fit, "lines": lines})

    # overlays: a logo tile ({template: logo_pop, props}), a picture card ({picture}) or a transparent video ({file}); x/y are 1080-wide px
    ovs = []
    for j, ov in enumerate(edl.get("overlays") or []):
        a_ = float(ov["at"]); b_ = a_ + float(ov["dur"]) - 0.001
        item = {"start": fc(a_), "frames": max(1, int(math.floor(b_ * fps + 1e-6)) - fc(a_) + 1), "x": float(ov.get("x", 540)), "y": float(ov.get("y", 960))}
        if ov.get("picture"):   # a still (screenshot, photo) on a card: library/pictures/..., job-relative or absolute
            fp = next((c for c in (rel(ov["picture"]), os.path.join(KIT, ov["picture"])) if os.path.isfile(c)), None)
            if not fp: qe.die(f"picture {ov['picture']} not found (put it in library/pictures/ or the job folder)")
            key = media_key("pic", os.path.realpath(fp)); media[key] = os.path.realpath(fp)
            item.update(picture=key, w=float(ov.get("w", 620)), round=float(ov.get("round", 28)))
        elif ov.get("template"):
            item.update(template=ov["template"], props=template_props(ov.get("props") or {}, media, edl_dir))
        else:
            fp = os.path.realpath(rel(ov["file"])); key = media_key("overlay", fp)
            media[key] = fp; item.update(file=key)
        ovs.append(item)
    broll = []
    for b in edl.get("broll") or []:
        fp = os.path.realpath(rel(b["file"])); key = media_key("broll", fp)
        media[key] = fp
        bw_, bh_, _ = probe_video(fp)
        bx, by, bw, bh = crop_box(bw_, bh_, float(b.get("zoom", 1.0)), float(b.get("crop_x", 0.5)), 0.5, W / H)
        broll.append({"start": fc(float(b["at"])), "frames": f(float(b.get("dur", 1.5))), "file": key,
                      "src_frame": f(float(b.get("from", 0))), "crop": [bx, by, bw, bh], "src_w": bw_, "src_h": bh_,
                      "layout": b.get("layout") or "full"})   # full | pip (his face in a corner) | split (b-roll top, face bottom)
    sfx = []
    for s in edl.get("sfx") or []:
        fp = os.path.realpath(rel(s["file"])); key = media_key("sfx", fp)
        media[key] = fp
        sfx.append({"start": fc(float(s["at"])), "file": key, "gain_db": float(s.get("gain_db", -6))})
    gfx = [{"start": fc(float(g["at"])), "frames": f(float(g.get("dur", 1.2))), "text": g["text"]} for g in edl.get("graphics") or []]
    # HyperFrames library blocks (hyperframes catalog): {name, at, dur, vars, box: [x, y, w, h] in output px}
    blocks = [{"name": b["name"], "start": fc(float(b["at"])), "frames": f(float(b.get("dur", 2.0))),
               "vars": b.get("vars") or {}, "box": b.get("box")} for b in edl.get("blocks") or []]

    dlg = dialogue(edl, edl_dir, src, pieces, st, total)

    style = {k: v for k, v in st.items() if not k.startswith("_")}
    style["font_css_scale"] = font_scale(st)
    style["center_y_frac"], place = caption_y(edl, st, cfr, cam, caps, fps, W, H)
    font_file = qe._font_path(st); FONT = media_key("font", font_file)
    media[FONT] = font_file
    tl = {"fps": fps, "width": W, "height": H, "frames": frames, "src_w": iw, "src_h": ih,
          "audio_processing": {"pipeline": audio_clean.VERSION, "cleanup": (edl.get("audio") or {}).get("cleanup", True)},
          "style_name": edl.get("style_name") or "", "style": style, "font": FONT,
          "dialogue": dlg, "camera": cam, "captions": caps, "overlays": ovs, "broll": broll, "sfx": sfx, "graphics": gfx, "blocks": blocks,
          "caption_place": place}
    return tl, media


SAFE_BOTTOM = 0.18   # qa.py --safe-bottom: the Shorts/Reels button zone captions must stay above


def face_bottoms(cfr, cam, fps):
    """Lowest face edge (0-1 of frame height) in each camera piece's window, from a frame in the middle of the piece.
    Same Apple Vision face detector the QA gate uses. Cached per source + windows."""
    key = hashlib.sha1(json.dumps([os.path.realpath(cfr), os.path.getsize(cfr), [(p["src_frame"], p["frames"], p["crop"]) for p in cam]]).encode()).hexdigest()[:16]
    cache = os.path.join(qe.KIT, ".cache", "faces", key + ".json")
    if os.path.exists(cache): return json.load(open(cache))
    import qa, tempfile
    out = []
    with tempfile.TemporaryDirectory() as d:
        for i, p in enumerate(cam):
            x, y, w, h = p["crop"]; jpg = os.path.join(d, f"{i}.jpg")
            t = (p["src_frame"] + p["frames"] / 2) / fps
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", cfr, "-frames:v", "1",
                            "-vf", f"crop={int(w)}:{int(h)}:{int(x)}:{int(y)},scale=540:960", jpg], check=True)
            _, faces = qa.vision_analyze(jpg, 0.05, False)
            out.append(max((f["b"] for f in faces if f["h"] >= 0.06), default=None))
    os.makedirs(os.path.dirname(cache), exist_ok=True); json.dump(out, open(cache, "w"))
    return out


def caption_y(edl, st, cfr, cam, caps, fps, W, H):
    """Caption height for this video. The plan's caption_y_frac wins (his choice for this video); else the style's height,
    moved down just below his face when the face reaches it (style avoid_faces, on by default), but never into the
    bottom button zone. Returns (center_y_frac, a one-line reason)."""
    base = float(st.get("center_y_frac", 0.64))
    if edl.get("caption_y_frac") is not None:
        return float(edl["caption_y_frac"]), f"captions at {float(edl['caption_y_frac']):.2f} (set in the plan)"
    if not st.get("avoid_faces", True) or not caps or not cam:
        return base, f"captions at {base:.2f} (style)"
    half = max(c["size"] for c in caps) / H / 2
    faces = [b for b in face_bottoms(cfr, cam, fps) if b is not None]
    if not faces:
        return base, f"captions at {base:.2f} (style; no face found)"
    face = max(faces)
    safe = SAFE_BOTTOM if H > W else 0.06   # Shorts buttons vs the YouTube player bar
    lo, hi = face + half + 0.01, 1 - safe - half - 0.005
    if base >= lo:
        return base, f"captions at {base:.2f} (style; clear of his face, lowest face edge {face:.2f})"
    if lo <= hi:
        return round(lo, 4), f"captions moved {base:.2f} -> {lo:.2f}, just below his face (lowest face edge {face:.2f})"
    return round(hi, 4), (f"captions at {hi:.2f}, as low as the button zone allows; his face reaches {face:.2f}, so some words may "
                          f"touch his chin. Reframe tighter or set caption_y_frac in the plan")
