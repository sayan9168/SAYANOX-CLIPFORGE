from social import caption, hashtags


def test_hashtags_from_english_text():
    tags = hashtags("Here's why nobody tells you the secret about scoring", "shorts")
    joined = " ".join(tags).lower()
    assert "#secret" in joined or "#scoring" in joined or "#nobody" in joined
    assert "#shorts" in joined


def test_caption_pack_is_english_and_copyable():
    pack = caption(
        "The secret nobody tells you",
        "Here's why this scoring trick actually works on short clips.",
        platform="tiktok",
    )
    assert pack["language"] == "en"
    assert "secret" in pack["caption"].lower()
    assert pack["hashtag_line"].startswith("#")
    assert "#fyp" in pack["post"]
    assert "\n\n" in pack["post"]
