"""Sound effects are always there: a soft swipe on every move into and out of b-roll and a graphic, placed by the kit
so nobody has to ask. Sounds the plan already has are kept and win; the kit only fills the moves that have none.

Rules (the ones his approved test Short followed): the swipe starts a beat before the cut, in the gap between words
when there is one; it never starts while another sound is starting; it sits well under his voice.
Off only when he asks: `"sfx_auto": false` in the plan or the style.
"""
import os

LEAD = 0.15      # the swipe starts this long before the picture changes
CLEAR = 0.4      # no two sounds start closer together than this
GAIN_DB = -12.0
SWIPE = ("library/sfx/swipe-soft.wav", "assets/sfx/swipe-soft.wav")   # his own copy first, then the one the kit ships


def enabled(edl, st):
    for src in (edl, st):
        if src.get("sfx_auto") is not None:
            return bool(src["sfx_auto"])
    return True


def swipe_file(kit_dir):
    return next((p for p in (os.path.join(kit_dir, rel) for rel in SWIPE) if os.path.isfile(p)), None)


def moves(broll, blocks, fps, total):
    """Output times (seconds) where the picture changes to or from b-roll or a graphic, merged when they coincide."""
    ts = []
    for item in list(broll) + list(blocks):
        a = item["start"] / fps
        ts += [a, a + item["frames"] / fps]
    out = []
    for t in sorted(ts):
        if t < 0.3 or t > total - 0.3:   # the very start and the very end get no swipe
            continue
        if out and t - out[-1] < 0.25:
            continue
        out.append(t)
    return out


def place(move, words):
    """When the swipe for a picture change at `move` starts: LEAD before it, pushed to the end of a word it would
    otherwise start inside (as long as that is still before the change)."""
    t = move - LEAD
    for w in words:
        if w["s"] < t < w["e"]:
            if w["e"] <= move + 0.05:
                t = w["e"]
            break
    return max(0.0, t)


def auto_times(broll, blocks, words, taken, fps, total):
    """Start times for the kit's own swipes. `taken`: start times (seconds) of sounds the plan already has."""
    used = sorted(taken)
    out = []
    for m in moves(broll, blocks, fps, total):
        t = place(m, words)
        if any(abs(t - u) < CLEAR or abs(m - u) < CLEAR for u in used):
            continue
        out.append(round(t, 3)); used.append(t)
    return out
