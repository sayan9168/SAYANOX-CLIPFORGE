"""Extra FastAPI routes mounted once at JobStore.start()."""
from __future__ import annotations

_mounted = False


def mount() -> None:
    global _mounted
    if _mounted:
        return
    try:
        import main as m
        from fastapi import Depends, Request
        from config import settings
        from projects import list_projects, save_project
        from stock_bgm import ensure_stock
        from translate import pack, translate
    except Exception:
        return

    app = getattr(m, "app", None)
    store = getattr(m, "store", None)
    require_token = getattr(m, "require_token", None)
    if app is None or store is None:
        return

    deps = [Depends(require_token)] if require_token else []

    @app.get("/jobs", dependencies=deps)
    def jobs_list(limit: int = 50):
        rows = []
        for j in store.list(max(1, min(200, int(limit)))):
            rows.append({
                "id": j.get("id"), "kind": j.get("kind"), "status": j.get("status"),
                "progress": j.get("progress"), "error": j.get("error"),
            })
        return {"jobs": rows}

    @app.get("/projects", dependencies=deps)
    def projects_get(request: Request):
        token = request.headers.get("x-clipforge-user") or "local"
        return {"projects": list_projects(settings.data_dir, token)}

    @app.post("/projects", dependencies=deps)
    async def projects_post(request: Request):
        token = request.headers.get("x-clipforge-user") or "local"
        body = await request.json()
        return save_project(settings.data_dir, token, body if isinstance(body, dict) else {})

    @app.post("/translate", dependencies=deps)
    async def translate_post(request: Request):
        body = await request.json()
        text = str((body or {}).get("text") or "")
        target = str((body or {}).get("target") or "bn")
        source = str((body or {}).get("source") or "en")
        return {"text": translate(text, target, source), "pack": pack(text)}

    @app.get("/stock-bgm", dependencies=deps)
    def stock_bgm():
        tracks = ensure_stock(settings.data_dir)
        return {"tracks": list(tracks)}

    _mounted = True
