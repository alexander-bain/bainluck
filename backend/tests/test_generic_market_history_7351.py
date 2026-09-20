"""#7351 — the always-on half: identity, layering, the claim, and the fences.

PILLAR: TRUTH. SHIP: opening a generic Discover market shows its supported
historical observations on the phone and the web, including history missed by
our periodic polls.

The behavioural proof — both real routes, the real task, real Postgres and real
Redis — is `tests/integration/test_generic_market_history_7351_real_pg_redis.py`
and it only runs where its disposable services exist. This file needs nothing,
so it runs in every shard, and it holds the rules a refactor is most likely to
loosen without noticing:

  * a cached series is served ONLY to the market, outcome id and exact venue
    contract it was fetched for — never by name;
  * a capture is never displaced by a venue point;
  * the claim fails CLOSED and is bounded per market and per hour;
  * the generic fill never blends venues, never matches legs, never dispatches a
    task, and its route seam never reaches a provider.
"""

from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.tasks import generic_market_history_fill as fill
from app.utils import generic_market_history as gmh

NOW = datetime(2026, 9, 20, 3, 42, 32, tzinfo=timezone.utc)
APP = Path(__file__).resolve().parents[1] / "app"


def _market(source="kalshi", market_id=1, external_id="KXQ-26", status="open"):
    return SimpleNamespace(id=market_id, source=source, external_id=external_id, status=status)


def _outcome(oid=10, external_id="KXQ-26-YES", name="Yes"):
    return SimpleNamespace(id=oid, external_id=external_id, name=name)


def _payload(market, outcome, *, points=None, contract=None, **over):
    points = points if points is not None else [
        [(NOW - timedelta(hours=h)).isoformat(), 0.1 + h / 1000, 0.09, 0.11, None, "kalshi_candle_60m"]
        for h in (30, 20, 10)
    ]
    body = {
        "schema": gmh.SCHEMA, "version": gmh.CACHE_VERSION, "scale": gmh.SCALE,
        "market_id": market.id, "market_source": market.source,
        "market_external_id": market.external_id,
        "attempted_at": NOW.isoformat(), "built_at": NOW.isoformat(), "status": "ok",
        "outcomes": {str(outcome.id): {
            "outcome_id": outcome.id,
            "contract": contract or gmh.kalshi_contract(outcome),
            "points": points,
        }},
        # A payload whose series came from its OWN attempt — the ordinary case.
        # `stats.fetched_points` is counted before the last-good merge, so a
        # payload that merely CARRIES a series says 0 here while looking
        # identical above (CERT-3152); the arms that need that shape pass it.
        "stats": {"fetched_points": len(points)},
    }
    body.update(over)
    return body


# ── identity ────────────────────────────────────────────────────────────────


def test_a_valid_payload_is_served_to_its_own_market_outcome_and_contract():
    market, outcome = _market(), _outcome()
    accepted, refusals = gmh.validate_payload(_payload(market, outcome), market, [outcome])
    assert refusals == [] and list(accepted) == [outcome.id]
    assert [p.probability for p in accepted[outcome.id]] == pytest.approx([0.13, 0.12, 0.11])
    assert accepted[outcome.id][0].yes_bid == 0.09, "the book must travel with the point"


@pytest.mark.parametrize("field, value, reason", [
    ("market_id", 2, "market_id_mismatch"),
    ("market_source", "polymarket", "market_source_mismatch"),
    ("market_external_id", "KXOTHER-26", "market_external_id_mismatch"),
    ("scale", "devigged", "scale_mismatch"),
    ("version", "v0", "schema_or_version_mismatch"),
    ("schema", "event-concept", "schema_or_version_mismatch"),
    ("built_at", "yesterday", "built_at_unparseable"),
])
def test_a_payload_for_anything_else_is_refused_whole(field, value, reason):
    market, outcome = _market(), _outcome()
    accepted, refusals = gmh.validate_payload(
        _payload(market, outcome, **{field: value}), market, [outcome]
    )
    assert accepted == {} and refusals == [{"scope": "payload", "reason": reason}]


def test_two_markets_each_with_a_yes_never_share_a_series():
    """The whole reason this cache is not the concept cache."""
    mine, mine_yes = _market(market_id=1, external_id="KXA-26"), _outcome(10, "KXA-26-Y", "Yes")
    theirs, their_yes = _market(market_id=2, external_id="KXB-26"), _outcome(20, "KXB-26-Y", "Yes")
    their_payload = _payload(theirs, their_yes)

    # Same NAME, their outcome id under my envelope.
    forged = dict(their_payload, market_id=mine.id, market_external_id=mine.external_id)
    accepted, refusals = gmh.validate_payload(forged, mine, [mine_yes])
    assert accepted == {} and refusals[0]["reason"] == "not_a_charted_outcome_of_this_market"

    # My outcome id, their CONTRACT.
    entry = dict(their_payload["outcomes"]["20"], outcome_id=10)
    accepted, refusals = gmh.validate_payload(dict(forged, outcomes={"10": entry}), mine, [mine_yes])
    assert accepted == {} and refusals[0]["reason"] == "contract_outcome_external_id_mismatch"


def test_an_outcome_re_pointed_at_another_contract_orphans_its_old_series():
    market, outcome = _market(), _outcome()
    payload = _payload(market, outcome)
    outcome.external_id = "KXQ-26-NEWTICKER"
    accepted, refusals = gmh.validate_payload(payload, market, [outcome])
    assert accepted == {} and refusals[0]["reason"] == "contract_outcome_external_id_mismatch"


def test_polymarket_contract_binds_condition_and_token_and_the_leg():
    market = _market("polymarket", external_id="990001")
    cond = "0x" + "ab" * 32
    no_leg = _outcome(11, f"{cond}_no", "No")
    contract = gmh.polymarket_contract(no_leg, token_id="222", resolved_via="gamma_condition_by_name")
    assert contract["condition_id"] == cond and contract["outcome_external_id"] == f"{cond}_no"
    ok, refusals = gmh.validate_payload(_payload(market, no_leg, contract=contract), market, [no_leg])
    assert refusals == [] and list(ok) == [11]
    # The YES leg of the same condition may not inherit the NO leg's series.
    yes_leg = _outcome(11, f"{cond}_yes", "Yes")
    ok, refusals = gmh.validate_payload(_payload(market, no_leg, contract=contract), market, [yes_leg])
    assert ok == {} and refusals[0]["reason"] == "contract_outcome_external_id_mismatch"
    assert gmh.polymarket_contract(_outcome(12, "not-a-condition", "X"), token_id="1", resolved_via="x") is None
    assert gmh.wanted_gamma_outcome_name(no_leg) == "No"
    assert gmh.wanted_gamma_outcome_name(_outcome(13, cond, "Detroit Tigers")) == "Detroit Tigers"


@pytest.mark.parametrize("mutate, reason", [
    (lambda pts: pts.reverse(), "timestamps_not_strictly_ascending"),
    (lambda pts: pts.append(list(pts[-1])), "timestamps_not_strictly_ascending"),
    (lambda pts: pts[-1].__setitem__(0, (NOW + timedelta(hours=1)).isoformat()), "timestamp_after_build"),
    (lambda pts: pts[0].__setitem__(0, "2026-09-18T00:00:00"), "timestamp_unparseable_or_naive"),
    (lambda pts: pts[1].__setitem__(1, 1.01), "probability_out_of_range"),
    (lambda pts: pts[1].__setitem__(1, None), "probability_out_of_range"),
    (lambda pts: pts[1].__setitem__(1, True), "probability_out_of_range"),
    (lambda pts: pts.__setitem__(1, "junk"), "point_malformed"),
])
def test_one_impossible_point_refuses_the_whole_series(mutate, reason):
    market, outcome = _market(), _outcome()
    payload = _payload(market, outcome)
    mutate(payload["outcomes"][str(outcome.id)]["points"])
    accepted, refusals = gmh.validate_payload(payload, market, [outcome])
    assert accepted == {} and refusals[0]["reason"] == reason


def test_a_supported_zero_is_a_value_not_a_hole():
    market, outcome = _market(), _outcome()
    points = [[(NOW - timedelta(hours=2)).isoformat(), 0, None, None, None, "clob"],
              [(NOW - timedelta(hours=1)).isoformat(), 0.0, None, None, None, "clob"]]
    accepted, _ = gmh.validate_payload(_payload(market, outcome, points=points), market, [outcome])
    assert [p.probability for p in accepted[outcome.id]] == [0.0, 0.0]


# ── layering ────────────────────────────────────────────────────────────────


def test_a_capture_always_stands_and_venue_points_fill_only_unclaimed_instants():
    captures = [NOW - timedelta(hours=h) for h in (9, 6, 3)]
    near = captures[1] + timedelta(minutes=20)       # inside the capture's 30-minute claim
    far = captures[1] + timedelta(minutes=45)
    same = captures[2]
    after_build = NOW - timedelta(minutes=30)        # no capture near it
    kept = gmh.unclaimed_instants([near, far, same, after_build], captures)
    assert kept == {far, after_build}
    assert gmh.unclaimed_instants([], captures) == set()
    assert gmh.unclaimed_instants([far], []) == {far}


def test_last_good_points_survive_a_venue_that_answers_with_less():
    old = [gmh.VenuePoint(NOW - timedelta(hours=h), 0.2) for h in (30, 20, 10)]
    fresh = [gmh.VenuePoint(NOW - timedelta(hours=10), 0.25), gmh.VenuePoint(NOW - timedelta(hours=1), 0.3)]
    merged = gmh.merge_last_good(fresh, old)
    assert [(p.observed_at, p.probability) for p in merged] == [
        (NOW - timedelta(hours=30), 0.2), (NOW - timedelta(hours=20), 0.2),
        (NOW - timedelta(hours=10), 0.25), (NOW - timedelta(hours=1), 0.3),
    ]


# ── the claim ───────────────────────────────────────────────────────────────


class _Redis:
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


class _DeadRedis:
    def __getattr__(self, name):
        raise ConnectionError("redis is down")


def _plan(payload=None, *, thin=True, market=None, rc=None, now=NOW):
    market = market or _market()
    return fill.plan_on_demand_fill(market, [_outcome()], payload, chart_is_thin=thin, now=now, rc=rc)


def test_one_claim_per_market_with_its_own_expiry_and_an_hourly_budget():
    rc = _Redis()
    assert _plan(rc=rc) == {"enqueue": True, "reason": "claimed"}
    assert rc.ttl[gmh.claim_key(1)] == fill.CLAIM_TTL_SECONDS, "a claim with no expiry is permanent"
    assert _plan(rc=rc)["reason"] == "already_claimed"
    fill.release_claim(1, rc)
    assert _plan(rc=rc)["enqueue"] is True

    capped = _Redis()
    capped.kv[gmh.budget_key(NOW.strftime("%Y%m%d%H"))] = fill.HOURLY_FILL_CAP
    assert _plan(rc=capped) == {"enqueue": False, "reason": "hourly_cap"}
    assert gmh.claim_key(1) not in capped.kv, "a refused fill kept its claim"


def test_no_redis_means_no_claim_and_no_venue_means_no_question():
    assert _plan(rc=_DeadRedis()) == {"enqueue": False, "reason": "no_redis"}
    assert _plan(market=_market("odds_api"), rc=_Redis())["reason"] == "source_has_no_venue_history"
    assert _plan(thin=False, rc=_Redis())["reason"] == "chart_not_thin"


def test_an_answer_even_an_empty_one_is_not_asked_for_again_until_it_ages():
    market, outcome = _market(), _outcome()
    empty = dict(_payload(market, outcome), outcomes={}, status="empty")
    assert _plan(empty, rc=_Redis())["reason"] == "answered_recently"
    later = NOW + timedelta(seconds=fill.REFRESH_AFTER_SECONDS + 1)
    assert _plan(empty, rc=_Redis(), now=later)["enqueue"] is True
    assert _plan(empty, thin=False, rc=_Redis(), now=later)["reason"] == "chart_not_thin"


def test_only_a_successful_post_settlement_fill_ends_a_settled_markets_retries():
    """The settled short-circuit is about an ANSWER, never about a date.

    A settled payload is cached for SEVEN DAYS, so every attempt this test walks
    would have frozen the chart for a week under the first presentation: it
    short-circuited on any dated attempt whatever it contained. Each of these is
    a state a real fill reaches — the venue rate-limited us, one window errored,
    or the fill simply ran the day before the market settled and so cannot hold
    the hours that decided it.
    """
    market, outcome = _market(), _outcome()
    settled = _market(status="settled")
    later = NOW + timedelta(seconds=fill.REFRESH_AFTER_SECONDS + 1)

    def reason(payload):
        return _plan(payload, market=settled, rc=_Redis(), now=later)["reason"]

    answered = dict(_payload(market, outcome), market_settled=True)
    assert reason(answered) == "settled_and_already_answered"
    assert fill.answers_a_settled_market(answered) is True

    # Every other shape is an ATTEMPT, and an attempt recovers on the ordinary
    # bounded retry rather than standing as the week's answer.
    for label, payload in [
        ("empty", dict(_payload(market, outcome), outcomes={}, status="empty",
                       market_settled=True)),
        ("degraded", dict(_payload(market, outcome), status="degraded",
                          market_settled=True)),
        ("ok but carrying no series", dict(_payload(market, outcome), outcomes={},
                                           market_settled=True)),
        # 🔴 CERT-3152's finding, as a unit: a HEALTHY pre-settlement series
        # carried forward by last-good is a full payload, status `ok`, stamped
        # settled by the fill that ran — and the attempt behind it fetched
        # nothing, so it cannot hold the hours that decided the question.
        ("ok, but every point was carried out of the cache",
         dict(_payload(market, outcome, stats={"fetched_points": 0}),
              market_settled=True)),
        ("taken before the market settled", dict(_payload(market, outcome),
                                                 market_settled=False)),
        ("from a fill that never stamped the state", _payload(market, outcome)),
    ]:
        assert reason(payload) == "claimed", f"a {label} fill froze a settled chart"
        assert fill.answers_a_settled_market(payload) is False

    # The retry stays BOUNDED: inside the refresh age even a settled market's
    # failed attempt is left alone, so this is a ceiling and not a sweep.
    stale = dict(_payload(market, outcome), outcomes={}, status="empty", market_settled=True)
    assert _plan(stale, market=settled, rc=_Redis(), now=NOW)["reason"] == "answered_recently"


def test_a_venue_that_has_purged_a_settled_market_is_asked_a_bounded_number_of_times():
    """The repair for "one attempt froze the chart" must not be "ask forever".

    Kalshi purges a settled market's candles (gotcha #35), so a venue can be
    empty for good. Asking on every read past the refresh age would then spend a
    request every three hours, for every settled chart, for the whole seven-day
    TTL — the same defect paid to the venue instead of the reader. After
    `MAX_SETTLED_EMPTY_ATTEMPTS` post-settlement attempts that fetched nothing of
    their own, the carried series is accepted as all there is.
    """
    market, outcome = _market(), _outcome()
    settled = _market(status="settled")
    later = NOW + timedelta(seconds=fill.REFRESH_AFTER_SECONDS + 1)
    carried = dict(_payload(market, outcome, stats={"fetched_points": 0}),
                   market_settled=True)

    for spent in range(fill.MAX_SETTLED_EMPTY_ATTEMPTS):
        attempt = dict(carried, settled_empty_attempts=spent)
        assert fill.answers_a_settled_market(attempt) is False, (
            f"attempt {spent + 1} of {fill.MAX_SETTLED_EMPTY_ATTEMPTS} is inside "
            "the ceiling and the venue must still be asked"
        )
        assert _plan(attempt, market=settled, rc=_Redis(), now=later)["reason"] == "claimed"

    spent_out = dict(carried, settled_empty_attempts=fill.MAX_SETTLED_EMPTY_ATTEMPTS)
    assert fill.answers_a_settled_market(spent_out) is True
    assert _plan(spent_out, market=settled, rc=_Redis(), now=later)["reason"] == (
        "settled_and_already_answered"
    )

    # The counter counts ATTEMPTS MADE WHILE SETTLED that fetched nothing…
    empty = {"stats": {"fetched_points": 0}}
    assert fill.next_settled_empty_attempts(None, empty, settled=True) == 1
    assert fill.next_settled_empty_attempts(spent_out, empty, settled=True) == (
        fill.MAX_SETTLED_EMPTY_ATTEMPTS + 1
    )
    # …an OPEN market's empty fill is an ordinary retry and is not on this clock…
    assert fill.next_settled_empty_attempts(spent_out, empty, settled=False) == 0
    # …and one fetched point resets it, because a venue that answered once is
    # not the silent venue this ceiling exists for.
    answered_now = {"stats": {"fetched_points": 4}}
    assert fill.next_settled_empty_attempts(spent_out, answered_now, settled=True) == 0

    # A counter nobody can read is not a licence to stop asking.
    for junk in ("three", None, -2, {}):
        assert fill.settled_empty_attempts(dict(carried, settled_empty_attempts=junk)) == 0


def test_a_failed_attempt_never_spends_the_ceiling_that_is_about_silence():
    """"The venue gave me nothing" and "I could not ask" are different facts.

    The first cut of the ceiling spent both, so three 429s inside nine hours
    exhausted it and a `degraded` payload with no points — possibly a market
    whose history we had never once fetched — read as the week's answer. That is
    the freeze this ship removes, rebuilt out of the repair for it (CERT-3156).
    A failed attempt is always retryable on the ordinary bounded interval,
    however many have gone before.
    """
    market, outcome = _market(), _outcome()
    settled = _market(status="settled")
    later = NOW + timedelta(seconds=fill.REFRESH_AFTER_SECONDS + 1)
    spent = fill.MAX_SETTLED_EMPTY_ATTEMPTS

    # Every shape a failed attempt arrives in, at and beyond the ceiling.
    for label, over in [
        ("one window errored", {"stats": {"fetched_points": 0, "window_errors": 1}}),
        ("the venue call raised", {"stats": {"fetched_points": 0, "fetch_errors": 1}}),
        ("status says degraded", {"status": "degraded",
                                  "stats": {"fetched_points": 0}}),
        ("degraded with no history at all", {"status": "degraded", "outcomes": {},
                                             "stats": {"fetched_points": 0}}),
    ]:
        failed = dict(_payload(market, outcome), market_settled=True,
                      settled_empty_attempts=spent, **over)
        assert fill.answers_a_settled_market(failed) is False, (
            f"a settled chart froze for a week on: {label}"
        )
        assert _plan(failed, market=settled, rc=_Redis(), now=later)["reason"] == "claimed"
        # …and it does not advance the counter either, so a bad afternoon at the
        # venue cannot exhaust a ceiling that is about silence.
        assert fill.next_settled_empty_attempts(failed, failed, settled=True) == spent

    # The clean empty at the same count still satisfies it — otherwise this arm
    # would pass against a ceiling that never fires at all.
    clean = dict(_payload(market, outcome, stats={"fetched_points": 0}),
                 market_settled=True, settled_empty_attempts=spent)
    assert fill.answers_a_settled_market(clean) is True

    # Three failures do not move a count of zero…
    failed_clean_slate = {"stats": {"fetched_points": 0, "fetch_errors": 1}}
    count = 0
    for _ in range(3):
        count = fill.next_settled_empty_attempts(
            dict(failed_clean_slate, settled_empty_attempts=count),
            failed_clean_slate, settled=True,
        )
    assert count == 0, "three failed attempts spent the silence ceiling"
    # …and a healthy answer after them ends the retries, which is the other half
    # of the required repair.
    healthy = dict(_payload(market, outcome), market_settled=True,
                   settled_empty_attempts=count)
    assert fill.answers_a_settled_market(healthy) is True


class _SessionReturning:
    """The one query `fill_generic_market_history` makes, answered from memory."""

    def __init__(self, market):
        self.market = market

    async def execute(self, *_args, **_kwargs):
        market = self.market
        return SimpleNamespace(scalar_one_or_none=lambda: market)


def test_the_fill_stamps_the_settlement_state_its_answer_was_taken_under():
    """Without the stamp the planner above can only guess, so the write owes it."""
    import asyncio
    import json

    from app.utils.generic_market_history import build_payload, cache_key

    for status, expected in (("settled", True), ("open", False)):
        market = _market(status=status)
        market.outcomes = []
        rc = _Redis()
        result = asyncio.run(
            fill.fill_generic_market_history(
                _SessionReturning(market), market.id, rc=rc, now=NOW
            )
        )
        assert result["cached"] is True
        cached = json.loads(rc.kv[cache_key(market.id)])
        assert cached["market_settled"] is expected, (
            "the cached payload must record the state the fill ran under"
        )
        assert rc.ttl[cache_key(market.id)] == (
            fill.SETTLED_CACHE_TTL_SECONDS if expected else fill.CACHE_TTL_SECONDS
        ), "the settled payload is the one held for a week, so it owes the stamp"

    # The stamp is the FILL's to add, because only the fill knows. A payload that
    # never went through it cannot claim to answer a settled market.
    bare = build_payload(_market(), {}, now=NOW, stats={}, degraded=False)
    assert "market_settled" not in bare
    assert fill.answers_a_settled_market(bare) is False


def test_the_task_is_bounded_to_named_markets():
    import asyncio

    assert asyncio.run(fill.run_generic_market_history_fill(None))["markets_attempted"] == 0
    assert fill.MAX_MARKETS_PER_TASK <= 3 and fill.TOP_N_OUTCOMES <= 12


# ── fences ──────────────────────────────────────────────────────────────────


def _names_used(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    used |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            used |= {alias.name for alias in node.names}
    return used


def test_the_generic_fill_never_blends_venues_matches_legs_or_dispatches():
    used = _names_used(APP / "tasks" / "generic_market_history_fill.py")
    for forbidden in ("blend_venues", "find_venue_legs", "same_question",
                      "find_cross_source_markets", "_polymarket_token_id",
                      "apply_async", "delay", "send_task"):
        assert forbidden not in used, f"generic fill uses `{forbidden}`"
    # …and it writes no table: no session write verb appears in the module at all.
    # (`delete` is absent from this list on purpose — it is the Redis claim release.)
    for writer in ("insert", "add", "add_all", "merge", "commit", "flush", "bulk_insert_mappings"):
        assert writer not in used, f"generic fill calls `{writer}`"


def test_this_attempts_yield_is_counted_before_the_last_good_merge():
    """The count is only true in ONE place in the function, so pin the place.

    `stats.fetched_points` is what tells a settled market's answered attempt
    from a payload that merely carries a healthy series (CERT-3152). It is
    countable only while `entries` holds this attempt's points ALONE — one line
    below the last-good merge, a carried series and a fetched one are the same
    list, the count comes back positive for an attempt that fetched nothing, and
    the freeze this ship removed comes straight back. No behavioural test in
    this file can see that: it needs a venue, and the arm that watches the value
    over a real fill is B11 in
    `tests/integration/test_generic_market_history_7351_real_pg_redis.py`.

    So this one watches the POSITION, which is the part a refactor moves.
    """
    source = (APP / "tasks" / "generic_market_history_fill.py").read_text()
    tree = ast.parse(source)
    func = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "build_generic_history"
    )

    def _line(predicate, what):
        hits = [n.lineno for n in ast.walk(func) if predicate(n)]
        assert hits, f"`build_generic_history` no longer {what}"
        return min(hits)

    counted = _line(
        lambda n: (isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Constant)
                   and n.slice.value == "fetched_points"),
        "records `stats['fetched_points']`",
    )
    merged = _line(
        lambda n: (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                   and n.func.id == "validate_payload"),
        "carries a last-good series through `validate_payload`",
    )
    assert counted < merged, (
        f"`stats['fetched_points']` is set at line {counted}, AFTER the last-good "
        f"merge begins at line {merged}. Past that point the count includes points "
        "carried out of the cache, so an attempt that fetched nothing reads as an "
        "answered one and a settled chart freezes for the week (CERT-3152)."
    )


def test_the_route_seam_reads_a_cache_and_never_a_provider():
    source = (APP / "routes" / "futures.py").read_text(encoding="utf-8")
    start = source.index("class _GenericVenueHistory:")
    end = source.index('@router.get("/{market_id}/probability-timeline")')
    seam = source[start:end]
    for forbidden in ("KalshiAPIService", "PolymarketAPIService", "httpx", "get_prices_history",
                      "get_markets_candlesticks_raw", "build_generic_history",
                      "fill_generic_market_history(", "read_cached_series", "apply_venue_history"):
        assert forbidden not in seam, f"the request path names `{forbidden}`"
    assert seam.count(".apply_async(") == 1, "exactly one dispatch, in the route (not in app/tasks/)"
    assert "release_claim(market.id)" in seam, "a failed dispatch must hand the claim back"


def test_the_task_is_registered_routed_to_background_and_not_on_a_beat():
    from app import tasks

    name = "app.tasks.fill_generic_market_history"
    assert name in tasks.celery_app.tasks
    assert name in tasks._HEAVY_KEEP_ON_BACKGROUND and name not in tasks.HEAVY_TASKS
    beat = tasks.celery_app.conf.beat_schedule or {}
    assert all(entry.get("task") != name for entry in beat.values()), "no population sweep"
