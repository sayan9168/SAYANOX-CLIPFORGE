# Termux (Android) setup — SAYANOX CLIPFORGE

## Why installs failed before

Termux ships **rolling Python** (often 3.14). Older pins like `pydantic==2.10.4` pull `pydantic-core` that cannot build on 3.14 (PyO3 / jiter). Main `requirements.txt` now allows **pydantic ≥ 2.12**, which supports Python 3.14.

## One-shot

```bash
cd "$HOME"
pkg update -y
pkg install -y git python ffmpeg clang make rust
git clone https://github.com/sayan9168/SAYANOX-CLIPFORGE.git
bash SAYANOX-CLIPFORGE/scripts/termux-setup.sh
```

## Manual

```bash
cd "$HOME/SAYANOX-CLIPFORGE/worker"
export ANDROID_API_LEVEL=24
export PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1
python -m venv .venv && source .venv/bin/activate
pip install -U pip setuptools wheel maturin
pip install -r requirements-termux.txt
# Optional:
pip install yt-dlp
# Whisper is heavy on phones — only if you have RAM:
# pip install openai-whisper
```

## Run

**Terminal A (worker):**
```bash
cd "$HOME/SAYANOX-CLIPFORGE/worker"
source .venv/bin/activate
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

**Terminal B (web):**
```bash
cd "$HOME/SAYANOX-CLIPFORGE"
pkg install -y nodejs
npm install
echo 'WORKER_API_URL=http://127.0.0.1:8000' > .env.local
npm run dev -- -H 127.0.0.1 -p 3000
```

Open `http://127.0.0.1:3000`.

## Limits on phone

| Item | Advice |
|------|--------|
| Whisper | use `tiny` only |
| Long YouTube | may OOM — prefer short uploads |
| Storage | set `CLIPFORGE_DATA=$HOME/clipforge-data` |
| Path | always `cd "$HOME/..."` — never a folder named `~` |

## If pydantic still fails to build

1. `pip install -U 'pydantic>=2.12'` (not 2.10.x)
2. Install TUR older Python if available: `pkg install tur-repo && pkg install python3.12`
3. Or run worker on PC/VPS and only use the phone browser for the UI
