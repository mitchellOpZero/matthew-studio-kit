"""premium-motion, creative instructions, and preview-before-render. No media or network."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))
import kit  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
STYLE = ROOT / "styles" / "premium-motion"
BLOCKS = ("kinetic-label", "stat-count", "callout", "lower-third", "idea-swipe")


class PremiumMotionTests(unittest.TestCase):
    def test_style_validates_and_leaves_the_basics_alone(self):
        st = json.loads((STYLE / "style.json").read_text())
        self.assertEqual(kit.validate_style(st, STYLE), [])
        self.assertEqual(st["caption_template"], "kinetic")
        self.assertEqual(st["font_file"], "Outfit-Bold.ttf")
        matthew = json.loads((ROOT / "styles" / "matthew" / "style.json").read_text())
        long = json.loads((ROOT / "styles" / "matthew-long" / "style.json").read_text())
        self.assertEqual(matthew["font"], "Montserrat ExtraBold")
        self.assertNotIn("caption_template", matthew)
        self.assertEqual(long["font"], "Montserrat ExtraBold")
        self.assertEqual(long["shape"], "16:9")

    def test_blocks_are_seekable_compositions(self):
        for name in BLOCKS:
            html = (STYLE / "templates" / name / f"{name}.html").read_text()
            self.assertIn(f'data-composition-id="{name}"', html)
            self.assertIn("gsap.timeline({ paused: true })", html)
            self.assertIn(f'window.__timelines["{name}"]', html)
            self.assertNotIn("http://", html)
            self.assertNotIn("https://", html)
            self.assertTrue((STYLE / "templates" / name / "assets").is_dir())
        kinetic = STYLE / "templates" / "kinetic"
        self.assertTrue((kinetic / "captions.js").is_file())
        self.assertTrue((kinetic / "captions.css").is_file())
        self.assertTrue((STYLE / "fonts" / "Outfit-Bold.ttf").is_file())

    def test_instructions_cover_creative_asks_new_styles_and_render_phrases(self):
        agents = (ROOT / "AGENTS.md").read_text()
        graphics = (ROOT / "skills" / "graphics" / "SKILL.md").read_text()
        style = (ROOT / "skills" / "style" / "SKILL.md").read_text()
        edit = (ROOT / "skills" / "edit-short" / "SKILL.md").read_text()
        episode = (ROOT / "skills" / "episode" / "SKILL.md").read_text()
        readme = (ROOT / "README.md").read_text()
        for text in (agents, graphics, edit):
            self.assertIn("premium-motion", text)
            self.assertIn("go crazy", text.lower())
        self.assertIn("bin/kit style new", style)
        self.assertIn("keep it, tweak it, or delete it", style)
        self.assertIn("premium-motion", style)
        self.assertIn("reference", style.lower())
        for text in (agents, edit, episode, readme):
            self.assertIn("render them", text.lower())
            self.assertIn("render 3 and 5", text.lower())
        self.assertNotIn("just finish", episode.lower())
        remote = (ROOT / "docs" / "remote-access.md").read_text()
        self.assertIn("Tailscale", remote)
        self.assertIn("Remote Login", remote)
        self.assertIn("System Settings", remote)
        self.assertIn("2.3.0", (ROOT / "CHANGELOG.md").read_text())
        self.assertEqual(json.loads((ROOT / "plugin.json").read_text())["version"], "2.3.0")
        self.assertEqual(json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text())["version"], "2.3.0")


if __name__ == "__main__":
    unittest.main()
