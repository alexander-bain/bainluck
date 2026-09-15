"""AN UNATTACHED MARKET STOPS HEADLINING A MATCH THAT IS OVER. #6304.

`https://bainluck.com/search?q=Townsend`, production, 390px, 2026-09-14 20:5xZ.
#6296 removed the five ghost-attached open questions. One card survived — the
ANSWERS block's own headline:

    Guadalajara Open Akron: Tatjana Maria vs Taylor Townsend -- 49% -- Sep 20

for a match the same page prints as `Sep 14 . FINAL . Maria 1 - 2 Townsend`.

Market 60842470 carries `event_id IS NULL`, and BOTH of #6296's arms correlate
on `FuturesMarket.event_id`, so both are structurally blind to it — along with
the other 32,483 unattached markets this pool admits. There is no game state to
read because there is no game attached.

WHAT DOES REACH IT. 60842470 shares `group_id = polymarket:1009726` with six
siblings, five of them attached to the ghost of the completed match. So: a
market with no event of its own, whose venue-group siblings sit on a game
already played, is about that played game.

🔴 AND THAT SENTENCE IS FALSE FOR A COMBAT-SPORTS CARD, WHICH IS WHY THE NAME
CHECK EXISTS. Measured on production 2026-09-15 04:4xZ, `polymarket:13696` is
UFC 308 — two markets on a `closed` Topuria/Holloway plus four unattached
siblings that are DIFFERENT FIGHTS (`Whittaker vs. Chimaev`, `Murphy vs. Ige`,
`Ankalaev vs. Rakic`, `Magomedov vs. Petrosyan`). A Polymarket `group_id` is a
venue EVENT id: one match for tennis, one CARD for the UFC.

    reachable candidates ....................................... 16
      id-only rule would suppress .............................. 16   <- 4 wrong
      with the name check ...................................... 12   <- correct
    count(DISTINCT event) = 1 for ALL 16, UFC included

so "the group points at one event" does NOT discriminate — that was measured and
rejected. The name check does, and it FAILS CLOSED: names disagree, the card
stays, which is exactly today's behaviour.

🔴 THE VETO #6304's BODY ASKED FOR IS INERT. "At least one played sibling AND no
unplayed sibling" selects the same 16 rows with the second half and without it,
because an unplayed sibling of a played game is normally itself unattached and
so invisible to it. It is omitted deliberately; `TestTheInertVeto` pins that the
name check — not the veto — is what keeps the UFC card.

🔴 THE NAME IS READ OFF THE ATTACHED ROW, NOT THE CANONICAL. The attached row
stores the venue's terse form (`Jacquemot`/`Samsonova`), the canonical the full
one (`Elsa Jacquemot`/`Liudmila Samsonova`), and the terse form is a substring
of the full — so it covers markets named either way and the full one does not:

    attached row's spelling only ......... 12   <- shipped
    canonical's spelling only ............  8
    either ............................... 12

`either` equalling `attached-only` proves the canonical's names add nothing, so
consulting them would only widen the suppressing side for no reach. The
canonical is still JOINED, because only it carries the settled status.
"""

from __future__ import annotations

from datetime import datetime, timezone

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


from app.models import Event, FuturesMarket, Sport  # noqa: E402
from app.models.models import Base  # noqa: E402
from app.routes.events import _futures_game_already_played  # noqa: E402
from app.services.anchor_channel import duplicate_tag  # noqa: E402
from app.utils.event_completion import SETTLED_STATUSES  # noqa: E402

_T = datetime(2026, 9, 14, 16, 0, tzinfo=timezone.utc)

# ── The production rows, by id ──────────────────────────────────────────────
# Tennis: the group IS the match.
TENNIS_CANONICAL = 15312415     # Maria v Townsend, completed 1-2
TENNIS_GHOST = 15311057         # the same match, `suspended`, holds the markets
TENNIS_GROUP = "polymarket:1009726"
M_SPECIMEN = 60842470           # unattached, names the played pair -> SUPPRESS

# Tennis, the terse/full spelling split.
SETS_CANONICAL = 15312416       # Elsa Jacquemot / Liudmila Samsonova, completed
SETS_GHOST = 15311058           # terse: Jacquemot / Samsonova
SETS_GROUP = "polymarket:1009728"
M_TERSE_NAME = 60862160         # "Set 1 Winner: Jacquemot vs Samsonova" -> SUPPRESS

# UFC 308: the group is a CARD, not a match.
UFC_EVENT = 15146528            # Topuria / Holloway, closed
UFC_GROUP = "polymarket:13696"
M_ATTACHED_UFC = 55295796       # on the closed fight -> suppressed by arm 1
M_OTHER_FIGHT = 55295798        # "Whittaker vs. Chimaev" -> MUST SURVIVE

# A group whose played sibling has NOT been played.
UPCOMING_EVENT = 15312656       # Cardinals / Giants, scheduled
UPCOMING_GROUP = "polymarket:2000001"
M_UPCOMING_UNATTACHED = 61047745  # -> MUST SURVIVE

# The 32,483-row class: unattached AND ungrouped.
M_NO_GROUP = 60999001           # -> MUST SURVIVE, untouched as a class

# Only ONE side of the pair is named -> fail closed.
M_HALF_NAMED = 60999002         # "Townsend Total Games" -> MUST SURVIVE

# A settled event whose team names are BLANK. `'%' || '' || '%'` is `'%%'`, which
# every name matches, so the name check inverts into a wildcard and the arm eats
# the whole venue group. Zero production rows are in this state (measured
# 2026-09-15 06:2xZ, `events` scanned for blank/whitespace team names: 0) — these
# fixtures exist so a future writer cannot put one there silently.
BLANK_EVENT = 15312998          # completed, both names ""
BLANK_GROUP = "polymarket:2000002"
M_BLANK_ATTACHED = 61047747     # on the blank event -> suppressed by arm 1 either way
M_BLANK_UNATTACHED = 61047748   # -> MUST SURVIVE

WS_EVENT = 15312997             # completed, both names " " (whitespace, not empty)
WS_GROUP = "polymarket:2000003"
M_WS_ATTACHED = 61047749
M_WS_UNATTACHED = 61047750      # -> MUST SURVIVE

HALFBLANK_EVENT = 15312996      # completed, home "", away "Townsend"
HALFBLANK_GROUP = "polymarket:2000004"
M_HALFBLANK_ATTACHED = 61047751
M_HALFBLANK_UNATTACHED = 61047752  # names Townsend only -> MUST SURVIVE


def _event(event_id, status, home, away, *, tags=None):
    return Event(
        id=event_id,
        sport_id=7,
        home_team_name=home,
        away_team_name=away,
        commence_time=_T,
        status=status,
        event_tags=tags,
    )


def _market(market_id, event_id, name, group_id=None):
    return FuturesMarket(
        id=market_id,
        source="polymarket",
        external_id=f"ext-{market_id}",
        event_id=event_id,
        name=name,
        category="game_prop",
        status="open",
        group_id=group_id,
    )


@pytest.fixture(scope="module")
def engine():
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(Sport(id=7, key="tennis_wta", name="WTA"))

        # Tennis match: canonical completed, ghost suspended and holding markets.
        s.add(_event(TENNIS_CANONICAL, "completed", "Tatjana Maria", "Taylor Townsend"))
        s.add(
            _event(
                TENNIS_GHOST, "suspended", "Maria", "Townsend",
                tags=[duplicate_tag(TENNIS_CANONICAL)],
            )
        )
        s.add(_market(60862172, TENNIS_GHOST, "Set 1 Winner: Maria vs Townsend", TENNIS_GROUP))
        s.add(
            _market(
                M_SPECIMEN, None,
                "Guadalajara Open Akron: Tatjana Maria vs Taylor Townsend",
                TENNIS_GROUP,
            )
        )
        s.add(_market(M_HALF_NAMED, None, "Townsend Total Games", TENNIS_GROUP))

        # The terse/full spelling split.
        s.add(
            _event(SETS_CANONICAL, "completed", "Elsa Jacquemot", "Liudmila Samsonova")
        )
        s.add(
            _event(
                SETS_GHOST, "suspended", "Jacquemot", "Samsonova",
                tags=[duplicate_tag(SETS_CANONICAL)],
            )
        )
        s.add(_market(60857347, SETS_GHOST, "Completed Match: Elsa Jacquemot", SETS_GROUP))
        s.add(
            _market(
                M_TERSE_NAME, None, "Set 1 Winner: Jacquemot vs Samsonova", SETS_GROUP
            )
        )

        # UFC 308 — one card, four other fights.
        s.add(_event(UFC_EVENT, "closed", "Topuria", "Holloway"))
        s.add(_market(M_ATTACHED_UFC, UFC_EVENT, "UFC 308: Topuria vs. Holloway", UFC_GROUP))
        s.add(_market(M_OTHER_FIGHT, None, "Whittaker vs. Chimaev", UFC_GROUP))

        # A group on a game not yet played.
        s.add(_event(UPCOMING_EVENT, "scheduled", "Cardinals", "Giants"))
        s.add(_market(61047746, UPCOMING_EVENT, "Cardinals v Giants F5", UPCOMING_GROUP))
        s.add(
            _market(
                M_UPCOMING_UNATTACHED, None, "Cardinals v Giants Total", UPCOMING_GROUP
            )
        )

        # Unattached AND ungrouped.
        s.add(_market(M_NO_GROUP, None, "Tatjana Maria vs Taylor Townsend", None))

        # Settled events with blank team names — the wildcard edge.
        s.add(_event(BLANK_EVENT, "completed", "", ""))
        s.add(_market(M_BLANK_ATTACHED, BLANK_EVENT, "Blank Event Winner", BLANK_GROUP))
        s.add(
            _market(
                M_BLANK_UNATTACHED, None, "Kostyuk vs Jovic Total Games", BLANK_GROUP
            )
        )

        s.add(_event(WS_EVENT, "completed", " ", " "))
        s.add(_market(M_WS_ATTACHED, WS_EVENT, "Whitespace Event Winner", WS_GROUP))
        s.add(
            _market(M_WS_UNATTACHED, None, "Bejlek vs Parry Total Games", WS_GROUP)
        )

        s.add(_event(HALFBLANK_EVENT, "completed", "", "Townsend"))
        s.add(
            _market(
                M_HALFBLANK_ATTACHED, HALFBLANK_EVENT, "Half Blank Winner",
                HALFBLANK_GROUP,
            )
        )
        s.add(
            _market(
                M_HALFBLANK_UNATTACHED, None,
                "Guadalajara Open Akron: Marta Kostyuk vs Taylor Townsend",
                HALFBLANK_GROUP,
            )
        )
        s.commit()
    return eng


def _offered(eng, clause):
    with Session(eng) as s:
        return set(s.execute(select(FuturesMarket.id).where(clause)).scalars().all())


def _the_6296_arms_alone():
    """#6296 exactly as it shipped — both arms, correlated on `event_id`.

    Rebuilt rather than imported: the point of this control is to be the BEFORE
    state, and a control that reads the code under test cannot be one.
    """
    from sqlalchemy import and_
    from sqlalchemy.orm import aliased

    from app.utils.proven_duplicates import ghost_names_canonical

    ghost = aliased(Event, name="ctl_ghost")
    canonical = aliased(Event, name="ctl_canonical")
    return and_(
        ~(
            select(Event.id)
            .where(
                Event.id == FuturesMarket.event_id,
                Event.status.in_(tuple(sorted(SETTLED_STATUSES))),
            )
            .correlate(FuturesMarket)
            .exists()
        ),
        ~(
            select(canonical.id)
            .where(
                ghost.id == FuturesMarket.event_id,
                ghost_names_canonical(ghost, canonical),
                canonical.status.in_(tuple(sorted(SETTLED_STATUSES))),
            )
            .correlate(FuturesMarket)
            .exists()
        ),
    )


def _sql(stmt) -> str:
    """The Postgres rendering, with `literal_binds`' printf escaping undone.

    `literal_binds` doubles every `%` so the string is safe for a driver that
    interpolates; the SQL the server receives has single ones. Undoing it here
    means the assertions below quote the predicate as it really executes,
    instead of a spelling no reader would recognise.
    """
    return str(
        stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    ).replace("%%", "%")


# ---------------------------------------------------------------------------
# 1. The specimen, and proof the shipped predicate let it through
# ---------------------------------------------------------------------------


class TestTheSpecimen:
    def test_the_6296_arms_alone_offer_the_finished_match(self, engine):
        """🔴 RED FIRST on the same rows. If this passes after the fix, the
        fixture stopped reproducing the bug and everything below is decoration.
        """
        assert M_SPECIMEN in _offered(engine, _the_6296_arms_alone())

    def test_the_new_arm_suppresses_it(self, engine):
        assert M_SPECIMEN not in _offered(engine, _futures_game_already_played())

    def test_the_terse_venue_spelling_is_reached_too(self, engine):
        """`Set 1 Winner: Jacquemot vs Samsonova` against a canonical that says
        `Elsa Jacquemot`. Matching the canonical ALONE misses this — it is 4 of
        the 12 suppressible rows on production."""
        assert M_TERSE_NAME in _offered(engine, _the_6296_arms_alone())
        assert M_TERSE_NAME not in _offered(engine, _futures_game_already_played())


# ---------------------------------------------------------------------------
# 2. The UFC card — the control that makes the arm safe
# ---------------------------------------------------------------------------


class TestACardIsNotAMatch:
    def test_a_different_fight_on_the_same_card_survives(self, engine):
        """The whole safety of the arm. An id-only rule suppresses this row."""
        assert M_OTHER_FIGHT in _offered(engine, _futures_game_already_played())

    def test_the_attached_fight_is_still_suppressed_by_the_first_arm(self, engine):
        assert M_ATTACHED_UFC not in _offered(engine, _futures_game_already_played())

    def test_the_group_points_at_one_event_would_not_have_saved_it(self, engine):
        """Pins the rejected discriminator. The UFC group's attached siblings all
        name ONE event, exactly like the tennis group's — which is why
        `count(DISTINCT event) = 1` was measured and rejected as a guard.
        """
        with Session(engine) as s:
            for group in (UFC_GROUP, TENNIS_GROUP, SETS_GROUP):
                distinct_events = s.execute(
                    select(FuturesMarket.event_id)
                    .where(
                        FuturesMarket.group_id == group,
                        FuturesMarket.event_id.isnot(None),
                    )
                    .distinct()
                ).scalars().all()
                assert len(distinct_events) == 1, group


class TestTheInertVeto:
    def test_the_ufc_card_has_no_unplayed_attached_sibling_to_veto_on(self, engine):
        """#6304's specified veto ("no unplayed attached sibling") cannot save the
        UFC card, because the other fights are UNATTACHED and so invisible to it.
        This is why the veto measured 16 rows with and without it, and why the
        name check — not the veto — is the guard that shipped.
        """
        with Session(engine) as s:
            unplayed_attached = s.execute(
                select(FuturesMarket.id)
                .join(Event, Event.id == FuturesMarket.event_id)
                .where(
                    FuturesMarket.group_id == UFC_GROUP,
                    Event.status.notin_(tuple(sorted(SETTLED_STATUSES))),
                )
            ).scalars().all()
            assert unplayed_attached == []


# ---------------------------------------------------------------------------
# 3. Fail-closed: everything the arm must NOT touch
# ---------------------------------------------------------------------------


class TestTheArmFailsClosed:
    def test_a_group_on_a_game_not_yet_played_keeps_every_card(self, engine):
        assert M_UPCOMING_UNATTACHED in _offered(engine, _futures_game_already_played())

    def test_an_unattached_market_with_no_group_is_untouched(self, engine):
        """The 32,483-row class. Its name even matches the played pair — only the
        missing `group_id` keeps it, so this pins the correlation and not luck."""
        assert M_NO_GROUP in _offered(engine, _futures_game_already_played())

    def test_naming_only_one_side_of_the_pair_is_not_enough(self, engine):
        """`Townsend Total Games` sits in the played match's own group and names
        one player. One name is a common surname away from a false suppression —
        this population already contains a player called `Day`."""
        assert M_HALF_NAMED in _offered(engine, _futures_game_already_played())

    def test_the_arm_only_ever_removes_rows(self, engine):
        """It is a suppression, so its result is a strict subset of the BEFORE."""
        before = _offered(engine, _the_6296_arms_alone())
        after = _offered(engine, _futures_game_already_played())
        assert after < before
        assert after == before - {M_SPECIMEN, M_TERSE_NAME}


# ---------------------------------------------------------------------------
# 3b. The blank-name wildcard — the one way the name check fails OPEN
# ---------------------------------------------------------------------------


def _the_arm_with_an_unguarded_name_check():
    """The arm as first shipped: name containment with no emptiness test.

    The BEFORE for this section, rebuilt rather than imported for the same
    reason `_the_6296_arms_alone` is — a control that reads the code under test
    cannot be one. Everything here is the shipped arm except the two
    `trim(...) != ''` terms.
    """
    from sqlalchemy import and_
    from sqlalchemy.orm import aliased

    from app.utils.proven_duplicates import ghost_names_canonical

    sib = aliased(FuturesMarket, name="ctl_sibling")
    ghost = aliased(Event, name="ctl_grp_ghost")
    canonical = aliased(Event, name="ctl_grp_canonical")
    from sqlalchemy import literal, or_

    return ~(
        select(sib.id)
        .select_from(sib)
        .join(ghost, ghost.id == sib.event_id)
        .outerjoin(canonical, ghost_names_canonical(ghost, canonical))
        .where(
            FuturesMarket.event_id.is_(None),
            FuturesMarket.group_id.isnot(None),
            sib.group_id == FuturesMarket.group_id,
            or_(
                ghost.status.in_(tuple(sorted(SETTLED_STATUSES))),
                canonical.status.in_(tuple(sorted(SETTLED_STATUSES))),
            ),
            and_(
                FuturesMarket.name.ilike(
                    literal("%") + ghost.home_team_name + literal("%")
                ),
                FuturesMarket.name.ilike(
                    literal("%") + ghost.away_team_name + literal("%")
                ),
            ),
        )
        .correlate(FuturesMarket)
        .exists()
    )


class TestABlankTeamNameCannotSwallowAGroup:
    """`'%' || '' || '%'` is `'%%'`, and every name matches it.

    So a settled event that stores a blank team name turns the arm's safety
    check into a wildcard and suppresses its ENTIRE venue group — the UFC
    straddle this design exists to prevent, arriving through the back door.
    Zero production rows are in that state today (`events` scanned 2026-09-15
    06:2xZ: 0 blank or whitespace-only team names), so these are guards against
    a writer rather than a repair. Flagged by the desk at merge time.
    """

    @pytest.mark.parametrize(
        "market_id",
        [M_BLANK_UNATTACHED, M_WS_UNATTACHED, M_HALFBLANK_UNATTACHED],
    )
    def test_the_unguarded_check_would_have_suppressed_it(self, engine, market_id):
        """🔴 RED FIRST. If this stops holding, the fixtures no longer reproduce
        the edge and the three assertions below are decoration."""
        assert market_id not in _offered(engine, _the_arm_with_an_unguarded_name_check())

    @pytest.mark.parametrize(
        "market_id",
        [M_BLANK_UNATTACHED, M_WS_UNATTACHED, M_HALFBLANK_UNATTACHED],
    )
    def test_the_shipped_arm_keeps_it(self, engine, market_id):
        assert market_id in _offered(engine, _futures_game_already_played())

    def test_a_blank_side_is_not_the_other_half_of_the_pair(self, engine):
        """The half-blank row is the sharp one: its name really does contain
        `Townsend`, the away side of the settled event. Requiring BOTH names is
        no protection at all when one of them matches everything, so this fails
        if someone guards only one side.
        """
        assert "Townsend" in "Guadalajara Open Akron: Marta Kostyuk vs Taylor Townsend"
        assert M_HALFBLANK_UNATTACHED in _offered(engine, _futures_game_already_played())

    def test_the_emptiness_test_renders_on_postgres(self):
        """SQLite and Postgres both spell it `trim(...)`, but the guard suite
        runs the portable dialect, so the production rendering is pinned BY NAME
        the way the rest of this arm's Postgres shape is.
        """
        sql = _sql(select(FuturesMarket.id).where(_futures_game_already_played()))
        assert "trim(grp_ghost.home_team_name) != ''" in sql
        assert "trim(grp_ghost.away_team_name) != ''" in sql


# ---------------------------------------------------------------------------
# 4. The rendering production actually runs
# ---------------------------------------------------------------------------


class TestThePostgresRendering:
    """🔴 The guard suite above runs SQLite. These pin the Postgres SQL BY NAME,
    because a behavioural green on the portable dialect proves the wrong half —
    the lesson #6299 paid for.
    """

    def test_the_name_check_renders_as_ilike_containment_on_postgres(self):
        sql = _sql(select(FuturesMarket.id).where(_futures_game_already_played()))
        assert "grp_sibling" in sql
        assert "futures_markets.name ILIKE ('%' || grp_ghost.home_team_name || '%')" in sql
        assert "futures_markets.name ILIKE ('%' || grp_ghost.away_team_name || '%')" in sql

    def test_the_name_is_read_off_the_attached_row_not_the_canonical(self):
        """Measured on production: attached-row spelling 12, canonical 8, either
        12 — so the canonical's names are a strict subset and add nothing. The
        canonical is still joined, because only IT carries the settled status.
        """
        sql = _sql(select(FuturesMarket.id).where(_futures_game_already_played()))
        assert "grp_ghost.home_team_name" in sql
        assert "grp_canonical.home_team_name" not in sql, (
            "the canonical's SPELLING is inert and must not widen the OR"
        )
        assert "grp_canonical.status IN" in sql, (
            "the canonical's STATUS is the only thing that says the game is over"
        )

    def test_the_arm_is_correlated_and_scoped_to_unattached_grouped_rows(self):
        sql = _sql(select(FuturesMarket.id).where(_futures_game_already_played()))
        assert "futures_markets.event_id IS NULL" in sql
        assert "futures_markets.group_id IS NOT NULL" in sql
        assert "grp_sibling.group_id = futures_markets.group_id" in sql

    def test_the_arm_is_a_not_exists_and_not_a_top_level_or(self):
        """The short-circuit spelling measured median 21.4 / max 133.5 ms against
        12.2 / 20.7 for this one — a top-level OR blocks the anti-join
        transformation. This fails if someone re-introduces it.
        """
        sql = _sql(select(FuturesMarket.id).where(_futures_game_already_played()))
        assert "NOT (EXISTS (SELECT grp_sibling.id" in sql
        assert "futures_markets.event_id IS NOT NULL OR" not in sql

    def test_the_predicate_survives_an_outer_query_that_joins_events(self):
        """`.correlate(FuturesMarket)` is load-bearing: without it an enclosing
        query that also joins `events` raises at COMPILE time. Inherited from
        #4914 and re-asserted because this arm adds two more `events` aliases.
        """
        stmt = (
            select(FuturesMarket.id)
            .join(Event, Event.id == FuturesMarket.event_id)
            .where(_futures_game_already_played())
        )
        assert "grp_sibling" in _sql(stmt)
