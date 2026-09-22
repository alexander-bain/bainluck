"""#2427 — the three themed dashboards stop answering a question with "Yes / No".

THE SHIP: a reader on `/entertainment`, `/politics` or `/economics` stops seeing
a Polymarket `_yes`/`_no` leg rendered as if it were one of the named answers to
the card's own question.

Measured on production 2026-09-22 13:50Z — `/api/entertainment` card 61858010,
*"What will MrBeast say during his next gaming YouTube video?"* — served:

    Prize   51%
    Yes     51%
    No      50%

off a 14-rung ladder. `futures_outcomes` for that market holds
``0xe54e…172e`` "Prize" 0.505 beside ``0xe54e…172e_no`` "No" 0.495 and
``0xe54e…172e_yes`` "Yes" 0.505: three rows describing one condition, which is
exactly the shape `drop_duplicate_legs` (#2434) was written for and has removed
in `routes/feed.py`, `routes/futures.py` and `routes/events.py` since
2026-08-31.

🔴 THE FIX WAS NOT ABSENT, IT WAS UNWIRED. The defect matched the shipped fix's
own discriminator 449-for-449 across the open Polymarket population, and
`grep -c drop_duplicate_legs` per route file read 4 / 8 / 1 for feed, futures and
events and **0 / 0 / 0** for politics, entertainment and economics. So this ship
is call sites, not a new rule — and this file guards the WIRING, because a rule
that is correct everywhere and reachable nowhere is what #2427 already was.

WHAT THIS FILE PINS

  1. the production specimen renders its real rungs, asserted as an equality on
     the served names — never as "No is gone", which an empty list satisfies;
  2. the row is STILL SERVED and its `outcome_count` falls 14 → 12. A vanished
     card satisfies every "the wrong row went away" assertion as happily as a
     repair does;
  3. a CONTROL proving the specimen actually exercises the defect — through the
     bare `clean_outcomes` the routes used to call, "Yes" and "No" DO take the
     card. Without this the specimen could be healthy and every assertion above
     would pass vacuously;
  4. 🔴 the other direction — a correctly decomposed sub-market, whose only rows
     ARE `_yes`/`_no` and which has no bare twin, keeps both legs. This is the
     arm that stops the fix deleting working markets;
  5. 🔴 the Kalshi population is UNTOUCHED, explicitly. The nine Kalshi rows on
     these same pages carry plain tickers with no `_yes` suffix and no stripped
     twin; they are a real unlabelled terminal leg inside a date ladder, a
     different defect with its own row, and widening this predicate to reach
     them is what `drop_duplicate_legs`' second condition forbids;
  6. a row whose `external_id` is NULL survives — it cannot be PROVEN a
     duplicate, and the column is nullable;
  7. REACH — the two seams, derived from the module source rather than trusted.
     `economics.py` reads outcomes through `_outcomes_sorted` at twelve call
     sites that never touch `_clean_outcomes`, so wiring the alias alone would
     have left that page almost entirely unfixed.
"""

from __future__ import annotations

import ast
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.models import FuturesMarket, FuturesOutcome
from app.utils.cross_source_matching import (
    clean_and_dedupe_outcomes,
    clean_outcomes,
)

BACKEND = Path(__file__).resolve().parents[1]
ROUTES = BACKEND / "app" / "routes"
THEMED = ("politics.py", "entertainment.py", "economics.py")

# The production specimen, verbatim from market 61858010.
PRIZE = "0xe54e3becc75a156b1ee6f740268d0b7232ae96e632d23ac0494316a29f90172e"

#: Every row on market 61858010 the same minute the payload was read, as
#: ``(external_id, name, current_probability)``. The last two are the duplicate
#: legs of the first.
MRBEAST_ROWS: list[tuple[str, str, float]] = [
    (PRIZE, "Prize", 0.505),
    ("0x0c96…b525", "Build", 0.48),
    ("0x1b62…4f37", "Minecraft", 0.475),
    ("0x9199…2291", "Contestant", 0.22),
    ("0xddda…2a03", "Fight", 0.105),
    ("0x76b5…e89a", "Chandler", 0.085),
    ("0xc3d4…f180", "Dream", 0.08),
    ("0x2e6b…54f4", "GTA / Grand Theft Auto", 0.075),
    ("0xb742…f65b", "Chameleon", 0.075),
    ("0xd630…34d6", "Race", 0.075),
    ("0x3580…fa6a", "Karl", 0.04),
    ("0xb8ba…2d9c", "-No Qualifying Event-", 0.02),
    (f"{PRIZE}_no", "No", 0.495),
    (f"{PRIZE}_yes", "Yes", 0.505),
]


def _market(
    rows: list[tuple[str, str, float | None]],
    *,
    name: str = "What will MrBeast say during his next gaming YouTube video?",
    mid: int = 61858010,
    source: str = "polymarket",
) -> FuturesMarket:
    """A real `FuturesMarket` carrying real `FuturesOutcome` rows.

    Real ORM objects rather than stand-ins, for the reason the #6696 guard
    states: these builders read `.source` and `.rank` as well as `.name`, and a
    double carrying only today's fields turns tomorrow's column read into an
    AttributeError in the guard instead of a finding in the code.
    """
    market = FuturesMarket(id=mid, name=name, source=source)
    market.outcomes = [
        FuturesOutcome(
            name=n, external_id=eid, current_probability=p, rank=i
        )
        for i, (eid, n, p) in enumerate(rows)
    ]
    return market


def _names(outcomes) -> list[str]:
    return [o.name for o in outcomes]


# --------------------------------------------------------------------------
# 3. The control — the specimen really does carry the defect
# --------------------------------------------------------------------------


def test_control_the_bare_filter_lets_yes_and_no_take_the_card():
    """🔴 Without this, every assertion below could pass on a healthy fixture.

    `clean_outcomes` is what the three routes called before this ship. Through
    it, sorted the way the row builders sort, the top three of market 61858010
    are the card a reader complained about.
    """
    market = _market(MRBEAST_ROWS)
    top = sorted(
        clean_outcomes(market.outcomes),
        key=lambda o: float(o.current_probability or 0),
        reverse=True,
    )[:3]
    assert _names(top) == ["Prize", "Yes", "No"]


# --------------------------------------------------------------------------
# 1 + 2. The ship, on the seam all three routes now pass through
# --------------------------------------------------------------------------


def test_the_duplicate_legs_leave_the_ladder():
    market = _market(MRBEAST_ROWS)
    kept = clean_and_dedupe_outcomes(market.outcomes)

    assert "Yes" not in _names(kept)
    assert "No" not in _names(kept)
    # An equality, not an absence: the twelve real rungs are all still here and
    # in their original order.
    assert _names(kept) == [n for _, n, _ in MRBEAST_ROWS[:12]]


def test_the_card_still_names_a_leader_and_real_rungs():
    """The row is repaired, not withdrawn."""
    market = _market(MRBEAST_ROWS)
    top = sorted(
        clean_and_dedupe_outcomes(market.outcomes),
        key=lambda o: float(o.current_probability or 0),
        reverse=True,
    )[:3]
    assert _names(top) == ["Prize", "Build", "Minecraft"]


def test_the_ladders_arity_falls_by_exactly_the_two_legs():
    market = _market(MRBEAST_ROWS)
    assert len(market.outcomes) == 14
    assert len(clean_and_dedupe_outcomes(market.outcomes)) == 12


# --------------------------------------------------------------------------
# 4 + 5 + 6. The directions the fix must NOT reach
# --------------------------------------------------------------------------


def test_a_decomposed_sub_market_keeps_both_its_legs():
    """🔴 The arm that stops this fix deleting working markets.

    The ordinary Polymarket sub-market shape is `_yes`/`_no` and NOTHING else —
    no bare twin. Those two rows are the real outcomes. Suppressing on the
    suffix alone would empty every such card on all three pages.
    """
    rows = [(f"{PRIZE}_yes", "Yes", 0.62), (f"{PRIZE}_no", "No", 0.38)]
    kept = clean_and_dedupe_outcomes(_market(rows).outcomes)
    assert _names(kept) == ["Yes", "No"]


def test_the_kalshi_date_ladder_is_untouched():
    """🔴 The explicit non-widening arm — the nine Kalshi rows are NOT this fix.

    A Kalshi rung carries a plain ticker: no `_yes` suffix, and no bare sibling
    to strip to. `KXAMBMALAY-26JAN06-JAN01`'s terminal unlabelled leg is a real
    defect on these pages and it is a DIFFERENT one, with its own row. If this
    test ever fails, the predicate has been widened past its evidence.
    """
    rows = [
        ("KXAMBMALAY-26JAN06-JAN01", "Jan 1", 0.12),
        ("KXAMBMALAY-26JAN06-JAN08", "Jan 8", 0.30),
        ("KXAMBMALAY-26JAN06", "", 0.58),
    ]
    kept = clean_and_dedupe_outcomes(_market(rows, source="kalshi").outcomes)
    assert len(kept) == 3


def test_a_row_with_no_external_id_survives():
    """The column is nullable; an unreadable id cannot PROVE a duplicate."""
    rows = [(None, "Unknown", 0.4), (PRIZE, "Prize", 0.5), (f"{PRIZE}_yes", "Yes", 0.5)]
    kept = clean_and_dedupe_outcomes(_market(rows).outcomes)
    assert _names(kept) == ["Unknown", "Prize"]


def test_a_row_object_without_the_attribute_at_all_does_not_raise():
    """🔴 `getattr` with a default, not `o.external_id` — and this is the ONLY
    test in this file that can see the difference.

    The test above passes either way: a real `FuturesOutcome` always HAS the
    attribute, it is merely `None`. The rule only bites on a row object that
    does not carry the column at all, which is what the reduced stand-ins
    across the existing `politics`/`entertainment`/`economics` suites are —
    severing the default turns 251 of them from assertions about this page into
    `AttributeError`s, which is a guard failing for the wrong reason.

    A reduced fixture that does not carry the attribute must mean UNKNOWN, not
    raise; `routes/feed.py` states the same rule for the same shape.
    """
    from types import SimpleNamespace

    rows = [
        SimpleNamespace(name="Prize", current_probability=0.5),
        SimpleNamespace(name="Build", current_probability=0.4),
    ]
    assert _names(clean_and_dedupe_outcomes(rows)) == ["Prize", "Build"]


# --------------------------------------------------------------------------
# The three routes, through their own row builders
# --------------------------------------------------------------------------


def test_entertainment_row_stops_printing_yes_and_no():
    from app.routes.entertainment import _market_row

    row = _market_row(_market(MRBEAST_ROWS), max_outcomes=3)
    assert row is not None, "the card must be repaired, not withdrawn"
    assert [o["name"] for o in row["top_outcomes"]] == ["Prize", "Build", "Minecraft"]
    assert row["outcome_count"] == 12


def test_politics_row_stops_printing_yes_and_no():
    from app.routes.politics import _market_row

    row = _market_row(
        _market(MRBEAST_ROWS, name="Which party will control the Senate?"),
        now=datetime(2026, 9, 22, tzinfo=timezone.utc),
    )
    assert row is not None, "the card must be repaired, not withdrawn"
    names = [o["name"] for o in row["top_outcomes"]]
    assert "Yes" not in names and "No" not in names
    assert names[0] == "Prize"


def test_economics_second_seam_dedupes():
    """`_outcomes_sorted`, the seam `_clean_outcomes` does not cover.

    Twelve call sites in `economics.py` — the ladder and partition builders and
    `_render_multi_outcome`, which renders every market `_market_row` refuses
    above five outcomes — read outcomes through here.
    """
    from app.routes.economics import _outcomes_sorted

    kept = _outcomes_sorted(_market(MRBEAST_ROWS))
    assert "Yes" not in _names(kept)
    assert "No" not in _names(kept)
    assert len(kept) == 12


def test_economics_row_stops_printing_yes_and_no():
    from app.routes.economics import _market_row

    # Four real rungs plus the pair — six raw, which is over `_market_row`'s
    # five-outcome ceiling and would fall through to `_render_multi_outcome`
    # undeduped. Deduped it is a four-rung row this builder serves.
    rows = [
        (PRIZE, "Above 3%", 0.505),
        ("0xaaa1", "2 to 3%", 0.30),
        ("0xaaa2", "1 to 2%", 0.12),
        ("0xaaa3", "Below 1%", 0.075),
        (f"{PRIZE}_yes", "Yes", 0.505),
        (f"{PRIZE}_no", "No", 0.495),
    ]
    # This builder names ONE leg rather than a rung list (#6696's seam: the
    # number, the name and the `market_id` all read a single object), so the
    # assertion is on the leg it chose.
    row = _market_row(_market(rows, name="What will CPI print in December?"))
    assert row is not None, "the card must be repaired, not withdrawn"
    assert row["leader"] not in ("Yes", "No")
    assert row["leader"] == "Above 3%"
    assert row["prob"] == 50.5


# --------------------------------------------------------------------------
# 7. REACH — the wiring, derived from the source
# --------------------------------------------------------------------------


@pytest.mark.parametrize("filename", THEMED)
def test_the_themed_route_imports_the_deduping_pair(filename: str):
    """🔴 The half that earns its place — #2427 WAS a correct, unreachable rule.

    Read off the import statement rather than a hand-kept list, so re-pointing
    the alias back at bare `clean_outcomes` fails here instead of silently
    restoring the defect on a page nobody re-shot.
    """
    tree = ast.parse((ROUTES / filename).read_text())
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module == "app.utils.cross_source_matching"
        for alias in node.names
    }
    assert "clean_and_dedupe_outcomes" in imported, (
        f"{filename} no longer routes its outcome reads through the deduping "
        "pair — #2427's duplicate legs are back on that page"
    )
    assert "clean_outcomes" not in imported, (
        f"{filename} imports the bare filter, which does not dedupe"
    )
