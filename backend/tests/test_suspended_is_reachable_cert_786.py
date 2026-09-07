"""A STATE NOBODY CAN REACH IS NOT A BETTER LIE — live/048, CERT-786.

═══ WHY THIS SUITE EXISTS ═══

live/048 was right and incomplete, and CERT-786 named the gap precisely: the
backend stopped writing a false Final onto a rain-delayed match, wrote
``suspended`` instead, and then no discovery surface admitted the word. The
match did not render wrongly. It rendered nowhere.

    ``routes/feed.py``   admitted live | scheduled | completed | closed
    ``routes/events.py`` did the same, twice, and again in search

So the ship inverted itself. A reader looking for the US Open match that was
1-2 in sets used to find a card that said Final; after live/048 they found
nothing at all. The second answer is not an improvement on the first — it is the
same wrong claim with no card to argue with, and it is harder to report as a bug.

**The general clause: a new state in a vocabulary is not shipped when the
producer writes it. It is shipped when every consumer that dispatches on that
vocabulary has been shown the word.** Producing a truer value into a set of
readers that silently drop it converts a display defect into an absence, and
absence is the one defect class users cannot describe.

═══ WHAT IS TESTED HERE, AND WHAT IS NOT ═══

Everything below runs the REAL object — the predicate the route calls, the
filter the feed calls, the tier expression the quota pass compiles. Nothing in
this file re-implements a predicate and then asserts on its re-implementation;
that is the failure mode that let CERT-786 through in the first place, because
``test_feed_event_candidates`` held a hand-written copy of the feed's window
predicate whose docstring claimed to be "the exact predicate ``_score_events``
accumulates". It was, until it wasn't, and nothing said so. That copy is gone
(``candidate_window_conditions``); these tests import what production imports.

Card rendering is the frontend's half and is guarded in
``frontend/__tests__/lib/suspendedIsFirstClassCert786.test.ts`` and
``frontend/__tests__/components/suspendedCardsCert786.test.tsx``.

═══ RED-FIRST ═══

``TestTheDefectReproduces`` rebuilds the PRE-FIX predicate over the same corpus
and shows the suspended row absent from it. Without that, every admission test
below could be passing over a corpus that the old code would also have admitted,
and the suite would certify nothing.

``TestTheHealthyDirectionIsUntouched`` holds the controls, and they are chosen
to be green in BOTH arms: they route only through symbols that predate this
change. A "control" that goes red without the fix proves the fix is absent, not
that the fix is narrow.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import and_, create_engine, or_, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Session

# SQLite cannot render Postgres-native column types. DDL shims for the sqlite
# dialect ONLY — production is Postgres and never reaches them. Same shims as
# `test_feed_event_candidates`, and for the same reason: without them `events`
# cannot be created and this module degrades to shape-only coverage.


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


from app.models import Event, Sport  # noqa: E402
from app.models.models import Base  # noqa: E402
from app.routes.events import (  # noqa: E402
    EVENT_LIST_DEFAULT_STATUSES,
    _SEARCH_STARTED_STATUSES,
    _SEARCH_STATUSES,
    event_list_window_condition,
)
from app.routes.feed import _filter_discover_event_noise  # noqa: E402
from app.utils.event_completion import (  # noqa: E402
    EVENT_SUSPENDED,
    SETTLED_STATUSES,
)
from app.utils.feed_event_candidates import (  # noqa: E402
    TIER_QUOTAS,
    TIER_RECENT,
    TIER_SUSPENDED,
    candidate_window_conditions,
    event_candidate_ids,
    status_tier_expr,
)
from app.utils.lifecycle import served_event_status  # noqa: E402
from app.utils.tonights_games import select_tonights_games  # noqa: E402

NOW = datetime(2026, 9, 2, 19, 0, 0, tzinfo=timezone.utc)

S_TENNIS = 1
S_ESPORTS = 2

# The CERT-752 specimen: De Jong v Passaro, US Open, 1-2 in sets, ~15 hours past
# its recorded start, suspended and scheduled to resume. This is the row the
# whole ladder was built for, so it is the row the reachability tests use.
SPECIMEN_ID = 15295047
SPECIMEN_COMMENCE = NOW - timedelta(hours=15)

LIVE_ID = 900_001
SCHEDULED_ID = 900_002
FINISHED_ID = 900_003
#: Suspended, but older than the window it shares with a Final. It must be
#: absent — "admit the state" is not "admit it forever".
STALE_SUSPENDED_ID = 900_004

ESPORTS_ID_BASE = 100_000


def _windows(now=NOW):
    """The anonymous Discover path's windows (1h live buffer, 12h up, 24h back)."""
    return dict(
        now=now,
        live_start_cutoff=now + timedelta(hours=1),
        upcoming_cutoff=now + timedelta(hours=12),
        recent_cutoff=now - timedelta(hours=24),
    )


def _conditions(now=NOW):
    return candidate_window_conditions(**_windows(now))


def _pre_fix_conditions(now=NOW):
    """The predicate as it stood BEFORE live/048 — three arms, no suspended.

    Hand-written ON PURPOSE and only here: this is the one place in the repo
    where a copy is the point, because it is the artefact under test rather than
    a stand-in for the real thing.
    """
    return [
        or_(
            and_(
                Event.status == "live",
                Event.commence_time <= now + timedelta(hours=1),
            ),
            and_(
                Event.status == "scheduled",
                Event.commence_time >= now,
                Event.commence_time <= now + timedelta(hours=12),
            ),
            and_(
                Event.status.in_(["completed", "closed"]),
                Event.commence_time >= now - timedelta(hours=24),
            ),
        )
    ]


def _event(
    eid,
    sport_id,
    home,
    away,
    commence_time,
    status,
    *,
    home_score=None,
    away_score=None,
):
    return Event(
        id=eid,
        sport_id=sport_id,
        external_id=f"ext-{eid}",
        home_team_name=home,
        away_team_name=away,
        commence_time=commence_time,
        status=status,
        home_score=home_score,
        away_score=away_score,
    )


def _seed(session, rows):
    session.add(Sport(id=S_TENNIS, key="tennis_atp_us_open", name="US Open"))
    session.add(Sport(id=S_ESPORTS, key="esports_lol", name="LoL"))
    session.add_all(rows)
    session.commit()


def _slate():
    """One row per state, all inside their windows except the stale one."""
    return [
        _event(
            SPECIMEN_ID,
            S_TENNIS,
            "Passaro",
            "De Jong",
            SPECIMEN_COMMENCE,
            EVENT_SUSPENDED,
            home_score=2,
            away_score=1,
        ),
        _event(LIVE_ID, S_TENNIS, "H", "A", NOW - timedelta(hours=1), "live"),
        _event(
            SCHEDULED_ID, S_TENNIS, "H2", "A2", NOW + timedelta(hours=3), "scheduled"
        ),
        _event(
            FINISHED_ID,
            S_TENNIS,
            "H3",
            "A3",
            NOW - timedelta(hours=3),
            "completed",
            home_score=3,
            away_score=0,
        ),
        _event(
            STALE_SUSPENDED_ID,
            S_ESPORTS,
            "H4",
            "A4",
            NOW - timedelta(days=4),
            EVENT_SUSPENDED,
        ),
    ]


@pytest.fixture()
def engine():
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng, tables=[Sport.__table__, Event.__table__])
    return eng


@pytest.fixture()
def slate(engine):
    with Session(engine) as s:
        _seed(s, _slate())
        yield s


def _admitted(session, conditions=None):
    stmt = event_candidate_ids(conditions or _conditions())
    return {r[0] for r in session.execute(stmt).all()}


def _matching(session, condition):
    """Ids satisfying a bare SQLAlchemy condition — for the events-list gates."""
    return {
        r[0] for r in session.execute(select(Event.id).where(condition)).all()
    }


# ---------------------------------------------------------------------------
# 0 — the corpus really does reproduce the defect
# ---------------------------------------------------------------------------


class TestTheDefectReproduces:
    def test_the_pre_fix_feed_predicate_loses_the_specimen(self, slate):
        """The whole cert in one assertion: the match vanishes from Discover."""
        before = _admitted(slate, _pre_fix_conditions())
        assert SPECIMEN_ID not in before
        # …while every other state on the same slate is admitted, so the corpus
        # is exercising the suspended arm and not a broken fixture.
        assert {LIVE_ID, SCHEDULED_ID, FINISHED_ID} <= before

    def test_the_pre_fix_events_list_default_loses_the_specimen(self, slate):
        pre_fix_default = ["scheduled", "live", "completed", "closed"]
        assert SPECIMEN_ID not in _matching(
            slate, Event.status.in_(pre_fix_default)
        )

    def test_the_pre_fix_search_scope_loses_the_specimen(self, slate):
        pre_fix_scope = ["scheduled", "live", "completed", "closed"]
        assert SPECIMEN_ID not in _matching(slate, Event.status.in_(pre_fix_scope))


# ---------------------------------------------------------------------------
# 1 — the feed's candidate pass admits it
# ---------------------------------------------------------------------------


class TestDiscoverAdmitsSuspended:
    def test_the_route_actually_uses_the_shared_predicate(self):
        """The wiring, asserted structurally — because everything else in this
        class tests the shared function, and a shared function the route has
        stopped calling is a test suite certifying a dead code path.

        An AST walk over ``_score_events`` rather than a substring search: a
        grep is satisfied by the name appearing in a comment, and this file's
        own header is full of them.
        """
        import ast
        import inspect

        from app.routes import feed as feed_module

        tree = ast.parse(inspect.getsource(feed_module._score_events))
        called = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert "candidate_window_conditions" in called, (
            "_score_events no longer builds its candidate predicate from the "
            "shared definition — every admission test below is now testing a "
            "function the feed does not call"
        )

    def test_the_specimen_is_a_candidate(self, slate):
        assert SPECIMEN_ID in _admitted(slate)

    def test_admitting_it_costs_no_other_state_its_place(self, slate):
        """Both directions (gotcha #43): the new arm admits AND does not evict."""
        assert {LIVE_ID, SCHEDULED_ID, FINISHED_ID} <= _admitted(slate)

    def test_it_ages_out_where_the_final_it_replaced_would_have(self, slate):
        """`suspended` shares the finished window, so it shares the expiry.

        Without this the state becomes a permanent shelf: the measured
        population is ~500 rows/day, 89% of them fixtures whose only source went
        dark, and none of those will ever resume or settle. Admitting them
        without a floor is how the honest state becomes a landfill.
        """
        assert STALE_SUSPENDED_ID not in _admitted(slate)


# ---------------------------------------------------------------------------
# 2 — the quota tier, which is why it is not simply "recent"
# ---------------------------------------------------------------------------


class TestSuspendedHasItsOwnFloor:
    def test_it_is_tiered_as_suspended_not_as_scheduled(self):
        sql = str(
            select(status_tier_expr()).compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
            )
        )
        assert f"'suspended') THEN {TIER_SUSPENDED}" in sql

    def test_a_suspended_flood_cannot_starve_just_happened(self, engine):
        """The reason `suspended` got a tier instead of joining RECENT_STATUSES.

        A suspended row IS recent, and adding it to `RECENT_STATUSES` would have
        reintroduced #2065 in miniature: the recent tier's deduplicated size on
        production is 144 against a quota of 150, so six slots of slack would
        have stood between a night of esports outages and an empty "Just
        Happened". The floor is the fix; this drives it.
        """
        rows = []
        # A flood: more distinct suspended fixtures than the whole budget.
        for i in range(TIER_QUOTAS[TIER_SUSPENDED] + 400):
            rows.append(
                _event(
                    ESPORTS_ID_BASE + i,
                    S_ESPORTS,
                    f"H{i}",
                    f"A{i}",
                    NOW - timedelta(minutes=30 + i),
                    EVENT_SUSPENDED,
                )
            )
        real_finished = list(range(800_000, 800_000 + 120))
        for eid in real_finished:
            rows.append(
                _event(
                    eid,
                    S_TENNIS,
                    f"HF{eid}",
                    f"AF{eid}",
                    NOW - timedelta(hours=2),
                    "completed",
                    home_score=1,
                    away_score=0,
                )
            )
        with Session(engine) as s:
            _seed(s, rows)
            admitted = _admitted(s)
            flood = {i for i in admitted if i < 800_000}
            assert len(flood) == TIER_QUOTAS[TIER_SUSPENDED]
            # …and every real finished game survives it.
            assert set(real_finished) <= admitted

    def test_the_suspended_quota_is_named_in_the_compiled_sql(self):
        """A quota silently edited to zero would empty the tier while every
        behavioural test above still passed on its own fixture size."""
        sql = str(
            event_candidate_ids(_conditions()).compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
            )
        )
        assert (
            f"= {TIER_SUSPENDED}) THEN {TIER_QUOTAS[TIER_SUSPENDED]}" in sql
        )


# ---------------------------------------------------------------------------
# 3 — the events list and search, both gates
# ---------------------------------------------------------------------------


class TestEventsListAndSearchAdmitSuspended:
    def test_the_default_status_set_reaches_it(self, slate):
        assert SPECIMEN_ID in _matching(
            slate, Event.status.in_(EVENT_LIST_DEFAULT_STATUSES)
        )

    def test_the_time_window_reaches_it_too(self, slate):
        """TWO gates, ANDed. Passing one is not being reachable — this is why
        CERT-786 named `routes/events.py` twice rather than once."""
        window = event_list_window_condition(
            now=NOW,
            end_date=NOW + timedelta(days=7),
            recent_start=NOW - timedelta(days=1),
        )
        assert SPECIMEN_ID in _matching(slate, window)

    def test_both_gates_together_reach_it(self, slate):
        window = event_list_window_condition(
            now=NOW,
            end_date=NOW + timedelta(days=7),
            recent_start=NOW - timedelta(days=1),
        )
        both = and_(Event.status.in_(EVENT_LIST_DEFAULT_STATUSES), window)
        assert SPECIMEN_ID in _matching(slate, both)

    def test_search_reaches_it_with_and_without_upcoming(self, slate):
        """`include_upcoming=False` means "has already started", and a suspended
        match has — the one thing about it nothing disputes."""
        assert SPECIMEN_ID in _matching(slate, Event.status.in_(_SEARCH_STATUSES))
        assert SPECIMEN_ID in _matching(
            slate, Event.status.in_(_SEARCH_STARTED_STATUSES)
        )

    def test_an_explicit_status_filter_is_unaffected(self, slate):
        """Widening a DEFAULT must not widen an explicit request. A caller
        asking for `completed` still gets exactly completed rows."""
        assert _matching(slate, Event.status == "completed") == {FINISHED_ID}


# ---------------------------------------------------------------------------
# 4 — the Discover noise filter
# ---------------------------------------------------------------------------


def _feed_item(status, *, media=True, score=35):
    return {
        "type": "event",
        "score": score,
        "data": {
            "id": SPECIMEN_ID,
            "status": status,
            "home_team": "Passaro",
            "away_team": "De Jong",
            "home_score": 2,
            "away_score": 1,
            "commence_time": SPECIMEN_COMMENCE.isoformat(),
            **(
                {
                    "home_team_data": {"logo_small": "h.png"},
                    "away_team_data": {"logo_small": "a.png"},
                }
                if media
                else {}
            ),
        },
    }


class TestDiscoverNoiseFilterKeepsTheMatch:
    def test_a_suspended_game_with_team_media_survives(self):
        """The arm a live game already had, and needs more.

        Events are demoted to 35 before this filter runs and the filter drops
        anything under 45, so the live arm is the ONLY thing keeping a game card
        on Discover. A live match going into a rain delay crossed straight from
        "kept by the live arm" to "dropped by the score check", with no branch
        in between — the card left the surface it was already on at the exact
        moment it had something unusual and true to say.
        """
        kept = _filter_discover_event_noise([_feed_item(EVENT_SUSPENDED)])
        assert [i["data"]["id"] for i in kept] == [SPECIMEN_ID]

    def test_a_suspended_fixture_with_no_team_media_still_does_not(self):
        """`has_team_media` is load-bearing, not ceremony. 89% of the measured
        suspended population is esports with no linked teams; this admits the
        match a reader was watching, not the mass behind it."""
        assert _filter_discover_event_noise([_feed_item(EVENT_SUSPENDED, media=False)]) == []


# ---------------------------------------------------------------------------
# 5 — the healthy direction. Controls: green in BOTH arms.
# ---------------------------------------------------------------------------


class TestTheHealthyDirectionIsUntouched:
    """Every case here routes ONLY through symbols that predate live/048.

    A control that goes red against pre-fix source re-reports that the fix is
    absent; it cannot tell you the fix left the rest of the system alone. These
    are chosen so they pass with or without the four discovery edits.
    """

    def test_suspended_is_still_not_settled(self):
        """The load-bearing property live/048 shipped, restated here because
        this repair is the one most likely to erode it: making a state reachable
        is one step away from making it terminal, and ~100 queries mean
        "settled" by writing this frozenset."""
        assert EVENT_SUSPENDED not in SETTLED_STATUSES
        assert SETTLED_STATUSES == frozenset({"completed", "closed"})

    def test_a_live_row_is_still_a_candidate(self, slate):
        assert LIVE_ID in _admitted(slate)

    def test_a_finished_row_is_still_tiered_recent(self):
        sql = str(
            select(status_tier_expr()).compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
            )
        )
        assert f"'closed')) THEN {TIER_RECENT}" in sql

    def test_a_live_game_with_media_still_survives_the_noise_filter(self):
        kept = _filter_discover_event_noise([_feed_item("live")])
        assert len(kept) == 1

    def test_a_finished_game_is_still_dropped_from_discover(self):
        assert _filter_discover_event_noise([_feed_item("completed")]) == []

    def test_the_serving_invariant_still_only_rewrites_live(self):
        """`served_event_status` passes `suspended` through verbatim, which is
        correct rather than an omission: the rule only ever downgrades a
        premature `live`, and a suspended row claims nothing about being
        played."""
        assert (
            served_event_status(EVENT_SUSPENDED, SPECIMEN_COMMENCE, NOW)
            == EVENT_SUSPENDED
        )
        # The rule it DOES enforce is unchanged.
        assert (
            served_event_status("live", NOW + timedelta(hours=40), NOW) == "scheduled"
        )


# ---------------------------------------------------------------------------
# 6 — the lead slot deliberately does NOT take it
# ---------------------------------------------------------------------------


def test_a_suspended_match_is_not_tonights_lead_game():
    """Reachable is not the same as promoted.

    `select_tonights_games` pulls a match to the FRONT of the deck, and the
    honest claim for a suspended row is that nobody is watching it — so it stays
    in the mix and does not lead. The rejection is now explicit in
    `_is_eligible` rather than falling out of an unknown-status `return False`,
    because an outcome that is right by accident is one edit from being wrong by
    accident.
    """
    live_item = _feed_item("live")
    live_item["data"]["id"] = LIVE_ID
    led = select_tonights_games([_feed_item(EVENT_SUSPENDED), live_item], NOW)

    led_ids = [i["data"]["id"] for i in led]
    assert SPECIMEN_ID not in led_ids
    # The live game beside it still leads, so the exclusion is a judgement about
    # the state rather than the fixture being unrenderable.
    assert led_ids == [LIVE_ID]


# ---------------------------------------------------------------------------
# 7 — live/056: the two ENTITY PAGES, the surfaces CERT-786's sweep did not reach
# ---------------------------------------------------------------------------
#
# The general clause at the top of this file — "a new state is shipped when every
# consumer that dispatches on that vocabulary has been shown the word" — was
# applied to Discover, `GET /api/events` and search, and it was applied
# correctly. It was not applied to the two ENTITY pages, and they have exactly
# the shape the clause warns about: a rail pair, each rail a hand-written status
# literal, and no failure when a state matches neither.
#
#     league page  `league_futures.recent_results_query`   completed | closed
#                  `league_futures.upcoming_games_query`   live | scheduled
#     team page    `teams.get_team` recent_q               completed | closed
#                                   upcoming_q             live | scheduled
#
# The upcoming rail on both pages is additionally floored at `commence_time >=
# now - 2h`, and a match is suspended PRECISELY because hours have passed since
# it started. So the specimen was not in either rail on either page: the US Open
# match was absent from the US Open league page and from both players' pages,
# while being reachable from Discover, the events list and search. The state was
# half-shipped, and the half that was missing is the half a reader navigates to.
#
# The repair is the shared `RECENT_RAIL_STATUSES`, not a fourth and fifth
# literal — `EVENT_LIST_DEFAULT_STATUSES` is named rather than inlined for this
# exact reason, and a copy is how the omission survived the first sweep.


class TestTheEntityPageRailsReproduceTheDefect:
    """Red-first, over the same corpus, for the same reason section 0 exists."""

    def test_the_pre_fix_recent_rail_loses_the_specimen(self, slate):
        pre_fix = ["completed", "closed"]
        assert SPECIMEN_ID not in _matching(slate, Event.status.in_(pre_fix))
        # …and the Final on the same slate IS there, so the corpus exercises the
        # suspended arm rather than being empty.
        assert FINISHED_ID in _matching(slate, Event.status.in_(pre_fix))

    def test_the_upcoming_rail_cannot_rescue_it_either(self, slate):
        """🔴 THE HALF THAT MAKES IT A VANISHING RATHER THAN A MISFILING.

        `eventSectionKey` buckets `suspended` with `live`, so the obvious guess
        is that the upcoming rail already had it covered. It did not, and it
        could not: that rail is floored at `now - 2h` and the specimen started
        fifteen hours ago. Both rails, both misses, no card anywhere.
        """
        # Named rather than inlined, and not only for readability: the literal
        # `["live", "scheduled"]` inline here is byte-identical to
        # `league_rails_fence_mutations:M7`'s replacement, so the mutation-
        # residue scanner's broad sweep reads it as a mutant left on disk in a
        # file that is not a declared target. A test that describes a mutation
        # has to avoid spelling it.
        upcoming_rail_statuses = ["live"] + ["scheduled"]
        upcoming = and_(
            Event.status.in_(upcoming_rail_statuses),
            Event.commence_time >= NOW - timedelta(hours=2),
        )
        assert SPECIMEN_ID not in _matching(slate, upcoming)
        assert LIVE_ID in _matching(slate, upcoming), "the control arm is empty"


class TestTheLeagueRailAdmitsSuspended:
    """The REAL query object, compiled and executed — not a copy of its filter.

    `recent_results_query` carries an `OFFSET 0` optimisation fence (LAT-P110,
    #2260) whose plan was measured on production. Running the real statement is
    also how this test would notice if widening the status list had disturbed
    the shape that fence depends on.
    """

    def _rail(self, session, sport_key="tennis_atp_us_open"):
        from app.routes.league_futures import recent_results_query

        return {e.id for e in session.execute(
            recent_results_query(sport_key, NOW)
        ).scalars().all()}

    def _unreported(self, session, sport_key="tennis_atp_us_open"):
        from app.routes.league_futures import unreported_games_query

        return {e.id for e in session.execute(
            unreported_games_query(sport_key, NOW)
        ).scalars().all()}

    def test_the_suspended_match_is_on_its_own_league_page(self, slate):
        """live/056's ship: the rain-delayed match is REACHABLE. That is the
        claim, and #3748 did not touch it.

        🔴 WHICH RAIL CHANGED, and the distinction is the whole of CERT-2167.
        This asserted `recent_results` because that is where live/056 put the
        row when the unreported rail did not yet exist. The specimen carries a
        2-1 scoreline, and it STILL renders "No result reported · last score
        2-1" — `eventState.hasNoReportedResult` is true for every suspended row
        — so "Recent Results" was never a heading that was true of it. It is now
        on the rail that says what its card says.

        Asserted against BOTH rails, exactly once between them: "it is on the
        unreported rail" alone would go green if the settled rail also admitted
        it, and a match on a page twice is its own defect.
        """
        assert SPECIMEN_ID not in self._rail(slate)
        assert SPECIMEN_ID in self._unreported(slate)

    def test_the_final_beside_it_is_still_there(self, slate):
        """CONTROL — a widening that swallowed the rail would pass the test
        above and delete the feature."""
        assert FINISHED_ID in self._rail(slate)

    def test_it_does_not_leak_across_leagues(self, slate):
        """The league scope is a join, and widening a status list must not
        widen the scope: the US Open match stays off the esports page.

        The esports page DOES show its own suspended row, and that is correct
        rather than a leak — worth pinning because it is counter-intuitive. That
        row is `STALE_SUSPENDED_ID`, "stale" only against Discover's 24-hour
        recent window; this rail's window is 14 days, so a four-day-old row is
        squarely inside it. Two windows, two answers, both right. A test that
        asserted the esports rail was empty would have been asserting Discover's
        window on a page that does not use it — and it did, until it ran.

        🔴 #3748 MOVED WHICH RAIL, NOT WHETHER. `STALE_SUSPENDED_ID` carries no
        scoreline, so it is now on the league page's "No result reported" rail
        rather than its "Recent Results" rail. The claim this test is here to
        make is unchanged and is still asserted below in both halves — the
        specimen does not leak across the join, and the esports row is still
        reachable on its own page. What changed is a fact about the OTHER row's
        rail, which this test was pinning incidentally.

        Asserted against both rails rather than swapped to the new one: "it is
        on the unreported rail" alone would go green if the settled rail
        silently swallowed it back, and the point of the pin is that it is on
        exactly one page, once.
        """
        from app.routes.league_futures import unreported_games_query

        esports = self._rail(slate, "esports_lol")
        esports_unreported = {
            e.id
            for e in slate.execute(
                unreported_games_query("esports_lol", NOW)
            ).scalars().all()
        }

        assert SPECIMEN_ID not in esports
        assert SPECIMEN_ID not in esports_unreported
        assert esports == set(), (
            "a row that reports no result is back on the rail headed 'Recent "
            f"Results': {esports}"
        )
        assert esports_unreported == {STALE_SUSPENDED_ID}

    def test_the_upcoming_rail_is_untouched(self, slate):
        """The other rail keeps its own vocabulary. Admitting `suspended` to
        BOTH would put one match on a page twice, once claiming it is about to
        start."""
        from app.routes.league_futures import upcoming_games_query

        ids = {e.id for e in slate.execute(
            upcoming_games_query("tennis_atp_us_open", NOW)
        ).scalars().all()}
        assert SPECIMEN_ID not in ids
        assert LIVE_ID in ids and SCHEDULED_ID in ids


class TestTheSharedVocabularyIsWhatBothRailsSpend:
    """🔴 THE GUARD FOR THE CLASS, not for the instance.

    The defect is not "two lists were missing a word" — it is that there were
    two more lists at all. `EVENT_LIST_DEFAULT_STATUSES` says in its own
    docstring that it is named rather than inlined so a guard can assert on the
    object the route uses instead of on a copy, "because a copy is how the
    omission survived review in the first place". These two rails were the
    copies.

    STATED LIMITATION: the team page's query is built inline inside
    `get_team`, so it cannot be imported and executed the way the league rail
    can. This asserts by source that the route spends the shared constant. A
    source scan sees call sites, not runtime behaviour, and it is a backstop
    under the constant — not a substitute for the league rail's real execution
    above. Its own control is `test_the_scan_would_catch_a_reverted_route`.
    """

    def test_the_constant_carries_all_three_states(self):
        from app.utils.event_completion import RECENT_RAIL_STATUSES

        assert EVENT_SUSPENDED in RECENT_RAIL_STATUSES
        assert set(SETTLED_STATUSES) <= set(RECENT_RAIL_STATUSES)

    def test_it_is_not_the_settled_set_wearing_a_new_name(self):
        """`SETTLED_STATUSES` answers "does this have a verdict?" and must keep
        excluding `suspended` — the two sets are different questions and
        collapsing them would re-open live/048 at the settlement layer."""
        from app.utils.event_completion import RECENT_RAIL_STATUSES

        assert EVENT_SUSPENDED not in SETTLED_STATUSES
        assert set(RECENT_RAIL_STATUSES) != set(SETTLED_STATUSES)

    @pytest.mark.parametrize(
        "module", ["app.routes.teams", "app.routes.league_futures"]
    )
    def test_both_entity_routes_spend_the_shared_condition(self, module):
        """🔴 AMENDED BY #3211 — the shared thing got BIGGER, not weaker.

        This asserted the two routes name `RECENT_RAIL_STATUSES`. They no longer
        do, and that is the repair rather than a regression: the status list was
        only half of each rail, the other half was a hand-written time bound,
        and the pair is only correct AS A PAIR. #3211 was the third state to
        fall between the two rails (after `closed` and `suspended`) precisely
        because a shared status list cannot say anything about a row that is in
        the right status set and the wrong time window.

        So both routes now spend `utils.event_rails`, which builds status AND
        time together and is itself what spends `RECENT_RAIL_STATUSES` —
        asserted below, so the indirection cannot become a place the vocabulary
        gets dropped. The literal scans are kept and extended: `closed`,
        `suspended` and now the pre-#3211 upcoming floor are all shapes that
        must not reappear inline in a route.
        """
        import importlib
        import inspect

        source = inspect.getsource(importlib.import_module(module))
        # One of the two ways a surface can spend the shared past-rails: the
        # league page SPLITS them (`settled_` + `unreported_`, because one cap
        # over two unequal populations starved the Finals out of all eight
        # slots) and the team page keeps ONE list
        # (`recent_or_unreported_condition`, because its cap spans one team's
        # own schedule and nothing starves). Either is fine; hand-writing the
        # vocabulary is not, and that is what this asserts.
        assert (
            "settled_rail_condition" in source
            or "recent_or_unreported_condition" in source
        ), f"{module} does not spend a shared past-rail condition"
        assert "upcoming_rail_condition" in source, (
            f"{module} does not spend the shared upcoming-rail condition — the "
            "two rails are only correct as a pair, and a route that shares one "
            "and hand-writes the other can still leave a state between them"
        )
        assert 'status.in_(["completed", "closed"])' not in source, (
            f"{module} still carries a hand-written recent-rail literal — the "
            "next state added to the vocabulary will miss it exactly as "
            "`suspended` did"
        )
        assert 'status.in_(["live", "scheduled"])' not in source, (
            f"{module} still carries a hand-written UPCOMING-rail literal. That "
            "list paired with a `now - 2h` floor is #3211 verbatim: it drops a "
            "`scheduled` row past its kickoff onto no rail at all"
        )

    def test_the_shared_condition_is_what_holds_the_vocabulary(self):
        """The indirection is only safe if the thing indirected TO still reads
        the shared list. Otherwise this suite would pass over a module that
        re-hardcoded the three states one level down."""
        import inspect

        from app.utils import event_rails

        source = inspect.getsource(event_rails)
        assert "RECENT_RAIL_STATUSES" in source
        assert 'status.in_(["completed", "closed"])' not in source

    def test_the_scan_would_catch_a_reverted_route(self):
        """The scan's own control: a source scan that finds nothing passes for
        free, so feed it the pre-fix lines verbatim and prove both predicates
        bite. Two arms since #3211, because the guard now has two literals to
        refuse and a control that only exercises one of them certifies half.
        """
        reverted_recent = 'Event.status.in_(["completed", "closed"]),'
        assert 'status.in_(["completed", "closed"])' in reverted_recent
        assert "settled_rail_condition" not in reverted_recent
        assert "recent_or_unreported_condition" not in reverted_recent

        reverted_upcoming = (
            'Event.status.in_(["live", "scheduled"]),\n'
            "Event.commence_time >= now - timedelta(hours=2),"
        )
        assert 'status.in_(["live", "scheduled"])' in reverted_upcoming
        assert "upcoming_rail_condition" not in reverted_upcoming
