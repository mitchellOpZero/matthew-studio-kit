---
name: video-qa
description: "Check a finished video for problems before posting: cut-off or covered text, faces cropped, app-UI zones, missing or repeated words, dead air, loudness, frozen or black frames. Use for: check this video, run QA, is this ready."
---

# QA gate

`bin/kit qa <video> [--job <job>]` writes `QA-REPORT.md`, `qa.json`, `flags-sheet.jpg` and `overview-sheet.jpg`. It runs on its own inside `bin/kit render`.

- **FAIL:** each line has a time and what's wrong. Look at the flagged frames before deciding. Fix the plan or the project (skills/edit-short step 5), never the exported video.
- **WARN:** read it, and decide whether it matters.
- **Also check by eye** what QA can't judge: does the opening grab, does it end cleanly, does he look away mid-line, does b-roll freeze, does a picture or block cover his face.
Never call a FAIL done.
