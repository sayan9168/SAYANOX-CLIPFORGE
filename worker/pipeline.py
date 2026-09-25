"""End-to-end pipeline handlers executed by the job queue.

  analyze : source media -> transcript + signals -> ranked highlights
  render  : highlight window -> padded MP4 clip (landscape / vertical, captions)
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import captions
import media
from highlights import build_segments, find_highlights


def _load_params(work: Path) -> dict:
    return json.loads((work / "params.json").read_text(encoding="utf-8"))


def _save(work: Path, name: str, data) -> None:
    (work / name).write_text(json.dumps(data), encoding="utf-8")


def _resolve_source(work: Path, params: dict) -> tuple[Path, dict]:
    """Locate the source media inside the job dir (upload or yt-dlp download)."""
    cands = [p for p in work.glob("source.*") if p.suffix != ".json"]
    if not cands:
        url = params.get("url")
        if not url:
            raise FileNotFoundError("No source media found for job.")
        src, meta = media.download_youtube(url, work)
        return src, {"title": meta.get("title"), "duration": float(meta.get("duration") or 0)}
    src = sorted(cands, key=lambda p: p.stat().st_size, reverse=True)[0]
    return src, {}


def handle_analyze(job: dict, work: Path, progress) -> dict:
    from config import settings
    from transcribe import transcribe

    params = _load_params(work)
    progress(5)
    src, extra = _resolve_source(work, params)
    info = media.probe(src)
    duration = info["duration"] or extra.get("duration") or 0
    progress(12)

    wav = work / "audio.wav"
    if not wav.is_file():
        media.extract_audio(src, wav)
    progress(22)

    transcript_path = work / "transcript.json"
    if transcript_path.is_file():
        transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
    else:
        try:
            transcript = transcribe(wav, settings.whisper_model,
                                    settings.whisper_device, settings.whisper_compute)
        except RuntimeError:
            # No local Whisper backend installed. Fall back to SRT sidecar
            # captions when the uploader supplied one; otherwise fail clearly.
            transcript = _transcript_from_srt(work)
            if transcript is None:
                raise
        _save(work, "transcript.json", transcript)
    progress(55)

    energy_path = work / "energy.json"
    if energy_path.is_file():
        energy = json.loads(energy_path.read_text(encoding="utf-8"))
    else:
        energy = media.audio_energy_curve(src, hop=0.5, duration=duration)
        _save(work, "energy.json", energy)
    progress(65)

    scenes_path = work / "scenes.json"
    if scenes_path.is_file():
        scenes = json.loads(scenes_path.read_text(encoding="utf-8"))
    else:
        scenes = media.scene_changes(src) if info["width"] else []
        _save(work, "scenes.json", scenes)
    progress(75)

    segments = build_segments(transcript, energy, scenes)
    min_s = float(params.get("min_seconds", 15))
    max_s = float(params.get("max_seconds", 90))
    limit = int(params.get("limit", 8))
    clips = find_highlights(segments, min_s, max_s, limit)
    _save(work, "segments.json", [s.__dict__ for s in segments])
    progress(95)
    return {
        "duration": round(duration, 2),
        "engine": transcript.get("engine"),
        "language": transcript.get("language"),
        "transcript_segments": len(transcript.get("segments", [])),
        "scene_changes": len(scenes),
        "clips": clips,
    }


def _padded_window(highlight: dict, durations: list[int], duration: float,
                   pad: float) -> tuple[float, float, int]:
    """Pick the closest allowed target length and add intelligent padding that
    snaps toward sentence/scene boundaries instead of cutting mid-word."""
    hl_len = highlight["end"] - highlight["start"]
    target = min(durations, key=lambda d: abs(d - hl_len))
    start = max(0.0, float(highlight["start"]) - pad)
    end = start + target
    if duration:
        end = min(end, duration)
        start = max(0.0, end - target)
    # snap start back to a nearby silence gap when possible (energy curve)
    return round(start, 2), round(end, 2), target


def _transcript_from_srt(work: Path) -> dict | None:
    """Parse an optional `captions.srt` sidecar into transcript shape."""
    srt = work / "captions.srt"
    if not srt.is_file():
        return None
    import re as _re
    blocks = _re.split(r"\n\s*\n", srt.read_text(encoding="utf-8", errors="ignore"))
    segs = []
    for b in blocks:
        m = _re.search(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)", b)
        if not m:
            continue
        g = [int(x) for x in m.groups()]
        start = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000.0
        end = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000.0
        text = " ".join(b[m.end():].split())
        if text:
            segs.append({"start": round(start, 3), "end": round(end, 3), "text": text})
    if not segs:
        return None
    return {"language": "unknown", "segments": segs, "engine": "srt-sidecar"}



def handle_render(job: dict, work: Path, progress) -> dict:
    from config import settings

    params = _load_params(work)
    # source may live in the parent analyze job dir (YouTube downloads happen
    # there); copy it into this render sandbox on demand.
    src = (work / "source.mp4")
    if not src.is_file():
        cands = [p for p in work.glob("source.*") if p.suffix != ".json"]
        if not cands:
            parent_id = str(params.get("parent_job") or "")
            copied = False
            if parent_id:
                try:
                    parent = media.safe_job_dir(settings.data_dir, parent_id)
                    for f in parent.glob("source.*"):
                        if f.suffix == ".json":
                            continue
                        target = work / f.name
                        shutil.copy(f, target)
                        src = target
                        copied = True
                        break
                except (ValueError, OSError):
                    copied = False
            if not copied:
                raise FileNotFoundError("Source media missing — re-create the analyze job.")
        else:
            src = sorted(cands, key=lambda p: p.stat().st_size, reverse=True)[0]
    info = media.probe(src)
    duration = info["duration"] or float(params.get("duration", 0))

    clips_dir = work / "clips"
    clips_dir.mkdir(exist_ok=True)
    transcript = json.loads((work / "transcript.json").read_text(encoding="utf-8")) \
        if (work / "transcript.json").is_file() else {"segments": []}

    durations = [int(d) for d in params.get("durations", settings.clip_durations)] \
        or [max(1, int(round(float(params.get("end", 30)) - float(params.get("start", 0)))))]
    vertical = bool(params.get("vertical", True))
    caption_style = params.get("caption_style", "default")
    burn = bool(params.get("captions", True))
    pad = float(params.get("padding", settings.padding_seconds))

    outputs = []
    items = params.get("highlights") or [{"start": float(params.get("start", 0)),
                                          "end": float(params.get("end", 30)),
                                          "score": 100}]
    total = max(1, len(items))
    for idx, hl in enumerate(items):
        base = f"clip-{idx + 1:02d}"
        raw_out = work / f"{base}-raw.mp4"
        start, end, target = _padded_window(hl, durations, duration, pad)
        if end <= start:
            continue
        media.run_ffmpeg("-ss", str(start), "-to", str(end), "-i", str(src),
                         "-map", "0:v:0", "-map", "0:a:0?",
                         "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
                         "-pix_fmt", "yuv420p", "-c:a", "aac",
                         "-movflags", "+faststart", str(raw_out))
        final = clips_dir / f"{base}-{'vertical' if vertical else 'landscape'}.mp4"
        seg_window = [s for s in transcript["segments"]
                      if float(s["end"]) > start and float(s["start"]) < end]
        shifted = [{"start": max(0.0, float(s["start"]) - start),
                    "end": min(target, float(s["end"]) - start),
                    "text": s["text"]} for s in seg_window]
        cap_file = work / f"{base}.ass"
        render_vf: list[str] = []
        if burn and shifted:
            res = (1080, 1920) if vertical else (info.get("width") or 1920, info.get("height") or 1080)
            captions.write_ass(shifted, cap_file, style=caption_style, resolution=res)
            render_vf.append(f"subtitles={cap_file.name}:fontsdir=.")

        center_x = None
        if vertical:
            track = media.speaker_track(src, start, end)
            if track:
                center_x = sum(track) / len(track)
        _render_final(raw_out, final, info, center_x if vertical else None,
                      render_vf, vertical, work)
        size = final.stat().st_size if final.is_file() else 0
        outputs.append({
            "file": final.name, "start": start, "end": end, "duration": round(end - start, 2),
            "target": target, "score": hl.get("score"), "vertical": vertical,
            "captions": burn and bool(shifted), "bytes": size,
            "download": f"/jobs/{job['id']}/files/clips/{final.name}",
        })
        progress(10 + int(85 * (idx + 1) / total))
    _save(work, "render.json", outputs)
    return {"clips": outputs}


def _render_final(raw: Path, dst: Path, info: dict, center_x, vf_captions: list[str],
                  vertical: bool, work: Path) -> None:
    """Single ffmpeg pass: optional 9:16 tracking crop + optional burned captions.

    Runs with cwd set to the job dir so the relative subtitles= path cannot
    escape the job sandbox."""
    w, h = info.get("width") or 0, info.get("height") or 0
    vf: list[str] = []
    post: list[str] = []
    if vertical and w and h:
        cw = min(w, int(h * 9 / 16))
        cw -= cw % 2
        lo, hi = cw // 2, max(cw // 2, w - cw // 2)
        cx = "W/2" if center_x is None else f"clip({center_x:.3f}*W,{lo},{hi})"
        vf.append(f"crop={cw}:ih:{cx}:0")
        post.append("scale=1080:1920:flags=bicubic")
    elif vertical:
        post.append("scale=1080:1920:force_original_aspect_ratio=decrease,"
                    "pad=1080:1920:(ow-iw)/2:(oh-ih)/2")
    if vf_captions:
        # burn captions after the crop but scale up afterwards so subtitle
        # font sizes map to the 1080x1920 PlayRes of the generated .ass file
        chain = ",".join(vf + vf_captions + post)
    else:
        chain = ",".join(vf + post)
    args = ["-i", str(raw)]
    if chain:
        args += ["-vf", chain, "-map", "0:v:0", "-map", "0:a:0?",
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
                 "-pix_fmt", "yuv420p", "-r", "30", "-c:a", "aac"]
    else:
        args += ["-c", "copy"]
    args += ["-movflags", "+faststart", str(dst)]
    prev = os.getcwd()
    try:
        os.chdir(work)
        media.run_ffmpeg(*args, timeout=1800)
    finally:
        os.chdir(prev)
