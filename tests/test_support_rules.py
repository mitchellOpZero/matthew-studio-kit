import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'engine'))
from support_rules import inventory, compare
import support


class RulesTests(unittest.TestCase):
    def test_layers_duplicates_and_no_contents(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            root = home / 'kit'; cwd = root / 'nested'
            codex = home / '.codex'
            files = {'kit/AGENTS.md': 'PRIVATE_RULE', 'kit/nested/AGENTS.override.md': 'PRIVATE_OVERRIDE',
                     'kit/nested/AGENTS.md': 'PRIVATE_IGNORED', '.codex/AGENTS.md': 'PRIVATE_GLOBAL',
                     '.codex/config.toml': 'api_key="PRIVATE_SECRET"',
                     '.agents/skills/one/SKILL.md': '---\nname: same\n---\nPRIVATE_SKILL',
                     '.codex/plugins/cache/vendor/kit/1/skills/one/SKILL.md': '---\nname: same\n---\nPRIVATE_OTHER'}
            for path, content in files.items():
                p = home / path; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(content)
            report = inventory(root, cwd, home, codex)
            self.assertNotIn('PRIVATE', json.dumps(report))
            self.assertNotIn(str(home), json.dumps(report))
            rows = {r['source']: r for r in report['sources']}
            self.assertTrue(rows['project/nested/AGENTS.override.md']['default_discovery_candidate'])
            self.assertFalse(rows['project/nested/AGENTS.md']['default_discovery_candidate'])
            self.assertTrue(report['duplicate_skills'][0]['different_content'])
            (root / 'AGENTS.md').write_text('CHANGED')
            second = inventory(root, cwd, home, codex)
            self.assertEqual(compare(report, second)['different_content'], ['project/AGENTS.md'])

    def test_missing_source_and_wrong_input(self):
        left = {'sources': [{'source': 'global/AGENTS.md', 'sha256': 'a'}]}
        right = {'provenance': {'rules': {'sources': []}}}
        self.assertEqual(compare(left, right)['only_left'], ['global/AGENTS.md'])
        with self.assertRaises(ValueError):
            compare({}, {})

    def test_malformed_existing_hooks_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); target = root / '.codex' / 'hooks.json'
            target.parent.mkdir(); target.write_text('{invalid')
            with patch.object(support, 'ROOT', root), patch.object(support, 'config', return_value={}):
                with self.assertRaises(ValueError):
                    support.install_hooks()
            self.assertEqual(target.read_text(), '{invalid')

    def test_rule_file_references_are_observed_without_values(self):
        result = support.command_summary('cat AGENTS.override.md .codex/config.toml .codex/rules/kit.rules')
        self.assertEqual(len(result['files']), 3)

