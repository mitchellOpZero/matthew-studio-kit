# Dialogue cleanup and leveling

Version 2.2.1 ports the voice treatment from Mitchell's November 4 Remotion project's
build.py and its fixed-gain master approach. This is an audio pipeline update, not a
renderer migration or a new visual preset.

- Remove low rumble with a 70 Hz high-pass filter.
- Apply restrained FFT denoising: `afftdn=nr=6:nf=-58:tn=0`.
- Measure active 10 ms voice windows above -36 dBFS per real edit cut. Aim at -19 dBFS
  active RMS, limiting the gain adjustment to +/-8 dB. Silent cuts receive no boost.
  Punch-in splits within a continuous cut do not cause another gain change.
- Preserve the existing sample-aligned joins, crossfades, external dialogue source and offset.
- Mix dialogue in floating point so leveling does not clip before mastering.
- Measure the assembled voice, apply fixed gain plus a latency-compensated limiter,
  and keep the saved style's existing loudness/peak targets and ending fade. The default
  Matthew style remains -14 LUFS / -1.5 dBTP. Dynamic loudnorm is no longer used here.
- Keep the final export's existing fixed-gain loudness correction after sound effects are mixed.

The pipeline does not add music, change effects, change the cut plan or touch style files.
Captions, fonts, colours, graphics, crop and timing remain controlled by the same saved style.

## Updating existing work

Run `bin/kit update` in the existing kit. New drafts and ordinary generated previews use the
new processing. Audio cache keys include the pipeline version and cleanup option, so an old
cached dialogue track cannot silently be reused for a new build.

Hand-edited Studio projects keep their current audio and visuals. Updating the kit alone does
not upgrade those projects. `bin/kit support inspect <job>` reports the audio pipeline and
flags a missing/older version. Make a separate comparison job with the same source and saved
style. A forced rebuild can discard visual hand edits and requires explicit approval.

## Already processed sources

Set `audio.cleanup` to `false` in the job's edit plan to skip denoising and per-cut leveling
for externally cleaned audio. Preserve other audio fields. The saved-style loudness master
still applies. Existing `audio.pre` filters are preserved after assembly; review them to avoid
unintentional double processing. Do not normalize every input to Mitchell's -16 LUFS master:
Matthew's own saved loudness target remains authoritative.

The cache sidecar records per-cut measured level and applied gain; timeline.json records the
pipeline, cleanup flag, master gain and measured master levels. Support inspect includes safe
processing metadata. These records establish which code ran, not a subjective listening verdict.
