# Studio Kit 2.3.4 preview reproduction

This is the synthetic **Cut With Purpose** test that was opened in HyperFrames Studio. The attached [resulting clip](demo.mp4) is the exact diagnostic render. It is not a production edit, a creative approval, or a passing QA example.

- Kit: `mitchellOpZero/matthew-studio-kit@e42b4074c6691a326a11836494787fc4e2d07706` (2.3.4). The 50 tracked `engine/` files in the tested install matched this commit byte for byte.
- Runtime: HyperFrames **0.8.214** (also the release's `engine/hyperframes.json` floor; npm latest was 0.9.39 when checked), Node **24.19.0**, Python **3.12.14**, FFmpeg **9.0.1**, macOS, faster-whisper **small.en**.
- Host adapter: `matthew-studio-kit-standalone` **2.3.4-standalone1**. [standalone_guard.py](standalone_guard.py) is the exact additional file used by the host launcher. It kept the upstream engine unchanged. It disabled automatic dependency changes, external skill discovery and support reports, prevented previous preferences/library indices from applying, and independently muted the composition preview. Its layout fallback did not select this demo's framing; the plan explicitly selected `full`.
- The main output is **1080 × 1920**, **30 fps**, **4.300 s**, SHA-256 `80ba8df7ce9329fccc3c88ed7c9e8f9f040d190d54e56ab545caf12820f0c00a`. No cover is part of the test.

## What was called

Paths below stand in for the corresponding local paths. `$WRAPPER` is the installed adapter's `scripts/kit.py`; `$SESSION_KIT` is the exact session's kit root. Nothing ran against the older Studio Kit runtime.

```sh
# Create a fresh session. OWNER is the existing operator's chat ID.
python3 -B "$WRAPPER" session create cut-with-purpose-1112 \
  --owner "$OWNER" --job cut-with-purpose --port 45201

# In the fresh session kit, generate a synthetic source.
cd "$SESSION_KIT"
/usr/bin/say -r 177 -o "$SCRATCH/demo-voice.aiff" \
  'Start with one clear idea. Give it a beat. Cut when the story moves.'
ffmpeg -v error -nostdin -f lavfi \
  -i 'gradients=size=540x960:rate=30:c0=0x10122E:c1=0x172C58:c2=0x38306E:n=3:speed=0.10' \
  -i "$SCRATCH/demo-voice.aiff" -af 'adelay=240,apad=pad_dur=0.75' \
  -c:v libx264 -pix_fmt yuv420p -c:a aac -shortest inbox/cut-with-purpose-source.mp4
python3 -B "$WRAPPER" --session cut-with-purpose-1112 \
  draft inbox/cut-with-purpose-source.mp4 --name cut-with-purpose

# Apply the included pre-QA plan and use its exact component.
cp "$REPRO/edit-plan.json" .work/cut-with-purpose/edl.json
cp "$REPRO/words.json" .work/cut-with-purpose/inputs/words.json
mkdir -p graphics/cut-purpose/assets
cp "$REPRO/cut-purpose.html" graphics/cut-purpose/cut-purpose.html
cp styles/default/fonts/Outfit-Bold.ttf graphics/cut-purpose/assets/demo-outfit.ttf

python3 -B "$WRAPPER" --session cut-with-purpose-1112 preview cut-with-purpose
python3 -B "$WRAPPER" --session cut-with-purpose-1112 preview --stop
python3 -B "$WRAPPER" --session cut-with-purpose-1112 render cut-with-purpose

# The first browser open was started from a different caller directory.
cd "$CALLER"
python3 -B "$WRAPPER" --session cut-with-purpose-1112 preview cut-with-purpose

# Stop that server and open the exact project, fixing the stale project label.
cd "$SESSION_KIT/.work/_studio/cut-with-purpose"
python3 -B "$WRAPPER" --session cut-with-purpose-1112 preview --stop
python3 -B "$WRAPPER" --session cut-with-purpose-1112 preview cut-with-purpose
```

The wrapper invoked the session's Python on `standalone_guard.py` with these native arguments: `draft inbox/cut-with-purpose-source.mp4 --name cut-with-purpose`, `preview cut-with-purpose --port 45201`, `preview --stop`, and `render cut-with-purpose`. The native renderer then ran `hyperframes@0.8.214 check --json`, `preview --background --no-open --port 45201`, and `render PROJECT --output OUTPUT` as appropriate. The word timings are unchanged; the source path in `words.json` was made relative for publication, so its file hash differs from the recorded local hash. The attached binary preserves the actual output. Re-running the source generator can vary with the Mac's selected system voice and encoder build.

## What made the look

The native **default** supplied its Outfit capsule captions. The test plan overrode the caption accent to `#C8FF54`, the caption anchor to `0.675`, the framing to full, and disabled punch-ins. It kept one continuous 0–4.3-second cut. There are no actual footage cuts between the three graphics beats.

The motion came from the included **hand-authored** HTML/CSS/GSAP component, mounted at `[0, 185, 1080, 870]`: a focus bracket, concentric arcs, then an angled panel and slash. An offline registry search found `type-match-cut` among other results, but **no registry block was used**. The visuals are not evidence that a former Cold Approach skill or the old red preset triggered. The quality criticism applies to this test's chosen graphics and pacing; this run does not isolate the renderer's effect on creative quality.

## Observed issues

1. **Preview opened under the wrong project name.** HyperFrames 0.8.214's implicit preview path computes the name with `basename(process.env.PWD ?? dir)`. The wrapper changed the process working directory but preserved a stale `PWD` from the caller. The initial Studio tab showed the caller's folder name even though the demo composition was present. Restarting the preview from the compiled project folder made the correct project name appear. A follow-up fix should pass the project directory explicitly to HyperFrames or set `PWD` to that exact directory in the child environment.
2. **The first graphic build failed font lint.** The component used the parent composition's `kitfont` name without a local declaration. The final component in this folder explicitly declares `DemoOutfit` and bundles the kit's existing Outfit font through the job's asset directory.
3. **The diagnostic render failed picture QA.** The only flag was `picture:edge-band`, reporting a 270 px dark top band from 0.67 to 1.33 seconds. The source used a dark synthetic gradient; the edge detector counts flat dark scanlines. This result does not establish whether the condition was intentional, visually acceptable or a renderer regression. The clip was left as diagnostic evidence; the user requested the editable preview rather than another export.

The preview was left paused and independently muted. No playback or listening verification was performed.
