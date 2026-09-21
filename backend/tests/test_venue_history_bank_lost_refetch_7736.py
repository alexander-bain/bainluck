"""#7736 — an EVICTED venue history bank is re-fetched; one that never existed is not.

PILLAR: TRUTH. SHIP: a generic market chart that once showed its venue history
shows it again after Redis evicts the bank, instead of dropping to our own poll
samples for good.

THE DEFECT THIS PINS. `plan_on_demand_fill` read `payload_age_seconds(...) is
None` as one state. It is two: "this market never had venue history" (refusing is
#7351's own scope boundary) and "it had some and `allkeys-lru` evicted it"
(refusing abandons it permanently — the serve path never calls a provider, and
Postgres holds only our own poll snapshots, so nothing else ever asks again).
The evidence that the second state happened is evicted along with the bank, which
is why the marker that separates them has to be durable.

THE CONTROL THAT MATTERS is `test_a_market_that_never_held_a_bank_is_still_refused`:
without it this suite would pass just as well against a change that simply deleted
the `chart_not_thin` fence, which would turn every densely-polled market on the
site into outbound venue traffic.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.tasks import generic_market_history_fill as fill
from app.utils import generic_market_history as gmh

NOW = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)


def _market(*, marker=None, status="open", market_id=1, metadata=None):
    """A planner-shaped market. `metadata` wins over `marker` so the shape-tolerance
    arms can pass things that are not dicts at all."""
    if metadata is None:
        metadata = {} if marker is None else {gmh.BANK_MARKER_KEY: marker}
    return SimpleNamespace(
        id=market_id, source="kalshi", external_id="KXQ-26",
        status=status, market_metadata=metadata,
    )


def _outcome(oid=10, external_id="KXQ-26-YES"):
    return SimpleNamespace(id=oid, external_id=external_id, name="Yes")


def _real_marker(points=46):
    return {"first_built_at": (NOW - timedelta(days=2)).isoformat(),
            "points": points, "outcomes": 1}


class _Redis:
    """Enough Redis for the claim + hourly budget, and nothing else."""

    def __init__(self):
        self.kv: dict = {}
        self.ttl: dict = {}

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.kv:
            return None
        self.kv[key], self.ttl[key] = value, ex
        return True

    def get(self, key):
        return self.kv.get(key)

    def incr(self, key):
        self.kv[key] = int(self.kv.get(key, 0)) + 1
        return self.kv[key]

    def expire(self, key, seconds):
        self.ttl[key] = seconds

    def delete(self, key):
        self.kv.pop(key, None)


def _plan(*, market, thin, payload=None, rc=None):
    return fill.plan_on_demand_fill(
        market, [_outcome()], payload,
        chart_is_thin=thin, now=NOW, rc=rc or _Redis(),
    )


# ── the ship ────────────────────────────────────────────────────────────────


def test_an_evicted_bank_on_a_densely_polled_chart_is_refetched():
    """THE SHIP. Cold key + dense own-poll chart + a durable marker ⇒ re-fetch."""
    plan = _plan(market=_market(marker=_real_marker()), thin=False, payload=None)
    assert plan["enqueue"] is True, (
        "a market KNOWN to have held a venue bank must re-fetch after eviction — "
        "nothing else in the system will ever ask for it again"
    )


def test_a_market_that_never_held_a_bank_is_still_refused():
    """THE CONTROL. #7351's scope boundary is unchanged for markets with no marker.

    Without this arm, deleting the `chart_not_thin` fence outright would pass
    every other arm here while converting page views into venue traffic.
    """
    plan = _plan(market=_market(marker=None), thin=False, payload=None)
    assert plan == {"enqueue": False, "reason": "chart_not_thin"}


def test_a_thin_chart_is_unchanged_with_or_without_a_marker():
    """The path #7351 shipped is untouched in both directions."""
    for marker in (None, _real_marker()):
        assert _plan(market=_market(marker=marker), thin=True, payload=None)["enqueue"] is True


def test_the_marker_does_not_defeat_the_negative_cache():
    """A marker re-opens a COLD key. It must not re-open a WARM recent answer.

    Otherwise the repair for "we abandoned the history" becomes "we re-ask the
    venue on every page view", which is the same bug aimed at the venue.
    """
    fresh = {"attempted_at": (NOW - timedelta(minutes=5)).isoformat(),
             "built_at": (NOW - timedelta(minutes=5)).isoformat(), "outcomes": {}}
    plan = _plan(market=_market(marker=_real_marker()), thin=False, payload=fresh)
    assert plan == {"enqueue": False, "reason": "answered_recently"}


def test_the_marker_does_not_override_an_unfillable_source():
    """A marker cannot conjure venue history for a source that publishes none."""
    market = _market(marker=_real_marker())
    market.source = "odds_api"
    plan = fill.plan_on_demand_fill(
        market, [_outcome()], None, chart_is_thin=False, now=NOW, rc=_Redis()
    )
    assert plan == {"enqueue": False, "reason": "source_has_no_venue_history"}


def test_a_refetch_still_spends_one_claim_and_the_hourly_budget():
    """The new path goes through the SAME fences, not around them."""
    rc = _Redis()
    market = _market(marker=_real_marker())
    assert _plan(market=market, thin=False, rc=rc)["enqueue"] is True
    assert rc.ttl[gmh.claim_key(1)] == fill.CLAIM_TTL_SECONDS
    assert _plan(market=market, thin=False, rc=rc)["reason"] == "already_claimed"


# ── what earns a marker ─────────────────────────────────────────────────────


def test_only_a_payload_with_points_earns_a_marker():
    market = SimpleNamespace(id=1, source="kalshi", external_id="KXQ-26")
    with_points = {
        "built_at": NOW.isoformat(),
        "outcomes": {"10": {"outcome_id": 10, "points": [["t", 0.4], ["t2", 0.5]]}},
    }
    marker = gmh.build_bank_marker(with_points, now=NOW)
    assert marker == {"first_built_at": NOW.isoformat(), "points": 2, "outcomes": 1}
    assert gmh.market_had_bank(_market(marker=marker)) is True
    assert market is not None  # the helper reads the payload, never the row


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        {"built_at": NOW.isoformat(), "outcomes": {}},                      # empty answer
        {"built_at": NOW.isoformat(), "outcomes": {"10": {"points": []}}},  # present, no points
        {"built_at": NOW.isoformat(), "outcomes": "not-a-dict"},
    ],
)
def test_an_empty_or_degraded_answer_earns_no_marker(payload):
    """A venue with nothing to say must not be stamped as having a bank.

    If it were, every cold key on that market would re-ask for ever — the
    negative cache spent backwards.
    """
    assert gmh.build_bank_marker(payload, now=NOW) is None


@pytest.mark.parametrize(
    "metadata",
    [None, {}, "not-a-dict", 7, {"venue_history_bank": None}, {"venue_history_bank": "yes"}],
)
def test_marker_reading_tolerates_every_shape_a_row_can_carry(metadata):
    """The planner runs on a SimpleNamespace built in the route, and the column is
    nullable — so a bad shape must read as "no marker", never raise."""
    assert gmh.market_had_bank(_market(metadata=metadata)) is False


def test_a_market_object_with_no_metadata_attribute_at_all_reads_as_no_marker():
    assert gmh.market_had_bank(SimpleNamespace(id=1)) is False


# ── the durable write ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_stamp_is_a_core_jsonb_merge_and_not_an_orm_assignment():
    """Gotcha #4: JSONB goes through a Core UPDATE with `||`, never attribute
    assignment — and the merge must PRESERVE the column's other keys."""
    captured = []

    session = SimpleNamespace(execute=lambda stmt: _record(captured, stmt))
    await fill._stamp_bank_marker(session, 42, _real_marker())

    assert len(captured) == 1, "exactly one statement"
    sql = str(captured[0]).lower()
    assert "update futures_markets" in sql
    assert "||" in sql, "a whole-column write would clobber a sibling's keys"
    assert "coalesce" in sql, "a NULL market_metadata must merge, not vanish"
    assert "jsonb" in sql


def _record(captured, stmt):
    captured.append(stmt)

    class _Awaitable:
        def __await__(self):
            return iter(())

    return _Awaitable()
