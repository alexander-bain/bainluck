"""#2263 — the runner-up the matcher already found stops being thrown away.

THE DEFECT, as measured in production on 2026-08-29T01:18Z by the roll-call
sentinel and re-measured from this lane at 13:0xZ the same day:

  Of the 17 MLB fixtures ESPN published for 2026-08-29, **10 existed twice**.
  Every pair the same shape — a good row, and a bare twin ONE MINUTE earlier
  with ``espn_id`` NULL and no probability sources at all. And it was visible:
  ``GET /api/leagues/baseball_mlb`` printed Dodgers–Tigers, Marlins–Nationals
  and Padres–Rays twice each, spending 3 of the rail's 8 slots on second copies.

WHY IT WAS INVISIBLE TO EVERY EXISTING GUARD. ``feed_event_candidates``
collapses rows sharing ``(sport, home, away, commence_time)`` EXACTLY, and
``prune_unanchored_duplicates`` groups on ``(home, away, commence_time)``
exactly. The twins are a minute apart — and one pair is ``"St.Louis Cardinals"``
against ``"St. Louis Cardinals"`` — so neither ever grouped them. Both guards
were working as specified and neither could see this.

WHERE THE PROOF WAS. ``_structured_matches`` (then
``_find_by_structured_match``) had it all along. ESPN's fixture 401816721
resolves onto BOTH rows: it binds to the closest and did
``return matches[0][1]``, discarding the rest, once, silently, and never
reconsidering — because Step 1 finds the row by ``espn_id`` on every subsequent
poll and Step 3 never runs again. ESPN is the ONLY provider carrying
``schedule_derived=True``, so this is ruling 048 arm B, "THE canonical legitimate
cross-source join" in the words of its own call site. The same authority that
licenses binding the id to row A says row B is that fixture too. We were
believing half of what it told us.

WHAT THIS SUITE PINS, in the order the fix runs:

  Part A  the judgement — which runner-up is the same game, and which is a
          doubleheader. Pure, no database, because that is the part that must be
          readable.
  Part B  the matcher returns the runners-up at all, and the single-answer face
          still answers singly.
  Part C  the read side, EXECUTED against a real engine: a proven duplicate is
          not printed, and — the trap this nearly shipped with — an UNTAGGED row
          still is.
  Part D  the three surfaces actually carry the predicate.
  Part E  the reader of the id columns cannot drift from their writer.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Session


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


from app.models import Event, Sport  # noqa: E402
from app.models.models import Base  # noqa: E402
from app.services.anchor_channel import duplicate_tag  # noqa: E402
from app.services.event_registry import (  # noqa: E402
    _SAME_FIXTURE_MAX_SEPARATION,
    _attach_claim,
    _find_by_structured_match,
    _proven_duplicates,
    _structured_matches,
    EventClaim,
)
from app.utils.proven_duplicates import not_a_proven_duplicate  # noqa: E402

from tests.test_event_registry import _FakeRegistrySession  # noqa: E402

# ── The production specimen, to the minute ──────────────────────────────────
#
# LAD @ DET, ESPN fixture 401816721. The good row is `15294237` at 17:11Z
# holding that espn_id; the bare twin is `15290969` at 17:10Z holding nothing.
ESPN_FIXTURE = "401816721"
GOOD_ID = 15294237
TWIN_ID = 15290969
GOOD_TIME = datetime(2026, 8, 29, 17, 11, tzinfo=timezone.utc)
TWIN_TIME = datetime(2026, 8, 29, 17, 10, tzinfo=timezone.utc)
S_MLB = 3

ESPN_CLAIM = EventClaim("espn", ESPN_FIXTURE, schedule_derived=True)


def _row(
    id,
    commence_time,
    *,
    espn_id=None,
    sources=None,
    home_score=None,
    away_score=None,
    home="Detroit Tigers",
    away="Los Angeles Dodgers",
    sport_id=S_MLB,
    status="scheduled",
    event_tags=None,
):
    return Event(
        id=id,
        sport_id=sport_id,
        home_team_name=home,
        away_team_name=away,
        commence_time=commence_time,
        status=status,
        espn_id=espn_id,
        win_probability_sources=sources,
        home_score=home_score,
        away_score=away_score,
        event_tags=event_tags,
    )


def _good():
    return _row(GOOD_ID, GOOD_TIME, espn_id=ESPN_FIXTURE, sources={"espn": {"value": 0.57}})


def _twin():
    return _row(TWIN_ID, TWIN_TIME)


# ════════════════════════════════════════════════════════════════════════════
# Part A — the judgement
# ════════════════════════════════════════════════════════════════════════════


class TestTheJudgement:
    def test_the_2263_specimen_is_a_proven_duplicate(self):
        """The whole point. This is the row the MLB page printed twice."""
        twin = _twin()
        proven = _proven_duplicates(_good(), [twin], ESPN_CLAIM)
        assert [e.id for e in proven] == [TWIN_ID]
        assert proven[0] is twin

    def test_a_doubleheader_partner_is_never_a_proven_duplicate(self):
        """THE FALSIFIER for `_SAME_FIXTURE_MAX_SEPARATION`.

        Same clubs, same day, no espn_id yet, no odds priced yet — every guard
        except separation says "twin". Three hours apart says otherwise, and it
        must win, because tagging this row is the product silently dropping a
        real game. If this test ever has to be relaxed to make something else
        pass, the bound is wrong and must be re-argued from the schedule.
        """
        game_two = _row(15290970, GOOD_TIME + timedelta(hours=3))
        assert _proven_duplicates(_good(), [game_two], ESPN_CLAIM) == []

    def test_the_bound_is_far_from_both_edges_it_separates(self):
        """A constant tuned to its own specimen fails on the next one.

        Measured twin separation is 60s and the shortest real same-pair gap is
        hours. The bound must sit clear of both rather than hug either.
        """
        assert _SAME_FIXTURE_MAX_SEPARATION >= timedelta(minutes=10)
        assert _SAME_FIXTURE_MAX_SEPARATION <= timedelta(hours=1)

    def test_a_runner_up_answering_to_a_different_espn_fixture_is_a_different_game(self):
        """It says what it is. Believe it."""
        other = _row(15290970, TWIN_TIME, espn_id="401816799")
        assert _proven_duplicates(_good(), [other], ESPN_CLAIM) == []

    def test_a_runner_up_with_a_probability_is_not_a_bare_twin(self):
        substantial = _row(15290970, TWIN_TIME, sources={"kalshi": {"value": 0.4}})
        assert _proven_duplicates(_good(), [substantial], ESPN_CLAIM) == []

    def test_a_runner_up_with_a_score_is_not_a_bare_twin(self):
        played = _row(15290970, TWIN_TIME, home_score=4, away_score=1)
        assert _proven_duplicates(_good(), [played], ESPN_CLAIM) == []

    def test_a_runner_up_with_a_zero_zero_score_is_still_substance(self):
        """0 is a score. `if not score` would read it as absence."""
        nil_nil = _row(15290970, TWIN_TIME, home_score=0, away_score=0)
        assert _proven_duplicates(_good(), [nil_nil], ESPN_CLAIM) == []

    def test_an_empty_sources_dict_is_not_substance(self):
        """`{}` is what the bare twin actually carries — absence, not content."""
        empty = _row(15290970, TWIN_TIME, sources={})
        assert [e.id for e in _proven_duplicates(_good(), [empty], ESPN_CLAIM)] == [15290970]

    def test_an_unanchored_claim_proves_nothing(self):
        """Ruling 048. Only a provider that dereferences its own id gets a say.

        This cannot be reached through the cascade — the gate in `_find_existing`
        stops it first — which is exactly why it is asserted here as well.

        THE SETUP IS THE TEST. Every OTHER guard is deliberately satisfied: the
        winner really does hold this StatPal fixture id, the twin really is bare
        and a minute away. The only thing standing between StatPal and the
        authority to declare two of our rows one game is `schedule_derived`, so
        this fails if and only if that gate is removed.

        Written the obvious way first — a StatPal claim against an ESPN-bound
        winner — it passed with the gate deleted, because the winner held no
        StatPal id and guard 2 caught it instead. A test that cannot tell which
        guard saved it is not testing either of them.
        """
        winner = _good()
        winner.statpal_fixture_id = "355422"
        unanchored = EventClaim("statpal", "355422", schedule_derived=False)

        assert _proven_duplicates(winner, [_twin()], unanchored) == []

        # ...and the same claim, anchored, WOULD prove it — so the assertion
        # above is about the flag and nothing else.
        anchored = EventClaim("statpal", "355422", schedule_derived=True)
        assert [e.id for e in _proven_duplicates(winner, [_twin()], anchored)] == [TWIN_ID]

    def test_a_winner_that_does_not_hold_the_claims_id_proves_nothing(self):
        """`_attach_claim` refused, so this fixture is not that row's game.

        A match we are already unsure of does not get to convict a third row.
        """
        wrong = _row(GOOD_ID, GOOD_TIME, espn_id="401816799")
        assert _proven_duplicates(wrong, [_twin()], ESPN_CLAIM) == []

    def test_the_winner_is_never_tagged_as_its_own_duplicate(self):
        winner = _good()
        assert _proven_duplicates(winner, [winner], ESPN_CLAIM) == []

    def test_no_runners_up_is_the_ordinary_case_and_costs_nothing(self):
        assert _proven_duplicates(_good(), [], ESPN_CLAIM) == []

    def test_a_timeless_row_is_never_judged(self):
        assert _proven_duplicates(_good(), [_row(1, None)], ESPN_CLAIM) == []
        assert _proven_duplicates(_row(1, None, espn_id=ESPN_FIXTURE), [_twin()], ESPN_CLAIM) == []

    def test_an_unloaded_row_is_never_tagged(self):
        """FAIL CLOSED. `__dict__.get` cannot tell "column is empty" from
        "column was never loaded", and those point opposite ways. Unloaded must
        read as substantial, because the alternative silently drops a real game
        from every surface and nothing reports it."""
        from app.services.event_registry import _has_substance

        twin = _twin()
        del twin.__dict__["win_probability_sources"]

        assert _has_substance(twin) is True
        assert _proven_duplicates(_good(), [twin], ESPN_CLAIM) == []

    def test_a_fully_loaded_bare_row_still_reads_as_no_substance(self):
        """The fail-closed arm must not swallow the ordinary case."""
        from app.services.event_registry import _has_substance

        assert _has_substance(_twin()) is False

    def test_several_twins_are_all_proven(self):
        """Nothing about the finding is limited to one runner-up."""
        twins = [_twin(), _row(15290971, GOOD_TIME + timedelta(minutes=2))]
        assert len(_proven_duplicates(_good(), twins, ESPN_CLAIM)) == 2


# ════════════════════════════════════════════════════════════════════════════
# Part B — the matcher stops discarding
# ════════════════════════════════════════════════════════════════════════════


class TestTheMatcherReturnsTheRunnersUp:
    @pytest.mark.asyncio
    async def test_red_first_the_old_return_dropped_the_twin(self):
        """The defect, stated as an assertion about the OLD contract.

        `_find_by_structured_match` is the pre-fix shape, preserved. It answers
        with one row. That answer is not wrong — it is incomplete, and this pins
        the exact information the old code destroyed: a second row matched, and
        nothing downstream could ever learn it.
        """
        session = _FakeRegistrySession(structured_candidates=[_good(), _twin()])

        winner = await _find_by_structured_match(
            session, S_MLB, "Detroit Tigers", "Los Angeles Dodgers",
            GOOD_TIME, claim=ESPN_CLAIM,
        )

        assert winner.id == GOOD_ID
        # ...and the twin is nowhere in that answer. One row in, one row out.

    @pytest.mark.asyncio
    async def test_structured_matches_returns_both_closest_first(self):
        session = _FakeRegistrySession(structured_candidates=[_twin(), _good()])

        matches = await _structured_matches(
            session, S_MLB, "Detroit Tigers", "Los Angeles Dodgers",
            GOOD_TIME, claim=ESPN_CLAIM,
        )

        assert [e.id for e in matches] == [GOOD_ID, TWIN_ID]

    @pytest.mark.asyncio
    async def test_the_single_answer_face_still_answers_singly(self):
        """Every existing caller and test reads `_find_by_structured_match`."""
        session = _FakeRegistrySession(structured_candidates=[_twin(), _good()])

        winner = await _find_by_structured_match(
            session, S_MLB, "Detroit Tigers", "Los Angeles Dodgers",
            GOOD_TIME, claim=ESPN_CLAIM,
        )

        assert winner.id == GOOD_ID

    @pytest.mark.asyncio
    async def test_no_match_returns_an_empty_list_not_none(self):
        session = _FakeRegistrySession(structured_candidates=[])

        assert await _structured_matches(
            session, S_MLB, "Detroit Tigers", "Los Angeles Dodgers",
            GOOD_TIME, claim=ESPN_CLAIM,
        ) == []

    @pytest.mark.asyncio
    async def test_an_unanchored_claim_still_cannot_reach_the_matcher(self):
        """Ruling 048's defence in depth survives the refactor."""
        session = _FakeRegistrySession(structured_candidates=[_good()])

        with pytest.raises(AssertionError, match="ruling 048"):
            await _structured_matches(
                session, S_MLB, "Detroit Tigers", "Los Angeles Dodgers",
                GOOD_TIME, claim=EventClaim("statpal", "355422"),
            )


# ════════════════════════════════════════════════════════════════════════════
# Part C — the read side, executed
# ════════════════════════════════════════════════════════════════════════════

UNTAGGED_ID = 1
NULL_TAGS_ID = 2
TAGGED_ID = 3
OTHER_TAGS_ID = 4


@pytest.fixture
def engine():
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(Sport(id=S_MLB, key="baseball_mlb", name="MLB"))
        s.add(_row(UNTAGGED_ID, GOOD_TIME, event_tags=["provenance:source:odds_api"]))
        s.add(_row(NULL_TAGS_ID, GOOD_TIME, event_tags=None))
        s.add(_row(TAGGED_ID, TWIN_TIME, event_tags=[duplicate_tag(UNTAGGED_ID)]))
        s.add(
            _row(
                OTHER_TAGS_ID,
                GOOD_TIME,
                event_tags=["provenance:source:statpal", "provenance:unanchored"],
            )
        )
        s.commit()
    return eng


def _admitted(eng):
    with Session(eng) as s:
        return sorted(
            s.execute(select(Event.id).where(not_a_proven_duplicate())).scalars().all()
        )


class TestTheReadSide:
    def test_a_proven_duplicate_is_not_printed(self, engine):
        assert TAGGED_ID not in _admitted(engine)

    def test_every_other_row_still_is(self, engine):
        """THE TRAP, and it is not hypothetical.

        `event_tags` is nullable and most rows carry no tags. A bare
        `NOT LIKE` evaluates to NULL — not TRUE — for those rows, so the naive
        predicate admits NOTHING and every rail it is added to renders empty.
        A guard that only checked the tagged row would have shipped that.
        """
        assert _admitted(engine) == [UNTAGGED_ID, NULL_TAGS_ID, OTHER_TAGS_ID]

    def test_a_row_carrying_OTHER_provenance_tags_is_untouched(self, engine):
        """`provenance:` is a shared prefix; only `duplicate-of:` excludes."""
        assert OTHER_TAGS_ID in _admitted(engine)

    def test_the_predicate_names_the_canonical_tag_prefix(self):
        """Read against the constant, so renaming the tag cannot silently
        disarm this without also failing here."""
        from app.services.anchor_channel import DUPLICATE_TAG_PREFIX

        compiled = str(
            select(Event.id)
            .where(not_a_proven_duplicate())
            .compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
        )
        assert DUPLICATE_TAG_PREFIX in compiled
        assert "IS NULL" in compiled

    def test_it_compiles_for_postgres(self):
        """SQLite agreeing is not Postgres agreeing."""
        compiled = str(
            select(Event.id)
            .where(not_a_proven_duplicate())
            .compile(dialect=postgresql.dialect())
        )
        assert "CAST" in compiled.upper()
        assert "NOT LIKE" in compiled.upper()


# ════════════════════════════════════════════════════════════════════════════
# Part D — the surfaces carry it
# ════════════════════════════════════════════════════════════════════════════


class TestEverySurfaceThatPrintsOneCardPerGame:
    """A predicate nobody calls is a predicate that fixes nothing.

    Compiled rather than executed: what is at stake is that the clause is IN the
    statement each surface builds. Part C already proved what the clause does.
    """

    @staticmethod
    def _carries_the_guard(statement) -> bool:
        from app.services.anchor_channel import DUPLICATE_TAG_PREFIX

        return DUPLICATE_TAG_PREFIX in str(
            statement.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        )

    def test_the_league_upcoming_rail(self):
        from app.routes.league_futures import upcoming_games_query

        assert self._carries_the_guard(upcoming_games_query("baseball_mlb", GOOD_TIME))

    def test_the_league_results_rail(self):
        from app.routes.league_futures import recent_results_query

        assert self._carries_the_guard(recent_results_query("baseball_mlb", GOOD_TIME))

    def test_the_feed_candidate_pass(self):
        from app.utils.feed_event_candidates import event_candidate_ids

        assert self._carries_the_guard(
            event_candidate_ids([Event.status == "live"])
        )

    def test_the_feed_guard_does_not_replace_the_exact_collapse(self):
        """Both guards, not one. They catch disjoint populations: the collapse
        fuses byte-identical restatements (#2065's 291-copy esports rows), this
        drops a proven near-miss twin (#2263's one-minute MLB rows). Deleting
        either re-opens its own incident."""
        from app.utils.feed_event_candidates import event_candidate_ids

        compiled = str(
            event_candidate_ids([Event.status == "live"]).compile(
                dialect=postgresql.dialect()
            )
        )
        assert "row_number" in compiled.lower()
        assert "PARTITION BY events.sport_id, events.home_team_name" in compiled

    def test_the_team_page_rails(self):
        """Same shape, same gap — asserted through the module source because
        both queries are built inline inside the request handler."""
        import inspect

        from app.routes import teams

        source = inspect.getsource(teams)
        assert source.count("not_a_proven_duplicate()") == 2

    def test_the_two_search_surfaces(self):
        """CERT-439's finding, pinned in the ordinary suite.

        The cert blocked this ship for one reason: the league, team and feed
        rails consumed the proof and `/api/events/search` did not, so a tagged
        row vanished from three surfaces and stayed a separate search result on
        the fourth. The product then answered "one game" or "two games"
        according to how the user navigated to it, off the same global identity
        finding.

        SEVEN call sites, and the number is the assertion:

          `/search`             `event_scope_conditions` — the list the two UNION
                                recall arms, the outer entity query, the
                                identity-only count and the substring-existence
                                guard are all built from
          `/search`             `fuzzy_conditions` — replaces `query` and
                                `total_count` wholesale, so it needs its own
          `/typeahead`          the dropdown event pool
          `/typeahead`          the dropdown's fuzzy pool
          `/search-suggestions` live close games · starting soon · recent upsets
                                — the search box's zero state, eight chips across
                                four sources

        All three suggestion sources carry it, not only "starting soon" — the
        one a twin reaches today. "This query cannot return a tagged row anyway"
        is an argument about the SHAPE of the twins we have seen (bare,
        score-less, source-less), and the tag makes no claim about shape. It
        says this row is not a game to print.

        A source count rather than a compiled statement because every one is
        built inline inside its request handler, exactly as the team rails are.
        What this cannot prove is that the clause changes the ANSWER — that is
        `tests/integration/test_search_proven_duplicate_pg.py`, which drives the
        routes against a real PostgreSQL with a tagged/untagged control. This
        one catches the deletion; that one catches the lie.
        """
        import inspect

        from app.routes import events

        source = inspect.getsource(events)
        assert source.count("not_a_proven_duplicate()") == 7, (
            "one of the seven search-surface call sites is gone — see CERT-439"
        )

    def test_the_behavioural_search_gate_exists_and_is_wired_into_ci(self):
        """A guard suite nobody runs is a guard suite that proves nothing.

        The real-Postgres file above is invisible to `backend-tests`' four
        shards in the sense that matters — its cases are all `needs_postgres`
        and skip there. It only grades anything inside the `search-recall` job,
        and that job names each of its integration files EXPLICITLY. A file
        added without its step is a gate that exists and never runs, which is
        the failure `test_tag_counts_real_postgres.py`'s own job step was
        written to end.
        """
        from pathlib import Path

        repo = Path(__file__).resolve().parents[2]
        gate = repo / "backend/tests/integration/test_search_proven_duplicate_pg.py"
        assert gate.exists(), "the behavioural CERT-439 gate is missing"

        workflow = (repo / ".github/workflows/ci.yml").read_text()
        assert "tests/integration/test_search_proven_duplicate_pg.py" in workflow, (
            "the CERT-439 gate is not named by any CI step, so it never runs"
        )


# ════════════════════════════════════════════════════════════════════════════
# Part E — the reader cannot drift from the writer
# ════════════════════════════════════════════════════════════════════════════


class TestTheIdColumnMap:
    def test_every_mapped_column_is_the_one_attach_claim_writes(self):
        """`_proven_duplicates` asks "does this row hold the claim's id?" and
        `_attach_claim` is what puts it there. If the map and the writer ever
        name different columns the guard reads a column nobody writes, silently
        answers None, every runner-up looks unbound — and it starts OVER-tagging,
        which is the one direction this design refuses to fail in.

        The map is `SCALAR_DERIVED_ID_COLUMNS` rather than a private copy, so
        this is checking the shared constant against the writer, not two local
        lists against each other.
        """
        from app.utils.provider_anchor_keys import SCALAR_DERIVED_ID_COLUMNS

        assert SCALAR_DERIVED_ID_COLUMNS, "an empty map would vacuously pass"

        for source, column in SCALAR_DERIVED_ID_COLUMNS.items():
            event = _row(1, GOOD_TIME, espn_id=None)
            event.external_id = None
            event.statpal_fixture_id = None

            assert (
                _attach_claim(
                    event,
                    EventClaim(source, "written-by-attach"),
                    espn_id_is_held=False,
                )
                is True
            )
            assert getattr(event, column) == "written-by-attach", (
                f"_attach_claim({source!r}) did not write {column!r}"
            )

    def test_claim_id_value_reads_what_attach_claim_wrote(self):
        """The round trip, through the function `_proven_duplicates` calls."""
        from app.services.event_registry import _claim_id_value
        from app.utils.provider_anchor_keys import SCALAR_DERIVED_ID_COLUMNS

        for source in SCALAR_DERIVED_ID_COLUMNS:
            event = _row(1, GOOD_TIME, espn_id=None)
            event.external_id = None
            event.statpal_fixture_id = None

            assert _claim_id_value(event, source) is None
            _attach_claim(
                event, EventClaim(source, "round-trip"), espn_id_is_held=False
            )
            assert _claim_id_value(event, source) == "round-trip"

    def test_a_source_with_no_id_column_reads_as_unbound(self):
        """Kalshi and Polymarket have no column; None is the correct answer."""
        from app.services.event_registry import _claim_id_value

        assert _claim_id_value(_good(), "kalshi") is None
        assert _claim_id_value(_good(), "polymarket") is None


# ════════════════════════════════════════════════════════════════════════════
# Part F — the FOLD: what the suppressed row was holding (#2693)
# ════════════════════════════════════════════════════════════════════════════
#
# Parts C and D prove the second card stops printing. That is only half of "one
# match, one card": on the population this tag was written for, the suppressed
# row is usually the one holding the PRICES.
#
#     ghosts carrying at least one market            110 / 172
#     ghosts carrying MORE markets than their own
#       canonical                                     63 / 172
#     Andreeva/Potapova QF, 2026-09-07     ghost 13 markets, canonical  0
#     Cerundolo/Blockx   QF, 2026-09-07    ghost 17 markets, canonical  1
#
# So `not_a_proven_duplicate` alone, applied to those two, does not remove a
# duplicate card — it removes the only card with prices. `folded_event_ids` is
# the reverse lookup that lets the surviving card read them.

CANON_ID = 15305578
GHOST_ID = 15305553
DECOY_ID = 1530  # a PREFIX of CANON_ID — see the trap below
UNRELATED_ID = 99

# Part G's fixture — the same production pair, served through the real route.
S_TENNIS = 77
QF_TIME = datetime(2026, 9, 7, 17, 0, tzinfo=timezone.utc)
E2E_MARKET_ID = 901


class _SyncAsAsync:
    """The one `await db.execute(...)` `folded_event_ids` makes, over a sync Session.

    `folded_event_ids` is async because every caller is; the statement it runs is
    ordinary SQLAlchemy Core. This shim lets Part F execute it against the same
    real engine Part C uses rather than assert on a mock's call args.
    """

    def __init__(self, session):
        self._session = session

    async def execute(self, statement):
        return self._session.execute(statement)


@pytest.fixture
def fold_engine():
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(Sport(id=S_MLB, key="baseball_mlb", name="MLB"))
        s.add(_row(CANON_ID, GOOD_TIME, event_tags=None))
        s.add(_row(GHOST_ID, TWIN_TIME, event_tags=[duplicate_tag(CANON_ID)]))
        s.add(_row(DECOY_ID, GOOD_TIME, event_tags=None))
        s.add(_row(UNRELATED_ID, GOOD_TIME, event_tags=[duplicate_tag(DECOY_ID)]))
        s.commit()
    return eng


def _folded(eng, event_id):
    import asyncio

    from app.utils.proven_duplicates import folded_event_ids

    with Session(eng) as s:
        return asyncio.run(folded_event_ids(_SyncAsAsync(s), event_id))


class TestTheFold:
    def test_the_canonical_reads_its_suppressed_twins_content(self, fold_engine):
        """The ship: `/events/15305578` gets `15305553`'s 17 markets."""
        assert _folded(fold_engine, CANON_ID) == [CANON_ID, GHOST_ID]

    def test_an_untagged_event_folds_to_exactly_itself(self, fold_engine):
        """🔴 The no-change case, and it is the overwhelming majority.

        Almost every event on the site has no duplicate. If this ever returned
        `[]` the caller's `event_id.in_(...)` would become `IN ()` and every
        event page on the site would lose every market at once — so the
        canonical is unconditionally first and unconditionally present.
        """
        assert _folded(fold_engine, DECOY_ID + 7) == [DECOY_ID + 7]

    def test_a_shorter_canonical_id_does_not_claim_a_longer_ones_duplicates(
        self, fold_engine
    ):
        """🔴 THE TRAP. `duplicate-of:1530` is a prefix of `duplicate-of:15305578`.

        The portable arm is a LIKE, so an unquoted pattern would fold a
        completely unrelated match's markets onto this page — and the failure is
        silent, because extra markets on a busy page look like coverage. The
        element is matched WITH its quotes for exactly this reason.
        """
        assert _folded(fold_engine, DECOY_ID) == [DECOY_ID, UNRELATED_ID]
        assert GHOST_ID not in _folded(fold_engine, DECOY_ID)

    def test_a_row_tagged_as_its_own_duplicate_is_not_returned_twice(self):
        """Defensive: `IN (x, x)` is harmless, a duplicated market row is not."""
        eng = create_engine("sqlite://")
        Base.metadata.create_all(eng)
        with Session(eng) as s:
            s.add(Sport(id=S_MLB, key="baseball_mlb", name="MLB"))
            s.add(_row(CANON_ID, GOOD_TIME, event_tags=[duplicate_tag(CANON_ID)]))
            s.commit()
        assert _folded(eng, CANON_ID) == [CANON_ID]

    def test_the_postgres_rendering_is_the_one_the_gin_index_can_answer(self):
        """🔴 THE PERFORMANCE CONTRACT, pinned because it fails silently.

        Measured on production 2026-09-07, `EXPLAIN (ANALYZE, BUFFERS)` root node
        for the same single row:

            event_tags @> '["provenance:duplicate-of:15304938"]'
                Bitmap Index Scan, ix_events_event_tags     5 blocks     0.06 ms
            CAST(event_tags AS text) LIKE '%"…:15304938"%'
                Seq Scan                              105,540 blocks  8,296 ms

        A fall back to the portable arm on Postgres keeps every test in this
        file green and puts an eight-second table scan on every event page.
        SQLite agreeing is not Postgres agreeing.
        """
        from app.utils.proven_duplicates import tagged_duplicate_of

        compiled = str(
            select(Event.id)
            .where(tagged_duplicate_of(CANON_ID))
            .compile(dialect=postgresql.dialect())
        )
        assert "@>" in compiled
        assert "LIKE" not in compiled.upper()
        assert "CAST(events.event_tags AS VARCHAR)" not in compiled

    def test_the_fold_and_the_suppression_read_the_same_tag(self):
        """One writer, one tag, two readers. They cannot be allowed to drift."""
        from sqlalchemy.dialects import sqlite as sqlite_dialect

        from app.services.anchor_channel import DUPLICATE_TAG_PREFIX
        from app.utils.proven_duplicates import tagged_duplicate_of

        compiled = str(
            select(Event.id)
            .where(tagged_duplicate_of(CANON_ID))
            .compile(
                dialect=sqlite_dialect.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        )
        assert f'"{DUPLICATE_TAG_PREFIX}{CANON_ID}"' in compiled

    def test_a_folded_market_survives_a_ticker_date_the_canonical_does_not_share(self):
        """🔴 THE HAZARD THE FOLD CREATES, and the measurement that closes it.

        `_build_game_markets` runs `filter_foreign_game_markets(markets,
        event.commence_time.date())` immediately after the fold — and the ghost's
        Kalshi tickers do NOT carry the canonical's date. All six US Open
        quarter-finals on 2026-09-07 have this shape:

            ghost ticker   KXATPMATCH-26SEP06CERBLO     -> 2026-09-06
            canonical      commence_time                -> 2026-09-07 17:00Z

        A date-keyed filter reading the CANONICAL's date over the GHOST's tickers
        is exactly how a fold turns into a silent no-op (gotcha #53): the markets
        arrive and are dropped one line later, the page looks unchanged, and the
        repair reports success.

        It does not happen, and the reason is structural rather than lucky: a
        twin is the SAME matchup, so the folded markets carry the same team code,
        and `filter_foreign_game_markets` short-circuits at
        `len(team_codes) <= 1` before it consults a date at all. Verified against
        the real production external_ids for 15305578 + 15305553 — 18/18 kept
        under Sep 7, and 18/18 under Sep 6 as well.

        The filter's own suite is `test_foreign_game_markets.py`; this case lives
        here because the input shape is the fold's, not the filter's.
        """
        from datetime import date
        from types import SimpleNamespace

        from app.utils.prediction_market_matching import filter_foreign_game_markets

        folded = [
            SimpleNamespace(id=1, external_id="972932"),  # the canonical's own
            SimpleNamespace(id=2, external_id="KXATPMATCH-26SEP06CERBLO"),
            SimpleNamespace(id=3, external_id="KXATPEXACTMATCH-26SEP06CERBLO"),
            SimpleNamespace(id=4, external_id="0xb7299024535d27679bef5f29ce57"),
        ]
        kept = filter_foreign_game_markets(folded, date(2026, 9, 7))
        assert [m.id for m in kept] == [1, 2, 3, 4]

    def test_a_fold_that_brought_a_SECOND_matchup_is_still_filtered(self):
        """The other direction (gotcha #43): the safety net must still bite.

        If the fold ever carried in a genuinely foreign game's markets, two team
        codes are present, the date decides, and the foreign one is dropped. A
        test that only proved the survival case above would have licensed
        removing the filter.
        """
        from datetime import date
        from types import SimpleNamespace

        from app.utils.prediction_market_matching import filter_foreign_game_markets

        mixed = [
            SimpleNamespace(id=1, external_id="KXATPMATCH-26SEP07CERBLO"),
            SimpleNamespace(id=2, external_id="KXATPMATCH-26SEP07SINALC"),
            SimpleNamespace(id=3, external_id="KXATPMATCH-26SEP06SINALC"),
        ]
        # Two team codes, so the date is consulted: SINALC is the code with a
        # ticker on the event's own day, CERBLO is the foreign game and goes.
        kept = [m.id for m in filter_foreign_game_markets(mixed, date(2026, 9, 6))]
        assert kept == [2, 3]

    def test_the_event_pages_market_read_actually_carries_the_fold(self):
        """Part D's discipline: a predicate nothing calls repairs nothing.

        `_build_game_markets` is the read that populates
        `GET /api/events/{id}/game-markets` — measured on production as 32
        market entries on the ghost against 3 on the canonical, which is the
        gap this ship closes.
        """
        import inspect

        from app.routes.events import _build_game_markets

        source = inspect.getsource(_build_game_markets)
        assert "folded_event_ids" in source
        assert "FuturesMarket.event_id.in_(market_event_ids)" in source
        assert "FuturesMarket.event_id == event_id" not in source


# ════════════════════════════════════════════════════════════════════════════
# Part G — the two halves in ONE response (UNPLAYED-TWIN-FOLD-END-TO-END-2693)
# ════════════════════════════════════════════════════════════════════════════
#
# CERT-2172's named nonblocking follow-up. Everything above proves the halves
# SEPARATELY: Part C proves the tag suppresses the second card, Part F proves
# `folded_event_ids` resolves the tag to a list, and the test directly above
# proves the route mentions it — by `inspect.getsource`, which is a grep. A
# grep cannot tell you the payload changed; it survives a caller that computes
# `market_event_ids` and then never puts it in the query, and it survives every
# way the markets could be dropped downstream of the fold (the ticker-date
# filter one line later being the specific hazard Part F's first case covers).
#
# So this part runs the REAL `_build_game_markets` against a real engine and
# asserts on the body a user is served. The two arms are seeded identically and
# differ in exactly one field — the ghost's `event_tags`. That single-variable
# contrast is what joins the halves: the tag is shown to be the thing that moves
# the prices onto the surviving card, rather than the fold happening to work.


def _fold_e2e_engine(*, tagged: bool):
    """Canonical + ghost for one real fixture; the ghost holds the market.

    The production shape (#2693): US Open QF Cerundolo–Blockx, where the row we
    have declined to print is the row carrying the prices. `tagged=False` is the
    control — the SAME two events and the SAME market, with only the provenance
    tag removed.
    """
    from app.models.models import FuturesMarket, FuturesOutcome

    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(Sport(id=S_TENNIS, key="tennis_atp", name="ATP"))
        for row_id in (CANON_ID, GHOST_ID):
            s.add(
                Event(
                    id=row_id,
                    sport_id=S_TENNIS,
                    home_team_name="Cerundolo",
                    away_team_name="Blockx",
                    commence_time=QF_TIME,
                    status="scheduled",
                    event_tags=(
                        [duplicate_tag(CANON_ID)]
                        if tagged and row_id == GHOST_ID
                        else None
                    ),
                )
            )
        # The ghost's market, with the ghost's OWN Kalshi ticker — note the
        # `26SEP06` against a canonical stamped Sep 7 (Part F's hazard).
        s.add(
            FuturesMarket(
                id=E2E_MARKET_ID,
                event_id=GHOST_ID,
                sport_id=S_TENNIS,
                source="kalshi",
                external_id="KXATPEXACTMATCH-26SEP06CERBLO",
                name="Cerundolo vs Blockx - Exact Score",
                category="game",
                llm_sport_category="tennis",
                market_type="game_prop",
                status="open",
            )
        )
        s.add(
            FuturesOutcome(
                id=8001,
                market_id=E2E_MARKET_ID,
                external_id="CERBLO-3-1",
                name="Francisco Cerundolo 3-1",
                current_probability=0.10,
            )
        )
        s.add(
            FuturesOutcome(
                id=8002,
                market_id=E2E_MARKET_ID,
                external_id="CERBLO-3-0",
                name="Francisco Cerundolo 3-0",
                current_probability=0.08,
            )
        )
        s.commit()
    return eng


def _served_game_markets(eng, event_id):
    """`GET /api/events/{id}/game-markets`'s builder, actually executed."""
    import asyncio

    from app.routes.events import _build_game_markets

    with Session(eng) as s:
        return asyncio.run(_build_game_markets(event_id, _SyncAsAsync(s)))


class TestTheFoldEndToEnd:
    def test_the_canonicals_page_is_SERVED_the_ghosts_priced_market(self):
        """🔴 THE SHIP, in the payload: the unplayed QF prints its prices.

        Before #2693 this response was empty on the canonical while the ghost —
        the row we suppress — served the Exact Score ladder. A user opening the
        one card we print saw no prices at all.
        """
        response, _status, market_ids = _served_game_markets(
            _fold_e2e_engine(tagged=True), CANON_ID
        )

        assert market_ids == [E2E_MARKET_ID]
        other = response["other"]
        assert [o["outcome_name"] for o in other] == [
            "Francisco Cerundolo 3-1",
            "Francisco Cerundolo 3-0",
        ]
        assert [o["probability"] for o in other] == [0.10, 0.08]
        assert {o["market_name"] for o in other} == {
            "Cerundolo vs Blockx - Exact Score"
        }

    def test_without_the_TAG_the_same_market_never_arrives(self):
        """🔴 The control, and the only reason the case above proves anything.

        Identical events, identical market, identical outcomes — the ghost's
        `event_tags` is the single field that differs. If this ever passes
        alongside the case above, the fold has stopped reading the tag and is
        reaching markets by some other route (a name/time join, say), which is
        precisely the name-and-time absorption ruling 048 bans.
        """
        response, _status, market_ids = _served_game_markets(
            _fold_e2e_engine(tagged=False), CANON_ID
        )

        assert market_ids == []
        assert response["other"] == []
