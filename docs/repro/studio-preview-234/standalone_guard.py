"""Local execution boundaries. The GitHub engine itself is unchanged."""
import json
import os
from pathlib import Path
import sys

root = Path(__file__).resolve().parent
sys.path.insert(0, str(root / "engine"))
import kit
import quick_edit
import render_hf
import timeline

kit.deps.auto = lambda: None
kit.deps.apply = lambda: None
kit.other_skills = lambda: []
render_hf.env = lambda: dict(os.environ)
quick_edit.load_preferences = lambda *args, **kwargs: {}
# No read of the former runtime or global library indices.
import library
library._notion_broll = lambda: []

original_style = quick_edit.resolve_style
def plan_style(plan):
    style = original_style(plan)
    output = plan.get("output") or {}
    if output.get("w", 1080) > output.get("h", 1920):
        style["captions_enabled"] = False
    if plan.get("style_name") == "default" and not plan.get("blocks") and "frame_layout" not in (plan.get("style") or {}):
        style["frame_layout"] = "full"
    return style
quick_edit.resolve_style = plan_style

caption_chunks = quick_edit.caption_chunks
def selected_captions(words, total, plan, style):
    if style.get("captions_enabled") is False:
        return [], []
    return caption_chunks(words, total, plan, style)
quick_edit.caption_chunks = selected_captions

write_html = render_hf.write_html
def guarded_html(*args, **kwargs):
    html = write_html(*args, **kwargs)
    guard = """<script>
    if (!window.__HF_RENDER_CAPTURE_MODE) {
      const p = HTMLMediaElement.prototype;
      const volume = Object.getOwnPropertyDescriptor(p, 'volume');
      const muted = Object.getOwnPropertyDescriptor(p, 'muted');
      const quiet = m => { volume.set.call(m, 0); muted.set.call(m, true); };
      Object.defineProperty(p, 'volume', {configurable:true,get:()=>0,set:function(){quiet(this)}});
      Object.defineProperty(p, 'muted', {configurable:true,get:()=>true,set:function(){quiet(this)}});
      const play = p.play;
      p.play = function(){quiet(this);return play.apply(this,arguments);};
      document.addEventListener('DOMContentLoaded',()=>document.querySelectorAll('audio,video').forEach(m=>{quiet(m);m.pause()}));
      document.addEventListener('play',e=>{if(e.target instanceof HTMLMediaElement)quiet(e.target)},true);
    }
    </script>"""
    assert "<head>" in html
    return html.replace("<head>", "<head>" + guard, 1)
render_hf.write_html = guarded_html

# Renderer support/remote reporting stay unreachable; diagnostics are local.
if sys.argv[1:2] == ["doctor"]:
    import shutil, subprocess
    required = [shutil.which(x) for x in ("ffmpeg","ffprobe","node")]
    required += [os.environ.get("HYPERFRAMES_BROWSER_PATH"),
                 str(Path(os.environ["HF_HOME"]) / "hub" / kit.MODEL),
                 str(root / "styles/default/style.json")]
    import faster_whisper, numpy, PIL, Vision
    assert all(x and Path(x).exists() for x in required), "Missing pinned local dependency"
    print("Studio Kit " + kit.kit_version())
    subprocess.run(render_hf.hf() + ["--version"], check=True)
    print("Local renderer, Chrome, speech model, Python and styles verified.")
    raise SystemExit(0)

raise SystemExit(kit.main())
