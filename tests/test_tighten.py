"""2.3.8: repeated takes and long pauses are cut by the kit itself, at draft and at every preview, and everything timed
after a removed stretch stays on the same words."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
import kit
import tighten as tg


def words(*spans):
    return [{"w": f"w{i}", "s": s, "e": e} for i, (s, e) in enumerate(spans)]


# he talks 0-1.0, pauses 0.6 s, talks 1.6-2.4, says a line at 3.0-3.5 then restarts it at 3.8, ends at 5.0
WORDS = words((0.0, 0.4), (0.45, 1.0), (1.6, 2.0), (2.05, 2.4), (2.5, 2.9), (3.0, 3.5), (3.8, 4.3), (4.35, 5.0))
RESTART = [{"text": "w5", "first_start": 3.0, "first_end": 3.5, "retake_start": 3.8}]


def gaps_inside(edl, ws):
    out = []
    for c in edl["cuts"]:
        inside = [(w["s"], w["e"]) for w in ws if w["s"] >= c["in"] - 1e-3 and w["e"] <= c["out"] + 1e-3]
        out += [round(b[0] - a[1], 3) for a, b in zip(inside, inside[1:])]
    return out


class TightenTests(unittest.TestCase):
    def test_a_pause_merged_back_into_a_piece_is_cut_again(self):
        edl = {"cuts": [{"in": 0.0, "out": 2.45, "zoom": 1.3}]}
        new, notes = tg.tighten_plan(edl, WORDS, [])
        self.assertEqual([(c["in"], c["out"]) for c in new["cuts"]], [(0.0, 1.08), (1.52, 2.45)])
        self.assertTrue(all(c["zoom"] == 1.3 for c in new["cuts"]))   # a split piece keeps its settings
        self.assertTrue(all(g <= tg.PAUSE for g in gaps_inside(new, WORDS)))
        self.assertIn("tightened 1 pause", "; ".join(notes))
        self.assertEqual(edl["cuts"], [{"in": 0.0, "out": 2.45, "zoom": 1.3}])   # the plan passed in is not changed

    def test_a_restart_keeps_only_the_last_take(self):
        edl = {"cuts": [{"in": 2.45, "out": 5.08}]}
        new, notes = tg.tighten_plan(edl, WORDS, RESTART)
        self.assertEqual([(c["in"], c["out"]) for c in new["cuts"]], [(2.45, 3.0), (3.72, 5.08)])
        self.assertIn("cut 1 repeated take", "; ".join(notes))

    def test_a_restart_already_cut_out_changes_nothing(self):
        edl = {"cuts": [{"in": 2.45, "out": 2.98}, {"in": 3.72, "out": 5.08}]}
        new, notes = tg.tighten_plan(edl, WORDS, RESTART)
        self.assertEqual(notes, [])
        self.assertIs(new, edl)

    def test_running_it_twice_changes_nothing_more(self):
        edl = {"cuts": [{"in": 0.0, "out": 5.08}]}
        once, notes = tg.tighten_plan(edl, WORDS, RESTART)
        self.assertTrue(notes)
        twice, again = tg.tighten_plan(once, WORDS, RESTART)
        self.assertEqual(again, [])
        self.assertEqual(twice["cuts"], once["cuts"])

    def test_graphics_broll_and_sounds_stay_on_the_same_words(self):
        # one piece 0-5.08; the pause (1.08-1.52, 0.44 s) and the first take (3.0-3.72, 0.72 s) come out
        edl = {"cuts": [{"in": 0.0, "out": 5.08}], "broll": [{"file": "x.mp4", "at": 0.5, "dur": 0.4}],
               "blocks": [{"name": "imessage-chat", "at": 2.05}], "sfx": [{"file": "s.wav", "at": 4.35}],
               "overlays": [{"picture": "p.png", "at": 3.3}], "graphics": [{"text": "x", "at": 1.3}],
               "caption_hide": [[2.05, 2.4]]}
        new, _ = tg.tighten_plan(edl, WORDS, RESTART)
        self.assertEqual(new["broll"][0]["at"], 0.5)                 # before anything was removed
        self.assertEqual(new["graphics"][0]["at"], 1.08)             # was inside the pause: lands where the pause was
        self.assertEqual(new["blocks"][0]["at"], round(2.05 - 0.44, 4))
        self.assertEqual(new["overlays"][0]["at"], round(3.0 - 0.44, 4))   # was inside the first take
        self.assertEqual(new["sfx"][0]["at"], round(4.35 - 0.44 - 0.72, 4))
        self.assertEqual(new["caption_hide"], [[round(2.05 - 0.44, 4), round(2.4 - 0.44, 4)]])

    def test_he_can_keep_a_pause_or_a_repeat_on_purpose(self):
        self.assertEqual(tg.tighten_plan({"cuts": [{"in": 0.0, "out": 2.45, "keep_pause": True}]}, WORDS, [])[1], [])
        self.assertEqual(tg.tighten_plan({"cuts": [{"in": 0.0, "out": 2.45}], "keep_pauses": True}, WORDS, [])[1], [])
        kept = tg.tighten_plan({"cuts": [{"in": 2.45, "out": 5.08}], "keep_restarts": True}, WORDS, RESTART)
        self.assertEqual(kept[1], [])

    def test_dead_air_at_the_edges_of_a_piece_is_trimmed(self):
        edl = {"cuts": [{"in": 0.0, "out": 1.35}, {"in": 1.36, "out": 2.45}]}   # 0.35 s after "w1", 0.24 s before "w2"
        new, notes = tg.tighten_plan(edl, WORDS, [])
        self.assertEqual([(c["in"], c["out"]) for c in new["cuts"]], [(0.0, 1.08), (1.52, 2.45)])
        self.assertIn("tightened 2 pauses", "; ".join(notes))
        self.assertEqual(tg.tighten_plan(new, WORDS, [])[1], [])

    def test_an_edge_that_cuts_through_a_word_is_left_alone(self):
        self.assertEqual(tg.tighten_plan({"cuts": [{"in": 0.0, "out": 1.08}, {"in": 1.8, "out": 2.45}]}, WORDS, [])[1], [])

    def test_the_last_pieces_tail_is_left_alone(self):
        self.assertEqual(tg.tighten_plan({"cuts": [{"in": 3.72, "out": 5.6}]}, WORDS, [])[1], [])

    def test_a_restart_that_only_grazes_a_piece_is_left_alone(self):
        self.assertEqual(tg.tighten_plan({"cuts": [{"in": 3.69, "out": 5.08}]}, WORDS, RESTART)[1], [])

    def test_short_gaps_between_words_are_left_alone(self):
        edl = {"cuts": [{"in": 1.52, "out": 3.58}]}   # gaps of 0.05 and 0.1 s only
        self.assertEqual(tg.tighten_plan(edl, WORDS, [])[1], [])

    def test_pieces_put_out_of_order_on_purpose_are_left_alone(self):
        edl = {"cuts": [{"in": 3.72, "out": 5.08}, {"in": 0.0, "out": 2.45}]}
        self.assertEqual(tg.tighten_plan(edl, WORDS, RESTART)[1], [])

    def test_restarts_are_read_from_an_older_jobs_transcript(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "TRANSCRIPT.txt").write_text(
                "RESTARTS HEARD (the transcript below may show these only once). Cut the first take, keep the last:\n"
                "  20.46-20.96  first take  \"she's busy,\"   retake starts 21.26\n\n"
                "   0.05-  0.59  That\n")
            self.assertEqual(tg.transcript_restarts(d), [{"first_start": 20.46, "first_end": 20.96, "text": "she's busy,",
                                                         "retake_start": 21.26}])
            self.assertEqual(tg.transcript_restarts(str(Path(d) / "nope")), [])

    def test_the_job_step_rewrites_the_plan_only_when_something_changed(self):
        with tempfile.TemporaryDirectory() as d:
            job = Path(d)
            (job / "inputs").mkdir()
            (job / "inputs" / "words.json").write_text(json.dumps([{"w": w["w"], "start": w["s"], "end": w["e"]} for w in WORDS]))
            plan = {"words": "inputs/words.json", "cuts": [{"in": 0.0, "out": 5.08}], "restarts": RESTART, "sfx": [{"file": "s.wav", "at": 4.35}]}
            (job / "edl.json").write_text(json.dumps(plan))
            new, notes = kit.tighten_job(job)
            self.assertTrue(notes)
            on_disk = json.loads((job / "edl.json").read_text())
            self.assertEqual(on_disk["cuts"], new["cuts"])
            self.assertEqual(len(on_disk["cuts"]), 3)
            before = (job / "edl.json").read_text()
            self.assertEqual(kit.tighten_job(job)[1], [])
            self.assertEqual((job / "edl.json").read_text(), before)

    def test_docs_say_the_kit_does_it(self):
        skill = (ROOT / "skills" / "edit-short" / "SKILL.md").read_text()
        self.assertIn("bin/kit tighten", skill)
        self.assertIn("keep_pause", skill)
        self.assertIn("2.3.8", (ROOT / "CHANGELOG.md").read_text())


if __name__ == "__main__":
    unittest.main()
