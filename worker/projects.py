"""Atomic project snapshots scoped to a workspace (not a login system)."""
from __future__ import annotations

import json
import re
import threading
import time
import uuid
from pathlib import Path

from jobs import write_json
from schemas import ProjectRequest

_SAFE_KEY = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_LOCK = threading.RLock()


def _safe(value: str) -> str:
    if not _SAFE_KEY.fullmatch(value):
        raise ValueError("Workspace and project IDs must use 1–64 letters, numbers, underscores or hyphens.")
    return value


def _folder(data_dir: Path, workspace: str) -> Path:
    base = Path(data_dir).resolve() / "projects"
    folder = base / _safe(workspace or "local")
    if base.is_symlink() or folder.is_symlink():
        raise ValueError("Linked workspace directories are not allowed.")
    return folder


def get_project(data_dir: Path, workspace: str, project_id: str) -> dict | None:
    path = _folder(data_dir, workspace) / f"{_safe(project_id)}.json"
    if path.is_symlink():
        return None
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        return document if isinstance(document, dict) and document.get("id") == project_id else None
    except (OSError, ValueError):
        return None


def list_projects(data_dir: Path, workspace: str) -> list[dict]:
    with _LOCK:
        folder = _folder(data_dir, workspace)
        if not folder.is_dir():
            return []
        documents = []
        for path in folder.glob("*.json"):
            if _SAFE_KEY.fullmatch(path.stem):
                document = get_project(data_dir, workspace, path.stem)
                if document:
                    documents.append(document)
        return sorted(documents, key=lambda document: float(document.get("updated_at", 0)), reverse=True)


def save_project(data_dir: Path, workspace: str, body: dict) -> dict:
    snapshot = ProjectRequest.model_validate(body)
    if not snapshot.name.strip():
        raise ValueError("Project name cannot be blank.")
    with _LOCK:
        folder = _folder(data_dir, workspace)
        folder.mkdir(parents=True, exist_ok=True)
        project_id = snapshot.id or uuid.uuid4().hex[:12]
        previous = get_project(data_dir, workspace, project_id)
        document = {**snapshot.model_dump(), "id": project_id, "name": snapshot.name.strip(),
                    "created_at": (previous or {}).get("created_at", time.time()), "updated_at": time.time()}
        write_json(folder / f"{project_id}.json", document)
        return document


def delete_project(data_dir: Path, workspace: str, project_id: str) -> bool:
    with _LOCK:
        if get_project(data_dir, workspace, project_id) is None:
            return False
        (_folder(data_dir, workspace) / f"{_safe(project_id)}.json").unlink()
        return True
