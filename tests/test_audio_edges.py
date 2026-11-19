"""Cuts follow the sound: word edges, hidden pauses, his own pause limit, and plans drafted before 2.4.3 left alone."""
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
import edges
import tighten


def room(seconds, spans, speech=-25.0, floor=-60.0):
    """A loudness track (5 ms steps): the room, with speech over each (start, end) span."""
    db = np.full(int(seconds / 0.005), floor)
    for a, b in spans:
        db[int(a / 0.005):int(b / 0.005)] = speech
    return db


class WordEdges(unittest.TestCase):
    def test_a_word_ended_early_runs_to_the_end_of_its_sound(self):
        db = room(3, [(0.5, 1.2), (2.0, 2.5)])
        (s, e), _ = edges.refine([{"w": "trash", "start": 0.5, "end": 1.05}, {"w": "next", "start": 2.0, "end": 2.5}], db)
        self.assertAlmostEqual(e, 1.2, delta=0.02)

    def test_a_word_given_no_length_reaches_back_to_its_first_syllable(self):
        db = room(4, [(0.2, 0.6), (1.4, 2.6)])
        ws = [{"w": "three,", "start": 0.2, "end": 0.6}, {"w": "emotional", "start": 2.0, "end": 2.0},
              {"w": "detachment.", "start": 2.0, "end": 2.6}]
        self.assertAlmostEqual(edges.refine(ws, db)[1][0], 1.4, delta=0.02)

    def test_a_word_never_takes_its_neighbours_time(self):
        db = room(3, [(0.5, 2.5)])
        ws = [{"w": "one", "start": 0.5, "end": 1.0}, {"w": "two", "start": 1.0, "end": 1.6}, {"w": "three", "start": 1.6, "end": 2.5}]
        self.assertEqual([tuple(x) for x in edges.refine(ws, db)], [(0.5, 1.0), (1.0, 1.6), (1.6, 2.5)])

    def test_silences_are_listed_from_the_sound(self):
        runs = edges.quiet_runs(room(3, [(0.5, 1.2), (2.0, 2.5)]))
        self.assertTrue(any(abs(a - 1.2) < 0.03 and abs(b - 2.0) < 0.03 for a, b in runs))


class PauseLimit(unittest.TestCase):
    WORDS = [{"w": "cold", "s": 0.1, "e": 0.5}, {"w": "because", "s": 0.5, "e": 1.5}, {"w": "you", "s": 1.5, "e": 1.8}]

    def test_the_kits_own_limit_is_unchanged(self):
        self.assertEqual(tighten.limits({}), (tighten.PAUSE, tighten.PAD, tighten.EDGE))
        self.assertEqual(tighten.limits({"max_pause_s": 0.15})[0], 0.15)

    def test_a_pause_hidden_inside_a_word_is_cut_when_the_sound_says_so(self):
        plan = {"cuts": [{"in": 0.0, "out": 1.9}]}
        same, notes = tighten.tighten_plan(plan, self.WORDS)                       # by the words alone there is no pause
        self.assertEqual(notes, [])
        pause, pad, edge = tighten.limits({"max_pause_s": 0.15})
        new, notes = tighten.tighten_plan(plan, self.WORDS, None, pause, pad, edge, quiet=[[0.6, 1.1]])
        self.assertEqual(len(new["cuts"]), 2)
        left = (new["cuts"][0]["out"] - 0.6) + (1.1 - new["cuts"][1]["in"])     # silence left around the cut
        self.assertLessEqual(left, 0.15)
        self.assertGreater(left, 0.05)


class OlderPlans(unittest.TestCase):
    def test_new_drafts_are_marked_and_older_plans_read_as_before(self):
        import kit
        self.assertEqual(kit.AUDIO_REV, 2)
        self.assertEqual(kit.audio_rev({}), 1)
        self.assertEqual(kit.audio_rev({"audio_rev": 2}), 2)

    def test_the_last_word_keeps_air_for_the_ending_fade(self):
        import kit
        words = [{"w": "it", "start": 1.0, "end": 1.2}, {"w": "works.", "start": 1.2, "end": 1.7}]
        self.assertEqual(kit.draft_cuts(words)[-1]["out"], 1.78)
        self.assertEqual(kit.draft_cuts(words, tail=0.23, duration=5.0)[-1]["out"], 1.93)
        self.assertEqual(kit.draft_cuts(words, tail=0.23, duration=1.8)[-1]["out"], 1.8)


if __name__ == "__main__":
    unittest.main()
