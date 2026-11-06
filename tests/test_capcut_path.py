"""CapCut export records the folder it really sits in (CapCut rejects an 'unusual path')."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'engine'))
import capcut_export


class CapCutPathTests(unittest.TestCase):
    def test_export_lands_in_capcut_drafts_with_real_path(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            job = d / '_preview-x'
            (job / 'inputs').mkdir(parents=True)
            (job / 'inputs' / 'a.mp4').write_bytes(b'x')
            (job / 'edl.json').write_text(json.dumps({'source': 'inputs/a.mp4', 'cuts': [{'in': 0, 'out': 1.5}]}))
            drafts = d / 'drafts'
            drafts.mkdir()
            with patch.dict(os.environ, {'KIT_CAPCUT_DRAFTS': str(drafts)}):
                folder = capcut_export.export_job(job)
            self.assertEqual(folder, drafts / 'kit-preview-x')
            meta = json.loads((folder / 'draft_meta_info.json').read_text())
            self.assertEqual(meta['draft_fold_path'], str(folder.resolve()))
            self.assertEqual(meta['draft_root_path'], str(drafts.resolve()))


if __name__ == '__main__':
    unittest.main()
