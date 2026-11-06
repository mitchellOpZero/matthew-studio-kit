"""A CapCut draft Matthew can open and trim. Video segments only: no text track and no captions."""
import hashlib
import json
import os
from pathlib import Path


def _hid(text):
    return hashlib.sha256(text.encode()).hexdigest()[:32]


def _us(seconds):
    return int(round(float(seconds) * 1_000_000))


def export_project(edl, source, dest, *, width=None, height=None, fps=None):
    """Write a CapCut draft folder for this edit. The source file is referenced, not copied.

    Segments are the plan's cuts. There is no text material and no caption track.
    """
    source = Path(source).expanduser().resolve()
    if not source.is_file():
        raise ValueError(f"no file {source}")
    cuts = edl.get("cuts") or []
    if not cuts:
        raise ValueError("the edit has no cuts to export")
    output = edl.get("output") or {}
    width = int(width or output.get("w") or 1080)
    height = int(height or output.get("h") or 1920)
    fps = float(fps or output.get("fps") or 30)
    material_id = _hid("video:" + str(source))
    segments = []
    cursor = 0
    for i, cut in enumerate(cuts):
        start = float(cut["in"])
        dur = float(cut["out"]) - start
        if dur <= 0:
            continue
        dur_us = _us(dur)
        segments.append({
            "id": _hid(f"seg:{i}:{start}:{dur}"),
            "material_id": material_id,
            "source_timerange": {"start": _us(start), "duration": dur_us},
            "target_timerange": {"start": cursor, "duration": dur_us},
            "speed": 1.0,
            "volume": 1.0,
            "extra_material_refs": [],
            "enable_adjust": True,
            "clip": {"scale": {"x": 1.0, "y": 1.0}, "transform": {"x": 0.0, "y": 0.0},
                     "rotation": 0.0, "flip": {"horizontal": False, "vertical": False}},
        })
        cursor += dur_us
    if not segments:
        raise ValueError("the edit has no cuts to export")
    name = edl.get("name") or source.stem
    draft = {
        "id": _hid("draft:" + name + str(source)),
        "name": name,
        "duration": cursor,
        "fps": fps,
        "canvas_config": {"width": width, "height": height, "ratio": "original"},
        "materials": {
            "videos": [{
                "id": material_id,
                "path": str(source),
                "material_name": source.name,
                "duration": _us(max(c["out"] for c in cuts)),
                "width": width,
                "height": height,
                "type": "video",
                "category_name": "local",
            }],
            "audios": [],
            "texts": [],
            "stickers": [],
            "effects": [],
        },
        "tracks": [{
            "id": _hid("track:" + name),
            "type": "video",
            "segments": segments,
        }],
    }
    folder = Path(dest).expanduser()
    folder.mkdir(parents=True, exist_ok=True)
    content = json.dumps(draft, indent=2)
    (folder / "draft_content.json").write_text(content + "\n")
    (folder / "draft_info.json").write_text(content + "\n")
    meta = {"draft_id": draft["id"], "draft_name": name, "tm_duration": cursor, "draft_fold_path": str(folder)}
    (folder / "draft_meta_info.json").write_text(json.dumps(meta, indent=2) + "\n")
    return folder


def export_job(job_dir):
    job_dir = Path(job_dir)
    edl_path = job_dir / "edl.json"
    if not edl_path.is_file():
        raise ValueError(f"no edit plan at {edl_path}")
    edl = json.loads(edl_path.read_text())
    source = edl.get("source") or ""
    src = Path(source)
    if not src.is_absolute():
        src = job_dir / source
    return export_project(edl, src, job_dir / "capcut")
