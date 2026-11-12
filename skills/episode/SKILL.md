---
name: episode
description: "Edit every clip in inbox/ with a style and open each one in its own Studio tab. Do not render until he says render them, or render 3 and 5. Use for: do the episode, edit everything in inbox, batch edit, run all my clips. $episode is the call."
---

# Episode

1. For each video file directly in `inbox/` (`.mp4`, `.mov`, any case; not the `inbox/edited/` folder), in name order: follow skills/edit-short steps 1-3 (or skills/long-form for a 16:9 clip) with the default look (plus any saved preferences). Use the clip's file name, lowercased, as the job name.
2. Preview them all together with **one** command: `bin/kit preview <job1> <job2> ...`. Each gets its own Studio link (3101, 3102, ...). Give him a numbered list, 1 to N, in that order: the link and one sentence on what you kept. Do not render. Do not wait for an mp4. About 8 previews is a normal batch; opening them is the whole job.
3. Change notes name the video ("on 2, cut the opener", "the third one, lower the caption"). Update that job and `bin/kit preview` it again. The other tabs stay as they are. Notes do not render.
4. Render only when he says **"render them"** (every job on the list) or **"render 3 and 5"** (those numbers only). Then `bin/kit render <job>` for each one he named. A PASS lands in `done/`; move that clip into `inbox/edited/` (make the folder if needed) so the next `$episode` doesn't edit it again. A clip that still fails after two fix rounds stays in `inbox/`; write `<clip>.NOTES.md` beside it saying what failed. "Looks good" and "finish them" are not render commands.

After a render, give one line per rendered clip: PASS with its `done/` path, or FAIL with the reason. Do not stop the batch for one failed clip. Until he asks for a render, the report is the numbered preview list. `bin/kit preview --stop` closes the Studio servers when he is finished watching.
