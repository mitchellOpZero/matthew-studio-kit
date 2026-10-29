# Your studio kit: how to use it

Open **Codex** in `~/ColdApproach/matthew-studio-kit` and just ask. Codex does the editing. You never need the terminal
(except once, to connect Notion).

## Edit a video
1. Drop your raw clip in the `inbox` folder.
2. Ask Codex:
   - "Edit the clip in inbox with my style." This cleans up the full clip.
   - "Make a 15 second Short from the clip in inbox." Codex picks the strongest 15 seconds.
   - "Make a long-form video from the clip in inbox." A 16:9 YouTube edit.
   - "$episode" edits every clip in inbox.
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
Send Codex the reel and say **"Make a style from this."** It copies the captions and zoom pacing into a new style. Then use it: "Edit this with the <name> style."

## Your library (Notion)
Your b-roll, pictures (Hinge and text screenshots, photos) and sound effects live in your Notion library database.
Add a row with a Name, a Type (B-roll, Picture or SFX) and the file. Then tell Codex **"sync my library"** and use
them by name: "use the gym b-roll when I talk about the gym". Connecting Notion the first time takes one Terminal
command; Codex walks you through it.

## Graphics
"What graphics do I have?" lists the kit's own (logo pop, picture card, text card). There are also about 200 ready-made
animated pieces (chat and app mock-ups, lists, numbers, titles): ask for one ("show this as a text conversation",
"a list of the 3 steps") and Codex finds and places it. Anything that doesn't exist yet, Codex builds into your style.

## If something goes wrong
- Codex tells you in plain words what failed. A failed video never lands in `done/`.
- "Run setup" (or "check my kit") fixes missing installs.
- Still stuck? Send Mitchell the message Codex showed you.
