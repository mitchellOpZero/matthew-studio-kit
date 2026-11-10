"""Small real-FFmpeg checks of the shipped dialogue path; no video render/network."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'engine'))
import audio_clean as ac
import quick_edit as qe
import timeline as tl
import render_hf as rh

SR = 48000


def write(path, samples):
    with wave.open(str(path), 'wb') as f:
        f.setparams((1, 2, SR, 0, 'NONE', 'not compressed'))
        f.writeframes((np.clip(samples, -1, 1) * 32767).astype('<i2').tobytes())


def read(path):
    raw = subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(path), '-f', 'f32le', '-ac', '1', '-ar', str(SR), '-'])
    return np.frombuffer(raw, '<f4')


def rms(x):
    return 20 * np.log10(np.sqrt(np.mean(x.astype(float) ** 2)) + 1e-12)


@unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg required')
class AudioChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.source = self.root / 'source.wav'
        for name in ('DLG', 'KIT'):
            p = patch.object(tl, name, str(self.root / 'cache') if name == 'DLG' else str(self.root))
            p.start(); self.addCleanup(p.stop)
        t = np.arange(SR * 6) / SR
        self.voice = .14 * np.sin(2 * np.pi * 1000 * t)
        self.voice[SR * 3:] *= .5
        self.style = {'xfade_ms': 12}
        self.pieces = [(0, 3, 1, True, True), (3, 6, 1, True, True)]
        write(self.source, self.voice)

    def dialogue(self, audio=None):
        return tl.dialogue({'audio': audio or {}}, str(self.root), str(self.source), self.pieces, self.style, 6)

    def test_takes_are_leveled_without_changing_timing_and_old_cache_is_ignored(self):
        old_key = hashlib.sha256(json.dumps([tl.sha_file(str(self.source)), 0., .012,
                    [[0, 3, 0.], [3, 6, 3.]], 6, None]).encode()).hexdigest()[:20]
        old = Path(tl.DLG) / (old_key + '.wav'); old.parent.mkdir(); old.write_bytes(b'old-cache')
        cleaned = self.dialogue(); x = read(cleaned)
        self.assertNotEqual(str(old), cleaned)
        self.assertEqual(old.read_bytes(), b'old-cache')
        self.assertEqual(len(x), SR * 6)
        self.assertLess(abs(rms(x[SR:SR*2]) - rms(x[SR*4:SR*5])), .3)
        report = json.loads(Path(cleaned + '.json').read_text())
        self.assertEqual(len(report['cuts']), 2)
        self.assertAlmostEqual(report['cuts'][1]['gain_db'] - report['cuts'][0]['gain_db'], 6.02, delta=.1)
        self.assertEqual(cleaned, self.dialogue())

    def test_rumble_reduced_and_cleanup_can_be_disabled(self):
        t = np.arange(SR * 6) / SR
        write(self.source, .1*np.sin(2*np.pi*1000*t) + .05*np.sin(2*np.pi*25*t))
        clean = read(self.dialogue())[SR:SR*2]
        plain_path = self.dialogue({'cleanup': False}); plain = read(plain_path)[SR:SR*2]
        def ratio(x):
            s = abs(np.fft.rfft(x))
            return 20*np.log10((s[25]+1e-12)/(s[1000]+1e-12))
        self.assertLess(ratio(clean), ratio(plain)-12)
        self.assertEqual(json.loads(Path(plain_path+'.json').read_text())['cleanup'], False)

    def test_silence_stays_silent_and_gain_is_bounded(self):
        write(self.source, np.zeros(SR*6))
        self.assertEqual(ac.piece_gain(self.source, 0, 6)['gain_db'], 0)
        out = self.root/'voice.wav'
        result = ac.master(self.dialogue(), out, 6, -14, -1.5, .15)
        self.assertEqual(result['gain_db'], 0)
        self.assertEqual(np.max(np.abs(read(out))), 0)
        write(self.source, self.voice * .2)
        self.assertLessEqual(abs(ac.piece_gain(self.source, 0, 6)['gain_db']), 8)

    def test_renderer_voice_master_keeps_style_target_and_sample_count(self):
        style = {'loudness': {'I': -14, 'TP': -1.5, 'LRA': 11}, 'end_fade_s': .15}
        before = json.dumps(style, sort_keys=True)
        out = self.root/'voice.wav'; dialogue = self.dialogue()
        result = rh.voice_track({'style': style, 'frames': 180, 'fps': 30, 'dialogue': dialogue}, str(out))
        x, original = read(out), read(dialogue)
        self.assertEqual(len(x), len(original))
        self.assertLess(abs(result['measured_lufs']+14), .3)
        self.assertLessEqual(result['measured_peak_db'], -1.4)
        self.assertEqual(json.dumps(style, sort_keys=True), before)
        self.assertGreater(np.corrcoef(x[SR:SR*2], original[SR:SR*2])[0, 1], .999)

    def test_external_audio_offset_is_used_for_leveling(self):
        external = self.root/'external.wav'
        write(external, np.r_[np.zeros(SR), self.voice])
        x = read(self.dialogue({'file': str(external), 'offset': -1}))
        self.assertEqual(len(x), 6*SR)
        self.assertLess(abs(rms(x[SR:SR*2]) - rms(x[SR*4:SR*5])), .3)

