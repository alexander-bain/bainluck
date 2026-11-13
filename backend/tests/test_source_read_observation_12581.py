"""Headline ages follow received prices through replays, never write clocks."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.utils.aggregation import (
    PRICE_READ_KEY,
    PricedOutcomeRead,
    priced_outcome_read_time,
    source_price_read_time,
    stamp_source_reading,
)
from app.utils.source_mark import headline_source_marks


READ = datetime.now(timezone.utc) - timedelta(hours=3)
BASIS = {"42": READ.timestamp(), "43": (READ - timedelta(minutes=2)).timestamp()}


def received(sources=None, *, value=0.61, basis=BASIS):
    return stamp_source_reading(
        sources, "kalshi", value, now=READ + timedelta(seconds=8),
        observed_basis=basis, price_read_at=READ - timedelta(minutes=2),
    )


def age(sources, value=0.61):
    return source_price_read_time(
        sources, "kalshi", value, now=READ + timedelta(days=1),
    )


def test_matcher_recompute_keeps_original_read_despite_later_publication():
    first = received()
    recomputed = stamp_source_reading(
        first, "kalshi", 0.61, now=READ + timedelta(hours=2), observed_basis=BASIS,
    )
    assert age(first) == age(recomputed) == READ - timedelta(minutes=2)
    assert recomputed["kalshi"]["updated_at"] != first["kalshi"]["updated_at"]
    assert recomputed["kalshi"][PRICE_READ_KEY] == first["kalshi"][PRICE_READ_KEY]


@pytest.mark.parametrize("change", ["price", "same_price_new_clock", "different_leg", "unknown_basis"])
def test_recompute_cannot_borrow_a_read_from_a_different_input(change):
    value, basis = 0.61, dict(BASIS)
    if change == "price":
        value = 0.62
    elif change == "same_price_new_clock":
        basis["42"] += 30
    elif change == "different_leg":
        basis["44"] = basis.pop("43")
    else:
        basis = None
    later = stamp_source_reading(
        received(), "kalshi", value, now=READ + timedelta(hours=1), observed_basis=basis,
    )
    assert age(later, value) is None
    assert PRICE_READ_KEY not in later["kalshi"]


def test_later_actual_same_price_read_can_advance_age():
    later = stamp_source_reading(
        received(), "kalshi", 0.61, now=READ + timedelta(minutes=10),
        observed_basis={"42": READ.timestamp(), "43": READ.timestamp()}, price_read_at=READ,
    )
    assert age(later) == READ


def test_publication_and_outcome_touch_alone_never_supply_age():
    sources = stamp_source_reading({}, "kalshi", 0.61, now=READ, observed_basis=BASIS)
    assert age(sources) is None


def test_another_venue_cannot_refresh_this_sources_age():
    original = received()
    later = stamp_source_reading(
        original, "polymarket", 0.64, now=READ + timedelta(hours=1), price_read_at=READ,
    )
    assert later["kalshi"] == original["kalshi"]
    assert age(later) == READ - timedelta(minutes=2)


def test_full_nonvenue_input_is_bound_but_an_unobserved_rewrite_clears_it():
    original = stamp_source_reading({}, "betting", 0.61, now=READ, price_read_at=READ)
    assert source_price_read_time(original, "betting", 0.61, now=READ) == READ
    replayed = stamp_source_reading(original, "betting", 0.61, now=READ + timedelta(hours=1))
    assert source_price_read_time(replayed, "betting", 0.61, now=READ) is None


@pytest.mark.parametrize("damage", ["value", "bound", "basis", "observed_value", "clock", "naive_clock", "bool", "nan"])
def test_malformed_or_detached_evidence_is_unknown(damage):
    sources = received()
    entry = sources["kalshi"]
    if damage == "value":
        entry["value"] = 0.6
    elif damage == "bound":
        entry[PRICE_READ_KEY]["value"] = 0.6
    elif damage == "basis":
        entry["observed_basis"]["42"] += 1
    elif damage == "observed_value":
        entry["observed_value"] = 0.6
    elif damage == "clock":
        entry[PRICE_READ_KEY]["observed_at"] = "not-a-date"
    elif damage == "naive_clock":
        entry[PRICE_READ_KEY]["observed_at"] = READ.replace(tzinfo=None).isoformat()
    elif damage == "bool":
        entry[PRICE_READ_KEY]["basis"]["42"] = True
        entry["observed_basis"]["42"] = True
    else:
        entry[PRICE_READ_KEY]["value"] = float("nan")
    assert age(sources) is None


def test_future_read_does_not_turn_into_page_time():
    sources = received()
    assert source_price_read_time(sources, "kalshi", 0.61, now=READ - timedelta(hours=1)) is None


def test_cached_headline_keeps_exact_price_clock_on_both_axes():
    sources = received()
    fixture = SimpleNamespace(win_probability_sources=sources)
    hero = SimpleNamespace(source="blend")
    home, away = headline_source_marks(fixture, hero, [("kalshi", 0.61)])
    cached = deepcopy(home)
    fixture.win_probability_sources = stamp_source_reading(
        sources, "kalshi", 0.7, now=READ + timedelta(hours=2),
        observed_basis=BASIS, price_read_at=READ + timedelta(hours=1),
    )
    assert home == cached
    assert home["state"] == away["state"] == "single"
    assert home["sources"][0]["observed_at"] == away["sources"][0]["observed_at"]
    assert home["sources"][0]["observed_at"] == (
        READ - timedelta(minutes=2)
    ).isoformat().replace("+00:00", "Z")
    assert home["sources"][0]["probability"] == 0.61
    assert away["sources"][0]["probability"] == 0.39


def test_headline_trace_cannot_borrow_a_sources_clock_for_other_price():
    home, _ = headline_source_marks(
        SimpleNamespace(win_probability_sources=received()),
        SimpleNamespace(source="blend"), [("kalshi", 0.62)],
    )
    assert home["sources"][0]["observed_at"] is None


@pytest.mark.parametrize("valid_age", [True, False])
def test_reversed_club_fold_preserves_number_and_only_its_bound_age(valid_age):
    from app.utils.event_twin_fold import _flipped_reading

    original = received()["kalshi"]
    if not valid_age:
        original[PRICE_READ_KEY]["value"] = 0.7
    ok, flipped = _flipped_reading("kalshi", original)
    assert ok
    assert flipped["value"] == flipped["observed_value"] == 0.39
    at = source_price_read_time({"kalshi": flipped}, "kalshi", 0.39, now=READ)
    assert at == (READ - timedelta(minutes=2) if valid_age else None)
    assert original["value"] == 0.61


def priced_row(oid, price=0.61):
    return SimpleNamespace(
        id=oid, market_id=7, external_id=f"contract-{oid}",
        current_probability=price, last_updated=READ,
    )


def witness(row, at):
    return PricedOutcomeRead(
        market_id=row.market_id, external_id=row.external_id,
        probability=row.current_probability, row_time=row.last_updated, received_at=at,
    )


def test_combined_price_uses_oldest_real_contributing_read_not_pass_clock():
    left, right = priced_row(42), priced_row(43, 0.6)
    reads = {42: witness(left, READ), 43: witness(right, READ + timedelta(minutes=2))}
    assert priced_outcome_read_time([left, right], reads) == READ
    # The second use of a cached event response carries the original witness.
    assert priced_outcome_read_time([right], reads) == READ + timedelta(minutes=2)


@pytest.mark.parametrize("change", ["unfetched", "price", "touch", "market", "contract"])
def test_a_database_reload_cannot_date_an_unread_or_changed_contributor(change):
    left, right = priced_row(42), priced_row(43)
    reads = {42: witness(left, READ), 43: witness(right, READ)}
    if change == "unfetched":
        reads.pop(43)
    elif change == "price":
        right.current_probability = 0.62
    elif change == "touch":
        right.last_updated += timedelta(seconds=1)
    elif change == "market":
        right.market_id = 8
    else:
        right.external_id = "other-contract"
    assert priced_outcome_read_time([left, right], reads) is None


@pytest.fixture
def actual_detail(monkeypatch):
    from tests.test_blend_fold_chart_pin_parity_3911 import both_routes

    routes = both_routes.__wrapped__(monkeypatch)
    routes.cache.clear()
    yield routes
    routes.cache.clear()


def detail_session(routes, *, now, price=0.61, read_at):
    sources = stamp_source_reading(
        {}, "polymarket", price, now=now,
        observed_basis={"42": read_at.timestamp()}, price_read_at=read_at,
    )
    twin_sources = stamp_source_reading(
        {}, "kalshi", price - 0.02, now=now,
        observed_basis={"43": read_at.timestamp()}, price_read_at=read_at,
    )
    session = routes.session(now, sources=sources, twin_sources=twin_sources)
    session.event.status = "live"
    session.event.commence_time = now - timedelta(hours=1)
    return session


def test_real_detail_serves_the_bound_clock_and_actual_method(actual_detail):
    now = datetime.now(timezone.utc)
    read_at = now - timedelta(minutes=4)
    body = actual_detail.detail(detail_session(actual_detail, now=now, read_at=read_at))
    assert body["hero_probability"] == pytest.approx(0.60)
    for field in ("source_mark", "away_source_mark"):
        mark = body[field]
        assert [row["key"] for row in mark["sources"]] == ["kalshi", "polymarket"]
        assert {row["observed_at"] for row in mark["sources"]} == {
            read_at.isoformat().replace("+00:00", "Z")
        }
        assert mark["method"] == "Bain Luck blend · a weighted average of these sources"


def test_real_detail_cache_keeps_the_price_and_its_own_read_together(actual_detail):
    now = datetime.now(timezone.utc)
    old = now - timedelta(minutes=4)
    first = actual_detail.detail(detail_session(actual_detail, now=now, read_at=old))
    changed = detail_session(
        actual_detail, now=now, price=0.71, read_at=now - timedelta(seconds=1),
    )
    cached = actual_detail.detail(changed)
    assert cached["hero_probability"] == first["hero_probability"] == pytest.approx(0.60)
    assert cached["source_mark"] == first["source_mark"]
    assert cached["away_source_mark"] == first["away_source_mark"]
    actual_detail.cache.clear()
    refreshed = actual_detail.detail(changed)
    assert refreshed["hero_probability"] == pytest.approx(0.70)
    assert {s["observed_at"] for s in refreshed["source_mark"]["sources"]} == {
        (now - timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
    }
