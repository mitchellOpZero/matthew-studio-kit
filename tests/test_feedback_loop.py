"""Reports reach Mitchell (webhook or the official kit), carry no footage, and the kit only ever fast-forwards itself."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
import report
import selfupdate


class Reports(unittest.TestCase):
    def test_a_webhook_on_the_mac_wins_and_is_never_in_the_kit_folder(self):
        self.assertNotIn(str(ROOT), str(report.WEBHOOK))
        with mock.patch.dict(os.environ, {"KIT_REPORT_WEBHOOK": "https://example.invalid/hook", "KIT_REPORT_BEARER": "t"}):
            self.assertEqual(report.webhook(), {"url": "https://example.invalid/hook", "bearer": "t"})

    def test_the_report_is_posted_as_text_with_the_token_in_the_header_only(self):
        seen = {}

        class Answer:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *a): return False

        def fake(req, timeout=0):
            seen.update(url=req.full_url, auth=req.get_header("Authorization"), body=req.data.decode())
            return Answer()

        with mock.patch("urllib.request.urlopen", fake):
            self.assertEqual(report.post({"url": "https://example.invalid/hook", "bearer": "abc"}, "kit report: x", "body"), "")
        self.assertEqual(seen["auth"], "Bearer abc")
        self.assertNotIn("abc", seen["body"])
        self.assertIn("kit report: x", seen["body"])

    def test_job_facts_describe_the_plan_without_his_words(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(report, "KIT", Path(tmp)):
            job = Path(tmp) / ".work" / "demo"
            job.mkdir(parents=True)
            (job / "edl.json").write_text(json.dumps({"audio_rev": 2, "cuts": [{"in": 0, "out": 2.5}], "style_name": "default",
                                                      "blocks": [{"name": "headline-slam", "vars": {"text": "his secret line"}}],
                                                      "audio": {"pre": "atrim=start_sample=1200"}}))
            facts = "\n".join(report.job_facts("demo"))
        self.assertIn("audio_rev 2", facts)
        self.assertIn("headline-slam", facts)
        self.assertIn("audio.pre", facts)
        self.assertNotIn("his secret line", facts)

    def test_reports_go_to_the_official_kit_not_the_macs_own_fork(self):
        def fake(cmd, **kw):
            url = {"upstream": "https://github.com/mitchellOpZero/matthew-studio-kit.git", "origin": "https://github.com/someone/fork.git"}[cmd[-1]]
            return subprocess.CompletedProcess(cmd, 0, url + "\n", "")
        with mock.patch("subprocess.run", fake):
            self.assertEqual(report.repo(), "mitchellOpZero/matthew-studio-kit")


class SelfUpdate(unittest.TestCase):
    def test_off_when_he_asks_or_when_a_kit_command_runs_another(self):
        with mock.patch.dict(os.environ, {"KIT_NO_AUTO_UPDATE": "1"}):
            self.assertFalse(selfupdate.enabled())

    def test_only_a_fast_forward_and_never_git_asking_for_a_password(self):
        src = (ROOT / "engine" / "selfupdate.py").read_text()
        self.assertIn('"merge", "--ff-only"', src)
        self.assertIn('GIT_TERMINAL_PROMPT="0"', src)
        for word in ("reset", "stash", "checkout", "clean", "--force"):
            self.assertNotIn(f'"{word}"', src)

    def test_instructions_send_faceless_videos_through_the_voice_command(self):
        text = (ROOT / "AGENTS.md").read_text()
        self.assertIn("bin/kit voice", text)
        self.assertIn("bin/kit report --auto on", text)


if __name__ == "__main__":
    unittest.main()
