"""Persistent job system: queued / processing / completed / failed."""
from __future__ import annotations

import json
import shutil
import threading
import time
import uuid
from pathlib import Path
from queue import Queue, Empty

STATUSES = ("queued", "processing", "completed", "failed")


class JobStore:
    def __init__(self, root: Path, concurrency: int = 1, max_attempts: int = 3,
                 ttl_hours: float = 24.0, max_total_gb: float = 50.0):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.max_attempts = max(1, int(max_attempts))
        self.ttl_seconds = float(ttl_hours) * 3600
        self.max_total_bytes = float(max_total_gb) * 1024 ** 3
        self._handlers: dict[str, object] = {}
        self._lock = threading.RLock()
        self._queue: Queue[str] = Queue()
        self._workers: list[threading.Thread] = []
        self._concurrency = max(1, int(concurrency))
        self._stop = threading.Event()

    def _dir(self, job_id: str) -> Path:
        return self.root / job_id

    def _meta_path(self, job_id: str) -> Path:
        return self._dir(job_id) / "job.json"

    def register_handler(self, kind: str, fn) -> None:
        self._handlers[kind] = fn

    def create(self, kind: str, params: dict, client: str = "") -> dict:
        if kind not in self._handlers:
            raise KeyError(f"Unknown job kind: {kind}")
        job_id = uuid.uuid4().hex[:16]
        d = self._dir(job_id)
        d.mkdir(parents=True, exist_ok=True)
        job = {
            "id": job_id, "kind": kind, "status": "queued", "progress": 0,
            "attempts": 0, "max_attempts": self.max_attempts,
            "created_at": time.time(), "updated_at": time.time(),
            "client": client, "params": params, "result": None, "error": None,
        }
        self._write(job)
        self._queue.put(job_id)
        self._ensure_workers()
        return job

    def _write(self, job: dict) -> None:
        job["updated_at"] = time.time()
        self._meta_path(job["id"]).write_text(json.dumps(job), encoding="utf-8")

    def get(self, job_id: str) -> dict | None:
        p = self._meta_path(job_id)
        if not p.is_file():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

    def update(self, job_id: str, **fields) -> dict | None:
        with self._lock:
            job = self.get(job_id)
            if not job:
                return None
            job.update(fields)
            self._write(job)
            return job

    def set_progress(self, job_id: str, pct: float) -> None:
        self.update(job_id, progress=max(0, min(100, round(float(pct)))))

    def list(self, limit: int = 50) -> list[dict]:
        jobs = []
        for meta in sorted(self.root.glob("*/job.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                jobs.append(json.loads(meta.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                continue
            if len(jobs) >= limit:
                break
        return jobs

    def _ensure_workers(self) -> None:
        with self._lock:
            alive = [w for w in self._workers if w.is_alive()]
            self._workers = alive
            while len(alive) < self._concurrency:
                t = threading.Thread(target=self._run_loop, daemon=True, name="clipforge-worker")
                t.start()
                alive.append(t)
                self._workers.append(t)

    def _run_loop(self) -> None:
        while not self._stop.is_set():
            try:
                job_id = self._queue.get(timeout=1.0)
            except Empty:
                continue
            try:
                self._process(job_id)
            except Exception as e:
                self.update(job_id, status="failed", error=f"worker crash: {e}", progress=0)
            finally:
                self._queue.task_done()

    def _notify(self, job: dict | None) -> None:
        if not job:
            return
        try:
            from webhook import notify
            notify(job)
        except Exception:
            pass

    def _process(self, job_id: str) -> None:
        with self._lock:
            job = self.get(job_id)
            if not job or job["status"] != "queued":
                return
            attempts = int(job.get("attempts", 0)) + 1
            handler = self._handlers.get(job["kind"])
            if handler is None:
                self.update(job_id, status="failed", error=f"No handler for {job['kind']}")
                return
            self.update(job_id, status="processing", attempts=attempts, progress=1)
        try:
            result = handler(job, self._dir(job_id), lambda pct: self.set_progress(job_id, pct))
        except Exception as e:
            with self._lock:
                cur = self.get(job_id)
                if cur is None or cur.get("status") != "processing":
                    return
                if attempts < self.max_attempts:
                    self.update(job_id, status="queued", attempts=attempts,
                                error=f"attempt {attempts} failed: {e}", progress=0)
                    self._queue.put(job_id)
                else:
                    failed = self.update(job_id, status="failed", error=str(e)[:2000])
                    self._notify(failed)
            return
        with self._lock:
            cur = self.get(job_id)
            if cur is None or cur.get("status") != "processing":
                return
            done = self.update(job_id, status="completed", progress=100, result=result, error=None)
            self._notify(done)

    def retry(self, job_id: str) -> dict | None:
        with self._lock:
            job = self.get(job_id)
            if not job:
                return None
            if job["status"] == "processing":
                return job
            self.update(job_id, status="queued", progress=0, error=None, attempts=0)
            self._queue.put(job_id)
            self._ensure_workers()
            return self.get(job_id)

    def start(self) -> None:
        try:
            from addon import mount
            mount()
        except Exception:
            pass
        for meta in self.root.glob("*/job.json"):
            try:
                job = json.loads(meta.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if job.get("status") in ("queued", "processing"):
                self.update(job["id"], status="queued", progress=0)
                self._queue.put(job["id"])
        self._ensure_workers()

    def shutdown(self) -> None:
        self._stop.set()

    def dir_size(self, job_id: str) -> int:
        d = self._dir(job_id)
        return sum(f.stat().st_size for f in d.rglob("*") if f.is_file()) if d.is_dir() else 0

    def total_size(self) -> int:
        return sum(f.stat().st_size for f in self.root.rglob("*") if f.is_file())

    def delete(self, job_id: str) -> bool:
        d = self._dir(job_id)
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)
            return True
        return False

    def cleanup(self) -> dict:
        removed, now = [], time.time()
        for meta in self.root.glob("*/job.json"):
            try:
                job = json.loads(meta.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                shutil.rmtree(meta.parent, ignore_errors=True)
                continue
            age = now - float(job.get("created_at", 0))
            abandoned = job.get("status") == "failed" and age > 3600
            if age > self.ttl_seconds or abandoned:
                shutil.rmtree(meta.parent, ignore_errors=True)
                removed.append(job.get("id", meta.parent.name))
        while self.total_size() > self.max_total_bytes:
            dirs = sorted((d for d in self.root.iterdir() if d.is_dir()),
                          key=lambda d: d.stat().st_mtime)
            if not dirs:
                break
            shutil.rmtree(dirs[0], ignore_errors=True)
            removed.append(dirs[0].name)
        return {"removed": removed, "total_bytes": self.total_size()}
