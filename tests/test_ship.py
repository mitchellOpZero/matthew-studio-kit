"""Shipped behavior Matthew needs: fixture hub, update, and the look. No network and no Notion writes."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
import kit
import notion_index as ni
import notion_sort as ns
import quick_edit as qe


def _schema(title, files):
    body = "<data-source-state>\n" + json.dumps({"schema": {title: {"type": "title"}, files: {"type": "file"}}}) + "\n</data-source-state>"
    return {"content": [{"type": "text", "text": json.dumps({"text": body})}]}


class FixtureHubTests(unittest.TestCase):
    def test_configure_index_find_and_scoped_upload_stay_offline(self):
        layout = ni.detect({
            "workspace_id": "workspace-authorized",
            "hub_id": "hub-authorized",
            "workflow": "posts",
            "roles": {"broll": {"database_id": "db-broll", "data_source_id": "ds-broll",
                                "fetch": _schema("Name", "Files & media"), "view_url": "view://broll-table"}},
        })
        self.assertFalse(layout["notion_writeback"])
        self.assertEqual(layout["asset_upload"], "authorized_hub")
        self.assertEqual(layout["roles"]["broll"]["title_property"], "Name")
        self.assertEqual(layout["roles"]["broll"]["files_property"], "Files & media")
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            clip = root / "cafe.mp4"
            clip.write_bytes(b"fixture-bytes")
            row = {"id": "page-cafe", "role": "broll", "title": "Runway cafe", "body": "Origin: ai. Provenance only, not a licence clearance.",
                   "files": [{"name": "cafe.mp4", "ref": "asset-cafe", "path": str(clip)}]}
            inventory = {"complete_roles": ["broll"], "rows": [row]}
            index = ni.empty_index()
            with patch.object(ni, "media_info", return_value={"width": 720, "height": 1280, "duration": 4, "aspect": "vertical"}), \
                 patch.object(ni, "make_local_poster", return_value=str(clip)):
                ni.refresh(index, layout, inventory, [row], root)
            hits = ni.find(index, "cafe", kind="broll", origin="ai")
            self.assertTrue(hits)
            self.assertEqual(hits[0]["page_id"], "page-cafe")
            self.assertIn("licence", hits[0]["origin_basis"])
            plan = ni.upload_plan(layout, role="broll", title="cafe", local_file=clip, origin="ai",
                                  workspace_id="workspace-authorized", hub_id="hub-authorized")
            self.assertFalse(plan["write_performed"])
            self.assertEqual(plan["workspace_id"], "workspace-authorized")
            self.assertEqual(plan["hub_id"], "hub-authorized")
            with self.assertRaises(ValueError):
                ni.upload_plan(layout, role="broll", title="cafe", local_file=clip, workspace_id="other-workspace")
            bare = ni.detect({"roles": {}})
            self.assertFalse(bare["notion_writeback"])
            self.assertEqual(bare["asset_upload"], "off")
            back = ns.writeback(index, ns.OPT_IN, "page-cafe")
            self.assertEqual(back["patches"], [])
            self.assertFalse(back["notion_writeback"])
            self.assertFalse(back["write_performed"])

    def test_runway_and_mixkit_docs_call_origin_provenance(self):
        docs = (ROOT / "docs" / "NOTION-MCP.md").read_text()
        skill = (ROOT / "skills" / "library" / "SKILL.md").read_text()
        guide = (ROOT / "docs" / "GUIDE.md").read_text()
        setup = (ROOT / "skills" / "setup" / "SKILL.md").read_text()
        sort = (ROOT / "skills" / "sort-my-notion" / "SKILL.md").read_text()
        url = "https://mixkit.co/free-stock-video/"
        for text in (docs, skill):
            self.assertIn(url, text)
            self.assertIn("Runway", text)
            self.assertIn("Mixkit", text)
            self.assertNotIn("Mixit", text)
            self.assertIn("not a licence clearance", text)
        self.assertIn(url, guide)
        self.assertIn("Runway", guide)
        self.assertIn("Mixkit", guide)
        self.assertIn("does not clear the licence", guide)
        self.assertIn("Content page", setup)
        self.assertNotIn("Keychain", setup)
        self.assertIn("not licence clearance", sort)


class UpdateAndLookTests(unittest.TestCase):
    def test_update_is_ff_only_pull_and_styles_and_library_are_gitignored(self):
        src = (ROOT / "engine" / "kit.py").read_text()
        body = src.split("def cmd_update", 1)[1].split("\ndef ", 1)[0]
        self.assertIn('["git", "-C", str(KIT), "pull", "--ff-only"]', body)
        self.assertIn("my-styles/ are safe", body)
        self.assertNotIn("rmtree", body)
        self.assertNotIn("library/", body)
        apply = (ROOT / "engine" / "deps.py").read_text().split("def apply", 1)[1].split("\ndef ", 1)[0]
        self.assertNotIn("my-styles", apply)
        self.assertNotIn("library/", apply)
        ignored = subprocess.run(
            ["git", "-C", str(ROOT), "check-ignore", "-v", "my-styles/saved/style.json", "library/broll/clip.mp4"],
            capture_output=True, text=True, check=True)
        self.assertIn("my-styles/", ignored.stdout)
        self.assertIn("library/*", ignored.stdout)
        readme = (ROOT / "README.md").read_text()
        self.assertIn("update my kit", readme)
        self.assertIn("git pull", readme)

    def test_matthew_look_is_red_one_and_a_half_and_a_modest_punch(self):
        st = json.loads((ROOT / "styles" / "matthew" / "style.json").read_text())
        self.assertEqual(st["highlight_color"], "#DC143C")
        self.assertEqual(st["font_size_frac"], 0.093)
        self.assertAlmostEqual(st["font_size_frac"] / 0.062, 1.5, places=5)
        self.assertGreaterEqual(st["punch"]["zoom_tight"], 1.05)
        self.assertLessEqual(st["punch"]["zoom_tight"], 1.2)
        self.assertEqual(st["punch"]["zoom_tight"], 1.17)
        self.assertTrue(st["kw_sync_pop"])
        render = (ROOT / "engine" / "render_hf.py").read_text()
        self.assertIn('hf() + ["preview"', render)
        self.assertIn('hf() + ["render"', render)
        self.assertIn('highlight_color", "#DC143C"', render)
        preview = (ROOT / "engine" / "kit.py").read_text().split("def cmd_preview", 1)[1].split("\ndef ", 1)[0]
        do_render = (ROOT / "engine" / "kit.py").read_text().split("def cmd_render", 1)[1].split("\ndef ", 1)[0]
        self.assertIn(".preview(", preview)
        self.assertNotIn(".render(", preview)
        self.assertIn(".render(", do_render)

    def test_no_reverse_any_video_skill(self):
        """This kit cuts pauses and previews in HyperFrames. It does not clone or reverse an arbitrary video."""
        names = [p.name.lower() for p in (ROOT / "skills").iterdir() if p.is_dir()]
        self.assertFalse(any("reverse" in name for name in names))
        self.assertIn("edit-short", names)
        self.assertTrue(hasattr(kit, "draft_cuts"))
        self.assertIn("def draft_cuts", (ROOT / "engine" / "kit.py").read_text())


if __name__ == "__main__":
    unittest.main()
