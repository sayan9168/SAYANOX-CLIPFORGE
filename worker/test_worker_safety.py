"""API regression tests for validation, namespaces, downloads and preparation."""
import io
import json
import time
import zipfile
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient


def completed_parent(result=None):
    import main
    job = main.store.create("analyze", {}, enqueue=False)
    work = main.store.root / job["id"]
    (work / "source.mov").write_bytes(b"complete-source-bytes")
    main.store.update(job["id"], status="completed", result=result or {"duration": 60, "has_video": True, "clips": [{"start": 0, "end": 20, "score": 80}]})
    return job["id"], work


@pytest.mark.parametrize("options", [
    {"min_seconds": -1}, {"max_seconds": 181}, {"min_seconds": 30, "max_seconds": 20},
    {"limit": 0}, {"limit": 21}, {"min_seconds": "NaN"}, {"max_seconds": "Infinity"},
])
def test_invalid_analysis_controls_rejected_before_job_creation(client, options):
    import main
    response = client.post("/jobs/youtube", json={"url": "https://youtu.be/valid", **options})
    assert response.status_code == 400
    assert not main.store.list()


@pytest.mark.parametrize("url", ["https://youtube.com.evil.test/watch?v=x", "https://user@youtube.com/watch?v=x", "https://youtube.com/playlist?list=x", "https://youtu.be:8080/x"])
def test_youtube_domain_and_video_validation(client, url):
    assert client.post("/jobs/youtube", json={"url": url}).status_code == 400


@pytest.mark.parametrize("payload", [
    {"highlights": [{"start": -1, "end": 10}]}, {"highlights": [{"start": 8, "end": 2}]},
    {"highlights": [{"start": "NaN", "end": 10}]}, {"durations": [22.5]},
    {"durations": "30"}, {"captions": "false"}, {"padding": "Infinity"},
    {"bgm_volume": 2}, {"aspect": "bad"}, {"grade": "true"},
])
def test_invalid_render_options_return_clear_400s(client, payload):
    response = client.post("/jobs/render", json={"parent_job": "missing-parent", **payload})
    assert response.status_code == 400
    assert isinstance(response.json()["detail"], str)


def test_failed_uploads_leave_no_orphan_jobs(client, monkeypatch):
    import config
    import main
    assert client.post("/jobs/upload", files={"video": ("empty.mp4", b"", "video/mp4")}).status_code == 400
    assert main.store.list() == []
    monkeypatch.setattr(config, "settings", replace(config.settings, max_upload_mb=0))
    assert client.post("/jobs/upload", files={"video": ("large.mp4", b"x" * 100, "video/mp4")}).status_code == 413
    assert main.store.list() == []


def test_oversized_upload_rejected_before_parsing(client, monkeypatch):
    import config
    monkeypatch.setattr(config, "settings", replace(config.settings, max_upload_mb=1))
    response = client.post("/jobs/upload", content=b"not parsed", headers={"Content-Length": str(100 * 1024 ** 2), "Content-Type": "multipart/form-data; boundary=x"})
    assert response.status_code == 413


def test_legacy_clip_requires_token_before_multipart_parsing(client):
    bare = TestClient(client.app)
    assert bare.post("/clip", content=b"bad body").status_code == 401
    assert bare.get("/projects").status_code == 401
    assert bare.post("/score", json={}).status_code == 401


def test_render_options_and_inputs_are_persisted_before_execution(client):
    import main
    from test_jobs import wait
    parent, parent_dir = completed_parent()
    (parent_dir / "transcript.json").write_text(json.dumps({"engine": "srt-sidecar", "segments": []}))
    def handler(job, work, progress):
        options = json.loads((work / "params.json").read_text())
        assert (work / "source.mov").read_bytes() == b"complete-source-bytes"
        assert (work / "transcript.json").is_file()
        assert options["grade"] and options["hook_zoom"] and options["parent_job"] == parent
        assert job["params"]["grade"] and job["params"]["hook_zoom"]
        return {"clips": []}
    main.store.register_handler("render", handler)
    response = client.post("/jobs/render", json={"parent_job": parent, "highlights": [{"start": 2, "end": 20}], "grade": True, "hook_zoom": True})
    assert response.status_code == 200
    assert wait(main.store, response.json()["job_id"])["status"] == "completed"


def test_render_requires_completed_video_analysis_and_valid_trims(client):
    import main
    parent, _ = completed_parent()
    assert client.post("/jobs/render", json={"parent_job": parent, "highlights": [{"start": 50, "end": 70}]}).status_code == 400
    main.store.update(parent, status="failed")
    assert client.post("/jobs/render", json={"parent_job": parent}).status_code == 409
    main.store.update(parent, status="completed", result={"duration": 60, "has_video": False})
    assert client.post("/jobs/render", json={"parent_job": parent}).status_code == 400


def test_artifacts_support_ranges_and_hide_private_metadata(client):
    parent, work = completed_parent()
    data = (work / "source.mov").read_bytes()
    response = client.get(f"/jobs/{parent}/files/source.mov", headers={"Range": "bytes=2-5"})
    assert response.status_code == 206 and response.content == data[2:6]
    assert response.headers["content-range"] == f"bytes 2-5/{len(data)}"
    assert response.headers["cache-control"] == "private, no-store"
    assert client.get(f"/jobs/{parent}/files/job.json").status_code == 404
    assert client.get(f"/jobs/{parent}/files/params.json").status_code == 404
    assert client.get(f"/jobs/{parent}/files/source.mov", headers={"Range": "bytes=9999-"}).status_code == 416


def test_prefix_and_symlink_traversal_cannot_escape_job(client):
    parent, work = completed_parent()
    sibling = work.with_name(work.name + "-other")
    sibling.mkdir()
    (sibling / "secret.mp4").write_bytes(b"private")
    (work / "source.mp4").symlink_to(sibling / "secret.mp4")
    assert client.get(f"/jobs/{parent}/files/source.mp4").status_code == 404
    assert client.get(f"/jobs/{parent}/files/..%2f{parent}-other%2fsecret.mp4").status_code == 404


def test_transcript_downloads_export_real_cues_only(client):
    parent, work = completed_parent()
    (work / "transcript.json").write_text(json.dumps({"engine": "srt-sidecar", "segments": [{"start": 0.25, "end": 2, "text": "বাংলা test"}]}))
    for format in ("srt", "vtt", "txt", "json"):
        response = client.get(f"/jobs/{parent}/transcript?format={format}")
        assert response.status_code == 200
        assert "attachment" in response.headers["content-disposition"]
        assert "বাংলা test" in response.text
    assert client.get(f"/jobs/{parent}/transcript?format=exe").status_code == 400
    (work / "transcript.json").write_text(json.dumps({"engine": "energy-fallback", "segments": [{"start": 0, "end": 2, "text": "placeholder"}]}))
    assert client.get(f"/jobs/{parent}/transcript").status_code == 409


def test_zip_includes_sidecars_cover_and_manifest_without_private_inputs(client):
    import main
    job = main.store.create("render", {}, enqueue=False)
    work = main.store.root / job["id"]
    clips = work / "clips"
    clips.mkdir()
    for name in ("clip.mp4", "clip.srt", "clip.vtt", "clip.jpg"):
        (clips / name).write_bytes(b"output")
    (clips / "private.txt").write_text("do not export")
    (work / "render.json").write_text("[]")
    main.store.update(job["id"], status="completed")
    response = client.get(f"/jobs/{job['id']}/zip")
    assert response.status_code == 200
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    assert sorted(archive.namelist()) == ["clip.jpg", "clip.mp4", "clip.srt", "clip.vtt", "render.json"]
    assert (work / "exports.zip").is_file()  # Bundled on disk, not in a multi-GB BytesIO.


def test_project_settings_restore_and_workspaces_are_isolated(client):
    payload = {"name": "My edit", "job_id": "sourcejob", "settings": {"aspect": "1:1", "durations": [22], "grade": True, "hook_zoom": True}, "editor": {"selected": [True], "trims": [{"start": 2, "end": 22}]}, "notes": "Keep this cut"}
    saved = client.post("/projects", json=payload, headers={"x-clipforge-user": "alpha"})
    assert saved.status_code == 200
    project = saved.json()
    project_id = project["id"]
    assert client.get("/projects", headers={"x-clipforge-user": "beta"}).json()["projects"] == []
    loaded = client.get(f"/projects/{project_id}", headers={"x-clipforge-user": "alpha"}).json()
    assert loaded["settings"]["grade"] and loaded["settings"]["hook_zoom"]
    assert loaded["editor"] == payload["editor"]
    assert loaded["notes"] == "Keep this cut"
    assert client.delete(f"/projects/{project_id}", headers={"x-clipforge-user": "beta"}).status_code == 404
    updated = client.post("/projects", json={**payload, "id": project_id, "name": "Updated"}, headers={"x-clipforge-user": "alpha"}).json()
    assert updated["created_at"] == loaded["created_at"]
    assert client.delete(f"/projects/{project_id}", headers={"x-clipforge-user": "alpha"}).status_code == 200
    assert client.get("/projects", headers={"x-clipforge-user": "alpha"}).json()["projects"] == []


@pytest.mark.parametrize("payload", [{"id": "../../escape", "name": "bad"}, {"name": "   "}, {"name": "bad", "editor": {"trims": [{"start": 20, "end": 2}]}}])
def test_invalid_projects_cannot_escape_storage_or_crash(client, payload):
    assert client.post("/projects", json=payload).status_code == 400
    assert client.get("/projects", headers={"x-clipforge-user": "a/b"}).status_code == 400


def test_worker_auth_readiness_can_be_checked_without_leaking_token(client):
    assert client.get("/health").json()["auth_required"] is True
    assert client.get("/auth-check").json() == {"ok": True}
    assert TestClient(client.app).get("/auth-check").status_code == 401


def test_storage_errors_are_actionable_json_not_unhandled_500s(client, monkeypatch):
    import main
    def no_space(*args, **kwargs):
        raise OSError("simulated full volume")
    monkeypatch.setattr(main.store, "create", no_space)
    response = client.post("/jobs/youtube", json={"url": "https://youtu.be/authorized"})
    assert response.status_code == 507
    assert "disk space" in response.json()["error"]
