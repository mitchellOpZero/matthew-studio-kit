# Matthew Studio Kit

Turns raw talking-head clips into finished Shorts and long-form videos in a saved style, on your Mac, inside Codex.
You watch the whole edit live in HyperFrames Studio before anything renders, change anything by asking (or by hand),
then it renders once and goes through the quality check.
Default style: **matthew**. That's white captions with your crimson on each keyword as you say it, 1.5x size, one line,
snap punch-ins, logo pops, and your voice at -14 LUFS. **matthew-long** is the same look for 16:9 YouTube.
**premium-motion** is the creative look: kinetic type, gold and cream graphics, stats, callouts, and swipes.
Say "go crazy" and Codex uses it. A plain "make a Short" stays on matthew.

## Quick start
1. In Terminal, once (the repo is private; accept Mitchell's GitHub invite first):
   `brew install gh && gh auth login && gh auth setup-git`, then
   `gh repo clone mitchellOpZero/matthew-studio-kit ~/ColdApproach/matthew-studio-kit`
   (No Homebrew yet? Install it from brew.sh first.)
2. Open the **Codex app** on that folder and say **"set this up"**. Codex installs everything, checks it, brings over your
   saved styles from the old kit, and runs a first edit with you. No plugin is needed: Codex reads `AGENTS.md` in this folder.
3. Later, say **"update my kit"** or **"update-my-kit"** to get the latest version from GitHub. Codex runs `bin/kit update`, which is a `git pull`. Your styles and library are kept. **2.1.0** adds B-roll titles and tags on your Notion Content page: Codex looks at each clip, then proposes one consistent title (`Woman - walking - cafe - brown hair`) and descriptive tags on the B Roll table. Your own tags and the original title are kept, and every clip Codex adds is titled and tagged the same way. See `docs/NOTION-MCP.md`.

**Remote support (2.2.0):** say "turn on support diagnostics" to record redacted tool activity and graphic sources on a per-computer branch of this private GitHub repo. Mitchell can inspect the records and prepare a focused fix. Support starts only after enable and native hook review. [Support setup and limits](docs/SUPPORT.md).

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
- `bin/kit version` shows the version and exact commit. This release is **2.3.0**. Older releases: 2.0.0, 2.0.1, 2.0.2, 2.2.0, 2.2.1. See `CHANGELOG.md`.
- Update the kit: say "update my kit" or "update-my-kit" (Codex runs `bin/kit update`, a `git pull` of this repo).
- HyperFrames and the Python packages update on their own: once a day the kit looks for newer versions (same release
  line), tests them on a short clip against the current ones (same words heard, same frames, same audio, same QA
  verdict) and switches them in at the next edit only if they pass. `engine/hyperframes.json` and `requirements.txt`
  are the floor, the versions the kit was released with. `bin/kit deps status` shows what's in use, `bin/kit deps rollback`
  goes back. Log: `.cache/deps/log.txt`.
- Your styles live in `my-styles/`, your library in `library/`. Updates never touch them.

## Use it (just ask Codex)
Codex opens a Studio preview and stops. Nothing is rendered until you say so.
- "Edit the clip in inbox with my style." Or "make a 15 second Short from inbox/clip.MP4." You get a Studio link.
- "Make a long-form video from the clip in inbox." 16:9, with screen recordings, b-roll, pictures and graphics.
- "$episode" or "edit everything in inbox": every clip opens in its own Studio tab, numbered. About 8 at a time is normal. Nothing renders yet.
- "On 2, cut the opener." "Video 4, make the stat say 10." That preview updates. The others stay.
- "Render them." Renders the whole batch into `done/`.
- "Render 3 and 5." Renders those numbers only.
- "Render it." Renders the one video you are looking at.
- "Go crazy." "Be creative." "Make the graphics look cool." Codex uses **premium-motion** (or saves a new style if that look doesn't fit) and the first preview already has kinetic type, callouts, stats, and swipes. Then you change it with notes.
- "Make a style from this." A reference reel becomes a style, graphics included. It works with the creative look: the reel sets the colours and pacing, and the motion graphics are built into that same style.
- "Make my captions a bit smaller." Codex asks whether to save over your style or as a new one, then shows a preview. "Undo that" goes back. If Codex invented a style for a video, it tells you the name. Say keep it, tweak it, or delete it.
- "Refresh my library", "use the Hinge screenshot", "put a chat on screen here".
- "Sort my Notion": Codex looks at your B-roll and puts searchable titles and tags on the B Roll table in Notion, then tells you what changed.
- "Upload this Runway clip to my Content page." B-roll sources and the Notion setup are in `docs/NOTION-MCP.md`.
- "Send it to CapCut." Codex renders that one video, then puts it in CapCut.
- "Turn on support diagnostics." See `docs/SUPPORT.md`. Letting Mitchell work on this Mac from his computer: `docs/remote-access.md`.

Plain-words guide: `docs/GUIDE.md`.

## How it works
One fixed pipeline:
1. **draft** (Python): transcript, pause and filler cuts, restart listener.
2. Codex reviews the cuts, keywords, b-roll, pictures and graphics.
3. **preview**: the plan becomes a HyperFrames project (`.work/_studio/<job>/`), and you watch it live in Studio. Hand edits there are kept.
4. **render**: HyperFrames draws it, with your voice as one sample-exact track.
5. **QA**.

- Styles: `styles/<name>/style.json` (+ `STYLE.md`, caption designs and graphics in `templates/`), old versions in `versions/`.
- Graphics: the kit's own (`graphics/`), the `premium-motion` compositions, about 200 HyperFrames library blocks (`bin/kit blocks search`), and ones built for a video.
- Library: `library/` (b-roll, pictures, sound effects), indexed from the Notion Content page you already have (`docs/NOTION-MCP.md`, `skills/library`). Codex can upload a b-roll clip, picture, or style, and title and tag reviewed B-roll, only on that page.

Replaces the Remotion-based Matthew Edit Kit (1.x), which still works on its own if you need it.

### Creative graphics and preview-first batches (2.3.0)

"Go crazy" uses the `premium-motion` style and custom HyperFrames graphics, and Codex may save a new style when none of the current ones fit. It tells you the name. Previews open first, one Studio tab per video. Files land in `done/` only after "render them" or "render 3 and 5". Details: `CHANGELOG.md`.

### Voice cleanup (2.2.1)

Newly built previews use Mitchell's dialogue cleanup: a 70 Hz rumble filter, light noise
reduction, and per-cut voice leveling capped at 8 dB. Mastering uses measured fixed gain
and a limiter at the saved style's existing loudness target. Captions, graphics, fonts,
punch-ins, music choices and saved styles are unchanged. See [audio details](docs/AUDIO.md).
