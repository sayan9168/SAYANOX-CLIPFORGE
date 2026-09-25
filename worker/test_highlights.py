from highlights import Segment, find_highlights, hook_strength, build_segments


def test_ranks_non_overlapping_segments():
    xs = [Segment(0, 20, "This is a strong complete point!", .9, .8, .8, .7),
          Segment(10, 30, "Overlapping weaker point", .2, .2, .2, .2),
          Segment(40, 65, "Another useful complete explanation?", .8, .7, .7, .8)]
    out = find_highlights(xs, 15, 60, 3)
    assert out
    assert all(15 <= x["end"] - x["start"] <= 90 for x in out)


def test_duplicate_overlapping_moments_are_removed():
    xs = [Segment(0, 18, "The secret nobody tells you about scoring.", .9, .9, .9, .9),
          Segment(2, 20, "The secret nobody tells you about scoring.", .9, .9, .9, .9),
          Segment(60, 80, "A completely different closing thought.", .8, .8, .8, .8)]
    out = find_highlights(xs, 15, 90, 5)
    starts = [(x["start"], x["end"]) for x in out]
    for i, (s1, e1) in enumerate(starts):
        for s2, e2 in starts[i + 1:]:
            assert e1 <= s2 or e2 <= s1, "chosen highlights must not overlap"


def test_hook_detection_scores_strong_openers_higher():
    assert hook_strength("Here's why nobody tells you the secret") > \
        hook_strength("and then we went and had lunch together")


def test_signals_are_reported():
    xs = [Segment(0, 20, "Stop scrolling — here's how this works!", .9, .8, .7, .6)]
    out = find_highlights(xs, 15, 60, 1)
    assert out and set(out[0]["signals"]) == {"hook", "speech", "emotion", "audio", "visual"}


def test_build_segments_fuses_audio_and_scene_signals():
    transcript = {"segments": [{"start": 0, "end": 10, "text": "Loud exciting part."},
                               {"start": 10, "end": 20, "text": "Quiet boring part."}]}
    energy = [-10.0] * 20 + [-80.0] * 20           # loud then silent
    scenes = [3.0, 4.0, 5.0]                        # cuts only inside first segment
    segs = build_segments(transcript, energy, scenes)
    assert segs[0].audio_score > segs[1].audio_score
    assert segs[0].visual_score > segs[1].visual_score
    assert segs[1].speech_score < 0.2               # silence detected
