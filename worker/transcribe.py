"""Transcription adapters: faster-whisper, openai-whisper, whisper.cpp, energy fallback.

Normalised shape:
    {"language": str, "segments": [{"start","end","text"}], "engine": str}
"""
from __future__ import annotations

import json
import os
import re
import shutil
import threading
from contextlib import contextmanager
from pathlib import Path

from execution import check_cancelled, run_process

_LOCK = threading.Lock()
_MODEL = None
_MODEL_NAME = ""

_TS = re.compile(
    r"(?:(\d+):)?(\d{1,2}):(\d{2})[,.](\d{1,3})"
)


@contextmanager
def _model_lock():
    while not _LOCK.acquire(timeout=0.25):
        check_cancelled()
    try:
        check_cancelled()
        yield
    finally:
        _LOCK.release()


def _ffprobe_duration(path: Path) -> float:
    try:
        p = run_process(
            [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "json", str(path),
            ],
            capture_output=True, text=True, timeout=60,
        )
        if p.returncode == 0:
            return float(json.loads(p.stdout).get("format", {}).get("duration") or 0)
    except Exception:
        check_cancelled()
    return 0.0


def _parse_ts(s: str) -> float:
    m = _TS.search(str(s).strip())
    if not m:
        try:
            return float(s)
        except (TypeError, ValueError):
            return 0.0
    h = int(m.group(1) or 0)
    mi, sec, ms = int(m.group(2)), int(m.group(3)), int(m.group(4).ljust(3, "0")[:3])
    return h * 3600 + mi * 60 + sec + ms / 1000.0


def energy_chunk_transcript(audio_path: Path, chunk: float = 25.0) -> dict:
    """No-ML fallback when no STT backend is available."""
    duration = _ffprobe_duration(audio_path)
    if duration <= 0:
        duration = 60.0
    chunk = max(5.0, float(chunk))
    segs = []
    t = 0.0
    idx = 1
    while t < duration - 0.5:
        end = min(t + chunk, duration)
        segs.append({
            "start": round(t, 3),
            "end": round(end, 3),
            "text": f"Highlight window {idx} ({int(t)}s–{int(end)}s)",
        })
        t = end
        idx += 1
    if not segs:
        segs = [{"start": 0.0, "end": round(duration, 3), "text": "Full clip"}]
    return {"language": "unknown", "segments": segs, "engine": "energy-fallback"}


def _whisper_cpp_bin() -> str | None:
    env = os.getenv("WHISPER_CPP_BIN", "").strip()
    if env and Path(env).is_file() and os.access(env, os.X_OK):
        return env
    for name in ("whisper-cli", "whisper-cpp", "main"):
        found = shutil.which(name)
        if found:
            return found
    home = Path.home()
    for cand in (
        home / "whisper.cpp" / "build" / "bin" / "whisper-cli",
        home / "whisper.cpp" / "build" / "bin" / "main",
        home / "whisper.cpp" / "main",
        Path("/data/data/com.termux/files/home/whisper.cpp/build/bin/whisper-cli"),
    ):
        if cand.is_file() and os.access(cand, os.X_OK):
            return str(cand)
    return None


def _whisper_cpp_model(model_name: str) -> Path | None:
    env = os.getenv("WHISPER_CPP_MODEL", "").strip()
    if env and Path(env).is_file():
        return Path(env)
    # Map openai-style names to ggml files
    key = (model_name or "tiny").lower().replace("whisper-", "")
    names = [
        f"ggml-{key}.bin",
        f"ggml-{key}.en.bin",
        "ggml-tiny.bin",
        "ggml-base.bin",
    ]
    roots = [
        Path.home() / "whisper.cpp" / "models",
        Path.home() / "models",
        Path("/data/data/com.termux/files/home/whisper.cpp/models"),
        Path.cwd() / "models",
    ]
    for root in roots:
        for n in names:
            p = root / n
            if p.is_file():
                return p
    return None


def _segs_from_whisper_cpp_json(data: dict) -> list[dict]:
    segs: list[dict] = []
    # Newer whisper.cpp json
    transcription = data.get("transcription") or data.get("segments") or []
    if isinstance(transcription, list):
        for item in transcription:
            if not isinstance(item, dict):
                continue
            text = (item.get("text") or "").strip()
            if not text:
                continue
            ts = item.get("timestamps") or {}
            if "from" in ts and "to" in ts:
                start, end = _parse_ts(ts["from"]), _parse_ts(ts["to"])
            else:
                start = float(item.get("offsets", {}).get("from", item.get("start", 0)) or 0)
                end = float(item.get("offsets", {}).get("to", item.get("end", start)) or start)
                # offsets sometimes in ms
                if start > 1000 or end > 1000:
                    start, end = start / 1000.0, end / 1000.0
            if end <= start:
                end = start + 0.5
            segs.append({"start": round(start, 3), "end": round(end, 3), "text": text})
    return segs


def whisper_cpp_transcribe(audio_path: Path, model_name: str = "tiny") -> dict | None:
    """Termux-friendly STT via whisper.cpp binary (no PyTorch / no av)."""
    binary = _whisper_cpp_bin()
    model = _whisper_cpp_model(model_name)
    if not binary or not model:
        return None

    out_base = audio_path.with_suffix("")  # audio → json beside wav
    # whisper.cpp writes <stem>.json when -oj is set
    cmd = [
        binary,
        "-m", str(model),
        "-f", str(audio_path),
        "-oj",  # json output
        "-l", os.getenv("WHISPER_CPP_LANG", "auto"),
        "-t", os.getenv("WHISPER_CPP_THREADS", "4"),
    ]
    # Some builds use different flag names; ignore unknown via best-effort run
    try:
        p = run_process(cmd, capture_output=True, text=True, timeout=int(os.getenv("WHISPER_CPP_TIMEOUT", "1800")))
    except Exception:
        check_cancelled()
        return None

    json_path = Path(str(out_base) + ".json")
    if not json_path.is_file():
        # Some builds write next to cwd
        alt = Path.cwd() / (audio_path.stem + ".json")
        if alt.is_file():
            json_path = alt
    if not json_path.is_file():
        return None
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    segs = _segs_from_whisper_cpp_json(data)
    if not segs:
        return None
    lang = data.get("result", {}).get("language") or data.get("language") or "unknown"
    return {"language": lang, "segments": segs, "engine": "whisper.cpp"}


def transcribe(audio_path: Path, model_name: str = "base",
               device: str = "cpu", compute_type: str = "int8") -> dict:
    """Timestamped transcript. Prefer ML backends, then whisper.cpp, then energy."""
    global _MODEL, _MODEL_NAME
    check_cancelled()

    # 1) faster-whisper (desktop / VPS)
    try:
        from faster_whisper import WhisperModel  # type: ignore
        with _model_lock():
            key = f"fw:{model_name}:{device}:{compute_type}"
            if _MODEL is None or _MODEL_NAME != key:
                _MODEL = WhisperModel(model_name, device=device, compute_type=compute_type)
                _MODEL_NAME = key
            raw, info = _MODEL.transcribe(str(audio_path), vad_filter=True)
            segs = []
            for segment in raw:
                check_cancelled()
                segs.append({
                    "start": round(segment.start, 3),
                    "end": round(segment.end, 3),
                    "text": segment.text.strip(),
                })
            return {"language": info.language, "segments": segs, "engine": "faster-whisper"}
    except Exception:
        check_cancelled()

    # 2) openai-whisper
    try:
        import whisper  # type: ignore
        with _model_lock():
            key = f"ow:{model_name}:{device}"
            if _MODEL is None or _MODEL_NAME != key:
                _MODEL = whisper.load_model(model_name, device="cpu" if device == "cpu" else device)
                _MODEL_NAME = key
            result = _MODEL.transcribe(str(audio_path))
            segs = [
                {
                    "start": round(float(s["start"]), 3),
                    "end": round(float(s["end"]), 3),
                    "text": s["text"].strip(),
                }
                for s in result.get("segments", [])
            ]
            return {
                "language": result.get("language", "unknown"),
                "segments": segs,
                "engine": "openai-whisper",
            }
    except Exception:
        check_cancelled()

    # 3) whisper.cpp binary — Termux-compatible real STT
    check_cancelled()
    cpp = whisper_cpp_transcribe(audio_path, model_name=model_name or "tiny")
    if cpp and cpp.get("segments"):
        return cpp

    # 4) last resort
    return energy_chunk_transcript(audio_path)


def available_engine() -> str:
    try:
        import faster_whisper  # noqa: F401
        return "faster-whisper"
    except Exception:
        pass
    try:
        import whisper  # noqa: F401
        return "openai-whisper"
    except Exception:
        pass
    if _whisper_cpp_bin() and _whisper_cpp_model(os.getenv("WHISPER_MODEL", "tiny")):
        return "whisper.cpp"
    return "energy-fallback"
