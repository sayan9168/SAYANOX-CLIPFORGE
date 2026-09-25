"""Transcription adapters: faster-whisper (preferred), openai-whisper fallback.

Both produce the same normalised shape:
    {"language": str, "segments": [{"start","end","text"}], "engine": str}
"""
from __future__ import annotations

import threading
from pathlib import Path

_LOCK = threading.Lock()
_MODEL = None
_MODEL_NAME = ""


def transcribe(audio_path: Path, model_name: str = "base",
               device: str = "cpu", compute_type: str = "int8") -> dict:
    """Timestamped transcript for a 16 kHz wav. Raises RuntimeError if no
    Whisper backend is installed — callers must surface that clearly."""
    global _MODEL, _MODEL_NAME
    fw_err = ow_err = None
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except Exception as e:  # pragma: no cover - env dependent
        fw_err = e
        WhisperModel = None
    try:
        with _LOCK:
            if WhisperModel is not None:
                if _MODEL is None or _MODEL_NAME != f"fw:{model_name}":
                    _MODEL = WhisperModel(model_name, device=device, compute_type=compute_type)
                    _MODEL_NAME = f"fw:{model_name}"
                raw, info = _MODEL.transcribe(str(audio_path), vad_filter=True)
                segs = [
                    {"start": round(s.start, 3), "end": round(s.end, 3), "text": s.text.strip()}
                    for s in raw
                ]
                return {"language": info.language, "segments": segs, "engine": "faster-whisper"}
            # fall back to openai-whisper
            import whisper  # type: ignore
            if _MODEL is None or _MODEL_NAME != f"ow:{model_name}":
                _MODEL = whisper.load_model(model_name, device="cpu" if device == "cpu" else device)
                _MODEL_NAME = f"ow:{model_name}"
            result = _MODEL.transcribe(str(audio_path))
            segs = [
                {"start": round(float(s["start"]), 3), "end": round(float(s["end"]), 3),
                 "text": s["text"].strip()}
                for s in result.get("segments", [])
            ]
            return {"language": result.get("language", "unknown"), "segments": segs,
                    "engine": "openai-whisper"}
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "No local Whisper backend installed. Add faster-whisper or openai-whisper "
            f"to the worker image ({fw_err}; {ow_err or e})."
        ) from e


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
        return "none"
