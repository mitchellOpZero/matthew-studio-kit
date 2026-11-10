---
name: setup
description: "Install and check the Matthew Studio Kit on his Mac, start to finish. Use when Codex is opened in the kit for the first time, or for: set this up, install, it's not working, check my kit, doctor."
---

# Set up the kit (Codex does all of it)

He just cloned the kit and said "set this up". Do every step yourself. Ask before anything that needs the internet or changes his settings. Explain each step in one plain line. Stop and tell him if a step fails.

0. **Trust the folder first.** When Codex asks whether to trust this folder, he says yes. That turns on `.codex/rules/kit.rules`, which lets `bin/kit` reach the internet for installs and start the Studio preview and HyperFrames' Chrome. Without it installs, previews and renders stop with sandbox errors.
1. **Tools.** Check `brew -v`.
   - If Homebrew is missing, tell him to run the official install command from brew.sh in Terminal (it needs his password), then continue.
   - Then: `brew install gh git ffmpeg-full python@3.12 node`. Skip anything already installed.
   - If `gh auth status` says he isn't logged in: he runs `gh auth login` and then `gh auth setup-git` in Terminal (GitHub.com, HTTPS, log in with a browser). Updates (`git pull` of this private repo) and problem reports to Mitchell both use it.
2. **Python packages.** In the kit folder: `python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt`. These are the tested starting versions; newer ones install on their own later, after passing a test.
3. **HyperFrames** (previews and draws every video). `bin/kit prepare`. It fetches the tested HyperFrames version and its own headless Chrome once (about 200 MB). From then on the kit updates HyperFrames and the Python packages by itself, once a day, testing each update before switching (`bin/kit deps status`).
4. (Trust: done in step 0. If a preview or render later stops with a sandbox error, the folder isn't trusted.)
5. **Check.** `bin/kit version` should show `2.1.0` or newer. Then `bin/kit doctor`. Fix each FIX line with the command it prints, and run doctor again until it says "Ready to edit." The speech-model line can stay FIX: the model downloads on the first edit.
6. **His old kit.** If `~/ColdApproach/matthew-edit-kit` exists, bring his saved styles over: `bin/kit style import ~/ColdApproach/matthew-edit-kit`. Leave the old kit where it is; it still works on its own.
7. **No plugin needed.** Codex reads this folder's AGENTS.md whenever it is opened here, and that points to every skill. Installing the plugin is optional: it makes the skills available in other folders too (`codex plugin marketplace add mitchellOpZero/matthew-studio-kit --ref main`, then `codex plugin add matthew-studio-kit@matthew-studio-kit`).
8. **Clashes.** Look for other video plugins (`codex plugin list`) and loose skills (`ls ~/.codex/skills ~/.agents/skills`) with names like edit-short, episode, style, video-qa, hyperframes or media-use. List them and ask before moving any to `~/codex-skills-backup/`. Never delete them. The old Matthew Edit Kit plugin, if installed, has the same skill names: ask before removing it from Codex (`codex plugin remove matthew-edit-kit@matthew-edit-kit`); its folder stays.
9. **Notion Content library** (optional, can be later): skills/library. He shares the Content page he already has with the Notion connection Codex is signed into, then pastes that page's URL. No new integration. Codex runs the one-time setup (reuses his tables, adds Pictures and Styles if missing, after his OK) and builds the local index.
10. **First edit.** Ask him to drop a clip in `inbox/`, then follow skills/edit-short. The first edit downloads the speech model once (464 MB). Give him the Studio link, then show him the result in `done/`.
11. Tell him he's ready, and point him to `docs/GUIDE.md`.

Never change kit files during setup.
