"""Regression coverage for preparation races, cancellation and retention safety."""
import json
import sys
import threading
import time

import pytest

from execution import run_process
from jobs import JobConflict, JobStore, QueueFull, write_json
from test_jobs import wait


def test_inputs_are_ready_before_enqueue(tmp_path):
    store = JobStore(tmp_path)
    called = threading.Event()
    def handler(job, work, progress):
        assert json.loads((work / "params.json").read_text())["value"] == 42
        assert (work / "source.mp4").read_bytes() == b"complete"
        called.set()
        return {}
    store.register_handler("analyze", handler)
    store.start()
    try:
        job = store.create("analyze", {"value": 42}, enqueue=False)
        assert job["status"] == "preparing"
        assert not called.wait(0.1)
        (tmp_path / job["id"] / "source.mp4").write_bytes(b"complete")
        store.enqueue(job["id"])
        assert wait(store, job["id"])["status"] == "completed"
    finally:
        store.shutdown()


def test_cancel_interrupts_subprocess_and_can_retry(tmp_path):
    store = JobStore(tmp_path)
    started = threading.Event()
    def handler(job, work, progress):
        started.set()
        run_process([sys.executable, "-c", "import time; time.sleep(30)"], timeout=60)
        return {}
    store.register_handler("render", handler)
    try:
        job = store.create("render", {})
        assert started.wait(2)
        assert store.cancel(job["id"])["status"] == "cancelling"
        assert wait(store, job["id"], timeout=4)["status"] == "cancelled"
        assert store.get(job["id"])["attempts"] == 1
        store.register_handler("render", lambda *args: {"retried": True})
        store.retry(job["id"])
        assert wait(store, job["id"])["result"] == {"retried": True}
    finally:
        store.shutdown()


def test_queued_cancel_and_retry_are_idempotent(tmp_path):
    store = JobStore(tmp_path, concurrency=1)
    started, release = threading.Event(), threading.Event()
    calls = []
    def handler(job, work, progress):
        calls.append(job["id"])
        started.set()
        assert release.wait(3)
        return {}
    store.register_handler("task", handler)
    try:
        first = store.create("task", {})
        assert started.wait(2)
        second = store.create("task", {})
        for _ in range(10):
            assert store.retry(second["id"])["status"] == "queued"
        assert store.cancel(second["id"])["status"] == "cancelled"
        assert store.cancel(second["id"])["status"] == "cancelled"
        with pytest.raises(JobConflict):
            store.delete(first["id"])
        release.set()
        wait(store, first["id"])
        assert second["id"] not in calls
        store.retry(second["id"])
        assert wait(store, second["id"])["status"] == "completed"
        assert calls.count(second["id"]) == 1
        with pytest.raises(JobConflict):
            store.retry(second["id"])
    finally:
        release.set()
        store.shutdown()


def test_restart_recovers_running_jobs_but_not_incomplete_uploads(tmp_path):
    first = JobStore(tmp_path)
    first.register_handler("task", lambda *args: {})
    ready = first.create("task", {}, enqueue=False)
    first.update(ready["id"], status="processing")
    interrupted = first.create("task", {}, enqueue=False)
    first.shutdown()
    second = JobStore(tmp_path)
    second.register_handler("task", lambda *args: {"resumed": True})
    try:
        second.start()
        second.start()  # Idempotent startup must not duplicate a queued job.
        assert wait(second, ready["id"])["result"] == {"resumed": True}
        assert second.get(interrupted["id"])["status"] == "failed"
        assert "interrupted" in second.get(interrupted["id"])["error"]
    finally:
        second.shutdown()


def test_cleanup_protects_active_jobs_and_project_stock_directories(tmp_path):
    store = JobStore(tmp_path, ttl_hours=0, max_total_gb=1)
    started, release = threading.Event(), threading.Event()
    def handler(job, work, progress):
        started.set()
        release.wait(3)
        return {}
    store.register_handler("task", handler)
    try:
        job = store.create("task", {})
        assert started.wait(2)
        (tmp_path / "projects" / "local").mkdir(parents=True)
        (tmp_path / "projects" / "local" / "project.json").write_text("saved")
        (tmp_path / "stock").mkdir()
        (tmp_path / "stock" / "soft.wav").write_bytes(b"music")
        store.max_total_bytes = 1
        result = store.cleanup()
        assert result["over_limit"] is True
        assert job["id"] not in result["removed"]
        assert (tmp_path / "projects" / "local" / "project.json").is_file()
        assert (tmp_path / "stock" / "soft.wav").is_file()
        assert store.get(job["id"])["status"] == "processing"
    finally:
        release.set()
        store.shutdown()


def test_queue_capacity_is_bounded(tmp_path):
    store = JobStore(tmp_path, max_pending=1)
    store.register_handler("task", lambda *args: {})
    try:
        store.create("task", {}, enqueue=False)
        with pytest.raises(QueueFull):
            store.create("task", {})
    finally:
        store.shutdown()


def test_concurrent_retries_do_not_lose_queue_entries(tmp_path):
    store = JobStore(tmp_path, concurrency=2, max_attempts=3)
    def fail(job, work, progress):
        raise ValueError("transient")
    store.register_handler("task", fail)
    try:
        jobs = [store.create("task", {}) for _ in range(8)]
        for job in jobs:
            assert wait(store, job["id"])["attempts"] == 3
        assert len(store._workers) == 2
        assert len({id(worker) for worker in store._workers}) == 2
    finally:
        store.shutdown()


def test_atomic_json_rejects_nan_and_does_not_leave_temporary_files(tmp_path):
    path = tmp_path / "result.json"
    with pytest.raises(ValueError):
        write_json(path, {"score": float("nan")})
    assert not path.exists()
    assert list(tmp_path.iterdir()) == []


def test_cancelled_audio_extraction_does_not_publish_partial_cache(tmp_path, monkeypatch):
    import media
    from execution import JobCancelled
    monkeypatch.setattr(media, "probe", lambda path: {"duration": 6, "has_audio": True})
    def cancelled(*args, **kwargs):
        __import__("pathlib").Path(args[-1]).write_bytes(b"partial WAV")
        raise JobCancelled()
    monkeypatch.setattr(media, "run_ffmpeg", cancelled)
    with pytest.raises(JobCancelled):
        media.extract_audio(tmp_path / "source.mp4", tmp_path / "audio.wav")
    assert not (tmp_path / "audio.wav").exists()
    assert not list(tmp_path.glob(".audio-*.wav"))


def test_interrupted_youtube_download_is_not_reused_as_source(tmp_path, monkeypatch):
    import media
    import subprocess
    from execution import JobCancelled
    monkeypatch.setenv("CLIPFORGE_ALLOW_YTDLP", "true")
    monkeypatch.setattr(media, "have_tool", lambda name: True)
    def download(args, **kwargs):
        if "--dump-single-json" in args:
            return subprocess.CompletedProcess(args, 0, '{"duration": 6}', '')
        output = __import__("pathlib").Path(args[args.index("-o") + 1]).parent / "source.mp4"
        output.write_bytes(b"unfinished merge")
        raise JobCancelled()
    monkeypatch.setattr(media, "run_process", download)
    with pytest.raises(JobCancelled):
        media.download_youtube("https://youtu.be/authorized", tmp_path)
    assert not list(tmp_path.glob("source.*"))


def test_corrupt_metadata_is_skipped_without_crashing_job_listing(tmp_path):
    store = JobStore(tmp_path)
    store.register_handler("task", lambda *args: {})
    try:
        job = store.create("task", {}, enqueue=False)
        path = tmp_path / job["id"] / "job.json"
        document = json.loads(path.read_text())
        document["created_at"] = "corrupted"
        path.write_text(json.dumps(document))
        assert store.get(job["id"]) is None
        assert store.list() == []
        assert store.cleanup()["removed"] == []
    finally:
        store.shutdown()


def test_queue_survives_an_unexpected_storage_error(tmp_path, monkeypatch):
    store = JobStore(tmp_path)
    store.register_handler("task", lambda *args: {"survived": True})
    process = store._process
    failed = threading.Event()
    def fail_once(job_id):
        if not failed.is_set():
            store._active[job_id] = threading.Event()
            failed.set()
            raise OSError("simulated storage error before handler startup")
        return process(job_id)
    monkeypatch.setattr(store, "_process", fail_once)
    try:
        first = store.create("task", {})
        assert wait(store, first["id"])["status"] == "failed"
        assert first["id"] not in store._active
        second = store.create("task", {})
        assert wait(store, second["id"])["result"] == {"survived": True}
    finally:
        store.shutdown()
