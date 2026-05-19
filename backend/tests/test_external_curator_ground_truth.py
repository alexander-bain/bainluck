"""Tests for external-curator ground truth parsing."""

from datetime import datetime, timezone
import os

import pytest

from app.utils.external_curator_ground_truth import (
    load_external_curator_ground_truth_from_csv_text,
    load_external_curator_ground_truth_from_json_text,
    load_external_curator_ground_truth_from_jsonl_text,
    load_external_curator_ground_truth_from_text,
    load_external_curator_ground_truth_report_from_env,
    normalize_external_curator_ground_truth_rows,
)


def test_csv_parser_normalizes_shape_and_tolerates_missing_optional_fields():
    items = load_external_curator_ground_truth_from_csv_text(
        "\n".join(
            [
                "Source,Market Name,Category,Leader Probability,Hook,URL,Published At",
                (
                    "Public List, Will Fed cut rates in June? ,economics,55%,"
                    " Fed story ,https://example.com/story?b=2&a=1,2026-05-18"
                ),
                "Public List,Will another market matter?,,,,,",
            ]
        )
    )

    assert items == [
        {
            "source": "Public List",
            "category": "economics",
            "name": "Will Fed cut rates in June?",
            "probability": "55%",
            "hook": "Fed story",
            "url": "https://example.com/story?a=1&b=2",
            "published_at": "2026-05-18",
            "platform": "",
            "handle": "",
            "engagement": "",
            "evidence": "",
            "confidence": "",
            "extraction_notes": "",
            "review_status": "",
        },
        {
            "source": "Public List",
            "category": "?",
            "name": "Will another market matter?",
            "probability": "",
            "hook": "",
            "url": "",
            "published_at": "",
            "platform": "",
            "handle": "",
            "engagement": "",
            "evidence": "",
            "confidence": "",
            "extraction_notes": "",
            "review_status": "",
        },
    ]


def test_json_parser_accepts_items_wrapper_and_aliases():
    items = load_external_curator_ground_truth_from_json_text("""
        {
          "items": [
            {
              "curator": "News Curator",
              "question": "Will AI model exports be restricted?",
              "topic": "tech",
              "chance": 0.42,
              "summary": "Policy story",
              "link": "HTTPS://Example.ORG/policy#ignored",
              "platform": "x",
              "handle": "@markets",
              "engagement_count": "1200"
            }
          ]
        }
        """)

    assert items == [
        {
            "source": "News Curator",
            "category": "tech",
            "name": "Will AI model exports be restricted?",
            "probability": "0.42",
            "hook": "Policy story",
            "url": "https://example.org/policy",
            "published_at": "",
            "platform": "x",
            "handle": "@markets",
            "engagement": "1200",
            "evidence": "",
            "confidence": "",
            "extraction_notes": "",
            "review_status": "",
        }
    ]


def test_jsonl_parser_skips_blank_lines_and_defaults_missing_source():
    items = load_external_curator_ground_truth_from_jsonl_text(
        '\n{"title": "Will the hurricane make landfall?", "category": "weather"}\n'
    )

    assert items == [
        {
            "source": "external_curator",
            "category": "weather",
            "name": "Will the hurricane make landfall?",
            "probability": "",
            "hook": "",
            "url": "",
            "published_at": "",
            "platform": "",
            "handle": "",
            "engagement": "",
            "evidence": "",
            "confidence": "",
            "extraction_notes": "",
            "review_status": "",
        }
    ]


def test_parser_preserves_social_extraction_review_fields():
    items = normalize_external_curator_ground_truth_rows(
        [
            {
                "source": "Instagram @kalshi",
                "name": "Will Fed cut rates in June?",
                "evidence": "Graphic text says Fed cut rates",
                "confidence": "high",
                "extraction_notes": "Caption and image agree",
            }
        ]
    )

    assert items[0]["evidence"] == "Graphic text says Fed cut rates"
    assert items[0]["confidence"] == "high"
    assert items[0]["extraction_notes"] == "Caption and image agree"
    assert items[0]["review_status"] == ""


def test_pending_or_rejected_review_rows_are_skipped():
    items = normalize_external_curator_ground_truth_rows(
        [
            {
                "source": "Instagram @kalshi",
                "name": "Pending market",
                "review_status": "pending",
            },
            {
                "source": "Instagram @kalshi",
                "name": "Rejected market",
                "decision": "rejected",
            },
            {
                "source": "Instagram @kalshi",
                "name": "Accepted market",
                "review_status": "accepted",
            },
        ]
    )

    assert [item["name"] for item in items] == ["Accepted market"]
    assert items[0]["review_status"] == "accepted"


def test_dedupes_by_normalized_name_and_source_or_url():
    items = normalize_external_curator_ground_truth_rows(
        [
            {
                "source": "Curator",
                "name": "  Will Fed cut rates in June? ",
                "url": "https://example.com/fed",
            },
            {
                "source": "Different Curator",
                "name": "WILL FED CUT RATES IN JUNE?",
                "url": "https://example.com/fed",
            },
            {
                "source": "Curator",
                "name": "Will Fed cut rates in June?",
            },
            {
                "source": "Curator",
                "name": "will fed cut rates in june",
            },
        ]
    )

    assert [item["source"] for item in items] == [
        "Curator",
        "Curator",
    ]


def test_rejects_non_public_or_non_string_urls_without_rejecting_row():
    items = normalize_external_curator_ground_truth_rows(
        [
            {"name": "Invalid relative URL", "url": "/markets/123"},
            {"name": "Loopback URL", "url": "https://127.0.0.1/market"},
            {"name": "Private IP URL", "url": "https://10.0.0.1/market"},
            {"name": "Localhost URL", "url": "https://localhost/market"},
            {"name": "Credential URL", "url": "https://user@example.com/market"},
            {"name": "Non-string URL", "url": 123},
            {"name": "Public URL", "url": "https://markets.example.com/market"},
        ]
    )

    assert [item["url"] for item in items] == [
        "",
        "",
        "",
        "",
        "",
        "",
        "https://markets.example.com/market",
    ]


def test_rows_without_name_are_skipped():
    items = normalize_external_curator_ground_truth_rows(
        [
            {"source": "Curator", "name": ""},
            {"source": "Curator", "hook": "No name"},
            {"source": "Curator", "name": "Valid item"},
        ]
    )

    assert [item["name"] for item in items] == ["Valid item"]


def test_unsupported_format_raises_value_error():
    with pytest.raises(ValueError, match="input_format"):
        load_external_curator_ground_truth_from_text("", input_format="xml")


def test_env_report_loads_multiple_local_exports(monkeypatch, tmp_path):
    csv_path = tmp_path / "curators.csv"
    csv_path.write_text(
        "\n".join(
            [
                "source,name,category,url",
                "Curator A,Will OpenAI release GPT-6?,tech,https://example.com/a",
            ]
        )
    )
    jsonl_path = tmp_path / "curators.jsonl"
    jsonl_path.write_text(
        '{"source":"Curator B","name":"Will Fed cut rates?","category":"economics"}\n'
    )
    monkeypatch.setenv(
        "EXTERNAL_CURATOR_GROUND_TRUTH_PATHS",
        f"{csv_path}{os.pathsep}{jsonl_path}",
    )

    report = load_external_curator_ground_truth_report_from_env()

    assert report["metadata"]["configured"] is True
    assert report["metadata"]["loaded_count"] == 2
    assert report["metadata"]["error"] is None
    assert [item["source"] for item in report["items"]] == ["Curator A", "Curator B"]


def test_env_report_includes_source_counts_and_freshness(monkeypatch, tmp_path):
    csv_path = tmp_path / "curators.csv"
    csv_path.write_text(
        "\n".join(
            [
                "source,name,category,published_at,platform",
                "Curator A,Will OpenAI release GPT-6?,tech,2026-05-17,x",
                "Curator A,Will Fed cut rates?,economics,2026-05-16,newsletter",
                "Curator B,Will a hurricane make landfall?,weather,2026-05-10,x",
            ]
        )
    )
    monkeypatch.setenv("EXTERNAL_CURATOR_GROUND_TRUTH_PATHS", str(csv_path))

    report = load_external_curator_ground_truth_report_from_env(
        now=datetime(2026, 5, 18, tzinfo=timezone.utc)
    )

    assert report["metadata"]["latest_date"] == "2026-05-17"
    assert report["metadata"]["stale"] is False
    assert report["metadata"]["stale_after_days"] == 7
    assert report["metadata"]["source_counts"] == {"Curator A": 2, "Curator B": 1}
    assert report["metadata"]["source_health"] == [
        {
            "source": "Curator A",
            "count": 2,
            "latest_date": "2026-05-17",
            "stale": False,
            "platform_counts": {"newsletter": 1, "x": 1},
        },
        {
            "source": "Curator B",
            "count": 1,
            "latest_date": "2026-05-10",
            "stale": True,
            "platform_counts": {"x": 1},
        },
    ]


def test_env_report_is_inert_without_paths(monkeypatch):
    monkeypatch.delenv("EXTERNAL_CURATOR_GROUND_TRUTH_PATHS", raising=False)

    report = load_external_curator_ground_truth_report_from_env()

    assert report["items"] == []
    assert report["metadata"]["configured"] is False
    assert report["metadata"]["latest_date"] is None
