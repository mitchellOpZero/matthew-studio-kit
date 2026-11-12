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
| "go crazy", "be creative", "be innovative", "make the graphics look cool", premium graphics | `skills/graphics/SKILL.md` and `skills/style/SKILL.md`. Use `premium-motion` when it fits. A plain Short stays `matthew`. |
| b-roll, pictures, sound effects, "my library", Notion, Runway, Mixkit | `skills/library/SKILL.md` |
| "sort my Notion", "tag / title my B-roll in Notion" | `skills/sort-my-notion/SKILL.md` |
| check a finished video | `skills/video-qa/SKILL.md` |
| diagnose Codex, old graphics, tracking, support diagnostics | `skills/support/SKILL.md` |
| "send it to CapCut", open or finish an edit in CapCut | render it if it isn't yet, then `bin/kit capcut <job>` (`skills/edit-short/SKILL.md`, Open in CapCut). Tell him to quit and reopen CapCut; the project is in its Projects list. |
| update the kit | run `bin/kit update`. It pulls the newest kit, then brings HyperFrames and the Python packages up to date (tested first). His styles in `my-styles/` and his library in `library/` are untouched. Then tell him the new version. |
| "is HyperFrames up to date?", a library problem | `bin/kit deps status`. A bad update: `bin/kit deps rollback`. |
| "send Mitchell a report", "tell Mitchell this is broken" | `bin/kit report --dry-run --note "<what he was doing, in his words>"`; obtain approval of the exact issue before sending (below) |

## One way to edit, every time
0. **Clips he drops into the chat** (attached videos, or a path he pastes) count the same as clips in `inbox/`: first copy each one into `inbox/` keeping its file name (`cp "<path>" inbox/`; add `-2` before the extension if that name is taken), tell him "copied to inbox", then edit the copies. "Edit these" means the ones he just dropped; "edit everything in inbox" includes them too. A reference reel for a style is the exception: it never goes in `inbox/` (skills/style).
1. `bin/kit draft <clip> [--style <name>] [--name <job>] [--long]` makes `.work/<job>/` with `edl.json` (the plan) and `TRANSCRIPT.txt`.
2. You review and fix the plan (skills/edit-short step 3, or skills/long-form). That is the only part that needs judgment.
3. `bin/kit preview <job> [<job> ...]` opens each job in its own HyperFrames Studio tab. He watches the edit live. Nothing is rendered. Give him every link. An open tab reloads by itself after a change.
   A batch (several clips, "$episode", "edit these", about 8 at a time): draft each one, then open them all with **one** `bin/kit preview` command. Number the list 1 to N in that order. Do not render while the tabs open, and do not wait on a finished mp4.
4. His notes ("on 2, cut the opener", "video 4, make the stat say 10"): change that video's plan and run `bin/kit preview` for that job again, or edit its `.work/_studio/<job>/index.html`. He can also change things by hand in Studio. Notes update the preview only. They do not render.
5. **Render only when he says so.** "render them" renders every job in the numbered list. "render 3 and 5" (or "render #3 and #5") renders those numbers only. "render <name>" renders that job. A single video: "render it". `bin/kit render <job>` renders what's in Studio, sets loudness, runs QA, and copies a PASS to `done/`. "Looks good", "finish it", and "go ahead" are not render commands.
6. A FAIL after he asked for a render: fix it from `QA-REPORT.md`, preview, and render that job again. Two fix rounds at most, then stop and report. CapCut is the other time a file gets rendered: he said "send it to CapCut".

## Rules
- **Resolve the editing workflow explicitly.** Start with this kit's `skills/` and `bin/kit` for kit jobs. Follow the user's explicit choice of a downloaded skill, plugin or reference style. Before mixing in a different video workflow, identify its source and any conflicting instructions; do not silently import an old ColdApproach style or use another editor's defaults. For cross-computer differences run `bin/kit support doctor` and `bin/kit support inspect <job>` before changing either setup. Installed skills are candidates, not proof they were used. HyperFrames kit projects run through `bin/kit`.
- **Outside libraries update on their own.** Once a day `bin/kit` checks for newer HyperFrames and Python packages (same release line), tests them on a short clip against the current ones, and switches them in at the start of the next edit only if they pass. Never run `npm install`, `npx hyperframes upgrade` or `pip install` yourself to change versions; that skips the test. Pass on the one-line "kit: updated ..." notice to him.
- The edit pipeline is fixed: draft, review, preview. Render and QA only when he asks ("render them", "render 3 and 5", "render <name>", "render it", or "send it to CapCut"). Never write your own ffmpeg render, caption file or render script for a video. Never edit `engine/`.
- **Preview first.** Opening Studio is not rendering. A batch of about 8 stays on previews until he names what to render. Change notes update that video's preview and stop there.
- **Go crazy means richer graphics, still this pipeline.** "Go crazy", "be creative", "be innovative", or "make the graphics look cool" is not a reason to leave `bin/kit`, and not a reason to stay on logo_pop, picture, text_card, and underline. Follow skills/graphics: use the full HyperFrames block library and author custom GSAP/HTML for this video. `premium-motion` is the creative style when it fits. The first preview should already look designed. He then changes it with notes. A plain "make a Short" still uses `matthew`.
- **A new style, on your own, when none fit.** If the footage or a creative ask fits none of the styles you have, save a new one with a clear new name (`bin/kit style new`). Never overwrite `matthew`, `matthew-long`, `premium-motion`, or anything already in `my-styles/`. Tell him the name and that he can keep it, tweak it, or delete it. Changing a style he already uses still waits for "save over it, or save as a new style?" A reference reel still becomes a style (skills/style), and that style can carry the same custom graphics.
- **Hand edits stick.** Once a project's `index.html` has been changed (by him in Studio, or by you), `bin/kit preview` keeps it and says "kept (hand-edited)". Put a later plan change into `index.html` by hand, or ask him before `bin/kit preview <job> --rebuild` (it starts over from the plan and drops the hand edits).
- The look is open. Anything he wants (captions, zooms, graphics, layout, fonts) goes into a style: settings in `styles/<name>/style.json` (his copies in `my-styles/`), plain-words rules in `STYLE.md`, new pieces (a caption design, a graphic) in the style's `templates/` (skills/style, skills/graphics). Never tell him "the kit can't do that". Build it, test it (`bin/kit style test`), preview it.
- Before saving a style change, ask: "save over <name>, or save as a new style?" Every save keeps the previous version. A look change he asks for while reviewing previews ("make my captions smaller") is a style change too: ask, save it with `bin/kit style set`, then rebuild the previews. Never patch the look into `index.html` files unless he says "just this video".
- Do not put look values in `edl.json`. Per-video choices (cuts, keywords, which b-roll, picture or block goes where, a caption height for this video) do go there.
- Follow the style's STYLE.md on every edit. Matthew's default `matthew` is "the basics": no music, no stacked sound effects, no clutter.
- Report in plain words: the Studio link while he's reviewing; then the file in `done/`, its length, the QA verdict, and what was cut.
- **Diagnose before changing things.** If the same kit error persists after a real fix attempt, or QA fails after two fix rounds, follow `skills/support/SKILL.md`. Collect `bin/kit support doctor` and `bin/kit support inspect <job>`. When support was explicitly enabled, redacted technical records sync to that computer's private GitHub support branch. Do not reset styles, remove plugins or rebuild hand edits as a diagnostic step. Do not post GitHub issues, email or message anyone automatically. Legacy `bin/kit report --dry-run` prepares an issue; show its exact destination and full body and obtain explicit approval before invoking its sending form.
