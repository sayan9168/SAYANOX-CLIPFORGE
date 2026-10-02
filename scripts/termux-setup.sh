#!/data/data/com.termux/files/usr/bin/bash
# SAYANOX CLIPFORGE — lightweight, non-destructive Termux setup
set -euo pipefail
export ANDROID_API_LEVEL="${ANDROID_API_LEVEL:-24}"
export PYO3_USE_ABI3_FORWARD_COMPATIBILITY="${PYO3_USE_ABI3_FORWARD_COMPATIBILITY:-1}"

ROOT="${HOME}/SAYANOX-CLIPFORGE"
pkg install -y python ffmpeg git clang make rust binutils nodejs
if [ ! -d "$ROOT" ]; then
  git clone https://github.com/sayan9168/SAYANOX-CLIPFORGE.git "$ROOT"
fi
cd "$ROOT/worker"
echo "Python: $(python --version 2>&1)"
# Re-running setup must not wipe the environment, settings or worker token.
if [ ! -d .venv ]; then python -m venv .venv; fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -U "pip>=26.2.1" "setuptools>=84.0.0" wheel maturin
pip install -r requirements-termux.txt
mkdir -p "${HOME}/clipforge-data"
if [ ! -f .env ]; then
  TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
  cat > .env <<EOF
CLIPFORGE_DATA=${HOME}/clipforge-data
WORKER_API_TOKEN=${TOKEN}
WHISPER_MODEL=tiny
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
CLIPFORGE_WORKER_CONCURRENCY=1
CLIPFORGE_FFMPEG_THREADS=1
CLIPFORGE_MAX_UPLOAD_MB=512
CLIPFORGE_MAX_VIDEO_SECONDS=1800
CLIPFORGE_ALLOW_YTDLP=false
EOF
  chmod 600 .env
fi
if [ ! -f "$ROOT/.env.local" ]; then
  python - "$ROOT/.env.local" <<'PY'
import sys
from pathlib import Path
from dotenv import dotenv_values
values = dotenv_values('.env')
Path(sys.argv[1]).write_text('WORKER_API_URL=http://127.0.0.1:8000\nWORKER_API_TOKEN=' + str(values.get('WORKER_API_TOKEN') or '') + '\n', encoding='utf-8')
PY
  chmod 600 "$ROOT/.env.local"
fi
cd "$ROOT"
npm ci
printf '\nReady. Start in two terminals:\n'
printf '  cd %s/worker && source .venv/bin/activate\n' "$ROOT"
printf '  python -m uvicorn main:app --host 127.0.0.1 --port 8000\n'
printf '  cd %s && npm run dev:termux\n' "$ROOT"
printf '\nOpen http://127.0.0.1:3000. Attach SRT before choosing your video for real captions.\n'
printf 'Optional: pip install yt-dlp, then enable CLIPFORGE_ALLOW_YTDLP in worker/.env.\n'
