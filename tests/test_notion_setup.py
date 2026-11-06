"""One-time Content page setup plan: offline, no Notion calls."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'engine'))
import notion_index as ni

KIT = Path(__file__).resolve().parents[1]
HUB = {'workspace_id': 'ws-1', 'hub_id': 'hub-1'}


class SetupPlanTests(unittest.TestCase):
    def test_empty_page_creates_every_table(self):
        plan = ni.setup_plan(dict(HUB, databases=[]))
        self.assertFalse(plan['write_performed'])
        self.assertEqual([s['action'] for s in plan['steps']], ['create_database'] * 4)
        self.assertEqual({s['role'] for s in plan['steps']}, {'broll', 'pictures', 'graphics', 'styles'})
        for s in plan['steps']:
            self.assertEqual(s['parent_page_id'], 'hub-1')
            self.assertEqual(s['properties']['Name'], {'type': 'title'})
            self.assertEqual(s['properties']['Files & media'], {'type': 'files'})
        broll = next(s for s in plan['steps'] if s['role'] == 'broll')
        self.assertEqual(broll['properties']['Origin'], {'type': 'select', 'options': ['AI', 'Stock', 'Own']})

    def test_reuses_his_tables_and_adds_only_missing_fields(self):
        dbs = [{'title': 'B-roll clips', 'database_id': 'db-b', 'schema': {'Name': {'type': 'title'}}},
               {'title': 'Motion graphics database', 'database_id': 'db-g',
                'schema': {'Description of Graphic': {'type': 'title'}, 'File': {'type': 'files'},
                           'Tags': {'type': 'rich_text'}}}]
        steps = {s['role']: s for s in ni.setup_plan(dict(HUB, databases=dbs))['steps']}
        self.assertEqual(steps['broll']['action'], 'add_properties')
        self.assertEqual(steps['broll']['database_id'], 'db-b')
        self.assertEqual(set(steps['broll']['properties']), {'Files & media', 'Tags', 'Origin', 'Duration (s)'})
        # his graphics table already has a files field and a Tags field of another type: nothing changed
        self.assertEqual(steps['graphics']['action'], 'reuse')
        self.assertIn('Tags is rich_text', steps['graphics']['notes'][0])
        self.assertEqual(steps['pictures']['action'], 'create_database')
        self.assertEqual(steps['styles']['action'], 'create_database')

    def test_complete_page_needs_nothing(self):
        full = {'Name': {'type': 'title'}, 'Files & media': {'type': 'files'}, 'Tags': {'type': 'multi_select'},
                'Origin': {'type': 'select'}, 'Duration (s)': {'type': 'number'}}
        dbs = [{'title': t, 'database_id': t, 'schema': full} for t in ['B Roll', 'Pictures', 'Graphics', 'Styles']]
        self.assertEqual({s['action'] for s in ni.setup_plan(dict(HUB, databases=dbs))['steps']}, {'reuse'})

    def test_refuses_without_hub_or_with_two_lookalikes(self):
        with self.assertRaises(ValueError):
            ni.setup_plan({'databases': []})
        two = [{'title': 'Styles', 'schema': {}}, {'title': 'Style', 'schema': {}}]
        with self.assertRaises(ValueError):
            ni.setup_plan(dict(HUB, databases=two))

    def test_setup_then_detect_maps_styles_so_push_works(self):
        plan = ni.setup_plan(dict(HUB, databases=[]))
        roles = {s['role']: {'database_id': 'db-' + s['role'], 'data_source_id': 'ds-' + s['role'],
                             'schema': {k: {'type': v['type']} for k, v in s['properties'].items()}}
                 for s in plan['steps']}
        layout = ni.detect(dict(HUB, roles=roles))
        self.assertEqual(layout['roles']['styles']['files_property'], 'Files & media')
        with tempfile.TemporaryDirectory() as d:
            style = Path(d) / 'red' / 'style.json'
            style.parent.mkdir()
            style.write_text('{"caption": {"color": "white"}}')
            push = ni.push_style(layout, style, title='red')
        self.assertEqual(push['database_id'], 'db-styles')

    def test_cli(self):
        with tempfile.TemporaryDirectory() as d:
            hub = Path(d) / 'hub.json'
            hub.write_text(json.dumps(dict(HUB, databases=[])))
            out = subprocess.run([str(KIT / 'bin' / 'kit'), 'library', 'setup', '--input', str(hub),
                                  '--layout', str(Path(d) / 'layout.json'), '--index', str(Path(d) / 'index.json')],
                                 capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(json.loads(out.stdout)['command'], 'setup_content_hub')

    def test_pull_reads_attached_style_file(self):
        layout = ni.detect(dict(HUB, roles={'styles': {'database_id': 'db', 'schema': {'Name': {'type': 'title'}, 'Files & media': {'type': 'files'}}}}))
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 'matthew.style.json'
            f.write_text('{"highlight_color": "#dc143c", "font_size_frac": 0.093, "_about": "x"}')
            out = ni.import_style(layout, dict(HUB, title='matthew', body='', files=[{'name': f.name, 'path': str(f)}]), Path(d) / 'my-styles' / 'matthew')
            data = json.loads(Path(out['path']).read_text())
        self.assertEqual(data['highlight_color'], '#dc143c')
        self.assertNotIn('_about', data)

    def test_broll_only_when_style_turns_it_on(self):
        src = (KIT / 'engine' / 'kit.py').read_text()
        call = 'edl["broll"] = library.select_broll('
        self.assertIn(call, src)
        guard = src[src.index(call) - 200: src.index(call)]
        self.assertIn('(st.get("broll") or {}).get("auto")', guard)


if __name__ == '__main__':
    unittest.main()
