"""Support transport fixtures. No GitHub writes, real auth, hook trust or user configs."""
import base64
from concurrent.futures import ThreadPoolExecutor
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'engine'))
import support as s


class FakeGitHub:
    def __init__(self):
        self.private = True
        self.push = True
        self.created = False
        self.content = None
        self.sha = 'b' * 40
        self.calls = []
        self.fail = None
        self.conflict = False
        self.lose_response = False

    def __call__(self, method, endpoint, payload=None):
        self.calls.append((method, endpoint, payload))
        if self.fail:
            raise s.GitHubError(self.fail)
        base = 'repos/' + s.REPO
        if endpoint == base:
            return {'full_name': s.REPO, 'private': self.private, 'permissions': {'push': self.push}, 'default_branch': 'main'}
        if '/git/ref/heads/main' in endpoint:
            return {'object': {'sha': 'a' * 40}}
        if method == 'GET' and '/git/ref/heads/support/' in endpoint:
            if not self.created:
                raise s.GitHubError('http_404')
            return {'object': {'sha': 'a' * 40}}
        if method == 'POST' and endpoint.endswith('/git/refs'):
            assert payload['ref'].startswith('refs/heads/support/')
            self.created = True
            return {'ref': payload['ref']}
        if '/git/matching-refs/heads/support/' in endpoint:
            return [{'ref': 'refs/heads/support/' + 'd' * 32}, {'ref': 'refs/heads/main'}, {'ref': 'refs/heads/support/../../main'}]
        if '/contents/' in endpoint:
            if method == 'GET':
                assert '?ref=support%2F' in endpoint
                if self.content is None:
                    raise s.GitHubError('http_404')
                return {'type': 'file', 'path': s.DATA_FILE, 'encoding': 'base64', 'sha': self.sha,
                        'content': base64.b64encode(json.dumps(self.content).encode()).decode()}
            assert method == 'PUT' and endpoint == base + '/contents/' + s.DATA_FILE
            assert payload['branch'].startswith('support/')
            assert payload['message'].startswith('[skip ci]')
            if self.conflict:
                self.conflict = False
                raise s.GitHubError('http_409')
            self.content = json.loads(base64.b64decode(payload['content']))
            if self.lose_response:
                self.lose_response = False
                raise s.GitHubError('github_unavailable')
            return {'commit': {'sha': 'c' * 40}}
        raise AssertionError((method, endpoint))


class SupportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'kit'; self.root.mkdir()
        self.env = patch.dict(os.environ, {'KIT_SUPPORT_HOME': str(Path(self.tmp.name) / 'state')})
        self.env.start(); self.addCleanup(self.env.stop)
        self.root_patch = patch.object(s, 'ROOT', self.root); self.root_patch.start(); self.addCleanup(self.root_patch.stop)
        s.save_config({'enabled': True, 'root': str(self.root), 'repo': s.REPO, 'device': 'd' * 32, 'generation': 'test'})
        self.fake = FakeGitHub()

    def event(self, kind='PreToolUse', call='call-1', **extra):
        return {'hook_event_name': kind, 'session_id': 'session-1', 'turn_id': 'turn-1', 'tool_use_id': call,
                'tool_name': 'Bash', 'cwd': str(self.root), 'tool_input': {'command': 'bin/kit preview demo'}, **extra}

    def records(self):
        with s.database() as db:
            return [json.loads(r[0]) for r in db.execute('SELECT body FROM events')]

    def cli(self, args):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = s.main(args)
        return code, json.loads(stream.getvalue())

    def test_pre_post_dedup_and_correlation(self):
        s.observe(self.event()); s.observe(self.event())
        s.observe(self.event('PostToolUse', tool_response={'exit_code': 1, 'output': 'ValueError: PRIVATE TEXT'}))
        values = self.records()
        self.assertEqual(len(values), 2)
        self.assertEqual(values[0]['call'], values[1]['call'])
        self.assertEqual(values[1]['result'], {'exit_code': 1, 'status': 'failed', 'error_class': 'ValueError'})
        self.assertEqual(s.coverage()['unmatched_pre'], 0)
        self.assertNotIn('PRIVATE TEXT', json.dumps(values))

    def test_secret_and_content_canaries_never_retained(self):
        raw = self.event(tool_input={'command': 'TOKEN=CANARY_ENV curl -H "Authorization: Bearer CANARY_HEADER" https://u:CANARY_PASSWORD@example.com/?key=CANARY_QUERY; python3 -c "CANARY_CODE"; bin/kit preview demo'},
                         tool_response={'output': 'CANARY_OUTPUT sk-123456789012345678901234', 'secret': 'CANARY_EXTRA'},
                         prompt='CANARY_PROMPT', transcript_path='/private/CANARY_TRANSCRIPT')
        s.observe(raw)
        raw['hook_event_name'] = 'PostToolUse'; s.observe(raw)
        s.observe(self.event(call='mcp', tool_name='mcp__notion__fetch', tool_input={'url': 'CANARY_NOTION', 'headers': {'token': 'CANARY_TOKEN'}}))
        text = json.dumps(self.records())
        self.assertNotIn('CANARY', text)
        self.assertNotIn('sk-123', text)
        self.assertIn('curl', text)
        self.assertIn('preview', text)

    def test_scope_and_mid_session_enable(self):
        outside = str(Path(self.tmp.name) / 'unrelated')
        s.observe(self.event(cwd=outside))
        self.assertEqual(self.records(), [])
        s.observe(self.event())
        s.observe(self.event('PostToolUse', cwd=outside))
        self.assertEqual(len(self.records()), 2)
        self.assertEqual(s.coverage()['out_of_scope'], 1)

    def test_invalid_identity_does_not_join_unrelated_sessions(self):
        event = self.event(); event.pop('session_id')
        s.observe(event)
        self.assertEqual(self.records()[0]['kind'], 'gap')

    def test_concurrent_capture_and_bounded_queue_reports_loss(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda i: s.observe(self.event(call='c-' + str(i))), range(25)))
        self.assertEqual(len(self.records()), 25)
        with patch.object(s, 'MAX_EVENTS', 10):
            s.observe(self.event(call='new'))
        self.assertEqual(len(self.records()), 10)
        self.assertEqual(s.coverage()['unsent_dropped'], 16)

    def test_queue_to_github_and_remote_readback(self):
        s.observe(self.event()); s.observe(self.event('PostToolUse', tool_response={'exit_code': 0}))
        with patch.object(s, 'gh', self.fake):
            result = s.flush(force=True)
            read = s.remote(s.REPO, 'd' * 32)
            devices = s.remote(s.REPO)
        self.assertEqual(result['uploaded'], 2)
        self.assertEqual(len(read['events']), 2)
        self.assertEqual(devices['devices'], ['d' * 32])
        self.assertEqual(s.coverage()['pending'], 0)
        for method, endpoint, payload in self.fake.calls:
            if method == 'PUT':
                self.assertEqual(endpoint, 'repos/' + s.REPO + '/contents/' + s.DATA_FILE)
                self.assertNotEqual(payload['branch'], 'main')

    def test_enable_hook_subprocess_sync_remote_cli_end_to_end(self):
        self.cli(['disable'])
        with patch.object(s, 'gh', self.fake), patch.object(s, 'start_worker', return_value=True):
            code, result = self.cli(['enable'])
        self.assertEqual(code, 0)
        observer = Path(__file__).resolve().parents[1] / 'hooks' / 'observe.py'
        for kind in ('PreToolUse', 'PostToolUse'):
            result = subprocess.run([sys.executable, str(observer)], input=json.dumps(self.event(kind)), text=True, capture_output=True)
            self.assertEqual((result.returncode, result.stdout, result.stderr), (0, '', ''))
        with patch.object(s, 'gh', self.fake):
            self.assertEqual(s.flush(force=True)['status'], 'synced')
            code, result = self.cli(['remote', 'd' * 32])
        self.assertEqual(code, 0)
        self.assertEqual({r['kind'] for r in result['events']}, {'snapshot', 'PreToolUse', 'PostToolUse'})

    def test_public_or_read_only_repo_stops_before_write(self):
        s.observe(self.event())
        for private, push in [(False, True), (True, False)]:
            self.fake.private, self.fake.push = private, push
            with patch.object(s, 'gh', self.fake):
                result = s.flush(force=True)
            self.assertEqual(result['status'], 'queued')
            self.assertEqual(s.coverage()['pending'], 1)
            self.assertFalse(any(method in {'PUT', 'POST'} for method, _, _ in self.fake.calls))

    def test_foreign_or_malformed_remote_file_is_not_overwritten(self):
        s.observe(self.event())
        self.fake.created = True
        self.fake.content = {'schema': 1, 'device': 'd' * 32, 'events': [{'id': 'e' * 32, 'raw_prompt': 'CANARY_RAW'}]}
        with patch.object(s, 'gh', self.fake):
            self.assertEqual(s.flush(force=True)['error'], 'invalid_support_snapshot')
        self.assertEqual(s.coverage()['pending'], 1)
        self.assertFalse(any(method == 'PUT' for method, _, _ in self.fake.calls))

    def test_generation_change_before_write_stops_old_sync(self):
        s.observe(self.event())
        fake = self.fake
        def change(method, endpoint, payload=None):
            result = fake(method, endpoint, payload)
            if method == 'GET' and endpoint.endswith('/git/ref/heads/main'):
                cfg = s.config(); cfg['generation'] = 'new'; cfg['enabled'] = False; s.save_config(cfg)
            return result
        with patch.object(s, 'gh', change):
            self.assertEqual(s.flush(force=True)['status'], 'queued')
        self.assertFalse(any(method in {'POST', 'PUT'} for method, _, _ in fake.calls))

    def test_rate_limit_offline_and_conflict_keep_queue(self):
        s.observe(self.event())
        for error in ['http_429', 'http_403', 'github_unavailable']:
            self.fake.fail = error
            with patch.object(s, 'gh', self.fake):
                self.assertEqual(s.flush(force=True)['error'], error)
            self.assertEqual(s.coverage()['pending'], 1)
        self.fake.fail = None; self.fake.conflict = True
        with patch.object(s, 'gh', self.fake):
            self.assertEqual(s.flush(force=True)['status'], 'synced')

    def test_uncertain_delivery_is_read_back_not_duplicated(self):
        s.observe(self.event())
        self.fake.lose_response = True
        with patch.object(s, 'gh', self.fake):
            self.assertEqual(s.flush(force=True)['status'], 'queued')
            self.assertEqual(s.coverage()['pending'], 1)
            self.assertEqual(s.flush(force=True)['status'], 'synced')
        self.assertEqual(sum(method == 'PUT' for method, _, _ in self.fake.calls), 1)

    def test_throttle_and_disable_no_more_network(self):
        s.observe(self.event())
        self.fake.fail = 'http_429'
        with patch.object(s, 'gh', self.fake):
            s.flush()
            count = len(self.fake.calls)
            self.assertEqual(s.flush()['status'], 'throttled')
            self.assertEqual(len(self.fake.calls), count)
            self.cli(['disable'])
            s.observe(self.event(call='after-disable'))
            self.assertEqual(s.flush(force=True)['status'], 'disabled')
            self.assertEqual(len(self.fake.calls), count)
        self.assertEqual(len(self.records()), 1)

    def test_reenable_requires_explicit_resume_and_preserves_foreign_hooks(self):
        target = self.root / '.codex' / 'hooks.json'; target.parent.mkdir()
        foreign = {'type': 'command', 'command': 'echo foreign', 'timeout': 1}
        target.write_text(json.dumps({'description': 'mine', 'hooks': {'Stop': [{'hooks': [foreign]}]}}))
        s.install_hooks(); first = target.read_text(); s.install_hooks()
        self.assertEqual(target.read_text(), first)
        s.install_hooks(remove=True)
        self.assertEqual(json.loads(target.read_text())['hooks']['Stop'][0]['hooks'], [foreign])
        s.observe(self.event()); self.cli(['disable'])
        with patch.object(s, 'gh', self.fake), patch.object(s, 'start_worker', return_value=True):
            code, _ = self.cli(['enable'])
            self.assertEqual(code, 1)
            self.assertFalse(s.config()['enabled'])
            code, result = self.cli(['enable', '--resume-queued'])
        self.assertEqual(code, 0)
        self.assertTrue(result['native_review_required'])

    def test_malformed_existing_hooks_fail_without_enabling(self):
        self.cli(['disable'])
        target = self.root / '.codex' / 'hooks.json'; target.parent.mkdir()
        target.write_text('{"hooks":{"Stop":7}}')
        with patch.object(s, 'gh', self.fake):
            code, _ = self.cli(['enable'])
        self.assertEqual(code, 1)
        self.assertFalse(s.config()['enabled'])
        self.assertEqual(target.read_text(), '{"hooks":{"Stop":7}}')

    def test_exact_provenance_saved_style_inline_override_and_stale_block(self):
        def write(rel, data):
            p = self.root / rel; p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(data) if isinstance(data, dict) else data)
            return p
        write('styles/matthew/style.json', {'font_size_frac': .09})
        saved = write('my-styles/matthew/style.json', {'font_size_frac': .05})
        write('.work/demo/edl.json', {'style_name': 'matthew', 'style': {'font_size_frac': .08}, 'blocks': [{'name': 'chat'}]})
        write('my-styles/matthew/templates/chat/chat.html', 'new graphic')
        write('.work/_studio/demo/compositions/chat.html', 'old graphic')
        html = write('.work/_studio/demo/index.html', 'edited')
        write('.work/_studio/demo/.kit-generated', 'wrong hash')
        before = html.read_bytes()
        info = s.provenance('demo', self.root)
        self.assertEqual(info['style_layer'], 'saved')
        self.assertEqual(info['style_source']['sha256'], s.digest(saved))
        self.assertEqual(info['effective_settings']['font_size_frac'], .08)
        self.assertTrue(info['hand_edited'])
        self.assertTrue(info['blocks'][0]['different_bytes'])
        self.assertEqual(html.read_bytes(), before)
        self.assertNotIn(str(Path.home()), json.dumps(info))

    def test_gh_uses_fixed_host_stdin_and_does_not_leak_error(self):
        with patch.object(s.shutil, 'which', return_value='/fake/gh'), patch.object(s.subprocess, 'run') as run:
            run.return_value = subprocess.CompletedProcess([], 0, '{}', '')
            s.gh('PUT', 'repos/' + s.REPO + '/contents/' + s.DATA_FILE, {'branch': 'support/' + 'd' * 32, 'content': 'CANARY_PAYLOAD'})
            args, kwargs = run.call_args
            self.assertIn('--hostname', args[0]); self.assertIn('github.com', args[0])
            self.assertNotIn('CANARY_PAYLOAD', str(args))
            self.assertIn('CANARY_PAYLOAD', kwargs['input'])
            run.return_value = subprocess.CompletedProcess([], 1, '', 'CANARY_PASSWORD (HTTP 403)')
            with self.assertRaisesRegex(s.GitHubError, '^http_403$'):
                s.gh('GET', 'repos/' + s.REPO)

    def test_hook_script_no_stdout_on_malformed_or_disabled_payload(self):
        self.cli(['disable'])
        observer = Path(__file__).resolve().parents[1] / 'hooks' / 'observe.py'
        for payload in ['not JSON', json.dumps(self.event())]:
            result = subprocess.run([sys.executable, str(observer)], input=payload, text=True, capture_output=True)
            self.assertEqual((result.returncode, result.stdout, result.stderr), (0, '', ''))

    def test_bundled_hook_contract_and_observed_health(self):
        file = Path(__file__).resolve().parents[1] / 'hooks' / 'hooks.json'
        hooks = json.loads(file.read_text())['hooks']
        for event in s.EVENTS:
            local = hooks[event][0]['hooks'][0]
            self.assertEqual(local['type'], 'command')
            self.assertNotIn('async', local)
            self.assertLessEqual(local['timeout'], 3)
            self.assertIn('${PLUGIN_ROOT}', local['command'])
        self.assertFalse(s.status()['sync_worker_observed_recently'])
        with s.database() as db:
            s.meta_set(db, 'watch_heartbeat', s.time.time())
            s.meta_set(db, 'watch_generation', s.config()['generation'])
        self.assertTrue(s.status()['sync_worker_observed_recently'])

    def test_unknown_repository_and_branch_never_reach_api(self):
        with patch.object(s, 'gh') as gh:
            with self.assertRaises(s.GitHubError): s.check_repo('attacker/public')
            with self.assertRaises(s.GitHubError): s.remote_snapshot(s.REPO, '../../main')
            gh.assert_not_called()
        with patch.object(s.subprocess, 'run') as run:
            with self.assertRaises(s.GitHubError):
                s.gh('PUT', 'repos/' + s.REPO + '/contents/plugin.json', {'branch': 'main'})
            run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
