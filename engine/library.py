"""His library: b-roll clips, pictures (dating-app screenshots, photos) and sound effects he reuses across videos.

The files live in library/broll/, library/pictures/ and library/sfx/ inside the kit (the source of truth the edits read). library/index.json lists them
with a name and tags, so Codex can place one by name ("the hinge match screenshot", "gym b-roll").
Notion is the catalogue he browses and adds to: one database, one row per item, the file attached to the row.
`kit library sync` copies rows that aren't here yet into library/. Nothing is ever written back to Notion.

The Notion database needs these properties (names are matched case-insensitively):
  Name   (title)               what he calls it
  Type   (select)              B-roll, Picture or SFX (also accepted: Broll, Photo, Image, Screenshot, Sound)
  File   (files & media)       the clip, picture or sound (an uploaded file or a link)
  Tags   (multi-select, optional)
Access: a Notion internal integration shared with that database. Its token is kept in the macOS Keychain
(service "matthew-studio-kit-notion"), or NOTION_TOKEN; it is never printed or written to a file.
"""
import datetime as dt, json, os, re, shutil, subprocess, sys, urllib.error, urllib.parse, urllib.request

ENGINE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(ENGINE)
LIB = os.path.join(KIT, "library")
INDEX = os.path.join(LIB, "index.json")
CONF = os.path.join(LIB, "notion.json")
TYPES = {"broll": "broll", "b-roll": "broll", "b roll": "broll", "video": "broll", "clip": "broll",
         "picture": "picture", "photo": "picture", "image": "picture", "screenshot": "picture", "pic": "picture",
         "sfx": "sfx", "sound": "sfx", "sound effect": "sfx", "audio": "sfx"}
EXT = {"broll": {".mp4", ".mov", ".m4v", ".webm"}, "picture": {".png", ".jpg", ".jpeg", ".webp", ".heic"},
       "sfx": {".wav", ".mp3", ".m4a", ".aiff", ".aif"}}
FOLDER = {"broll": "broll", "picture": "pictures", "sfx": "sfx"}
KEYCHAIN = "matthew-studio-kit-notion"
API = os.environ.get("NOTION_API_BASE", "https://api.notion.com/v1")


def die(msg):
    print(f"kit: {msg}", file=sys.stderr); sys.exit(1)


def load():
    try: return json.load(open(INDEX))
    except Exception: return {"items": []}


def save(idx):
    os.makedirs(LIB, exist_ok=True)
    json.dump(idx, open(INDEX + ".tmp", "w"), indent=2); os.replace(INDEX + ".tmp", INDEX)


def slug(s):
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", s.lower())).strip("-")[:60] or "item"


def _place(src, kind, name, ext):
    """Copy into library/<type>/<slug>.<ext> (a new number if that name is taken by a different file). Pictures in
    HEIC (iPhone) become PNG so every browser draws them."""
    d = os.path.join(LIB, FOLDER[kind]); os.makedirs(d, exist_ok=True)
    if ext == ".heic":
        out = os.path.join(d, slug(name) + ".png")
        subprocess.run(["sips", "-s", "format", "png", src, "--out", out], check=True, capture_output=True)
        return out
    base, n = slug(name), 1
    out = os.path.join(d, base + ext)
    while os.path.exists(out):
        n += 1; out = os.path.join(d, f"{base}-{n}{ext}")
    shutil.copy2(src, out)
    return out


def _record(kind, name, path, tags, source=None):
    idx = load()
    rel = os.path.relpath(path, KIT)
    item = {"name": name, "type": kind, "file": rel, "tags": [t for t in tags if t], "added": dt.date.today().isoformat()}
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
    return 0


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
        print(f"{it['type']:7} {it['name']}  ->  {it['file']}" + (f"  [{', '.join(it['tags'])}]" if it.get("tags") else ""))
    if not hits:
        print("nothing in the library" + (f" matching {words!r}" if words else "") + (" yet: kit library sync, or kit library add" if not idx else ""))
    return 0


# ---------------------------------------------------------------- Notion
def token():
    if os.environ.get("NOTION_TOKEN"): return os.environ["NOTION_TOKEN"]
    r = subprocess.run(["security", "find-generic-password", "-s", KEYCHAIN, "-w"], capture_output=True, text=True)
    if r.returncode or not r.stdout.strip():
        die("no Notion token yet. In Terminal (not Codex), run:\n"
            f"  security add-generic-password -U -s {KEYCHAIN} -a notion -w\n"
            "and paste the integration's secret when it asks (it isn't shown). Then: kit library sync")
    return r.stdout.strip()


def _call(method, path, body=None):
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {token()}", "Notion-Version": "2022-06-28",
                                          "Content-Type": "application/json"})
    try:
        return json.load(urllib.request.urlopen(req, timeout=60))
    except urllib.error.HTTPError as e:
        msg = e.read().decode(errors="replace")[:300]
        if e.code in (401, 403): die("Notion refused the token. Check the integration's secret, and that the database is shared with it (••• > Connections).")
        if e.code == 404: die("Notion can't find that database. Share it with the integration (••• > Connections), and check the link.")
        die(f"Notion error {e.code}: {msg}")


def db_id(link):
    low = link.lower().split("?")[0]   # ?v=<view id> is the view, not the database
    m = (re.findall(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", low)
         or re.findall(r"(?<![0-9a-f])[0-9a-f]{32}(?![0-9a-f])", low))
    if not m: die("that doesn't look like a Notion database link or id")
    h = m[0].replace("-", "")
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"


def connect(link):
    d = db_id(link)
    info = _call("GET", f"/databases/{d}")
    props = {k.lower(): v["type"] for k, v in info.get("properties", {}).items()}
    need = [p for p, t in (("name", "title"), ("type", "select"), ("file", "files")) if props.get(p) != t
            and not (p == "name" and "title" in props.values()) and not (p == "file" and "files" in props.values())]
    title = "".join(t.get("plain_text", "") for t in info.get("title", []))
    os.makedirs(LIB, exist_ok=True)
    json.dump({"database_id": d, "title": title}, open(CONF, "w"), indent=2)
    print(f"connected to Notion database \"{title}\"" + (f". Missing properties: {', '.join(need)} (see engine/library.py)" if need else ""))
    return 0


def _prop(props, want_type, names=()):
    for k, v in props.items():
        if k.lower() in names and v.get("type") == want_type: return v
    for v in props.values():
        if v.get("type") == want_type: return v
    return None


def _text(v):
    if not v: return ""
    arr = v.get(v["type"]) or []
    return "".join(t.get("plain_text", "") for t in arr) if isinstance(arr, list) else ""


def sync():
    if not os.path.exists(CONF): die("connect the Notion library first: kit library connect <database link>")
    d = json.load(open(CONF))["database_id"]
    have = {i.get("notion_id"): i for i in load()["items"] if i.get("notion_id")}
    new = skipped = 0
    cursor = None
    while True:
        res = _call("POST", f"/databases/{d}/query", {"page_size": 100, **({"start_cursor": cursor} if cursor else {})})
        for page in res.get("results", []):
            props = page.get("properties", {})
            name = _text(_prop(props, "title")) or "untitled"
            sel = (_prop(props, "select", ("type", "kind")) or {}).get("select") or {}
            kind = TYPES.get((sel.get("name") or "").lower())
            files = (_prop(props, "files", ("file", "files", "media")) or {}).get("files") or []
            tags = [t["name"] for t in ((_prop(props, "multi_select", ("tags", "tag")) or {}).get("multi_select") or [])]
            edited = page.get("last_edited_time")
            if not files:
                print(f"skip \"{name}\": no file attached in Notion yet"); skipped += 1; continue
            if page["id"] in have and have[page["id"]].get("notion_edited") == edited and os.path.exists(os.path.join(KIT, have[page["id"]]["file"])):
                continue
            f = files[0]; url = (f.get("file") or f.get("external") or {}).get("url")
            ext = os.path.splitext(urllib.parse.urlparse(url or "").path)[1].lower() or os.path.splitext(f.get("name", ""))[1].lower()
            kind = kind or next((k for k, e in EXT.items() if ext in e), None)
            if not url or kind not in EXT or ext not in EXT[kind]:
                print(f"skip \"{name}\": no usable {kind or 'file'} ({ext or 'no file type'})"); skipped += 1; continue
            tmp = os.path.join(KIT, ".cache", "notion-dl" + ext); os.makedirs(os.path.dirname(tmp), exist_ok=True)
            try:
                urllib.request.urlretrieve(url, tmp)
            except Exception as e:
                print(f"skip \"{name}\": download failed ({e})"); skipped += 1; continue
            if page["id"] in have:   # changed in Notion: replace the old copy
                old = os.path.join(KIT, have[page["id"]]["file"])
                if os.path.exists(old): os.remove(old)
            out = _place(tmp, kind, name, ext); os.remove(tmp)
            it = _record(kind, name, out, tags, {"notion_id": page["id"], "notion_edited": edited, "notion_url": page.get("url")})
            print(f"+ {kind} \"{name}\" -> {it['file']}"); new += 1
        if not res.get("has_more"): break
        cursor = res.get("next_cursor")
    print(f"library synced: {new} new or changed, {len(load()['items'])} in the library" + (f", {skipped} skipped (see above)" if skipped else ""))
    return 0
