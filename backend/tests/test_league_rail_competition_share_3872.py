"""One competition may not take the whole rail — #3872.

── WHAT A PERSON SAW ──

`/sport/tennis/atp`, production, phone width, 2026-09-08 08:1xZ, during the US
Open men's semi-finals. LIVE & UPCOMING was eight cards and every one of them
was an ATP Challenger or ITF match — Derepasko–Ryan Ziegann, Sach–Truong,
Bax–Jones, Purcell–Pacheco Mendez, O'Connell–Ellis, Cuong–Weber, Samrej–Rawat,
Vishal Balsekar–Shimizu — seven of the eight priced 99%/1%, all eight carrying
NULL scores. Then "Showing the next 8 — more exist."

Shelton–Alcaraz, a US Open semi-final commencing that day at 18:30Z, was not on
the page. Neither was Zverev, nor Khachanov, nor Tiafoe–Michelsen.

This is the second half of #3677. That ship widened all three rails to the
tour's tournament keys and fixed the RESULTS rail — both tour pages now carry
real US Open finals — and it could not fix this one, because the defect here is
ordering and not scope. Measured in the rail's own candidate window that hour:

    feeder-circuit rows (Challenger/ITF)   12 live, 82 scheduled
    everything else                         0 live, 15 scheduled

Nothing had gone wrong. The Challengers at Phan Thiet and Shanghai genuinely
started at 06:00–07:10Z and the Slam hours later, so `live_first_order` handed
them all eight slots exactly as designed. It is the RULE that is wrong, and it
is the same sentence #3640 already wrote for `/hub/tennis`: a clock is not a
reason to bury the tournament during the tournament.

── WHY NOT THE MECHANISM #3640 ALREADY SHIPPED ──

`is_tennis_feeder_circuit` names the Challenger circuit from venue-stated text
and the hub sorts on it. It was the first thing tried here and it is not enough
on its own, for two reasons that only show up on this surface:

* The hub's tier key sorts INSIDE the live band, deliberately, so that a live
  Challenger still leads a Slam match that has not started. On the hub that cost
  nothing. Here it fixes nothing at all: on 09-08 the Challengers WERE the live
  band and the Slam was entirely scheduled, so a key that only reorders within
  "live" leaves all eight slots exactly where they were.
* Demoting the feeder circuit by a tuned cap still missed the specimen. Behind
  the twelve Challengers sat six US Open DOUBLES matches all stamped 18:00Z,
  ahead of Shelton–Alcaraz at 18:30Z. Caps of 5, 4 and 3 were each checked
  against the measured population and every one of them spent the slots it
  freed on doubles. A cap tuned until one specimen appears is tuned to one day.

So the rule carries no tuned number: each competition in play may take an EQUAL
SHARE, `limit // competitions`, and the remainder is backfilled in the rail's
own order. On the measured population that is 8 // 4 = 2 apiece.

── WHY IT CANNOT REACH MLB, THE NFL OR NCAAF ──

Measured on the same pass, across every league's rail window:

    tennis_atp             105 events, 105 with a competition, 9 distinct
    tennis_wta              17          17                     4
    americanfootball_ncaaf  93          61                     1
    baseball_mlb           104          49                     1
    americanfootball_nfl    32          32                     1
    every soccer league   ~500           0                     0

MLB and NCAAF name ONE competition and leave half their rows unnamed, so a rule
that thinned the named group there would promote unnamed rows over named ones
on pages nobody has complained about. With one competition there is no share to
take and the rule returns the rail untouched by identity — the guard below
asserts that against the real shapes, not against a mock.

The per-league opt-in is belt AND braces, and deliberately so: inert-by-identity
is a property of today's data, while the opt-in is a property of the decision.
MMA and boxing are absent from it in #3640's words — a UFC prelim is on the card
the reader came for.

── WHAT IS NOT FIXED HERE ──

The twins. `Shelton / Alcaraz` and `Ben Shelton / Carlos Alcaraz` are two event
rows for one match (15306391 and 15306813), as are the two Zverevs and the two
Khachanovs. That is #2693/#2878 and lane1's under D39. This changes no event row
and merges nothing; `not_a_proven_duplicate()` keeps the proven pairs off the
rail and the rest stay visible, which is the honest state until the write side
is repaired.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.dialects import postgresql

from app.routes.league_futures import (
    RAIL_COMPETITION_SCAN_DEPTH,
    RAIL_COMPETITION_SHARE_LEAGUES,
    UPCOMING_GAMES_LIMIT,
    upcoming_games_query,
)
from app.utils.rail_competition_share import equal_share_by_competition

NOW = datetime(2026, 9, 8, 8, 30, tzinfo=timezone.utc)


@dataclass
class Row:
    """A rail candidate, carrying only what the share reads."""

    name: str
    competition: str | None = None


def _share(rows, limit=UPCOMING_GAMES_LIMIT):
    return equal_share_by_competition(
        rows, limit=limit, competition_of=lambda r: r.competition
    )


def _names(rows):
    return [r.name for r in rows]


# ---------------------------------------------------------------------------
# the specimen: the ATP rail as production actually held it on 2026-09-08
# ---------------------------------------------------------------------------

#: Natural order — `live_first_order` then `commence_time` — as measured. The
#: twelve live Challengers first, then the scheduled rows by kickoff. Trimmed to
#: the shape that decides the outcome; the real window held 94 feeder rows.
PHAN = "ATP Challenger Phan Thiet 3"
SHANGHAI = "ATP Challenger Shanghai"
DOUBLES = "US Open Men Doubles"
SINGLES = "US Open Men Singles"

ATP_20260908 = [
    Row("bax-jones", PHAN),
    Row("derepasko-ziegann", PHAN),
    Row("sach-truong", PHAN),
    Row("purcell-pacheco", PHAN),
    Row("oconnell-ellis", PHAN),
    Row("cuong-weber", SHANGHAI),
    Row("samrej-rawat", SHANGHAI),
    Row("balsekar-shimizu", SHANGHAI),
    Row("tiafoe-michelsen", None),
    Row("carpico-ram", DOUBLES),
    Row("miedler-arevalo", DOUBLES),
    Row("nys-andreozzi", DOUBLES),
    Row("gonzalez-granollers", DOUBLES),
    Row("heliovaara-cabral", DOUBLES),
    Row("krawietz-cash", DOUBLES),
    Row("shelton-alcaraz", SINGLES),
    Row("schnaitter-harrison", DOUBLES),
    Row("bolelli-krajicek", DOUBLES),
]


def test_the_us_open_semi_final_reaches_the_rail():
    """THE ship. Shelton–Alcaraz was on no page; now it is on this one."""
    assert "shelton-alcaraz" in _names(_share(ATP_20260908))


def test_the_challenger_circuit_no_longer_takes_every_slot():
    chosen = _share(ATP_20260908)
    feeder = [r for r in chosen if r.competition in (PHAN, SHANGHAI)]
    assert len(chosen) == UPCOMING_GAMES_LIMIT
    assert len(feeder) == 4, _names(chosen)


def test_the_doubles_do_not_take_the_slots_the_challengers_gave_up():
    """The half a tuned cap kept getting wrong."""
    chosen = _share(ATP_20260908)
    assert len([r for r in chosen if r.competition == DOUBLES]) == 2, _names(chosen)


def test_the_rail_still_leads_with_what_is_being_played():
    """`live_first_order` is untouched: the live Challengers still come first."""
    assert _names(_share(ATP_20260908))[0] == "bax-jones"


def test_every_competition_in_play_is_represented():
    chosen = _share(ATP_20260908)
    assert {r.competition for r in chosen} == {PHAN, SHANGHAI, DOUBLES, SINGLES, None}


# ---------------------------------------------------------------------------
# the rule
# ---------------------------------------------------------------------------


def test_the_share_is_an_equal_split_of_the_rail():
    rows = [Row(f"{c}-{i}", c) for c in "abcd" for i in range(5)]
    chosen = _share(rows)
    assert len(chosen) == 8
    for c in "abcd":
        assert len([r for r in chosen if r.competition == c]) == 2


def test_the_rail_order_survives_the_share():
    """Selection only decides WHICH rows, never where they sit."""
    chosen = _share(ATP_20260908)
    positions = [ATP_20260908.index(r) for r in chosen]
    assert positions == sorted(positions)


def test_an_unnamed_row_is_never_held_back():
    """`None` is the absence of evidence, not a group to be shared out.

    ``one`` is capped at its share of 4 and rows 5 and 6 are held; every unnamed
    row behind them is still taken, in order, without ever being counted.
    """
    rows = (
        [Row(f"x{i}", "one") for i in range(6)]
        + [Row(f"n{i}") for i in range(3)]
        + [Row("y", "two")]
    )
    assert _names(_share(rows)) == ["x0", "x1", "x2", "x3", "n0", "n1", "n2", "y"]


# ---------------------------------------------------------------------------
# the directions a diversity cap gets wrong (gotcha #43, #1091)
# ---------------------------------------------------------------------------


def test_a_single_competition_rail_is_returned_untouched():
    """MLB, the NFL, NCAAF. Byte-identical to the pre-#3872 answer."""
    rows = [Row(f"g{i}", "MLB") for i in range(20)]
    assert _share(rows) == rows[:UPCOMING_GAMES_LIMIT]


def test_a_league_that_names_nothing_is_returned_untouched():
    """Every soccer league: 0 rows carry a competition."""
    rows = [Row(f"g{i}") for i in range(20)]
    assert _share(rows) == rows[:UPCOMING_GAMES_LIMIT]


def test_one_named_competition_beside_unnamed_rows_is_untouched():
    """NCAAF's real shape — 61 of 93 named, and all one name."""
    rows = [Row(f"named{i}", "NCAAF") for i in range(6)] + [
        Row(f"bare{i}") for i in range(6)
    ]
    assert _share(rows) == rows[:UPCOMING_GAMES_LIMIT]


def test_the_share_never_empties_the_rail():
    """The flood is capped AND the surface stays populated — both directions."""
    rows = [Row(f"a{i}", "a") for i in range(12)] + [Row("b0", "b")]
    chosen = _share(rows)
    assert len(chosen) == UPCOMING_GAMES_LIMIT
    assert "b0" in _names(chosen)


def test_a_backfilled_row_lands_in_the_rails_order_not_at_the_end():
    rows = [Row(f"a{i}", "a") for i in range(12)] + [Row("b0", "b")]
    assert _names(_share(rows)) == [
        "a0",
        "a1",
        "a2",
        "a3",
        "a4",
        "a5",
        "a6",
        "b0",
    ]


def test_a_short_rail_keeps_every_row():
    rows = [Row("a0", "a"), Row("b0", "b")]
    assert _share(rows) == rows


def test_a_zero_limit_takes_nothing():
    assert _share(ATP_20260908, limit=0) == []


# ---------------------------------------------------------------------------
# the wiring
# ---------------------------------------------------------------------------


def _sql(query) -> str:
    return str(query.compile(dialect=postgresql.dialect()))


def test_a_league_that_does_not_share_compiles_the_statement_it_always_did():
    """LAT-P110's block table is a claim about an exact statement.

    Both halves, because either alone can pass while the page is wrong: the
    league must be out of the opt-in AND the default must still be the bare cap.
    """
    for key in ("baseball_mlb", "americanfootball_nfl", "soccer_epl"):
        assert key not in RAIL_COMPETITION_SHARE_LEAGUES
        assert upcoming_games_query(key, NOW)._limit == UPCOMING_GAMES_LIMIT + 1
        assert _sql(upcoming_games_query(key, NOW)) == _sql(
            upcoming_games_query(key, NOW, scan_depth=0)
        )


def test_an_opted_in_rail_scans_past_its_cap():
    deep = upcoming_games_query(
        "tennis_atp", NOW, scan_depth=RAIL_COMPETITION_SCAN_DEPTH
    )
    assert deep._limit == UPCOMING_GAMES_LIMIT + 1 + RAIL_COMPETITION_SCAN_DEPTH
    assert upcoming_games_query("tennis_atp", NOW)._limit == UPCOMING_GAMES_LIMIT + 1


def test_the_scan_clears_the_measured_wall():
    """12 live feeder rows stood between the cap and the first US Open row."""
    assert RAIL_COMPETITION_SCAN_DEPTH >= 24


def test_only_the_tennis_tours_opt_in():
    assert RAIL_COMPETITION_SHARE_LEAGUES == {"tennis_atp", "tennis_wta"}


def test_the_combat_sports_are_left_alone():
    """#3640: a UFC prelim is on the card the reader came for."""
    for key in ("mma_mixed_martial_arts", "boxing_boxing"):
        assert key not in RAIL_COMPETITION_SHARE_LEAGUES
