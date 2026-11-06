---
name: edit-short
description: "Edit a raw talking-head clip into a finished vertical video in a saved style (default: matthew, his red captions). He watches the whole edit live in Studio before it renders. Use for: edit this clip, cut a Short, make a 15/30 second version, clean up this take, edit the clip in inbox."
---

# Edit a clip

Run everything from the kit folder (the one with AGENTS.md). Never write your own ffmpeg, caption or render code.
For a 16:9 long-form video, follow skills/long-form instead.

## 1. Draft
`bin/kit draft <clip> --style <style> --name <job>`
- Style: what he asked for, else `matthew`. List styles: `bin/kit style list`.
- Job name: short, lowercase, e.g. `coaching-gap-15s`.
- If it says a job with that name already exists, pick another name. Use `--replace` only when he wants that edit started over (it drops its plan and his hand edits in Studio).

It writes `.work/<job>/edl.json` (cuts with pauses and fillers already removed, keywords, logos, and b-roll from his library when a clip's name or tags match a keyword) and `.work/<job>/TRANSCRIPT.txt` (one word per line with its time in the clip). When the kept edit is longer than about 16 seconds it also writes `.work/<job>-15s/` with a vertical cut of about 15 seconds beside it.

## 2. Read
Read the style's `STYLE.md` (`my-styles/<style>/` if he has his own copy, else `styles/<style>/`: the look and its per-video rules), then `TRANSCRIPT.txt` (restarts heard are listed at the top) and `edl.json`. `cuts` are the kept pieces, in source seconds: `{"in": s, "out": s}`.

## 3. Fix the plan (your judgment; same rules as Mitchell's hero-short)
Edit `.work/<job>/edl.json` only.
- **Length.** Full clip unless he asked for a length. For "a 15 s / 30 s Short": keep one complete idea. Open on his first strong line, with no intro. Keep the problem, the turn and the punch line. End on a line that closes the thought (it should loop). Drop asides.
- **Retakes.** When he says a phrase twice, or starts a sentence and restarts it ("and that's the gap between, and that's the gap..."), keep only the LAST complete take. Cut from the first take's first word to the retake's first word. Also cut false starts, "let me start over", stutters, and any "um"/"uh" the draft missed.
- **Pauses.** The draft already cut every pause longer than 0.35 s, so each gap between two pieces is a removed pause. Never merge two pieces into one, and never stretch a piece across a gap. To shorten the video, delete whole pieces or trim a piece's edges. Pauses left inside a piece are short on purpose.
- **Edges.** Never cut inside a word. A piece starts about 0.06-0.1 s before its first word and ends about 0.06-0.1 s after its last word (times from TRANSCRIPT.txt). Pieces must not overlap and must be in order.
- **Keywords** (these words turn crimson as he says them): about one per caption, the word that carries the meaning. Nouns, strong verbs, numbers, brand names. Never: a, the, to, would, might, has, very, more, really, just. Punctuation and capitals do not matter.
- **Caption breaks** (optional): `caption_breaks` is a list of source start times where a new caption must begin. Use it only when a line still splits a phrase badly. The kit already starts a new caption after a clause (a word ending `.` `!` `?` `,` `;` `:`) and before and, but, so, or, or because, and it does not glue that break back together for being short. A `%` stays on the number before it.
- **Caption height.** The kit moves captions below his face on its own when his face reaches them (it prints where they went). Set `"caption_y_frac": 0.72` in the plan only if he asks for a different height on this video.
- **B-roll, pictures, sound effects** from his library (skills/library) and **graphics or library blocks** (skills/graphics), when the style's STYLE.md asks for them or he does. Times in the plan's `overlays`, `broll`, `sfx`, `graphics` and `blocks` are output seconds (after the cuts). The draft already places logo pops.
- Leave `style_name`, `output` and every look value alone. To change the look, use skills/style, not the plan.

## 4. Preview (he watches it before anything renders)
`bin/kit preview <job>` prints a Studio link like `http://localhost:3101/#project/<job>`. Give him the link. Studio plays the whole edit with his voice; nothing has been rendered yet.
- **Showing it in Codex:** open each job's Studio link once in Codex's browser (one tab per job) and leave those tabs open. They reload by themselves after every change, so never open another tab or another copy for the same job.
- If he's not watching, look at it yourself first: `kit preview` already ran HyperFrames' own layout check; also read the caption line it printed.
- **His notes:**
  - Cuts, keywords, which part of the clip, b-roll / pictures / blocks: change `edl.json`, run `bin/kit preview <job>` again. His tab reloads by itself.
  - A tweak on this video only (move a picture, nudge a caption, a colour on one word): edit `.work/_studio/<job>/index.html`. Studio reloads.
  - He can drag, trim and change things by hand in Studio; that lands in the same `index.html`.
  - Once `index.html` has hand edits, a plan change has to go into `index.html` too (the kit keeps hand-edited projects). Ask him before `bin/kit preview <job> --rebuild`, which starts over from the plan.
  - **A look change** (caption size, colour or position, zoom amount, font, how keywords look) is a style change, even mid-review: follow skills/style and **ask first**: "Save over **<style>**, or save as a new style?" Use `bin/kit style set`, never a find-and-replace in `index.html`. Then `bin/kit preview <job> ... --rebuild` so the open tabs show the new look; if any of those projects has hand edits, tell him the rebuild drops them and ask first. Only when he says "just this video" does it go into that video's `index.html`.
- Keep going until he says it looks right. If he asked you to just finish it, go straight to step 5.

## 5. Render and check
`bin/kit render <job>`: about 20 s for a 15 s Short and about 1 min for a 60 s edit, plus 20-40 s for QA.
- PASS: the video is in `done/<job>.mp4`. QA notes are in `done/<job>.QA-REPORT.md`.
- FAIL: read `.work/<job>/out/qa/QA-REPORT.md`. Look at `.work/<job>/out/qa/flags-sheet.jpg`.
  - Missing or clipped word: widen that piece's edge by 0.05-0.1 s.
  - Repeat: cut the earlier take.
  - Pause: tighten the edges around it.
  - Text over a face or in the button zone: set `caption_y_frac` in the plan, or move the picture/block.
  - Caption problems: fix keywords or caption_breaks.
  Preview and render again. Two fix rounds at most, then stop and report what is still failing.

## Open in CapCut
When he wants to finish or tweak an edit in CapCut ("send it to CapCut", "open in CapCut"): render it first, then `bin/kit capcut <job>`. That makes a CapCut project with the whole finished video (captions, b-roll, graphics included) in CapCut's Projects list. Tell him to quit and reopen CapCut if it was open. In CapCut he can trim, add music or text, or cut it up. The kit's captions are part of the video there: to change them, change the edit here and send it again.

## 6. Report
Give him the `done/` path, the length, the QA verdict, what you cut (retakes, pauses), and the keywords. Offer to change the look (skills/style) or edit another clip. `bin/kit preview --stop` closes Studio when he's finished.
