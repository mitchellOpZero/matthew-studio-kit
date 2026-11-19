"""Mitchell's restrained dialogue chain, independent of the video's visual style."""
import math
import subprocess
import tempfile

import numpy as np

VERSION = 'dialogue-clean-v1'
CLEAN_FILTER = 'highpass=f=70,afftdn=nr=6:nf=-58:tn=0'
TARGET_RMS_DB = -19.0
ACTIVE_FLOOR_DB = -36.0
MAX_GAIN_DB = 8.0


_DELAY = {}


def clean_delay(rate=48000):
    """How late CLEAN_FILTER hands its sound back, in samples at `rate`. The noise reducer works in blocks and returns
    each piece that much late and that much short, so the end of a word was lost at every cut. Measured once on this
    Mac's ffmpeg with a burst of noise (0 when it can't be measured, or when a newer ffmpeg makes up for it itself)."""
    if rate in _DELAY:
        return _DELAY[rate]
    d = 0
    try:
        rng = np.random.default_rng(7)
        x = np.zeros(rate, dtype='<f4')
        a = rate // 2
        x[a:a + rate // 50] = (rng.standard_normal(rate // 50) * 0.3).astype('<f4')
        run = lambda af: np.frombuffer(subprocess.run(
            ['ffmpeg', '-v', 'error', '-nostdin', '-f', 'f32le', '-ar', str(rate), '-ac', '1', '-i', '-', '-af', af,
             '-f', 'f32le', '-'], input=x.tobytes(), capture_output=True, timeout=60).stdout, dtype='<f4').astype(np.float64)
        y = run(CLEAN_FILTER)
        if len(y) >= rate // 2:
            lags = range(0, rate // 10)
            seg = x[a:a + rate // 50].astype(np.float64)
            best = max(lags, key=lambda k: float(np.dot(seg, y[a + k:a + k + len(seg)])) if a + k + len(seg) <= len(y) else -1.0)
            d = int(best) if best >= 8 else 0
    except Exception:
        d = 0
    _DELAY[rate] = d
    return d


def piece_gain(source, start, duration):
    """Mean energy of active 10 ms windows; silence never gets a positive gain.

    Stream mono analysis at 16 kHz so long takes do not consume unbounded memory.
    This is the reference editor's -19 dBFS target and +/-8 dB gain guard.
    """
    frame = 160
    energy, count, pending = 0.0, 0, b''
    with tempfile.TemporaryFile() as err:
        proc = subprocess.Popen(['ffmpeg', '-v', 'error', '-nostdin', '-ss', str(start),
                                 '-t', str(duration), '-i', str(source), '-map', '0:a:0',
                                 '-vn', '-ac', '1', '-ar', '16000', '-f', 'f32le', '-'],
                                stdout=subprocess.PIPE, stderr=err)
        try:
            while True:
                data = proc.stdout.read(64000)
                if not data:
                    break
                pending += data
                n = len(pending) // (frame * 4) * frame * 4
                if not n:
                    continue
                samples = np.frombuffer(pending[:n], dtype='<f4').reshape(-1, frame)
                power = np.mean(samples.astype(np.float64) ** 2, axis=1)
                active = power[power > 10 ** (ACTIVE_FLOOR_DB / 10)]
                energy += float(active.sum()); count += len(active)
                pending = pending[n:]
            if proc.wait():
                raise RuntimeError('Could not measure dialogue source')
        finally:
            proc.stdout.close()
            if proc.poll() is None:
                proc.kill(); proc.wait()
    rms = 10 * math.log10(energy / count) if count else None
    gain_db = max(-MAX_GAIN_DB, min(MAX_GAIN_DB, TARGET_RMS_DB - rms)) if rms is not None else 0.0
    return {'gain_db': round(gain_db, 4), 'active_rms_db': round(rms, 4) if rms is not None else None,
            'active_windows': count}


def master(source, output, total, target, peak, end_fade):
    """Measured constant gain and limiter, with no dynamic loudnorm stage."""
    import quick_edit as qe
    # Measure after the end fade; pad and trim to the exact video duration.
    end_fade = max(0.0, min(float(end_fade), total))
    with tempfile.TemporaryDirectory(prefix='kit-audio-') as tmp:
        prepared = tmp + '/prepared.wav'
        af = f'aresample=48000,apad,atrim=duration={total:.6f}'
        if end_fade:
            af += f',afade=t=out:st={total-end_fade:.6f}:d={end_fade:.6f}:curve=cub'
        subprocess.run(['ffmpeg', '-y', '-v', 'error', '-nostdin', '-i', str(source),
                        '-af', af, '-c:a', 'pcm_f32le', prepared], check=True)
        loudness, measured_peak = qe.measure_loud(prepared)
        # Avoid amplifying effectively silent tracks or non-finite measurements.
        audible = math.isfinite(loudness) and math.isfinite(measured_peak) and measured_peak > -60
        gain = target - loudness if audible else 0.0
        limit = 10 ** (peak / 20)
        for attempt in range(2):
            filters = f'volume={gain:.4f}dB,alimiter=limit={limit:.8f}:attack=5:release=60:level=disabled:latency=1'
            subprocess.run(['ffmpeg', '-y', '-v', 'error', '-nostdin', '-i', prepared,
                            '-af', filters, '-ar', '48000', '-c:a', 'pcm_s24le', str(output)], check=True)
            actual, actual_peak = qe.measure_loud(output)
            if not audible or not math.isfinite(actual) or abs(actual - target) <= .2:
                break
            if attempt == 0:
                gain += target - actual
        return {'pipeline': VERSION, 'master': 'fixed-gain-limiter', 'gain_db': round(gain, 4),
                'target_lufs': target, 'measured_lufs': actual if math.isfinite(actual) else None,
                'measured_peak_db': actual_peak if math.isfinite(actual_peak) else None}
