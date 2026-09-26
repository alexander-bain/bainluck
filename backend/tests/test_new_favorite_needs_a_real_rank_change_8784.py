"""#8784 — "New favorite" only when the stored rank change describes a real overtake.

Served on Discover page one 2026-09-26 03:25Z: "2027 Steel Bridge National
Champion — New favorite: University of Florida (81%)". Florida opened the market
at 79.5% and led it throughout. Its row read `rank 1, rank_change_24h +98,
probability_change_24h NULL`: the price blinked out for one poll (unpriced legs
rank after every priced one) and came back as a 98-place "rise".

Three more of the eight served "New favorite" cards led on a rank change whose
old rank (`rank + rank_change_24h`) is below 1 — Galatasaray -5, Charley Hull -1,
Alina Korneeva -2 — which describes no board that ever existed.

Both directions are asserted: the controls are real overtakes, including the
one the feed's builders make hard to see (the leader's own price held, so the
builder hands the scorer `probability_change_24h: None` for a stored 0.0).
"""

from types import SimpleNamespace

import pytest

from app.routes import feed
from app.utils.feed_reasons import generate_futures_headline
from app.utils.futures_highlights import (
    compute_futures_highlight,
    rank_claim_is_evidence,
)


def _row(name, probability, rank, rank_change, *, change, prior_priced, opening=None):
    return {
        "name": name,
        "probability": probability,
        "probability_change_24h": change,
        "rank": rank,
        "rank_change_24h": rank_change,
        "prior_priced": prior_priced,
        "opening_probability": opening,
    }


# Production rows, 2026-09-26 03:25Z (`futures_outcomes`, market 61461617).
STEEL_BRIDGE = [
    _row("University of Florida", 0.805, 1, 98, change=None, prior_priced=False, opening=0.795),
    _row("Alaska Fairbanks", 0.07, 2, -1, change=-0.39, prior_priced=True),
    _row("Youngstown State", 0.065, 3, 96, change=None, prior_priced=False, opening=0.075),
    _row("Lafayette College", 0.06, 4, -1, change=-0.38, prior_priced=True),
    _row("Cal Poly Pomona", 0.06, 4, -2, change=-0.38, prior_priced=True),
]

# Market 60607786 — rank 1 with -5 puts the old rank at -4.
GALATASARAY = [
    _row("Galatasaray", 0.485, 1, -5, change=None, prior_priced=True, opening=0.055),
    _row("Bodø/Glimt", 0.0355, 4, -3, change=None, prior_priced=True, opening=0.04),
]

REAL_OVERTAKE = [
    _row("Boston Celtics", 0.41, 1, 1, change=0.06, prior_priced=True, opening=0.30),
    _row("Denver Nuggets", 0.33, 2, -1, change=-0.07, prior_priced=True, opening=0.38),
]

# The old leader fell past a leader whose price held exactly: a stored 0.0, which
# `_score_futures` folds into None. `prior_priced` is what keeps this true claim.
HELD_PRICE_OVERTAKE = [
    _row("Boston Celtics", 0.35, 1, 1, change=None, prior_priced=True, opening=0.30),
    _row("Denver Nuggets", 0.30, 2, -1, change=-0.10, prior_priced=True, opening=0.38),
]


def _score(rows, name="2027 Steel Bridge National Champion"):
    return compute_futures_highlight(
        market_name=name,
        market_tier=1,
        sport_category="basketball",
        outcomes=rows,
    )


def _headline(result, rows):
    leader = rows[0]
    return generate_futures_headline(
        result.reasons,
        top_mover_name=result.top_mover_name,
        top_mover_change=result.top_mover_change,
        leader_name=leader["name"],
        leader_probability=leader["probability"],
    )


class TestTheClaimIsRefused:
    def test_a_leader_that_only_got_its_price_back_is_not_a_new_favorite(self):
        result = _score(STEEL_BRIDGE)
        assert "leader_change" not in result.reasons
        assert not result.flags.leader_changed
        assert "New favorite" not in (_headline(result, STEEL_BRIDGE) or "")

    def test_an_impossible_old_rank_is_not_a_new_favorite(self):
        result = _score(GALATASARAY, "UEFA Champions League: League Phase Winner")
        assert "leader_change" not in result.reasons
        assert "New favorite" not in (_headline(result, GALATASARAY) or "")

    @pytest.mark.parametrize("rank_change", [-1, -2, -5])
    def test_every_negative_change_at_rank_one_is_refused(self, rank_change):
        row = _row("X", 0.4, 1, rank_change, change=0.01, prior_priced=True)
        assert not rank_claim_is_evidence(row)

    def test_unpriced_returns_do_not_make_a_shakeup(self):
        # Two top-5 rank changes on Steel Bridge come from legs regaining a
        # price; the other three are -1/-2 moves caused by those returns.
        rows = [
            _row("A", 0.5, 1, 40, change=None, prior_priced=False),
            _row("B", 0.3, 2, 40, change=None, prior_priced=False),
            _row("C", 0.1, 3, 0, change=0.0, prior_priced=True),
        ]
        assert "rank_shakeup" not in _score(rows).reasons


class TestRealOvertakesKeepTheClaim:
    def test_a_real_overtake_is_still_a_new_favorite(self):
        result = _score(REAL_OVERTAKE, "NBA Champion")
        assert "leader_change" in result.reasons
        assert "New favorite" in (_headline(result, REAL_OVERTAKE) or "")

    def test_a_leader_whose_own_price_held_is_still_a_new_favorite(self):
        result = _score(HELD_PRICE_OVERTAKE, "NBA Champion")
        assert "leader_change" in result.reasons

    def test_a_real_shakeup_is_still_a_shakeup(self):
        rows = [
            _row("A", 0.5, 1, 1, change=0.05, prior_priced=True),
            _row("B", 0.3, 2, -1, change=-0.05, prior_priced=True),
            _row("C", 0.1, 3, 0, change=0.0, prior_priced=True),
        ]
        assert "rank_shakeup" in _score(rows).reasons

    def test_a_row_without_the_key_keeps_the_old_reading(self):
        # Hand-built rows (tests, the digest) never looked, so they cannot refuse.
        assert rank_claim_is_evidence({"rank": 1, "rank_change_24h": 3})
        assert not rank_claim_is_evidence({"rank": 1, "rank_change_24h": 0})
        assert not rank_claim_is_evidence({"rank": None, "rank_change_24h": 3})


class TestTheFeedBuildersSayWhatTheyKnow:
    def test_the_trace_builder_reads_prior_priced_off_the_stored_column(self):
        outcomes = [
            SimpleNamespace(
                id=1, name="University of Florida", team_id=None, external_id="UF",
                current_probability=0.805, probability_change_24h=None,
                rank=1, rank_change_24h=98, opening_probability=0.795,
            ),
            SimpleNamespace(
                id=2, name="Boston", team_id=None, external_id="BOS",
                current_probability=0.1, probability_change_24h=0.0,
                rank=2, rank_change_24h=-1, opening_probability=None,
            ),
        ]
        rows, _leader, _prob = feed._top_outcomes_for_trace(
            SimpleNamespace(outcomes=outcomes, name="Steel Bridge")
        )
        by_name = {r["name"]: r for r in rows}
        assert by_name["University of Florida"]["prior_priced"] is False
        # A stored 0.0 had a price before; it is not "unpriced".
        assert by_name["Boston"]["prior_priced"] is True

    def test_every_scoring_row_that_carries_a_rank_change_carries_prior_priced(self):
        """Pin the SET, not one site: three builders hand rows to the scorer."""
        import inspect

        source = inspect.getsource(feed)
        rank_rows = source.count('"rank_change_24h": o.rank_change_24h,') + source.count(
            '"rank_change_24h": outcome.rank_change_24h,'
        )
        assert rank_rows == 3
        assert source.count('"prior_priced": ') == rank_rows
