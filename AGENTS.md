# Matthew Studio Kit (Codex)

This folder is the kit. Run every command from here as `bin/kit ...` (it uses the kit's own `.venv`, Node and HyperFrames).
`.codex/rules/kit.rules` lets `bin/kit` run outside the sandbox, because previews and renders start HyperFrames' headless
Chrome and a local Studio server. Always call it as `bin/kit`, so the rule applies.

## Which instructions to follow (read the file before acting)
| He asks to... | Read and follow |
|---|---|
| set up, install, "it's not working", check the kit | `skills/setup/SKILL.md` |
| edit a clip, make a Short, clean up a take | `skills/edit-short/SKILL.md` |
| a long-form / YouTube video, a 16:9 edit | `skills/long-form/SKILL.md` |
| edit everything in inbox, "$episode" | `skills/episode/SKILL.md` |
| change the look, make or change a style, undo a style change | `skills/style/SKILL.md` |
| add or use a graphic, a library block, a picture on screen | `skills/graphics/SKILL.md` |
| b-roll, pictures, sound effects, "my library", Notion | `skills/library/SKILL.md` |
| check a finished video | `skills/video-qa/SKILL.md` |
| update the kit | run `bin/kit update`. It pulls the newest kit, then brings HyperFrames and the Python packages up to date (tested first). His styles in `my-styles/` and his library in `library/` are untouched. Then tell him the new version. |
| "is HyperFrames up to date?", a library problem | `bin/kit deps status`. A bad update: `bin/kit deps rollback`. |
| "send Mitchell a report", "tell Mitchell this is broken" | `bin/kit report --note "<what he was doing, in his words>"` (below) |

## One way to edit, every time
1. `bin/kit draft <clip> [--style <name>] [--name <job>] [--long]` makes `.work/<job>/` with `edl.json` (the plan) and `TRANSCRIPT.txt`.
2. You review and fix the plan (skills/edit-short step 3, or skills/long-form). That is the only part that needs judgment.
3. `bin/kit preview <job> [<job> ...]` opens each job in HyperFrames Studio: he watches the whole edit live before anything renders. Give him the link it prints. His open tab reloads by itself after every change.
4. His notes: change the plan and run `bin/kit preview <job>` again, or edit that video's `.work/_studio/<job>/index.html`. He can also change things by hand in Studio. Keep going until he says it looks right.
5. `bin/kit render <job>` renders exactly what's in Studio, sets loudness, runs the QA gate, and copies a PASS to `done/`.
6. A FAIL: fix it from `QA-REPORT.md` (in the plan or the project), render again. Two fix rounds at most, then stop and report.

## Rules
- **Use only this kit.** In this folder, use only the skills in `skills/` and the tools `bin/kit` runs. Ignore every other skill or plugin installed on this Mac (for example hyperframes, media-use, remotion skills, other editors) unless he asks for one by name. HyperFrames runs only through `bin/kit`.
- **Outside libraries update on their own.** Once a day `bin/kit` checks for newer HyperFrames and Python packages (same release line), tests them on a short clip against the current ones, and switches them in at the start of the next edit only if they pass. Never run `npm install`, `npx hyperframes upgrade` or `pip install` yourself to change versions; that skips the test. Pass on the one-line "kit: updated ..." notice to him.
- The edit pipeline is fixed: draft, review, preview, render, QA. Never write your own ffmpeg render, caption file or render script for a video. Never edit `engine/`.
- **Hand edits stick.** Once a project's `index.html` has been changed (by him in Studio, or by you), `bin/kit preview` keeps it and says "kept (hand-edited)". Put a later plan change into `index.html` by hand, or ask him before `bin/kit preview <job> --rebuild` (it starts over from the plan and drops the hand edits).
- The look is open. Anything he wants (captions, zooms, graphics, layout, fonts) goes into a style: settings in `styles/<name>/style.json` (his copies in `my-styles/`), plain-words rules in `STYLE.md`, new pieces (a caption design, a graphic) in the style's `templates/` (skills/style, skills/graphics). Never tell him "the kit can't do that". Build it, test it (`bin/kit style test`), preview it.
- Before saving a style change, ask: "save over <name>, or save as a new style?" Every save keeps the previous version. A look change he asks for while reviewing previews ("make my captions smaller") is a style change too: ask, save it with `bin/kit style set`, then rebuild the previews. Never patch the look into `index.html` files unless he says "just this video".
- Do not put look values in `edl.json`. Per-video choices (cuts, keywords, which b-roll, picture or block goes where, a caption height for this video) do go there.
- Follow the style's STYLE.md on every edit. Matthew's default `matthew` is "the basics": no music, no stacked sound effects, no clutter.
- Report in plain words: the Studio link while he's reviewing; then the file in `done/`, its length, the QA verdict, and what was cut.
- **Problems go to Mitchell by themselves.** When the kit fails and you can't fix it (the same `bin/kit` error twice after a real fix attempt, a Python traceback, or QA still failing after two fix rounds), run `bin/kit report --note "<one line: what he asked for and what broke>"` without asking him, then tell him: "That's a kit problem, so I sent Mitchell a report; he'll fix it in an update." It files a GitHub issue with the error, the recent commands and the versions, never a video, a transcript or a secret. Don't report his own choices the kit rightly refused (a bad value, a missing clip), and never put a secret in the note. If it says it couldn't send, tell him to send Mitchell the file it names.
