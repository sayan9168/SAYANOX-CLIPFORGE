# SAYANOX CLIPFORGE · v1.0

A local-first video clipping studio: Next.js web UI + a separate FastAPI/FFmpeg worker. **Real media only; no demo results.**

## What's new

- **Recoverable workflow:** browser draft/preset autosave, reopen jobs, sequential polling with reconnect/backoff, safe cancel and kind-aware retry.
- **Advanced analysis:** choose 5–180 second windows and up to 20 highlights; submit up to 5 authorized YouTube videos per batch.
- **Precise exports:** exact trims or smart target lengths; 9:16, 1:1 and 16:9; explicit color grade and a first-two-second hook zoom.
- **Real subtitles:** attach an SRT before uploading, or use Whisper. Download full transcripts as SRT/VTT/TXT/JSON and per-clip SRT/VTT. VTT can also play as an optional caption track.
- **Background audio:** upload a track, control its volume and duck it under speech; otherwise use a synthesized soft tone bed.
- **Projects:** save/load/update/delete picks, trims, notes and export settings; export a JSON snapshot. Workspace keys organize projects, **not user authentication**.
- **Job dashboard:** search/status filters, progress stages, cancel/retry/open/delete and safe retention pruning.
- **Diagnostics:** worker/tool availability, token mismatch detection, upload/storage limits and honest no-Whisper warnings.

## Quick start

Requires Node.js 22, Python 3.11+ and `ffmpeg` + `ffprobe` on the worker's PATH.

```bash
npm ci
cp .env.example .env.local
python -m venv .venv
.venv/bin/python -m pip install -r worker/requirements.txt
cp .env.example worker/.env
```

Set the **same** randomly generated `WORKER_API_TOKEN` in `.env.local` and `worker/.env` before exposing either service. `worker/.env` is loaded automatically; shell environment variables take precedence. Never commit these files.

Terminal A:

```bash
cd worker
../.venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Terminal B, at the repository root:

```bash
npm run dev
```

Open the web server on port 3000. The browser only uses relative `/api/...` URLs; `WORKER_API_URL` is a **server-side** connection. On a remote deployment, use the worker's reachable address, not the visitor's localhost.

### Optional speech/YouTube capabilities

```bash
.venv/bin/python -m pip install -r worker/requirements-ml.txt
# Or install only the capability you need:
# .venv/bin/python -m pip install faster-whisper yt-dlp
```

Enable YouTube ingestion with `CLIPFORGE_ALLOW_YTDLP=true` **only for videos you own or are authorized to process**. The UI directs you to uploads if yt-dlp is missing/disabled.

Without a working Whisper engine, the worker can rank timeline/audio/scene windows, but it **does not invent speech captions**. Attach a real SRT for accurate subtitles on lightweight/Termux deployments. Speech inference and initial model downloads depend on hardware/network availability. Face detection requires optional OpenCV; otherwise vertical crops are centered.

Language tabs localize social calls-to-action. They do not automatically translate the source hook. Optional `CLIPFORGE_TRANSLATE_URL` enables the worker's `/translate` bridge.

## Docker / hosting / Android

- [DEPLOY.md](DEPLOY.md): Docker Compose, Vercel limits, CPU/GPU prerequisites and deployment security.
- [worker/README.md](worker/README.md): worker API and lifecycle.
- [TERMUX.md](TERMUX.md): lightweight Android setup.

**Important:** a worker token protects the worker, not public web users. Put authentication/access control in front of the web application before sharing a private deployment. Projects retain metadata; job media still expires according to retention settings. Back up exports and the persistent worker volume.

## Checks

```bash
npm run lint
npm run typecheck
npm test
npm run build
PYTHONPATH=worker .venv/bin/python -m pytest worker -q

# Browser regression suite (UI API responses are mocked, not a demo app mode):
npx playwright install --with-deps chromium
npm run test:e2e
```

Worker tests include real FFmpeg upload → SRT analysis → render → range/ZIP downloads, all three aspect ratios, parallel renders, cancellation, restart recovery, validation and project isolation. Media integration tests skip only when FFmpeg/FFprobe are absent; CI installs them. No GPU, external video downloads or model downloads are required for the test suite.

The npm lockfile makes installs reproducible; patched PostCSS is explicitly overridden. Generated media, caches, virtual environments and secrets stay out of Git.
