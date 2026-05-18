"""Tests for external-curator ground truth parsing."""

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
        },
        {
            "source": "Public List",
            "category": "?",
            "name": "Will another market matter?",
            "probability": "",
            "hook": "",
            "url": "",
            "published_at": "",
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
              "link": "HTTPS://Example.ORG/policy#ignored"
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
        }
    ]


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


def test_env_report_is_inert_without_paths(monkeypatch):
    monkeypatch.delenv("EXTERNAL_CURATOR_GROUND_TRUTH_PATHS", raising=False)

    report = load_external_curator_ground_truth_report_from_env()

    assert report["items"] == []
    assert report["metadata"]["configured"] is False
