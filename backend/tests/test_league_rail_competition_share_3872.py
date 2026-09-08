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

── THE RULE, AND THE TWO THINGS PRODUCTION TAUGHT IT ──

Each competition in play may take an EQUAL SHARE of the rail,
`limit // competitions`, and the remainder is backfilled in the rail's own
order. No tuned number: a cap tuned until one specimen appears is tuned to one
day, and caps of 5, 4 and 3 were each tried and each spent the slots they freed
on the six US Open DOUBLES matches stamped 18:00Z, ahead of Shelton–Alcaraz at
18:30Z.

Both of the following were found by REPLAYING the rule on production's own rows,
and neither was visible in a hand-written fixture. They are the reason that
pre-flight is part of this ship and not a nicety.

1. **The feeder circuit has to be ONE group.** Shared out per tournament it is
   not thinned, it is SUBDIVIDED: the window held SEVEN separate Challenger
   draws, so the unfolded share is 8 // 9 = 0 → 1 and the circuit takes seven of
   the eight slots one draw at a time. Replayed on the real rows, unfolded gives
   Bax–Jones, Ymer–Kotov, Tobon–Kirci, Added–Masur, Kolar–Wallin, Seyboth
   Wild–Ferrari, Sanchez Jover–Bueno and Tiafoe — no Shelton–Alcaraz.
   `is_tennis_feeder_circuit`, #3640's own venue-stated predicate, is what says
   which matches fold together. So the mechanism the hub already ships is not
   bypassed here; it is what makes the share work.
2. **The scan must be sized against the RANK of the row that must appear**, not
   against the wall in front of it. The first guess was 24 — three times the
   twelve LIVE Challenger rows — and reached no US Open row at all, because the
   wall is every Challenger SCHEDULED before the Slam's first ball.

Folded, with the scan deep enough: 3 groups, share 2, and the rail becomes two
live Challengers, Tiafoe–Michelsen, two US Open doubles, Shelton–Alcaraz, Zverev
and Khachanov.

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
    RAIL_FEEDER_GROUP,
    UPCOMING_GAMES_LIMIT,
    upcoming_games_query,
)
from app.utils.event_tennis import is_tennis_feeder_circuit
from app.utils.rail_competition_share import equal_share_by_competition

NOW = datetime(2026, 9, 8, 8, 30, tzinfo=timezone.utc)

FEEDER = RAIL_FEEDER_GROUP


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

#: Natural order — `live_first_order` then `commence_time` — as production held
#: it, with the RANKS measured rather than guessed:
#:
#:     107   candidate rows in the window
#:      81   the first non-feeder row (Tiafoe–Michelsen, 17:00Z)
#:     103   Shelton–Alcaraz, the semi-final the issue is about
#:
#: Trimmed to the shape that decides the outcome — the 80 feeder rows are stood
#: in for by `_FEEDER_WALL` — and every group label is the one the venue wrote.
DOUBLES = "US Open Men Doubles"
SINGLES = "US Open Men Singles"

#: The SEVEN separate Challenger draws in that window, as the venue spelled
#: them. Seven DISTINCT competition strings and one errand, which is the whole
#: reason the route folds them to `RAIL_FEEDER_GROUP` before the share sees
#: them — and the count is load-bearing, not decoration: at seven the unfolded
#: share is 8 // 9 = 0 → 1, and the circuit takes seven of the eight slots one
#: draw at a time. An earlier version of this fixture guessed five, where the
#: unfolded rule still happens to seat Shelton–Alcaraz, and the negative control
#: below passed for the wrong reason until production was asked.
CHALLENGER_DRAWS = (
    "ATP Challenger Phan Thiet 3",
    "ATP Challenger Istanbul 3",
    "ATP Challenger Shanghai",
    "ATP Challenger Tulln",
    "ATP Challenger Cassis",
    "ATP Challenger Genoa",
    "ATP Challenger Seville",
)

_FEEDER_WALL = [Row(f"challenger-{i}", FEEDER) for i in range(80)]

#: Shelton–Alcaraz, Zverev and Khachanov carry NO competition on production: the
#: surname-only copies that DO carry "US Open Men Singles" are proven duplicates
#: and never reach the rail. Faithfully reproduced, because "unnamed rows are
#: never held back" is what puts them on the page.
ATP_20260908 = [
    *_FEEDER_WALL,
    Row("tiafoe-michelsen", SINGLES),
    Row("nys-andreozzi", DOUBLES),
    Row("krawietz-cash", DOUBLES),
    Row("carpico-ram", DOUBLES),
    Row("heliovaara-cabral", DOUBLES),
    Row("gonzalez-granollers", DOUBLES),
    Row("miedler-arevalo", DOUBLES),
    Row("shelton-alcaraz", None),
    Row("zverev-vandezandschulp", None),
    Row("khachanov-blockx", None),
]


def test_the_us_open_semi_final_reaches_the_rail():
    """THE ship. Shelton–Alcaraz was on no page; now it is on this one."""
    assert "shelton-alcaraz" in _names(_share(ATP_20260908))


def test_the_slams_other_marquee_singles_reach_it_too():
    chosen = _names(_share(ATP_20260908))
    assert "zverev-vandezandschulp" in chosen
    assert "khachanov-blockx" in chosen
    assert "tiafoe-michelsen" in chosen


def test_the_challenger_circuit_no_longer_takes_every_slot():
    chosen = _share(ATP_20260908)
    assert len(chosen) == UPCOMING_GAMES_LIMIT
    assert len([r for r in chosen if r.competition == FEEDER]) == 2, _names(chosen)


def test_the_doubles_do_not_take_the_slots_the_challengers_gave_up():
    """The half a tuned cap kept getting wrong."""
    chosen = _share(ATP_20260908)
    assert len([r for r in chosen if r.competition == DOUBLES]) == 2, _names(chosen)


def test_the_rail_still_leads_with_what_is_being_played():
    """`live_first_order` is untouched: the live feeder rows still come first."""
    assert _names(_share(ATP_20260908))[:2] == ["challenger-0", "challenger-1"]


def test_the_feeder_circuit_must_be_ONE_group_not_five():
    """🔴 The defect the fixture could not show and production did.

    Left as five separate Challenger draws, the share does not thin the circuit
    — it SUBDIVIDES it, handing each draw a slot of its own and filling the rail
    before the scan ever reaches rank 81. One match from each of five feeder
    tournaments is not an improvement on five from one.
    """
    unfolded = [
        (
            Row(r.name, CHALLENGER_DRAWS[i % len(CHALLENGER_DRAWS)])
            if r.competition == FEEDER
            else r
        )
        for i, r in enumerate(ATP_20260908)
    ]
    assert "shelton-alcaraz" not in _names(_share(unfolded))
    assert "shelton-alcaraz" in _names(_share(ATP_20260908))


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


def test_unnamed_rows_are_not_capped_among_themselves():
    """More unnamed rows than the share, so counting them would be visible.

    Two competitions make the share 4. The six unnamed rows must ALL be taken
    ahead of the second competition's, because they are six separate absences
    of evidence and not one six-row group.
    """
    rows = (
        [Row(f"x{i}", "one") for i in range(2)]
        + [Row(f"n{i}") for i in range(6)]
        + [Row("y", "two")]
    )
    chosen = _names(_share(rows))
    assert chosen == ["x0", "x1", "n0", "n1", "n2", "n3", "n4", "n5"]


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


def test_the_scan_reaches_the_row_the_issue_is_about():
    """Sized against RANK, not against the wall in front of it.

    Shelton–Alcaraz was row 103 of a 107-row window. The first guess here was
    24 — three times the twelve LIVE feeder rows — and it reached none of the
    US Open at all, because the wall is every Challenger scheduled before the
    Slam's first ball and not the ones already on court.
    """
    assert RAIL_COMPETITION_SCAN_DEPTH >= 107


def test_only_the_tennis_tours_opt_in():
    assert set(RAIL_COMPETITION_SHARE_LEAGUES) == {"tennis_atp", "tennis_wta"}


def test_both_tours_use_the_shipped_venue_stated_predicate():
    """#3640's, not a second opinion about what a Challenger is."""
    assert set(RAIL_COMPETITION_SHARE_LEAGUES.values()) == {is_tennis_feeder_circuit}


def test_the_combat_sports_are_left_alone():
    """#3640: a UFC prelim is on the card the reader came for."""
    for key in ("mma_mixed_martial_arts", "boxing_boxing"):
        assert key not in RAIL_COMPETITION_SHARE_LEAGUES


def test_the_feeder_group_cannot_collide_with_a_venue_string():
    """It shares a namespace with whatever Kalshi writes in `competition`."""
    assert not is_tennis_feeder_circuit(None, None, RAIL_FEEDER_GROUP)
    assert "\x00" in RAIL_FEEDER_GROUP


# ---------------------------------------------------------------------------
# the fold itself — `_event_rail_groups`, the half that reads the venue
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeDB:
    """Just enough of an AsyncSession to answer one `select(...)`."""

    def __init__(self, rows):
        self._rows = rows
        self.calls = 0

    async def execute(self, _statement):
        self.calls += 1
        return _FakeResult(self._rows)


#: (event_id, external_id, name, competition) exactly as production holds them.
MARKET_ROWS = [
    (
        1,
        "KXATPCHALLENGERMATCH-26SEP07BAXJON",
        "Bax vs Jones",
        "ATP Challenger Phan Thiet 3",
    ),
    (
        2,
        "KXATPCHALLENGERMATCH-26SEP07DERRYA",
        "Derepasko vs Ryan Ziegann",
        "ATP Challenger Shanghai",
    ),
    (3, "KXATPMATCH-26SEP08SHEALC", "Shelton vs Alcaraz", "US Open Men Singles"),
    (
        3,
        "KXATPEXACTMATCH-26SEP08SHEALC",
        "Ben Shelton vs Carlos Alcaraz: Exact Match Score",
        "US Open Men Singles",
    ),
    (4, None, "Set 1 Winner: Derepasko vs Ziegann", None),
]


def _groups(rows):
    import asyncio

    from app.routes.league_futures import _event_rail_groups

    return asyncio.run(
        _event_rail_groups(
            _FakeDB(rows), [1, 2, 3, 4], is_feeder=is_tennis_feeder_circuit
        )
    )


def test_two_different_challenger_draws_fold_to_one_group():
    """🔴 M7. Without this the share subdivides the circuit instead of thinning
    it, and seven draws take seven of the eight slots one at a time."""
    out = _groups(MARKET_ROWS)
    assert out[1] == RAIL_FEEDER_GROUP
    assert out[2] == RAIL_FEEDER_GROUP
    assert out[1] == out[2]


def test_a_slam_match_keeps_the_name_the_venue_gave_it():
    assert _groups(MARKET_ROWS)[3] == "US Open Men Singles"


def test_an_event_whose_venue_named_nothing_is_absent():
    """Absent, not `None`-valued: the share must never hold it back."""
    assert 4 not in _groups(MARKET_ROWS)


def test_one_venue_naming_the_circuit_is_enough():
    """The other venue's silence is not counter-evidence."""
    rows = [
        (7, "0xdeadbeef", "Phan Thiet 3: Timofei Derepasko vs Sam Ziegann", None),
        (
            7,
            "KXATPCHALLENGERMATCH-26SEP07DERRYA",
            "Derepasko vs Ryan Ziegann",
            "ATP Challenger Phan Thiet 3",
        ),
    ]
    import asyncio

    from app.routes.league_futures import _event_rail_groups

    out = asyncio.run(
        _event_rail_groups(_FakeDB(rows), [7], is_feeder=is_tennis_feeder_circuit)
    )
    assert out[7] == RAIL_FEEDER_GROUP


def test_no_event_ids_asks_the_database_nothing():
    import asyncio

    from app.routes.league_futures import _event_rail_groups

    db = _FakeDB([])
    assert (
        asyncio.run(_event_rail_groups(db, [], is_feeder=is_tennis_feeder_circuit))
        == {}
    )
    assert db.calls == 0
