# Matthew Studio Kit

Turns raw talking-head clips into finished Shorts and long-form videos in a saved style, on your Mac, inside Codex.
You watch the whole edit live in HyperFrames Studio before anything renders, change anything by asking (or by hand),
then it renders once and goes through the quality check.
Default style: **matthew**. That's white captions with your crimson on each keyword as you say it, 1.5x size, one line,
snap punch-ins, logo pops, and your voice at -14 LUFS. **matthew-long** is the same look for 16:9 YouTube.

## Quick start
1. In Terminal, once (the repo is private; accept Mitchell's GitHub invite first):
   `brew install gh && gh auth login && gh auth setup-git`, then
   `gh repo clone mitchellOpZero/matthew-studio-kit ~/ColdApproach/matthew-studio-kit`
   (No Homebrew yet? Install it from brew.sh first.)
2. Open the **Codex app** on that folder and say **"set this up"**. Codex installs everything, checks it, brings over your
   saved styles from the old kit, and runs a first edit with you. No plugin is needed: Codex reads `AGENTS.md` in this folder.
3. Later, say **"update my kit"** to get the latest version from GitHub. Your styles and library are kept.

## Install by hand (what "set this up" does)
The repo is private: you need a GitHub account with access (Mitchell sends the invite).
```
brew install gh git ffmpeg-full python@3.12 node
gh auth login && gh auth setup-git          # sign in to GitHub once
git clone https://github.com/mitchellOpZero/matthew-studio-kit ~/ColdApproach/matthew-studio-kit
cd ~/ColdApproach/matthew-studio-kit
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
bin/kit prepare                                # HyperFrames + its Chrome (newer versions follow on their own)
bin/kit doctor                                 # every line OK, shows the kit version
bin/kit style import ~/ColdApproach/matthew-edit-kit   # only if you used the old kit
# open the folder in the Codex app and trust it (turns on .codex/rules/kit.rules, which previews and renders need)
```

## Versions and updates
- `bin/kit version` shows the version and exact commit. Releases are tagged `v2.0.0`, `v2.1.0`, and so on.
- Update the kit: say "update my kit" (Codex runs `bin/kit update`).
- HyperFrames and the Python packages update on their own: once a day the kit looks for newer versions (same release
  line), tests them on a short clip against the current ones (same words heard, same frames, same audio, same QA
  verdict) and switches them in at the next edit only if they pass. `engine/hyperframes.json` and `requirements.txt`
  are the floor, the versions the kit was released with. `bin/kit deps status` shows what's in use, `bin/kit deps rollback`
  goes back. Log: `.cache/deps/log.txt`.
- Your styles live in `my-styles/`, your library in `library/`. Updates never touch them.

## Use it (just ask Codex)
- "Edit the clip in inbox with my style." Or "make a 15 second Short from inbox/clip.MP4." You get a Studio link to watch it.
- "Make a long-form video from the clip in inbox." 16:9, with screen recordings, b-roll, pictures and graphics.
- "$episode": edits every clip in `inbox/`, opens them all in Studio, then renders the ones you approve to `done/`.
- "Make my captions a bit smaller." Codex asks whether to save over your style or as a new one, then shows a preview. "Undo that" goes back.
- "Sync my library", "use the Hinge screenshot", "put a chat on screen here".

Plain-words guide: `docs/GUIDE.md`.

## How it works
One fixed pipeline:
1. **draft** (Python): transcript, pause and filler cuts, restart listener.
2. Codex reviews the cuts, keywords, b-roll, pictures and graphics.
3. **preview**: the plan becomes a HyperFrames project (`.work/_studio/<job>/`), and you watch it live in Studio. Hand edits there are kept.
4. **render**: HyperFrames draws it, with your voice as one sample-exact track.
5. **QA**.

- Styles: `styles/<name>/style.json` (+ `STYLE.md`, caption designs and graphics in `templates/`), old versions in `versions/`.
- Graphics: the kit's own (`graphics/`), about 200 HyperFrames library blocks (`bin/kit blocks search`), and ones built for you.
- Library: `library/` (b-roll, pictures, sound effects), synced from your Notion database (`skills/library`).

Replaces the Remotion-based Matthew Edit Kit (1.x), which still works on its own if you need it.
