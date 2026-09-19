"""#7021 + #7191 — the twin drain can SEE a punctuation twin, and can SURVIVE a bad pair.

Both halves ship together because neither delivers anything alone, and the way
they fail alone is the whole lesson of this file.

* **#7021 (see).** ``_duplicate_name_match_sql`` compared participants with
  ``LOWER``, so ``St.Louis Cardinals`` and ``St. Louis Cardinals`` were never
  even candidates — despite sharing ``statpal_fixture_id``, the sport and the
  start time. Measured on production: 95 pairs share a provider id, 18 are
  inside the drain's own sport + 6h + 30-day window, and **11 of those differ
  only in punctuation**. Widening the SELECT alone would have found 11 more
  pairs every 30 minutes and refused every one of them, because
  ``matchup_agrees`` — the corroboration the DELETE requires — compared the same
  two strings the same way. A candidate the guard must refuse is not a fix.

* **#7191 (survive).** The drain absorbed the orphan's ``espn_id`` onto the
  keeper *before* deleting the orphan, so the merge violated
  ``uq_events_espn_id`` using nothing but its own two rows. The raise was
  outside the per-pair ``try``, which covered only the two refusal checks, so it
  ended the pass. The offending pair is head-of-line in a deterministic
  candidate set: Sentry 7728308265 recorded **327** occurrences between
  2026-09-12 and 2026-09-19 against a beat that runs 48×/day — essentially every
  run — and in that week the rail merged nothing while reporting nothing.

The order guard is asserted on the STATEMENTS THE DRAIN ISSUES, never on the
source text. "The UPDATE appears after the DELETE in the file" is a fact about
formatting; a reordered pair of awaits inside one ``try`` would keep the text in
place and put the write back in front.
"""

from __future__ import annotations

import contextlib
from datetime import datetime, timedelta, timezone

import pytest

from app.tasks.sports import _duplicate_name_match_sql, duplicate_pairs_sql
from app.utils.event_merge_invariant import (
    UncorroboratedMergeRefused,
    assert_absorbable,
    fold_participant_name,
    folded_name_sql,
    matchup_agrees,
)

BASE = datetime(2026, 9, 19, 0, 15, tzinfo=timezone.utc)

#: The two production specimens, by the ids they carry in `events`.
CARDINALS = ("St.Louis Cardinals", "St. Louis Cardinals")   # 15310833 / 15314166
PSG = ("Paris Saint Germain", "Paris Saint-Germain")        # 15297786 / 15311919


def _event(
    *, id, espn_id=None, external_id=None, statpal_fixture_id=None,
    home="Yankees", away="Dodgers", commence=BASE,
):
    return {
        "id": id,
        "espn_id": espn_id,
        "external_id": external_id,
        "statpal_fixture_id": statpal_fixture_id,
        "home_team_name": home,
        "away_team_name": away,
        "home_team_normalized": None,
        "away_team_normalized": None,
        "commence_time": commence,
    }


# ── #7021, the pure half ─────────────────────────────────────────────────────


class TestTheFoldNamesTheParticipantAndNothingElse:
    @pytest.mark.parametrize("raw,expected", [
        ("St.Louis Cardinals", "stlouiscardinals"),
        ("St. Louis Cardinals", "stlouiscardinals"),
        ("Paris Saint-Germain", "parissaintgermain"),
        ("Paris Saint Germain", "parissaintgermain"),
        ("  Lazio  ", "lazio"),
        ("D.C. United", "dcunited"),
        ("Gen.G", "geng"),
    ])
    def test_punctuation_and_spacing_are_not_participants(self, raw, expected):
        assert fold_participant_name(raw) == expected

    def test_digits_survive_because_they_are_part_of_the_name(self):
        """``Mainz`` vs ``FSV Mainz 05`` is an ALIAS question, not this one.

        Both are real production rows sharing a provider id, and they stay
        unequal here deliberately: dropping the ``05`` would make this a fuzzy
        name matcher, which is the thing ruling 048 forbids.
        """
        assert fold_participant_name("FSV Mainz 05") == "fsvmainz05"
        assert fold_participant_name("FSV Mainz 05") != fold_participant_name("Mainz")

    def test_the_fold_is_ascii_only_so_it_can_agree_with_the_sql(self):
        """``str.isalnum()`` is Unicode-aware and ``[^a-z0-9]`` is not.

        The obvious one-liner (``if ch.isalnum()``) keeps ``á`` and makes the
        Python and SQL forms disagree on every accented name in the table, which
        is a drift no test that only exercises one form can see.
        """
        assert fold_participant_name("Málaga") == "mlaga"
        assert fold_participant_name("Atlético Madrid") == "atlticomadrid"

    def test_a_name_with_no_ascii_alphanumerics_folds_to_empty(self):
        assert fold_participant_name("横浜") == ""
        assert fold_participant_name("!!!") == ""


class TestTheCorroborationAcceptsTheTwinAndStillRefusesTheCollisions:
    @pytest.mark.parametrize("name_a,name_b", [CARDINALS, PSG])
    def test_a_punctuation_twin_is_one_matchup(self, name_a, name_b):
        a = _event(id=1, home=name_a, away="Washington Nationals")
        b = _event(id=2, home=name_b, away="Washington Nationals")
        assert matchup_agrees(a, b) is True

    @pytest.mark.parametrize("home_a,away_a,home_b,away_b,espn", [
        ("Yankees", "Dodgers", "Mets", "Dodgers", "401816142"),
        ("Real Madrid", "Real Sociedad", "Real Sociedad", "Real Betis", "401882919"),
        ("Texas", "Ohio State", "Texas", "Texas State", "401856667"),
    ])
    def test_the_1947_collisions_are_still_different_games(
        self, home_a, away_a, home_b, away_b, espn
    ):
        """The fold must not buy #7021 with #1947.

        Each pair shares a real production ``espn_id`` and is two different
        games. Folding punctuation cannot reach them — the participants differ
        in letters — and this asserts that it did not.
        """
        a = _event(id=1, espn_id=espn, home=home_a, away=away_a)
        b = _event(id=2, espn_id=espn, home=home_b, away=away_b)
        assert matchup_agrees(a, b) is False
        with pytest.raises(UncorroboratedMergeRefused):
            assert_absorbable(a, b, context="test")

    def test_two_unnameable_rows_do_not_agree_by_folding_to_empty(self):
        """``"" == ""`` is the ``NULL == NULL`` merge wearing a costume.

        Two different clubs written in a non-Latin script both fold away to the
        empty string. Without the emptiness check they satisfy the matchup arm,
        and a shared ``statpal_fixture_id`` would then delete one of them.
        """
        a = _event(id=1, statpal_fixture_id="9", home="横浜", away="鹿島")
        b = _event(id=2, statpal_fixture_id="9", home="浦和", away="川崎")
        assert matchup_agrees(a, b) is None
        with pytest.raises(UncorroboratedMergeRefused):
            assert_absorbable(a, b, context="test")

    def test_the_cardinals_pair_is_absorbable_end_to_end(self):
        """The specimen, through the assertion the DELETE actually calls."""
        a = _event(id=15310833, statpal_fixture_id="365774",
                   home=CARDINALS[0], away="Washington Nationals")
        b = _event(id=15314166, statpal_fixture_id="365774", espn_id="401816991",
                   home=CARDINALS[1], away="Washington Nationals")
        assert_absorbable(a, b, context="test")  # must not raise


class TestTheCandidateSqlFoldsEveryArm:
    """A reverted arm is the realistic regression: three near-identical clauses."""

    @pytest.fixture(scope="class")
    def predicate(self):
        return _duplicate_name_match_sql("a", "b")

    @pytest.mark.parametrize("column", [
        "home_team_name", "away_team_name",
        "home_team_normalized", "away_team_normalized",
    ])
    def test_every_compared_column_is_folded(self, predicate, column):
        for alias in ("a", "b"):
            bare = f"LOWER({alias}.{column})"
            assert f"{bare} =" not in predicate and f"= {bare}" not in predicate, (
                f"{alias}.{column} is compared with a bare LOWER(); a "
                "punctuation twin fails this arm"
            )

    def test_all_three_orientations_survive_the_rewrite(self, predicate):
        folded = predicate.count(folded_name_sql("a.home_team_name"))
        assert folded >= 2, (
            "the normal and swapped arms should both fold a.home_team_name; "
            "an arm was dropped rather than folded"
        )

    def test_the_emptiness_guard_is_present(self, predicate):
        assert "<> ''" in predicate, (
            "without this, two rows whose names fold to '' match every arm"
        )

    def test_the_shipped_query_still_requires_a_shared_provider_id(self):
        """#7021 widened the NAME half only. Arm A is not negotiable."""
        sql = duplicate_pairs_sql()
        for column in ("external_id", "espn_id", "statpal_fixture_id"):
            assert f"a.{column} = b.{column}" in sql


# ── #7191, through the real drain ────────────────────────────────────────────


class _CandidateRow:
    """One row of ``_merge_duplicate_events_impl``'s candidate SELECT."""

    def __init__(self, a, b, *, snaps_a=True, snaps_b=False):
        self.id_a, self.id_b = a["id"], b["id"]
        self.ext_a, self.ext_b = a["external_id"], b["external_id"]
        self.espn_a, self.espn_b = a["espn_id"], b["espn_id"]
        self.statpal_a = a["statpal_fixture_id"]
        self.statpal_b = b["statpal_fixture_id"]
        self.has_snaps_a, self.has_snaps_b = snaps_a, snaps_b
        self.source_a = self.source_b = "odds_api"
        self.end_a = self.end_b = None
        self.htid_a = self.atid_a = self.htid_b = self.atid_b = None
        self.home_team_name = a["home_team_name"]
        self.away_team_name = a["away_team_name"]


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def mappings(self):
        return self


class _Session:
    """Answers the drain's statements and records the ORDER it issued them.

    ``raise_on`` makes one statement fail the way Postgres does, so the pass's
    survival can be driven rather than argued.
    """

    def __init__(self, pair_rows, live_rows, *, raise_on=None):
        self._pairs = pair_rows
        self._live = {r["id"]: r for r in live_rows}
        self._raise_on = raise_on
        self.log: list[str] = []
        self.deletes: list = []
        self.rollbacks = 0
        self.commits = 0
        self._first = True

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if "FOR UPDATE" in sql:
            wanted = {params["keep_id"], params["orphan_id"]}
            return _Result([self._live[i] for i in wanted if i in self._live])
        if "DELETE FROM events" in sql:
            self.log.append(f"DELETE:{params['orphan']}")
            self.deletes.append(params)
            return _Result([])
        if sql.strip().upper().startswith("UPDATE EVENTS SET"):
            kind = "ABSORB" if "COALESCE" in sql else "UPDATE"
            self.log.append(f"{kind}:{params.get('kid')}")
            if self._raise_on and self._raise_on in sql:
                raise RuntimeError(
                    'duplicate key value violates unique constraint "uq_events_espn_id"'
                )
            return _Result([])
        if sql.strip().upper().startswith("UPDATE"):
            return _Result([])
        if self._first:
            self._first = False
            return _Result(self._pairs)
        return _Result([])

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


def _drive(monkeypatch, session):
    @contextlib.asynccontextmanager
    async def _fake():
        yield session

    import app.tasks.base as base
    monkeypatch.setattr(base, "get_task_session", lambda: _fake())


def _lazio_pair():
    """The exact rows Sentry named: keeper has no espn_id, orphan has 401874941."""
    a = _event(id=15297966, external_id="b412817739a87e18bf391bf6ccff6560",
               statpal_fixture_id="9545725", home="Lazio", away="AC Milan")
    b = _event(id=15298413, external_id="366bace2b2db1dd852ade6db533f1a48",
               espn_id="401874941", statpal_fixture_id="9545725",
               home="Lazio", away="AC Milan")
    return a, b


class TestTheOrphanIsGoneBeforeItsIdIsAbsorbed:
    @pytest.mark.asyncio
    async def test_the_delete_precedes_the_absorb(self, monkeypatch):
        """THE #7191 specimen, asserted on issued statements.

        With the absorb first, the keeper is handed the orphan's ``espn_id``
        while the orphan still holds it, and ``uq_events_espn_id`` rejects the
        merge's own two rows.
        """
        from app.tasks.sports import _merge_duplicate_events_impl

        a, b = _lazio_pair()
        session = _Session([_CandidateRow(a, b, snaps_b=True)], [a, b])
        _drive(monkeypatch, session)

        result = await _merge_duplicate_events_impl(dry_run=False)

        assert "DELETE:15298413" in session.log, "the orphan was never deleted"
        assert "ABSORB:15297966" in session.log, "the keeper absorbed nothing"
        assert session.log.index("DELETE:15298413") < session.log.index("ABSORB:15297966"), (
            f"the absorb ran while the orphan still held its unique ids: {session.log}"
        )
        assert result["write_failed"] == 0
        assert result["deleted"] == 1


class TestOneBadPairDoesNotWipeThePass:
    @pytest.mark.asyncio
    async def test_a_failed_write_is_counted_and_the_next_pair_still_merges(
        self, monkeypatch
    ):
        """Gotcha #42, on the half that had no cover.

        The first pair's absorb fails the way a third row holding the same
        ``espn_id`` would. Before #7191 that ended the task, so the second pair
        — a perfectly mergeable twin — was never reached, every run, for a week.
        """
        from app.tasks.sports import _merge_duplicate_events_impl

        bad_a, bad_b = _lazio_pair()
        good_a = _event(id=15310833, statpal_fixture_id="365774",
                        home=CARDINALS[0], away="Washington Nationals")
        good_b = _event(id=15314166, statpal_fixture_id="365774",
                        external_id="f383973af69817d515b481a52d17ff6d",
                        home=CARDINALS[1], away="Washington Nationals")

        session = _Session(
            [
                _CandidateRow(bad_a, bad_b, snaps_b=True),
                _CandidateRow(good_a, good_b, snaps_a=False, snaps_b=True),
            ],
            [bad_a, bad_b, good_a, good_b],
            raise_on="espn_id = COALESCE",
        )
        _drive(monkeypatch, session)

        result = await _merge_duplicate_events_impl(dry_run=False)

        assert result["write_failed"] == 1, (
            "the failing pair was not counted; before #7191 this condition was "
            "an uncaught exception whose only trace was in Sentry"
        )
        assert session.rollbacks == 1, (
            "the poisoned transaction was not rolled back — every later "
            "statement in the pass fails with InFailedSQLTransaction, which "
            "reproduces the outage one layer down"
        )
        assert result["deleted"] == 1, (
            "the drain stopped at the bad pair: the Cardinals twin behind it "
            "was never merged, which is exactly the week-long head-of-line "
            "block #7191 records"
        )
        assert session.deletes[-1]["orphan"] == 15310833

    @pytest.mark.asyncio
    async def test_a_punctuation_twin_is_merged_by_the_real_drain(self, monkeypatch):
        """The ship itself: one game, two rows, one survivor.

        This is the arm that goes red if either half is reverted — the SELECT
        would not offer the pair, or the corroboration would refuse it.
        """
        from app.tasks.sports import _merge_duplicate_events_impl

        a = _event(id=15310833, statpal_fixture_id="365774",
                   home=CARDINALS[0], away="Washington Nationals")
        b = _event(id=15314166, statpal_fixture_id="365774", espn_id="401816991",
                   external_id="f383973af69817d515b481a52d17ff6d",
                   home=CARDINALS[1], away="Washington Nationals")
        session = _Session([_CandidateRow(a, b, snaps_a=False, snaps_b=True)], [a, b])
        _drive(monkeypatch, session)

        result = await _merge_duplicate_events_impl(dry_run=False)

        assert result["deleted"] == 1
        assert result["refused_uncorroborated"] == 0, (
            "the corroboration refused a punctuation twin — widening the "
            "candidate SELECT without widening matchup_agrees ships a drain "
            "that finds the pair and declines it forever"
        )
        assert session.deletes == [{"orphan": 15310833}]
