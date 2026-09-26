"""Optional LibreTranslate bridge. Falls back to identity if unset/unavailable."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

LANGS = {"en": "en", "bn": "bn", "hi": "hi", "bengali": "bn", "hindi": "hi"}


def translate(text: str, target: str, source: str = "en") -> str:
    url = os.getenv("CLIPFORGE_TRANSLATE_URL", "").strip()
    tgt = LANGS.get(target, target)
    src = LANGS.get(source, source)
    if not text.strip() or not url or tgt == src:
        return text
    payload = json.dumps({"q": text, "source": src, "target": tgt, "format": "text"}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return str(data.get("translatedText") or data.get("translated_text") or text)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
        return text


def pack(text: str) -> dict:
    return {
        "en": text,
        "bn": translate(text, "bn"),
        "hi": translate(text, "hi"),
    }
