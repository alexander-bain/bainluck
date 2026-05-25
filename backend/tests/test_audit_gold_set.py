"""Tests for the gold-set label comparison in audit_feed_quality.py."""

from __future__ import annotations

import sys
from pathlib import Path
from io import StringIO

# Ensure scripts directory is importable
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.audit_feed_quality import _load_gold_set_labels, _print_gold_set_report


def test_load_gold_set_labels_requires_admin_token(monkeypatch):
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    result = _load_gold_set_labels("https://api.bainluck.com/api/feed")
    assert result["loaded"] is False
    assert "ADMIN_TOKEN" in result["reason"]


def test_print_gold_set_report_handles_empty_feed(capsys):
    gold_set_report = {
        "loaded": True,
        "rows": [
            {
                "market_id": 100,
                "market_name": "Will X happen?",
                "label": "love",
                "category": "politics",
            },
            {
                "market_id": 200,
                "market_name": "Boring market",
                "label": "bad",
                "category": "economics",
            },
        ],
        "total": 2,
        "split_counts": {"train": 2},
        "label_counts": {"love": 1, "bad": 1},
    }
    _print_gold_set_report(gold_set_report, [])
    out = capsys.readouterr().out
    assert "GOLD-SET LABEL COMPARISON" in out
    assert "labeled rows:" in out
    assert "gold-in-feed:" in out


def test_print_gold_set_report_detects_boring_intrusion(capsys):
    gold_set_report = {
        "loaded": True,
        "rows": [
            {
                "market_id": 100,
                "market_name": "Cool politics market",
                "label": "love",
                "category": "politics",
            },
            {
                "market_id": 200,
                "market_name": "Boring ladder market",
                "label": "bad",
                "category": "economics",
            },
        ],
        "total": 2,
        "split_counts": {"train": 1, "dev": 1},
        "label_counts": {"love": 1, "bad": 1},
    }
    # Feed has both markets in top 20
    classified_feed = [
        {
            "id": 100,
            "rank": 1,
            "name": "Cool politics market",
            "category": "politics",
        },
        {
            "id": 200,
            "rank": 2,
            "name": "Boring ladder market",
            "category": "economics",
        },
    ]
    _print_gold_set_report(gold_set_report, classified_feed)
    out = capsys.readouterr().out
    assert "boring-intrusion@20:" in out
    assert "1/20" in out
    assert "Boring ladder market" in out


def test_print_gold_set_report_computes_love_recall(capsys):
    gold_set_report = {
        "loaded": True,
        "rows": [
            {
                "market_id": 100,
                "market_name": "Great market",
                "label": "love",
                "category": "politics",
            },
            {
                "market_id": 200,
                "market_name": "Also great",
                "label": "love",
                "category": "tech",
            },
        ],
        "total": 2,
        "split_counts": {"train": 2},
        "label_counts": {"love": 2},
    }
    # Only market 100 is in the feed
    classified_feed = [
        {
            "id": 100,
            "rank": 1,
            "name": "Great market",
            "category": "politics",
        },
    ]
    _print_gold_set_report(gold_set_report, classified_feed)
    out = capsys.readouterr().out
    assert "love-recall@feed:" in out
    assert "1/2" in out
    assert "50%" in out


def test_print_gold_set_report_shows_missing_loved_markets(capsys):
    gold_set_report = {
        "loaded": True,
        "rows": [
            {
                "market_id": 999,
                "market_name": "Missing loved market",
                "label": "love",
                "category": "entertainment",
            },
        ],
        "total": 1,
        "split_counts": {"train": 1},
        "label_counts": {"love": 1},
    }
    _print_gold_set_report(gold_set_report, [])
    out = capsys.readouterr().out
    assert "loved markets missing from feed:" in out
    assert "Missing loved market" in out
