"""Pauses and repeated takes come out of every plan the same way, without anyone asking.

`tighten_plan` rewrites a plan's `cuts` so that:
  - a restart the listener heard (he says a line, then starts it again) keeps only the last take, and
  - no kept piece holds a pause longer than PAUSE between two words (the draft's own rule, enforced again after any
    edit merges pieces back together), or more than EDGE of silence before its first word or after its last one.
Everything timed on the output clock after a removed stretch (b-roll, blocks, sound effects, overlays, text cards,
caption_hide windows) moves earlier by the same amount, so it stays on the same words. Running it twice changes nothing.

Opt-outs, only when he asks for them: `"keep_pauses": true` or `"keep_restarts": true` at the top of the plan, or
`"keep_pause": true` on one piece in `cuts` (a beat he holds on purpose).
"""
import copy
import os
import re

PAUSE = 0.35      # the longest silence left between two words inside a kept piece (seconds); same as the draft
PAD = 0.08        # air kept after the last word and before the next one
EDGE = 0.2        # the longest silence left at the start or end of a kept piece before it is trimmed back to PAD
MIN_PIECE = 0.12  # a sliver shorter than this is dropped rather than kept as its own piece
MIN_RESTART = 0.1 # a restart that only grazes a kept piece (already cut by hand) is left alone
KIT_PAUSE = PAUSE
MIN_PAUSE = 0.1   # his own limit (style or preferences "max_pause_s") is never taken below this
TIMED = ("broll", "blocks", "sfx", "overlays", "graphics")

_RESTART_LINE = re.compile(r"^\s+([\d.]+)-([\d.]+)\s+first take\s+\"(.*)\"\s+retake starts\s+([\d.]+)\s*$")


def limits(st=None):
    """(pause, pad, edge) for a plan: the kit's own unless his style or preferences set "max_pause_s" (the longest
    silence he wants between two words). The air kept around a word shrinks with it, so a cut pause is never left
    longer than his limit, and a piece's own edges are trimmed to the same air."""
    try:
        pause = float((st or {}).get("max_pause_s") or PAUSE)
    except (TypeError, ValueError):
        pause = PAUSE
    if pause >= PAUSE:
        return pause, PAD, EDGE
    pause = max(MIN_PAUSE, pause)
    pad = round(pause / 2 - 0.02, 4)     # a word's last sound fades for a moment after the cut point: leave room for it
    return pause, pad, round(pad + 0.005, 4)


def _span(w):
    return float(w["s"] if "s" in w else w["start"]), float(w["e"] if "e" in w else w["end"])


def transcript_restarts(job_dir):
    """The restarts listed at the top of a job's TRANSCRIPT.txt (plans drafted before 2.3.8 only have them there)."""
    p = os.path.join(job_dir, "TRANSCRIPT.txt")
    out = []
    if not os.path.isfile(p):
        return out
    for line in open(p):
        if not line.strip():
            if out:
                break
            continue
        m = _RESTART_LINE.match(line.rstrip("\n"))
        if m:
            out.append({"first_start": float(m.group(1)), "first_end": float(m.group(2)), "text": m.group(3),
                        "retake_start": float(m.group(4))})
    return out


def _merge(spans):
    out = []
    for a, b, why in sorted(spans):
        if out and a <= out[-1][1] + 1e-6:
            out[-1] = (out[-1][0], max(out[-1][1], b), out[-1][2] if out[-1][2] == why else "pause and restart")
        else:
            out.append((a, b, why))
    return out


def _out_pos(cuts, t):
    """Where source time t sits on the output clock of `cuts` (None when t is not inside a kept piece)."""
    acc = 0.0
    for c in cuts:
        a, b = float(c["in"]), float(c["out"])
        if a - 1e-6 <= t <= b + 1e-6:
            return acc + (t - a)
        acc += b - a
    return None


def tighten_plan(edl, words, restarts=None, pause=PAUSE, pad=PAD, edge=EDGE, quiet=None):
    """(new plan, notes). The plan is returned unchanged, with no notes, when there is nothing to tighten.
    `pause`, `pad`, `edge`: see `limits` (the kit's own values unless he set a limit).
    `quiet`: the recording's real silences (engine/edges.py). With them, a pause is cut wherever the sound stops for
    longer than `pause`, including one the speech model hid inside a word."""
    PAUSE, PAD, EDGE = pause, pad, edge
    # a real silence is shorter than the pause he hears (a word's last sound fades into it), so with his own limit a
    # silence is trimmed as soon as trimming leaves the air around the words whole
    QUIET = PAUSE if PAUSE >= KIT_PAUSE else 2 * PAD + 0.012
    cuts = edl.get("cuts") or []
    if not cuts or not words:
        return edl, []
    if any(float(cuts[i]["in"]) < float(cuts[i - 1]["out"]) - 1e-6 for i in range(1, len(cuts))):
        return edl, []   # pieces re-ordered on purpose: leave the plan alone
    spans = sorted(_span(w) for w in words)
    remove = []
    if edl.get("keep_restarts") is not True:
        for r in restarts if restarts is not None else (edl.get("restarts") or []):
            a, b = float(r["first_start"]), float(r["retake_start"]) - PAD
            if b - a > 0.05:
                remove.append((a, b, "restart"))
    if edl.get("keep_pauses") is not True:
        for c in cuts:
            if c.get("keep_pause"):
                continue
            a, b = float(c["in"]), float(c["out"])
            inside = [(s, e) for s, e in spans if s >= a - 1e-3 and e <= b + 1e-3]
            for (s1, e1), (s2, e2) in zip(inside, inside[1:]):
                if s2 - e1 > PAUSE + 1e-6 and (s2 - PAD) - (e1 + PAD) > 0.012:
                    remove.append((e1 + PAD, s2 - PAD, "pause"))
            for qa, qb in quiet or ():
                lo, hi = max(float(qa), a), min(float(qb), b)
                if hi - lo <= 0:
                    continue
                if lo <= a + 1e-3:                      # silence at the head of the piece
                    if hi - lo > EDGE + 1e-6:
                        remove.append((a, hi - PAD, "pause"))
                elif hi >= b - 1e-3:                    # at its tail (the video's own ending keeps its air)
                    if c is not cuts[-1] and hi - lo > EDGE + 1e-6:
                        remove.append((lo + PAD, b, "pause"))
                elif hi - lo > QUIET + 1e-6 and (hi - PAD) - (lo + PAD) > 0.01:
                    remove.append((lo + PAD, hi - PAD, "pause"))
            if not inside:
                continue
            # dead air at a piece's edges, unless the edge cuts through a word (then the edge is someone's choice)
            if inside[0][0] - a > EDGE + 1e-6 and not any(s < a < e for s, e in spans):
                remove.append((a, inside[0][0] - PAD, "pause"))
            if c is not cuts[-1] and b - inside[-1][1] > EDGE + 1e-6 and not any(s < b < e for s, e in spans):
                remove.append((inside[-1][1] + PAD, b, "pause"))
    if not remove:
        return edl, []

    new_cuts, taken = [], []   # taken: (output time on the old clock where it started, seconds removed, why)
    for c in cuts:
        a, b = float(c["in"]), float(c["out"])
        parts, cur = [], a
        for ra, rb, why in _merge(remove):
            ra, rb = max(ra, a), min(rb, b)
            if rb - ra <= 1e-6 or rb <= cur or (why == "restart" and rb - ra < MIN_RESTART):
                continue
            if ra - cur >= MIN_PIECE:
                parts.append((cur, ra))
            elif ra > cur:   # a sliver before the removed stretch goes with it
                ra = cur
            taken.append((_out_pos(cuts, ra), rb - ra, why))
            cur = rb
        if b - cur >= MIN_PIECE:
            parts.append((cur, b))
        elif b > cur:
            taken.append((_out_pos(cuts, cur), b - cur, "pause"))
        for x, y in parts:
            new_cuts.append(dict(copy.deepcopy(c), **{"in": round(x, 4), "out": round(y, 4)}))
    taken = [(t, n, why) for t, n, why in taken if t is not None and n > 1e-6]
    if not taken or not new_cuts:
        return edl, []

    def moved(t):
        t = float(t)
        shift = 0.0
        for at, n, _ in taken:
            if t >= at + n:
                shift += n
            elif t > at:
                shift += t - at
        return round(t - shift, 4)

    out = copy.deepcopy(edl)
    out["cuts"] = new_cuts
    for key in TIMED:
        for item in out.get(key) or []:
            if isinstance(item, dict) and item.get("at") is not None:
                item["at"] = moved(item["at"])
    if out.get("caption_hide"):
        out["caption_hide"] = [[moved(a), moved(b)] for a, b in out["caption_hide"]]
    n_restart = sum(1 for _, _, why in taken if "restart" in why)
    n_pause = len(taken) - n_restart
    saved = sum(n for _, n, _ in taken)
    notes = []
    if n_restart:
        notes.append(f"cut {n_restart} repeated take{'s' if n_restart != 1 else ''} (kept the last one)")
    if n_pause:
        notes.append(f"tightened {n_pause} pause{'s' if n_pause != 1 else ''}")
    notes.append(f"{saved:.1f} s shorter; b-roll, graphics and sounds after them moved earlier to stay on the same words")
    return out, notes
