"""UX-P268 (#2661): the progression table publishes the blend, not one source's raw price.

`/golf` printed two different win probabilities for the same golfer about 500px
apart: the DP World Tour card read `probability` from `GET /api/golf` (the mean of
every source that prices the golfer) while the Tournament Progression table read
one market's raw `current_probability`. Matt Wallace was 5.8% on the card and 4.5%
in the table — 29% relative — and the disagreement reordered the leaderboard.

The defect had two halves and BOTH are exercised here, because fixing either alone
ships nothing a user can see:

  1. DISCOVERY. Sibling lookup stopped as soon as it found A sibling, which answers
     "does this tournament have other STAGES" and never "does it have other
     SOURCES". Omega European Masters' DataGolf prefix scan returns the four other
     DataGolf stages, so the Kalshi "Omega European Masters Winner" — open, priced,
     and already blended into the card — was never looked for at all.
  2. SELECTION. Even once found, `stage_markets` kept the first market per stage and
     silently discarded the rest.

Why the row set is held fixed rather than merged (this is the load-bearing design
decision, and the obvious fix gets it wrong): 15 of the Kalshi market's 162 outcomes
do not merge with a DataGolf outcome, and 7 of those outrank the display cut. Letting
the secondary market contribute participants would therefore render "Eugenio
Chacarra" AND "Eugenio Lopez-Chacarra", "Angel Ayora" AND "Angel Ayora Fanegas" —
the same golfer twice at two prices, which is a worse defect than the one being
fixed and is exactly what #2661 names as its two controls.

All numbers below are the real production prices for markets 59863411 (DataGolf) and
59759220 (Kalshi), measured 2026-09-02.

Every assertion reads the endpoint's own response body. An earlier repair in this
repo (#2579 / CERT-718) shipped green guards that asserted on an intermediate list
while the route re-ranked it afterwards, so nothing upstream of `resp.json()` is
trusted here.
"""

from datetime import datetime, timezone
from statistics import mean
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.anyio


# --- Real production prices -------------------------------------------------
# DataGolf market 59863411 "Omega European Masters - Winner"
DG_WALLACE = 0.045100
DG_GERARD = 0.088700
DG_CHACARRA = 0.033117  # single-source: CONTROL
DG_NICOLAI = 0.044567  # spelled "Nicolai Hojgaard" by DataGolf

# Kalshi market 59759220 "Omega European Masters Winner"
KS_WALLACE = 0.069500
KS_GERARD = 0.082000
KS_LOPEZ_CHACARRA = 0.026000  # never merges with DG_CHACARRA
KS_NICOLAI = 0.043500  # spelled "Nicolai Højgaard" by Kalshi (note the o-slash)

# The blend reproduces GET /api/golf's arithmetic exactly: every per-source price is
# quantized to 3dp, those are averaged, and the mean is quantized again. Averaging
# the raw prices is NOT equivalent at the precision the page renders — it leaves
# Wallace at 5.7% against the card's 5.8%, and 4 of the tournament's 15 golfers
# still showing two different numbers, which is the whole defect in miniature.
def _blend(*source_prices):
    return round(mean(round(v, 3) for v in source_prices), 3)


BLEND_WALLACE = _blend(DG_WALLACE, KS_WALLACE)  # 0.058 -> the card's 5.8%
BLEND_GERARD = _blend(DG_GERARD, KS_GERARD)  # 0.085 -> the card's 8.5%
BLEND_NICOLAI = _blend(DG_NICOLAI, KS_NICOLAI)  # 0.044 -> the card's 4.4%

# What the DP World Tour card prints for each golfer, read off GET /api/golf on
# 2026-09-02. The ship is that the table now prints these same strings.
CARD_STRINGS = {"Matt Wallace": "5.8%", "Ryan Gerard": "8.5%", "Nicolai Hojgaard": "4.4%"}


def _as_card_renders(probability):
    """Mirror of the card's `(p * 100).toFixed(1)` for values under 10%."""
    return f"{probability * 100:.1f}%"


def _result_unique_all(values):
    result = MagicMock()
    result.scalars.return_value.unique.return_value.all.return_value = values
    return result


def _result_scalar_one_or_none(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _outcome(name, probability, *, change=None, team_id=None):
    return SimpleNamespace(
        name=name,
        team_id=team_id,
        current_probability=probability,
        probability_change_24h=change,
    )


def _market(market_id, name, external_id, source, outcomes, *, tier=None):
    return SimpleNamespace(
        id=market_id,
        name=name,
        external_id=external_id,
        source=source,
        market_tier=tier,
        status="open",
        llm_sport_category="golf",
        canonical_market_key=None,
        resolution_date=datetime(2026, 9, 6, tzinfo=timezone.utc),
        event_id=None,
        outcomes=outcomes,
    )


def _datagolf_win(outcomes=None):
    return _market(
        59863411,
        "Omega European Masters - Winner",
        "datagolf:euro:2026134:win",
        "datagolf",
        outcomes
        if outcomes is not None
        else [
            _outcome("Ryan Gerard", DG_GERARD),
            _outcome("Matt Wallace", DG_WALLACE),
            _outcome("Nicolai Hojgaard", DG_NICOLAI),
            _outcome("Eugenio Chacarra", DG_CHACARRA),
        ],
    )


def _datagolf_top5():
    return _market(
        59863412,
        "Omega European Masters - Top 5 Finish",
        "datagolf:euro:2026134:top_5",
        "datagolf",
        [_outcome("Ryan Gerard", 0.277458), _outcome("Matt Wallace", 0.2)],
    )


def _kalshi_win(outcomes=None):
    return _market(
        59759220,
        "Omega European Masters Winner",
        "KXDPWORLDTOUR-OMEM26",
        "kalshi",
        outcomes
        if outcomes is not None
        else [
            _outcome("Ryan Gerard", KS_GERARD),
            _outcome("Matt Wallace", KS_WALLACE),
            _outcome("Nicolai Højgaard", KS_NICOLAI),
            _outcome("Eugenio Lopez-Chacarra", KS_LOPEZ_CHACARRA),
        ],
        tier=1,
    )


def _wire(mock_db, *, siblings, cross_source=None):
    """Queries in order: load market -> DataGolf prefix scan -> [cross-source scan]."""
    results = [
        _result_scalar_one_or_none(_datagolf_win()),
        _result_unique_all(siblings),
    ]
    if cross_source is not None:
        results.append(_result_unique_all(cross_source))
    mock_db.execute.side_effect = results


async def _get(client, market_id=59863411, top_n=40):
    resp = await client.get(f"/api/futures/{market_id}/progression?top_n={top_n}")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _win_of(body, name):
    for p in body["participants"]:
        if p["name"] == name:
            return p["probabilities"].get("win")
    return None


def _names(body):
    return [p["name"] for p in body["participants"]]


class TestTheShip:
    """The two lists agree because the table publishes the same blend the card does."""

    async def test_two_source_win_stage_publishes_the_mean(self, client, mock_db):
        _wire(mock_db, siblings=[_datagolf_top5()], cross_source=[_kalshi_win()])

        body = await _get(client)

        # 4.5% (DataGolf raw, the bug) -> 5.7% (the blend, matching the card's 5.8%)
        assert _win_of(body, "Matt Wallace") == pytest.approx(BLEND_WALLACE)
        assert _win_of(body, "Ryan Gerard") == pytest.approx(BLEND_GERARD)

    async def test_table_prints_the_same_string_the_card_prints(
        self, client, mock_db
    ):
        """The ship, stated the way a user would check it: the number rendered in
        the Tournament Progression table and the number rendered on the DP World
        Tour card about 500px above it are the same string.

        Verified to discriminate: swapping the quantized blend for a plain mean of
        the raw prices — a fix that is otherwise indistinguishable — turns this red
        (4 of 16 red in total), because 0.0573 renders "5.7%" beside the card's
        "5.8%"."""
        _wire(mock_db, siblings=[_datagolf_top5()], cross_source=[_kalshi_win()])

        body = await _get(client)

        assert {
            name: _as_card_renders(_win_of(body, name)) for name in CARD_STRINGS
        } == CARD_STRINGS

    async def test_blend_is_neither_source_raw(self, client, mock_db):
        """Counter-case: a 'fix' that just picked the other market would pass the
        equality above only by coincidence, so pin that both raws are gone."""
        _wire(mock_db, siblings=[_datagolf_top5()], cross_source=[_kalshi_win()])

        wallace = _win_of(await _get(client), "Matt Wallace")

        assert wallace != pytest.approx(DG_WALLACE), "still publishing DataGolf raw"
        assert wallace != pytest.approx(KS_WALLACE), "now publishing Kalshi raw"

    async def test_diacritic_variants_merge_into_one_row(self, client, mock_db):
        """DataGolf writes 'Hojgaard', Kalshi writes 'Højgaard'. One golfer, one row,
        one blended number — the merge key transliterates o-slash."""
        _wire(mock_db, siblings=[_datagolf_top5()], cross_source=[_kalshi_win()])

        body = await _get(client)

        assert _names(body).count("Nicolai Hojgaard") == 1
        assert "Nicolai Højgaard" not in _names(body)
        assert _win_of(body, "Nicolai Hojgaard") == pytest.approx(BLEND_NICOLAI)


class TestTheRowSetIsHeldFixed:
    """#2661's two named controls, and the duplicate-row regression they detect."""

    async def test_single_source_participant_is_untouched(self, client, mock_db):
        """CONTROL — green on main too. Chacarra is priced by DataGolf alone, so the
        blend of one source must be that source, to the last decimal."""
        _wire(mock_db, siblings=[_datagolf_top5()], cross_source=[_kalshi_win()])

        assert _win_of(await _get(client), "Eugenio Chacarra") == pytest.approx(
            DG_CHACARRA
        )

    async def test_secondary_only_participant_never_becomes_a_row(
        self, client, mock_db
    ):
        """The regression the obvious fix ships: Kalshi's 'Eugenio Lopez-Chacarra'
        does not merge with DataGolf's 'Eugenio Chacarra', and at 2.6% it is above
        the display cut, so a row-merging fix renders the same man twice."""
        _wire(mock_db, siblings=[_datagolf_top5()], cross_source=[_kalshi_win()])

        names = _names(await _get(client))

        assert "Eugenio Lopez-Chacarra" not in names
        assert names.count("Eugenio Chacarra") == 1

    async def test_row_set_is_exactly_the_primary_markets_participants(
        self, client, mock_db
    ):
        """Stated as a set equality rather than a count, so a swap cannot pass."""
        _wire(mock_db, siblings=[_datagolf_top5()], cross_source=[_kalshi_win()])

        assert set(_names(await _get(client))) == {
            "Ryan Gerard",
            "Matt Wallace",
            "Nicolai Hojgaard",
            "Eugenio Chacarra",
        }

    async def test_secondary_source_cannot_add_a_row_even_when_it_would_lead(
        self, client, mock_db
    ):
        """The strongest form: a secondary-only name priced above every displayed
        row still does not appear. Row membership is the primary's alone."""
        _wire(
            mock_db,
            siblings=[_datagolf_top5()],
            cross_source=[_kalshi_win([_outcome("Nobody At All", 0.99)])],
        )

        assert "Nobody At All" not in _names(await _get(client))


class TestUnaffectedShapes:
    """Controls that must be green in both arms — the fix is a no-op for them."""

    async def test_single_market_stage_is_unchanged(self, client, mock_db):
        """CONTROL — green on main too. With one market per stage there is nothing
        to blend, so every number is the raw price, byte for byte. The cross-source
        scan runs and comes back empty, which is the no-second-source case."""
        _wire(mock_db, siblings=[_datagolf_top5()], cross_source=[])

        body = await _get(client)

        assert _win_of(body, "Matt Wallace") == pytest.approx(DG_WALLACE)
        assert _win_of(body, "Ryan Gerard") == pytest.approx(DG_GERARD)
        assert body["participants"][0]["probabilities"]["top_5"] == pytest.approx(
            0.277458
        )

    async def test_other_stages_are_untouched_by_a_win_stage_blend(
        self, client, mock_db
    ):
        """CONTROL — green on main too. Make Cut / Top 20 / Top 10 / Top 5 are
        DataGolf-only markets with no second source; #2661 requires they not move."""
        _wire(mock_db, siblings=[_datagolf_top5()], cross_source=[_kalshi_win()])

        body = await _get(client)
        gerard = next(p for p in body["participants"] if p["name"] == "Ryan Gerard")

        assert gerard["probabilities"]["top_5"] == pytest.approx(0.277458)

    async def test_stage_market_attribution_still_names_the_primary(
        self, client, mock_db
    ):
        """CONTROL — green on main too. Blending prices must not silently re-point
        the stage's published `market_id`."""
        _wire(mock_db, siblings=[_datagolf_top5()], cross_source=[_kalshi_win()])

        body = await _get(client)
        win_stage = next(s for s in body["stages"] if s["key"] == "win")

        assert win_stage["market_id"] == 59863411


class TestOrderIndependenceAndStatus:
    async def test_blend_does_not_depend_on_which_market_was_primary(
        self, client, mock_db
    ):
        """The mean is taken over all contributing sources at once, so the published
        number is the same whichever market the request happened to name."""
        _wire(mock_db, siblings=[_datagolf_top5()], cross_source=[_kalshi_win()])
        dg_primary = _win_of(await _get(client), "Matt Wallace")

        # Same two markets, discovered in the opposite order.
        mock_db.execute.side_effect = [
            _result_scalar_one_or_none(_datagolf_win()),
            _result_unique_all([_kalshi_win(), _datagolf_top5()]),
        ]
        ks_first = _win_of(await _get(client), "Matt Wallace")

        assert dg_primary == pytest.approx(ks_first)

    async def test_clinched_is_recomputed_from_the_published_number(
        self, client, mock_db
    ):
        """A participant certain in one source and a coin-flip in the other is not
        clinched. Status is a claim about the number we print."""
        mock_db.execute.side_effect = [
            _result_scalar_one_or_none(
                _datagolf_win([_outcome("Matt Wallace", 1.0)])
            ),
            _result_unique_all([_datagolf_top5()]),
            _result_unique_all([_kalshi_win([_outcome("Matt Wallace", 0.5)])]),
        ]
        body = await _get(client)
        wallace = next(p for p in body["participants"] if p["name"] == "Matt Wallace")

        assert wallace["probabilities"]["win"] == pytest.approx(0.75)
        assert wallace["status"].get("win") is None


class TestCrossSourceDiscovery:
    """The half without which the blend has nothing to blend."""

    async def test_cross_source_scan_runs_when_every_sibling_shares_one_source(
        self, client, mock_db
    ):
        _wire(mock_db, siblings=[_datagolf_top5()], cross_source=[_kalshi_win()])

        await _get(client)

        # load market, DataGolf prefix scan, cross-source scan
        assert mock_db.execute.await_count == 3

    async def test_cross_source_scan_is_skipped_when_a_second_source_is_present(
        self, client, mock_db
    ):
        """It must not cost a query it cannot pay for."""
        mock_db.execute.side_effect = [
            _result_scalar_one_or_none(_datagolf_win()),
            _result_unique_all([_datagolf_top5(), _kalshi_win()]),
        ]

        body = await _get(client)

        assert mock_db.execute.await_count == 2
        # and it still blends, because the sibling scan already found both
        assert _win_of(body, "Matt Wallace") == pytest.approx(BLEND_WALLACE)

    async def test_cross_source_scan_escapes_like_metacharacters(
        self, client, mock_db
    ):
        """`source_tournament_name` is data. A tournament named with `%` or `_` must
        not turn the lookup into a wildcard scan of the whole sport."""
        odd = _market(
            59863411,
            "50_50 Masters %Open - Winner",
            "datagolf:euro:2026134:win",
            "datagolf",
            [_outcome("Ryan Gerard", DG_GERARD)],
        )
        mock_db.execute.side_effect = [
            _result_scalar_one_or_none(odd),
            _result_unique_all([_datagolf_top5()]),
            _result_unique_all([]),
        ]

        await _get(client)

        sql = str(mock_db.execute.await_args_list[-1].args[0])
        assert "ESCAPE" in sql.upper(), "the ilike lost its escape clause"
        needle = mock_db.execute.await_args_list[-1].args[0].compile().params
        assert any(
            isinstance(v, str) and "\\%" in v and "\\_" in v for v in needle.values()
        ), f"LIKE metacharacters reached the query unescaped: {needle}"
