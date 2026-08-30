"""The illiquidity grade — the rule, and the four surfaces that carry it.

UX-P157, Alex's 2026-08-28 ruling / #2256 / #2257.

WHAT THESE GUARD, stated as the failures they would catch rather than as the
code they cover:

  1. **The rule stops being threshold-free.** Every constant a later queue could
     be tempted to add — a dollar floor, a spread width, a "small enough to
     ignore" tail — is asserted against here by specimen. Q428 measured why
     they cannot exist (the distributions have no empty middle) and the cheap
     way to lose that is to tune one in during a follow-up.
  2. **The mark becomes a filter.** The grid charter and Alex's triage ruling
     both forbid deleting a thin cell. `test_marking_never_removes_a_cell`
     asserts the count of rendered cells is identical with and without the
     signal — the one property that must survive every future change here.
  3. **A blend launders a thin leg.** A cell built from one traded book and one
     dead one must grade as the dead one. This is the UX-P135 defect (a row
     reading live off its freshest leg) in a new field, and it is the reason
     `thinnest_liquidity` exists at all.
  4. **An absence reads as a clean bill of health.** Gotcha #53. An outcome we
     cannot check must grade `unknown`, never `traded`.

The specimens are the real ones from #2257's residual table wherever a real one
exists, so a change that stops explaining Venus Williams' inverted pair fails
here rather than on the page.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.market_liquidity import (
    LIQUIDITY_BARELY,
    LIQUIDITY_THIN,
    LIQUIDITY_TRADED,
    LIQUIDITY_UNKNOWN,
    REASON_NO_TRADES_24H,
    REASON_SPREAD_EXCEEDS_PRICE,
    grade_liquidity,
    thinnest_liquidity,
)
from app.utils.tournament_grid import build_playoff_grid
from app.utils.tournament_slate import build_props

NOW = datetime(2026, 8, 28, 22, 0, tzinfo=timezone.utc)

#: "We asked the venue half an hour ago." UX-P158 made the volume fact take the
#: age of its own observation, so every specimen below that means to CHECK that
#: fact has to say when it was checked. A literal rather than a fixture: these
#: are unit specimens and an age is one of their coordinates now, exactly like
#: a bid.
FRESH_HOURS = 0.5


# ═══════════════════════════════════════════════════════════════════════
# THE RULE
# ═══════════════════════════════════════════════════════════════════════


class TestGradeLiquidity:
    def test_a_traded_market_on_a_tight_book_is_not_marked(self):
        """Ben Shelton's R16 cell: $7 in 24h on a 0.69/0.71 book.

        Deliberately one of #2257's SIXTEEN and deliberately UNMARKED. Seven
        dollars is a real trade and two cents is not a wide book, so a rule
        that marked this would be marking "small" rather than "untradeable",
        and the next queue would have to invent a floor to say where small
        begins. The report says out loud that three of the sixteen come out
        this way; that is the rule being honest, not the rule missing.
        """
        assert grade_liquidity(
            bid=0.69, ask=0.71, volume_24h=7, volume_observed_age_hours=FRESH_HOURS
        ) == {
            "level": LIQUIDITY_TRADED,
            "reasons": [],
        }

    def test_no_trades_in_a_day_is_one_level(self):
        assert grade_liquidity(
            bid=0.69, ask=0.71, volume_24h=0, volume_observed_age_hours=FRESH_HOURS
        ) == {
            "level": LIQUIDITY_THIN,
            "reasons": [REASON_NO_TRADES_24H],
        }

    def test_a_book_wider_than_its_own_number_is_one_level(self):
        """#2257's shape: quoted 0.00/0.08 — eight cents, and TIGHT by
        `FEED_PHANTOM_MIN_SPREAD` (0.20 absolute) — while the uncertainty band
        is twice the 4% it is printing."""
        assert grade_liquidity(
            bid=0.0, ask=0.08, volume_24h=195, volume_observed_age_hours=FRESH_HOURS
        ) == {
            "level": LIQUIDITY_THIN,
            "reasons": [REASON_SPREAD_EXCEEDS_PRICE],
        }

    def test_both_wrong_is_the_second_level(self):
        """Venus Williams' QF cell, the specimen Alex's ruling is about."""
        graded = grade_liquidity(
            bid=0.0, ask=0.08, volume_24h=0, volume_observed_age_hours=FRESH_HOURS
        )
        assert graded["level"] == LIQUIDITY_BARELY
        assert set(graded["reasons"]) == {
            REASON_NO_TRADES_24H,
            REASON_SPREAD_EXCEEDS_PRICE,
        }

    def test_the_djokovic_book_q428_declined_is_the_second_level_too(self):
        """7c bid / 98c ask, the book behind the $5 trade that produced a 71%
        R16 above a 79% QF. Q428 stopped the number being published from it;
        this asserts that if such a book ever reaches a reader again it arrives
        wearing the strongest mark we have."""
        assert grade_liquidity(
            bid=0.07, ask=0.98, volume_24h=0, volume_observed_age_hours=FRESH_HOURS
        )["level"] == (LIQUIDITY_BARELY)

    def test_nothing_to_check_is_unknown_and_never_traded(self):
        """GOTCHA #53. An outcome with no book and no volume figure is a
        question we could not ask, and `traded` would be an absence rendered as
        a good answer — the exact class the gotcha is about."""
        assert grade_liquidity()["level"] == LIQUIDITY_UNKNOWN
        assert grade_liquidity(bid=None, ask=None, volume_24h=None)["level"] == (
            LIQUIDITY_UNKNOWN
        )

    def test_a_poison_value_is_unknown_not_a_mark(self):
        """A mark invented from a parse failure is indistinguishable, on the
        page, from one we measured."""
        for bad in ("wide", {}, [], float("nan")):
            assert grade_liquidity(bid=bad, ask=bad, volume_24h=bad)["level"] == (
                LIQUIDITY_UNKNOWN
            )

    def test_half_the_evidence_still_grades_on_what_it_has(self):
        """One known-bad fact with the other uncheckable is `thin` — the honest
        floor. Not `barely` (we have not found two problems) and not `unknown`
        (we have found one)."""
        assert grade_liquidity(volume_24h=0, volume_observed_age_hours=FRESH_HOURS) == {
            "level": LIQUIDITY_THIN,
            "reasons": [REASON_NO_TRADES_24H],
        }
        assert grade_liquidity(bid=0.0, ask=0.08) == {
            "level": LIQUIDITY_THIN,
            "reasons": [REASON_SPREAD_EXCEEDS_PRICE],
        }

    def test_an_empty_book_on_both_sides_is_marked(self):
        """0.00/0.00 is no offers in either direction. It is the one value a
        strict `>` would let through unmarked, which is why the comparison is
        `>=`."""
        assert (
            REASON_SPREAD_EXCEEDS_PRICE
            in grade_liquidity(
                bid=0.0, ask=0.0, volume_24h=5, volume_observed_age_hours=FRESH_HOURS
            )["reasons"]
        )

    def test_a_crossed_book_is_not_graded_as_tight(self):
        """`ask < bid` is a garbled reading, not a tight market. It must not
        come back `traded` — that would be the parse error reading as a clean
        bill of health."""
        graded = grade_liquidity(
            bid=0.90, ask=0.10, volume_24h=0, volume_observed_age_hours=FRESH_HOURS
        )
        assert graded["level"] == LIQUIDITY_THIN
        assert graded["reasons"] == [REASON_NO_TRADES_24H]

    @pytest.mark.parametrize(
        "bid,ask,marked",
        [
            # ratio just under 1 — the book is narrower than its own number
            (0.30, 0.55, False),
            # exactly 1 — `>=`, so marked
            (0.25, 0.75, True),
            # over 1
            (0.10, 0.90, True),
        ],
    )
    def test_the_width_test_carries_no_constant(self, bid, ask, marked):
        """The comparison is `ask - bid >= (bid + ask) / 2` and nothing else.

        Parametrised across the boundary so that adding a tolerance — the
        obvious "tidy-up" for the straddling markets Q428 measured — fails
        here. If a tolerance is ever genuinely wanted it needs its own ruling
        and its own measurement, not a quiet epsilon.
        """
        graded = grade_liquidity(
            bid=bid, ask=ask, volume_24h=100, volume_observed_age_hours=FRESH_HOURS
        )
        assert (REASON_SPREAD_EXCEEDS_PRICE in graded["reasons"]) is marked


class TestThinnestLiquidity:
    def test_a_blend_is_as_solid_as_its_thinnest_leg(self):
        """The UX-P135 rule in a new field. A row that took the BEST of its
        legs is the defect that let a twenty-day-old number render live."""
        assert thinnest_liquidity([LIQUIDITY_TRADED, LIQUIDITY_BARELY]) == (
            LIQUIDITY_BARELY
        )
        assert thinnest_liquidity([LIQUIDITY_THIN, LIQUIDITY_TRADED]) == LIQUIDITY_THIN

    def test_one_uncheckable_leg_stops_the_cell_being_cleared(self):
        assert thinnest_liquidity([LIQUIDITY_TRADED, LIQUIDITY_UNKNOWN]) == (
            LIQUIDITY_UNKNOWN
        )

    def test_a_found_problem_outranks_an_uncheckable_leg(self):
        assert thinnest_liquidity([LIQUIDITY_UNKNOWN, LIQUIDITY_THIN]) == LIQUIDITY_THIN

    def test_nothing_at_all_is_unknown(self):
        assert thinnest_liquidity([]) == LIQUIDITY_UNKNOWN
        assert thinnest_liquidity([None, "not-a-level"]) == LIQUIDITY_UNKNOWN


# ═══════════════════════════════════════════════════════════════════════
# THE SURFACES
# ═══════════════════════════════════════════════════════════════════════


def _price(
    probability,
    *,
    bid=None,
    ask=None,
    volume=None,
    hours_ago=1.0,
    volume_age_hours=FRESH_HOURS,
):
    return {
        "probability": probability,
        "opening_probability": probability,
        "observed_at": NOW - timedelta(hours=hours_ago),
        "source_name": "yes",
        "liquidity": grade_liquidity(
            bid=bid,
            ask=ask,
            volume_24h=volume,
            volume_observed_age_hours=volume_age_hours,
        ),
    }


def _grid_register(*, second_source: bool):
    """Two players, one reach round, one title board row.

    `second_source` adds a Polymarket leg to Venus' QF cell so the blend path
    is exercised — the grid's own blender is what turns two grades into one.
    """
    sources = [
        {
            "source": "kalshi",
            "status": "live",
            "market_id": 1,
            "market_external_id": "KX-VENUS-QF",
            "outcome_id": 11,
        }
    ]
    if second_source:
        sources.append(
            {
                "source": "polymarket",
                "status": "live",
                "market_id": 2,
                "market_external_id": "PM-VENUS-QF",
                "outcome_id": 12,
            }
        )
    return {
        "slug": "us-open",
        "players": [
            {
                "entity_key": "venus-williams",
                "display_name": "Venus Williams",
                "draw": "womens",
                "seed": None,
            },
            {
                "entity_key": "iga-swiatek",
                "display_name": "Iga Swiatek",
                "draw": "womens",
                "seed": 1,
            },
        ],
        "reaches": [
            {
                "entity_key": "venus-williams",
                "draw": "womens",
                "round": "QF",
                "sources": sources,
            },
            {
                "entity_key": "iga-swiatek",
                "draw": "womens",
                "round": "QF",
                "sources": [
                    {
                        "source": "kalshi",
                        "status": "live",
                        "market_id": 3,
                        "market_external_id": "KX-IGA-QF",
                        "outcome_id": 21,
                    }
                ],
            },
        ],
    }


def _grid(prices, *, register=None, board_rows=None):
    """One womens grid. `build_playoff_grid` rather than `build_grids` because
    the latter iterates BOARDS, and a draw whose contenders are all ladder-only
    (which is the thin tail this queue is about) has no board rows at all."""
    return build_playoff_grid(
        register if register is not None else _grid_register(second_source=False),
        board_rows=board_rows or [],
        prices=prices,
        draw="womens",
        now=NOW,
    )


class TestTheGridCarriesTheMark:
    def test_a_dead_book_cell_is_marked_and_a_traded_one_is_not(self):
        prices = {
            # Venus' QF: nothing traded, book wider than the number.
            11: _price(0.036, bid=0.0, ask=0.08, volume=0),
            # Iga's QF: a real book with real trading.
            21: _price(0.705, bid=0.70, ask=0.71, volume=195),
        }
        grid = _grid(prices)
        cells = {row["entity_key"]: row["cells"]["QF"] for row in grid["rows"]}
        assert cells["venus-williams"]["liquidity"] == LIQUIDITY_BARELY
        assert cells["venus-williams"]["liquidity_reasons"] == [
            REASON_NO_TRADES_24H,
            REASON_SPREAD_EXCEEDS_PRICE,
        ]
        assert cells["iga-swiatek"]["liquidity"] == LIQUIDITY_TRADED
        assert cells["iga-swiatek"]["liquidity_reasons"] == []

    def test_marking_never_removes_a_cell(self):
        """THE PROPERTY THAT MUST SURVIVE EVERY FUTURE CHANGE HERE.

        Alex's triage ruling: illiquid cells are documented, not deleted. Q428
        measured what filtering on this signal would cost — 416 priced cells
        down to about 120 — and refused it. So the same register priced two
        ways must produce the same number of priced cells, the same
        probabilities, and differ ONLY in the mark.
        """
        register = _grid_register(second_source=False)
        dead = {
            11: _price(0.036, bid=0.0, ask=0.08, volume=0),
            21: _price(0.705, bid=0.0, ask=0.08, volume=0),
        }
        alive = {
            11: _price(0.036, bid=0.03, ask=0.04, volume=900),
            21: _price(0.705, bid=0.70, ask=0.71, volume=900),
        }
        marked = _grid(dead, register=register)
        clean = _grid(alive, register=register)

        assert marked["priced_cells"] == clean["priced_cells"]
        assert marked["total_cells"] == clean["total_cells"]
        assert marked["alarm_cells"] == clean["alarm_cells"] == 0
        for a, b in zip(marked["rows"], clean["rows"]):
            for key, cell in a["cells"].items():
                assert cell["probability"] == b["cells"][key]["probability"]
                assert cell["state"] == b["cells"][key]["state"]
        assert {row["cells"]["QF"]["liquidity"] for row in marked["rows"]} == {
            LIQUIDITY_BARELY
        }
        assert {row["cells"]["QF"]["liquidity"] for row in clean["rows"]} == {
            LIQUIDITY_TRADED
        }

    def test_a_blended_cell_takes_its_thinnest_leg(self):
        """One venue quoting a healthy book, the other quoting nothing anybody
        will trade at. The reader sees ONE number and both books are inside it.
        """
        prices = {
            11: _price(0.036, bid=0.03, ask=0.04, volume=900),
            12: _price(0.040, bid=0.0, ask=0.08, volume=0),
            21: _price(0.705, bid=0.70, ask=0.71, volume=195),
        }
        grid = _grid(prices, register=_grid_register(second_source=True))
        cell = next(
            row["cells"]["QF"]
            for row in grid["rows"]
            if row["entity_key"] == "venus-williams"
        )
        assert cell["source_count"] == 2
        assert cell["probability"] is not None
        assert cell["liquidity"] == LIQUIDITY_BARELY
        # The UNION of both legs' reasons, not the worst leg's own list: the
        # cell has both problems and the reveal should be able to name both.
        assert cell["liquidity_reasons"] == [
            REASON_NO_TRADES_24H,
            REASON_SPREAD_EXCEEDS_PRICE,
        ]

    def test_a_non_priced_cell_is_unknown_and_draws_nothing(self):
        """A settled result, a censused absence and an alarm have no live book
        to grade. `unknown` renders no mark, so those cells are untouched."""
        grid = _grid({})
        for row in grid["rows"]:
            for cell in row["cells"].values():
                assert cell["liquidity"] == LIQUIDITY_UNKNOWN
                assert cell["liquidity_reasons"] == []

    def test_the_title_column_inherits_the_board_row_rather_than_regrading(self):
        """The title cell IS the board's cell. A second grading pass over the
        same two books would be the "second opinion one tab away" the column
        exists to avoid."""
        boards = [
            {
                "entity_key": "venus-williams",
                "display_name": "Venus Williams",
                "seed": None,
                "rank": 1,
                "probability": 0.004,
                "state": "live",
                "price_state": "live",
                "on_board": True,
                "sources": [],
                "age_hours": 1.0,
                "observed_at": NOW.isoformat(),
                "blend_rule": "single",
                "divergent": False,
                "liquidity": LIQUIDITY_BARELY,
                "liquidity_reasons": [
                    REASON_NO_TRADES_24H,
                    REASON_SPREAD_EXCEEDS_PRICE,
                ],
            }
        ]
        grid = _grid({}, board_rows=boards)
        title = next(
            row["cells"]["title"]
            for row in grid["rows"]
            if row["entity_key"] == "venus-williams"
        )
        assert title["liquidity"] == LIQUIDITY_BARELY
        assert title["liquidity_reasons"] == [
            REASON_NO_TRADES_24H,
            REASON_SPREAD_EXCEEDS_PRICE,
        ]


class TestThePropsCardsCarryTheMark:
    def _register(self):
        return {
            "slug": "us-open",
            "props": [
                {
                    "key": "second-major",
                    "title": "Who wins a second major this year?",
                    "hook": None,
                    "draw": None,
                    "source": "kalshi",
                    "markets": [{"market_external_id": "KX-A"}],
                    "outcomes": [
                        {
                            "entity_key": "carlos-alcaraz",
                            "display_name": "Carlos Alcaraz",
                            "outcome_id": 31,
                            "market_external_id": "KX-A",
                            "is_answer": False,
                        },
                        {
                            "entity_key": "jannik-sinner",
                            "display_name": "Jannik Sinner",
                            "outcome_id": 32,
                            "market_external_id": "KX-A",
                            "is_answer": False,
                        },
                    ],
                }
            ],
        }

    def test_each_row_grades_itself_and_the_card_takes_the_worst(self):
        """A field card's leader can be heavily traded while the tail it is
        printed above is quoted by nobody. Marking only the card would say the
        wrong thing about both ends of it."""
        prices = {
            31: _price(0.42, bid=0.41, ask=0.43, volume=8_400),
            32: _price(0.03, bid=0.0, ask=0.06, volume=0),
        }
        card = build_props(self._register(), prices=prices, now=NOW)[0]
        by_key = {row["entity_key"]: row for row in card["outcomes"]}
        assert by_key["carlos-alcaraz"]["liquidity"] == LIQUIDITY_TRADED
        assert by_key["jannik-sinner"]["liquidity"] == LIQUIDITY_BARELY
        assert card["liquidity"] == LIQUIDITY_BARELY

    def test_an_unpriced_row_does_not_vote_on_the_card(self):
        """Matching the freshness rule beside it: a row with no reading has no
        book to be thin, and letting it vote would mark every partially-quoted
        field card as barely traded."""
        prices = {
            31: _price(0.42, bid=0.41, ask=0.43, volume=8_400),
            32: _price(None),
        }
        card = build_props(self._register(), prices=prices, now=NOW)[0]
        assert card["liquidity"] == LIQUIDITY_TRADED


# ═══════════════════════════════════════════════════════════════════════
# THE WRITER — WITHOUT IT THE GRADE HAS ONE REACHABLE LEVEL
# ═══════════════════════════════════════════════════════════════════════


class TestTheSubMarketRecordsItsOwn24hVolume:
    """UX-P157's backend rider, and the reason it is not optional.

    MEASURED 2026-08-28 against production, before a line was written: all
    **336** US Open reach-a-round markets — one per bracket-grid cell — hold
    ``volume_24h IS NULL``, while the PARENT event rows they hang off hold real
    figures (event `910235` = $5,493). The parent upsert has always written the
    column; the per-condition sub-market upsert never has, though the same loop
    is holding `market.volume_24h`, parsed by `PolymarketMarket` from Gamma's
    own `volume24hr`.

    The consequence is not a missing column, it is a MISSING GRADE. Alex's
    ruling asks for at least two levels; `grade_liquidity` builds them from two
    facts, and with this one absent every cell on the surface the ruling is
    about could only ever reach level one. A graded signal with one reachable
    grade is not a graded signal.

    Asserted against the source the way `test_polymarket_under_leg_book` does,
    for the same reason: this is a WRITER defect, the fix is four lines in one
    upsert, and a behavioural test would need the whole Gamma ingest stood up
    to observe a column being set.
    """

    @staticmethod
    def _sub_market_block() -> str:
        import inspect

        from app.tasks import polymarket

        src = inspect.getsource(polymarket)
        start = src.index("# ── ITS OWN 24h VOLUME (UX-P157, #2256).")
        end = src.index("# Create Over/Yes outcome")
        assert end > start
        return src[start:end]

    def test_the_insert_carries_the_volume(self):
        assert "volume_24h=sub_volume_24h," in self._sub_market_block()

    def test_the_conflict_update_carries_it_too(self):
        """An insert-only fix leaves all 336 existing rows NULL forever, and
        Polymarket re-serves open events continuously — so the UPDATE path is
        the one that repairs the live grid."""
        assert '"volume_24h": sub_volume_24h,' in self._sub_market_block()

    def test_it_is_null_preserving(self):
        """A market Gamma serves without the field keeps NULL, which grades as
        `unknown` and draws nothing. A fabricated 0 would read downstream as a
        measured "nobody traded this" — an absence wearing a finding's clothes,
        gotcha #53 in the column that the finding is built from."""
        block = self._sub_market_block()
        assert "if market.volume_24h is not None" in block
        assert "else None" in block
        assert "int(market.volume_24h or 0)" not in block
