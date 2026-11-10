# Remote support through the private GitHub repository

Support is off until explicitly enabled on the computer being diagnosed. Installing this update
does not turn it on. It records supported local Codex tool calls and kit provenance so Mitchell
can inspect the evidence from GitHub, then prepare a normal kit update.

## On Matthew's computer

From the kit folder, after updating to 2.2.0:

```sh
bin/kit support enable
bin/kit support status
```

Enable checks that `mitchellOpZero/matthew-studio-kit` is still private and that the current `gh`
login has write access. It never reads or prints the login token and never changes account
permissions. If the account only has read access, it reports that problem instead of silently
claiming remote support works. Repository membership must be resolved separately by its owner.

Enable merges project hooks into `.codex/hooks.json`, backs up an existing file privately, and
preserves unrelated handlers. The generated file is gitignored. Plugin installations also bundle
the same observer under `hooks/hooks.json`. Duplicate tool events from both sources share an id.

**Review hooks in Codex** using the composer or **Settings > Hooks**; CLI users can use `/hooks`.
Changed hooks/scripts require another native review. Do not bypass it. Then start/resume a chat
in the kit and perform a normal task. `support status` must show observed `PreToolUse` and
`PostToolUse` events; installation alone is not evidence of execution. A desktop app may use a
different bundled engine from the `codex` executable on PATH. Doctor reports these distinctly.

For an existing troublesome edit:

```sh
bin/kit support doctor
bin/kit support inspect the-job-name
bin/kit support sync --force
```

Inspect queues the safe snapshot when enabled. It resolves the actual saved/built-in style,
per-video style overrides, block source priority and the graphic bytes already copied into that
project. It identifies a hand-edited preview and differing source/project files without changing
them. A difference may be intentional; it is evidence to inspect, not an automatic repair order.
Doctor also records versions, instruction hashes, available related skills and recent kit-command
summaries. Available skills do not prove they were used. Old kit logs do not reconstruct past
Codex calls. Tracking can only observe new supported calls after enable/trust.

## Reading it from Mitchell's computer

Use the existing GitHub login with read access:

```sh
bin/kit support remote
bin/kit support remote THE_32_CHARACTER_DEVICE_ID
```

The first command lists the support devices. The second reads the latest JSON snapshot with
session/turn/call ids, tool names, command summaries, outcomes, unmatched calls and provenance.
No hosted server, extra account or public endpoint is needed. The fixed data file is
`.support/diagnostics.json` on `support/<32-character-device-id>`. The local checkout never
switches branches. Transport checks the private repository identity again before uploading and
its write helper rejects source/main writes. These are application checks, not restricted GitHub
token permissions: the account's actual repository permissions may be broader.

## What is recorded

- Supported local shell, file-edit, MCP and other function-tool events, including nested tool
  calls that Codex routes through hooks. Each has a session, turn and call id when supplied.
- Tool names, input field names and safe command structure (program/script identities and kit
  verbs). Unknown argument values and inline code are omitted. Raw tool output is omitted;
  structured outcomes and recognizable exception class names are kept.
- Exact kit commit/version, instruction/style/template hashes, saved style precedence,
  per-video override keys/hash, actual project composition hashes and known font-copy differences.
- Queue health, observed hook counts, unmatched calls, last successful sync and failure category.

No raw prompts, transcripts, video, screenshots, Notion page contents, environment dumps, auth
headers or full tool arguments/output are sent. Paths are represented relative to the kit or by
limited external file identities. Capture is scoped to kit sessions; unrelated chats are skipped.
Once a session is observed inside the configured kit, calls from that session can still be
observed if its working directory changes. Other old kit folders opened as separate chats are
outside the default scope; use their own updated kit setup to observe them.

## Delivery, limits and stopping

Local capture is a short synchronous hook with no network access. A separate background worker
syncs at most once a minute; background hooks can also restart it. Local records stay queued
until the GitHub snapshot is read back and confirms their ids. Retries deduplicate an update
whose response was lost; conflict/offline/rate-limit failures keep the queue. Sync uses the `gh`
login through its own API client; no credential is copied into kit configuration.

The local queue keeps at most 3,000 events. If unsent events must be evicted, `unsent_dropped`
reports the loss. The latest GitHub file is bounded to 1,000 events and 900 KB; older redacted
versions remain in Git commit history. This is NOT automatic erasure or bounded Git history.
The kit never force-pushes, rewrites history or deletes remote records.

Hosted tools (for example hosted web search), specialized paths and older/unsupported runtimes
can be outside hook coverage. Payloads over 2 MB produce a gap marker rather than raw content.
Observer I/O failures, cancellations or disabled/untrusted hooks can also leave gaps. Never use
this feature as proof that every action was captured. Unmatched before/after records may reflect
a still-running or cancelled call, ordering differences, or records outside retained history.
Hooks observe activity; they do not approve, block or rewrite any tool, change permissions,
grant remote shell access or automatically repair a saved style.

```sh
bin/kit support disable
bin/kit support uninstall-hooks
```

Disable stops new collection and sync; the worker exits. A request already accepted by GitHub
may still finish. Existing records remain; export locally with `support export`. Resuming an old
queue requires an explicit `support enable --resume-queued`. Re-enabling starts a new worker.

GitHub issues, comments, email and messages are separate communications. They are prepared for
approval and are never the automatic transport for support data. Saved styles and hand edits
must be reviewed before any repair overwrites them. A code fix is delivered through the normal
kit update path after its review; support branches are data branches and must not be merged.

Sources: [Codex hook contracts and tool coverage](https://learn.chatgpt.com/docs/hooks),
[GitHub repository contents API](https://docs.github.com/en/rest/repos/contents),
[GitHub reference API](https://docs.github.com/en/rest/git/refs).

## Comparing the two laptops

Run this from each laptop's actual kit folder, in the same context used for the edit:

```sh
bin/kit support doctor > laptop-report.json
bin/kit support inspect the-job-name > video-report.json
```

Use different filenames for the two laptops. Copy the reports to one computer, then:

```sh
bin/kit support compare mitchell-report.json matthew-report.json
```

The comparison lists missing and changed instruction/config/skill sources. Doctor inventories
Codex-home AGENTS files, project AGENTS and overrides, ancestor candidates, configuration
fingerprints, command approval rules, local skills and cached plugin skills. Duplicate skill
names with different content are flagged. Contents and configuration values are never exported.
`support rules --cwd /path/to/the/chat/folder` checks a nested launch folder explicitly.
The reported candidate chain uses default discovery; custom fallback names, size limits, trust,
plugin enablement and already-running chat context can change what Codex actually loaded.
Cached does not mean enabled; present does not mean used. Tool records separately show observed
references to AGENTS, SKILL.md, config and rules files when the supported call exposes them.
When support is enabled, inventory sources sync in numbered parts sharing a scan id. All parts
must be present before treating a remote inventory as complete. Without support, reports remain
local. Never commit local reports to the source branch.

Compare kit/app versions and the two video reports as well: saved styles, per-video overrides,
fonts, hand edits and copied graphic bytes can differ even when the kit commit is identical.
Start a fresh chat after updating instructions; existing chat context can retain old guidance.
Use the same source clip, reference, requested style and model for a meaningful video comparison.
The report identifies differences; it cannot itself prove why an edit looks better.

Instruction discovery reference: [Codex AGENTS.md documentation](https://learn.chatgpt.com/docs/agent-configuration/agents-md).
