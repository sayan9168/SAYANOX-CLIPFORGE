from social import caption, hashtags, language_packs, platform_packs


def test_hashtags_from_english_text():
    tags = hashtags("Here's why nobody tells you the secret about scoring", "youtube")
    joined = " ".join(tags).lower()
    assert "#shorts" in joined and "#youtube" in joined


def test_caption_pack_is_english_and_copyable():
    pack = caption(
        "The secret nobody tells you",
        "Here's why this scoring trick actually works on short clips.",
        platform="tiktok",
    )
    assert pack["language"] == "en"
    assert "#fyp" in pack["post"]


def test_three_platform_packs():
    packs = platform_packs("Stop scrolling", "Here is why this matters for creators.")
    assert set(packs) == {"youtube", "instagram", "tiktok"}
    assert "#youtube" in packs["youtube"]["post"].lower()


def test_bn_hi_language_packs():
    packs = language_packs("Stop scrolling", "Creators need this clip.")
    assert set(packs) == {"en", "bn", "hi"}
    assert "#bangla" in packs["bn"]["youtube"]["post"].lower()
    assert "#hindi" in packs["hi"]["tiktok"]["post"].lower()
    assert "সাবসক্রাইব" in packs["bn"]["youtube"]["post"]
    assert "सबस्क्राइब" in packs["hi"]["youtube"]["post"]
