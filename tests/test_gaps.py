"""Documents gaps that are still not a selector or an exporter. These tests pass by proving the absence."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
import kit
import notion_index as ni


class GapTests(unittest.TestCase):
    def test_no_automatic_broll_selector(self):
        """library find ranks rows. Draft leaves broll empty. Nothing places a hit into an edit."""
        kit_src = (ROOT / "engine" / "kit.py").read_text()
        index_src = (ROOT / "engine" / "notion_index.py").read_text()
        self.assertIn('"broll": []', kit_src)
        self.assertNotIn("def select_broll", kit_src)
        self.assertNotIn("def select_broll", index_src)
        self.assertEqual(ni.find(ni.empty_index(), "cafe"), [])

    def test_no_automatic_15_second_cut(self):
        """A long run of speech stays long. A 15s Short is still a plan Codex trims by hand."""
        words, t = [], 0.2
        for i in range(30):
            words.append({"w": f"w{i}", "start": t, "end": t + 0.5})
            t += 0.7
        cuts = kit.draft_cuts(words)
        span = cuts[-1]["out"] - cuts[0]["in"]
        self.assertGreater(span, 15)
        self.assertNotIn("def cut_to_short", (ROOT / "engine" / "kit.py").read_text())

    def test_no_capcut_exporter(self):
        """No CapCut project writer, and no CapCut caption path. Trim-export remains a gap."""
        found = []
        for folder in ("engine", "skills", "docs", "graphics"):
            for path in (ROOT / folder).rglob("*"):
                if path.is_file() and "capcut" in path.name.lower():
                    found.append(str(path.relative_to(ROOT)))
                elif path.suffix in {".py", ".md", ".json", ".js"} and path.is_file():
                    if "capcut" in path.read_text(errors="ignore").lower():
                        found.append(str(path.relative_to(ROOT)))
        self.assertEqual(found, [])

    def test_style_upload_does_not_round_trip_style_json(self):
        """Uploading a style file plans one create. It does not read style.json or write Notion."""
        self.assertFalse(hasattr(ni, "import_style"))
        self.assertFalse(hasattr(ni, "push_style"))
        with tempfile.TemporaryDirectory() as d:
            style = Path(d) / "look.json"
            style.write_text(json.dumps({"font_size_frac": 0.08, "highlight_color": "#DC143C"}))
            before = style.read_text()
            layout = {"workspace_id": "workspace-authorized", "hub_id": "hub-authorized",
                      "asset_upload": "authorized_hub", "notion_writeback": False,
                      "roles": {"styles": {"database_id": "db-styles", "title_property": "Name",
                                           "files_property": "Files & media"}}}
            plan = ni.upload_plan(layout, role="styles", title="matthew", local_file=style, origin="own")
            self.assertFalse(plan["write_performed"])
            self.assertEqual(plan["command"], "upload_to_authorized_hub")
            self.assertEqual(plan["properties"], {"Name": "matthew"})
            self.assertNotIn("font_size_frac", plan["properties"])
            self.assertEqual(style.read_text(), before)
            self.assertEqual(plan["schema_columns_added"], [])


if __name__ == "__main__":
    unittest.main()
