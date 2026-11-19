"""Where each word really starts and stops, taken from the sound itself.

The speech model's word times are a guess: a word's end is often set before its last consonant has finished, its
start after its first syllable, or the word is stretched across a silence. Cutting on those times clips words and
hides pauses. `refine` listens to the recording and moves every word's edges to where the sound actually is:
  - out to the real end of the word (through a stop's short closure to its release) and back to its real start, and
  - in off a silence the model stretched the word across.
Edges never move past the neighbouring word's own time, so no word takes another's sound.

`ensure` does this once for a job's words file and marks it (`"edges"`); the model's own times stay beside the new
ones as `start_asr` / `end_asr`. Plans drafted with `"audio_rev": 2` use it (engine/kit.py, engine/timeline.py).
"""
import json
import os
import subprocess

import numpy as np

VERSION = 1
RATE = 16000
HOP = 80                 # 5 ms
FWD = 0.30               # how far past the model's end a word may run (seconds)
BACK = 0.20              # how far before the model's start it may begin
BRIDGE_END = 0.09        # a quiet stretch this short inside a word's end is a stop's closure, not the end
BRIDGE_START = 0.05
MIN_WORD = 0.06          # a word is never shrunk to less than this
MIN_SHRINK = 0.03        # ignore smaller trims: they are within the model's own error
PER_LETTER = 0.06        # a word the model gave less time than this per letter was squeezed (often to no time at all):
                         # its sound lies before the time it was given, so it may reach that much further back


def envelope(clip):
    """Loudness of the recording in 5 ms steps (dB), low rumble removed so a hum does not read as speech."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-i", str(clip), "-map", "0:a:0", "-vn", "-ac", "1",
                          "-ar", str(RATE), "-af", "highpass=f=100", "-f", "f32le", "-"], capture_output=True).stdout
    x = np.frombuffer(raw, dtype="<f4").astype(np.float64)
    n = len(x) // HOP
    if n < 20:
        return None
    p = (x[:n * HOP].reshape(n, HOP) ** 2).mean(axis=1)
    p = (p + np.concatenate([p[1:], p[-1:]])) / 2          # 10 ms window
    return 10 * np.log10(p + 1e-12)


def levels(db):
    """(loud, silent): above `loud` is speech; at or under `silent` is the room's own noise (None when the recording
    is too noisy to tell, and then no word is ever trimmed)."""
    floor, speech = float(np.percentile(db, 5)), float(np.percentile(db, 90))
    loud = min(max(floor + 8.0, speech - 35.0), speech - 12.0)
    # in a very clean recording the room is far below anything he could hear: 42 dB under his voice counts as silence too
    silent = min(max(floor + 5.0, speech - 42.0), loud - 2.0) if speech - floor >= 24.0 else None
    return loud, silent


QUIET_MIN = 0.08         # silences shorter than this are not listed


def still_mask(db, silent):
    """True where the recording holds nothing but the room. Judged on a 30 ms average, so the room's own flicker
    neither reads as speech nor breaks a silence in two."""
    pw = np.convolve(10 ** (db / 10), np.ones(6) / 6, mode="same")
    return 10 * np.log10(pw + 1e-12) <= silent + 1.0


def quiet_runs(db):
    """Every stretch of the recording with no speech in it, [[start, end], ...] in seconds: the room, a breath, the
    tail of a word dying away. The speech model often hides a pause inside a word (it stretches the next word back
    over it), so pauses are found here, in the sound, not between its words. Judged on a 30 ms average, so one loud
    flicker does not break a pause in two."""
    if db is None:
        return []
    loud, _ = levels(db)
    pw = np.convolve(10 ** (db / 10), np.ones(6) / 6, mode="same")
    still, hop, out, k, n = 10 * np.log10(pw + 1e-12) <= loud, HOP / RATE, [], 0, len(db)
    while k < n:
        if still[k]:
            j = k
            while j < n and still[j]:
                j += 1
            if (j - k) * hop >= QUIET_MIN:
                out.append([round(k * hop, 3), round(j * hop, 3)])
            k = j
        else:
            k += 1
    return out


def quiet(words_file):
    """The silences `ensure` found for a job's words file ([] when it has none)."""
    try:
        return list((json.load(open(words_file)).get("edges") or {}).get("quiet") or [])
    except (OSError, ValueError, AttributeError):
        return []


def refine(words, db):
    """New (start, end) for every word. `words`: [{"start", "end", ...}] in time order, the model's times."""
    if db is None or not words:
        return [(float(w["start"]), float(w["end"])) for w in words]
    loud, silent = levels(db)
    n, hop = len(db), HOP / RATE
    fr = lambda t: max(0, min(n, int(round(t / hop))))
    still = still_mask(db, silent) if silent is not None else None
    out = []
    for i, w in enumerate(words):
        s, e = float(w["start"]), float(w["end"])
        squeezed = max(0.0, PER_LETTER * sum(ch.isalnum() for ch in str(w.get("w") or "")) - (e - s))
        lo = max(0.0, s - BACK - min(squeezed, 0.9), float(words[i - 1]["end"]) if i else 0.0)
        hi = min(n * hop, e + FWD, float(words[i + 1]["start"]) if i + 1 < len(words) else n * hop)
        s2, e2 = s, e
        # the end: out through the sound that follows, across a short closure
        last, quiet = None, 0
        for k in range(fr(e), fr(max(hi, e))):
            if db[k] > loud:
                last, quiet = k, 0
            else:
                quiet += 1
                if quiet * hop > BRIDGE_END:
                    break
        if last is not None:
            e2 = min(max(hi, e), (last + 1) * hop)
        elif still is not None:             # nothing after it: was it stretched over a silence?
            k = min(n, fr(e)) - 1
            while k > fr(s + MIN_WORD) and still[k]:
                k -= 1
            if e - (k + 1) * hop >= MIN_SHRINK:
                e2 = (k + 1) * hop
        # the start: back through the sound before it
        first, quiet = None, 0
        for k in range(fr(s) - 1, fr(min(lo, s)) - 1, -1):
            if k < 0:
                break
            if db[k] > loud:
                first, quiet = k, 0
            else:
                quiet += 1
                if quiet * hop > BRIDGE_START:
                    break
        if first is not None:
            s2 = max(min(lo, s), first * hop)
        elif still is not None:
            k = fr(s)
            while k < min(n, fr(e2 - MIN_WORD)) and still[k]:
                k += 1
            if k * hop - s >= MIN_SHRINK:
                s2 = k * hop
        out.append([min(s2, e2), max(s2, e2)])
    for i in range(1, len(out)):            # two words that reached into the same gap meet at its quietest point
        if out[i][0] < out[i - 1][1]:
            a, b = fr(out[i][0]), max(fr(out[i][0]) + 1, fr(out[i - 1][1]))
            m = (a + int(np.argmin(db[a:b]))) * hop if b <= n else out[i][0]
            m = min(max(m, out[i - 1][0]), out[i][1])
            out[i - 1][1] = out[i][0] = m
    return [(round(a, 3), round(b, 3)) for a, b in out]


def ensure(words_file, clip):
    """Refine a job's words file in place, once. True when the file now holds real edges."""
    try:
        d = json.load(open(words_file))
    except (OSError, ValueError):
        return False
    if not isinstance(d, dict) or not d.get("words"):
        return False
    if (d.get("edges") or {}).get("v") == VERSION:
        return True
    if not os.path.isfile(str(clip)):
        return False
    ws = d["words"]
    for w in ws:                             # always start from the model's own times
        if "start_asr" in w:
            w["start"], w["end"] = w["start_asr"], w["end_asr"]
    db = envelope(clip)
    if db is None:
        return False
    loud, silent = levels(db)
    for w, (a, b) in zip(ws, refine(ws, db)):
        w["start_asr"], w["end_asr"] = w["start"], w["end"]
        w["start"], w["end"] = a, b
    d["edges"] = {"v": VERSION, "loud_db": round(loud, 1), "silent_db": None if silent is None else round(silent, 1),
                  "quiet": quiet_runs(db)}
    tmp = str(words_file) + ".tmp"
    json.dump(d, open(tmp, "w"))
    os.replace(tmp, words_file)
    return True
