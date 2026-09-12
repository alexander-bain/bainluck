"""The `backfill-wps` admin repair may not write a leg the blend would refuse.

CU-1 clause (1) on #5273: *"every poll / WebSocket / refresh / repair path uses
the same admission function"*. Three writers of the Polymarket blend leg already
did — the 15-minute matcher, the 120s poll's `live_blend_refresh`, and the
WebSocket fast lane, which delegates to it. `POST
/api/admin/prediction-markets/backfill-wps` was the fourth, and it did not.

WHAT IT WROTE INSTEAD. Its candidate query filters on `name ILIKE '% vs %'` /
`external_id ILIKE '%game%'` — a TITLE gate, the instrument #5273 rung 1
measured as insufficient, because Polymarket's derivative baskets wear the
match's title (`… - More Markets`, `… - Halftime Result`) and carry the books as
their OUTCOMES. `find_moneyline_outcome` then resolves the lone competitor-shaped
outcome by containment, and a handicap's price is stamped as the match winner.

Measured on production 2026-09-12 over the entire (-6h, +72h) slate — the 56
events holding a linked Polymarket market and NO polymarket leg, which is
exactly the population this endpoint is eligible to write (`if source in wps:
skipped`): it wrote on 3, and the gate refuses all 3. Zero correct writes. The
three specimens below are those rows, verbatim.

AND THE RETIREMENT IS WHAT MADE THEM ELIGIBLE. All three have
`count_admissible_speakers == 0`, so they are precisely the events
`_retire_unbacked_blend_source` (#5031) clears the leg from — and clearing it
leaves the key ABSENT, which is this loop's write condition. So the gate that
only refuses to write did not hold: a fourth writer could put the retired number
back. That composition, not the endpoint alone, is the defect this file guards.

The Kalshi delta is provably zero and `test_a_kalshi_game_market_is_untouched`
is what proves it: the exemption inside `admissible_as_blend_speaker` is per
SOURCE, so a Kalshi row returns True before the class recognizer runs.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.sql.dml import Update

from app.routes.admin_matching import backfill_win_probability_sources


def _request():
    return SimpleNamespace(headers={"authorization": "Bearer test-secret"})


def _outcome(name, prob, rank):
    return SimpleNamespace(name=name, current_probability=prob, rank=rank)


def _market(*, market_id, name, source="polymarket", external_id=None, outcomes=()):
    return SimpleNamespace(
        id=market_id,
        name=name,
        source=source,
        external_id=external_id if external_id is not None else f"0x{market_id}",
        outcomes=list(outcomes),
    )


def _event(*, event_id=15305044, home="Eintracht Braunschweig", away="SG Dynamo Dresden"):
    return SimpleNamespace(
        id=event_id,
        home_team_name=home,
        away_team_name=away,
        win_probability_sources={},
    )


class _FakeDb:
    """Returns the candidate rows once, then records every UPDATE issued."""

    def __init__(self, rows):
        self._rows = rows
        self.updates = []

    async def execute(self, stmt):
        if isinstance(stmt, Update):
            self.updates.append(stmt)
            return MagicMock()
        result = MagicMock()
        result.unique.return_value.all.return_value = self._rows
        return result

    async def commit(self):
        return None


def _written_sources(db):
    """The `win_probability_sources` payload of each UPDATE the route issued."""
    out = []
    for stmt in db.updates:
        params = stmt.compile().params
        if "win_probability_sources" in params:
            out.append(params["win_probability_sources"])
    return out


async def _run(monkeypatch, rows):
    monkeypatch.setenv("ADMIN_TOKEN", "test-secret")
    db = _FakeDb(rows)
    stats = await backfill_win_probability_sources(
        request=_request(), secret=None, limit=500, event_id=None, db=db,
    )
    return stats, db


# ── the three production specimens ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_more_markets_basket_is_refused_not_published(monkeypatch):
    """Event 15305044, LIVE at the time of measurement, stored 0.165.

    The basket's only competitor-shaped outcome is a 1.5-goal handicap, so
    containment resolved `Eintracht Braunschweig (-1.5)` and published its price
    as the match winner.
    """
    market = _market(
        market_id=59837320,
        name="Eintracht Braunschweig vs. SG Dynamo Dresden - More Markets",
        outcomes=[
            _outcome("O/U 0.5", 0.94, 0),
            _outcome("O/U 1.5", 0.78, 1),
            _outcome("Eintracht Braunschweig (-1.5)", 0.165, 2),
            _outcome("Both Teams to Score", 0.55, 3),
        ],
    )
    stats, db = await _run(monkeypatch, [(market, _event())])

    assert stats["written"] == 0
    assert stats["refused_inadmissible"] == 1
    assert _written_sources(db) == []


@pytest.mark.asyncio
async def test_a_halftime_result_book_is_refused(monkeypatch):
    """Event 15296383 — a half's winner is not the match's, at 0.87.

    Every outcome here is competitor-shaped, so no outcome-level tell exists:
    the refusal has to come from the market's own title qualifier.
    """
    market = _market(
        market_id=59852323,
        name=(
            "CSyD Defensa y Justicia vs. CA Gimnasia y Esgrima de Mendoza "
            "- Halftime Result"
        ),
        outcomes=[
            _outcome("Draw", 0.09, 0),
            _outcome("CSyD Defensa y Justicia", 0.87, 1),
            _outcome("CA Gimnasia y Esgrima de Mendoza", 0.04, 2),
        ],
    )
    event = _event(
        event_id=15296383,
        home="CSyD Defensa y Justicia",
        away="CA Gimnasia y Esgrima de Mendoza",
    )
    stats, db = await _run(monkeypatch, [(market, event)])

    assert stats["written"] == 0
    assert stats["refused_inadmissible"] == 1
    assert _written_sources(db) == []


@pytest.mark.asyncio
async def test_a_lone_handicap_outcome_is_refused(monkeypatch):
    """Event 15310749 — a single `(-2.5)` outcome, published at 0.515.

    The one-outcome shape is why arity cannot be the discriminator and the
    predicate has to read vocabulary.
    """
    market = _market(
        market_id=60814360,
        name="FK Polissia vs. FK Livyi Bereh - More Markets",
        outcomes=[_outcome("FK Livyi Bereh (-2.5)", 0.485, 0)],
    )
    event = _event(event_id=15310749, home="FK Polissia", away="FK Livyi Bereh")
    stats, db = await _run(monkeypatch, [(market, event)])

    assert stats["written"] == 0
    assert stats["refused_inadmissible"] == 1
    assert _written_sources(db) == []


# ── the other direction: a real winner still gets through, with its record ───


@pytest.mark.asyncio
async def test_a_genuine_two_sided_winner_is_still_written(monkeypatch):
    """The gate must not be a blanket refusal of this endpoint's Polymarket arm.

    Without this, the three tests above pass just as well against a writer that
    was deleted.
    """
    market = _market(
        market_id=59837999,
        name="Eintracht Braunschweig vs. SG Dynamo Dresden",
        outcomes=[
            _outcome("Eintracht Braunschweig", 0.62, 0),
            _outcome("SG Dynamo Dresden", 0.38, 1),
        ],
    )
    stats, db = await _run(monkeypatch, [(market, _event())])

    assert stats["refused_inadmissible"] == 0
    assert stats["written"] == 1
    written = _written_sources(db)
    assert len(written) == 1
    assert "polymarket" in written[0]


@pytest.mark.asyncio
async def test_the_written_leg_names_the_rule_that_admitted_it(monkeypatch):
    """CU-4 (#5311): a leg from this path is no longer indistinguishable.

    Before the gate this writer passed no record, so its readings graded
    UNVERIFIED and could not be told apart from a gated writer's — the reason
    the endpoint sat in `KNOWN_UNRECORDED_MINTS`. The record is minted FROM the
    gate applied above, never asserted independently.
    """
    market = _market(
        market_id=59837999,
        name="Eintracht Braunschweig vs. SG Dynamo Dresden",
        outcomes=[
            _outcome("Eintracht Braunschweig", 0.62, 0),
            _outcome("SG Dynamo Dresden", 0.38, 1),
        ],
    )
    _stats, db = await _run(monkeypatch, [(market, _event())])

    entry = _written_sources(db)[0]["polymarket"]
    record = entry["eligibility"]
    assert record["rule"] == "live_blend.admissible_as_blend_speaker@5031"
    assert record["market_id"] == 59837999


# ── the Kalshi delta, which must be exactly zero ─────────────────────────────


@pytest.mark.asyncio
async def test_a_kalshi_game_market_is_untouched(monkeypatch):
    """`is_primary=True` is safe because the gate's exemption is per SOURCE.

    A Kalshi row returns True before the class recognizer runs, and it has
    already passed `feeds_win_prob_blend` — its own measured admission rule —
    immediately above the new check. This pins that the new gate adds no second
    Kalshi burden; the 13 live UFC primaries `admissible_as_blend_speaker`'s
    docstring names are the population that would otherwise go blank.
    """
    market = _market(
        market_id=77001,
        name="Boston Celtics at New York Knicks",
        source="kalshi",
        external_id="KXNBAGAME-26MAY17BOSNYK-BOS",
        outcomes=[
            _outcome("Boston Celtics", 0.58, 0),
            _outcome("New York Knicks", 0.42, 1),
        ],
    )
    event = _event(event_id=123, home="Boston Celtics", away="New York Knicks")
    stats, db = await _run(monkeypatch, [(market, event)])

    assert stats["refused_inadmissible"] == 0
    assert stats["written"] == 1
    assert "kalshi" in _written_sources(db)[0]
