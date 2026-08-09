"""UX-P028 — the provider-independent social ground-truth extraction contract.

Replaces `test_extract_social_ground_truth_with_manus.py`. The vendor is gone; the
contract it used to carry (manifest parsing, prompt shape, output parsing) is now
pure and lives in `app.utils.social_ground_truth_extraction`, which is what makes
these assertions possible without a network.
"""

import json

import pytest

from app.utils.social_ground_truth_extraction import (
    EXTRACTOR_VERSION,
    REVIEW_FIELDS,
    TARGET_HANDLES,
    ExtractionUnavailable,
    build_extraction_prompt,
    parse_extraction_output,
    parse_post_manifest,
)

CAPTION = "Traders give France the best odds to win the World Cup at 18.1%"

GOOD_ROW = {
    "source": "Instagram @kalshi",
    "category": "sports",
    "name": "France to win the 2026 World Cup",
    "probability": "18.1%",
    "hook": "France leads the World Cup field.",
    "url": "https://www.instagram.com/p/ABC/",
    "published_at": "2026-08-01",
    "platform": "instagram",
    "handle": "@kalshi",
    "engagement": "",
    "evidence": f"Caption: '{CAPTION}'",
    "confidence": "high",
    "extraction_notes": "Stated in caption.",
}


# ---------------------------------------------------------------- manifest ---


def test_manifest_accepts_csv_and_normalizes_aliases():
    csv_text = "account,link,text,date\nkalshi,https://x/p/1,Some caption,2026-08-01\n"
    rows = parse_post_manifest(csv_text, suffix=".csv")
    assert len(rows) == 1
    # bare handle gets the @, and alias column names map onto the canonical keys
    assert rows[0]["handle"] == "@kalshi"
    assert rows[0]["post_url"] == "https://x/p/1"
    assert rows[0]["caption"] == "Some caption"
    assert rows[0]["published_at"] == "2026-08-01"


def test_manifest_accepts_jsonl_and_json_object_wrapper():
    jsonl = json.dumps({"handle": "@polymarket", "url": "https://x/p/2"}) + "\n"
    assert parse_post_manifest(jsonl, suffix=".jsonl")[0]["handle"] == "@polymarket"

    wrapped = json.dumps({"posts": [{"handle": "@kalshisports"}]})
    assert parse_post_manifest(wrapped, suffix=".json")[0]["handle"] == "@kalshisports"


def test_manifest_rejects_unknown_format():
    with pytest.raises(ValueError):
        parse_post_manifest("whatever", suffix=".xlsx")


# ------------------------------------------------------------------ prompt ---


def test_prompt_is_deterministic_for_the_same_manifest():
    """Replay idempotence starts here: same input, byte-identical prompt."""
    posts = parse_post_manifest(
        json.dumps({"posts": [{"handle": "@kalshi", "caption": CAPTION}]}), suffix=".json"
    )
    assert build_extraction_prompt(posts) == build_extraction_prompt(posts)


def test_prompt_names_the_target_handles_and_demands_jsonl():
    prompt = build_extraction_prompt([])
    for handle in TARGET_HANDLES:
        assert handle in prompt
    assert "JSONL" in prompt
    # The no-invention rule is load-bearing: these rows steer a live feed lane.
    assert "Do not invent probabilities" in prompt


# ------------------------------------------------------------------- parse ---


def test_parses_a_clean_jsonl_reply_into_review_rows():
    result = parse_extraction_output(json.dumps(GOOD_ROW))
    assert result["rejected"] == []
    assert len(result["rows"]) == 1
    row = result["rows"][0]
    assert row["name"] == "France to win the 2026 World Cup"
    assert set(REVIEW_FIELDS).issubset(row.keys())


def test_every_extracted_row_is_pending_never_auto_accepted():
    """Accepted rows reach a live Discover recall+rank lane — extraction may
    never promote its own output."""
    accepted_attempt = {**GOOD_ROW, "review_status": "accepted"}
    result = parse_extraction_output(json.dumps(accepted_attempt))
    assert result["rows"][0]["review_status"] == "pending"


def test_extractor_version_is_stamped_on_every_row():
    row = parse_extraction_output(json.dumps(GOOD_ROW))["rows"][0]
    assert EXTRACTOR_VERSION in row["extraction_notes"]
    # the model's own note survives alongside the provenance stamp
    assert "Stated in caption." in row["extraction_notes"]


def test_code_fenced_reply_is_still_parsed():
    fenced = f"```jsonl\n{json.dumps(GOOD_ROW)}\n```"
    assert len(parse_extraction_output(fenced)["rows"]) == 1


def test_malformed_lines_are_ISOLATED_not_silently_dropped():
    """A run that discards half the reply must not look like a thin harvest."""
    reply = "\n".join(
        [
            json.dumps(GOOD_ROW),
            "{not json at all",
            json.dumps(["a", "list", "not", "an", "object"]),
            json.dumps({**GOOD_ROW, "name": ""}),
        ]
    )
    result = parse_extraction_output(reply)

    assert len(result["rows"]) == 1
    assert len(result["rejected"]) == 3
    reasons = " ".join(r["reason"] for r in result["rejected"])
    assert "invalid json" in reasons
    assert "not a json object" in reasons
    assert "missing market name" in reasons
    # every reject carries its line number, so a human can go look at it
    assert all(r["line"].isdigit() for r in result["rejected"])


def test_empty_reply_is_empty_rows_not_a_crash():
    result = parse_extraction_output("")
    assert result["rows"] == []
    assert result["rejected"] == []


def test_parse_is_deterministic_across_repeated_runs():
    reply = json.dumps(GOOD_ROW)
    assert parse_extraction_output(reply) == parse_extraction_output(reply)


# ----------------------------------------------------------- fail closed ---


def test_missing_provider_raises_rather_than_returning_no_rows(monkeypatch):
    """The whole reason this queue exists: a dead producer must be loud.

    `ExtractionUnavailable` distinguishes "the provider is gone" from "the posts
    contained no markets" — collapsing those is how a rail reports success while
    producing nothing.
    """
    from scripts import extract_social_ground_truth as extractor
    from app.services import llm

    monkeypatch.setattr(llm, "_get_client", lambda: None)
    with pytest.raises(ExtractionUnavailable):
        extractor.extract_rows([{"handle": "@kalshi", "caption": CAPTION}])


def test_provider_reply_flows_through_the_pure_contract(monkeypatch):
    """The model call is a thin edge: whatever it returns is parsed by the same
    pure function the fixtures above pin."""
    from scripts import extract_social_ground_truth as extractor
    from app.services import llm

    class _Message:
        content = json.dumps(GOOD_ROW)

    class _Choice:
        message = _Message()

    class _Response:
        choices = [_Choice()]

    class _Completions:
        def create(self, **kwargs):
            # determinism is a property of the call, not a hope about the model
            assert kwargs["temperature"] == 0
            return _Response()

    class _Chat:
        completions = _Completions()

    class _Client:
        chat = _Chat()

    monkeypatch.setattr(llm, "_get_client", lambda: _Client())
    result = extractor.extract_rows([{"handle": "@kalshi", "caption": CAPTION}])
    assert len(result["rows"]) == 1
    assert result["rows"][0]["review_status"] == "pending"
    assert EXTRACTOR_VERSION in result["rows"][0]["extraction_notes"]
