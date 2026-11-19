"""The kit keeps itself current, so a fix reaches him without anyone sitting at his Mac.

Once a day, in the background, it looks for a newer kit on GitHub (`git fetch`, nothing else). A newer kit switches in
only at the start of a new edit (`bin/kit draft`, `bin/kit voice`, `bin/kit doctor`), never in the middle of one, and
only as a plain fast-forward: if a kit file was changed on this Mac in a way the update would overwrite, nothing is
touched and the reason is logged (and goes out with the next `bin/kit report`). `my-styles/`, `library/`, `.work/` and
`done/` are not part of the kit's files and are never changed.

Off when he asks: `"auto_update": false` in `my-styles/preferences.json`. `bin/kit update` still updates by hand.
"""
import json
import os
import subprocess
import sys
import time

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(KIT, ".cache", "update")
STATE = os.path.join(D, "state.json")
LOG = os.path.join(KIT, ".cache", "deps", "log.txt")     # the updater log `bin/kit report` already sends
EVERY_S = 24 * 3600
BRANCH = "main"


def _git(*args, timeout=90):
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never")   # never stop to ask for a password
    try:
        r = subprocess.run(["git", "-C", KIT, *args], capture_output=True, text=True, timeout=timeout, env=env,
                           stdin=subprocess.DEVNULL)
        return r.returncode, (r.stdout + r.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, str(e)


def _state():
    try:
        return json.load(open(STATE))
    except (OSError, ValueError):
        return {}


def _save(st):
    os.makedirs(D, exist_ok=True)
    json.dump(st, open(STATE + ".tmp", "w"))
    os.replace(STATE + ".tmp", STATE)


def log(msg):
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} kit: {msg}\n")
    except OSError:
        pass


def enabled():
    if os.environ.get("KIT_NO_AUTO_UPDATE"):
        return False
    try:
        return json.load(open(os.path.join(KIT, "my-styles", "preferences.json"))).get("auto_update") is not False
    except (OSError, ValueError, AttributeError):
        return True


def remote():
    """Where kit releases come from: `upstream` (the official kit) when this clone has one, else `origin`."""
    code, out = _git("remote")
    names = out.split() if code == 0 else []
    return "upstream" if "upstream" in names else ("origin" if "origin" in names else None)


def version():
    try:
        return json.load(open(os.path.join(KIT, "plugin.json"))).get("version", "?")
    except (OSError, ValueError):
        return "?"


def fetch():
    """The daily look, run in the background: fetch the newest kit. Changes no file of the kit."""
    st = _state(); st["last_fetch"] = time.time(); _save(st)
    r = remote()
    if not r:
        return 1
    code, out = _git("fetch", "--quiet", r, BRANCH)
    if code:
        log(f"couldn't look for a newer kit ({out[-200:] or 'no answer'})")
    return code


def pending():
    """The newer kit waiting to switch in (its commit), or None. Only ever a fast-forward of `main`."""
    r = remote()
    if not r or _git("rev-parse", "--abbrev-ref", "HEAD")[1] != BRANCH:
        return None
    code, new = _git("rev-parse", "--verify", "--quiet", f"{r}/{BRANCH}")
    if code or not new:
        return None
    if _git("merge-base", "--is-ancestor", "HEAD", new)[0] != 0 or _git("rev-parse", "HEAD")[1] == new:
        return None
    return new


def apply():
    """Switch a waiting kit in. True when the kit's files changed (the caller starts the command again on them)."""
    new = pending()
    st = _state()
    if not new or st.get("blocked") == new:
        return False
    old = version()
    code, out = _git("merge", "--ff-only", "--quiet", new)
    if code:
        st["blocked"] = new; _save(st)       # say it once, not on every command
        why = "a kit file was changed on this Mac" if "overwritten" in out or "local changes" in out else (out[-200:] or "git refused")
        log(f"a newer kit is waiting but couldn't switch in: {why}. `bin/kit update` shows the details.")
        print(f"NOTE a newer kit is waiting but couldn't switch in by itself ({why}). Run bin/kit update when he asks.")
        return False
    st.pop("blocked", None); st["floor"] = True; _save(st)
    log(f"updated itself {old} -> {version()}")
    print(f"The kit updated itself: {old} -> {version()} (CHANGELOG.md says what changed).", flush=True)
    return True


def after():
    """In the fresh process after an update: bring the outside libraries up to what this kit was tested with."""
    st = _state()
    if not st.pop("floor", None):
        return
    _save(st)
    try:
        import deps
        deps.floor()
    except Exception as e:   # an edit never stops because of this
        log(f"after updating itself: {e}")


def auto(new_edit=False):
    """Called at the start of a command. A waiting kit switches in at the start of a new edit; the daily look runs in
    the background. True when the kit's files just changed."""
    if not enabled():
        return False
    changed = apply() if new_edit else False
    if time.time() - _state().get("last_fetch", 0) >= EVERY_S:
        os.makedirs(D, exist_ok=True)
        try:
            subprocess.Popen([sys.executable, os.path.abspath(__file__), "fetch"], stdin=subprocess.DEVNULL,
                             stdout=open(os.path.join(D, "last-run.txt"), "w"), stderr=subprocess.STDOUT,
                             start_new_session=True)
        except OSError:
            pass
    return changed


if __name__ == "__main__":
    sys.exit(fetch() if sys.argv[1:] == ["fetch"] else 2)
