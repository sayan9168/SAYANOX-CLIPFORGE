from social import caption, hashtags, platform_packs


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
    assert pack["platform"] == "tiktok"
    assert "secret" in pack["caption"].lower()
    assert "#fyp" in pack["post"]
    assert "stitch" in pack["post"].lower() or "fyp" in pack["post"].lower()


def test_three_platform_packs():
    packs = platform_packs("Stop scrolling", "Here is why this matters for creators.")
    assert set(packs) == {"youtube", "instagram", "tiktok"}
    assert "#youtube" in packs["youtube"]["post"].lower()
    assert "#instagram" in packs["instagram"]["post"].lower() or "#reels" in packs["instagram"]["post"].lower()
    assert "#tiktok" in packs["tiktok"]["post"].lower() or "#fyp" in packs["tiktok"]["post"].lower()
    assert "subscribe" in packs["youtube"]["post"].lower()
