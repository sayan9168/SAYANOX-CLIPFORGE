"""Central configuration for the ClipForge worker (env driven)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(name: str, default):
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    if isinstance(default, bool):
        return raw.lower() in ("1", "true", "yes", "on")
    if isinstance(default, int):
        return int(raw)
    if isinstance(default, float):
        return float(raw)
    return raw


def _default_data_dir() -> Path:
    """Prefer writable locations — Termux often has read-only /tmp."""
    env = os.getenv("CLIPFORGE_DATA")
    candidates: list[Path] = []
    if env:
        candidates.append(Path(env).expanduser())
    home = Path.home()
    candidates.extend(
        [
            home / "clipforge-data",
            home / ".cache" / "clipforge",
            Path("/data/data/com.termux/files/home/clipforge-data"),
            Path("/tmp/clipforge"),
        ]
    )
    for p in candidates:
        try:
            p.mkdir(parents=True, exist_ok=True)
            # Prove we can write (Termux sometimes allows mkdir then fails writes).
            probe = p / ".write_test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return p
        except OSError:
            continue
    # Last resort: cwd-relative (always try to create).
    fallback = Path.cwd() / "clipforge-data"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


@dataclass(frozen=True)
class Settings:
    data_dir: Path = field(default_factory=_default_data_dir)
    api_token: str = field(default_factory=lambda: _env("WORKER_API_TOKEN", ""))
    max_upload_mb: int = field(default_factory=lambda: _env("CLIPFORGE_MAX_UPLOAD_MB", 2048))
    job_ttl_hours: float = field(default_factory=lambda: _env("CLIPFORGE_JOB_TTL_HOURS", 24.0))
    max_total_storage_gb: float = field(default_factory=lambda: _env("CLIPFORGE_MAX_STORAGE_GB", 50.0))
    rate_limit_per_minute: int = field(default_factory=lambda: _env("CLIPFORGE_RATE_LIMIT", 30))
    whisper_model: str = field(default_factory=lambda: _env("WHISPER_MODEL", "tiny"))
    whisper_device: str = field(default_factory=lambda: _env("WHISPER_DEVICE", "cpu"))
    whisper_compute: str = field(default_factory=lambda: _env("WHISPER_COMPUTE_TYPE", "int8"))
    allow_faster_whisper: bool = field(default_factory=lambda: _env("CLIPFORGE_ALLOW_FASTER_WHISPER", True))
    worker_concurrency: int = field(default_factory=lambda: _env("CLIPFORGE_WORKER_CONCURRENCY", 1))
    max_attempts: int = field(default_factory=lambda: _env("CLIPFORGE_MAX_ATTEMPTS", 3))
    clip_durations: tuple = (15, 30, 60, 90)
    padding_seconds: float = field(default_factory=lambda: _env("CLIPFORGE_PADDING_SECONDS", 0.5))
    webhook_url: str = field(default_factory=lambda: _env("CLIPFORGE_WEBHOOK_URL", ""))


settings = Settings()
# data_dir already created inside _default_data_dir()
