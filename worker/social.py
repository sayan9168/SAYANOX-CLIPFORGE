"""English social caption + hashtag pack for Shorts / Reels / TikTok."""
from __future__ import annotations

import re

STOP = {
    "the", "a", "an", "and", "or", "but", "so", "to", "of", "in", "on", "for",
    "is", "are", "was", "were", "be", "been", "it", "this", "that", "with",
    "you", "your", "we", "our", "i", "me", "my", "they", "them", "their",
    "at", "as", "from", "by", "if", "then", "than", "too", "very", "just",
    "about", "into", "over", "also", "not", "no", "yes", "do", "does", "did",
    "have", "has", "had", "will", "can", "could", "should", "would",
}

PLATFORM_TAGS = {
    "tiktok": ["#fyp", "#foryou", "#viral"],
    "reels": ["#reels", "#instagram", "#explore"],
    "shorts": ["#shorts", "#youtube", "#subscribe"],
    "square": ["#clip", "#highlight"],
    "": ["#shorts", "#reels", "#fyp"],
}


def _slug_tag(word: str) -> str | None:
    clean = re.sub(r"[^A-Za-z0-9]", "", word)
    if len(clean) < 3 or clean.lower() in STOP:
        return None
    if clean.isdigit():
        return None
    return "#" + clean[:24]


def hashtags(text: str, platform: str = "", limit: int = 8) -> list[str]:
    tags: list[str] = []
    seen: set[str] = set()
    for raw in re.findall(r"[A-Za-z][A-Za-z0-9']+", text or ""):
        tag = _slug_tag(raw)
        if not tag:
            continue
        key = tag.lower()
        if key in seen:
            continue
        seen.add(key)
        tags.append(tag)
        if len(tags) >= max(1, limit - 3):
            break
    for extra in PLATFORM_TAGS.get(platform, PLATFORM_TAGS[""]):
        if extra.lower() not in seen:
            tags.append(extra)
            seen.add(extra.lower())
    return tags[:limit]


def caption(title: str, text: str, platform: str = "") -> dict:
    """English post copy + hashtag line ready to paste."""
    hook = " ".join((title or "").split()) or "Watch this clip."
    if len(hook) > 140:
        hook = hook[:137] + "..."
    body = " ".join((text or "").split())
    if body and body.lower() != hook.lower():
        snippet = body if len(body) <= 180 else body[:177] + "..."
        line = f"{hook}\n\n{snippet}"
    else:
        line = hook
    tags = hashtags(f"{title} {text}", platform=platform)
    tag_line = " ".join(tags)
    return {
        "caption": line,
        "hashtags": tags,
        "hashtag_line": tag_line,
        "post": f"{line}\n\n{tag_line}".strip(),
        "language": "en",
    }
