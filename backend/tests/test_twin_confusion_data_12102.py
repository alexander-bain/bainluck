"""#12102 S0b: reconcile the full committed confusion matrix with S0a.

Moved from the equivalent frontend guard so the installed reviewer can execute
it with its existing pytest permission. No workflow setting or data is changed.
"""

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
EXAM = json.loads(
    (ROOT / "frontend/lib/evals/data/twin-exam-2026-11-05.json").read_bytes()
)
CONFUSION = json.loads(
    (ROOT / "frontend/lib/evals/data/twin-confusion-2026-11-05.json").read_bytes()
)
DENOMINATORS = {
    "twin": 25,
    "same_number": 12,
    "implies": 3,
    "path_step": 2,
    "by_when": 2,
    "same_decision": 1,
    "grouping": 1,
    "related": 7,
    "unrelated": 4,
    "uncheckable": 3,
}


def test_confusion_uses_the_same_frozen_run_score_and_receipt():
    for key in ["run_id", "recorded_at_pt", "receipt_url"]:
        assert CONFUSION[key] == EXAM[key]
    assert CONFUSION["score_sha256"] == EXAM["hashes"]["score"]


@pytest.mark.parametrize("pass_id", ["1", "2", "3"])
def test_confusion_retains_each_heldout_denominator(pass_id):
    section = CONFUSION["per_pass"][pass_id]["test"]
    assert section["n"] == 60
    assert set(section["rows"]) == set(DENOMINATORS)
    for relation, n in DENOMINATORS.items():
        row = section["rows"][relation]
        assert row["n"] == n
        assert sum(row["counts"].values()) == n


@pytest.mark.parametrize("pass_id", ["1", "2", "3"])
def test_confusion_reconciles_every_row_column_and_diagonal(pass_id):
    for split in ["test", "dev"]:
        section = CONFUSION["per_pass"][pass_id][split]
        metrics = EXAM["per_pass"][pass_id][split]["per_relation"]
        assert sum(row["n"] for row in section["rows"].values()) == 60
        for relation, metric in metrics.items():
            row = section["rows"][relation]
            predictions = sum(
                truth["counts"][relation] for truth in section["rows"].values()
            )
            assert row["n"] == metric["recall"]["n"]
            assert row["counts"][relation] == metric["recall"]["k"]
            assert predictions == metric["precision"]["n"]
            assert all(type(n) is int and n >= 0 for n in row["counts"].values())


def test_confusion_preserves_errors_without_publishing_the_pair_key():
    assert (
        CONFUSION["per_pass"]["1"]["test"]["rows"]["uncheckable"]["counts"][
            "same_number"
        ]
        == 2
    )
    assert (
        CONFUSION["per_pass"]["3"]["test"]["rows"]["related"]["counts"]["path_step"]
        == 1
    )
    text = json.dumps(CONFUSION, separators=(",", ":"))
    assert not re.search(r"pair-\d+-\d+", text)
    for key in [
        "pair_id",
        "market_id",
        "outcome_id",
        "evidence",
        "messages",
        "title",
        "description",
    ]:
        assert f'"{key}":' not in text
