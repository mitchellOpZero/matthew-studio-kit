"""Guards for graphics on a vertical Short, run on every build (kit preview / kit render), so a bad placement, a canned
text graphic or wrong on-screen text stops the build with a clear message instead of reaching his screen.

Two layouts for a Short with graphics (the plan's "graphic_layout", else the style's frame_layout):
  - panel (the default look): while a graphic shows, a panel on top sized to the graphic (big and sharp, no empty
    half-screen), his face below it; full face the rest of the time. Captions stay at one fixed height all video.
  - full: his face stays full frame; each graphic pops in as an overlay in the space around his face, or as a
    full-screen cutaway when there's no room. Never on his face.
Checks:
  - every block sits where the layout allows (place_blocks), at a size his phone can read
  - text-only stock pieces (accent underline, kinetic type, lower thirds ...) are flagged as canned (canned)
  - every word a graphic shows has to come from what he says around that moment (unsupported_text), including words
    typed straight into a graphic's HTML (html_texts)
  - message graphics (iMessage threads, DMs, notifications) are the exception: their texts are made up, realistic
    messages, and they must not copy his script (copied_lines)
"""
import html as _html, json, re

SEAM_FRAC = 0.045          # 2.3.6's graphic area: the top half minus the caption strip (graphic_area); a box inside it is always fine
MIN_BOX_W_FRAC = 0.6       # a block narrower than this on a Short is unreadable on a phone (the tiny notification)
MIN_BOX_H = 240            # px at 1920 tall
MIN_SCALE = 0.8            # a fixed-canvas block shrunk below this has phone-unreadable text; it is reflowed instead
PANEL_MIN_H = 440          # px at 1920: the smallest top panel (a short thread, one notification)
PANEL_DEFAULT_H = 760      # px at 1920: a graphic whose height isn't known (a component that fills its box)
FACE_ROOM = 0.22           # share of the frame height kept for his face between the panel and the captions
OVERLAY_MIN_H = 360        # px at 1920: below this there is no room for an overlay beside his face; it becomes a cutaway
EDGE = 0.04                # side margin of an overlay, share of the width
CAP_GAP = 24               # px at 1920 kept clear between a graphic and the caption line
DEFAULT_FACE = {"top": 0.16, "bottom": 0.52}   # where a talking head usually is when no face was found (share of height)
PANEL_LAYOUTS = {"split", "panel", "top-panel"}
FULL_LAYOUTS = {"full", "full-face", "fullscreen", "cutaway", "overlay"}

# text-only stock pieces: words on a coloured shape, not a replica of anything real
CANNED = re.compile(r"(underline|kinetic|lower[-_]?third|title[-_]?card|stat[-_]?count|count[-_]?up|callout|idea[-_]?swipe|"
                    r"word[-_]?(swipe|pop|stack)|text[-_]?(reveal|pop|slam|stack)|quote[-_]?card|sticker|headline|big[-_]?number)", re.I)
# a message graphic: a phone conversation or notification from someone (her texts), not an AI chat or an app screen
MESSAGE = re.compile(r"(i-?message|thread[-_]?message|message[-_]?(stack|thread|bubble)|text[-_]?(message|thread)|chat[-_]?message|"
                     r"(^|[-_])sms($|[-_])|(^|[-_])dms?($|[-_])|direct[-_]?message|notification|whatsapp|messenger|snapchat|"
                     r"(^|[-_])texts?($|[-_])|lock[-_]?screen|"
                     r"(^|[-_])(chats?|messages?|threads?|convos?|conversations?|inbox)($|[-_])|hinge|tinder|bumble)", re.I)
NOT_MESSAGE = re.compile(r"(^|[-_])(ai|gpt|chatgpt|claude|gemini|assistant|bot)($|[-_])", re.I)


def is_vertical(W, H):
    return H > W


def graphic_area(W, H):
    """[x, y, w, h] of 2.3.6's half-height panel: the top half minus the strip the caption capsule straddled. A panel is
    no longer forced to this size (panel_box); a box inside it still always passes."""
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


def is_message(block):
    """An iMessage thread, a DM, a notification, a dating-app screen: by the plan's "kind": "messages", the block's name
    (chat, messages, thread, dm, notification, hinge ...), or data / vars shaped like a conversation."""
    if str(block.get("kind") or "").lower() in {"messages", "message", "dm", "notification", "imessage"}:
        return True
    name = block.get("name") or ""
    if NOT_MESSAGE.search(name):
        return False
    if MESSAGE.search(name):
        return True
    d = block.get("data")
    if isinstance(d, dict) and isinstance(d.get("messages"), list) and any(isinstance(m, dict) and "side" in m for m in d["messages"]):
        return True
    v = block.get("vars")   # a graphic built for this video that takes its thread as a variable ("messages": "sent:...|recv:...")
    return isinstance(v, dict) and bool(v.get("messages"))


def graphic_layout(edl, st):
    """'panel' or 'full' for a Short's graphics: the plan's graphic_layout (his choice for this video), else the style's
    frame_layout. 'panel' unless something says full."""
    v = str((edl or {}).get("graphic_layout") or st.get("graphic_layout") or st.get("frame_layout") or "panel").strip().lower()
    return "full" if v in FULL_LAYOUTS else "panel"


def caption_top(cap_y, cap_h, H):
    """The top edge (px) of the fixed caption line: its centre cap_y (share of height) minus half its tallest height."""
    return cap_y * H - cap_h / 2


def panel_max(H, cap_top):
    """The tallest top panel: down to the caption line minus room for his face, never shorter than PANEL_MIN_H."""
    return max(PANEL_MIN_H * H / 1920, min(0.62 * H, cap_top - CAP_GAP * H / 1920 - FACE_ROOM * H))


def natural_h(block, meta, W, H):
    """How tall a block wants its panel (px): the plan's panel_h, a message list's own height, a fixed canvas at the
    full width, or PANEL_DEFAULT_H for a component that fills any box."""
    if block.get("panel_h"):
        return float(block["panel_h"]) * H / 1920
    d = block.get("data")
    if isinstance(d, dict) and isinstance(d.get("messages"), list):
        lines = sum(1 + len(str(m.get("text", "")) if isinstance(m, dict) else "") // 26 for m in d["messages"])
        return (150 + 92 * lines + 40 * len(d["messages"])) * H / 1920
    if meta and not meta.get("fluid") and meta.get("w") and meta.get("h"):
        return W * meta["h"] / meta["w"]
    return PANEL_DEFAULT_H * H / 1920


def panel_box(block, meta, W, H, cap_top):
    """[0, 0, W, h]: the block's panel, sized to the block between PANEL_MIN_H and panel_max."""
    lo, hi = PANEL_MIN_H * H / 1920, panel_max(H, cap_top)
    return [0, 0, W, int(max(lo, min(hi, natural_h(block, meta, W, H))))]


def face_box(face, W, H):
    """His face in the full frame [x, y, w, h] (px), padded, from face_focus ({top, bottom} shares of height)."""
    f = face or DEFAULT_FACE
    pad = 0.04 * H
    top, bot = max(0.0, f["top"] * H - pad), min(float(H), f["bottom"] * H + pad)
    return [0, top, W, bot - top]


def overlay_box(face, W, H, cap_top):
    """Where an overlay pops in on a full-face Short: the bigger space above or below his face (above the captions),
    with side margins. None when neither is tall enough (the graphic becomes a full-screen cutaway)."""
    fx, fy, fw, fh = face_box(face, W, H)
    m, top_m = round(EDGE * W), round(0.03 * H)
    above = (top_m, fy - CAP_GAP * H / 1920)
    below = (fy + fh, cap_top - CAP_GAP * H / 1920)
    y0, y1 = max((above, below), key=lambda r: r[1] - r[0])
    if y1 - y0 < OVERLAY_MIN_H * H / 1920:
        return None
    return [m, int(round(y0)), W - 2 * m, int(round(y1 - y0))]


def place_blocks(blocks, W, H, layout="panel", cap_top=None, face=None, metas=None):
    """Every block's box on a vertical Short, checked and fixed in place. Returns notes.
    panel: no box, or a box over his face, across the caption line, or too small, gets the panel sized to the block.
    full: "show": "cutaway" fills the frame; otherwise the overlay space around his face, or a cutaway when there's none.
    A text-only canned piece stops the build unless the plan says he asked for it ("canned_ok": true)."""
    notes = []
    if not is_vertical(W, H):
        return notes
    if cap_top is None:
        cap_top = H / 2
    for i, b in enumerate(blocks):
        name = b.get("name", "")
        if canned(name) and not b.get("canned_ok"):
            raise ValueError(f"block {name!r} is a canned text graphic (words on a shape, not a replica of anything real). "
                             "The default look shows a real-looking replica of what he talks about (skills/graphics). Pick or build a "
                             "replica, or set \"canned_ok\": true on it only if he asked for this exact piece.")
        meta = (metas or {}).get(i)
        box = b.get("box")
        if box is not None:
            try:
                box = [float(v) for v in box]
                assert len(box) == 4
            except (TypeError, ValueError, AssertionError):
                raise ValueError(f"block {name!r}: box must be [x, y, w, h] in output pixels, got {b.get('box')!r}")
        small = lambda bx: bx[2] < MIN_BOX_W_FRAC * W or bx[3] < MIN_BOX_H * H / 1920
        if layout == "full":
            fb = face_box(face, W, H)
            if str(b.get("show") or "").lower() == "cutaway":
                b["box"], b["show"] = [0, 0, W, H], "cutaway"; continue
            if box is not None and not overlaps(box, fb) and not small(box) and box[1] + box[3] <= cap_top + 1:
                b["box"], b["show"] = box, "overlay"; continue
            ob = overlay_box(face, W, H, cap_top)
            b["box"], b["show"] = (ob, "overlay") if ob else ([0, 0, W, H], "cutaway")
            if ob: _fit_tall(b, meta, W, H)
            if box is not None:
                notes.append(f"block {name} at {[round(v) for v in box]} would cover his face, the captions, or be too small; "
                             f"shown as {'an overlay at ' + str(ob) if ob else 'a full-screen cutaway'}")
            continue
        b["show"] = "panel"
        pb = panel_box(b, meta, W, H, cap_top)
        if box is None:
            b["box"] = pb; _fit_tall(b, meta, W, H); continue
        why = []
        lim = max(pb[3], panel_max(H, cap_top))
        if box[1] + box[3] > lim + 1:
            why.append("it reached down onto his face or the captions")
        elif not inside(box, [0, 0, W, lim]):
            why.append("it went past the frame edge")
        if small(box): why.append("it was too small to read on a phone")
        if why:
            b["box"] = pb
            notes.append(f"block {name} at {[round(v) for v in box]} moved into the top panel {pb} ({'; '.join(why)})")
        else:
            b["box"] = box
    return notes


def _fit_tall(b, meta, W, H):
    """A graphic taller than the space it got (a long thread in a short gap) is laid out a little taller and mounted
    slightly smaller (never below MIN_SCALE), so nothing is cut off; below that it's laid out at the box as is."""
    if meta and meta.get("fluid") and not isinstance((b.get("data") or {}).get("messages"), list):
        return
    nh = natural_h(b, meta, W, H)
    k = b["box"][3] / nh if nh else 1.0
    if k < 0.999:
        b["reflow_scale"] = round(max(MIN_SCALE, k), 4)


def place_overlays(overlays, W, H, cap_top=None):
    """Logo tiles and picture cards on a panel Short: a centre down on his face or the captions moves up above them."""
    notes = []
    if not is_vertical(W, H):
        return notes
    sc = min(W, H) / 1080
    lim = panel_max(H, cap_top if cap_top is not None else H / 2)
    for o in overlays:
        if o.get("y", 0) * sc > lim - 120 * sc:
            old = o["y"]; o["y"] = round(lim / 2 / sc, 1)
            notes.append(f"overlay at y={old:g} moved up above his face (y={o['y']:g})")
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


# words a real app screen shows on its own (its chrome), not claims: ignored when a graphic's HTML text is checked
UI_CHROME = set("""imessage message messages text sms delivered read seen today yesterday now typing online active offline
assistant ask anything send sent reply search google results result images videos news maps shopping more tools settings
new editor ready edit done cancel back next home inbox notification notifications unread mark close open share copy like
likes follow following followers view views comment comments post posts profile chat chatgpt gpt claude gemini dashboard
menu tab tabs account sign login log save saved delete archive draft drafts compose subject mail gmail email stripe
payments balance revenue total week month year day hour minute min mins ago sec pm am mon tue wed thu fri sat sun jan feb
mar apr may jun jul aug sep oct nov dec""".split())


def html_texts(html_text):
    """The words a graphic's HTML puts on screen by itself: text between tags, plus placeholder values, skipping <head>, <script>, <style>, comments, the hidden data block, and elements marked data-ui (app chrome)."""
    s = re.sub(r"<!--.*?-->", "", html_text, flags=re.S)
    s = re.sub(r"<(head|script|style|title|template|svg)\b.*?</\1\s*>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<div[^>]*data-hf-primitive-data[^>]*>.*?</div>", " ", s, flags=re.S)
    s = re.sub(r"<(\w+)\b[^>]*\bdata-ui\b[^>]*>.*?</\1\s*>", " ", s, flags=re.S | re.I)
    out = [m.group(2) for m in re.finditer(r"\b(placeholder)\s*=\s*\"([^\"]*)\"", s, re.I)]
    out += [t for t in re.split(r"<[^>]*>", s)]
    out = [re.sub(r"\s+", " ", _html.unescape(t)).strip() for t in out]
    keep = []
    for t in out:
        if not t or re.fullmatch(r"[\d\s:.,%$€£+\-/·•|▶►◀✓✔×]*(am|pm)?", t, re.I):
            continue
        if all(_stem(w) in UI_CHROME or w in UI_CHROME for w in _tokens(t)):
            continue
        keep.append(t)
    return keep


def _norm_words(text):
    return re.findall(r"[a-z0-9']+", str(text).lower().replace("’", "'"))


def copied_lines(texts, words, need=0.7):
    """Message texts that copy his script: the message (3+ words) appears in what he says word for word or with a word or
    two swapped, or most of its content words (3+) are said together within a stretch about the message's length."""
    spoken = [w for x in words for w in _norm_words(x["w"])]
    joined = " " + " ".join(spoken) + " "
    stems = [_stem(t) if t not in STOP and (len(t) >= 3 or t.isdigit()) else None for t in spoken]
    bad = []
    for text in texts:
        ws = _norm_words(text)
        if len(ws) >= 3 and " " + " ".join(ws) + " " in joined:
            bad.append(text); continue
        if len(ws) >= 3 and any(sum(a == c for a, c in zip(ws, spoken[i:i + len(ws)])) >= max(3, 0.75 * len(ws))
                                for i in range(len(spoken) - len(ws) + 1)):
            bad.append(text); continue   # his line with a word or two swapped ("booked a call with you")
        toks = {_stem(t) for t in _tokens(text)}
        if len(toks) < 3:
            continue
        span = len(ws) + 4
        for i in range(max(1, len(stems) - span + 1)):
            win = {t for t in stems[i:i + span] if t}
            if len(toks & win) / len(toks) >= need:
                bad.append(text); break
    return bad


META_LABEL = re.compile(r"\b(fictional|fictitious|illustrative|hypothetical|placeholder|lorem ipsum|for illustration|not (a )?real|"
                        r"mock[- ]?up|(sample|example|demo|fake|made[- ]up|test) (chat|dm|dms|message|messages|text|texts|thread|"
                        r"conversation|convo|profile|notification|post|account|user|contact))\b", re.I)


def meta_labels(texts):
    """On-screen text that says the graphic is made up ("Fictional DM", "Illustrative example", "Sample chat"). A graphic
    passes for the real thing: a real-looking name and the app's own header, never a label about itself."""
    return [t for t in texts if META_LABEL.search(str(t))]


def check_text(blocks, graphics, words, fps):
    """Errors for on-screen text. A normal graphic's text (its data and vars, which include a library block's own sample
    text when the plan didn't replace it, and words typed into its HTML) and each text card must be words he says near
    that moment. A message graphic's texts are made up, so they skip that check, but must not copy his script."""
    errs = []
    for b in blocks:
        if b.get("tryout"):   # bin/kit blocks test: the block's own sample text, on a throwaway clip
            continue
        t0 = b["start"] / fps; t1 = (b["start"] + b["frames"]) / fps
        texts = list(b.get("texts") or []) + [t for t in (b.get("html_texts") or []) if t not in (b.get("texts") or [])]
        for text in meta_labels(texts):
            errs.append(f"graphic {b['name']} at {t0:.1f}s labels itself: \"{text}\". A graphic never says it is fictional, an "
                        "example or a sample; give it a real-looking name and the app's own header")
        if b.get("message"):
            if b.get("needs_data"):
                errs.append(f"message graphic {b['name']} at {t0:.1f}s still shows its saved sample texts; write fresh made-up "
                            "texts for this video in its \"data\" (realistic texts from her, not his script)")
            for text in copied_lines(texts, words):
                errs.append(f"message graphic {b['name']} at {t0:.1f}s copies his script: \"{text}\". Make up a realistic text "
                            "from her instead (never his lines)")
            continue
        if b.get("invented_ok"):
            continue
        for text in unsupported_text(texts, words, t0, t1):
            errs.append(f"block {b['name']} at {t0:.1f}s shows \"{text}\", which he doesn't say around then")
    for g in graphics:
        t0 = g["start"] / fps; t1 = (g["start"] + g["frames"]) / fps
        for text in meta_labels([g["text"]]):
            errs.append(f"text card at {t0:.1f}s labels itself: \"{text}\". Never say a graphic is fictional, an example or a sample")
        for text in unsupported_text([g["text"]], words, t0, t1):
            errs.append(f"text card at {t0:.1f}s shows \"{text}\", which he doesn't say around then")
    return errs
