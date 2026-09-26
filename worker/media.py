"""Media ingestion + analysis helpers: ffmpeg / ffprobe / yt-dlp wrappers.

All functions degrade gracefully when optional tooling is unavailable so the
API can report precise errors instead of crashing at import time.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

ALLOWED_EXTENSIONS = {
    ".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".mts",
    ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg",
}
_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def have_tool(name: str) -> bool:
    return shutil.which(name) is not None


def run_ffmpeg(*args: str, timeout: int = 3600) -> str:
    p = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args],
        capture_output=True, text=True, timeout=timeout,
    )
    if p.returncode:
        raise RuntimeError((p.stderr or p.stdout)[-2000:])
    return p.stdout


def probe(path: Path) -> dict:
    info = {"duration": 0.0, "width": 0, "height": 0, "fps": 0.0, "has_audio": False}
    if not have_tool("ffprobe"):
        return info
    p = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json",
         "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True,
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
            m = re.match(r"(\d+)/(\d+)", s.get("r_frame_rate") or "")
            if m and int(m.group(2)):
                info["fps"] = round(int(m.group(1)) / int(m.group(2)), 3)
        if s.get("codec_type") == "audio":
            info["has_audio"] = True
    try:
        info["duration"] = float(data.get("format", {}).get("duration") or 0)
    except (TypeError, ValueError):
        pass
    return info


def extract_audio(source: Path, target: Path) -> Path:
    run_ffmpeg("-i", str(source), "-vn", "-ac", "1", "-ar", "16000",
               "-c:a", "pcm_s16le", str(target))
    return target


def audio_energy_curve(source: Path, hop: float = 0.5, duration: float = 0.0) -> list[float]:
    if not have_tool("ffmpeg"):
        return []
    try:
        out = subprocess.run(
            ["ffmpeg", "-hide_banner", "-i", str(source), "-map", "0:a:0?",
             "-af", f"asetnsamples={max(1, int(hop * 16000))},astats=metadata=1:reset=1",
             "-f", "null", "-"],
            capture_output=True, text=True, timeout=1800,
        ).stderr
    except subprocess.TimeoutExpired:
        return []
    curve = [float(x) for x in re.findall(r"RMS_level:\s*(-?[\d.]+)\s*dB", out)]
    if not curve and duration > 0:
        curve = [float("-inf")] * max(1, int(duration / hop))
    return curve


def scene_changes(source: Path, threshold: float = 0.30, limit: int = 400) -> list[float]:
    if not have_tool("ffmpeg"):
        return []
    try:
        out = subprocess.run(
            ["ffmpeg", "-hide_banner", "-i", str(source),
             "-filter:v", f"select='gt(scene,{threshold})',showinfo",
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
        out = subprocess.run(
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
    cap = cv2.VideoCapture(str(source))
    if not cap.isOpened():
        return None
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    w = cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 1.0
    cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    xs: list[float] = []
    dur = max(0.5, end - start)
    for i in range(samples):
        t = start + (dur * (i + 0.5) / samples)
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(t * fps)))
        ok, frame = cap.read()
        if not ok or frame is None:
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = cascade.detectMultiScale(gray, 1.2, 4, minSize=(40, 40))
        if len(faces) == 0:
            continue
        # largest face
        x, y, fw, fh = max(faces, key=lambda f: f[2] * f[3])
        xs.append((x + fw / 2) / w)
    cap.release()
    if not xs:
        return None
    return round(sum(xs) / len(xs), 3)


def mix_bgm(
    video: Path,
    bgm: Path,
    dest: Path,
    *,
    speech_vol: float = 1.0,
    bgm_vol: float = 0.18,
    duck: bool = True,
) -> Path:
    """Mix background music under speech. Optional sidechain-style ducking via
    volume envelopes (lightweight, no sidechaincompress dependency)."""
    if not bgm.is_file():
        shutil.copy(video, dest)
        return dest
    # Loop BGM to video length; lower BGM; keep speech dominant
    if duck:
        # speech full, BGM quieter — approximate duck by fixed low bed
        af = (
            f"[1:a]volume={bgm_vol},aloop=loop=-1:size=2e+09,aformat=fltp[bg];"
            f"[0:a]volume={speech_vol}[sp];"
            f"[sp][bg]amix=inputs=2:duration=first:dropout_transition=2[a]"
        )
    else:
        af = (
            f"[1:a]volume={bgm_vol},aloop=loop=-1:size=2e+09[bg];"
            f"[0:a]volume={speech_vol}[sp];"
            f"[sp][bg]amix=inputs=2:duration=first[a]"
        )
    run_ffmpeg(
        "-i", str(video), "-i", str(bgm),
        "-filter_complex", af,
        "-map", "0:v:0", "-map", "[a]",
        "-c:v", "copy", "-c:a", "aac", "-shortest",
        "-movflags", "+faststart", str(dest),
        timeout=1800,
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
    meta_p = subprocess.run(
        ["yt-dlp", "--no-warnings", "--dump-json", "--no-download", url],
        capture_output=True, text=True, timeout=120,
    )
    if meta_p.returncode:
        raise RuntimeError(f"yt-dlp metadata failed: {meta_p.stderr[-500:]}")
    meta = json.loads(meta_p.stdout)
    p = subprocess.run(
        ["yt-dlp", "--no-warnings", "-f", "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b",
         "--merge-output-format", "mp4", "-o", str(work / "source.%(ext)s"), url],
        capture_output=True, text=True, timeout=7200,
    )
    src = work / "source.mp4"
    if not src.is_file():
        cands = sorted(work.glob("source.*"))
        if not cands:
            raise RuntimeError(f"yt-dlp download failed: {p.stderr[-500:]}")
        src = cands[0]
    return src, meta


def safe_job_dir(root: Path, job_id: str) -> Path:
    if not _SAFE_ID.match(job_id):
        raise ValueError("Invalid job id.")
    path = (root / job_id).resolve()
    if not str(path).startswith(str(root.resolve())):
        raise ValueError("Invalid job path.")
    return path
