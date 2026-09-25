"""#8522 / CERT-3444 follow-ups — drive the second writer, and the edges of the rule.

CERT-3444 granted the #8522 deferral and named two follow-ups:

* ``8522-ODDS-POLL-DEFER-BEHAVIOR-GUARD`` — the odds-poll writer of
  ``stat_model`` (events with no ESPN link, #1829) was guarded only by reading
  its source text. Here the REAL ``_poll_all_odds`` runs over a seeded database
  with an Odds API scores payload at 0–0, and the assertions read the row and
  the ``win_prob_snapshots`` table back through a fresh session.
* ``8522-DEFER-TRANSITION-AND-ELIGIBILITY`` — (a) a market that arrives AFTER
  the model already wrote, and (b) a market entry the blend explicitly refuses.

Both were real gaps, fixed beside this file:

(a) A writer that only declines to write freezes the reading it wrote last
    (#5031's lesson). The hero ages sources relative to each other, so a frozen
    1.0-weight 50% held the headline over a fresh 0.8-weight Kalshi price for
    ~16 minutes. A deferring writer now retires the ``stat_model`` entry.
(b) The rule counted a refused entry as a market price while
    ``_tier1_readings`` drops it, so the model deferred to a number the
    headline never uses and the row served no number at all.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.utils.aggregation import (
    MAX_STALENESS,
    compute_aggregate_probability,
    stamp_source_reading,
)
from app.utils.probability_eligibility import ineligible_record, is_refused
from app.utils.win_probability import (
    priorless_model_defers_to_market,
    retire_priorless_model_reading,
)
from tests.test_a_settled_final_survives_the_writer_7147_e2e import (
    _AsyncShim as _PollShim,
    _engine,
    _FakeRedis,
    _score_record,
)
from tests.test_priorless_stat_model_defers_to_market_8522 import (
    KALSHI_JUST_BEFORE,
    STAMP,
    _live_row_on_disk,
    _run_writer,
    _stored as _stored_espn,
)


def _row(sources):
    """A real, unsaved ``Event``: a MagicMock answers every other attribute the
    aggregate reads with a truthy mock, which is not a row."""
    from app.models.models import Event

    return Event(
        win_probability_sources=sources, status="live", opening_home_probability=None
    )


def _refused_kalshi(value=KALSHI_JUST_BEFORE):
    """A Kalshi entry held in the column but refused by the blend (CU-1R shape)."""
    return stamp_source_reading(
        {},
        "kalshi",
        value,
        eligibility=ineligible_record(rule="cu1r_contaminated_leg"),
    )["kalshi"]


# ---------------------------------------------------------------------------
# 1. Eligibility — a refused market entry is not a price
# ---------------------------------------------------------------------------


def test_the_refused_fixture_is_refused_by_the_blends_own_gate_8522():
    """Strawman guard: the fixture below must be what `_tier1_readings` drops."""
    entry = _refused_kalshi()
    assert is_refused(entry)
    assert compute_aggregate_probability(_row({"kalshi": entry}), "live") is None


def test_a_refused_lone_market_does_not_silence_the_model_8522():
    assert (
        priorless_model_defers_to_market(None, None, {"kalshi": _refused_kalshi()})
        is False
    )


def test_a_refused_market_beside_a_usable_one_still_defers_8522():
    sources = {"kalshi": _refused_kalshi(), "polymarket": 0.71}
    assert priorless_model_defers_to_market(None, None, sources) is True


@pytest.mark.asyncio
async def test_the_espn_writer_keeps_its_model_when_the_only_market_is_refused_8522():
    """Before the fix: deferred, and the row served NO number at all."""
    session, event = _live_row_on_disk(sources={"kalshi": _refused_kalshi()})
    wrote, stats = await _run_writer(session, event)
    row, snaps = _stored_espn(session)

    assert wrote is True
    assert "stat_model_priorless_deferred" not in stats
    assert "stat_model" in row.win_probability_sources
    assert len(snaps) == 1
    assert compute_aggregate_probability(row, row.status) == pytest.approx(
        0.5, abs=0.02
    )


# ---------------------------------------------------------------------------
# 2. Transition — the market arrives after the model already wrote
# ---------------------------------------------------------------------------


def _model_then_market(model_age_seconds):
    now = datetime.now(timezone.utc)
    sources = stamp_source_reading(
        {}, "stat_model", 0.5, now=now - timedelta(seconds=model_age_seconds)
    )
    return stamp_source_reading(sources, "kalshi", KALSHI_JUST_BEFORE, now=now)


def test_why_the_writer_must_retire_a_frozen_reading_8522():
    """MEASURED: a frozen priorless reading keeps the headline for ~16 minutes.

    Declining to write is not enough — the hero ages sources RELATIVE to one
    another, and a 1.0-weight model six minutes older than the 0.8-weight
    market still wins. This pins that fact so the retirement below is not
    mistaken for a belt-and-braces extra.
    """
    for age in (60, MAX_STALENESS + 60):
        row = _row(_model_then_market(model_age_seconds=age))
        assert compute_aggregate_probability(row, "live") == pytest.approx(0.5)


def test_the_retire_helper_drops_only_the_model_8522():
    sources = _model_then_market(model_age_seconds=60)
    retired = retire_priorless_model_reading(sources)
    assert retired == {"kalshi": sources["kalshi"]}
    assert "stat_model" in sources, "the caller's dict is not mutated"
    assert retire_priorless_model_reading({"kalshi": 0.7}) is None
    assert retire_priorless_model_reading(None) is None


@pytest.mark.asyncio
async def test_a_market_arriving_after_the_model_retires_the_frozen_reading_8522():
    """THE GUARD: the next ESPN pass defers AND drops the earlier 50%."""
    sources = _model_then_market(model_age_seconds=60)
    session, event = _live_row_on_disk(sources=sources)
    wrote, stats = await _run_writer(session, event)
    row, snaps = _stored_espn(session)

    assert wrote is False
    assert stats.get("stat_model_priorless_deferred") == 1
    assert stats.get("stat_model_priorless_retired") == 1
    assert row.win_probability_sources == {"kalshi": sources["kalshi"]}
    assert snaps == []
    assert compute_aggregate_probability(row, row.status) == pytest.approx(
        KALSHI_JUST_BEFORE
    )


@pytest.mark.asyncio
async def test_a_deferral_with_nothing_to_retire_writes_nothing_8522():
    """No stat_model key ⇒ no write and no retire count: the pass does not
    rewrite the column every cycle."""
    kalshi = {"kalshi": {"value": KALSHI_JUST_BEFORE, "updated_at": STAMP}}
    session, event = _live_row_on_disk(sources=kalshi)
    wrote, stats = await _run_writer(session, event)
    row, _ = _stored_espn(session)

    assert wrote is False
    assert "stat_model_priorless_retired" not in stats
    assert row.win_probability_sources == kalshi


# ---------------------------------------------------------------------------
# 3. The odds-poll writer, executed
# ---------------------------------------------------------------------------

NHL = "icehockey_nhl"


async def _run_poll(
    *, sources, opening_home_probability=None, opening_home_spread=None
):
    """Seed one live, ESPN-less NHL row at 0–0; run the REAL ``_poll_all_odds``."""
    from app.models.models import (
        Base,
        Event,
        ScoreSnapshot,
        Sport,
        Team,
        WinProbSnapshot,
    )
    import app.tasks.odds_polling as odds_polling

    engine = _engine()
    Base.metadata.create_all(
        engine,
        tables=[
            Sport.__table__,
            Team.__table__,
            Event.__table__,
            ScoreSnapshot.__table__,
            WinProbSnapshot.__table__,
        ],
    )
    session = Session(engine, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    commence = now - timedelta(minutes=2)

    sport = Sport(key=NHL, name="NHL", active=True)
    session.add(sport)
    session.flush()
    row = Event(
        sport_id=sport.id,
        external_id="odds-api-ducks-sharks",
        espn_id=None,
        home_team_name="San Jose Sharks",
        away_team_name="Anaheim Ducks",
        commence_time=commence,
        status="live",
        home_score=0,
        away_score=0,
        opening_home_probability=opening_home_probability,
        opening_home_spread=opening_home_spread,
        win_probability_sources=sources,
    )
    session.add(row)
    session.commit()
    event_id = row.id

    service = MagicMock()
    service.get_odds = AsyncMock(return_value=[])
    service.get_scores = AsyncMock(
        return_value=[
            _score_record(
                external_id="odds-api-ducks-sharks",
                commence=commence,
                home_team="San Jose Sharks",
                away_team="Anaheim Ducks",
                home=0,
                away=0,
                completed=False,
            )
        ]
    )
    service.close = AsyncMock()
    service.last_requests_remaining = None
    service.last_requests_used = None

    class _Ctx:
        async def __aenter__(self_inner):
            return _PollShim(session)

        async def __aexit__(self_inner, *_exc):
            session.commit()
            return False

    with patch.object(
        odds_polling, "check_quota_guard", return_value=(True, "ok")
    ), patch.object(odds_polling, "OddsAPIService", return_value=service), patch.object(
        odds_polling,
        "get_redis_client",
        return_value=_FakeRedis(now.timestamp() - 100_000),
    ), patch.object(
        odds_polling, "get_task_session", return_value=_Ctx()
    ), patch.object(
        odds_polling,
        "detect_and_close_stale_events",
        AsyncMock(return_value={"closed": 0, "suspended": 0}),
    ), patch.object(
        odds_polling, "update_poll_state", MagicMock()
    ), patch(
        "app.tasks.excitement_index.update_live_ei",
        AsyncMock(return_value=0),
    ):
        result = await odds_polling._poll_all_odds()

    session.close()
    return result, engine, event_id, service


def _stored_poll(engine, event_id):
    """Through a NEW session: the writer is Core SQL the identity map never sees."""
    from app.models.models import Event, WinProbSnapshot

    with Session(engine) as fresh:
        row = fresh.execute(select(Event).where(Event.id == event_id)).scalar_one()
        snaps = (
            fresh.execute(
                select(WinProbSnapshot).where(
                    WinProbSnapshot.event_id == event_id,
                    WinProbSnapshot.source == "stat_model",
                )
            )
            .scalars()
            .all()
        )
        return dict(row.win_probability_sources or {}), len(snaps)


@pytest.mark.asyncio
async def test_poll_control_a_game_with_no_market_gets_its_model_8522():
    """POSITIVE CONTROL: the rig reaches the writer and the writer writes."""
    result, engine, event_id, service = await _run_poll(sources={})
    sources, snaps = _stored_poll(engine, event_id)

    assert service.get_scores.await_count >= 1, "the pass never fetched scores"
    assert result["stat_model_from_poll"] == 1
    assert result["stat_model_priorless_deferred"] == 0
    assert sources["stat_model"]["value"] == pytest.approx(0.5, abs=0.02)
    assert snaps == 1


@pytest.mark.asyncio
async def test_poll_the_specimen_writes_no_coin_flip_beside_kalshi_8522():
    """THE GUARD for the second writer: no prior, Kalshi on the row."""
    kalshi = {"kalshi": {"value": KALSHI_JUST_BEFORE, "updated_at": STAMP}}
    result, engine, event_id, _ = await _run_poll(sources=kalshi)
    sources, snaps = _stored_poll(engine, event_id)

    assert result["stat_model_priorless_deferred"] == 1
    assert result["stat_model_priorless_retired"] == 0
    assert result["stat_model_from_poll"] == 0
    assert "stat_model" not in sources
    assert sources["kalshi"] == kalshi["kalshi"]
    assert snaps == 0


@pytest.mark.asyncio
async def test_poll_a_model_with_a_prior_still_votes_beside_kalshi_8522():
    kalshi = {"kalshi": {"value": KALSHI_JUST_BEFORE, "updated_at": STAMP}}
    result, engine, event_id, _ = await _run_poll(
        sources=kalshi, opening_home_probability=0.74
    )
    sources, snaps = _stored_poll(engine, event_id)

    assert result["stat_model_priorless_deferred"] == 0
    assert result["stat_model_from_poll"] == 1
    assert sources["stat_model"]["value"] > 0.6
    assert snaps == 1


@pytest.mark.asyncio
async def test_poll_a_refused_lone_market_does_not_silence_the_model_8522():
    result, engine, event_id, _ = await _run_poll(sources={"kalshi": _refused_kalshi()})
    sources, snaps = _stored_poll(engine, event_id)

    assert result["stat_model_priorless_deferred"] == 0
    assert result["stat_model_from_poll"] == 1
    assert "stat_model" in sources
    assert snaps == 1


@pytest.mark.asyncio
async def test_poll_a_market_arriving_after_the_model_retires_the_frozen_reading_8522():
    sources = _model_then_market(model_age_seconds=60)
    result, engine, event_id, _ = await _run_poll(sources=sources)
    stored, snaps = _stored_poll(engine, event_id)

    assert result["stat_model_priorless_deferred"] == 1
    assert result["stat_model_priorless_retired"] == 1
    assert stored == {"kalshi": sources["kalshi"]}
    assert snaps == 0
