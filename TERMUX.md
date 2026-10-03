# Termux / Android · ClipForge v1.0

## Lightweight setup

```bash
pkg update -y
pkg install -y git
# If not already cloned:
git clone https://github.com/sayan9168/SAYANOX-CLIPFORGE.git
bash "$HOME/SAYANOX-CLIPFORGE/scripts/termux-setup.sh"
```

The script reuses an existing virtual environment, preserves existing `.env` files, generates a private worker token on first setup and creates matching web configuration. It does not reinstall heavy speech models. Rolling Termux Python needs modern Pydantic (2.12+); Rust/maturin are available if a wheel needs compiling. The Termux requirements avoid Uvicorn's optional native uvloop/httptools dependencies.

## Start

Terminal A:

```bash
cd "$HOME/SAYANOX-CLIPFORGE/worker"
source .venv/bin/activate
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Terminal B:

```bash
cd "$HOME/SAYANOX-CLIPFORGE"
npm run dev:termux
```

Next.js 15 already uses Webpack by default; no unsupported `--webpack` flag is needed. Open `http://127.0.0.1:3000` on the same phone. For remote/browser previews, bind both servers to `0.0.0.0` and protect access; the browser still uses relative API URLs. `WORKER_API_URL=http://127.0.0.1:8000` is only a server-to-server address on the phone.

## Caption workflow without Whisper

1. Select **Upload file**.
2. Add a real `.srt` sidecar first (optional background audio can also be attached).
3. Set analysis lengths appropriately; for a short test video use a 5-second minimum.
4. Choose/drop your source video.
5. Pick/trim clips and render. Download MP4/SRT/VTT or the ZIP bundle.

Without SRT/Whisper, highlight windows are based on timeline/audio/scenes and labeled honestly; fake speech captions are not generated. Downloaded SRTs and burned Bengali/Hindi captions need real transcript text and suitable device fonts.

## Phone limits

The setup defaults to 512 MB source uploads, 1800-second source duration, one worker and one FFmpeg thread. Start much smaller in practice; final 1080p renders and speech inference can be expensive on a phone. Settings live in `worker/.env` and are loaded automatically. Use `$HOME/clipforge-data` for writable persistent storage.

Optional:

```bash
cd "$HOME/SAYANOX-CLIPFORGE/worker"
source .venv/bin/activate
pip install yt-dlp
# Enable CLIPFORGE_ALLOW_YTDLP=true only for authorized videos.
# Speech models are heavy and device-dependent:
# pip install openai-whisper
```

If a dependency still cannot build on rolling Python, use a supported older Python package if available, or run the worker on a PC/VPS and use the phone as a browser. No device/GPU compatibility is guaranteed without testing on that hardware. Keep worker/web tokens matched; health diagnostics report a mismatch before submission.
