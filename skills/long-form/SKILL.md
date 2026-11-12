---
name: long-form
description: "Edit a long-form 16:9 YouTube video from his raw camera footage (plus screen recordings, b-roll and pictures from his library), previewed live in Studio before it renders. Use for: long-form, YouTube video, full episode, 16:9 edit, edit this whole video."
---

# Long-form (16:9)

Same pipeline as a Short (skills/edit-short), with a landscape frame, the `matthew-long` style, and more structure. Read skills/edit-short first; the rules below are what's different.

## 1. Draft
`bin/kit draft <clip> --long --name <job>` (style `matthew-long` unless he named another). The source can be 4K; the kit frames it to 1920x1080.
If he recorded several camera files, draft each as its own job and keep the episode in one plan: the plan's `source` is one file, so for now edit one camera file per job and tell him which parts are in which job.

## 2. Plan the story (your judgment)
Read the whole transcript before cutting. Then in `edl.json`:
- **Order:** hook (his strongest line or the result) → what this video is about → each point as its own section → his proof (a screenshot, a result, a demo) → the close and what to do next. Cut warm-ups ("okay so", "let's get into it") and repeated points.
- **Retakes, pauses, edges, keywords:** exactly as skills/edit-short step 3. On long-form, keep a breath between sections: don't trim every pause to nothing.
- **Mumbled endings:** end a piece on his last clean word.
- **Slow starts:** each piece should start speaking within about 0.2 s.
- **Look-aways:** if he looks down or away for more than a moment mid-line, cover it with b-roll, a picture or a block from the word before the glance, or cut it. A quick glance while thinking can stay.
- **Never invent words.** Don't generate speech he didn't say.

## 3. Cover the talking
Long-form needs something to look at every 10-20 s besides his face. From his library (skills/library) and the block library (skills/graphics):
- **Screen recordings and app demos:** `broll` with `"layout": "pip"`: the recording full frame, his face in a corner box, so he never disappears for long.
  `{"file": "library/broll/<file>.mp4", "at": <output s>, "dur": <s>, "from": <seconds into the recording>, "layout": "pip"}`
- **Cutaways** (gym, a date spot, the street): `broll` with the default `"layout": "full"`, 1.5-4 s each, on the words they show.
- **Pictures** (a match screenshot, a text, a photo): an overlay card beside his head, never over his face:
  `{"picture": "library/pictures/<file>.png", "at": s, "dur": s, "x": 1480, "y": 430, "w": 640}` (x/y = card centre, px of the 1920x1080 frame).
- **A block** for a list, a chat, a number or a title: `blocks` with a `box` on the side he isn't on, e.g. `[1260, 80, 560, 920]`.
- A **sound effect** at most where a picture or block lands, quiet (`gain_db` -10). Matthew's styles are "the basics": no music, no stacked effects.
- B-roll never freezes: `from` + `dur` must fit inside the clip (`bin/kit library list` shows clips; check the clip's length).

## 4. Preview, then wait
`bin/kit preview <job>`, then his notes (skills/edit-short steps 4-5). Do not render until he says "render it", "render them", or "render 3 and 5". A creative long-form ask uses skills/graphics: save a new 16:9 style rather than stretching `premium-motion` across the frame. A plain long-form stays `matthew-long`.

When he does ask for a render: `bin/kit render <job>`. A long render takes about the video's length again (a 10-minute video renders in roughly 8-12 minutes, then QA). Tell him the ETA before you start it, and don't stop the session while it runs. Run it so it can take that long (a background or long-running command you check on), not with a short command timeout; if the command is cut off, `bin/kit render <job>` again starts it over.

## 5. Report
The `done/` path, the length, the QA verdict, the section list with output times (YouTube chapters: `0:00 Intro`, ... from your plan), and what was cut.

## Voice processing

Version 2.2.1 builds previews with light rumble/noise cleanup and bounded leveling for each
real cut, then fixed-gain mastering at the existing style's loudness target. This does not
change the visual style or add music/SFX. Do not copy a different editor's visual defaults.
For an already cleaned source, set `audio.cleanup` to `false` in the edit plan if needed;
keep any existing `audio.file`, `audio.offset` and `audio.pre` fields. See `docs/AUDIO.md`.
Existing hand-edited previews are preserved. Do not force-rebuild one to apply audio updates.
Inspect it with `bin/kit support inspect <job>`; make a separate comparison job from the same
source and saved style, or obtain explicit approval before overwriting the hand edits.
