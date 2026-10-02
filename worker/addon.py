"""Optional routes registered once, without capturing a stale JobStore."""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from pydantic import ValidationError

from projects import delete_project, get_project, list_projects, save_project
from stock_bgm import ensure_stock
from translate import pack, translate


def mount(app, get_store, require_token) -> None:
    dependencies = [Depends(require_token)]

    def workspace(request: Request) -> str:
        return request.headers.get("x-clipforge-user") or "local"

    @app.get("/projects", dependencies=dependencies)
    def projects_get(request: Request):
        try:
            return {"projects": list_projects(get_store().root, workspace(request))}
        except ValueError as error:
            raise HTTPException(400, str(error)) from error

    @app.post("/projects", dependencies=dependencies)
    def projects_post(request: Request, body: dict):
        try:
            return save_project(get_store().root, workspace(request), body)
        except ValidationError as error:
            raise HTTPException(400, "; ".join(item["msg"] for item in error.errors(include_context=False)[:5])) from error
        except ValueError as error:
            raise HTTPException(400, str(error)) from error

    @app.get("/projects/{project_id}", dependencies=dependencies)
    def projects_one(project_id: str, request: Request):
        try:
            project = get_project(get_store().root, workspace(request), project_id)
        except ValueError as error:
            raise HTTPException(400, str(error)) from error
        if not project:
            raise HTTPException(404, "Project not found in this workspace.")
        return project

    @app.delete("/projects/{project_id}", dependencies=dependencies)
    def projects_delete(project_id: str, request: Request):
        try:
            deleted = delete_project(get_store().root, workspace(request), project_id)
        except ValueError as error:
            raise HTTPException(400, str(error)) from error
        if not deleted:
            raise HTTPException(404, "Project not found in this workspace.")
        return {"deleted": project_id}

    @app.post("/translate", dependencies=dependencies)
    def translate_post(body: dict):
        text = str(body.get("text") or "")
        if len(text) > 10000:
            raise HTTPException(400, "Translation text must be at most 10,000 characters.")
        target, source = str(body.get("target") or "bn"), str(body.get("source") or "en")
        return {"text": translate(text, target, source), "pack": pack(text)}

    @app.get("/stock-bgm", dependencies=dependencies)
    def stock_bgm():
        return {"tracks": list(ensure_stock(get_store().root))}
