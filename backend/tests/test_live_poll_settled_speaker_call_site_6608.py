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

from app.utils import live_blend as _live_blend

from tests.test_live_poll_commit_boundary_5682 import (  # noqa: E402
    _Event,
    _KalshiService,
    _Outcome,
    _Population,
    _PolyService,
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

    async def test_the_kalshi_primary_never_reaches_the_class_recognizer(
        self, monkeypatch
    ):
        """Names the short-circuit that makes the Polymarket arms below necessary.

        Every positive arm above rides a Kalshi PRIMARY, which
        `admissible_as_blend_speaker` admits on the second clause
        (`source == "kalshi" and is_primary`) and returns True before
        `_class_says_game_winner` or `outcomes_refute_game_winner` is asked.
        That exemption is MEASURED — 13 live UFC primaries would go blank
        without it — so it is correct, and it is exactly why those two clauses
        have no coverage from a Kalshi double. Pinned rather than described, so
        that if the exemption is ever reordered below the class gate this file
        says so instead of the Polymarket arms quietly changing meaning.
        """
        asked: list = []
        real = _live_blend._class_says_game_winner

        def _record(market):
            asked.append(getattr(market, "source", None))
            return real(market)

        monkeypatch.setattr(_live_blend, "_class_says_game_winner", _record)
        stamped = await _stamped_events(
            monkeypatch, _beat(market_status="open", completed_at=None)
        )

        assert stamped, "the beat never reached the blend at all"
        assert asked == [], (
            "a Kalshi primary reached the class recognizer — the exemption this "
            f"file relies on has moved: {asked}"
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


# --------------------------------------------------------------------------
# the Polymarket half of the same call site
# --------------------------------------------------------------------------
#
# WHY A SECOND SOURCE AND NOT A SECOND FIXTURE. The arms above all ride a
# Kalshi primary, so they enter `admissible_as_blend_speaker`, meet
# `source == "kalshi" and is_primary` and return True — proven by
# `test_the_kalshi_primary_never_reaches_the_class_recognizer`. #6608's clause
# sits ABOVE that exemption and is source-blind, so the refusal arm is real for
# both sources; but the POSITIVE arms only prove that Kalshi's short-circuit
# still fires. For every other source the admission is decided by a traversal
# the Kalshi double cannot reach: `_class_says_game_winner`, then
# `outcomes_refute_game_winner`, then #4854's kickoff clause.
#
# That traversal is where a source-blind refusal could go wrong without any
# Kalshi arm noticing — a clause that returned False one line too early would
# retire every Polymarket hero on the site and leave this file green. So the
# positive arm here asserts the recognizer was actually ASKED, not merely that
# a number came out: an arm that stamps for a reason it did not name is the
# vacuous half of a gate.
#
# WHAT IS DELIBERATELY NOT PINNED: #4854's `speaker_unobserved_since_kickoff`
# abstains here, because `_group_for` withholds `event_commence_time` (`kickoff
# is None ⇒ return False`). That withholding is the call site's own recorded
# choice — adopting two rules on a new surface in one step — and it is what
# lets these positive arms survive at all. An arm asserting the kickoff clause
# is SILENT would be pinning the absence of a ship that is deliberately not
# taken yet, so its adoption is left to fail loudly here instead.

POLY_EVENT_ID = "poly-evt-1"


class _PolyMarket:
    """A Polymarket match-winner row — NOT exempt the way a Kalshi primary is.

    The name is a bare matchup on purpose: `game_market_class` keys on that
    shape rather than on English words, so this is the title that carries a
    Polymarket row THROUGH the recognizer instead of past it. 5682's own
    `_Market` is named `market 1`, which does not parse, and a group built from
    it would fall silent before admission was ever decided.
    """

    def __init__(self, mid: int, *, status: str):
        self.id = mid
        self.source = "polymarket"
        self.external_id = POLY_EVENT_ID
        self.name = "Los Angeles R vs New York G"
        self.market_type = "game_winner"
        self.market_metadata = None
        self.status = status


def _poly_beat(*, market_status: str, completed_at) -> _Population:
    """One live Polymarket game, its book, and whether we have a result."""
    market = _PolyMarket(1, status=market_status)
    event = _Event(101, completed_at=completed_at)
    # A bare team name, so `outcomes_refute_game_winner` finds no derivative to
    # refute with. A name like `Los Angeles R (-1.5)` or `2 - 2` is the shape
    # that SHOULD refuse, and refusing it is #5273's arm, not this file's.
    outcome = _Outcome(1001, 1, f"{POLY_EVENT_ID}-LAR", "Los Angeles R")
    outcome.current_probability = 0.99
    return _Population([(market, event)], [outcome])


async def _poly_stamped_events(monkeypatch, population) -> tuple[list, list]:
    """Run the REAL beat over a Polymarket population.

    Returns `(stamped values, sources asked of the class recognizer)` — the
    second half is what proves the positive arm went through the traversal
    rather than around it.

    Both venue doubles are supplied even though only one source is in the
    population: `_run` patches a service only when it is handed one, and an
    unpatched branch constructs the real client. Empty payloads make the fetch
    loop a no-op, so the fixture's own price is what the blend reads.
    """
    stamped: list = []
    asked: list = []
    real_stamp = _aggregation.stamp_source_reading
    real_class = _live_blend._class_says_game_winner

    def _recording(existing, source, value, **kwargs):
        stamped.append(value)
        return real_stamp(existing, source, value, **kwargs)

    def _record_class(market):
        asked.append(getattr(market, "source", None))
        return real_class(market)

    monkeypatch.setattr(_aggregation, "stamp_source_reading", _recording)
    monkeypatch.setattr(_live_blend, "_class_says_game_winner", _record_class)
    _disable_inversion(monkeypatch)

    session = _Session([population, population])
    await _run(
        monkeypatch,
        session,
        kalshi=_KalshiService({}, []),
        poly=_PolyService({}, []),
        blend={},
    )
    return stamped, asked


class TestTheClauseIsSourceBlindAtThisCallSite:
    """#6608's clause is above the Kalshi exemption, so it binds Polymarket too."""

    async def test_an_open_polymarket_market_is_stamped_through_the_recognizer(
        self, monkeypatch
    ):
        """The positive traversal the Kalshi primary short-circuits past."""
        stamped, asked = await _poly_stamped_events(
            monkeypatch, _poly_beat(market_status="open", completed_at=None)
        )

        assert stamped, (
            "a live Polymarket match-winner lost its hero: the beat stamped "
            "nothing for a source whose admission depends on the class gate"
        )
        assert "polymarket" in asked, (
            "the Polymarket row was admitted WITHOUT being asked the class "
            f"question — this arm proves nothing about the traversal: {asked}"
        )

    async def test_a_resolved_polymarket_market_is_not_stamped_on_a_live_event(
        self, monkeypatch
    ):
        """The ship, on the source that does not get the primary's exemption."""
        stamped, asked = await _poly_stamped_events(
            monkeypatch, _poly_beat(market_status="resolved", completed_at=None)
        )

        assert stamped == [], (
            "the two-minute beat republished a settled Polymarket book as the "
            f"live hero: stamped {stamped}"
        )
        # The clause sits ABOVE the class gate, so a refusal here must happen
        # BEFORE the recognizer is asked. If the recognizer was asked, the row
        # was refused further down for some unrelated reason and this arm would
        # be green for the wrong cause.
        assert asked == [], (
            "the settled Polymarket row was refused somewhere below the class "
            f"gate, not by #6608's clause: {asked}"
        )

    async def test_a_resolved_polymarket_market_keeps_its_closing_line(
        self, monkeypatch
    ):
        """Settled means settled on this source too (gotcha #43, other side)."""
        stamped, _asked = await _poly_stamped_events(
            monkeypatch, _poly_beat(market_status="resolved", completed_at=_now())
        )

        assert stamped, (
            "a settled Polymarket market lost its closing line on a game we "
            "HAVE a result for — the gate became an off switch"
        )
