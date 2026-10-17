"""On-demand browser-compatible MP4s and optional Live Photo still/motion pairs."""
import os
import json
import hashlib
import shutil
import subprocess
import tempfile
import threading
from datetime import datetime, timedelta
from pathlib import Path

from flask import abort
from werkzeug.utils import secure_filename

from app.models import LivePhotoPair, SessionLocal
from app.routes.api import _find_media_folder

STILL_EXTS = {'.jpg', '.jpeg', '.png', '.heic', '.heif', '.webp'}
MOTION_EXTS = {'.mov', '.mp4'}
VIDEO_EXTS = {'.mov', '.mp4', '.avi', '.mkv', '.webm'}
_conversion_slot = threading.BoundedSemaphore(1)


def validate_pairs(raw_pairs, content_urls):
    """Validate posted pairing metadata before committing an item."""
    if not isinstance(raw_pairs, list) or len(raw_pairs) > 20:
        raise ValueError('Too many Live Photo pairs')
    attached = set(name for name in content_urls.split(';') if name)
    used = set()
    result = []
    for value in raw_pairs:
        if not isinstance(value, dict):
            raise ValueError('Invalid Live Photo entry')
        still, video = value.get('still'), value.get('motion')
        if (not isinstance(still, str) or not isinstance(video, str)
                or still not in attached or video not in attached
                or still in used or video in used
                or still == video or Path(still).suffix.lower() not in STILL_EXTS
                or Path(video).suffix.lower() not in MOTION_EXTS):
            raise ValueError('Live Photo requires two distinct attached still and motion files')
        if any(secure_filename(name) != name for name in (still, video)):
            raise ValueError('Unsafe media filename')
        used.update((still, video))
        result.append((still, video))
    return result


def persist_pairs(item_id, pairs):
    if not pairs:
        return
    db = SessionLocal()
    try:
        db.add_all(LivePhotoPair(itemID=item_id, stillFilename=still, motionFilename=motion)
                   for still, motion in pairs)
        db.commit()
    finally:
        db.close()


def live_photos_for(item_id):
    db = SessionLocal()
    try:
        return {entry.stillFilename: entry.motionFilename
                for entry in db.query(LivePhotoPair).filter(LivePhotoPair.itemID == item_id)}
    finally:
        db.close()


def media_source(filename):
    if (not filename or filename != secure_filename(filename)
            or Path(filename).suffix.lower() not in VIDEO_EXTS):
        abort(400)
    folder = Path(_find_media_folder(filename)).resolve()
    source = (folder / filename).resolve()
    if source.parent != folder or not source.is_file():
        abort(404)
    return source


def _ffmpeg():
    binary = shutil.which('ffmpeg')
    if binary:
        return binary
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError):
        return None


def _browser_compatible_mp4(source):
    if source.suffix.lower() != '.mp4':
        return False
    probe = shutil.which('ffprobe')
    if not probe:
        return False
    try:
        result = subprocess.run([
            probe, '-v', 'error', '-show_entries',
            'stream=codec_type,codec_name,pix_fmt', '-of', 'json', str(source)
        ], capture_output=True, text=True, timeout=10, check=False)
        streams = json.loads(result.stdout).get('streams', []) if result.returncode == 0 else []
        video = [entry for entry in streams if entry.get('codec_type') == 'video']
        audio = [entry for entry in streams if entry.get('codec_type') == 'audio']
        return (len(video) == 1 and video[0].get('codec_name') == 'h264'
                and video[0].get('pix_fmt') == 'yuv420p'
                and all(entry.get('codec_name') == 'aac' for entry in audio))
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return False


def schedule_video_preview(filename):
    """Prepare new uploads on the existing APScheduler, if it is running."""
    if Path(filename).suffix.lower() not in VIDEO_EXTS:
        return
    from app.scheduler import _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.add_job(
            browser_video_path, 'date', args=[filename, True],
            run_date=datetime.now() + timedelta(seconds=1),
            id='video:' + hashlib.sha256(filename.encode()).hexdigest(),
            replace_existing=True,
        )


def browser_video_path(filename, background=False):
    """Keep original media untouched and atomically cache a H.264/AAC MP4 derivative."""
    source = media_source(filename)
    if _browser_compatible_mp4(source):
        return source
    base = Path(__file__).resolve().parent / 'uploads' / 'web-video'
    base.mkdir(parents=True, exist_ok=True)
    target = base / f'web-{filename}.mp4'
    if target.is_file() and target.stat().st_size and target.stat().st_mtime_ns >= source.stat().st_mtime_ns:
        return target
    binary = _ffmpeg()
    if not binary:
        abort(503, description='Video conversion requires ffmpeg')
    if not _conversion_slot.acquire(blocking=background):
        abort(503, description='Video conversion busy; retry shortly')
    try:
        with tempfile.NamedTemporaryFile(dir=base, suffix='.mp4', delete=False) as tmp:
            name = Path(tmp.name)
        try:
            command = [
                binary, '-nostdin', '-hide_banner', '-loglevel', 'error', '-y',
                '-i', str(source),
                '-map', '0:v:0', '-map', '0:a:0?', '-map_metadata', '-1',
                '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '25',
                '-preset', 'veryfast', '-vf', 'scale=trunc(min(iw\\,1920)/2)*2:-2',
                '-c:a', 'aac', '-b:a', '128k',
                '-movflags', '+faststart', str(name),
            ]
            completed = subprocess.run(command, capture_output=True, timeout=300, check=False)
            if completed.returncode != 0 or not name.is_file() or name.stat().st_size == 0:
                abort(422, description='Unable to prepare a browser-compatible video')
            os.replace(name, target)
            return target
        except subprocess.TimeoutExpired:
            abort(503, description='Video conversion timed out')
        finally:
            name.unlink(missing_ok=True)
    finally:
        _conversion_slot.release()
