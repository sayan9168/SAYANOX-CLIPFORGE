# SAYANOX CLIPFORGE

AI highlight engine. **No demo mode.** Analyze and render only work when the FastAPI worker is running.

## Required setup

```bash
# worker
cd worker
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000

# web
cp .env.example .env.local
# WORKER_API_URL=http://127.0.0.1:8000
npm install && npm run dev
```

If `WORKER_API_URL` is missing the API returns **503** — it will not invent fake clips.

YouTube ingest needs `CLIPFORGE_ALLOW_YTDLP=true` and rights to the video.

## Live features

- YouTube URL (one or many, newline/comma) + file upload / drag-drop
- Whisper transcript + hook/speech/emotion/audio/scene scoring
- Clip picker, locked trim, platform presets, custom 5–180s
- Captions: default/karaoke/clean/bold/bengali/hindi + first-2s hook title
- EN / বাংলা / हिंदी post copy for YouTube, Instagram, TikTok
- BGM ducking, face-crop fallback, ZIP download, JPEG thumbs
- Job history, retry, delete, optional `CLIPFORGE_WEBHOOK_URL`
- CI: web build + worker tests + worker image

## Not included (needs your platform credentials)

Direct auto-upload to YouTube / Instagram / TikTok accounts.

## License

Apache-2.0. Only process media you own or may use.
