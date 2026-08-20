"""#2020 — the auto-create loop that generated 51,673 unanchored events, and the
growth gate that could not see it.

Two defects, one incident, guarded here together because neither is safe alone:

1. **The create path manufactured rows its own linkage guard was guaranteed to
   refuse.** `_create_event_from_prediction_market` stamped Kalshi's
   `commence_time` — which is the market's CLOSE time, not the game start
   (gotcha #14) — onto every event it created. The very next poll,
   `_check_duplicate_kalshi_linkage_reason` compared that row against the
   market's TICKER date, found a two-day disagreement, refused the link, and
   sent the market straight back to the auto-create. Measured: **297 events for
   ONE market**, a new row every ~5 minutes for 21.5 hours.

2. **The Flow Sentinel's meter check passed throughout.** It gated on
   `created > 0 and reconciled == 0`; `reconciled` had drifted to 173 by
   incidental means, so the gate read PASS while the population went
   500 -> 51,673 at ~2,400 rows/hour.

Both directions are asserted for each: the loop terminates AND legitimate
creates still happen; the growth gate fires AND a quiet night stays green.
"""

from datetime import datetime, timedelta, timezone

from app.tasks.flow_sentinel import (
    UNANCHORED_GROWTH_PER_HOUR_CEILING,
    provenance_growth,
)
from app.tasks.prediction_market_matching import (
    auto_create_commence_time,
    auto_create_self_refutes,
)


class _Market:
    """The three fields both helpers read. Deliberately not an ORM object."""

    def __init__(self, external_id, source="kalshi", commence_time=None):
        self.external_id = external_id
        self.source = source
        self.commence_time = commence_time


# The production specimen, read live 2026-08-20T04:0xZ. One market, 297 events.
_SPECIMEN_TICKER = "KXLOLGAME-26AUG210500GAMTSW"
_SPECIMEN_TICKER_TIME = datetime(2026, 8, 21, 5, 0, tzinfo=timezone.utc)
_SPECIMEN_CLOSE_TIME = datetime(2026, 8, 23, 9, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Defect 1 — the create path
# ---------------------------------------------------------------------------
def test_the_specimen_close_time_is_what_the_guard_refuses():
    """The premise, asserted rather than assumed: the OLD behaviour self-refutes.

    If this ever stops being true the loop below is not the loop we fixed, and
    the rest of this file is guarding a story instead of a defect.
    """
    market = _Market(_SPECIMEN_TICKER, commence_time=_SPECIMEN_CLOSE_TIME)
    assert auto_create_self_refutes(market, _SPECIMEN_CLOSE_TIME) is True


def test_the_created_row_no_longer_self_refutes():
    """The fix: stamp the TICKER time, and the row the guard sees is acceptable."""
    market = _Market(_SPECIMEN_TICKER, commence_time=_SPECIMEN_CLOSE_TIME)
    commence, source = auto_create_commence_time(market, _SPECIMEN_CLOSE_TIME)

    assert commence == _SPECIMEN_TICKER_TIME
    assert source == "kalshi_ticker"
    # ...and the loop is closed: the row we would now write is one the guard
    # accepts, so the next poll LINKS instead of creating a 298th event.
    assert auto_create_self_refutes(market, commence) is False


def test_a_market_with_no_parseable_ticker_keeps_the_fallback():
    """Polymarket has no ticker at all — it must not be broken by the Kalshi fix."""
    fallback = datetime(2026, 8, 23, 9, 0, tzinfo=timezone.utc)
    market = _Market("0xdeadbeef", source="polymarket", commence_time=fallback)

    commence, source = auto_create_commence_time(market, fallback)
    assert commence == fallback
    assert source is None
    # And it can never be refused by a guard that only reads Kalshi tickers.
    assert auto_create_self_refutes(market, commence) is False


def test_a_kalshi_market_whose_ticker_agrees_still_creates():
    """The cap must not eat legitimate creates — the #1091/gotcha #43 direction.

    A ticker and a commence_time that agree is the ordinary, healthy case, and it
    has to survive a change whose whole purpose is to refuse things.
    """
    market = _Market(_SPECIMEN_TICKER, commence_time=_SPECIMEN_TICKER_TIME)
    assert auto_create_self_refutes(market, _SPECIMEN_TICKER_TIME) is False


def test_combat_stays_exempt():
    """Combat is exempt from the date guard entirely, so it can never self-refute.

    If this refused, the create path would start dropping combat events that the
    guard would have happily linked.
    """
    market = _Market("KXUFCFIGHT-26AUG210500ABCDEF")
    far_off = datetime(2026, 12, 25, 9, 0, tzinfo=timezone.utc)
    assert auto_create_self_refutes(market, far_off) is False


# ---------------------------------------------------------------------------
# Defect 1, at the CALL SITE — because a helper is not a call site
# ---------------------------------------------------------------------------
# Ruling 102, obligation 4: `test_the_helper_coerces()` can be satisfied by a
# helper nobody calls. Everything above tests two pure functions; these two
# drive the real `_create_event_from_prediction_market` and assert what it does
# with them. Delete either call and these go red — the ones above would not.


class _Matchup:
    def __init__(self, team_a, team_b):
        self.team_a = team_a
        self.team_b = team_b


class _FullMarket(_Market):
    def __init__(self, external_id, commence_time):
        super().__init__(external_id, source="kalshi", commence_time=commence_time)
        self.name = "GAM Esports vs. Team Secret Whales"
        self.llm_sport_category = None
        self.id = 59180741


async def test_call_site_refuses_the_self_refuting_create(monkeypatch):
    """The bleed-stop, at the call site: no registry call, no row, no loop."""
    import app.services.event_registry as registry
    from app.tasks.prediction_market_matching import (
        _create_event_from_prediction_market,
    )

    called = []

    async def _never(*a, **kw):
        called.append(kw)
        raise AssertionError("find_or_create_event must not be reached")

    monkeypatch.setattr(registry, "find_or_create_event", _never)
    # Force the pre-fix commence_time selection so the call site is asked the
    # question the loop asked it 297 times. Without the refusal it would create.
    monkeypatch.setattr(
        "app.tasks.prediction_market_matching.auto_create_commence_time",
        lambda market, fallback: (_SPECIMEN_CLOSE_TIME, None),
    )

    result = await _create_event_from_prediction_market(
        None,
        _Matchup("GAM Esports", "Team Secret Whales"),
        _FullMarket(_SPECIMEN_TICKER, _SPECIMEN_CLOSE_TIME),
        datetime(2026, 8, 20, 4, 0, tzinfo=timezone.utc),
    )

    assert result is None
    assert called == []


async def test_call_site_stamps_the_ticker_time_on_the_identity(monkeypatch):
    """The fix, at the call site: the row we would write carries the TICKER time.

    Captures the `EventIdentity` the registry is actually handed, then raises
    ValueError — which the call site already catches — so nothing downstream of
    the registry has to be faked to read the one thing under test.
    """
    import app.services.event_registry as registry
    from app.tasks.prediction_market_matching import (
        _create_event_from_prediction_market,
    )

    seen = {}

    async def _capture(session, identity):
        seen["identity"] = identity
        raise ValueError("stop here — the identity is what this test reads")

    monkeypatch.setattr(registry, "find_or_create_event", _capture)

    result = await _create_event_from_prediction_market(
        None,
        _Matchup("GAM Esports", "Team Secret Whales"),
        _FullMarket(_SPECIMEN_TICKER, _SPECIMEN_CLOSE_TIME),
        datetime(2026, 8, 20, 4, 0, tzinfo=timezone.utc),
    )

    assert result is None  # the ValueError path, as designed
    identity = seen["identity"]
    assert identity.commence_time == _SPECIMEN_TICKER_TIME, (
        "the created row must carry the ticker's game time, not Kalshi's close "
        "time — stamping the close time is what closed the 297-event loop"
    )
    assert identity.commence_time_source == "kalshi_ticker"
    # Ruling 048 is untouched by this fix: the claim stays unanchored.
    assert identity.claim.schedule_derived is False


# ---------------------------------------------------------------------------
# Defect 2 — the growth gate
# ---------------------------------------------------------------------------
def _reading(created, reconciled, hours_ago, now):
    return {
        "read_at": (now - timedelta(hours=hours_ago)).isoformat(),
        "created_unanchored": created,
        "reconciled": reconciled,
        "unreconciled": created - reconciled,
    }


def test_the_incident_rate_is_caught():
    """The reading the old gate passed on. 41,872 -> 51,673 over ~27h."""
    now = datetime(2026, 8, 20, 4, 3, tzinfo=timezone.utc)
    prior = _reading(41_872, 173, 27.0, now)
    growth = provenance_growth(prior, {"created_unanchored": 51_673, "reconciled": 195}, now)

    assert growth["measured"] is True
    assert growth["created_delta"] == 9_801
    assert growth["rate_per_hour"] > UNANCHORED_GROWTH_PER_HOUR_CEILING


def test_the_old_gate_would_have_passed_on_that_same_reading():
    """Why the growth gate had to be added, asserted rather than narrated.

    `created > 0 and reconciled == 0` is FALSE here — 195 rows had reconciled by
    incidental means — so the pre-#2020 check reported PASS while the population
    grew 100x. A gate that passes while the thing it guards runs away is worse
    than a noisy one, because it gets quoted as evidence of health.
    """
    created, reconciled = 51_673, 195
    assert not (created > 0 and reconciled == 0)


def test_a_quiet_night_stays_green():
    """The healthy regime, measured: 2026-08-18 added 6 rows in a day."""
    now = datetime(2026, 8, 19, 0, 0, tzinfo=timezone.utc)
    prior = _reading(500, 0, 24.0, now)
    growth = provenance_growth(prior, {"created_unanchored": 506, "reconciled": 0}, now)

    assert growth["measured"] is True
    assert growth["rate_per_hour"] < UNANCHORED_GROWTH_PER_HOUR_CEILING


def test_no_prior_reading_never_fails_the_gate():
    """An absent comparison is not evidence of health — and not of sickness either.

    gotcha #53: the emptier reading must not be turned into a fact. `measured`
    is False and `rate_per_hour` is None, which the caller treats as "do not
    gate", and the reason says which of the two it is.
    """
    now = datetime(2026, 8, 20, 4, 0, tzinfo=timezone.utc)
    growth = provenance_growth(None, {"created_unanchored": 51_673, "reconciled": 195}, now)

    assert growth["measured"] is False
    assert growth["rate_per_hour"] is None
    assert "no prior reading" in growth["reason"]


def test_a_future_stamped_prior_refuses_to_produce_a_rate():
    """Ahead-drift must not make the gate fail OPEN.

    A prior stamped in the future gives a negative interval and therefore a
    negative rate, which sits below any ceiling forever. The lane locks learned
    this exact failure twice (`reference_program_lane_double_window`); a clock
    comparison that can go negative must refuse, not compute.
    """
    now = datetime(2026, 8, 20, 4, 0, tzinfo=timezone.utc)
    prior = _reading(41_872, 173, -6.0, now)  # stamped 6h in the FUTURE
    growth = provenance_growth(prior, {"created_unanchored": 51_673, "reconciled": 195}, now)

    assert growth["measured"] is False
    assert growth["rate_per_hour"] is None
    assert "non-positive interval" in growth["reason"]


def test_a_negative_reconciled_delta_is_reported_not_swallowed():
    """`reconciled` is NOT monotone — it was observed moving 180 -> 173 live.

    So it is reported for context and never used as a denominator; a reader who
    treats it as drain progress would conclude the drain ran backwards.
    """
    now = datetime(2026, 8, 20, 4, 0, tzinfo=timezone.utc)
    prior = _reading(41_872, 180, 12.0, now)
    growth = provenance_growth(prior, {"created_unanchored": 47_957, "reconciled": 173}, now)

    assert growth["reconciled_delta"] == -7
    assert growth["measured"] is True
