"""Cuts and caption breaks. No media, network, or Notion."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))
import kit
import quick_edit as qe


def word(text, start, end):
    return {"w": text, "start": start, "end": end}


class CutTests(unittest.TestCase):
    def test_short_filler_is_cut_out(self):
        words = [word("hello", 0.10, 0.40), word("um", 0.42, 0.55), word("there", 0.58, 0.90)]
        cuts = kit.draft_cuts(words)
        self.assertGreaterEqual(len(cuts), 2)
        self.assertFalse(any(c["in"] < 0.50 < c["out"] for c in cuts))
        for w in (words[0], words[2]):
            self.assertTrue(any(c["in"] <= w["start"] and c["out"] >= w["end"] for c in cuts))

    def test_removed_pause_rejoins_near_a_fifth_of_a_second(self):
        words = [word("hello", 0.10, 0.40), word("there", 0.90, 1.20)]
        cuts = kit.draft_cuts(words)
        self.assertEqual(len(cuts), 2)
        handle = (cuts[0]["out"] - 0.40) + (0.90 - cuts[1]["in"])
        self.assertGreaterEqual(handle, 0.14)
        self.assertLessEqual(handle, 0.20)
        self.assertLessEqual(cuts[0]["out"], words[1]["start"])

    def test_no_cut_inside_a_kept_word(self):
        words = [word("alpha", 0.20, 0.50), word("uh", 0.55, 0.70), word("beta", 1.40, 1.70), word("gamma", 1.78, 2.10)]
        cuts = kit.draft_cuts(words)
        for i, c in enumerate(cuts):
            self.assertLess(c["in"], c["out"])
            if i:
                self.assertLessEqual(cuts[i - 1]["out"], c["in"])
        for w in words:
            if kit.norm(w["w"]) in kit.FILLERS:
                self.assertFalse(any(c["in"] < (w["start"] + w["end"]) / 2 < c["out"] for c in cuts))
            else:
                self.assertTrue(any(c["in"] <= w["start"] + 1e-3 and c["out"] >= w["end"] - 1e-3 for c in cuts))

    def test_pause_at_or_under_0_35_stays_and_words_are_not_clipped(self):
        """Pauses of 0.35s or less are one piece on purpose. A longer gap is cut, with the words still whole."""
        kept = [word("hello", 1.00, 1.30), word("there", 1.65, 1.95)]
        self.assertEqual(len(kit.draft_cuts(kept)), 1)
        self.assertAlmostEqual(1.65 - 1.30, 0.35)
        split = [word("hello", 1.00, 1.30), word("there", 1.66, 1.96)]
        cuts = kit.draft_cuts(split)
        self.assertEqual(len(cuts), 2)
        for w in split:
            self.assertTrue(any(c["in"] <= w["start"] and c["out"] >= w["end"] for c in cuts))

    def test_keywords_skip_fillers_and_stop_words(self):
        words = [word("the", 0, 0.2), word("um", 0.2, 0.3), word("confidence", 0.3, 0.8),
                 word("to", 0.8, 1.0), word("50%", 1.0, 1.3), word("youtube", 1.3, 1.8)]
        keys = {kit.norm(k) for k in kit.draft_keywords(words)}
        self.assertIn("confidence", keys)
        self.assertIn("youtube", keys)
        self.assertNotIn("the", keys)
        self.assertNotIn("um", keys)
        self.assertNotIn("to", keys)


class CaptionTests(unittest.TestCase):
    def test_percent_stays_with_the_number(self):
        st = qe.load_style("matthew")
        ow, t = [], 0.0
        for text, dur in (("save", 0.3), ("50", 0.2), ("%", 0.1), ("more", 0.3)):
            ow.append({"w": text, "ss": t, "s": t, "e": t + dur, "piece_end": 10})
            t += dur + 0.02
        chunks, _ = qe.caption_chunks(ow, t + 1, {"caption_breaks": []}, st)
        lines = [[w["w"] for w in c] for c, _, _ in chunks]
        self.assertTrue(any(line[:2] == ["50", "%"] or line[-2:] == ["50", "%"] for line in lines))
        self.assertFalse(any(line and line[0] == "%" for line in lines))

    def test_percent_token_is_not_rewritten(self):
        st = qe.load_style("matthew")
        ow = [{"w": "50%", "ss": 0.0, "s": 0.0, "e": 0.4, "piece_end": 2},
              {"w": "off", "ss": 0.4, "s": 0.42, "e": 0.7, "piece_end": 2}]
        chunks, _ = qe.caption_chunks(ow, 2, {"caption_breaks": []}, st)
        shown = " ".join(w["w"] for c, _, _ in chunks for w in c)
        self.assertIn("50%", shown)
        self.assertNotIn("50%%", shown)

    def _lines(self, texts, **style):
        st = qe.load_style("matthew")
        st.update(style)
        ow, t = [], 0.0
        for text in texts:
            ow.append({"w": text, "ss": t, "s": t, "e": t + 0.25, "piece_end": 30})
            t += 0.27
        chunks, _ = qe.caption_chunks(ow, t + 1, {"caption_breaks": []}, st)
        return [[w["w"] for w in c] for c, _, _ in chunks]

    def test_clause_break_before_conjunction_and_after_comma(self):
        # min_chunk_s is longer than the first word, so a word-wrap joiner would glue "store," back onto "and".
        lines = self._lines(["store,", "and", "bought", "milk."], max_words=8, max_chars=80, min_chunk_s=1.0, gap_break_s=5)
        self.assertEqual(lines[0], ["store,"])
        self.assertEqual(lines[1][0], "and")
        bare = self._lines(["store", "and", "bought"], max_words=8, max_chars=80, min_chunk_s=1.0, gap_break_s=5)
        self.assertEqual(bare[0], ["store"])
        self.assertEqual(bare[1][0], "and")

    def test_word_wrap_still_splits_a_clause_on_the_word_limit(self):
        lines = self._lines(["one", "two", "three", "four"], max_words=2, max_chars=40, min_chunk_s=0.05, gap_break_s=5)
        self.assertEqual(lines, [["one", "two"], ["three", "four"]])

    def test_punch_split_lands_on_a_word_gap(self):
        st = qe.load_style("matthew")
        words = [{"w": "one", "s": 0.2, "e": 0.6}, {"w": "two", "s": 2.4, "e": 2.9}, {"w": "three", "s": 4.8, "e": 5.4}]
        pieces = qe.build_pieces({"cuts": [{"in": 0.0, "out": 6.0}]}, words, st, fps=30)
        self.assertGreaterEqual(len(pieces), 2)
        for a, b, *_ in pieces:
            for w in words:
                self.assertFalse(w["s"] < a < w["e"] or w["s"] < b < w["e"])


if __name__ == "__main__":
    unittest.main()
