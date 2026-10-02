"""A BOXED 0-TOTAL FINAL IS REPLACED BY ESPN'S FINAL OR BY NOTHING — #980 follow-up.

The forward path re-feeds a boxed 0-total row once and stamps it
`scores_checked_at` whatever the answer, so a row checked while ESPN's
`is_final` was missing is frozen at 0 - 0 forever. The repair ignores that stamp
and carries its own marker. These tests run the SHIPPED statements against a
real sqlite engine with a stub ESPN, and assert:

  * who is asked: settled, ESPN-anchored, ALREADY boxed, 0-total (0-0 or
    NULL-NULL), old enough, not a draw-capable sport — oldest first, bounded;
  * who is written: only a row whose own anchor is that id, the same game,
    FINAL, scored — and then only as #980's `_corrected_final_score` says;
  * preview writes and creates nothing; `--apply` banks before it writes;
  * the marker stops a postponed/scoreless row being asked twice, and re-opens
    the question only when the anchor itself changed;
  * the undo restores only what this pass wrote and keeps newer truth.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


from app.models import Event, Sport  # noqa: E402
from app.models.models import Base  # noqa: E402
from app.tasks import espn_sync  # noqa: E402
from scripts import repair_5841_zero_zero_finals_from_the_authority as r5841  # noqa: E402
from scripts import repair_980_boxed_zero_scores as r980  # noqa: E402

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
S_MLB, S_NCAAB, S_SOCCER = 1, 2, 3
BOX = {"source": "espn", "players": {}, "scoring_plays": [], "scores_checked_at": "2026-04-12T00:00:00+00:00"}


class _AsyncSession:
    """`await`-able face on the sync sqlite session — every statement is the shipped one."""

    def __init__(self, session):
        self._session = session

    async def execute(self, *args, **kwargs):
        return self._session.execute(*args, **kwargs)

    async def commit(self):
        self._session.commit()

    async def rollback(self):
        self._session.rollback()

    def get_bind(self):
        return self._session.get_bind()


class _ESPN:
    """Stub authority: answers by espn_id, records every question asked."""

    def __init__(self, answers):
        self.answers = answers
        self.asked = []

    async def get_event(self, sport_key, espn_id):
        self.asked.append(espn_id)
        answer = self.answers.get(espn_id)
        if isinstance(answer, Exception):
            raise answer
        return answer


def _aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _event(eid, home, away, commence, *, sport_id=S_MLB, status="completed",
           score=(0, 0), espn_id=None, box=True, **kw):
    fields = dict(
        id=eid, sport_id=sport_id, external_id=f"ext-{eid}",
        home_team_name=home, away_team_name=away, commence_time=_aware(commence),
        status=status, home_score=score[0], away_score=score[1], espn_id=espn_id,
    )
    if box:
        fields["box_score_data"] = dict(BOX)
    fields.update(kw)
    return Event(**fields)


def _anchor(espn_id, *, date, home, away, home_score, away_score, status="post",
            stopped_without_result=False, time_valid=True):
    return NS(
        espn_id=espn_id, date=_aware(date), status=status,
        stopped_without_result=stopped_without_result, time_valid=time_valid,
        home_team=NS(display_name=home, name=home.split()[-1]),
        away_team=NS(display_name=away, name=away.split()[-1]),
        home_score=home_score, away_score=away_score,
    )


# #980's own Batch-0 specimens (ESPN-verified), plus the NULL-NULL shape.
STL_ARI = (101, "Arizona Diamondbacks", "St. Louis Cardinals", datetime(2026, 6, 24, 21, 40), "401815890")
WSH_PHI = (102, "Philadelphia Phillies", "Washington Nationals", datetime(2026, 6, 24, 22, 45), "401815887")
POSTPONED = (103, "Chicago Cubs", "Milwaukee Brewers", datetime(2026, 6, 23, 18, 20), "401815854")
NCAAB_NULL = (104, "Duke Blue Devils", "North Carolina Tar Heels", datetime(2026, 3, 8, 23, 0), "401700001")


def _answers():
    return {
        "401815890": _anchor("401815890", date=STL_ARI[3], home=STL_ARI[1], away=STL_ARI[2],
                             home_score=9, away_score=4),
        "401815887": _anchor("401815887", date=WSH_PHI[3], home=WSH_PHI[1], away=WSH_PHI[2],
                             home_score=5, away_score=4),
        "401815854": _anchor("401815854", date=POSTPONED[3], home=POSTPONED[1], away=POSTPONED[2],
                             home_score=0, away_score=0, stopped_without_result=True),
        "401700001": _anchor("401700001", date=NCAAB_NULL[3], home=NCAAB_NULL[1], away=NCAAB_NULL[2],
                             home_score=84, away_score=79),
    }


@pytest.fixture
def corpus():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all([
            Sport(id=S_MLB, key="baseball_mlb", name="MLB"),
            Sport(id=S_NCAAB, key="basketball_ncaab", name="NCAAB"),
            Sport(id=S_SOCCER, key="soccer_epl", name="EPL"),
        ])
        for eid, home, away, commence, espn_id in (STL_ARI, WSH_PHI, POSTPONED):
            session.add(_event(eid, home, away, commence, espn_id=espn_id))
        eid, home, away, commence, espn_id = NCAAB_NULL
        session.add(_event(eid, home, away, commence, espn_id=espn_id, sport_id=S_NCAAB,
                           status="closed", score=(None, None)))
        # NOT candidates, each for one reason:
        session.add(_event(201, "Boston Red Sox", "New York Yankees", datetime(2026, 6, 20, 17, 0),
                           espn_id="700201", box=False))                       # unboxed: forward path's
        session.add(_event(202, "Boston Red Sox", "Tampa Bay Rays", datetime(2026, 6, 21, 17, 0),
                           espn_id="700202", score=(3, 2)))                    # real score
        session.add(_event(203, "Everton", "Fulham", datetime(2026, 6, 21, 14, 0),
                           sport_id=S_SOCCER, espn_id="700203"))               # draw-capable
        session.add(_event(204, "Detroit Tigers", "Kansas City Royals", datetime(2026, 6, 21, 17, 0)))  # no anchor
        session.add(_event(205, "Detroit Tigers", "Chicago White Sox", datetime(2026, 6, 22, 17, 0),
                           espn_id="700205", status="scheduled"))             # not settled
        session.add(_event(206, "Detroit Tigers", "Minnesota Twins", NOW - timedelta(hours=3),
                           espn_id="700206"))                                  # too young
        session.add(_event(207, "Detroit Tigers", "Cleveland Guardians", datetime(2026, 6, 22, 17, 0),
                           espn_id="700207", score=(0, 1)))                    # nonzero total
        session.commit()
        yield session


def _run(corpus, espn, **kw):
    params = dict(apply=False, limit=r980.DEFAULT_LIMIT, only_ids=None, ignore_marker=False, now=NOW)
    params.update(kw)
    return asyncio.run(r980._run_inner(espn=espn, session=_AsyncSession(corpus), **params))


def _scores(corpus):
    corpus.expire_all()
    return {e.id: (e.home_score, e.away_score) for e in corpus.execute(select(Event)).scalars()}


def _bank_exists(corpus):
    return bool(corpus.execute(text(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=:n"), {"n": r980.BAK_TABLE}).scalar())


def _bank(corpus):
    return {r.event_id: r for r in corpus.execute(text(f"SELECT * FROM {r980.BAK_TABLE}")).all()}


class TestThePopulation:
    def _slice(self, corpus, *, marker=False, limit=25, only_ids=None):
        sql = r980.candidates_sql(marker=marker, only_ids=bool(only_ids))
        params = {"settled": sorted(r980.SETTLED_STATUSES),
                  "settled_before": NOW - timedelta(hours=r980.SETTLED_FOR_HOURS), "limit": limit}
        if only_ids:
            params["only_ids"] = only_ids
        return [r.id for r in corpus.execute(r980.statement(sql, only_ids=bool(only_ids)), params).all()]

    def test_selects_exactly_the_boxed_zero_total_settled_anchored_rows_oldest_first(self, corpus):
        # NCAAB NULL-NULL (March) first, then the June MLB rows by start.
        assert self._slice(corpus) == [104, 103, 101, 102]

    def test_scores_checked_at_does_not_hide_a_row(self, corpus):
        # Every corpus row carries the forward path's stamp; that stamp is what froze them.
        assert all("scores_checked_at" in (e.box_score_data or {"scores_checked_at": 1})
                   for e in corpus.execute(select(Event)).scalars())
        assert 101 in self._slice(corpus)

    def test_limit_bounds_the_slice_and_ids_restrict_inside_sql(self, corpus):
        assert self._slice(corpus, limit=2) == [104, 103]
        assert self._slice(corpus, limit=1, only_ids=[102, 201]) == [102]

    def test_population_count_matches_the_unbounded_slice(self, corpus):
        params = {"settled": sorted(r980.SETTLED_STATUSES),
                  "settled_before": NOW - timedelta(hours=r980.SETTLED_FOR_HOURS)}
        count = corpus.execute(r980.statement(r980.population_sql(marker=False)), params).scalar()
        assert count == len(self._slice(corpus, limit=200)) == 4


class TestTheAuthorityDecides:
    def _verdict(self, corpus, eid, anchor):
        row = next(r for r in corpus.execute(
            r980.statement(r980.candidates_sql(marker=False, only_ids=True), only_ids=True),
            {"settled": sorted(r980.SETTLED_STATUSES), "settled_before": NOW, "limit": 5,
             "only_ids": [eid]}).all())
        espn = _ESPN({row.espn_id: anchor})
        return asyncio.run(r980.adjudicate(_AsyncSession(corpus), espn, row))

    def test_a_verified_final_is_written_from_correct_orientation(self, corpus):
        v = self._verdict(corpus, 101, _answers()["401815890"])
        assert (v["verdict"], v["home_score"], v["away_score"]) == ("WRITE", 9, 4)

    def test_null_null_boxed_row_is_written_too(self, corpus):
        v = self._verdict(corpus, 104, _answers()["401700001"])
        assert (v["verdict"], v["home_score"], v["away_score"]) == ("WRITE", 84, 79)

    def test_postponed_is_refused(self, corpus):
        v = self._verdict(corpus, 103, _answers()["401815854"])
        assert v["verdict"] == "REFUSED" and "not_final" in v["reason"]

    def test_espn_scoreless_final_leaves_the_row(self, corpus):
        a = _anchor("401815890", date=STL_ARI[3], home=STL_ARI[1], away=STL_ARI[2], home_score=0, away_score=0)
        v = self._verdict(corpus, 101, a)
        assert v["verdict"] == "REFUSED" and "confirms_0_0" in v["reason"]

    def test_a_different_returned_id_is_refused(self, corpus):
        a = _answers()["401815890"]
        a.espn_id = "401815887"
        v = self._verdict(corpus, 101, a)
        assert v["verdict"] == "REFUSED" and "different_id" in v["reason"]

    def test_reversed_orientation_is_refused(self, corpus):
        a = _anchor("401815890", date=STL_ARI[3], home=STL_ARI[2], away=STL_ARI[1], home_score=4, away_score=9)
        v = self._verdict(corpus, 101, a)
        assert v["verdict"] == "REFUSED" and "different_game" in v["reason"]

    def test_a_borrowed_anchor_from_another_date_is_refused_and_placeholder_flagged(self, corpus):
        a = _answers()["401815890"]
        a.date = _aware(STL_ARI[3]) - timedelta(days=1, hours=2)
        a.time_valid = False
        v = self._verdict(corpus, 101, a)
        assert v["verdict"] == "REFUSED" and "different_date" in v["reason"]
        assert "placeholder" in v["reason"]

    def test_not_yet_final_is_refused(self, corpus):
        a = _answers()["401815890"]
        a.status = "in"
        v = self._verdict(corpus, 101, a)
        assert v["verdict"] == "REFUSED" and "not_final" in v["reason"]

    def test_no_answer_and_transient_error_are_distinct(self, corpus):
        assert self._verdict(corpus, 101, None)["verdict"] == "NO_ANSWER"
        assert self._verdict(corpus, 101, RuntimeError("429"))["verdict"] == "ERROR"

    def test_a_scored_twin_is_refused_without_a_fetch(self, corpus):
        corpus.add(_event(301, STL_ARI[1], STL_ARI[2], STL_ARI[3], espn_id="401999999", score=(9, 4)))
        corpus.commit()
        row = next(r for r in corpus.execute(
            r980.statement(r980.candidates_sql(marker=False, only_ids=True), only_ids=True),
            {"settled": sorted(r980.SETTLED_STATUSES), "settled_before": NOW, "limit": 5,
             "only_ids": [101]}).all())
        espn = _ESPN(_answers())
        v = asyncio.run(r980.adjudicate(_AsyncSession(corpus), espn, row))
        assert v["verdict"] == "REFUSED" and "scored_twin" in v["reason"] and espn.asked == []

    def test_the_rules_are_the_shipped_ones_not_copies(self):
        assert r980._corrected_final_score is espn_sync._corrected_final_score
        assert r980.anchor_refusal_reason is r5841.anchor_refusal_reason
        assert r980.scored_twin is r5841.scored_twin
        assert r980.DRAW_CAPABLE_PREFIXES is r5841.DRAW_CAPABLE_PREFIXES


class TestPreviewAndApply:
    def test_preview_writes_nothing_and_creates_nothing(self, corpus):
        before = _scores(corpus)
        assert _run(corpus, _ESPN(_answers())) == 0
        assert _scores(corpus) == before
        assert not _bank_exists(corpus)

    def test_apply_banks_then_writes_only_the_verified_finals(self, corpus):
        before = _scores(corpus)
        assert _run(corpus, _ESPN(_answers()), apply=True) == 0
        after = _scores(corpus)
        assert after[101] == (9, 4) and after[102] == (5, 4) and after[104] == (84, 79)
        assert after[103] == (0, 0)  # postponed untouched
        assert {k: v for k, v in after.items() if k not in (101, 102, 104)} == \
               {k: v for k, v in before.items() if k not in (101, 102, 104)}
        bank = _bank(corpus)
        assert set(bank) == {101, 102, 103, 104}
        assert (bank[101].verdict, bank[101].old_home_score, bank[101].new_home_score) == ("WRITE", 0, 9)
        assert bank[104].old_home_score is None and bank[104].written_at is not None
        assert bank[103].verdict == "REFUSED" and bank[103].written_at is None

    def test_the_write_touches_only_the_two_score_columns(self):
        set_clause = r980._WRITE_SQL.split("SET", 1)[1].split("WHERE", 1)[0]
        assert [c.split("=")[0].strip() for c in set_clause.split(",")] == ["home_score", "away_score"]
        assert "is_winner" not in r980._WRITE_SQL and "box_score_data" not in r980._WRITE_SQL

    def test_a_row_that_moved_between_plan_and_write_is_skipped(self, corpus):
        rows = corpus.execute(
            r980.statement(r980.candidates_sql(marker=False, only_ids=True), only_ids=True),
            {"settled": sorted(r980.SETTLED_STATUSES), "settled_before": NOW, "limit": 5,
             "only_ids": [101]}).all()
        verdict = {"id": 101, "espn_id": "401815890", "verdict": "WRITE", "home_score": 9, "away_score": 4}
        # The live pass lands a real (different) final after the plan was built.
        corpus.execute(text("UPDATE events SET home_score = 10, away_score = 4 WHERE id = 101"))
        corpus.commit()
        out = asyncio.run(r980.apply_verdicts(_AsyncSession(corpus), [verdict], {101: rows[0]}))
        assert out["written"] == 0 and out["skipped"] == [101]
        assert _scores(corpus)[101] == (10, 4)
        assert _bank(corpus)[101].written_at is None

    def test_a_transient_error_is_not_marked_and_fails_the_exit(self, corpus):
        answers = _answers()
        answers["401815887"] = RuntimeError("503")
        assert _run(corpus, _ESPN(answers), apply=True) == 1
        assert 102 not in _bank(corpus)
        assert _scores(corpus)[101] == (9, 4)

    def test_apply_refuses_a_population_past_the_ceiling(self, corpus, monkeypatch):
        monkeypatch.setattr(r980, "MAX_EXPECTED_POPULATION", 3)
        espn = _ESPN(_answers())
        before = _scores(corpus)
        assert _run(corpus, espn, apply=True) == 2
        assert _scores(corpus) == before and espn.asked == []


class TestTheMarker:
    def test_a_checked_row_is_not_asked_again(self, corpus):
        _run(corpus, _ESPN(_answers()), apply=True)
        espn = _ESPN(_answers())
        assert _run(corpus, espn, apply=True) == 0
        assert espn.asked == []  # postponed 103 marked; written rows left the population

    def test_ignore_marker_reasks_and_replaces_the_refusal(self, corpus):
        _run(corpus, _ESPN(_answers()), apply=True)
        answers = _answers()
        answers["401815854"] = _anchor("401815854", date=POSTPONED[3], home=POSTPONED[1],
                                       away=POSTPONED[2], home_score=2, away_score=1)
        espn = _ESPN(answers)
        assert _run(corpus, espn, apply=True, ignore_marker=True) == 0
        assert espn.asked == ["401815854"]
        assert _scores(corpus)[103] == (2, 1)
        bank = _bank(corpus)[103]
        assert (bank.verdict, bank.new_home_score, bank.old_home_score) == ("WRITE", 2, 0)
        assert bank.written_at is not None

    def test_a_reanchored_row_is_a_new_question(self, corpus):
        _run(corpus, _ESPN(_answers()), apply=True)
        corpus.execute(text("UPDATE events SET espn_id = '401815855' WHERE id = 103"))
        corpus.commit()
        espn = _ESPN({"401815855": None})
        _run(corpus, espn, apply=True)
        assert espn.asked == ["401815855"]

    def test_a_declined_write_is_reasked(self, corpus):
        rows = corpus.execute(
            r980.statement(r980.candidates_sql(marker=False, only_ids=True), only_ids=True),
            {"settled": sorted(r980.SETTLED_STATUSES), "settled_before": NOW, "limit": 5,
             "only_ids": [101]}).all()
        verdict = {"id": 101, "espn_id": "401815890", "verdict": "WRITE", "home_score": 9, "away_score": 4}
        corpus.execute(text("UPDATE events SET status = 'live' WHERE id = 101"))
        corpus.commit()
        asyncio.run(r980.apply_verdicts(_AsyncSession(corpus), [verdict], {101: rows[0]}))
        corpus.execute(text("UPDATE events SET status = 'completed' WHERE id = 101"))
        corpus.commit()
        espn = _ESPN(_answers())
        _run(corpus, espn, apply=True, only_ids=[101])
        assert espn.asked == ["401815890"] and _scores(corpus)[101] == (9, 4)


class TestTheUndo:
    def _restore(self, corpus, apply):
        return asyncio.run(r980._restore_inner(session=_AsyncSession(corpus), apply=apply))

    def test_restore_before_any_apply_is_a_noop(self, corpus):
        assert self._restore(corpus, True) == 0 and not _bank_exists(corpus)

    def test_restore_preview_writes_nothing_then_apply_puts_back_the_pre_image(self, corpus):
        _run(corpus, _ESPN(_answers()), apply=True)
        assert self._restore(corpus, False) == 0
        assert _scores(corpus)[101] == (9, 4)
        assert self._restore(corpus, True) == 0
        after = _scores(corpus)
        assert after[101] == (0, 0) and after[102] == (0, 0) and after[104] == (None, None)
        assert _bank(corpus)[101].restored_at is not None
        assert self._restore(corpus, True) == 0  # idempotent: nothing left to restore

    def test_restore_keeps_newer_truth(self, corpus):
        _run(corpus, _ESPN(_answers()), apply=True)
        corpus.execute(text("UPDATE events SET home_score = 10 WHERE id = 101"))
        corpus.commit()
        self._restore(corpus, True)
        after = _scores(corpus)
        assert after[101] == (10, 4) and after[102] == (0, 0)
        assert _bank(corpus)[101].restored_at is None


def test_preview_is_the_default_and_limit_is_bounded():
    args = r980.parse_args([])
    assert args.apply is False and args.limit == r980.DEFAULT_LIMIT
    with pytest.raises(SystemExit):
        r980.parse_args(["--limit", str(r980.MAX_LIMIT + 1)])


def test_selftest_passes():
    assert r980._selftest() == 0
