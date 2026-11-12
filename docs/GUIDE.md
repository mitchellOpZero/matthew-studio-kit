# Your studio kit: how to use it

Open **Codex** in `~/ColdApproach/matthew-studio-kit` and just ask. Codex does the editing. You only need Terminal for a
few one-time steps (installing Homebrew, logging in to GitHub, connecting Notion); Codex tells you exactly what to type.

## Edit a video
1. Drop your raw clip in the `inbox` folder, or drag it straight into the Codex chat (Codex copies it into `inbox` for you).
2. Ask Codex:
   - "Edit the clip in inbox with my style." This cleans up the full clip.
   - "Make a 15 second Short from the clip in inbox." Codex picks the strongest 15 seconds.
   - "Make a long-form video from the clip in inbox." A 16:9 YouTube edit.
   - "$episode" edits every clip in inbox and opens each one in its own Studio tab, numbered. Nothing renders yet. After you say "render them", finished clips move to `inbox/edited/`, so the next episode doesn't edit them twice.
3. Codex gives you a **Studio link** for each video. Click it: the edit plays with your voice, captions, zooms and graphics. Nothing
   has been rendered yet, so changes are instant.
4. Tell Codex what to change ("cut the first sentence", "on 2, make the stat say 10", "put the Hinge screenshot when I say
   match"), or change it yourself in Studio: drag, trim, move things. Your hand changes are kept. The preview updates. Nothing is rendered yet.
5. When you want the files, say **"render them"** for the whole batch, **"render 3 and 5"** for those numbers, or **"render it"** for the one you are watching. About a minute later each finished video is in `done/`, with a QA report beside it. "Looks good" does not render.

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

Once: open that Content page, share it with the Notion connection Codex is already signed into (••• → Connections), then paste the page URL and say **"Use the library skill to set up my Content page and build the local index."** After that, "use the gym b-roll when I talk about the gym" finds what was indexed. Say **"refresh my library"** after you add something. Say **"sort my Notion"** and Codex looks at your B-roll clips, then puts a title (like `Woman - walking - cafe - brown hair`) and tags on each one in the B Roll table and tells you what changed. Your own tags stay, and the old title is kept in an Original title field. B-roll you ask Codex to add gets its title and tags the same way, right then. It asks first only if the table needs a new field.

Codex can add a b-roll clip, a picture, or a style only on that Content page. It will not write to a different workspace, and it never deletes or renames anything.

**B-roll.** Runway is the usual place for AI B-roll: generate the clip, download the MP4, and add it to your B Roll database (or ask Codex to upload it). For free stock, use Mixkit at <https://mixkit.co/free-stock-video/>: search, download a free clip, and add it the same way. The kit then indexes it like any other clip. Marking a clip AI or stock records where it came from. It does not clear the licence. Details: `docs/NOTION-MCP.md`.

## Finish in CapCut

Say **"send it to CapCut"**. Codex renders the edit if it isn't yet, then makes a CapCut project with the whole finished video in it (captions, b-roll and graphics included). Quit and reopen CapCut: the project is in your Projects list, ready to trim, add music or text, or cut up. The kit's captions are part of the video there, so to change a caption, ask Codex to change the edit and send it again.

## A richer look
Say **"go crazy"**, **"be creative"**, or **"make the graphics look cool."** Codex switches to the premium-motion look
(kinetic titles, a count-up stat, a sticker callout, a lower third, a swipe) and shows you a preview. A plain
"make a Short" stays on your usual red captions.

If none of the saved looks fit the footage, Codex may save a new style on its own and tell you the name. Say keep it,
tweak it, or delete it. Your existing styles are not overwritten.

A reel you like still works. Save the video, drag it in, and say **"make a style from this."** If you also want the
graphics to go further, say so: Codex copies the reel's look and builds the motion graphics into that same style.

## Graphics
"What graphics do I have?" lists the kit's own (logo pop, picture card, text card) plus the premium-motion pieces.
There are also about 200 ready-made animated pieces (chat and app mock-ups, lists, numbers, titles): ask for one
("show this as a text conversation", "a list of the 3 steps") and Codex finds and places it. Anything that doesn't
exist yet, Codex builds into the style for this video.

## If something goes wrong
- Codex tells you in plain words what failed. A failed video never lands in `done/`.
- "Run setup" (or "check my kit") fixes missing installs.
- Say **"turn on support diagnostics"** once. Codex explains the private GitHub destination and enables it after your request, then you review the hooks in Codex. Supported tool calls, errors and graphic sources sync as redacted technical records. Say **"turn off support diagnostics"** to stop. See `docs/SUPPORT.md`.
- Mitchell can read the records from GitHub and prepare a fix for the next kit update. Issues, email and messages are prepared for explicit approval, never sent automatically.
