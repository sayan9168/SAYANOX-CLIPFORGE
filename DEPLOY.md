# ClipForge deploy

## Web (Vercel, one click)

1. Import `sayan9168/SAYANOX-CLIPFORGE` in Vercel.
2. Root directory: repo root.
3. Env:
   - `WORKER_API_URL` = public URL of the worker (`https://worker.example.com`)
   - `WORKER_API_TOKEN` = same token as the worker
4. Deploy. Framework: Next.js.

Worker cannot run on Vercel (FFmpeg + Whisper + disk). Host it separately.

## Worker (GPU Whisper)

```bash
cd worker
docker build -t clipforge-worker .
docker run --gpus all -p 8000:8000 \
  -e WHISPER_DEVICE=cuda \
  -e WHISPER_COMPUTE_TYPE=float16 \
  -e WHISPER_MODEL=medium \
  -e CLIPFORGE_ALLOW_YTDLP=true \
  -e WORKER_API_TOKEN=change-me \
  -e CLIPFORGE_WEBHOOK_URL=https://your.app/api/hooks/clipforge \
  -e CLIPFORGE_TRANSLATE_URL=http://127.0.0.1:5000/translate \
  -v clipforge-data:/tmp/clipforge \
  clipforge-worker
```

CPU fallback: omit `--gpus all`, set `WHISPER_DEVICE=cpu` and `WHISPER_COMPUTE_TYPE=int8`.

## LibreTranslate (optional real EN↔BN/HI)

```bash
docker run -p 5000:5000 libretranslate/libretranslate
# then CLIPFORGE_TRANSLATE_URL=http://127.0.0.1:5000/translate
```

Without that URL the worker keeps the built-in language packs.
