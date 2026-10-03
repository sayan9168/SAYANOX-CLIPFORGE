import pytest

from captions import segments_to_ass, segments_to_srt, segments_to_vtt, trim_segments
from pipeline import _transcript_from_srt


def test_srt_vtt_timestamps_roll_over_and_preserve_unicode():
    segments = [{"start": 59.9996, "end": 61.5, "text": "বাংলা এবং हिंदी"}]
    srt = segments_to_srt(segments)
    assert "00:01:00,000 --> 00:01:01,500" in srt
    assert "বাংলা এবং हिंदी" in srt
    vtt = segments_to_vtt(segments)
    assert vtt.startswith("WEBVTT\n\n")
    assert "00:01:00.000 --> 00:01:01.500" in vtt


def test_trimmed_subtitles_cannot_extend_past_actual_clip():
    shifted = trim_segments([{"start": 1, "end": 8, "text": "Hello"}], 2.25, 4.6)
    assert shifted[0]["start"] == 0
    assert shifted[0]["end"] == pytest.approx(2.35)
    assert segments_to_srt(shifted).count("-->") == 1


def test_invalid_subtitle_segments_are_skipped():
    segments = [{"start": float("nan"), "end": 2, "text": "bad"}, {"start": 3, "end": 1, "text": "bad"}, {"start": 0, "end": 1, "text": "valid"}]
    assert "bad" not in segments_to_srt(segments)
    assert "valid" in segments_to_srt(segments)


def test_ass_override_text_is_escaped():
    ass = segments_to_ass([{"start": 0, "end": 2, "text": r"{\pos(1,1)} test"}], hook_text=r"{\b1} Hook")
    dialogues = [line for line in ass.splitlines() if line.startswith("Dialogue:")]
    assert all("{" not in line and "\\pos" not in line and "\\b" not in line for line in dialogues)


def test_srt_sidecars_take_real_cues_and_parse_crlf_bom(tmp_path):
    (tmp_path / "captions.srt").write_text("\ufeff1\r\n00:00:01,5 --> 00:00:04,250\r\n<b>My real captions</b>\r\n")
    transcript = _transcript_from_srt(tmp_path)
    assert transcript["engine"] == "srt-sidecar"
    assert transcript["segments"] == [{"start": 1.5, "end": 4.25, "text": "My real captions"}]


def test_invalid_srt_is_a_clear_error_not_placeholder_captions(tmp_path):
    (tmp_path / "captions.srt").write_text("invalid content")
    with pytest.raises(ValueError, match="no valid subtitle cues"):
        _transcript_from_srt(tmp_path)
