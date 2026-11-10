"""Sorting regressions: local fixtures only, no network or model calls."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'engine'))
import notion_index as ni
import notion_sort as ns

class SortTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'IMG_1234.png'; self.path.write_bytes(b'synthetic fixture')
        self.sha = ni.sha256(self.path); self.key = 'p:' + self.sha
        self.index = ni.empty_index()
        self.index['entries'][self.key] = {'page_id':'p','sha256':self.sha,'path':str(self.path),'role':'graphics','kind':'graphic','stale':False,'title':'IMG_1234','file_name':'IMG_1234.png','file_names':['IMG_1234.png'],'body':'hidden provenance cafe','tags':['hidden','provenance','cafe'],'origin':'stock','media':{'aspect':'vertical'},'sort_frames':[{'path':str(self.path),'sha256':self.sha}]}
        self.record = {'entry_key':self.key,'subject':['profile','phone'],'setting':'phone-screen','people':{'count':'0'},'mood':'neutral','shot_type':'graphic','time_of_day':'unknown','origin':{'value':'unknown','confidence':.2,'evidence':[{'source':'vision','detail':'Graphic appearance does not establish provenance.'}],'note':'not licence clearance'},'description':'Dating profile on a phone screen','confidence':.95,'sorted_at':'2026-11-02T23:00:00Z','file_sha256':self.sha,'frame_hashes':[self.sha],'sorter':'codex-vision','ignore_body':True}
    def test_validate_apply_and_skip(self):
        self.assertEqual(ns.plan(self.index)['to_sort'],[self.key]); ns.apply(self.index,[self.record]); self.assertEqual(ns.plan(self.index)['to_sort'],[])
    def test_invalid_vocab_and_atomic(self):
        for field,value in [('setting','restaurant'),('confidence',float('nan')),('people',{'count':5}),('subject',['celebrity']),('sorted_at','2026-11-02')]:
            r=copy.deepcopy(self.record);r[field]=value; before=copy.deepcopy(self.index)
            with self.assertRaises(ValueError):ns.apply(self.index,[self.record,r])
            self.assertEqual(self.index,before)
    def test_invalid_hashes(self):
        for field in ['file_sha256','frame_hashes']:
            r=copy.deepcopy(self.record);r[field]='0'*64 if field=='file_sha256' else ['0'*64]
            with self.assertRaises(ValueError):ns.apply(self.index,[r])
    def test_changed_bytes_require_refresh(self):
        ns.apply(self.index,[self.record]);self.path.write_bytes(b'changed')
        with self.assertRaises(ValueError):ns.plan(self.index)
    def test_one_new_entry(self):
        ns.apply(self.index,[self.record]);other=copy.deepcopy(self.index['entries'][self.key]);other.pop('ai_sort');other['page_id']='q';self.index['entries']['q:'+self.sha]=other
        self.assertEqual(ns.plan(self.index)['to_sort'],['q:'+self.sha])
    def test_visual_ranking_without_body(self):
        self.assertEqual(ni.find(self.index,'dating profile',ignore_body=True),[])
        self.assertEqual(ni.find(self.index,'cafe',ignore_body=True),[])
        ns.apply(self.index,[self.record]);hits=ni.find(self.index,'dating profile',ignore_body=True)
        self.assertEqual(hits[0]['page_id'],'p');self.assertTrue(any('ai.' in r for r in hits[0]['match_reasons']))
    def test_manual_overrides_win(self):
        ns.apply(self.index,[self.record]);ni.set_override(self.index,'p',{'origin':'own','tags_add':['favorite'],'tags_remove':['dating','profile']})
        self.assertEqual(ni.effective(self.index['entries'][self.key],self.index)['origin'],'own')
        self.assertEqual(ni.find(self.index,'dating profile',ignore_body=True),[])
        self.assertTrue(ni.find(self.index,'favorite',ignore_body=True))
        ni.set_override(self.index,'p',{'exclude':True});self.assertEqual(ni.find(self.index,'phone',ignore_body=True),[])
    def test_a_phrase_without_a_fresh_snapshot_never_plans_a_write(self):
        ns.apply(self.index,[self.record])
        for phrase in [None, 'save tags', ns.OPT_IN]:
            for page in [None, 'p']:
                result=ns.writeback(self.index,phrase,page)
                self.assertEqual(result['patches'],[])
                self.assertFalse(result['write_performed'])
                self.assertFalse(result['notion_writeback'])
    def test_body_excluded_record_cannot_cite_body(self):
        self.record['origin']['evidence'][0]['source']='body'
        with self.assertRaises(ValueError):ns.apply(self.index,[self.record])
    def test_body_aware_record_not_used_in_strict_search(self):
        self.record['ignore_body']=False;ns.apply(self.index,[self.record])
        self.assertEqual(ni.find(self.index,'dating profile',ignore_body=True),[])
        self.assertEqual(ns.plan(self.index,ignore_body=True)['to_sort'],[self.key])
    def test_removed_tag_does_not_return_via_title_fuzzy_match(self):
        self.index['entries'][self.key]['title'] = 'dating profile'
        ns.apply(self.index,[self.record]);ni.set_override(self.index,'p',{'tags_remove':['profile']})
        self.assertEqual(ni.find(self.index,'dating profile',ignore_body=True),[])
    def test_no_snapshot_no_patches_with_overrides(self):
        ns.apply(self.index,[self.record]);ni.set_override(self.index,'p',{'origin':'own'})
        self.assertEqual(ns.writeback(self.index,ns.OPT_IN,'p')['patches'],[])
        ni.set_override(self.index,'p',{'exclude':True})
        self.assertEqual(ns.writeback(self.index,ns.OPT_IN,'p')['patches'],[])
    def test_default_config_writeback_false(self):
        self.assertFalse(ni.detect({'roles':{}})['notion_writeback'])

if __name__=='__main__':unittest.main()
