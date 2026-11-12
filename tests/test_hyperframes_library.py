"""HyperFrames 0.9, the library (blocks and components), the Studio project name, and the frame layout. No network."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
import kit
import render_hf as rh
import timeline as tlm


class VersionTests(unittest.TestCase):
    def test_floor_is_current_line(self):
        self.assertEqual(json.loads((ROOT / "engine" / "hyperframes.json").read_text())["version"], "0.9.39")

    def test_old_line_left_in_cache_is_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            floor, live = os.path.join(d, "floor.json"), os.path.join(d, "live.json")
            json.dump({"version": "0.9.39"}, open(floor, "w"))
            with patch.object(rh, "FLOOR", floor), patch.object(rh, "LIVE", live), patch.dict(os.environ, {}, clear=False):
                os.environ.pop("KIT_HF_VERSION", None)
                for cached, want in (("0.8.230", "0.9.39"), ("0.9.12", "0.9.39"), ("0.9.40", "0.9.40")):
                    json.dump({"version": cached}, open(live, "w"))
                    self.assertEqual(rh.hf_version(), want, cached)


class StudioProjectNameTests(unittest.TestCase):
    """HyperFrames names the Studio project from $PWD: every call about a project names it and sets PWD to it."""
    def test_calls_name_the_project(self):
        calls = []
        def fake(cmd, **kw):
            calls.append((cmd, kw))
            return SimpleNamespace(returncode=0, stdout="{}", stderr="")
        with tempfile.TemporaryDirectory() as proj, patch.object(rh.subprocess, "run", fake), \
                patch.dict(os.environ, {"PWD": "/somewhere/else"}):
            rh.running(proj); rh.stop(proj); rh.snapshot(proj, [1.0]); rh.check(proj)
            for cmd, kw in calls:
                self.assertIn(os.path.abspath(proj), cmd, cmd)
                self.assertEqual(kw["env"]["PWD"], os.path.abspath(proj), cmd)


class LibraryTests(unittest.TestCase):
    def _cache(self, d, rel, html):
        p = Path(d) / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(html)
        return str(p)

    def test_component_and_block_are_both_found(self):
        with tempfile.TemporaryDirectory() as d:
            comp = self._cache(d, "compositions/components/type-match-cut.html",
                               '<html data-composition-id="type-match-cut" data-composition-duration="4"><template>'
                               '<div id="root" data-composition-id="type-match-cut" data-duration="4"></div></template></html>')
            self.assertEqual(rh.library_file(d, "type-match-cut"), comp)
            m = rh.block_meta(comp, "type-match-cut")
            self.assertTrue(m["fluid"]); self.assertEqual(m["src"], "compositions/components/type-match-cut.html"); self.assertEqual(m["dur"], 4.0)
            blk = self._cache(d, "compositions/ai-chat-reveal.html",
                              '<div data-composition-id="ai-chat-reveal" data-width="1080" data-height="1920" data-duration="19.3"></div>')
            m = rh.block_meta(blk, "ai-chat-reveal")
            self.assertFalse(m["fluid"]); self.assertEqual((m["w"], m["h"]), (1080, 1920)); self.assertEqual(m["src"], "compositions/ai-chat-reveal.html")

    def test_add_is_offered_and_uses_the_registry(self):
        src = (ROOT / "engine" / "render_hf.py").read_text()
        self.assertIn('["add", name, "--dir", tmp, "--json", "--no-clipboard"]', src)
        self.assertIn('choices=["search", "add", "test"]', (ROOT / "engine" / "kit.py").read_text())

    def _tl(self, blocks, layout="split"):
        return {"fps": 30, "width": 1080, "height": 1920, "frames": 90, "font": "f.ttf", "camera": [], "broll": [], "sfx": [],
                "captions": [], "overlays": [], "graphics": [], "blocks": blocks, "style_name": "",
                "style": {"frame_layout": layout, "loudness": {"I": -14, "TP": -1.5}}}

    def test_component_fills_the_top_panel(self):
        html = rh.write_html(self._tl([{"name": "type-match-cut", "start": 0, "frames": 60, "vars": {}, "box": None}]),
                             {"type-match-cut": {"id": "type-match-cut", "w": 1080, "h": 1920, "dur": 4, "fluid": True,
                                                 "src": "compositions/components/type-match-cut.html"}})
        self.assertIn('data-composition-src="compositions/components/type-match-cut.html"', html)
        self.assertIn("width:1080px;height:960px", html)
        self.assertIn("transform:scale(1.00000)", html)

    def test_block_is_never_scaled_up_and_fits_the_panel(self):
        html = rh.write_html(self._tl([{"name": "ai-chat-reveal", "start": 0, "frames": 60, "vars": {}, "box": None}]),
                             {"ai-chat-reveal": {"id": "ai-chat-reveal", "w": 540, "h": 400, "dur": 19, "fluid": False,
                                                 "src": "compositions/ai-chat-reveal.html"}})
        self.assertIn('data-width="540" data-height="400"', html)
        self.assertIn("transform:scale(1.00000)", html)


class FrameLayoutTests(unittest.TestCase):
    st = {"frame_layout": "split", "center_y_frac": 0.5}

    def test_no_graphics_means_full_frame(self):
        st, note = tlm.frame_layout({}, self.st, [], [], [])
        self.assertEqual(st["frame_layout"], "full"); self.assertEqual(st["center_y_frac"], 0.7); self.assertIn("full frame", note)
        self.assertEqual(self.st["frame_layout"], "split")   # the style itself is untouched

    def test_graphics_keep_the_split(self):
        for blocks, ovs, gfx in (([{"name": "x"}], [], []), ([], [{"x": 1}], []), ([], [], [{"text": "a"}])):
            self.assertEqual(tlm.frame_layout({}, self.st, blocks, ovs, gfx)[0]["frame_layout"], "split")

    def test_plan_choice_wins(self):
        st, _ = tlm.frame_layout({"style": {"frame_layout": "split"}}, self.st, [], [], [])
        self.assertEqual(st["frame_layout"], "split")

    def test_full_styles_untouched(self):
        st, note = tlm.frame_layout({}, {"frame_layout": "full", "center_y_frac": 0.64}, [], [], [])
        self.assertEqual((st["frame_layout"], st["center_y_frac"], note), ("full", 0.64, ""))


if __name__ == "__main__":
    unittest.main()
