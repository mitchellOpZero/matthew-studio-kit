# Changelog

## 2.3.7

- Message graphics (iMessage threads, DMs, notifications) show made-up, realistic texts from her, like real iMessages, never his script. They skip the word check (no "mark as allowed" flag), and the preview stops if a text copies a line he says, or if a library or saved message graphic still shows the texts it came with.
- Every other graphic is still his words only, and now that includes words typed straight into a graphic's HTML, not just its data. App chrome (Search, Delivered, times) is fine; `data-ui` marks other chrome.
- No forced half screen. While a graphic shows, the top panel is only as tall as the graphic needs (a short thread gets a short panel and more of his face), with his face right below it. New choice when he asks: `"graphic_layout": "full"` keeps his face full frame and graphics pop in around him, or cut away full screen when there's no room. A full-frame style is no longer forced into a panel. Graphics still never cover his face, and tiny or blurry graphics are still refused.
- Captions keep one size for the whole video (a long one breaks onto a second line instead of shrinking) and one height (no jumping to the seam while a graphic shows). Default height 0.75.
- A Short never saves anything into his style by itself. A video's graphics go in `.work/<job>/graphics/<name>/`. A graphic an older video left in `my-styles/` without being saved is refused, so new Shorts don't inherit old text. `bin/kit graphics save <name> --job <job>` keeps one in his style, only when he asks. A `frame_layout` in a plan's `style` is ignored.

## 2.3.6

- Graphics on a Short always go in the top panel, never on his face. Any block switches the frame to split while it shows, even in the `matthew` style or a plan that says full frame. A block placed over his face, across the caption seam, or too small to read is moved into the panel. Between graphics (and in the hook) his face is full frame, so there is no empty dark top half.
- His face is framed in the bottom half from where his face actually is, forehead to chin, instead of a fixed spot that cut his chin off.
- Sharp graphics: library blocks are laid out at the panel's size instead of shrunk (tiny text) or enlarged (soft), blur filters are stripped, and `thread-message-stack` now looks like a real iMessage thread instead of see-through bubbles on a blurred backdrop.
- Graphics show his words: the kit checks every graphic's text against what he says around that moment and stops the preview on invented messages, names, or a library block's sample text. Put his words in the block's `"data"`.
- Text-only canned pieces (accent underline, kinetic words, lower thirds, count-ups ...) are refused unless he asked for that exact piece.
- Errors block preview and render: lint/check output that can't be read now counts as a failure, a Studio tab already showing a broken project is closed, and the kit's own layout check catches hand edits that put a block on his face. `bin/kit check <job>` shows the errors.

## 2.3.5

- HyperFrames moves from 0.8.214 to 0.9.39 (the current release). A leftover 0.8 copy on his Mac is ignored, so updating the kit always gets the new one.
- Codex checks the HyperFrames library first (about 450 blocks and components) and uses real pieces when they fit the default look, instead of hand-drawing. New: `bin/kit blocks add <name>` installs one from the library; `bin/kit blocks search` now finds components too (e.g. `type-match-cut`).
- Studio shows the right project name. It used to take the name of whatever folder Codex's terminal was in.
- A Short with no graphics shows his face full frame instead of an empty top half. The top panel comes back as soon as there's a graphic.

## 2.3.4

- "Matthew style" uses his old look (red captions, like his old videos) on that video only. It is never saved, so the next video is back on the default.

## 2.3.3

- Removed the old canned graphics (title card, count-up stat, sticker callout, lower third, word swipe) and the old caption animation from the default look.
- `matthew` is labeled as the old red style, used only when he asks for it by name.

## 2.3.2

- The default look's folder is now called `default`. Old edit plans that say `premium-motion` still open it.

## 2.3.1

- The default look for a Short or a YouTube video is real-world UI replicas (a real Google page, a real ChatGPT window) in a clean layout, with a quality check after every change. The old canned title/stat/swipe pack is no longer the default.
- Saved preferences (for example his red captions) layer on top of that default and never replace the graphics, layout, or quality gate. Say what to change and it is saved so it sticks. "Copy this reference video" still works.
- Previews open first, one Studio tab per video, about 8 at a time. Files render only when he says "render them", "render 3 and 5", or "render it".
- QA no longer hard-fails a known Whisper brand mix-up (e.g. "GBT gym" vs "GPT, Gemini"). `qa.accept_asr_mismatch` in the edit plan is a one-line override after a visual check.
- B-roll only when he asks.

## 2.3.0

- Previews before rendering, one Studio tab per video, about 8 at a time. (Its graphics changes were replaced by 2.3.1.)

## 2.2.1

- Light voice cleanup and bounded leveling on newly built previews, then fixed-gain mastering at the style's loudness target. Captions, graphics, and saved styles are unchanged. See `docs/AUDIO.md`.

## 2.2.0

- Opt-in support diagnostics on a private per-computer branch. See `docs/SUPPORT.md`.

## 2.1.0

- B-roll titles and tags on the Notion Content page. See `docs/NOTION-MCP.md`.

## 2.0.0

- First HyperFrames kit. Replaces the Remotion-based Matthew Edit Kit for new edits.
