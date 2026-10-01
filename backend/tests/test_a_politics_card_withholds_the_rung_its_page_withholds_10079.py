"""A /politics CARD STOPS PRINTING A RUNG ITS OWN PAGE WITHHOLDS — #10079.

Seen at 390px on production 2026-10-01 14:03Z, Gubernatorial section:

    Tim Walz out as Governor of Minnesota?
        Before 2027        6%
        Before February    1%    <- Kalshi …-TWAL-26FEB01: a Feb 1 2026 deadline

`/api/futures/108678` served that leg as `probability: null` in the same
minute: `stale_observation_keys` (#7537) withholds it, because it was last
written 2026-04-13 while its board was written that morning. The card ran only
`expired_ladder_rungs`, which spares a year-less rung past the 180-day
look-back by design. The rungs below are production's, read from
`futures_outcomes` that minute.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

from app.routes.politics import _market_row

NOW = datetime(2026, 10, 1, 14, 5, 0, tzinfo=timezone.utc)

# (name, current_probability, last_updated) — market 108678
WALZ = [
    ("Before 2027", 0.056, "2026-10-01T10:10:31+00:00"),
    ("Before February", 0.010, "2026-04-13T16:45:15+00:00"),
    ("Before July", 0.001, "2026-09-07T06:50:46+00:00"),
    ("Before Sep 1, 2026", 0.0, "2026-10-01T13:40:14+00:00"),
]
# Control — market 11617619, same page, same minute: every rung the card shows
# was written with its board, so nothing it shows may move.
GALLEGO = [
    ("Before Nov 3, 2026", 0.045, "2026-10-01T10:52:39+00:00"),
    ("Before Oct 1, 2026", 0.010, "2026-10-01T10:52:39+00:00"),
    ("Before Jun 1, 2026", 0.0, "2026-08-02T19:34:10+00:00"),
    ("Before Sep 1, 2026", 0.0, "2026-10-01T09:39:51+00:00"),
    ("Before Aug 1, 2026", 0.0, "2026-10-01T09:39:51+00:00"),
]


def _market(rungs, **extra):
    return SimpleNamespace(
        id=1,
        name="Will it happen?",
        source="kalshi",
        external_id="kxtest",
        outcomes=[
            SimpleNamespace(
                id=i + 1,
                name=n,
                current_probability=p,
                probability_change_24h=None,
                rank=None,
                # The ORM column is a datetime, and `stale_observation_keys`
                # reads nothing else as a stamp.
                last_updated=datetime.fromisoformat(t) if t else None,
                is_winner=False,
            )
            for i, (n, p, t) in enumerate(rungs)
        ],
        **extra,
    )


def _names(row):
    return [o["name"] for o in row["top_outcomes"]]


def test_the_walz_card_stops_listing_before_february():
    row = _market_row(_market(WALZ), now=NOW)
    assert _names(row) == ["Before 2027"]
    assert row["prob"] == 5.6


def test_the_withheld_rung_still_counts_toward_the_pages_more_badge():
    # `/futures/108678` keeps the leg on its board (as "More outcomes (1)"),
    # so the badge still promises it; only its PRICE is withheld.
    row = _market_row(_market(WALZ), now=NOW)
    assert row["more_count"] == 1
    assert row["outcome_count"] == 4


def test_control_a_board_observed_together_keeps_every_shown_rung():
    row = _market_row(_market(GALLEGO), now=NOW)
    assert _names(row) == ["Before Nov 3, 2026", "Before Oct 1, 2026"]


def test_a_settled_board_is_a_result_and_withholds_nothing():
    # The page's rule is open-only; a stamp spread on a closed board is history.
    row = _market_row(_market(WALZ, status="resolved"), now=NOW)
    assert "Before February" in _names(row)


def test_a_board_whose_only_current_leg_is_unpriced_is_withdrawn():
    rungs = [
        ("Yes", None, "2026-10-01T10:00:00+00:00"),
        ("No", 0.40, "2026-08-01T10:00:00+00:00"),
    ]
    assert _market_row(_market(rungs), now=NOW) is None


def test_no_readable_stamps_withholds_nothing():
    # No evidence is not evidence of death (#7537): a writer that never sets
    # the column must not blank the card.
    rungs = [(n, p, None) for n, p, _ in WALZ]
    assert "Before February" in _names(_market_row(_market(rungs), now=NOW))


# Market 59693666, production 2026-10-01: four live rungs the poller last wrote
# on 2026-09-10 beside a settled rung written that morning. `/api/futures/`
# serves all four as `probability: null` (`prices_withheld: 4`), so the card
# has no live price to show — and must not fall back to the passed rung.
HARP = [
    ("Before Jan 1, 2027", 0.185, "2026-09-10T06:52:00+00:00"),
    ("Before Dec 1, 2026", 0.115, "2026-09-10T06:52:00+00:00"),
    ("Before Oct 1, 2026", 0.060, "2026-09-10T06:52:00+00:00"),
    ("Before Nov 1, 2026", 0.090, "2026-09-10T06:52:00+00:00"),
    ("Before Sep 1, 2026", 0.0, "2026-10-01T13:00:00+00:00"),
]


def test_a_passed_rung_never_stands_in_for_live_rungs_the_page_withholds():
    assert _market_row(_market(HARP), now=NOW) is None


def test_control_a_ladder_whose_rungs_have_all_passed_keeps_them():
    # #9109's "never the whole board" is unchanged: nothing is withheld here
    # (one stamp), every rung has passed, and the card still shows them.
    rungs = [
        ("Before Aug 1, 2026", 0.02, "2026-10-01T10:00:00+00:00"),
        ("Before Sep 1, 2026", 0.03, "2026-10-01T10:00:00+00:00"),
    ]
    assert _names(_market_row(_market(rungs), now=NOW)) == [
        "Before Sep 1, 2026",
        "Before Aug 1, 2026",
    ]
