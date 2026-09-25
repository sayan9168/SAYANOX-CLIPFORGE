import time
from pathlib import Path

import pytest

from jobs import JobStore


@pytest.fixture()
def store(tmp_path: Path) -> JobStore:
    s = JobStore(tmp_path / "data", concurrency=1, max_attempts=2, ttl_hours=0.001)
    yield s
    s.shutdown()


def wait(store, job_id, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = store.get(job_id)
        if job and job["status"] in ("completed", "failed"):
            return job
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def test_lifecycle_and_progress(store):
    def handler(job, work, progress):
        progress(50)
        return {"ok": True}
    store.register_handler("t", handler)
    job = store.create("t", {})
    done = wait(store, job["id"])
    assert done["status"] == "completed"
    assert done["progress"] == 100
    assert done["result"] == {"ok": True}
    assert (store.root / job["id"] / "job.json").is_file()


def test_retry_then_fail(store):
    calls = {"n": 0}
    def boom(job, work, progress):
        calls["n"] += 1
        raise ValueError("nope")
    store.register_handler("b", boom)
    job = store.create("b", {})
    done = wait(store, job["id"])
    assert done["status"] == "failed"
    assert calls["n"] == 2                      # max_attempts respected
    assert done["attempts"] == 2
    again = store.retry(job["id"])
    assert again["status"] in ("queued", "processing")


def test_cleanup_removes_expired_jobs(store):
    store.register_handler("c", lambda j, w, p: {})
    job = store.create("c", {})
    wait(store, job["id"])
    meta = store.root / job["id"] / "job.json"
    data = __import__("json").loads(meta.read_text())
    data["created_at"] -= 100000
    meta.write_text(__import__("json").dumps(data))
    res = store.cleanup()
    assert job["id"] in res["removed"]
    assert not (store.root / job["id"]).exists()


def test_state_survives_restart(tmp_path):
    root = tmp_path / "data"
    s1 = JobStore(root)
    s1.register_handler("k", lambda j, w, p: {"v": 1})
    job = s1.create("k", {})
    wait(s1, job["id"])
    s1.shutdown()
    s2 = JobStore(root)
    assert s2.get(job["id"])["status"] == "completed"
    s2.shutdown()
