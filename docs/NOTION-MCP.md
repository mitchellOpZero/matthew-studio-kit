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
4. This version is **2.0.2**. Say **"update my kit"** or **"update-my-kit"**. Codex runs
   `bin/kit update`, which is a `git pull`. Styles in `my-styles/` and files in `library/`
   stay put.

## Guardrail: where a write is allowed

Reads and writes stay inside the one hub recorded when this session configured that
Content page. The layout file stores its `workspace_id` and `hub_id`. `asset_upload`
is `authorized_hub` only when both were saved. `notion_writeback` on the layout stays
false: that flag is not a licence to push tags, status, or QA.

Allowed remote changes: the one-time setup plan above (after his OK), and:

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

`library sort writeback` always returns an empty patch list, including the old phrase
"sort my Notion and save tags to Notion". Visual tags stay on this Mac.
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
fails instead of guessing. Tags, Origin, and Duration are optional and are never created.

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
   Read the body, provenance, and actual `page_last_edited_at`. Resolve files with
   `notion-get-file-download-urls` for the `notion-file-block://` references the fetch
   returned. If media exists only on a files property and the MCP result has no such
   reference, `notion-fetch` with `include_file_urls:true` supplies download URLs.
   Do not invent block references or add a block just for indexing. Match downloaded
   names and identities to the files property.
4. Download through the short-lived URLs into a local asset cache. Keep every file;
   do not silently keep only the first attachment. Verify the downloads.
   Export changed pages as `{id,role,title,files:[{name,ref,path}]}`, plus the actual
   `body`, `last_edited_time`, and optional `tags`, `origin`, `kind`.
   Write `refresh.json` as `{inventory:<full inventory>,pages:[changed pages]}`.
5. `library index` hashes the local bytes, probes the media, writes local PNG posters,
   and stores entries keyed by page id plus SHA256. It never uploads posters or adds
   columns. Rows missing from an explicitly complete role, and replaced hashes, become
   stale. They are not deleted. Unchanged bytes reuse the local metadata and poster.

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
printf '%s\n' '{"page_id":"the-page-id","patch":{"tags_add":["favorite"],"tags_remove":["unwanted"],"origin":"stock","exclude":false}}' | bin/kit library override --input -
```

Overrides live in a separate page-id section of the local index.

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

After a successful upload, refresh the index so `library find` sees the new file.
Also `bin/kit library add <file> --type broll|picture --name "<title>"` when he wants
the file in `library/` for an edit before the next refresh. Sound effects stay local
(`library add --type sfx`); they are not a Notion upload role.

## Getting B-roll

Two places to get a clip, then the same path into his B Roll database. The kit indexes
it like any other clip. AI or stock is provenance, not a licence clearance.

**Runway (primary AI B-roll).** Generate the clip in Runway. Download the MP4. Add that
file to the B Roll Clips database on his Content page, or ask Codex to upload it into
the authorized hub (`library upload <file> --role broll --name "<what it shows>" --origin ai`).

**Mixkit (free stock).** Open <https://mixkit.co/free-stock-video/>, search, and download
a free clip. Spell it Mixkit. Upload it the same way, with `--origin stock` when he
wants that provenance sentence in the page body.

Then refresh the index. `library find "cafe" --kind broll --origin ai` and
`--origin stock` are separate filters. Stock here means the index did not mark the
clip as AI. It does not mean the licence was checked.

## Local QA records

`bin/kit library workflow --input post-row.json --qa-report PATH/qa.json` returns
`command: local_qa_record`, `local_status`, empty `properties`, and empty `patches`.
PASS, FAIL, and tags stay on this Mac. Do not apply this record to Notion. A
human-posted flag does not enable a Notion write.

## Optional visual sorting, no external API

Say **sort my Notion**. Follow [the sorting skill](../skills/sort-my-notion/SKILL.md).
After the MCP refresh, Codex runs:

```sh
bin/kit library sort plan
bin/kit library sort frames --frames-dir "$HOME/.matthew-studio-kit/sort-frames" > frames.json
# Codex opens every extracted frame with its built-in image viewer,
# then writes tags.json using engine/sort_schema.json and the manifest hashes.
bin/kit library sort apply --input tags.json
bin/kit library find "dating profile" --kind graphic
bin/kit library sort plan
```

Use `--index <path>` or `KIT_NOTION_INDEX` to keep a run in a test directory.
Add `--ignore-body` to frames, plan, and find for a body-free evaluation. Strict search
recomputes lexical tags without the body and ignores body-aware visual records.
Annotations are local, per page id plus file SHA256. Source and frame hashes must match
before an atomic apply. Manual overrides win. The same bytes keep their annotations
when the title changes. Replaced bytes become stale and need another look.
Three evenly spaced frames can miss action; open more frames when the first three are
ambiguous. The CLI checks structure and hashes. It cannot tell whether the frames were
actually viewed.

`library sort writeback` returns no patches. Do not append, update, or delete Notion
pages to store visual tags.
