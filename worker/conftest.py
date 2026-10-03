import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("CLIPFORGE_DATA", "/tmp/clipforge-test")

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
