---
name: episode
description: "Edit every clip in inbox/ with a style, show him all of them live in Studio at once, then render each and put the QA-passed videos in done/. Use for: do the episode, edit everything in inbox, batch edit, run all my clips. $episode is the call."
---

# Episode

1. For each video file directly in `inbox/` (`.mp4`, `.mov`, any case; not the `inbox/edited/` folder), in name order: follow skills/edit-short steps 1-3 (or skills/long-form for a 16:9 clip) with the style he named (default `matthew`). Use the clip's file name, lowercased, as the job name.
2. Preview them all together: `bin/kit preview <job1> <job2> ...`. Each gets its own Studio link (3101, 3102, ...). Give him the list, one line per clip: the link and one sentence on what you kept.
3. Take his notes per clip (skills/edit-short step 4). If he said to just finish them, skip to 4.
4. `bin/kit render <job>` for each. A PASS lands in `done/`; then move that clip into `inbox/edited/` (make the folder if needed) so the next `$episode` doesn't edit it again. A clip that still fails after two fix rounds stays in `inbox/`; write `<clip>.NOTES.md` beside it saying what failed.

At the end, give one line per clip: PASS with its `done/` path, or FAIL with the reason. Do not stop the batch for one failed clip. `bin/kit preview --stop` closes the Studio servers.
