# default

The kit's default look for every Short. Saved preferences (for example his red captions) only refine it; they never swap in a canned pack.

Vertical (9:16) with a fixed frame: a reserved graphic panel in the **top half**, his talking head in the **bottom half**, and captions in a dark capsule sitting on the **seam** between them. The kit applies this when `frame_layout` is `split` and the video has at least one graphic (do not fight it in `index.html` unless a single graphic needs a tweak). His face stays in the lower half and is never covered. A Short with no graphics gets his face full frame instead of an empty top half, with captions at `full_center_y_frac` (0.7).

The motion graphics are not a template pack. They are high-fidelity replicas of real things he mentions, drawn as HyperFrames HTML/GSAP compositions, and they should look like a real screen — not a sticker, card, or typographic sting.

## Every video in this style

1. **Read the transcript first.** List every concrete real-world thing he mentions: products, sites, UIs, numbers, documents, dashboards, messages. Google search, a ChatGPT answer, a Stripe dashboard, an email, a tweet, an analytics chart, a results page, a dollar amount with a product around it — each one is a graphic if it can be shown.

2. **Build a faithful replica of each one**, as a new composition in `my-styles/default/templates/<name>/` (snapshot the style first; do not edit `styles/default/` on his Mac). Match the real product:
   - Real brand colours, typography, spacing, and layout. A Google search uses the real Google wordmark (the four-colour letters, or an official logo asset), a real search bar with the query, and real-styled result listings (blue titles, green/black URLs, grey snippets, favicons). If his page is missing or buried, the results should show that — not a caption that says "NOT INDEXED" on a designed card.
   - A ChatGPT / Stripe / Gmail / X / analytics graphic should look like that actual UI, not an abstract chart or a gold callout.
   - Use a live reference (a screenshot you capture, or a well-known official marketing/screenshot reference) when it helps, then match it closely. Do not invent a stylized cousin of the product.
   - Animate it the way the real UI moves, tastefully: typing into the search bar, results loading, a highlight or zoom on the key line. No bounce-in stickers, no diagonal word wipes, no letter-stagger title cards.
   - Show only what the real UI would show. No fake find-in-page widgets or invented chrome. Never bake meta labels such as "reconstruction", "not specified in narration", or "illustrative" into the graphic.
   - Every graphic holds at least about 1.5s. Charts use plausible, believable data, not a perfectly regular made-up shape.
   - Design the composition at 1080×960 (the top panel). Leave `box` off in the plan so it fills the reserved top half like a screen.

This is the default for a creative ask, not the only mode the kit has. A reference reel still wins for the look; a new style is still allowed; if he asks for a different direction, follow that.

3. **Quality gate, before you show him anything and again after every later change.** For every graphic, grab an in, mid, and out still (`bin/kit blocks test <name> --style default`, then after preview, snapshot the Studio project at those times — see skills/graphics). Actually look at the images. If the browser preview tool fails, stills are the path; do not skip looking. Ask: would this pass for the real thing, and does the frame look professionally designed? Redo any that fail, up to three tries, before the preview is considered ready. It must look good every time, including after his edits.

4. **Captions.** Automatic, capsule template, on the seam. Mixed case, a few words, never over his face and never over the graphic panel. Do not add a text card that repeats the caption.

5. **What not to place by default.** Never use canned title cards, count-up stats, sticker callouts, lower thirds, or word swipes. Use a stock kit graphic or a library block only if it genuinely is the closest match to the real thing and it passes the quality gate. Never use a full-frame sting, swipe, or any graphic that covers his face.

6. **Sound.** His voice only, at -14 LUFS. No music, no stacked sound effects, unless he asks.

7. **B-roll only when he asks.** Pick it from the transcript (his library, or Mixkit / Runway) and fit it into this same layout — top panel or split, never over his face. Do not add it unasked.

A 16:9 video does not use this style full-frame. Save a new style with `"shape": "16:9"` and design that video's replicas at 1920×1080, starting from these rules.

## Changes Matthew asked for
(A dated line is added here each time he changes this style; undo reads the newest one.)
2026-11-12: drop the canned five-graphic stack; real-world UI replicas in a reserved top panel; captions in a capsule on the seam
2026-11-12: no invented chrome or meta labels in replicas; each graphic holds ~1.5s; believable charts; quality gate after every edit; b-roll only on request
