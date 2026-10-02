"""Analysis and rendering handlers; no process-global cwd or partial inputs."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import captions
import media
from execution import check_cancelled
from highlights import build_segments, find_highlights
from jobs import write_json
from pipeline_hooks import grab_thumbnail, window_for


def _load_params(work: Path) -> dict:
    return json.loads((work / "params.json").read_text(encoding="utf-8"))


def _save(work: Path, name: str, data) -> None:
    write_json(work / name, data)


def _resolve_source(work: Path, params: dict) -> tuple[Path, dict]:
    candidates = [path for path in work.glob("source.*") if path.suffix.lower() in media.ALLOWED_EXTENSIONS]
    if candidates:
        return max(candidates, key=lambda path: path.stat().st_size), {}
    if not params.get("url"):
        raise FileNotFoundError("No source media found. Upload it again.")
    source, metadata = media.download_youtube(params["url"], work)
    return source, metadata


def _transcript_from_srt(work: Path) -> dict | None:
    path = work / "captions.srt"
    if not path.is_file():
        return None
    segments = []
    content = path.read_text(encoding="utf-8-sig", errors="replace").replace("\r\n", "\n")
    pattern = r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)"
    for block in re.split(r"\n\s*\n", content):
        match = re.search(pattern, block)
        if not match:
            continue
        groups = match.groups()
        def timestamp(offset):
            h, m, s, fraction = groups[offset:offset + 4]
            return int(h) * 3600 + int(m) * 60 + int(s) + int(fraction) / (10 ** len(fraction))
        text = re.sub(r"<[^>]+>", "", block[match.end():])
        segments.append({"start": timestamp(0), "end": timestamp(4), "text": text})
    segments = captions.valid_segments(segments)
    if not segments:
        raise ValueError("The SRT sidecar contains no valid subtitle cues. Correct it or upload without it.")
    return {"language": "unknown", "segments": segments, "engine": "srt-sidecar"}


def _check_media(source: Path) -> dict:
    from config import settings
    if not media.have_tool("ffmpeg") or not media.have_tool("ffprobe"):
        raise FileNotFoundError("FFmpeg and FFprobe are required. Install them on the worker.")
    info = media.probe(source)
    if info["duration"] <= 0 or (not info["width"] and not info["has_audio"]):
        raise ValueError("The media file is empty, damaged or unreadable by FFmpeg. Try a valid MP4/MOV file.")
    if info["duration"] > settings.max_video_seconds:
        raise ValueError(f"Video exceeds the {settings.max_video_seconds}-second worker limit.")
    return info


def handle_analyze(job: dict, work: Path, progress) -> dict:
    from config import settings
    from transcribe import energy_chunk_transcript, transcribe

    params = _load_params(work)
    progress(5, "Reading source media")
    source, _ = _resolve_source(work, params)
    info = _check_media(source)
    duration = info["duration"]
    warnings = []
    progress(12, "Extracting audio")
    wav = work / "audio.wav"
    if not wav.is_file():
        media.extract_audio(source, wav)
    progress(22, "Transcribing speech")

    transcript_path = work / "transcript.json"
    if transcript_path.is_file():
        transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
    else:
        transcript = _transcript_from_srt(work)
        if transcript is None:
            transcript = (transcribe(wav, settings.whisper_model, settings.whisper_device, settings.whisper_compute)
                          if info["has_audio"] else energy_chunk_transcript(wav))
        if transcript.get("engine") == "energy-fallback":
            chunk = max(float(params.get("min_seconds", 15)), min(25.0, float(params.get("max_seconds", 90))))
            transcript = energy_chunk_transcript(wav, chunk=chunk)
        _save(work, "transcript.json", transcript)
    if transcript.get("engine") == "energy-fallback":
        warnings.append("No speech transcript is available. Highlights use timeline/audio/scene signals; install Whisper or upload an SRT sidecar for real subtitles.")
    if not info["has_audio"]:
        warnings.append("This video has no audio track.")
    progress(55, "Measuring audio energy")

    energy_path = work / "energy.json"
    if energy_path.is_file():
        energy = json.loads(energy_path.read_text(encoding="utf-8"))
    else:
        energy = media.audio_energy_curve(source, hop=0.5, duration=duration) if info["has_audio"] else [-90.0] * max(1, int(duration * 2))
        _save(work, "energy.json", energy)
    progress(65, "Detecting scene changes")
    scenes_path = work / "scenes.json"
    if scenes_path.is_file():
        scenes = json.loads(scenes_path.read_text(encoding="utf-8"))
    else:
        scenes = media.scene_changes(source) if info["width"] else []
        _save(work, "scenes.json", scenes)
    progress(75, "Ranking highlights")
    segments = build_segments(transcript, energy, scenes)
    clips = find_highlights(segments, params.get("min_seconds", 15), params.get("max_seconds", 90), params.get("limit", 8))
    _save(work, "segments.json", [segment.__dict__ for segment in segments])
    progress(95, "Saving analysis")
    return {"duration": round(duration, 2), "engine": transcript.get("engine"),
            "language": transcript.get("language"), "source_file": source.name,
            "has_video": bool(info["width"]), "has_audio": info["has_audio"],
            "has_transcript": transcript.get("engine") != "energy-fallback" and bool(transcript.get("segments")),
            "transcript_segments": len(transcript.get("segments", [])), "scene_changes": len(scenes),
            "warnings": warnings, "clips": clips}


def _padded_window(highlight: dict, durations: list[int], duration: float, pad: float) -> tuple[float, float, int]:
    return window_for(highlight, durations, duration, pad)


def _find_bgm(work: Path) -> Path | None:
    for suffix in ("mp3", "wav", "m4a", "aac", "ogg"):
        path = work / f"bgm.{suffix}"
        if path.is_file():
            return path
    return None


def handle_render(job: dict, work: Path, progress) -> dict:
    from config import settings

    params = _load_params(work)
    progress(3, "Checking render inputs")
    source, _ = _resolve_source(work, params)
    info = _check_media(source)
    if not info["width"] or not info["height"]:
        raise ValueError("The source contains audio only. A video track is required to render MP4 clips.")
    duration = info["duration"]
    clips_dir = work / "clips"
    clips_dir.mkdir(exist_ok=True)
    # Retried jobs must never expose stale files from a previous attempt.
    for path in clips_dir.iterdir():
        if path.is_file() and media.allowed_artifact(f"clips/{path.name}"):
            path.unlink()
    (work / "exports.zip").unlink(missing_ok=True)
    transcript = (json.loads((work / "transcript.json").read_text(encoding="utf-8"))
                  if (work / "transcript.json").is_file() else {"segments": []})
    speech_segments = [] if transcript.get("engine") == "energy-fallback" else transcript.get("segments", [])
    durations = [int(value) for value in params.get("durations", settings.clip_durations)]
    aspect = str(params.get("aspect", "9:16" if params.get("vertical", True) else "16:9"))
    burn = bool(params.get("captions", True))
    style = params.get("caption_style", "default")
    padding = float(params.get("padding", settings.padding_seconds))
    bgm = _find_bgm(work) if params.get("bgm") else None
    warnings = []
    if params.get("bgm") and bgm is None:
        from stock_bgm import resolve_track
        bgm = resolve_track(work.parent, "soft")
        if bgm is None:
            warnings.append("Background audio was unavailable; clips keep their original audio.")
    items = params.get("highlights") or [{"start": params.get("start", 0), "end": params.get("end", 30), "locked": True}]
    outputs = []
    for index, highlight in enumerate(items):
        progress(10 + int(85 * index / len(items)), f"Rendering clip {index + 1}/{len(items)}")
        start, end, target = _padded_window(highlight, durations, duration, padding)
        if end <= start or start >= duration:
            raise ValueError("A selected trim is outside the source video duration.")
        base = f"clip-{index + 1:02d}"
        raw = work / f"{base}-raw.mp4"
        staged = work / f"{base}-staged.mp4"
        suffix = {"9:16": "vertical", "1:1": "square", "16:9": "landscape"}[aspect]
        final = clips_dir / f"{base}-{suffix}.mp4"
        try:
            media.run_ffmpeg(
                "-ss", str(start), "-t", str(end - start), "-i", str(source),
                "-map", "0:v:0", "-map", "0:a:0?", "-c:v", "libx264", "-threads", str(max(1, settings.ffmpeg_threads)),
                "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p", "-c:a", "aac",
                "-movflags", "+faststart", str(raw),
            )
            shifted = captions.trim_segments(speech_segments, start, end)
            subtitles = {}
            if shifted:
                for format in ("srt", "vtt"):
                    path = clips_dir / f"{base}-{suffix}.{format}"
                    path.write_text(getattr(captions, f"segments_to_{format}")(shifted), encoding="utf-8")
                    subtitles[format] = path.name
            hook = str(highlight.get("title") or highlight.get("text") or "")[:72]
            filters = []
            if burn and (shifted or hook):
                resolution = {"9:16": (1080, 1920), "1:1": (1080, 1080), "16:9": (1920, 1080)}[aspect]
                track = work / f"{base}.ass"
                captions.write_ass(shifted, track, style=style, resolution=resolution, hook_text=hook)
                filters.append(captions.burn_filter(Path(track.name)))
            center_x = media.face_center_x(source, start, end) if params.get("face_crop", True) and aspect == "9:16" else None
            extra = ["eq=contrast=1.08:saturation=1.15:brightness=0.02"] if params.get("grade") else []
            _render_final(raw, staged if bgm else final, info, center_x, filters, aspect, work, extra,
                          hook_zoom=bool(params.get("hook_zoom")))
            mixed_bgm = False
            if bgm:
                try:
                    media.mix_bgm(staged, bgm, final, bgm_vol=params.get("bgm_volume", 0.18), duck=params.get("duck", True))
                    mixed_bgm = True
                except Exception:
                    check_cancelled()
                    shutil.copy2(staged, final)
                    warnings.append(f"Clip {index + 1}: background audio could not be mixed; original audio kept.")
            if not final.is_file() or final.stat().st_size == 0:
                raise RuntimeError("FFmpeg did not produce a valid output file.")
            thumbnail = grab_thumbnail(final, clips_dir / f"{base}-{suffix}.jpg", min(0.3, (end - start) / 2))
            outputs.append({"file": final.name, "start": start, "end": end, "duration": round(end - start, 2),
                            "target": target, "score": highlight.get("score"), "aspect": aspect,
                            "vertical": aspect == "9:16", "captions": burn and bool(shifted or hook),
                            "bgm": mixed_bgm, "bytes": final.stat().st_size,
                            "thumbnail": thumbnail.name if thumbnail else None, "subtitles": subtitles,
                            "download": f"/jobs/{job['id']}/files/clips/{final.name}"})
        finally:
            raw.unlink(missing_ok=True)
            staged.unlink(missing_ok=True)
        progress(10 + int(85 * (index + 1) / len(items)), f"Saved clip {index + 1}/{len(items)}")
    _save(work, "render.json", outputs)
    return {"clips": outputs, "warnings": list(dict.fromkeys(warnings))}


def _render_final(raw: Path, destination: Path, info: dict, center_x, caption_filters: list[str],
                  aspect: str, work: Path, extra_filters: list[str] | None = None, *, hook_zoom: bool = False) -> None:
    from config import settings
    width, height = int(info.get("width") or 0), int(info.get("height") or 0)
    filters = list(extra_filters or [])
    if aspect in ("9:16", "1:1") and width >= 2 and height >= 2:
        ratio = 9 / 16 if aspect == "9:16" else 1
        crop_w = max(2, min(width, int(height * ratio)) // 2 * 2)
        crop_h = max(2, min(height, int(width / ratio)) // 2 * 2)
        x = max(0, min(width - crop_w, round((center_x if center_x is not None else 0.5) * width - crop_w / 2)))
        filters.append(f"crop={crop_w}:{crop_h}:{x}:{(height - crop_h) // 2}")
    output_w, output_h = {"9:16": (1080, 1920), "1:1": (1080, 1080), "16:9": (1920, 1080)}[aspect]
    filters.append(f"scale={output_w}:{output_h}:force_original_aspect_ratio=decrease:force_divisible_by=2:flags=bicubic")
    filters.append(f"pad={output_w}:{output_h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30")
    if hook_zoom:
        filters.append(f"zoompan=z='if(lt(on,60),1.08-0.08*on/60,1)':d=1:x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':s={output_w}x{output_h}:fps=30")
    filters.extend(caption_filters)
    media.run_ffmpeg(
        "-i", str(raw), "-vf", ",".join(filters), "-map", "0:v:0", "-map", "0:a:0?",
        "-c:v", "libx264", "-threads", str(max(1, settings.ffmpeg_threads)), "-preset", "veryfast", "-crf", "22",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-movflags", "+faststart", str(destination),
        timeout=1800, cwd=work,
    )
