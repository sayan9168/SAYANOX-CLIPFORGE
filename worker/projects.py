"""Disk-backed projects (cloud = worker volume). Token is the account key."""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path


def _root(data_dir: Path) -> Path:
    p = Path(data_dir) / "projects"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _safe(token: str) -> str:
    raw = "".join(ch for ch in (token or "local") if ch.isalnum() or ch in "-_")[:64]
    return raw or "local"


def list_projects(data_dir: Path, token: str) -> list[dict]:
    folder = _root(data_dir) / _safe(token)
    if not folder.is_dir():
        return []
    items = []
    for f in sorted(folder.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            items.append(json.loads(f.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    return items


def save_project(data_dir: Path, token: str, body: dict) -> dict:
    folder = _root(data_dir) / _safe(token)
    folder.mkdir(parents=True, exist_ok=True)
    pid = str(body.get("id") or uuid.uuid4().hex[:12])
    doc = {
        "id": pid,
        "name": str(body.get("name") or "Untitled")[:80],
        "job_id": body.get("job_id"),
        "url": body.get("url"),
        "notes": body.get("notes") or "",
        "updated_at": time.time(),
    }
    (folder / f"{pid}.json").write_text(json.dumps(doc), encoding="utf-8")
    return doc
