"""2.3.7: message graphics show made-up texts (never his script), every other graphic's words come from him (including
words typed into its HTML), captions keep one size and one height, and a Short never saves or inherits graphics."""
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
import quick_edit as qe
import render_hf as rh

WORDS = [{"w": w, "s": 4.8 + i * 0.3, "e": 5.0 + i * 0.3} for i, w in enumerate(
    "Last night some random guy I've never met booked a call with me while I was already in bed.".split())]


def blk(name="thread-message-stack", **kw):
    return dict({"name": name, "start": 150, "frames": 90, "vars": {}, "box": None}, **kw)


class MessageGraphicTests(unittest.TestCase):
    def test_what_counts_as_a_message_graphic(self):
        for name in ("thread-message-stack", "imessage-thread", "ig-dm", "instagram-dm-card", "macos-notification", "chat-message",
                     "text-thread", "lock-screen-notification"):
            self.assertTrue(gg.is_message({"name": name}), name)
        for name in ("ai-chat-reveal", "chatgpt-window", "google-search", "stripe-dashboard", "type-match-cut", "gpt-chat-message"):
            self.assertFalse(gg.is_message({"name": name}), name)
        self.assertTrue(gg.is_message({"name": "my-phone", "kind": "messages"}))
        self.assertTrue(gg.is_message({"name": "my-phone", "data": {"messages": [{"side": "incoming", "text": "hey"}]}}))

    def test_made_up_texts_pass_without_any_allow_flag(self):
        b = blk(message=True, texts=["omg are you still up??", "wait who is this lol", "ok you're kinda funny"])
        self.assertEqual(gg.check_text([b], [], WORDS, 30), [])

    def test_texts_copied_from_his_script_fail(self):
        b = blk(message=True, texts=["Booked a call with you", "hey cutie", "random guy booked a call while already in bed"])
        errs = gg.check_text([b], [], WORDS, 30)
        self.assertEqual(len(errs), 2, errs)
        self.assertTrue(all("copies his script" in e for e in errs))

    def test_a_message_graphic_far_from_his_line_still_cannot_copy_it(self):
        b = blk(message=True, start=3000, texts=["booked a call with me"])     # 100 s later: the whole transcript counts
        self.assertTrue(gg.check_text([b], [], WORDS, 30))

    def test_sample_or_old_texts_must_be_replaced(self):
        b = blk(message=True, needs_data=True, texts=["wait, that is actually wild"])
        self.assertIn("fresh made-up texts", gg.check_text([b], [], WORDS, 30)[0])

    def test_block_tryout_shows_sample_text(self):
        b = blk(message=True, needs_data=True, tryout=True, texts=["wait, that is actually wild"])
        self.assertEqual(gg.check_text([b], [], WORDS, 30), [])
        self.assertIn('"tryout": True', (ROOT / "engine" / "kit.py").read_text())

    def test_other_graphics_still_need_his_words(self):
        errs = gg.check_text([blk("google-search", texts=["Want to meet this week?"])], [], WORDS, 30)
        self.assertIn("doesn't say", errs[0])


class HtmlTextTests(unittest.TestCase):
    PAGE = ('<html><head><title>Demo Title</title><style>.a{color:red}</style></head><body>'
            '<div data-composition-id="g"><span class="logo">Google</span><input placeholder="Search Google">'
            '<h3>Cold approach coaching that works</h3><p data-ui>Sponsored result settings</p>'
            '<span>9:41</span><img alt="logo"><script>var t = "never shown";</script>'
            '<div hidden data-hf-primitive-data>{"q": "x"}</div></div></body></html>')

    def test_typed_text_is_read_but_chrome_and_code_are_not(self):
        self.assertEqual(gg.html_texts(self.PAGE), ["Cold approach coaching that works"])

    def test_text_typed_into_a_graphic_is_checked(self):
        with tempfile.TemporaryDirectory() as proj:
            os.makedirs(os.path.join(proj, "compositions"))
            open(os.path.join(proj, "compositions", "g.html"), "w").write(self.PAGE)
            b = blk("google-results", box=[0, 0, 1080, 700])
            rh.prepare_block(b, 0, proj, {"id": "g", "w": 1080, "h": 700, "dur": 5, "fluid": True, "src": "compositions/g.html"})
        self.assertEqual(b["html_texts"], ["Cold approach coaching that works"])
        errs = gg.check_text([dict(b, texts=[])], [], WORDS, 30)
        self.assertIn("Cold approach coaching that works", errs[0])

    def test_message_graphic_from_the_library_without_data_is_flagged(self):
        src = ('<div data-composition-id="tms" data-width="1080" data-height="1920">'
               '<div hidden data-hf-primitive-data>{"messages": [{"side": "incoming", "text": "wait, that is actually wild"}]}</div></div>')
        with tempfile.TemporaryDirectory() as proj:
            os.makedirs(os.path.join(proj, "compositions"))
            open(os.path.join(proj, "compositions", "tms.html"), "w").write(src)
            meta = {"id": "tms", "w": 1080, "h": 1920, "dur": 8, "fluid": False, "src": "compositions/tms.html", "origin": "library"}
            b = blk(box=[0, 0, 1080, 600]); rh.prepare_block(b, 0, proj, meta)
            self.assertTrue(b["message"]); self.assertTrue(b["needs_data"])
            b = blk(box=[0, 0, 1080, 600], data={"messages": [{"side": "incoming", "text": "u up? 👀"}]}); rh.prepare_block(b, 1, proj, meta)
            self.assertFalse(b["needs_data"])


class CaptionTests(unittest.TestCase):
    ST = dict(qe.STYLE_DEFAULTS, font_file="Outfit-Bold.ttf", _style_dir=str(ROOT / "styles" / "default"), uppercase=False,
              kw_pop_pct=8, keyword_scale=1.08)

    def words(self, text):
        return [{"w": w} for w in text.split()]

    def test_short_caption_stays_one_line(self):
        self.assertEqual(len(qe.fit_lines(self.words("booked a call"), self.ST, 81, 1080)), 1)

    def test_long_caption_breaks_instead_of_shrinking(self):
        lines = qe.fit_lines(self.words("Unbelievably extraordinary entrepreneurship"), self.ST, 140, 1080)
        self.assertGreater(len(lines), 1)
        self.assertEqual(sum(len(l) for l in lines), 3)                 # every word kept, in order

    def test_no_per_caption_shrink_left(self):
        self.assertFalse(hasattr(qe, "_fit_one_line"))
        src = (ROOT / "engine" / "timeline.py").read_text()
        self.assertIn('"size": round(fs), "lines": lines', src)

    def test_captions_never_jump_to_a_seam(self):
        src = (ROOT / "engine" / "render_hf.py").read_text()
        self.assertNotIn('class="cap" style=', src); self.assertNotIn("seams", src)


class NoAutoSaveTests(unittest.TestCase):
    def _kit(self, d):
        k = Path(d)
        (k / "styles" / "default").mkdir(parents=True)
        (k / "styles" / "default" / "style.json").write_text("{}")
        return k

    def test_unsaved_graphic_in_my_styles_is_refused(self):
        with tempfile.TemporaryDirectory() as d, patch.object(rh, "KIT", d):
            t = Path(d) / "my-styles" / "default" / "templates" / "old-thread"
            t.mkdir(parents=True); (t / "old-thread.html").write_text("<div>Booked a call</div>")
            with self.assertRaises(SystemExit) as e:
                rh.own_block("default", "old-thread")
            self.assertIn("older video", str(e.exception))
            (t / "manifest.json").write_text(json.dumps({"saved": True}))
            self.assertEqual(rh.own_block("default", "old-thread")[1], "style")

    def test_this_videos_graphic_comes_first(self):
        with tempfile.TemporaryDirectory() as d, patch.object(rh, "KIT", d):
            g = Path(d) / ".work" / "j" / "graphics" / "dm"
            g.mkdir(parents=True); (g / "dm.html").write_text("<div></div>")
            self.assertEqual(rh.own_block("default", "dm", [str(g.parent)]), (str(g), "video"))

    def test_graphics_save_only_on_request_and_marks_it(self):
        with tempfile.TemporaryDirectory() as d:
            k = self._kit(d)
            job = k / ".work" / "j"; (job / "graphics" / "dm").mkdir(parents=True); (job / "graphics" / "dm" / "dm.html").write_text("<div></div>")
            with patch.object(kit, "KIT", k), patch.object(kit, "STYLES", k / "styles"), patch.object(kit, "USER_STYLES", k / "my-styles"), \
                    patch.object(kit, "resolve_job", lambda n: job):
                dst = kit.graphics_save("dm", "j", "default")
            self.assertTrue(json.loads((dst / "manifest.json").read_text())["saved"])
            self.assertTrue((dst / "dm.html").exists())

    def test_docs_say_build_in_the_job_folder(self):
        for f in ("skills/graphics/SKILL.md", "styles/default/STYLE.md"):
            txt = (ROOT / f).read_text()
            self.assertIn(".work/<job>/graphics/", txt, f)
            self.assertNotIn("my-styles/<style>/templates/<name>/<name>.html", txt, f)
            self.assertNotIn("my-styles/default/templates/<name>/", txt, f)


if __name__ == "__main__":
    unittest.main()
