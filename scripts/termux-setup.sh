#!/data/data/com.termux/files/usr/bin/bash
# SAYANOX CLIPFORGE — Termux one-shot setup
set -euo pipefail

export ANDROID_API_LEVEL="${ANDROID_API_LEVEL:-24}"
export PYO3_USE_ABI3_FORWARD_COMPATIBILITY="${PYO3_USE_ABI3_FORWARD_COMPATIBILITY:-1}"

ROOT="${HOME}/SAYANOX-CLIPFORGE"
if [ ! -d "$ROOT" ]; then
  echo "Cloning repo into $ROOT ..."
  git clone https://github.com/sayan9168/SAYANOX-CLIPFORGE.git "$ROOT"
fi

cd "$ROOT/worker"
echo "Python: $(python --version 2>&1)"
echo "ANDROID_API_LEVEL=$ANDROID_API_LEVEL"

pkg install -y python ffmpeg git clang make rust binutils 2>/dev/null || true

rm -rf .venv
python -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -U pip setuptools wheel maturin
pip install -r requirements-termux.txt

mkdir -p "${HOME}/clipforge-data"
cat > .env << EOF
CLIPFORGE_DATA=${HOME}/clipforge-data
WORKER_API_TOKEN=
WHISPER_MODEL=tiny
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
CLIPFORGE_WORKER_CONCURRENCY=1
EOF

echo ""
echo "OK. Start worker with:"
echo "  cd $ROOT/worker && source .venv/bin/activate"
echo "  python -m uvicorn main:app --host 127.0.0.1 --port 8000"
echo ""
echo "Optional YouTube download support:"
echo "  pip install yt-dlp"
echo "Optional speech-to-text (heavy):"
echo "  pip install openai-whisper"
