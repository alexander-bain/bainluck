"""#7429 — on a COUNT market the bare number is the answer, not a placeholder.

Mystery-shopping `/politics` at 390px (standing notice 4 / D48), 2026-09-20. The
whole ranked outcome list on `https://bainluck.com/futures/25923847` — **"How
many Senate seats will Republicans hold after the Midterms?"**, an open market on
the flagship midterms question:

     1  E48        13%
     2  E49        13%
     3  E50        13%
     4  E47        12%
     5  E51         9%
     6  E46         7%
     7  Below 45    7%     <- the only legible row
     8  E52         6%
     9  E45         4%
    10  E53         4%
    11  E54         3%

12 of 13 rows are a raw Kalshi ticker segment; the chart legend on the same page
reads `E49 · E50 · E48`. `Below 45` at rank 7 is the tell — two labelling paths
in one list, and only one produced a word.

WHAT THE VENUE ACTUALLY SERVES (Kalshi's own `/markets`, standing notice 26,
read 2026-09-20 before any claim was made):

    KXDSENATESEATS-29-E52   yes_sub_title="52"        <- we stored "E52"
    KXDSENATESEATS-29-E48   yes_sub_title="48"        <- we stored "E48"
    KXDSENATESEATS-29-A56   yes_sub_title="Above 56"  <- we stored it, correctly
    KXDSENATESEATS-29-B45   yes_sub_title="Below 45"  <- we stored it, correctly

and across the whole live `KXHOUSEWINSTATE` series, 84 open markets, 54 with an
`-E<n>` ticker, EVERY one serving a bare-number `yes_sub_title`.

THE MECHANISM is one arm of the same regex #4246 narrowed, landing one rung
further down. `_GENERIC_OUTCOME_PATTERNS` ends with a standalone `[0-9]+$`, so
`_is_generic_outcome_name("52")` is True; the subtitle is absent; the title is a
question and #4246 refuses it; and the ladder hands back the ticker. This is NOT
#4064 (that is the `Team {SUFFIX}` arm landing on the title) and NOT #4316 (the
collision resolver correctly never fires here — step 6 gives each leg a
*distinct* unreadable name, so no group collides).

Population, keyed on `external_id` and not on the display name: 252 rows / 149
markets store the raw `E<n>` leg, of which **114 rows on 24 open markets**, every
one a count question. (Keying on `name ~ '^[A-Z][0-9]+$'` instead sweeps in the
esports orgs `T1`, `G2`, `M80` and `F1` — the label is not the instrument.)

THE FIX IS TWO INDEPENDENT LOCKS, the shape `outcome_display_names` (#4151)
establishes: only-digits label AND a ticker whose final segment is `-E<those
exact digits>`. The venue has to say the same number twice, in two
independently-authored fields, so the ladder can never assert what the venue did
not. The failure direction is one-way — an unrecognised shape keeps the ladder's
answer — which is why the older `-FLD-7-7` ticker format is deliberately left to
step 6, where it already reads correctly.

The poll rewrites `name` on conflict (#4246), so this drains without a backfill.
"""

import json
import pathlib

import pytest

from app.services.kalshi_api import KalshiMarket
from app.tasks.kalshi import (
    _exact_count_label,
    _is_generic_outcome_name,
    _kalshi_outcome_name,
    kalshi_outcome_names,
)

_VENUE = (
    pathlib.Path(__file__).parent / "fixtures" / "kalshi_KXDSENATESEATS_29_7429.json"
)


def _market(ticker: str, title: str, **kw) -> KalshiMarket:
    """A real `KalshiMarket`, so the fixture cannot drift from the parser."""
    return KalshiMarket(
        ticker=ticker,
        event_ticker=ticker.rsplit("-", 1)[0],
        title=title,
        status="active",
        **kw,
    )


def _seat_market(n: int) -> KalshiMarket:
    """One `exactly n seats` leg, exactly as Kalshi serves it."""
    return _market(
        f"KXDSENATESEATS-29-E{n}",
        f"Will the Democratic party hold exactly {n} Senate seats "
        f"in the 121st Congress?",
        yes_sub_title=str(n),
        no_sub_title=str(n),
    )


# ── the defect itself ─────────────────────────────────────────────────────


def test_the_midterms_senate_card_names_its_seat_counts():
    """The row the reader could not read: `E52` must be `52`."""
    assert (
        _kalshi_outcome_name(
            "Democratic Senate Seat Count (2028)", _seat_market(52), 14
        )
        == "52"
    )


def test_no_row_on_the_seat_count_card_is_a_raw_ticker_leg():
    """The card read as a whole — the assertion the issue names as the guard."""
    markets = [_seat_market(n) for n in range(45, 57)] + [
        _market(
            "KXDSENATESEATS-29-A56",
            "Will the Democratic party hold more than 56 Senate seats "
            "in the 121st Congress?",
            yes_sub_title="Above 56",
            no_sub_title="Above 56",
        ),
        _market(
            "KXDSENATESEATS-29-B45",
            "Will the Democratic party hold fewer than 45 Senate seats "
            "in the 121st Congress?",
            yes_sub_title="Below 45",
            no_sub_title="Below 45",
        ),
    ]
    names = kalshi_outcome_names("Democratic Senate Seat Count (2028)", markets)

    raw = {t: n for t, n in names.items() if n.startswith("E") and n[1:].isdigit()}
    assert raw == {}, f"rows still wearing their ticker leg: {raw}"

    # and the two rows that were ALREADY right are untouched — the regression
    # this fix could plausibly cause.
    assert names["KXDSENATESEATS-29-A56"] == "Above 56"
    assert names["KXDSENATESEATS-29-B45"] == "Below 45"

    # a name that cannot tell two rows apart is not a name (#4316's invariant)
    assert len(set(names.values())) == len(markets)


def test_the_whole_card_replays_from_the_venues_own_bytes():
    """The 14 markets Kalshi served for `KXDSENATESEATS-29`, captured verbatim.

    A hand-built fake can go wrong in a way that makes a helper take its
    unresolved branch, which reads exactly like a principled refusal — so the
    specimen here is the venue's own response body.
    """
    served = json.loads(_VENUE.read_text())["markets"]
    assert len(served) == 14, "fixture drifted from the captured venue response"

    markets = [
        _market(
            m["ticker"],
            m["title"],
            yes_sub_title=m.get("yes_sub_title"),
            no_sub_title=m.get("no_sub_title"),
        )
        for m in served
    ]
    names = kalshi_outcome_names("Democratic Senate Seat Count (2028)", markets)

    assert sorted(names.values(), key=lambda s: (not s[0].isdigit(), s)) == [
        "45",
        "46",
        "47",
        "48",
        "49",
        "50",
        "51",
        "52",
        "53",
        "54",
        "55",
        "56",
        "Above 56",
        "Below 45",
    ]


# ── the equality is load-bearing, and the failure direction is one-way ─────
#
# An earlier draft asserted an `isdigit()` pre-check as a separate "lock". Its
# mutant survived all eleven tests — `leg.group(1)` is `[0-9]+`, so the equality
# below already implies the label is only digits. The branch was removed rather
# than kept with a test that could not kill it.


@pytest.mark.parametrize(
    "ticker,label,why",
    [
        ("KXSOMEFIELD-26-ALPHA", "1", "uncorroborated ordinal — could be obfuscation"),
        ("KXDSENATESEATS-29-E52", "51", "both present, but they disagree"),
        ("KXDSENATESEATS-29-A56", "Above 56", "not a count leg; step 3 handles it"),
        ("KXDSENATESEATS-29-E52", "", "no label at all"),
        ("KXDSENATESEATS-29-E52", "052", "same value, not the same string"),
        ("KXHOUSEWINSTATE-E52-FLD", "52", "`-E<n>` mid-ticker is not the LEG"),
    ],
)
def test_the_venue_must_say_the_same_number_twice(ticker, label, why):
    """Anything short of an exact agreement falls through to the ladder."""
    assert _exact_count_label(_market(ticker, "…", yes_sub_title=label)) is None, why


def test_the_older_bare_number_ticker_format_is_deliberately_untouched():
    """`KXHOUSEWINSTATE-FLD-7-7` already reaches the reader as `7`.

    Widening the lock to match it would buy nothing and risk something, so the
    one-way failure keeps it on the ladder — and it must still come out `7`.

    🔴 THE LADDER ALONE IS NOT THE PATH THIS TAKES. In isolation
    `_kalshi_outcome_name` returns `Fld` here: step 6's parser walks backwards
    past every purely-numeric segment (`-7-7`) and lands on the state code. All
    seven legs therefore collapse to one string, collide, and #4316's resolver
    re-derives them from `_ticker_leg` — which for THIS format is the bare
    number. So the assertion has to be made on `kalshi_outcome_names`, the
    function the poll actually calls; asserting the single-leg helper would have
    tested a string no reader ever sees.
    """
    legs = [
        _market(
            f"KXHOUSEWINSTATE-FLD-{n}-{n}",
            "How many House seats will Democrats win in Florida?",
            yes_sub_title=str(n),
            no_sub_title=str(n),
        )
        for n in range(4, 11)
    ]
    assert all(_exact_count_label(m) is None for m in legs)

    names = kalshi_outcome_names(
        "How many House seats will Democrats win in Florida?", legs
    )
    assert names["KXHOUSEWINSTATE-FLD-7-7"] == "7"
    assert sorted(names.values(), key=int) == ["4", "5", "6", "7", "8", "9", "10"]


def test_a_single_market_event_still_says_yes():
    """Step 1 outranks the new step 2 — a lone leg is a Yes/No question."""
    assert _kalshi_outcome_name("Will X happen?", _seat_market(52), 1) == "Yes"


# ── the regex arm this is built on top of is unchanged ────────────────────


@pytest.mark.parametrize("label", ["52", "7", "0"])
def test_the_generic_regex_still_calls_a_bare_number_generic(label):
    """The fix routes AROUND the arm rather than widening it.

    Deleting `|[0-9]+$` outright would let a bare number win step 3 on every
    market, corroborated or not. This asserts the blast radius stayed closed:
    the arm still fires, and only `_exact_count_label` overrides it.
    """
    assert _is_generic_outcome_name(label) is True
