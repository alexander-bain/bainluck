"""#3992 — an inning is a period, and every inning is.

Kalshi ships one total market per inning (`KXMLBINNINGTOTAL-…-2` … `-9`). Those
markets classified as `game_total`, so eight of them contributed **16 rungs at
thresholds 0.5 and 1.5** to the pool that prices the projected final score. The
real ladder there is `Total Runs`, 11 monotone rungs crossing 50% at 8.1.

The crossover walk met the contaminated low end first and derived:

    ImpliedTotal(total=1.5, confidence=1.0,
                 lower_threshold=1.5, upper_threshold=1.5,
                 lower_prob=0.975, upper_prob=0.195)

`lower_threshold == upper_threshold` — it "crossed" between two rungs at the same
threshold and called that certainty. The projection then served `home 1.5 /
away 0.0`, and because the line requires BOTH scores above zero, Mets @ Marlins
(15307196) and 15307207 rendered no projected final at all.

**Only the first inning escaped, and only by accident**: `"1st inning"` sat in
`_HALF_PATTERNS`, so one inning of nine was called a half. That is why these
tests walk innings 1-9 rather than sampling one — the bug was invisible to any
test that only ever asked about the first.

Two guards that will not catch this class, so neither is relied on here:

* the **sport-range guard** — baseball's band is `(0.5, 30)` and every
  contaminating rung sits inside it;
* **`_PM_PERIOD_SCOPES`** as #3921 wrote it — halves and quarters, the periods
  American football has. Baseball's period is the inning.

This regression became reachable through #3948, which removed the misfiled
*spread* rungs that had been holding the crossover somewhere plausible. It did
not introduce the contamination; it removed what was masking it. So the route
arm below is the one that matters: a classifier-only test stays on one side of
the boundary the defect actually lived on.

Every number here is production's, read from `/api/events/15307196/history` on
`9ff3f617` — an invented ladder would pass just as green and prove nothing.
"""

import pytest

from app.routes.events import (
    _PM_PERIOD_SCOPES,
    _classify_game_market,
)

from tests.test_projection_never_negative_3951 import _event, _projection
from tests.test_projection_source_confidence_3921 import _market, _outcome

#: `New York M vs Miami: Total Runs` — the ladder the page should price off.
#: Crosses 50% between 7.5 (0.545) and 8.5 (0.465) => 8.1 runs.
REAL_TOTAL_RUNS = (
    (1.5, 0.975), (2.5, 0.955), (3.5, 0.895), (4.5, 0.835),
    (5.5, 0.725), (6.5, 0.655), (7.5, 0.545), (8.5, 0.465),
    (9.5, 0.365), (10.5, 0.285), (11.5, 0.215),
)

#: The eight per-inning markets (innings 2-9), each two rungs, verbatim.
REAL_INNING_RUNGS = (
    (0.345, 0.195), (0.470, 0.245), (0.385, 0.245), (0.445, 0.210),
    (0.405, 0.255), (0.435, 0.245), (0.415, 0.200), (0.430, 0.195),
)

#: What the contaminated pool derived, and what the clean one does.
CONTAMINATED_TOTAL = 1.5
REAL_TOTAL = 8.1


def _total_runs_market():
    return _market(
        "kalshi",
        [_outcome(f"Over {t}", p) for t, p in REAL_TOTAL_RUNS],
        name="New York M vs Miami: Total Runs",
        external_id="KXMLBTOTAL-26SEP081840NYMMIA",
    )


def _inning_total_markets():
    """Kalshi's per-inning totals — the market NAME carries the inning.

    The outcome text is a bare "Over 0.5", indistinguishable from a game total.
    Nothing below the market level can tell these apart, which is why the scope
    has to be decided from the market.
    """
    return [
        _market(
            "kalshi",
            [_outcome("Over 0.5", half_run), _outcome("Over 1.5", run_and_a_half)],
            name=f"New York M vs Miami: {inning}th Inning Total",
            external_id=f"KXMLBINNINGTOTAL-26SEP081840NYMMIA-{inning}",
        )
        for inning, (half_run, run_and_a_half) in zip(
            range(2, 10), REAL_INNING_RUNGS
        )
    ]


def _run_line_market():
    """A second arm, so a projected final exists to be rendered or withheld."""
    return _market(
        "kalshi",
        [
            _outcome("Miami win by 0.5+", 0.62),
            _outcome("Miami win by 1.5+", 0.55),
            _outcome("Miami win by 2.5+", 0.41),
        ],
        name="New York M vs Miami: Run Line",
        external_id="KXMLBSPREAD-26SEP081840NYMMIA",
    )


def _marlins_event():
    return _event(
        id=15307196,
        home_team_name="Miami Marlins",
        away_team_name="New York Mets",
    )


class TestTheClassifierKnowsAnInning:
    def test_every_inning_is_a_period_not_only_the_first(self):
        """Innings 1-9, each of the three market kinds.

        Sampling the first inning alone is exactly how this survived: it was
        caught by the `"1st inning"` entry in `_HALF_PATTERNS` while 2-9 were
        not, so the one inning anybody would reach for was the one that worked.
        """
        for inning in range(1, 10):
            for kind, expected in (
                ("Total", "inning_total"),
                ("Spread", "inning_spread"),
                ("Winner", "inning_winner"),
            ):
                name = f"New York M vs Miami: {inning}th Inning {kind}"
                got = _classify_game_market(name, None)
                assert got == expected, f"{name!r} classified {got!r}"
                assert got in _PM_PERIOD_SCOPES, (
                    f"{got!r} must be a period scope or it still prices the game"
                )

    def test_the_ticker_alone_is_enough(self):
        """A market whose NAME carries no marker still has its ticker."""
        assert _classify_game_market(
            "New York M vs Miami", "KXMLBINNINGTOTAL-26SEP081840NYMMIA-7"
        ) == "inning_total"
        assert _classify_game_market(
            "New York M vs Miami", "KXMLBINNINGWIN-26SEP081840NYMMIA-3"
        ) == "inning_winner"

    @pytest.mark.parametrize(
        "name,expected",
        [
            # #3951 pins these. A run OF innings is half the game, not a period
            # of it, and the plural is the only thing that says so.
            ("1st 5 Innings O/U 2.5", "half_total"),
            ("First 5 Innings O/U 2.5", "half_total"),
            ("1st 5 Innings Spread -1.5", "half_spread"),
            ("New York M vs Miami: First 5 Innings Total", "half_total"),
            # And the game's own quantities are untouched.
            ("New York M vs Miami: Total Runs", "game_total"),
            ("Over 7.5", "game_total"),
            ("Team Total", "team_total"),
            ("1st Half Total", "half_total"),
            ("1st Quarter Total", "quarter_total"),
        ],
    )
    def test_the_half_game_aggregates_do_not_move(self, name, expected):
        assert _classify_game_market(name, None) == expected


class TestTheRouteStopsPricingTheGameOffAnInning:
    """The arm that crosses the boundary. The classifier can be right and the
    pool still wrong, which is the shape of every defect in this family."""

    @pytest.mark.asyncio
    async def test_the_derived_total_is_the_game_not_an_inning(self):
        markets = [_total_runs_market(), *_inning_total_markets()]
        pm = await _projection(_marlins_event(), markets)

        kalshi = (pm.get("implied_totals") or {}).get("kalshi")
        assert kalshi is not None, "the real Total Runs ladder must still derive"

        assert kalshi["total"] == pytest.approx(REAL_TOTAL, abs=0.2), (
            f"derived {kalshi['total']} — the inning rungs are back in the pool"
        )
        assert kalshi["total"] != pytest.approx(CONTAMINATED_TOTAL, abs=0.2)

    @pytest.mark.asyncio
    async def test_the_inning_rungs_are_absent_from_the_pool(self):
        """Named separately from the derived value: a future change to the
        interpolation could land on 8.1 with the contamination still present."""
        markets = [_total_runs_market(), *_inning_total_markets()]
        pm = await _projection(_marlins_event(), markets)

        contracts = (pm["implied_totals"]["kalshi"]).get("contracts") or []
        thresholds = [c["threshold"] for c in contracts]

        assert 0.5 not in thresholds, "an inning's 0.5 rung is pricing the game"
        assert len(contracts) == len(REAL_TOTAL_RUNS), (
            f"{len(contracts)} contracts, expected the {len(REAL_TOTAL_RUNS)} "
            f"rungs of Total Runs alone: {sorted(thresholds)}"
        )

    @pytest.mark.asyncio
    async def test_the_name_alone_defends_the_pool(self):
        """Production markets carry BOTH a name and a ticker, so either path
        alone keeps the pool clean and neither is proven by the tests above —
        removing the name rule left every route arm green on the ticker.
        Here the markets have no `external_id` at all."""
        markets = [
            _market(
                "kalshi",
                [_outcome(f"Over {t}", p) for t, p in REAL_TOTAL_RUNS],
                name="New York M vs Miami: Total Runs",
            ),
            *[
                _market(
                    "kalshi",
                    [_outcome("Over 0.5", lo), _outcome("Over 1.5", hi)],
                    name=f"New York M vs Miami: {inning}th Inning Total",
                )
                for inning, (lo, hi) in zip(range(2, 10), REAL_INNING_RUNGS)
            ],
        ]
        pm = await _projection(_marlins_event(), markets)

        kalshi = (pm.get("implied_totals") or {}).get("kalshi")
        assert kalshi is not None
        assert kalshi["total"] == pytest.approx(REAL_TOTAL, abs=0.2), (
            f"derived {kalshi['total']} from names alone"
        )

    @pytest.mark.asyncio
    async def test_the_ticker_alone_defends_the_pool(self):
        """The converse: the inning is in the ticker, the name says nothing."""
        markets = [
            _market(
                "kalshi",
                [_outcome(f"Over {t}", p) for t, p in REAL_TOTAL_RUNS],
                name="New York M vs Miami: Total Runs",
                external_id="KXMLBTOTAL-26SEP081840NYMMIA",
            ),
            *[
                _market(
                    "kalshi",
                    [_outcome("Over 0.5", lo), _outcome("Over 1.5", hi)],
                    name="New York M vs Miami",
                    external_id=f"KXMLBINNINGTOTAL-26SEP081840NYMMIA-{inning}",
                )
                for inning, (lo, hi) in zip(range(2, 10), REAL_INNING_RUNGS)
            ],
        ]
        pm = await _projection(_marlins_event(), markets)

        kalshi = (pm.get("implied_totals") or {}).get("kalshi")
        assert kalshi is not None
        assert kalshi["total"] == pytest.approx(REAL_TOTAL, abs=0.2), (
            f"derived {kalshi['total']} from tickers alone"
        )

    @pytest.mark.asyncio
    async def test_the_page_gets_a_projected_final_it_can_render(self):
        """The user-visible end of it. Both scores must clear zero or the line
        is not drawn at all — which is what production served."""
        markets = [
            _total_runs_market(),
            _run_line_market(),
            *_inning_total_markets(),
        ]
        pm = await _projection(_marlins_event(), markets)

        final = pm.get("projected_final")
        assert final is not None, "no projected final at all"
        assert final["home_score"] > 0 and final["away_score"] > 0, (
            f"{final} — a score of 0.0 renders NO projection line"
        )
        assert final["home_score"] + final["away_score"] == pytest.approx(
            REAL_TOTAL, abs=0.4
        ), f"{final} does not add up to a nine-inning game"
