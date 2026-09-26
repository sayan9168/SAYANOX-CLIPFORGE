from captions import CAPTION_STYLES, segments_to_ass


def test_ass_has_style_and_events():
    ass = segments_to_ass([{"start": 0.5, "end": 2.5, "text": "Hello world"}], style="karaoke")
    assert "[V4+ Styles]" in ass and "[Events]" in ass
    assert "Dialogue: 0,0:00:00.50,0:00:02.50,Cap" in ass


def test_long_lines_are_wrapped_and_braces_escaped():
    long = "word " * 40 + "{unsafe}"
    ass = segments_to_ass([{"start": 0, "end": 4, "text": long}])
    assert "(unsafe)" in ass
    dialogues = [l for l in ass.splitlines() if l.startswith("Dialogue")]
    assert len(dialogues) >= 2


def test_timestamp_format():
    from captions import _ts
    assert _ts(3661.5) == "1:01:01.50"


def test_phase2_indic_styles_exist():
    assert "bengali" in CAPTION_STYLES and "hindi" in CAPTION_STYLES
    ass = segments_to_ass(
        [{"start": 0, "end": 2, "text": "বাংলা টেক্সট"}], style="bengali"
    )
    assert "Noto Sans Bengali" in ass
    ass_hi = segments_to_ass(
        [{"start": 0, "end": 2, "text": "हिन्दी पाठ"}], style="hindi"
    )
    assert "Noto Sans Devanagari" in ass_hi
