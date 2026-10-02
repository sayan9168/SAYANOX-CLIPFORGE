# ClipForge processing worker · v1.0

FastAPI + persistent job queue + FFmpeg. Upload only media you own or are authorized to process.

## Local run

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
# Install ffmpeg and ffprobe via your OS package manager.
# Optional speech/YouTube capabilities:
# .venv/bin/python -m pip install -r requirements-ml.txt
cp ../.env.example .env
.venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Set a private `WORKER_API_TOKEN` before exposing the service. `.env` is loaded automatically without overriding shell variables. Configure a writable persistent `CLIPFORGE_DATA`. Use one Uvicorn process per volume; tune `CLIPFORGE_WORKER_CONCURRENCY` rather than `--workers`.

## API

All endpoints except health/docs require `Authorization: Bearer <token>` when configured. Authentication and declared-length checks happen before multipart parsing; streamed bodies are bounded too.

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | Tool availability, limits, queue/storage and auth-required flag |
| `GET /auth-check` | Verify the configured bearer token |
| `POST /jobs/upload` | Multipart `video`, optional `captions` SRT and `bgm` audio; analysis controls |
| `POST /jobs/youtube` | Authorized video URL; requires enabled yt-dlp |
| `GET /jobs?limit=200&status=failed` | Latest jobs and optional status filter |
| `GET /jobs/{id}` | Kind, stage, progress, attempts, parent and result |
| `POST /jobs/render` | Completed video-analysis parent, selected highlights and export settings |
| `POST /jobs/{id}/cancel` | Cancel queued/running work safely |
| `POST /jobs/{id}/retry` | Retry failed/cancelled work; active retry requests are idempotent |
| `DELETE /jobs/{id}` | Delete media/metadata once work has stopped |
| `POST /jobs/cleanup` | Prune only inactive expired/over-quota jobs |
| `GET /jobs/{id}/files/{path}` | Allowlisted artifacts with HTTP byte-range support |
| `GET /jobs/{id}/transcript?format=srt` | Real transcript as SRT, VTT, TXT or JSON |
| `GET /jobs/{id}/zip` | Completed MP4s, covers, subtitles and render manifest; disk-backed archive |
| `GET/POST /projects` | Read/write snapshots under `x-clipforge-user` workspace namespace |
| `GET/DELETE /projects/{id}` | Load/delete a workspace's project snapshot |
| `POST /translate` | Optional LibreTranslate bridge |
| `POST /score` | Bounded, finite transcript-segment scoring |
| `POST /clip` | Authenticated legacy upload/trim endpoint (0–180 second clip length) |

## Lifecycle and recovery

`preparing → queued → processing → completed / failed`

Cancellation transitions `processing → cancelling → cancelled`. FFmpeg/yt-dlp process groups are interrupted; Whisper may finish its current inference segment/stage. Active files cannot be deleted during processing. Progress checks also cooperate with cancellation.

Jobs are only queued after their inputs/params are complete. Metadata is written atomically; interrupted WAVs/downloads are not published as source caches. Restart recovers queued/processing jobs, finishes pending cancellation and marks incomplete preparation as a failed upload requiring re-upload.

A real SRT takes precedence over Whisper. Missing/failed speech engines use explicitly labeled timeline windows; those labels are not exported as speech subtitles. Audio-only uploads can be analyzed/transcribed but cannot produce video MP4s. Face detection is optional and falls back to a centered crop.

`render_mode=exact` preserves trims. `render_mode=target` fits each selection to the nearest requested duration, clamped to the source. Render settings include aspect, caption style/burning, grade, first-2s hook zoom, BGM volume/ducking and optional face crop. Per-clip SRT/VTT always uses actual clipped time bounds when a real transcript exists.

Projects are metadata snapshots, not permanent media backups or a login system. Cleanup skips project/stock/model directories and active job dependencies. See [../DEPLOY.md](../DEPLOY.md) for hosting limits and security.

## Tests

```bash
PYTHONPATH=. .venv/bin/python -m pytest -q
```

FFmpeg media integration tests need both tools on PATH; otherwise they skip. No external YouTube videos, speech-model downloads or GPU are needed.
