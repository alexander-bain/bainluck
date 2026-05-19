"""Tests for Discover ground-truth debug helpers."""

from app.utils.feed_quality_debug import find_missing_ground_truth_items


def test_missing_ground_truth_preserves_public_curator_provenance():
    missing = find_missing_ground_truth_items(
        [],
        [
            {
                "source": "Curator",
                "category": "tech",
                "name": "Will OpenAI release GPT-6?",
                "probability": "42%",
                "url": "https://example.com/gpt6",
                "published_at": "2026-05-18",
                "platform": "x",
                "handle": "@markets",
                "engagement": "1200",
            }
        ],
    )

    assert missing[0]["url"] == "https://example.com/gpt6"
    assert missing[0]["published_at"] == "2026-05-18"
    assert missing[0]["platform"] == "x"
    assert missing[0]["handle"] == "@markets"
    assert missing[0]["engagement"] == "1200"
