"""Tests for the Manus social ground-truth extraction helper."""

from scripts.extract_social_ground_truth_with_manus import (
    build_prompt,
    load_post_manifest,
    normalize_review_rows,
    parse_extraction_report,
)


def test_load_post_manifest_normalizes_instagram_fields(tmp_path):
    manifest = tmp_path / "posts.csv"
    manifest.write_text(
        "\n".join(
            [
                "account,post_url,date,caption,image_text,media_url,likes",
                "@kalshi,https://instagram.com/p/abc,2026-05-19,Caption text,Market text,https://cdn.example/image.jpg,1200",
            ]
        )
    )

    assert load_post_manifest(manifest) == [
        {
            "handle": "@kalshi",
            "post_url": "https://instagram.com/p/abc",
            "published_at": "2026-05-19",
            "caption": "Caption text",
            "ocr_text": "Market text",
            "image_url": "https://cdn.example/image.jpg",
            "engagement": "1200",
        }
    ]


def test_build_prompt_names_target_accounts_and_schema():
    prompt = build_prompt(
        [
            {
                "handle": "@polymarket",
                "post_url": "https://instagram.com/p/pm",
                "published_at": "2026-05-19",
                "caption": "A market about the Fed",
                "ocr_text": "Will Fed cut rates?",
                "image_url": "",
                "engagement": "",
            }
        ]
    )

    assert "@kalshi" in prompt
    assert "@polymarketsports" in prompt
    assert "Output ONLY JSONL" in prompt
    assert "Will Fed cut rates?" in prompt


def test_parse_extraction_report_keeps_review_evidence_fields():
    rows = parse_extraction_report(
        """
        ```jsonl
        {"source":"Instagram @kalshi","category":"economics","name":"Will Fed cut rates in June?","hook":"Fed caption","url":"https://instagram.com/p/abc","published_at":"2026-05-19","platform":"instagram","handle":"@kalshi","engagement":"1200","evidence":"image says Fed cut","confidence":"high","extraction_notes":"clear"}
        ```
        """
    )

    assert rows == [
        {
            "source": "Instagram @kalshi",
            "category": "economics",
            "name": "Will Fed cut rates in June?",
            "probability": "",
            "hook": "Fed caption",
            "url": "https://instagram.com/p/abc",
            "published_at": "2026-05-19",
            "platform": "instagram",
            "handle": "@kalshi",
            "engagement": "1200",
            "evidence": "image says Fed cut",
            "confidence": "high",
            "extraction_notes": "clear",
        }
    ]


def test_normalize_review_rows_defaults_platform_and_sanitizes_url():
    rows = normalize_review_rows(
        [
            {
                "source": "Instagram @kalshisports",
                "category": "sports",
                "name": "Will Knicks win the series?",
                "url": "https://instagram.com/p/series?b=2&a=1#frag",
                "evidence": "graphic names Knicks",
                "confidence": "medium",
            }
        ]
    )

    assert rows[0]["platform"] == "instagram"
    assert rows[0]["url"] == "https://instagram.com/p/series?a=1&b=2"
    assert rows[0]["evidence"] == "graphic names Knicks"
    assert rows[0]["confidence"] == "medium"
