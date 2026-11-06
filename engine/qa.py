#!/usr/bin/env python3
"""Video QA gate: checks a finished export for the problems Mitchell keeps catching by hand.

Run with the kit venv (faster-whisper, Pillow, and Apple Vision on macOS or RapidOCR on Linux):
    bin/kit qa VIDEO [--job JOB]    or    ./.venv/bin/python engine/qa.py VIDEO [options]

Writes <out>/QA-REPORT.md, <out>/qa.json and flagged frames under <out>/flags/.
Exit code: 0 = no FAIL, 1 = at least one FAIL, 2 = could not run.

With --edl edl.json (the project's edit plan) it reads the words and sfx from `captions`, the dialogue stem and
loudness target from `render`, and --end-text/--expect-text from `qa`, unless given on the command line; after
the run it writes the verdict, report path and every FAIL/WARN into edl.json `qa`.

Checks
  picture : text touching a frame edge (cut off), text over a face, head cropped at the top,
            Shorts UI safe zones, end card present / complete / held, frozen and black frames
  sound   : integrated loudness and true peak, sudden loud sections, words missing from the
            final audio (vs. the intended script; spoken numbers like "a thousand dollars" match
            "$1,000"), words buried under music/SFX (with a dialogue stem), quiet stretches (second
            speaker), SFX landing on words, dead air, phrases said twice (restarts left in)
"""
import argparse, difflib, json, math, os, re, shutil, subprocess, sys, tempfile, time
from pathlib import Path

import numpy as np

FAIL, WARN, INFO = 'FAIL', 'WARN', 'INFO'


# ----------------------------------------------------------------------------- helpers

def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def ts(t):
    t = max(0.0, float(t))
    return f"{int(t // 60)}:{t % 60:04.1f}"


def norm(w):
    return re.sub(r"[^a-z0-9$%]", "", w.lower())


def db(x):
    return 20 * math.log10(math.sqrt(float(np.mean(np.square(x)))) + 1e-9) if len(x) else -120.0


# Spoken forms Whisper writes differently from the script. Without these, "$1,000" vs "a thousand dollars"
# and Claude vs "cloud" raised false missing-word FAILs on the Claude Startups episode (Oct 2026).
ALIASES = {'cloud': 'claude', 'clawed': 'claude', 'clod': 'claude', 'claud': 'claude', 'clawd': 'claude',
           'quad': 'claude', 'thropic': 'anthropic', 'anthropics': 'anthropic', 'operator0': 'operatorzero'}
NUM = {w: i for i, w in enumerate('zero one two three four five six seven eight nine ten eleven twelve thirteen '
                                  'fourteen fifteen sixteen seventeen eighteen nineteen'.split())}
NUM.update({w: 10 * i for i, w in enumerate('twenty thirty forty fifty sixty seventy eighty ninety'.split(), 2)})
ORD = {w: i for i, w in enumerate('zeroth first second third fourth fifth sixth seventh eighth ninth tenth eleventh '
                                  'twelfth thirteenth fourteenth fifteenth sixteenth seventeenth eighteenth nineteenth '
                                  'twentieth'.split())}
ORD.update({'thirtieth': 30, 'thirtyfirst': 31})
MULT = {'hundred': 100, 'thousand': 1000, 'grand': 1000, 'k': 1000, 'million': 10 ** 6, 'm': 10 ** 6}
CURRENCY = {'dollar', 'dollars', 'bucks'}
STOP = set('a an the and or but so to of in on at for with from by is are was were be been it its this that these '
           'those i im ive id you youre your we our they them he she his her my me us do does did just like um uh '
           'okay ok yeah right there here what which who how when where then than if as not no yes can will would '
           'could should get got go going gonna have has had about up out all some any more very really'.split())


def canon(words):
    """Canonical tokens for matching: numbers merged into '#<value>' (with $, k, grand, 'dollars'), brand
    mishearings mapped, hyphens split. Returns (tokens, groups): groups[i] = indices of `words` behind tokens[i]."""
    raw = []
    for i, w in enumerate(words):
        txt = w['w'] if isinstance(w, dict) else w
        for part in re.split(r'[\s\-–—]+', txt):
            n = norm(part)
            if n:
                raw.append((n, i))
    toks, groups, k = [], [], 0
    while k < len(raw):
        t, i = raw[k]
        val, j = None, k
        m = re.fullmatch(r'\$?(\d+)(k|m)?', t)
        o = re.fullmatch(r'(\d+)(st|nd|rd|th)', t)
        if o or t in ORD:                                                   # "6th" = "sixth"
            toks.append(f'#{int(o.group(1)) if o else ORD[t]}')
            groups.append([i])
            k += 1
            continue
        if t in ('11', 'eleven') and k + 1 < len(raw) and raw[k + 1][0] == 'labs':   # "11 labs" = ElevenLabs
            toks.append('elevenlabs')
            groups.append(sorted({i, raw[k + 1][1]}))
            k += 2
            continue
        if m:
            val, j = int(m.group(1)) * MULT.get(m.group(2), 1), k + 1
            if val < 1000 and j < len(raw) and raw[j][0] == '000':        # "$6" ",000"
                val, j = val * 1000, j + 1
            if j < len(raw) and raw[j][0] in MULT:                          # "45 k", "6 grand"
                val, j = val * MULT[raw[j][0]], j + 1
        elif t.lstrip('$') in NUM or t in ('hundred', 'thousand') or (
                t in ('a', 'an') and k + 1 < len(raw) and raw[k + 1][0] in MULT):
            total, cur, j = 0, 0, k
            while j < len(raw):
                u = raw[j][0].lstrip('$')
                if u in NUM:
                    cur += NUM[u]
                elif u in ('a', 'an') and j == k:
                    cur = 1
                elif u == 'hundred':
                    cur = max(cur, 1) * 100
                elif u in MULT and u != 'hundred' and (cur or total or j == k):   # "thousand dollars"
                    total, cur = total + max(cur, 1) * MULT[u], 0
                elif u == 'and' and j + 1 < len(raw) and raw[j + 1][0] in NUM and (cur >= 100 or total):
                    pass
                else:
                    break
                j += 1
            val = total + cur
        if val is not None and j > k:
            while j < len(raw) and raw[j][0] in CURRENCY:
                j += 1
            toks.append(f'#{val}')
            groups.append(sorted({raw[x][1] for x in range(k, j)}))
            k = j
        else:
            toks.append(ALIASES.get(t, t))
            groups.append([i])
            k += 1
    return toks, groups


class Report:
    def __init__(self):
        self.items = []

    def add(self, sev, check, msg, start=None, end=None, image=None, detail=None):
        self.items.append(dict(sev=sev, check=check, msg=msg, start=start, end=end, image=image, detail=detail))

    def count(self, sev):
        return sum(1 for i in self.items if i['sev'] == sev)


def probe(video):
    r = run(['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_type,width,height,r_frame_rate:format=duration',
             '-of', 'json', str(video)])
    if r.returncode:
        raise SystemExit(f"ffprobe failed: {r.stderr.strip()}")
    j = json.loads(r.stdout)
    v = next((s for s in j['streams'] if s['codec_type'] == 'video'), None)
    a = next((s for s in j['streams'] if s['codec_type'] == 'audio'), None)
    if not v:
        raise SystemExit('no video stream')
    num, den = v['r_frame_rate'].split('/')
    return dict(w=int(v['width']), h=int(v['height']), fps=float(num) / float(den),
                dur=float(j['format']['duration']), has_audio=a is not None)


def load_audio(path, sr=16000):
    r = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(path), '-ac', '1', '-ar', str(sr), '-f', 'f32le', '-'],
                       capture_output=True)
    return np.frombuffer(r.stdout, np.float32)


def load_words(path):
    """Accept [{w|word|text, s|start, e|end}] or {"words": [...], "sfx": [[name, t, dur], ...]}
    (a path, or the already-loaded edl.json `captions` section)."""
    d = path if isinstance(path, dict) else json.load(open(path))
    words = d.get('words', []) if isinstance(d, dict) else d
    sfx = d.get('sfx', []) if isinstance(d, dict) else []
    out = []
    for w in words:
        text = w.get('w', w.get('word', w.get('text', '')))
        s = w.get('s', w.get('start'))
        e = w.get('e', w.get('end', s))
        if text and s is not None:
            out.append(dict(w=str(text).strip(), s=float(s), e=float(e)))
    return out, sfx


# ----------------------------------------------------------------------------- picture

def extract_frames(video, fps, out_dir, height):
    out_dir.mkdir(parents=True, exist_ok=True)
    scale = f",scale=-2:{height}" if height else ""
    r = run(['ffmpeg', '-v', 'error', '-i', str(video), '-vf', f'fps={fps}{scale}', '-q:v', '3',
             str(out_dir / 'f_%06d.jpg')])
    if r.returncode:
        raise SystemExit(f"frame extraction failed: {r.stderr.strip()[:400]}")
    frames = sorted(out_dir.glob('f_*.jpg'))
    return [(i / fps, p) for i, p in enumerate(frames)]


_OCR = None
_FACE = None


def vision_analyze(path, min_text_h, accurate):
    """Apple Vision on macOS. RapidOCR and OpenCV Haar on Linux. Same box contract."""
    if sys.platform == "darwin":
        return _vision_apple(path, min_text_h, accurate)
    return _vision_linux(path, min_text_h, accurate)


def _vision_apple(path, min_text_h, accurate):
    import Vision
    from Foundation import NSURL
    handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(NSURL.fileURLWithPath_(str(path)), None)
    ocr = Vision.VNRecognizeTextRequest.alloc().init()
    ocr.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate if accurate
                             else Vision.VNRequestTextRecognitionLevelFast)
    ocr.setUsesLanguageCorrection_(False)
    ocr.setMinimumTextHeight_(min_text_h)
    faces = Vision.VNDetectFaceRectanglesRequest.alloc().init()
    handler.performRequests_error_([ocr, faces], None)

    def box(bb):
        x, y, w, h = bb.origin.x, bb.origin.y, bb.size.width, bb.size.height
        return dict(l=x, r=x + w, t=1 - (y + h), b=1 - y, w=w, h=h)

    texts = []
    for o in (ocr.results() or []):
        c = o.topCandidates_(1)
        if c and len(c):
            text, conf = str(c[0].string()), float(c[0].confidence())
            if conf >= 0.5 and norm(text):
                texts.append(dict(text=text, conf=conf, **box(o.boundingBox())))
    fcs = [box(f.boundingBox()) for f in (faces.results() or [])]
    return texts, fcs


def _vision_linux(path, min_text_h, accurate):
    global _OCR, _FACE
    import cv2
    if _OCR is None:
        from rapidocr_onnxruntime import RapidOCR
        _OCR = RapidOCR()
        _FACE = [cv2.CascadeClassifier(cv2.data.haarcascades + n) for n in
                 ("haarcascade_frontalface_default.xml", "haarcascade_profileface.xml")]
    img = cv2.imread(str(path))
    if img is None:
        return [], []
    height, width = img.shape[:2]

    def box(x, y, w, h):
        return dict(l=x / width, r=(x + w) / width, t=y / height, b=(y + h) / height, w=w / width, h=h / height)

    texts = []
    res, _ = _OCR(img)
    for quad, text, conf in (res or []):
        xs = [q[0] for q in quad]
        ys = [q[1] for q in quad]
        found = box(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
        if float(conf) >= 0.5 and norm(text) and found["h"] >= min_text_h:
            texts.append(dict(text=text, conf=float(conf), **found))
    gray = cv2.equalizeHist(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
    faces = []
    minimum = int(min(width, height) * 0.08)
    for cascade in _FACE:
        for (x, y, w, h) in cascade.detectMultiScale(gray, 1.1, 6, minSize=(minimum, minimum)):
            found = box(x, y, w, h)
            if all(iou(found, other) < 0.3 for other in faces):
                faces.append(found)
    return texts, faces


def overlap(a, b):
    w = max(0.0, min(a['r'], b['r']) - max(a['l'], b['l']))
    h = max(0.0, min(a['b'], b['b']) - max(a['t'], b['t']))
    return w * h


def iou(a, b):
    inter = overlap(a, b)
    return inter / (a['w'] * a['h'] + b['w'] * b['h'] - inter + 1e-9)


def frame_flags(texts, static, faces, vertical, a):
    """Return {key: [boxes]} for one frame. Edge/safe checks use only static (graphic) text."""
    flags = {}
    big = [t for t in texts if t['h'] >= a.min_text_h]
    still = [t for t in static if t['h'] >= a.min_text_h]
    eps = a.edge_eps
    for t in still:
        for side, hit in (('left', t['l'] <= eps), ('right', t['r'] >= 1 - eps),
                          ('top', t['t'] <= eps), ('bottom', t['b'] >= 1 - eps)):
            if hit:
                flags.setdefault(('edge', side), []).append(t)
    real_faces = [f for f in faces if f['h'] >= 0.06]
    for t in big:
        for f in real_faces:
            ov = overlap(t, f)
            if ov >= 0.30 * (t['w'] * t['h']) or ov >= 0.15 * (f['w'] * f['h']):
                flags.setdefault(('face', 'text'), []).extend([t, f])
    for f in real_faces:
        if f['h'] >= 0.15 and f['t'] - 0.35 * f['h'] < 0:
            flags.setdefault(('head', 'top'), []).append(f)
    if vertical:
        for t in still:
            if t['t'] < a.safe_top:
                flags.setdefault(('safe', 'top'), []).append(t)
            if t['b'] > 1 - a.safe_bottom:
                flags.setdefault(('safe', 'bottom'), []).append(t)
            if t['l'] > 1 - a.safe_right and (t['t'] + t['b']) / 2 > 0.4:
                flags.setdefault(('safe', 'right'), []).append(t)
    return flags


LABELS = {
    ('edge', 'left'): (FAIL, 'Text touches the LEFT edge (cut off?)'),
    ('edge', 'right'): (FAIL, 'Text touches the RIGHT edge (cut off?)'),
    ('edge', 'top'): (FAIL, 'Text touches the TOP edge (cut off?)'),
    ('edge', 'bottom'): (FAIL, 'Text touches the BOTTOM edge (cut off?)'),
    ('face', 'text'): (FAIL, 'Text over a face'),
    ('head', 'top'): (FAIL, 'Top of head cropped (punch-in needs headroom)'),
    ('safe', 'top'): (WARN, 'Text in the top band (under the TikTok/Reels header)'),
    ('safe', 'bottom'): (FAIL, 'Text in the bottom UI zone (covered by captions/buttons)'),
    ('safe', 'right'): (WARN, 'Text in the right-hand button column'),
}


def _font(size):
    from PIL import ImageFont
    for f in ('/System/Library/Fonts/Supplemental/Arial Bold.ttf', '/System/Library/Fonts/Helvetica.ttc'):
        try:
            return ImageFont.truetype(f, size)
        except OSError:
            pass
    return ImageFont.load_default()


def draw(frame_path, boxes, out_path, label):
    from PIL import Image, ImageDraw
    im = Image.open(frame_path).convert('RGB')
    W, H = im.size
    d = ImageDraw.Draw(im)
    for b in boxes:
        color = (255, 40, 40) if 'text' in b else (255, 165, 0)
        d.rectangle([b['l'] * W, b['t'] * H, b['r'] * W, b['b'] * H], outline=color, width=5)
    bar = max(40, H // 28)
    d.rectangle([0, 0, W, bar], fill=(0, 0, 0))
    d.text((12, bar * 0.18), label[:70], fill=(255, 255, 255), font=_font(int(bar * 0.6)))
    im.thumbnail((720, 720))
    im.save(out_path, quality=85)


def contact_sheet(paths, out_path, cols=4, tile_w=360):
    from PIL import Image
    ims = [Image.open(p).convert('RGB') for p in paths]
    if not ims:
        return None
    th = int(tile_w * ims[0].height / ims[0].width)
    rows = math.ceil(len(ims) / cols)
    sheet = Image.new('RGB', (cols * tile_w, rows * th), (24, 24, 24))
    for k, i in enumerate(ims):
        r, c = divmod(k, cols)
        sheet.paste(i.resize((tile_w, th)), (c * tile_w, r * th))
    sheet.save(out_path, quality=80)
    return out_path


def edge_bands(path):
    """Height in px of flat, dark strips on each edge of a frame (top, bottom, left, right)."""
    from PIL import Image
    g = np.asarray(Image.open(path).convert('L'), dtype=np.float32)
    def run_len(lines):
        n = 0
        for line in lines:
            if line.mean() < 28 and line.std() < 8:
                n += 1
            else:
                break
        return n
    return dict(top=run_len(g), bottom=run_len(g[::-1]), left=run_len(g.T), right=run_len(g.T[::-1])), g.shape


def check_edges_and_face(per, fps, info, a, rep):
    min_band = max(6, int(0.006 * max(info['w'], info['h'])))
    allowed = [(float(s), float(e)) for s, e in (getattr(a, 'fullscreen', None) or [])]
    def full_card(t):
        return any(s - 0.2 <= t <= e + 0.2 for s, e in allowed)
    banded, faceless = [], []
    for i, f in enumerate(per):
        bands, shape = edge_bands(f['path'])
        scale = info['h'] / shape[0]
        hit = {k: round(v * scale) for k, v in bands.items() if v * scale >= min_band}
        if hit:
            banded.append((i, hit))
        if not full_card(f['t']) and not any(x['h'] >= 0.06 for x in f['faces']):
            faceless.append(i)
    def runs(ix):
        out, cur = [], []
        for i in ix:
            if cur and i != cur[-1] + 1:
                out.append(cur)
                cur = []
            cur.append(i)
        if cur:
            out.append(cur)
        return out
    for r in runs([i for i, _ in banded]):
        if len(r) < a.persist:
            continue
        worst = {}
        for i, hit in banded:
            if r[0] <= i <= r[-1]:
                for k, v in hit.items():
                    worst[k] = max(worst.get(k, 0), v)
        rep.add(FAIL, 'picture:edge-band', 'Empty strip along the edge (picture slid or scaled off the frame)',
                per[r[0]]['t'], per[r[-1]]['t'] + 1 / fps, detail=', '.join(f'{k} {v}px' for k, v in worst.items()))
    with_face = len(per) - len(faceless)
    if len(per) >= 6 and with_face >= 0.5 * len(per):  # a talking-head video: the face should stay on screen
        for r in runs(faceless):
            dur = len(r) / fps
            if dur >= 1.0:
                rep.add(FAIL, 'picture:no-face', f'Face not visible for {dur:.1f}s (covered by a card, or cropped out)',
                        per[r[0]]['t'], per[r[-1]]['t'] + 1 / fps)
            elif len(r) >= a.persist:
                rep.add(WARN, 'picture:no-face', f'Face not visible for {dur:.1f}s', per[r[0]]['t'], per[r[-1]]['t'] + 1 / fps)


def check_picture(video, info, a, rep, out, tmp):
    vertical = info['h'] > info['w'] * 1.2
    fps = a.fps or (3.0 if info['h'] > info['w'] and info['dur'] <= 90 else 2.0 if info['dur'] <= 180 else 1.0)
    t0 = time.time()
    frames = extract_frames(video, fps, tmp / 'frames', 1080 if max(info['w'], info['h']) > 1920 else None)
    per = []
    for t, p in frames:
        texts, faces = vision_analyze(p, a.min_text_h, not a.fast_ocr)
        per.append(dict(t=t, path=p, texts=texts, faces=faces))
    rep.add(INFO, 'picture', f"Analyzed {len(per)} frames at {fps:g} fps in {time.time() - t0:.0f}s "
                             f"({'vertical' if vertical else 'horizontal'} {info['w']}x{info['h']})")

    # Text that sits in a large share of all frames is part of the scene (a shirt, a sign, a watermark),
    # not a graphic or caption; graphics and captions come and go.
    # It must also keep coming back in separate stretches (a shirt across camera cuts); one continuous
    # hold is a graphic or end card and stays in.
    from collections import Counter, defaultdict
    freq, seen = Counter(), defaultdict(list)
    for i, f in enumerate(per):
        for n in {norm(t['text']) for t in f['texts']}:
            freq[n] += 1
            seen[n].append(i)
    def stretches(ix):
        return 1 + sum(1 for x, y in zip(ix, ix[1:]) if y - x > 1)
    scene = {n for n, c in freq.items()
             if len(per) >= 10 and c >= a.scene_share * len(per) and stretches(seen[n]) >= 3}
    if scene:
        rep.add(INFO, 'picture', 'Ignored as scene text (on screen in ≥{:.0%} of frames): {}'.format(
            a.scene_share, ', '.join(sorted(scene))[:200]))
    for f in per:
        f['texts'] = [t for t in f['texts'] if norm(t['text']) not in scene]
    # Edge and safe-zone checks only count text that holds still with the same words in a neighbouring
    # sample. Rendered graphics do; text printed on clothing shifts and reads differently frame to frame.
    for i, f in enumerate(per):
        nbrs = [per[j]['texts'] for j in (i - 1, i + 1) if 0 <= j < len(per)]
        f['static'] = [t for t in f['texts'] if any(
            norm(u['text']) == norm(t['text']) and iou(t, u) >= 0.7 for n in nbrs for u in n)]
        f['flags'] = frame_flags(f['texts'], f['static'], f['faces'], vertical, a)

    # Empty strips along an edge (the picture slid or scaled off the frame) and a missing face. Neither is
    # text, so the flags above never see them; both shipped once on a QA PASS.
    check_edges_and_face(per, fps, info, a, rep)

    # Group consecutive frames carrying the same flag; drop one-sample blips (entrance animations).
    flag_dir = out / 'flags'
    flag_dir.mkdir(parents=True, exist_ok=True)
    flagged_imgs = []
    for key, (sev, label) in LABELS.items():
        runs, cur = [], []
        for i, f in enumerate(per):
            if key in f['flags']:
                if cur and i != cur[-1] + 1:
                    runs.append(cur)
                    cur = []
                cur.append(i)
        if cur:
            runs.append(cur)
        for r in runs:
            if len(r) < a.persist:
                continue
            mid = per[r[len(r) // 2]]
            boxes = mid['flags'][key]
            words = ' | '.join(dict.fromkeys(b['text'] for b in boxes if 'text' in b))[:80]
            img = flag_dir / f"{key[0]}-{key[1]}_{mid['t']:07.1f}.jpg"
            draw(mid['path'], boxes, img, f"{label} @ {ts(mid['t'])}")
            flagged_imgs.append(img)
            rep.add(sev, f'picture:{key[0]}', label, per[r[0]]['t'], per[r[-1]]['t'] + 1 / fps,
                    image=str(img.relative_to(out)), detail=words or None)

    # End card: present, complete, held past the last word.
    if a.end_text:
        want = norm(a.end_text)
        tail = [f for f in per if f['t'] >= info['dur'] - a.end_window]
        joined = [norm(''.join(t['text'] for t in f['texts'])) for f in tail]
        full = [f for f, j in zip(tail, joined) if want in j]
        partial = [f for f, j in zip(tail, joined) if want not in j and want[:max(4, len(want) // 2)] in j]
        if full:
            last_full = max(f['t'] for f in full)
            if last_full < info['dur'] - 2.0:
                rep.add(FAIL, 'picture:endcard', f'"{a.end_text}" disappears {info["dur"] - last_full:.1f}s before the end',
                        last_full, info['dur'])
            else:
                rep.add(INFO, 'picture:endcard', f'"{a.end_text}" is on screen at the end', full[0]['t'], info['dur'])
        elif partial:
            p = partial[-1]
            img = flag_dir / f"endcard_{p['t']:07.1f}.jpg"
            draw(p['path'], p['texts'], img, f'End card text incomplete @ {ts(p["t"])}')
            flagged_imgs.append(img)
            rep.add(FAIL, 'picture:endcard', f'"{a.end_text}" is only partly visible at the end (cut off?)',
                    p['t'], info['dur'], image=str(img.relative_to(out)),
                    detail=' | '.join(t['text'] for t in p['texts'])[:80])
        else:
            rep.add(FAIL, 'picture:endcard', f'"{a.end_text}" not found in the last {a.end_window:g}s')

    for want in a.expect_text:
        n = norm(want)
        hits = [f['t'] for f in per if n in norm(''.join(t['text'] for t in f['texts']))]
        if hits:
            rep.add(INFO, 'picture:expect', f'"{want}" seen fully on screen', hits[0], hits[-1])
        else:
            rep.add(WARN, 'picture:expect', f'"{want}" never read fully on screen (cut off, or OCR missed stylized text)')

    if flagged_imgs:
        contact_sheet(flagged_imgs[:24], out / 'flags-sheet.jpg')
    step = max(1, len(per) // 16)
    contact_sheet([per[i]['path'] for i in range(0, len(per), step)][:16], out / 'overview-sheet.jpg')
    return per


def check_motion(video, info, rep):
    r = run(['ffmpeg', '-v', 'error', '-i', str(video), '-an', '-vf',
             'scale=480:-2,freezedetect=n=-60dB:d=1.5,blackdetect=d=0.25:pix_th=0.10,metadata=mode=print:file=-',
             '-f', 'null', '-'])
    # The dynamic linker prints this when a parent process sets LD_LIBRARY_PATH.
    # It is not a decoder error, and -v error does not suppress it.
    noise = [line for line in r.stderr.splitlines() if "no version information available" not in line]
    err = "\n".join(noise).strip()
    if err:
        rep.add(FAIL, 'decode', 'Decoder errors in the export', detail=err[:300])
    out = r.stdout
    starts = [float(x) for x in re.findall(r'lavfi\.freezedetect\.freeze_start=([\d.]+)', out)]
    durs = [float(x) for x in re.findall(r'lavfi\.freezedetect\.freeze_duration=([\d.]+)', out)]
    for s, d in zip(starts, durs):
        if s + d >= info['dur'] - 0.3 and s >= info['dur'] - 6:
            continue  # held end card
        sev = FAIL if d >= 3.0 else WARN
        rep.add(sev, 'picture:freeze', f'Picture frozen for {d:.1f}s (B-roll ran out, or a static screen held too long)', s, s + d)
    bs = [float(x) for x in re.findall(r'lavfi\.black_start=([\d.]+)', out)]
    be = [float(x) for x in re.findall(r'lavfi\.black_end=([\d.]+)', out)]
    for s, e in zip(bs, be + [info['dur']] * (len(bs) - len(be))):
        if s < 0.2 or e > info['dur'] - 0.2:
            continue
        rep.add(FAIL, 'picture:black', f'Black frames for {e - s:.2f}s mid-video', s, e)


# ----------------------------------------------------------------------------- sound

def check_loudness(video, info, rep, target):
    r = run(['ffmpeg', '-nostats', '-i', str(video), '-vn', '-af', 'ebur128=peak=true:framelog=verbose', '-f', 'null', '-'])
    err = r.stderr
    summ = err[err.rfind('Summary:'):]
    I = re.search(r'I:\s+(-?[\d.]+) LUFS', summ)
    P = re.search(r'Peak:\s+(-?[\d.]+|-inf) dBFS', summ)
    if not I:
        rep.add(WARN, 'sound:loudness', 'Could not measure loudness')
        return None
    I = float(I.group(1))
    peak = float(P.group(1)) if P and P.group(1) != '-inf' else None
    off = abs(I - target)
    rep.add(FAIL if off > 2 else WARN if off > 1 else INFO, 'sound:loudness',
            f'Integrated loudness {I:.1f} LUFS (target {target:g})')
    if peak is not None:
        rep.add(FAIL if peak > 0 else WARN if peak > -1.0 else INFO, 'sound:peak', f'True peak {peak:.1f} dBTP (keep ≤ -1)')
    # Short-term loudness spikes: "music gets randomly loud".
    pts = [(float(t), float(s)) for t, s in re.findall(r't:\s*([\d.]+)\s+TARGET.*?S:\s*(-?[\d.]+)', err)]
    loud, cur = [], None
    for t, s in pts:
        if s > I + 5:
            cur = [cur[0], t] if cur else [t, t]
        elif cur:
            loud.append(cur)
            cur = None
    if cur:
        loud.append(cur)
    for s, e in loud:
        if e - s >= 1.5:
            rep.add(WARN, 'sound:loud-section', f'Short-term loudness >5 LU above the average (a loud swell)', s - 3, e)
    return I


# Whisper silently drops restarts ("talk about, talk about" came back once). A disfluent prompt with no
# carried-over context keeps them: small.en + this prompt recovered all four repeats Mitchell caught by ear
# in the Claude Startups episode; base without it found none. Costs ~13 s per 2 min of audio.
VERBATIM = "Umm, so, so I I mean, let me, let me say, uh, it can take, it can take up to, like, two, two days."


_MODELS = {}


def transcribe(audio16, model_name):
    from faster_whisper import WhisperModel
    m = _MODELS.get(model_name) or _MODELS.setdefault(model_name, WhisperModel(model_name, device='cpu', compute_type='int8'))
    segs, _ = m.transcribe(audio16, language='en', word_timestamps=True, vad_filter=False, beam_size=5,
                           initial_prompt=VERBATIM, condition_on_previous_text=False)
    heard = [dict(w=w.word.strip(), s=float(w.start), e=float(w.end)) for s in segs for w in (s.words or [])]
    return heard


def find_repeats(heard, window=8.0):
    """Phrases said twice close together: (gram, first_start, first_end, second_start, second_end, gap, kind).
    kind 'stutter' = immediate repeat with a content word; 'restart' = ≥3 tokens with ≥2 content words said
    again within `window` seconds. Longer phrases win; their sub-phrases are not reported again."""
    C, G = canon(heard)
    t0 = [heard[g[0]]['s'] for g in G]
    t1 = [heard[g[-1]]['e'] for g in G]
    content = [len(c) >= 3 and c not in STOP for c in C]
    found, used = [], set()
    for n in range(8, 1, -1):
        for i in range(len(C) - n + 1):
            if any(x in used for x in range(i, i + n)):
                continue
            gram = C[i:i + n]
            k = sum(content[i:i + n])
            if k == 0:
                continue
            for j in range(i + n, len(C) - n + 1):
                gap = t0[j] - t1[i + n - 1]
                if gap > window:
                    break
                if C[j:j + n] != gram or any(x in used for x in range(j, j + n)):
                    continue
                if j == i + n:
                    kind = 'stutter'
                elif n >= 3 and k >= 2:
                    kind = 'restart'
                else:
                    continue
                found.append((' '.join(heard[x]['w'] for x in range(G[i][0], G[i + n - 1][-1] + 1)),
                              t0[i], t1[i + n - 1], t0[j], t1[j + n - 1], gap, kind))
                used.update(range(i, i + n))
                used.update(range(j, j + n))
                break
    return sorted(found, key=lambda f: f[1])


def check_repeats(heard, rep, window=8.0):
    for text, s1, e1, s2, e2, gap, kind in find_repeats(heard, window):
        between = {norm(w['w']) for w in heard if e1 <= w['s'] < s2}
        if (kind == 'stutter' or gap <= 2.5) and 'again' not in between:   # "let me say that again" is on purpose
            rep.add(FAIL, 'sound:repeat', f'Said twice {gap:.1f}s apart: a restart left in. Keep only the cleaner take',
                    s1, e2, detail=text[:100])
        else:
            rep.add(WARN, 'sound:repeat', f'Same phrase again {gap:.1f}s later: intended, or a restart?',
                    s1, e2, detail=text[:100])


def _align_stem(mix, dialogue, sr, max_ms=80):
    """Shift the dialogue stem onto the export. AAC priming is about 40 ms and is not burial."""
    limit = int(sr * max_ms / 1000)
    n = min(len(mix), len(dialogue))
    best_lag, best = 0, -1e30
    step = max(1, sr // 100)

    def score_at(lag):
        if lag >= 0:
            left, right = mix[lag:n], dialogue[:n - lag]
        else:
            left, right = mix[:n + lag], dialogue[-lag:n]
        if len(left) < sr:
            return -1e30
        return float(np.dot(left, right))

    for lag in range(-limit, limit + 1, step):
        score = score_at(lag)
        if score > best:
            best, best_lag = score, lag
    for lag in range(best_lag - step, best_lag + step + 1):
        if abs(lag) > limit:
            continue
        score = score_at(lag)
        if score > best:
            best, best_lag = score, lag
    if best_lag > 0:
        dialogue = np.concatenate([np.zeros(best_lag, dtype=dialogue.dtype), dialogue])
    elif best_lag < 0:
        dialogue = dialogue[-best_lag:]
    n = min(len(mix), len(dialogue))
    return mix[:n], dialogue[:n]


def check_speech(video, info, a, rep, out):
    sr = 16000
    mix = load_audio(video, sr)
    if not len(mix):
        rep.add(FAIL, 'sound', 'No audio decoded')
        return
    model = a.model or 'small.en'
    t0 = time.time()
    heard = transcribe(mix, model)
    rep.add(INFO, 'sound:transcript', f'Transcribed {len(heard)} words with faster-whisper {model} in {time.time() - t0:.0f}s')
    (out / 'heard-words.json').write_text(json.dumps(heard, indent=1))
    speech_end = max((w['e'] for w in heard), default=0.0)

    expected, sfx = load_words(a.words) if a.words else ([], [])

    # 1. Script vs. what is actually audible (robust to cuts: aligned by order, not time).
    #    Compared on canonical tokens, so "$1,000" matches "a thousand dollars" and Claude matches "cloud".
    if expected:
        E = [norm(w['w']) for w in expected]
        Ec, Eg = canon(expected)
        Hc, _ = canon(heard)
        sm = difflib.SequenceMatcher(None, Ec, Hc, autojunk=False)
        hit = set()
        for blk in sm.get_matching_blocks():
            hit.update(range(blk.a, blk.a + blk.size))
        # Fuzzy rescue: misspellings inside replaced spans.
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == 'replace':
                for i in range(i1, i2):
                    if any(difflib.SequenceMatcher(None, Ec[i], Hc[j]).ratio() >= 0.7 for j in range(j1, j2)):
                        hit.add(i)
        matched = {x for i in hit for x in Eg[i]}
        missing_runs, cur = [], []
        for i, w in enumerate(expected):
            if i not in matched and len(E[i]) >= 2:
                cur.append(i)
            elif cur:
                missing_runs.append(cur)
                cur = []
        if cur:
            missing_runs.append(cur)
        # Whisper sometimes drops a whole sentence at a 30 s window boundary. Before failing a run (or a number),
        # re-transcribe just that slice; drop the flag if the words are there.
        kept = []
        for r in missing_runs:
            text = ' '.join(expected[i]['w'] for i in r)
            if len(r) >= 3 or re.search(r'\d', text):
                s0, s1 = max(0.0, expected[r[0]]['s'] - 1.5), expected[r[-1]]['e'] + 1.5
                got = set(canon(transcribe(mix[int(s0 * sr):int(s1 * sr)], model))[0])
                want = [c for c in canon([expected[i] for i in r])[0] if len(c) >= 2]
                if want and sum(c in got for c in want) >= 0.8 * len(want):
                    rep.add(INFO, 'sound:slice-recheck', 'Heard on a slice re-check (full-pass transcript dropped it)',
                            expected[r[0]]['s'], expected[r[-1]]['e'], detail=text[:120])
                    continue
            kept.append(r)
        missing_runs = kept
        n_miss = sum(len(r) for r in missing_runs)
        for r in missing_runs:
            text = ' '.join(expected[i]['w'] for i in r)
            sev = FAIL if len(r) >= 3 or re.search(r'\d', text) else WARN  # numbers are the payoff
            rep.add(sev, 'sound:missing-words',
                    f'{len(r)} scripted word(s) not heard in the final audio (cut, clipped, or buried)',
                    expected[r[0]]['s'], expected[r[-1]]['e'], detail=text[:120])
        rep.add(INFO, 'sound:script-match', f'{len(expected) - n_miss}/{len(expected)} scripted words heard '
                                            '(times shown use the script\'s clock; they shift after any later cut)')

    # 2. Per-word clearance against music + SFX, when the dialogue stem is supplied.
    words = expected or heard
    if a.dialogue:
        # AAC-LC priming is 2048 samples at 48 kHz, which is not an integer sample after
        # the 16 kHz resample used for the transcript. Measure clearance at 48 kHz.
        csr = 48000
        d = load_audio(a.dialogue, csr)
        m, d = _align_stem(load_audio(video, csr), d, csr)
        n = len(m)
        k = float(np.dot(m, d) / (np.dot(d, d) + 1e-9))
        rest = m - k * d
        low = []
        for w in words:
            i, j = int(w['s'] * csr), int(max(w['e'], w['s'] + 0.12) * csr)
            if j > n:
                continue
            v, r_ = db(k * d[i:j]), db(rest[i:j])
            if v - r_ < 8:
                low.append((w, v - r_))
        groups = []
        for w, mg in low:
            if groups and w['s'] - groups[-1][-1][0]['e'] < 0.6:
                groups[-1].append((w, mg))
            else:
                groups.append([(w, mg)])
        for g in groups:
            worst = min(mg for _, mg in g)
            sev = FAIL if worst < 4 or len(g) >= 3 else WARN
            rep.add(sev, 'sound:buried', f'Speech only {worst:.0f} dB above music/SFX (want ≥ 8 dB)',
                    g[0][0]['s'], g[-1][0]['e'], detail=' '.join(w['w'] for w, _ in g)[:100])
    else:
        # 3. Without stems: stretches much quieter than the typical word (e.g. second speaker).
        lv = [(w, db(mix[int(w['s'] * sr):int(max(w['e'], w['s'] + 0.12) * sr)])) for w in heard]
        if lv:
            med = float(np.median([v for _, v in lv]))
            run_, runs = [], []
            for w, v in lv:
                if v < med - 10:
                    run_.append(w)
                elif run_:
                    runs.append(run_)
                    run_ = []
            if run_:
                runs.append(run_)
            for r in runs:
                if len(r) < 2:
                    continue  # one soft word is normal speech
                rep.add(FAIL if len(r) >= 3 else WARN, 'sound:quiet',
                        'Speech >10 dB quieter than the rest (second speaker or a dropped lav?)',
                        r[0]['s'], r[-1]['e'], detail=' '.join(w['w'] for w in r)[:100])

    # 3b. Spoken but never captioned: the reverse of 1. A word the viewer hears with no caption.
    if expected:
        Ec, _ = canon(expected)
        Hc, Hg = canon(heard)
        sm2 = difflib.SequenceMatcher(None, Ec, Hc, autojunk=False)
        heard_hit = set()
        for blk in sm2.get_matching_blocks():
            heard_hit.update(range(blk.b, blk.b + blk.size))
        for tag, i1, i2, j1, j2 in sm2.get_opcodes():
            if tag == 'replace':
                for j in range(j1, j2):
                    if any(difflib.SequenceMatcher(None, Ec[i], Hc[j]).ratio() >= 0.7 for i in range(i1, i2)):
                        heard_hit.add(j)
        run_, runs_ = [], []
        for j in range(len(Hc)):
            if j in heard_hit:
                if run_:
                    runs_.append(run_)
                run_ = []
            else:
                run_.append(j)
        if run_:
            runs_.append(run_)
        for r in runs_:
            content = [Hc[j] for j in r if len(Hc[j]) >= 3 and Hc[j] not in STOP]
            if not content:
                continue
            ws = [heard[x] for j in r for x in Hg[j]]
            rep.add(FAIL, 'captions:missing', f'{len(ws)} spoken word(s) never captioned (the transcript dropped them)',
                    ws[0]['s'], ws[-1]['e'], detail=' '.join(w['w'] for w in ws)[:100])

    # 4. SFX landing on a word.
    if sfx and expected:
        for item in sfx:
            try:
                name, t = str(item[0]), float(item[1])
            except (TypeError, ValueError, IndexError):
                continue
            hit = next((w for w in expected if w['s'] + 0.04 < t < w['e'] - 0.04), None)
            if hit:
                rep.add(WARN, 'sound:sfx-on-word', f'SFX "{name}" starts inside the word "{hit["w"]}" (move it just after)', t, t)

    # 5. Dead air between words.
    gap_max = a.max_gap or (1.0 if info['h'] > info['w'] else 1.5)
    for p, q in zip(heard, heard[1:]):
        g = q['s'] - p['e']
        if g > gap_max:
            rep.add(WARN, 'sound:pause', f'{g:.1f}s with no speech (dead air?)', p['e'], q['s'],
                    detail=f'…{p["w"]} | {q["w"]}…')

    # 6. Repeated phrases left in (restarts). Mitchell caught four by ear in one cut (Oct 2026): "talk about,
    #    talk about", "two to three business days" twice, "toughest workflows" twice, "help step through".
    check_repeats(heard, rep, a.repeat_window)
    #    The long pass writes a restart down once ("so hiring, so hiring" -> "so hiring"). Re-hear the speech in
    #    short pieces (engine/listen.py) and flag repeats only that pass hears.
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from listen import chunk_words, restarts
    except ImportError:
        chunk_words = None
    if chunk_words:
        t1 = time.time()
        heard2 = chunk_words(mix, _MODELS[model])
        seen = [(f[1], f[4]) for f in find_repeats(heard, a.repeat_window)]
        # A restart's words were really said, so the long pass heard them there too (once). Short pieces that start
        # mid-phrase can make Whisper invent words ("just, just, me ... Thanks for watching!"): those aren't restarts.
        said = lambda r: all(any(norm(w['w']) == t and abs(w['s'] - r['first_start']) <= 2.0 for w in heard)
                             for t in (norm(x) for x in r['text'].split()) if t)
        extra = [r for r in restarts(heard2, find_repeats, a.repeat_window)
                 if not any(r['first_start'] < e and s < r['retake_start'] for s, e in seen) and said(r)]
        for r in extra:
            rep.add(FAIL, 'sound:repeat', 'Restart left in (heard by the short-piece listener). Keep only the last take',
                    r['first_start'], r['retake_start'], detail=r['text'][:100])
        rep.add(INFO, 'sound:listener', f'Short-piece restart listener: {len(extra)} extra repeat(s), {time.time() - t1:.0f}s')

    if a.end_text and speech_end:
        hold = info['dur'] - speech_end
        if hold < 2.0:
            rep.add(WARN, 'picture:endcard', f'Video ends {hold:.1f}s after the last word (hold the end card ~3s)',
                    speech_end, info['dur'])


# ----------------------------------------------------------------------------- report

def write_report(video, info, rep, out, args):
    order = {FAIL: 0, WARN: 1, INFO: 2}
    items = sorted(rep.items, key=lambda i: (order[i['sev']], i['start'] if i['start'] is not None else -1))
    verdict = 'FAIL' if rep.count(FAIL) else 'PASS'
    L = [f'# QA report: {Path(video).name}', '',
         f'**{verdict}** · {rep.count(FAIL)} fail · {rep.count(WARN)} warn · '
         f'{info["w"]}x{info["h"]} · {ts(info["dur"])} · {time.strftime("%Y-%m-%d %H:%M")}', '',
         'Every FAIL gets fixed, or gets a one-line reason in the delivery note (e.g. an intentional UI crop). '
         'Look at each flagged frame before deciding.', '',
         '| | Check | Time | What | Detail |', '|---|---|---|---|---|']
    for i in items:
        tm = '' if i['start'] is None else (ts(i['start']) + ('' if i['end'] is None or abs(i['end'] - i['start']) < 0.05 else f'–{ts(i["end"])}'))
        what = i['msg'] + (f' ([frame]({i["image"]}))' if i['image'] else '')
        det = (i['detail'] or '').replace('|', '/')
        L.append(f'| {i["sev"]} | {i["check"]} | {tm} | {what} | {det} |')
    L += ['', 'Sheets: `flags-sheet.jpg` (every flagged frame), `overview-sheet.jpg` (16 frames across the video).',
          '', f'Command: `qa.py {" ".join(sys.argv[1:])}`']
    (out / 'QA-REPORT.md').write_text('\n'.join(L) + '\n')
    (out / 'qa.json').write_text(json.dumps(dict(video=str(video), verdict=verdict, info=info, items=items), indent=1))
    print(f'\n{verdict}: {rep.count(FAIL)} fail, {rep.count(WARN)} warn  →  {out / "QA-REPORT.md"}')
    for i in items:
        if i['sev'] != INFO:
            tm = '' if i['start'] is None else ts(i['start'])
            print(f"  {i['sev']:4} {tm:>7}  {i['msg']}" + (f"  [{i['detail']}]" if i['detail'] else ''))
    return verdict


# ----------------------------------------------------------------------------- edit plan (edl.json)

def edl_inputs(a):
    """Fill options left off the command line from the edit plan. Command-line flags always win."""
    plan = json.load(open(a.edl))
    base = Path(a.edl).expanduser().resolve().parent
    cap, ren, q = plan.get('captions') or {}, plan.get('render') or {}, plan.get('qa') or {}
    if not a.words and cap.get('words'):
        a.words = cap                                    # same shape as short.json: {"words": [...], "sfx": [...]}
    if not a.dialogue and ren.get('dialogue'):
        stem = base / ren['dialogue']
        if stem.exists():
            a.dialogue = str(stem)
        else:
            print(f'edl.json render.dialogue not found ({stem}); running without the stem')
    if a.target_lufs is None:
        a.target_lufs = (ren.get('loudness') or {}).get('target_lufs')
    a.fullscreen = [(g.get('t'), g.get('until')) for g in (plan.get('broll') or {}).get('graphics') or []
                    if (g.get('kind') or g.get('what')) == 'cut_scene' and g.get('t') is not None and g.get('until') is not None]
    if not a.end_text and q.get('end_text'):
        a.end_text = q['end_text']
    if not a.expect_text and q.get('expect_text'):
        a.expect_text = list(q['expect_text'])


def edl_record(a, video, rep, out, verdict):
    """Write the verdict and every FAIL/WARN into edl.json `qa` (paths relative to the plan's folder)."""
    base = Path(a.edl).expanduser().resolve().parent
    rel = lambda p: os.path.relpath(str(p), str(base))
    r3 = lambda x: None if x is None else round(float(x), 3)
    order = {FAIL: 0, WARN: 1}
    flags = [dict(sev=i['sev'], check=i['check'], msg=i['msg'], start=r3(i['start']), end=r3(i['end']),
                  detail=i['detail'], image=rel(out / i['image']) if i['image'] else None)
             for i in sorted((i for i in rep.items if i['sev'] in order),
                             key=lambda i: (order[i['sev']], i['start'] if i['start'] is not None else -1))]
    plan = json.load(open(a.edl))                        # re-read: keep any edit made while the gate ran
    q = plan.get('qa') or {}
    q.update(verdict=verdict, video=rel(video), report=rel(out / 'QA-REPORT.md'), qa_json=rel(out / 'qa.json'),
             fails=rep.count(FAIL), warns=rep.count(WARN), flags=flags)
    plan['qa'] = q
    Path(a.edl).write_text(json.dumps(plan, indent=2, sort_keys=True, ensure_ascii=False) + '\n')
    print(f'edl.json qa: {verdict}, {len(flags)} flag(s) recorded in {a.edl}')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('video')
    ap.add_argument('--out', help='report folder (default: <video dir>/qa-<video name>)')
    ap.add_argument('--words', help='intended words JSON (list of {w,s,e} or {"words":[...],"sfx":[...]}); enables the script diff and SFX check')
    ap.add_argument('--dialogue', help='dialogue-only stem on the same timeline; enables per-word clearance vs music/SFX')
    ap.add_argument('--end-text', help='text the end card must show in full, e.g. operatorzero.ai')
    ap.add_argument('--expect-text', action='append', default=[], help='text that must appear fully on screen at least once (repeatable)')
    ap.add_argument('--edl', help='edl.json edit plan: reads captions/render/qa for the options above, writes the verdict to its qa section')
    ap.add_argument('--target-lufs', type=float, help='default -14 (or edl.json render.loudness.target_lufs)')
    ap.add_argument('--fps', type=float, help='frames per second to inspect (default 3 for vertical ≤90 s, 2 for ≤3 min, else 1)')
    ap.add_argument('--model', help='faster-whisper model (default small.en; base misses restarts)')
    ap.add_argument('--repeat-window', type=float, default=8.0, help='flag a phrase said again within this many seconds (restarts left in)')
    ap.add_argument('--max-gap', type=float, help='dead-air threshold in seconds (default 1.0 vertical, 1.5 horizontal)')
    ap.add_argument('--min-text-h', type=float, default=0.018, help='ignore text shorter than this fraction of frame height (small UI text)')
    ap.add_argument('--edge-eps', type=float, default=0.004, help='how close to the frame edge counts as touching')
    ap.add_argument('--safe-top', type=float, default=0.10)
    ap.add_argument('--safe-bottom', type=float, default=0.18)
    ap.add_argument('--safe-right', type=float, default=0.12)
    ap.add_argument('--end-window', type=float, default=4.0)
    ap.add_argument('--scene-share', type=float, default=0.2, help='text on screen in at least this share of frames is treated as scene text')
    ap.add_argument('--persist', type=int, default=2, help='consecutive sampled frames a picture flag must persist')
    ap.add_argument('--fast-ocr', action='store_true')
    ap.add_argument('--skip-audio', action='store_true')
    ap.add_argument('--skip-picture', action='store_true')
    a = ap.parse_args()

    video = Path(a.video).expanduser().resolve()
    if not video.exists():
        print(f'not found: {video}')
        return 2
    if a.edl:
        if not Path(a.edl).expanduser().exists():
            print(f'not found: {a.edl}')
            return 2
        edl_inputs(a)
    if a.target_lufs is None:
        a.target_lufs = -14.0
    out = Path(a.out).expanduser() if a.out else video.parent / f'qa-{video.stem}'
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    info = probe(video)
    rep = Report()
    with tempfile.TemporaryDirectory(prefix='qa-') as tmp:
        tmp = Path(tmp)
        if not a.skip_picture:
            check_picture(video, info, a, rep, out, tmp)
            check_motion(video, info, rep)
        if not a.skip_audio and info['has_audio']:
            check_loudness(video, info, rep, a.target_lufs)
            check_speech(video, info, a, rep, out)
        elif not info['has_audio']:
            rep.add(FAIL, 'sound', 'Export has no audio stream')
    verdict = write_report(video, info, rep, out, a)
    if a.edl:
        edl_record(a, video, rep, out, verdict)
    return 1 if verdict == 'FAIL' else 0


if __name__ == '__main__':
    sys.exit(main())
