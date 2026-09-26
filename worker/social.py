"""Social caption packs for YouTube, Instagram and TikTok in EN / BN / HI."""
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
    "tiktok": ["#fyp", "#foryou", "#viral", "#tiktok"],
    "instagram": ["#reels", "#instagram", "#explore", "#instareels"],
    "reels": ["#reels", "#instagram", "#explore", "#instareels"],
    "youtube": ["#shorts", "#youtube", "#youtubeshorts", "#subscribe"],
    "shorts": ["#shorts", "#youtube", "#youtubeshorts", "#subscribe"],
    "square": ["#clip", "#highlight"],
    "": ["#shorts", "#reels", "#fyp"],
}

CTA = {
    ("en", "tiktok"): "Watch till the end — then stitch this.",
    ("en", "instagram"): "Save this Reel and share it with a friend.",
    ("en", "youtube"): "If this helped, like and subscribe for more Shorts.",
    ("en", ""): "Watch this clip.",
    ("bn", "tiktok"): "শেষ পর্যন্ত দেখুন — তারপর স্টিচ করুন।",
    ("bn", "instagram"): "রিলটা সেভ করুন এবং বন্ধুদের শেয়ার করুন।",
    ("bn", "youtube"): "সাহায্য হলে লাইক ও সাবসক্রাইব করুন।",
    ("bn", ""): "ক্লিপটাটি দেখুন।",
    ("hi", "tiktok"): "अंत तक देखें — फिर स्टिच करें।",
    ("hi", "instagram"): "रील सेव करें और दोस्त के साथ शेयर करें।",
    ("hi", "youtube"): "अच्छा लगा तो लाइक और सबस्क्राइब करें।",
    ("hi", ""): "यह क्लिप देखें।",
}

LANG_TAGS = {
    "bn": ["#bangla", "#bengali"],
    "hi": ["#hindi", "#india"],
    "en": [],
}


def _normalize_platform(platform: str) -> str:
    p = (platform or "").strip().lower()
    aliases = {
        "yt": "youtube", "you tube": "youtube", "youtube shorts": "youtube",
        "ig": "instagram", "insta": "instagram",
        "tt": "tiktok", "tik tok": "tiktok",
    }
    return aliases.get(p, p)


def _slug_tag(word: str) -> str | None:
    clean = re.sub(r"[^A-Za-z0-9]", "", word)
    if len(clean) < 3 or clean.lower() in STOP:
        return None
    if clean.isdigit():
        return None
    return "#" + clean[:24]


def hashtags(text: str, platform: str = "", limit: int = 10, lang: str = "en") -> list[str]:
    platform = _normalize_platform(platform)
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
        if len(tags) >= max(1, limit - 5):
            break
    for extra in LANG_TAGS.get(lang, []) + PLATFORM_TAGS.get(platform, PLATFORM_TAGS[""]):
        if extra.lower() not in seen:
            tags.append(extra)
            seen.add(extra.lower())
    return tags[:limit]


def _hook(title: str, text: str) -> str:
    hook = " ".join((title or "").split()) or "Watch this clip."
    if len(hook) > 140:
        hook = hook[:137] + "..."
    body = " ".join((text or "").split())
    if body and body.lower() != hook.lower():
        snippet = body if len(body) <= 160 else body[:157] + "..."
        return f"{hook}\n\n{snippet}"
    return hook


def caption(title: str, text: str, platform: str = "", lang: str = "en") -> dict:
    platform = _normalize_platform(platform)
    lang = lang if lang in ("en", "bn", "hi") else "en"
    line = _hook(title, text)
    cta = CTA.get((lang, platform)) or CTA.get((lang, "")) or CTA[("en", "")]
    if cta and cta.lower() not in line.lower():
        line = f"{line}\n\n{cta}"
    tags = hashtags(f"{title} {text}", platform=platform, lang=lang)
    tag_line = " ".join(tags)
    return {
        "caption": line,
        "hashtags": tags,
        "hashtag_line": tag_line,
        "post": f"{line}\n\n{tag_line}".strip(),
        "language": lang,
        "platform": platform or "all",
    }


def platform_packs(title: str, text: str, lang: str = "en") -> dict[str, dict]:
    return {
        "youtube": caption(title, text, "youtube", lang=lang),
        "instagram": caption(title, text, "instagram", lang=lang),
        "tiktok": caption(title, text, "tiktok", lang=lang),
    }


def language_packs(title: str, text: str) -> dict[str, dict[str, dict]]:
    return {lang: platform_packs(title, text, lang=lang) for lang in ("en", "bn", "hi")}
