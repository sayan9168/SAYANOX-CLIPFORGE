"""Media ingestion + analysis helpers: ffmpeg / ffprobe / yt-dlp wrappers.

All functions degrade gracefully when optional tooling is unavailable so the
API can report precise errors instead of crashing at import time.
"""
from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
import uuid
from pathlib import Path

from execution import check_cancelled, run_process

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".mts"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}
ALLOWED_EXTENSIONS = VIDEO_EXTENSIONS | AUDIO_EXTENSIONS
_ARTIFACTS = (
    re.compile(r"^clips/[A-Za-z0-9][A-Za-z0-9._-]*\.(mp4|webm|jpg|jpeg|png|srt|vtt)$", re.I),
    re.compile(r"^source\.(mp4|mov|mkv|webm|avi|m4v|mts|mp3|wav|m4a|aac|flac|ogg)$", re.I),
    re.compile(r"^(energy|render|transcript)\.json$|^captions\.srt$", re.I),
)


def allowed_artifact(path: str) -> bool:
    return ".." not in path and any(pattern.fullmatch(path) for pattern in _ARTIFACTS)
_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def have_tool(name: str) -> bool:
    return shutil.which(name) is not None


def run_ffmpeg(*args: str, timeout: int = 3600, cwd: Path | None = None) -> str:
    from config import settings
    threads = str(max(1, settings.ffmpeg_threads))
    p = run_process(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-filter_threads", threads, "-filter_complex_threads", threads, *args],
        capture_output=True, text=True, timeout=timeout, cwd=cwd,
    )
    if p.returncode:
        raise RuntimeError((p.stderr or p.stdout)[-2000:])
    return p.stdout


def probe(path: Path) -> dict:
    info = {"duration": 0.0, "width": 0, "height": 0, "fps": 0.0, "has_audio": False}
    if not have_tool("ffprobe"):
        return info
    p = run_process(
        ["ffprobe", "-v", "error", "-print_format", "json",
         "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True, timeout=60,
    )
    if p.returncode:
        return info
    try:
        data = json.loads(p.stdout)
    except json.JSONDecodeError:
        return info
    for s in data.get("streams", []):
        if s.get("codec_type") == "video" and not info["width"]:
            info["width"] = int(s.get("width") or 0)
            info["height"] = int(s.get("height") or 0)
            # Phone MOV/MP4s often store a landscape frame with a 90° display
            # matrix. FFmpeg autorotates it; crop dimensions must do the same.
            rotation = (s.get("tags") or {}).get("rotate", 0)
            for side in s.get("side_data_list", []):
                if side.get("side_data_type") == "Display Matrix":
                    rotation = side.get("rotation", rotation)
                    break
            try:
                angle = float(rotation)
                if math.isfinite(angle) and math.isclose(abs(angle) % 180, 90, abs_tol=0.01):
                    info["width"], info["height"] = info["height"], info["width"]
            except (TypeError, ValueError):
                pass
            m = re.match(r"(\d+)/(\d+)", s.get("r_frame_rate") or "")
            if m and int(m.group(2)):
                info["fps"] = round(int(m.group(1)) / int(m.group(2)), 3)
        if s.get("codec_type") == "audio":
            info["has_audio"] = True
    try:
        value = float(data.get("format", {}).get("duration") or 0)
        info["duration"] = value if math.isfinite(value) and value > 0 else 0
    except (TypeError, ValueError):
        pass
    return info


def extract_audio(source: Path, target: Path) -> Path:
    """Publish a complete WAV atomically; cancelled extraction is never cached."""
    info = probe(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".audio-{uuid.uuid4().hex}.wav")
    try:
        if info.get("has_audio"):
            try:
                run_ffmpeg("-i", str(source), "-vn", "-map", "0:a:0", "-ac", "1", "-ar", "16000",
                           "-c:a", "pcm_s16le", str(temporary))
                if temporary.is_file() and temporary.stat().st_size > 44:
                    temporary.replace(target)
                    return target
            except RuntimeError:
                check_cancelled()
        # No usable audio: silence is for timing only, never a fake speech transcript.
        duration = max(1.0, float(info.get("duration") or 30.0))
        run_ffmpeg("-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono", "-t", f"{duration:.3f}",
                   "-c:a", "pcm_s16le", str(temporary))
        temporary.replace(target)
        return target
    finally:
        temporary.unlink(missing_ok=True)


def audio_energy_curve(source: Path, hop: float = 0.5, duration: float = 0.0) -> list[float]:
    if not have_tool("ffmpeg"):
        return []
    try:
        out = run_process(
            ["ffmpeg", "-hide_banner", "-i", str(source), "-map", "0:a:0?",
             "-af", f"aresample=16000,asetnsamples=n={max(1, int(hop * 16000))}:p=0,"
                    "astats=metadata=1:reset=1,ametadata=print:key=lavfi.astats.Overall.RMS_level",
             "-f", "null", "-"],
            capture_output=True, text=True, timeout=1800,
        ).stderr
    except subprocess.TimeoutExpired:
        return []
    values = re.findall(r"lavfi\.astats\.Overall\.RMS_level=(-?(?:[\d.]+|inf))", out)
    curve = [max(-90.0, min(0.0, float(value))) for value in values]
    if not curve and duration > 0:
        curve = [-90.0] * max(1, math.ceil(duration / hop))
    return curve


def scene_changes(source: Path, threshold: float = 0.30, limit: int = 400) -> list[float]:
    if not have_tool("ffmpeg"):
        return []
    try:
        out = run_process(
            ["ffmpeg", "-hide_banner", "-i", str(source),
             "-filter:v", f"scale=320:-2,select='gt(scene,{threshold})',showinfo",
             "-f", "null", "-"],
            capture_output=True, text=True, timeout=3600,
        ).stderr
    except subprocess.TimeoutExpired:
        return []
    stamps = [round(float(t), 2) for t in re.findall(r"pts_time:\s*([\d.]+)", out)]
    return stamps[:limit]


def speaker_track(source: Path, start: float, end: float, samples: int = 24) -> list[float]:
    dur = max(0.5, end - start)
    vf = (
        f"crop=iw/2:ih:iw/2:0,scale=64:-1,"
        f"signalstats,metadata=print:key=lavfi.signalstats.YAVG:file=-"
    )
    try:
        out = run_process(
            ["ffmpeg", "-hide_banner", "-ss", str(start), "-t", str(dur),
             "-i", str(source), "-vf", vf, "-f", "null", "-"],
            capture_output=True, text=True, timeout=600,
        ).stdout
    except subprocess.TimeoutExpired:
        return []
    vals = [float(v) for v in re.findall(r"YAVG=([\d.]+)", out)]
    if len(vals) < 3:
        return []
    base = sum(vals) / len(vals) or 1.0
    track = [min(1.0, max(0.0, 0.5 + (v - base) / (base * 4))) for v in vals]
    return track


def face_center_x(source: Path, start: float, end: float, samples: int = 6) -> float | None:
    """Phase 2: optional OpenCV face center (0..1). Returns None if unavailable."""
    try:
        import cv2  # type: ignore
    except Exception:
        return None
    if not source.is_file():
        return None
    check_cancelled()
    cap = cv2.VideoCapture(str(source))
    if not cap.isOpened():
        return None
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    w = cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 1.0
    cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    if cascade.empty():
        cap.release()
        return None
    xs: list[float] = []
    dur = max(0.5, end - start)
    for i in range(samples):
        try:
            check_cancelled()
        except BaseException:
            cap.release()
            raise
        t = start + (dur * (i + 0.5) / samples)
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(t * fps)))
        ok, frame = cap.read()
        if not ok or frame is None:
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = cascade.detectMultiScale(gray, 1.2, 4, minSize=(40, 40))
        if len(faces) == 0:
            continue
        x, y, fw, fh = max(faces, key=lambda f: f[2] * f[3])
        xs.append((x + fw / 2) / w)
    cap.release()
    if not xs:
        return None
    return round(sum(xs) / len(xs), 3)


def mix_bgm(video: Path, bgm: Path, dest: Path, *, speech_vol: float = 1.0,
            bgm_vol: float = 0.18, duck: bool = True) -> Path:
    if not bgm.is_file():
        shutil.copy(video, dest)
        return dest
    info = probe(video)
    if info["has_audio"]:
        if duck:
            filters = (
                f"[0:a]volume={speech_vol},asplit=2[voice][side];"
                f"[1:a]volume={bgm_vol}[bed];"
                "[bed][side]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=250[ducked];"
                "[voice][ducked]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[a]"
            )
        else:
            filters = (f"[0:a]volume={speech_vol}[voice];[1:a]volume={bgm_vol}[bed];"
                       "[voice][bed]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[a]")
    else:
        filters = f"[1:a]volume={bgm_vol},alimiter=limit=0.95[a]"
    run_ffmpeg(
        "-i", str(video), "-stream_loop", "-1", "-i", str(bgm),
        "-filter_complex", filters, "-map", "0:v:0", "-map", "[a]",
        "-c:v", "copy", "-c:a", "aac", "-shortest", "-t", str(info["duration"]),
        "-movflags", "+faststart", str(dest), timeout=1800,
    )
    return dest


def download_youtube(url: str, work: Path) -> tuple[Path, dict]:
    import os
    if os.getenv("CLIPFORGE_ALLOW_YTDLP", "").lower() not in ("1", "true", "yes", "on"):
        raise PermissionError(
            "YouTube ingestion is disabled. Set CLIPFORGE_ALLOW_YTDLP=true only for "
            "videos you own or are authorised to process."
        )
    if not have_tool("yt-dlp"):
        raise FileNotFoundError("yt-dlp is not installed in the worker image.")
    meta_p = run_process(
        ["yt-dlp", "--ignore-config", "--no-warnings", "--no-playlist", "--dump-single-json", "--no-download", "--", url],
        capture_output=True, text=True, timeout=120,
    )
    if meta_p.returncode:
        raise RuntimeError(f"yt-dlp metadata failed: {meta_p.stderr[-500:]}")
    meta = json.loads(meta_p.stdout)
    from config import settings
    if float(meta.get("duration") or 0) > settings.max_video_seconds:
        raise ValueError(f"Video exceeds the {settings.max_video_seconds}-second worker limit.")
    # Downloads/merges stay private until yt-dlp has successfully completed.
    # An interrupted download must not become a valid source cache on retry.
    ingest = work / ".ingest"
    ingest.mkdir(exist_ok=True)
    # Prefer merged A+V; avoid video-only files that break extract_audio.
    p = run_process(
        [
            "yt-dlp", "--ignore-config", "--no-warnings",
            "-f", "bv*[height<=720]+ba/b[height<=720]/b",
            "--merge-output-format", "mp4",
            "--no-playlist", "--max-filesize", f"{settings.max_upload_mb}M",
            "-o", str(ingest / "source.%(ext)s"),
            "--", url,
        ],
        capture_output=True, text=True, timeout=7200,
    )
    if p.returncode:
        raise RuntimeError(f"yt-dlp download failed: {(p.stderr or p.stdout)[-800:]}")
    src = ingest / "source.mp4"
    if not src.is_file():
        cands = [c for c in sorted(ingest.glob("source.*")) if c.suffix.lower() in ALLOWED_EXTENSIONS]
        if not cands:
            raise RuntimeError(f"yt-dlp download failed: {(p.stderr or p.stdout)[-800:]}")
        src = cands[0]
    if src.suffix.lower() not in (".mp4", ".m4v"):
        fixed = ingest / "source.mp4"
        try:
            run_ffmpeg("-i", str(src), "-c", "copy", "-movflags", "+faststart", str(fixed))
            if fixed.is_file():
                src = fixed
        except RuntimeError:
            pass
    check_cancelled()
    destination = work / src.name
    src.replace(destination)
    shutil.rmtree(ingest, ignore_errors=True)
    return destination, meta


def safe_job_dir(root: Path, job_id: str) -> Path:
    if not _SAFE_ID.fullmatch(job_id):
        raise ValueError("Invalid job id.")
    path = (root / job_id).resolve()
    if path.parent != root.resolve():
        raise ValueError("Invalid job path.")
    return path
