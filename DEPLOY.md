# Deploy ClipForge v1.0

Deploy the web and worker from the same revision. A web-only deployment cannot analyze or render videos.

## Recommended: one-host Docker Compose

Copy `.env.example` to `.env.local`, then set a long random `WORKER_API_TOKEN`. Keep it private.

```bash
docker compose --env-file .env.local up --build -d
```

The root `compose.yaml` runs:

- Web on `0.0.0.0:3000`.
- CPU Whisper worker on the internal Compose network (`http://worker:8000`). It is **not exposed on a public host port**.
- Persistent worker media, models and project metadata in the `clipforge-data` volume.

The browser uses same-origin `/api/...` proxies, not container names or localhost. Check `/api/health` in the web UI. Use a reverse proxy for TLS and **web-user authentication**. Do not point multiple Uvicorn processes/containers at the same job volume; the persistent queue uses one process with configurable internal concurrency.

The default image is CPU-oriented (`WHISPER_DEVICE=cpu`, `WHISPER_COMPUTE_TYPE=int8`). The first speech-analysis job may need a model download. SRT uploads bypass that dependency.

## Web on Vercel, worker on a separate host

1. Import the repository with its root as the Next.js project directory.
2. Set `WORKER_API_URL` to the worker's reachable HTTPS address.
3. Set `WORKER_API_TOKEN` to the same private value used by the worker.
4. Deploy both components from v1.0.

FFmpeg, disk-backed queues and Whisper cannot run inside Vercel functions. **Serverless request-size, response-size and execution-time limits still apply to uploads and downloads.** A 2048 MB worker limit does not override those provider limits. Use the self-hosted web/Compose deployment for large video files and bundles. The upload proxy streams bodies without buffering them in Next.js, but it cannot bypass hosting limits.

## Standalone worker

```bash
cd worker
docker build -t clipforge-worker .
docker run -p 8000:8000 \
  --env-file .env \
  -e CLIPFORGE_DATA=/data \
  -e WHISPER_DEVICE=cpu -e WHISPER_COMPUTE_TYPE=int8 \
  -v clipforge-data:/data \
  clipforge-worker
```

Restrict the worker port by firewall/private networking. Use `CLIPFORGE_ALLOW_YTDLP=true` only for authorized media. GPU inference requires a compatible NVIDIA runtime, CTranslate2/CUDA/cuDNN libraries and a GPU-capable image; simply adding `--gpus all` to the CPU image is not sufficient. Start with `tiny`/`base` and concurrency 1, then tune against your hardware.

The worker image installs Noto fonts for Bengali/Hindi caption styles. For non-Docker hosts, install suitable fonts and optional OpenCV if face detection is needed.

## Retention and safety

- `CLIPFORGE_MAX_UPLOAD_MB`: per-source upload limit (SRT 20 MB, BGM 50 MB).
- `CLIPFORGE_MAX_VIDEO_SECONDS`: source duration ceiling, default 7200.
- `CLIPFORGE_MAX_PENDING_JOBS`: bounded admission queue, default 100.
- `CLIPFORGE_FFMPEG_THREADS`: FFmpeg thread budget, default 2.
- `CLIPFORGE_JOB_TTL_HOURS`: creation-time TTL for inactive jobs, default 24.
- `CLIPFORGE_MAX_STORAGE_GB`: storage/admission budget, default 50.

Cleanup never removes active jobs, their parent jobs, project directories, stock tracks or unrelated volume directories. When protected data alone exceeds quota it reports `over_limit` rather than deleting it. Cancel active jobs and wait for `cancelled` before deleting them. FFmpeg/yt-dlp stop promptly; speech inference stops at supported stage/segment boundaries.

Project snapshots do not pin media forever. Export ZIP/JSON backups before media TTL expires. Use a durable volume; `/tmp` is not a long-term project store.

**Workspace keys are namespaces, not login credentials.** Every authorized worker client can access its shared job list. A worker token is not a substitute for authentication on the public Next.js proxy.

## Optional translation / webhook

Point `CLIPFORGE_TRANSLATE_URL` to a reachable LibreTranslate `/translate` endpoint to enable worker-side translation. Without it, source text is retained; the UI only localizes social calls-to-action. Configure `CLIPFORGE_WEBHOOK_URL` for completion/failure/cancellation notifications. Webhook receivers must be trusted and protected; no signed multi-user account system is included.
