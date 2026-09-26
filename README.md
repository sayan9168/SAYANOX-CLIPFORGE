# SAYANOX CLIPFORGE

**AI-powered video highlight & short-form clip engine**

Turn long videos into share-ready vertical (or square / landscape) clips with smart moment detection, Whisper transcription, burned captions, and FFmpeg rendering — all under your control.

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Stack](https://img.shields.io/badge/stack-Next.js%20%2B%20FastAPI%20%2B%20Whisper%20%2B%20FFmpeg-green)](#architecture)

---

## What it does

1. Paste a YouTube URL (or upload media when worker supports it)
2. Worker downloads / ingests → extracts audio → transcribes with Whisper
3. Fuses transcript + audio energy + scene changes into ranked highlights
4. You pick duration / aspect / caption style → FFmpeg renders real MP4s
5. Preview + download vertical 9:16 (or 1:1 / 16:9) clips with burned captions

**Privacy-first design:** processing happens on *your* worker. No third-party AI API required for core pipeline.

---

## Architecture

```
Browser (Next.js)
    │
    ├─ POST /api/analyze  ──► Worker /jobs/youtube  (or demo mode)
    ├─ GET  /api/jobs/status?job=…
    ├─ POST /api/jobs/render
    └─ GET  /api/jobs/files?job=…&path=clips/…

Worker (FastAPI + job queue)
    analyze → download → Whisper → energy + scenes → highlight scoring
    render  → pad windows → crop (speaker-aware) → burn ASS captions → MP4
```

| Layer | Tech |
|-------|------|
| Web UI | Next.js 15, React 19, TypeScript |
| Worker | FastAPI, job store, rate-limit, token auth |
| Speech | faster-whisper / Whisper (CPU or GPU) |
| Media | FFmpeg + ffprobe + yt-dlp |
| Captions | Styled ASS (default / karaoke / clean / bold) |

---

## Features (v0.6)

### Highlight engine
- Hook-pattern detection + information density + sentence completeness
- Audio energy peaks + scene-change density
- Speech ratio / silence awareness
- Overlap deduplication + ranked top-N
- **Auto titles & reasons** generated from transcript signals

### Rendering
- Target lengths: 15 / 30 / 60 / 90 s
- Aspect ratios: **9:16** (default), 1:1, 16:9
- Caption styles: default · karaoke · clean · **bold**
- Speaker-aware vertical crop (center tracking)
- Faststart MP4 ready for social upload

### Platform
- Real job queue with progress, retries, TTL cleanup
- Bearer-token auth + per-IP rate limiting
- Upload size / storage caps
- Demo mode when worker is not configured (safe local UI)
- Docker-ready worker

---

## Quick start

### 1. Web app

```bash
git clone https://github.com/sayan9168/SAYANOX-CLIPFORGE.git
cd SAYANOX-CLIPFORGE
npm install
cp .env.example .env.local   # optional: set WORKER_API_URL
npm run dev
```

Open http://localhost:3000

### 2. Worker (required for real analysis)

```bash
cd worker
# install system deps: ffmpeg, ffprobe, yt-dlp
pip install -r requirements.txt
# optional ML stack:
# pip install -r requirements-ml.txt

# run
uvicorn main:app --host 0.0.0.0 --port 8000

# or Docker
docker compose up --build
```

In the web app env:

```env
WORKER_API_URL=http://localhost:8000
WORKER_API_TOKEN=your-secret-token   # optional but recommended
```

On the worker side set the same token via `WORKER_API_TOKEN`.

YouTube ingestion only runs when `CLIPFORGE_ALLOW_YTDLP=true` and you have rights to the content.

---

## Environment reference

| Variable | Where | Default | Purpose |
|----------|-------|---------|---------|
| `WORKER_API_URL` | Web | — | Base URL of FastAPI worker |
| `WORKER_API_TOKEN` | Web + Worker | empty | Shared bearer token |
| `CLIPFORGE_DATA` | Worker | `/tmp/clipforge` | Job storage root |
| `CLIPFORGE_MAX_UPLOAD_MB` | Worker | 2048 | Upload size cap |
| `CLIPFORGE_JOB_TTL_HOURS` | Worker | 24 | Auto-delete old jobs |
| `CLIPFORGE_RATE_LIMIT` | Worker | 30 | POST requests / IP / min |
| `WHISPER_MODEL` | Worker | base | tiny / base / small / … |
| `WHISPER_DEVICE` | Worker | cpu | cpu / cuda |
| `CLIPFORGE_ALLOW_YTDLP` | Worker | false | Enable YouTube download |
| `CLIPFORGE_WORKER_CONCURRENCY` | Worker | 1 | Parallel jobs |

---

## API surface (worker)

| Method | Path | Notes |
|--------|------|-------|
| GET | `/health` | ffmpeg / whisper / queue status |
| POST | `/jobs/youtube` | Queue analyze from URL |
| POST | `/jobs/upload` | Queue analyze from file |
| POST | `/jobs/render` | Queue clip render from parent job |
| GET | `/jobs/{id}` | Status + progress + result |
| GET | `/jobs/{id}/files/{path}` | Download clip / artifacts |
| POST | `/jobs/{id}/retry` | Re-queue failed job |
| DELETE | `/jobs/{id}` | Remove job + files |

All mutating routes respect the bearer token when configured.

---

## Development

```bash
# Web
npm run dev

# Worker tests
cd worker && pytest -q
```

---

## Roadmap ideas

- Batch URL / playlist mode
- Local file drag-drop end-to-end in UI
- Optional BGM + volume ducking
- Face-detection crop fallback
- Multi-language caption presets (Bengali / Hindi font stacks)
- ZIP bulk download

---

## License

Apache-2.0 © Sayanox / sayan9168

**Only process media you own or have explicit permission to use.**
