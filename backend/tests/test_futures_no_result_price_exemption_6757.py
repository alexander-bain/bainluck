"""#6757 residual — ``ungradeable_result`` is a retraction, not a grade, on the detail route.

The route-level proof against a real Postgres is
``tests/integration/test_futures_no_result_price_exemption_6757_pg.py`` (CI job
``search-recall``). THIS file is the everyday guard: it runs without a database,
in the same shape as ``test_futures_detail_empty_book_6757.py``, and pins each
arm plus the one predicate both arms read — ``row_carries_a_verdict``, which
#6876 already shipped in ``futures_unsupported_price`` for the price rails on
this same route. The repair introduces no predicate of its own; asking the
house one here is the whole change.

WHAT A READER SAW (production v4709, 2026-09-18 04:09Z). ``/futures/2951399``,
"WBC Featherweight Title on January 1, 2027", ``status='open'``: seventeen prices
summing to 876.5%, thirteen of them **49%**, "Title is vacant — 49%" among them.
Every leg carried ``resolution_source='ungradeable_result'``, so #6757's grade
exemption — "``resolution_source is None``" on both arms — kept every one.
``prices_withheld: 0`` was not a judgement; it was an empty population.
"""

import inspect
from types import SimpleNamespace

import pytest

from app.utils.kalshi_fabricated_loss import RETRACTION_SOURCE
from app.utils.resolution_authority import (
    AUTHORITATIVE_SOURCES,
    KNOWN_SOURCES,
    TERMINAL_SOURCES,
    is_authoritative,
)

#: The WBC book shape: a 1-cent bid against a 97-cent ask, price on the midpoint.
_EMPTY_BOOK = (0.490, 0.0100, 0.9700)
#: A real two-sided quote — the specimen's hero.
_REAL_QUOTE = (0.930, 0.9000, 0.9600)


def _leg(id_, name, probability, yes_bid, yes_ask, resolution_source, is_winner=False):
    return SimpleNamespace(
        id=id_,
        name=name,
        external_id=f"synthetic-6757-{id_}",
        current_probability=probability,
        current_yes_bid=yes_bid,
        current_yes_ask=yes_ask,
        current_american_odds=None,
        rank=id_,
        rank_change_24h=None,
        probability_change_24h=None,
        opening_probability=None,
        opening_american_odds=None,
        is_winner=is_winner,
        resolution_source=resolution_source,
        last_updated=None,
    )


def _market(legs, source="kalshi", status="open"):
    return SimpleNamespace(
        id=2951399,
        name="SYNTHETIC-6757 WBC Featherweight Title on January 1, 2027",
        description=None,
        category="championship",
        source=source,
        external_id="synthetic-6757-wbc",
        status=status,
        sport=None,
        sport_id=None,
        event_id=None,
        market_type=None,
        market_tier=5,
        llm_sport_category="boxing",
        mutually_exclusive=True,
        commence_time=None,
        resolution_date=None,
        created_at=None,
        updated_at=None,
        group_id=None,
        canonical_market_key=None,
        hook_description=None,
        image_url=None,
        category_tags=[],
        market_metadata=None,
        outcomes=legs,
    )


def _snapshot(outcome_id, probability, yes_bid, yes_ask, bookmaker="kalshi"):
    return SimpleNamespace(
        outcome_id=outcome_id,
        bookmaker=bookmaker,
        probability=probability,
        yes_bid=yes_bid,
        yes_ask=yes_ask,
        last_price=None,
    )


class TestThePredicate:
    def test_the_sentinel_is_the_canonical_spelling_and_a_terminal_no_result(self):
        """DRIFT GUARD. The repair reads ``RETRACTION_SOURCE``, not a literal.

        If ``kalshi_fabricated_loss`` ever renames the retraction, or
        ``resolution_authority`` ever promotes it to a real grade, this is the
        test that says the route's reading of it needs re-deciding.
        """
        assert RETRACTION_SOURCE == "ungradeable_result"
        assert RETRACTION_SOURCE in TERMINAL_SOURCES
        assert RETRACTION_SOURCE in KNOWN_SOURCES
        assert not is_authoritative(RETRACTION_SOURCE)

    @pytest.mark.parametrize(
        "resolution_source, protects",
        [
            (None, False),
            (RETRACTION_SOURCE, False),
            ("api_settlement", True),
            ("clob_authoritative", True),
            ("box_score", True),
            ("clean_resolution", True),
            # Adjacent terminal sources: PINNED to today's behaviour, not ruled.
            ("all_losers", True),
            ("did_not_play", True),
            ("withdrew", True),
            ("date_passed", True),
            # A guess is still a non-null source today; unchanged by this patch.
            ("pass2_guess", True),
        ],
    )
    def test_only_the_retraction_loses_the_exemption(self, resolution_source, protects):
        from app.routes.futures import row_carries_a_verdict

        assert row_carries_a_verdict(resolution_source) is protects

    def test_every_known_source_but_the_retraction_still_protects(self):
        """The patch is one source narrower than before — exactly one."""
        from app.routes.futures import row_carries_a_verdict

        yielding = {s for s in KNOWN_SOURCES if not row_carries_a_verdict(s)}
        assert yielding == {RETRACTION_SOURCE}
        assert all(row_carries_a_verdict(s) for s in AUTHORITATIVE_SOURCES)

    def test_the_route_asks_the_house_predicate_and_never_a_copy_of_it(self):
        """ANTI-FORK GUARD. One spelling, or the rails drift apart (#6876).

        ``futures_unsupported_price`` already owns this question — its own
        docstring is the measured case for it, and ``needs_trade_evidence`` and
        ``price_refuted_by_live_book`` on this same route already read it. A
        private ``_grade_protects_the_price`` beside them would be a second copy
        of a price policy, which is the drift ``kalshi_empty_book`` names in its
        own words. This asserts the route imports the canonical object rather
        than re-deriving an equal one, so a re-fork is red even when it agrees.
        """
        from app.routes import futures as futures_route
        from app.utils.futures_unsupported_price import row_carries_a_verdict

        assert futures_route.row_carries_a_verdict is row_carries_a_verdict
        source = inspect.getsource(futures_route)
        assert "_grade_protects_the_price" not in source
        assert "resolution_source is None and is_empty_book_midpoint" not in source


class TestTheLadderArm:
    def test_a_retracted_empty_book_leg_is_withheld(self):
        """🔴 RED ON BASE: the retraction claimed the exemption and kept its 49%."""
        from app.routes.futures import _empty_book_outcome_ids

        market = _market([_leg(1, "Title is vacant", *_EMPTY_BOOK, RETRACTION_SOURCE)])
        assert _empty_book_outcome_ids(market) == {1}

    def test_a_retracted_leg_on_a_real_quote_keeps_its_price(self):
        """A no-result marker must not DELETE a supported quote either."""
        from app.routes.futures import _empty_book_outcome_ids

        market = _market(
            [
                _leg(1, "hero, real quote", *_REAL_QUOTE, RETRACTION_SOURCE),
                _leg(
                    2,
                    "real 0.50 on a tight book",
                    0.500,
                    0.4900,
                    0.5100,
                    RETRACTION_SOURCE,
                ),
                _leg(3, "no book stored", 0.490, None, None, RETRACTION_SOURCE),
            ]
        )
        assert _empty_book_outcome_ids(market) == set()

    def test_the_specimens_own_hero_survives_on_a_book_as_empty_as_its_siblings(self):
        """THE PRODUCTION SHAPE, and it is not the one the fixtures above assume.

        Read off the stored rows for market 2951399 (2026-09-18, `db-query`), the
        93% hero's book is ``0.0100 / 0.9600`` — the SAME empty book as the
        thirteen 49s beside it, not the two-sided quote a reader would guess from
        the number. It survives on condition 3 alone: 0.93 is nowhere near that
        book's 0.485 midpoint, so it was never manufactured from it, while its
        siblings sit on theirs to the cent.

        That distinction is the whole safety argument for this change, so it is
        asserted on the real shape rather than on a tidier one: the arm withholds
        a FABRICATED MIDPOINT, never merely a leg whose book is thin. A widening
        that keyed on the empty book alone would pass every other test in this
        class and blank the one number on the page worth printing.
        """
        from app.routes.futures import _empty_book_outcome_ids

        hero = _leg(1, "Bruce Carrington", 0.930, 0.0100, 0.9600, RETRACTION_SOURCE)
        sibling = _leg(2, "Title is vacant", 0.490, 0.0100, 0.9700, RETRACTION_SOURCE)
        # `Nick Ball`, the other book on that page: 0.485 IS its midpoint.
        near = _leg(3, "Nick Ball", 0.485, 0.0100, 0.9600, RETRACTION_SOURCE)

        assert _empty_book_outcome_ids(_market([hero, sibling, near])) == {2, 3}

    def test_a_genuinely_graded_leg_on_a_stale_empty_book_is_still_exempt(self):
        """#6532's case, unchanged: a settled row's number is a result."""
        from app.routes.futures import _empty_book_outcome_ids

        market = _market(
            [
                _leg(
                    1, "settled winner", *_EMPTY_BOOK, "api_settlement", is_winner=True
                ),
                _leg(
                    2, "settled loser", *_EMPTY_BOOK, "api_settlement", is_winner=False
                ),
                _leg(3, "did_not_play", *_EMPTY_BOOK, "did_not_play"),
                _leg(4, "all_losers", *_EMPTY_BOOK, "all_losers"),
            ]
        )
        assert _empty_book_outcome_ids(market) == set()

    def test_null_is_winner_beside_the_retraction_is_not_a_result(self):
        """``is_winner`` NULL or FALSE next to the sentinel changes nothing."""
        from app.routes.futures import _empty_book_outcome_ids

        market = _market(
            [
                _leg(
                    1, "NULL verdict", *_EMPTY_BOOK, RETRACTION_SOURCE, is_winner=None
                ),
                _leg(
                    2, "FALSE verdict", *_EMPTY_BOOK, RETRACTION_SOURCE, is_winner=False
                ),
            ]
        )
        assert _empty_book_outcome_ids(market) == {1, 2}

    @pytest.mark.asyncio
    async def test_the_handler_withholds_the_wall_of_49s_and_keeps_the_hero(
        self, monkeypatch
    ):
        """The route, not the helper: three sibling arms stubbed to the empty set,
        so a withheld price here can only have come from the #6757 arm."""
        import app.routes.futures as fr

        legs = [
            _leg(i, f"retracted empty-book #{i}", *_EMPTY_BOOK, RETRACTION_SOURCE)
            for i in range(1, 14)
        ]
        legs.append(_leg(14, "hero, real quote", *_REAL_QUOTE, RETRACTION_SOURCE))
        market = _market(legs)

        class _Result:
            def scalar_one_or_none(self):
                return market

        class _DB:
            async def execute(self, *_a, **_k):
                return _Result()

        async def _no_ids(_db, _market):
            return set()

        async def _no_sources(_db, _market_id, _outcome_ids):
            return [], []

        monkeypatch.setattr(fr, "_unsupported_price_outcome_ids", _no_ids)
        monkeypatch.setattr(fr, "_refuted_midpoint_outcome_ids", _no_ids)
        monkeypatch.setattr(fr, "_book_refuted_outcome_ids", lambda _m: set())
        monkeypatch.setattr(fr, "_load_market_sources", _no_sources)

        detail = await fr.get_futures_market(2951399, _DB())

        assert detail["prices_withheld"] == 13
        assert len(detail["outcomes"]) == 14, "rows stay; prices are withheld"
        by_name = {o["name"]: o for o in detail["outcomes"]}
        assert by_name["hero, real quote"]["probability"] == pytest.approx(0.93)
        assert all(
            by_name[f"retracted empty-book #{i}"]["probability"] is None
            for i in range(1, 14)
        )
        # Identity and the stored grade travel untouched.
        assert (
            by_name["retracted empty-book #1"]["resolution_source"] == RETRACTION_SOURCE
        )
        assert by_name["retracted empty-book #1"]["is_winner"] is False


class TestTheChartArm:
    def test_retracted_midpoints_are_dropped_and_a_real_point_survives(self):
        """🔴 RED ON BASE. PER POINT: the empty-book midpoints go, the real point stays."""
        from app.routes.futures import _drop_unsupported_snapshot_points

        outcomes = [
            SimpleNamespace(id=1, resolution_source=RETRACTION_SOURCE, is_winner=False)
        ]
        snapshots = [
            _snapshot(1, 0.450, 0.4000, 0.5000),
            _snapshot(1, *_EMPTY_BOOK),
            _snapshot(1, *_EMPTY_BOOK),
            _snapshot(1, 0.490, 0.0100, 0.9600),
        ]
        kept = _drop_unsupported_snapshot_points(snapshots, outcomes)
        assert [s.probability for s in kept] == [pytest.approx(0.450)]

    def test_a_settled_journey_is_still_shown_whole(self):
        from app.routes.futures import _drop_unsupported_snapshot_points

        for source, winner in (
            ("api_settlement", True),
            ("api_settlement", False),
            ("all_losers", False),
        ):
            outcomes = [
                SimpleNamespace(id=1, resolution_source=source, is_winner=winner)
            ]
            snapshots = [_snapshot(1, *_EMPTY_BOOK) for _ in range(3)]
            assert (
                len(_drop_unsupported_snapshot_points(snapshots, outcomes)) == 3
            ), source

    def test_the_two_arms_read_the_same_row_the_same_way(self):
        """THE LADDER AND THE CHART MUST NOT DISAGREE (#5898) — for the retraction too."""
        from app.routes.futures import (
            _drop_unsupported_snapshot_points,
            _empty_book_outcome_ids,
        )

        for source in (None, RETRACTION_SOURCE, "api_settlement", "did_not_play"):
            leg = _leg(1, "leg", *_EMPTY_BOOK, source)
            ladder_withholds = 1 in _empty_book_outcome_ids(_market([leg]))
            chart_drops = (
                _drop_unsupported_snapshot_points(
                    [_snapshot(1, *_EMPTY_BOOK)],
                    [SimpleNamespace(id=1, resolution_source=source, is_winner=False)],
                )
                == []
            )
            assert ladder_withholds is chart_drops, source
