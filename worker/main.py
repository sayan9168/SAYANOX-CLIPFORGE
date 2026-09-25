"""ClipForge processing worker — FastAPI app.

Pipeline: Web -> Job API -> Worker Queue -> Transcription -> Highlight Engine
          -> FFmpeg -> Generated Clips -> Preview / Download

Security: bearer-token auth, per-IP rate limiting, upload validation
(extension + streamed size limit), path-traversal-safe file serving and
automatic TTL/size cleanup of abandoned jobs.
"""
from __future__ import annotations

import json
import re
import shutil
import threading
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

import media
import pipeline
from config import settings
from highlights import Segment, find_highlights
from jobs import JobStore
from schemas import HighlightRequest
from transcribe import available_engine

VERSION = "0.4.0"
store = JobStore(settings.data_dir, concurrency=settings.worker_concurrency,
                 max_attempts=settings.max_attempts, ttl_hours=settings.job_ttl_hours,
                 max_total_gb=settings.max_total_storage_gb)
store.register_handler("analyze", pipeline.handle_analyze)
store.register_handler("render", pipeline.handle_render)

_YT = re.compile(r"^https?://(www\.)?(youtube\.com|youtu\.be)/[A-Za-z0-9._%\-/?&=#]+$", re.I)


# ---------------- security middleware ----------------
class RateLimit(BaseHTTPMiddleware):
    """Simple fixed-window per-client-IP limiter for mutating endpoints."""

    def __init__(self, app, limit: int = 0, window: float = 60.0):
        super().__init__(app)
        self.static_limit = limit
        self.window = window
        self.hits: dict[str, deque] = defaultdict(deque)
        self.lock = threading.Lock()

    async def dispatch(self, request: Request, call_next):
        from config import settings as live_settings
        limit = live_settings.rate_limit_per_minute or self.static_limit
        if limit != getattr(self, "_active_limit", None):
            self._active_limit = limit
            self.hits.clear()
        if request.method in ("POST", "PUT", "DELETE") and limit > 0:
            ip = request.client.host if request.client else "unknown"
            now = time.time()
            with self.lock:
                q = self.hits[ip]
                while q and now - q[0] > self.window:
                    q.popleft()
                if len(q) >= limit:
                    return JSONResponse({"error": "Rate limit exceeded. Try again shortly."},
                                        status_code=429)
                q.append(now)
        return await call_next(request)


def require_token(request: Request) -> None:
    from config import settings as live_settings
    token = live_settings.api_token
    if not token:
        return  # open mode (local dev)
    header = request.headers.get("authorization", "")
    if header != f"Bearer {token}":
        raise HTTPException(status_code=401, detail="Missing or invalid worker token.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    store.start()
    stop = threading.Event()

    def janitor():
        while not stop.wait(600):  # every 10 minutes
            try:
                store.cleanup()
            except Exception:
                pass

    t = threading.Thread(target=janitor, daemon=True, name="clipforge-janitor")
    t.start()
    yield
    stop.set()
    store.shutdown()


app = FastAPI(title="SAYANOX CLIPFORGE Worker", version=VERSION, lifespan=lifespan)
app.add_middleware(RateLimit, limit=settings.rate_limit_per_minute)


# ---------------- basic endpoints ----------------
@app.get("/health")
def health():
    return {
        "ok": True, "service": "clipforge-worker", "version": VERSION,
        "ffmpeg": media.have_tool("ffmpeg"), "ffprobe": media.have_tool("ffprobe"),
        "yt_dlp": media.have_tool("yt-dlp"), "whisper_engine": available_engine(),
        "queue_jobs": sum(1 for j in store.list(200) if j["status"] in ("queued", "processing")),
        "storage_bytes": store.total_size(),
    }


def _save_stream(upload: UploadFile, dest: Path, limit_mb: int | None = None) -> int:
    """Stream an upload to disk enforcing the size cap; returns bytes written."""
    from config import settings as live_settings
    limit = (limit_mb if limit_mb is not None else live_settings.max_upload_mb) * 1024 * 1024
    written = 0
    with dest.open("wb") as f:
        while chunk := upload.file.read(1024 * 1024):
            written += len(chunk)
            if written > limit:
                f.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(413, f"Upload exceeds {live_settings.max_upload_mb} MB limit.")
            f.write(chunk)
    if written == 0:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, "Empty upload.")
    return written


def _validate_media_name(filename: str | None) -> str:
    if not filename:
        raise HTTPException(400, "Missing filename.")
    safe = Path(filename).name  # strip any directory components
    suffix = Path(safe).suffix.lower()
    if suffix not in media.ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file type '{suffix or safe}'. Allowed: "
                                 + ", ".join(sorted(media.ALLOWED_EXTENSIONS)))
    return safe


# ---------------- job endpoints ----------------
@app.post("/jobs/upload", dependencies=[Depends(require_token)])
async def job_upload(request: Request, video: UploadFile = File(...),
                     min_seconds: float = Form(15), max_seconds: float = Form(90),
                     limit: int = Form(8), captions: UploadFile | None = File(None)):
    form = await request.form()
    if isinstance(captions, list):  # defensive: duplicate field -> reject
        raise HTTPException(400, "Duplicate 'captions' field.")
    name = _validate_media_name(video.filename)
    if max_seconds < min_seconds:
        raise HTTPException(400, "max_seconds must be >= min_seconds")
    job = store.create("analyze", {"min_seconds": min_seconds, "max_seconds": max_seconds,
                                   "limit": limit, "filename": name},
                       client=request.client.host if request.client else "")
    work = media.safe_job_dir(settings.data_dir, job["id"])
    src = work / f"source{Path(name).suffix}"
    _save_stream(video, src)
    captions_file = form.get("captions")
    if isinstance(captions_file, UploadFile) and captions_file.filename:
        # optional SRT sidecar used when no local Whisper backend is installed
        suffix = Path(captions_file.filename).suffix.lower()
        if suffix in (".srt",):
            _save_stream(captions_file, work / "captions.srt", limit_mb=20)
    (work / "params.json").write_text(json.dumps(job["params"]), encoding="utf-8")
    return {"job_id": job["id"], "status": "queued"}


@app.post("/jobs/youtube", dependencies=[Depends(require_token)])
async def job_youtube(request: Request, payload: dict):
    url = str(payload.get("url", "")).strip()
    if not _YT.match(url):
        raise HTTPException(400, "Enter a valid YouTube URL.")
    params = {
        "url": url,
        "min_seconds": float(payload.get("min_seconds", 15)),
        "max_seconds": float(payload.get("max_seconds", 90)),
        "limit": int(payload.get("limit", 8)),
    }
    job = store.create("analyze", params, client=request.client.host or "")
    work = media.safe_job_dir(settings.data_dir, job["id"])
    (work / "params.json").write_text(json.dumps(params), encoding="utf-8")
    return {"job_id": job["id"], "status": "queued",
            "note": "YouTube ingestion runs only when CLIPFORGE_ALLOW_YTDLP=true "
                    "and requires content you are authorised to process."}


@app.post("/jobs/render", dependencies=[Depends(require_token)])
async def job_render(request: Request, payload: dict):
    parent_id = str(payload.get("parent_job", ""))
    try:
        parent = media.safe_job_dir(settings.data_dir, parent_id) if parent_id else None
    except ValueError:
        raise HTTPException(400, "Invalid parent job id.")
    if not parent or not parent.is_dir():
        raise HTTPException(404, "Parent analyze job not found.")
    highlights = payload.get("highlights") or []
    durations = [int(d) for d in payload.get("durations", settings.clip_durations)]
    bad = [d for d in durations if d not in settings.clip_durations]
    if bad:
        raise HTTPException(400, f"Durations must be from {list(settings.clip_durations)}")
    style = str(payload.get("caption_style", "default"))
    if style not in ("default", "karaoke", "clean"):
        raise HTTPException(400, "caption_style must be default|karaoke|clean")
    params = {
        "highlights": highlights, "durations": durations,
        "vertical": bool(payload.get("vertical", True)),
        "captions": bool(payload.get("captions", True)),
        "caption_style": style,
        "padding": float(payload.get("padding", settings.padding_seconds)),
    }
    if not highlights:
        pj = parent / "job.json"
        if pj.is_file():
            result = json.loads(pj.read_text(encoding="utf-8")).get("result") or {}
            params["highlights"] = result.get("clips", [])[:len(durations) or 1]
    job = store.create("render", params, client=request.client.host or "")
    work = media.safe_job_dir(settings.data_dir, job["id"])
    # hard-link (fallback copy) the source + transcript so render is sandboxed
    for pat in ("source.*", "transcript.json", "captions.srt"):
        for f in parent.glob(pat):
            if f.suffix == ".json" and pat.startswith("source"):
                continue
            target = work / f.name
            try:
                shutil.copy(f, target)
            except OSError:
                pass
    (work / "params.json").write_text(json.dumps(params), encoding="utf-8")
    return {"job_id": job["id"], "status": "queued"}


@app.get("/jobs/{job_id}", dependencies=[Depends(require_token)])
def job_status(job_id: str):
    try:
        media.safe_job_dir(settings.data_dir, job_id)
    except ValueError:
        raise HTTPException(400, "Invalid job id.")
    job = store.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found.")
    return {
        "job_id": job["id"], "kind": job["kind"], "status": job["status"],
        "progress": job["progress"], "attempts": job["attempts"],
        "max_attempts": job["max_attempts"], "error": job["error"],
        "result": job.get("result"),
    }


@app.get("/jobs/{job_id}/files/{file_path:path}", dependencies=[Depends(require_token)])
def job_file(job_id: str, file_path: str):
    try:
        work = media.safe_job_dir(settings.data_dir, job_id)
    except ValueError:
        raise HTTPException(400, "Invalid job id.")
    target = (work / file_path).resolve()
    if not str(target).startswith(str(work.resolve())) or not target.is_file():
        raise HTTPException(404, "File not found.")
    media_types = {".mp4": "video/mp4", ".ass": "text/plain", ".json": "application/json",
                   ".wav": "audio/wav", ".webvtt": "text/vtt"}
    return FileResponse(target, media_type=media_types.get(target.suffix, "application/octet-stream"),
                        filename=target.name)


@app.post("/jobs/{job_id}/retry", dependencies=[Depends(require_token)])
def job_retry(job_id: str):
    try:
        media.safe_job_dir(settings.data_dir, job_id)
    except ValueError:
        raise HTTPException(400, "Invalid job id.")
    job = store.retry(job_id)
    if not job:
        raise HTTPException(404, "Job not found.")
    return {"job_id": job["id"], "status": job["status"]}


@app.delete("/jobs/{job_id}", dependencies=[Depends(require_token)])
def job_delete(job_id: str):
    try:
        media.safe_job_dir(settings.data_dir, job_id)
    except ValueError:
        raise HTTPException(400, "Invalid job id.")
    if not store.delete(job_id):
        raise HTTPException(404, "Job not found.")
    return {"deleted": job_id}


@app.post("/jobs/cleanup", dependencies=[Depends(require_token)])
def jobs_cleanup():
    return store.cleanup()


# ---------------- legacy / stateless endpoints (kept compatible) ----------------
@app.post("/score")
async def score_segments(payload: HighlightRequest):
    try:
        segs = [Segment(float(x["start"]), float(x["end"]), str(x.get("text", "")),
                        float(x.get("speech_score", .5)), float(x.get("emotion_score", .5)),
                        float(x.get("audio_score", .5)), float(x.get("visual_score", .5)))
                for x in payload.segments]
        return {"clips": find_highlights(segs, payload.min_seconds, payload.max_seconds,
                                         payload.limit)}
    except (KeyError, TypeError, ValueError) as e:
        raise HTTPException(400, f"Invalid segment data: {e}")


@app.post("/clip")
async def create_clip(video: UploadFile = File(...), start: float = Form(0),
                      end: float = Form(30)):
    """Legacy one-shot endpoint — now backed by the render job queue."""
    if end <= start or end - start > 300:
        raise HTTPException(400, "Clip must be 0-300 seconds.")
    name = _validate_media_name(video.filename)
    job_id = store.create("render", {"start": start, "end": end})["id"]
    work = media.safe_job_dir(settings.data_dir, job_id)
    src = work / f"source{Path(name).suffix}"
    _save_stream(video, src)
    (work / "params.json").write_text(json.dumps({
        "start": start, "end": end, "vertical": False, "captions": False,
        "durations": [], "padding": 0.0,
        "highlights": [{"start": start, "end": min(end, start + 300)}]}), encoding="utf-8")
    return {"job_id": job_id, "duration": round(end - start, 3),
            "download": f"/jobs/{job_id}/files/clips/clip-01-landscape.mp4",
            "status": "queued"}
