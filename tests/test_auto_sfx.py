"""2.3.9: sound effects are always there (the kit adds swipes on b-roll and graphic moves), b-roll is the default,
and captions over a full-screen graphic stay readable."""
import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
import auto_sfx as ax

FPS = 30
WORDS = [{"w": "a", "s": 4.6, "e": 5.05}, {"w": "b", "s": 5.33, "e": 5.9}, {"w": "c", "s": 6.0, "e": 7.03},
         {"w": "d", "s": 7.35, "e": 9.9}, {"w": "e", "s": 9.95, "e": 12.0}]
BROLL = [{"start": 161, "frames": 54}]          # 5.37 s to 7.17 s
BLOCKS = [{"start": 215, "frames": 79}]         # 7.17 s to 9.80 s


class AutoSfxTests(unittest.TestCase):
    def test_a_swipe_on_each_move_in_the_gap_before_it(self):
        ts = ax.auto_times(BROLL, BLOCKS, WORDS, [], FPS, 30.0)
        self.assertEqual(len(ts), 3)                       # into b-roll, b-roll to graphic (one move), out of the graphic
        self.assertAlmostEqual(ts[0], 5.22, places=2)      # 0.15 s before the cut, in the gap after "a"
        self.assertAlmostEqual(ts[1], 7.03, places=2)      # would start inside "c": pushed to where "c" ends
        self.assertTrue(all(b - a >= ax.CLEAR for a, b in zip(ts, ts[1:])))

    def test_sounds_already_in_the_plan_win(self):
        ts = ax.auto_times(BROLL, BLOCKS, WORDS, [5.18, 7.04], FPS, 30.0)
        self.assertEqual(len(ts), 1)                       # only the move the plan left silent
        self.assertGreater(ts[0], 9.0)

    def test_no_swipe_at_the_very_start_or_end(self):
        self.assertEqual(ax.auto_times([{"start": 0, "frames": 60}], [], [], [], FPS, 2.1), [])

    def test_it_is_on_unless_he_asks_for_none(self):
        self.assertTrue(ax.enabled({}, {}))
        self.assertFalse(ax.enabled({"sfx_auto": False}, {}))
        self.assertFalse(ax.enabled({}, {"sfx_auto": False}))
        self.assertTrue(ax.enabled({"sfx_auto": True}, {"sfx_auto": False}))   # the plan's word wins

    def test_the_kit_ships_his_approved_sounds(self):
        for f in ("swipe-soft.wav", "ui-pop.wav", "ui-tick.wav"):
            self.assertTrue((ROOT / "assets" / "sfx" / f).is_file(), f)
        self.assertTrue(ax.swipe_file(str(ROOT)).endswith("swipe-soft.wav"))

    def test_docs_make_broll_and_sound_the_default(self):
        agents = (ROOT / "AGENTS.md").read_text()
        self.assertIn("B-roll on most Shorts", agents)
        self.assertIn("Sound effects always", agents)
        self.assertNotIn("B-roll only when he asks", agents)
        self.assertNotIn("B-roll only when he asks", (ROOT / "styles" / "default" / "STYLE.md").read_text())
        self.assertIn("2.3.9", (ROOT / "CHANGELOG.md").read_text())

    def test_captions_over_a_full_screen_graphic_get_a_halo(self):
        src = (ROOT / "engine" / "render_hf.py").read_text()
        self.assertIn(".ongfx .w", src)
        self.assertIn('b.get("show") == "cutaway"', src)


if __name__ == "__main__":
    unittest.main()
