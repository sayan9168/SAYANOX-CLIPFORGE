"""Real FFmpeg integration tests; no downloads, GPU or speech models needed."""
import io
import json
import math
import shutil
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

import media
import pipeline
from jobs import write_json
from test_jobs import wait

pytestmark = pytest.mark.skipif(not media.have_tool("ffmpeg") or not media.have_tool("ffprobe"), reason="FFmpeg and FFprobe are required for media integration tests")
SRT = "1\n00:00:00,000 --> 00:00:03,000\nHere is why this matters!\n\n2\n00:00:03,000 --> 00:00:06,000\nWatch this amazing result.\n"


@pytest.fixture(scope="module")
def source(tmp_path_factory):
    path = tmp_path_factory.mktemp("media") / "source.mp4"
    media.run_ffmpeg("-f", "lavfi", "-i", "testsrc2=size=160x90:rate=25", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=16000", "-t", "6", "-c:v", "libx264", "-threads", "2", "-c:a", "aac", str(path))
    return path


def test_srt_analysis_precedes_whisper_and_energy_json_is_finite(source, tmp_path, monkeypatch):
    import transcribe
    monkeypatch.setattr(transcribe, "transcribe", lambda *args: (_ for _ in ()).throw(AssertionError("SRT must bypass Whisper")))
    shutil.copy2(source, tmp_path / "source.mov")
    (tmp_path / "captions.srt").write_text(SRT)
    write_json(tmp_path / "params.json", {"min_seconds": 5, "max_seconds": 10, "limit": 3})
    result = pipeline.handle_analyze({"id": "sourcejob"}, tmp_path, lambda *args: None)
    assert result["engine"] == "srt-sidecar" and result["has_transcript"]
    assert result["source_file"] == "source.mov" and result["has_video"]
    assert result["clips"]
    curve = json.loads((tmp_path / "energy.json").read_text())
    assert 10 <= len(curve) <= 14 and all(math.isfinite(value) for value in curve)
    assert any(value > -60 for value in curve)


@pytest.mark.parametrize("aspect,dimensions", [("9:16", (1080, 1920)), ("1:1", (1080, 1080)), ("16:9", (1920, 1080))])
def test_real_render_aspects_and_subtitle_bounds(source, tmp_path, aspect, dimensions):
    shutil.copy2(source, tmp_path / "source.mp4")
    write_json(tmp_path / "transcript.json", {"engine": "srt-sidecar", "segments": [{"start": 0, "end": 6, "text": "Real captions"}]})
    write_json(tmp_path / "params.json", {"highlights": [{"start": 1, "end": 3, "locked": True, "title": "Stop scrolling"}], "durations": [5], "aspect": aspect, "captions": True, "face_crop": False, "grade": True, "hook_zoom": aspect == "9:16", "bgm": aspect == "9:16"})
    result = pipeline.handle_render({"id": "renderjob"}, tmp_path, lambda *args: None)
    clip = result["clips"][0]
    info = media.probe(tmp_path / "clips" / clip["file"])
    assert (info["width"], info["height"]) == dimensions
    assert info["duration"] == pytest.approx(2, abs=0.15)
    assert info["has_audio"]
    assert clip["subtitles"]["srt"] and clip["subtitles"]["vtt"]
    assert "00:00:00,000 --> 00:00:02,000" in (tmp_path / "clips" / clip["subtitles"]["srt"]).read_text()
    assert not list(tmp_path.glob("*-raw.mp4")) and not list(tmp_path.glob("*-staged.mp4"))


def test_energy_fallback_does_not_export_fake_speech_captions(source, tmp_path):
    shutil.copy2(source, tmp_path / "source.mp4")
    write_json(tmp_path / "transcript.json", {"engine": "energy-fallback", "segments": [{"start": 0, "end": 6, "text": "Highlight window placeholder"}]})
    write_json(tmp_path / "params.json", {"highlights": [{"start": 0, "end": 1, "locked": True, "title": "My hook"}], "aspect": "1:1", "captions": True, "face_crop": False})
    clip = pipeline.handle_render({"id": "fallbackjob"}, tmp_path, lambda *args: None)["clips"][0]
    assert clip["subtitles"] == {}
    assert "Highlight window placeholder" not in (tmp_path / "clip-01.ass").read_text()
    assert "My hook" in (tmp_path / "clip-01.ass").read_text()


def test_concurrent_render_does_not_change_process_cwd(source, tmp_path):
    before = Path.cwd()
    def render(index):
        work = tmp_path / f"work {index}"
        work.mkdir()
        shutil.copy2(source, work / "source.mp4")
        write_json(work / "params.json", {"highlights": [{"start": index, "end": index + 1, "locked": True, "title": f"Hook {index}"}], "aspect": "1:1", "captions": True, "face_crop": False})
        outputs = pipeline.handle_render({"id": f"job{index}"}, work, lambda *args: None)
        assert "Hook " + str(index) in (work / "clip-01.ass").read_text()
        assert (work / "clips" / outputs["clips"][0]["file"]).is_file()
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(render, [0, 1]))
    assert Path.cwd() == before


def test_full_upload_analysis_render_and_download_api(client, source):
    import main
    uploaded = client.post("/jobs/upload", files={"video": ("original.MOV", source.read_bytes(), "video/quicktime"), "captions": ("real.srt", SRT.encode(), "application/x-subrip")}, data={"min_seconds": "5", "max_seconds": "10", "limit": "2"})
    assert uploaded.status_code == 200
    parent = uploaded.json()["job_id"]
    analyzed = wait(main.store, parent, timeout=20)
    assert analyzed["status"] == "completed" and analyzed["result"]["engine"] == "srt-sidecar"
    rendered = client.post("/jobs/render", json={"parent_job": parent, "highlights": [{"start": 1, "end": 3, "title": "My real cut"}], "aspect": "1:1", "grade": True, "captions": True, "face_crop": False})
    assert rendered.status_code == 200
    job_id = rendered.json()["job_id"]
    done = wait(main.store, job_id, timeout=20)
    assert done["status"] == "completed"
    clip = done["result"]["clips"][0]
    response = client.get(f"/jobs/{job_id}/files/clips/{clip['file']}", headers={"Range": "bytes=0-1023"})
    assert response.status_code == 206 and len(response.content) == 1024
    assert client.get(f"/jobs/{parent}/transcript?format=vtt").text.startswith("WEBVTT")
    archive = zipfile.ZipFile(io.BytesIO(client.get(f"/jobs/{job_id}/zip").content))
    assert clip["file"] in archive.namelist() and clip["subtitles"]["srt"] in archive.namelist() and "render.json" in archive.namelist()


def test_phone_rotation_metadata_is_used_for_safe_vertical_crops(source, tmp_path):
    rotated = tmp_path / "source.mp4"
    try:
        media.run_ffmpeg("-display_rotation", "90", "-i", str(source), "-c", "copy", str(rotated))
    except RuntimeError as error:
        if "Unrecognized option" not in str(error):
            raise
        # Legacy FFmpeg sets display matrices with output metadata instead.
        media.run_ffmpeg("-i", str(source), "-c", "copy", "-metadata:s:v:0", "rotate=90", str(rotated))
    assert (media.probe(rotated)["width"], media.probe(rotated)["height"]) == (90, 160)
    write_json(tmp_path / "params.json", {"highlights": [{"start": 0, "end": 1, "locked": True}], "aspect": "9:16", "captions": False, "face_crop": False})
    clip = pipeline.handle_render({"id": "phonejob"}, tmp_path, lambda *args: None)["clips"][0]
    info = media.probe(tmp_path / "clips" / clip["file"])
    assert (info["width"], info["height"]) == (1080, 1920)
    assert info["duration"] == pytest.approx(1, abs=0.15)
