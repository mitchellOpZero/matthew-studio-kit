"""QA thresholds and the render-to-QA handoff. No video, no network, no Notion."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))
import kit
import qa


class ThresholdTests(unittest.TestCase):
    def test_loudness_fails_outside_one_lu(self):
        self.assertEqual(qa.loudness_mark(-14, -14)[0], qa.INFO)
        self.assertEqual(qa.loudness_mark(-15, -14)[0], qa.INFO)
        self.assertEqual(qa.loudness_mark(-13, -14)[0], qa.INFO)
        self.assertEqual(qa.loudness_mark(-15.01, -14)[0], qa.FAIL)
        self.assertEqual(qa.loudness_mark(-12.5, -14)[0], qa.FAIL)

    def test_peak_fails_hotter_than_minus_one(self):
        self.assertEqual(qa.peak_mark(-1.5), qa.INFO)
        self.assertEqual(qa.peak_mark(-1.0), qa.INFO)
        self.assertEqual(qa.peak_mark(-0.99), qa.FAIL)
        self.assertEqual(qa.peak_mark(0.2), qa.FAIL)
        self.assertIsNone(qa.peak_mark(None))

    def test_dead_air_warns_at_one_second_not_a_fifth(self):
        self.assertEqual(qa.dead_air_limit(True), 1.0)
        self.assertEqual(qa.dead_air_limit(False), 1.5)
        self.assertEqual(qa.dead_air_limit(True, 0.4), 0.4)
        self.assertGreater(qa.dead_air_limit(True), 0.35)


class RenderHandoffTests(unittest.TestCase):
    def test_words_are_output_timed_and_dialogue_is_the_voice_stem(self):
        with tempfile.TemporaryDirectory() as d:
            job = Path(d) / "clip"
            (job / "inputs").mkdir(parents=True)
            words = {"words": [
                {"w": "hello", "start": 0.10, "end": 0.40},
                {"w": "um", "start": 0.42, "end": 0.55},
                {"w": "there", "start": 0.58, "end": 0.90},
            ]}
            (job / "inputs" / "words.json").write_text(json.dumps(words))
            cuts = kit.draft_cuts(words["words"])
            edl = {"name": "clip", "style_name": "matthew", "source": "inputs/missing.mp4",
                   "words": "inputs/words.json", "cuts": cuts, "output": {"w": 1080, "h": 1920, "fps": 30}}
            (job / "edl.json").write_text(json.dumps(edl))
            args = kit.qa_extra_args(job)
            self.assertIn("--words", args)
            self.assertNotIn("--dialogue", args)
            self.assertIn("--target-lufs", args)
            self.assertEqual(args[args.index("--target-lufs") + 1], "-14")
            payload = json.loads(Path(args[args.index("--words") + 1]).read_text())
            heard = [w["w"] for w in payload["words"]]
            self.assertEqual(heard, ["hello", "there"])
            self.assertLess(payload["words"][1]["s"], 0.58)
            voice = kit.KIT / ".work" / "_studio" / job.name / "assets"
            voice.mkdir(parents=True, exist_ok=True)
            (voice / "voice.wav").write_bytes(b"")
            studio = voice.parent.parent
            try:
                args = kit.qa_extra_args(job)
                self.assertEqual(args[args.index("--dialogue") + 1], str(voice / "voice.wav"))
            finally:
                import shutil
                shutil.rmtree(studio, ignore_errors=True)



class AsrMismatchTests(unittest.TestCase):
    def test_whisper_gbt_gym_matches_gpt_gemini(self):
        heard = [{"w": "GBT"}, {"w": "gym"}]
        expected = [{"w": "GPT"}, {"w": "Gemini"}]
        self.assertEqual(qa.canon(heard)[0], qa.canon(expected)[0])
        self.assertEqual(qa.canon(heard)[0], ["gpt", "gemini"])

    def test_gym_alone_is_not_gemini(self):
        self.assertEqual(qa.canon(["gym"])[0], ["gym"])
        self.assertEqual(qa.canon(["gbt"])[0], ["gpt"])

    def test_accept_asr_mismatch_downgrades_only_asr_fails(self):
        rep = qa.Report()
        rep.add(qa.FAIL, "captions:missing", "2 spoken word(s) never captioned", 1.0, 1.4, detail="GBT gym")
        rep.add(qa.FAIL, "safe:top", "Text in the top UI zone")
        n = qa.apply_asr_override(rep, "whisper heard GBT gym for GPT Gemini; captions are on screen")
        self.assertEqual(n, 1)
        sev = {i["check"]: i["sev"] for i in rep.items}
        self.assertEqual(sev["captions:missing"], qa.WARN)
        self.assertEqual(sev["safe:top"], qa.FAIL)
        self.assertEqual(rep.count(qa.FAIL), 1)


if __name__ == "__main__":
    unittest.main()
