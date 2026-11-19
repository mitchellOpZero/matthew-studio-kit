---
name: graphics
description: "Put graphics on screen from the HyperFrames library (about 450 ready-made pieces), all in the video's one theme: titles, lists, charts, annotations, app screens, chats, transitions. Use for: add a graphic, show a chat/DM, a list on screen, a stat, copy a reference video's graphics, make a new motion graphic."
---

# Graphics

Every graphic is drawn by HyperFrames on the same timeline as his video and is visible in Studio before anything renders. Preview only until he says "render them" or "render 3 and 5" (skills/edit-short).

Two rules decide almost everything:
1. **Use the HyperFrames library.** Any piece may be used. Adjust a library piece before you draw anything of your own.
2. **One theme per video.** Every graphic in a video wears the same colours.

## Read HyperFrames' skills before you build or restyle
Adjusting a piece's look or motion, or building a new graphic, is HyperFrames work. Before you write any HTML, CSS or GSAP for one, read HyperFrames' own skills (in `~/.agents/skills/`, put there by `bin/kit prepare`) and build the way they say:
- **`hyperframes`** first: the composition contract in its `SKILL.md`, then `references/motion.md` (animation and keyframes: eases, titles, cuts, punch-ins, holds), `references/look.md` (the creative side: type, colour, layout), `references/overlays.md` (cards over a talking head), and `references/format.md` and `references/runtimes.md` (attributes, GSAP and the other animation runtimes).
- **`hyperframes-registry`**: what each library piece is and how it is meant to be changed.
- On an older install the same knowledge is split across `hyperframes-animation`, `hyperframes-creative`, `hyperframes-keyframes` and `motion-graphics`. Read those when they are the ones installed.

The kit still decides the rest on his videos: his words, the video's one theme, where the graphic sits, and `bin/kit blocks`, `bin/kit preview` and `bin/kit check` in place of the `npx hyperframes` commands those skills name. If the skills are missing, run `bin/kit prepare`.

## 1. Pick the pieces
For each moment that should have a graphic, in this order:
1. **What he already likes:** `bin/kit graphics find <words>`. These are graphics he said he liked and kept. Reuse one with `bin/kit graphics use <name> --job <job>` (same design and motion, this video's words).
2. **The library:** `bin/kit blocks search <words>`. Search for what it should show and for the kind of piece (`headline`, `title`, `list`, `checklist`, `chart`, `counter`, `annotate`, `chat`, `notification`, `transition`). **Blocks** are whole scenes with their own canvas (chat and app mock-ups, charts, titles). **Components** fill whatever box they're given (a headline, a list, a counter, a message).
3. **Install and try it:** `bin/kit blocks add <name>`, then `bin/kit blocks test <name>` (it must print OK; look at the still). It needs the internet once; after that the piece is reused offline.
4. **Only if nothing can be made to fit:** build a new one (part 5), from library pieces where you can.

Pieces that work well on his talking-head videos: `headline-slam`, `marker-highlight`, `text-match-cut`, `per-word-rise`, `titlecard-lockup`, `vox-annotate`, `strikethrough-replace`, `count-up`, `number-wheel`, `grid-card-assemble`, `chart-story`, `chat-thread`, `chat-message`, `native-notification-pop`, `notes-typing`, and the hand-drawn `hw-` family (`hw-arrow`, `hw-underline`, `hw-callout-circle`).

## 2. Give it his words
- A piece with settings takes them in `"vars"`: `{"name": "headline-slam", "at": 4.9, "dur": 1.5, "vars": {"text": "Ruthless prioritization", "accent_word_index": 0}}`. `bin/kit blocks test <name>` shows what a piece takes.
- A piece with sample content takes `"data"` (the same shape as its `data-hf-primitive-data`).
- A piece with words typed into it takes `"replace": {"its sample line": "his words"}`.
- **His words only.** Every word on a graphic is a quote or close paraphrase of what he says around that moment. The kit compares them with the transcript and stops the preview on a line he doesn't say. `"invented_ok": true` only when he asked for that exact text.
- **Message graphics are the exception: just make it up.** iMessage threads, DMs and notifications show made-up, realistic texts from a girl, the way real messages read (lowercase, short, emojis). Never copy his script into the bubbles. Put them in `"data"`, e.g. `{"messages": [{"side": "incoming", "text": "wait are you the guy from the gym 😭"}, {"side": "outgoing", "text": "maybe"}]}`. Give her a believable first name and the app's real header. A graphic never labels itself ("Fictional DM", "Sample chat").

## 3. One theme
`bin/kit draft` puts a theme in the plan (`"theme"`); the next video gets the next one in turn, so videos differ and each one matches itself.
- `bin/kit theme list` shows them. `bin/kit theme set <theme> <job>` changes one video ("make this one the green one"). `"theme"` in `my-styles/preferences.json` pins one for every video.
- Library pieces pick the theme up by themselves. A piece you adjust or draw uses the theme's names, never a colour of its own: `var(--bg)` the page, `var(--surface)` a card, `var(--fg)` type, `var(--muted)` quiet type, `var(--border)` lines, `var(--accent)` the one accent, `var(--accent-2)` the second colour.
- A real app screen (iMessage, Google, ChatGPT, a notification) keeps the app's real colours. Find a current real screenshot of that screen online, keep it in `.work/<job>/refs/`, and match it.
- **His own theme:** `my-styles/themes/<name>.json` with the same nine colours a kit theme has (`bin/kit theme show crimson` shows the shape).

## 4. Copy a reference
When he gives a reference video or picture ("make it like this"):
1. `bin/kit style sheet <reel>` and look at it.
2. Take its colours as this video's theme: write them to `my-styles/themes/<name>.json` and `bin/kit theme set <name> <job>`.
3. For each thing the reference shows (a title treatment, a list, a chat, a chart, a transition), find the closest library piece and use it.
4. Adjust those pieces to match the reference (part 5) instead of drawing your own.
5. Tell him which library piece stands in for which part of the reference.

## 5. Adjust a piece, or build one
- **Adjust first.** A piece that is close but not right gets a restyle, not a replacement: `graphics/_looks/<name>.css` (added after the piece's own styles), or `graphics/_looks/vertical/<name>.css` for vertical videos only. Many type pieces are built for a wide frame and keep their words on one small line; the vertical looks stack the words big. The kit gives each graphic two sizes that fit its own words: `var(--kit-word-fit)` (one word per line) and `var(--kit-line-fit)` (a whole line).
- **A new graphic, only when nothing fits:** read HyperFrames' skills first (top of this file), then write `.work/<job>/graphics/<name>/<name>.html` (a HyperFrames composition: a root `data-composition-id`, `data-width`, `data-height`, `data-duration`, and one paused GSAP timeline registered as `window.__timelines["<id>"]`; no timers, no random values; its own `@font-face` with the font file in its `assets/`). Theme colours by name. Start from the closest library piece's file when there is one. `bin/kit blocks test <name> --job <job>` must print OK.
- **Keep what he likes:** when he says he likes a graphic, `bin/kit graphics save <name> --job <job> --about "<what it shows, when to use it>"`. It is then found by `bin/kit graphics find`. Don't save one he hasn't said he likes.

## 6. Place it and look
`"blocks": [{"name": "<name>", "at": <output s>, "dur": <s>, "vars": {...}}]` in `edl.json`. Times are output seconds (after the cuts). Each graphic holds at least about 1.5 s.
- **On a Short, leave `box` off;** the kit places it. The default is a top panel as tall as the graphic needs, his face below. If he asks to keep his face full screen: `"graphic_layout": "full"` in the plan; a graphic then pops in around his face, or cuts away full screen (`"show": "cutaway"`).
- **A themed cut scene** (`"show": "scene"`, only when it suits the video or he asks): the theme's page, the graphic on it, and his video in a card under it.
- **On long-form,** `box` is where it sits, on the side he isn't on.
- Never on his face. Captions stay on top, at one height and one size all video. `bin/kit check <job>` fails a hand edit that puts a graphic on his face or in the captions.
- B-roll and full-screen graphics swipe in and out with a whoosh by themselves; small cards pop in quietly.
- `bin/kit preview <job>`, then look at stills at the in, middle and out of every graphic:
  `.venv/bin/python -c "import sys; sys.path.insert(0,'engine'); import render_hf; print(render_hf.snapshot(render_hf.project_dir('<job>'), [t1, t2, t3]))"`
  Open the PNG files. Each still must show the graphic big and sharp, his whole face where his face shows, one theme, and only his words. Redo what fails before he sees it. The preview refuses to open while HyperFrames check or the kit's layout check report an error: fix every one it prints (`bin/kit check <job>`).

## The kit's own small graphics
`bin/kit graphics list`: **logo_pop** (an app logo on a white tile; more logos go in `assets/logos/`), **picture** (a still from his library on a card, skills/library), **text_card** (a short line on his highlight colour). Each manifest's `plan` line shows what to put in `edl.json`.
