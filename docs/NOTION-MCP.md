# Notion Content hub

Codex uses the Notion connection already signed in (`mcp__notion__*`). Do not create a
Notion integration, and do not paste a token. `library sync` and `library connect` are
disabled compatibility commands: they exit with an error and never read the Keychain,
an environment variable, or the Notion HTTP API.

The page to connect is Matthew's existing Content page in Cold Approach HQ, the live hub
he already uses. Do not point this at a test copy. It already has tables such as Posts,
Scripts, B Roll Clips and a Graphics database. The kit needs four: B-roll, Pictures,
Graphics and Styles. **Run the one-time setup first** (below): it reuses the tables that are
there, adds only the fields the kit needs, and creates the ones that are missing, after
he says OK. Nothing is ever deleted or renamed, and no field changes type.

## One-time Content page setup (run this first)

1. `notion-fetch` the Content page URL. List every database directly on that page with
   its title, database id, data source id, and schema (`{field name: {type}}`).
   Use only that page; never search the workspace by name.
2. Write `hub.json`: `{"workspace_id": ..., "hub_id": <Content page id>, "databases": [...]}`.
3. `bin/kit library setup --input hub.json` prints the plan. Show him the `summary`
   lines in plain words ("I'll add Pictures and Styles tables, and add Tags and a file
   field to B Roll Clips") and wait for his OK.
4. Apply exactly the plan with the Notion connection: `create_database` steps become new
   tables under the Content page with exactly the listed fields (Origin options AI,
   Stock, Own); `add_properties` steps add only the listed fields to that table. Never
   delete or rename a table or field. Never write outside the Content page.
5. Fetch the tables again and continue with the setup below (detect, plan, index).
   Then `bin/kit style push <style>` works, because Styles now has a file field.

## What Matthew does

1. In Notion, open the Content page. Share it with the Notion connection Codex already
   uses (the page's ••• menu → Connections). That is the authorization for this session.
2. In Codex, in this kit folder, say: "Use the library skill to set up my Content page
   and build the local index." Paste the Content page URL. Codex shows the setup plan
   and waits for his OK before changing anything.
3. To pick up new clips later, say "refresh my library". To add a file, see
   [Getting B-roll](#getting-b-roll) below, or hand Codex the file and ask it to upload
   the file into that same Content page.
4. This version is **2.3.4**. Say **"update my kit"** or **"update-my-kit"**. Codex runs
   `bin/kit update`, which is a `git pull`. Styles in `my-styles/` and files in `library/`
   stay put.

## Guardrail: where a write is allowed

Reads and writes stay inside the one hub recorded when this session configured that
Content page. The layout file stores its `workspace_id` and `hub_id`. `asset_upload`
is `authorized_hub` only when both were saved. `notion_writeback` on the layout stays
false: that flag is not a licence to push anything. Status, QA and comments are never
written.

Allowed remote changes: the one-time setup plan above (after his OK), the B-roll title
and tag plan ([below](#b-roll-titles-and-tags-in-notion); his request to sort, tag or
add B-roll is the go-ahead), and:

- `bin/kit library upload <file> --role broll|pictures|styles --name "<title>" [--origin ai|stock|own|unknown]`
  prints one create plan. Codex may apply it only when the command exits 0 and every
  id still matches the page just fetched.

Before applying that plan:

1. Fetch the destination database with the Notion connection. Confirm its workspace id
   is `workspace_id` and its parent is `hub_id` (compare ids with or without dashes).
   If either check fails, or you cannot tell, do not write.
2. Create one page in that database only. Set only the properties named in `properties`
   (the title that already exists). Attach the local file to `files_property`. Put `body`
   on the page as content.
3. Outside the one-time setup, do not add, rename, or delete properties. Do not create select options. Do not upload
   the local poster, and do not add a cover or poster column. Do not write status, QA,
   tags, or comments. Do not create a page in any other database, hub, or workspace.
   An upload carries only the name he gave (`descriptive_labels: false`), so for B-roll
   the title is provisional and the plan says `completion_required: true`: finish its
   `required_steps` (look at the frames, title and tag the page, read it back) in the
   same request. See [Adding a clip](#adding-a-clip-picture-or-style).

`library sort writeback` without `--input` plans nothing, whatever phrase is passed
(including the old "sort my Notion and save tags to Notion"). With a fresh snapshot,
`library sort writeback --input snapshot.json` prints the B-roll title and tag plan.
`library workflow` is local QA bookkeeping: `properties` and `patches` are empty. Do not
apply them to Notion.

A different workspace or a different hub is a hard stop, even if the schema looks the same.

## One-time setup

From the kit root, with the Content page URL:

Codex must resolve the real database and view ids under that hub. Do not search the
workspace by a global name and take the first hit. Map roles `broll`, `graphics`,
optional `pictures`, `posts`, optional `videos`, and `styles` when that database is
present and already has a title and a files property. Title and files properties are
detected by type and preferred names (`Files & media`, `File`). An ambiguous schema
fails instead of guessing. Tags, Origin, Duration and Original title are optional for
indexing; only a setup plan he approved ever creates one.

After the one-time setup every kit table has a files field. If a table still has
none, run setup again rather than leaving the role out.

Codex saves `schemas.json` with this envelope. Each `fetch` is the raw MCP notion-fetch
result, not invented schema data:

```json
{
  "workspace_id": "workspace id of the shared Content page",
  "hub_id": "id of that Content page",
  "workflow": "posts",
  "workflow_settings": {
    "status_property": "Status",
    "edit_statuses": ["Filmed", "Editing"],
    "review_status": "In review",
    "posted_status": "Posted",
    "flag_property": "Flag",
    "failure_flag": "Needs fix"
  },
  "roles": {
    "broll": {"fetch": {}, "view_url": "view://the-unfiltered-broll-table"},
    "graphics": {"fetch": {}, "view_url": "view://the-unfiltered-graphics-table"},
    "pictures": {"fetch": {}, "view_url": "view://the-unfiltered-pictures-table"},
    "styles": {"fetch": {}, "view_url": "view://the-unfiltered-styles-table"},
    "posts": {"fetch": {}, "view_url": "view://the-edit-queue"}
  }
}
```

The status strings above are examples. Read his schema and save the mapping you agree.
Never silently create missing status options. Videos mode uses `status_property`,
`edit_statuses`, `review_status`, optionally `failure_status` and `qa_property`. It
does not assume a Posts database exists.

`bin/kit library detect` records `asset_upload: "authorized_hub"` when both ids are
present, and leaves `notion_writeback` false.

Exact one-time shell commands after Codex has written the exports:

```sh
mkdir -p "$HOME/.matthew-studio-kit"
bin/kit library detect --input schemas.json
bin/kit library plan --input inventory.json > refresh-plan.json
bin/kit library index --input refresh.json
bin/kit library find "dating profile" --kind graphic
bin/kit library find "cafe" --kind broll --origin stock
bin/kit library find "cafe ai" --kind broll --origin ai
```

Defaults are `~/.matthew-studio-kit/notion_layout.json` and `notion_index.json`.
Override with `KIT_NOTION_LAYOUT`, `KIT_NOTION_INDEX`, or `--layout`, `--index`.
JSON input can be piped with `--input -`. These commands do not call Notion. Codex
fetches and downloads; the commands only read the files Codex wrote.

## Export and refresh protocol

1. `notion-fetch` each configured database or data source and its saved view. Query
   each asset role's unfiltered Table with `notion-query-data-sources`,
   `data:{mode:"view",view_url:...,page_size:50}`. Follow `next_cursor` until
   `has_more:false`. Do not treat a partial or filtered view as a complete inventory.
   Posts edit queues are filtered and are never a full asset inventory.
2. Normalize each view row to `{id,role,title,files:[{name,ref}]}`. Decode Markdown
   escapes and link labels in MCP rich-text titles (for example `IMG\_1234`, or an
   automatically linked `.mp` substring) to the same plain title a page fetch returns.
   The indexer also runs that decode, so a later plain title still matches.
   Decode the files property's `file://` JSON wrapper to recover the stable attachment
   identity and name; keep that wrapper as `ref`. Never use a signed URL as identity.
   Include `last_edited_time` when supplied. Include known content hashes when supplied
   consistently. Write `{rows:[...],complete_roles:["broll","graphics"]}` as
   `inventory.json`. It contains every row in those roles, including rows with no file.
3. `library plan` prints the ids that need a full read. Fetch only those page ids.
   Read the body, provenance, and actual `page_last_edited_at`. Keep each file's
   `ref` (its stable identity from the files property). **Do not download anything
   during a refresh.** His library can be hundreds of gigabytes; files stay in Notion
   until an edit uses one.
4. Export changed pages as `{id,role,title,files:[{name,ref}]}` (no `path`), plus the actual
   `body`, `last_edited_time`, and optional `tags`, `origin`, `kind`.
   Write `refresh.json` as `{inventory:<full inventory>,pages:[changed pages]}`.
5. `library index` lists those files by page id and ref (name, tags, provenance) without
   downloading them. Rows missing from an explicitly complete role become stale. They are
   not deleted.
6. Its result includes `broll_labels_pending`: how many B-roll pages are new or changed
   and have no reviewed title and tags yet. A refresh downloads none of them. Tell him
   the count. If his request was to add, sort or tag B-roll, go on and label them in
   batches (visual sorting below); if it was only "refresh", stop at the count.

## Using a Notion file in an edit (download only what the edit uses)

1. `bin/kit library find "<words>"`. A hit that is not on this Mac yet shows
   `downloaded: false` and a `next_step`.
2. Download only that file: `notion-get-file-download-urls` for its `notion-file-block://`
   reference (or `notion-fetch` with `include_file_urls:true` when the media is only on a
   files property). Save it under `~/.matthew-studio-kit/assets/`. The URLs expire after
   about an hour, so download right before you use it.
3. `bin/kit library attach <page_id> <downloaded file>` hashes it, reads its length and
   shape, and makes a poster. Then place that path in `edl.json`.
4. A file already attached is reused next time; it is not downloaded again.

**Incremental limit:** a minimal-schema view may omit edit time. The cheap scan then
sees renamed titles and new or changed file references, plus local hash changes. It
cannot see a body-only edit, or bytes replaced behind an unchanged URL, without reading
them. Use `library plan --force` and `library index --force` for a full audit, or pass
real edit metadata when the connection provides it. Never claim a body was rechecked
when it was not. No Tags, Origin, Poster, or Licence column is required.

## Lookup and overrides

`library find "query" --kind broll|graphic|picture|style --origin ai|stock --aspect vertical|horizontal|square --limit 10`
prints scores, token, synonym, and fuzzy-title reasons, paths, metadata, and provenance.
Stock means **not detected as AI**, not a licence clearance. Lexical AI inference
(ai, veo, runway, sora, wan, generated) can be wrong. Read the provenance before use.
For vague filenames, use the optional visual-sorting workflow below. Visual origin and
time-of-day notes are fallible observations, not provenance proof.

To keep a correction across refreshes:

```sh
printf '%s\n' '{"page_id":"the-page-id","patch":{"tags_add":["favorite"],"tags_remove":["unwanted"],"origin":"stock","exclude":false,"title":"Morning cafe walk"}}' | bin/kit library override --input -
```

Overrides live in a separate page-id section of the local index. In the Notion plan,
`title` replaces the generated title, `tags_add` are added, `tags_remove` are not added
(a tag already on his page is never taken off), and `exclude` skips the page.

## Adding a clip, picture, or style

He can add a row himself in the existing database (B Roll Clips, Pictures, or Styles):
a natural title, the file on the existing files property, and source, licence, and AI
disclosure in the page body. For a graphic he already files by hand, use Description
of Graphic plus Files & media. Then ask Codex to refresh the index.

Or ask Codex to upload a local file. Codex runs `library upload` and applies the plan
under the guardrail above. Roles Codex may create are `broll`, `pictures`, and `styles`
only, and only when that role was mapped with a real database id. Graphics, posts, and
videos are indexed from rows he already has; upload will not create those.
`--origin` is written as a sentence in the page body. It is provenance, not a licence
clearance, and it does not create an Origin column or a new select option. If the body
says the clip is from Runway, the next index can infer origin `ai` from that text.

**B-roll is not added until it is titled and tagged.** Whenever a B-roll clip goes into
Notion through Codex, the create is the first half. In the same request, without asking
again: refresh the index, `library attach <new page id> <the local file>` (it is already
on this Mac, nothing to download), `library sort frames`, look at every frame,
`library sort apply`, take a fresh snapshot, `library sort writeback --input snapshot.json
--page-id <new page id>`, apply the patch, then snapshot and run it once more. Say
"added" only when that last run lists the page under `unchanged`. If something blocks
(a missing field that needs his OK, a frame you could not judge), say the clip is in
Notion but not yet titled and tagged, and why. A clip he adds to Notion by hand shows
up in `broll_labels_pending` at the next refresh.

After a successful upload, refresh the index so `library find` sees the new file.
Also `bin/kit library add <file> --type broll|picture --name "<title>"` when he wants
the file in `library/` for an edit before the next refresh. Sound effects stay local
(`library add --type sfx`); they are not a Notion upload role.

## Getting B-roll

Two places to get a clip, then the same path into his B Roll database. The kit indexes
it like any other clip. AI or stock is provenance, not a licence clearance.

**Runway (primary AI B-roll).** Generate the clip in Runway. Download the MP4. Add that
file to the B Roll Clips database on his Content page, or ask Codex to upload it into
the authorized hub (`library upload <file> --role broll --name "<what he calls it>" --origin ai`).

**Mixkit (free stock).** Open <https://mixkit.co/free-stock-video/>, search, and download
a free clip. Spell it Mixkit. Upload it the same way, with `--origin stock` when he
wants that provenance sentence in the page body.

Then refresh the index. `library find "cafe" --kind broll --origin ai` and
`--origin stock` are separate filters. Stock here means the index did not mark the
clip as AI. It does not mean the licence was checked.

## Local QA records

`bin/kit library workflow --input post-row.json --qa-report PATH/qa.json` returns
`command: local_qa_record`, `local_status`, empty `properties`, and empty `patches`.
PASS, FAIL, and QA flags stay on this Mac. Do not apply this record to Notion. A
human-posted flag does not enable a Notion write.

## Visual sorting, no external API

Say **sort my Notion**. Follow [the sorting skill](../skills/sort-my-notion/SKILL.md).
A refresh never downloads. Sorting downloads only the files Codex is about to look at,
one batch at a time:

```sh
bin/kit library sort plan --batch 10        # to_download: still in Notion; to_sort: on this Mac, not reviewed
# download only download_batch through the Notion connection, then for each file:
bin/kit library attach <page_id> <downloaded file>
bin/kit library sort frames --frames-dir "$HOME/.matthew-studio-kit/sort-frames" > frames.json
# Codex opens every extracted frame with its built-in image viewer,
# then writes tags.json using engine/sort_schema.json and the manifest hashes.
bin/kit library sort apply --input tags.json
bin/kit library find "woman walking cafe brown hair" --kind broll
bin/kit library sort plan                   # repeat until to_download and to_sort are empty
```

Use `--index <path>` or `KIT_NOTION_INDEX` to keep a run in a test directory.
Add `--ignore-body` to frames, plan, and find for a body-free evaluation. Strict search
recomputes lexical tags without the body and ignores body-aware visual records.
Annotations are per page id plus file SHA256. Source and frame hashes must match
before an atomic apply. Manual overrides win. The same attachment keeps its local copy
and its review when the page title or tags change. Replaced bytes become stale and need
another look. Keep the frames folder: the Notion plan re-checks those frames.
Three evenly spaced frames can miss action; open more frames when the first three are
ambiguous. The CLI checks structure and hashes. It cannot tell whether the frames were
actually viewed, so never write a record for a frame you did not open.

### What a B-roll record says

All values come from the fixed lists in `engine/sort_schema.json`. Use `unknown` (or
leave the optional field out) whenever the frames do not clearly show it.

| Field | Values |
|---|---|
| `people.count` | `0`, `1`, `2`, `3+` |
| `people.subjects[]` | one per visible person (up to 3): `descriptor` woman, man or unknown; `hair_color`; `hair_length` (bald, covered included); `hair_style`. Each trait stays with its own person. |
| `action` | walking, talking, sitting, texting, ... `none`, `unknown` |
| `setting`, `shot_type`, `subject`, `mood`, `time_of_day` | as before; put the main subject noun first |
| `ethnicity` (optional) | only with `evidence.source` `user-statement` or `source-metadata` and the exact `quote` |
| `source_credit` (optional) | a name the page or file name actually gives (Mixkit, a credited creator), with the `quote` |

Rules the kit enforces on `sort apply`:

- A B-roll record needs `action`, and `people.subjects` whenever someone is visible.
  Records for graphics and pictures are unchanged.
- There is no age field and no name field for a person. Never identify anyone.
- **Ethnicity comes from recorded evidence, never from appearance.** The schema rejects
  `vision`, a title, a file name or a guess as the source. `source-metadata` must quote
  words found in the page body or in a Notion tag he supplied (never a tag the kit added),
  and the quote must state the value. The Notion plan checks the quote again against the
  page's current body and tags.
  `user-statement` must quote what he said about this clip, and that must state the
  value. With several people, `applies_to` says which listed person it is about.
  Race and nationality follow the same rule. When in doubt, leave it out.
- In a clip with two people, hair and ethnicity become tags only as
  `woman - brown hair` style pairs, and only when the two people have different known
  descriptors. Otherwise they are left out. Groups get no hair tags.

### Title format

One format, built only from those reviewed fields. Unknown parts are left out; fewer
than two known parts means no title is proposed.

| Clip | Title |
|---|---|
| one person | `Woman - walking - cafe - brown hair` (`<Subject> - <action> - <setting> - <hair>`) |
| one person, ethnicity given with evidence | `Woman - walking - cafe - brown hair - Latina` (never added without the evidence; left out of titles with several people) |
| two people | `Woman and man - talking - bar`, `Two women - ...`, `Two people - ...` |
| three or more | `Group - dancing - club` |
| nobody | `Phone - dating app - close-up` (`<Subject> - <setting> - <shot type>`) |

`library find` shows this as `kit_title` and matches the new labels (`ai.labels=...`).
Everyday words find the fixed labels: girl, girls, women, lady find `woman`; guy, men find
`man`; brunette finds `brown hair`; blond finds `blonde hair`; redhead finds `red hair`.
These are search conveniences only. They add no label and say nothing about age or identity.

## B-roll titles and tags in Notion

Reviewed B-roll labels are stored on the pages of the B Roll table of the authorized
Content hub: the page title, the existing **Tags** field, and a one-time **Original
title**. The kit only prints a plan (`write_performed` is always false); Codex applies
it with the Notion connection. No token, no HTTP API.

1. Refresh the index and finish the visual sorting above for the clips to label.
2. Take a snapshot now, with the Notion connection: `notion-fetch` the B Roll database
   (its id, data source id, parent page, workspace, schema with the Tags options), then
   query its unfiltered Table view and follow `next_cursor` until `has_more:false`.
   Write `snapshot.json`:

   ```json
   {
     "workspace_id": "...", "hub_id": "the Content page id",
     "fetched_at": "2026-11-10T20:00:00Z", "complete": true,
     "database": {"database_id": "...", "data_source_id": "...", "parent_id": "the Content page id",
                  "schema": {"Name": {"type": "title"}, "Tags": {"type": "multi_select", "options": [{"name": "favorite"}]},
                             "Original title": {"type": "rich_text"}}},
     "pages": [{"id": "...", "parent_database_id": "...", "title": "IMG_1234", "last_edited_time": "...",
                "properties": {"Tags": ["favorite"], "Original title": ""},
                "files": [{"name": "IMG_1234.mp4", "ref": "file://..."}],
                "body": "page text as fetched now"}]
   }
   ```

   Every value is what Notion returned, not a guess. `complete` is true only when every
   page of the view was read. Set `parent_database_id` (or `parent_data_source_id`) per
   page from that page's own parent.
   - `last_edited_time` is required on every page. It must equal the edit time the index
     holds for that page; if the page was edited since the last refresh, the page is
     blocked until you refresh.
   - `body` is required on a page whose review gives ethnicity with `source-metadata`:
     fetch that page and put its current text here. The quote is checked against this
     body and the tags in this snapshot, not against what the index remembered. Tags the
     kit added itself never count as evidence, so a label cannot support itself. Other
     pages may leave `body` out.
3. `bin/kit library sort writeback --input snapshot.json [--page-id id,id]` prints the plan.
4. Approval. `approval: covered_by_his_request_to_tag_or_add_broll`: when he asked to
   sort, tag, title or add B-roll, that request is the go-ahead for the patches. Do not
   ask again; tell him what changed afterwards. A plain "refresh" is not such a request.
   `approval: needs_his_ok` (a `setup_required` plan that adds fields) always waits for
   his OK, and so does anything outside this plan.
5. For each entry in `patches`, before `valid_until`: fetch the page again, confirm it
   is still in that database under that hub and still shows every value in `expected`
   (title, tags, original title, files, last_edited_time). If anything differs, skip it and start again
   from a new snapshot. Then set only the properties in `set`. The Tags value in `set`
   is the complete new value. If `options_to_create` is not empty and the connection
   does not create options on write, add exactly those options to the Tags field first.
   `notion-update-page` uses `command: "update_properties"`, the patch's `page_id`,
   and `properties` equal to `set`; multi-select values are arrays of strings.
   To add options with `notion-update-data-source`, fetch the latest schema and use
   its specific data source id. Its `ALTER COLUMN` operation replaces the option
   list: **include every existing option plus the additions**, preserving existing
   names and colors. `options_to_create` is only the additions, never the full
   replacement list. Omitting an old option removes it. Fetch again to confirm the
   schema before applying page patches. Do not invent unsupported DDL syntax.
6. Refresh the index (the write changed the pages' edit time), take a new snapshot and
   run the command again. Pages that took the change are listed
   under `unchanged` and `patches` is empty for them. Only say a page was titled and
   tagged when that second run shows it. Pages under `blocked` or `needs_his_correction`
   are not finished; say so. Then refresh the index.

What the plan refuses or holds back:

| Situation | Result |
|---|---|
| snapshot from another workspace, hub, database or data source; the B Roll table not directly on the Content page; hub not recorded | command fails, nothing planned |
| snapshot older than 30 minutes, dated in the future, or without a timezone | command fails; fetch again |
| title field is not the mapped title, Tags options not listed, two fields named Tags | command fails (`invalid schema`) |
| Tags or Original title missing | `status: setup_required` with one `add_properties` step for that table only; no page changes. Apply it after his OK, then snapshot again |
| Tags is not multi-select or text, Original title is not text | `status: schema_conflict`; nothing written, no field retyped, no other field used |
| page's parent is not the B Roll table, or not stated | that page is `blocked` |
| page not in the index, not a b-roll row, or its files (name and ref) differ from the index | `blocked`; refresh first |
| a file not downloaded, not reviewed, reviewed for other bytes, local file changed, frames missing or changed, record without the descriptive fields, confidence under 0.7 | `blocked` |
| the stored review is not a valid record (checked before anything else, so a damaged record blocks instead of crashing), or it no longer passes the evidence rules against the snapshot's current body and tags (the quoted ethnicity or source words are gone, or the only support is a tag the kit added) | `blocked` (`review_no_longer_valid`); review the clip again |
| the page's `last_edited_time` is missing from the snapshot or differs from the index | `blocked` (`edit_time_missing_from_snapshot`, `page_edited_since_index_refresh_first`) |
| a review cites `source-metadata` for ethnicity and the snapshot page has no `body` | `blocked` (`snapshot_needs_page_body_for_source_evidence`) |
| current tags, title or original title missing from the snapshot | `blocked` (the kit will not overwrite what it cannot see) |
| `--page-id` not in the snapshot, or a page listed twice | command fails (`ambiguous target`) |

What it preserves:

- **His tags.** The new Tags value is the tags the page already has, in order, plus the
  missing kit tags. An existing option is reused in its own spelling. No option is
  renamed or recolored; a text Tags field is appended to.
- **Only the kit's own tags are ever replaced.** A tag counts as the kit's own only if
  an earlier plan proposed adding it and a later snapshot showed it on the page. A plan
  alone is not a receipt. When a new review no longer supports such a tag (brown hair
  corrected to blonde hair), the patch leaves it out and lists it in `removes_tags`.
  A tag that no longer fits but was his, or was never confirmed, stays on the page and
  is reported under `needs_his_correction`: tell him, and do not call the page corrected.
- **A kit tag he took off stays off** (`removed_in_notion`) unless he adds it back with a
  `tags_add` override.
- **The first title.** It goes into Original title the first time the kit retitles a
  page and is never replaced. File names, files, the page body and Origin are not touched.
- **His later edits.** If he renames a page after the kit titled it, the kit leaves the
  title alone (`title_edited_in_notion`). A `title` override is the way to change it.
- **Several files on one page.** Every file must be reviewed. If they agree, the page
  gets that title and the tags of all files. If they show different things, the title is
  left alone and only tags true of every file are added (`multi_file_conflict`).
- Two pages may end up with the same title; `duplicate_titles` lists them.

Limits: the plan cannot see Notion, so it is only as true as the snapshot; it never
proves a write happened. Notion's edit time is coarse (to the minute), so the edit-time
check catches most edits made since the refresh, not all; that is why source evidence is
read from the snapshot body as well. Which tags are the kit's own is remembered in the local index;
if that index is rebuilt, older kit tags count as his and are reported, not removed, and
a title the kit set earlier is treated as hand-edited and left alone.
The kit cannot check that a quoted user statement was really said.
