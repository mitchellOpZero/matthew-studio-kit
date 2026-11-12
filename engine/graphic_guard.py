"""Guards for graphics on a vertical Short, run on every build (kit preview / kit render), so a bad placement, a canned
text graphic or invented on-screen text stops the build with a clear message instead of reaching his screen.

The default vertical frame is split: a graphic panel on top, his face below, captions on the seam between them.
  - every block sits inside the graphic area: the top panel, above the caption seam (place_blocks)
  - a block is mounted at a size his phone can read (no tiny corner boxes, no heavy downscaling)
  - text-only stock pieces (accent underline, kinetic type, lower thirds ...) are flagged as canned (canned)
  - every word a graphic shows has to come from what he says around that moment (unsupported_text)
"""
import json, re

SEAM_FRAC = 0.045          # half the caption capsule's height (as a fraction of frame height) kept clear above the seam
MIN_BOX_W_FRAC = 0.6       # a block narrower than this on a Short is unreadable on a phone (the tiny notification)
MIN_BOX_H = 240            # px at 1920 tall
MIN_SCALE = 0.8            # a fixed-canvas block shrunk below this has phone-unreadable text; it is reflowed instead

# text-only stock pieces: words on a coloured shape, not a replica of anything real
CANNED = re.compile(r"(underline|kinetic|lower[-_]?third|title[-_]?card|stat[-_]?count|count[-_]?up|callout|idea[-_]?swipe|"
                    r"word[-_]?(swipe|pop|stack)|text[-_]?(reveal|pop|slam|stack)|quote[-_]?card|sticker|headline|big[-_]?number)", re.I)


def is_vertical(W, H):
    return H > W


def graphic_area(W, H):
    """[x, y, w, h] a graphic may use on a split Short: the top panel minus the strip the caption capsule straddles."""
    return [0, 0, W, int(H // 2 - round(SEAM_FRAC * H))]


def face_area(W, H):
    return [0, H // 2, W, H - H // 2]


def overlaps(a, b):
    return min(a[0] + a[2], b[0] + b[2]) > max(a[0], b[0]) and min(a[1] + a[3], b[1] + b[3]) > max(a[1], b[1])


def inside(box, area, tol=1):
    x, y, w, h = box; ax, ay, aw, ah = area
    return x >= ax - tol and y >= ay - tol and x + w <= ax + aw + tol and y + h <= ay + ah + tol


def canned(name):
    return bool(CANNED.search(name or ""))


def place_blocks(blocks, W, H):
    """Every block's box on a vertical Short, checked and fixed in place: a box missing, outside the graphic area, over
    his face or the caption seam, or too small to read is moved into (and sized to) the graphic area. Returns notes.
    A text-only canned piece stops the build unless the plan says he asked for it ("canned_ok": true)."""
    notes = []
    if not is_vertical(W, H):
        return notes
    area = graphic_area(W, H)
    for b in blocks:
        name = b.get("name", "")
        if canned(name) and not b.get("canned_ok"):
            raise ValueError(f"block {name!r} is a canned text graphic (words on a shape, not a replica of anything real). "
                             "The default look shows a real-looking replica of what he talks about (skills/graphics). Pick or build a "
                             "replica, or set \"canned_ok\": true on it only if he asked for this exact piece.")
        box = b.get("box")
        if box is None:
            b["box"] = list(area); continue
        try:
            x, y, w, h = (float(v) for v in box)
        except (TypeError, ValueError):
            raise ValueError(f"block {name!r}: box must be [x, y, w, h] in output pixels, got {box!r}")
        why = []
        if overlaps([x, y, w, h], face_area(W, H)): why.append("it covered his face")
        elif not inside([x, y, w, h], area): why.append("it crossed the caption seam or the frame edge")
        if w < MIN_BOX_W_FRAC * W or h < MIN_BOX_H * H / 1920: why.append("it was too small to read on a phone")
        if why:
            b["box"] = list(area)
            notes.append(f"block {name} at {box} moved into the top graphic panel {area} ({'; '.join(why)})")
        else:
            b["box"] = [x, y, w, h]
    return notes


def place_overlays(overlays, W, H):
    """Logo tiles and picture cards on a split Short: a centre below the graphic area moves up into the panel."""
    notes = []
    if not is_vertical(W, H):
        return notes
    ax, ay, aw, ah = graphic_area(W, H); sc = min(W, H) / 1080
    for o in overlays:
        if o.get("y", 0) * sc > ay + ah - 120 * sc:
            old = o["y"]; o["y"] = round((ay + ah / 2) / sc, 1)
            notes.append(f"overlay at y={old:g} moved up into the top graphic panel (y={o['y']:g}); it sat on his face")
    return notes


# ------------------------------------------------------------------ on-screen text must come from what he says
STOP = set("""a an the and or but so to of in on at for with from by as is are was were be been am i you he she it we they me my
your his her its our their this that these those there here what who how when why do does did not no yes just like get got
im ive id youre thats dont cant wont its it's i'm i've don't can't won't up out if then than too very really all any some""".split())
NUM = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
       "ten": "10", "grand": "000", "k": "000", "thousand": "000"}


def _tokens(text):
    out = []
    for t in re.findall(r"[a-z0-9']+", str(text).lower().replace("’", "'")):
        t = t.strip("'")
        if not t or t in STOP or len(t) < 3 and not t.isdigit():
            continue
        out.append(t)
    return out


def _stem(t):
    t = NUM.get(t, t)
    for suf in ("ing", "ed", "es", "s", "ly"):
        if len(t) > len(suf) + 2 and t.endswith(suf):
            return t[: -len(suf)]
    return t


def strings_in(value):
    """Every piece of text in a plan value (a string, or the strings inside a list/dict), skipping colours, urls, ids."""
    if isinstance(value, str):
        v = value.strip()
        if not v or re.fullmatch(r"#[0-9a-fA-F]{3,8}|rgba?\(.*\)|https?://\S+|[\w./-]+\.(png|jpe?g|webp|svg|mp4|webm|mov|wav|mp3)|"
                                 r"[-+]?\d+(\.\d+)?(px|s|ms|%)?|(incoming|outgoing|left|right|top|bottom|center|true|false)", v):
            return []
        return [v]
    if isinstance(value, dict):
        return [s for k, v in value.items() if k not in ("side", "color", "colour", "theme", "id", "src", "avatar", "icon", "time")
                for s in strings_in(v)]
    if isinstance(value, (list, tuple)):
        return [s for v in value for s in strings_in(v)]
    return []


def unsupported_text(texts, words, t0, t1, window=4.0, need=0.6):
    """The texts shown from t0 to t1 (output seconds) whose words he doesn't say from t0-window to t1+window.
    A text passes when at least `need` of its content words (stemmed, numbers spelled either way) are spoken nearby."""
    said = {_stem(t) for w in words if w["s"] <= t1 + window and w["e"] >= t0 - window for t in _tokens(w["w"])}
    bad = []
    for text in texts:
        toks = [_stem(t) for t in _tokens(text)]
        if not toks:
            continue
        hit = sum(1 for t in toks if t in said)
        if hit / len(toks) < need:
            bad.append(text)
    return bad


def primitive_data(html_text):
    """The JSON a library block keeps in its <div hidden data-hf-primitive-data> (its sample messages, labels ...)."""
    m = re.search(r"<div[^>]*data-hf-primitive-data[^>]*>(.*?)</div>", html_text, re.S)
    if not m:
        return None
    try:
        return json.loads(re.sub(r"\s*[\r\n]+\s*", " ", m.group(1)))
    except ValueError:
        return None


def set_primitive_data(html_text, data):
    return re.sub(r"(<div[^>]*data-hf-primitive-data[^>]*>)(.*?)(</div>)",
                  lambda m: m.group(1) + "\n" + json.dumps(data, ensure_ascii=False).replace("<", "\\u003c") + "\n" + m.group(3),
                  html_text, count=1, flags=re.S)


def check_text(blocks, graphics, words, fps):
    """Errors for on-screen text he never says near that moment: each block's text (its data and vars, which include a
    library block's own sample text when the plan didn't replace it) and each text card."""
    errs = []
    for b in blocks:
        if b.get("invented_ok"):
            continue
        t0 = b["start"] / fps; t1 = (b["start"] + b["frames"]) / fps
        for text in unsupported_text(b.get("texts") or [], words, t0, t1):
            errs.append(f"block {b['name']} at {t0:.1f}s shows \"{text}\", which he doesn't say around then")
    for g in graphics:
        t0 = g["start"] / fps; t1 = (g["start"] + g["frames"]) / fps
        for text in unsupported_text([g["text"]], words, t0, t1):
            errs.append(f"text card at {t0:.1f}s shows \"{text}\", which he doesn't say around then")
    return errs
