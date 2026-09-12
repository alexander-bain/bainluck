"""#5746/#5779 — two rows carrying one StatPal fixture id become one card.

Every row in this file is a PRODUCTION row, read from `events` on 2026-09-12 at
23:1xZ. The whole population is small enough to hold: **12 groups of rows sharing
a `statpal_fixture_id`, across five sports.** Nine are one contest held twice.
Three are two genuinely different games wearing one id.

That three-in-twelve is why this file is written around the refusals rather than
around the happy path. A rail that tagged on the shared id alone would pass every
"one card" test anyone would think to write AND hide three real NBA/NHL games.

WHAT IS GRADED, AND IN WHICH DIRECTION
──────────────────────────────────────
* `TestTheShip` — the nine admissible groups plan a tag, and the survivor is the
  row a reader wants (scored, ESPN-anchored).
* `TestTheThreeItRefuses` — the three fabricated-id groups plan NOTHING, on their
  real ids and real kickoffs. Delete the minute check and this file goes red on
  production data, not on a strawman.
* `TestTheOtherRefusals` — blank / `statpal_live_…` / split-sport / swapped /
  already-suppressed. Orientation refuses 0 of the 12 today and is graded on a
  manufactured swap, which is stated rather than dressed up: the read side folds
  the suppressed row's `win_probability_sources` onto the survivor, so a swapped
  fold prints one side's probability under the other's name.
* `TestTheWriterCannotDoubleAppendOrLoseItsFailures` — the SQL, its idempotence
  guard, and what a rowcount of 0 means.
* `TestTheReaderSeesOneCard` — the point of all of it: with the tag on the row,
  `not_a_proven_duplicate()` returns ONE of the two, and it is the canonical.
"""

import json
import os
import sys
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Optional

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.models import Event, Sport  # noqa: E402
from app.models.models import Base  # noqa: E402
from app.services.anchor_channel import duplicate_tag  # noqa: E402
from app.tasks.reconcile_shared_fixture_ids import (  # noqa: E402
    APPEND_DUPLICATE_TAG,
    REFUSAL_ALREADY_SUPPRESSED,
    REFUSAL_KICKOFF_DIFFERS,
    REFUSAL_NOT_A_CONTEST_ID,
    REFUSAL_ORIENTATION,
    REFUSAL_SPLIT_SPORT,
    plan_shared_fixture_duplicates,
    reconcile_shared_fixture_ids,
)
from app.tasks.stamp_v1_statpal_fixtures import is_statpal_contest_id  # noqa: E402
from app.utils.proven_duplicates import not_a_proven_duplicate  # noqa: E402

MLB, NBA, NHL, BUNDESLIGA, SERIE_A = 1, 2, 3, 4, 5


def _at(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


@dataclass
class Row:
    """A row of `SELECT_ROWS_FOR_FIXTURES`, by the names that SELECT projects.

    Hand-built rather than selected, so a rename in the statement breaks this —
    which is the point. `win_probability_sources` and `event_tags` default to the
    shapes asyncpg returns (a dict / a list), never to the SQLite text form; the
    text form is graded separately in `test_a_serialised_tag_array_is_read`.
    """

    id: int
    sport_id: int
    statpal_fixture_id: Optional[str]
    home_team_name: str
    away_team_name: str
    commence_time: Optional[datetime]
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    espn_id: Optional[str] = None
    external_id: Optional[str] = None
    win_probability_sources: Optional[dict] = None
    event_tags: Any = None


# ── The 12 production groups, verbatim ───────────────────────────────────────
#
# `SELECT s.key, e.statpal_fixture_id, e.id, e.espn_id, e.external_id,
#         e.home_team_name, e.away_team_name, e.commence_time, e.status,
#         e.home_score, e.away_score FROM events e JOIN sports s …`
# over every `(sport_id, statpal_fixture_id)` group with more than one row.

#: Five MLB pairs. In every one the ghost is the StatPal-schedule row — created
#: days ahead, still `suspended`, no score, no `espn_id`, no `external_id`, and
#: spelling the club `St.Louis Cardinals` without the space (#5746).
MLB_PAIRS = [
    (
        "364886",
        Row(15299649, MLB, "364886", "San Francisco Giants", "St.Louis Cardinals",
            _at("2026-09-08T00:10:00")),
        Row(15306176, MLB, "364886", "San Francisco Giants", "St. Louis Cardinals",
            _at("2026-09-08T00:10:00"), 5, 4, "401816850",
            "7e08f8c46ae533c3c09d2e5d1a37ac2b"),
    ),
    (
        "364906",
        Row(15300848, MLB, "364906", "San Francisco Giants", "St.Louis Cardinals",
            _at("2026-09-09T01:45:00")),
        Row(15307210, MLB, "364906", "San Francisco Giants", "St. Louis Cardinals",
            _at("2026-09-09T01:45:00"), 2, 1, "401816864",
            "7fe872788a9a570ceb3aa6918bbf641d"),
    ),
    (
        "364910",
        Row(15301158, MLB, "364910", "San Francisco Giants", "St.Louis Cardinals",
            _at("2026-09-09T19:45:00")),
        Row(15308234, MLB, "364910", "San Francisco Giants", "St. Louis Cardinals",
            _at("2026-09-09T19:45:00"), 7, 6, "401816879",
            "4a391464b8e1ffee0ee5e205298840de"),
    ),
    (
        # The pair in #5746's screenshot: FINAL 7-3 on the results rail and the
        # same game under NO RESULT REPORTED.
        "364953",
        Row(15304908, MLB, "364953", "St.Louis Cardinals", "Chicago White Sox",
            _at("2026-09-12T00:15:00")),
        Row(15309733, MLB, "364953", "St. Louis Cardinals", "Chicago White Sox",
            _at("2026-09-12T00:15:00"), 7, 3, "401816896",
            "c4e5d894df1c758237b65a07b20a62b2"),
    ),
    (
        # Not yet played — no score on EITHER row, so the election falls through
        # to the ESPN id. A pair the score rule cannot separate is the one a
        # "hide the emptier row" heuristic gets wrong.
        "364969",
        Row(15305691, MLB, "364969", "St.Louis Cardinals", "Chicago White Sox",
            _at("2026-09-12T23:15:00")),
        Row(15310371, MLB, "364969", "St. Louis Cardinals", "Chicago White Sox",
            _at("2026-09-12T23:15:00"), None, None, "401816911",
            "14b28cc8951c1250a20d6aa224ec3317"),
    ),
]

#: #5779's specimen. The two rows spell the club `FSV Mainz 05` and `Mainz`, so
#: the id-FREE name fold (`fold_twin_events`) cannot see this pair at all — it is
#: the whole reason the issue was filed, and the reason an id arm was needed.
BUNDESLIGA_PAIR = (
    "9543399",
    Row(15297803, BUNDESLIGA, "9543399", "FSV Mainz 05", "Eintracht Frankfurt",
        _at("2026-09-12T13:30:00"), 1, 3, None,
        "467fe6e71bc34a255dfb47e13b8fa34e"),
    Row(15310934, BUNDESLIGA, "9543399", "Mainz", "Eintracht Frankfurt",
        _at("2026-09-12T13:30:00"), 1, 3, "401884794", None),
)

#: The control from #5779: the names DO agree here, the serve-time fold already
#: collapses it, and production serves the espn-anchored row. This rail must
#: elect the same one or a folding page and a tag-reading page disagree.
SERIE_A_PAIR = (
    "9545725",
    Row(15297966, SERIE_A, "9545725", "Lazio", "AC Milan",
        _at("2026-09-12T16:00:00"), 2, 2, None,
        "b412817739a87e18bf391bf6ccff6560"),
    Row(15298413, SERIE_A, "9545725", "Lazio", "AC Milan",
        _at("2026-09-12T16:00:00"), 2, 2, "401874941",
        "366bace2b2db1dd852ade6db533f1a48"),
)

#: Two NHL pairs whose kickoffs DO agree. Both carry a Kalshi-synthetic
#: `external_id` on one side, which is the shape #2263 was written for.
NHL_PAIRS = [
    (
        "627215",
        Row(11962575, NHL, "627215", "Los Angeles", "Vancouver",
            _at("2026-04-10T02:30:00"), None, None, None,
            "pm_kalshi_KXNHLGAME-26MAR26LAVAN"),
        Row(13437248, NHL, "627215", "Los Angeles Kings", "Vancouver Canucks",
            _at("2026-04-10T02:30:00"), 4, 1, None,
            "70acbfc016bd945470b87f3799a0650f"),
    ),
    (
        "637987",
        Row(6032536, NHL, "637987", "Minnesota", "Colorado",
            _at("2026-05-12T00:00:00"), 2, 5, None,
            "pm_kalshi_KXNHLGAME-26FEB26MINCOL"),
        Row(14631266, NHL, "637987", "Minnesota Wild", "Colorado Avalanche",
            _at("2026-05-12T00:00:00"), 2, 5, None,
            "06019ea348b06f7e342d8998911baca1"),
    ),
]

#: THE THREE THAT ARE NOT DUPLICATES. Same id, different night — a back-to-back
#: or an adjacent game in the series, which is exactly the population the
#: stamper's own ±1h ceiling exists to keep apart (its finding 1).
FABRICATED_ID_GROUPS = [
    (
        "1027790",
        Row(14271392, NBA, "1027790", "Charlotte Hornets", "Miami Heat",
            _at("2026-04-15T23:40:00"), 127, 126, None,
            "48d7cc894162372714ad016109df0e73"),
        Row(14276967, NBA, "1027790", "Charlotte Hornets", "Miami Heat",
            _at("2026-04-14T23:30:00"), 127, 126, None,
            "25f53495c4044a1d8fb682e3715eb7b3"),
    ),
    (
        "1027792",
        Row(14275110, NBA, "1027792", "Philadelphia 76ers", "Orlando Magic",
            _at("2026-04-14T23:40:00"), None, None, None,
            "77fc0797ec86af0045233c0b4b1d2976"),
        Row(14276969, NBA, "1027792", "Philadelphia 76ers", "Orlando Magic",
            _at("2026-04-15T23:30:00"), 109, 97, "401866757",
            "f7264c00c662a127d58f4ab12fc498bc"),
    ),
    (
        "637968",
        Row(14623538, NHL, "637968", "Colorado Avalanche", "Minnesota Wild",
            _at("2026-05-04T01:00:00"), 9, 6, None,
            "dffd95aefd43cfbbe00c7e861001be14"),
        Row(14627433, NHL, "637968", "Colorado Avalanche", "Minnesota Wild",
            _at("2026-05-06T00:00:00"), 5, 2, None,
            "fbc314d1e8c60127f6b1a302f544af53"),
    ),
]

ADMISSIBLE_GROUPS = MLB_PAIRS + [BUNDESLIGA_PAIR, SERIE_A_PAIR] + NHL_PAIRS
ALL_GROUPS = ADMISSIBLE_GROUPS + FABRICATED_ID_GROUPS


def _rows(groups):
    """Fresh COPIES of the specimen rows.

    The specimens are module-level and the refusal tests mutate a kickoff and a
    tag bag. Handing out the originals let one test leave `364953` an hour late
    and four later tests read `planned 4` where the population is 5 — a rig
    defect that reads exactly like a product defect (the whole class in
    `INDEX-test-rig-traps`).
    """
    return [replace(row) for group in groups for row in group[1:]]


def _plan(rows):
    return plan_shared_fixture_duplicates(rows, is_contest_id=is_statpal_contest_id)


class TestTheShip:
    def test_every_one_contest_group_plans_exactly_one_tag(self):
        tags, _ = _plan(_rows(ADMISSIBLE_GROUPS))
        assert len(tags) == len(ADMISSIBLE_GROUPS) == 9
        assert {t.fixture_id for t in tags} == {g[0] for g in ADMISSIBLE_GROUPS}

    def test_the_whole_production_population_plans_nine_and_refuses_three(self):
        tags, refusals = _plan(_rows(ALL_GROUPS))
        assert len(tags) == 9
        assert len(refusals) == 3

    @pytest.mark.parametrize(
        "fixture_id,ghost_id,canonical_id",
        [
            ("364886", 15299649, 15306176),
            ("364906", 15300848, 15307210),
            ("364910", 15301158, 15308234),
            ("364953", 15304908, 15309733),
            ("364969", 15305691, 15310371),
            # #5779: `Mainz` wins on its ESPN id even though the other row is
            # richer in tags and carries the Odds id.
            ("9543399", 15297803, 15310934),
            # The control — production already serves 15298413 on /sport/soccer/seriea.
            ("9545725", 15297966, 15298413),
            ("627215", 11962575, 13437248),
            ("637987", 14631266, 6032536),
        ],
    )
    def test_the_row_a_reader_wants_survives(self, fixture_id, ghost_id, canonical_id):
        tags, _ = _plan(_rows(ALL_GROUPS))
        tag = next(t for t in tags if t.fixture_id == fixture_id)
        assert (tag.duplicate_id, tag.canonical_id) == (ghost_id, canonical_id)

    def test_the_tag_is_the_one_the_reader_already_knows(self):
        """Minted by `anchor_channel.duplicate_tag`, not spelled out here.

        The read side compiles `event_tags @> ["<duplicate_tag(id)>"]`. A tag
        this rail spelled by hand would be written, indexed, and invisible.
        """
        tags, _ = _plan(_rows([MLB_PAIRS[3]]))
        assert tags[0].tag == duplicate_tag(15309733)

    def test_a_single_row_per_fixture_is_not_a_finding(self):
        """Healthy rows produce NO receipt — not a tag and not a refusal.

        The second half is the one that bites: with the arity test at `< 1`
        instead of `< 2`, every lone row whose column is blank or polluted files
        a `NOT_A_CONTEST_ID` refusal, and the receipt the bus reads for
        fabricated ids fills with rows that have no duplicate at all.
        """
        tags, refusals = _plan(_rows([MLB_PAIRS[0]])[1:] + [SERIE_A_PAIR[2]])
        assert (tags, refusals) == ([], [])

        lonely = replace(MLB_PAIRS[0][2], statpal_fixture_id="statpal_live_9")
        assert _plan([lonely]) == ([], [])


class TestTheThreeItRefuses:
    """The minute check, graded on the rows that make it load-bearing."""

    @pytest.mark.parametrize("group", FABRICATED_ID_GROUPS, ids=lambda g: g[0])
    def test_two_different_nights_are_not_one_game(self, group):
        tags, refusals = _plan(_rows([group]))
        assert tags == []
        assert [r["reason"] for r in refusals] == [REFUSAL_KICKOFF_DIFFERS]

    def test_the_refusal_names_the_row_so_it_can_be_repaired(self):
        _, refusals = _plan(_rows([FABRICATED_ID_GROUPS[0]]))
        assert refusals[0]["statpal_fixture_id"] == "1027790"
        assert refusals[0]["event_id"] in (14271392, 14276967)

    def test_a_ten_second_disagreement_is_still_the_same_minute(self):
        """The tolerance is a MINUTE, and both directions of it are pinned.

        Without the second assertion the truncation could be a no-op equality
        and this class would still pass — a live/scheduled pair whose two
        providers stamp :00 and :00.4 is the ordinary case.
        """
        ghost, canonical = _pair_with_fixture("364953")
        ghost.commence_time = ghost.commence_time.replace(second=40)
        tags, _ = _plan([ghost, canonical])
        assert len(tags) == 1

        ghost.commence_time = ghost.commence_time.replace(minute=16, second=0)
        tags, refusals = _plan([ghost, canonical])
        assert tags == []
        assert refusals[0]["reason"] == REFUSAL_KICKOFF_DIFFERS


class TestTheOtherRefusals:
    def test_a_blank_id_groups_nothing(self):
        """`statpal-blank-ids` — an empty column is not a shared identity.

        Both arms: the empty string and whitespace. `NULL` is covered by the
        SELECT, which cannot return a row whose column is NULL for `= ANY(...)`.
        """
        for blank in ("", "   "):
            ghost, canonical = _pair_with_fixture(blank)
            tags, refusals = _plan([ghost, canonical])
            assert tags == []
            assert refusals[0]["reason"] == REFUSAL_NOT_A_CONTEST_ID

    def test_the_polluted_column_value_groups_nothing(self):
        """#2963 put `statpal_live_…` sentences in this column."""
        ghost, canonical = _pair_with_fixture("statpal_live_15304938")
        tags, refusals = _plan([ghost, canonical])
        assert tags == []
        assert refusals[0]["reason"] == REFUSAL_NOT_A_CONTEST_ID

    def test_two_sports_sharing_one_id_are_a_collision(self):
        """D55/#2879: id spaces overlap between sports, so the sport is part of it."""
        ghost, canonical = _pair_with_fixture("364953")
        ghost.sport_id = NBA
        tags, refusals = _plan([ghost, canonical])
        assert tags == []
        assert refusals[0]["reason"] == REFUSAL_SPLIT_SPORT

    def test_a_swapped_pair_is_refused(self):
        """Refuses 0 of the 12 production groups; graded on a manufactured swap.

        Stated plainly because an inert guard that looks load-bearing is worse
        than none: the reason it is here is that the read side folds this row's
        `win_probability_sources` onto the survivor, and a swapped fold prints
        one club's win probability under the other's name.
        """
        ghost, canonical = _pair_with_fixture("364953")
        ghost.home_team_name, ghost.away_team_name = (
            ghost.away_team_name,
            ghost.home_team_name,
        )
        tags, refusals = _plan([ghost, canonical])
        assert tags == []
        assert refusals[0]["reason"] == REFUSAL_ORIENTATION

    def test_a_row_already_tagged_is_not_tagged_again(self):
        ghost, canonical = _pair_with_fixture("364953")
        ghost.event_tags = [duplicate_tag(canonical.id)]
        tags, refusals = _plan([ghost, canonical])
        assert tags == []
        assert refusals[0]["reason"] == REFUSAL_ALREADY_SUPPRESSED

    def test_a_canonical_that_is_itself_a_duplicate_starts_no_chain(self):
        ghost, canonical = _pair_with_fixture("364953")
        canonical.event_tags = [duplicate_tag(99999999)]
        tags, refusals = _plan([ghost, canonical])
        assert tags == []
        assert refusals[0]["reason"] == REFUSAL_ALREADY_SUPPRESSED

    def test_a_serialised_tag_array_is_read(self):
        """SQLite hands `event_tags` back as text, asyncpg as a list.

        Iterating the text form yields single CHARACTERS and finds no tag — a
        pass that re-plans every row it has already tagged, with every
        Postgres-shaped test still green.
        """
        ghost, canonical = _pair_with_fixture("364953")
        ghost.event_tags = json.dumps([duplicate_tag(canonical.id)])
        tags, refusals = _plan([ghost, canonical])
        assert tags == []
        assert refusals[0]["reason"] == REFUSAL_ALREADY_SUPPRESSED

    def test_an_unrelated_tag_does_not_suppress(self):
        """The prefix test is a PREFIX test, not "has any tag"."""
        ghost, canonical = _pair_with_fixture("364953")
        ghost.event_tags = ["provenance:source:statpal", "audience:local_interest"]
        tags, _ = _plan([ghost, canonical])
        assert len(tags) == 1


def _pair_with_fixture(fixture_id):
    """#5746's pair, re-keyed. Copies, so a mutation cannot leak between tests."""
    ghost, canonical = MLB_PAIRS[3][1], MLB_PAIRS[3][2]
    return replace(ghost, statpal_fixture_id=fixture_id), replace(
        canonical, statpal_fixture_id=fixture_id
    )


class _FakeSession:
    """Records statements and rowcounts. Never pretends to be a transaction.

    It cannot prove anything about locking or flush ordering and does not try
    to: what is graded here is the statement, its binds, and what the caller
    does with a rowcount of 0 and with a raise.
    """

    def __init__(self, select_rows, *, rowcounts=None, raise_on=()):
        self._select_rows = select_rows
        self._rowcounts = list(rowcounts or [])
        self._raise_on = set(raise_on)
        self.statements: list[tuple[str, dict]] = []
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, statement, params=None):
        sql = str(statement)
        self.statements.append((sql, params or {}))
        if "SELECT" in sql:
            return _Result(self._select_rows, None)
        if (params or {}).get("event_id") in self._raise_on:
            raise RuntimeError("deadlock detected")
        rowcount = self._rowcounts.pop(0) if self._rowcounts else 1
        return _Result([], rowcount)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


class _Result:
    def __init__(self, rows, rowcount):
        self._rows = rows
        self.rowcount = rowcount

    def all(self):
        return self._rows


class TestTheWriterCannotDoubleAppendOrLoseItsFailures:
    @pytest.mark.asyncio
    async def test_the_update_is_idempotent_in_the_database(self):
        """`NOT … @>` is what makes the backup-free undo honest.

        A rowcount of 1 has to mean "the element was absent a moment ago", or
        `event_tags - '<tag>'` is not the inverse of this write.
        """
        assert "NOT COALESCE(event_tags, '[]'::jsonb) @> CAST(:tag_array AS jsonb)" in (
            APPEND_DUPLICATE_TAG
        )
        assert "statpal_fixture_id = :fixture_id" in APPEND_DUPLICATE_TAG

    @pytest.mark.asyncio
    async def test_it_writes_one_tag_per_ghost_and_commits_each(self):
        session = _FakeSession(_rows(MLB_PAIRS))
        out = await reconcile_shared_fixture_ids(
            session, [g[0] for g in MLB_PAIRS], is_contest_id=is_statpal_contest_id
        )
        assert (out["tags_planned"], out["tags_written"]) == (5, 5)
        assert session.commits == 5
        updates = [p for sql, p in session.statements if "UPDATE" in sql]
        assert [p["event_id"] for p in updates] == [
            15299649, 15300848, 15301158, 15304908, 15305691
        ]
        assert json.loads(updates[3]["tag_array"]) == [duplicate_tag(15309733)]

    @pytest.mark.asyncio
    async def test_a_second_pass_plans_the_same_and_writes_nothing(self):
        """The steady state. `planned 5 / written 0` is health, not a failure."""
        session = _FakeSession(_rows(MLB_PAIRS), rowcounts=[0, 0, 0, 0, 0])
        out = await reconcile_shared_fixture_ids(
            session, [g[0] for g in MLB_PAIRS], is_contest_id=is_statpal_contest_id
        )
        assert (out["tags_planned"], out["tags_written"]) == (5, 0)
        assert out["failed_event_ids"] == []

    @pytest.mark.asyncio
    async def test_one_failed_row_does_not_cost_the_other_four(self):
        session = _FakeSession(_rows(MLB_PAIRS), raise_on={15301158})
        out = await reconcile_shared_fixture_ids(
            session, [g[0] for g in MLB_PAIRS], is_contest_id=is_statpal_contest_id
        )
        assert out["tags_written"] == 4
        assert out["failed_event_ids"] == [15301158]
        assert session.rollbacks == 1

    @pytest.mark.asyncio
    async def test_plan_only_issues_no_update(self):
        session = _FakeSession(_rows(MLB_PAIRS))
        out = await reconcile_shared_fixture_ids(
            session,
            [g[0] for g in MLB_PAIRS],
            is_contest_id=is_statpal_contest_id,
            apply=False,
        )
        assert out["tags_planned"] == 5
        assert out["tags_written"] == 0
        assert not [sql for sql, _ in session.statements if "UPDATE" in sql]

    @pytest.mark.asyncio
    async def test_no_fixtures_is_no_round_trip(self):
        session = _FakeSession([])
        out = await reconcile_shared_fixture_ids(
            session, ["", "   "], is_contest_id=is_statpal_contest_id
        )
        assert out["fixtures_examined"] == 0
        assert session.statements == []

    def test_the_contest_predicate_has_no_default(self):
        """A caller cannot forget it, and there is no second digits rule to drift.

        `is_contest_id` is keyword-only with no default in BOTH entry points, so
        the stamper's own `is_statpal_contest_id` is the only definition of what
        a StatPal id is. A default here would be a silent second one.
        """
        import inspect

        for fn in (plan_shared_fixture_duplicates, reconcile_shared_fixture_ids):
            param = inspect.signature(fn).parameters["is_contest_id"]
            assert param.default is inspect.Parameter.empty
            assert param.kind is inspect.Parameter.KEYWORD_ONLY


class TestTheReaderSeesOneCard:
    """The tag, on the row, through the predicate every surface already uses."""

    @pytest.fixture
    def engine(self):
        eng = create_engine("sqlite://")
        Base.metadata.create_all(eng)
        with Session(eng) as s:
            s.add(Sport(id=MLB, key="baseball_mlb", name="MLB"))
            ghost, canonical = MLB_PAIRS[3][1], MLB_PAIRS[3][2]
            for row, status in ((ghost, "suspended"), (canonical, "completed")):
                s.add(
                    Event(
                        id=row.id,
                        sport_id=row.sport_id,
                        statpal_fixture_id=row.statpal_fixture_id,
                        home_team_name=row.home_team_name,
                        away_team_name=row.away_team_name,
                        commence_time=row.commence_time,
                        home_score=row.home_score,
                        away_score=row.away_score,
                        espn_id=row.espn_id,
                        external_id=row.external_id,
                        status=status,
                    )
                )
            s.commit()
        return eng

    def test_both_rows_print_before_the_tag(self, engine):
        """The strawman guard: without it, the test below proves nothing."""
        with Session(engine) as s:
            printed = s.scalars(select(Event.id).where(not_a_proven_duplicate())).all()
        assert sorted(printed) == [15304908, 15309733]

    def test_one_row_prints_after_it(self, engine):
        with Session(engine) as s:
            ghost = s.get(Event, 15304908)
            ghost.event_tags = [duplicate_tag(15309733)]
            s.commit()
            printed = s.scalars(select(Event.id).where(not_a_proven_duplicate())).all()
        assert printed == [15309733]
