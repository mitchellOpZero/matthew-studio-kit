# Changelog

## 2.3.0

- Creative asks ("go crazy", "be creative", "make the graphics look cool") use the full HyperFrames block library and custom GSAP/HTML graphics. A plain "make a Short" still uses `matthew`.
- New built-in style `premium-motion`: kinetic captions (Outfit), a letter-staggered title, a count-up stat, a sticker callout, an editorial lower third, and a one-word swipe. `matthew` and `matthew-long` are unchanged.
- Codex may save a new style on its own when none of the current looks fit, without overwriting an existing one, and tells Matthew the name so he can keep, tweak, or delete it. A reference reel still becomes a style, and that style can carry the same custom graphics.
- Previews are the default for one video or a batch of about 8. Each video opens in its own Studio tab. Files render only when he says "render them", "render 3 and 5", "render it", or "send it to CapCut". Change notes update the preview and do not render.
- `docs/remote-access.md`: how Matthew installs Tailscale, joins Mitchell's network from an invite link, turns on Remote Login, and turns both off.

## 2.2.1

- Light voice cleanup and bounded leveling on newly built previews, then fixed-gain mastering at the style's loudness target. Captions, graphics, and saved styles are unchanged. See `docs/AUDIO.md`.

## 2.2.0

- Opt-in support diagnostics on a private per-computer branch. See `docs/SUPPORT.md`.

## 2.1.0

- B-roll titles and tags on the Notion Content page. See `docs/NOTION-MCP.md`.

## 2.0.0

- First HyperFrames kit. Replaces the Remotion-based Matthew Edit Kit for new edits.
