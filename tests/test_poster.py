import json, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'engine'))
import library, poster
from PIL import Image
class PosterTests(unittest.TestCase):
    def test_image_poster_decodes(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'input.png';Image.new('RGB',(400,800),'red').save(p)
            out=poster.make_poster(p)
            self.assertEqual(out.name,'input.poster.png');self.assertTrue(p.exists())
            with Image.open(out) as im:self.assertEqual(im.format,'PNG')
    def test_index_records_pending_cover(self):
        with tempfile.TemporaryDirectory() as d,patch.object(library,'KIT',d),patch.object(library,'LIB',d),patch.object(library,'INDEX',str(Path(d)/'index.json')):
            p=Path(d)/'input.png';Image.new('RGB',(100,100),'blue').save(p)
            item=library._record('picture','sample',str(p),['test'])
            self.assertTrue((Path(d)/item['poster']).exists());self.assertEqual(item['notion_cover']['status'],'local_only')
    def test_failure_does_not_record_success(self):
        with patch.object(poster,'make_poster',side_effect=ValueError('cannot decode')),patch.object(library,'load',return_value={'items':[]}),patch.object(library,'save') as save:
            with self.assertRaises(SystemExit):library._record('picture','bad','/missing.png',[])
            save.assert_not_called()
    def test_rasterizer_failure_propagates(self):
        import subprocess
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'bad.html';source.write_text('<html>test</html>')
            with patch.object(poster.subprocess,'run',side_effect=subprocess.CalledProcessError(1,['node'],stderr='Local Chrome missing')):
                with self.assertRaises(subprocess.CalledProcessError):poster.make_poster(source)
            self.assertFalse(source.with_suffix('.poster.png').exists())
