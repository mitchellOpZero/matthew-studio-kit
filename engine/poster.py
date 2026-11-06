"""Local poster stills for library items. Nothing is uploaded.

A video poster is one frame at about one second. A PNG/JPEG is re-encoded beside the
source as <name>.poster.png. HTML and SVG are rasterized with a local browser
(KIT_BROWSER_PATH or HYPERFRAMES_BROWSER_PATH). Remote hosts are not resolved.
"""
import os
import subprocess
from pathlib import Path

from PIL import Image, UnidentifiedImageError


def make_poster(path, output=None):
    src = Path(path)
    if not src.is_file():
        raise ValueError(f'no file {src}')
    dest = Path(output) if output is not None else src.with_suffix('.poster.png')
    dest.parent.mkdir(parents=True, exist_ok=True)
    ext = src.suffix.lower()
    if ext in {'.html', '.svg'}:
        _rasterize(src, dest)
    elif ext in {'.mp4', '.mov', '.m4v', '.webm', '.ogv', '.mkv', '.avi'}:
        _video_frame(src, dest)
    else:
        _image_poster(src, dest)
    if not dest.is_file():
        raise ValueError(f'poster was not written for {src.name}')
    return dest


def _image_poster(src, dest):
    try:
        with Image.open(src) as image:
            image.convert('RGBA').save(dest, 'PNG')
    except (UnidentifiedImageError, OSError) as exc:
        if dest.exists():
            dest.unlink()
        raise ValueError(f'cannot decode {src.name}') from exc


def _video_frame(src, dest):
    if dest.exists():
        dest.unlink()
    last_error = None
    for timestamp in ('1', '0'):
        try:
            subprocess.run(
                ['ffmpeg', '-y', '-v', 'error', '-ss', timestamp, '-i', str(src), '-frames:v', '1', str(dest)],
                check=True, capture_output=True, timeout=60)
            break
        except (OSError, subprocess.SubprocessError) as exc:
            last_error = exc
            if dest.exists():
                dest.unlink()
    else:
        raise ValueError(f'no poster frame for {src.name}') from last_error
    if not dest.is_file():
        raise ValueError(f'no poster frame for {src.name}')


def _rasterize(src, dest):
    """One local browser screenshot. Hostnames other than loopback do not resolve."""
    if dest.exists():
        dest.unlink()
    browser = os.environ.get('KIT_BROWSER_PATH') or os.environ.get('HYPERFRAMES_BROWSER_PATH') or 'google-chrome'
    subprocess.run(
        [browser, '--headless=new', '--disable-gpu', '--no-sandbox', '--no-first-run', '--disable-extensions',
         '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1',
         f'--screenshot={dest}', '--window-size=800,800', '--virtual-time-budget=2000',
         src.resolve().as_uri()],
        check=True, capture_output=True, timeout=90)
