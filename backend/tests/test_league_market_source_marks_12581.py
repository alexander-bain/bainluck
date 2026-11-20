"""The awards and linked-match cards retain the inputs to their served rows."""

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.routes.league_futures import _serialize_outcomes


def _market(*, status="open", mutually_exclusive=True):
    return SimpleNamespace(
        name="NL MVP Winner",
        source="kalshi",
        status=status,
        mutually_exclusive=mutually_exclusive,
    )


def _outcome(outcome_id, price, *, winner=None, authority=None):
    return SimpleNamespace(
        id=outcome_id,
        name=f"Player {outcome_id}",
        current_probability=Decimal(price) if price is not None else None,
        opening_probability=None,
        probability_change_24h=None,
        rank=outcome_id,
        team_id=None,
        is_winner=winner,
        resolution_source=authority,
        last_updated=datetime(2020, 1, 1, 20, tzinfo=timezone.utc),
    )


def test_award_preview_marks_raw_quotes_and_keeps_the_full_field_divisor():
    outcomes = [_outcome(1, "0.625"), _outcome(2, "0.355")]
    outcomes.extend(_outcome(i, "0.025") for i in range(3, 12))

    rows = _serialize_outcomes(outcomes, _market())

    assert [(r["id"], r["rank"]) for r in rows] == [(i, i) for i in range(1, 11)]
    assert [r["probability"] for r in rows] == pytest.approx(
        [float(o.current_probability / Decimal("1.205")) for o in outcomes[:10]],
        abs=0.0001,
    )
    assert [r["source_mark"]["sources"][0]["probability"] for r in rows] == [
        float(o.current_probability) for o in outcomes[:10]
    ]
    assert rows[0]["source_mark"] == {
        "state": "single",
        "sources": [
            {
                "key": "kalshi",
                "name": "Kalshi",
                "probability": 0.625,
                "observed_at": None,
                "reason": "observation_unknown",
            }
        ],
        "method": "Bain Luck field · scaled with the other outcomes to total 100%",
    }


def test_withheld_quote_stays_absent_from_the_mark_and_the_divisor():
    rows = _serialize_outcomes(
        [_outcome(1, "0.80"), _outcome(2, "0.55"), _outcome(3, "0.45")],
        _market(),
        withheld_ids={1},
    )

    assert [(r["id"], r["probability"]) for r in rows] == [
        (2, 0.55),
        (3, 0.45),
        (1, None),
    ]
    assert rows[0]["source_mark"]["sources"][0]["probability"] == 0.55
    assert "method" not in rows[0]["source_mark"]
    assert rows[2]["source_mark"] == {
        "state": "none",
        "sources": [],
        "reason": "no_probability",
    }


def test_league_grade_refusal_does_not_create_an_official_loss_in_the_mark():
    rows = _serialize_outcomes(
        [
            _outcome(1, "0.60", winner=False, authority="api_settlement"),
            _outcome(2, "0.40", winner=False, authority="ungradeable_result"),
        ],
        _market(),
    )

    assert [(r["probability"], r["settled"]) for r in rows] == [
        (0.60, False),
        (0.40, False),
    ]
    assert [r["source_mark"]["state"] for r in rows] == ["single", "single"]
    assert [r["source_mark"]["sources"][0]["probability"] for r in rows] == [
        0.60,
        0.40,
    ]


def test_settled_marks_require_an_authoritative_grade():
    rows = _serialize_outcomes(
        [
            _outcome(1, "1.0", winner=True, authority="api_settlement"),
            _outcome(2, "0.0", winner=False, authority="api_settlement"),
            _outcome(3, "0.0", winner=False),
        ],
        _market(status="resolved"),
    )
    marks = {r["id"]: r["source_mark"] for r in rows}

    assert all(r["settled"] for r in rows)
    assert marks[1]["settled"] == {
        "source": "api_settlement",
        "result": "Won",
        "at": None,
    }
    assert marks[2]["settled"] == {
        "source": "api_settlement",
        "result": "Lost",
        "at": None,
    }
    assert marks[3] == {"state": "none", "sources": [], "reason": "result_unknown"}
