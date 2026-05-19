"""Tests for the approved social capture manifest builder."""

import csv
import json
from io import StringIO

from scripts.build_social_post_manifest import (
    build_manifest_rows,
    build_summary,
    load_capture_rows,
    normalize_capture_row,
    write_manifest,
)


def test_normalize_capture_row_maps_common_instagram_export_fields():
    row = normalize_capture_row(
        {
            "account": "KalshiSports",
            "permalink": "https://instagram.com/p/abc",
            "date": "2026-05-19",
            "text": "Caption",
            "image_text": "Will Knicks win?",
            "media_url": "https://cdn.example/abc.jpg",
            "likes": 1234,
        }
    )

    assert row == {
        "handle": "@kalshisports",
        "post_url": "https://instagram.com/p/abc",
        "published_at": "2026-05-19",
        "caption": "Caption",
        "ocr_text": "Will Knicks win?",
        "image_url": "https://cdn.example/abc.jpg",
        "engagement": "1234",
        "capture_notes": "",
    }


def test_build_manifest_rows_filters_unapproved_non_target_and_empty_evidence():
    rows = build_manifest_rows(
        [
            {
                "handle": "@kalshi",
                "caption": "A Fed market",
                "approved": "yes",
            },
            {
                "handle": "@kalshi",
                "caption": "Rejected",
                "approved": "no",
            },
            {
                "handle": "@random",
                "caption": "Wrong account",
                "approved": "yes",
            },
            {
                "handle": "@polymarket",
                "approved": "yes",
            },
        ]
    )

    assert rows == [
        {
            "handle": "@kalshi",
            "post_url": "",
            "published_at": "",
            "caption": "A Fed market",
            "ocr_text": "",
            "image_url": "",
            "engagement": "",
            "capture_notes": "",
        }
    ]


def test_build_manifest_rows_dedupes_same_capture():
    rows = build_manifest_rows(
        [
            {"handle": "@polymarket", "url": "https://instagram.com/p/pm", "caption": "Fed"},
            {"handle": "@polymarket", "url": "https://instagram.com/p/pm", "caption": "Fed"},
        ]
    )

    assert len(rows) == 1


def test_load_capture_rows_supports_text_files_with_default_handle(tmp_path):
    source = tmp_path / "captions.txt"
    source.write_text("First post caption\n\nSecond post caption\n")

    rows = load_capture_rows(
        [source],
        text_files=True,
        default_handle="@kalshifacts",
    )

    assert rows == [
        {
            "handle": "@kalshifacts",
            "caption": "First post caption",
            "capture_notes": "text_file=captions.txt; platform=instagram",
        },
        {
            "handle": "@kalshifacts",
            "caption": "Second post caption",
            "capture_notes": "text_file=captions.txt; platform=instagram",
        },
    ]


def test_write_manifest_jsonl_and_csv():
    rows = [
        {
            "handle": "@kalshi",
            "post_url": "https://instagram.com/p/abc",
            "published_at": "2026-05-19",
            "caption": "Caption",
            "ocr_text": "",
            "image_url": "",
            "engagement": "",
            "capture_notes": "manual",
        }
    ]

    jsonl_output = StringIO()
    write_manifest(rows, jsonl_output, output_format="jsonl")
    assert json.loads(jsonl_output.getvalue())["handle"] == "@kalshi"

    csv_output = StringIO()
    write_manifest(rows, csv_output, output_format="csv")
    parsed = list(csv.DictReader(StringIO(csv_output.getvalue())))
    assert parsed[0]["capture_notes"] == "manual"


def test_build_summary_counts_evidence_fields():
    assert build_summary(
        [
            {"handle": "@kalshi", "caption": "Caption", "ocr_text": "", "image_url": ""},
            {"handle": "@kalshi", "caption": "", "ocr_text": "OCR", "image_url": "https://cdn.example/a.jpg"},
        ]
    ) == {
        "rows": 2,
        "handles": {"@kalshi": 2},
        "with_caption": 1,
        "with_ocr_text": 1,
        "with_image_url": 1,
        "target_handles": [
            "@kalshi",
            "@kalshisports",
            "@kalshifacts",
            "@polymarket",
            "@polymarketsports",
        ],
    }
