"""#7993 — a bout The Odds API re-minted under a new id stops printing twice.

Specimen (production, 2026-09-25): Marvin Vettori vs Ismail Naurdiev, UFC 332.
`15318421` carries id `57b0…2749` dated 2026-10-11 00:00Z (minted 09-24), and
`15318685` carries `4a46…751d` dated 2026-10-04 00:00Z (minted 09-25). The
provider's `/events` listing at 16:30Z held only the second. `/search?q=Vettori`
printed the first as an "Oct 10 5:00 PM" card.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import app.tasks.odds_api_remint_sweep as sweep
from app.utils.odds_api_remints import (
    RemintRow,
    matchup_key,
    plan_remint_tags,
    sports_needing_listing,
)

NOW = datetime(2026, 9, 25, 16, 30, tzinfo=timezone.utc)
MMA = "mma_mixed_martial_arts"

GHOST_X = "57b0b29bb4c565d85e62ebcc023f2749"
CANON_X = "4a469d6a287808bf75aa8a246197f51d"


def _row(eid, xid, home, away, *, sport=MMA, at=None, result=False, dup=None,
         prices=frozenset()):
    return RemintRow(
        event_id=eid,
        sport_key=sport,
        external_id=xid,
        home_team_name=home,
        away_team_name=away,
        commence_time=at or NOW + timedelta(days=8),
        has_result=result,
        duplicate_of=dup,
        price_sources=frozenset(prices),
    )


def _specimen():
    return [
        _row(15318421, GHOST_X, "Marvin Vettori", "Ismail Naurdiev",
             at=datetime(2026, 10, 11, tzinfo=timezone.utc)),
        _row(15318685, CANON_X, "Marvin Vettori", "Ismail Naurdiev",
             at=datetime(2026, 10, 4, tzinfo=timezone.utc)),
    ]


# ════════════════════════════════════════════════════════════════════════════
# The judgement
# ════════════════════════════════════════════════════════════════════════════


class TestThePlanner:
    def test_the_specimen_folds_onto_the_row_the_provider_lists(self):
        plan = plan_remint_tags(_specimen(), {MMA: frozenset({CANON_X})}, NOW)
        assert [(t.ghost_id, t.canonical_id) for t in plan.tags] == [
            (15318421, 15318685)
        ]
        assert plan.refusals == []

    def test_the_direction_comes_from_the_listing_not_from_id_order(self):
        # Swap which id the provider lists: the OLDER row becomes canonical.
        plan = plan_remint_tags(_specimen(), {MMA: frozenset({GHOST_X})}, NOW)
        assert [(t.ghost_id, t.canonical_id) for t in plan.tags] == [
            (15318685, 15318421)
        ]

    def test_a_pair_the_provider_lists_both_of_is_two_events(self):
        plan = plan_remint_tags(
            _specimen(), {MMA: frozenset({GHOST_X, CANON_X})}, NOW
        )
        assert plan.tags == []
        assert "separate events" in plan.refusals[0]

    def test_a_pair_the_provider_lists_neither_of_is_refused(self):
        # Shevchenko–Silva on 09-25: both rows dead, no successor to choose.
        plan = plan_remint_tags(_specimen(), {MMA: frozenset({"f" * 32})}, NOW)
        assert plan.tags == []
        assert "lists none" in plan.refusals[0]

    def test_an_unread_listing_is_not_an_empty_one(self):
        plan = plan_remint_tags(_specimen(), {}, NOW)
        assert plan.tags == []
        assert "listing unread" in plan.refusals[0]
        assert plan.groups_examined == 1

    @pytest.mark.parametrize(
        "sport",
        ["americanfootball_nfl", "baseball_mlb", "basketball_nba", "soccer_epl"],
    )
    def test_team_sports_are_never_judged(self, sport):
        # Home-and-away and doubleheaders are routine; "not listed yet" proves
        # nothing about a far-future team fixture.
        rows = [
            _row(1, GHOST_X, "Chicago Bears", "Green Bay Packers", sport=sport),
            _row(2, CANON_X, "Green Bay Packers", "Chicago Bears", sport=sport),
        ]
        plan = plan_remint_tags(rows, {sport: frozenset({CANON_X})}, NOW)
        assert plan.tags == [] and plan.groups_examined == 0
        assert sports_needing_listing(rows, NOW) == set()

    def test_boxing_is_judged(self):
        rows = [
            _row(13977632, "30ef422e4011f94920c5ab5ebf5323c7", "Anthony Joshua",
                 "Tyson Fury", sport="boxing_boxing"),
            _row(15318306, "0b629a238b2f333babea078766b9a4bb", "Anthony Joshua",
                 "Tyson Fury", sport="boxing_boxing"),
        ]
        plan = plan_remint_tags(
            rows, {"boxing_boxing": frozenset({"0b629a238b2f333babea078766b9a4bb"})},
            NOW,
        )
        assert [(t.ghost_id, t.canonical_id) for t in plan.tags] == [
            (13977632, 15318306)
        ]

    def test_orientation_does_not_split_a_pair(self):
        rows = _specimen()
        rows[0] = _row(15318421, GHOST_X, "Ismail Naurdiev", "Marvin Vettori")
        plan = plan_remint_tags(rows, {MMA: frozenset({CANON_X})}, NOW)
        assert len(plan.tags) == 1

    def test_a_row_holding_a_result_is_never_hidden(self):
        rows = _specimen()
        rows[0] = _row(15318421, GHOST_X, "Marvin Vettori", "Ismail Naurdiev",
                       result=True)
        assert plan_remint_tags(rows, {MMA: frozenset({CANON_X})}, NOW).tags == []

    def test_a_started_bout_is_out_of_scope(self):
        # A finished bout drops off the listing normally, so its absence is
        # not evidence of anything.
        rows = _specimen()
        rows[0] = _row(15318421, GHOST_X, "Marvin Vettori", "Ismail Naurdiev",
                       at=NOW - timedelta(minutes=1))
        assert plan_remint_tags(rows, {MMA: frozenset({CANON_X})}, NOW).tags == []

    def test_a_row_with_another_providers_id_is_out_of_scope(self):
        rows = _specimen()
        rows[0] = _row(15318421, "pm_kalshi_KXUFCFIGHT-26OCT03VETNAU",
                       "Marvin Vettori", "Ismail Naurdiev")
        assert plan_remint_tags(rows, {MMA: frozenset({CANON_X})}, NOW).tags == []

    def test_a_degenerate_or_unreadable_matchup_names_nobody(self):
        assert matchup_key(_row(1, GHOST_X, "Silva", "Silva")) is None
        assert matchup_key(_row(1, GHOST_X, "王聪", "李明")) is None
        assert matchup_key(_row(1, GHOST_X, None, "Silva")) is None

    def test_an_already_labelled_ghost_is_counted_not_rewritten(self):
        rows = _specimen()
        rows[0] = _row(15318421, GHOST_X, "Marvin Vettori", "Ismail Naurdiev",
                       dup=15318685)
        plan = plan_remint_tags(rows, {MMA: frozenset({CANON_X})}, NOW)
        assert plan.tags == [] and plan.already_tagged == 1

    def test_a_ghost_labelled_onto_a_different_row_is_left_alone(self):
        rows = _specimen()
        rows[0] = _row(15318421, GHOST_X, "Marvin Vettori", "Ismail Naurdiev",
                       dup=999)
        plan = plan_remint_tags(rows, {MMA: frozenset({CANON_X})}, NOW)
        assert plan.tags == [] and "duplicate-of:999" in plan.refusals[0]

    def test_a_canonical_that_is_itself_a_duplicate_is_refused(self):
        rows = _specimen()
        rows[1] = _row(15318685, CANON_X, "Marvin Vettori", "Ismail Naurdiev",
                       dup=777)
        plan = plan_remint_tags(rows, {MMA: frozenset({CANON_X})}, NOW)
        assert plan.tags == [] and "itself tagged" in plan.refusals[0]

    def test_a_ghost_holding_a_price_the_canonical_lacks_is_refused(self):
        # 1292 -> 1298 on 2026-09-25: the hero fold gap-fills, so the dropped
        # id's January `betting` 0.7258 would have become 1298's number.
        rows = _specimen()
        rows[0] = _row(15318421, GHOST_X, "Marvin Vettori", "Ismail Naurdiev",
                       prices={"betting"})
        plan = plan_remint_tags(rows, {MMA: frozenset({CANON_X})}, NOW)
        assert plan.tags == [] and "['betting']" in plan.refusals[0]

    def test_a_ghost_whose_prices_the_canonical_also_holds_is_tagged(self):
        # 13977632 -> 15318306 (Joshua–Fury): the canonical's own reading wins
        # the gap-fill, so the ghost's never reaches the hero.
        rows = _specimen()
        rows[0] = _row(15318421, GHOST_X, "Marvin Vettori", "Ismail Naurdiev",
                       prices={"betting"})
        rows[1] = _row(15318685, CANON_X, "Marvin Vettori", "Ismail Naurdiev",
                       prices={"betting", "kalshi"})
        assert len(plan_remint_tags(rows, {MMA: frozenset({CANON_X})}, NOW).tags) == 1

    def test_a_single_row_asks_the_provider_nothing(self):
        assert sports_needing_listing(_specimen()[:1], NOW) == set()
        assert sports_needing_listing(_specimen(), NOW) == {MMA}


# ════════════════════════════════════════════════════════════════════════════
# The task, end to end against a fake session and a fake provider
# ════════════════════════════════════════════════════════════════════════════


def _db_row(eid, xid, home, away, *, at, tags="[]", sport=MMA, score=None,
            sources="{}"):
    return SimpleNamespace(
        id=eid, sport_key=sport, external_id=xid, home_team_name=home,
        away_team_name=away, commence_time=at, home_score=score,
        away_score=None, completed_at=None, tags_text=tags, sources_text=sources,
    )


def _db_specimen(ghost_tags="[]"):
    future = datetime.now(timezone.utc) + timedelta(days=8)
    return [
        _db_row(15318421, GHOST_X, "Marvin Vettori", "Ismail Naurdiev",
                at=future + timedelta(days=7), tags=ghost_tags),
        _db_row(15318685, CANON_X, "Marvin Vettori", "Ismail Naurdiev",
                at=future),
    ]


class _Result:
    def __init__(self, rows=(), rowcount=0):
        self._rows, self.rowcount = list(rows), rowcount

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, rows, *, read_raises=False, write_silently_noops=False):
        self.rows = list(rows)
        self.read_raises = read_raises
        self.write_silently_noops = write_silently_noops
        self.calls: list[str] = []
        self.tagged: set[int] = set()
        self.banked: list[tuple] = []
        self.population_params: dict = {}

    async def execute(self, clause, params=None):
        sql = " ".join(str(clause).split())
        params = params or {}
        if "FROM events e" in sql:
            self.calls.append("population")
            self.population_params = params
            if self.read_raises:
                raise RuntimeError("connection reset by peer")
            return _Result(self.rows)
        if sql.startswith("CREATE TABLE IF NOT EXISTS"):
            assert sweep.BAK_TABLE in sql
            self.calls.append("create_backup_table")
            return _Result()
        if sql.startswith("INSERT INTO bak_"):
            self.calls.append("bank")
            self.banked.append((params["eid"], params["cid"], params["old"]))
            return _Result(rowcount=1)
        if sql.startswith("UPDATE events"):
            self.calls.append("append_tag")
            assert f"duplicate-of:{15318685}" in params["tag_array"]
            if not self.write_silently_noops:
                self.tagged.add(params["eid"])
            return _Result(rowcount=0 if self.write_silently_noops else 1)
        if sql.startswith("SELECT id FROM events"):
            self.calls.append("verify")
            return _Result(
                [SimpleNamespace(id=i) for i in params["ids"] if i in self.tagged]
            )
        raise AssertionError(f"unexpected SQL: {sql[:120]}")

    async def commit(self):
        return None

    async def rollback(self):
        return None


class _FakeProvider:
    def __init__(self, listing=None, raises=None):
        self.listing = listing or {}
        self.raises = raises or set()
        self.asked: list[str] = []

    async def get_events(self, sport_key):
        self.asked.append(sport_key)
        if sport_key in self.raises:
            raise RuntimeError("503 Service Unavailable")
        return [{"id": i} for i in self.listing.get(sport_key, ())]


def _run(rows, monkeypatch, *, provider=None, apply=True, **kw):
    session = _FakeSession(rows, **kw)

    @contextlib.asynccontextmanager
    async def _fake_session():
        yield session

    import app.tasks.base as base
    import app.tasks.tennis_twin_sweep as tennis

    async def _no_sleep(_s):
        return None

    monkeypatch.setattr(base, "get_task_session", _fake_session)
    monkeypatch.setattr(tennis.asyncio, "sleep", _no_sleep)
    provider = provider or _FakeProvider({MMA: [CANON_X]})
    out = asyncio.run(sweep.run_odds_api_remint_sweep(apply=apply, service=provider))
    return out, session, provider


class TestPriceSources:
    @pytest.mark.parametrize(
        "text, expected",
        [
            ('{"betting": 0.7258}', {"betting"}),  # the bare-float shape
            ('{"betting": {"value": 0.38, "updated_at": "2026-09-24T12:05:59Z"}}',
             {"betting"}),
            ('{"betting": null}', set()),  # present key, no reading
            ('{"betting_book_count": 7}', set()),  # not a weighted source
            ("not json", set()),
            ("[]", set()),
        ],
    )
    def test_only_weighted_readings_count(self, text, expected):
        assert sweep.price_sources(text) == frozenset(expected)


class TestTheTask:
    def test_the_specimen_is_tagged_after_its_prior_tags_are_banked(self, monkeypatch):
        out, session, provider = _run(_db_specimen(), monkeypatch)
        assert out["terminal"] == "complete" and out["written"] == 1
        assert session.tagged == {15318421}
        assert session.banked == [(15318421, 15318685, "[]")]
        assert session.calls.index("bank") < session.calls.index("append_tag")
        assert provider.asked == [MMA]
        assert out["undo"].endswith("restore_7993_odds_api_remint_tags.py --apply")

    def test_the_population_read_binds_its_patterns(self, monkeypatch):
        _, session, _ = _run(_db_specimen(), monkeypatch)
        assert session.population_params == {
            "mma": "mma_%", "boxing": "boxing_%", "id_re": "^[0-9a-f]{32}$",
        }

    def test_an_already_tagged_specimen_is_a_green_no_write(self, monkeypatch):
        out, session, _ = _run(
            _db_specimen('["provenance:duplicate-of:15318685"]'), monkeypatch
        )
        assert out["terminal"] == "complete" and out["written"] == 0
        assert out["already_tagged"] == 1
        assert "append_tag" not in session.calls

    def test_a_ghost_carrying_a_lone_price_is_not_tagged(self, monkeypatch):
        rows = _db_specimen()
        rows[0].sources_text = '{"betting": 0.7258}'
        out, session, _ = _run(rows, monkeypatch)
        assert out["terminal"] == "complete" and out["written"] == 0
        assert out["refusals"] == 1 and "append_tag" not in session.calls

    def test_a_quiet_day_asks_the_provider_nothing(self, monkeypatch):
        out, _, provider = _run(_db_specimen()[:1], monkeypatch)
        assert out["terminal"] == "complete" and out["written"] == 0
        assert provider.asked == []

    def test_an_unreadable_listing_is_failed_not_green(self, monkeypatch):
        out, session, _ = _run(
            _db_specimen(), monkeypatch, provider=_FakeProvider(raises={MMA})
        )
        assert out["terminal"] == "failed"
        assert MMA in out["listing_errors"]
        assert "append_tag" not in session.calls

    def test_one_unreadable_listing_among_several_is_partial(self, monkeypatch):
        future = datetime.now(timezone.utc) + timedelta(days=30)
        rows = _db_specimen() + [
            _db_row(1, "a" * 32, "Anthony Joshua", "Tyson Fury",
                    sport="boxing_boxing", at=future),
            _db_row(2, "b" * 32, "Anthony Joshua", "Tyson Fury",
                    sport="boxing_boxing", at=future),
        ]
        out, session, _ = _run(
            rows, monkeypatch,
            provider=_FakeProvider({MMA: [CANON_X]}, raises={"boxing_boxing"}),
        )
        assert out["terminal"] == "partial"
        assert session.tagged == {15318421}

    def test_a_write_that_silently_does_not_land_is_partial(self, monkeypatch):
        out, _, _ = _run(_db_specimen(), monkeypatch, write_silently_noops=True)
        assert out["terminal"] == "partial"
        assert out["still_untagged"] == [15318421]

    def test_a_read_that_raises_is_failed_and_unmeasured(self, monkeypatch):
        out, _, _ = _run(_db_specimen(), monkeypatch, read_raises=True)
        assert out["terminal"] == "failed" and out["measured"] is False

    def test_an_empty_population_is_no_work(self, monkeypatch):
        out, _, _ = _run([], monkeypatch)
        assert out["terminal"] == "no_work"

    def test_a_dry_run_withholds_and_says_so(self, monkeypatch):
        out, session, _ = _run(_db_specimen(), monkeypatch, apply=False)
        assert out["terminal"] == "no_work" and "withheld" in out["reason"]
        assert "append_tag" not in session.calls and "bank" not in session.calls


# ════════════════════════════════════════════════════════════════════════════
# Wiring
# ════════════════════════════════════════════════════════════════════════════


class TestWiring:
    def test_the_beat_entry_applies_hourly_on_the_background_worker(self):
        from app.tasks import celery_app

        entry = celery_app.conf.beat_schedule["odds-api-remint-sweep"]
        assert entry["task"] == "app.tasks.odds_api_remint_sweep"
        assert entry["task"] in celery_app.tasks
        assert entry["kwargs"] == {"apply": True}
        assert entry["options"] == {"queue": "background"}
        assert entry["schedule"].minute == {13}

    def test_it_is_enrolled_in_enforced_tasks(self):
        from app.utils.task_verdict import ENFORCED_TASKS, verdict_for

        assert "odds_api_remint_sweep" in ENFORCED_TASKS
        assert verdict_for(
            "odds_api_remint_sweep", {"terminal": "failed", "measured": False}
        ).verdict != "complete"

    def test_the_undo_reads_the_table_the_sweep_banks_into(self):
        import importlib.util
        from pathlib import Path

        path = Path(__file__).parents[1] / "scripts/restore_7993_odds_api_remint_tags.py"
        spec = importlib.util.spec_from_file_location("restore_7993", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert module.BAK_TABLE == sweep.BAK_TABLE == "bak_7993_odds_api_remint_tags"
