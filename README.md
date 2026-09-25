# SAYANOX CLIPFORGE

AI-powered video highlight and clip generation platform.

## Current stack

- Next.js web application
- Separate FastAPI processing worker
- FFmpeg clip cutting/transcoding
- Pluggable highlight scoring
- GitHub Actions CI
- Docker deployment for the worker

## Architecture

```
Web UI
  -> /api/analyze
  -> highlight scoring
  -> authorized media processing worker
  -> FFmpeg
  -> MP4 clip
```

The processing worker accepts uploaded media that the operator is authorized to use. It does not scrape, bypass access controls, DRM, private videos, or platform restrictions.

## Worker

```bash
cd worker
docker compose up --build
```

Set `WORKER_API_URL` and optional `WORKER_API_TOKEN` in the web application's environment to connect the API route to the worker.

## Development

```bash
npm install
npm run dev
```

## License

Apache-2.0
