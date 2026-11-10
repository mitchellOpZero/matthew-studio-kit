"""B-roll titles and tags for Notion: labels, evidence rules and the guarded plan. Offline; no Notion call."""
import copy
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'engine'))
import notion_index as ni
import notion_sort as ns

NOW = datetime(2026, 11, 10, 20, 0, tzinfo=timezone.utc)
WS, HUB, DB, DS = 'ws-1', 'hub-1', 'db-broll', 'ds-broll'
PID = 'a' * 32
PID2 = 'b' * 32
EDITED = '2026-11-01T00:00:00Z'


def woman(**extra):
    return {'descriptor': 'woman', 'hair_color': 'brown', 'hair_length': 'long', **extra}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.layout = {'workspace_id': WS, 'hub_id': HUB, 'asset_upload': 'authorized_hub', 'notion_writeback': False,
                       'roles': {'broll': {'database_id': DB, 'data_source_id': DS, 'title_property': 'Name',
                                           'files_property': 'Files & media', 'tags_property': 'Tags'},
                                 'graphics': {'database_id': 'db-g', 'title_property': 'Name', 'files_property': 'File'}}}
        self.index = ni.empty_index()
        self.snapshot = {'workspace_id': WS, 'hub_id': HUB, 'fetched_at': (NOW - timedelta(minutes=5)).isoformat(), 'complete': True,
                         'database': {'database_id': DB, 'data_source_id': DS, 'parent_id': HUB,
                                      'schema': {'Name': {'type': 'title'}, 'Files & media': {'type': 'files'},
                                                 'Tags': {'type': 'multi_select', 'options': [{'name': 'favorite'}, {'name': 'Cafe'}]},
                                                 'Original title': {'type': 'rich_text'}, 'Origin': {'type': 'select'}}},
                         'pages': []}
        self.key = self.add_file(PID, 'IMG_1234.mp4', title='IMG_1234')
        self.record = self.review(self.key)
        self.page = self.add_page(PID, 'IMG_1234', ['IMG_1234.mp4'], tags=['favorite'])

    def add_file(self, pid, name, title, role='broll', body=''):
        path = self.root / (pid[:4] + '-' + name)
        path.write_bytes(('bytes of ' + pid + name).encode())
        frame = self.root / (pid[:4] + '-' + name + '.frame.png')
        frame.write_bytes(('frame of ' + pid + name).encode())
        sha = ni.sha256(path)
        key = pid + ':' + sha
        self.index['entries'][key] = {
            'page_id': pid, 'sha256': sha, 'path': str(path), 'role': role, 'kind': 'broll', 'stale': False, 'downloaded': True,
            'title': title, 'file_name': name, 'file_names': [name], 'body': body, 'tags': [], 'explicit_tags': [],
            'origin': 'stock', 'media': {'aspect': 'vertical', 'duration': 5}, 'ref': 'file://' + name, 'last_edited_time': EDITED,
            'sort_frames': [{'path': str(frame), 'sha256': ni.sha256(frame), 'time': 2.5}]}
        row = self.index['rows'].setdefault(pid, {'signature': {'role': role, 'title': title, 'last_edited_time': None, 'files': []}, 'stale': False})
        row['signature']['files'].append({'name': name, 'ref': 'file://' + name})
        return key

    def make_record(self, key, **changes):
        entry = self.index['entries'][key]
        record = {'entry_key': key, 'subject': ['coffee', 'indoor'], 'setting': 'cafe',
                  'people': {'count': '1', 'subjects': [woman()]}, 'action': 'walking', 'mood': 'calm',
                  'shot_type': 'medium', 'time_of_day': 'day',
                  'origin': {'value': 'unknown', 'confidence': .2, 'evidence': [{'source': 'vision', 'detail': 'Pixels do not show where it came from.'}]},
                  'description': 'A woman carries a cup across a cafe.', 'confidence': .9, 'sorted_at': '2026-11-10T19:00:00Z',
                  'file_sha256': entry['sha256'], 'frame_hashes': [f['sha256'] for f in entry['sort_frames']],
                  'sorter': 'codex-vision', 'ignore_body': False}
        record.update(changes)
        return record

    def review(self, key, **changes):
        record = self.make_record(key, **changes)
        ns.apply(self.index, [record])
        return record

    def add_page(self, pid, title, names, tags=(), original='', parent=DB):
        page = {'id': pid, 'parent_database_id': parent, 'title': title, 'last_edited_time': EDITED,
                'properties': {'Tags': list(tags), 'Original title': original},
                'files': [{'name': n, 'ref': 'file://' + n} for n in names]}
        self.snapshot['pages'].append(page)
        return page

    def plan(self, **kw):
        return ns.writeback_plan(self.index, self.layout, self.snapshot, now=NOW, **kw)

    def perform(self, plan, refresh=True):
        """What the Notion connection would do with the plan, done to the fixture snapshot.

        A write moves the page's edit time; refresh=True also does what the index refresh that follows would.
        """
        pages = {ni.row_id(p): p for p in self.snapshot['pages']}
        for patch_ in plan['patches']:
            page = pages[patch_['page_id']]
            for prop, value in patch_['set'].items():
                if prop == 'Name':
                    page['title'] = value
                else:
                    page['properties'][prop] = value
            self.clock = getattr(self, 'clock', 0) + 1
            page['last_edited_time'] = f'2026-11-02T00:{self.clock:02d}:00Z'
            if refresh:
                self.sync(patch_['page_id'])

    def sync(self, pid):
        page = next(p for p in self.snapshot['pages'] if ni.row_id(p) == pid)
        for entry in self.index['entries'].values():
            if entry['page_id'] == pid:
                entry['last_edited_time'] = page['last_edited_time']


class LabelTests(Base):
    def test_title_format_is_consistent(self):
        self.assertEqual(ns.kit_title(self.record), 'Woman - walking - cafe - brown hair')
        two = self.make_record(self.key, people={'count': '2', 'subjects': [woman(), {'descriptor': 'man', 'hair_color': 'black'}]},
                               action='talking', setting='bar')
        self.assertEqual(ns.kit_title(two), 'Woman and man - talking - bar')
        group = self.make_record(self.key, people={'count': '3+', 'subjects': [woman()]}, action='dancing', setting='club')
        self.assertEqual(ns.kit_title(group), 'Group - dancing - club')
        screen = self.make_record(self.key, subject=['phone', 'app'], people={'count': '0'}, action='none', setting='dating-app', shot_type='close-up')
        self.assertEqual(ns.kit_title(screen), 'Phone - dating app - close-up')
        bald = self.make_record(self.key, people={'count': '1', 'subjects': [{'descriptor': 'man', 'hair_length': 'bald'}]}, action='sitting', setting='unknown')
        self.assertEqual(ns.kit_title(bald), 'Man - sitting - bald')

    def test_unknown_is_left_out_not_guessed(self):
        vague = self.make_record(self.key, people={'count': '1', 'subjects': [{'descriptor': 'unknown'}]}, action='unknown', setting='unknown')
        self.assertIsNone(ns.kit_title(vague))
        self.assertNotIn('woman', ns.kit_tags(vague))
        self.assertFalse([t for t in ns.kit_tags(vague) if 'hair' in t or 'unknown' in t])
        back = self.make_record(self.key, people={'count': '1', 'subjects': [{'descriptor': 'unknown', 'hair_length': 'covered'}]})
        self.assertEqual(ns.kit_title(back), 'Person - walking - cafe')

    def test_tags_never_move_a_trait_to_another_person(self):
        self.assertEqual(ns.kit_tags(self.record)[:3], ['woman', 'brown hair', 'long hair'])
        two = self.make_record(self.key, people={'count': '2', 'subjects': [woman(), {'descriptor': 'man', 'hair_color': 'black'}]})
        tags = ns.kit_tags(two)
        self.assertIn('woman - brown hair', tags)
        self.assertIn('man - black hair', tags)
        self.assertNotIn('brown hair', tags)
        self.assertNotIn('black hair', tags)
        same = self.make_record(self.key, people={'count': '2', 'subjects': [woman(), woman(hair_color='blonde')]})
        self.assertFalse([t for t in ns.kit_tags(same) if 'hair' in t])
        group = self.make_record(self.key, people={'count': '3+', 'subjects': [woman(), {'descriptor': 'man'}]})
        self.assertFalse([t for t in ns.kit_tags(group) if 'hair' in t])
        self.assertIn('group', ns.kit_tags(group))

    def test_schema_has_no_age_and_no_free_text_person_fields(self):
        for people in [{'count': '1', 'subjects': [woman(age='20s')]}, {'count': '1', 'subjects': [woman(name='Jane')]},
                       {'count': '1', 'subjects': [{'descriptor': 'girl'}]}, {'count': '1', 'subjects': [woman(hair_color='auburn-ish')]},
                       {'count': '1', 'subjects': [woman(), woman()]}, {'count': '0', 'subjects': [woman()]},
                       {'count': '1', 'subjects': [woman(hair_length='bald')]}]:
            with self.assertRaises(ValueError, msg=str(people)):
                ns.apply(self.index, [self.make_record(self.key, people=people)])
        with self.assertRaises(ValueError):
            ns.apply(self.index, [self.make_record(self.key, age='young')])

    def test_broll_needs_descriptors_but_other_roles_are_unchanged(self):
        legacy = self.make_record(self.key)
        legacy.pop('action')
        with self.assertRaises(ValueError):
            ns.apply(self.index, [legacy])
        no_people = self.make_record(self.key, people={'count': '1'})
        with self.assertRaises(ValueError):
            ns.apply(self.index, [no_people])
        gkey = self.add_file(PID2, 'card.png', 'card', role='graphics')
        graphic = self.make_record(gkey, people={'count': '0'}, shot_type='graphic')
        graphic.pop('action')
        ns.apply(self.index, [graphic])
        self.assertEqual(ns.plan(self.index)['to_sort'], [])

    def test_search_finds_the_new_descriptors(self):
        hit = ni.find(self.index, 'brown hair woman walking')[0]
        self.assertEqual(hit['page_id'], PID)
        self.assertEqual(hit['kit_title'], 'Woman - walking - cafe - brown hair')
        self.assertTrue(any(r.startswith('ai.labels=') for r in hit['match_reasons']))
        self.assertTrue(any(r.startswith('ai.action=') for r in hit['match_reasons']))
        self.assertEqual(ni.find(self.index, 'blonde'), [])

    def test_everyday_words_find_the_fixed_labels(self):
        for query in ['girl', 'women', 'brunette', 'brunette girl walking']:
            self.assertEqual([h['page_id'] for h in ni.find(self.index, query)], [PID], query)
        for query in ['blond', 'guy', 'redhead']:
            self.assertEqual(ni.find(self.index, query), [], query)
        self.review(self.key, people={'count': '1', 'subjects': [{'descriptor': 'man', 'hair_color': 'blonde'}]},
                    description='Someone carries a cup across a cafe.')
        for query in ['blond', 'blonde guy', 'men']:
            self.assertEqual([h['page_id'] for h in ni.find(self.index, query)], [PID], query)
        self.assertEqual(ni.find(self.index, 'girl'), [])
        # an alias only widens a search: it adds no label, and there is still no age field to fill
        self.assertNotIn('girl', ns.kit_tags(self.record))
        self.assertNotIn('brunette', ns.kit_tags(self.record))
        ni.set_override(self.index, PID, {'tags_remove': ['walking']})
        self.assertEqual(ni.find(self.index, 'walking'), [])


class EthnicityTests(Base):
    def eth(self, value='Latina', source='source-metadata', quote='Model release: Latina woman, 20s', **extra):
        return {'value': value, 'evidence': {'source': source, 'quote': quote}, **extra}

    def test_vision_name_and_model_guesses_are_not_evidence(self):
        for source in ['vision', 'name', 'body', 'model', 'title']:
            with self.assertRaises(ValueError, msg=source):
                ns.apply(self.index, [self.make_record(self.key, ethnicity=self.eth(source=source))])
        with self.assertRaises(ValueError):       # no evidence at all
            ns.apply(self.index, [self.make_record(self.key, ethnicity={'value': 'Latina'})])
        self.assertNotIn('ethnicity', self.index['entries'][self.key]['ai_sort'])

    def test_source_metadata_must_be_quoted_from_the_page_not_the_title(self):
        entry = self.index['entries'][self.key]
        entry['title'] = 'Latina woman cafe'
        entry['file_names'] = ['latina-woman.mp4']
        with self.assertRaises(ValueError):       # only the title and file name say it
            ns.apply(self.index, [self.make_record(self.key, ethnicity=self.eth(quote='Latina woman'))])
        entry['body'] = 'Mixkit clip 4410. Model release: Latina woman, 20s.'
        with self.assertRaises(ValueError):       # the quote does not state the value
            ns.apply(self.index, [self.make_record(self.key, ethnicity=self.eth(value='Mexican'))])
        with self.assertRaises(ValueError):       # an --ignore-body review may not lean on the body
            ns.apply(self.index, [self.make_record(self.key, ethnicity=self.eth(), ignore_body=True)])
        ns.apply(self.index, [self.make_record(self.key, ethnicity=self.eth())])
        self.assertIn('latina', ns.kit_tags(self.index['entries'][self.key]['ai_sort']))
        self.assertEqual(ns.kit_title(self.index['entries'][self.key]['ai_sort']), 'Woman - walking - cafe - brown hair - Latina')

    def test_evidence_is_checked_again_when_planning_the_write(self):
        entry = self.index['entries'][self.key]
        entry['body'] = self.page['body'] = 'Model release: Latina woman, 20s.'
        ns.apply(self.index, [self.make_record(self.key, ethnicity=self.eth())])
        self.assertIn('latina', self.plan()['patches'][0]['set']['Tags'])
        # the page text changed in Notion; the index still remembers the old body, and the edit time did not move
        self.page['body'] = 'Metadata corrected; no ethnicity supplied.'
        self.assertIn('Latina', self.index['entries'][self.key]['body'])
        plan = self.plan()
        self.assertEqual(plan['patches'], [])
        self.assertIn('review_no_longer_valid', ' '.join(plan['blocked'][0]['reasons']))
        self.assertNotIn('latina', json.dumps(plan['patches']))
        del self.page['body']                                        # no current body supplied: cannot be confirmed either
        plan = self.plan()
        self.assertEqual(plan['patches'], [])
        self.assertIn('snapshot_needs_page_body_for_source_evidence', ' '.join(plan['blocked'][0]['reasons']))
        ns.apply(self.index, [self.make_record(self.key)])          # a new review without it clears the block
        self.assertNotIn('latina', self.plan()['patches'][0]['set']['Tags'])

    def test_a_tag_the_kit_added_is_never_its_own_evidence(self):
        self.index['entries'][self.key]['body'] = self.page['body'] = 'Model release: Latina woman, 20s.'
        ns.apply(self.index, [self.make_record(self.key, ethnicity=self.eth())])
        self.perform(self.plan())
        self.assertEqual(self.plan()['status'], 'nothing_to_do')              # read-back: confirmed, body still says it
        self.assertIn('latina', self.index['writeback_proposals'][PID]['owned'])
        # the source text is corrected; the only place left that says it is the tag the kit wrote
        self.page['body'] = 'Metadata corrected; no ethnicity supplied.'
        entry = self.index['entries'][self.key]
        entry['body'] = self.page['body']
        entry['explicit_tags'] = list(self.page['properties']['Tags'])
        plan = self.plan()
        self.assertEqual(plan['patches'], [])
        self.assertIn('review_no_longer_valid', ' '.join(plan['blocked'][0]['reasons']))
        with self.assertRaises(ValueError):                                   # nor may a new review cite that tag
            ns.apply(self.index, [self.make_record(self.key, ethnicity=self.eth(quote='latina'))])
        ns.apply(self.index, [self.make_record(self.key)])
        patch_ = self.plan()['patches'][0]
        self.assertEqual(patch_['removes_tags'], ['latina'])
        self.assertEqual(patch_['set']['Name'], 'Woman - walking - cafe - brown hair')

    def test_a_tag_he_supplied_is_evidence_and_stays_evidence(self):
        self.page['properties']['Tags'] = ['favorite', 'Latina model']
        self.index['entries'][self.key]['explicit_tags'] = ['favorite', 'Latina model']
        self.page['body'] = ''
        ns.apply(self.index, [self.make_record(self.key, ethnicity=self.eth(quote='Latina model'))])
        plan = self.plan()
        self.assertIn('latina', plan['patches'][0]['adds_tags'])
        self.perform(plan)
        self.assertEqual(self.plan()['status'], 'nothing_to_do')
        self.page['properties']['Tags'].remove('Latina model')                # he takes his tag back: the support is gone
        self.assertIn('review_no_longer_valid', ' '.join(self.plan()['blocked'][0]['reasons']))

    def test_a_record_edited_around_the_checks_is_not_trusted(self):
        good = copy.deepcopy(self.index['entries'][self.key]['ai_sort'])
        for damage in [lambda r: r.__setitem__('ethnicity', {'value': 'Latina', 'evidence': {'source': 'vision', 'quote': 'looks Latina'}}),
                       lambda r: r.__setitem__('ethnicity', {'value': 'Latina', 'evidence': {'source': 'user-statement', 'quote': 'no such words'}}),
                       lambda r: r['people']['subjects'][0].__setitem__('age', '20s'),
                       lambda r: r.__setitem__('action', 'flirting'),
                       lambda r: r.pop('people'),
                       lambda r: r.__setitem__('people', 'x'),
                       lambda r: r.__setitem__('confidence', 'high'),
                       lambda r: r.__setitem__('frame_hashes', None),
                       lambda r: r.pop('file_sha256'),
                       lambda r: r.__setitem__('ethnicity', 'Latina'),
                       lambda r: r.__setitem__('ethnicity', {'value': 'Latina', 'evidence': 'vision'}),
                       lambda r: r['people'].__setitem__('subjects', 'x'),
                       lambda r: r.__setitem__('source_credit', {'name': 'Jane Doe', 'quote': 'Jane Doe'})]:
            record = copy.deepcopy(good)
            damage(record)
            self.index['entries'][self.key]['ai_sort'] = record
            plan = self.plan()
            self.assertEqual(plan['patches'], [])
            self.assertIn('review_no_longer_valid', ' '.join(plan['blocked'][0]['reasons']))
        self.index['entries'][self.key]['ai_sort'] = 'reviewed'               # not even a record
        self.assertIn('review_no_longer_valid', ' '.join(self.plan()['blocked'][0]['reasons']))

    def test_title_carries_evidenced_ethnicity_for_one_person_only(self):
        self.index['entries'][self.key]['body'] = self.page['body'] = 'Model release: Latina woman, 20s'
        one = self.make_record(self.key, ethnicity=self.eth())
        ns.apply(self.index, [one])
        self.assertEqual(self.plan()['patches'][0]['set']['Name'], 'Woman - walking - cafe - brown hair - Latina')
        self.assertEqual(ns.kit_title(self.make_record(self.key)), 'Woman - walking - cafe - brown hair')      # none given, none shown
        two = self.make_record(self.key, people={'count': '2', 'subjects': [woman(), {'descriptor': 'man'}]}, ethnicity=self.eth(applies_to=0))
        ns.apply(self.index, [two])
        self.assertEqual(ns.kit_title(self.index['entries'][self.key]['ai_sort']), 'Woman and man - walking - cafe')

    def test_user_statement_must_name_it_in_words(self):
        with self.assertRaises(ValueError):
            ns.apply(self.index, [self.make_record(self.key, ethnicity=self.eth(source='user-statement', quote='tag her how she looks'))])
        ns.apply(self.index, [self.make_record(self.key, ethnicity=self.eth(source='user-statement', quote='He said: tag this one Latina'))])
        self.page['properties']['Tags'] = []
        plan = self.plan()
        self.assertIn('latina', plan['patches'][0]['adds_tags'])
        self.assertTrue(any('user-statement' in n for n in plan['patches'][0]['notes']))

    def test_several_people_need_attribution(self):
        people = {'count': '2', 'subjects': [woman(), {'descriptor': 'man'}]}
        self.index['entries'][self.key]['body'] = 'Model release: Latina woman, 20s'
        with self.assertRaises(ValueError):
            ns.apply(self.index, [self.make_record(self.key, people=people, ethnicity=self.eth())])
        with self.assertRaises(ValueError):
            ns.apply(self.index, [self.make_record(self.key, people=people, ethnicity=self.eth(applies_to=2))])
        ns.apply(self.index, [self.make_record(self.key, people=people, ethnicity=self.eth(applies_to=0))])
        tags = ns.kit_tags(self.index['entries'][self.key]['ai_sort'])
        self.assertIn('woman - latina', tags)
        self.assertNotIn('latina', tags)
        twins = {'count': '2', 'subjects': [woman(), woman()]}
        ns.apply(self.index, [self.make_record(self.key, people=twins, ethnicity=self.eth(applies_to=1))])
        self.assertFalse([t for t in ns.kit_tags(self.index['entries'][self.key]['ai_sort']) if 'latina' in t])
        with self.assertRaises(ValueError):       # nobody on screen
            ns.apply(self.index, [self.make_record(self.key, people={'count': '0'}, ethnicity=self.eth())])

    def test_source_credit_must_be_given_not_invented(self):
        with self.assertRaises(ValueError):
            ns.apply(self.index, [self.make_record(self.key, source_credit={'name': 'Mixkit', 'quote': 'from Mixkit'})])
        self.index['entries'][self.key]['body'] = 'Downloaded from Mixkit, free licence page.'
        with self.assertRaises(ValueError):
            ns.apply(self.index, [self.make_record(self.key, source_credit={'name': 'Pexels', 'quote': 'from Mixkit'})])
        ns.apply(self.index, [self.make_record(self.key, source_credit={'name': 'Mixkit', 'quote': 'Downloaded from Mixkit'})])
        self.assertIn('mixkit', ns.kit_tags(self.index['entries'][self.key]['ai_sort']))


class WritebackTests(Base):
    def test_plan_sets_title_keeps_original_and_his_tags(self):
        self.page['properties']['Tags'] = ['favorite', 'cafe']
        before = copy.deepcopy(self.snapshot)
        plan = self.plan()
        self.assertEqual(self.snapshot, before)
        self.assertEqual(plan['status'], 'proposed')
        self.assertFalse(plan['write_performed'])
        self.assertTrue(plan['notion_writeback'])
        self.assertEqual((plan['workspace_id'], plan['hub_id'], plan['database_id']), (WS, HUB, DB))
        self.assertIn('PROPOSED ONLY', plan['instruction'])
        patch_ = plan['patches'][0]
        self.assertEqual(set(patch_['set']), {'Name', 'Tags', 'Original title'})
        self.assertEqual(patch_['set']['Name'], 'Woman - walking - cafe - brown hair')
        self.assertEqual(patch_['set']['Original title'], 'IMG_1234')
        self.assertEqual(patch_['set']['Tags'][:2], ['favorite', 'cafe'])
        self.assertEqual(patch_['set']['Tags'].count('cafe') + patch_['set']['Tags'].count('Cafe'), 1)
        for tag in ['woman', 'brown hair', 'long hair', 'walking', 'medium', 'coffee']:
            self.assertIn(tag, patch_['set']['Tags'])
        self.assertEqual(patch_['expected']['title'], 'IMG_1234')
        self.assertEqual(patch_['expected']['Tags'], ['favorite', 'cafe'])
        self.assertEqual(patch_['expected']['files'], [{'name': 'IMG_1234.mp4', 'ref': 'file://IMG_1234.mp4'}])
        self.assertNotIn('favorite', plan['options_to_create'])
        self.assertIn('woman', plan['options_to_create'])
        self.assertEqual(self.index['writeback_proposals'][PID]['status'], 'proposed')
        self.assertEqual(self.index['entries'][self.key]['title'], 'IMG_1234')      # local index is not rewritten

    def test_existing_option_spelling_is_reused(self):
        patch_ = self.plan()['patches'][0]
        self.assertIn('Cafe', patch_['set']['Tags'])
        self.assertNotIn('cafe', patch_['set']['Tags'])
        self.assertNotIn('cafe', self.plan()['options_to_create'])

    def test_only_title_tags_and_original_title_are_ever_named(self):
        for extra in [{}, {'tags_add': ['hero']}, {'title': 'My cafe walk'}]:
            ni.set_override(self.index, PID, extra) if extra else None
            for patch_ in self.plan()['patches']:
                self.assertLessEqual(set(patch_['set']), {'Name', 'Tags', 'Original title'})

    def test_repeat_after_the_write_is_a_no_op(self):
        first = self.plan()
        self.perform(first)
        again = self.plan()
        self.assertEqual(again['status'], 'nothing_to_do')
        self.assertEqual(again['patches'], [])
        self.assertFalse(again['notion_writeback'])
        self.assertFalse(again['write_performed'])
        self.assertEqual([u['page_id'] for u in again['unchanged']], [PID])
        self.assertEqual(self.index['writeback_proposals'][PID]['status'], 'matches_snapshot')
        self.assertEqual(self.page['properties']['Original title'], 'IMG_1234')

    def test_missing_fields_give_a_bounded_setup_plan(self):
        del self.snapshot['database']['schema']['Original title']
        plan = self.plan()
        self.assertEqual(plan['status'], 'setup_required')
        self.assertEqual(plan['patches'], [])
        self.assertFalse(plan['notion_writeback'])
        self.assertEqual(plan['setup'], {'action': 'add_properties', 'database_id': DB, 'data_source_id': DS,
                                         'properties': {'Original title': {'type': 'rich_text'}}})
        del self.snapshot['database']['schema']['Tags']
        self.assertEqual(set(self.plan()['setup']['properties']), {'Tags', 'Original title'})
        self.assertNotIn('writeback_proposals', self.index)

    def test_wrong_field_types_are_never_written_or_retyped(self):
        schema = self.snapshot['database']['schema']
        for name, kind in [('Tags', 'select'), ('Tags', 'relation'), ('Original title', 'multi_select')]:
            saved = copy.deepcopy(schema[name])
            schema[name] = {'type': kind}
            plan = self.plan()
            self.assertEqual(plan['status'], 'schema_conflict', name)
            self.assertEqual(plan['patches'], [])
            self.assertNotIn('setup', plan)
            schema[name] = saved

    def test_invalid_schema_refused(self):
        schema = self.snapshot['database']['schema']
        saved = copy.deepcopy(schema)
        for change in [lambda: schema['Tags'].pop('options'), lambda: schema.pop('Name'),
                       lambda: schema.__setitem__('Name', {'type': 'rich_text'}), lambda: schema.__setitem__('tags', {'type': 'multi_select', 'options': []})]:
            change()
            with self.assertRaises(ValueError):
                self.plan()
            schema.clear()
            schema.update(copy.deepcopy(saved))
        self.snapshot['database'].pop('schema')
        with self.assertRaises(ValueError):
            self.plan()

    def test_other_workspace_hub_or_database_refused(self):
        for path, value in [(('workspace_id',), 'ws-other'), (('hub_id',), 'hub-other'), (('workspace_id',), None),
                            (('database', 'database_id'), 'db-g'), (('database', 'data_source_id'), 'ds-other'),
                            (('database', 'parent_id'), 'hub-other'), (('database', 'parent_id'), None)]:
            snap = copy.deepcopy(self.snapshot)
            target = snap
            for part in path[:-1]:
                target = target[part]
            target[path[-1]] = value
            with self.assertRaises(ValueError, msg=str(path)):
                ns.writeback_plan(self.index, self.layout, snap, now=NOW)
        for layout in [{'roles': self.layout['roles']}, self.layout | {'asset_upload': 'off'},
                       self.layout | {'roles': {'graphics': self.layout['roles']['graphics']}}]:
            with self.assertRaises(ValueError):
                ns.writeback_plan(self.index, layout, self.snapshot, now=NOW)
        self.assertNotIn('writeback_proposals', self.index)

    def test_snapshot_must_be_fresh(self):
        for stamp in [(NOW - timedelta(minutes=45)).isoformat(), (NOW + timedelta(minutes=10)).isoformat(), '2026-11-10T19:55:00', 'today', None]:
            self.snapshot['fetched_at'] = stamp
            with self.assertRaises(ValueError, msg=str(stamp)):
                self.plan()

    def test_page_membership_and_role_are_checked_per_page(self):
        self.page['parent_database_id'] = 'db-posts'
        self.assertIn('not_in_broll_database', self.plan()['blocked'][0]['reasons'])
        del self.page['parent_database_id']
        plan = self.plan()
        self.assertIn('membership_unconfirmed', plan['blocked'][0]['reasons'])
        self.assertEqual(plan['patches'], [])
        self.page['parent_data_source_id'] = DS
        self.assertEqual(len(self.plan()['patches']), 1)
        gkey = self.add_file(PID2, 'card.mp4', 'card', role='graphics')
        self.review(gkey)
        self.add_page(PID2, 'card', ['card.mp4'])
        plan = self.plan()
        self.assertEqual([b['page_id'] for b in plan['blocked']], [PID2])
        self.assertIn('not_a_broll_row', plan['blocked'][0]['reasons'])
        self.add_page('c' * 32, 'stranger', ['x.mp4'])
        self.assertIn('not_in_index_refresh_first', self.plan()['blocked'][-1]['reasons'])

    def test_ambiguous_targets_refused(self):
        with self.assertRaises(ValueError):
            self.plan(page_ids=['d' * 32])
        self.snapshot['pages'].append(copy.deepcopy(self.page))
        with self.assertRaises(ValueError):
            self.plan()

    def test_page_filter_limits_the_plan(self):
        key2 = self.add_file(PID2, 'b.mp4', 'b')
        self.review(key2, setting='gym', action='working-out')
        self.add_page(PID2, 'b', ['b.mp4'])
        plan = self.plan(page_ids=['bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'])
        self.assertEqual([p['page_id'] for p in plan['patches']], [PID2])
        self.assertEqual(plan['patches'][0]['set']['Name'], 'Woman - working out - gym - brown hair')

    def test_file_identity_must_match_the_index(self):
        self.page['files'][0]['ref'] = 'file://replaced'
        self.assertIn('files_differ_from_index_refresh_first', self.plan()['blocked'][0]['reasons'])
        self.page['files'] = self.page['files'] + [{'name': 'extra.mp4', 'ref': 'file://extra.mp4'}]
        self.assertEqual(self.plan()['patches'], [])
        del self.page['files']
        self.assertEqual(self.plan()['patches'], [])

    def test_stale_or_missing_review_evidence_blocks(self):
        def reasons():
            plan = self.plan()
            self.assertEqual(plan['patches'], [])
            return ' '.join(plan['blocked'][0]['reasons'])
        entry = self.index['entries'][self.key]
        frame = Path(entry['sort_frames'][0]['path'])
        saved = frame.read_bytes()
        frame.unlink()
        self.assertIn('frames_missing', reasons())
        frame.write_bytes(b'other pixels')
        self.assertIn('frames_changed', reasons())
        frame.write_bytes(saved)
        self.assertEqual(len(self.plan()['patches']), 1)
        hashes = entry['sort_frames'][0]['sha256']
        entry['sort_frames'][0]['sha256'] = '0' * 64
        self.assertIn('frames_do_not_match_review', reasons())
        entry['sort_frames'][0]['sha256'] = hashes
        source = Path(entry['path'])
        original = source.read_bytes()
        source.write_bytes(b'replaced clip')
        self.assertIn('local_file_missing_or_changed', reasons())
        source.write_bytes(original)
        entry['ai_sort']['file_sha256'] = '1' * 64
        self.assertIn('review_is_for_other_bytes', reasons())

    def test_low_confidence_unreviewed_and_legacy_records_block(self):
        entry = self.index['entries'][self.key]
        entry['ai_sort']['confidence'] = .5
        self.assertIn('low_confidence', ' '.join(self.plan()['blocked'][0]['reasons']))
        entry['ai_sort']['confidence'] = .9
        entry['ai_sort'].pop('action')
        self.assertIn('needs_descriptive_review', ' '.join(self.plan()['blocked'][0]['reasons']))
        self.assertEqual(ns.plan(self.index)['to_sort'], [self.key])
        entry.pop('ai_sort')
        self.assertIn('not_reviewed', ' '.join(self.plan()['blocked'][0]['reasons']))
        entry.update(path=None, sha256=None, downloaded=False)
        self.assertIn('not_downloaded_so_not_reviewed', ' '.join(self.plan()['blocked'][0]['reasons']))
        self.assertEqual(self.plan()['patches'], [])

    def test_page_edited_since_the_index_blocks(self):
        self.page['last_edited_time'] = '2026-11-03T09:00:00Z'
        plan = self.plan()
        self.assertEqual(plan['patches'], [])
        self.assertEqual(plan['blocked'][0]['reasons'], ['page_edited_since_index_refresh_first'])
        self.page['last_edited_time'] = '2026-11-01T01:00:00+01:00'           # the same instant, written another way
        self.assertEqual(len(self.plan()['patches']), 1)
        del self.page['last_edited_time']
        self.assertEqual(self.plan()['blocked'][0]['reasons'], ['edit_time_missing_from_snapshot'])
        self.page['last_edited_time'] = EDITED
        self.index['entries'][self.key]['last_edited_time'] = None            # index never recorded one: cannot tell
        self.assertEqual(self.plan()['blocked'][0]['reasons'], ['page_edited_since_index_refresh_first'])

    def test_read_back_needs_the_refresh_that_follows_a_write(self):
        self.perform(self.plan(), refresh=False)
        stale = self.plan()
        self.assertEqual((stale['patches'], stale['unchanged']), ([], []))
        self.assertEqual(stale['blocked'][0]['reasons'], ['page_edited_since_index_refresh_first'])
        self.sync(PID)
        self.assertEqual([u['page_id'] for u in self.plan()['unchanged']], [PID])

    def test_unreadable_current_values_block_instead_of_clobbering(self):
        del self.page['properties']['Tags']
        self.assertIn('current_tags_unreadable', self.plan()['blocked'][0]['reasons'])
        self.page['properties']['Tags'] = 'favorite'
        self.assertIn('current_tags_unreadable', self.plan()['blocked'][0]['reasons'])
        self.page['properties']['Tags'] = []
        del self.page['properties']['Original title']
        self.assertIn('original_title_unreadable', self.plan()['blocked'][0]['reasons'])

    def test_multi_file_page_that_agrees_is_aggregated(self):
        key2 = self.add_file(PID, 'IMG_1235.mp4', 'IMG_1234')
        self.page['files'].append({'name': 'IMG_1235.mp4', 'ref': 'file://IMG_1235.mp4'})
        plan = self.plan()
        self.assertEqual(plan['patches'], [])
        self.assertIn('IMG_1235.mp4: not_reviewed', plan['blocked'][0]['reasons'])
        self.review(key2, shot_type='wide', mood='warm')
        patch_ = self.plan()['patches'][0]
        self.assertEqual(patch_['set']['Name'], 'Woman - walking - cafe - brown hair')
        self.assertIn('wide', patch_['set']['Tags'])
        self.assertIn('medium', patch_['set']['Tags'])
        self.assertEqual(len(patch_['file_sha256']), 2)

    def test_multi_file_conflict_does_not_mix_people(self):
        key2 = self.add_file(PID, 'IMG_1235.mp4', 'IMG_1234')
        self.page['files'].append({'name': 'IMG_1235.mp4', 'ref': 'file://IMG_1235.mp4'})
        self.review(key2, people={'count': '1', 'subjects': [{'descriptor': 'man', 'hair_color': 'black'}]}, action='texting')
        patch_ = self.plan()['patches'][0]
        self.assertNotIn('Name', patch_['set'])
        self.assertNotIn('Original title', patch_['set'])
        for tag in ['woman', 'man', 'brown hair', 'black hair', 'walking', 'texting']:
            self.assertNotIn(tag, patch_['set']['Tags'])
        self.assertIn('Cafe', patch_['set']['Tags'])
        self.assertTrue(any(n.startswith('multi_file_conflict') for n in patch_['notes']))
        ni.set_override(self.index, PID, {'title': 'Cafe couple, two angles'})
        self.assertEqual(self.plan()['patches'][0]['set']['Name'], 'Cafe couple, two angles')

    def test_manual_corrections_win(self):
        ni.set_override(self.index, PID, {'tags_add': ['hero shot'], 'tags_remove': ['Walking', 'calm'], 'title': 'Morning cafe walk'})
        patch_ = self.plan()['patches'][0]
        self.assertEqual(patch_['set']['Name'], 'Morning cafe walk')
        self.assertIn('hero shot', patch_['set']['Tags'])
        self.assertNotIn('walking', patch_['set']['Tags'])
        self.assertNotIn('calm', patch_['set']['Tags'])
        self.assertIn('favorite', patch_['set']['Tags'])            # tags_remove never removes what is already on his page
        ni.set_override(self.index, PID, {'exclude': True})
        plan = self.plan()
        self.assertEqual(plan['patches'], [])
        self.assertEqual(plan['skipped'], [{'page_id': PID, 'reason': 'excluded_by_override'}])
        with self.assertRaises(ValueError):
            ni.set_override(self.index, PID, {'title': '  '})

    def test_a_title_he_edited_after_the_kit_is_left_alone(self):
        self.perform(self.plan())
        self.page['title'] = 'My favourite opener clip'
        plan = self.plan()
        self.assertEqual(plan['patches'], [])
        self.assertTrue(any('title_edited_in_notion' in n for n in plan['unchanged'][0]['notes']))
        self.assertEqual(self.page['properties']['Original title'], 'IMG_1234')

    def test_a_new_review_updates_the_kits_own_title_but_not_the_original(self):
        self.perform(self.plan())
        self.review(self.key, action='sitting')
        patch_ = self.plan()['patches'][0]
        self.assertEqual(patch_['set']['Name'], 'Woman - sitting - cafe - brown hair')
        self.assertNotIn('Original title', patch_['set'])
        self.assertEqual(patch_['adds_tags'], ['sitting'])
        self.assertEqual(patch_['removes_tags'], ['walking'])         # the kit's own confirmed tag, now wrong
        self.assertNotIn('walking', patch_['set']['Tags'])
        self.assertEqual(patch_['set']['Tags'][:2], ['favorite', 'woman'])
        self.assertIn('Cafe', patch_['set']['Tags'])

    def test_corrected_review_replaces_the_kits_own_tags_and_keeps_his(self):
        for text in [False, True]:
            with self.subTest(text_field=text):
                self.setUp()
                if text:
                    self.snapshot['database']['schema']['Tags'] = {'type': 'rich_text'}
                    self.page['properties']['Tags'] = 'favorite, date night'
                else:
                    self.page['properties']['Tags'] = ['favorite', 'date night']
                self.perform(self.plan())
                self.review(self.key, people={'count': '1', 'subjects': [woman(hair_color='blonde')]})
                plan = self.plan()
                patch_ = plan['patches'][0]
                value = patch_['set']['Tags']
                tags = [t.strip() for t in value.split(',')] if text else value
                self.assertEqual(patch_['set']['Name'], 'Woman - walking - cafe - blonde hair')
                self.assertNotIn('brown hair', tags)
                self.assertIn('blonde hair', tags)
                self.assertEqual(tags[:2], ['favorite', 'date night'])
                self.assertEqual(patch_['removes_tags'], ['brown hair'])
                self.assertEqual(plan['needs_his_correction'], [])
                self.perform(plan)
                self.assertEqual(self.plan()['status'], 'nothing_to_do')
                self.review(self.key)                                  # back to brown: a tag the kit removed itself may return
                self.assertEqual(self.plan()['patches'][0]['adds_tags'], ['brown hair'])

    def test_an_unconfirmed_plan_owns_nothing(self):
        self.page['properties']['Tags'] = ['favorite', 'brown hair']       # his own tag, there before the kit
        self.plan()                                                        # proposed, never applied
        self.review(self.key, people={'count': '1', 'subjects': [woman(hair_color='blonde')]})
        plan = self.plan()
        patch_ = plan['patches'][0]
        self.assertEqual(patch_['removes_tags'], [])
        self.assertIn('brown hair', patch_['set']['Tags'])
        self.assertIn('blonde hair', patch_['set']['Tags'])
        self.assertTrue(any(n.startswith('needs_his_correction') and 'brown hair' in n for n in patch_['notes']))
        self.assertEqual([x['page_id'] for x in plan['needs_his_correction']], [PID])
        self.perform(plan)
        after = self.plan()                                                # still says so after the write; never silently "done"
        self.assertEqual(after['patches'], [])
        self.assertEqual([x['page_id'] for x in after['needs_his_correction']], [PID])
        self.assertIn('brown hair', self.page['properties']['Tags'])

    def test_a_kit_tag_he_removed_in_notion_stays_removed(self):
        self.perform(self.plan())
        self.plan()                                                        # this snapshot confirms the write
        self.page['properties']['Tags'].remove('calm')
        plan = self.plan()
        self.assertEqual(plan['patches'], [])
        self.assertTrue(any(n.startswith('removed_in_notion') for n in plan['unchanged'][0]['notes']))
        self.assertEqual(self.plan()['patches'], [])                       # and it stays that way
        ni.set_override(self.index, PID, {'tags_add': ['calm']})
        self.assertEqual(self.plan()['patches'][0]['adds_tags'], ['calm'])

    def test_duplicate_titles_and_coverage_are_reported(self):
        key2 = self.add_file(PID2, 'b.mp4', 'b')
        self.review(key2)
        self.add_page(PID2, 'b', ['b.mp4'])
        self.add_file('e' * 32, 'c.mp4', 'c')
        plan = self.plan()
        self.assertEqual(plan['duplicate_titles'], {'Woman - walking - cafe - brown hair': [PID, PID2]})
        self.assertEqual(plan['coverage']['indexed_pages_not_in_snapshot'], ['e' * 32])
        self.assertEqual(plan['coverage']['to_change'], 2)
        self.assertTrue(plan['coverage']['snapshot_complete'])

    def test_text_tags_field_is_appended_not_replaced(self):
        self.snapshot['database']['schema']['Tags'] = {'type': 'rich_text'}
        self.page['properties']['Tags'] = 'favorite, Cafe'
        plan = self.plan()
        text = plan['patches'][0]['set']['Tags']
        self.assertTrue(text.startswith('favorite, Cafe, woman, brown hair'))
        self.assertEqual(text.lower().count('cafe'), 1)
        self.assertEqual(plan['options_to_create'], [])
        self.page['properties']['Tags'] = text
        self.page['title'] = plan['patches'][0]['set']['Name']
        self.page['properties']['Original title'] = 'IMG_1234'
        self.assertEqual(self.plan()['patches'], [])


class UnchangedBehaviorTests(Base):
    def test_no_snapshot_means_no_patches(self):
        for phrase in [None, ns.OPT_IN]:
            result = ns.writeback(self.index, phrase, PID)
            self.assertEqual(result['patches'], [])
            self.assertFalse(result['notion_writeback'])
            self.assertFalse(result['write_performed'])
        self.assertFalse(ni.detect({'workspace_id': WS, 'hub_id': HUB, 'roles': {}})['notion_writeback'])

    def test_upload_plan_claims_no_descriptive_labels(self):
        plan = ni.upload_plan(self.layout, role='broll', title='gym clip', local_file=self.index['entries'][self.key]['path'])
        self.assertFalse(plan['descriptive_labels'])
        self.assertEqual(plan['properties'], {'Name': 'gym clip'})
        self.assertFalse(plan['write_performed'])
        # adding B-roll is not finished by the create: reviewed title and tags are part of the same job
        self.assertTrue(plan['completion_required'])
        self.assertTrue(plan['title_is_provisional'])
        steps = ' '.join(plan['required_steps'])
        for words in ['look at every frame', 'sort writeback', 'do not ask again', 'only when the page is listed under unchanged']:
            self.assertIn(words, steps)
        picture = self.root / 'p.png'
        picture.write_bytes(b'png')
        other = ni.upload_plan(self.layout | {'roles': {'pictures': {'database_id': 'db-p', 'title_property': 'Name', 'files_property': 'Files'}}},
                               role='pictures', title='shot', local_file=picture)
        self.assertFalse(other['completion_required'])
        self.assertEqual(other['required_steps'], [])

    def test_plan_approval_is_his_request_but_setup_still_needs_his_ok(self):
        plan = self.plan()
        self.assertEqual(plan['approval'], 'covered_by_his_request_to_tag_or_add_broll')
        self.assertIn('do not ask again', plan['instruction'])
        self.assertNotIn('wait for his OK', plan['instruction'])
        del self.snapshot['database']['schema']['Original title']
        setup = self.plan()
        self.assertEqual(setup['approval'], 'needs_his_ok')
        self.assertIn('wait for his OK', setup['instruction'])

    def _listed_only(self):
        layout = {'roles': {'broll': {'data_source_id': 'ds', 'title_property': 'Name', 'files_property': 'Files & media'}}}
        row = {'id': 'page-gym', 'role': 'broll', 'title': 'IMG_9', 'body': '', 'last_edited_time': 'v1',
               'files': [{'name': 'ropes.mp4', 'ref': 'file://ropes'}]}
        idx = ni.empty_index()
        ni.refresh(idx, layout, {'complete_roles': ['broll'], 'rows': [row]}, [row], self.root)
        return layout, row, idx

    def test_refresh_stays_download_free_and_sort_plan_lists_what_to_download(self):
        layout, row, idx = self._listed_only()
        self.assertEqual(ni.plan(idx, {'complete_roles': ['broll'], 'rows': [row]})['fetch'], [])    # second refresh does not crash
        again = ni.refresh(idx, layout, {'complete_roles': ['broll'], 'rows': [row]}, [], self.root)
        self.assertEqual(again['broll_labels_pending']['count'], 1)                                  # surfaced, not downloaded
        self.assertEqual(again['broll_labels_pending']['pages'], ['page-gym'])
        self.assertFalse(next(iter(idx['entries'].values()))['downloaded'])
        self.assertEqual(ni.broll_pending(self.index), {'count': 0, 'pages': []})                    # the reviewed fixture clip
        plan = ns.plan(idx, batch=1)
        self.assertEqual(plan['to_sort'], [])
        self.assertEqual([d['page_id'] for d in plan['to_download']], ['page-gym'])
        self.assertEqual(plan['download_batch'][0]['ref'], 'file://ropes')
        self.assertEqual(plan['coverage'], {'reviewed': 0, 'downloaded_needs_review': 0, 'not_downloaded': 1})
        self.assertEqual(ns.frames(idx, self.root / 'frames'), [])
        record = self.make_record(self.key)
        record['entry_key'] = plan['to_download'][0]['entry_key']
        with self.assertRaises(ValueError):       # a file that was never downloaded cannot be labelled
            ns.apply(idx, [record])

    def test_review_survives_the_refresh_that_follows_a_title_change(self):
        layout, row, idx = self._listed_only()
        clip = self.root / 'ropes.mp4'
        clip.write_bytes(b'clip')
        with patch.object(ni, 'media_info', return_value={'width': 720, 'height': 1280, 'duration': 6.5, 'aspect': 'vertical'}), \
             patch.object(ni, 'make_local_poster', return_value=str(clip)):
            ni.attach(idx, 'page-gym', clip, self.root)
        key = 'page-gym:' + ni.sha256(clip)
        idx['entries'][key]['ai_sort'] = {'file_sha256': ni.sha256(clip), 'ignore_body': False}
        renamed = dict(row, title='Woman - working out - gym', last_edited_time='v2', tags=['woman', 'gym'])
        ni.refresh(idx, layout, {'complete_roles': ['broll'], 'rows': [renamed]}, [renamed], self.root)
        live = {k: e for k, e in idx['entries'].items() if not e['stale']}
        self.assertEqual(list(live), [key])
        self.assertEqual(live[key]['title'], 'Woman - working out - gym')
        self.assertEqual(live[key]['explicit_tags'], ['woman', 'gym'])
        self.assertIn('ai_sort', live[key])
        self.assertTrue(live[key]['downloaded'])
        replaced = dict(renamed, last_edited_time='v3', files=[{'name': 'ropes.mp4', 'ref': 'file://new-upload'}])
        ni.refresh(idx, layout, {'complete_roles': ['broll'], 'rows': [replaced]}, [replaced], self.root)
        self.assertTrue(idx['entries'][key]['stale'])                 # new attachment: the old review does not carry over

    def test_attach_refuses_to_guess_between_files(self):
        layout = {'roles': {'broll': {'title_property': 'Name', 'files_property': 'Files & media'}}}
        row = {'id': 'page-two', 'role': 'broll', 'title': 'two', 'files': [{'name': 'a.mp4', 'ref': 'r-a'}, {'name': 'b.mp4', 'ref': 'r-b'}]}
        idx = ni.empty_index()
        ni.refresh(idx, layout, {'rows': [row]}, [row], self.root)
        other = self.root / 'download.mp4'
        other.write_bytes(b'x')
        with self.assertRaises(ValueError):
            ni.attach(idx, 'page-two', other, self.root)

    def test_cli_plans_offline_and_reports_nothing_as_written(self):
        layout, index, snap = self.root / 'layout.json', self.root / 'index.json', self.root / 'snapshot.json'
        ni.save_json(layout, self.layout)
        ni.save_json(index, self.index)
        self.snapshot['fetched_at'] = datetime.now(timezone.utc).isoformat()
        ni.save_json(snap, self.snapshot)
        kit = [str(ROOT / 'bin' / 'kit'), 'library', 'sort', 'writeback', '--layout', str(layout), '--index', str(index)]
        bare = subprocess.run(kit, capture_output=True, text=True)
        self.assertEqual(bare.returncode, 0, bare.stderr)
        self.assertEqual(json.loads(bare.stdout)['patches'], [])
        out = subprocess.run(kit + ['--input', str(snap), '--page-id', PID], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        plan = json.loads(out.stdout)
        self.assertEqual(plan['status'], 'proposed')
        self.assertFalse(plan['write_performed'])
        self.assertEqual(plan['patches'][0]['set']['Name'], 'Woman - walking - cafe - brown hair')
        self.assertEqual(json.loads(index.read_text())['writeback_proposals'][PID]['status'], 'proposed')
        self.snapshot['hub_id'] = 'hub-other'
        ni.save_json(snap, self.snapshot)
        refused = subprocess.run(kit + ['--input', str(snap)], capture_output=True, text=True)
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn('refusing writeback', refused.stdout + refused.stderr)
        listing = subprocess.run([str(ROOT / 'bin' / 'kit'), 'library', 'sort', 'plan', '--index', str(index), '--batch', '5'], capture_output=True, text=True)
        self.assertEqual(json.loads(listing.stdout)['skipped'], [self.key])


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'needs ffmpeg')
class EndToEndCliTests(unittest.TestCase):
    """The real commands in order on a generated clip: list, attach, frames, apply, plan, refresh, plan again."""
    def test_list_review_plan_and_repeat(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            clip = root / 'IMG_7.mp4'
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc=duration=3:size=320x568:rate=10',
                            '-pix_fmt', 'yuv420p', str(clip)], check=True)
            paths = ['--layout', str(root / 'layout.json'), '--index', str(root / 'index.json')]

            def kit(*args, data=None):
                if data is not None:
                    ni.save_json(root / 'in.json', data)
                    args += ('--input', str(root / 'in.json'))
                out = subprocess.run([str(ROOT / 'bin' / 'kit'), 'library', *args, *paths], capture_output=True, text=True)
                self.assertEqual(out.returncode, 0, out.stderr + out.stdout)
                return json.loads(out.stdout)

            schema = {'Name': {'type': 'title'}, 'Files & media': {'type': 'files'}, 'Tags': {'type': 'multi_select'}}
            kit('detect', data={'workspace_id': WS, 'hub_id': HUB, 'roles': {'broll': {'database_id': DB, 'data_source_id': DS, 'schema': schema}}})
            row = {'id': PID, 'role': 'broll', 'title': 'IMG_7', 'body': '', 'last_edited_time': 'v1', 'files': [{'name': 'IMG_7.mp4', 'ref': 'file://x'}]}
            refresh = {'inventory': {'complete_roles': ['broll'], 'rows': [row]}, 'pages': [row]}
            kit('index', data=refresh)
            self.assertEqual(kit('sort', 'plan')['coverage']['not_downloaded'], 1)
            self.assertEqual(kit('sort', 'frames', '--frames-dir', str(root / 'frames')), [])      # nothing downloaded, nothing to look at
            kit('attach', PID, str(clip))
            manifest = kit('sort', 'frames', '--frames-dir', str(root / 'frames'))[0]
            self.assertEqual(len(manifest['frames']), 3)
            record = {'entry_key': manifest['entry_key'], 'subject': ['text', 'graphic'], 'setting': 'unknown', 'people': {'count': '0'},
                      'action': 'none', 'mood': 'neutral', 'shot_type': 'graphic', 'time_of_day': 'unknown',
                      'origin': {'value': 'unknown', 'confidence': .1, 'evidence': [{'source': 'vision', 'detail': 'Generated test pattern.'}]},
                      'description': 'Colour bars test pattern.', 'confidence': .95, 'sorted_at': '2026-11-10T20:00:00Z',
                      'file_sha256': manifest['file_sha256'], 'frame_hashes': [f['sha256'] for f in manifest['frames']],
                      'sorter': 'codex-vision', 'ignore_body': False}
            kit('sort', 'apply', data=[record])
            snap = {'workspace_id': WS, 'hub_id': HUB, 'fetched_at': datetime.now(timezone.utc).isoformat(), 'complete': True,
                    'database': {'database_id': DB, 'data_source_id': DS, 'parent_id': HUB,
                                 'schema': {'Name': {'type': 'title'}, 'Tags': {'type': 'multi_select', 'options': []}}},
                    'pages': [{'id': PID, 'parent_database_id': DB, 'title': 'IMG_7', 'last_edited_time': 'v1',
                               'properties': {'Tags': ['mine'], 'Original title': ''}, 'files': row['files']}]}
            self.assertEqual(kit('sort', 'writeback', data=snap)['status'], 'setup_required')
            snap['database']['schema']['Original title'] = {'type': 'rich_text'}
            plan = kit('sort', 'writeback', data=snap)
            self.assertFalse(plan['write_performed'])
            self.assertEqual(plan['patches'][0]['set'], {'Name': 'Text - graphic', 'Original title': 'IMG_7',
                                                         'Tags': ['mine', 'no people', 'graphic', 'text']})
            self.assertEqual(plan['options_to_create'], ['no people', 'graphic', 'text'])
            # the write happens in Notion; the next refresh sees the new tags, and the review must survive it
            row2 = dict(row, title='Text - graphic', tags=['mine', 'no people', 'graphic', 'text'], last_edited_time='v2')
            kit('index', data={'inventory': {'complete_roles': ['broll'], 'rows': [row2]}, 'pages': [row2]})
            self.assertEqual(kit('sort', 'plan')['coverage'], {'reviewed': 1, 'downloaded_needs_review': 0, 'not_downloaded': 0})
            snap['pages'][0].update(title='Text - graphic', last_edited_time='v2', properties={'Tags': row2['tags'], 'Original title': 'IMG_7'})
            again = kit('sort', 'writeback', data=snap)
            self.assertEqual((again['status'], again['patches']), ('nothing_to_do', []))
            hit = kit('find', 'text', 'graphic', '--kind', 'broll')[0]
            self.assertTrue(hit['downloaded'])


class DocsTests(unittest.TestCase):
    def test_docs_agree_with_the_engine(self):
        docs = (ROOT / 'docs' / 'NOTION-MCP.md').read_text()
        sort = (ROOT / 'skills' / 'sort-my-notion' / 'SKILL.md').read_text()
        library = (ROOT / 'skills' / 'library' / 'SKILL.md').read_text()
        for text in (docs, sort, library):
            self.assertNotIn('always returns an empty patch list', text)
            self.assertNotIn('Visual tags stay on this Mac', text)
            self.assertIn('sort writeback --input', text)
            self.assertIn('Original title', text)
        for text in (docs, sort):
            self.assertIn('Woman - walking - cafe - brown hair', text)
            self.assertIn('never from appearance', text)
            self.assertIn('user-statement', text)
            self.assertIn('source-metadata', text)
        self.assertIn('Never identify people', sort)
        self.assertIn(f'{ns.SNAPSHOT_MAX_AGE_MINUTES} minutes', docs)
        self.assertIn(str(ns.MIN_CONFIDENCE), docs)
        version = json.loads((ROOT / 'plugin.json').read_text())['version']
        self.assertEqual(json.loads((ROOT / '.codex-plugin' / 'plugin.json').read_text())['version'], version)
        self.assertIn(f'**{version}**', (ROOT / 'README.md').read_text())
        self.assertIn(f'**{version}**', docs)


if __name__ == '__main__':
    unittest.main()
