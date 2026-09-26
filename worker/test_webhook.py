from webhook import notify
from translate import translate, pack
from projects import save_project, list_projects
from stock_bgm import PRESETS
from bumpers import stitch
from pathlib import Path


def test_notify_noop_without_url(monkeypatch):
    monkeypatch.delenv("CLIPFORGE_WEBHOOK_URL", raising=False)
    notify({"id": "abc", "kind": "analyze", "status": "completed"})


def test_translate_identity_without_url(monkeypatch):
    monkeypatch.delenv("CLIPFORGE_TRANSLATE_URL", raising=False)
    assert translate("Hello world", "bn") == "Hello world"
    p = pack("Hook line")
    assert p["en"] == "Hook line"


def test_projects_roundtrip(tmp_path):
    doc = save_project(tmp_path, "user-1", {"name": "Demo", "job_id": "j1"})
    items = list_projects(tmp_path, "user-1")
    assert items[0]["id"] == doc["id"]
    assert items[0]["name"] == "Demo"


def test_stock_presets_defined():
    assert set(PRESETS) == {"soft", "warm", "pulse"}


def test_stitch_noop_without_bumpers(tmp_path):
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"x")
    assert stitch(clip, tmp_path) == clip
