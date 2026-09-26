# SAYANOX CLIPFORGE

No demo mode. Worker required.

## New pages

- `/jobs` — live worker job list
- `/projects` — saved projects on the worker volume

## Worker extras (after boot)

- `GET /jobs` job list
- `GET|POST /projects`
- `POST /translate` (LibreTranslate if `CLIPFORGE_TRANSLATE_URL` is set)
- `GET /stock-bgm` generated royalty-free sine beds (`soft` / `warm` / `pulse`)
- Drop `intro.mp4` / `outro.mp4` in the job folder or `data/bumpers/`
- Webhook: `CLIPFORGE_WEBHOOK_URL` on complete/fail (`worker/test_webhook.py`)

## Deploy

See [DEPLOY.md](DEPLOY.md) for Vercel web + GPU Whisper worker.
