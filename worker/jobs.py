"""Atomic, disk-backed jobs with preparation, cancellation and safe cleanup."""
from __future__ import annotations

import json
import logging
import math
import re
import shutil
import threading
import time
import uuid
from pathlib import Path
from queue import Empty, Queue

from execution import JobCancelled, cancellation_scope, check_cancelled

STATUSES = ("preparing", "queued", "processing", "cancelling", "completed", "failed", "cancelled")
ACTIVE_STATUSES = {"preparing", "queued", "processing", "cancelling"}
TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class JobConflict(ValueError):
    pass


class QueueFull(RuntimeError):
    pass


class StorageFull(RuntimeError):
    pass


def write_json(path: Path, data) -> None:
    """Never expose partially written metadata or non-standard NaN JSON."""
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(data, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


class JobStore:
    def __init__(self, root: Path, concurrency: int = 1, max_attempts: int = 3,
                 ttl_hours: float = 24.0, max_total_gb: float = 50.0,
                 max_pending: int = 100):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.max_attempts = max(1, int(max_attempts))
        self.ttl_seconds = max(0, float(ttl_hours)) * 3600
        self.max_total_bytes = max(0, float(max_total_gb)) * 1024 ** 3
        self.max_pending = max(1, int(max_pending))
        self._handlers: dict[str, object] = {}
        self._lock = threading.RLock()
        self._queue: Queue[str] = Queue()
        self._scheduled: set[str] = set()
        self._active: dict[str, threading.Event] = {}
        self._workers: list[threading.Thread] = []
        self._concurrency = max(1, int(concurrency))
        self._stop = threading.Event()
        self._started = False

    def _dir(self, job_id: str) -> Path:
        if not _SAFE_ID.fullmatch(job_id):
            raise ValueError("Invalid job id.")
        path = self.root / job_id
        if path.is_symlink():
            raise ValueError("Invalid job path.")
        return path

    def _meta_path(self, job_id: str) -> Path:
        return self._dir(job_id) / "job.json"

    def register_handler(self, kind: str, fn) -> None:
        self._handlers[kind] = fn

    def create(self, kind: str, params: dict, client: str = "", *, enqueue: bool = True) -> dict:
        with self._lock:
            if kind not in self._handlers:
                raise KeyError(f"Unknown job kind: {kind}")
            if self._stop.is_set():
                raise JobConflict("Worker is shutting down. Try again shortly.")
            if sum(j["status"] in ACTIVE_STATUSES for j in self.list(None)) >= self.max_pending:
                raise QueueFull("Worker queue is full. Wait for a job to finish.")
            if self.total_size() >= self.max_total_bytes:
                raise StorageFull("Worker storage is full. Delete old jobs or increase the storage limit.")
            job_id = uuid.uuid4().hex[:16]
            work = self._dir(job_id)
            work.mkdir()
            now = time.time()
            job = {
                "id": job_id, "kind": kind, "status": "preparing", "progress": 0,
                "stage": "Preparing inputs", "attempts": 0, "max_attempts": self.max_attempts,
                "created_at": now, "updated_at": now, "started_at": None, "finished_at": None,
                "client": client, "params": dict(params), "result": None, "error": None,
            }
            try:
                write_json(work / "params.json", params)
                self._write(job)
                if enqueue:
                    return self.enqueue(job_id)
                return job
            except BaseException:
                shutil.rmtree(work, ignore_errors=True)
                raise

    def enqueue(self, job_id: str) -> dict:
        """Only publish a job after every input has been prepared successfully."""
        with self._lock:
            job = self.get(job_id)
            if not job:
                raise JobConflict("Job no longer exists.")
            if job["status"] != "preparing":
                if job["status"] == "queued":
                    return job
                raise JobConflict("Job cannot be queued in its current state.")
            job = self.update(job_id, status="queued", stage="Waiting for worker")
            self._schedule(job_id)
            self._ensure_workers()
            return job

    def discard_prepared(self, job_id: str) -> None:
        with self._lock:
            job = self.get(job_id)
            if job and job["status"] == "preparing":
                shutil.rmtree(self._dir(job_id), ignore_errors=True)

    def _schedule(self, job_id: str) -> None:
        if job_id not in self._scheduled:
            self._scheduled.add(job_id)
            self._queue.put(job_id)

    def _write(self, job: dict) -> None:
        job["updated_at"] = time.time()
        write_json(self._meta_path(job["id"]), job)

    def get(self, job_id: str) -> dict | None:
        try:
            path = self._meta_path(job_id)
            if path.is_symlink():
                return None
            job = json.loads(path.read_text(encoding="utf-8"))
            if (not isinstance(job, dict) or job.get("id") != job_id
                    or job.get("status") not in STATUSES or not isinstance(job.get("params"), dict)
                    or not isinstance(job.get("kind"), str)):
                return None
            for key in ("created_at", "updated_at", "progress", "attempts", "max_attempts"):
                value = job.get(key)
                if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                    return None
            return job
        except (OSError, ValueError, TypeError):
            return None

    def update(self, job_id: str, **fields) -> dict | None:
        with self._lock:
            job = self.get(job_id)
            if not job:
                return None
            job.update(fields)
            self._write(job)
            return job

    def set_progress(self, job_id: str, pct: float, stage: str | None = None) -> None:
        check_cancelled()
        with self._lock:
            job = self.get(job_id)
            if not job or job["status"] != "processing":
                return
            fields = {"progress": max(0, min(99, round(float(pct))))}
            if stage:
                fields["stage"] = stage[:160]
            self.update(job_id, **fields)

    def list(self, limit: int | None = 50) -> list[dict]:
        with self._lock:
            jobs = []
            for meta in self.root.glob("*/job.json"):
                job = self.get(meta.parent.name)
                if job:
                    jobs.append(job)
            jobs.sort(key=lambda j: float(j.get("created_at", 0)), reverse=True)
            return jobs if limit is None else jobs[:max(0, limit)]

    def _ensure_workers(self) -> None:
        with self._lock:
            if self._stop.is_set():
                return
            self._workers = [worker for worker in self._workers if worker.is_alive()]
            while len(self._workers) < self._concurrency:
                worker = threading.Thread(target=self._run_loop, daemon=True, name="clipforge-worker")
                self._workers.append(worker)
                worker.start()

    def _run_loop(self) -> None:
        while not self._stop.is_set():
            try:
                job_id = self._queue.get(timeout=0.25)
            except Empty:
                continue
            try:
                with self._lock:
                    self._scheduled.discard(job_id)
                if not self._stop.is_set():
                    self._process(job_id)
            except Exception:
                # A storage/metadata failure must not kill the queue consumer.
                with self._lock:
                    self._active.pop(job_id, None)
                    try:
                        self.update(job_id, status="failed", stage="Worker/storage error",
                                    error="Worker could not complete this job. Check storage and retry.", finished_at=time.time())
                    except Exception:
                        logging.error("Could not persist a job failure; check worker disk space and permissions.")
            finally:
                self._queue.task_done()

    def _notify(self, job: dict | None) -> None:
        if job:
            try:
                from webhook import notify
                notify(job)
            except Exception:
                pass

    def _process(self, job_id: str) -> None:
        with self._lock:
            job = self.get(job_id)
            if not job or job["status"] != "queued" or job_id in self._active:
                return
            handler = self._handlers.get(job["kind"])
            if handler is None:
                self._notify(self.update(job_id, status="failed", stage="Failed",
                                         error=f"No handler for {job['kind']}", finished_at=time.time()))
                return
            event = threading.Event()
            self._active[job_id] = event
            attempts = int(job.get("attempts", 0)) + 1
            self.update(job_id, status="processing", attempts=attempts, progress=1,
                        stage="Starting", started_at=time.time(), finished_at=None)
        retry_pending = False
        try:
            with cancellation_scope(event):
                result = handler(job, self._dir(job_id),
                                 lambda pct, stage=None: self.set_progress(job_id, pct, stage))
                check_cancelled()
            with self._lock:
                current = self.get(job_id)
                if current and current["status"] == "processing":
                    self._notify(self.update(job_id, status="completed", progress=100, stage="Complete",
                                             result=result, error=None, finished_at=time.time()))
                elif current and current["status"] == "cancelling":
                    self._finish_cancel(job_id)
        except JobCancelled:
            with self._lock:
                current = self.get(job_id)
                if current:
                    if self._stop.is_set() and current["status"] != "cancelling":
                        self.update(job_id, status="queued", stage="Interrupted; resumes after restart", progress=0)
                    else:
                        self._finish_cancel(job_id)
        except Exception as error:
            with self._lock:
                current = self.get(job_id)
                if not current:
                    return
                if event.is_set() or current["status"] == "cancelling":
                    if self._stop.is_set() and current["status"] != "cancelling":
                        self.update(job_id, status="queued", stage="Interrupted; resumes after restart", progress=0)
                    else:
                        self._finish_cancel(job_id)
                elif attempts < self.max_attempts and not isinstance(error, (PermissionError, FileNotFoundError)):
                    self.update(job_id, status="queued", stage=f"Retrying ({attempts}/{self.max_attempts})",
                                error=str(error)[:2000], progress=0)
                    retry_pending = True
                else:
                    self._notify(self.update(job_id, status="failed", stage="Failed",
                                             error=str(error)[:2000], finished_at=time.time()))
        finally:
            with self._lock:
                self._active.pop(job_id, None)
                if retry_pending and not self._stop.is_set():
                    self._schedule(job_id)

    def _finish_cancel(self, job_id: str) -> dict | None:
        job = self.update(job_id, status="cancelled", stage="Cancelled", error=None, finished_at=time.time())
        self._notify(job)
        return job

    def cancel(self, job_id: str) -> dict | None:
        with self._lock:
            job = self.get(job_id)
            if not job:
                return None
            if job["status"] in ("cancelled", "cancelling"):
                return job
            if job["status"] == "queued":
                return self._finish_cancel(job_id)
            if job["status"] == "processing":
                event = self._active.get(job_id)
                if event is None:
                    return self._finish_cancel(job_id)
                event.set()
                return self.update(job_id, status="cancelling", stage="Stopping safely")
            raise JobConflict("Only queued or processing jobs can be cancelled.")

    def retry(self, job_id: str) -> dict | None:
        with self._lock:
            job = self.get(job_id)
            if not job:
                return None
            if job["status"] in ("queued", "processing"):
                return job  # Idempotent: never run the same job twice.
            if job["status"] not in ("failed", "cancelled") or job_id in self._active:
                raise JobConflict("Wait for cancellation to finish, or create a new job for completed work.")
            if sum(j["status"] in ACTIVE_STATUSES for j in self.list(None)) >= self.max_pending:
                raise QueueFull("Worker queue is full. Try again shortly.")
            job = self.update(job_id, status="queued", stage="Waiting for worker", progress=0,
                              error=None, attempts=0, result=None, finished_at=None)
            self._schedule(job_id)
            self._ensure_workers()
            return job

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            self._started = True
            self._stop.clear()
            for job in self.list(None):
                if job["id"] in self._active:
                    continue
                if job["status"] == "preparing":
                    self.update(job["id"], status="failed", stage="Upload interrupted",
                                error="Input preparation was interrupted. Upload the source again.", finished_at=time.time())
                elif job["status"] == "cancelling":
                    self._finish_cancel(job["id"])
                elif job["status"] in ("queued", "processing"):
                    self.update(job["id"], status="queued", progress=0, stage="Resuming after restart")
                    self._schedule(job["id"])
            self._ensure_workers()

    def shutdown(self) -> None:
        self._stop.set()
        with self._lock:
            for event in self._active.values():
                event.set()
            workers = self._workers[:]
        deadline = time.monotonic() + 5
        for worker in workers:
            worker.join(timeout=max(0, deadline - time.monotonic()))
        self._started = False

    @staticmethod
    def _size(path: Path) -> int:
        total = 0
        for entry in path.rglob("*"):
            try:
                if entry.is_file() and not entry.is_symlink():
                    total += entry.stat().st_size
            except OSError:
                continue
        return total

    def dir_size(self, job_id: str) -> int:
        return self._size(self._dir(job_id))

    def total_size(self) -> int:
        return self._size(self.root)

    def delete(self, job_id: str) -> bool:
        with self._lock:
            job = self.get(job_id)
            if not job:
                return False
            if job["status"] in ("preparing", "processing", "cancelling") or job_id in self._active:
                raise JobConflict("Cancel the job and wait for it to stop before deleting it.")
            shutil.rmtree(self._dir(job_id))
            return True

    def cleanup(self) -> dict:
        """Prune only inactive jobs. Never delete projects, stock BGM or active inputs."""
        with self._lock:
            removed, now = [], time.time()
            jobs = self.list(None)
            protected = set(self._active)
            for job in jobs:
                if job["status"] in ACTIVE_STATUSES:
                    protected.add(job["id"])
                    parent = job["params"].get("parent_job")
                    if isinstance(parent, str):
                        protected.add(parent)
            candidates = [j for j in jobs if j["status"] in TERMINAL_STATUSES and j["id"] not in protected]
            for job in candidates:
                # Keep original creation-time TTL semantics, but never prune active jobs.
                if now - float(job.get("created_at", now)) > self.ttl_seconds:
                    if self.delete(job["id"]):
                        removed.append(job["id"])
            remaining = sorted((j for j in candidates if j["id"] not in removed),
                               key=lambda j: float(j.get("updated_at", 0)))
            total = self.total_size()
            for job in remaining:
                if total <= self.max_total_bytes:
                    break
                if self.delete(job["id"]):
                    removed.append(job["id"])
                    total = self.total_size()
            return {"removed": removed, "total_bytes": total,
                    "over_limit": total > self.max_total_bytes, "protected_jobs": len(protected)}
