"""SAYANOX CLIPFORGE worker: validated, persistent analysis/render jobs."""
from __future__ import annotations

import hmac
import json
import math
import os
import re
import shutil
import threading
import time
import zipfile
from collections import Counter, defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import ValidationError
from starlette.middleware.base import BaseHTTPMiddleware

import captions as subtitle_tools
import media
import pipeline
from captions import CAPTION_STYLES
from config import settings
from highlights import Segment, find_highlights
from jobs import JobConflict, JobStore, QueueFull, StorageFull
from schemas import AnalysisOptions, HighlightRequest, RenderRequest
from transcribe import available_engine

VERSION = "1.0.0"
MIN_CLIP_SEC = 5
MAX_CLIP_SEC = 180
_ZIP_LOCK = threading.Lock()


def build_store(data_dir: Path, concurrency: int, max_attempts: int,
                ttl_hours: float, max_total_gb: float) -> JobStore:
    result = JobStore(data_dir, concurrency=concurrency, max_attempts=max_attempts,
                      ttl_hours=ttl_hours, max_total_gb=max_total_gb,
                      max_pending=settings.max_pending_jobs)
    result.register_handler("analyze", pipeline.handle_analyze)
    result.register_handler("render", pipeline.handle_render)
    return result


store = build_store(settings.data_dir, settings.worker_concurrency, settings.max_attempts,
                    settings.job_ttl_hours, settings.max_total_storage_gb)


def _data_root() -> Path:
    return store.root


def _validation_message(errors: list[dict]) -> str:
    return "; ".join(f"{'.'.join(str(p) for p in e['loc']) or 'request'}: {e['msg']}" for e in errors[:5])


def _validate(model, data):
    try:
        return model.model_validate(data)
    except ValidationError as error:
        raise HTTPException(400, _validation_message(error.errors(include_context=False))) from error


class RateLimit(BaseHTTPMiddleware):
    def __init__(self, app, limit: int = 0, window: float = 60.0):
        super().__init__(app)
        self.static_limit = limit
        self.window = window
        self.hits: dict[str, deque] = defaultdict(deque)
        self.lock = threading.Lock()
        self.last_limit = None

    async def dispatch(self, request: Request, call_next):
        from config import settings as live_settings
        limit = live_settings.rate_limit_per_minute
        if request.method in ("POST", "PUT", "DELETE") and limit > 0:
            now = time.monotonic()
            ip = request.client.host if request.client else "unknown"
            with self.lock:
                context = (limit, str(store.root))
                if self.last_limit != context:
                    self.hits.clear()
                    self.last_limit = context
                # Bound the map; stale clients must not accumulate forever.
                for key in list(self.hits):
                    queue = self.hits[key]
                    while queue and now - queue[0] >= self.window:
                        queue.popleft()
                    if not queue:
                        del self.hits[key]
                queue = self.hits[ip]
                if len(queue) >= limit:
                    retry = max(1, math.ceil(self.window - (now - queue[0])))
                    return JSONResponse({"error": "Rate limit exceeded. Try again shortly."},
                                        status_code=429, headers={"Retry-After": str(retry)})
                queue.append(now)
        return await call_next(request)


def _token_valid(headers) -> bool:
    from config import settings as live_settings
    if not live_settings.api_token:
        return True
    actual = headers.get("authorization", "").encode("utf-8")
    expected = f"Bearer {live_settings.api_token}".encode("utf-8")
    return hmac.compare_digest(actual, expected)


def require_token(request: Request) -> None:
    if not _token_valid(request.headers):
        raise HTTPException(401, "Missing or invalid worker token.")


class RequestGuard:
    """Authenticate before multipart parsing and bound streamed upload bodies."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        from config import settings as live_settings
        from starlette.datastructures import Headers
        headers = Headers(scope=scope)
        if scope["path"] not in ("/", "/health", "/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect") and not _token_valid(headers):
            return await JSONResponse({"error": "Missing or invalid worker token."}, status_code=401)(scope, receive, send)
        if scope["method"] == "POST" and scope["path"] in ("/jobs/upload", "/clip"):
            maximum = (max(0, live_settings.max_upload_mb) + 72) * 1024 * 1024
            try:
                length = int(headers.get("content-length", "0"))
            except ValueError:
                return await JSONResponse({"error": "Invalid Content-Length."}, status_code=400)(scope, receive, send)
            if length > maximum:
                return await JSONResponse({"error": "Upload body exceeds the worker limit."}, status_code=413)(scope, receive, send)
            received = 0
            original_receive = receive
            async def bounded_receive():
                nonlocal received
                message = await original_receive()
                if message["type"] == "http.request":
                    received += len(message.get("body", b""))
                    if received > maximum:
                        raise HTTPException(413, "Upload body exceeds the worker limit.")
                return message
            receive = bounded_receive
        await self.app(scope, receive, send)


@asynccontextmanager
async def lifespan(app: FastAPI):
    store.start()
    stop = threading.Event()

    def janitor():
        while not stop.wait(600):
            try:
                store.cleanup()
            except OSError:
                pass

    thread = threading.Thread(target=janitor, daemon=True, name="clipforge-janitor")
    thread.start()
    try:
        yield
    finally:
        stop.set()
        store.shutdown()
        thread.join(timeout=1)


def create_app() -> FastAPI:
    result = FastAPI(title="SAYANOX CLIPFORGE Worker", version=VERSION, lifespan=lifespan)
    result.add_middleware(RateLimit, limit=settings.rate_limit_per_minute)
    result.add_middleware(RequestGuard)
    return result


app = create_app()


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, error: RequestValidationError):
    return JSONResponse({"error": _validation_message(error.errors())}, status_code=422)


@app.exception_handler(JobConflict)
async def job_conflict(request: Request, error: JobConflict):
    return JSONResponse({"error": str(error)}, status_code=409)


@app.exception_handler(QueueFull)
async def queue_full(request: Request, error: QueueFull):
    return JSONResponse({"error": str(error)}, status_code=503, headers={"Retry-After": "10"})


@app.exception_handler(StorageFull)
async def storage_full(request: Request, error: StorageFull):
    return JSONResponse({"error": str(error)}, status_code=507)


@app.exception_handler(OSError)
async def storage_error(request: Request, error: OSError):
    return JSONResponse({"error": "Worker storage could not be accessed. Free disk space and check volume permissions."}, status_code=507)


@app.get("/")
@app.get("/health")
def health():
    from config import settings as live_settings
    counts = Counter(job["status"] for job in store.list(None))
    ffmpeg, ffprobe = media.have_tool("ffmpeg"), media.have_tool("ffprobe")
    return {
        "ok": True, "ready": ffmpeg and ffprobe, "auth_required": bool(live_settings.api_token), "service": "clipforge-worker", "version": VERSION,
        "ffmpeg": ffmpeg, "ffprobe": ffprobe, "yt_dlp": media.have_tool("yt-dlp"),
        "youtube_enabled": os.getenv("CLIPFORGE_ALLOW_YTDLP", "").lower() in ("1", "true", "yes", "on"),
        "whisper_engine": available_engine(), "queue_jobs": counts["queued"] + counts["processing"],
        "jobs_by_status": dict(counts), "concurrency": store._concurrency,
        "max_pending_jobs": store.max_pending, "max_upload_mb": live_settings.max_upload_mb,
        "storage_bytes": store.total_size(), "max_storage_bytes": store.max_total_bytes,
        "clip_duration_range": [MIN_CLIP_SEC, MAX_CLIP_SEC], "caption_styles": list(CAPTION_STYLES),
    }


@app.get("/auth-check", dependencies=[Depends(require_token)])
def auth_check():
    return {"ok": True}


def _job_dir(job_id: str) -> Path:
    try:
        return media.safe_job_dir(_data_root(), job_id)
    except ValueError as error:
        raise HTTPException(400, "Invalid job id.") from error


def _job(job_id: str) -> dict:
    _job_dir(job_id)
    job = store.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found. It may have expired.")
    return job


def _save_stream(upload: UploadFile, destination: Path, limit_mb: int | None = None) -> int:
    from config import settings as live_settings
    maximum = limit_mb if limit_mb is not None else live_settings.max_upload_mb
    written = 0
    try:
        with destination.open("wb") as output:
            while chunk := upload.file.read(1024 * 1024):
                written += len(chunk)
                if written > maximum * 1024 * 1024:
                    raise HTTPException(413, f"Upload exceeds {maximum} MB limit.")
                output.write(chunk)
        if not written:
            raise HTTPException(400, "Empty upload.")
        return written
    except BaseException:
        destination.unlink(missing_ok=True)
        raise


def _validate_media_name(filename: str | None, allowed=None) -> str:
    if not filename:
        raise HTTPException(400, "Missing filename.")
    safe = Path(filename.replace("\\", "/")).name
    suffix = Path(safe).suffix.lower()
    allowed = allowed or media.ALLOWED_EXTENSIONS
    if suffix not in allowed:
        raise HTTPException(400, f"Unsupported file type '{suffix or safe}'. Allowed: " + ", ".join(sorted(allowed)))
    return safe


@app.post("/jobs/upload", dependencies=[Depends(require_token)])
def job_upload(
    request: Request, video: UploadFile = File(...), min_seconds: float = Form(15),
    max_seconds: float = Form(90), limit: int = Form(8), captions: UploadFile | None = File(None),
    bgm: UploadFile | None = File(None),
):
    name = _validate_media_name(video.filename)
    options = _validate(AnalysisOptions, {"min_seconds": min_seconds, "max_seconds": max_seconds, "limit": limit})
    if captions and captions.filename:
        _validate_media_name(captions.filename, {".srt"})
    if bgm and bgm.filename:
        _validate_media_name(bgm.filename, {".mp3", ".wav", ".m4a", ".aac", ".ogg"})
    job = store.create("analyze", {**options.model_dump(), "filename": name},
                       client=request.client.host if request.client else "", enqueue=False)
    work = _job_dir(job["id"])
    try:
        _save_stream(video, work / f"source{Path(name).suffix.lower()}")
        if captions and captions.filename:
            _save_stream(captions, work / "captions.srt", limit_mb=20)
        if bgm and bgm.filename:
            _save_stream(bgm, work / f"bgm{Path(bgm.filename).suffix.lower()}", limit_mb=50)
        store.enqueue(job["id"])
    except OSError as error:
        store.discard_prepared(job["id"])
        raise HTTPException(507, "Unable to save the upload. Check worker storage and permissions.") from error
    except BaseException:
        store.discard_prepared(job["id"])
        raise
    finally:
        for upload in (video, captions, bgm):
            if upload:
                upload.file.close()
    return {"job_id": job["id"], "status": "queued"}


def _youtube_params(payload: dict) -> dict:
    url = str(payload.get("url", "")).strip()
    try:
        parsed = urlsplit(url)
        if (parsed.scheme not in ("http", "https") or parsed.hostname not in
                ("youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "www.youtu.be")
                or parsed.username or parsed.password or parsed.port not in (None, 80, 443)):
            raise ValueError
        if "youtu.be" in parsed.hostname:
            video_id = parsed.path.strip("/")
        elif parsed.path.rstrip("/") == "/watch":
            video_id = parse_qs(parsed.query).get("v", [""])[0]
        else:
            match = re.fullmatch(r"/(?:shorts|live|embed)/([A-Za-z0-9_-]+)/*", parsed.path)
            video_id = match.group(1) if match else ""
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", video_id):
            raise ValueError
    except (ValueError, TypeError):
        raise HTTPException(400, "Enter a valid YouTube video URL (watch, Shorts, live or youtu.be).")
    options = _validate(AnalysisOptions, payload)
    return {"url": url, **options.model_dump()}


@app.post("/jobs/youtube", dependencies=[Depends(require_token)])
def job_youtube(request: Request, payload: dict):
    job = store.create("analyze", _youtube_params(payload), client=request.client.host if request.client else "")
    return {"job_id": job["id"], "status": "queued",
            "note": "YouTube ingestion requires CLIPFORGE_ALLOW_YTDLP=true and permission to process the video."}


def _copy_input(source: Path, destination: Path) -> None:
    if source.is_symlink():
        raise HTTPException(400, "Linked input files are not allowed.")
    try:
        os.link(source, destination)  # Immutable inputs: no unnecessary multi-GB copy.
    except OSError:
        shutil.copy2(source, destination)


@app.post("/jobs/render", dependencies=[Depends(require_token)])
def job_render(request: Request, payload: dict):
    options = _validate(RenderRequest, payload)
    parent = _job(options.parent_job)
    if parent["kind"] != "analyze" or parent["status"] != "completed":
        raise HTTPException(409, "Wait for the parent analysis to complete before rendering.")
    parent_dir = _job_dir(options.parent_job)
    sources = [path for path in parent_dir.glob("source.*") if path.suffix.lower() in media.ALLOWED_EXTENSIONS]
    if not sources:
        raise HTTPException(404, "Source media is missing. Upload the video again.")
    parent_result = parent.get("result") or {}
    if parent_result.get("has_video") is False:
        raise HTTPException(400, "This source contains audio only. Upload a video to render MP4 clips.")
    highlights = [item.model_dump() for item in options.highlights if item.selected]
    if not options.highlights:
        highlights = (parent_result.get("clips") or [])[:20]
    if not highlights:
        raise HTTPException(400, "Select at least one valid highlight.")
    source_duration = float(parent_result.get("duration") or 0)
    for highlight in highlights:
        if source_duration and (highlight["start"] >= source_duration or highlight["end"] > source_duration + 0.1):
            raise HTTPException(400, "Clip trim must stay within the source video duration.")
    for highlight in highlights:
        highlight["locked"] = options.render_mode == "exact"
    params = options.model_dump(exclude={"highlights"})
    params.update(highlights=highlights, vertical=options.aspect == "9:16")
    job = store.create("render", params, client=request.client.host if request.client else "", enqueue=False)
    work = _job_dir(job["id"])
    try:
        for pattern in ("source.*", "transcript.json", "captions.srt", "bgm.*"):
            for source in parent_dir.glob(pattern):
                if pattern == "source.*" and source.suffix.lower() not in media.ALLOWED_EXTENSIONS:
                    continue
                _copy_input(source, work / source.name)
        store.enqueue(job["id"])
    except BaseException:
        store.discard_prepared(job["id"])
        raise
    return {"job_id": job["id"], "status": "queued"}


@app.get("/jobs", dependencies=[Depends(require_token)])
def job_list(limit: int = 50, status: str = ""):
    if status and status not in ("preparing", "queued", "processing", "cancelling", "completed", "failed", "cancelled"):
        raise HTTPException(400, "Invalid job status filter.")
    rows = []
    for job in store.list(None):
        if status and job["status"] != status:
            continue
        rows.append({key: job.get(key) for key in
                     ("id", "kind", "status", "stage", "progress", "error", "attempts", "max_attempts", "created_at", "updated_at")}
                    | {"label": job["params"].get("filename") or job["params"].get("url") or "Render clips",
                       "parent_job": job["params"].get("parent_job")})
        if len(rows) >= max(1, min(200, limit)):
            break
    return {"jobs": rows}


@app.get("/jobs/{job_id}", dependencies=[Depends(require_token)])
def job_status(job_id: str):
    job = _job(job_id)
    return {"job_id": job["id"], **{key: job.get(key) for key in
            ("kind", "status", "stage", "progress", "attempts", "max_attempts", "error", "result", "created_at", "updated_at")},
            "parent_job": job["params"].get("parent_job"),
            "label": job["params"].get("filename") or job["params"].get("url") or "Render clips"}


@app.get("/jobs/{job_id}/files/{file_path:path}", dependencies=[Depends(require_token)])
def job_file(job_id: str, file_path: str):
    job = _job(job_id)
    work = _job_dir(job_id)
    if job["status"] == "preparing" or file_path.startswith("clips/") and job["status"] != "completed":
        raise HTTPException(404, "File is not ready yet.")
    if not media.allowed_artifact(file_path):
        raise HTTPException(404, "File not found.")
    target = (work / file_path).resolve()
    if not target.is_relative_to(work) or not target.is_file():
        raise HTTPException(404, "File not found.")
    types = {".srt": "application/x-subrip", ".vtt": "text/vtt", ".json": "application/json",
             ".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime",
             ".mkv": "video/x-matroska", ".avi": "video/x-msvideo", ".jpg": "image/jpeg", ".png": "image/png"}
    return FileResponse(target, media_type=types.get(target.suffix.lower()), filename=target.name,
                        content_disposition_type="inline",
                        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@app.get("/jobs/{job_id}/transcript", dependencies=[Depends(require_token)])
def job_transcript(job_id: str, format: str = "srt"):
    if format not in ("json", "srt", "vtt", "txt"):
        raise HTTPException(400, "Transcript format must be json, srt, vtt or txt.")
    _job(job_id)
    path = _job_dir(job_id) / "transcript.json"
    try:
        transcript = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise HTTPException(404, "Transcript is not available yet.")
    if transcript.get("engine") == "energy-fallback":
        raise HTTPException(409, "No speech transcript: install Whisper or upload an SRT sidecar and analyze again.")
    if format == "json":
        content, mime = json.dumps(transcript, ensure_ascii=False), "application/json"
    elif format == "txt":
        content = "\n".join(str(segment.get("text", "")) for segment in transcript.get("segments", [])) + "\n"
        mime = "text/plain"
    else:
        content = getattr(subtitle_tools, f"segments_to_{format}")(transcript.get("segments", []))
        mime = "text/vtt" if format == "vtt" else "application/x-subrip"
    return Response(content, media_type=mime, headers={"Cache-Control": "no-store",
                    "Content-Disposition": f'attachment; filename="transcript-{job_id[:8]}.{format}"'})


@app.get("/jobs/{job_id}/zip", dependencies=[Depends(require_token)])
def job_zip(job_id: str):
    job = _job(job_id)
    work = _job_dir(job_id)
    clips = work / "clips"
    mp4s = list(clips.glob("*.mp4")) if clips.is_dir() else []
    if not mp4s:
        raise HTTPException(404, "No MP4 clips to zip.")
    if job["status"] != "completed":
        raise HTTPException(409, "Wait for rendering to finish before downloading the bundle.")
    archive = work / "exports.zip"
    with _ZIP_LOCK:
        if not archive.is_file():
            temporary = work / ".exports.zip.tmp"
            try:
                with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as bundle:
                    for path in sorted(clips.iterdir()):
                        if (media.allowed_artifact(f"clips/{path.name}") and path.is_file()
                                and not path.is_symlink()):
                            bundle.write(path, arcname=path.name)
                    if (work / "render.json").is_file():
                        bundle.write(work / "render.json", arcname="render.json")
                temporary.replace(archive)
            finally:
                temporary.unlink(missing_ok=True)
    return FileResponse(archive, media_type="application/zip", filename=f"clipforge-{job_id[:8]}.zip",
                        headers={"Cache-Control": "private, no-store"})


@app.post("/jobs/{job_id}/cancel", dependencies=[Depends(require_token)])
def job_cancel(job_id: str):
    _job(job_id)
    job = store.cancel(job_id)
    return {"job_id": job["id"], "status": job["status"]}


@app.post("/jobs/{job_id}/retry", dependencies=[Depends(require_token)])
def job_retry(job_id: str):
    _job(job_id)
    job = store.retry(job_id)
    return {"job_id": job["id"], "status": job["status"]}


@app.delete("/jobs/{job_id}", dependencies=[Depends(require_token)])
def job_delete(job_id: str):
    _job(job_id)
    store.delete(job_id)
    return {"deleted": job_id}


@app.post("/jobs/cleanup", dependencies=[Depends(require_token)])
def jobs_cleanup():
    return store.cleanup()


@app.post("/score", dependencies=[Depends(require_token)])
def score_segments(payload: HighlightRequest):
    segments = [Segment(segment.start, segment.end, segment.text, segment.speech_score,
                        segment.emotion_score, segment.audio_score, segment.visual_score)
                for segment in payload.segments]
    return {"clips": find_highlights(segments, payload.min_seconds, payload.max_seconds, payload.limit)}


@app.post("/clip", dependencies=[Depends(require_token)])
def create_clip(video: UploadFile = File(...), start: float = Form(0), end: float = Form(30)):
    if not math.isfinite(start) or not math.isfinite(end) or start < 0 or not 0 < end - start <= 180:
        raise HTTPException(400, "Clip start must be non-negative and length must be 0–180 seconds.")
    name = _validate_media_name(video.filename, media.VIDEO_EXTENSIONS)
    params = {"start": start, "end": end, "vertical": False, "aspect": "16:9", "captions": False,
              "durations": [], "padding": 0, "highlights": [{"start": start, "end": end, "locked": True}]}
    job = store.create("render", params, enqueue=False)
    try:
        _save_stream(video, _job_dir(job["id"]) / f"source{Path(name).suffix.lower()}")
        store.enqueue(job["id"])
    except BaseException:
        store.discard_prepared(job["id"])
        raise
    finally:
        video.file.close()
    return {"job_id": job["id"], "duration": round(end - start, 3), "status": "queued",
            "download": f"/jobs/{job['id']}/files/clips/clip-01-landscape.mp4"}


# Register optional routes at import time, using the live store instead of
# capturing a stale store or hiding routes until a background thread starts.
from addon import mount
mount(app, lambda: store, require_token)
