---
name: graphics
description: "Put graphics on screen: the logo pop, a picture card, a text card, any of about 200 HyperFrames library blocks, the premium-motion compositions, or a new GSAP graphic. Use for: add a graphic, show a chat/DM, a list on screen, a stat, go crazy, be creative, make the graphics look cool, make a new motion graphic."
---

# Graphics

Three kinds, all drawn by HyperFrames on the same timeline as his video, all visible in Studio before anything renders. Preview only until he says "render them" or "render 3 and 5" (skills/edit-short).

## When he says go crazy
"Go crazy", "be creative", "be innovative", "make the graphics look cool", or "premium" means the first preview is already designed. Do not stop at logo_pop, picture, text_card, and underline.

1. Use `premium-motion` when this is a vertical talking-head Short and he did not hand you a reference reel. Its STYLE.md says which blocks to place (kinetic label, stat, callout, lower third, swipe) and the words go in `vars`. That is the first preview. He changes it with notes; notes do not render.
2. Search the library too: `bin/kit blocks search <words>`, then `bin/kit blocks test <name> --style <style>`. Place a block that matches a chat, a list, a chart, or a title. If search fails, carry on. The style's own graphics are enough.
3. Author a new GSAP/HTML composition when neither the style nor the library covers this video (part 3). Per-video words, timing, and placement go in the plan's `blocks`. Fonts, colours, and motion stay in the HTML.
4. A reference reel still wins for the look (skills/style). Build the graphics in that new style so the reel's captions and the custom motion live together. Start from `premium-motion` when its type is close.
5. A plain "make a Short", with no creative ask and no reel, stays on `matthew`. Do not add these graphics.

## 1. The kit's own graphics
`bin/kit graphics list`:
- **logo_pop**: an app logo on a white tile. `kit draft` places YouTube/Instagram ones itself when the style has `logos.enabled`. More logos: put any good-looking PNG of that logo in `assets/logos/` (official, a clean copy, or remade; see `assets/logos/README.md`).
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

## 3. A new graphic he asks for, or that this video needs
Build it inside the style for this video (skills/style, "Building something new"), as a block-style HTML file. On a creative ask you do this without waiting for him to name the graphic. The first preview should already include it.
1. Start from the closest library block (`bin/kit blocks search`), or from scratch. Run `bin/kit style snapshot <style>` first, then put it in `my-styles/<style>/templates/<name>/<name>.html` (a HyperFrames composition: a root `data-composition-id`, `data-width`, `data-height`, `data-duration`, and one paused GSAP timeline registered as `window.__timelines["<id>"]`). Every animation must come from that timeline (no timers, no random values, no network), so every frame renders the same every time.
2. Use his colours and font: `highlight_color` and `font_file` from his style.json.
   Images it needs go in that folder's `assets/` and are referenced as `assets/<file>`.
3. `bin/kit blocks test <name> --style <style>` must print OK. Look at the still. The plan then uses it like any block: `"blocks": [{"name": "<name>", ...}]` (his own block wins over a library block with the same name). A graphic every style should have goes in `graphics/<name>/<name>.html` instead.
4. Add a line to the style's STYLE.md saying when it appears. Tell him it's saved.
