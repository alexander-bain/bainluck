"""#10960 — the repair moves a Kalshi MLB game question onto the game its
ticker names, and only when ESPN's own board vouches for that game.

Specimens are production rows read 2026-10-12 (ids kept so a reader can
re-read them); the ESPN boards are the ones read the same hour.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
from datetime import date, datetime, timezone

import pytest

_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts", "repair_10960_mlb_markets_on_another_game.py",
)
_spec = importlib.util.spec_from_file_location("repair_10960", _PATH)
rp = importlib.util.module_from_spec(_spec)
sys.modules["repair_10960"] = rp  # dataclasses resolve their module by name
_spec.loader.exec_module(rp)

UTC = timezone.utc

ATL, SD, SEA, PHI, TB, LAD = 11626, 10739, 10743, 10737, 10741, 10707


def _t(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=UTC)


def market(mid, ticker, event_id, start, home, away):
    return rp.Market(mid, ticker, f"{ticker} name", event_id, _t(start), home, away)


def cand(event_id, start, home, away, espn_id, status="completed"):
    return rp.Candidate(event_id, _t(start), home, away, espn_id, status)


def board(*entries):
    return {e[0]: rp.BoardEntry(e[0], _t(e[1]), e[2]) for e in entries}


# KXMLBTEAMTOTAL-26JUN222210ATLSD = Jun 22 22:10 ET = Jun 23 02:10Z. It sat on
# 15165211, Padres v Braves on JULY 22. 14956089 is the ticker's own game.
ATL_SD = market(53104746, "KXMLBTEAMTOTAL-26JUN222210ATLSD", 15165211,
                "2026-07-22T23:15:00", ATL, SD)
ATL_SD_GAME = cand(14956089, "2026-06-23T02:10:00", SD, ATL, "401815865")
JUN22 = {date(2026, 6, 22): board(("401815865", "2026-06-23T02:10:00", "STATUS_FINAL"))}


class TestTheShip:
    def test_a_question_on_another_game_moves_to_the_game_its_ticker_names(self):
        plan = rp.plan_moves([ATL_SD], {ATL_SD.market_id: [ATL_SD_GAME]}, JUN22)
        assert [(m["market_id"], m["from_event_id"], m["to_event_id"]) for m in plan.moves] == [
            (53104746, 15165211, 14956089)
        ]
        assert plan.moves[0]["espn_id"] == "401815865"
        assert plan.kept == []

    def test_the_ticker_start_is_read_as_eastern(self):
        # 22:10 ET in June is 02:10Z the NEXT day; read as UTC it would be 4h off
        # and the true game would fall outside the window.
        assert rp.ticker_start(ATL_SD.external_id) == _t("2026-06-23T02:10:00")
        # ESPN's board is keyed by the Eastern date, not the UTC one.
        assert rp.eastern_date(rp.ticker_start(ATL_SD.external_id)) == date(2026, 6, 22)


class TestWhatIsNeverMoved:
    def test_a_market_inside_the_matchers_window_is_not_examined(self):
        on_its_game = market(1, "KXMLBTEAMTOTAL-26JUN222210ATLSD", 14956089,
                             "2026-06-23T03:00:00", SD, ATL)
        plan = rp.plan_moves([on_its_game], {1: [ATL_SD_GAME]}, JUN22)
        assert plan.moves == [] and plan.kept == [] and plan.in_window == 1

    def test_a_changed_start_with_no_row_at_the_ticker_time_stays(self):
        # PHI@ATL wild card: ticketed 14:00 ET, played 20:00 ET — one game, one
        # ESPN id, correctly linked although 6h from the ticker.
        m = market(64118686, "KXMLBTEAMTOTAL-26OCT011400PHIATL", 15322407,
                   "2026-10-02T00:00:00", ATL, PHI)
        plan = rp.plan_moves([m], {}, {})
        assert plan.moves == []
        assert [k["verdict"] for k in plan.kept] == [rp.NO_CANDIDATE]

    def test_a_doubleheader_with_two_rows_in_the_window_is_ambiguous(self):
        other = cand(99, "2026-06-23T04:30:00", SD, ATL, "401815866")
        plan = rp.plan_moves([ATL_SD], {ATL_SD.market_id: [ATL_SD_GAME, other]}, JUN22)
        assert plan.moves == []
        assert plan.kept[0]["verdict"] == rp.AMBIGUOUS
        assert plan.kept[0]["candidates"] == [99, 14956089]

    def test_a_row_for_other_clubs_is_never_a_target(self):
        stranger = cand(14956089, "2026-06-23T02:10:00", SD, LAD, "401815865")
        plan = rp.plan_moves([ATL_SD], {ATL_SD.market_id: [stranger]}, JUN22)
        assert plan.moves == [] and plan.kept[0]["verdict"] == rp.NO_CANDIDATE

    def test_a_row_outside_the_window_is_never_a_target(self):
        late = cand(14956089, "2026-06-23T05:40:00", SD, ATL, "401815865")
        plan = rp.plan_moves([ATL_SD], {ATL_SD.market_id: [late]}, JUN22)
        assert plan.moves == [] and plan.kept[0]["verdict"] == rp.NO_CANDIDATE

    def test_a_retired_row_is_reported_not_linked(self):
        # KXMLBTEAMTOTAL-26MAY052140ATLSEA: its game 14626103 (ESPN 401815225,
        # final 3-2) is status 'merged'. A link onto a hidden row is not a fix.
        m = market(54069118, "KXMLBTEAMTOTAL-26MAY052140ATLSEA", 14626493,
                   "2026-05-06T20:10:00", SEA, ATL)
        merged = cand(14626103, "2026-05-06T01:40:00", SEA, ATL, "401815225", "merged")
        b = {date(2026, 5, 5): board(("401815225", "2026-05-06T01:40:00", "STATUS_FINAL"))}
        plan = rp.plan_moves([m], {m.market_id: [merged]}, b)
        assert plan.moves == []
        assert plan.kept[0]["verdict"] == rp.RETIRED_TARGET
        assert plan.kept[0]["target_event_id"] == 14626103

    def test_a_target_without_an_espn_id_is_not_anchored(self):
        bare = cand(14956089, "2026-06-23T02:10:00", SD, ATL, None)
        plan = rp.plan_moves([ATL_SD], {ATL_SD.market_id: [bare]}, JUN22)
        assert plan.moves == [] and plan.kept[0]["verdict"] == rp.NO_ESPN_ID


class TestEspnIsTheAnchor:
    def test_a_dark_board_moves_nothing(self):
        dark = {date(2026, 6, 22): None}
        plan = rp.plan_moves([ATL_SD], {ATL_SD.market_id: [ATL_SD_GAME]}, dark)
        assert plan.moves == [] and plan.kept[0]["verdict"] == rp.ESPN_DARK

    def test_an_unread_day_moves_nothing(self):
        plan = rp.plan_moves([ATL_SD], {ATL_SD.market_id: [ATL_SD_GAME]}, {})
        assert plan.moves == [] and plan.kept[0]["verdict"] == rp.ESPN_DARK

    def test_a_board_without_the_targets_id_moves_nothing(self):
        b = {date(2026, 6, 22): board(("401815999", "2026-06-23T02:10:00", "STATUS_FINAL"))}
        plan = rp.plan_moves([ATL_SD], {ATL_SD.market_id: [ATL_SD_GAME]}, b)
        assert plan.moves == [] and plan.kept[0]["verdict"] == rp.ESPN_DISAGREES

    def test_espn_placing_the_id_at_another_time_moves_nothing(self):
        b = {date(2026, 6, 22): board(("401815865", "2026-06-23T19:10:00", "STATUS_FINAL"))}
        plan = rp.plan_moves([ATL_SD], {ATL_SD.market_id: [ATL_SD_GAME]}, b)
        assert plan.moves == [] and plan.kept[0]["verdict"] == rp.ESPN_DISAGREES

    def test_a_postponed_game_on_its_original_day_is_a_target(self):
        # KXMLBTEAMTOTAL-26MAY051945MILSTL: postponed; Kalshi settled it scalar the
        # same day. ESPN keeps 401815223 on May 5; our 15290177 carries it.
        mil, stl = 10735, 10740
        m = market(54069190, "KXMLBTEAMTOTAL-26MAY051945MILSTL", 14626206,
                   "2026-05-06T17:15:00", stl, mil)
        ppd = cand(15290177, "2026-05-05T23:45:00", stl, mil, "401815223", "suspended")
        b = {date(2026, 5, 5): board(("401815223", "2026-05-05T23:45:00", "STATUS_POSTPONED"))}
        plan = rp.plan_moves([m], {m.market_id: [ppd]}, b)
        assert [x["to_event_id"] for x in plan.moves] == [15290177]

    def test_an_empty_espn_answer_is_dark_not_a_disagreement(self):
        assert rp.board_from_espn(None) is None
        assert rp.board_from_espn({}) is None
        assert rp.board_from_espn({"events": []}) is None
        got = rp.board_from_espn({"events": [
            {"id": 401815865, "date": "2026-06-23T02:10Z",
             "status": {"type": {"name": "STATUS_FINAL"}}},
            {"id": "bad"},
        ]})
        assert list(got) == ["401815865"]
        assert got["401815865"].start == _t("2026-06-23T02:10:00")


class TestRails:
    def test_series_bounds_bump_the_last_letter(self):
        assert rp.series_bounds("KXMLBTEAMTOTAL") == ("KXMLBTEAMTOTAL", "KXMLBTEAMTOTAM")
        assert rp.series_bounds("KXMLB") == ("KXMLB", "KXMLC")
        with pytest.raises(rp.Refused):
            rp.series_bounds("KXMLB-")

    def test_refuses_off_production(self):
        with pytest.raises(rp.Refused):
            rp.refuse_unless_production({"HEROKU_APP_NAME": "bainluck-staging"})
        with pytest.raises(rp.Refused):
            rp.refuse_unless_production({})
        rp.refuse_unless_production({"HEROKU_APP_NAME": "bainluck"})


# ── The apply path, on a fake session that answers by statement ──────────────


class _Rows(list):
    def all(self):
        return list(self)

    def scalar(self):
        return self[0][0] if self else None


class _Result:
    def __init__(self, rows=(), rowcount=0):
        self._rows = _Rows(rows)
        self.rowcount = rowcount

    def __iter__(self):
        return iter(self._rows)

    def all(self):
        return self._rows.all()

    def scalar(self):
        return self._rows.scalar()


class _Row:
    def __init__(self, **kw):
        self.__dict__.update(kw)

    def __getitem__(self, i):
        return list(self.__dict__.values())[i]


class FakeSession:
    """Holds ``futures_markets.event_id`` and a backup bank; nothing else."""

    def __init__(self, links, *, bank_short=False):
        self.links = dict(links)
        self.bank: dict[int, tuple[int, int]] = {}
        self.bank_short = bank_short
        self.updates = 0

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        params = params or {}
        if "FROM futures_markets fm\n  JOIN events e" in sql:
            return _Result([_Row(id=53104746, external_id=ATL_SD.external_id, name="n",
                                 event_id=self.links[53104746],
                                 commence_time=ATL_SD.event_start,
                                 home_team_id=ATL, away_team_id=SD)])
        if "FROM unnest" in sql and "JOIN events e" in sql:
            return _Result([_Row(market_id=53104746, id=14956089,
                                 commence_time=ATL_SD_GAME.start, home_team_id=SD,
                                 away_team_id=ATL, espn_id="401815865",
                                 status="completed")])
        if sql.startswith("CREATE TABLE"):
            return _Result()
        if sql.startswith(f"INSERT INTO {rp.BACKUP_TABLE}"):
            if not self.bank_short:
                for i, b, a in zip(params["ids"], params["befores"], params["afters"]):
                    self.bank.setdefault(i, (b, a))
            return _Result()
        if sql.startswith("SELECT market_id, event_id_before"):
            return _Result([_Row(market_id=k, event_id_before=v[0], event_id_after=v[1])
                            for k, v in self.bank.items()])
        if sql.startswith("UPDATE futures_markets"):
            # The fake can only honour a compare-and-swap the SQL actually asks for.
            assert "AND event_id = :old" in sql, "the move must compare-and-swap"
            if self.links.get(params["id"]) == params["old"]:
                self.links[params["id"]] = params["new"]
                self.updates += 1
                return _Result(rowcount=1)
            return _Result(rowcount=0)
        if "SELECT count(*) FROM futures_markets" in sql:
            n = sum(1 for i, e in zip(params["ids"], params["evs"]) if self.links.get(i) == e)
            return _Result([(n,)])
        raise AssertionError(f"unexpected statement: {sql[:80]}")

    async def commit(self):
        pass

    async def rollback(self):
        pass


async def _boards(days):
    assert days == {date(2026, 6, 22)}
    return JUN22


@pytest.fixture
def no_receipts(monkeypatch):
    seen = []

    async def fake(rows, **kw):
        seen.append((kw["previous_event_id"], kw["new_event_id"], kw["actor"], kw["phase"],
                     [r["id"] for r in rows]))
        return len(rows)

    import app.utils.match_receipts as mr
    monkeypatch.setattr(mr, "record_link_change_receipts", fake)
    return seen


def _run(session, **kw):
    return asyncio.run(rp.run(session, series_list=["KXMLBTEAMTOTAL"],
                              boards_reader=_boards, **kw))


class TestApply:
    def test_a_dry_run_writes_nothing(self):
        s = FakeSession({53104746: 15165211})
        out = _run(s, apply=False, max_moves=10)
        assert out["counts"][rp.MOVE] == 1
        assert s.links[53104746] == 15165211 and s.bank == {} and s.updates == 0

    def test_apply_banks_moves_receipts_and_reads_back(self, no_receipts):
        s = FakeSession({53104746: 15165211})
        out = _run(s, apply=True, max_moves=10)
        assert s.bank == {53104746: (15165211, 14956089)}
        assert s.links[53104746] == 14956089
        assert out["written"] == 1 and out["readback_on_target"] == 1
        assert no_receipts == [(15165211, 14956089, "admin_repair", "repair_10960", [53104746])]

    def test_a_plan_above_the_ceiling_refuses_before_any_write(self):
        s = FakeSession({53104746: 15165211})
        with pytest.raises(rp.Refused):
            _run(s, apply=True, max_moves=0)
        assert s.bank == {} and s.updates == 0

    def test_a_short_bank_refuses_before_any_write(self):
        s = FakeSession({53104746: 15165211}, bank_short=True)
        with pytest.raises(rp.Refused):
            _run(s, apply=True, max_moves=10)
        assert s.links[53104746] == 15165211 and s.updates == 0

    def test_a_market_that_moved_under_the_run_is_left_alone(self, no_receipts, monkeypatch):
        s = FakeSession({53104746: 15165211})
        real = s.execute

        async def racing(stmt, params=None):
            if str(stmt).startswith("UPDATE futures_markets"):
                s.links[53104746] = 777  # a matcher pass moved it first
            return await real(stmt, params)

        monkeypatch.setattr(s, "execute", racing)
        out = _run(s, apply=True, max_moves=10)
        assert s.links[53104746] == 777
        assert out["written"] == 0 and out["changed_under_run"] == [53104746]
        assert no_receipts == []


class _RestoreSession(FakeSession):
    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if sql.startswith("SELECT to_regclass"):
            return _Result([("bak",)] if self.bank else [(None,)])
        if sql.startswith("SELECT b.market_id"):
            return _Result([
                _Row(market_id=k, event_id_before=v[0], event_id_after=v[1],
                     event_id=self.links.get(k), external_id="x", name="n")
                for k, v in sorted(self.bank.items())
            ])
        return await super().execute(stmt, params)


class TestRestore:
    def test_restore_moves_back_only_what_is_still_where_the_repair_put_it(self, no_receipts):
        s = _RestoreSession({1: 20, 2: 999})
        s.bank = {1: (10, 20), 2: (11, 21)}  # market 2 has moved again since
        out = asyncio.run(rp.restore(s))
        assert s.links == {1: 10, 2: 999}
        assert out["written"] == 1 and out["readback_on_before"] == 1
        assert out["not_on_after_left_alone"] == [2]
        assert no_receipts == [(20, 10, "admin_repair", "repair_10960", [1])]

    def test_restore_without_a_bank_refuses(self):
        with pytest.raises(rp.Refused):
            asyncio.run(rp.restore(_RestoreSession({})))
