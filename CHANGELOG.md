# Changelog

## 2.3.1

- The default look for a Short or a YouTube video is real-world UI replicas (a real Google page, a real ChatGPT window) in a clean layout, with a quality check after every change. The old canned title/stat/swipe pack is no longer the default.
- Saved preferences (for example his red captions) layer on top of that default and never replace the graphics, layout, or quality gate. Say what to change and it is saved so it sticks. "Copy this reference video" still works.
- Previews open first, one Studio tab per video, about 8 at a time. Files render only when he says "render them", "render 3 and 5", or "render it".
- QA no longer hard-fails a known Whisper brand mix-up (e.g. "GBT gym" vs "GPT, Gemini"). `qa.accept_asr_mismatch` in the edit plan is a one-line override after a visual check.
- B-roll only when he asks.

## 2.3.0

- Creative asks ("go crazy", "be creative", "make the graphics look cool") use the full HyperFrames block library and custom GSAP/HTML graphics. A plain "make a Short" still uses `matthew`.
- New built-in style `premium-motion`: kinetic captions (Outfit), a letter-staggered title, a count-up stat, a sticker callout, an editorial lower third, and a one-word swipe. `matthew` and `matthew-long` are unchanged.
- Codex may save a new style on its own when none of the current looks fit, without overwriting an existing one, and tells Matthew the name so he can keep, tweak, or delete it. A reference reel still becomes a style, and that style can carry the same custom graphics.
- Previews are the default for one video or a batch of about 8. Each video opens in its own Studio tab. Files render only when he says "render them", "render 3 and 5", "render it", or "send it to CapCut". Change notes update the preview and do not render.

## 2.2.1

- Light voice cleanup and bounded leveling on newly built previews, then fixed-gain mastering at the style's loudness target. Captions, graphics, and saved styles are unchanged. See `docs/AUDIO.md`.

## 2.2.0

- Opt-in support diagnostics on a private per-computer branch. See `docs/SUPPORT.md`.

## 2.1.0

- B-roll titles and tags on the Notion Content page. See `docs/NOTION-MCP.md`.

## 2.0.0

- First HyperFrames kit. Replaces the Remotion-based Matthew Edit Kit for new edits.
