"""Tests for the daily social ground-truth operator wrapper."""

import json

import httpx

from scripts.run_daily_social_ground_truth import (
    build_default_paths,
    build_next_commands,
    download_capture_urls,
    main,
    resolve_output_dir,
)


def test_default_output_dir_uses_run_date():
    path = resolve_output_dir(None, run_date="20260520")

    assert str(path).endswith("/tmp/bainluck_social_ground_truth/20260520")


def test_build_next_commands_includes_review_and_upload(tmp_path):
    paths = build_default_paths(tmp_path)

    commands = build_next_commands(paths, accepted_count=2, pending_count=1)

    assert "review_social_ground_truth.py" in commands["review"]
    assert str(paths["review"]) in commands["review"]
    assert "upload_external_curator_ground_truth.py" in commands["upload"]
    assert str(paths["accepted"]) in commands["upload"]


def test_download_capture_urls_writes_response_content(tmp_path, monkeypatch):
    def fake_get(url, timeout):
        return httpx.Response(
            200,
            content=b"handle,caption\nkalshi,Will Fed cut rates?\n",
            headers={"content-type": "text/csv"},
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr("scripts.run_daily_social_ground_truth.httpx.get", fake_get)

    paths = download_capture_urls(["https://example.com/export"], output_dir=tmp_path)

    assert len(paths) == 1
    assert paths[0].endswith(".csv")
    assert (
        "Will Fed cut rates?" in (tmp_path / "captures" / "capture_1.csv").read_text()
    )


def test_main_dry_operator_run_writes_manifest_prompt_and_summary(tmp_path, capsys):
    source = tmp_path / "captures.jsonl"
    source.write_text(
        json.dumps(
            {
                "account": "kalshi",
                "caption": "Traders give France the best odds to win the World Cup.",
                "approved": "yes",
            }
        )
        + "\n"
    )
    output_dir = tmp_path / "daily"

    result = main(
        [
            str(source),
            "--date",
            "20260520",
            "--output-dir",
            str(output_dir),
            "--summary-json",
        ]
    )

    assert result == 0
    assert (output_dir / "social.posts.jsonl").exists()
    assert (output_dir / "social.prompt.md").exists()
    summary = json.loads((output_dir / "social.summary.json").read_text())
    assert summary["run_date"] == "20260520"
    assert summary["manifest"]["rows"] == 1
    printed = json.loads(capsys.readouterr().out)
    assert printed["paths"]["manifest"] == str(output_dir / "social.posts.jsonl")
