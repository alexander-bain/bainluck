"""#6608 — the TWO-MINUTE beat stops re-stamping a settled book as the live hero.

## the ship, as the reader sees it

`/events/15313399` — *Rinaldo Persson v Pigato*, WTA challenger — served, at
2026-09-16 19:49Z, a **live** match at **1% – 99%**, captioned as a blend, from a
Kalshi book we had marked `resolved` two hours earlier (market `61188963`,
`settled_at 17:50:00Z`), over an event carrying `completed_at IS NULL`. The
stamp said we had learned it seconds ago.

Worse than one stale number: the hero **blinked out**. #5820's withdrawal fires
on the 15-minute matcher and empties the key; this beat put it back ~90 seconds
later; the two alternated for as long as the match stayed live. A reader
watching the page saw the number vanish and return without touching anything.

## the clause was already shipped — this call site could not reach it

#5820's rule lives in `live_blend.admissible_as_blend_speaker` and is armed by a
SCOPE FIELD, not by its predicate. `MarketOutcomes.event_has_result` is
tri-state: `False` arms the clause, `None` means "the caller did not say" and
makes it abstain by construction.

Two of the blend's three writers supplied it. The 15-minute matcher carries it
on `_LinkedMarketRef`; the WebSocket fast lane reads it off its own joined Event
row. `_poll_live_prediction_market_prices` — every two minutes, on the main app
— built its groups in `_group_for` with **neither** scope field, so the clause
abstained there and only there. The guard was live, correct, and unreachable
from the writer that runs 720 times a day.

That asymmetry is also why the defect was mis-attributed to the fast lane on
first reading. The measurement that settled it: at 2026-09-16 20:00Z, 11 live
events with `completed_at IS NULL` cited a `status='resolved'` Kalshi market,
and **all 11 carried the identical `updated_at` to the microsecond**
(`19:57:09.172215`), byte-equal to those markets' `futures_outcomes.last_updated`.
The fast lane computes `datetime.now()` per event inside its loop and cannot
produce one shared microsecond; this beat stamps the OBSERVATION time of the
rows it read. One batch writer, and the row named it.

## the ladder of controls, and why each one is load-bearing

The dangerous version of this fix is "stop pricing anything we have marked
settled". That would wipe the closing line of every finished game — the evidence
calibration reads (gotcha #21) — and settled means settled. #5820 scoped it to
`completed_at IS NULL` for exactly that reason, so BOTH directions are asserted
here (gotcha #43): a withheld arm and an empty surface are not the same outcome,
and only the pair tells them apart.

* a `resolved` market on an event with no result is **not** stamped — the ship;
* an `open` market on the same event **is** stamped — proves the beat still
  writes at all, so the arm above is a refusal and not a broken harness;
* a `resolved` market on a **completed** event is still stamped — settled means
  settled, and the closing line survives.

The last two are what make this a gate rather than an off switch.
"""

from __future__ import annotations

from app.tasks import prediction_market_matching as pmm
from app.utils import aggregation as _aggregation

from tests.test_live_poll_commit_boundary_5682 import (  # noqa: E402
    _Event,
    _KalshiService,
    _Outcome,
    _Population,
    _Session,
    _now,
    _leg,
    _run,
)

# `pytest.ini` runs asyncio in AUTO mode, so the coroutines below need no mark.

TICKER = "KXNFLGAME-EVT1"


class _Market:
    """A Kalshi game-winner row whose TITLE parses into a matchup.

    5682's own `_Market` names itself `market 1`, which
    `extract_matchup_with_ticker_fallback` cannot parse — so a group built from
    it produces no reading at all and every arm below would pass against the
    unfixed function for the wrong reason. The name here is the one thing that
    makes the positive controls real, and `status` is the field the clause
    reads.
    """

    def __init__(self, mid: int, *, status: str):
        self.id = mid
        self.source = "kalshi"
        self.external_id = TICKER
        self.name = "Los Angeles R vs New York G"
        self.market_type = "game_winner"
        self.market_metadata = None
        self.status = status


def _beat(*, market_status: str, completed_at) -> _Population:
    """One live Kalshi game, its book, and whether we have a result for it."""
    market = _Market(1, status=market_status)
    event = _Event(101, completed_at=completed_at)
    outcome = _Outcome(1001, 1, f"{TICKER}-LAR", "Los Angeles R")
    # Strictly inside (0, 1): a Kalshi book settles at the last TRADE, so the
    # settled specimen is 0.99/0.01 and NOT at a boundary. That is the whole
    # reason #5548's price arm cannot see this class — a terminal-price fixture
    # would be silenced by that older rule and prove nothing about this one.
    outcome.current_probability = 0.99
    return _Population([(market, event)], [outcome])


def _disable_inversion(monkeypatch) -> None:
    """Orientation is a different question, and it needs a real session.

    `_check_and_fix_inversion` queries `odds_snapshots` through `session.get`,
    which 5682's fake transaction does not implement — every existing arm built
    on that harness switches the blend stage off entirely and so never meets it.
    Returning the home probability unchanged is the no-inversion verdict, which
    is what a fixture with no sportsbook consensus should produce anyway. Left
    UNPATCHED the beat swallows an AttributeError per event and stamps nothing,
    which would make every refusal arm here pass for the wrong reason.
    """

    async def _no_inversion(session, event_id, home_prob, source):
        return home_prob

    monkeypatch.setattr(pmm, "_check_and_fix_inversion", _no_inversion)


async def _stamped_events(monkeypatch, population) -> list[int]:
    """Run the REAL beat; return the event ids whose blend key it stamped.

    Observed at `stamp_source_reading` — the helper the beat writes the hero
    through — rather than by reading the fake session's UPDATE statements: the
    question this file asks is "did the number get republished", and that helper
    is where the answer is decided for every writer of the key.
    """
    stamped: list[int] = []
    real = _aggregation.stamp_source_reading

    def _recording(existing, source, value, **kwargs):
        stamped.append(value)
        return real(existing, source, value, **kwargs)

    monkeypatch.setattr(_aggregation, "stamp_source_reading", _recording)
    _disable_inversion(monkeypatch)

    session = _Session([population, population])
    service = _KalshiService({TICKER: [_leg(f"{TICKER}-LAR", TICKER)]}, [])
    # `blend={}` keeps the REAL primary selection and reading path. `_run`'s
    # default switches the blend stage OFF, which would make every arm here
    # vacuous.
    await _run(monkeypatch, session, kalshi=service, blend={})
    return stamped


class TestTheBeatCarriesTheSettledSpeakerClause:
    async def test_a_resolved_market_is_not_stamped_on_an_event_with_no_result(
        self, monkeypatch
    ):
        """The ship. This is the arm that fails against the unfixed beat."""
        stamped = await _stamped_events(
            monkeypatch, _beat(market_status="resolved", completed_at=None)
        )
        assert stamped == [], (
            "the two-minute beat republished a settled book as the live hero: "
            f"stamped {stamped}"
        )

    async def test_an_open_market_on_the_same_event_is_still_stamped(
        self, monkeypatch
    ):
        """The refusal above is a REFUSAL, not a harness that writes nothing."""
        stamped = await _stamped_events(
            monkeypatch, _beat(market_status="open", completed_at=None)
        )
        assert stamped, (
            "the beat stopped writing the blend entirely — the arm above proves "
            "nothing unless this one writes"
        )

    async def test_a_resolved_market_on_a_completed_event_is_still_stamped(
        self, monkeypatch
    ):
        """Settled means settled: the closing line of a finished game survives.

        The scope is `completed_at IS NULL`, and this is the other side of it
        (gotcha #43). A fix that dropped this leg would delete the evidence
        calibration reads.
        """
        stamped = await _stamped_events(
            monkeypatch,
            _beat(market_status="resolved", completed_at=_now()),
        )
        assert stamped, (
            "a settled market lost its closing line on a game we HAVE a result "
            "for — the gate became an off switch"
        )


class TestTheScopeFieldIsTheThingThatWasMissing:
    async def test_the_group_the_beat_builds_carries_the_tri_state(
        self, monkeypatch
    ):
        """Pinned at the seam, because the clause is armed by a FIELD.

        The three arms above observe the consequence; this one names the cause,
        so a later edit that drops the field back to its default fails with the
        reason rather than as a mysterious re-stamp. It also pins that the value
        is `False` — the ARMED state — and not `None`, which is the shape the
        defect wore for as long as it existed.
        """
        seen: list = []
        real = pmm._compute_source_home_probability

        def _capture(group, home, away):
            seen.extend(group)
            return real(group, home, away)

        monkeypatch.setattr(pmm, "_compute_source_home_probability", _capture)
        await _stamped_events(
            monkeypatch, _beat(market_status="open", completed_at=None)
        )

        assert seen, "the beat never reached the blend reading"
        assert [entry.event_has_result for entry in seen] == [False], (
            "the beat's blend group did not carry #5820's tri-state as ARMED: "
            f"{[entry.event_has_result for entry in seen]}"
        )

    async def test_a_market_whose_event_vanished_does_not_throw_the_beat(
        self, monkeypatch
    ):
        """The `ev is None` arm, asserted where it is actually observable.

        Reading the tri-state costs an attribute lookup on a row the pass may no
        longer be able to resolve — a market can outlive its event in the
        population between the rollback re-read and this loop (gotcha #6 is the
        same hazard one step along). Without the guard, `ev.completed_at` raises
        inside `_group_for`, the per-event `except` counts it, and the event
        loses its price for that beat.

        The tri-state VALUE on that path is deliberately not asserted: the loop
        resolves the event again immediately afterwards and `continue`s, so the
        `None` never reaches a reading and an assertion on it would pin
        something no reader can observe. What IS observable, and what this arm
        holds, is that the beat comes back clean instead of erroring per event.
        """
        population = _beat(market_status="open", completed_at=None)
        session = _Session([population, population])
        service = _KalshiService({TICKER: [_leg(f"{TICKER}-LAR", TICKER)]}, [])

        real_build = pmm._load_live_poll_population

        async def _blind(*args, **kwargs):
            pop = await real_build(*args, **kwargs)
            # The market is still in the population; only the event behind it
            # has gone. Not otherwise reachable from a fixture.
            pop.event_by_market_id.clear()
            return pop

        monkeypatch.setattr(pmm, "_load_live_poll_population", _blind)
        _disable_inversion(monkeypatch)
        stats = await _run(monkeypatch, session, kalshi=service, blend={})

        assert not stats["errors"], (
            "reading the tri-state threw on a market whose event had gone: "
            f"{stats['errors']}"
        )
