# Matthew Studio Kit

Turns raw talking-head clips into finished Shorts and YouTube videos, on your Mac, inside Codex.
You watch the whole edit live in HyperFrames Studio before anything renders, change anything by asking (or by hand),
then it renders once and goes through the quality check.
The default look shows the real things you're talking about (a real Google page, a real ChatGPT window) in a clean layout,
with a quality check after every change. Say what to tweak (for example, "make my captions smaller") and it is saved
as a preference on top of that default — it never goes back to the old canned pack.

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
- `bin/kit version` shows the version and exact commit. This release is **2.3.9**. Older releases: 2.0.0, 2.0.1, 2.0.2, 2.2.0, 2.2.1, 2.3.0, 2.3.1, 2.3.2, 2.3.3, 2.3.4, 2.3.5, 2.3.6, 2.3.7, 2.3.8. See `CHANGELOG.md`.
- Update the kit: say "update my kit" or "update-my-kit" (Codex runs `bin/kit update`, a `git pull` of this repo).
- HyperFrames and the Python packages update on their own: once a day the kit looks for newer versions (same release
  line), tests them on a short clip against the current ones (same words heard, same frames, same audio, same QA
  verdict) and switches them in at the next edit only if they pass. `engine/hyperframes.json` and `requirements.txt`
  are the floor, the versions the kit was released with. `bin/kit deps status` shows what's in use, `bin/kit deps rollback`
  goes back. Log: `.cache/deps/log.txt`.
- Your look preferences live in `my-styles/`, your library in `library/`. Updates never touch them.

## Use it (just ask Codex)
Codex opens a Studio preview and stops. Nothing is rendered until you say so.
- "Make this a Short." Or "make a 15 second Short from inbox/clip.MP4." You get a Studio link. Graphics already look like the real things you mention.
- "Make this a YouTube video." A 16:9 edit, same default look, never covering your face.
- "$episode" or "edit everything in inbox": every clip opens in its own Studio tab, numbered. About 8 at a time is normal. Nothing renders yet.
- "On 2, cut the opener." "Make my captions smaller." That preview updates, and look tweaks are saved so they stick. The others stay.
- "Render them." Renders the whole batch into `done/`.
- "Render 3 and 5." Renders those numbers only.
- "Render it." Renders the one video you are looking at.
- "Copy this reference video." The kit matches that reference on top of the same default quality.
- "Add B-roll." Or "put gym B-roll when I talk about the gym." B-roll only when you ask.
- "Refresh my library", "use the Hinge screenshot", "put a chat on screen here".
- "Sort my Notion": Codex looks at your B-roll and puts searchable titles and tags on the B Roll table in Notion, then tells you what changed.
- "Upload this Runway clip to my Content page." B-roll sources and the Notion setup are in `docs/NOTION-MCP.md`.
- "Send it to CapCut." Codex renders that one video, then puts it in CapCut.
- "Turn on support diagnostics." See `docs/SUPPORT.md`.

Plain-words guide: `docs/GUIDE.md`.

## How it works
One fixed pipeline:
1. **draft** (Python): transcript, pause and filler cuts, restart listener.
2. Codex reviews the cuts, keywords, b-roll, pictures and graphics.
3. **preview**: the plan becomes a HyperFrames project (`.work/_studio/<job>/`), and you watch it live in Studio. Hand edits there are kept.
4. **render**: HyperFrames draws it, with your voice as one sample-exact track.
5. **QA**.

- Look: the default real-world graphics, plus any saved preferences in `my-styles/preferences.json`.
- Graphics: the kit's own (`graphics/`), custom compositions for this video, and about 450 HyperFrames library blocks and components (`bin/kit blocks search`, `bin/kit blocks add`).
- Library: `library/` (b-roll, pictures, sound effects), indexed from the Notion Content page you already have (`docs/NOTION-MCP.md`, `skills/library`). Codex can upload a b-roll clip, picture, or style, and title and tag reviewed B-roll, only on that page.

Replaces the Remotion-based Matthew Edit Kit (1.x), which still works on its own if you need it.

### The default look (2.3.1)

Every Short and YouTube video starts from real-world UI replicas in a clean layout. Say what to change and it is saved as a preference on top of that default — it never restores the old canned pack. Say "Matthew style" to get your old look (red captions like your old videos) on just that video. Previews open first, one Studio tab per video. Files land in `done/` only after "render them", "render 3 and 5", or "render it". Details: `CHANGELOG.md`.

### Voice cleanup (2.2.1)

Newly built previews use Mitchell's dialogue cleanup: a 70 Hz rumble filter, light noise
reduction, and per-cut voice leveling capped at 8 dB. Mastering uses measured fixed gain
and a limiter at the saved style's existing loudness target. Captions, graphics, fonts,
punch-ins, music choices and saved styles are unchanged. See [audio details](docs/AUDIO.md).
