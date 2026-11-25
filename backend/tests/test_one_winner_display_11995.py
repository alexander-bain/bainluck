"""The served full field owns normalization and whole-percent allocation."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.routes.feed import _apply_card_percents, _normalize_feed_probabilities
from app.utils.outcome_display import normalize_display_probs


@pytest.mark.parametrize(
    "raw, normalize",
    [([0.625, 0.185], False), ([0.815, 0.1, 0.05, 0.04], True),
     ([0.90, 0.71], False)],
)
def test_kalshi_zero_bids_have_no_share_on_the_page_set_or_card(raw, normalize):
    from app.routes.feed import _feed_display_scale
    from app.utils.container_machinery import _canonical_market_outcome_map
    from app.utils.outcome_display import mark_kalshi_ask_ceilings

    market = SimpleNamespace(source="kalshi", status="open")
    complete = [
        SimpleNamespace(id=i, name=f"Named player {i}", current_probability=p,
                        current_yes_bid=p - 0.001, current_yes_ask=p + 0.001)
        for i, p in enumerate(raw)
    ]
    complete.extend([
        SimpleNamespace(id=90, name="Five-cent ceiling", current_probability=0.05,
                        current_yes_bid=0, current_yes_ask=0.05),
        SimpleNamespace(id=91, name="One-cent ceiling", current_probability=0.01,
                        current_yes_bid=0, current_yes_ask=0.01),
    ])
    page = [
        {"id": o.id, "name": o.name, "probability": o.current_probability}
        for o in complete
    ]
    card = deepcopy(page)
    mark_kalshi_ask_ceilings(market, page, {o.id: o for o in complete})
    expected_scale = sum(raw) if normalize else 1
    assert normalize_display_probs(page) is normalize
    _normalize_feed_probabilities(card, complete, market=market, mutually_exclusive=True)
    assert _feed_display_scale(complete, market=market, mutually_exclusive=True) == pytest.approx(expected_scale)
    set_rows, *_ = _canonical_market_outcome_map(page)
    for surface in (page, set_rows, card):
        assert [r["probability"] for r in surface[:-2]] == pytest.approx(
            [p / expected_scale for p in raw]
        )
        assert [r["probability"] for r in surface[-2:]] == [0.05, 0.01]
    assert [r.get("ask_ceiling") for r in page[-2:]] == [0.05, 0.01]
    assert all("rendered_percent" not in r for r in page[-2:])


def test_kalshi_ask_only_ceiling_is_never_a_price_input():
    from app.tasks.kalshi import _kalshi_yes_probability

    assert _kalshi_yes_probability(0, 0.01, None) is None
    assert _kalshi_yes_probability(0, 0.05, 0.71) is None
    assert _kalshi_yes_probability(0.01, 0.03, 0.71) == pytest.approx(0.02)


def test_a_partial_preview_does_not_round_supported_rows_up_to_100():
    from app.utils.container_machinery import _canonical_market_outcome_map
    from app.utils.outcome_display import mark_kalshi_ask_ceilings

    market = SimpleNamespace(source="kalshi", status="open")
    outcomes = [
        SimpleNamespace(id=1, name="Alice", current_probability=0.61, current_yes_bid=0.60),
        SimpleNamespace(id=2, name="Bob", current_probability=0.38, current_yes_bid=0.37),
        SimpleNamespace(id=3, name="Carol", current_probability=None, current_yes_bid=0,
                        current_yes_ask=0.05),
    ]
    page = [
        {"id": outcome.id, "name": outcome.name, "probability": outcome.current_probability}
        for outcome in outcomes
    ]
    preview = deepcopy(page[:2])
    mark_kalshi_ask_ceilings(market, page, {outcome.id: outcome for outcome in outcomes})
    assert normalize_display_probs(page) is False
    _normalize_feed_probabilities(preview, outcomes, mutually_exclusive=True, market=market)
    _apply_card_percents(preview)
    set_rows, *_ = _canonical_market_outcome_map(page)
    assert [row["probability"] for row in page[:2]] == [0.61, 0.38]
    for surface in (preview, set_rows):
        assert [row["rendered_percent"] for row in surface] == [61, 38]


@pytest.mark.parametrize(
    "book, divisor",
    [
        ("ceiling", 1.10),
        ("withheld ceiling", 1.10),
        ("unknown residual", 1),
        ("stale ceiling", 1),
    ],
)
def test_detail_set_and_card_distinguish_zero_bid_from_unknown_mass(book, divisor):
    from datetime import datetime, timedelta, timezone

    from app.routes.feed import _feed_display_scale, _field_has_withheld_legs
    from app.routes.futures import _apply_verified_title_to_detail, _format_market_detail
    from app.utils.container_machinery import _canonical_market_outcome_map
    from app.utils.futures_verified_title import Refusal
    from tests.test_midterms_complete_outcome_prices_11948 import _detail_field

    market = _detail_field()
    market.outcomes = market.outcomes[:3]
    observed_at = datetime(2026, 11, 24, tzinfo=timezone.utc)
    for outcome, (price, bid, ask) in zip(
        market.outcomes, [(0.68, 0.65, 0.71), (0.42, 0.40, 0.44), (None, 0, 0.05)]
    ):
        outcome.current_probability = price
        outcome.current_yes_bid = bid
        outcome.current_yes_ask = ask
        outcome.last_updated = observed_at

    ceiling = market.outcomes[-1]
    withheld = {ceiling.id} if book == "withheld ceiling" else set()
    if book == "unknown residual":
        ceiling.current_yes_bid = ceiling.current_yes_ask = None
    elif book == "stale ceiling":
        ceiling.last_updated -= timedelta(days=40)

    detail = _format_market_detail(market, unsupported_price_outcome_ids=withheld)
    set_detail = _format_market_detail(
        market, unsupported_price_outcome_ids=withheld, normalize_numbers=False
    )
    _apply_verified_title_to_detail(
        set_detail, Refusal("no_corroborating_venue"), market
    )
    set_rows, *_ = _canonical_market_outcome_map(set_detail["outcomes"])
    card_outcomes = [outcome for outcome in market.outcomes if outcome.id not in withheld]
    card_divisor = _feed_display_scale(
        card_outcomes, market=market, mutually_exclusive=True,
        field_complete=not _field_has_withheld_legs(market, market.outcomes, withheld),
    )
    assert card_divisor == pytest.approx(divisor)
    for surface in (detail["outcomes"], set_rows):
        by_id = {row["id"]: row["probability"] for row in surface}
        for outcome in market.outcomes[:2]:
            assert by_id[outcome.id] == pytest.approx(outcome.current_probability / divisor)


@pytest.mark.parametrize(
    "prices",
    [[0.40, 0.39], [0.52, 0.51], [0.5, 0.4, 0.3], [0.5, 0.4, 0.004]],
)
def test_every_complete_one_winner_field_sums_to_one_and_prints_100(prices):
    rows = [
        {"id": i, "name": f"Candidate {i}", "probability": p}
        for i, p in enumerate(prices)
    ]
    normalize_display_probs(rows)
    assert [o["probability"] for o in rows] == pytest.approx(
        [p / sum(prices) for p in prices]
    )
    assert sum(o["probability"] for o in rows) == pytest.approx(1)
    assert sum(o["rendered_percent"] for o in rows) == 100


def test_preview_keeps_full_divisor_and_allocation_including_overflow():
    full = [
        SimpleNamespace(id=i, name=f"Candidate {i}", current_probability=p)
        for i, p in enumerate([0.35, 0.34, 0.33, 0.2, 0.15])
    ]
    page = [
        {"id": o.id, "name": o.name, "probability": o.current_probability} for o in full
    ]
    normalize_display_probs(page)
    preview = [
        {"id": o.id, "name": o.name, "probability": o.current_probability}
        for o in full[:3]
    ]
    _normalize_feed_probabilities(preview, full, mutually_exclusive=True)
    _apply_card_percents(preview)
    assert preview == page[:3]
    assert sum(o["rendered_percent"] for o in preview) < 100
    assert sum(o["rendered_percent"] for o in page) == 100


@pytest.mark.parametrize(
    "kwargs",
    [
        {"mutually_exclusive": False},
        {"mutually_exclusive": None},
        {"field_complete": False},
        {"mutually_exclusive": None, "field_complete": False},
    ],
)
def test_nonexclusive_or_withheld_field_stays_raw(kwargs):
    rows = [{"name": n, "probability": p} for n, p in [("Alice", 0.8), ("Bob", 0.7)]]
    before = deepcopy(rows)
    assert normalize_display_probs(rows, **kwargs) is False
    assert rows == before


@pytest.mark.parametrize("prices", [[None, 0.7], [float("nan"), 0.7], [0.0, 0.0]])
def test_unknown_or_empty_mass_never_becomes_a_distribution(prices):
    rows = [{"name": f"Candidate {i}", "probability": p} for i, p in enumerate(prices)]
    assert normalize_display_probs(rows) is False
    assert all("rendered_percent" not in row for row in rows)


def test_cumulative_ladder_is_raw_even_with_a_bad_exclusivity_flag():
    rows = [
        {"name": n, "probability": p} for n, p in [("Above 50", 0.8), ("Above 60", 0.6)]
    ]
    before = deepcopy(rows)
    assert normalize_display_probs(rows, mutually_exclusive=True) is False
    assert rows == before


def test_whole_allocation_does_not_depend_on_card_order():
    rows = [{"id": i, "name": f"Candidate {i}", "probability": 0.4} for i in range(3)]
    backwards = list(reversed(deepcopy(rows)))
    normalize_display_probs(rows)
    normalize_display_probs(backwards)
    assert {o["id"]: o["rendered_percent"] for o in rows} == {
        o["id"]: o["rendered_percent"] for o in backwards
    }
    assert sum(o["rendered_percent"] for o in rows) == 100


@pytest.mark.parametrize("bounded", [False, True])
def test_search_preview_keeps_the_detail_full_field_divisor(bounded):
    from app.routes.events import _build_search_top_outcomes
    from app.routes.futures import _format_market_detail
    from tests.test_midterms_complete_outcome_prices_11948 import _detail_field

    market = _detail_field()
    if not bounded:
        for o, price in zip(market.outcomes, [0.45, 0.4, 0.3] + [0.005] * 21):
            o.current_probability = price
    page = _format_market_detail(market)
    preview = _build_search_top_outcomes(market, limit=5)
    full = {o["name"]: o for o in page["outcomes"]}
    assert len(preview) == 5
    for row in preview:
        assert row["probability"] == full[row["name"]]["probability"]
        assert row["rendered_percent"] == full[row["name"]]["rendered_percent"]


@pytest.mark.parametrize(
    "result",
    [
        {"is_winner": True, "resolution_source": "api_settlement"},
        {"is_winner": True, "resolution_source": "datagolf_settlement"},
    ],
)
def test_a_declared_winner_is_not_scaled_back_into_an_uncertain_price(result):
    rows = [
        {"name": "Winner", "probability": 1.0, **result},
        {"name": "Loser", "probability": 0.003},
    ]
    before = deepcopy(rows)
    assert normalize_display_probs(rows) is False
    assert rows == before


def test_a_refused_history_tick_does_not_turn_unknown_mass_into_zero():
    from datetime import datetime, timedelta, timezone
    from app.utils.futures_history_basis import devigged_consensus_by_time

    start = datetime(2026, 11, 4, tzinfo=timezone.utc)
    full = {1: 0.4, 2: 0.3, 3: 0.2}
    partial = {2: 0.3, 3: 0.2}
    result = devigged_consensus_by_time(
        {
            start: {"polymarket": full},
            start + timedelta(minutes=1): {"polymarket": partial},
        },
        mutually_exclusive=True,
        incomplete_times={start + timedelta(minutes=1)},
    )
    assert sum(result[start].values()) == pytest.approx(1)
    assert result[start + timedelta(minutes=1)] == partial


@pytest.mark.parametrize("source", ["polymarket", "draftkings"])
def test_absent_history_members_stay_raw_before_and_after_the_book_blend(source):
    from datetime import datetime, timedelta, timezone
    from app.utils.futures_history_basis import devigged_consensus_by_time

    start = datetime(2026, 11, 4, tzinfo=timezone.utc)
    full = {1: 0.4, 2: 0.3, 3: 0.2}
    partial = {2: 0.3, 3: 0.2}
    incomplete = set()
    result = devigged_consensus_by_time(
        {start: {source: full}, start + timedelta(minutes=1): {source: partial}},
        incomplete_times=incomplete,
    )
    assert sum(result[start].values()) == pytest.approx(1)
    assert result[start + timedelta(minutes=1)] == partial
    assert incomplete == {start + timedelta(minutes=1)}


def test_a_history_member_that_never_wrote_is_still_required_by_the_full_field():
    from datetime import datetime, timezone
    from app.utils.futures_history_basis import devigged_consensus_by_time

    instant = datetime(2026, 11, 4, tzinfo=timezone.utc)
    partial = {1: 0.1, 2: 0.1}
    incomplete = set()
    result = devigged_consensus_by_time(
        {instant: {"kalshi": partial}},
        outcome_names={1: "Alice", 2: "Bob", 3: "Casey"},
        incomplete_times=incomplete,
    )
    assert result[instant] == partial
    assert incomplete == {instant}


def test_event_row_alias_preserves_ladder_semantics_and_rounding_identity():
    ladder = [
        {"outcome_name": "Above 50", "probability": 0.8},
        {"outcome_name": "Above 60", "probability": 0.6},
    ]
    before = deepcopy(ladder)
    assert normalize_display_probs(ladder) is False
    assert ladder == before
    rows = [{"outcome_name": name, "probability": 0.4} for name in ("Zoe", "Alice", "Bob")]
    page = [{"name": row["outcome_name"], "probability": row["probability"]} for row in reversed(rows)]
    normalize_display_probs(rows)
    normalize_display_probs(page)
    assert {r["outcome_name"]: r["rendered_percent"] for r in rows} == {
        r["name"]: r["rendered_percent"] for r in page
    }


def test_distribution_rows_copy_the_same_full_field_allocation_after_classification():
    from app.routes.feed import _annotate_distribution_allocations

    prices = [0.255, 0.255, 0.25, 0.24]
    outcomes = [SimpleNamespace(id=i, name=name, external_id=None, current_probability=p)
                for i, (name, p) in enumerate(zip(["Alice", "Bob", "Casey", "Dani"], prices))]
    card = {"suggested_format": "outcome_distribution", "field_is_a_race": True,
            "distribution_outcomes": [{"label": o.name, "probability": o.current_probability} for o in outcomes]}
    before = deepcopy(card)
    _annotate_distribution_allocations(card, outcomes, "Winner", mutually_exclusive=True, field_complete=True)
    assert [r["rendered_percent"] for r in card["distribution_outcomes"]] == [26, 25, 25, 24]
    assert sum(r["rendered_percent"] for r in card["distribution_outcomes"]) == 100
    assert card["suggested_format"] == before["suggested_format"]
    for row, original in zip(card["distribution_outcomes"], before["distribution_outcomes"]):
        assert {k: v for k, v in row.items() if k != "rendered_percent"} == original


def test_feed_divisor_and_allocation_keep_an_authoritative_winner_as_a_result():
    from app.routes.feed import _feed_display_scale

    outcomes = [
        SimpleNamespace(id=1, name="Winner", current_probability=1.0, is_winner=True, resolution_source="api_settlement"),
        SimpleNamespace(id=2, name="Loser", current_probability=0.003, is_winner=False, resolution_source="api_settlement"),
    ]
    assert _feed_display_scale(outcomes, mutually_exclusive=True) == 1
    rows = [{"id": o.id, "name": o.name, "probability": o.current_probability} for o in outcomes]
    assert _normalize_feed_probabilities(rows, outcomes, mutually_exclusive=True) == rows
    assert rows[0]["probability"] == 1.0
    assert all("rendered_percent" not in r for r in rows)


def test_feed_allocation_matches_humanized_rows_by_id():
    outcomes = [SimpleNamespace(id=1, name="Yes", current_probability=0.505),
                SimpleNamespace(id=2, name="No", current_probability=0.495)]
    top = [{"id": 1, "name": "Will it happen?", "probability": 0.505},
           {"id": 2, "name": "It will not happen", "probability": 0.495}]
    _normalize_feed_probabilities(top, outcomes, mutually_exclusive=True)
    assert [o["rendered_percent"] for o in top] == [50, 50]


def _comparison_field():
    from datetime import datetime, timedelta, timezone
    from app.utils.futures_market_snapshot import (
        DATED_BASIS_METADATA_KEY,
        DATED_BASIS_ELIGIBILITY_METADATA_KEY,
        DATED_BASIS_PRICED_LEG,
    )
    from tests.test_midterms_complete_outcome_prices_11948 import _detail_field

    now = datetime(2026, 11, 4, 20, tzinfo=timezone.utc)
    market = _detail_field()
    market.source = "datagolf"
    market.outcomes = market.outcomes[:3]
    prior = [0.02, 0.68, 0.3]
    for row, current, opening in zip(
        market.outcomes, [0.1505, 0.55, 0.3], [0.3, 0.6, 0.3]
    ):
        row.current_probability = current
        row.opening_probability = opening
        row.opening_captured_at = now - timedelta(hours=30)
        row.probability_change_24h = 0.0005
        row.last_updated = now
    market.market_metadata = {
        DATED_BASIS_METADATA_KEY: {
            str(o.id): [p, (now - timedelta(hours=19)).isoformat()]
            for o, p in zip(market.outcomes, prior)
        },
        DATED_BASIS_ELIGIBILITY_METADATA_KEY: DATED_BASIS_PRICED_LEG,
    }
    rows = [
        {
            "id": o.id,
            "name": o.name,
            "probability": o.current_probability,
            "opening_probability": o.opening_probability,
            "probability_change_24h": o.probability_change_24h,
        }
        for o in market.outcomes
    ]
    return market, rows, now


def test_tiny_overround_keeps_normalized_movement_and_opening_at_their_own_instants():
    from app.utils.futures_market_snapshot import normalized_field_comparisons

    market, rows, now = _comparison_field()
    before = deepcopy(rows)
    metadata_before = deepcopy(market.market_metadata)
    result = normalized_field_comparisons(market, rows, now=now)
    leader = result[rows[0]["id"]]
    assert leader["probability"] == pytest.approx(0.1505 / 1.0005)
    assert leader["probability_change_24h"] == pytest.approx(
        0.1505 / 1.0005 - 0.02, abs=1e-8
    )
    assert leader["opening_probability"] == pytest.approx(0.3 / 1.2)
    assert rows == before and market.market_metadata == metadata_before


@pytest.mark.parametrize(
    "kind", ["missing peer", "different instant", "invalid peer", "current incomplete"]
)
def test_normalized_comparison_refuses_an_incomplete_endpoint(kind):
    from datetime import timedelta
    from app.utils.futures_market_snapshot import (
        DATED_BASIS_METADATA_KEY,
        normalized_field_comparisons,
    )

    market, rows, now = _comparison_field()
    bank = market.market_metadata[DATED_BASIS_METADATA_KEY]
    peer = str(rows[1]["id"])
    if kind == "missing peer":
        bank.pop(peer)
    if kind == "different instant":
        bank[peer][1] = (now - timedelta(hours=18)).isoformat()
    if kind == "invalid peer":
        bank[peer][0] = None
    result = normalized_field_comparisons(
        market, rows, now=now, field_complete=kind != "current incomplete"
    )
    if kind == "current incomplete":
        assert (
            result is None
        )  # no normalized current distribution; preserve the raw journey
        return
    assert all(row["probability_change_24h"] is None for row in result.values())


@pytest.mark.parametrize("missing", [False, True])
def test_opening_field_requires_every_member_at_the_same_recorded_instant(missing):
    from datetime import timedelta
    from app.utils.futures_market_snapshot import (
        normalized_field_comparisons,
        to_plain,
        from_plain,
    )

    market, rows, now = _comparison_field()
    market.outcomes[1].opening_captured_at = (
        None if missing else now - timedelta(hours=29)
    )
    for carrier in [market, from_plain(to_plain([market]))[0]]:
        result = normalized_field_comparisons(carrier, rows, now=now)
        assert all(row["opening_probability"] is None for row in result.values())
        assert result[rows[0]["id"]]["probability_change_24h"] is not None


def test_complete_opening_and_dated_fields_survive_the_shared_snapshot():
    from app.utils.futures_market_snapshot import (
        normalized_field_comparisons,
        to_plain,
        from_plain,
    )

    market, rows, now = _comparison_field()
    snapshot = from_plain(to_plain([market]))[0]
    assert normalized_field_comparisons(
        snapshot, rows, now=now
    ) == normalized_field_comparisons(market, rows, now=now)
    assert snapshot.market_metadata == market.market_metadata


@pytest.mark.parametrize("zero_opening", [False, True])
def test_detail_keeps_the_actual_normalized_move_and_opening(monkeypatch, zero_opening):
    from datetime import datetime
    from app.routes import futures

    market, rows, now = _comparison_field()
    if zero_opening:
        for row, opening in zip(market.outcomes, [0.0, 0.6, 0.4]):
            row.opening_probability = opening

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now if tz is None else now.astimezone(tz)

    monkeypatch.setattr(futures, "datetime", Clock)
    detail = futures._format_market_detail(market)
    leader = next(row for row in detail["outcomes"] if row["id"] == rows[0]["id"])
    assert leader["probability"] == pytest.approx(0.1505 / 1.0005)
    assert leader["probability_change_24h"] == pytest.approx(
        0.1505 / 1.0005 - 0.02, abs=1e-8
    )
    assert leader["opening_probability"] == pytest.approx(0.0 if zero_opening else 0.25)
    assert detail["openings_withheld"] is False


@pytest.mark.parametrize("composition", [False, True])
def test_verified_title_keeps_complete_same_estimator_references(
    monkeypatch, composition
):
    from datetime import datetime
    from app.routes import futures
    from app.utils.futures_verified_title import Composition, OutcomeOverlay, Refusal

    market, rows, now = _comparison_field()

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now if tz is None else now.astimezone(tz)

    monkeypatch.setattr(futures, "datetime", Clock)
    monkeypatch.setattr("app.utils.futures_market_snapshot.datetime", Clock)
    detail = futures._format_market_detail(market, normalize_numbers=False)
    verdict = Refusal("no_corroborating_venue")
    if composition:
        verdict = Composition(
            {},
            {
                o.id: OutcomeOverlay(
                    float(o.current_probability),
                    [market.source],
                    None,
                    "single_source",
                    False,
                )
                for o in market.outcomes
            },
            [market.source],
        )
    futures._apply_verified_title_to_detail(detail, verdict, market)
    leader = next(row for row in detail["outcomes"] if row["id"] == rows[0]["id"])
    assert leader["probability"] == pytest.approx(0.1505 / 1.0005, abs=1e-8)
    assert leader["opening_probability"] == pytest.approx(0.25)
    assert leader["probability_change_24h"] == pytest.approx(
        0.1505 / 1.0005 - 0.02, abs=1e-8
    )
    assert detail["openings_withheld"] is False


def test_unknown_exclusivity_keeps_only_the_feeds_existing_population_band():
    from app.routes.events import _build_search_top_outcomes
    from app.routes.futures import _format_market_detail
    from app.routes.league_futures import _serialize_outcomes
    from tests.test_midterms_complete_outcome_prices_11948 import _detail_field

    market = _detail_field()
    market.mutually_exclusive = None
    market.outcomes = market.outcomes[:3]
    for outcome, p in zip(market.outcomes, [0.5, 0.4, 0.3]):
        outcome.current_probability = p
    detail = _format_market_detail(market)
    preview = _build_search_top_outcomes(market, limit=3)
    league = _serialize_outcomes(market.outcomes, market)
    for row in detail["outcomes"] + preview + league:
        raw = next(
            o.current_probability for o in market.outcomes if o.name == row["name"]
        )
        assert row["probability"] == raw
        assert "rendered_percent" not in row
    feed = [
        {"id": o.id, "name": o.name, "probability": o.current_probability}
        for o in market.outcomes
    ]
    _normalize_feed_probabilities(feed, market.outcomes, mutually_exclusive=None)
    assert [o["probability"] for o in feed] == pytest.approx(
        [0.5 / 1.2, 0.4 / 1.2, 0.3 / 1.2], abs=5e-5
    )
