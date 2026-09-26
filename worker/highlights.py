"""Highlight detection engine (v0.8).

Combines transcript signals with media signals and attaches English
social caption packs for YouTube, Instagram and TikTok.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Iterable

from social import caption as social_caption
from social import platform_packs

HOOK_PATTERNS = [
    r"\b(the secret|most important|here'?s why|here'?s how|nobody tells|the truth about)\b",
    r"\b(stop scrolling|watch this|you need to|don'?t make this mistake|biggest mistake)\b",
    r"\b(why|how)\b.*\?",
    r"^\W*(number \d+|#\d+|\d+ (ways|tips|reasons|things))\b",
    r"\b(i learned|i discovered|the result|finally|turns out)\b",
    r"\b(what if|imagine if|think about|let me tell you)\b",
    r"\b(game.?changer|mind.?blowing|life.?changing|never.?before)\b",
]

_EXCITEMENT = re.compile(
    r"[!?]|amazing|insane|unbelievable|huge|incredible|crazy|wow|shocking|powerful",
    re.I,
)

TITLE_STOP = re.compile(
    r"^(so|and|but|well|okay|ok|um|uh|like|you know|basically)\b", re.I
)


@dataclass(frozen=True)
class Segment:
    start: float
    end: float
    text: str
    speech_score: float = 0.5
    emotion_score: float = 0.5
    audio_score: float = 0.5
    visual_score: float = 0.5
    hook_score: float | None = None


def hook_strength(text: str) -> float:
    t = text.lower().strip()
    if not t:
        return 0.0
    hits = sum(1 for p in HOOK_PATTERNS if re.search(p, t))
    return min(1.0, 0.25 + 0.35 * hits) if hits else 0.15


def _emotion(text: str) -> float:
    base = 0.4 if not _EXCITEMENT.search(text) else 0.75
    caps = sum(1 for c in text if c.isupper())
    words = max(1, len(text.split()))
    return min(1.0, base + min(0.25, caps / words))


def _make_title(text: str, score_val: int) -> str:
    cleaned = " ".join(text.split())
    if not cleaned:
        return f"Highlight ({score_val})"
    parts = re.split(r"(?<=[.!?])\s+", cleaned)
    candidate = parts[0] if parts else cleaned
    candidate = TITLE_STOP.sub("", candidate).strip(" ,;:-")
    words = candidate.split()
    if len(words) > 10:
        candidate = " ".join(words[:10]) + "…"
    if len(candidate) > 72:
        candidate = candidate[:69] + "…"
    return candidate or f"Highlight ({score_val})"


def _make_reason(seg: Segment, value: int) -> str:
    bits = []
    hook = seg.hook_score if seg.hook_score is not None else hook_strength(seg.text)
    if hook >= 0.5:
        bits.append("strong hook")
    if seg.speech_score >= 0.7:
        bits.append("clear speech")
    if seg.emotion_score >= 0.65:
        bits.append("high energy")
    if seg.audio_score >= 0.65:
        bits.append("audio peak")
    if seg.visual_score >= 0.55:
        bits.append("visual cuts")
    if seg.text.rstrip().endswith((".", "!", "?")):
        bits.append("complete thought")
    if not bits:
        bits.append("balanced signals")
    return f"Score {value}/100 — " + ", ".join(bits) + "."


def score(s: Segment) -> int:
    duration = max(0.5, s.end - s.start)
    density = min(1.0, len(s.text.strip()) / (duration * 4.0))
    ending = 1.0 if s.text.rstrip().endswith((".", "!", "?")) else 0.45
    hook = s.hook_score if s.hook_score is not None else hook_strength(s.text)
    emotion = max(
        s.emotion_score, 0.9 if _EXCITEMENT.search(s.text) else s.emotion_score
    )
    q_bonus = 0.05 if "?" in s.text else 0.0
    return round(
        100
        * (
            hook * 0.24
            + density * 0.14
            + s.speech_score * 0.14
            + emotion * 0.14
            + s.audio_score * 0.12
            + s.visual_score * 0.10
            + ending * 0.10
            + q_bonus
        )
    )


def enrich(segments: Iterable[Segment]) -> list[Segment]:
    out = []
    for s in segments:
        out.append(
            replace(
                s,
                hook_score=hook_strength(s.text),
                emotion_score=max(s.emotion_score, _emotion(s.text)),
            )
        )
    return out


def _overlap(a: Segment, b: Segment) -> float:
    inter = min(a.end, b.end) - max(a.start, b.start)
    if inter <= 0:
        return 0.0
    return inter / max(1e-6, min(a.end - a.start, b.end - b.start))


def find_highlights(
    segments: Iterable[Segment],
    min_seconds=15,
    max_seconds=90,
    limit=10,
    dedupe_threshold=0.35,
    platform: str = "",
):
    items = enrich(list(segments))
    candidates: list[tuple[int, Segment]] = []
    n = len(items)
    for i, s in enumerate(items):
        if not s.text.strip():
            continue
        end = s.end
        texts = [s.text.strip()]
        j = i + 1
        while j < n and end - s.start < min_seconds:
            texts.append(items[j].text.strip())
            end = items[j].end
            j += 1
        if not (min_seconds <= end - s.start <= max_seconds * 1.5):
            continue
        merged = replace(s, end=end, text=" ".join(t for t in texts if t))
        candidates.append((score(merged), merged))

    candidates.sort(key=lambda x: x[0], reverse=True)
    chosen: list[tuple[int, Segment]] = []
    for value, seg in candidates:
        dup = any(
            _overlap(seg, old) > dedupe_threshold
            or (seg.start < old.end and seg.end > old.start)
            for _, old in chosen
        )
        if dup:
            continue
        chosen.append((value, seg))
        if len(chosen) >= limit:
            break

    results = []
    for value, seg in chosen:
        title = _make_title(seg.text, value)
        pack = social_caption(title, seg.text, platform=platform)
        packs = platform_packs(title, seg.text)
        results.append(
            {
                "start": round(seg.start, 2),
                "end": round(seg.end, 2),
                "score": value,
                "text": seg.text,
                "title": title,
                "reason": _make_reason(seg, value),
                "caption": pack["caption"],
                "hashtags": pack["hashtags"],
                "hashtag_line": pack["hashtag_line"],
                "post": pack["post"],
                "packs": packs,
                "caption_language": "en",
                "signals": {
                    "hook": round(
                        seg.hook_score
                        if seg.hook_score is not None
                        else hook_strength(seg.text),
                        2,
                    ),
                    "speech": round(seg.speech_score, 2),
                    "emotion": round(seg.emotion_score, 2),
                    "audio": round(seg.audio_score, 2),
                    "visual": round(seg.visual_score, 2),
                },
            }
        )
    return results


def build_segments(
    transcript: dict,
    energy_curve: list[float],
    scenes: list[float],
    hop: float = 0.5,
    silence_db: float = -45.0,
) -> list[Segment]:
    segs: list[Segment] = []
    for seg in transcript.get("segments", []):
        start, end = float(seg["start"]), float(seg["end"])
        lo, hi = int(start / hop), int(end / hop) + 1
        window = energy_curve[lo:hi] if energy_curve else []
        voiced = [v for v in window if v > silence_db]
        speech_ratio = len(voiced) / max(1, len(window)) if window else 0.6
        if window and energy_curve:
            loud = sum(window) / len(window)
            global_med = sorted(energy_curve)[len(energy_curve) // 2]
            audio_norm = max(0.0, min(1.0, 0.5 + (loud - global_med) / 24.0))
        else:
            audio_norm = 0.5
        cuts = sum(1 for t in scenes if start <= t <= end)
        visual = min(1.0, 0.2 + cuts * 0.25)
        segs.append(
            Segment(
                round(start, 2),
                round(end, 2),
                str(seg.get("text", "")).strip(),
                speech_score=round(speech_ratio, 2),
                audio_score=round(audio_norm, 2),
                visual_score=round(visual, 2),
            )
        )
    return segs
