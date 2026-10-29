"""Restart listener: re-hear speech in short pieces so restarts the long pass drops are heard.

A full-clip Whisper pass writes "so hiring, so hiring" down once. The same model on <= 8 s pieces of speech,
with no context carried over, hears both takes. This pass is only used to FIND restarts (kit draft hints,
QA sound:repeat); captions and cut times still come from the main transcript.
"""
from __future__ import annotations

import subprocess

import numpy as np

SR = 16000
MAX_PIECE_S = 8.0
VERBATIM = "Umm, so, so I I mean, let me, let me say, uh, it can take, it can take up to, like, two, two days."


def load_audio(path: str) -> np.ndarray:
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-i", str(path), "-vn", "-ac", "1", "-ar", str(SR),
                          "-f", "f32le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(pcm, np.float32).copy()


def speech_pieces(audio: np.ndarray, max_s: float = MAX_PIECE_S) -> list[tuple[int, int]]:
    """Voice-activity spans grouped into pieces of at most max_s seconds, split only at silences."""
    from faster_whisper.vad import VadOptions, get_speech_timestamps

    # max_speech_duration_s: an edited video has no pauses left, so one VAD span can run 15 s+; split it
    spans = get_speech_timestamps(audio, VadOptions(min_silence_duration_ms=250, speech_pad_ms=150,
                                                    max_speech_duration_s=max_s))
    pieces: list[list[int]] = []
    for sp in spans:
        if pieces and (sp["end"] - pieces[-1][0]) / SR <= max_s:
            pieces[-1][1] = sp["end"]
        else:
            pieces.append([sp["start"], sp["end"]])
    return [(a, b) for a, b in pieces]


def chunk_words(audio: np.ndarray, model) -> list[dict]:
    """Words heard piece by piece: [{w, s, e}] in seconds of `audio`."""
    words = []
    for a, b in speech_pieces(audio):
        segs, _ = model.transcribe(audio[a:b], language="en", word_timestamps=True, vad_filter=False, beam_size=5,
                                   temperature=0.0, initial_prompt=VERBATIM, condition_on_previous_text=False)
        for seg in segs:
            for w in seg.words or []:
                t = (w.word or "").strip()
                if t and w.end > w.start:
                    words.append({"w": t, "s": round(a / SR + float(w.start), 3), "e": round(a / SR + float(w.end), 3)})
    return words


def model(name: str = "small.en", threads: int = 4):
    from faster_whisper import WhisperModel

    return WhisperModel(name, device="cpu", compute_type="int8", cpu_threads=threads)


STOP = set("""a an the and or but so to of in on at for with from by is are was were be been it its this that these those
i you he she we they me my your our their um uh like just very really""".split())


def _n(w: str) -> str:
    return "".join(ch for ch in w.lower() if ch.isalnum() or ch == "'")


def restarts(words: list[dict], qa_find_repeats=None, window: float = 8.0) -> list[dict]:
    """Restarts in `words`: QA's phrase repeats (2+ words), plus one strong word said again within 1.2 s with at
    most one word between ("hiring, so hiring", "the gap, gap"). Each: {text, first_start, first_end, retake_start}."""
    out = []
    if qa_find_repeats:
        for text, s1, e1, s2, e2, gap, kind in qa_find_repeats(words, window):
            if kind == "stutter" or gap <= 2.5:
                out.append({"text": text, "first_start": s1, "first_end": e1, "retake_start": s2})
    toks = [_n(w["w"]) for w in words]
    for i, t in enumerate(toks):
        if len(t) < 4 or t in STOP:
            continue
        for j in (i + 1, i + 2):
            if j < len(toks) and toks[j] == t and words[j]["s"] - words[i]["e"] <= 1.2:
                if not any(o["first_start"] <= words[i]["s"] <= o["retake_start"] for o in out):
                    # "so hiring, so hiring": the word before repeats too, so both takes start one word earlier
                    lead = j == i + 2 and i > 0 and toks[i - 1] == toks[j - 1] and words[i]["s"] - words[i - 1]["e"] < 0.3
                    a, b = (i - 1, j - 1) if lead else (i, j)
                    out.append({"text": " ".join(w["w"] for w in words[a:b]),
                                "first_start": words[a]["s"], "first_end": words[b - 1]["e"], "retake_start": words[b]["s"]})
                break
    return sorted(out, key=lambda o: o["first_start"])
