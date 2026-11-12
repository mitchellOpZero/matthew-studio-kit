# premium-motion

The creative look. Use it when he says go crazy, be creative, be innovative, make the graphics look cool, or premium. A plain "make a Short" stays on `matthew`.

Vertical (9:16). Captions are short, tracked, uppercase, cream with a gold keyword. The motion graphics are the point: they are drawn as HyperFrames compositions in this style's `templates/`, not as the stock logo pop and text card alone.

## Every video in this style
Place these in the plan's `blocks`. Words and timing are per video (`at`, `dur`, `vars`). The motion, fonts, and colours live in the templates. Leave `box` off on a Short: each graphic sits itself on a 1080x1920 canvas and the rest is clear, so his face still shows.

- **Captions.** Automatic. Two words, uppercase, Outfit. Each word rises in. The keyword turns gold and a bar draws under it. Do not add a text card that repeats the caption.
- **Kinetic label, opening.** For the first strong line, about 1.6–2.4 s, starting as he says it. One to three designed words, not a whole sentence. A phrase he says is fine: the motion is the point.
  `{"name": "kinetic-label", "at": 0.3, "dur": 2.2, "vars": {"kicker": "THE REAL", "line": "GAP", "sub": "between a like and a date"}}`
- **Animated stat.** When he says a number, count it up for about 2 s. The number is the one he said.
  `{"name": "stat-count", "at": 3.0, "dur": 2.2, "vars": {"value": "3", "suffix": "x", "label": "MORE DATES"}}`
- **Callout.** Once, on the turn or the rule, about 1.8 s. A sticker, not a paragraph.
  `{"name": "callout", "at": 5.0, "dur": 1.8, "vars": {"title": "STOP SCROLLING", "detail": "the feed is not the work"}}`
- **Lower third.** Once, about 2.2 s, when he names himself or the role the video is about. It sits above the bottom app buttons.
  `{"name": "lower-third", "at": 6.2, "dur": 2.2, "vars": {"index": "01", "name": "MATTHEW", "role": "DATING COACH"}}`
- **Swipe.** One beat, about 0.8 s, on the cut between the problem and the turn. One word.
  `{"name": "idea-swipe", "at": 2.4, "dur": 0.85, "vars": {"word": "TURN"}}`
- **Library blocks.** If he describes a chat, a list, a chart, or a screen the templates don't cover, `bin/kit blocks search` and `bin/kit blocks test` that block, then add it. A failed search does not stop the edit: the graphics above are already enough for a strong first preview.
- **Something new.** If none of those fit this video, author a GSAP composition in a new style or in his copy (`skills/graphics`). Do not edit `styles/premium-motion/` on his Mac (a later update is a fast-forward pull). `bin/kit style snapshot premium-motion` first, then add the file under `my-styles/premium-motion/templates/`.
- **Logos.** Still pop once when he names YouTube or Instagram. Not on top of the kinetic label.
- **Sound.** His voice only, at -14 LUFS. No music, no stacked sound effects, unless he asks.
- **Don't stack.** The label, the stat, and the callout take turns. Two may cross for a beat. The swipe is the only full-frame cover, and it is gone in under a second. Keep type out of his eyes and out of the top and bottom app UI.

A 16:9 video does not use this style full-frame. Save a new style with `"shape": "16:9"` and design that video's compositions at 1920x1080, starting from these.

## Changes Matthew asked for
(A dated line is added here each time he changes this style; undo reads the newest one.)
