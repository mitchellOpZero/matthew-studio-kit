"""Local frame extraction, validated Codex annotations, and the B-roll title/tag plan for Notion.

No vision or network API and no Notion call. `writeback_plan` only prints what the
Notion connection may change on B Roll pages of the authorized Content hub: the title,
the existing Tags field and a one-time Original title. Codex applies it; this module
never does, and it never reports a write as performed.
"""
import copy
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
import re
import subprocess

import notion_index as ni

SCHEMA = Path(__file__).with_name('sort_schema.json')
OPT_IN = 'sort my Notion and save tags to Notion'   # legacy phrase; it never enabled a write and still does not
BROLL = 'broll'
MIN_CONFIDENCE = 0.7
SNAPSHOT_MAX_AGE_MINUTES = 30
MAX_TAGS = 25
ORIGINAL_TITLE = 'Original title'
TAG_TYPES = {'multi_select', 'rich_text'}
TITLE_FORMAT = ('<Subject> - <action> - <setting> - <hair> for one person (Woman - walking - cafe - brown hair), plus '
                '- <ethnicity> at the end only when it was given with evidence; '
                '<Subject> - <action> - <setting> for several people (Woman and man - talking - bar); '
                '<Subject> - <setting> - <shot type> with no people (Phone - dating app - close-up). '
                'Unknown parts are left out.')


def clean_tag(text):
    """One Notion tag: plain text, no comma (Notion splits options on commas)."""
    return ' '.join(str(text).replace(',', ' ').split())[:100]


def _norm(text):
    return ' '.join(str(text).casefold().split())


def _hair_tags(person):
    length = person.get('hair_length', 'unknown')
    if length == 'bald':
        return ['bald']
    if length == 'covered':
        return []
    tags = []
    if person.get('hair_color', 'unknown') != 'unknown':
        tags.append(person['hair_color'] + ' hair')
    if length != 'unknown':
        tags.append(length + ' hair')
    style = person.get('hair_style', 'unknown')
    if style != 'unknown':
        tags.append({'ponytail': 'ponytail', 'bun': 'hair bun', 'braided': 'braided hair'}.get(style, style + ' hair'))
    return tags


def _subject_label(record):
    count, people = record['people']['count'], record['people'].get('subjects') or []
    if count == '0':
        return record['subject'][0].capitalize()
    if count == '1':
        return {'woman': 'Woman', 'man': 'Man'}.get(people[0]['descriptor'] if people else 'unknown', 'Person')
    if count == '2':
        pair = tuple(sorted(p['descriptor'] for p in people))
        return {('man', 'woman'): 'Woman and man', ('woman', 'woman'): 'Two women', ('man', 'man'): 'Two men'}.get(pair, 'Two people')
    return 'Group'


def kit_title(record):
    """The one title format (TITLE_FORMAT), built only from reviewed fixed-vocabulary fields. None if too little is known."""
    count, people = record['people']['count'], record['people'].get('subjects') or []
    parts = [_subject_label(record)]
    if record.get('action', 'unknown') not in {'unknown', 'none'}:
        parts.append(record['action'].replace('-', ' '))
    if record['setting'] != 'unknown':
        parts.append(record['setting'].replace('-', ' '))
    if count == '1' and people:
        parts += _hair_tags(people[0])[:1]
        if record.get('ethnicity'):       # only ever present with recorded evidence (check_record); one person, so no doubt who it is about
            parts.append(' '.join(record['ethnicity']['value'].split()))
    elif count == '0':
        parts.append(record['shot_type'])
    unique = [p for i, p in enumerate(parts) if p.casefold() not in {q.casefold() for q in parts[:i]}]
    return ' - '.join(unique) if len(unique) >= 2 else None


def kit_tags(record):
    """Searchable tags from a reviewed record. A trait of one person is never attached to another."""
    count, people = record['people']['count'], record['people'].get('subjects') or []
    known = [p['descriptor'] for p in people if p['descriptor'] != 'unknown']
    # In a clip with several people a trait is only tagged when it can be pinned to one of them by a descriptor nobody else shares.
    owner = lambda i: (people[i]['descriptor'] if people[i]['descriptor'] != 'unknown'
                       and [p['descriptor'] for p in people].count(people[i]['descriptor']) == 1 else None)
    tags = []
    if count == '0':
        tags.append('no people')
    elif count == '1':
        tags += known + (_hair_tags(people[0]) if people else [])
    else:
        tags += ['two people' if count == '2' else 'group'] + list(dict.fromkeys(known))
        if count == '2' and len(people) == 2:
            for i, person in enumerate(people):
                if owner(i):
                    tags += [f'{owner(i)} - {t}' for t in _hair_tags(person)]
    if record.get('action', 'unknown') not in {'unknown', 'none'}:
        tags.append(record['action'])
    if record['setting'] != 'unknown':
        tags.append(record['setting'])
    tags.append(record['shot_type'])
    tags += record['subject']
    if record['time_of_day'] in {'day', 'night', 'dusk', 'dawn'}:
        tags.append(record['time_of_day'])
    if record['mood'] not in {'neutral', 'unknown'}:
        tags.append(record['mood'])
    ethnicity = record.get('ethnicity')
    if ethnicity and people:
        value = _norm(ethnicity['value'])
        if len(people) == 1:
            tags.append(value)
        elif owner(int(ethnicity['applies_to'])):
            tags.append(f"{owner(int(ethnicity['applies_to']))} - {value}")
    if record.get('source_credit'):
        tags.append(_norm(record['source_credit']['name']))
    return list(dict.fromkeys(clean_tag(t) for t in tags))


def kit_added(index, page_id):
    """Tags the kit itself put (or proposed to put) on this page. They can never be cited as source evidence."""
    prev = (index.get('writeback_proposals') or {}).get(page_id) or {}
    return {_norm(t) for field in ('owned', 'pending_adds', 'pending_removes') for t in prev.get(field, [])}


def check_record(record, entry, generated=frozenset()):
    """Rules the JSON schema cannot express: who a trait belongs to, and what counts as evidence.

    generated: tags the kit added to the page (kit_added). A label must not become its own evidence.
    """
    key = record['entry_key']
    count, people = record['people']['count'], record['people'].get('subjects')
    if entry['role'] == BROLL:
        if 'action' not in record:
            raise ValueError('b-roll record needs action (unknown when unclear): ' + key)
        if count != '0' and not people:
            raise ValueError('b-roll record with people needs people.subjects (descriptor unknown when unclear): ' + key)
    if people is not None:
        if count == '0' or (count in {'1', '2'} and len(people) != int(count)):
            raise ValueError('people.subjects does not match people.count: ' + key)
        for person in people:
            if person.get('hair_length') in {'bald', 'covered'} and {person.get('hair_color', 'unknown'), person.get('hair_style', 'unknown')} != {'unknown'}:
                raise ValueError('bald or covered hair cannot also have a color or style: ' + key)
    body = [] if record['ignore_body'] else [entry.get('body', '')]
    source_tags = [t for t in entry.get('explicit_tags', []) if _norm(t) not in generated]
    ethnicity = record.get('ethnicity')
    if ethnicity:
        if not people:
            raise ValueError('ethnicity needs a listed person: ' + key)
        which = ethnicity.get('applies_to', 0 if len(people) == 1 else None)
        if isinstance(which, bool) or not isinstance(which, int) or which >= len(people):
            raise ValueError('ethnicity.applies_to must name one listed person (0-based) when several are listed: ' + key)
        ethnicity['applies_to'] = which
        evidence = ethnicity['evidence']
        if _norm(ethnicity['value']) not in _norm(evidence['quote']):
            raise ValueError('ethnicity must be stated in the quoted words, never inferred: ' + key)
        if evidence['source'] == 'source-metadata' and not any(_norm(evidence['quote']) in _norm(t) for t in [*source_tags, *body] if t):
            raise ValueError('ethnicity quote is not in the page body or in a Notion tag he supplied (titles, file names, appearance and tags the kit added are not evidence): ' + key)
    credit = record.get('source_credit')
    if credit:
        texts = [entry.get('title', ''), *entry.get('file_names', []), *source_tags, *body]
        if _norm(credit['name']) not in _norm(credit['quote']) or not any(_norm(credit['quote']) in _norm(t) for t in texts if t):
            raise ValueError('source_credit must quote a name the page or file name actually gives: ' + key)


def validate(value, schema, location='record'):
    """Validate the deliberately small JSON Schema subset used by our fixed schema."""
    types = {'object': dict, 'array': list, 'string': str, 'number': (int, float), 'boolean': bool}
    kind = schema.get('type')
    if kind and (not isinstance(value, types[kind]) or kind == 'number' and (isinstance(value, bool) or not math.isfinite(value))):
        raise ValueError(f'{location}: expected {kind}')
    if 'const' in schema and value != schema['const'] or 'enum' in schema and value not in schema['enum']:
        raise ValueError(f'{location}: value outside fixed vocabulary')
    if kind == 'object':
        if set(schema.get('required', [])) - value.keys():
            raise ValueError(f'{location}: missing required fields')
        if schema.get('additionalProperties') is False and value.keys() - schema['properties'].keys():
            raise ValueError(f'{location}: unknown fields')
        for key, item in value.items():
            validate(item, schema['properties'][key], location + '.' + key)
    elif kind == 'array':
        if not schema.get('minItems', 0) <= len(value) <= schema.get('maxItems', float('inf')):
            raise ValueError(f'{location}: invalid array length')
        if schema.get('uniqueItems') and len({json.dumps(x, sort_keys=True) for x in value}) != len(value):
            raise ValueError(f'{location}: duplicate items')
        for item in value:
            validate(item, schema['items'], location + '[]')
    elif kind == 'string':
        if not schema.get('minLength', 0) <= len(value) <= schema.get('maxLength', float('inf')):
            raise ValueError(f'{location}: invalid text length')
        if 'pattern' in schema and not re.search(schema['pattern'], value):
            raise ValueError(f'{location}: invalid text format')
        if schema.get('format') == 'date-time':
            try:
                stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
                if stamp.tzinfo is None:
                    raise ValueError('timezone required')
            except ValueError as exc:
                raise ValueError(f'{location}: expected ISO timestamp with timezone') from exc
    elif kind == 'number' and not schema.get('minimum', -float('inf')) <= value <= schema.get('maximum', float('inf')):
        raise ValueError(f'{location}: out of range')


def descriptive(record):
    """True when a record carries the reviewed fields a B-roll title and its tags are built from."""
    people = record.get('people', {})
    return 'action' in record and (people.get('count') == '0' or bool(people.get('subjects')))


def plan(index, ignore_body=False, batch=10):
    pending, skipped, to_download = [], [], []
    for key, entry in index['entries'].items():
        if entry['stale'] or entry['role'] not in {'broll', 'graphics', 'pictures'} or ni.effective(entry, index)['exclude']:
            continue
        if not entry.get('path') or not entry.get('sha256'):
            # Listed by a refresh, still in Notion. It can only be labelled after it is downloaded and looked at.
            to_download.append({'entry_key': key, 'page_id': entry['page_id'], 'role': entry['role'],
                                'title': entry['title'], 'file_name': entry['file_name'], 'ref': entry.get('ref')})
            continue
        if ni.sha256(entry['path']) != entry['sha256']:
            raise ValueError('source bytes changed; refresh index first: ' + key)
        record = entry.get('ai_sort')
        done = bool(record and record['file_sha256'] == entry['sha256'] and (not ignore_body or record['ignore_body'])
                    and (entry['role'] != BROLL or descriptive(record)))
        (skipped if done else pending).append(key)
    return {'to_sort': pending, 'skipped': skipped, 'to_download': to_download,
            'download_batch': to_download[:max(0, batch)],
            'coverage': {'reviewed': len(skipped), 'downloaded_needs_review': len(pending), 'not_downloaded': len(to_download)},
            'notion_writeback': False, 'write_performed': False,
            'instruction': 'to_download files are still in Notion. Download only download_batch through the Notion '
                           'connection, library attach each one, then sort frames, look at every frame, sort apply, '
                           'sort writeback. Go on batch by batch for as much as he asked to have tagged, and say how '
                           'many are left. Never label a file you did not view.'}


def frames(index, directory, ignore_body=False):
    root = Path(directory).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    result = []
    for key in plan(index, ignore_body)['to_sort']:
        entry = index['entries'][key]
        folder = root / (entry['page_id'] + '-' + entry['sha256'][:16])
        folder.mkdir(exist_ok=True)
        source = Path(entry['path'])
        video = source.suffix.lower() in {'.mp4', '.mov', '.webm', '.mkv', '.m4v', '.avi'}
        duration = entry['media'].get('duration')
        if video and (not duration or duration <= 0):
            raise ValueError('video duration missing: ' + key)
        times = [duration * x for x in (.1, .5, .9)] if video else [0]
        extracted = []
        for i, time in enumerate(times):
            dest = folder / f'frame-{i}.png'
            input_path = entry['poster'] if source.suffix.lower() in {'.html', '.svg'} else str(source)
            command = ['ffmpeg', '-y', '-v', 'error']
            if video:
                command += ['-ss', str(time)]
            command += ['-i', input_path, '-frames:v', '1', '-vf', 'scale=640:640:force_original_aspect_ratio=decrease,setsar=1', str(dest)]
            subprocess.run(command, check=True, timeout=60)
            extracted.append({'path': str(dest), 'sha256': ni.sha256(dest), 'time': time})
        entry['sort_frames'] = extracted
        result.append({'entry_key': key, 'file_sha256': entry['sha256'], 'title': entry['title'], 'file_name': entry['file_name'],
                       'body': '' if ignore_body else entry.get('body', ''), 'ignore_body': ignore_body, 'frames': extracted})
    return result


def apply(index, records):
    if not isinstance(records, list):
        raise ValueError('input must be an array of records')
    work = copy.deepcopy(index)
    seen = set()
    schema = json.loads(SCHEMA.read_text())
    for record in records:
        validate(record, schema)
        key = record['entry_key']
        if key in seen:
            raise ValueError('duplicate entry record: ' + key)
        seen.add(key)
        entry = work['entries'].get(key)
        if not entry or entry['stale']:
            raise ValueError('unknown or stale entry: ' + key)
        if not entry.get('path') or not entry.get('sha256'):
            raise ValueError('not downloaded, so it cannot have been viewed: ' + key)
        if record['file_sha256'] != entry['sha256'] or ni.sha256(entry['path']) != entry['sha256']:
            raise ValueError('source SHA mismatch: ' + key)
        extracted = entry.get('sort_frames', [])
        if not extracted or record['frame_hashes'] != [ni.sha256(f['path']) for f in extracted] or record['frame_hashes'] != [f['sha256'] for f in extracted]:
            raise ValueError('frame hashes do not match extracted files: ' + key)
        if record['ignore_body'] and any(e['source'] == 'body' for e in record['origin']['evidence']):
            raise ValueError('body evidence forbidden for --ignore-body annotation')
        check_record(record, entry, kit_added(work, entry['page_id']))
        entry['ai_sort'] = copy.deepcopy(record)
    index.clear()
    index.update(work)
    return {'applied': sorted(seen), 'write_performed': False, 'notion_writeback': False}


def writeback(index, phrase=None, page_id=None):
    """Without a fresh Notion snapshot there is nothing to plan. No phrase stands in for one."""
    return {'patches': [], 'notion_writeback': False, 'write_performed': False,
            'instruction': 'No snapshot, so no Notion change is planned. To put reviewed B-roll titles and tags on '
                           'his Content page, fetch the B Roll database and its pages now and run '
                           'library sort writeback --input snapshot.json (docs/NOTION-MCP.md). '
                           'A phrase alone never writes anything.'}


def _stamp(value, what):
    try:
        stamp = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except ValueError as exc:
        raise ValueError(what + ' must be an ISO timestamp with timezone') from exc
    if stamp.tzinfo is None:
        raise ValueError(what + ' must be an ISO timestamp with timezone')
    return stamp


def _review_problems(entry, current=None, generated=frozenset()):
    """Why this file's labels may not go to Notion. Empty when the visual review still checks out.

    current: the entry with body and tags as the fresh snapshot shows them, so evidence is judged
    against the page as it is now and not against what the index remembered.
    """
    if not entry.get('path') or not entry.get('sha256'):
        return ['not_downloaded_so_not_reviewed']
    record = entry.get('ai_sort')
    if not record:
        return ['not_reviewed']
    try:
        # First of all: the stored record must still be a valid record. Nothing below reads a field before this passes.
        validate(record, json.loads(SCHEMA.read_text()))
        if not descriptive(record):
            return ['needs_descriptive_review']       # a valid older record, made before B-roll reviews carried these fields
        check_record(copy.deepcopy(record), current or entry, generated)
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        return ['review_no_longer_valid (' + str(exc) + ')']
    problems = []
    if record['file_sha256'] != entry['sha256']:
        problems.append('review_is_for_other_bytes')
    if not Path(entry['path']).is_file() or ni.sha256(entry['path']) != entry['sha256']:
        problems.append('local_file_missing_or_changed')
    extracted = entry.get('sort_frames') or []
    if not extracted or [f['sha256'] for f in extracted] != record['frame_hashes']:
        problems.append('frames_do_not_match_review')
    elif not all(Path(f['path']).is_file() for f in extracted):
        problems.append('frames_missing')
    elif any(ni.sha256(f['path']) != f['sha256'] for f in extracted):
        problems.append('frames_changed')
    if record['confidence'] < MIN_CONFIDENCE:
        problems.append('low_confidence')
    return problems


def _same_time(left, right):
    if not left or not right:
        return False
    try:
        return _stamp(left, 'time') == _stamp(right, 'time')
    except ValueError:
        return str(left) == str(right)


def writeback_plan(index, layout, snapshot, page_ids=None, now=None):
    """Plan title and tag changes for B Roll pages of the authorized Content hub. Does not call Notion.

    snapshot (what Codex fetched just now through the Notion connection):
      {workspace_id, hub_id, fetched_at, complete,
       database: {database_id, data_source_id, parent_id, schema: {name: {type, options}}},
       pages: [{id, parent_database_id | parent_data_source_id, title, last_edited_time (required),
                properties: {<Tags>: [...] | "text", "Original title": "..."}, files: [{name, ref}],
                body (the page text as fetched now; required when a review cites source-metadata for ethnicity)}]}
    Anything this cannot confirm is refused (the whole plan) or blocked (that page). It only adds:
    existing tags stay, files and the page body are untouched, and the first title is kept in
    Original title.
    """
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get('database'), dict) or not isinstance(snapshot.get('pages'), list):
        raise ValueError('snapshot needs workspace_id, hub_id, fetched_at, database and pages')
    if not snapshot.get('workspace_id') or not snapshot.get('hub_id'):
        raise ValueError('snapshot does not say which workspace and hub it was fetched from')
    try:
        ws, hub = ni._require_hub(layout, snapshot['workspace_id'], snapshot['hub_id'])
    except ValueError as exc:
        raise ValueError(str(exc).replace('refusing upload', 'refusing writeback').replace('before uploading', 'first')) from exc
    role = (layout.get('roles') or {}).get(BROLL) or {}
    if not role.get('database_id') or not role.get('title_property'):
        raise ValueError('the B Roll database is not mapped on the authorized hub')
    db = snapshot['database']
    if not ni.same_hub_id(db.get('database_id'), role['database_id']):
        raise ValueError('refusing writeback: snapshot database is not the mapped B Roll database')
    if role.get('data_source_id') and db.get('data_source_id') and not ni.same_hub_id(db['data_source_id'], role['data_source_id']):
        raise ValueError('refusing writeback: snapshot data source is not the mapped B Roll data source')
    if not ni.same_hub_id(db.get('parent_id'), hub):
        raise ValueError('refusing writeback: the B Roll database is not directly on the authorized Content page')
    now = now or datetime.now(timezone.utc)
    fetched = _stamp(snapshot.get('fetched_at'), 'snapshot fetched_at')
    if fetched > now + timedelta(minutes=2) or now - fetched > timedelta(minutes=SNAPSHOT_MAX_AGE_MINUTES):
        raise ValueError(f'snapshot is not fresh (older than {SNAPSHOT_MAX_AGE_MINUTES} minutes, or dated in the future); fetch again')
    schema = db.get('schema')
    title_prop = role['title_property']
    if not isinstance(schema, dict) or (schema.get(title_prop) or {}).get('type') != 'title':
        raise ValueError('invalid schema: the mapped title field is not the title of this database; run library detect again')
    base = {'command': 'broll_title_tag_writeback_plan', 'scope': 'authorized_hub', 'role': BROLL,
            'workspace_id': ws, 'hub_id': hub, 'database_id': role['database_id'],
            'data_source_id': role.get('data_source_id') or db.get('data_source_id'),
            'snapshot_fetched_at': snapshot['fetched_at'],
            'valid_until': (fetched + timedelta(minutes=SNAPSHOT_MAX_AGE_MINUTES)).isoformat(),
            'write_performed': False, 'title_format': TITLE_FORMAT, 'patches': []}

    def named(name):
        found = [k for k in schema if k.casefold() == name.casefold()]
        if len(found) > 1:
            raise ValueError('invalid schema: more than one field named ' + name)
        return found[0] if found else None
    tags_prop, original_prop = named(role.get('tags_property') or 'Tags'), named(ORIGINAL_TITLE)
    wrong = []
    if tags_prop and schema[tags_prop].get('type') not in TAG_TYPES:
        wrong.append(f"{tags_prop} is {schema[tags_prop].get('type')}; tags need multi_select or text")
    if original_prop and schema[original_prop].get('type') != 'rich_text':
        wrong.append(f"{original_prop} is {schema[original_prop].get('type')}; it must be text")
    if wrong:
        return dict(base, status='schema_conflict', notion_writeback=False, conflicts=wrong,
                    instruction='Nothing is written. The kit never changes a field type and never writes tags into '
                                'another field. Tell him which field is in the way and let him decide.')
    missing = {name: {'type': kind} for name, kind, have in
               [('Tags', 'multi_select', tags_prop), (ORIGINAL_TITLE, 'rich_text', original_prop)] if not have}
    if missing:
        return dict(base, status='setup_required', notion_writeback=False, approval='needs_his_ok',
                    setup={'action': 'add_properties', 'database_id': base['database_id'],
                           'data_source_id': base['data_source_id'], 'properties': missing},
                    summary=['add to B Roll: ' + ', '.join(missing)],
                    instruction='No page is changed yet. Show him the summary and wait for his OK. Then add only '
                                'these fields to this one database, fetch a new snapshot and run this command again. '
                                'Never rename, delete or retype a field.')
    tags_type = schema[tags_prop]['type']
    options = None
    if tags_type == 'multi_select':
        raw = schema[tags_prop].get('options')
        if not isinstance(raw, list):
            raise ValueError('invalid schema: the snapshot must list the Tags options')
        options = {str(o.get('name') if isinstance(o, dict) else o).casefold(): str(o.get('name') if isinstance(o, dict) else o) for o in raw}

    pages = {}
    for page in snapshot['pages']:
        pid = ni.row_id(page) if isinstance(page, dict) else ''
        if not pid or pid in pages:
            raise ValueError('snapshot has a missing or duplicate page id')
        pages[pid] = page
    wanted = [ni.row_id({'id': p}) for p in page_ids] if page_ids else list(pages)
    absent = [p for p in wanted if p not in pages]
    if absent:
        raise ValueError('ambiguous target: page not in the snapshot: ' + ', '.join(absent))

    proposals = copy.deepcopy(index.get('writeback_proposals', {}))
    patches, blocked, unchanged, skipped, titles = [], [], [], [], {}
    new_options = []
    for pid in wanted:
        page, reasons, notes = pages[pid], [], []
        parent = page.get('parent_database_id') or page.get('parent_data_source_id')
        if not parent:
            reasons.append('membership_unconfirmed')
        elif not (ni.same_hub_id(parent, db.get('database_id')) or ni.same_hub_id(parent, db.get('data_source_id'))):
            reasons.append('not_in_broll_database')
        row = index['rows'].get(pid)
        entries = [e for e in index['entries'].values() if e['page_id'] == pid and not e['stale']]
        if not row or row.get('stale') or not entries:
            reasons.append('not_in_index_refresh_first')
        elif row['signature']['role'] != BROLL or any(e['role'] != BROLL for e in entries):
            reasons.append('not_a_broll_row')
        else:
            listed = page.get('files')
            ident = lambda files: sorted((str(f.get('name')), str(f.get('ref'))) for f in files)
            if not isinstance(listed, list) or ident(listed) != ident(row['signature']['files']):
                reasons.append('files_differ_from_index_refresh_first')
            if len(entries) != len(row['signature']['files']):
                reasons.append('files_differ_from_index_refresh_first')
        props = page.get('properties') if isinstance(page.get('properties'), dict) else {}
        current_tags = props.get(tags_prop)
        if tags_type == 'multi_select' and not (isinstance(current_tags, list) and all(isinstance(t, str) for t in current_tags)):
            reasons.append('current_tags_unreadable')
        if tags_type == 'rich_text' and not isinstance(current_tags, str):
            reasons.append('current_tags_unreadable')
        if not isinstance(props.get(original_prop), str):
            reasons.append('original_title_unreadable')
        current_title = ni.plain_title(page.get('title'))
        if not current_title:
            reasons.append('current_title_unreadable')
        override = index['overrides'].get(pid, {})
        if override.get('exclude'):
            skipped.append({'page_id': pid, 'reason': 'excluded_by_override'})
            continue
        if not reasons:
            # The index must describe the page as it is now. An edit since the last refresh (a changed body,
            # tags or title) means labels and evidence were judged against something else.
            if not page.get('last_edited_time'):
                reasons.append('edit_time_missing_from_snapshot')
            elif not all(_same_time(page['last_edited_time'], e.get('last_edited_time')) for e in entries):
                reasons.append('page_edited_since_index_refresh_first')
        if not reasons:
            generated = kit_added(index, pid)
            tags_now = current_tags if tags_type == 'multi_select' else [t for t in (clean_tag(x) for x in current_tags.split(',')) if t]
            for e in entries:
                record = e.get('ai_sort')
                ethnicity = record.get('ethnicity') if isinstance(record, dict) else None
                evidence = ethnicity.get('evidence') if isinstance(ethnicity, dict) else None
                cites_source = isinstance(evidence, dict) and evidence.get('source') == 'source-metadata'
                if cites_source and not record.get('ignore_body') and not isinstance(page.get('body'), str):
                    reasons.append(f"{e['file_name']}: snapshot_needs_page_body_for_source_evidence")
                    continue
                # Evidence is read from the snapshot: its tags always, its body when it carries one.
                current = dict(e, explicit_tags=tags_now, body=page['body'] if isinstance(page.get('body'), str) else e.get('body', ''))
                reasons += [f"{e['file_name']}: {p}" for p in _review_problems(e, current, generated)]
        if reasons:
            blocked.append({'page_id': pid, 'title': current_title, 'reasons': sorted(set(reasons))})
            continue

        records = [e['ai_sort'] for e in sorted(entries, key=lambda e: e['file_name'])]
        made = [kit_title(r) for r in records]
        agree = len(set(made)) == 1
        tag_sets = [kit_tags(r) for r in records]
        if agree:
            tags = list(dict.fromkeys(t for group in tag_sets for t in group))
        else:
            # Several files that show different things: only what every file shares may describe the page.
            tags = [t for t in tag_sets[0] if all(t in group for group in tag_sets[1:])]
            notes.append('multi_file_conflict: files on this page show different things (' + ' | '.join(str(t) for t in made)
                         + '). Title left alone; only tags true of every file are added. Split the row or set a title override.')
        if any(r.get('ethnicity') for r in records):
            notes.append('ethnicity tag comes from recorded evidence (' + ', '.join(sorted({r['ethnicity']['evidence']['source'] for r in records if r.get('ethnicity')})) + '), never from appearance')
        removed = {t.casefold() for t in override.get('tags_remove', [])}
        tags = [t for t in list(dict.fromkeys(tags + [clean_tag(t) for t in override.get('tags_add', [])])) if t and t.casefold() not in removed][:MAX_TAGS]

        manual = ni.plain_title(override.get('title'))
        proposed = manual or (made[0] if agree else None)
        if agree and not manual and proposed is None:
            notes.append('not enough reviewed detail for a title; title left alone')
        change = {}
        original = props[original_prop].strip()
        last = (proposals.get(pid) or {}).get('title')
        if proposed and proposed != current_title:
            if manual or not original or current_title == last:
                change[title_prop] = proposed
                if not original:
                    change[original_prop] = current_title      # the first title is kept once, never replaced
            else:
                notes.append('title_edited_in_notion: the title was changed by hand after the kit set it; left alone. '
                             'Set a title override to change it.')
        final_title = change.get(title_prop, current_title)

        # Which tags on the page are the kit's own? Only ones an earlier plan proposed AND a later snapshot showed
        # in place. A plan is not a receipt. Everything else on the page is his and is never removed.
        multi = tags_type == 'multi_select'
        on_page = current_tags if multi else [t for t in (clean_tag(x) for x in current_tags.split(',')) if t]
        have = {t.casefold() for t in on_page}
        prev = proposals.get(pid) or {}
        owned = {t.casefold() for t in prev.get('owned', [])}
        pending = [t.casefold() for t in prev.get('pending_adds', [])]
        if pending and all(t in have for t in pending):
            owned |= set(pending)
        gone = owned - have
        declined = (set(prev.get('declined', [])) | (gone - {t.casefold() for t in prev.get('pending_removes', [])})) \
            - {clean_tag(t).casefold() for t in override.get('tags_add', [])}
        owned &= have
        if any(t.casefold() in declined for t in tags):
            notes.append('removed_in_notion: he took these kit tags off the page, so they stay off: '
                         + ', '.join(t for t in tags if t.casefold() in declined) + '. A tags_add override puts one back.')
        tags = [t for t in tags if t.casefold() not in declined]
        wanted_tags = {t.casefold() for t in tags}
        remove = [t for t in on_page if t.casefold() in owned and t.casefold() not in wanted_tags]
        # Labels the kit generated in an earlier review and no longer does. Remembered until the page stops carrying them.
        superseded = ({x.casefold() for x in prev.get('tags', [])} | set(prev.get('superseded', []))) - wanted_tags
        leftover = [t for t in on_page if t.casefold() in superseded and t.casefold() not in owned]
        add = [(options.get(t.casefold(), t) if multi else t) for t in tags if t.casefold() not in have]
        if remove:
            notes.append('replaced_by_new_review: removes tags the kit itself added (confirmed by an earlier snapshot) that the '
                         'current review no longer supports: ' + ', '.join(remove))
        if leftover:
            notes.append('needs_his_correction: these tags no longer match the review but cannot be shown to be kit-added '
                         '(they were his, or the earlier write was never confirmed), so they are left: ' + ', '.join(leftover)
                         + '. Tell him; do not call this page fully corrected.')
        if add or remove:
            kept = [t for t in on_page if t not in remove]
            if multi:
                change[tags_prop] = kept + add
                new_options += [t for t in add if t.casefold() not in options and t not in new_options]
            elif remove:
                change[tags_prop] = ', '.join(kept + add)
            else:
                change[tags_prop] = ', '.join(([current_tags.strip().rstrip(',')] if current_tags.strip() else []) + add)
        titles.setdefault(final_title, []).append(pid)
        proposals[pid] = {'title': proposed if proposed and final_title == proposed else last, 'tags': tags,
                          'pending_adds': add, 'pending_removes': remove, 'owned': sorted(owned), 'declined': sorted(declined),
                          'superseded': sorted(superseded & have),
                          'snapshot_fetched_at': snapshot['fetched_at'], 'status': 'proposed' if change else 'matches_snapshot'}
        if not change:
            unchanged.append({'page_id': pid, 'title': current_title, **({'notes': notes} if notes else {})})
            continue
        patches.append({'page_id': pid,
                        'expected': {'title': current_title, tags_prop: current_tags, original_prop: props[original_prop],
                                     'last_edited_time': page.get('last_edited_time'),
                                     'files': [{'name': f.get('name'), 'ref': f.get('ref')} for f in page['files']]},
                        'set': change, 'adds_tags': add, 'removes_tags': remove, 'keeps_tags': [t for t in on_page if t not in remove],
                        'file_sha256': [e['sha256'] for e in sorted(entries, key=lambda e: e['file_name'])],
                        **({'notes': notes} if notes else {})})

    in_index = {pid for pid, r in index['rows'].items() if r['signature']['role'] == BROLL and not r.get('stale')}
    index['writeback_proposals'] = proposals
    return dict(base, status='proposed' if patches else 'nothing_to_do', notion_writeback=bool(patches),
                patches=patches, unchanged=unchanged, blocked=blocked, skipped=skipped,
                tags_property=tags_prop, tags_type=tags_type, original_title_property=original_prop,
                options_to_create=new_options, approval='covered_by_his_request_to_tag_or_add_broll',
                needs_his_correction=[{'page_id': x['page_id'], 'notes': [n for n in x.get('notes', []) if n.startswith('needs_his_correction')]}
                                      for x in patches + unchanged if any(n.startswith('needs_his_correction') for n in x.get('notes', []))],
                duplicate_titles={t: p for t, p in titles.items() if len(p) > 1},
                coverage={'snapshot_complete': bool(snapshot.get('complete')), 'pages_in_snapshot': len(pages),
                          'broll_pages_in_index': len(in_index), 'indexed_pages_not_in_snapshot': sorted(in_index - set(pages)),
                          'to_change': len(patches), 'already_match': len(unchanged), 'blocked': len(blocked)},
                summary=[f"{len(patches)} B Roll page(s) to update, {len(unchanged)} already match, {len(blocked)} blocked, {len(skipped)} skipped"]
                        + ([f"new Tags options: {', '.join(new_options)}"] if new_options else []),
                instruction='PROPOSED ONLY: nothing has been written and this plan never proves a write happened. '
                            'His request to sort, tag or add B-roll is the go-ahead for these patches; do not ask again, '
                            'just tell him what changed. (A request that was only "refresh" is not: report what is '
                            'pending instead.) Before valid_until, for each patch: fetch that page, confirm it is still '
                            'in this database under this hub and still shows every value in expected (title, tags, '
                            'original title, files, last_edited_time); if anything differs, skip it and take a new snapshot. Set only the '
                            'properties in set. The Tags value in set is complete: it keeps every tag that is his and '
                            'leaves out only removes_tags, which the kit added itself earlier. If options_to_create is '
                            'not empty, add exactly those options to the Tags field. An ALTER options list must include '
                            'all existing options plus the additions: fetch the latest schema first and preserve every '
                            'existing name and color (never rename, recolor or delete an option). Do not touch files, '
                            'the page body, Origin, status, QA, comments, other pages, '
                            'other databases or other hubs. Afterwards refresh the index (the write changed the page), '
                            'fetch a new snapshot and re-run this command. Only a page '
                            'that then shows up under unchanged may be reported as titled and tagged; pages under '
                            'blocked or needs_his_correction are not finished.')


def run(args, index_path, layout_path=None):
    index = ni.read_json(index_path, ni.empty_index())
    action = args.args[0] if args.args else 'plan'
    if len(args.args) > 1:
        raise ValueError('sort accepts one action: plan, frames, apply or writeback')
    if action == 'plan':
        return plan(index, args.ignore_body, getattr(args, 'batch', 10))
    if action == 'frames':
        if not args.frames_dir:
            raise ValueError('--frames-dir required')
        result = frames(index, args.frames_dir, args.ignore_body)
    elif action == 'apply':
        if not args.input:
            raise ValueError('--input required')
        result = apply(index, ni.read_json(args.input))
    elif action == 'writeback':
        if not args.input:
            return writeback(index, args.phrase, args.page_id)
        if not layout_path or not Path(layout_path).expanduser().is_file():
            raise ValueError('layout config missing; configure the authorized Content hub first')
        snapshot = ni.read_json(args.input)
        if snapshot is None:
            raise ValueError('snapshot file does not exist')
        pages = [p.strip() for p in (args.page_id or '').split(',') if p.strip()] or None
        result = writeback_plan(index, ni.read_json(layout_path), snapshot, pages)
    else:
        raise ValueError('unknown sort action: ' + action)
    ni.save_json(index_path, index)
    return result
