"""Optional job-complete webhook (CLIPFORGE_WEBHOOK_URL)."""
from __future__ import annotations

import json
import threading
import urllib.request


def notify(job: dict) -> None:
    try:
        from config import settings
        url = getattr(settings, "webhook_url", "") or ""
    except Exception:
        url = ""
    if not url:
        return

    def _post() -> None:
        payload = json.dumps(
            {
                "job_id": job.get("id"),
                "kind": job.get("kind"),
                "status": job.get("status"),
                "error": job.get("error"),
                "progress": job.get("progress"),
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            url, data=payload, method="POST", headers={"Content-Type": "application/json"}
        )
        try:
            urllib.request.urlopen(req, timeout=8)
        except Exception:
            pass

    threading.Thread(target=_post, daemon=True, name="clipforge-webhook").start()
