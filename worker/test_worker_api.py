"""Worker API tests: auth, validation, rate limiting, job endpoints."""
import time

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPFORGE_DATA", str(tmp_path / "data"))
    monkeypatch.setenv("WORKER_API_TOKEN", "secret-token")
    monkeypatch.setenv("CLIPFORGE_RATE_LIMIT", "100")
    # Rebuild settings + store against the temp data dir so tests never
    # touch the default /tmp/clipforge path or share rate-limit state.
    import config

    fresh_settings = config.Settings()
    monkeypatch.setattr(config, "settings", fresh_settings)

    import main as worker_main
    from jobs import JobStore

    monkeypatch.setattr(worker_main, "settings", fresh_settings)
    fresh = JobStore(
        fresh_settings.data_dir,
        concurrency=1,
        max_attempts=2,
        ttl_hours=1.0,
        max_total_gb=1.0,
    )
    fresh.register_handler("analyze", worker_main.pipeline.handle_analyze)
    fresh.register_handler("render", worker_main.pipeline.handle_render)
    monkeypatch.setattr(worker_main, "store", fresh)

    # Fresh app so RateLimit middleware state is isolated
    app = worker_main.create_app()
    with TestClient(app) as c:
        c.headers.update({"Authorization": "Bearer secret-token"})
        yield c
    fresh.shutdown()


def test_health_is_public(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] and body["service"] == "clipforge-worker"
    assert "ffmpeg" in body and "whisper_engine" in body
    assert "version" in body


def test_auth_required(client):
    c = TestClient(client.app)
    assert c.get("/jobs/deadbeef").status_code == 401
    assert c.post("/jobs/youtube", json={"url": "https://youtu.be/x"}).status_code == 401


def test_youtube_job_validation(client):
    assert (
        client.post("/jobs/youtube", json={"url": "http://evil.example.com/v"}).status_code
        == 400
    )
    r = client.post(
        "/jobs/youtube",
        json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
    )
    assert r.status_code == 200
    job_id = r.json()["job_id"]
    s = client.get(f"/jobs/{job_id}").json()
    # yt-dlp disabled in CI -> may fail or stay queued/processing briefly
    assert s["status"] in ("queued", "processing", "failed")


def test_upload_rejects_bad_extension(client):
    r = client.post(
        "/jobs/upload",
        files={"video": ("malware.exe", b"MZ..", "application/x-msdownload")},
    )
    assert r.status_code == 400


def test_upload_queues_job_and_status(client):
    r = client.post(
        "/jobs/upload",
        files={"video": ("clip.mp4", b"\x00\x00\x00\x18ftypmp42fake", "video/mp4")},
        data={"min_seconds": "15", "max_seconds": "60"},
    )
    assert r.status_code == 200
    job_id = r.json()["job_id"]
    s = client.get(f"/jobs/{job_id}")
    assert s.status_code == 200
    body = s.json()
    assert body["progress"] >= 0 and body["max_attempts"] == 2


def test_path_traversal_blocked(client):
    assert client.get("/jobs/../config/files/../../etc/passwd").status_code in (400, 404)
    assert client.get("/jobs/ok/files/..%2f..%2fetc%2fpasswd").status_code in (400, 404)


def test_rate_limit(client):
    last = None
    for _ in range(120):
        last = client.post("/jobs/youtube", json={"url": "https://youtu.be/aaa"})
        if last.status_code == 429:
            break
    assert last is not None and last.status_code == 429


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
    payload = {
        "segments": [{"start": 0, "end": 20, "text": "Here's why this matters!"}],
        "min_seconds": 15,
        "max_seconds": 60,
        "limit": 3,
    }
    r = client.post("/score", json=payload)
    assert r.status_code == 200
    clips = r.json()["clips"]
    assert clips and clips[0]["score"] > 0
    # v0.6 fields
    assert "title" in clips[0] and "reason" in clips[0]


def test_caption_style_bold_accepted_in_render_validation(client):
    """Render without a real parent should 404, but style validation must allow bold."""
    r = client.post(
        "/jobs/render",
        json={
            "parent_job": "nonexistent0001",
            "highlights": [{"start": 0, "end": 20}],
            "durations": [30],
            "caption_style": "bold",
            "aspect": "9:16",
        },
    )
    # parent missing -> 404 (not 400 from style rejection)
    assert r.status_code == 404
