# Termux real speech-to-text (whisper.cpp)

`faster-whisper` / `openai-whisper` need PyTorch + often `av` — they break on Termux Python 3.14.

**Use [whisper.cpp](https://github.com/ggerganov/whisper.cpp)** instead: native C++, works on Android, same model family as Whisper.

ClipForge auto-detects it (engine order: faster-whisper → openai-whisper → **whisper.cpp** → energy-fallback).

## 1) Build whisper.cpp on Termux

```bash
pkg update -y
pkg install -y git clang make cmake wget

cd "$HOME"
git clone https://github.com/ggerganov/whisper.cpp.git
cd whisper.cpp
cmake -B build
cmake --build build -j$(nproc)
```

Binary should appear at:
`$HOME/whisper.cpp/build/bin/whisper-cli`
(or `main` on older checkouts)

## 2) Download a small model

```bash
cd "$HOME/whisper.cpp"
# tiny ≈ 75MB — best for phones
bash ./models/download-ggml-model.sh tiny
# optional: base
# bash ./models/download-ggml-model.sh base
```

Model path example:
`$HOME/whisper.cpp/models/ggml-tiny.bin`

## 3) Point ClipForge at it (optional env)

```bash
export WHISPER_CPP_BIN="$HOME/whisper.cpp/build/bin/whisper-cli"
export WHISPER_CPP_MODEL="$HOME/whisper.cpp/models/ggml-tiny.bin"
export WHISPER_MODEL=tiny
export CLIPFORGE_DATA="$HOME/clipforge-data"
export CLIPFORGE_ALLOW_YTDLP=true
```

If binaries/models sit in the default locations above, env vars are optional.

## 4) Start worker

```bash
cd "$HOME/SAYANOX-CLIPFORGE/worker"
source .venv/bin/activate
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Check:
```bash
curl -s http://127.0.0.1:8000/health
# whisper_engine should mention whisper.cpp when detected
```

## Notes

| Item | Advice |
|------|--------|
| Model | `tiny` only on phone |
| RAM | close other apps |
| Speed | short clips first |
| Quality | below desktop faster-whisper, but real words |

You do **not** need `pip install faster-whisper` on Termux when whisper.cpp is set up.
