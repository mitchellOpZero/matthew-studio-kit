# Your studio kit: how to use it

Open **Codex** in `~/ColdApproach/matthew-studio-kit` and just ask. Codex does the editing. You only need Terminal for a
few one-time steps (installing Homebrew, logging in to GitHub, connecting Notion); Codex tells you exactly what to type.

## Edit a video
1. Drop your raw clip in the `inbox` folder, or drag it straight into the Codex chat (Codex copies it into `inbox` for you).
2. Ask Codex:
   - "Edit the clip in inbox with my style." This cleans up the full clip.
   - "Make a 15 second Short from the clip in inbox." Codex picks the strongest 15 seconds.
   - "Make a long-form video from the clip in inbox." A 16:9 YouTube edit.
   - "$episode" edits every clip in inbox. Clips it finishes move to `inbox/edited/`, so it never edits them twice.
3. Codex gives you a **Studio link**. Click it: your edit plays with your voice, captions, zooms and graphics. Nothing
   has been rendered yet, so changes are instant.
4. Tell Codex what to change ("cut the first sentence", "make 'confidence' red", "put the Hinge screenshot when I say
   match"), or change it yourself in Studio: drag, trim, move things. Your hand changes are kept.
5. Say "looks good" and it renders. About a minute later the finished video is in `done/`, with a QA report beside it.

Every edit removes pauses, ums and uhs, and retakes (it keeps your last take). Then it adds your captions, zooms and logo
pops, keeps captions off your face, and sets the sound level. A video only goes into `done/` after it passes the quality check.

## Change your look
Ask in plain words, for example:
- "Make my captions a little smaller."
- "Put the captions a bit lower."
- "Zoom in more often."
- "Underline the keywords instead of making them red."

Codex asks: **"Save over your style, or save as a new style?"** Then it shows you a preview. Your old version is always kept, so you can say:
- **"Undo that"**
- **"Go back to how it was yesterday"**

## A new look from a video you like
Save the reel as a video file (download it, or screen-record it; a link won't work), drag the file into the Codex chat
and say **"Make a style from this."** It copies the captions and zoom pacing into a new style. Then use it: "Edit this with the <name> style."

## Your library (Notion)
Your b-roll, pictures, graphics, and styles live on the Content page you already have in Notion. Codex sets up what the kit needs there for you (it keeps B Roll Clips and your Graphics table, adds the fields they need, and adds Pictures and Styles), and shows you the plan before it changes anything. You do not create an integration.

Once: open that Content page, share it with the Notion connection Codex is already signed into (••• → Connections), then paste the page URL and say **"Use the library skill to set up my Content page and build the local index."** After that, "use the gym b-roll when I talk about the gym" finds what was indexed. Say **"refresh my library"** after you add something.

Codex can add a b-roll clip, a picture, or a style only on that Content page. It will not write to a different workspace, and it never deletes or renames anything.

**B-roll.** Runway is the usual place for AI B-roll: generate the clip, download the MP4, and add it to your B Roll database (or ask Codex to upload it). For free stock, use Mixkit at <https://mixkit.co/free-stock-video/>: search, download a free clip, and add it the same way. The kit then indexes it like any other clip. Marking a clip AI or stock records where it came from. It does not clear the licence. Details: `docs/NOTION-MCP.md`.

## Finish in CapCut

Say **"send it to CapCut"**. Codex renders the edit if it isn't yet, then makes a CapCut project with the whole finished video in it (captions, b-roll and graphics included). Quit and reopen CapCut: the project is in your Projects list, ready to trim, add music or text, or cut up. The kit's captions are part of the video there, so to change a caption, ask Codex to change the edit and send it again.

## Graphics
"What graphics do I have?" lists the kit's own (logo pop, picture card, text card). There are also about 200 ready-made
animated pieces (chat and app mock-ups, lists, numbers, titles): ask for one ("show this as a text conversation",
"a list of the 3 steps") and Codex finds and places it. Anything that doesn't exist yet, Codex builds into your style.

## If something goes wrong
- Codex tells you in plain words what failed. A failed video never lands in `done/`.
- "Run setup" (or "check my kit") fixes missing installs.
- If the kit itself breaks, Codex sends Mitchell a report on its own (the error and versions only: no video, no transcript).
  The fix reaches you with the next update. You can also say **"send Mitchell a report"** any time.
