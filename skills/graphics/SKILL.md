---
name: graphics
description: "Put graphics on screen: the logo pop, a picture card, a text card, any of about 450 HyperFrames library blocks and components, or a new GSAP graphic. Use for: add a graphic, show a chat/DM, a list on screen, a stat, make a new motion graphic."
---

# Graphics

Three kinds, all drawn by HyperFrames on the same timeline as his video, all visible in Studio before anything renders. Preview only until he says "render them" or "render 3 and 5" (skills/edit-short).

## The default look
The first preview is already designed like the real world, not like a motion-graphics pack. Faithful real-world UI replicas are always the default. Do not stop at logo_pop, picture, text_card, underline, or a fixed stack of title cards, stat stickers, lower thirds, and swipes.

1. On a vertical Short, read `TRANSCRIPT.txt` and list every concrete real-world thing he mentions (products, sites, UIs, numbers, documents). For each one, author a faithful high-fidelity HTML replica (part 3) and place it in the reserved top panel. That is the first preview. He changes it with notes; notes do not render. On a YouTube video, use a side or inset panel, or a full-screen cutaway with his face returning — never over his face (skills/long-form).
2. A replica has to pass for the real thing. A mention of Google search is a real Google results page: official wordmark, search bar with the query, real-styled listings, his page missing or buried if that is the point — animated like a screen recording (typing, results loading, a highlight or zoom on the key line). The same standard applies to ChatGPT, Stripe, email, a tweet, an analytics chart, or anything else he names. Use a reference screenshot when it helps. Never substitute an abstract card, a gold callout, or a typographic sting. Show only what the real UI would show: no fake find-in-page widgets or invented chrome, and no meta labels baked into the graphic ("reconstruction", "not specified in narration", "illustrative"). Each graphic holds at least about 1.5s. Charts use plausible, believable data — not a perfectly regular made-up shape.
3. **Check the HyperFrames library first** for every graphic: `bin/kit blocks search <words>` (the thing he mentions, e.g. `google search`, `chat`, `dashboard`, `match cut`). If a block or component looks like the real UI or is a clean transition that serves it, use it (`bin/kit blocks add <name>`, then `bin/kit blocks test <name>`) instead of hand-drawing. Keep it only if it passes the quality gate below; if it looks canned (a title card, count-up stat, sticker, lower third, word swipe), build your own replica.
4. Quality gate, before you show him anything and again after every later change (his notes, a hand edit, a rebuild): stills at the in, mid, and out of every graphic. Run `bin/kit blocks test <name> --style <style>` and look at the still it prints. After `bin/kit preview`, snapshot the Studio project at those times (from the kit folder):
   `.venv/bin/python -c "import sys; sys.path.insert(0,'engine'); import render_hf; print(render_hf.snapshot(render_hf.project_dir('<job>'), [t1, t2, t3]))"`
   Then actually open and look at those PNG files. If Codex's browser preview tool fails, stills are the required path — do not skip looking. Ask: would this pass for the real product, and does the frame look professionally designed? Redo any that fail, up to three tries, before the preview is considered ready. Never cover his face. The first quality pass is not enough.
5. A reference reel still wins for the look (skills/style). Build the graphics in that new style so the reel's captions and the real-world graphics live together. If he says "copy this reference video," match that reference on top of this same default quality (skills/style).
6. A plain "make a Short" or "make this a YouTube video" still gets this default look. Do not fall back to the old canned pack. Saved preferences (skills/style) layer on top and never replace these graphics or the quality gate.

## 1. The kit's own graphics
`bin/kit graphics list`:
- **logo_pop**: an app logo on a white tile. `kit draft` places YouTube/Instagram ones itself when the style has `logos.enabled`. More logos: put any good-looking PNG of that logo in `assets/logos/` (official, a clean copy, or remade; see `assets/logos/README.md`).
- **picture**: a still from his library on a white rounded card (skills/library).
- **text_card**: a short line on his highlight colour, near the top. Only for a line that adds something he doesn't say word for word.
Each manifest's `plan` line shows exactly what to put in `edl.json`. `bin/kit graphics test <name>` must print OK; look at the still it prints.

## 2. The HyperFrames library (about 450, free)
Ready-made animated pieces from the HyperFrames registry. **Blocks** are whole scenes with their own canvas (chat and app mock-ups, AI chats, charts, transitions). **Components** are pieces that fill whatever box they're given (a chat message, `type-match-cut`, highlights).
1. Find one: `bin/kit blocks search <words>` (e.g. `chat`, `google`, `match cut`). Each result says block or component.
2. Install it: `bin/kit blocks add <name>`. This is the supported registry intake (`hyperframes add <name> --json --no-clipboard` into `.cache/blocks/<name>/`). It needs the internet once; after that it is reused offline. Never block or wrap `hyperframes add` in a launcher.
3. Try it on his clip: `bin/kit blocks test <name>`. It must print OK; look at the still.
4. Place it in the plan: `"blocks": [{"name": "<name>", "at": <output s>, "dur": <s>, "box": [x, y, w, h], "vars": {...}}]`.
   - `box` is where it sits, in output pixels (1080x1920 on a Short, 1920x1080 on long-form). On a Short leave it out to fill the top panel. A block keeps its shape and is scaled to fit the box; a component fills the box exactly.
   - A tall block (1080x1920) scaled into the top panel can run under the caption capsule on the seam; `hyperframes check` then fails with `text_occluded`. Give it a box that stops above the seam (e.g. `[0, 0, 1080, 880]`) or pick a different block.
   - `vars` sets a block's own variables when it has them (text, colours). To change words a block has no variable for, preview first, then edit `.work/_studio/<job>/compositions/<name>.html` (that copy belongs to this video).
   - Captions stay on top of blocks. On a Short, keep a block out of his face; on long-form, put it on the side he isn't on.
5. `bin/kit preview <job>` and look.

## 3. A new graphic he asks for, or that this video needs
Build it inside the style for this video (skills/style, "Building something new"), as a block-style HTML file. On a creative ask you do this without waiting for him to name the graphic. The first preview should already include a replica of each real thing in the transcript.
1. Start from scratch when you are matching a real product UI, or from the closest library block only if it already looks like that UI. Run `bin/kit style snapshot <style>` first, then put it in `my-styles/<style>/templates/<name>/<name>.html` (a HyperFrames composition: a root `data-composition-id`, `data-width`, `data-height`, `data-duration`, and one paused GSAP timeline registered as `window.__timelines["<id>"]`). For a Short, design it at 1080×960 so it fills the top panel. Every animation must come from that timeline (no timers, no random values). **Declare its own font**: an `@font-face` inside the graphic with the font file in its own `assets/` (the page's `kitfont` is not visible to it, and HyperFrames' font check fails). Do not fetch the live product at render time; baked-in assets and HTML are fine, including a reference screenshot you saved into `assets/`.
2. Use the real product's colours, type, and layout, not only the style's `highlight_color` and `font_file`. Those style values are for captions and the frame, not for faking a Google page in Outfit and gold. Images the graphic needs go in that folder's `assets/` and are referenced as `assets/<file>`.
3. `bin/kit blocks test <name> --style <style>` must print OK. Look at the still, then run the quality gate above. The plan then uses it like any block: `"blocks": [{"name": "<name>", "at": <output s>, "dur": <s>, "vars": {...}}]` (leave `box` off on a Short so it fills the top panel). His own block wins over a library block with the same name. A graphic every style should have goes in `graphics/<name>/<name>.html` instead.
4. Add a line to the style's STYLE.md saying when it appears. Tell him it's saved.
