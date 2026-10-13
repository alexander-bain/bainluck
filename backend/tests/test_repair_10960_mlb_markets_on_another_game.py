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


class TestThePlanDigest:
    """The apply binds the plan a person read, not a count of it."""

    def _plan(self):
        return rp.plan_moves([ATL_SD], {ATL_SD.market_id: [ATL_SD_GAME]}, JUN22)

    def test_the_digest_is_order_free_and_binds_the_scope(self):
        a = {"market_id": 1, "to_event_id": 2}
        b = {"market_id": 3, "to_event_id": 4}
        assert rp.plan_digest(["KXMLBTEAMTOTAL"], [a, b]) == rp.plan_digest(
            ["KXMLBTEAMTOTAL"], [b, a])
        # A team-total digest never authorises the all-series plan.
        assert rp.plan_digest(["KXMLBTEAMTOTAL"], [a]) != rp.plan_digest([rp.ALL_SERIES], [a])

    def test_the_digest_binds_the_write_and_its_witness(self):
        assert set(rp.DIGEST_FIELDS) == {
            "market_id", "external_id", "from_event_id", "to_event_id",
            "ticker_start", "target_start", "espn_id", "espn_start", "espn_status",
        }

    @pytest.mark.parametrize("field", rp.DIGEST_FIELDS)
    def test_every_bound_field_changes_the_digest(self, field):
        move = dict(self._plan().moves[0])
        before = rp.plan_digest(["KXMLBTEAMTOTAL"], [move])
        move[field] = "changed"
        assert rp.plan_digest(["KXMLBTEAMTOTAL"], [move]) != before

    def test_a_move_carries_its_espn_witness(self):
        move = self._plan().moves[0]
        assert {k for k in rp.DIGEST_FIELDS if move.get(k) is None} == set()
        assert move["espn_start"] == "2026-06-23T02:10:00+00:00"


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


# A second wrong-game team total, so a batch can miss in the MIDDLE.
# KXMLBTEAMTOTAL-26JUN232210ATLSD = Jun 23 22:10 ET = Jun 24 02:10Z.
ATL_SD_2 = market(53104747, "KXMLBTEAMTOTAL-26JUN232210ATLSD", 15165211,
                  "2026-07-22T23:15:00", ATL, SD)
ATL_SD_GAME_2 = cand(14956090, "2026-06-24T02:10:00", SD, ATL, "401815880")
JUN22_23 = {
    **JUN22,
    date(2026, 6, 23): board(("401815880", "2026-06-24T02:10:00", "STATUS_FINAL")),
}


class FakeSession:
    """``futures_markets.event_id`` plus the backup bank, with transactions.

    Writes are live until ``rollback()`` restores the last committed state, so
    an all-or-nothing claim is tested against a store that can tell the two
    apart. ``external_write`` is another session's COMMITTED write.
    """

    def __init__(self, links, *, markets=(ATL_SD,), cands=None, bank_short=False,
                 retired=(), readback_drop=(), readback_raises=False, commit_fault=None):
        self.links = dict(links)
        self.bank: dict[int, tuple[int, int, bool]] = {}
        self.markets = list(markets)
        self.cands = cands if cands is not None else {ATL_SD.market_id: [ATL_SD_GAME]}
        self.bank_short = bank_short
        self.retired = set(retired)
        self.readback_drop = set(readback_drop)
        self.readback_raises = readback_raises
        # ``(n, lands)``: the n-th commit raises; ``lands`` = the server had
        # committed it and only the answer was lost.
        self.commit_fault = commit_fault
        self.commits = 0
        self.updates = 0
        self.statements: list[str] = []
        self.on_update = None
        self._commit_state()

    def _commit_state(self):
        self._links_c, self._bank_c = dict(self.links), dict(self.bank)

    def external_write(self, mid, event_id):
        self.links[mid] = event_id
        self._links_c[mid] = event_id

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        params = params or {}
        self.statements.append(sql)
        if "FROM futures_markets fm\n  JOIN events e" in sql:
            return _Result([
                _Row(id=m.market_id, external_id=m.external_id, name="n",
                     event_id=self.links[m.market_id], commence_time=m.event_start,
                     home_team_id=m.home_team_id, away_team_id=m.away_team_id)
                for m in self.markets
            ])
        if "FROM unnest" in sql and "JOIN events e" in sql:
            return _Result([
                _Row(market_id=mid, id=c.event_id, commence_time=c.start,
                     home_team_id=c.home_team_id, away_team_id=c.away_team_id,
                     espn_id=c.espn_id, status=c.status)
                for mid in params["mids"] for c in self.cands.get(mid, [])
            ])
        if sql.startswith("CREATE TABLE"):
            assert "applied_at timestamptz" in sql
            return _Result()
        if sql.startswith(f"INSERT INTO {rp.BACKUP_TABLE}"):
            if not self.bank_short:
                for i, b, a in zip(params["ids"], params["befores"], params["afters"]):
                    self.bank.setdefault(i, (b, a, False))
            return _Result()
        if sql.startswith("SELECT market_id, event_id_before"):
            return _Result([_Row(market_id=k, event_id_before=v[0], event_id_after=v[1])
                            for k, v in self.bank.items()])
        if sql.startswith("UPDATE futures_markets"):
            # The fake can only honour guards the SQL actually asks for.
            assert "AND event_id = :old" in sql, "the move must compare-and-swap"
            assert "status NOT IN ('merged', 'voided')" in sql
            if self.on_update:
                self.on_update(params)
            if (self.links.get(params["id"]) == params["old"]
                    and params["new"] not in self.retired):
                self.links[params["id"]] = params["new"]
                self.updates += 1
                return _Result(rowcount=1)
            return _Result(rowcount=0)
        if sql.startswith(f"UPDATE {rp.BACKUP_TABLE}"):
            n = 0
            for i, b, a in zip(params["ids"], params["befores"], params["afters"]):
                if self.bank.get(i, (None, None))[:2] == (b, a):
                    self.bank[i] = (b, a, True)
                    n += 1
            return _Result(rowcount=n)
        if sql.startswith("SELECT fm.id FROM futures_markets"):
            if self.readback_raises:
                raise RuntimeError("read-back connection reset")
            return _Result([(i,) for i, e in zip(params["ids"], params["evs"])
                            if self.links.get(i) == e and i not in self.readback_drop])
        raise AssertionError(f"unexpected statement: {sql[:80]}")

    async def commit(self):
        self.commits += 1
        if self.commit_fault and self.commit_fault[0] == self.commits:
            if self.commit_fault[1]:
                self._commit_state()
            raise ConnectionError("connection closed awaiting COMMIT reply")
        self._commit_state()

    async def rollback(self):
        self.links, self.bank = dict(self._links_c), dict(self._bank_c)


def _boards_for(boards):
    async def reader(days):
        assert days <= set(boards)
        return {d: boards[d] for d in days}
    return reader


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


def _run(session, *, boards=JUN22, max_moves=10, **kw):
    return asyncio.run(rp.run(session, series_list=["KXMLBTEAMTOTAL"],
                              boards_reader=_boards_for(boards), max_moves=max_moves, **kw))


def _reviewed(session, boards=JUN22) -> str:
    """The digest a person reads off the dry run."""
    return _run(session, boards=boards, apply=False)["plan_digest"]


def _wrote_nothing(s, links):
    assert s.links == links and s.bank == {} and s.updates == 0
    assert not any(x.startswith(("CREATE", "INSERT", "UPDATE")) for x in s.statements)


class TestApply:
    def test_a_dry_run_writes_nothing_and_prints_the_digest(self):
        s = FakeSession({53104746: 15165211})
        out = _run(s, apply=False)
        assert out["counts"][rp.MOVE] == 1 and out["outcome"] == rp.DRY_RUN
        assert out["plan_digest"] == rp.plan_digest(["KXMLBTEAMTOTAL"], out["moves"])
        _wrote_nothing(s, {53104746: 15165211})

    def test_apply_of_the_reviewed_plan_banks_moves_receipts_and_reads_back(self, no_receipts):
        s = FakeSession({53104746: 15165211})
        out = _run(s, apply=True, expected_digest=_reviewed(s))
        assert s.bank == {53104746: (15165211, 14956089, True)}
        assert s.links[53104746] == 14956089
        assert out["outcome"] == rp.APPLIED
        assert out["written"] == 1 and out["readback_on_target"] == 1
        assert out["banked_ids"] == out["landed_ids"] == [53104746]
        assert out["remaining_ids"] == [] and out["readback_off_target_ids"] == []
        assert out["undo"] == rp.UNDO_LINE
        assert no_receipts == [(15165211, 14956089, "admin_repair", "repair_10960", [53104746])]

    def test_apply_without_a_reviewed_digest_refuses_before_any_write(self):
        s = FakeSession({53104746: 15165211})
        with pytest.raises(rp.Refused, match="--plan-digest"):
            _run(s, apply=True)
        _wrote_nothing(s, {53104746: 15165211})

    def test_a_same_count_plan_with_a_different_target_refuses_before_the_backup(self):
        # The dry run read 14956089 as the ticker's game. By the apply a second
        # row (another ESPN id, same clubs, same time) replaced it: still ONE
        # move, so a count ceiling passes it — the digest must not.
        s = FakeSession({53104746: 15165211})
        reviewed = _reviewed(s)
        other = cand(14999999, "2026-06-23T02:10:00", SD, ATL, "401815999")
        s.cands = {ATL_SD.market_id: [other]}
        both = {date(2026, 6, 22): board(("401815865", "2026-06-23T02:10:00", "STATUS_FINAL"),
                                         ("401815999", "2026-06-23T02:10:00", "STATUS_FINAL"))}
        s.statements.clear()
        drifted = _run(s, boards=both, apply=False)
        assert drifted["counts"][rp.MOVE] == 1
        assert drifted["moves"][0]["to_event_id"] == 14999999
        with pytest.raises(rp.Refused, match="not the reviewed"):
            _run(s, boards=both, apply=True, expected_digest=reviewed)
        _wrote_nothing(s, {53104746: 15165211})

    def test_a_twin_target_with_the_same_espn_witness_refuses(self):
        # Two rows for one game: by the apply the reviewed target was replaced by
        # another row carrying the SAME ESPN id at the same time. Only the event
        # id differs — the write itself must be bound, not just its witness.
        s = FakeSession({53104746: 15165211})
        reviewed = _reviewed(s)
        twin = cand(14999998, "2026-06-23T02:10:00", SD, ATL, "401815865")
        s.cands = {ATL_SD.market_id: [twin]}
        drifted = _run(s, apply=False)
        assert {k: v for k, v in drifted["moves"][0].items() if k != "to_event_id"} == {
            k: v for k, v in _run(FakeSession({53104746: 15165211}), apply=False)["moves"][0].items()
            if k != "to_event_id"}
        s.statements.clear()
        with pytest.raises(rp.Refused, match="not the reviewed"):
            _run(s, apply=True, expected_digest=reviewed)
        _wrote_nothing(s, {53104746: 15165211})

    def test_a_changed_espn_witness_on_the_same_triple_refuses(self):
        # Same market, same from, same to — but ESPN now places the game 90
        # minutes later (still in the window). The operator never read that.
        s = FakeSession({53104746: 15165211})
        reviewed = _reviewed(s)
        moved = {date(2026, 6, 22): board(("401815865", "2026-06-23T03:40:00", "STATUS_FINAL"))}
        assert _run(s, boards=moved, apply=False)["counts"][rp.MOVE] == 1
        s.statements.clear()
        with pytest.raises(rp.Refused, match="not the reviewed"):
            _run(s, boards=moved, apply=True, expected_digest=reviewed)
        _wrote_nothing(s, {53104746: 15165211})

    def test_a_plan_above_the_ceiling_refuses_before_any_write(self):
        s = FakeSession({53104746: 15165211})
        reviewed = _reviewed(s)
        s.statements.clear()
        with pytest.raises(rp.Refused):
            _run(s, apply=True, max_moves=0, expected_digest=reviewed)
        _wrote_nothing(s, {53104746: 15165211})

    def test_a_short_bank_refuses_before_any_write(self):
        s = FakeSession({53104746: 15165211}, bank_short=True)
        with pytest.raises(rp.Refused):
            _run(s, apply=True, expected_digest=_reviewed(s))
        assert s.links[53104746] == 15165211 and s.updates == 0


def _two_market_session(**kw):
    return FakeSession(
        {53104746: 15165211, 53104747: 15165211},
        markets=[ATL_SD, ATL_SD_2],
        cands={ATL_SD.market_id: [ATL_SD_GAME], ATL_SD_2.market_id: [ATL_SD_GAME_2]},
        **kw,
    )


class TestAllOrNothing:
    def test_a_cas_miss_mid_batch_rolls_back_the_rows_that_already_landed(self, no_receipts):
        s = _two_market_session()
        reviewed = _reviewed(s, JUN22_23)

        def matcher_moves_the_second(params):
            if params["id"] == 53104747:
                s.external_write(53104747, 777)  # a matcher pass committed first

        s.on_update = matcher_moves_the_second
        out = _run(s, boards=JUN22_23, apply=True, expected_digest=reviewed)
        # 53104746's CAS landed before 53104747 missed — and is undone with it.
        assert s.updates == 1
        assert s.links == {53104746: 15165211, 53104747: 777}
        assert out["outcome"] == rp.ROLLED_BACK_CHANGED_UNDER_RUN
        assert out["written"] == 0 and out["landed_ids"] == []
        assert out["changed_under_run"] == [53104747]
        assert out["banked_ids"] == out["remaining_ids"] == [53104746, 53104747]
        assert no_receipts == []
        # The bank stays, but no row of it is marked applied.
        assert s.bank == {53104746: (15165211, 14956089, False),
                          53104747: (15165211, 14956090, False)}

    def test_a_restore_after_a_rolled_back_apply_moves_nothing(self, no_receipts):
        s = _two_market_session()
        reviewed = _reviewed(s, JUN22_23)
        s.on_update = lambda p: p["id"] == 53104747 and s.external_write(53104747, 777)
        _run(s, boards=JUN22_23, apply=True, expected_digest=reviewed)
        # Later something legitimately puts 53104746 on the planned target; the
        # undo must not "restore" a move the repair never made.
        s.external_write(53104746, 14956089)
        r = _RestoreSession.adopt(s)
        out = asyncio.run(rp.restore(r))
        assert r.links == {53104746: 14956089, 53104747: 777}
        assert out["written"] == 0
        assert out["never_applied_left_alone"] == [53104746, 53104747]

    def test_a_target_retired_since_the_read_rolls_the_batch_back(self, no_receipts):
        s = _two_market_session(retired={14956090})
        out = _run(s, boards=JUN22_23, apply=True, expected_digest=_reviewed(s, JUN22_23))
        assert out["outcome"] == rp.ROLLED_BACK_CHANGED_UNDER_RUN
        assert out["changed_under_run"] == [53104747]
        assert s.links == {53104746: 15165211, 53104747: 15165211}

    def test_an_error_mid_batch_rolls_back(self, no_receipts):
        s = _two_market_session()

        def boom(params):
            if params["id"] == 53104747:
                raise RuntimeError("connection lost")

        reviewed = _reviewed(s, JUN22_23)
        s.on_update = boom
        out = _run(s, boards=JUN22_23, apply=True, expected_digest=reviewed)
        assert out["outcome"] == rp.ROLLED_BACK_ERROR and "connection lost" in out["error"]
        assert s.links == {53104746: 15165211, 53104747: 15165211}
        assert all(not v[2] for v in s.bank.values())

    def test_a_whole_batch_lands_together(self, no_receipts):
        s = _two_market_session()
        out = _run(s, boards=JUN22_23, apply=True, expected_digest=_reviewed(s, JUN22_23))
        assert out["outcome"] == rp.APPLIED
        assert s.links == {53104746: 14956089, 53104747: 14956090}
        assert out["landed_ids"] == [53104746, 53104747]


class TestAfterTheCommitIsExplicit:
    def test_a_short_receipt_count_is_its_own_outcome(self, monkeypatch):
        async def none_written(rows, **kw):
            return 0

        import app.utils.match_receipts as mr
        monkeypatch.setattr(mr, "record_link_change_receipts", none_written)
        s = FakeSession({53104746: 15165211})
        out = _run(s, apply=True, expected_digest=_reviewed(s))
        assert out["outcome"] == rp.APPLIED_RECEIPTS_SHORT
        assert out["landed_ids"] == [53104746] and out["undo"] == rp.UNDO_LINE

    def test_a_row_read_back_off_target_is_named(self, no_receipts):
        s = _two_market_session(readback_drop={53104747})
        out = _run(s, boards=JUN22_23, apply=True, expected_digest=_reviewed(s, JUN22_23))
        assert out["outcome"] == rp.APPLIED_READBACK_SHORT
        assert out["readback_off_target_ids"] == [53104747]
        assert out["readback_on_target"] == 1 and out["undo"] == rp.UNDO_LINE


@pytest.fixture
def receipts_raise(monkeypatch):
    async def boom(rows, **kw):
        raise RuntimeError("receipt store unavailable")

    import app.utils.match_receipts as mr
    monkeypatch.setattr(mr, "record_link_change_receipts", boom)


def _never_rolled_back(out):
    assert out["outcome"] not in (rp.ROLLED_BACK_ERROR, rp.ROLLED_BACK_CHANGED_UNDER_RUN)
    assert out["outcome"] not in rp.CLEAN_OUTCOMES
    assert out["undo"] == rp.UNDO_LINE


class TestAfterTheCommitNothingRaises:
    """#10960 audit of 74033d87fe: once the move committed, a raising receipt
    store or read-back must not turn the run into a traceback with no ids."""

    def test_a_raised_receipt_store_reports_the_committed_ids_and_the_undo(self, receipts_raise):
        s = _two_market_session()
        out = _run(s, boards=JUN22_23, apply=True, expected_digest=_reviewed(s, JUN22_23))
        assert s.links == {53104746: 14956089, 53104747: 14956090}  # it DID land
        assert out["outcome"] == rp.APPLIED_POSTCOMMIT_UNVERIFIED
        assert out["committed"] is True
        assert out["landed_ids"] == [53104746, 53104747] and out["written"] == 2
        assert out["receipts"] is None
        assert "receipt store unavailable" in out["postcommit_errors"]["receipts"]
        assert out["readback_on_target"] == 2 and out["readback_off_target_ids"] == []
        _never_rolled_back(out)

    def test_a_raised_readback_reports_the_committed_ids_and_the_undo(self, no_receipts):
        s = _two_market_session(readback_raises=True)
        out = _run(s, boards=JUN22_23, apply=True, expected_digest=_reviewed(s, JUN22_23))
        assert s.links == {53104746: 14956089, 53104747: 14956090}
        assert out["outcome"] == rp.APPLIED_POSTCOMMIT_UNVERIFIED
        assert out["committed"] is True
        assert out["landed_ids"] == [53104746, 53104747]
        assert out["receipts"] == 2
        assert "read-back connection reset" in out["postcommit_errors"]["readback"]
        assert "readback_on_target" not in out  # unknown is not zero
        _never_rolled_back(out)

    def test_both_raising_still_reports_both(self, receipts_raise):
        s = _two_market_session(readback_raises=True)
        out = _run(s, boards=JUN22_23, apply=True, expected_digest=_reviewed(s, JUN22_23))
        assert set(out["postcommit_errors"]) == {"receipts", "readback"}
        assert out["landed_ids"] == [53104746, 53104747]
        _never_rolled_back(out)

    def test_the_undo_after_an_unverified_apply_moves_everything_back(self, receipts_raise):
        s = _two_market_session()
        _run(s, boards=JUN22_23, apply=True, expected_digest=_reviewed(s, JUN22_23))
        r = _RestoreSession.adopt(s)
        asyncio.run(rp.restore(r))
        assert r.links == {53104746: 15165211, 53104747: 15165211}


class TestALostCommitAnswerIsUncertain:
    """A COMMIT that raises may have landed on the server; never 'rolled back'.
    Commit 1 is the bank's, commit 2 the move's."""

    @pytest.mark.parametrize("lands", [True, False])
    def test_it_is_uncertain_whether_or_not_it_landed(self, no_receipts, lands):
        s = _two_market_session()
        reviewed = _reviewed(s, JUN22_23)
        s.commit_fault = (2, lands)
        out = _run(s, boards=JUN22_23, apply=True, expected_digest=reviewed)
        assert out["outcome"] == rp.COMMIT_UNCERTAIN
        assert out["committed"] == "unknown"
        assert out["uncertain_ids"] == [53104746, 53104747]
        assert "COMMIT reply" in out["error"]
        assert "remaining_ids" not in out
        assert out["readback_on_target_ids"] == ([53104746, 53104747] if lands else [])
        assert no_receipts == []
        _never_rolled_back(out)

    @pytest.mark.parametrize("lands", [True, False])
    def test_the_undo_is_right_either_way(self, no_receipts, lands):
        s = _two_market_session()
        reviewed = _reviewed(s, JUN22_23)
        s.commit_fault = (2, lands)
        _run(s, boards=JUN22_23, apply=True, expected_digest=reviewed)
        r = _RestoreSession.adopt(s)
        out = asyncio.run(rp.restore(r))
        assert r.links == {53104746: 15165211, 53104747: 15165211}
        assert out["written"] == (2 if lands else 0)

    def test_an_uncertain_commit_with_a_dead_readback_still_names_the_ids(self, no_receipts):
        s = _two_market_session(readback_raises=True)
        reviewed = _reviewed(s, JUN22_23)
        s.commit_fault = (2, True)
        out = _run(s, boards=JUN22_23, apply=True, expected_digest=reviewed)
        assert out["outcome"] == rp.COMMIT_UNCERTAIN
        assert out["uncertain_ids"] == [53104746, 53104747]
        assert "read-back connection reset" in out["readback_error"]
        _never_rolled_back(out)


class TestTheCli:
    def test_apply_without_a_digest_refuses_at_the_door(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["repair", "--apply"])
        monkeypatch.setenv("HEROKU_APP_NAME", "bainluck")
        assert asyncio.run(rp.main()) == 2
        assert "--plan-digest" in capsys.readouterr().out

    def _main_on(self, monkeypatch, s, *, exit_raises):
        import contextlib
        import json

        import app.tasks.base as base

        @contextlib.asynccontextmanager
        async def session_cm():
            yield s
            if exit_raises:  # get_task_session commits on exit; that can raise too
                raise ConnectionError("commit on session exit failed")

        monkeypatch.setattr(base, "get_task_session", session_cm)
        monkeypatch.setattr(rp, "read_boards", _boards_for(JUN22_23))
        monkeypatch.setenv("HEROKU_APP_NAME", "bainluck")
        monkeypatch.setattr(sys, "argv", ["repair", "--apply", "--plan-digest",
                                          _reviewed(s, JUN22_23)])
        return json

    @pytest.mark.parametrize("exit_raises", [False, True])
    def test_the_operator_gets_ids_and_undo_when_every_after_step_raises(
            self, monkeypatch, capsys, receipts_raise, exit_raises):
        s = _two_market_session(readback_raises=True)
        json = self._main_on(monkeypatch, s, exit_raises=exit_raises)
        if exit_raises:
            with pytest.raises(ConnectionError):
                asyncio.run(rp.main())
        else:
            assert asyncio.run(rp.main()) == 3
        printed = capsys.readouterr().out
        body = json.loads(printed[printed.index("{"):printed.rindex("}") + 1])
        assert body["outcome"] == rp.APPLIED_POSTCOMMIT_UNVERIFIED
        assert body["committed"] is True
        assert body["landed_ids"] == [53104746, 53104747]
        assert set(body["postcommit_errors"]) == {"receipts", "readback"}
        assert f"UNDO: {rp.UNDO_LINE}" in printed
        assert "ROLLED_BACK" not in printed


class _RestoreSession(FakeSession):
    @classmethod
    def adopt(cls, other):
        r = cls({})
        r.links, r.bank = dict(other.links), dict(other.bank)
        r._commit_state()
        return r

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if sql.startswith("SELECT to_regclass"):
            return _Result([("bak",)] if self.bank else [(None,)])
        if sql.startswith("SELECT b.market_id"):
            return _Result([
                _Row(market_id=k, event_id_before=v[0], event_id_after=v[1],
                     applied_at="t" if v[2] else None,
                     event_id=self.links.get(k), external_id="x", name="n")
                for k, v in sorted(self.bank.items())
            ])
        return await super().execute(stmt, params)


class TestRestore:
    def test_restore_moves_back_only_what_is_still_where_the_repair_put_it(self, no_receipts):
        s = _RestoreSession({1: 20, 2: 999})
        s.bank = {1: (10, 20, True), 2: (11, 21, True)}  # market 2 has moved again since
        out = asyncio.run(rp.restore(s))
        assert s.links == {1: 10, 2: 999}
        assert out["written"] == 1 and out["readback_on_before"] == 1
        assert out["restored_ids"] == [1]
        assert out["not_on_after_left_alone"] == [2]
        assert out["outcome"] == rp.RESTORED
        assert no_receipts == [(20, 10, "admin_repair", "repair_10960", [1])]

    def test_restore_names_a_market_that_moved_under_it(self, no_receipts):
        s = _RestoreSession({1: 20})
        s.bank = {1: (10, 20, True)}
        s.on_update = lambda p: s.external_write(1, 555)
        out = asyncio.run(rp.restore(s))
        assert s.links == {1: 555}
        assert out["changed_under_restore"] == [1] and out["outcome"] == rp.RESTORE_SHORT

    def test_a_raised_receipt_or_readback_after_the_restore_commit_still_names_the_ids(
            self, receipts_raise):
        s = _RestoreSession({1: 20, 2: 21}, readback_raises=True)
        s.bank = {1: (10, 20, True), 2: (11, 21, True)}
        out = asyncio.run(rp.restore(s))
        assert s.links == {1: 10, 2: 11}
        assert out["outcome"] == rp.RESTORED_POSTCOMMIT_UNVERIFIED
        assert out["committed"] is True and out["restored_ids"] == [1, 2]
        assert set(out["postcommit_errors"]) == {"receipts", "readback"}

    def test_a_lost_restore_commit_answer_is_uncertain(self, no_receipts):
        s = _RestoreSession({1: 20}, commit_fault=(1, True))
        s.bank = {1: (10, 20, True)}
        out = asyncio.run(rp.restore(s))
        assert out["outcome"] == rp.RESTORE_COMMIT_UNCERTAIN
        assert out["committed"] == "unknown" and out["restored_ids"] == [1]
        assert out["readback_on_before_ids"] == [1]

    def test_restore_without_a_bank_refuses(self):
        with pytest.raises(rp.Refused):
            asyncio.run(rp.restore(_RestoreSession({})))
