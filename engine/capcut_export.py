"""Send a finished edit to CapCut: a CapCut project with the rendered video on its timeline.

CapCut refuses projects written from scratch ("Couldn't use project: unusual path") and can't read
media outside its own folders ("File not accessible"). So the project is a copy of a blank project
CapCut itself made (capcut_template/blank), the clip uses the field set CapCut wrote for a video
clip (capcut_template/reference.json), and the video is copied into the project's media folder.
Proven on CapCut 9.4.1 (Mac): the project opens, plays, and the clip can be trimmed.
"""
import copy
import json
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parent / "capcut_template"


def _uid():
    return str(uuid.uuid4()).upper()


def _us(seconds):
    return int(round(float(seconds) * 1_000_000))


def capcut_drafts_dir():
    """CapCut's own projects folder on this Mac, so the project shows up in CapCut's list."""
    override = os.environ.get("KIT_CAPCUT_DRAFTS")
    if override:
        return Path(override).expanduser()
    mac = Path.home() / "Movies" / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft"
    return mac if mac.is_dir() else None


def _probe(path):
    out = json.loads(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=width,height,codec_type", "-of", "json", str(path)]))
    v = next(s for s in out["streams"] if s["codec_type"] == "video")
    return {"dur": float(out["format"]["duration"]), "w": int(v["width"]), "h": int(v["height"]),
            "audio": any(s["codec_type"] == "audio" for s in out["streams"])}


def export_video(video, name, drafts=None, probe=None):
    """Make a CapCut project called `name` holding `video` (one clip, full length). Returns its folder."""
    video = Path(video).expanduser().resolve()
    if not video.is_file():
        raise ValueError(f"no video at {video}")
    drafts = Path(drafts) if drafts else capcut_drafts_dir()
    if not drafts:
        raise ValueError("CapCut's project folder isn't on this Mac (~/Movies/CapCut/User Data/Projects/com.lveditor.draft). "
                         "Open CapCut once, then try again.")
    ref = json.loads((TEMPLATE / "reference.json").read_text())
    dest, n = drafts / name, 2
    while dest.exists():
        dest, n = drafts / f"{name} ({n})", n + 1
    shutil.copytree(TEMPLATE / "blank", dest, ignore=shutil.ignore_patterns(".keep"))
    (dest / "media").mkdir(exist_ok=True)
    media = dest / "media" / video.name
    shutil.copy2(video, media)
    info = probe or _probe(media)

    mat = copy.deepcopy(ref["video_material"])
    mat.update(id=_uid(), local_material_id=_uid(), path=str(media), material_name=media.name,
               duration=_us(info["dur"]), width=info["w"], height=info["h"], has_audio=info["audio"])
    for key in ("media_path", "material_url"):
        if key in mat:
            mat[key] = ""

    def fill(draft):
        mats = draft.setdefault("materials", {})
        mats["videos"] = [mat]
        refs = []
        for kind, m in ref["segment_materials"].items():
            m2 = copy.deepcopy(m)
            m2["id"] = _uid()
            mats.setdefault(kind, []).append(m2)
            refs.append(m2["id"])
        seg = copy.deepcopy(ref["segment"])
        seg.update(id=_uid(), material_id=mat["id"], extra_material_refs=refs,
                   source_timerange={"start": 0, "duration": _us(info["dur"])},
                   target_timerange={"start": 0, "duration": _us(info["dur"])})
        if "render_timerange" in seg:
            seg["render_timerange"] = {"start": 0, "duration": 0}
        track = copy.deepcopy(ref["track"])
        track.update(id=_uid(), segments=[seg])
        draft["tracks"] = [track]
        draft["duration"] = _us(info["dur"])
        draft["canvas_config"] = dict(draft.get("canvas_config") or {}, width=info["w"], height=info["h"], ratio="original")
        return draft

    for path in [dest / "draft_info.json", *dest.glob("Timelines/*/draft_info.json")]:
        path.write_text(json.dumps(fill(json.loads(path.read_text())), ensure_ascii=False))

    meta = json.loads((dest / "draft_meta_info.json").read_text())
    now = int(time.time() * 1_000_000)
    meta.update(draft_id=_uid(), draft_name=dest.name, draft_fold_path=str(dest), draft_root_path=str(drafts),
                draft_cover="draft_cover.jpg", tm_duration=_us(info["dur"]), tm_draft_create=now, tm_draft_modified=now,
                draft_timeline_materials_size_=media.stat().st_size)
    (dest / "draft_meta_info.json").write_text(json.dumps(meta, ensure_ascii=False))
    return dest


def finished_video(job_dir, kit_root):
    """The job's rendered video: done/<job>.mp4, else .work/<job>/out/<job>.mp4."""
    job_dir = Path(job_dir)
    for p in (Path(kit_root) / "done" / f"{job_dir.name}.mp4", job_dir / "out" / f"{job_dir.name}.mp4"):
        if p.is_file():
            return p
    return None


def export_job(job_dir, kit_root=None):
    kit_root = Path(kit_root) if kit_root else Path(__file__).resolve().parents[1]
    video = finished_video(job_dir, kit_root)
    if not video:
        raise ValueError(f"{Path(job_dir).name} isn't rendered yet: run bin/kit render {Path(job_dir).name} first")
    return export_video(video, Path(job_dir).name.lstrip("_"))
