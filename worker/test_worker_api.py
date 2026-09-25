"""Worker API tests: auth, validation, rate limiting, job endpoints."""
import json
import time

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPFORGE_DATA", str(tmp_path / "data"))
    monkeypatch.setenv("WORKER_API_TOKEN", "secret-token")
    monkeypatch.setenv("CLIPFORGE_RATE_LIMIT", "100")
    import config
    fresh_settings = config.Settings()
    monkeypatch.setattr(config, "settings", fresh_settings)
    import main as worker_main
    monkeypatch.setattr(worker_main, "settings", fresh_settings)
    fresh = worker_main.JobStore(fresh_settings.data_dir, concurrency=1, max_attempts=2)
    fresh.register_handler("analyze", worker_main.pipeline.handle_analyze)
    fresh.register_handler("render", worker_main.pipeline.handle_render)
    monkeypatch.setattr(worker_main, "store", fresh)
    with TestClient(worker_main.app) as c:
        c.headers.update({"Authorization": "Bearer secret-token"})
        yield c
    fresh.shutdown()


def _wait_status(client, job_id, wanted=("completed", "failed"), timeout=15.0):
    """Poll the public status endpoint until the job settles."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/jobs/{job_id}").json()
        if body["status"] in wanted:
            return body
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} did not settle ({wanted}) within {timeout}s")


def test_health_is_public(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] and body["service"] == "clipforge-worker"
    assert "ffmpeg" in body and "whisper_engine" in body


def test_auth_required(client):
    c = TestClient(client.app)
    assert c.get("/jobs/deadbeef").status_code == 401
    assert c.post("/jobs/youtube", json={"url": "https://youtu.be/x"}).status_code == 401


def test_youtube_job_validation(client):
    assert client.post("/jobs/youtube", json={"url": "http://evil.example.com/v"}).status_code == 400
    r = client.post("/jobs/youtube", json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"})
    assert r.status_code == 200
    job_id = r.json()["job_id"]
    s = client.get(f"/jobs/{job_id}").json()
    assert s["status"] in ("queued", "processing", "failed")  # yt-dlp disabled -> fails clearly


def test_upload_rejects_bad_extension(client):
    r = client.post("/jobs/upload", files={"video": ("malware.exe", b"MZ..", "application/x-msdownload")})
    assert r.status_code == 400


def test_upload_queues_job_and_status(client):
    r = client.post("/jobs/upload",
                    files={"video": ("clip.mp4", b"\x00\x00\x00\x18ftypmp42fake", "video/mp4")},
                    data={"min_seconds": "15", "max_seconds": "60"})
    assert r.status_code == 200
    job_id = r.json()["job_id"]
    s = client.get(f"/jobs/{job_id}")
    assert s.status_code == 200
    body = s.json()
    assert body["progress"] >= 0 and body["max_attempts"] == 2


def test_path_traversal_blocked(client):
    assert client.get("/jobs/../config/files/../../etc/passwd").status_code in (400, 404)
    assert client.get("/jobs/ok/files/..%2f..%2fetc%2fpasswd").status_code in (400, 404)


def test_rate_limit(client, monkeypatch):
    import main as worker_main
    for i in range(101):
        r = client.post("/jobs/youtube", json={"url": "https://youtu.be/aaa"})
        if r.status_code == 429:
            break
    assert r.status_code == 429


def test_retry_endpoint(client):
    r = client.post("/jobs/youtube", json={"url": "https://youtu.be/zzz"})
    job_id = r.json()["job_id"]
    rr = client.post(f"/jobs/{job_id}/retry")
    assert rr.status_code == 200
    assert rr.json()["status"] in ("queued", "processing")


def test_delete_and_cleanup(client):
    r = client.post("/jobs/youtube", json={"url": "https://youtu.be/del1"})
    job_id = r.json()["job_id"]
    assert client.delete(f"/jobs/{job_id}").status_code == 200
    assert client.get(f"/jobs/{job_id}").status_code == 404
    assert client.post("/jobs/cleanup").status_code == 200


def test_score_endpoint_stateless(client):
    payload = {"segments": [{"start": 0, "end": 20, "text": "Here's why this matters!"}],
               "min_seconds": 15, "max_seconds": 60, "limit": 3}
    r = client.post("/score", json=payload)
    assert r.status_code == 200
    clips = r.json()["clips"]
    assert clips and clips[0]["score"] > 0
