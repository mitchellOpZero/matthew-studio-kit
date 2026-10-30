---
name: graphics
description: "Put graphics on screen: the logo pop, a picture card, a text card, any of about 200 HyperFrames library blocks (chat and app mock-ups, lists, charts, titles, transitions), or a new graphic he asks for. Use for: add a graphic, show a chat/DM, a list on screen, a stat, what graphics do I have, make a new motion graphic."
---

# Graphics

Three kinds, all drawn by HyperFrames on the same timeline as his video, all visible in Studio before anything renders.

## 1. The kit's own graphics
`bin/kit graphics list`:
- **logo_pop**: an app logo on a white tile. `kit draft` places YouTube/Instagram ones itself when the style has `logos.enabled`. More logos: put the brand's own PNG in `assets/logos/` (rules in `assets/logos/README.md`).
- **picture**: a still from his library on a white rounded card (skills/library).
- **text_card**: a short line on his highlight colour, near the top. Only for a line that adds something he doesn't say word for word.
Each manifest's `plan` line shows exactly what to put in `edl.json`. `bin/kit graphics test <name>` must print OK; look at the still it prints.

## 2. Library blocks (about 200, free)
Ready-made animated pieces from HyperFrames: chat and app mock-ups (iMessage-style, AI chats), lists, rankings, charts, number count-ups, title cards, transitions.
1. Find one: `bin/kit blocks search <words>` (e.g. `chat`, `list`, `money`, `title`).
2. Try it on his clip: `bin/kit blocks test <name>`. It must print OK; look at the still. The block is now cached in `.cache/blocks/<name>/`.
3. Place it in the plan: `"blocks": [{"name": "<name>", "at": <output s>, "dur": <s>, "box": [x, y, w, h], "vars": {...}}]`.
   - `box` is where it sits, in output pixels (1080x1920 on a Short, 1920x1080 on long-form). Leave it out for full frame. The block keeps its shape and is scaled to fit the box.
   - `vars` sets a block's own variables when it has them (text, colours). To change words a block has no variable for, preview first, then edit `.work/_studio/<job>/compositions/<name>.html` (that copy belongs to this video).
   - Captions stay on top of blocks. On a Short, keep a block out of his face; on long-form, put it on the side he isn't on.
4. `bin/kit preview <job>` and look.

## 3. A new graphic he asks for
Build it inside his style (skills/style, "Building something new"), as a block-style HTML file:
1. Start from the closest library block (`bin/kit blocks search`), or from scratch. Put it in `my-styles/<style>/templates/<name>/<name>.html` (a HyperFrames composition: a root `data-composition-id`, `data-width`, `data-height`, `data-duration`, and one paused GSAP timeline registered as `window.__timelines["<id>"]`). Every animation must come from that timeline (no timers, no random values, no network), so every frame renders the same every time.
2. Use his colours and font: `highlight_color` and `font_file` from his style.json.
   Images it needs go in that folder's `assets/` and are referenced as `assets/<file>`.
3. `bin/kit blocks test <name> --style <style>` must print OK. Look at the still. The plan then uses it like any block: `"blocks": [{"name": "<name>", ...}]` (his own block wins over a library block with the same name). A graphic every style should have goes in `graphics/<name>/<name>.html` instead.
4. Add a line to the style's STYLE.md saying when it appears. Tell him it's saved.
