"""Opt-in, metadata-only Codex support. No prompts, transcripts, media or raw outputs.

Capture is local and passive. GitHub transport writes ONLY one data file on an opaque
support branch of the configured private repository. It never checks out that branch.
"""
from __future__ import annotations

import argparse
import base64
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import shlex
import shutil
import sqlite3
import subprocess
import sys
import time
from urllib.parse import quote
import uuid

ROOT = Path(__file__).resolve().parents[1]
REPO = 'mitchellOpZero/matthew-studio-kit'
DATA_FILE = '.support/diagnostics.json'
MAX_EVENTS = 3000
MAX_REMOTE = 1000
MAX_EVENT_BYTES = 20000
MAX_SNAPSHOT = 900000
SYNC_INTERVAL = 60
EVENTS = {'SessionStart', 'SessionEnd', 'PreToolUse', 'PostToolUse', 'Stop', 'Interrupt'}
SECRET = re.compile(r'(?i)(?:gh[pousr]_|github_pat_|sk-|ntn_|secret_|bearer\s|password|api.?key|access.?token)')
NAME = re.compile(r'^[A-Za-z0-9_./:+-]{1,160}$')
ID = re.compile(r'^[A-Za-z0-9_-]{1,128}$')
DEVICE = re.compile(r'^[a-f0-9]{32}$')
SHA = re.compile(r'^[a-f0-9]{40}$')
VERBS = {'draft', 'preview', 'render', 'style', 'graphics', 'blocks', 'library', 'doctor', 'update', 'version', 'qa', 'support', 'capcut', 'transcribe'}


def home():
    return Path(os.environ.get('KIT_SUPPORT_HOME', str(Path.home() / '.matthew-studio-kit' / 'support'))).expanduser()


def read_json(path, default=None):
    try:
        path = Path(path)
        if path.stat().st_size > 2000000:
            return default
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def config():
    value = read_json(home() / 'config.json', {})
    return value if isinstance(value, dict) else {}


def save_config(value):
    folder = home()
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = folder / ('config.' + uuid.uuid4().hex + '.tmp')
    temp.write_text(json.dumps(value, indent=2) + '\n')
    temp.chmod(0o600)
    temp.replace(folder / 'config.json')


def tag(value):
    value = str(value)
    return value if NAME.fullmatch(value) and not SECRET.search(value) else 'omitted'


def identity(value):
    value = str(value or '')
    return value if ID.fullmatch(value) and not SECRET.search(value) else 'h_' + hashlib.sha256(value.encode()).hexdigest()[:24]


def digest(path):
    try:
        path = Path(path)
        if not path.is_file() or path.stat().st_size > 2000000:
            return None
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def path_label(value, root=ROOT):
    """File identities, never user home names, URLs, or arbitrary argument values."""
    if not isinstance(value, (str, Path)) or '://' in str(value) or SECRET.search(str(value)):
        return 'omitted'
    try:
        p = Path(value).expanduser()
        p = (Path(root) / p).resolve() if not p.is_absolute() else p.resolve()
        try:
            return 'kit/' + '/'.join(tag(x) for x in p.relative_to(Path(root).resolve()).parts)
        except ValueError:
            return 'external/' + '/'.join(tag(x) for x in p.parts[-2:])
    except (OSError, ValueError):
        return 'omitted'


def fingerprint(path, root=ROOT):
    return {'path': path_label(path, root), 'sha256': digest(path)}


def command_summary(command, root=ROOT):
    # Unknown arguments and inline code are intentionally discarded, not regex-redacted.
    if not isinstance(command, str):
        return {'detail': 'omitted'}
    try:
        lex = shlex.shlex(command[:65536], posix=True, punctuation_chars=';&|')
        lex.whitespace_split = True
        parts = list(lex)
    except ValueError:
        return {'detail': 'unparsed'}
    programs, files, kit = [], [], []
    start = True
    for i, part in enumerate(parts):
        if part and all(c in ';&|' for c in part):
            start = True
            continue
        if start:
            if '=' in part:  # shell environment assignments are never retained
                continue
            programs.append(tag(Path(part).name))
            start = False
        if Path(part).name == 'kit':
            files.append(path_label(part, root))
            if i + 1 < len(parts) and parts[i + 1] in VERBS:
                kit.append(parts[i + 1])
        elif (part.endswith(('.py', '.rules')) or Path(part).name in {'SKILL.md', 'AGENTS.md', 'AGENTS.override.md', 'config.toml', 'style.json'}) and not part.startswith('-'):
            files.append(path_label(part, root))
    return {'programs': programs[:12], 'files': list(dict.fromkeys(files))[:16], 'kit_verbs': kit[:8], 'arguments': 'values omitted'}


def outcome(response):
    result = {'status': 'unknown'}
    if isinstance(response, dict):
        if isinstance(response.get('exit_code'), int):
            result.update(exit_code=response['exit_code'], status='failed' if response['exit_code'] else 'completed')
        elif response.get('isError') is True:
            result['status'] = 'failed'
        elif response.get('status') in {'completed', 'failed', 'cancelled'}:
            result['status'] = response['status']
        text = response.get('output', '')
    else:
        text = response if isinstance(response, str) else ''
    if isinstance(text, str):
        match = re.search(r'Process exited with code (-?\d+)', text[:8192])
        if match:
            result.update(exit_code=int(match[1]), status='failed' if int(match[1]) else 'completed')
        error = re.search(r'\b([A-Z][A-Za-z0-9]{0,45}(?:Error|Exception))\b', text[:8192])
        if error:
            result['error_class'] = tag(error[1])
    return result


@contextlib.contextmanager
def database():
    folder = home()
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    db = sqlite3.connect(str(folder / 'events.sqlite'), timeout=.2)
    try:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY,t REAL NOT NULL,body TEXT NOT NULL,sent INTEGER NOT NULL DEFAULT 0)')
        db.execute('CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY,value TEXT NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY,last REAL NOT NULL)')
        with db:
            yield db
    finally:
        db.close()


def meta_set(db, key, value):
    db.execute('INSERT OR REPLACE INTO meta VALUES (?,?)', (key, json.dumps(value)))


def meta_get(db, key, default=None):
    row = db.execute('SELECT value FROM meta WHERE key=?', (key,)).fetchone()
    return json.loads(row[0]) if row else default


def append(kind, fields, event_id=None, cfg=None):
    cfg = cfg or config()
    if not cfg.get('enabled'):
        return False
    record = {'id': event_id or uuid.uuid4().hex, 't': time.time(), 'kind': kind, **fields}
    payload = json.dumps(record, separators=(',', ':'))
    if len(payload.encode()) > MAX_EVENT_BYTES:
        record = {k: record[k] for k in ('id', 't', 'kind')}
        record['detail'] = 'oversize event omitted'
        payload = json.dumps(record)
    with database() as db:
        db.execute('INSERT OR IGNORE INTO events(id,t,body) VALUES (?,?,?)', (record['id'], record['t'], payload))
        extra = db.execute('SELECT max(0,count(*)-?) FROM events', (MAX_EVENTS,)).fetchone()[0]
        if extra:
            oldest = db.execute('SELECT id,sent FROM events ORDER BY sent DESC,t ASC LIMIT ?', (extra,)).fetchall()
            lost = sum(not row[1] for row in oldest)
            meta_set(db, 'unsent_dropped', meta_get(db, 'unsent_dropped', 0) + lost)
            db.executemany('DELETE FROM events WHERE id=?', [(r[0],) for r in oldest])
    return True


def observe(event):
    """Passive hook: no output, no permissions, no raw input/output retention."""
    cfg = config()
    if not cfg.get('enabled') or not isinstance(event, dict) or event.get('hook_event_name') not in EVENTS:
        return
    if not isinstance(event.get('session_id'), str) or not event['session_id'] or not isinstance(event.get('cwd'), str):
        append('gap', {'reason': 'hook identity missing'}, cfg=cfg)
        return
    root = Path(cfg.get('root', str(ROOT)))
    sid, turn, call = (identity(event.get(k)) for k in ('session_id', 'turn_id', 'tool_use_id'))
    try:
        inside = Path(event.get('cwd', '')).resolve().is_relative_to(root.resolve())
    except (OSError, ValueError, TypeError):
        inside = False
    with database() as db:
        seen = db.execute('SELECT 1 FROM sessions WHERE id=?', (sid,)).fetchone()
        if not inside and not seen:
            meta_set(db, 'out_of_scope', meta_get(db, 'out_of_scope', 0) + 1)
            return
        db.execute('INSERT OR REPLACE INTO sessions VALUES (?,?)', (sid, time.time()))
        db.execute('DELETE FROM sessions WHERE last<?', (time.time() - 7 * 86400,))
    kind = event['hook_event_name']
    fields = {'session': sid, 'turn': turn, 'call': call, 'model': tag(event.get('model', 'unknown'))}
    if kind in {'PreToolUse', 'PostToolUse'}:
        fields['tool'] = tag(event.get('tool_name', 'unknown'))
        inp = event.get('tool_input')
        if isinstance(inp, dict):
            fields['argument_names'] = [tag(k) for k in list(inp)[:24]]
            if fields['tool'] == 'Bash':
                fields['command'] = command_summary(inp.get('command', inp.get('cmd')), root)
            else:
                fields['files'] = [path_label(inp[k], root) for k in ('file_path', 'path') if isinstance(inp.get(k), str)]
        if kind == 'PostToolUse':
            fields['result'] = outcome(event.get('tool_response'))
    else:
        fields['source'] = tag(event.get('source', event.get('reason', 'unknown')))
    key = [cfg['device'], sid, turn, kind, call if event.get('tool_use_id') else str(int(time.time() // 2))]
    append(kind, fields, hashlib.sha256(json.dumps(key).encode()).hexdigest(), cfg)


def provenance(job=None, root=None):
    """Inspect source identities only. Never render, rebuild, or export media."""
    root = Path(root or ROOT).resolve()
    result = {'install': hashlib.sha256(str(root).encode()).hexdigest()[:16],
              'kit_version': tag((read_json(root / 'plugin.json', {}) or {}).get('version', 'unknown')),
              'instructions': [fingerprint(root / 'AGENTS.md', root)]}
    for skill in ('edit-short', 'style', 'graphics', 'library'):
        result['instructions'].append(fingerprint(root / 'skills' / skill / 'SKILL.md', root))
    if not job:
        result['styles'] = []
        for name in sorted({p.parent.name for base in ('styles', 'my-styles') for p in (root / base).glob('*/style.json')})[:15]:
            saved = root / 'my-styles' / name / 'style.json'
            selected = saved if saved.is_file() else root / 'styles' / name / 'style.json'
            result['styles'].append({'name': tag(name), 'layer': 'saved' if saved.is_file() else 'built-in',
                                     'source': fingerprint(selected, root), 'rules': fingerprint(selected.parent / 'STYLE.md', root)})
        result['recent_jobs'] = [tag(p.parent.name) for p in sorted((root / '.work').glob('*/edl.json'), key=lambda p: p.stat().st_mtime, reverse=True)[:8]]
        result['other_available_skills'] = []
        for base in (Path.home() / '.codex' / 'skills', Path.home() / '.agents' / 'skills'):
            for file in sorted(base.glob('*/SKILL.md')):
                if re.search(r'video|hyperframe|remotion|matthew', file.parent.name, re.I):
                    result['other_available_skills'].append(fingerprint(file, root))
                    if len(result['other_available_skills']) >= 16:
                        break
        result['recent_kit_commands'] = []
        try:
            from collections import deque
            with open(root / '.cache' / 'log' / 'events.jsonl') as stream:
                recent = list(deque(stream, maxlen=8))
            for line in recent:
                old = json.loads(line)
                if old.get('cmd') in VERBS:
                    result['recent_kit_commands'].append({'verb': old['cmd'], 'source': 'historical kit log only',
                        'command': command_summary('bin/kit ' + old['cmd'] + ' ' + str(old.get('args', '')), root),
                        'result': outcome({'exit_code': old.get('code'), 'output': old.get('error', '')})})
        except (OSError, ValueError, TypeError):
            pass
        return result
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', job):
        raise ValueError('use a kit job name, not a path')
    edl = read_json(root / '.work' / job / 'edl.json', {})
    if not isinstance(edl, dict):
        edl = {}
    name = edl.get('style_name', 'matthew')
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', name):
        name = 'unknown'
    saved = root / 'my-styles' / name / 'style.json'
    source = saved if saved.is_file() else root / 'styles' / name / 'style.json'
    style = read_json(source, {}) or {}
    if not isinstance(style, dict):
        style = {}
    overrides = edl.get('style') if isinstance(edl.get('style'), dict) else {}
    effective = dict(style, **overrides)
    result.update(job=tag(job), style_name=name, style_source=fingerprint(source, root),
                  style_layer='saved' if saved.is_file() else 'built-in',
                  override_keys=[tag(k) for k in overrides][:30],
                  overrides_sha256=hashlib.sha256(json.dumps(overrides, sort_keys=True).encode()).hexdigest())
    safe_settings = {}
    for key in ('font_size_frac', 'center_y_frac', 'max_words', 'kw_pop_pct', 'keyword_scale', 'one_line'):
        if isinstance(effective.get(key), (int, float, bool)):
            safe_settings[key] = effective[key]
    for key in ('caption_template', 'font_file', 'highlight_color'):
        if key in effective:
            safe_settings[key] = tag(effective[key])
    result['effective_settings'] = safe_settings
    project = root / '.work' / '_studio' / job
    html = project / 'index.html'
    result['project'] = fingerprint(html, root)
    mark = read_json(project / 'timeline.json', {}) or {}
    result['project_style_name'] = tag(mark.get('style_name', 'unknown'))
    result['warnings'] = []
    if html.is_file() and (project / '.kit-generated').is_file():
        generated_hash = (project / '.kit-generated').read_text().strip()
        actual = hashlib.sha256(re.sub(r' data-hf-id="[^"]*"', '', html.read_text()).encode()).hexdigest()
        result['hand_edited'] = actual != generated_hash
        if result['hand_edited']:
            result['warnings'].append('normal preview preserves this hand-edited project; forced rebuild would overwrite it')
    compare_keys = set(safe_settings) - {'center_y_frac'}  # face avoidance legitimately moves the caption height
    if isinstance(mark.get('style'), dict) and any(mark['style'].get(k) != effective.get(k) for k in compare_keys):
        result['warnings'].append('project settings differ from current style or per-video overrides')
    font_name = effective.get('font_file')
    if isinstance(font_name, str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,128}\.(?:ttf|otf)', font_name, re.I):
        options = [source.parent / 'fonts' / font_name, root / 'assets' / 'fonts' / font_name]
        font = next((p for p in options if p.is_file()), options[-1])
        copied = mark.get('font')
        if isinstance(copied, str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', copied):
            project_font = project / 'assets' / copied
            result['font'] = {'source': fingerprint(font, root), 'project_copy': fingerprint(project_font, root),
                              'different_bytes': bool(digest(font) and digest(project_font) and digest(font) != digest(project_font))}
    result['blocks'] = []
    for block in (edl.get('blocks') or [])[:20]:
        bname = block.get('name') if isinstance(block, dict) else None
        if not isinstance(bname, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', bname):
            continue
        candidates = [root / 'my-styles' / name / 'templates' / bname / (bname + '.html'),
                      root / 'styles' / name / 'templates' / bname / (bname + '.html'),
                      root / 'graphics' / bname / (bname + '.html'),
                      root / '.cache' / 'blocks' / bname / 'compositions' / (bname + '.html')]
        src = next((p for p in candidates if p.is_file()), candidates[-1])
        copy = project / 'compositions' / (bname + '.html')
        stale = bool(digest(src) and digest(copy) and digest(src) != digest(copy))
        result['blocks'].append({'name': bname, 'resolved_source': fingerprint(src, root),
                                 'project_copy': fingerprint(copy, root), 'different_bytes': stale})
        if stale:
            result['warnings'].append('project graphic differs from current source: ' + bname)
    return result


def diagnostic_snapshot():
    result = provenance()
    result['python_version'] = platform.python_version()
    for exe in ('codex', 'git'):
        try:
            version = subprocess.check_output([exe, '--version'], timeout=2, stderr=subprocess.DEVNULL).decode().strip()
            result[exe + '_cli_version'] = ' '.join(tag(x) for x in version.split()[:3])
        except (OSError, subprocess.SubprocessError):
            result[exe + '_cli_version'] = 'unavailable'
    try:
        value = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], timeout=2, stderr=subprocess.DEVNULL).decode().strip()
        result['commit'] = value if SHA.fullmatch(value) else 'unknown'
    except (OSError, subprocess.SubprocessError):
        result['commit'] = 'unknown'
    try:
        with open('/Applications/Codex.app/Contents/Info.plist', 'rb') as stream:
            result['desktop_app_version'] = tag(plistlib.load(stream).get('CFBundleShortVersionString', 'unknown'))
    except (OSError, ValueError, plistlib.InvalidFileException):
        result['desktop_app_version'] = 'unavailable'
    return result


def kit_event(argv, code, secs):
    cfg = config()
    if not cfg.get('enabled') or not argv or argv[0] == 'support':
        return
    verb = argv[0]
    job = argv[1] if verb in {'preview', 'render', 'qa'} and len(argv) > 1 and re.fullmatch(r'[A-Za-z0-9_-]{1,100}', argv[1]) else None
    info = provenance(job, Path(cfg['root']))
    try:
        sha = subprocess.check_output(['git', '-C', cfg['root'], 'rev-parse', 'HEAD'], timeout=2, stderr=subprocess.DEVNULL).decode().strip()
        info['commit'] = sha if SHA.fullmatch(sha) else 'unknown'
    except (OSError, subprocess.SubprocessError):
        info['commit'] = 'unknown'
    append('kit', {'verb': tag(verb), 'exit_code': int(code), 'seconds': round(secs, 3), 'provenance': info}, cfg=cfg)


class GitHubError(RuntimeError):
    pass


def gh(method, endpoint, payload=None):
    if method != 'GET':
        safe_ref = (method == 'POST' and endpoint == 'repos/' + REPO + '/git/refs' and isinstance(payload, dict)
                    and re.fullmatch(r'refs/heads/support/[a-f0-9]{32}', str(payload.get('ref', '')))
                    and SHA.fullmatch(str(payload.get('sha', ''))))
        safe_file = (method == 'PUT' and endpoint == 'repos/' + REPO + '/contents/' + DATA_FILE
                     and isinstance(payload, dict) and re.fullmatch(r'support/[a-f0-9]{32}', str(payload.get('branch', ''))))
        if not (safe_ref or safe_file):
            raise GitHubError('support_write_target_rejected')
    exe = shutil.which('gh')
    if not exe:
        raise GitHubError('gh_not_installed')
    args = [exe, 'api', '--hostname', 'github.com', '--method', method,
            '-H', 'Accept: application/vnd.github+json', '-H', 'X-GitHub-Api-Version: 2026-03-10', endpoint]
    if payload is not None:
        args += ['--input', '-']
    env = dict(os.environ, GH_PROMPT_DISABLED='1', GH_PAGER='cat')
    env.pop('GH_DEBUG', None)
    try:
        r = subprocess.run(args, input=json.dumps(payload) if payload is not None else None,
                           capture_output=True, text=True, timeout=15, env=env)
    except (OSError, subprocess.SubprocessError):
        raise GitHubError('github_unavailable')
    if r.returncode:
        status = re.search(r'HTTP\s+(\d{3})', r.stderr)
        raise GitHubError('http_' + status[1] if status else 'github_unavailable')
    try:
        if len(r.stdout.encode()) > 2000000:
            raise ValueError()
        return json.loads(r.stdout)
    except ValueError:
        raise GitHubError('invalid_github_response')


def check_repo(repo, write=False):
    if repo != REPO:
        raise GitHubError('repository_not_allowlisted')
    data = gh('GET', 'repos/' + repo)
    if data.get('full_name', '').casefold() != repo.casefold() or data.get('private') is not True:
        raise GitHubError('repository_not_private_or_identity_changed')
    if write and (data.get('permissions') or {}).get('push') is not True:
        raise GitHubError('repository_write_permission_missing')
    return data


def branch(device):
    if not isinstance(device, str) or not DEVICE.fullmatch(device):
        raise GitHubError('invalid_device_id')
    return 'support/' + device


def remote_snapshot(repo, device):
    if repo != REPO:
        raise GitHubError('repository_not_allowlisted')
    ref = branch(device)
    data = gh('GET', 'repos/' + repo + '/contents/' + DATA_FILE + '?ref=' + quote(ref, safe=''))
    if data.get('type') != 'file' or data.get('path') != DATA_FILE or data.get('encoding') != 'base64' or not SHA.fullmatch(str(data.get('sha', ''))):
        raise GitHubError('invalid_support_file')
    try:
        raw = base64.b64decode(data['content'], validate=False)
        if len(raw) > MAX_SNAPSHOT:
            raise ValueError()
        snap = json.loads(raw)
        if snap.get('schema') != 1 or snap.get('device') != device or not isinstance(snap.get('events'), list):
            raise ValueError()
        if any(not isinstance(e, dict) or not isinstance(e.get('id'), str) for e in snap['events']):
            raise ValueError()
        allowed = {'id', 't', 'kind', 'session', 'turn', 'call', 'model', 'tool', 'argument_names',
                   'command', 'files', 'result', 'source', 'detail', 'reason', 'verb', 'exit_code', 'seconds', 'provenance'}
        for event in snap['events']:
            if set(event) - allowed or not re.fullmatch(r'[a-f0-9]{32,64}', event['id']):
                raise ValueError()
    except (ValueError, KeyError, TypeError):
        raise GitHubError('invalid_support_snapshot')
    return snap, data['sha']


def flush(force=False):
    cfg = config()
    if not cfg.get('enabled'):
        return {'status': 'disabled', 'uploaded': 0}
    folder = home()
    folder.mkdir(parents=True, exist_ok=True)
    with open(folder / 'sync.lock', 'a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {'status': 'sync_in_progress', 'uploaded': 0}
        with database() as db:
            last = meta_get(db, 'last_attempt', 0)
            if not force and time.time() - last < SYNC_INTERVAL:
                return {'status': 'throttled', 'uploaded': 0}
            selected = db.execute('SELECT id,body FROM events WHERE sent=0 ORDER BY t LIMIT 500').fetchall()
            rows, size = [], 0
            for row in selected:
                if size + len(row[1].encode()) > 400000:
                    break
                rows.append(row); size += len(row[1].encode())
            if not rows:
                return {'status': 'up_to_date', 'uploaded': 0}
            meta_set(db, 'last_attempt', time.time())
        try:
            repo = cfg.get('repo')
            metadata = check_repo(repo, write=True)
            ref = branch(cfg.get('device'))
            try:
                gh('GET', 'repos/' + repo + '/git/ref/heads/' + ref)
            except GitHubError as exc:
                if str(exc) != 'http_404':
                    raise
                default = metadata.get('default_branch', '')
                if not re.fullmatch(r'[A-Za-z0-9_./-]{1,200}', default) or default.startswith('support/'):
                    raise GitHubError('invalid_default_branch')
                base = gh('GET', 'repos/' + repo + '/git/ref/heads/' + default)
                sha = (base.get('object') or {}).get('sha', '')
                if not SHA.fullmatch(sha):
                    raise GitHubError('invalid_commit')
                if not config().get('enabled'):
                    raise GitHubError('disabled')
                try:
                    gh('POST', 'repos/' + repo + '/git/refs', {'ref': 'refs/heads/' + ref, 'sha': sha})
                except GitHubError as exc:
                    if str(exc) != 'http_422':
                        raise
                    gh('GET', 'repos/' + repo + '/git/ref/heads/' + ref)
            batch = [json.loads(r[1]) for r in rows]
            for attempt in range(2):
                try:
                    old, file_sha = remote_snapshot(repo, cfg['device'])
                except GitHubError as exc:
                    if str(exc) != 'http_404':
                        raise
                    old, file_sha = {'events': []}, None
                ids = {e['id'] for e in old['events']}
                if not {r[0] for r in rows} <= ids:
                    batch_ids = {e['id'] for e in batch}
                    retained = sorted([e for e in old['events'] if e['id'] not in batch_ids], key=lambda e: e.get('t', 0))[-(MAX_REMOTE-len(batch)):]
                    values = sorted(retained + batch, key=lambda e: e.get('t', 0))
                    snap = {'schema': 1, 'device': cfg['device'], 'updated_at': time.time(), 'events': values,
                            'coverage': coverage(), 'retention': 'current snapshot bounded; Git history retains earlier commits'}
                    while len(json.dumps(snap).encode()) > MAX_SNAPSHOT and len(snap['events']) > len(batch):
                        drop = next((i for i, e in enumerate(snap['events']) if e['id'] not in batch_ids), None)
                        if drop is None:
                            break
                        snap['events'].pop(drop)
                    if not {r[0] for r in rows} <= {e['id'] for e in snap['events']}:
                        raise GitHubError('snapshot_capacity_exceeded')
                    payload = {'message': '[skip ci] Update kit support diagnostics', 'branch': ref,
                               'content': base64.b64encode(json.dumps(snap).encode()).decode()}
                    if file_sha:
                        payload['sha'] = file_sha
                    if not config().get('enabled') or config().get('generation') != cfg.get('generation'):
                        raise GitHubError('disabled_or_configuration_changed')
                    try:
                        gh('PUT', 'repos/' + repo + '/contents/' + DATA_FILE, payload)
                    except GitHubError as exc:
                        if str(exc) == 'http_409' and not attempt:
                            continue
                        raise
                    confirmed, _ = remote_snapshot(repo, cfg['device'])
                    if not {r[0] for r in rows} <= {e['id'] for e in confirmed['events']}:
                        raise GitHubError('readback_incomplete')
                with database() as db:
                    db.executemany('UPDATE events SET sent=1 WHERE id=?', [(r[0],) for r in rows])
                    meta_set(db, 'last_success', time.time())
                    meta_set(db, 'last_error', None)
                return {'status': 'synced', 'uploaded': len(rows), 'branch': ref}
            raise GitHubError('conflict_retry_exhausted')
        except (GitHubError, OSError, ValueError, TypeError) as exc:
            category = str(exc) if isinstance(exc, GitHubError) else 'local_sync_error'
            with database() as db:
                meta_set(db, 'last_error', category)
            return {'status': 'queued', 'uploaded': 0, 'error': category}


def coverage():
    if not (home() / 'events.sqlite').is_file():
        return {'observed': {}, 'pending': 0, 'unsent_dropped': 0}
    with database() as db:
        values = [json.loads(r[0]) for r in db.execute('SELECT body FROM events ORDER BY t')]
        counts = {kind: sum(e['kind'] == kind for e in values) for kind in EVENTS | {'kit'}}
        pre = {(e.get('session'), e.get('call')) for e in values if e['kind'] == 'PreToolUse'}
        post = {(e.get('session'), e.get('call')) for e in values if e['kind'] == 'PostToolUse'}
        return {'observed': counts, 'unmatched_pre': len(pre - post), 'unmatched_post': len(post - pre),
                'pending': db.execute('SELECT count(*) FROM events WHERE sent=0').fetchone()[0],
                'unsent_dropped': meta_get(db, 'unsent_dropped', 0), 'out_of_scope': meta_get(db, 'out_of_scope', 0),
                'last_success': meta_get(db, 'last_success'), 'last_error': meta_get(db, 'last_error'),
                'limits': 'Observed local hooks only; hosted/specialized tools may be absent. Unmatched calls may still be running, cancelled, or outside retained history.'}


def status():
    cfg = config()
    beat = 0
    generation = None
    if (home() / 'events.sqlite').is_file():
        with database() as db:
            beat = meta_get(db, 'watch_heartbeat', 0)
            generation = meta_get(db, 'watch_generation')
    return {'enabled': bool(cfg.get('enabled')), 'repo': cfg.get('repo'), 'device': cfg.get('device'),
            'sync_worker_observed_recently': bool(cfg.get('enabled') and generation == cfg.get('generation') and time.time() - beat < 20),
            'configured_root': path_label(cfg['root'], ROOT) if cfg.get('root') else None,
            'hooks_installed': bool(cfg.get('hook_commands')), 'native_trust': 'not inspected; observed event counts are evidence of execution',
            **coverage()}


def watch():
    cfg = config()
    if not cfg.get('enabled'):
        return
    with open(home() / 'watch.lock', 'a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        while config().get('enabled') and config().get('generation') == cfg.get('generation'):
            with database() as db:
                meta_set(db, 'watch_heartbeat', time.time())
                meta_set(db, 'watch_generation', cfg.get('generation'))
            try:
                flush()
            except (OSError, sqlite3.Error, ValueError):
                pass
            time.sleep(2)


def start_worker():
    if not config().get('enabled'):
        return False
    with database() as db:
        if meta_get(db, 'watch_generation') == config().get('generation') and time.time() - meta_get(db, 'watch_heartbeat', 0) < 20:
            return True
    try:
        subprocess.Popen([sys.executable, str(Path(__file__).resolve()), 'watch'], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        return True  # requested, not proof of health; status reports the observed heartbeat
    except OSError:
        return False


def hook_definitions(command):
    hooks = {}
    for event in sorted(EVENTS):
        handlers = [{'type': 'command', 'command': command, 'timeout': 3, 'statusMessage': 'Kit support diagnostics'}]
        if event in {'SessionStart', 'PostToolUse', 'Stop'}:
            handlers.append({'type': 'command', 'command': command + ' --flush', 'async': True, 'timeout': 120})
        hooks[event] = [{'hooks': handlers}]
    return hooks


def install_hooks(remove=False):
    cfg = config()
    target = ROOT / '.codex' / 'hooks.json'
    existed = target.exists()
    data = read_json(target, None) if existed else {}
    if not isinstance(data, dict) or not isinstance(data.get('hooks', {}), dict):
        raise ValueError('Existing hooks.json is invalid; no changes made')
    if any(not isinstance(groups, list) or any(not isinstance(g, dict) or not isinstance(g.get('hooks'), list)
           or any(not isinstance(h, dict) for h in g['hooks']) for g in groups) for groups in data.get('hooks', {}).values()):
        raise ValueError('Existing hooks.json is invalid; no changes made')
    command = shlex.quote(sys.executable) + ' ' + shlex.quote(str(ROOT / 'hooks' / 'observe.py'))
    owned = set(cfg.get('hook_commands', [])) | {command, command + ' --flush'}
    if existed:
        backup = home() / ('hooks-backup-' + hashlib.sha256(target.read_bytes()).hexdigest()[:16] + '.json')
        backup.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not backup.exists():
            backup.write_bytes(target.read_bytes())
            backup.chmod(0o600)
    for event, groups in list(data.get('hooks', {}).items()):
        cleaned = []
        for group in groups:
            item = dict(group)
            item['hooks'] = [h for h in group.get('hooks', []) if h.get('command') not in owned]
            if item['hooks']:
                cleaned.append(item)
        if cleaned:
            data['hooks'][event] = cleaned
        else:
            data['hooks'].pop(event, None)
    if not remove:
        for event, groups in hook_definitions(command).items():
            data.setdefault('hooks', {}).setdefault(event, []).extend(groups)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name('hooks.' + uuid.uuid4().hex + '.tmp')
    temp.write_text(json.dumps(data, indent=2) + '\n')
    temp.replace(target)
    cfg['hook_commands'] = [] if remove else sorted(owned)
    save_config(cfg)
    return {'hooks_installed': not remove, 'native_review_required': not remove, 'path': '.codex/hooks.json'}


def remote(repo, device=None):
    check_repo(repo)
    if device:
        return remote_snapshot(repo, device)[0]
    refs = gh('GET', 'repos/' + repo + '/git/matching-refs/heads/support/')
    if not isinstance(refs, list):
        raise GitHubError('invalid_reference_list')
    return {'devices': [r['ref'].removeprefix('refs/heads/support/') for r in refs
                        if isinstance(r, dict) and re.fullmatch(r'refs/heads/support/[a-f0-9]{32}', str(r.get('ref', '')))]}


def rules_snapshot(cwd=None):
    from support_rules import inventory
    result = inventory(ROOT, cwd)
    scan = uuid.uuid4().hex
    sources = result['sources']
    for start in range(0, len(sources), 8):
        append('snapshot', {'provenance': {'rules': {
            'scan': scan, 'part': start // 8 + 1, 'parts': (len(sources) + 7) // 8,
            'launch_directory': result['launch_directory'], 'sources': sources[start:start + 8],
            'truncated': result['truncated'], 'evidence': result['evidence']}}})
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description='Opt-in kit diagnostics; GitHub data branches, never messages or remote shell.')
    sub = ap.add_subparsers(dest='action', required=True)
    sub.add_parser('status')
    en = sub.add_parser('enable'); en.add_argument('--repo', default=REPO); en.add_argument('--resume-queued', action='store_true')
    sub.add_parser('disable'); sub.add_parser('install-hooks'); sub.add_parser('uninstall-hooks')
    ins = sub.add_parser('inspect'); ins.add_argument('job', nargs='?')
    sync = sub.add_parser('sync'); sync.add_argument('--force', action='store_true')
    sub.add_parser('watch')
    sub.add_parser('doctor')
    rules = sub.add_parser('rules'); rules.add_argument('--cwd')
    cmp = sub.add_parser('compare'); cmp.add_argument('left'); cmp.add_argument('right')
    rem = sub.add_parser('remote'); rem.add_argument('device', nargs='?'); rem.add_argument('--repo', default=REPO)
    ex = sub.add_parser('export'); ex.add_argument('--limit', type=int, default=200)
    a = ap.parse_args(argv)
    try:
        if a.action == 'enable':
            check_repo(a.repo, write=True)
            old = config()
            if not old.get('enabled') and coverage()['pending'] and not a.resume_queued:
                raise ValueError('Retained records require enable --resume-queued; export them first if needed.')
            cfg = {'enabled': False, 'repo': a.repo, 'root': str(ROOT), 'device': old.get('device') or uuid.uuid4().hex,
                   'generation': uuid.uuid4().hex}
            save_config(cfg)
            try:
                result = install_hooks()
            except Exception:
                save_config(old)
                raise
            cfg = config(); cfg['enabled'] = True; save_config(cfg)
            append('snapshot', {'provenance': diagnostic_snapshot()}, cfg=config())
            rules_snapshot()
            result['sync_worker_start_requested'] = start_worker()
            result.update(status='enabled; review hooks in Codex, then run a normal kit task', device=cfg['device'],
                          destination='private GitHub support/' + cfg['device'],
                          retention='Old snapshots remain in Git history; disabling does not erase them.')
        elif a.action == 'disable':
            cfg = config(); cfg['enabled'] = False; cfg['generation'] = uuid.uuid4().hex; save_config(cfg)
            result = {'enabled': False, 'note': 'No new capture or uploads. An already accepted GitHub request may finish. Local queue retained; enable --resume-queued is required to resume it.'}
        elif a.action in {'install-hooks', 'uninstall-hooks'}:
            result = install_hooks(a.action == 'uninstall-hooks')
        elif a.action == 'inspect':
            result = provenance(a.job)
            append('snapshot', {'provenance': result})
        elif a.action == 'sync':
            result = flush(a.force)
        elif a.action == 'doctor':
            result = status()
            result['provenance'] = diagnostic_snapshot()
            append('snapshot', {'provenance': result['provenance']})
            result['provenance']['rules'] = rules_snapshot()
            result['note'] = 'CLI version is not proof of the desktop bundled runtime. Review hooks in the desktop app; no observed hooks means coverage is unverified.'
        elif a.action == 'rules':
            result = rules_snapshot(a.cwd)
        elif a.action == 'compare':
            from support_rules import compare
            left, right = read_json(a.left), read_json(a.right)
            if not isinstance(left, dict) or not isinstance(right, dict):
                raise ValueError('Both inputs must be JSON reports')
            result = compare(left, right)
        elif a.action == 'remote':
            result = remote(a.repo, a.device)
        elif a.action == 'watch':
            watch()
            result = {'status': 'disabled'}
        elif a.action == 'export':
            if not (home() / 'events.sqlite').is_file():
                result = {'events': []}
            else:
                with database() as db:
                    result = {'events': [json.loads(r[0]) for r in db.execute('SELECT body FROM events ORDER BY t DESC LIMIT ?', (min(1000, max(1, a.limit)),))]}
        else:
            result = status()
    except (ValueError, GitHubError, OSError, sqlite3.Error) as exc:
        # No raw subprocess output or event data in errors.
        print(json.dumps({'status': 'error', 'error': str(exc) if isinstance(exc, (GitHubError, ValueError)) else type(exc).__name__}))
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
