# Changelog

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
