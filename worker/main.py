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

VERSION = "0.6.1"


def build_store(data_dir: Path, concurrency: int, max_attempts: int,
                ttl_hours: float, max_total_gb: float) -> JobStore:
    store = JobStore(
        Path(data_dir),
        concurrency=concurrency,
        max_attempts=max_attempts,
        ttl_hours=ttl_hours,
        max_total_gb=max_total_gb,
    )
    store.register_handler("analyze", pipeline.handle_analyze)
    store.register_handler("render", pipeline.handle_render)
    return store


store = build_store(
    settings.data_dir,
    settings.worker_concurrency,
    settings.max_attempts,
    settings.job_ttl_hours,
    settings.max_total_storage_gb,
)

_YT = re.compile(r"^https?://(www\.)?(youtube\.com|youtu\.be)/[A-Za-z0-9._%\-/?&=#]+$", re.I)


def _data_root() -> Path:
    """Canonical job storage root — always the live JobStore root.

    Tests monkeypatch `store`; using store.root (not settings.data_dir) keeps
    path checks and persistence on the same directory.
    """
    return Path(store.root)


class RateLimit(BaseHTTPMiddleware):
    def __init__(self, app, limit: int = 0, window: float = 60.0):
        super().__init__(app)
        self.static_limit = limit
        self.window = window

    async def dispatch(self, request: Request, call_next):
        from config import settings as live_settings
        limit = live_settings.rate_limit_per_minute or self.static_limit
        root = request.app
        seen = set()
        while getattr(root, "app", None) is not None and id(root) not in seen:
            seen.add(id(root))
            root = root.app
        hits = getattr(root, "_clipforge_rate_hits", None)
        if hits is None:
            hits = defaultdict(deque)
            setattr(root, "_clipforge_rate_hits", hits)
        lock = getattr(root, "_clipforge_rate_lock", None)
        if lock is None:
            lock = threading.Lock()
            setattr(root, "_clipforge_rate_lock", lock)
        if getattr(root, "_clipforge_rate_limit", None) != limit:
            setattr(root, "_clipforge_rate_limit", limit)
            with lock:
                hits.clear()
        if request.method in ("POST", "PUT", "DELETE") and limit > 0:
            ip = request.client.host if request.client else "unknown"
            now = time.time()
            with lock:
                q = hits[ip]
                while q and now - q[0] > self.window:
                    q.popleft()
                if len(q) >= limit:
                    return JSONResponse(
                        {"error": "Rate limit exceeded. Try again shortly."},
                        status_code=429,
                    )
                q.append(now)
        return await call_next(request)


def require_token(request: Request) -> None:
    from config import settings as live_settings
    token = live_settings.api_token
    if not token:
        return
    header = request.headers.get("authorization", "")
    if header != f"Bearer {token}":
        raise HTTPException(status_code=401, detail="Missing or invalid worker token.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    store.start()
    stop = threading.Event()

    def janitor():
        while not stop.wait(600):
            try:
                store.cleanup()
            except Exception:
                pass

    t = threading.Thread(target=janitor, daemon=True, name="clipforge-janitor")
    t.start()
    yield
    stop.set()
    store.shutdown()


def create_app() -> FastAPI:
    app = FastAPI(title="SAYANOX CLIPFORGE Worker", version=VERSION, lifespan=lifespan)
    app.add_middleware(RateLimit, limit=settings.rate_limit_per_minute)
    return app


app = create_app()


@app.get("/health")
def health():
    return {
        "ok": True,
        "service": "clipforge-worker",
        "version": VERSION,
        "ffmpeg": media.have_tool("ffmpeg"),
        "ffprobe": media.have_tool("ffprobe"),
        "yt_dlp": media.have_tool("yt-dlp"),
        "whisper_engine": available_engine(),
        "queue_jobs": sum(
            1 for j in store.list(200) if j["status"] in ("queued", "processing")
        ),
        "storage_bytes": store.total_size(),
    }


def _save_stream(upload: UploadFile, dest: Path, limit_mb: int | None = None) -> int:
    from config import settings as live_settings
    limit = (limit_mb if limit_mb is not None else live_settings.max_upload_mb) * 1024 * 1024
    written = 0
    with dest.open("wb") as f:
        while chunk := upload.file.read(1024 * 1024):
            written += len(chunk)
            if written > limit:
                f.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(
                    413, f"Upload exceeds {live_settings.max_upload_mb} MB limit."
                )
            f.write(chunk)
    if written == 0:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, "Empty upload.")
    return written


def _validate_media_name(filename: str | None) -> str:
    if not filename:
        raise HTTPException(400, "Missing filename.")
    safe = Path(filename).name
    suffix = Path(safe).suffix.lower()
    if suffix not in media.ALLOWED_EXTENSIONS:
        raise HTTPException(
            400,
            f"Unsupported file type '{suffix or safe}'. Allowed: "
            + ", ".join(sorted(media.ALLOWED_EXTENSIONS)),
        )
    return safe


@app.post("/jobs/upload", dependencies=[Depends(require_token)])
async def job_upload(
    request: Request,
    video: UploadFile = File(...),
    min_seconds: float = Form(15),
    max_seconds: float = Form(90),
    limit: int = Form(8),
    captions: UploadFile | None = File(None),
):
    form = await request.form()
    if isinstance(captions, list):
        raise HTTPException(400, "Duplicate 'captions' field.")
    name = _validate_media_name(video.filename)
    if max_seconds < min_seconds:
        raise HTTPException(400, "max_seconds must be >= min_seconds")
    job = store.create(
        "analyze",
        {
            "min_seconds": min_seconds,
            "max_seconds": max_seconds,
            "limit": limit,
            "filename": name,
        },
        client=request.client.host if request.client else "",
    )
    work = media.safe_job_dir(_data_root(), job["id"])
    work.mkdir(parents=True, exist_ok=True)
    src = work / f"source{Path(name).suffix}"
    _save_stream(video, src)
    captions_file = form.get("captions")
    if isinstance(captions_file, UploadFile) and captions_file.filename:
        suffix = Path(captions_file.filename).suffix.lower()
        if suffix in (".srt",):
            _save_stream(captions_file, work / "captions.srt", limit_mb=20)
    (work / "params.json").write_text(json.dumps(job["params"]), encoding="utf-8")
    return {"job_id": job["id"], "status": "queued"}


def _youtube_params(payload: dict) -> dict:
    url = str(payload.get("url", "")).strip()
    if not _YT.match(url):
        raise HTTPException(400, "Enter a valid YouTube URL.")
    try:
        min_s = float(payload.get("min_seconds", 15))
        max_s = float(payload.get("max_seconds", 90))
        limit = int(payload.get("limit", 8))
    except (TypeError, ValueError):
        raise HTTPException(400, "min_seconds/max_seconds/limit must be numeric.")
    if min_s <= 0 or max_s < min_s or not (1 <= limit <= 20):
        raise HTTPException(
            400, "Require 0 < min_seconds <= max_seconds and 1 <= limit <= 20."
        )
    return {"url": url, "min_seconds": min_s, "max_seconds": max_s, "limit": limit}


@app.post("/jobs/youtube", dependencies=[Depends(require_token)])
async def job_youtube(request: Request, payload: dict):
    params = _youtube_params(payload)
    job = store.create("analyze", params, client=request.client.host or "")
    work = media.safe_job_dir(_data_root(), job["id"])
    work.mkdir(parents=True, exist_ok=True)
    (work / "params.json").write_text(json.dumps(params), encoding="utf-8")
    # Batch mode (feature B1#3): a single URL that expands to many videos
    # (playlist/watch?v=...&list=...) may pass `batch: true` — the analyze
    # handler then enumerates and queues one child job per entry.
    if payload.get("batch"):
        job["params"]["batch"] = True
        (work / "job.json").write_text(json.dumps(job), encoding="utf-8")
    return {
        "job_id": job["id"],
        "status": "queued",
        "note": "YouTube ingestion runs only when CLIPFORGE_ALLOW_YTDLP=true "
        "and requires content you are authorised to process.",
    }


@app.post("/jobs/render", dependencies=[Depends(require_token)])
async def job_render(request: Request, payload: dict):
    highlights = payload.get("highlights") or []
    raw_durations = payload.get("durations", settings.clip_durations)
    try:
        durations = [int(d) for d in raw_durations]
    except (TypeError, ValueError):
        raise HTTPException(400, "durations must be numeric seconds.")
    # Custom lengths are allowed (UI min/max seconds, feature B1#14); the
    # legacy preset chips (15/30/60/90) remain the default. Anything outside
    # a sane range is rejected instead of silently clamped. Duration
    # validation runs BEFORE the parent lookup so bad input always answers 400.
    bad = [d for d in durations if not (5 <= d <= 600)]
    if bad:
        raise HTTPException(400, "Durations must be between 5 and 600 seconds.")
    if not durations:
        durations = [max(settings.clip_durations[0], 15)]
    style = str(payload.get("caption_style", "default"))
    if style not in ("default", "karaoke", "clean", "bold"):
        raise HTTPException(400, "caption_style must be default|karaoke|clean|bold")
    aspect = str(payload.get("aspect", "9:16"))
    if aspect not in ("9:16", "1:1", "16:9"):
        aspect = "9:16"
    vertical = aspect == "9:16"
    parent_id = str(payload.get("parent_job", ""))
    try:
        parent = media.safe_job_dir(_data_root(), parent_id) if parent_id else None
    except ValueError:
        raise HTTPException(400, "Invalid parent job id.")
    if not parent or not parent.is_dir():
        raise HTTPException(404, "Parent analyze job not found.")
    params = {
        "highlights": highlights,
        "durations": durations,
        "vertical": vertical,
        "aspect": aspect,
        "captions": bool(payload.get("captions", True)),
        "caption_style": style,
        "padding": float(payload.get("padding", settings.padding_seconds)),
    }
    if not highlights:
        pj = parent / "job.json"
        if pj.is_file():
            result = json.loads(pj.read_text(encoding="utf-8")).get("result") or {}
            params["highlights"] = result.get("clips", [])[: len(durations) or 1]
    job = store.create("render", params, client=request.client.host or "")
    work = media.safe_job_dir(_data_root(), job["id"])
    work.mkdir(parents=True, exist_ok=True)
    params["parent_job"] = parent_id
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
        media.safe_job_dir(_data_root(), job_id)
    except ValueError:
        raise HTTPException(400, "Invalid job id.")
    job = store.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found.")
    body = {
        "job_id": job["id"],
        "kind": job["kind"],
        "status": job["status"],
        "progress": job["progress"],
        "attempts": job["attempts"],
        "max_attempts": job["max_attempts"],
        "error": job["error"],
        "result": job.get("result"),
    }
    if job["kind"] == "render" and job["status"] == "processing":
        done = [c.get("file") for c in (job.get("result") or {}).get("clips", [])]
        if done:
            body["clips_done"] = done
    return body


@app.get("/jobs/{job_id}/files/{file_path:path}", dependencies=[Depends(require_token)])
def job_file(job_id: str, file_path: str):
    try:
        work = media.safe_job_dir(_data_root(), job_id)
    except ValueError:
        raise HTTPException(400, "Invalid job id.")
    target = (work / file_path).resolve()
    if not str(target).startswith(str(work.resolve())) or not target.is_file():
        raise HTTPException(404, "File not found.")
    media_types = {
        ".mp4": "video/mp4",
        ".ass": "text/plain",
        ".json": "application/json",
        ".wav": "audio/wav",
        ".webvtt": "text/vtt",
    }
    return FileResponse(
        target,
        media_type=media_types.get(target.suffix, "application/octet-stream"),
        filename=target.name,
    )


@app.post("/jobs/{job_id}/retry", dependencies=[Depends(require_token)])
def job_retry(job_id: str):
    try:
        media.safe_job_dir(_data_root(), job_id)
    except ValueError:
        raise HTTPException(400, "Invalid job id.")
    job = store.retry(job_id)
    if not job:
        raise HTTPException(404, "Job not found.")
    return {"job_id": job["id"], "status": job["status"]}


@app.delete("/jobs/{job_id}", dependencies=[Depends(require_token)])
def job_delete(job_id: str):
    try:
        media.safe_job_dir(_data_root(), job_id)
    except ValueError:
        raise HTTPException(400, "Invalid job id.")
    if not store.delete(job_id):
        raise HTTPException(404, "Job not found.")
    return {"deleted": job_id}


@app.get("/jobs/{job_id}/zip", dependencies=[Depends(require_token)])
def job_zip(job_id: str):
    """Stream every rendered clip of a render job as one download.zip."""
    try:
        work = media.safe_job_dir(_data_root(), job_id)
    except ValueError:
        raise HTTPException(400, "Invalid job id.")
    job = store.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found.")
    clips_dir = work / "clips"
    files = sorted(p for p in clips_dir.glob("*.mp4") if p.is_file()) \
        if clips_dir.is_dir() else []
    if not files:
        raise HTTPException(404, "No rendered clips to bundle yet.")

    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.write(f, arcname=f.name)
    buf.seek(0)
    from fastapi.responses import StreamingResponse

    filename = f"clipforge-{job_id}-clips.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/jobs/cleanup", dependencies=[Depends(require_token)])
def jobs_cleanup():
    return store.cleanup()


@app.post("/score")
async def score_segments(payload: HighlightRequest):
    try:
        segs = [
            Segment(
                float(x["start"]),
                float(x["end"]),
                str(x.get("text", "")),
                float(x.get("speech_score", 0.5)),
                float(x.get("emotion_score", 0.5)),
                float(x.get("audio_score", 0.5)),
                float(x.get("visual_score", 0.5)),
            )
            for x in payload.segments
        ]
        return {
            "clips": find_highlights(
                segs, payload.min_seconds, payload.max_seconds, payload.limit
            )
        }
    except (KeyError, TypeError, ValueError) as e:
        raise HTTPException(400, f"Invalid segment data: {e}")


@app.post("/clip")
async def create_clip(
    video: UploadFile = File(...), start: float = Form(0), end: float = Form(30)
):
    if end <= start or end - start > 300:
        raise HTTPException(400, "Clip must be 0-300 seconds.")
    name = _validate_media_name(video.filename)
    job_id = store.create("render", {"start": start, "end": end})["id"]
    work = media.safe_job_dir(_data_root(), job_id)
    work.mkdir(parents=True, exist_ok=True)
    src = work / f"source{Path(name).suffix}"
    _save_stream(video, src)
    (work / "params.json").write_text(
        json.dumps(
            {
                "start": start,
                "end": end,
                "vertical": False,
                "captions": False,
                "durations": [],
                "padding": 0.0,
                "highlights": [{"start": start, "end": min(end, start + 300)}],
            }
        ),
        encoding="utf-8",
    )
    return {
        "job_id": job_id,
        "duration": round(end - start, 3),
        "download": f"/jobs/{job_id}/files/clips/clip-01-landscape.mp4",
        "status": "queued",
    }
