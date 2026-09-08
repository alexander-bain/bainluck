"""#3995 — the Runs map on an MLB page is made of runs.

#3992 was the wrong SCOPE: an inning is a fraction of the contest. This is the
other axis — the right scope, the wrong UNIT. Two families were sitting on the
run ladder of `/api/events/15307196/game-markets` (Mets @ Marlins), measured on
`9ff3f617`:

    threshold  market                                  quantity
    0.5, 1.5   2nd Inning Total                        one inning   <- #3992
    2.0 .. 6.0 New York M vs Miami: Total Bases        BASES
    2.5 ..11.5 New York M vs Miami: Total Runs         runs   (the real ladder)
    16.5       Sean Manaea: Outs Recorded O/U 16.5     one pitcher's OUTS

Read in order the rail was `0.5, 1.5, 2.0, 2.5, 3.0, 3.5 … 11.5, 16.5` — a
ladder alternating between two quantities every half-step, then a 16.5 that is
one pitcher's outs line, five runs past the top of the real one.

🔴 THE HARM IS NOT THAT THE RUNGS ARE UNTIDY. `_enforce_monotonicity` caps each
rung at the one below it, and the bases rungs sort FIRST on a half-run grid, so
they crush the real ladder's prices on the way past. Production served, on the
run rungs themselves:

    threshold   real P(over)   served       capped by
    2.5         0.955          0.39         Total Bases 2.0
    3.5         0.895          0.20         Total Bases 3.0
    6.5 .. 11.5 0.655 .. 0.215 0.045        Total Bases 6.0

The map's headline is the rung nearest 50%, so a reader was told the game turns
on ~1.8 runs while the real ladder crosses at 8.2. A wrong-unit rung does not sit
quietly beside a right one; it takes the right one's price with it.

The two families are independent bugs with independent fixes, so every route arm
below seeds ONE of them with the other ABSENT. That is #3992's lesson paid
forward: it landed two redundant paths, and because production markets carry both
a name and a ticker, each path covered for the other and the suite only ever
proved "at least one of the two works".

Numbers are production's, read from `/api/events/15307196/game-markets` and
`/history` on `9ff3f617` and `410fd1ee`. An invented ladder would pass just as
green and prove nothing.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


from app.models import Event, Sport  # noqa: E402
from app.models.models import Base, FuturesMarket, FuturesOutcome  # noqa: E402
from app.routes.events import (  # noqa: E402
    _PLAYER_PROP_OU_STAT_RE,
    _PM_NON_GAME_TOTAL_SCOPES,
    _PM_PERIOD_SCOPES,
    _classify_game_market,
)

from tests.test_projection_never_negative_3951 import _event, _projection  # noqa: E402
from tests.test_projection_source_confidence_3921 import _market, _outcome  # noqa: E402

EVENT_ID = 15307196
SPORT_ID = 1
COMMENCE = datetime(2026, 9, 8, 22, 40, tzinfo=timezone.utc)

#: `New York M vs Miami: Total Runs` (`KXMLBTOTAL`) — the ladder the map is FOR.
#: Crosses 50% between 7.5 (0.545) and 8.5 (0.465) => 8.2 runs.
REAL_TOTAL_RUNS = (
    (1.5, 0.975), (2.5, 0.955), (3.5, 0.895), (4.5, 0.835),
    (5.5, 0.725), (6.5, 0.655), (7.5, 0.545), (8.5, 0.465),
    (9.5, 0.365), (10.5, 0.285), (11.5, 0.215),
)

#: `New York M vs Miami: Total Bases` (`KXMLBTB`) — a whole-game total counted in
#: BASES. Integer rungs, so they interleave with the run ladder's halves.
REAL_TOTAL_BASES = (
    (2.0, 0.39), (3.0, 0.20), (4.0, 0.11), (5.0, 0.06), (6.0, 0.045),
)

#: One pitcher's outs line. Polymarket's `<Player>: <Stat> O/U <line>` shape.
OUTS_PROP_NAME = "Sean Manaea: Outs Recorded O/U 16.5"
OUTS_PROP_LINE = 16.5


# --------------------------------------------------------------------------
# The classifier
# --------------------------------------------------------------------------


class TestTheClassifierKnowsWhatIsBeingCounted:
    @pytest.mark.parametrize(
        "name,external_id",
        [
            ("New York M vs Miami: Total Bases", "KXMLBTB-26SEP081840NYMMIA"),
            ("Arizona vs Atlanta: Total Bases", "KXMLBTB-26APR011215ARIATL"),
            # The doubleheader variants Kalshi emits, same family.
            ("Game 1 Total Bases", "KXMLBTB-26APR261340COLNYMG1"),
            ("Game 2 Total Bases", "KXMLBTB-26JUL071945MILSTLG2"),
        ],
    )
    def test_a_total_counted_in_bases_is_not_the_game_total(self, name, external_id):
        got = _classify_game_market(name, external_id)
        assert got == "stat_total", f"{name!r} classified {got!r}"

    @pytest.mark.parametrize(
        "name,external_id,expected",
        [
            # 🔴 The one that must not move. Same shape, same ticker family, one
            # word different — and that word is the whole ship.
            ("New York M vs Miami: Total Runs", "KXMLBTOTAL-26SEP081840NYMMIA", "game_total"),
            ("Game 2 Total Runs", "KXMLBTOTAL-26JUL071945MILSTLG2", "game_total"),
            ("Mets vs. Marlins: O/U 8.5", None, "game_total"),
            ("Over 7.5", None, "game_total"),
            # #3992 and #3951 pin these; a new branch above them must not shadow.
            ("New York M vs Miami: 2nd Inning Total", None, "inning_total"),
            ("New York M vs Miami: First 5 Innings Total", None, "half_total"),
            ("New York M vs Miami: Team Total", "KXMLBTEAMTOTAL-26SEP08NYMMIA", "team_total"),
            # 🔴 Soccer fixtures sit under the `baseball_other` sport key —
            # 374 events measured 2026-09-08, ticker roots `KXCLUBF`/`KXURYPD`/
            # `KXARGNACB`, filed as #4007 — so the baseball classifier sees them.
            # `\bbases\b` cannot reach "goals", and `goals`/`games` were kept OUT
            # of the rule deliberately rather than used to paper over #4007.
            # This arm is what keeps a future widening honest.
            ("Eldense vs Al-Ittifaq: Total Goals", "KXCLUBFTOTAL-26JUL25CDEITT", "game_total"),
        ],
    )
    def test_the_quantities_that_are_the_game_do_not_move(self, name, external_id, expected):
        assert _classify_game_market(name, external_id) == expected

    def test_a_players_bases_line_is_still_a_prop_not_a_stat_total(self):
        """🔴 ORDER. `stat_total` is tested below the player-prop check, and
        "<Player>: Total Bases O/U n" satisfies BOTH. Move the new branch above
        the prop check and this is the arm that goes red — 464 names on
        production (measured 2026-09-08) take this path."""
        for name in (
            "Brandon Marsh: Total Bases O/U 2.5",
            "Kyle Schwarber: Total Bases O/U 1.5",
        ):
            assert _classify_game_market(name, None) == "player_prop"

    def test_a_pitchers_outs_line_is_a_prop(self):
        assert _classify_game_market(OUTS_PROP_NAME, None) == "player_prop"

    def test_outs_does_not_reach_inside_strikeouts(self):
        """🔴 The negative control for the word added to the O/U vocabulary.

        Asserted on the regex itself, not through `_classify_game_market`:
        "Strikeouts O/U 5.5" is a player prop by `_PLAYER_PROP_RE` no matter what
        this regex says, so routing the claim through the classifier would let
        the shared vocabulary cover for a broken word boundary. `\\bouts\\b`
        cannot match "strikeouts" — the preceding "e" is a word character.
        """
        assert _PLAYER_PROP_OU_STAT_RE.search("Outs Recorded") is not None
        assert _PLAYER_PROP_OU_STAT_RE.search("Strikeouts") is None
        assert _PLAYER_PROP_OU_STAT_RE.search("Total Bases") is not None


class TestTheScopeSetsAgree:
    def test_a_stat_total_may_never_price_the_games_total(self):
        assert "stat_total" in _PM_NON_GAME_TOTAL_SCOPES

    def test_a_stat_total_is_not_a_PERIOD(self):
        """It is the whole game, counted in the wrong unit. Filing it as a
        period would be right by accident and wrong by description — and
        `_PM_PERIOD_SCOPES` drops the SPREAD arm too, which this never earns."""
        assert "stat_total" not in _PM_PERIOD_SCOPES


# --------------------------------------------------------------------------
# The route — the boundary the defect actually lived on
# --------------------------------------------------------------------------


def _engine(markets):
    """Seed one MLB event and the given (name, ticker, source, rungs) markets."""
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(Sport(id=SPORT_ID, key="baseball_mlb", name="MLB"))
        s.add(
            Event(
                id=EVENT_ID,
                sport_id=SPORT_ID,
                home_team_name="Miami Marlins",
                away_team_name="New York Mets",
                commence_time=COMMENCE,
                status="scheduled",
            )
        )
        outcome_id = 9000
        for market_id, (name, ticker, source, rungs) in enumerate(markets, start=700):
            s.add(
                FuturesMarket(
                    id=market_id,
                    event_id=EVENT_ID,
                    sport_id=SPORT_ID,
                    source=source,
                    external_id=ticker,
                    name=name,
                    category="game",
                    llm_sport_category="baseball",
                    market_type="game_total",
                    status="open",
                )
            )
            for threshold, prob in rungs:
                outcome_id += 1
                s.add(
                    FuturesOutcome(
                        id=outcome_id,
                        market_id=market_id,
                        external_id=f"{ticker}-{threshold}",
                        name=f"Over {threshold}",
                        current_probability=prob,
                    )
                )
        s.commit()
    return eng


class _SyncAsAsync:
    def __init__(self, session):
        self._session = session

    async def execute(self, statement):
        return self._session.execute(statement)


def _served(eng):
    """`GET /api/events/{id}/game-markets`'s builder, actually executed."""
    import asyncio

    from app.routes.events import _build_game_markets

    with Session(eng) as s:
        response, _status, _ids = asyncio.run(
            _build_game_markets(EVENT_ID, _SyncAsAsync(s))
        )
    return response


_RUNS = (
    "New York M vs Miami: Total Runs", "KXMLBTOTAL-26SEP081840NYMMIA",
    "kalshi", REAL_TOTAL_RUNS,
)
_BASES = (
    "New York M vs Miami: Total Bases", "KXMLBTB-26SEP081840NYMMIA",
    "kalshi", REAL_TOTAL_BASES,
)
# Polymarket keys a market by `condition_id`, never by a Kalshi-style ticker, so
# the ticker fallback in the classifier has nothing to read here — the NAME is
# the only signal, which is the whole reason this family was missed.
_OUTS = (
    OUTS_PROP_NAME,
    "0x2f1c9d5b7a3e46108d2b5c0f9a4e7d31c8b60f52a9e34d7b1c05a86f3e2d94b7",
    "polymarket",
    ((OUTS_PROP_LINE, 0.52),),
)


class TestTheServedRunLadder:
    """Each arm seeds ONE contaminant. Seeding both would let either fix alone
    pass the pair, which is exactly how #3992 shipped half-guarded."""

    def test_the_bases_rungs_leave_the_run_ladder(self):
        totals = _served(_engine([_RUNS, _BASES]))["totals"]

        names = {t["market_name"] for t in totals}
        assert names == {"New York M vs Miami: Total Runs"}, (
            f"a non-run quantity is on the run rail: {sorted(names)}"
        )
        assert [t["threshold"] for t in totals] == [t for t, _ in REAL_TOTAL_RUNS]

    def test_the_bases_rungs_do_not_CRUSH_the_run_prices(self):
        """🔴 The assertion that names the real harm.

        Named separately from the rung list because the two fail apart: a fix
        that dropped the bases rungs AFTER monotonicity ran would leave this red
        with the arm above green, and the page would still headline ~1.8 runs.
        """
        totals = _served(_engine([_RUNS, _BASES]))["totals"]
        served = {t["threshold"]: t["over_probability"] for t in totals}

        for threshold, real in REAL_TOTAL_RUNS:
            assert served[threshold] == pytest.approx(real, abs=1e-6), (
                f"rung {threshold} served {served[threshold]} not {real} — "
                "a bases rung is still capping the ladder"
            )

        # And the crossover the map headlines is the game's, not a bases ladder's.
        crossing = [t for t, p in sorted(served.items()) if p < 0.5][0]
        assert crossing == 8.5, f"map crosses 50% at {crossing}, not the real 8.5"

    def test_the_outs_prop_leaves_the_run_ladder(self):
        response = _served(_engine([_RUNS, _OUTS]))

        thresholds = [t["threshold"] for t in response["totals"]]
        assert OUTS_PROP_LINE not in thresholds, (
            "one pitcher's outs line is a rung on the game's run ladder"
        )
        assert thresholds == [t for t, _ in REAL_TOTAL_RUNS]

    def test_the_outs_prop_is_still_SERVED_as_a_prop(self):
        """Reclassifying moves a market; it must never delete one. The rung is
        wrong on the run rail and right in the props section."""
        response = _served(_engine([_RUNS, _OUTS]))

        assert OUTS_PROP_NAME in {p["market_name"] for p in response["player_props"]}

    def test_the_bases_market_is_still_SERVED_somewhere(self):
        """Same contract for the bases family. This is why `stat_total` is a
        LABEL and not an entry in the scope FILTER: the filter deletes the rungs
        from the response, and on the 68 events (measured) that carry
        `Total Bases` without `Total Runs` it would have taken the only market
        they have."""
        response = _served(_engine([_RUNS, _BASES]))

        served_anywhere = {
            row["market_name"]
            for section in ("totals", "player_props", "team_totals", "other")
            for row in response.get(section) or []
        }
        assert "New York M vs Miami: Total Bases" in served_anywhere


class TestTheProjectionPoolAgrees:
    """The map and the projected final read two different pools off the same
    classifier. #3948 is the standing lesson that a contaminant only looks
    harmless until the one masking it is removed."""

    @pytest.mark.asyncio
    async def test_a_bases_ladder_never_prices_the_projected_total(self):
        runs = _market(
            "kalshi",
            [_outcome(f"Over {t}", p) for t, p in REAL_TOTAL_RUNS],
            name="New York M vs Miami: Total Runs",
            external_id="KXMLBTOTAL-26SEP081840NYMMIA",
        )
        bases = _market(
            "kalshi",
            [_outcome(f"Over {t}", p) for t, p in REAL_TOTAL_BASES],
            name="New York M vs Miami: Total Bases",
            external_id="KXMLBTB-26SEP081840NYMMIA",
        )
        event = _event(
            id=EVENT_ID,
            home_team_name="Miami Marlins",
            away_team_name="New York Mets",
        )

        pm = await _projection(event, [runs, bases])
        kalshi = (pm.get("implied_totals") or {}).get("kalshi")
        assert kalshi is not None, "the real Total Runs ladder must still derive"

        thresholds = [c["threshold"] for c in kalshi.get("contracts") or []]
        assert thresholds == [t for t, _ in REAL_TOTAL_RUNS], (
            f"the bases rungs are in the projection pool: {thresholds}"
        )
        assert kalshi["total"] == pytest.approx(8.2, abs=0.2)
