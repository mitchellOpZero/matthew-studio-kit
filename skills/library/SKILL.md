---
name: library
description: "His library of b-roll, pictures and sound effects, indexed from the Notion Content page he already has. Use for: my library, Notion, Content page, refresh my library, add this b-roll, Runway, Mixkit, what b-roll do I have, upload to Notion."
---

# His library

Files for an edit live in `library/broll/`, `library/pictures/` and `library/sfx/`. `library/index.json` names the local copies. His Notion Content page is the catalogue he browses. Codex reads and, when he asks, uploads into that page through the Notion connection already signed in. No new integration, no token, no Keychain entry.

Read [docs/NOTION-MCP.md](../../docs/NOTION-MCP.md) and follow it. The page is the live Content hub he already has, not a new database and not a copy.

## Connect his Content page (once)

Tell him, in this order:

1. In Notion, open the Content page he already uses (B Roll Clips, Pictures, Graphics, Styles, Videos, Posts, and the rest). Share that page with the Notion connection Codex is already signed into (••• → Connections). Do not create an integration.
2. Paste that page's URL into Codex and say: "Use the library skill to configure my existing Content hub and build the local index. Do not add columns."

Then you:

- Fetch only under that URL. Resolve each database's real id from that page. Do not search the whole workspace by name and take the first match.
- Map `broll`, `graphics`, optional `pictures`, `posts`, optional `videos`, and `styles` if that database exists and already has a title and a files property. If Styles has no files property, leave it unmapped. Never add a column.
- Save `workspace_id` and `hub_id` from that page, run `bin/kit library detect`, then the inventory, plan, and index steps in docs/NOTION-MCP.md.
- `library sync` and `library connect` are disabled. If he says "sync my library", refresh with the MCP steps instead.

## Guardrail

Writes are allowed only for the hub this session recorded (`workspace_id` and `hub_id` in the layout, `asset_upload` equal to `authorized_hub`).

- You may create a b-roll clip, a picture, or a style in that hub when he asks you to add one.
- Run `bin/kit library upload <file> --role broll|pictures|styles --name "<title>" [--origin ai|stock|own|unknown]`. Apply the JSON only if the command succeeds. Fetch the destination database and confirm the workspace and parent hub still match the plan. If they do not, or you cannot tell, stop and do not write.
- Set only the title property the plan names. Attach the file to the files property it names. Put the body text on the page. Do not add, rename, or delete properties, do not create select options, and do not upload a poster.
- Do not write to any other workspace, hub, or database. Do not create graphics, posts, or video-queue rows with upload.
- Visual-sort tags and QA status stay on this Mac. `library sort writeback` and `library workflow` do not change Notion. Ignore any older phrase that asked to save tags or status back to Notion.

## Find something

`bin/kit library list [<words>] [--type broll|picture|sfx]` searches the local `library/` copies.
`bin/kit library find "<words>" [--kind broll|graphic|picture|style] [--origin ai|stock] [--aspect vertical|horizontal|square]` searches the Notion index. Read the score, the reasons, and the provenance before you place a file.

Before an edit that needs something he added in Notion this week, refresh the index (docs/NOTION-MCP.md), then find it.

Draft places b-roll on its own when a library clip's name or tags share a keyword with the transcript. `edl.json` `broll` stays empty when nothing matches. You can still move or replace those picks.

## Add a file he hands you

Local copy, for the edit: `bin/kit library add <file> --type broll|picture|sfx --name "<what he calls it>" [--tags a,b]`. iPhone HEIC pictures become PNG. HTML and SVG can be `--type picture`.

Every local visual add writes an adjacent `.poster.png` (video at about 1 second; SVG and HTML through a local browser). The index records `poster` and `notion_cover.path` with status `local_only`. Posters are not uploaded and are not a Notion column. Set `KIT_BROWSER_PATH` if Chrome is not on the default name. A poster failure stops the ingest and leaves the copied source in place.

Notion copy, when he wants it in the catalogue: upload into the authorized Content hub as above (`broll`, `pictures`, or `styles` only). Then refresh the index. Sound effects stay local.

## Getting B-roll

Tell him this when he asks where to get B-roll. AI or stock on a row is provenance, not a licence clearance. The kit then indexes the file like any other clip.

**Runway (primary AI B-roll).** Generate the clip in Runway, download the MP4, then either he adds it to his Notion B Roll database, or he asks you to upload it into the authorized Content hub:

`bin/kit library upload <file.mp4> --role broll --name "<what it shows>" --origin ai`

**Mixkit (free stock).** <https://mixkit.co/free-stock-video/> — search, download a free clip, same upload with `--origin stock`. Spell it Mixkit.

`--origin stock` means he is marking provenance. A find filter of `--origin stock` means the index did not decide the clip was AI. Neither one clears a licence.

## Using items in an edit

In the job's `edl.json` (times are output seconds, after the cuts):

- B-roll: `"broll": [{"file": "library/broll/<file>.mp4", "at": 6.2, "dur": 2.0, "from": 0.0}]` (`"layout": "pip"` or `"split"` keeps his face on screen; skills/long-form).
- Picture: `"overlays": [{"picture": "library/pictures/<file>.png", "at": 3.1, "dur": 2.5, "x": 540, "y": 640, "w": 620}]`. On a Short keep it above his head or in the top half; never over his face or the bottom button zone.
- Sound: `"sfx": [{"file": "library/sfx/<file>.wav", "at": 3.12, "gain_db": -10}]`, just after a word, never on one.

Then `bin/kit preview <job>`.

## Vague names / visual sorting

For `IMG_1234` and similar names, use [sort-my-notion](../sort-my-notion/SKILL.md). You view local keyframes and apply fixed-vocabulary annotations with `library sort plan`, `frames`, and `apply`. Search can show `ai.setting=...` reasons. `--ignore-body` drops body hints for a strict check. Manual overrides win. Those annotations stay on this Mac.
