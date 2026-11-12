"""Graphics on a vertical Short: always in the top panel at a readable size, never over his face or the caption seam,
no canned text pieces, no invented text, sharp (no blur, no upscaling), and the lint gate in front of preview and render.
No network: HyperFrames calls are faked."""
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
import graphic_guard as gg
import kit
import render_hf as rh
import timeline as tlm

W, H = 1080, 1920
AREA = gg.graphic_area(W, H)


def blk(name="thread-message-stack", box=None, **kw):
    return dict({"name": name, "start": 30, "frames": 90, "vars": {}, "box": box}, **kw)


class PlacementTests(unittest.TestCase):
    def test_area_is_the_top_panel_above_the_caption_seam(self):
        x, y, w, h = AREA
        self.assertEqual((x, y, w), (0, 0, W))
        self.assertLess(y + h, H / 2)                  # clear of the seam the captions sit on
        self.assertGreater(h, H / 2 - 120)             # but most of the panel

    def test_no_box_fills_the_graphic_area(self):
        b = [blk()]
        self.assertEqual(gg.place_blocks(b, W, H), [])
        self.assertEqual(b[0]["box"], AREA)

    def test_block_over_his_face_moves_into_the_panel(self):
        b = [blk(box=[0, 520, 1080, 880])]            # Matthew's: a message thread on his chest
        notes = gg.place_blocks(b, W, H)
        self.assertEqual(b[0]["box"], AREA)
        self.assertIn("covered his face", notes[0])

    def test_block_across_the_seam_moves_into_the_panel(self):
        b = [blk(box=[0, 300, 1080, 640])]            # ends at 940: inside the top half but under the capsule
        self.assertIn("caption seam", gg.place_blocks(b, W, H)[0])
        self.assertEqual(b[0]["box"], AREA)

    def test_tiny_corner_block_is_made_readable(self):
        b = [blk("macos-notification", box=[860, 40, 200, 120])]   # the near-invisible notification at the edge
        self.assertIn("too small", gg.place_blocks(b, W, H)[0])
        self.assertEqual(b[0]["box"], AREA)

    def test_good_box_is_kept(self):
        b = [blk(box=[40, 60, 1000, 700])]
        self.assertEqual(gg.place_blocks(b, W, H), [])
        self.assertEqual(b[0]["box"], [40, 60, 1000, 700])

    def test_canned_text_piece_is_flagged(self):
        for name in ("accent-underline", "kinetic-label", "lower-third", "stat-count", "idea-swipe", "callout"):
            with self.assertRaises(ValueError) as e:
                gg.place_blocks([blk(name)], W, H)
            self.assertIn("canned", str(e.exception))
        gg.place_blocks([blk("accent-underline", canned_ok=True)], W, H)   # he asked for that exact piece

    def test_replicas_are_not_canned(self):
        for name in ("thread-message-stack", "google-search", "ai-chat-reveal", "macos-notification", "type-match-cut"):
            self.assertFalse(gg.canned(name), name)

    def test_long_form_is_left_alone(self):
        b = [blk(box=[0, 0, 400, 200])]
        self.assertEqual(gg.place_blocks(b, 1920, 1080), [])
        self.assertEqual(b[0]["box"], [0, 0, 400, 200])

    def test_overlay_on_his_face_moves_up(self):
        ovs = [{"x": 540, "y": 1400}, {"x": 540, "y": 400}]
        notes = gg.place_overlays(ovs, W, H)
        self.assertEqual(len(notes), 1)
        self.assertLess(ovs[0]["y"], AREA[3]); self.assertEqual(ovs[1]["y"], 400)


class SplitIsForcedTests(unittest.TestCase):
    def test_blocks_force_split_even_when_plan_or_style_say_full(self):
        for edl, st in (({"style": {"frame_layout": "full"}}, {"frame_layout": "split"}),   # plan override
                        ({}, {"frame_layout": "full"}),                                   # a full-frame style
                        ({}, {})):                                                        # matthew style: no frame_layout
            out, note = tlm.frame_layout(edl, st, [{"name": "x"}], [], [], W, H)
            self.assertEqual(out["frame_layout"], "split", (edl, st))

    def test_no_blocks_keeps_face_full_frame(self):
        out, _ = tlm.frame_layout({}, {"frame_layout": "split", "center_y_frac": 0.5}, [], [], [], W, H)
        self.assertEqual(out["frame_layout"], "full")

    def test_long_form_is_not_forced(self):
        out, _ = tlm.frame_layout({}, {"frame_layout": "full"}, [{"name": "x"}], [], [], 1920, 1080)
        self.assertEqual(out["frame_layout"], "full")

    def test_mounted_block_sits_in_the_panel_and_captions_on_the_seam(self):
        tl = {"fps": 30, "width": W, "height": H, "frames": 90, "font": "f.ttf", "camera": [], "broll": [], "sfx": [],
              "captions": [{"start": 0, "end": 25, "t0": 0, "size": 80, "lines": [[{"text": "hook", "hot": False, "at": 0}]]},
                           {"start": 40, "end": 70, "t0": 40, "size": 80, "lines": [[{"text": "hi", "hot": False, "at": 40}]]}],
              "overlays": [], "graphics": [], "style_name": "", "src_w": 720, "src_h": 1280,
              "blocks": [blk(box=list(AREA))], "style": {"frame_layout": "split", "loudness": {"I": -14, "TP": -1.5}}}
        html = rh.write_html(tl, {0: {"id": "thread-message-stack", "w": AREA[2], "h": AREA[3], "dur": 8, "fluid": False,
                                      "src": "compositions/thread-message-stack--0.html"}})
        self.assertIn(f"left:0.0px;top:0.0px;width:{AREA[2]}px;height:{AREA[3]}px;transform-origin:0 0;transform:scale(1.00000)", html)
        self.assertIn(f'class="cap" style="top:{H // 2}px"><div id="capin1"', html)   # on the seam while the block shows
        self.assertIn('<div class="cap"><div id="capin0"', html)                      # the hook: full-frame height
        self.assertIn('id="panel0" class="clip" data-start="1.000000" data-duration="3.000000"', html)   # panel only with the block
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "index.html"), "w").write(html)
            self.assertEqual(rh.layout_errors(d), [])


class HandEditLayoutTests(unittest.TestCase):
    """A hand-edited index.html is checked too: a block moved onto his face fails the gate."""
    def _proj(self, d, style):
        open(os.path.join(d, "index.html"), "w").write(
            f'<div id="root" data-composition-id="main" data-start="0" data-duration="3" data-fps="30" data-width="1080" data-height="1920">'
            f'<div id="blk0" data-composition-id="t" data-composition-src="compositions/t.html" style="{style}"></div></div>')
        return d

    def test_block_on_face_fails(self):
        with tempfile.TemporaryDirectory() as d:
            errs = rh.layout_errors(self._proj(d, "position:absolute;left:0px;top:520px;width:1920px;height:1080px;transform:scale(0.5625)"))
            self.assertTrue(any("covers his face" in e for e in errs), errs)

    def test_tiny_or_upscaled_block_fails(self):
        with tempfile.TemporaryDirectory() as d:
            errs = rh.layout_errors(self._proj(d, "position:absolute;left:880px;top:20px;width:400px;height:200px;transform:scale(0.4)"))
            self.assertTrue(any("too small" in e for e in errs), errs)
        with tempfile.TemporaryDirectory() as d:
            errs = rh.layout_errors(self._proj(d, "position:absolute;left:0px;top:0px;width:540px;height:400px;transform:scale(1.8)"))
            self.assertTrue(any("scaled up" in e for e in errs), errs)


class SharpnessTests(unittest.TestCase):
    SRC = ('<div id="r" data-composition-id="tms" data-width="1920" data-height="1080"><style>#r { width: 1920px; height: 1080px; '
           'backdrop-filter: blur(24px); } .card { filter: blur(6px); max-width: 920px; }</style>'
           '<div hidden data-hf-primitive-data>{"messages": [{"side": "incoming", "text": "wait, that is actually wild", "sender": "Northbeam support"}]}</div></div>')

    def test_blur_is_stripped(self):
        out = rh.real_look(self.SRC, "no-look-for-this")
        self.assertNotIn("blur(", out)

    def test_reflow_lays_out_at_box_size(self):
        out = rh.reflow(self.SRC, 1920, 1080, 1080, 874)
        self.assertIn('data-width="1080" data-height="874"', out)
        self.assertIn("width: 1080px; height: 874px", out)
        self.assertIn("max-width: 920px", out)   # only the canvas size changes

    def test_thread_block_has_a_real_look(self):
        css = (ROOT / "graphics" / "_looks" / "thread-message-stack.css").read_text()
        self.assertIn("#tms-roll", css); self.assertIn("display: none", css)
        out = rh.real_look(self.SRC, "thread-message-stack")
        self.assertIn("kit real look", out)

    def test_prepare_block_reflows_and_takes_his_words(self):
        with tempfile.TemporaryDirectory() as proj:
            os.makedirs(os.path.join(proj, "compositions"))
            open(os.path.join(proj, "compositions", "tms.html"), "w").write(self.SRC)
            meta = {"id": "tms", "w": 1920, "h": 1080, "dur": 8, "fluid": False, "src": "compositions/tms.html"}
            b = blk("tms", box=list(AREA), data={"messages": [{"side": "incoming", "text": "booked a call with me"}]})
            m, texts = rh.prepare_block(b, 0, proj, meta)
            self.assertEqual((m["w"], m["h"]), (AREA[2], AREA[3]))
            self.assertEqual(texts, ["booked a call with me"])
            body = open(os.path.join(proj, m["src"])).read()
            self.assertIn("booked a call with me", body); self.assertNotIn("Northbeam", body); self.assertNotIn("blur(", body)

    def test_face_is_framed_in_the_bottom_half(self):
        tl = {"width": W, "height": H, "src_w": 720, "src_h": 1280, "style": {"face_focus_y": {"top": 0.30, "bottom": 0.75}}}
        pos = rh.face_pos(tl)
        rh_, ph = 1280 * W / 720, H // 2
        off = pos / 100 * (rh_ - ph)
        self.assertLessEqual(off, 0.30 * rh_)            # forehead in
        self.assertGreaterEqual(off + ph, 0.75 * rh_)   # chin in
        self.assertEqual(rh.face_pos({"width": W, "height": H, "src_w": 720, "src_h": 1280, "style": {}}), 28.0)


class InventedTextTests(unittest.TestCase):
    WORDS = [{"w": w, "s": 4.8 + i * 0.3, "e": 5.0 + i * 0.3} for i, w in enumerate(
        "Last night some random guy I've never met booked a call with me while I was already in bed.".split())]

    def test_his_words_pass(self):
        self.assertEqual(gg.unsupported_text(["Random guy booked a call", "already in bed"], self.WORDS, 5, 8), [])

    def test_invented_text_is_flagged(self):
        bad = gg.unsupported_text(["Want to meet this week?", "Attention has value", "Northbeam support", "booked a call"],
                                  self.WORDS, 5, 8)
        self.assertEqual(bad, ["Want to meet this week?", "Attention has value", "Northbeam support"])

    def test_text_far_from_the_moment_is_flagged(self):
        self.assertEqual(gg.unsupported_text(["booked a call"], self.WORDS, 40, 45), ["booked a call"])

    def test_check_text_reads_blocks_and_cards(self):
        errs = gg.check_text([dict(blk(start=150, frames=90), texts=["wait, that is actually wild", "booked a call"])],
                             [{"start": 150, "frames": 30, "text": "Attention has value"}], self.WORDS, 30)
        self.assertEqual(len(errs), 2)
        self.assertIn("wait, that is actually wild", errs[0]); self.assertIn("Attention has value", errs[1])
        self.assertEqual(gg.check_text([dict(blk(start=150, invented_ok=True), texts=["anything"])], [], self.WORDS, 30), [])

    def test_strings_skip_non_text(self):
        self.assertEqual(gg.strings_in({"messages": [{"side": "incoming", "text": "hi there"}], "stagger": 0.86, "color": "#0A84FF"}),
                         ["hi there"])


class LintGateTests(unittest.TestCase):
    """Preview and render refuse a project with lint/check errors and show them."""
    def _fake(self, payload, rc=1, prefix=""):
        def run(cmd, **kw):
            out = prefix + (json.dumps(payload) if isinstance(payload, dict) else payload)
            return SimpleNamespace(returncode=rc, stdout=out, stderr="")
        return run

    LINT = {"ok": False, "lint": {"ok": False, "errorCount": 27, "findings": [
        {"code": "missing_local_asset", "severity": "error", "message": "assets/x.png not found", "file": "/p/index.html", "line": 9}]}}

    def test_lint_errors_fail_and_are_listed(self):
        with tempfile.TemporaryDirectory() as proj, patch.object(rh.subprocess, "run", self._fake(self.LINT)):
            code, log = rh.check(proj)
        self.assertEqual(code, 1)
        self.assertIn("missing_local_asset", log); self.assertIn("error(s) to fix first", log)

    def test_unreadable_output_fails_closed(self):
        with tempfile.TemporaryDirectory() as proj, patch.object(rh.subprocess, "run", self._fake("Segmentation fault", rc=0)):
            self.assertEqual(rh.check(proj)[0], 1)

    def test_notice_before_json_is_read(self):
        ok = {"ok": True, "lint": {"ok": True, "errorCount": 0, "findings": []}}
        with tempfile.TemporaryDirectory() as proj, patch.object(rh.subprocess, "run", self._fake(ok, rc=0, prefix="Update available\n")):
            self.assertEqual(rh.check(proj), (0, "check passed"))

    def test_preview_refuses_and_closes_studio(self):
        with tempfile.TemporaryDirectory() as d:
            job = Path(d) / "j"; job.mkdir(); (job / "edl.json").write_text("{}")
            stopped, opened = [], []
            fake = SimpleNamespace(build=lambda p, force=False: (d, "built"), check=lambda p: (1, "1 error(s) to fix first:\nlint: boom"),
                                   stop=lambda p: stopped.append(p), preview=lambda p, port: opened.append(p) or ("u", True))
            with patch.object(kit, "hfm", lambda: fake), patch.object(kit, "resolve_job", lambda n: job), \
                    patch.object(kit, "place_logos", lambda e: None):
                with self.assertRaises(SystemExit):
                    kit.cmd_preview(SimpleNamespace(jobs=["j"], stop=False, rebuild=False, port=3101, open=False))
            self.assertEqual(opened, []); self.assertEqual(stopped, [d])

    def test_render_refuses(self):
        rendered = []
        def run(cmd, **kw):
            if "render" in cmd: rendered.append(cmd)
            return SimpleNamespace(returncode=1, stdout=json.dumps(self.LINT), stderr="")
        with tempfile.TemporaryDirectory() as proj, patch.object(rh.subprocess, "run", run):
            with self.assertRaises(SystemExit):
                rh.render(proj, os.path.join(proj, "out.mp4"))
        self.assertEqual(rendered, [])


if __name__ == "__main__":
    unittest.main()
