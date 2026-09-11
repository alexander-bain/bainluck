"""#4970 / D132 — every priced leg on an event page says when it was observed.

## The ship

The event page shows a spread, a total and eight props side by side as if they
were all current. They are not: on event 15309206, read 2026-09-11 17:50Z, the
betting contributor was eight minutes old while Kalshi and Polymarket were
seconds old — and on the three busiest events of that week, legs ranged from
seconds to **25 hours** stale. A reader has no way to tell, so a dead price
reads exactly like a live one.

`GET /api/events/{id}/game-markets` served **no age field of any kind** (ux/1197
measured the full key set across `totals` / `spreads` / `other` / `player_props`
/ `team_totals` / `period_markets` / `matchups` and found none), which is why
the display half of D132 could not start. Now every priced leg carries
`observed_at`, and `stalenessLabel()` turns it into "· 4m ago".

## 🔴 The field that was right there and would have lied

`FuturesOutcome.last_updated` is already on the loaded rows. Free, no query, no
join — and wrong, because it is bumped by ANY write to the outcome: settlement
backfill, calibration, volume, rank. Measured on production 2026-09-11 across
1,074 outcomes on events 15308640 / 15309206 / 15308638:

    outcomes                                              1,074
    last_updated >30 min newer than the real observation    890   (83%)
    mean gap                                        404 minutes   (6.7 h)
    worst gap                                          25.75 h

So it would have reported a day-old dark price as freshly seen — the exact
defect this field exists to expose, wearing the field's own name. #4970's
acceptance line calls for "payload proof that metadata-only updates cannot reset
observation age"; `test_the_age_is_the_observation_not_the_rows_last_write` is
that proof, and the numbers above are why it is not a hypothetical.

A `futures_odds_snapshots` row exists only because a price was READ, so its
`captured_at` answers the question directly. Coverage on the busiest event of
the week: 549 of 550 outcomes, 102 ms for the whole bounded probe pass, on the
rebuild path only.

## 🔴 Why the value is absolute and never an age

This payload is cached — 30 s live and 1 h final in Redis, and the L1 memo holds
a FINAL body for the life of the process. A computed `age_hours` or `price_state`
would be frozen at build time and read FRESHER than the truth for as long as the
entry survives, which is the same class of claim as rendering `cache.created_at`
as a price age. The server sends the timestamp; the client does the subtraction.
`test_no_relative_age_is_served_because_this_payload_is_cached` pins that.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.routes import events as events_route
from app.routes.events import _game_markets_cache

NOW = datetime(2026, 5, 17, 23, 30, tzinfo=timezone.utc)

#: The seven row families a reader sees prices in. `props_script` is absent on
#: purpose — it is the verdict list (THE SCRIPT), carries no price, and is
#: derived from rows that already state their own age.
PRICED_SECTIONS = (
    "totals",
    "player_props",
    "team_totals",
    "spreads",
    "period_markets",
    "matchups",
    "other",
)


@pytest.fixture(autouse=True)
def _clear_cache():
    _game_markets_cache.clear()
    yield
    _game_markets_cache.clear()


def _result(scalar=None, rows=None, all_rows=None):
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar
    result.scalars.return_value.all.return_value = rows or []
    result.all.return_value = all_rows if all_rows is not None else []
    return result


def _market(*, id, name, external_id=None):
    market = MagicMock()
    market.id, market.name, market.external_id = id, name, external_id
    market.event_id, market.category, market.status = 42, "game_prop", "open"
    market.source, market.sport_id = "kalshi", 1
    market.llm_sport_category = "basketball"
    market.commence_time = datetime(2026, 5, 17, 23, 0, tzinfo=timezone.utc)
    market.group_id = market.group_type = None
    market.market_metadata = None
    market.market_tier = 5
    return market


def _outcome(*, id, market_id, name, prob, last_updated=NOW):
    outcome = MagicMock()
    outcome.id, outcome.market_id, outcome.name = id, market_id, name
    outcome.current_probability = prob
    outcome.opening_probability = 0.5
    outcome.is_winner = outcome.resolution_source = None
    # Deliberately fresh on every fixture row: the served age must not be able
    # to come from here. See the module docstring.
    outcome.last_updated = last_updated
    return outcome


def _event():
    event = MagicMock()
    event.id, event.status, event.sport_id = 42, "live", 1
    event.sport = MagicMock()
    event.sport.key = "basketball_nba"
    event.home_team_name, event.away_team_name = "Boston Celtics", "New York Knicks"
    event.home_score, event.away_score = 88, 82
    event.commence_time = datetime(2026, 5, 17, 23, 0, tzinfo=timezone.utc)
    event.completed_at = event.box_score_data = None
    event.period, event.game_clock = "3rd Quarter", "6:32"
    return event


def _the_page():
    """One market per family, so all seven sections are populated at once."""
    markets = [
        _market(id=101, name="Celtics at Knicks: Total Points"),
        _market(id=102, name="Celtics at Knicks: Spread"),
        _market(id=103, name="Celtics at Knicks: Jaylen Brown Points"),
        _market(id=104, name="Head-to-Head: Scheffler vs McIlroy"),
        _market(id=105, name="Celtics at Knicks: Team Total Points"),
        _market(id=106, name="Celtics at Warriors"),
        _market(
            id=107,
            name="Celtics at Knicks",
            external_id="KXNBA2HTOTAL-26MAY17BOSNYK",
        ),
    ]
    outcomes = [
        _outcome(id=1, market_id=101, name="Over 210.5", prob=0.52),
        _outcome(id=2, market_id=101, name="Under 210.5", prob=0.48),
        _outcome(id=3, market_id=102, name="Celtics -3.5", prob=0.54),
        _outcome(id=4, market_id=103, name="Jaylen Brown: 22+", prob=0.61),
        _outcome(id=5, market_id=104, name="Scheffler", prob=0.55),
        _outcome(id=6, market_id=104, name="McIlroy", prob=0.45),
        _outcome(id=7, market_id=105, name="Over 105.5", prob=0.50),
        _outcome(id=8, market_id=106, name="Yes", prob=0.70),
        _outcome(id=9, market_id=107, name="Over 105.5", prob=0.52),
    ]
    return markets, outcomes


def _db(markets, outcomes, observations):
    """`observations` is `{outcome_id: datetime | None}`.

    A `None` reaches the loader as a row whose `observed_at` is NULL, which is
    how "this outcome has never been priced" arrives from PostgreSQL; the loader
    drops it, so the page serves `None`. An id absent from the dict entirely is
    the same state by the other route.
    """
    rows = [
        SimpleNamespace(id=oid, observed_at=seen)
        for oid, seen in observations.items()
    ]
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _result(scalar=_event()),
            _result(rows=[]),  # #2693 folded_event_ids
            _result(rows=markets),
            _result(all_rows=[]),  # polymarket parent groups
            _result(rows=[]),  # unlinked fallback
            _result(rows=outcomes),
            _result(all_rows=rows),  # #4970 the observation load
        ]
    )
    return db


def _payload(*, observations=None, markets=None, outcomes=None):
    fixture_markets, fixture_outcomes = _the_page()
    markets = fixture_markets if markets is None else markets
    outcomes = fixture_outcomes if outcomes is None else outcomes
    if observations is None:
        # Distinct per outcome, so a row serving the WRONG leg's age is visible
        # rather than accidentally right.
        observations = {o.id: NOW - timedelta(minutes=o.id) for o in outcomes}
    response, _status, _ids = asyncio.run(
        events_route._build_game_markets(42, _db(markets, outcomes, observations))
    )
    return response


def _priced_legs(payload):
    """Every dict in the payload that shows a reader a price.

    Defined by the PRICE, not by a hand-listed set of families: anything
    carrying `probability` or `over_probability` is a leg, wherever it sits and
    however deeply nested. A family added later is covered without editing this
    file — which is the only version of this check that stays true.
    """
    found = []

    def walk(node, path):
        if isinstance(node, dict):
            if "probability" in node or "over_probability" in node:
                found.append((path, node))
            for key, value in node.items():
                walk(value, f"{path}.{key}")
        elif isinstance(node, list):
            for i, value in enumerate(node):
                walk(value, f"{path}[{i}]")

    for section in PRICED_SECTIONS:
        walk(payload.get(section), section)
    return found


class TestEveryPricedLegStatesItsAge:
    def test_every_priced_leg_in_the_payload_carries_its_own_observation_time(self):
        """The ship, stated over the whole payload rather than one family."""
        payload = _payload()
        legs = _priced_legs(payload)

        missing = [path for path, leg in legs if "observed_at" not in leg]
        assert missing == [], (
            f"{len(missing)} priced legs reach the reader with no age: {missing}"
        )

    def test_the_fixture_really_fills_all_seven_families(self):
        """Vacuity floor. The check above passes trivially over an empty page.

        Every one of the seven sections must be populated AND contribute at
        least one priced leg, so a fixture that stops building rows fails here
        instead of quietly turning the guard above into an assertion about
        nothing.
        """
        payload = _payload()
        empty = [s for s in PRICED_SECTIONS if not payload.get(s)]
        assert empty == [], f"fixture populates no rows for {empty}"

        legs = _priced_legs(payload)
        assert len(legs) >= 8, f"only {len(legs)} priced legs in the whole payload"
        families = {path.split(".")[0].split("[")[0] for path, _ in legs}
        assert families == set(PRICED_SECTIONS), (
            f"priced legs came from {sorted(families)}, not all seven families"
        )

    def test_the_walk_would_catch_a_family_that_forgot_the_field(self):
        """The instrument fires. A screen that never detects anything is not a
        screen, and this one is the reason the guard above can be trusted — it
        is the same shape as `_priced_legs` running over a payload where one
        family was missed."""
        payload = _payload()
        payload["spreads"][0].pop("observed_at")

        missing = [path for path, leg in _priced_legs(payload) if "observed_at" not in leg]
        assert missing, "the walk did not notice a leg with no age"
        assert all(path.startswith("spreads") for path in missing)

    def test_the_nested_matchup_legs_are_reached_too(self):
        """A matchup's prices live one level down, under `outcomes`.

        Stated separately because the walk above finds them generically, and a
        change that flattened matchups would keep that check green while the
        nested legs stopped existing.
        """
        matchup = _payload()["matchups"][0]
        legs = matchup["outcomes"]
        assert len(legs) == 2
        assert all(leg["observed_at"] is not None for leg in legs)
        assert legs[0]["observed_at"] != legs[1]["observed_at"]


class TestTheAgeIsTheObservationAndNothingElse:
    def test_each_leg_serves_its_own_outcomes_observation(self):
        """Not the page's newest, not the market's — this leg's."""
        seen = {1: NOW - timedelta(minutes=90), 2: NOW - timedelta(minutes=90)}
        seen.update({i: NOW - timedelta(minutes=i) for i in range(3, 10)})
        payload = _payload(observations=seen)

        spread = payload["spreads"][0]
        assert spread["observed_at"] == (NOW - timedelta(minutes=3)).isoformat()

        prop = payload["player_props"][0]
        assert prop["observed_at"] == (NOW - timedelta(minutes=4)).isoformat()

    def test_the_age_is_the_observation_not_the_rows_last_write(self):
        """#4970's acceptance line: a metadata-only write cannot reset the age.

        Every fixture outcome carries `last_updated = NOW`. If the payload ever
        starts reading that field — it is on the row, it is free, and it is the
        obvious shortcut — this leg would report itself as observed right now
        instead of 26 hours ago. On production 83% of outcomes are in exactly
        that state.
        """
        stale = NOW - timedelta(hours=26)
        seen = {o.id: stale for o in _the_page()[1]}
        payload = _payload(observations=seen)

        legs = _priced_legs(payload)
        assert legs, "no priced legs to check"
        for path, leg in legs:
            assert leg["observed_at"] == stale.isoformat(), path
            assert leg["observed_at"] != NOW.isoformat(), (
                f"{path} served the row's last write, not its observation"
            )

    def test_a_leg_never_observed_serves_null_rather_than_a_fresh_time(self):
        """Absent means absent (gotcha #53).

        The key is present and `None` — not omitted, and above all not `now`.
        An unpriced leg reading as freshly seen is worse than showing nothing.
        """
        seen = {o.id: NOW - timedelta(minutes=5) for o in _the_page()[1]}
        seen[3] = None  # the spread's outcome has never been priced
        payload = _payload(observations=seen)

        spread = payload["spreads"][0]
        assert "observed_at" in spread
        assert spread["observed_at"] is None
        # Its neighbours are unaffected — one dark leg is not a dark page.
        assert payload["player_props"][0]["observed_at"] is not None

    def test_an_outcome_missing_from_the_load_entirely_is_also_null(self):
        """The loader omits never-observed outcomes rather than mapping them to
        `None`, so both spellings of "no observation" must land on the reader
        the same way."""
        seen = {o.id: NOW - timedelta(minutes=5) for o in _the_page()[1]}
        del seen[3]
        assert _payload(observations=seen)["spreads"][0]["observed_at"] is None


class TestTheContractIsCacheSafe:
    def test_no_relative_age_is_served_because_this_payload_is_cached(self):
        """A number that means "hours ago" freezes in the cache and reads
        fresher than the truth. Only the absolute stamp may travel."""
        legs = _priced_legs(_payload())
        assert legs
        for path, leg in legs:
            for banned in ("age_hours", "price_state", "age_minutes", "is_stale"):
                assert banned not in leg, (
                    f"{path} serves `{banned}`, which is relative to build time "
                    f"and this payload is cached for up to an hour"
                )

    def test_the_stamp_is_an_absolute_parseable_instant_with_a_timezone(self):
        """What the client subtracts from. A naive stamp would be read as local
        time in the browser and produce ages that are hours wrong."""
        for path, leg in _priced_legs(_payload()):
            stamp = leg["observed_at"]
            parsed = datetime.fromisoformat(stamp)
            assert parsed.tzinfo is not None, f"{path} stamp has no timezone"
            assert parsed == NOW - timedelta(
                minutes=int((NOW - parsed).total_seconds() // 60)
            )


class TestTheLoadItself:
    def test_the_observation_load_is_asked_for_exactly_the_pages_outcomes(
        self, monkeypatch
    ):
        """Proves the query RUNS, and that it stays bounded.

        `latest_observation` is only the right shape for a bounded id list — it
        is one index probe per id, and its own docstring says so. A caller that
        let the id list grow unbounded would be reintroducing the aggregate this
        helper exists to replace, so the ids it is handed are part of the
        contract, not an implementation detail.
        """
        captured = {}

        async def _spy(session, outcome_ids):
            captured["ids"] = list(outcome_ids)
            return {}

        monkeypatch.setattr(
            "app.utils.latest_observation.load_latest_observed_at", _spy
        )
        payload = _payload()

        assert "ids" in captured, "the observation load never ran"
        assert sorted(captured["ids"]) == list(range(1, 10))
        # And with the loader stubbed empty, every leg is honestly dark.
        assert all(leg["observed_at"] is None for _p, leg in _priced_legs(payload))


# ─────────────────────────────────────────────────────────────────────────────
# CERT-2640: a TRANSFORMED price carries its INPUT's clock, not its own.
#
# The first presentation stamped every leg correctly at the point it was built
# and then let two passes change the NUMBER while the stamp rode along
# unchanged. Both produce a row whose `observed_at` describes a price the reader
# is no longer being shown, and in one direction each the row reads FRESHER than
# the truth — the only direction a reader cannot catch.
# ─────────────────────────────────────────────────────────────────────────────

THIRTY_HOURS = NOW - timedelta(hours=30)
EIGHT_MINUTES = NOW - timedelta(minutes=8)


def _cross_source_prop(*, kalshi_prob, poly_prob):
    """Two venues quoting the SAME player+stat+threshold+side.

    That tuple is step 9b's dedup key, so these two rows are averaged into one.
    """
    kalshi = _market(id=201, name="Celtics at Knicks: Jaylen Brown Points")
    kalshi.source = "kalshi"
    poly = _market(id=202, name="Celtics at Knicks: Jaylen Brown Points")
    poly.source = "polymarket"
    outcomes = [
        _outcome(id=201, market_id=201, name="Jaylen Brown: 22+", prob=kalshi_prob),
        _outcome(id=202, market_id=202, name="Jaylen Brown: 22+", prob=poly_prob),
    ]
    return [kalshi, poly], outcomes


class TestABlendedPriceCarriesItsOldestContributorsClock:
    """A merged prop is nobody's quote, so it cannot claim anybody's clock."""

    @pytest.mark.parametrize(
        "kalshi_seen,poly_seen,label",
        [
            (THIRTY_HOURS, EIGHT_MINUTES, "stale Kalshi is the representative"),
            (EIGHT_MINUTES, THIRTY_HOURS, "fresh Kalshi is the representative"),
        ],
    )
    def test_the_blend_reports_its_stalest_input_in_either_order(
        self, kalshi_seen, poly_seen, label
    ):
        """🔴 The required regression, and the ORDER is the whole point.

        `best` is chosen by SOURCE — Kalshi always wins — never by age. So the
        two rows below serve the identical blended number, 50%, from the
        identical pair of clocks, and differ only in which venue holds the stale
        one. Before the repair the first case reported 30 h (pessimistic, and
        visible) and the second reported 8 MINUTES over a number half a day
        stale. A guard that pinned only one order would have passed on the
        broken code half the time.
        """
        markets, outcomes = _cross_source_prop(kalshi_prob=0.60, poly_prob=0.40)
        payload = _payload(
            markets=markets,
            outcomes=outcomes,
            observations={201: kalshi_seen, 202: poly_seen},
        )

        props = payload["player_props"]
        assert len(props) == 1, f"the two venues did not merge ({label})"
        merged = props[0]
        assert merged["source_count"] == 2
        assert merged["over_probability"] == 0.50, "fixture is not exercising the blend"

        assert merged["observed_at"] == THIRTY_HOURS.isoformat(), (
            f"the blend claims a clock its stalest half cannot support ({label})"
        )

    @pytest.mark.parametrize(
        "kalshi_seen,poly_seen,label",
        [
            (THIRTY_HOURS, EIGHT_MINUTES, "stale Kalshi is the representative"),
            (EIGHT_MINUTES, THIRTY_HOURS, "fresh Kalshi is the representative"),
        ],
    )
    def test_the_per_source_clocks_survive_the_merge(self, kalshi_seen, poly_seen, label):
        """Preserved, not just collapsed: which side is stale is recoverable.

        🔴 PARAMETRIZED BECAUSE THE UNPARAMETRIZED VERSION WAS VACUOUS. This test
        used to pin only the first row, where the representative is ALSO the
        stalest contributor — so writing the blended stamp onto `best` before
        reading the contributors back overwrote Kalshi's clock with a value
        identical to it, and the map came out right by accident. CERT-2647
        blocked on the second row: with the ages swapped, both venues reported
        30 h and the fresh side vanished. Same lesson as the blend test above,
        one field deeper.
        """
        markets, outcomes = _cross_source_prop(kalshi_prob=0.60, poly_prob=0.40)
        payload = _payload(
            markets=markets,
            outcomes=outcomes,
            observations={201: kalshi_seen, 202: poly_seen},
        )

        by_source = payload["player_props"][0]["observed_at_by_source"]
        assert by_source == {
            "kalshi": kalshi_seen.isoformat(),
            "polymarket": poly_seen.isoformat(),
        }, f"a contributor's own clock did not survive the merge ({label})"

    def test_one_unobserved_contributor_makes_the_blend_dark(self):
        """Absent is not recent (gotcha #53).

        A contributor with no priced snapshot has an UNKNOWN age, and unknown may
        be older than everything else in the blend. Reporting the minimum of the
        rest would publish a bound the data cannot support, so the row goes dark
        instead of guessing.
        """
        markets, outcomes = _cross_source_prop(kalshi_prob=0.60, poly_prob=0.40)
        payload = _payload(
            markets=markets,
            outcomes=outcomes,
            observations={201: EIGHT_MINUTES, 202: None},
        )

        merged = payload["player_props"][0]
        assert merged["source_count"] == 2, "fixture is not exercising the blend"
        assert merged["observed_at"] is None


def _two_total_rungs(*, low_prob, high_prob):
    """Two game-total rungs on one curve — the monotonicity pass's subject."""
    low = _market(id=301, name="Celtics at Knicks: Total Points")
    high = _market(id=302, name="Celtics at Knicks: Total Points")
    outcomes = [
        _outcome(id=301, market_id=301, name="Over 210.5", prob=low_prob),
        _outcome(id=302, market_id=302, name="Over 215.5", prob=high_prob),
    ]
    return [low, high], outcomes


class TestACappedRungCarriesTheClockOfThePriceItNowShows:
    def test_an_old_low_rung_capping_a_fresh_high_one_does_not_keep_the_fresh_clock(self):
        """🔴 The required regression.

        P(Over 215.5) may not exceed P(Over 210.5), so the 70% rung is rewritten
        to the 60% the older rung was observed at. The row keeps its identity —
        it is still the 215.5 line — but it no longer carries its own price, and
        before the repair it kept its own five-minute-old stamp over a six-hour-old
        number.
        """
        markets, outcomes = _two_total_rungs(low_prob=0.60, high_prob=0.70)
        old, fresh = NOW - timedelta(hours=6), NOW - timedelta(minutes=5)
        payload = _payload(
            markets=markets,
            outcomes=outcomes,
            observations={301: old, 302: fresh},
        )

        rungs = {t["threshold"]: t for t in payload["totals"]}
        assert set(rungs) == {210.5, 215.5}, f"fixture built {sorted(rungs)}"

        capped = rungs[215.5]
        assert capped["over_probability"] == 0.60, "the cap did not fire"
        assert capped["observed_at"] == old.isoformat(), (
            "the capped rung is serving the donor's price under its own fresh clock"
        )
        assert capped["observed_at_basis"] == "capped_to_sibling"

        # The donor is untouched: it still shows its own price and its own clock.
        assert rungs[210.5]["over_probability"] == 0.60
        assert rungs[210.5]["observed_at"] == old.isoformat()
        assert "observed_at_basis" not in rungs[210.5]

    def test_a_rung_that_is_not_capped_keeps_its_own_clock_and_is_not_marked(self):
        """The other side of the ratchet.

        Without this, "stamp every rung with the previous one's clock" passes the
        test above and destroys the field for every well-formed curve — the
        repair would have become a second, quieter version of the same bug.
        """
        markets, outcomes = _two_total_rungs(low_prob=0.70, high_prob=0.55)
        old, fresh = NOW - timedelta(hours=6), NOW - timedelta(minutes=5)
        payload = _payload(
            markets=markets,
            outcomes=outcomes,
            observations={301: old, 302: fresh},
        )

        rungs = {t["threshold"]: t for t in payload["totals"]}
        high = rungs[215.5]
        assert high["over_probability"] == 0.55, "this curve should not be capped"
        assert high["observed_at"] == fresh.isoformat()
        assert "observed_at_basis" not in high


# ─────────────────────────────────────────────────────────────────────────────
# 🔴 #4970 / CERT-2647 — THE SECOND BLOCK: A TRANSFORM THAT READS ITS OWN OUTPUT
#
# The first repair got both PRICES' clocks right and then lost the provenance
# underneath them, in two places that are the same mistake wearing two faces:
#
#   THE BLEND wrote the merged stamp onto `best` — which IS one of `entries`,
#   the same dict object — and only then walked `entries` to build the
#   per-source map. The representative's own clock was already gone, so a fresh
#   Kalshi price beside a stale Polymarket one reported BOTH venues as stale.
#
#   THE CAP took the donor's price and the donor's stamp, and kept the capped
#   row's own `observed_at_by_source` — a breakdown of the price it had just
#   discarded. One row, two contradictory observations, and the more specific
#   one blamed the wrong venue.
#
# Both are "read every input before writing any of them". Neither is visible
# unless the fixture makes the representative the FRESH side, which is why the
# order is parametrized here and in the merge test above.
# ─────────────────────────────────────────────────────────────────────────────


def _blended_donor_and_capped_rung(*, kalshi_prob, poly_prob, high_prob):
    """A cross-source blend at the low rung, single-source at the high rung.

    Step 9b merges the low rung (so it is the only kind of row that HAS an
    `observed_at_by_source` to donate); step 9c then caps the high rung to it.
    That ordering is what makes donor provenance reachable at all.
    """
    kalshi_low = _market(id=401, name="Celtics at Knicks: Jayson Tatum Points")
    kalshi_low.source = "kalshi"
    poly_low = _market(id=402, name="Celtics at Knicks: Jayson Tatum Points")
    poly_low.source = "polymarket"
    kalshi_high = _market(id=403, name="Celtics at Knicks: Jayson Tatum Points")
    kalshi_high.source = "kalshi"
    outcomes = [
        _outcome(id=401, market_id=401, name="Jayson Tatum: 22+", prob=kalshi_prob),
        _outcome(id=402, market_id=402, name="Jayson Tatum: 22+", prob=poly_prob),
        _outcome(id=403, market_id=403, name="Jayson Tatum: 26+", prob=high_prob),
    ]
    return [kalshi_low, poly_low, kalshi_high], outcomes


class TestATransformNeverReadsItsOwnOutput:
    """The required regression for CERT-2647, both halves."""

    @pytest.mark.parametrize(
        "kalshi_seen,poly_seen,label",
        [
            (THIRTY_HOURS, EIGHT_MINUTES, "stale Kalshi is the representative"),
            (EIGHT_MINUTES, THIRTY_HOURS, "fresh Kalshi is the representative"),
        ],
    )
    def test_per_source_clocks_survive_in_both_representative_age_orders_and_caps_copy_donor_provenance(
        self, kalshi_seen, poly_seen, label
    ):
        """🔴 The cert's named regression.

        One payload exercises both halves because they are one pipeline: the
        merged 22+ rung is the donor, and the 26+ rung is capped to it. The
        parametrized order is load-bearing — with the stale venue as the
        representative the BROKEN code returns the right map by accident, so a
        single-order guard would have passed on it half the time.
        """
        markets, outcomes = _blended_donor_and_capped_rung(
            kalshi_prob=0.60, poly_prob=0.40, high_prob=0.70
        )
        fresh_high = NOW - timedelta(minutes=5)
        payload = _payload(
            markets=markets,
            outcomes=outcomes,
            observations={401: kalshi_seen, 402: poly_seen, 403: fresh_high},
        )

        rungs = {p["threshold"]: p for p in payload["player_props"]}
        assert set(rungs) == {22.0, 26.0}, f"fixture built {sorted(rungs)}"

        # ── Half one: the blend keeps every contributor's OWN clock.
        donor = rungs[22.0]
        assert donor["source_count"] == 2, "the two venues did not merge"
        assert donor["over_probability"] == 0.50, "fixture is not exercising the blend"
        assert donor["observed_at_by_source"] == {
            "kalshi": kalshi_seen.isoformat(),
            "polymarket": poly_seen.isoformat(),
        }, f"the representative's own clock was overwritten before it was read ({label})"

        # ── Half two: the capped rung's provenance is the DONOR's, not the
        # discarded price's. `observed_at` and `observed_at_by_source` must
        # describe one and the same observation.
        capped = rungs[26.0]
        assert capped["over_probability"] == 0.50, "the cap did not fire"
        assert capped["observed_at_basis"] == "capped_to_sibling"
        assert capped["observed_at"] == donor["observed_at"]
        assert capped["observed_at_by_source"] == donor["observed_at_by_source"], (
            f"the capped rung kept the source map of the price it discarded ({label})"
        )
        assert fresh_high.isoformat() not in capped["observed_at_by_source"].values(), (
            "the discarded price's clock is still reachable on the served row"
        )

    def test_a_cap_from_a_single_source_donor_clears_a_stale_source_map(self):
        """🔴 The over-application's mirror, and the case that is easy to miss.

        When the donor has no breakdown of its own, "copy the donor's map" is a
        no-op — and a no-op LEAVES the capped row's own map standing over a
        price it no longer shows. Absent must beat wrong: the row goes down to
        its aggregate stamp rather than keeping a specific claim that is false.
        """
        markets, outcomes = _blended_donor_and_capped_rung(
            kalshi_prob=0.50, poly_prob=0.50, high_prob=0.70
        )
        # Make the HIGH rung the merged one and the LOW rung single-source, by
        # moving the Polymarket quote onto the 26+ line.
        markets[1].id = 402
        outcomes[1].market_id = 402
        outcomes[1].name = "Jayson Tatum: 26+"
        fresh_high = NOW - timedelta(minutes=5)
        payload = _payload(
            markets=markets,
            outcomes=outcomes,
            observations={401: THIRTY_HOURS, 402: EIGHT_MINUTES, 403: fresh_high},
        )

        rungs = {p["threshold"]: p for p in payload["player_props"]}
        capped = rungs.get(26.0)
        assert capped is not None, f"fixture built {sorted(rungs)}"
        # Asserted, never skipped-over: a conditional skip here would turn this
        # guard off silently the day the fixture stops capping, which is exactly
        # when it is needed.
        assert capped["observed_at_basis"] == "capped_to_sibling", "the cap did not fire"
        donor = rungs[22.0]
        assert "observed_at_by_source" not in donor, "fixture donor is not single-source"
        assert "observed_at_by_source" not in capped, (
            "a single-source donor left the capped rung's discarded source map standing"
        )
