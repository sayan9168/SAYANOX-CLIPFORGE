# ClipForge Processing Worker

A separate FastAPI + FFmpeg worker for authorized video files.

## Run

```bash
docker compose up --build
```

Health: `GET /health`

Create a clip by multipart uploading an authorized video to `POST /clip` with:
- `start`: start time in seconds
- `end`: end time in seconds

The worker intentionally accepts uploaded files rather than scraping or bypassing access controls on third-party platforms. Add transcript/highlight analysis only for media you are authorized to process.