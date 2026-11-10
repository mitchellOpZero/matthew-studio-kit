"""Offline Notion MCP import, asset search, local QA records, and scoped upload plans.

No network and no credentials. Codex talks to Notion through the connection already
signed in. This module never calls Notion. Only the one-time setup plan names tables or
fields to add (on his Content page, after his OK); nothing here deletes or renames them.
QA status stays on this Mac. Reviewed B-roll titles and tags reach Notion only through
the plan in notion_sort.writeback_plan. Every plan is valid only for the workspace id and
hub id saved from the Content page authorized in this session.
"""
import copy
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

STOP = set('a an the of in on at to for and or with from by is are this that it as was were be made via test clip file png mp4 jpg jpeg svg html webm com https www'.split())
SYNONYMS = [set('bar club nightlife'.split()), set('cafe coffee café'.split()), set('city skyline downtown'.split()), set('profile dating hinge'.split()), set('chat message conversation'.split()),
            # Everyday search words for the fixed labels. A convenience for lookup only: nothing about age or identity is read into a clip.
            set('woman women girl girls lady female'.split()), set('man men guy guys male'.split()),
            set('brown brunette'.split()), set('blonde blond'.split()), set('red redhead ginger'.split()), set('gray grey'.split())]
AI_WORDS = set('ai veo runway sora wan generated'.split())


def tokens(text):
    return set(re.findall(r'[^\W_]+', text.lower(), re.UNICODE)) - STOP


def expand(words):
    result = set(words)
    for group in SYNONYMS:
        if result & group:
            result |= group
    return result


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def read_json(path, default=None):
    if str(path) == '-':
        return json.load(sys.stdin)
    p = Path(path).expanduser()
    return json.loads(p.read_text()) if p.exists() else copy.deepcopy(default)


def save_json(path, data):
    p = Path(path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    temp = p.with_name(p.name + '.tmp')
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')
    temp.replace(p)


def plain_title(value):
    """Turn an MCP rich-text title into the plain title a page fetch would show.

    Handles markdown escapes (IMG\\_1234) and a link wrapped around part of a name
    (an autolinked .mp substring). Does not follow or store the link target.
    """
    if not isinstance(value, str):
        return ''
    text = (value.replace('\\_', '_').replace('\\*', '*').replace('\\`', '`')
            .replace('\\[', '[').replace('\\]', ']'))
    text = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', text)
    return ' '.join(text.split())


def same_hub_id(left, right):
    """True when both ids are the same, including a UUID written with or without dashes."""
    if left is None or right is None:
        return False
    if str(left) == str(right):
        return True
    def hexed(value):
        cleaned = re.sub(r'[^0-9a-f]', '', str(value).lower())
        return cleaned if len(cleaned) == 32 else None
    a, b = hexed(left), hexed(right)
    return bool(a and a == b)


def unwrap(value):
    """Accept raw MCP call result or its JSON text object."""
    if isinstance(value, str):
        try:
            return unwrap(json.loads(value))
        except json.JSONDecodeError:
            return {'text': value}
    if 'content' in value and isinstance(value['content'], list):
        return unwrap(value['content'][0]['text'])
    return value


def detect_role(source, role_name=None):
    fetched = unwrap(source.get('fetch', source))
    text = fetched.get('text', fetched.get('result', ''))
    schema = source.get('schema')
    if schema is None:
        match = re.search(r'<data-source-state>\s*(.*?)\s*</data-source-state>', text, re.S)
        if not match:
            raise ValueError('fetch must include a data-source-state schema')
        state = json.loads(match[1])
        schema = state['schema']
    def prop(types, preferred=(), required=False):
        found = [k for k, v in schema.items() if v.get('type') in types]
        preferred_found = [k for k in found if k.casefold() in preferred]
        if len(preferred_found) == 1:
            return preferred_found[0]
        if len(found) == 1:
            return found[0]
        if required:
            raise ValueError(f'expected one unambiguous property of type {types}; got {found}')
        return None
    db = source.get('database_id') or (re.search(r'https://app.notion.com/p/([a-f0-9-]+)', text) or [None, None])[1]
    ds = source.get('data_source_id') or (re.search(r'collection://([a-f0-9-]+)', text) or [None, None])[1]
    role = {'database_id': db, 'data_source_id': ds, 'title_property': prop({'title'}, required=True),
            'files_property': prop({'file', 'files'}, ('files & media', 'file'), required=role_name not in {'posts', 'videos'})}
    for key, names in [('tags', ['tags']), ('origin', ['origin']), ('duration', ['duration', 'duration (s)'])]:
        role[key + '_property'] = next((k for k in schema if k.casefold() in names), None)
    if role_name in {'posts', 'videos'}:
        role['input_property'] = role['files_property'] or next((k for k in schema if k.casefold() == 'raw footage'), None)
    for key in ['view_url', 'kind']:
        if key in source:
            role[key] = source[key]
    return role


def detect(payload):
    workflow = payload.get('workflow', 'posts')
    if workflow not in {'posts', 'videos'}:
        raise ValueError('workflow must be posts or videos')
    workspace_id, hub_id = payload.get('workspace_id'), payload.get('hub_id')
    # notion_writeback stays false: no flag licenses a write, and QA status is never pushed.
    # Uploads and the B-roll title/tag plan each need the hub this session recorded (asset_upload).
    return {'version': 1, 'notion_writeback': False,
            'asset_upload': 'authorized_hub' if workspace_id and hub_id else 'off',
            'workflow': workflow, 'workflow_settings': payload.get('workflow_settings', {}),
            'workspace_id': workspace_id, 'hub_id': hub_id,
            'roles': {role: detect_role(source, role) for role, source in payload['roles'].items()}}


def empty_index():
    return {'version': 1, 'entries': {}, 'rows': {}, 'overrides': {}}


def row_id(row):
    value = row.get('id', row.get('url', ''))
    match = re.search(r'([0-9a-f]{32}|[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})', value)
    return match[0].replace('-', '') if match else value


def signature(row):
    """Stable file refs only: never put expiring signed URLs in the inventory."""
    return {'role': row['role'], 'title': plain_title(row.get('title', '')),
            'last_edited_time': row.get('last_edited_time'),
            'files': [{k: f.get(k) for k in ('name', 'ref', 'sha256') if f.get(k) is not None} for f in row.get('files', [])]}


def matches_inventory(existing, listed):
    """Saved views may omit timestamps and SHA; compare only available fields."""
    comparable = copy.deepcopy(existing)
    if listed.get('last_edited_time') is None:
        comparable['last_edited_time'] = None
    for old_file, new_file in zip(comparable.get('files', []), listed.get('files', [])):
        if 'sha256' not in new_file:
            old_file.pop('sha256', None)
    return comparable == listed


def plan(index, inventory, force=False):
    fetch, unchanged = [], []
    seen = set()
    for row in inventory['rows']:
        pid = row_id(row)
        if not pid or pid in seen:
            raise ValueError('inventory has missing or duplicate page ID')
        seen.add(pid)
        old = index['rows'].get(pid)
        changed = force or old is None or old.get('stale') or not matches_inventory(old['signature'], signature(row))
        for e in index['entries'].values():
            if e['page_id'] == pid and not e['stale'] and e.get('path'):   # listed-only files have no local copy to check
                path = Path(e['path'])
                changed |= not path.is_file() or sha256(path) != e['sha256']
        (fetch if changed else unchanged).append(pid)
    complete = set(inventory.get('complete_roles', []))
    stale = [pid for pid, r in index['rows'].items() if r['signature']['role'] in complete and pid not in seen and not r.get('stale')]
    return {'fetch': fetch, 'unchanged': unchanged, 'stale': stale,
            'timestamp_limit': 'When view exports omit last_edited_time, title/file-ref changes are detected; use --force for body-only edits or external bytes changed at the same URL.'}


def media_info(path):
    path = Path(path)
    if path.suffix.lower() in {'.svg', '.html'}:
        return {'duration': None, 'width': None, 'height': None, 'aspect': None}
    data = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)], timeout=30))
    video = next((s for s in data['streams'] if s['codec_type'] == 'video'), {})
    w, h = video.get('width'), video.get('height')
    sar = video.get('sample_aspect_ratio', '1:1')
    try:
        a, b = map(float, sar.split(':'))
        ratio = (w * a / b) / h if w and h and b else None
    except (ValueError, ZeroDivisionError):
        ratio = w / h if w and h else None
    return {'duration': float(data['format']['duration']) if 'duration' in data['format'] else None,
            'width': w, 'height': h, 'sample_aspect_ratio': sar,
            'aspect': ('square' if abs(ratio - 1) < .03 else 'vertical' if ratio < 1 else 'horizontal') if ratio else None}


def make_local_poster(path, output):
    from poster import make_poster
    return str(make_poster(path, output))


def infer_origin(title, body, names):
    return 'ai' if tokens(' '.join([title, body, *names])) & AI_WORDS else 'stock'


def effective(entry, index):
    result = copy.deepcopy(entry)
    override = index['overrides'].get(entry['page_id'], {})
    result['tags'] = sorted((set(entry['tags']) | set(override.get('tags_add', []))) - set(override.get('tags_remove', [])))
    result['origin'] = override.get('origin', entry.get('ai_sort', {}).get('origin', {}).get('value', entry['origin']))
    result['exclude'] = override.get('exclude', False)
    return result


def set_override(index, pid, patch):
    if set(patch) - {'tags_add', 'tags_remove', 'origin', 'exclude', 'title'}:
        raise ValueError('unknown override field')
    if 'title' in patch and (not isinstance(patch['title'], str) or not plain_title(patch['title'])):
        raise ValueError('override title must be text')
    if 'origin' in patch and patch['origin'] not in {'ai', 'stock', 'own', 'unknown'}:
        raise ValueError('origin must be ai, stock, own or unknown')
    for key in ['tags_add', 'tags_remove']:
        if key in patch and (not isinstance(patch[key], list) or not all(isinstance(x, str) for x in patch[key])):
            raise ValueError('override tags must be a list of strings')
    if 'exclude' in patch and not isinstance(patch['exclude'], bool):
        raise ValueError('exclude must be boolean')
    index['overrides'].setdefault(row_id({'id': pid}), {}).update(patch)


def refresh(index, layout, inventory, rows, root, force=False):
    work = copy.deepcopy(index)
    p = plan(work, inventory, force)
    supplied = {row_id(r): r for r in rows}
    if set(p['fetch']) - supplied.keys():
        raise ValueError('missing changed page exports: ' + ', '.join(sorted(set(p['fetch']) - supplied.keys())))
    inventory_by_id = {row_id(r): r for r in inventory['rows']}
    root = Path(root)
    for pid in p['fetch']:
        row = supplied[pid]
        if row['role'] not in layout['roles']:
            raise ValueError('role not configured: ' + row['role'])
        supplied_sig, listed_sig = signature(row), signature(inventory_by_id[pid])
        if not matches_inventory(supplied_sig, listed_sig):
            raise ValueError('page export differs from inventory; rescan before indexing')
        active = []
        names = [x['name'] for x in row.get('files', [])]
        body, title = row.get('body', ''), plain_title(row.get('title', ''))
        explicit_tags = row.get('tags', [])
        kind = row.get('kind') or layout['roles'][row['role']].get('kind') or {'broll': 'broll', 'graphics': 'graphic', 'pictures': 'picture', 'styles': 'style'}.get(row['role'], 'graphic')
        for f in row.get('files', []):
            if not f.get('path'):
                # Listed only: the file stays in Notion until an edit uses it (library attach downloads it in).
                origin = row.get('origin', '').lower()
                # Same attachment already downloaded for an edit or a review: keep the local copy and its review.
                kept = next((k for k, e in work['entries'].items() if e['page_id'] == pid and not e['stale'] and e.get('downloaded')
                             and f.get('ref') and e.get('ref') == f['ref'] and e['file_name'] == f['name']
                             and e.get('path') and Path(e['path']).is_file() and k not in active), None)
                if kept:
                    work['entries'][kept].update({'title': title, 'file_names': names, 'body': body, 'kind': kind,
                        'last_edited_time': row.get('last_edited_time'), 'explicit_tags': explicit_tags,
                        'tags': sorted(expand(tokens(' '.join([title, *names, body, *explicit_tags])))),
                        'origin': origin if origin in {'ai', 'stock'} else infer_origin(title, body, names)})
                    active.append(kept)
                    continue
                key = pid + ':ref:' + hashlib.sha256(str(f.get('ref') or f['name']).encode()).hexdigest()[:16]
                prev = work['entries'].get(key) or {}
                work['entries'][key] = {'page_id': pid, 'sha256': None, 'role': row['role'], 'kind': kind,
                    'title': title, 'file_name': f['name'], 'file_names': names, 'body': body,
                    'last_edited_time': row.get('last_edited_time'), 'ref': f.get('ref'), 'path': None, 'downloaded': False,
                    'tags': sorted(expand(tokens(' '.join([title, *names, body, *explicit_tags])))),
                    'origin': origin if origin in {'ai', 'stock'} else infer_origin(title, body, names),
                    'origin_basis': 'explicit metadata or lexical inference; not licence verification',
                    'media': {}, 'poster': None, 'stale': False, 'explicit_tags': explicit_tags}
                for field in ('ai_sort', 'sort_frames'):
                    if field in prev:
                        work['entries'][key][field] = copy.deepcopy(prev[field])
                active.append(key)
                continue
            path = Path(f['path']).expanduser().resolve(strict=True)
            digest = sha256(path)
            if f.get('sha256') and f['sha256'] != digest:
                raise ValueError('download hash mismatch: ' + f['name'])
            key = pid + ':' + digest
            prev = work['entries'].get(key)
            metadata = prev['media'] if prev else media_info(path)
            poster = prev.get('poster') if prev else None
            if not poster or not Path(poster).is_file():
                poster = make_local_poster(path, root / 'posters' / (pid + '-' + digest[:16] + '.png'))
            # HTML/SVG dimensions come from the rendered poster; duration remains unknown.
            if not metadata.get('width'):
                metadata = media_info(poster)
            names = [x['name'] for x in row.get('files', [])]
            body, title = row.get('body', ''), plain_title(row.get('title', ''))
            explicit_tags = row.get('tags', [])
            origin = row.get('origin', '').lower()
            origin = origin if origin in {'ai', 'stock'} else infer_origin(title, body, names)
            kind = row.get('kind') or layout['roles'][row['role']].get('kind') or {'broll': 'broll', 'graphics': 'graphic', 'pictures': 'picture', 'styles': 'style'}.get(row['role'], 'graphic')
            work['entries'][key] = {'page_id': pid, 'sha256': digest, 'role': row['role'], 'kind': kind,
                'title': title, 'file_name': f['name'], 'file_names': names, 'body': body,
                'last_edited_time': row.get('last_edited_time'), 'ref': f.get('ref'), 'path': str(path),
                'tags': sorted(expand(tokens(' '.join([title, *names, body, *explicit_tags])))),
                'origin': origin, 'origin_basis': 'explicit metadata or lexical inference; not licence verification',
                'media': metadata, 'poster': poster, 'stale': False, 'explicit_tags': explicit_tags, 'downloaded': True}
            for field in ('ai_sort', 'sort_frames'):
                if prev and field in prev:
                    work['entries'][key][field] = copy.deepcopy(prev[field])
            active.append(key)
        for key, entry in work['entries'].items():
            if entry['page_id'] == pid and key not in active:
                entry['stale'] = True
        work['rows'][pid] = {'signature': signature(inventory_by_id[pid]), 'stale': False}
    for pid in p['stale']:
        work['rows'][pid]['stale'] = True
        for entry in work['entries'].values():
            if entry['page_id'] == pid:
                entry['stale'] = True
    index.clear()
    index.update(work)
    return {'reread': p['fetch'], 'unchanged': p['unchanged'], 'stale': p['stale'],
            'entries': len(index['entries']), 'active': sum(not e['stale'] for e in index['entries'].values()),
            'broll_labels_pending': broll_pending(index)}


def broll_pending(index, limit=20):
    """New or changed B-roll that has no current visual review yet. Cheap: reads the index only, downloads and hashes nothing."""
    pages = []
    for e in index['entries'].values():
        review = e.get('ai_sort') or {}
        done = e.get('sha256') and review.get('file_sha256') == e['sha256'] and 'action' in review
        if e['role'] == 'broll' and not e['stale'] and not done and not index['overrides'].get(e['page_id'], {}).get('exclude') \
                and e['page_id'] not in pages:
            pages.append(e['page_id'])
    return {'count': len(pages), 'pages': pages[:limit],
            'note': 'B-roll without a reviewed title and tags. A refresh downloads nothing: tell him the count. Label them when '
                    'he asked to add, sort or tag B-roll (library sort plan --batch N), a bounded batch at a time.'} if pages else {'count': 0, 'pages': []}


def attach(index, page_id, path, root):
    """Bring in one file an edit is about to use: hash, probe and poster it, then mark it downloaded."""
    path = Path(path).expanduser().resolve(strict=True)
    listed = [(k, e) for k, e in index['entries'].items() if e['page_id'] == page_id and not e['stale']]
    if not listed:
        raise ValueError('no indexed page ' + page_id + '; refresh the library first')
    named = [(k, e) for k, e in listed if e.get('file_name') == path.name]
    if not named and len(listed) > 1:
        raise ValueError('page ' + page_id + ' has several files; save the download under its Notion file name: '
                         + ', '.join(sorted(e['file_name'] for _, e in listed)))
    key, entry = (named or listed)[0]
    digest = sha256(path)
    media = media_info(path)
    poster = make_local_poster(path, Path(root) / 'posters' / (page_id + '-' + digest[:16] + '.png'))
    if not media.get('width'):
        media = media_info(poster)
    new = dict(entry, sha256=digest, path=str(path), media=media, poster=poster, downloaded=True)
    if key != page_id + ':' + digest:
        index['entries'].pop(key)
    index['entries'][page_id + ':' + digest] = new
    return {'attached': page_id, 'path': str(path), 'media': media}


def find(index, query, kind=None, origin=None, aspect=None, limit=10, ignore_body=False):
    q = tokens(query)
    expanded = expand(q)
    hits = []
    for raw in index['entries'].values():
        base = copy.deepcopy(raw)
        if ignore_body:
            base['tags'] = sorted(expand(tokens(' '.join([base['title'], *base['file_names'], *base.get('explicit_tags', [])]))))
            base['origin'] = 'ai' if tokens(' '.join([base['title'], *base['file_names']])) & AI_WORDS else 'unknown'
        e = effective(base, index)
        visual = e.get('ai_sort', {})
        if ignore_body and visual and not visual['ignore_body']:
            visual = {}
            e.pop('ai_sort', None)
            e['origin'] = index['overrides'].get(e['page_id'], {}).get('origin', base['origin'])
        removed = expand(tokens(' '.join(index['overrides'].get(e['page_id'], {}).get('tags_remove', []))))
        ai_fields = {k: ' '.join(v) if isinstance(v, list) else v for k, v in visual.items() if k in {'subject', 'setting', 'mood', 'shot_type', 'time_of_day', 'description', 'action'}}
        if visual:
            import notion_sort
            ai_fields['labels'] = ' '.join(notion_sort.kit_tags(visual))
            e['kit_title'] = index['overrides'].get(e['page_id'], {}).get('title') or notion_sort.kit_title(visual)
        ai_fields['origin'] = e['origin'] if visual else ''
        ai_matches = {k: expanded & (expand(tokens(v)) - removed) for k, v in ai_fields.items()}
        ai_overlap = set().union(*ai_matches.values()) if ai_matches else set()
        if e['stale'] or e['exclude'] or (kind and e['kind'] != kind) or (origin and e['origin'] != origin) or (aspect and (e.get('media') or {}).get('aspect') != aspect):
            continue
        if q and q <= removed:
            continue
        title = tokens(e['title']) - removed
        overlap = expanded & (set(e['tags']) - removed)
        overlap |= ai_overlap
        fuzzy = difflib.SequenceMatcher(None, query.lower(), e['title'].lower()).ratio()
        if q and not overlap and fuzzy < .45:
            continue
        score = 60 * len(overlap) / max(1, len(expanded)) + 25 * len(q & title) / max(1, len(q)) + 15 * fuzzy + 70 * len(ai_overlap) / max(1, len(expanded))
        if e.get('downloaded') is False:
            e['next_step'] = ('not on this Mac yet: download this file through the Notion connection, then '
                              f"bin/kit library attach {e['page_id']} <downloaded file>")
        hits.append({**e, 'score': round(score, 2), 'match_reasons': ['tokens/synonyms: ' + ', '.join(sorted(overlap)), f'title fuzzy ratio: {fuzzy:.3f}'] + [f"{'manual' if k == 'origin' and 'origin' in index['overrides'].get(e['page_id'], {}) else 'ai'}.{k}={ai_fields[k]}" for k, matched in ai_matches.items() if matched]})
    return sorted(hits, key=lambda e: (-e['score'], e['title'], e['file_name']))[:limit]


def transition(config, row, verdict, requested=None, human_posted=False, simulated=False):
    mode = config.get('workflow', 'posts')
    settings = config.get('workflow_settings', {})
    if mode not in {'posts', 'videos'} or not all(settings.get(k) for k in ('status_property', 'edit_statuses', 'review_status')):
        raise ValueError('workflow configuration requires status_property, edit_statuses and review_status')
    prop = settings['status_property']
    current = row.get('properties', {}).get(prop)
    posted = settings.get('posted_status')
    if mode == 'posts' and (not posted or settings['review_status'] == posted):
        raise ValueError('posts review_status must differ from configured posted_status')
    if verdict not in {'PASS', 'FAIL'}:
        raise ValueError('QA verdict must be PASS or FAIL')
    if posted and requested == posted and not human_posted:
        raise ValueError('Posted requires an explicit human command')
    if requested and requested != (posted if human_posted else settings['review_status']):
        raise ValueError('requested status does not match configured transition')
    if human_posted:
        if mode != 'posts' or verdict != 'PASS' or current != settings['review_status']:
            raise ValueError('human Posted requires a QA-passed row in the review status')
        changes = {prop: posted}
    else:
        if current not in settings['edit_statuses']:
            raise ValueError('row is not in a configured edit status')
        if verdict == 'PASS':
            changes = {prop: settings['review_status']}
            flag = settings.get('flag_property')
            if flag and row.get('properties', {}).get(flag) == settings.get('failure_flag'):
                changes[flag] = None
        elif mode == 'videos' and settings.get('failure_status'):
            changes = {prop: settings['failure_status']}
        elif settings.get('flag_property') and settings.get('failure_flag'):
            changes = {settings['flag_property']: settings['failure_flag']}
        else:
            raise ValueError('FAIL requires configured failure flag or videos failure status')
        if settings.get('qa_property'):
            changes[settings['qa_property']] = verdict.title()
    return {'page_id': row_id(row), 'command': 'local_qa_record', 'local_status': changes, 'properties': {}, 'patches': [], 'notion_writeback': False,
            'expected_current_status': current, 'workspace_id': config.get('workspace_id'),
            'hub_id': config.get('hub_id'), 'simulated_human_post': bool(human_posted and simulated),
            'write_performed': False, 'instruction': 'Local record only. Never apply status, flags or tags to Notion.'}


UPLOAD_ROLES = {'broll': 'broll', 'b-roll': 'broll', 'b roll': 'broll',
                'pictures': 'pictures', 'picture': 'pictures', 'photo': 'pictures',
                'styles': 'styles', 'style': 'styles'}
UPLOAD_EXT = {
    'broll': {'.mp4', '.mov', '.m4v', '.webm'},
    'pictures': {'.png', '.jpg', '.jpeg', '.webp', '.heic', '.gif'},
    'styles': {'.mp4', '.mov', '.m4v', '.webm', '.png', '.jpg', '.jpeg', '.webp', '.json', '.html'},
}


def _require_hub(layout, workspace_id=None, hub_id=None):
    """The only hub a style push may name. Raises if this session never recorded one, or the caller names another."""
    if not isinstance(layout, dict):
        raise ValueError('layout config missing; configure the authorized Content hub first')
    authorized_workspace, authorized_hub = layout.get('workspace_id'), layout.get('hub_id')
    if not authorized_workspace or not authorized_hub or layout.get('asset_upload') != 'authorized_hub':
        raise ValueError('no authorized Content hub in this session; configure that page before uploading')
    if workspace_id is not None and not same_hub_id(workspace_id, authorized_workspace):
        raise ValueError('refusing upload: workspace does not match the authorized Content hub')
    if hub_id is not None and not same_hub_id(hub_id, authorized_hub):
        raise ValueError('refusing upload: hub does not match the authorized Content hub')
    return authorized_workspace, authorized_hub


def _style_object(path):
    data = json.loads(Path(path).expanduser().read_text())
    if not isinstance(data, dict):
        raise ValueError('style file must be a JSON object')
    return {k: v for k, v in data.items() if not str(k).startswith('_')}


def _style_from_body(body):
    text = (body or '').strip()
    if not text:
        raise ValueError('style page has no body to import')
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', text, re.S)
        if not match:
            raise ValueError('style page body is not JSON')
        data = json.loads(match.group(0))
    if not isinstance(data, dict) or not any(k in data for k in ('font_size_frac', 'highlight_color', 'punch', 'font', 'loudness')):
        raise ValueError('page body is not a style file')
    return {k: v for k, v in data.items() if not str(k).startswith('_')}


def push_style(layout, style_path, *, title=None, workspace_id=None, hub_id=None):
    """Plan one Styles-database page whose body is the local style.json. Does not call Notion.

    notion_writeback on the layout stays false (it licenses nothing; QA never pushes). This plan is a style
    file only, and only when workspace and hub match the Content page authorized in this session.
    """
    ws, hub = _require_hub(layout, workspace_id, hub_id)
    configured = (layout.get('roles') or {}).get('styles')
    if not configured or not configured.get('database_id') or not configured.get('title_property'):
        raise ValueError('styles role is not mapped on the authorized hub')
    path = Path(style_path).expanduser()
    if not path.is_file():
        raise ValueError('no file ' + str(style_path))
    data = _style_object(path)
    name = plain_title(title or path.parent.name)
    if not name:
        raise ValueError('title required')
    return {'command': 'push_style_to_authorized_hub', 'notion_writeback': True, 'write_performed': False,
            'scope': 'authorized_hub', 'workspace_id': ws, 'hub_id': hub, 'role': 'styles',
            'database_id': configured['database_id'], 'data_source_id': configured.get('data_source_id'),
            'title': name, 'local_file': str(path.resolve()),
            'properties': {configured['title_property']: name},
            'files_property': configured.get('files_property'),
            'body': json.dumps(data, indent=2, ensure_ascii=False), 'style': data,
            'schema_columns_added': [],
            'instruction': 'Create or update one page in this Styles database only if its workspace and parent hub '
                           'still match workspace_id and hub_id. Set only the title property. Put body on the page '
                           'as the style JSON and attach local_file to files_property when that property exists. '
                           'Do not add columns. Do not write anywhere else.'}


def import_style(layout, page, dest, *, workspace_id=None, hub_id=None):
    """Write style.json from a page export. Refuses a different workspace or hub. Does not call Notion."""
    ws, hub = _require_hub(layout, workspace_id if workspace_id is not None else page.get('workspace_id'),
                           hub_id if hub_id is not None else page.get('hub_id'))
    if page.get('workspace_id') and not same_hub_id(page['workspace_id'], ws):
        raise ValueError('refusing import: workspace does not match the authorized Content hub')
    if page.get('hub_id') and not same_hub_id(page['hub_id'], hub):
        raise ValueError('refusing import: hub does not match the authorized Content hub')
    if isinstance(page.get('style'), dict):
        data = page['style']
    elif (page.get('body') or '').strip():
        data = _style_from_body(page['body'])
    else:   # a Styles row with the style file attached instead of pasted into the page
        attached = next((f.get('path') for f in page.get('files') or []
                         if str(f.get('path') or f.get('name') or '').endswith('.json') and f.get('path')), None)
        if not attached or not Path(attached).expanduser().is_file():
            raise ValueError('style page has no body and no downloaded .json file to import')
        data = _style_from_body(Path(attached).expanduser().read_text())
    data = {k: v for k, v in data.items() if not str(k).startswith('_')}
    folder = Path(dest).expanduser()
    folder.mkdir(parents=True, exist_ok=True)
    out = folder / 'style.json'
    tmp = out.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')
    tmp.replace(out)
    return {'path': str(out), 'notion_writeback': False, 'write_performed': False, 'imported': True}


def upload_plan(layout, *, role, title, local_file, workspace_id=None, hub_id=None, origin=None):
    """Plan one create inside the Content hub this session recorded. Does not call Notion.

    The only properties named are ones detect() already found. Origin is a sentence in
    the page body (provenance, not a licence clearance), never a new column or a new select option.
    """
    if not isinstance(layout, dict):
        raise ValueError('layout config missing; configure the authorized Content hub first')
    authorized_workspace, authorized_hub = layout.get('workspace_id'), layout.get('hub_id')
    if not authorized_workspace or not authorized_hub or layout.get('asset_upload') != 'authorized_hub':
        raise ValueError('no authorized Content hub in this session; configure that page before uploading')
    if workspace_id is not None and not same_hub_id(workspace_id, authorized_workspace):
        raise ValueError('refusing upload: workspace does not match the authorized Content hub')
    if hub_id is not None and not same_hub_id(hub_id, authorized_hub):
        raise ValueError('refusing upload: hub does not match the authorized Content hub')
    role_key = UPLOAD_ROLES.get((role or '').strip().lower())
    if role_key is None:
        raise ValueError('upload role must be broll, pictures or styles')
    configured = (layout.get('roles') or {}).get(role_key)
    if not configured:
        raise ValueError('role is not mapped on the authorized hub: ' + role_key)
    title_prop = configured.get('title_property')
    files_prop = configured.get('files_property')
    database_id = configured.get('database_id')
    if not title_prop or not files_prop or not database_id:
        raise ValueError('refusing upload: this database has no detected title, files property and database id')
    cleaned = plain_title(title)
    if not cleaned:
        raise ValueError('title required')
    path = Path(local_file).expanduser()
    if not path.is_file():
        raise ValueError('no file ' + str(local_file))
    ext = path.suffix.lower()
    if ext not in UPLOAD_EXT[role_key]:
        raise ValueError(f'a {role_key} upload must be one of {", ".join(sorted(UPLOAD_EXT[role_key]))} (got {ext or "no extension"})')
    if origin is not None and origin not in {'ai', 'stock', 'own', 'unknown'}:
        raise ValueError('origin must be ai, stock, own or unknown')
    properties = {title_prop: cleaned}
    body = ''
    if origin:
        body = f'Origin: {origin}. Provenance only, not a licence clearance.'
    return {'command': 'upload_to_authorized_hub', 'notion_writeback': True, 'write_performed': False,
            'scope': 'authorized_hub', 'workspace_id': authorized_workspace, 'hub_id': authorized_hub,
            'role': role_key, 'database_id': database_id, 'data_source_id': configured.get('data_source_id'),
            'title': cleaned, 'local_file': str(path.resolve()), 'properties': properties,
            'files_property': files_prop, 'body': body, 'schema_columns_added': [],
            'poster_upload': False, 'descriptive_labels': False,
            # B-roll is not "added" until it carries a reviewed title and tags. The create is only the first half.
            'completion_required': role_key == 'broll', 'title_is_provisional': role_key == 'broll',
            'required_steps': ['Create the page (this plan). Its title is provisional: the name he gave, no claim about what it shows.',
                               'Refresh the index, then library attach <new page id> <this local file> (no download needed).',
                               'library sort frames, look at every frame, library sort apply.',
                               'Fetch a fresh snapshot and library sort writeback --input snapshot.json --page-id <new page id>; apply its patch. '
                               'His request to add the clip already covers this; do not ask again.',
                               'Refresh the index, fetch again and re-run writeback. Tell him the clip is added only when the page is listed under unchanged. '
                               'If a step is blocked, say the clip is in Notion but not yet titled and tagged, and why.'] if role_key == 'broll' else [],
            'instruction': 'Create one page in this database only if its workspace and parent hub still match '
                           'workspace_id and hub_id. Set only properties (the existing title). Attach the local file '
                           'to files_property. Put body on the page as content. Do not add, rename or delete properties, '
                           'do not create select options, do not upload a poster, and do not write anywhere else.'}


# ---------------------------------------------------------------- one-time hub setup
# What the kit needs on his Content page, one table per role. Setup reuses a table that is
# already there (matched by name), adds only the missing fields, and creates a missing table.
# It never deletes or renames a table or a field, and never changes a field's type.
SETUP_ROLES = {
    'broll': {'title': 'B-roll Clips', 'names': {'broll', 'brollclips', 'brollclip', 'brolllibrary'},
              'properties': {'Name': 'title', 'Files & media': 'files', 'Tags': 'multi_select',
                             'Origin': 'select', 'Duration (s)': 'number', 'Original title': 'rich_text'}},
    'pictures': {'title': 'Pictures', 'names': {'pictures', 'picture', 'photos', 'images', 'screenshots'},
                 'properties': {'Name': 'title', 'Files & media': 'files', 'Tags': 'multi_select'}},
    'graphics': {'title': 'Motion Graphics', 'names': {'graphics', 'motiongraphics', 'motiongraphic', 'graphic'},
                 'properties': {'Name': 'title', 'Files & media': 'files', 'Tags': 'multi_select'}},
    'styles': {'title': 'Styles', 'names': {'styles', 'style', 'editingstyles', 'captionstyles'},
               'properties': {'Name': 'title', 'Files & media': 'files', 'Tags': 'multi_select'}},
}
SETUP_OPTIONS = {'Origin': ['AI', 'Stock', 'Own']}


def _setup_key(title):
    words = re.findall(r'[a-z0-9]+', plain_title(title).lower())
    return ''.join(w for w in words if w not in {'database', 'db', 'table', 'library'} or len(words) == 1)


def setup_plan(payload):
    """Plan the one-time Content page setup. Does not call Notion.

    payload: {workspace_id, hub_id, databases: [{title, database_id, data_source_id, schema: {name: {type}}}]}
    listing the tables already under that page (empty when the page is empty).
    """
    ws, hub = payload.get('workspace_id'), payload.get('hub_id')
    if not ws or not hub:
        raise ValueError('setup needs workspace_id and hub_id of the Content page')
    existing = payload.get('databases') or []
    steps, used = [], set()
    for role, spec in SETUP_ROLES.items():
        found = [d for d in existing if _setup_key(d.get('title', '')) in spec['names'] and id(d) not in used]
        if len(found) > 1:
            raise ValueError(f'more than one table looks like {role}: ' + ', '.join(d.get('title', '?') for d in found))
        if not found:
            props = {name: ({'type': t, 'options': SETUP_OPTIONS[name]} if name in SETUP_OPTIONS else {'type': t})
                     for name, t in spec['properties'].items()}
            steps.append({'action': 'create_database', 'role': role, 'parent_page_id': hub, 'title': spec['title'],
                          'properties': props})
            continue
        db = found[0]
        used.add(id(db))
        schema = db.get('schema') or {}
        types = {v.get('type') for v in schema.values()}
        add, conflicts = {}, []
        for name, t in spec['properties'].items():
            if t == 'title':
                continue                                  # every Notion table already has one title field
            if t == 'files' and 'files' in types:
                continue                                  # one files field is enough, whatever it is called
            same = next((k for k in schema if k.casefold() == name.casefold()), None)
            if same is not None:
                if schema[same].get('type') != t:
                    conflicts.append(f'{same} is {schema[same].get("type")}, kit wanted {t}; left as is')
                continue
            add[name] = {'type': t, 'options': SETUP_OPTIONS[name]} if name in SETUP_OPTIONS else {'type': t}
        step = {'action': 'add_properties' if add else 'reuse', 'role': role, 'title': db.get('title'),
                'database_id': db.get('database_id'), 'data_source_id': db.get('data_source_id')}
        if add:
            step['properties'] = add
        if conflicts:
            step['notes'] = conflicts
        steps.append(step)
    return {'command': 'setup_content_hub', 'write_performed': False, 'workspace_id': ws, 'hub_id': hub,
            'steps': steps,
            'summary': [f"{s['action'].replace('_', ' ')}: {s['title']}" + (f" (+ {', '.join(s['properties'])})" if s['action'] == 'add_properties' else '')
                        for s in steps],
            'instruction': 'Show him the summary and wait for his OK. Then, with the Notion connection, only inside '
                           'hub_id: create each create_database table under parent_page_id with exactly these fields, '
                           'and add only the listed fields to each add_properties table. Never delete or rename a '
                           'table or field, never change a field type, never write outside this page. Then fetch the '
                           'tables again and run library detect, plan and index (docs/NOTION-MCP.md).'}


def upload_cli(args):
    default = Path.home() / '.matthew-studio-kit'
    layout_path = args.layout or os.environ.get('KIT_NOTION_LAYOUT', str(default / 'notion_layout.json'))
    if not Path(layout_path).expanduser().is_file():
        raise ValueError('layout config missing; configure the authorized Content hub first')
    if not args.args or not args.role or not args.name:
        raise ValueError('kit library upload <file> --role broll|pictures|styles --name <title> [--origin ai|stock|own|unknown]')
    result = upload_plan(read_json(layout_path), role=args.role, title=args.name, local_file=args.args[0],
                         workspace_id=getattr(args, 'workspace_id', None), hub_id=getattr(args, 'hub_id', None),
                         origin=getattr(args, 'origin', None))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def run(args):
    default = Path.home() / '.matthew-studio-kit'
    layout_path = args.layout or os.environ.get('KIT_NOTION_LAYOUT', str(default / 'notion_layout.json'))
    index_path = args.index or os.environ.get('KIT_NOTION_INDEX', str(default / 'notion_index.json'))
    if args.action == 'sort':
        import notion_sort
        result = notion_sort.run(args, index_path, layout_path)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    payload = read_json(args.input or '-') if args.action not in {'find', 'attach'} else None
    index = read_json(index_path, empty_index())
    if args.action not in {'find', 'attach'} and payload is None:
        raise ValueError('input JSON file does not exist')
    if args.action in {'index', 'workflow'} and not Path(layout_path).expanduser().is_file():
        raise ValueError('layout config missing; run library detect with MCP schema exports first')
    if args.action == 'setup':
        result = setup_plan(payload)
    elif args.action == 'detect':
        result = detect(payload)
        save_json(layout_path, result)
    elif args.action == 'plan':
        result = plan(index, payload, args.force)
    elif args.action == 'index':
        result = refresh(index, read_json(layout_path), payload['inventory'], payload['pages'], Path(index_path).expanduser().parent, args.force)
        save_json(index_path, index)
    elif args.action == 'override':
        set_override(index, payload['page_id'], payload['patch'])
        save_json(index_path, index)
        result = index['overrides']
    elif args.action == 'attach':
        if len(args.args) != 2:
            raise ValueError('kit library attach <page_id> <downloaded file>')
        result = attach(index, args.args[0], args.args[1], Path(index_path).expanduser().parent)
        save_json(index_path, index)
    elif args.action == 'find':
        if args.limit < 1:
            raise ValueError('limit must be positive')
        result = find(index, ' '.join(args.args), args.kind, args.origin, args.aspect, args.limit, args.ignore_body)
    elif args.action == 'workflow':
        if not args.qa_report:
            raise ValueError('--qa-report must name the actual kit qa.json')
        qa = read_json(args.qa_report)
        if not qa or not Path(qa.get('video', '')).is_file():
            raise ValueError('QA report must reference an existing rendered video')
        if any(x.get('sev') == 'FAIL' for x in qa.get('items', [])) and qa.get('verdict') == 'PASS':
            raise ValueError('inconsistent QA report')
        result = transition(read_json(layout_path), payload, qa.get('verdict'), args.requested_status, args.human_posted, args.simulated)
        result['qa_report'] = str(Path(args.qa_report).resolve())
        result['video'] = qa['video']
        result['video_sha256'] = sha256(qa['video'])
    else:
        raise ValueError('unknown offline library command')
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0
