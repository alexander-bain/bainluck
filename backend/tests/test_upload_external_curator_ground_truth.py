"""Tests for admin API curator ground-truth uploader."""

from scripts.upload_external_curator_ground_truth import (
    build_import_payload,
    load_upload_rows,
)


def test_build_import_payload_wraps_rows():
    rows = [{"name": "France to win the 2026 World Cup", "review_status": "accepted"}]

    assert build_import_payload(rows) == {"rows": rows}


def test_load_upload_rows_applies_review_gate(tmp_path):
    source = tmp_path / "accepted.jsonl"
    source.write_text(
        "\n".join(
            [
                '{"source":"Instagram @kalshi","category":"sports","name":"France to win the 2026 World Cup","review_status":"accepted"}',
                '{"source":"Instagram @kalshi","category":"sports","name":"Pending row","review_status":"pending"}',
            ]
        )
    )

    rows = load_upload_rows(source)

    assert len(rows) == 1
    assert rows[0]["name"] == "France to win the 2026 World Cup"
    assert rows[0]["review_status"] == "accepted"
