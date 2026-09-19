"""#4079 — a card may not call an undated price change "today".

`probability_change_24h` is `new - previous` at write time, for a previous write
of unknown age, and three serving paths spent it on the sentence "Up 9.5 points
today". Measured on production 2026-09-19 over every row that made that claim
(open market, non-null delta at or above the card floor), n = 2,445:

    supported by a dated comparison        927   (38%)
    right sign, materially wrong amount    797   (33%)
      …of those, dated move under the floor  260
    no qualifying dated basis at all       513   (21%)

A4 (overstated travel) and A7 (contradicted direction) retire the two loudest
wrong classes at the source. Neither can make the AMOUNT right, and neither can
cover the ten minutes between a price write and the next sweep.

So the fix is a bank of DATED EVIDENCE — one observed price per in-scope
outcome, with the instant it was observed (`market_metadata`'s
`dated_movement_basis`, statement A8) — and a single shared consumer that
subtracts it from the price the card is already holding
(`feed._dated_movement_change`).

═══ WHAT THESE TESTS ARE, AND WHAT THEY DELIBERATELY ARE NOT ═══

They drive the REAL chain: a market carrier of the real shape, through the real
`_dated_movement_change`, into the real `generate_futures_headline` /
`compose_binary_card_copy`, and they assert the SENTENCE. A test that asserted
the helper's float would pass on a build where the composer ignored it.

They are not a test of the SQL — the producer is graded by
`test_movement_window.py` (statement text and ordering) and
`tests/integration/test_movement_window_pg.py` (real Postgres). The contract
between them is one constant, and `test_the_carrier_and_the_sweep_agree_on_the_window`
below is what stops the two halves drifting.

Each class below is a named specimen off Alex's phone, and each one is a
DIFFERENT reason the old code printed a wrong word.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.routes.feed import _dated_movement_change
from app.utils.feed_reasons import compose_binary_card_copy, generate_futures_headline
from app.utils.futures_highlights import MODERATE_MOVEMENT_THRESHOLD
from app.utils.futures_market_snapshot import (
    DATED_BASIS_METADATA_KEY,
    DATED_BASIS_MIN_AGE_HOURS,
    DATED_BASIS_WINDOW_HOURS,
)

NOW = datetime(2026, 9, 19, 9, 0, tzinfo=timezone.utc)


def _stamp(hours_ago: float) -> str:
    """A basis stamp the sweep's `to_char` would have written."""
    return (NOW - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


class _Market:
    """A market carrier of the shape both serving paths hand the consumer.

    `market_metadata` is a real column in `MARKET_COLUMNS`, so it is present on
    the plain ORM row AND on a `from_plain` snapshot rebuild, and the reader
    resolves it off `__dict__` for gotcha #42's reason. Modelling it as a plain
    attribute is therefore faithful to both carriers rather than to one.
    """

    def __init__(self, bank: dict | None = None, *, metadata: dict | None = None):
        if metadata is None:
            metadata = {"polymarket_event_id": "797729"}
            if bank is not None:
                metadata[DATED_BASIS_METADATA_KEY] = bank
        self.market_metadata = metadata


def _outcome(outcome_id: int, name: str, probability: float, delta: float | None):
    """One SCORING row, exactly as the three builders in `feed.py` make it."""
    return {
        "id": outcome_id,
        "name": name,
        "team_id": None,
        "team_name": None,
        "probability": probability,
        "probability_change_24h": delta,
        "rank": 1,
        "rank_change_24h": 0,
        "opening_probability": None,
    }


def _headline(
    change: float | None,
    mover: str,
    market_name: str = "The Game Awards: Game of the Year",
) -> str | None:
    """The card's headline, composed the way the serving paths compose it.

    `market_name` is a real argument and not a constant because the composer
    BRANCHES on it: a mover the module can say out loud as a side gets the
    "<side> up N points today" sentence, while a threshold rung gets
    "<market> odds up N points". Both are movement claims about the day and both
    must carry the dated number, so the specimens below assert whichever
    sentence their own shape produces rather than being bent to one branch.
    """
    return generate_futures_headline(
        highlight_reasons=["moderate_movement_24h"],
        top_mover_name=mover,
        top_mover_change=change,
        top_mover_is_printed=True,
        market_name=market_name,
    )


# ─── CLASS 1: SAME SIGN, WRONG AMOUNT ────────────────────────────────────────
#
# Codex's counterexample, and the class A7 explicitly leaves standing ("it fires
# only on a CONTRADICTED direction, never on a magnitude disagreement"). The
# stored delta spans the gap to the previous write; the day is longer than that
# gap and moved further.


def test_a_same_sign_claim_states_the_DATED_amount_not_the_per_write_one():
    """23 h ago 0.40, 1 h ago 0.45, now 0.50 — the day moved 10 points, not 5.

    The per-write delta is `+0.05` and passes every screen that exists: its
    sign is right, so A7 keeps it, and it is well inside the window's extrema,
    so A4 keeps it. The card said "Up 5 points today" about a day that moved 10.
    """
    market = _Market({"216388327": [0.40, _stamp(23)]})
    outcomes = [_outcome(216388327, "Phantom Blade Zero", 0.50, 0.05)]

    change = _dated_movement_change(market, outcomes, "Phantom Blade Zero", now=NOW)

    assert change == pytest.approx(0.10), (
        "the dated move is `current - basis` = 0.50 - 0.40; reading 0.05 means "
        "the consumer is still lifting the per-write delta off the row"
    )
    assert _headline(change, "Phantom Blade Zero") == (
        "Phantom Blade Zero up 10 points today"
    )


def test_the_live_phone_specimen_loses_a_word_rather_than_keeping_a_wrong_one():
    """`Phantom Blade Zero`, measured on production 2026-09-19 09:1xZ.

    Stored delta -2.50 points; observed at 0.0640 nineteen hours earlier and
    trading at 0.0505, so the day moved **-1.35** — under the card floor. The
    honest sentence is not a smaller number, it is no movement sentence: the day
    did not do the thing the chip claims.
    """
    market = _Market({"216388327": [0.0640, _stamp(19.3)]})
    outcomes = [_outcome(216388327, "Phantom Blade Zero", 0.0505, -0.025)]

    change = _dated_movement_change(market, outcomes, "Phantom Blade Zero", now=NOW)

    assert change is None
    assert _headline(change, "Phantom Blade Zero") != (
        "Phantom Blade Zero down 2.5 points today"
    )
    assert "today" not in (_headline(change, "Phantom Blade Zero") or "")


def test_a_dated_move_exactly_on_the_floor_is_sayable():
    """The bound is inclusive, on the same threshold that draws the chip.

    Both directions are asserted: a boundary test that only proves the reject
    side is satisfied by a consumer that rejects everything.
    """
    market = _Market({"1": [0.50, _stamp(20)]})
    at_floor = [_outcome(1, "Yes", 0.50 + MODERATE_MOVEMENT_THRESHOLD, 0.01)]
    assert _dated_movement_change(market, at_floor, "Yes", now=NOW) == pytest.approx(
        MODERATE_MOVEMENT_THRESHOLD
    )

    under = [_outcome(1, "Yes", 0.50 + MODERATE_MOVEMENT_THRESHOLD - 0.001, 0.01)]
    assert _dated_movement_change(market, under, "Yes", now=NOW) is None


# ─── CLASS 2: SIGN REVERSAL ──────────────────────────────────────────────────
#
# A7's population, retired at the source. This asserts the consumer ALSO gets it
# right from the bank, because A7 runs every ten minutes and a writer can strand
# a reversed delta inside that gap.


def test_a_reversed_sign_is_stated_the_way_the_day_actually_went():
    """`S&P 500 (SPY) closes above $745` — chip said DOWN 7.5, day rose 40.5."""
    spy = "S&P 500 (SPY) closes above $745 on September 21?"
    market = _Market({"9001": [0.49, _stamp(18.5)]})
    outcomes = [_outcome(9001, "$745", 0.895, -0.075)]

    change = _dated_movement_change(market, outcomes, "$745", now=NOW)

    assert change == pytest.approx(0.405)
    assert _headline(change, "$745", spy) == (
        "S&P 500 (SPY) closes above $745 on September 21 odds up 40.5 points"
    )
    assert "down" not in (_headline(change, "$745", spy) or "")


# ─── CLASS 3: MISSING EVIDENCE ───────────────────────────────────────────────
#
# 513 of 2,445. An absent qualifying baseline cannot authorise a dated number —
# and neither can a baseline that is too young to be about "today", nor one so
# old that the sweep that banked it has plainly stopped.


@pytest.mark.parametrize(
    "bank, why",
    [
        (None, "the market carries no bank at all"),
        ({}, "the bank is empty"),
        ({"other": [0.40, _stamp(20)]}, "the bank has no cell for THIS outcome"),
        ({"216388327": [0.40, _stamp(2)]}, "the basis is two hours old"),
        ({"216388327": [0.40, _stamp(40)]}, "the basis has aged out of the window"),
        ({"216388327": [0.40]}, "the cell is the wrong length"),
        ({"216388327": [0.40, "not-a-stamp"]}, "the stamp will not parse"),
        ({"216388327": [None, _stamp(20)]}, "the price is not a price"),
        ({"216388327": "0.40"}, "the cell is not a pair"),
    ],
)
def test_without_qualifying_dated_evidence_no_number_is_printed(bank, why):
    market = _Market(bank)
    outcomes = [_outcome(216388327, "Phantom Blade Zero", 0.50, 0.05)]

    change = _dated_movement_change(market, outcomes, "Phantom Blade Zero", now=NOW)

    assert change is None, f"a dated claim was authorised when {why}"
    assert "today" not in (_headline(change, "Phantom Blade Zero") or "")


def test_a_market_with_no_metadata_column_at_all_is_excluded_not_crashed():
    """A projection that stops loading `market_metadata` degrades to silence.

    Gotcha #42's shape: unreadable must mean "we do not know", never an
    exception inside the per-item serializer.
    """
    market = _Market(metadata=None)
    outcomes = [_outcome(216388327, "Phantom Blade Zero", 0.50, 0.05)]
    assert _dated_movement_change(market, outcomes, "Phantom Blade Zero", now=NOW) is None


def test_a_scoring_row_with_no_id_is_unknown_not_a_crash():
    """A reduced outcome object means UNKNOWN, never an exception.

    The three builders read the id with `getattr(..., None)`, the same tolerant
    read `team_id` has carried since #4700: a served ORM row always has the
    primary key, and a fixture that does not carry it must fold to "no dated
    evidence" rather than raise inside the per-item serializer. CI caught the
    intolerant first draft on
    `test_an_outcome_object_without_the_attribute_is_unknown_not_a_crash`.
    """
    market = _Market({"216388327": [0.40, _stamp(20)]})
    row = _outcome(216388327, "Phantom Blade Zero", 0.50, 0.05)
    row["id"] = None

    assert _dated_movement_change(market, [row], "Phantom Blade Zero", now=NOW) is None


def test_an_upper_age_bound_makes_a_STOPPED_SWEEP_fail_closed():
    """The sweep dying must silence the captions, not freeze a stale claim.

    A banked basis only ever gets older, so this is the whole outage detector:
    nothing has to notice the sweep stopped.
    """
    market = _Market({"1": [0.40, _stamp(DATED_BASIS_WINDOW_HOURS - 0.1)]})
    outcomes = [_outcome(1, "Yes", 0.50, 0.05)]
    assert _dated_movement_change(market, outcomes, "Yes", now=NOW) is not None

    stale = _Market({"1": [0.40, _stamp(DATED_BASIS_WINDOW_HOURS + 0.1)]})
    assert _dated_movement_change(stale, outcomes, "Yes", now=NOW) is None


# ─── CLASS 4: A WRITE BETWEEN SWEEPS ─────────────────────────────────────────
#
# The class no producer-side statement can reach. The sweep runs every ten
# minutes; a poll lands inside that gap and writes a fresh per-write delta that
# nothing has vetted. This is why the bank holds an OBSERVATION and the
# subtraction happens at serve time.


def test_a_price_write_between_sweeps_moves_the_answer_to_the_new_TRUTH():
    """Same bank, new price, no sweep in between.

    Before the write the day is +10 points. A poll then takes the price from
    0.50 to 0.62 and stores a per-write delta of +0.12. The old code printed
    that 12 immediately. The dated answer is +22, and this consumer reaches it
    without the sweep having run at all.
    """
    bank = {"216388327": [0.40, _stamp(23)]}
    market = _Market(bank)

    before = [_outcome(216388327, "Phantom Blade Zero", 0.50, 0.05)]
    assert _dated_movement_change(
        market, before, "Phantom Blade Zero", now=NOW
    ) == pytest.approx(0.10)

    after = [_outcome(216388327, "Phantom Blade Zero", 0.62, 0.12)]
    change = _dated_movement_change(market, after, "Phantom Blade Zero", now=NOW)

    assert change == pytest.approx(0.22), (
        "the un-swept per-write delta is 0.12; a card reading 0.12 here is the "
        "between-sweeps hole this design exists to close"
    )
    assert _headline(change, "Phantom Blade Zero") == (
        "Phantom Blade Zero up 22 points today"
    )


def test_a_write_between_sweeps_can_also_SILENCE_a_card():
    """The mirror, and the one that matters: the gap must not print a lie.

    A poll reverses the price back onto its basis. The stored delta still says
    -8 points and the old code still printed it; the day is now flat.
    """
    market = _Market({"1": [0.50, _stamp(23)]})
    outcomes = [_outcome(1, "Yes", 0.505, -0.08)]

    change = _dated_movement_change(market, outcomes, "Yes", now=NOW)

    assert change is None
    assert "today" not in (_headline(change, "Yes") or "")


# ─── THE GENUINE-MOVE CONTROL ────────────────────────────────────────────────
#
# 927 of 2,445 rows are honest, and the ship is worthless if it takes them with
# it. The control is the specimen's own sibling wherever one exists — same
# market, same poll, same basis age — because any predicate that takes both is
# indiscriminate rather than working.


def test_a_genuine_dated_move_keeps_its_chip_and_its_number():
    """`$740` — the sibling of the reversed `$745`, in the same market.

    Claims +39.5 against a +39.5 dated move, written by the same poll against a
    basis of the same age. It must survive unchanged, and its NUMBER must be the
    same number the card printed before this ship.
    """
    market = _Market(
        {
            "9001": [0.49, _stamp(18.5)],  # $745 — reversed
            "9002": [0.50, _stamp(18.5)],  # $740 — honest
        }
    )
    honest = [_outcome(9002, "$740", 0.895, 0.395)]

    change = _dated_movement_change(market, honest, "$740", now=NOW)

    assert change == pytest.approx(0.395)
    assert _headline(
        change, "$740", "S&P 500 (SPY) closes above $740 on September 21?"
    ) == "S&P 500 (SPY) closes above $740 on September 21 odds up 39.5 points"


def test_the_binary_card_copy_path_states_the_dated_move_too():
    """The yes/no composer is a second claim-producing path, not the same one.

    `compose_binary_card_copy` writes its own "today" sentence off the same
    argument, so a fix proved only on `generate_futures_headline` would leave
    every binary card — which is 97.8% of the book — unrepaired.
    """
    market = _Market({"221539112": [0.55, _stamp(20)]})
    outcomes = [_outcome(221539112, "Yes", 0.46, -0.01)]

    change = _dated_movement_change(market, outcomes, "Yes", now=NOW)
    assert change == pytest.approx(-0.09)

    copy = compose_binary_card_copy(
        market_name="US bank failure by December 31, 2026?",
        highlight_reasons=["major_movement_24h"],
        affirmative_probability=0.46,
        top_mover_change=change,
    )
    assert copy.headline == "Down 9 points today"


# ─── WHAT THE SHIP MAY NOT DO ────────────────────────────────────────────────


def test_the_bank_never_promotes_an_outcome_the_highlight_did_not_pick():
    """`US bank failure` has a real -9.0 dated move and a NULL per-write delta.

    Its card is silent today and stays silent: selecting on the bank would be a
    new ranking policy, which this ship is explicitly not. The bank decides what
    may be SAID about the outcome already chosen, never which outcome is chosen.
    """
    market = _Market({"221539112": [0.55, _stamp(20)]})
    outcomes = [_outcome(221539112, "Yes", 0.46, None)]

    assert _dated_movement_change(market, outcomes, "Yes", now=NOW) is None
    # …and with no mover named at all, there is nothing to ask about.
    assert _dated_movement_change(market, outcomes, None, now=NOW) is None


def test_refusing_the_today_claim_does_not_take_the_DATED_LIFETIME_one_with_it():
    """The `Meta training pause` specimen (market 61122553), read on production.

    🔴 SILENCING THE DAY IS NOT SILENCING THE CARD, AND NOTHING PINNED THAT.
    Both legs of 61122553 carry a NULL `probability_change_24h`, so
    `compute_futures_highlight` names no mover, `_dated_movement_change` refuses
    at its FIRST gate — before the bank is ever consulted — and there is no
    "today" sentence to be had. What the card actually prints is the DATED
    LIFETIME branch, off `_biggest_move_from_opening`: 0.835 on 2026-09-15 to
    0.050 now. That branch is this ship's control, the prose said so, and no
    case held it — so a later change that made the today-refusal return early,
    or dropped the surprise arm at a call site, would take a true dated sentence
    off a reader's card and every test here would still pass.

    That is not hypothetical. The production replay written to answer codex's
    1155Z note (`artifacts-discover/7176-addendum/replay.py`) omitted exactly
    this arm on its first run and reported this specimen as an EMPTY card, which
    is the wrong answer about the live page in the direction that looks like
    over-silencing.

    Values are the production rows read 2026-09-19 12:05Z via `db-query`.
    """
    market = _Market(None)
    outcomes = [
        _outcome(229745131, "Yes", 0.05, None),
        _outcome(229745132, "No", 0.95, None),
    ]
    opened_at = datetime(2026, 9, 15, 9, 15, 49, tzinfo=timezone.utc)

    # No mover, therefore no dated "today" number — at the first gate.
    assert _dated_movement_change(market, outcomes, None, now=NOW) is None
    assert _dated_movement_change(market, outcomes, "Yes", now=NOW) is None

    copy = compose_binary_card_copy(
        market_name="Meta announces a training pause by October 31?",
        highlight_reasons=["major_surprise"],
        affirmative_probability=0.05,
        top_mover_change=None,
        # `_biggest_move_from_opening` states a yes/no market's lifetime move
        # against the AFFIRMATIVE, and only when the opening carries a date.
        top_surprise_change=0.05 - 0.835,
        top_surprise_opened_at=opened_at,
        now=NOW,
    )

    assert copy.headline == "Down 78.5 points since Sep 15"
    assert copy.context_summary == "Down 78.5 points since Sep 15 — now 5% chance"
    assert "today" not in copy.reason


def test_an_undated_opening_still_buys_no_sentence_on_that_same_card():
    """The other half of the case above, so it cannot pass by always composing.

    Same specimen, same refused "today", but with the opening's date removed:
    an undated lifetime move is not a fact about any day either, and the card
    goes to its designed empty state rather than to a dateless number.
    """
    market = _Market(None)
    outcomes = [_outcome(229745131, "Yes", 0.05, None)]

    assert _dated_movement_change(market, outcomes, "Yes", now=NOW) is None

    copy = compose_binary_card_copy(
        market_name="Meta announces a training pause by October 31?",
        highlight_reasons=["major_surprise"],
        affirmative_probability=0.05,
        top_mover_change=None,
        top_surprise_change=0.05 - 0.835,
        top_surprise_opened_at=None,
        now=NOW,
    )

    assert copy.headline == ""
    assert copy.context_summary == ""
    assert copy.reason == ""


def test_a_stored_zero_delta_is_still_a_non_mover():
    """Truthiness, not `is not None` — verbatim from the three loops replaced.

    A row whose last write moved nothing is not a mover, however far the day
    travelled. Changing this would start drawing chips on rows that never had
    one, which is the ranking-policy line again.
    """
    market = _Market({"1": [0.40, _stamp(20)]})
    outcomes = [_outcome(1, "Yes", 0.50, 0.0)]
    assert _dated_movement_change(market, outcomes, "Yes", now=NOW) is None


def test_the_per_write_column_is_left_on_the_row_for_its_other_readers():
    """The consumer READS `probability_change_24h`; it never rewrites it.

    `max_movement_24h`, `/api/futures/movers`' ranking and
    `compute_futures_highlight`'s pick all key on this column, and reinterpreting
    it was the refused design. The scoring row must come back untouched.
    """
    market = _Market({"1": [0.40, _stamp(20)]})
    outcomes = [_outcome(1, "Yes", 0.50, 0.05)]
    before = dict(outcomes[0])

    _dated_movement_change(market, outcomes, "Yes", now=NOW)

    assert outcomes[0] == before


# ─── THE CONTRACT BETWEEN THE TWO HALVES ─────────────────────────────────────


def test_the_carrier_and_the_sweep_agree_on_the_window():
    """The producer's constants and the reader's are two records of one rule.

    They live in different modules only because `futures_market_snapshot` may
    not import Celery. A drift here is silent in the worst way: the sweep banks
    a basis the reader then refuses, and every movement caption on the site goes
    quiet with nothing red anywhere.
    """
    from app.tasks import DATED_BASIS_MIN_AGE_HOURS as sweep_min_age
    from app.tasks import MOVEMENT_WINDOW_HOURS as sweep_window

    assert DATED_BASIS_WINDOW_HOURS == sweep_window
    assert DATED_BASIS_MIN_AGE_HOURS == sweep_min_age


def test_the_sweep_imports_the_key_rather_than_retyping_it():
    """One string, two files. A mismatch is a bank nobody can find.

    The sweep INTERPOLATES the key into its SQL (`jsonb_build_object` is
    `VARIADIC "any"`, which asyncpg cannot type-infer from a bare parameter), so
    the only thing holding the two halves together is that the sweep imports
    this constant instead of retyping the literal. That the rendered statement
    then carries it is asserted against the executed SQL in
    `test_movement_window.py`, where the recording rig can see it — `getsource`
    here would only ever read back the f-string template.
    """
    import inspect

    from app import tasks

    source = inspect.getsource(tasks.update_max_movement)
    assert "import DATED_BASIS_METADATA_KEY" in source, (
        "the sweep must import the carrier key from the module the READER "
        "resolves it with, not spell it out a second time"
    )
    assert "bank_key = DATED_BASIS_METADATA_KEY" in source
