"""Local media copies and index.

Notion is reached only through Codex's existing Notion connection (docs/NOTION-MCP.md).
No integration token, environment credential, Keychain item or direct HTTP client.
connect and sync stay disabled. Adding a file to the authorized Content hub is
`kit library upload`, which plans one create and does not perform it.
"""
import datetime as dt, json, os, re, shutil, subprocess, sys

ENGINE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(ENGINE)
LIB = os.path.join(KIT, "library")
INDEX = os.path.join(LIB, "index.json")
TYPES = {"broll": "broll", "b-roll": "broll", "b roll": "broll", "video": "broll", "clip": "broll",
         "picture": "picture", "photo": "picture", "image": "picture", "screenshot": "picture", "pic": "picture",
         "sfx": "sfx", "sound": "sfx", "sound effect": "sfx", "audio": "sfx"}
EXT = {"broll": {".mp4", ".mov", ".m4v", ".webm", ".ogv"}, "picture": {".png", ".jpg", ".jpeg", ".webp", ".heic", ".svg", ".html"},
       "sfx": {".wav", ".mp3", ".m4a", ".aiff", ".aif"}}
FOLDER = {"broll": "broll", "picture": "pictures", "sfx": "sfx"}


def die(msg):
    print(f"kit: {msg}", file=sys.stderr); sys.exit(1)


def load():
    try: return json.load(open(INDEX))
    except Exception: return {"items": []}


def save(idx):
    os.makedirs(LIB, exist_ok=True)
    with open(INDEX + ".tmp", "w") as stream:
        json.dump(idx, stream, indent=2)
    os.replace(INDEX + ".tmp", INDEX)


def slug(s):
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", s.lower())).strip("-")[:60] or "item"


def _place(src, kind, name, ext):
    """Copy into library/<type>/<slug>.<ext> (a new number if that name is taken by a different file). Pictures in
    HEIC (iPhone) become PNG so every browser draws them."""
    d = os.path.join(LIB, FOLDER[kind]); os.makedirs(d, exist_ok=True)
    heic = ext == ".heic"
    ext = ".png" if heic else ext
    base, n = slug(name), 1
    out = os.path.join(d, base + ext)
    while os.path.exists(out):
        n += 1; out = os.path.join(d, f"{base}-{n}{ext}")
    if heic:
        subprocess.run(["sips", "-s", "format", "png", src, "--out", out], check=True, capture_output=True)
    else:
        shutil.copy2(src, out)
    return out


def _record(kind, name, path, tags, source=None):
    idx = load()
    rel = os.path.relpath(path, KIT)
    item = {"name": name, "type": kind, "file": rel, "tags": [t for t in tags if t], "added": dt.date.today().isoformat()}
    if kind != "sfx":
        from poster import make_poster
        try:
            poster = make_poster(path)
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            detail = getattr(exc, "stderr", "") or str(exc)
            if isinstance(detail, bytes): detail = detail.decode(errors="replace")
            die(f"poster generation failed for {rel}: {detail[-600:]}")
        item["poster"] = os.path.join(os.path.dirname(rel), os.path.basename(poster))
        item["notion_cover"] = {"path": item["poster"], "status": "local_only"}
    if source: item.update(source)
    idx["items"] = [i for i in idx["items"] if not (source and i.get("notion_id") == source.get("notion_id"))] + [item]
    save(idx)
    return item


def add(path, kind, name, tags=""):
    kind = TYPES.get(kind.lower(), kind.lower())
    if kind not in EXT: die("type must be broll, picture or sfx")
    if not os.path.isfile(path): die(f"no file {path}")
    ext = os.path.splitext(str(path))[1].lower()
    if ext not in EXT[kind]: die(f"a {kind} must be one of {', '.join(sorted(EXT[kind]))} (got {ext})")
    out = _place(str(path), kind, name, ext)
    it = _record(kind, name, out, [t.strip() for t in tags.split(",")])
    print(f"added {kind} \"{name}\": {it['file']}  (use it in a plan as \"{it['file']}\")")
    if it.get("poster"): print(f"poster: {it['poster']} (Notion cover: local only)")
    return 0


def _length(rel):
    """A clip's length, so b-roll is never asked to play past its end."""
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", os.path.join(KIT, rel)],
                           capture_output=True, text=True, timeout=20)
        return f"{float(r.stdout.strip()):.1f} s"
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return "length unknown"


def _tokens(text):
    return set(re.findall(r"[a-z0-9]+", (text or "").lower()))


def _notion_broll():
    """Clips already indexed from the authorized hub. Missing index means nothing to place."""
    path = os.path.join(os.path.expanduser("~"), ".matthew-studio-kit", "notion_index.json")
    alt = os.environ.get("KIT_NOTION_INDEX")
    found = []
    for candidate in (alt, path):
        if not candidate or not os.path.isfile(candidate):
            continue
        try:
            data = json.load(open(candidate))
        except (OSError, json.JSONDecodeError):
            continue
        for entry in (data.get("entries") or {}).values():
            if entry.get("stale") or entry.get("exclude"):
                continue
            if entry.get("role") != "broll" and entry.get("kind") != "broll":
                continue
            file_path = entry.get("path") or ""
            if not file_path:
                continue
            tags = entry.get("explicit_tags") or []
            title = entry.get("title") or entry.get("file_name") or ""
            found.append({"file": file_path, "name": title, "tags": tags,
                          "hay": _tokens(" ".join([title, " ".join(tags), entry.get("file_name") or ""]))})
        break
    return found


def broll_candidates():
    """Local library clips first, then the Notion index if one has been built on this Mac."""
    found = []
    for it in load().get("items") or []:
        if it.get("type") != "broll" or not it.get("file"):
            continue
        tags = it.get("tags") or []
        name = it.get("name") or ""
        found.append({"file": it["file"], "name": name, "tags": tags,
                      "hay": _tokens(" ".join([name, " ".join(tags), it["file"]]))})
    found.extend(_notion_broll())
    return found


def select_broll(words, keywords, cuts, limit=4, dur=2.0):
    """Put matching library clips on the keyword lines. No match, or an empty library, leaves the list empty."""
    cands = broll_candidates()
    if not cands or not cuts or not keywords:
        return []

    def output_time(t):
        acc = 0.0
        for c in cuts:
            if c["in"] <= t <= c["out"]:
                return acc + (t - c["in"])
            if t < c["in"]:
                return None
            acc += c["out"] - c["in"]
        return None

    used, placed = set(), []
    for key in keywords:
        q = _tokens(key)
        if not q:
            continue
        spoke = next((w for w in words if q <= _tokens(w.get("w") or "")), None)
        if not spoke:
            continue
        best, score = None, 0
        for cand in cands:
            if cand["file"] in used:
                continue
            hit = len(q & cand["hay"])
            if hit > score:
                best, score = cand, hit
        if not best:
            continue
        at = output_time(float(spoke.get("start", spoke.get("s", 0))))
        if at is None or any(abs(p["at"] - at) < dur - 0.05 for p in placed):
            continue
        placed.append({"file": best["file"], "at": round(at, 3), "dur": dur, "from": 0.0})
        used.add(best["file"])
        if len(placed) >= limit:
            break
    return placed


def list_items(words="", kind=None):
    idx = load()["items"]
    ws = [w for w in re.findall(r"[a-z0-9]+", words.lower())]
    hits = []
    for it in idx:
        if kind and it["type"] != kind: continue
        hay = " ".join([it["name"], " ".join(it.get("tags", [])), it["file"]]).lower()
        score = sum(w in hay for w in ws)
        if ws and not score: continue
        hits.append((score, it))
    for _, it in sorted(hits, key=lambda x: (-x[0], x[1]["type"], x[1]["name"])):
        print(f"{it['type']:7} {it['name']}  ->  {it['file']}" + (f"  ({_length(it['file'])})" if it["type"] in ("broll", "sfx") else "")
              + (f"  [{', '.join(it['tags'])}]" if it.get("tags") else ""))
    if not hits:
        print("nothing in the library" + (f" matching {words!r}" if words else "") + (" yet: Codex Notion refresh, or kit library add" if not idx else ""))
    return 0


# Old Keychain entry points. They fail before any credential, file or network access.
def connect(link):
    die("Notion uses the Codex Notion connection, not a token. See docs/NOTION-MCP.md.")


def sync():
    die("Direct sync is disabled. Ask Codex to refresh the authorized Content hub (docs/NOTION-MCP.md).")
