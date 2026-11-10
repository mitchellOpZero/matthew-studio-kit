---
name: library
description: "His library of b-roll, pictures and sound effects, indexed from the Notion Content page he already has. Use for: my library, Notion, Content page, refresh my library, add this b-roll, Runway, Mixkit, what b-roll do I have, upload to Notion."
---

# His library

Files for an edit live in `library/broll/`, `library/pictures/` and `library/sfx/`. `library/index.json` names the local copies. His Notion Content page is the catalogue he browses. Codex reads and, when he asks, uploads into that page through the Notion connection already signed in. No new integration, no token, no Keychain entry.

Read [docs/NOTION-MCP.md](../../docs/NOTION-MCP.md) and follow it. The page is the live Content hub he already has, not a copy. The one-time setup fills in what the kit needs there.

## Connect his Content page (once)

Tell him, in this order:

1. In Notion, open the Content page he already uses (B Roll Clips, Pictures, Graphics, Styles, Videos, Posts, and the rest). Share that page with the Notion connection Codex is already signed into (••• → Connections). Do not create an integration.
2. Paste that page's URL into Codex and say: "Use the library skill to set up my Content page and build the local index."

Then you:

- Run the one-time setup in docs/NOTION-MCP.md first: list the tables on that page, run `bin/kit library setup --input hub.json`, tell him in plain words what you'll create or add, and apply it only after his OK. It reuses B Roll Clips and his Graphics table and creates Pictures and Styles if they're missing. Never delete or rename anything.

- Fetch only under that URL. Resolve each database's real id from that page. Do not search the whole workspace by name and take the first match.
- Map `broll`, `graphics`, optional `pictures`, `posts`, optional `videos`, and `styles` if that database exists and already has a title and a files property. After setup every one of these has a files field. Outside setup, never add a field.
- Save `workspace_id` and `hub_id` from that page, run `bin/kit library detect`, then the inventory, plan, and index steps in docs/NOTION-MCP.md.
- `library sync` and `library connect` are disabled. If he says "sync my library", refresh with the MCP steps instead.

## Guardrail

Writes are allowed only for the hub this session recorded (`workspace_id` and `hub_id` in the layout, `asset_upload` equal to `authorized_hub`).

- You may create a b-roll clip, a picture, or a style in that hub when he asks you to add one.
- Run `bin/kit library upload <file> --role broll|pictures|styles --name "<title>" [--origin ai|stock|own|unknown]`. Apply the JSON only if the command succeeds. Fetch the destination database and confirm the workspace and parent hub still match the plan. If they do not, or you cannot tell, stop and do not write.
- Set only the title property the upload plan names. Attach the file to the files property it names. Put the body text on the page. The upload never adds, renames or deletes properties or select options and never uploads a poster. Additional fields require an approved setup plan; additional Tags options are limited to the later B-roll writeback plan below.
- An upload carries the name he gave and nothing else. Do not describe what a clip shows in its title or tags until you have looked at its frames.
- **Adding B-roll includes titling and tagging it.** A B-roll upload plan says `completion_required: true`. After the create, in the same request and without asking again, do its `required_steps`: refresh, `library attach <new page id> <the file>`, `library sort frames`, look at every frame, `library sort apply`, then `library sort writeback` with a fresh snapshot, apply it, and read it back (sort-my-notion steps 3 to 6). Tell him the clip is added only when the read-back lists the page under `unchanged`; otherwise say it is in Notion but not yet titled and tagged, and why.
- Do not write to any other workspace, hub, or database. Do not create graphics, posts, or video-queue rows with upload.
- B-roll titles and tags: after you have looked at a clip (sort-my-notion), `bin/kit library sort writeback --input snapshot.json` plans its title, its tags and a one-time Original title for that page in the B Roll table. His request to sort, tag or add B-roll is the go-ahead; apply exactly the plan and keep every tag that is his. A plan that adds fields (`setup_required`) still waits for his OK. Details and refusals: docs/NOTION-MCP.md, "B-roll titles and tags in Notion".
- QA status stays on this Mac. `library workflow` does not change Notion, and a phrase alone never saves tags or status to Notion.

## Find something

`bin/kit library list [<words>] [--type broll|picture|sfx]` searches the local `library/` copies.
`bin/kit library find "<words>" [--kind broll|graphic|picture|style] [--origin ai|stock] [--aspect vertical|horizontal|square]` searches the Notion index. Read the score, the reasons, and the provenance before you place a file.

Before an edit that needs something he added in Notion this week, refresh the index (docs/NOTION-MCP.md), then find it. A refresh only lists his files; it never downloads them (his library can be huge). It reports `broll_labels_pending`, the B-roll that still has no reviewed title and tags: tell him the count. Download a file only when this edit uses it, then `bin/kit library attach <page_id> <file>` (docs/NOTION-MCP.md, "Using a Notion file in an edit").

B-roll is his call. Draft leaves `broll` empty unless his style turns on automatic picks (`bin/kit style set <style> broll.auto=true`; then a clip whose name or tags share a keyword with the transcript is placed). When he asks for B-roll ("put gym b-roll when I talk about the gym", "add b-roll here"), find it with `bin/kit library find` and place it in `edl.json`.

## Add a file he hands you

Local copy, for the edit: `bin/kit library add <file> --type broll|picture|sfx --name "<what he calls it>" [--tags a,b]`. iPhone HEIC pictures become PNG. HTML and SVG can be `--type picture`.

Every local visual add writes an adjacent `.poster.png` (video at about 1 second; SVG and HTML through a local browser). The index records `poster` and `notion_cover.path` with status `local_only`. Posters are not uploaded and are not a Notion column. Set `KIT_BROWSER_PATH` if Chrome is not on the default name. A poster failure stops the ingest and leaves the copied source in place.

Notion copy, when he wants it in the catalogue: upload into the authorized Content hub as above (`broll`, `pictures`, or `styles` only). Then refresh the index. Sound effects stay local.

## Getting B-roll

Tell him this when he asks where to get B-roll. AI or stock on a row is provenance, not a licence clearance. The kit then indexes the file like any other clip.

**Runway (AI B-roll).** The kit doesn't generate clips. He makes them in Runway (its app, or a Runway plugin if he has one connected), downloads the MP4, and adds it to the B Roll Clips table on his Notion Content page, or asks you to upload it there:

`bin/kit library upload <file.mp4> --role broll --name "<what he calls it>" --origin ai`

**Mixkit (free stock).** <https://mixkit.co/free-stock-video/> — search, download a free clip, same upload with `--origin stock`. Spell it Mixkit.

`--origin stock` means he is marking provenance. A find filter of `--origin stock` means the index did not decide the clip was AI. Neither one clears a licence.

## Using items in an edit

In the job's `edl.json` (times are output seconds, after the cuts):

- B-roll: `"broll": [{"file": "library/broll/<file>.mp4", "at": 6.2, "dur": 2.0, "from": 0.0}]` (`"layout": "pip"` or `"split"` keeps his face on screen; skills/long-form).
- Picture: `"overlays": [{"picture": "library/pictures/<file>.png", "at": 3.1, "dur": 2.5, "x": 540, "y": 640, "w": 620}]`. On a Short keep it above his head or in the top half; never over his face or the bottom button zone.
- Sound: `"sfx": [{"file": "library/sfx/<file>.wav", "at": 3.12, "gain_db": -10}]`, just after a word, never on one.

Then `bin/kit preview <job>`.

## Vague names / visual sorting

For `IMG_1234` and similar names, use [sort-my-notion](../sort-my-notion/SKILL.md). You view local keyframes and apply fixed-vocabulary annotations with `library sort plan`, `frames`, and `apply`. Search can show `ai.setting=...` reasons. `--ignore-body` drops body hints for a strict check. Manual overrides win. For B-roll the same review gives each clip one consistent title and descriptive tags (who is in it as woman, man or group, hair, action, setting, shot), which go to the B Roll table in Notion through `library sort writeback --input` as part of his request to sort, tag or add B-roll. Refresh the index and verify the changes with a fresh snapshot before reporting completion.
