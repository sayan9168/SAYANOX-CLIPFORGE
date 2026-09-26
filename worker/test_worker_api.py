"""Worker API tests: auth, validation, rate limiting, job endpoints."""

import time

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Isolated worker app bound to a temp data dir + auth token."""
    monkeypatch.setenv("CLIPFORGE_DATA", str(tmp_path / "data"))
    monkeypatch.setenv("WORKER_API_TOKEN", "secret-token")
    monkeypatch.setenv("CLIPFORGE_RATE_LIMIT", "100")

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

    root = worker_main.app
    seen = set()
    while getattr(root, "app", None) is not None and id(root) not in seen:
        seen.add(id(root))
        root = root.app
    if hasattr(root, "_clipforge_rate_hits"):
        root._clipforge_rate_hits.clear()

    with TestClient(worker_main.app) as c:
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
    bare = TestClient(client.app)
    assert bare.get("/jobs/deadbeef").status_code == 401
    assert bare.post("/jobs/youtube", json={"url": "https://youtu.be/x"}).status_code == 401


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
    status = None
    for _ in range(20):
        s = client.get(f"/jobs/{job_id}")
        if s.status_code == 200 and "status" in s.json():
            status = s.json()["status"]
            break
        time.sleep(0.05)
    assert status in ("queued", "processing", "failed", "completed"), status


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
    body = None
    for _ in range(40):
        s = client.get(f"/jobs/{job_id}")
        if s.status_code == 200 and "status" in s.json():
            body = s.json()
            break
        time.sleep(0.05)
    assert body is not None, "job status never became readable"
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
    gone = False
    for _ in range(20):
        if client.get(f"/jobs/{job_id}").status_code == 404:
            gone = True
            break
        time.sleep(0.05)
    assert gone, "deleted job still visible"
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
    assert "title" in clips[0] and "reason" in clips[0]


def test_caption_style_bold_accepted_in_render_validation(client):
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
    assert r.status_code == 404


def test_zip_download_bundle(client, tmp_path):
    import io
    import json
    import zipfile

    import main as worker_main

    job = worker_main.store.create("render", {"durations": [30]})
    job_id = job["id"]
    work = worker_main.media.safe_job_dir(worker_main._data_root(), job_id)
    clips = work / "clips"
    clips.mkdir(parents=True, exist_ok=True)
    (clips / "clip-01-vertical.mp4").write_bytes(b"fake-mp4-one")
    (clips / "clip-02-vertical.mp4").write_bytes(b"fake-mp4-two")
    meta_path = work / "job.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["status"] = "completed"
    meta["updated_at"] = time.time()
    meta_path.write_text(json.dumps(meta), encoding="utf-8")

    z = client.get(f"/jobs/{job_id}/zip")
    assert z.status_code == 200
    assert z.headers["content-type"] == "application/zip"
    assert "attachment" in z.headers.get("content-disposition", "")
    archive = zipfile.ZipFile(io.BytesIO(z.content))
    names = sorted(archive.namelist())
    assert names == ["clip-01-vertical.mp4", "clip-02-vertical.mp4"]
    assert archive.read("clip-01-vertical.mp4") == b"fake-mp4-one"


def test_zip_missing_for_job_without_clips(client):
    r = client.post("/jobs/youtube", json={"url": "https://youtu.be/nozip"})
    job_id = r.json()["job_id"]
    assert client.get(f"/jobs/{job_id}/zip").status_code == 404
    assert client.get("/jobs/bad..id/zip").status_code in (400, 404)


def test_render_accepts_custom_durations(client):
    """Custom target lengths pass validation; invalid durations 400 before parent 404."""
    ok = client.post(
        "/jobs/render",
        json={
            "parent_job": "nonexistent0002",
            "highlights": [{"start": 0, "end": 22}],
            "durations": [22, 45],
        },
    )
    assert ok.status_code == 404
    bad = client.post(
        "/jobs/render",
        json={
            "parent_job": "nonexistent0002",
            "highlights": [{"start": 0, "end": 22}],
            "durations": [3],
        },
    )
    assert bad.status_code == 400
