---
name: style
description: "Change anything about how his videos look or sound, or make a new look: captions (size, colour, stacking, boxes, fonts, highlights, animation), zooms, logos, motion graphics, layout, sound. Also: make a style from a reference reel, list styles, undo a change, go back to an old version. Use for: captions smaller, stack the captions, change my style, add a graphic to my style, make it look like this reel, undo that."
---

# Customize a style

He can change anything he wants. **Never answer "the kit can't do that".** Either change a setting, or build what's missing inside the style. Then test it, preview it, and save it the way he chooses.

A style is a folder: `styles/<name>/` (built in) or `my-styles/<name>/` (his saved copies; the kit reads his copy first, and updates never touch it):
- `style.json`: settings (below)
- `STYLE.md`: the look in plain words, plus per-video rules ("logo pop when he names an app", "a stat card when he gives a number"). skills/edit-short follows it on every edit.
- `templates/<name>/`: pieces that belong to this style: a caption design (`captions.css` + `captions.js`), or a graphic (`<name>.html`, see skills/graphics)
- `fonts/`: fonts this style brings
- `versions/`: full copies from before each save

`matthew` is the default and was built from what Matthew asked for; `matthew-long` is the same look for 16:9 long-form. `bin/kit style list` shows every style. Styles he made in the old Matthew Edit Kit come over with `bin/kit style import ~/ColdApproach/matthew-edit-kit` (it says if anything has to be rebuilt).

## Steps for any change
1. Understand what he wants. If it's vague ("make it pop more"), make a sensible choice and show him. Don't quiz him.
2. **Saving.**
   - He asked to change the look ("make my captions smaller", "make my captions red again"): apply it as a **preference** on top of the default look, and save it so it sticks. Write caption and similar refinements to `my-styles/preferences.json` (only keys in `engine/quick_edit.py` `PREF_KEYS` — font, colour, caption size, and the like). Never replace the default graphics, layout, or quality gate, and never switch him back to the old canned pack. Do not ask "save over or save as."
   - If he says "copy this reference video," build that look as refinements on top of the same default quality (see "A style from a reference reel" below, phrased plainly to him as copying the reference).
   - Never edit files in `styles/` on his Mac. A later update is a fast-forward pull. `bin/kit style snapshot <name>` copies a built-in style into `my-styles/` before you add a template.
3. Make the change:
   - **A setting covers it:** `bin/kit style set <style> key=value ... [--as <new-name>]`. The command draws the style on his clip and only saves if it draws cleanly. If it fails, nothing changes.
   - **Nothing covers it:** build it (see "Building something new"). Run `bin/kit style snapshot <style>` before editing files, and for a new style run `bin/kit style new <new-name> --from <style>` first. Afterwards, `bin/kit style test <style>` must print OK. If it doesn't, fix it, or put it back with `bin/kit style undo <style>`.
4. `kit style set` writes a dated line under "Changes Matthew asked for" in the style's `STYLE.md` by itself (e.g. `2026-10-30: font_size_frac 0.093 -> 0.0837`). For a change you built by hand (a template, a rule in STYLE.md), add one line yourself in his words, e.g. `2026-10-28: captions stacked on two lines`.
5. Preview: `bin/kit style preview <style>` (3 s of his last clip, live in Studio, plus a still). **Look at the still yourself first.** The test only proves it draws, not that it looks right: check that the text is the size you meant, the colours are right, and nothing covers his face or runs off the edge. Fix anything wrong, then give him the Studio link.
6. **"Undo that" / "go back"** (in this chat or a new one): `bin/kit style undo` (or `bin/kit style undo <style>` if he names one). With no name it undoes the style he changed last. Don't ask what to undo. It puts back the version from before his newest change, prints what it undid, and logs it; tell him in one line ("Undid: captions 10% smaller"). Saying it again goes one change further back. A save the kit rejected is never in the undo list.
   - "Go back to how it was yesterday": `bin/kit style versions <style>`, then `bin/kit style restore <style> <the first version stamped today>` (each version is the style as it was just before that save). If nothing is stamped today, nothing changed since yesterday.
   - A restore is itself a change, so `bin/kit style undo` takes it back.

## Notion Styles
`bin/kit style push <name>` prints a plan whose body is that style's `style.json`, for the Styles database on the Content page authorized in this session. It does not call Notion. Codex applies the plan only when the workspace and hub still match. `bin/kit style pull <page.json> --as <name>` writes the page's style JSON into `my-styles/<name>/style.json`. A different workspace or hub is refused.

## Settings (style.json); combine freely
Values are JSON: `0.08`, `"#FF0000"`, `true`, `{"color": "#000000", "opacity": 0.7}`. Dotted keys reach inside: `punch.zoom_tight=1.25`.
- **Caption size and place**
  - `font_size_frac`: share of frame height. 0.093 is his 1.5x size.
  - `center_y_frac`: 0.64 is chest level.
  - `one_line`: shrink a line to fit instead of wrapping.
- **Caption layout**
  - `max_words`: words per caption.
  - `lines`: stacked lines, 1-4.
  - `words_per_line`
  - `max_chars`: per line.
  - `min_chunk_s`: shortest time a caption stays up.
  - `caption_breaks`: per video, in edl.json.
- **Caption look**
  - `color`, `highlight_color`, `stroke`, `stroke_color`, `shadow`, `uppercase`
  - A box behind the caption isn't a setting in this kit (`box` is refused): build it as a caption design (below, "Building something new"), with the box in `captions.css`.
  - `font`: family name. `font_file`: in assets/fonts or the style's fonts/.
- **Highlight**
  - `highlight_mode`: `keywords` (Codex picks per video), `every_word` (karaoke) or `none`.
  - `kw_sync_pop`: the colour lands as the word is spoken.
  - `kw_pop_pct`: the keyword pops this % bigger as it's spoken, then settles (0 = no pop).
  - `keyword_scale`: keywords drawn this much bigger than the other words (1.0 = same size, 1.15 = 15% bigger).
- **Caption motion**
  - `pop_scale`, `pop_ms`: how a caption pops in.
  - Every word popping as it's spoken isn't a setting in this kit (`word_pop` is refused): build it as a caption design (a `tl.fromTo` scale on each `.w` at its `at`).
- **Zooms**
  - `punch.zoom_wide`, `punch.zoom_tight`
  - `punch.every_s`: how often it switches.
  - `punch.anchor_y`: head position.
- **Logos:** `logos.enabled`, and `logos.<app>` = a PNG in assets/logos.
- **Text cards:** `graphic.size_frac`, `graphic.y_frac`, `graphic.box_color`, `graphic.text_color`.
- **Shape:** `shape` = `"16:9"` makes `kit draft` start a landscape (long-form) edit with this style.
- **Faces:** `avoid_faces` (on unless set to `false`): captions move just below his face when it reaches them.
- **Sound:** `loudness.I` (−14 default).
- `_about`: one sentence on what the style is.

## Building something new (when no setting covers it)
Build it inside the style folder. **Never edit `engine/`.** A new piece must pass `bin/kit style test <style>`.
- **A different caption design** (per-word boxes, two colours, captions that slide in, an underline, etc.): a caption design.
  1. `bin/kit style snapshot <style>` first (it also makes his own copy of a built-in style, so undo works). Then make `my-styles/<style>/templates/<name>/` with `manifest.json` (`"kind": "captions"`), `captions.css` and `captions.js`. `graphics/underline/` is a working example (keywords stay white, a bar slides in under each one); copy it as the starting point.
     - Every caption is drawn by the kit as `.capin` with one `.w` span per word (keywords also have `.kw`). `captions.css` restyles them.
     - `captions.js` runs once with `tl` (the video's GSAP timeline), `captions` (each `{el, t0, words: [{el, at, hot, text}]}`; times in seconds on the video's timeline), `style` (his style.json) and `scale` (frame height / 1920). Add timed animations with `tl.set / tl.to / tl.fromTo(..., at)`. You may add elements to a word. No timers, no random values, no network.
     - With a caption design set, the kit leaves keyword colouring to the design. Read colours and sizes from `style`, so later setting changes still work.
  2. Set `caption_template="<name>"` in style.json, then `bin/kit style test <style>`, then `bin/kit style preview <style>` and look at the keyword moments.
- **A new motion graphic** (DM card, list, stat card, lower third, etc.): see skills/graphics part 3 (start from a library block when one is close). Say in STYLE.md when it should appear; skills/edit-short then places it on each video.
- **A new font:** `bin/kit style snapshot <style>`, put the .ttf in `my-styles/<style>/fonts/` (never in `styles/`, which updates replace), then `bin/kit style set <style> font="<family>" font_file=<file>.ttf`.
- **Something needing a setting that doesn't exist yet:** build it with a template as above, and tell him it's done. Mitchell can fold it into the kit later.

## A style from a reference reel
0. **The reel has to be a video file.** If he sends an Instagram or TikTok link, ask him to save the video (download it, or screen-record it) and drag the file into the chat. Never put a reference reel in `inbox/` (that folder is his own clips, and `$episode` would edit it).
1. Make a contact sheet and look at it: `bin/kit style sheet <reel file>` (it prints where the picture is).
2. Note what you see:
   - caption font feel, case, colour, size (share of frame height), position, words per caption, lines, box or stroke, highlight style
   - how often and how far the shot zooms
   - graphics and B-roll
3. `bin/kit style new <name> --from matthew`. Set what the settings cover. Build what they don't (above). Write `STYLE.md` describing the look.
4. Test it, preview it, and show him. If the reel relies on b-roll, pictures or a graphic, find them in his library (skills/library) or the block library (skills/graphics) and say so in STYLE.md.
5. If the reel is full of motion graphics, do not stop at caption settings. Keep the default replica quality and layer the reel's colours, captions, and pacing on top. He reviews it in Studio. Do not render until he says so.
