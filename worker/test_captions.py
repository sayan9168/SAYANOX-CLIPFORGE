from captions import segments_to_ass, CAPTION_STYLES


def test_known_styles_exist():
    for name in ("default", "karaoke", "clean", "bold", "bengali", "hindi"):
        assert name in CAPTION_STYLES


def test_hook_dialogue_is_first_two_seconds():
    ass = segments_to_ass(
        [{"start": 0.5, "end": 3.0, "text": "Hello world this is a test."}],
        hook_text="Stop scrolling",
        hook_seconds=2.0,
    )
    assert "Style: Hook" in ass
    assert "Stop scrolling" in ass
    assert "0:00:00.00" in ass
