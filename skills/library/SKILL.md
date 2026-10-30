---
name: library
description: "His library of b-roll clips, pictures (dating-app screenshots, texts, photos) and sound effects, catalogued in his Notion database and copied into the kit for edits. Use for: sync my library, pull from Notion, add this b-roll, use the hinge screenshot, what b-roll do I have, connect Notion."
---

# His library

Files live in `library/broll/`, `library/pictures/` and `library/sfx/`. `library/index.json` names and tags them. Notion is the catalogue he browses and adds to; the kit copies from it and never writes back.

## Find something
`bin/kit library list [<words>] [--type broll|picture|sfx]`, e.g. `bin/kit library list hinge`. Each line shows the path to put in a plan (`library/pictures/hinge-match.png`).
Before an edit that needs library items, run `bin/kit library sync` first (when Notion is connected) so anything he added this week is here.

## Add a file he hands you
`bin/kit library add <file> --type broll|picture|sfx --name "<what he calls it>" [--tags a,b]`. iPhone HEIC pictures become PNG on the way in. If Notion is connected, tell him to also add it there so it stays in his catalogue.

## Notion
**Connect once** (needs him, in Terminal, for the secret):
1. In Notion: Settings → Connections → Develop or manage integrations → New integration ("Studio Kit", internal, read content only). Copy its secret.
2. Open his library database → ••• → Connections → add "Studio Kit".
3. In Terminal (not Codex, so the secret never goes through chat): `security add-generic-password -U -s matthew-studio-kit-notion -a notion -w`, then paste the secret when it asks. It's stored in his Mac's Keychain; never ask him to paste it in chat, and never print it.
4. `bin/kit library connect "<the database link>"`. It checks the database and says if a property is missing.

**The database** needs: **Name** (title), **Type** (select: B-roll, Picture or SFX), **File** (files & media: the upload, or a link), and optionally **Tags** (multi-select). One row per clip, picture or sound.

**Sync:** `bin/kit library sync` copies new and changed rows into `library/` and lists what it skipped and why (no file yet, a file type that doesn't match its Type).

## Using items in an edit
In the job's `edl.json` (times are output seconds, after the cuts):
- B-roll: `"broll": [{"file": "library/broll/<file>.mp4", "at": 6.2, "dur": 2.0, "from": 0.0}]` (`"layout": "pip"` or `"split"` keeps his face on screen; skills/long-form).
- Picture: `"overlays": [{"picture": "library/pictures/<file>.png", "at": 3.1, "dur": 2.5, "x": 540, "y": 640, "w": 620}]`. On a Short keep it above his head or in the top half; never over his face or the bottom button zone.
- Sound: `"sfx": [{"file": "library/sfx/<file>.wav", "at": 3.12, "gain_db": -10}]`, just after a word, never on one.
Then `bin/kit preview <job>`.

AI b-roll he makes elsewhere goes into Notion like any other clip; the kit treats it the same.
