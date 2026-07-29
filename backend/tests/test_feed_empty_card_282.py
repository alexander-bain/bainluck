"""Queue 282 / C79 — non-predictive futures envelopes are suppressed.

Exercises the real feed producer boundary (``_suppress_zero_probability_cards``,
the function the ``/api/feed`` pipeline runs before ranking) with the C79 empty
tournament/concept equivalents and the rejected live-empty counterexample. An
open futures card must carry at least one renderable non-null positive
probability to surface; result-first settled envelopes are preserved; a
near-100% price is never treated as settlement authority.
"""

import json
from pathlib import Path

from app.routes.feed import _suppress_zero_probability_cards

FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent
    / "scripts"
    / "evals"
    / "feed_credibility_fixtures.json"
)
_CORPUS = json.loads(FIXTURE_PATH.read_text())


def _row(fixture_id: str) -> dict:
    for row in _CORPUS["scenarios"] + _CORPUS["rejected_counterexamples"]:
        if row["id"] == fixture_id:
            return row
    raise KeyError(fixture_id)


def _item_from_row(row: dict) -> dict:
    """Translate a C79 credibility row into a producer feed item (futures card).

    Only the empty/probability dimension is modeled here — the freshness/display
    dimensions belong to the separate feed-trust contract eval.
    """
    # The standard futures serialization renders under "top_outcomes"; use the
    # real key so this exercises the producer boundary, not a source seam.
    data = {
        "top_outcomes": [
            {"name": o["name"], "probability": o.get("probability")}
            for o in row.get("rendered_outcomes", [])
        ],
        "leader_probability": row.get("leader_probability"),
    }
    if row.get("market_status") == "resolved":
        # A resolved market is a result-first envelope: it renders a winner.
        data["resolved"] = True
        data["winner"] = (row.get("rendered_outcomes") or [{}])[0].get("name")
    return {"type": "futures", "data": data}


def _surfaces(fixture_id: str) -> bool:
    kept, _ = _suppress_zero_probability_cards([_item_from_row(_row(fixture_id))])
    return len(kept) == 1


# --- Empty / non-predictive open cards must NOT surface (C79) ---------------

def test_empty_tournament_equivalent_is_suppressed():
    # open, rendered_outcomes == []
    assert _surfaces("empty_tournament_equivalent") is False


def test_empty_concept_equivalent_is_suppressed():
    # open, single outcome with null probability
    assert _surfaces("empty_concept_equivalent") is False


def test_rejected_empty_live_card_cannot_surface():
    # The rejected counterexample: an empty live card claiming surface=True.
    # The producer must drop it regardless.
    assert _surfaces("reject_empty_live_card") is False


# --- Predictive open cards remain eligible ---------------------------------

def test_active_known_future_surfaces():
    assert _surfaces("active_known_future") is True


def test_near_certain_but_open_surfaces():
    # 0.99 is a live line, not a settlement — it must still surface.
    assert _surfaces("near_certain_but_open") is True


def test_unknown_date_otherwise_clean_surfaces():
    assert _surfaces("unknown_date_otherwise_clean") is True


# --- Price is never settlement authority (C79 reject_price_only_settlement) --

def test_price_alone_does_not_hide_card_as_settled():
    """A 0.99 open card is NOT suppressed as if settled — only an explicit
    resolved/winner signal is result-first. It has a positive probability, so it
    surfaces as a live card."""
    row = _row("reject_price_only_settlement")
    item = _item_from_row(row)
    assert item["data"].get("resolved") is None  # not marked settled by price
    kept, dropped = _suppress_zero_probability_cards([item])
    assert kept and dropped == 0


# --- Result-first settled envelopes are preserved even with no live line -----

def test_settled_envelope_preserved_when_outcomes_empty():
    item = {
        "type": "futures",
        "data": {"outcomes": [], "leader_probability": None, "resolved": True,
                 "winner": "Team A"},
    }
    kept, dropped = _suppress_zero_probability_cards([item])
    assert kept and dropped == 0


def test_all_zero_card_still_suppressed():
    """The original #240 all-0% suppression still holds."""
    item = {
        "type": "futures",
        "data": {"outcomes": [{"name": "A", "probability": 0.0},
                              {"name": "B", "probability": 0.0}],
                 "leader_probability": 0.0},
    }
    kept, dropped = _suppress_zero_probability_cards([item])
    assert not kept and dropped == 1


def test_events_never_suppressed():
    item = {"type": "event", "data": {"outcomes": [], "leader_probability": None}}
    kept, dropped = _suppress_zero_probability_cards([item])
    assert kept and dropped == 0
