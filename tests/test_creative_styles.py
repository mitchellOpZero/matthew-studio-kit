"""default, creative instructions, and preview-before-render. No media or network."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))
import kit  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
STYLE = ROOT / "styles" / "default"
BLOCKS = ("kinetic-label", "stat-count", "callout", "lower-third", "idea-swipe")


class DefaultStyleTests(unittest.TestCase):
    def test_style_validates_and_leaves_the_basics_alone(self):
        st = json.loads((STYLE / "style.json").read_text())
        self.assertEqual(kit.validate_style(st, STYLE), [])
        self.assertEqual(st["caption_template"], "capsule")
        self.assertEqual(st.get("frame_layout"), "split")
        self.assertEqual(st["font_file"], "Outfit-Bold.ttf")
        matthew = json.loads((ROOT / "styles" / "matthew" / "style.json").read_text())
        long = json.loads((ROOT / "styles" / "matthew-long" / "style.json").read_text())
        self.assertEqual(matthew["font"], "Montserrat ExtraBold")
        self.assertNotIn("caption_template", matthew)
        self.assertEqual(long["font"], "Montserrat ExtraBold")
        self.assertEqual(long["shape"], "16:9")

    def test_blocks_are_seekable_compositions(self):
        # Old pack templates may still be on disk; they must not be the default.
        md = (STYLE / "STYLE.md").read_text()
        self.assertIn("replica", md.lower())
        self.assertIn("do not fire the old template stack", md.lower())
        for name in BLOCKS:
            self.assertTrue((STYLE / "templates" / name / f"{name}.html").is_file())
        capsule = STYLE / "templates" / "capsule"
        self.assertTrue((capsule / "captions.js").is_file())
        self.assertTrue((capsule / "captions.css").is_file())
        self.assertTrue((STYLE / "fonts" / "Outfit-Bold.ttf").is_file())

    def test_instructions_cover_creative_asks_new_styles_and_render_phrases(self):
        agents = (ROOT / "AGENTS.md").read_text()
        graphics = (ROOT / "skills" / "graphics" / "SKILL.md").read_text()
        style = (ROOT / "skills" / "style" / "SKILL.md").read_text()
        edit = (ROOT / "skills" / "edit-short" / "SKILL.md").read_text()
        episode = (ROOT / "skills" / "episode" / "SKILL.md").read_text()
        readme = (ROOT / "README.md").read_text()
        for text in (agents, graphics, edit):
            self.assertIn("replica", text.lower())
        self.assertIn("quality gate", graphics.lower())
        self.assertIn("do not auto-place", edit.lower())
        self.assertIn("one default look", agents.lower())
        self.assertIn("preferences layer on top", agents.lower())
        self.assertIn("look good every time", agents.lower())
        self.assertIn("find-in-page", graphics.lower())
        self.assertIn("1.5s", graphics.lower())
        self.assertIn("accept_asr_mismatch", edit)
        self.assertIn("copy this reference video", style.lower())
        self.assertIn("preferences.json", style)
        for text in (agents, edit, episode, readme):
            self.assertIn("render them", text.lower())
            self.assertIn("render 3 and 5", text.lower())
        self.assertNotIn("just finish", episode.lower())
        self.assertFalse((ROOT / "docs" / "remote-access.md").exists())
        self.assertNotIn("remote-access.md", readme)
        self.assertNotIn("go crazy", agents.lower())
        self.assertNotIn("premium-motion", agents.lower())
        self.assertIn("2.3.1", (ROOT / "CHANGELOG.md").read_text())
        self.assertEqual(json.loads((ROOT / "plugin.json").read_text())["version"], "2.3.2")
        self.assertEqual(json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text())["version"], "2.3.2")



class PreferenceOverlayTests(unittest.TestCase):
    def test_preferences_overlay_captions_only(self):
        import tempfile
        import quick_edit as qe
        self.assertIn("highlight_color", qe.PREF_KEYS)
        self.assertNotIn("frame_layout", qe.PREF_KEYS)
        self.assertNotIn("logos", qe.PREF_KEYS)
        with tempfile.TemporaryDirectory() as d:
            pref = Path(d) / "preferences.json"
            pref.write_text(json.dumps({
                "highlight_color": "#DC143C",
                "font": "Montserrat ExtraBold",
                "frame_layout": "should-be-ignored",
                "logos": {"enabled": True},
            }))
            got = qe.load_preferences(str(pref))
            self.assertEqual(got["highlight_color"], "#DC143C")
            self.assertEqual(got["font"], "Montserrat ExtraBold")
            self.assertNotIn("frame_layout", got)
            self.assertNotIn("logos", got)


if __name__ == "__main__":
    unittest.main()
