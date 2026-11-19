"""HyperFrames' own skills: bin/kit prepare installs them, nothing treats them as a clash, and the instructions route to
them (talking-head edits stay on bin/kit). No network: the HyperFrames calls are faked."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
import kit

UPSTREAM = ["figma", "hyperframes", "hyperframes-cli", "hyperframes-registry", "media-use", "remotion-to-hyperframes",
            "reverse-any-video", "slideshow", "style-sampling"]


def skill(home: Path, where: str, name: str):
    d = home / where / "skills" / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(f"---\nname: {name}\n---\n")


def lock(home: Path, names, extra=None):
    """The record HyperFrames' installer keeps of what it installed."""
    rows = {n: {"source": "heygen-com/hyperframes", "sourceUrl": "https://github.com/heygen-com/hyperframes.git"} for n in names}
    (home / ".agents").mkdir(exist_ok=True)
    (home / ".agents" / ".skill-lock.json").write_text(json.dumps({"version": 3, "skills": {**rows, **(extra or {})}}))


def fake_hf(home: Path, kit_env_home=None):
    """render_hf as cmd_prepare sees it: the pinned CLI, and the kit's usual env (skills skipped)."""
    return SimpleNamespace(hf=lambda: ["npx", "--yes", "hyperframes@0.9.39"], hf_version=lambda: "0.9.39",
                           env=lambda: {"HOME": str(kit_env_home or home), "HYPERFRAMES_SKIP_SKILLS": "1"})


class PrepareInstallsSkillsTests(unittest.TestCase):
    def prepare(self, home, hfr, call):
        out = StringIO()
        with patch.object(kit.Path, "home", lambda: home), patch.object(kit, "hfm", lambda: hfr), \
                patch.object(kit.subprocess, "call", call), patch.dict(os.environ, {}, clear=False), redirect_stdout(out):
            os.environ.pop("XDG_STATE_HOME", None)
            code = kit.cmd_prepare(SimpleNamespace())
        return code, out.getvalue()

    def test_prepare_runs_the_hyperframes_installer_with_skills_allowed(self):
        with tempfile.TemporaryDirectory() as d:
            home, calls = Path(d), []
            def call(cmd, **kw):
                calls.append((cmd, kw))
                if cmd[-1] == "skills":   # what HyperFrames' installer leaves behind
                    for n in UPSTREAM: skill(home, ".agents", n)
                    lock(home, UPSTREAM)
                return 0
            code, out = self.prepare(home, fake_hf(home), call)
            self.assertEqual(code, 0)
            self.assertEqual([c[0][3:] for c in calls], [["--version"], ["browser", "ensure"], ["skills"]])
            self.assertTrue(all(c[0][:3] == ["npx", "--yes", "hyperframes@0.9.39"] for c in calls))   # the pinned release
            self.assertEqual(calls[0][1]["env"].get("HYPERFRAMES_SKIP_SKILLS"), "1")   # every other call still skips them
            self.assertNotIn("HYPERFRAMES_SKIP_SKILLS", calls[2][1]["env"])
            for n in UPSTREAM: self.assertIn(n, out)
            self.assertIn("~/.agents/skills", out)

    def test_a_failed_skills_install_never_stops_prepare(self):
        for fail in (lambda: 1, lambda: (_ for _ in ()).throw(subprocess.TimeoutExpired("npx", 900)),
                     lambda: (_ for _ in ()).throw(OSError("no npx"))):
            with tempfile.TemporaryDirectory() as d:
                home = Path(d)
                code, out = self.prepare(home, fake_hf(home), lambda cmd, **kw: fail() if cmd[-1] == "skills" else 0)
                self.assertEqual(code, 0)
                self.assertIn("HyperFrames 0.9.39 and its Chrome are ready", out)
                self.assertIn("couldn't install HyperFrames' own skills", out)

    def test_sandboxed_home_is_not_installed_into(self):
        with tempfile.TemporaryDirectory() as d:
            home, calls = Path(d) / "home", []
            home.mkdir()
            hfr = fake_hf(home, kit_env_home=Path(d) / "kit" / ".cache" / "home")   # render_hf.env() inside a sandbox
            code, out = self.prepare(home, hfr, lambda cmd, **kw: calls.append(cmd) or 0)
            self.assertEqual(code, 0)
            self.assertNotIn(["skills"], [c[3:] for c in calls])
            self.assertIn("sandbox", out)

    def test_update_refreshes_them_through_prepare_and_touches_no_tracked_file(self):
        src = (ROOT / "engine" / "kit.py").read_text()
        self.assertIn("cmd_prepare(a)", src.split("def cmd_update", 1)[1].split("\ndef ", 1)[0])
        self.assertIn("install_hf_skills(hfr)", src.split("def cmd_prepare", 1)[1].split("\ndef ", 1)[0])
        body = src.split("def install_hf_skills", 1)[1].split("\ndef ", 1)[0]
        self.assertNotIn("KIT", body)   # the installer writes under the home folder only: git pull stays clean
        tracked = subprocess.run(["git", "-C", str(ROOT), "ls-files", ".agents", ".claude", ".codex"], capture_output=True, text=True).stdout
        self.assertNotIn("skills/", tracked)


class NotAClashTests(unittest.TestCase):
    def test_hyperframes_skills_are_never_listed_as_clashes(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            for n in UPSTREAM + ["hyperframes-animation", "edit-short", "writing-linkedin-posts"]: skill(home, ".agents", n)
            for n in ("hyperframes", "media-use", "video-qa"): skill(home, ".codex", n)
            lock(home, UPSTREAM, {"writing-linkedin-posts": {"source": "someone/else"}})
            with patch.object(kit.Path, "home", lambda: home), patch.dict(os.environ, {}, clear=False):
                os.environ.pop("XDG_STATE_HOME", None)
                others = [o.split(" ")[0] for o in kit.other_skills()]
                mine = kit.hf_skills()
            self.assertEqual(sorted(others), ["edit-short", "video-qa"])
            self.assertEqual(mine, sorted(UPSTREAM + ["hyperframes-animation"]))

    def test_no_lock_file_still_knows_hyperframes_by_name(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            for n in ("hyperframes", "hyperframes-cli", "media-use", "episode"): skill(home, ".agents", n)
            with patch.object(kit.Path, "home", lambda: home):
                self.assertEqual([o.split(" ")[0] for o in kit.other_skills()], ["episode"])
                self.assertEqual(kit.hf_skills(), ["hyperframes", "hyperframes-cli", "media-use"])


class InstructionTests(unittest.TestCase):
    def test_setup_keeps_only_the_old_kit_clash(self):
        setup = (ROOT / "skills" / "setup" / "SKILL.md").read_text()
        step8 = next(l for l in setup.splitlines() if l.startswith("8. "))
        self.assertIn("matthew-edit-kit", step8)
        self.assertNotIn("codex-skills-backup", setup)
        self.assertNotIn("media-use or", step8)
        self.assertIn("not a clash", step8)
        self.assertNotIn("move it aside", (ROOT / "engine" / "kit.py").read_text())
        step3 = next(l for l in setup.splitlines() if l.startswith("3. "))
        for n in UPSTREAM: self.assertIn(f"`{n}`", step3)
        self.assertIn("~/.agents/skills", step3)

    def test_graphics_reads_hyperframes_skills_before_building(self):
        g = (ROOT / "skills" / "graphics" / "SKILL.md").read_text()
        self.assertLess(g.index("## Read HyperFrames' skills before you build or restyle"), g.index("## 1. Pick the pieces"))
        for name in ("`hyperframes`", "references/motion.md", "references/look.md", "references/overlays.md", "`hyperframes-registry`",
                     "`hyperframes-animation`", "`hyperframes-creative`", "`hyperframes-keyframes`", "`motion-graphics`"):
            self.assertIn(name, g)
        self.assertIn("bin/kit preview", g)   # the kit's commands, not npx hyperframes, on his videos

    def test_agents_routes_talking_head_to_the_kit_and_the_rest_to_hyperframes(self):
        a = (ROOT / "AGENTS.md").read_text()
        for row in ("`skills/edit-short/SKILL.md`", "`skills/long-form/SKILL.md`", "`skills/graphics/SKILL.md`"):
            self.assertIn(row, a)
        self.assertIn("stay on `bin/kit`", a)
        for word in ("faceless explainer", "standalone motion graphic", "slideshow", "remake of a reference video",
                     "`reverse-any-video` needs a paid HyperFrames Pro login", "~/.agents/skills", "my-styles/RULES.md",
                     "my-styles/preferences.json"):
            self.assertIn(word, a)
        for n in UPSTREAM: self.assertIn(f"`{n}`", a)
        self.assertIn("Never open a kit job with `npx hyperframes preview`", a)

    def test_release_notes(self):
        self.assertIn("## 2.4.2", (ROOT / "CHANGELOG.md").read_text())
        self.assertIn(json.loads((ROOT / "plugin.json").read_text())["version"], ("2.4.2", "2.4.3", "2.4.4"))


if __name__ == "__main__":
    unittest.main()
