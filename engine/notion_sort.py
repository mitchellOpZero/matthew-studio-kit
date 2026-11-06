"""Local frame extraction and validated Codex annotations. No vision/network API."""
import copy
from datetime import datetime
import json
import math
from pathlib import Path
import re
import subprocess

import notion_index as ni

SCHEMA = Path(__file__).with_name('sort_schema.json')
OPT_IN = 'sort my Notion and save tags to Notion'


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


def plan(index, ignore_body=False):
    pending, skipped = [], []
    for key, entry in index['entries'].items():
        if entry['stale'] or entry['role'] not in {'broll', 'graphics', 'pictures'} or ni.effective(entry, index)['exclude']:
            continue
        if ni.sha256(entry['path']) != entry['sha256']:
            raise ValueError('source bytes changed; refresh index first: ' + key)
        record = entry.get('ai_sort')
        done = bool(record and record['file_sha256'] == entry['sha256'] and (not ignore_body or record['ignore_body']))
        (skipped if done else pending).append(key)
    return {'to_sort': pending, 'skipped': skipped, 'notion_writeback': False, 'write_performed': False}


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
        if record['file_sha256'] != entry['sha256'] or ni.sha256(entry['path']) != entry['sha256']:
            raise ValueError('source SHA mismatch: ' + key)
        extracted = entry.get('sort_frames', [])
        if not extracted or record['frame_hashes'] != [ni.sha256(f['path']) for f in extracted] or record['frame_hashes'] != [f['sha256'] for f in extracted]:
            raise ValueError('frame hashes do not match extracted files: ' + key)
        if record['ignore_body'] and any(e['source'] == 'body' for e in record['origin']['evidence']):
            raise ValueError('body evidence forbidden for --ignore-body annotation')
        entry['ai_sort'] = copy.deepcopy(record)
    index.clear()
    index.update(work)
    return {'applied': sorted(seen), 'write_performed': False, 'notion_writeback': False}


def writeback(index, phrase=None, page_id=None):
    """Visual tags stay local. No phrase turns them into Notion properties or new columns.

    Adding a b-roll clip, picture or style is `library upload`, which is limited to the
    Content hub authorized in this session and is a different command from this one.
    """
    return {'patches': [], 'notion_writeback': False, 'write_performed': False,
            'instruction': 'Visual tags stay in the local index (no new Notion columns). To add a clip, picture or style, use library upload; it only targets the Content hub authorized in this session.'}


def run(args, index_path):
    index = ni.read_json(index_path, ni.empty_index())
    action = args.args[0] if args.args else 'plan'
    if len(args.args) > 1:
        raise ValueError('sort accepts one action: plan, frames, apply or writeback')
    if action == 'plan':
        return plan(index, args.ignore_body)
    if action == 'frames':
        if not args.frames_dir:
            raise ValueError('--frames-dir required')
        result = frames(index, args.frames_dir, args.ignore_body)
    elif action == 'apply':
        if not args.input:
            raise ValueError('--input required')
        result = apply(index, ni.read_json(args.input))
    elif action == 'writeback':
        return writeback(index, args.phrase, args.page_id)
    else:
        raise ValueError('unknown sort action: ' + action)
    ni.save_json(index_path, index)
    return result
