"""The anchor channel gets a consumer — #2213, queue 413.

Queue 412R shipped ``app/utils/provider_anchor_keys.py``: a correct answer to
"what would an anchor row for this provider id be?". Nothing called it, and
``event_provider_anchors`` held **0 rows**, so the registry's documented Step 2
("Cross-source ID — check if ANY source already claimed it via other ID columns")
was a comment reading *"This step is implicit — Step 3 will find it by
sport+date+teams"*. After ruling 048 closed Step 3 to unanchored claims, that
sentence stopped being true and nothing replaced it. Step 2 has been absent, not
implicit, ever since.

## The specimen this file is built on

Alex's own home screen, 2026-08-25: one live Boston–Miami game rendered as two
cards printing 57/43 and 50/50. Two event rows, `15291666` (ESPN/odds) and
`15228865` (StatPal), sharing team ids and `commence_time` and **no provider
id whatsoever**.

Kalshi is the provider that resolves that class, and it is the one the registry
could never use: it has no id column on `events` at all. `KXMLBGAME-26AUG25MIABOS-BOS`
and `KXMLBGAME-26AUG25MIABOS-MIA` are two market tickers for one game, and both
reduce to the same namespace-qualified game anchor `baseball_mlb:26AUG25MIABOS`.
That anchor is derived from the ticker alone — it does not depend on which of the
two rows Kalshi happened to land on first — which is precisely what makes it an
id-anchored correspondence under ruling 048 arm A rather than a name-and-time
guess under Step 3.

## What is red before the fix, and why each one is behavioural

Three tests below fail against the un-wired registry by *creating a second event*
where they should return the first, or by writing no anchor at all. None of them
fails on an import error or a missing attribute — the module under test exists
and is importable before the wiring lands, so the red is a behaviour, at exit 1.

## What must stay green in BOTH directions (gotcha #43)

A guard that only proves the new path fires is half a guard. These pin the
refusals, and every one of them passes before the wiring as well as after:

* **The 41 groups are not absorbed.** 21 of them carry conflicting StatPal ids
  across two namespaces; `compare_statpal_ids` calls that `INCOMPARABLE`, and
  `INCOMPARABLE` authorizes nothing. This test asserts the duplicate *survives*,
  which reads backwards until you remember that the alternative is an absorption
  on no evidence.
* **`market` and `container` anchors never absorb.** Tennis Kalshi tickers and
  Polymarket `conditionId`s are recorded and are never consulted by Step 2.
* **Step 2 does not re-open Step 3.** An unanchored claim with no matching anchor
  still creates, and `_find_by_structured_match` is still never reached.
* **No cross-sport absorption**, even on an exact anchor hit.
"""
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.services.anchor_channel import (
    COLLISION,
    CONFIRMED,
    NO_KEY,
    STALE_INCUMBENT,
    WROTE,
    anchor_is_current,
    anchor_key_for_claim,
    duplicate_tag,
    find_event_by_anchor,
    invalidate_scalar_anchor,
    record_anchor,
)
from app.services.event_registry import (
    EventClaim,
    EventIdentity,
    _sport_id_cache,
    find_or_create_event,
)
from app.utils.provider_anchor_keys import (
    ANCHOR_KIND_CONTAINER,
    ANCHOR_KIND_GAME,
    ANCHOR_KIND_MARKET,
)
from tests.test_event_registry import _FakeRegistrySession, _FakeExecuteResult

MLB_SPORT_ID = 53232
NBA_SPORT_ID = 41111

# The two Kalshi tickers for Alex's game. Different markets, one game.
TICKER_BOS = "KXMLBGAME-26AUG25MIABOS-BOS"
TICKER_MIA = "KXMLBGAME-26AUG25MIABOS-MIA"
SHARED_GAME_ANCHOR = "baseball_mlb:26AUG25MIABOS"

# A tennis ticker: Alex's 2026-08-21 ruling keeps these at `market`, because
# their tickers carry no per-game token that survives the sport_key qualifier.
TICKER_TENNIS = "KXATPMATCH-26AUG25ALCSIN-SIN"

# The production rows behind the two cards (#2213, measured 2026-08-25).
ESPN_ROW_ID = 15291666
STATPAL_ROW_ID = 15228865
# 21 of the 41 groups look like this: one 6-digit StatPal id, one 10-digit,
# under one column name, for the same game.
STATPAL_ID_SHORT = "355372"
STATPAL_ID_LONG = "1329192448"

GAME_TIME = datetime(2026, 8, 25, 22, 40, tzinfo=timezone.utc)


def _row(*, event_id, sport_id=MLB_SPORT_ID, away="Boston Red Sox",
         home="Miami Marlins", commence=GAME_TIME, status="live",
         external_id=None, espn_id=None, statpal_fixture_id=None,
         commence_time_source="espn", tags=None):
    return SimpleNamespace(
        id=event_id, sport_id=sport_id,
        away_team_name=away, home_team_name=home,
        commence_time=commence, status=status,
        external_id=external_id, espn_id=espn_id,
        statpal_fixture_id=statpal_fixture_id,
        commence_time_source=commence_time_source,
        completed_at=None, event_tags=list(tags or []),
    )


class _AnchorSession(_FakeRegistrySession):
    """``_FakeRegistrySession`` plus an in-memory ``event_provider_anchors``.

    The anchor store is a dict keyed exactly as the real unique index is —
    ``(source, source_id, id_kind)`` — so ``ON CONFLICT DO NOTHING`` is modelled
    by the dict's own refusal to overwrite rather than by a flag this test could
    get wrong. ``sports`` maps event_id -> sport_id for the Step 2 join.
    """

    def __init__(self, *, anchors=None, event_sports=None, **kwargs):
        super().__init__(**kwargs)
        self.anchors = dict(anchors or {})
        self.anchor_writes = []
        self.anchor_deletes = []
        self.event_sports = dict(event_sports or {})
        self.tagged = []
        #: Step 2 loads the anchored row by primary key.
        self.by_id = {r.id: r for r in self.structured_candidates}

    async def execute(self, statement, params=None):
        sql = str(statement)

        # `.first()` on the real Result yields a Row; `_FakeExecuteResult`
        # models that with `first_row=`, NOT with `rows=` (which feeds
        # `.scalars()`). Getting this wrong makes every anchor read look like a
        # miss, which reads as a red in the code under test — so it is stated
        # here once rather than debugged three times.
        if "FROM event_provider_anchors a" in sql:
            self.statements.append(statement)
            hit = self.anchors.get(
                (params["source"], params["source_id"], params["id_kind"])
            )
            if hit is None:
                return _FakeExecuteResult()
            return _FakeExecuteResult(
                first_row=(hit, self.event_sports.get(hit, MLB_SPORT_ID))
            )

        # CERT-410 [P1]. The corroboration read: what does the anchored event
        # carry in its OWN columns right now? Answered from the seeded event
        # rows rather than from a flag, so a test makes an anchor stale the way
        # production does — by re-keying the column — and cannot make it stale
        # by asserting that it is.
        if "SELECT espn_id, external_id, statpal_fixture_id FROM events" in sql:
            self.statements.append(statement)
            row = self.by_id.get(params["event_id"])
            if row is None:
                return _FakeExecuteResult()
            return _FakeExecuteResult(
                first_row=(row.espn_id, row.external_id, row.statpal_fixture_id)
            )

        if "DELETE FROM event_provider_anchors" in sql:
            self.statements.append(statement)
            key = (params["source"], params["source_id"], params["id_kind"])
            scoped = params.get("event_id")
            held = self.anchors.get(key)
            if held is None or (scoped is not None and held != scoped):
                return _FakeExecuteResult(rowcount=0)
            del self.anchors[key]
            self.anchor_deletes.append((key, scoped))
            return _FakeExecuteResult(rowcount=1)

        if "INSERT INTO event_provider_anchors" in sql:
            self.statements.append(statement)
            key = (params["source"], params["source_id"], params["id_kind"])
            self.anchor_writes.append((key, params["event_id"]))
            if key in self.anchors:
                return _FakeExecuteResult()  # ON CONFLICT DO NOTHING
            self.anchors[key] = params["event_id"]
            self.event_sports.setdefault(params["event_id"], MLB_SPORT_ID)
            return _FakeExecuteResult(first_row=(params["event_id"],))

        if "SELECT event_id FROM event_provider_anchors" in sql:
            self.statements.append(statement)
            key = (params["source"], params["source_id"], params["id_kind"])
            if key not in self.anchors:
                return _FakeExecuteResult()
            return _FakeExecuteResult(first_row=(self.anchors[key],))

        if "UPDATE events SET event_tags" in sql:
            self.statements.append(statement)
            self.tagged.append((params["event_id"], params["tag_array"]))
            return _FakeExecuteResult()

        if "FROM events" in sql and "WHERE events.id =" in sql:
            self.statements.append(statement)
            wanted = next(iter(statement.compile().params.values()))
            return _FakeExecuteResult(scalar=self.by_id.get(wanted))

        return await super().execute(statement)


def _identity(source, source_id, *, sport_key="baseball_mlb",
              home="Miami Marlins", away="Boston Red Sox",
              commence=GAME_TIME, schedule_derived=False, status="live"):
    return EventIdentity(
        sport_key=sport_key, home_team_name=home, away_team_name=away,
        commence_time=commence,
        claim=EventClaim(source, source_id, schedule_derived=schedule_derived),
        commence_time_source=source, status=status,
    )


@pytest.fixture(autouse=True)
def _seed_sport_cache():
    _sport_id_cache["baseball_mlb"] = MLB_SPORT_ID
    _sport_id_cache["basketball_nba"] = NBA_SPORT_ID
    yield
    _sport_id_cache.pop("baseball_mlb", None)
    _sport_id_cache.pop("basketball_nba", None)


# ══════════════════════════════════════════════════════════════════════════
# RED before the wiring — Step 2 exists and fires
# ══════════════════════════════════════════════════════════════════════════

class TestStep2CrossSourceAnchor:
    """The cascade step the docstring promises and the code never had."""

    @pytest.mark.asyncio
    async def test_second_kalshi_ticker_lands_on_the_anchored_event(self):
        """Two tickers, one game, one row.

        This is the whole point. Before the wiring, ``_find_by_source_id``
        returns ``None`` for Kalshi (no id column exists), the ruling 048 gate
        blocks Step 3 for an unanchored claim, and the registry CREATES — which
        is how Alex got two cards. The anchor makes it Step 1's guarantee
        without Step 3's risk: the correspondence is an id, shared.
        """
        session = _AnchorSession(
            anchors={("kalshi", SHARED_GAME_ANCHOR, ANCHOR_KIND_GAME): ESPN_ROW_ID},
            event_sports={ESPN_ROW_ID: MLB_SPORT_ID},
            structured_candidates=[_row(event_id=ESPN_ROW_ID)],
            sport_id=MLB_SPORT_ID,
        )

        event, created = await find_or_create_event(
            session, _identity("kalshi", TICKER_MIA)
        )

        assert created is False, (
            "a Kalshi claim whose game anchor is already bound must find that "
            "event, not create a second row"
        )
        assert event.id == ESPN_ROW_ID
        assert session.added == [], "nothing may be created on an anchor hit"

    @pytest.mark.asyncio
    async def test_anchor_hit_does_not_require_schedule_derived(self):
        """Arm A never needed it, and Step 1 proves that every day.

        A shared id absorbs without ``schedule_derived`` in Step 1 today. Step 2
        reads the *same* shared id out of a table instead of out of a column, so
        requiring the flag here would be stricter than Step 1 for no reason —
        and granting anything extra when it is true would be a loosening. The
        claim below is explicitly unanchored and must still match.
        """
        session = _AnchorSession(
            anchors={("kalshi", SHARED_GAME_ANCHOR, ANCHOR_KIND_GAME): ESPN_ROW_ID},
            event_sports={ESPN_ROW_ID: MLB_SPORT_ID},
            structured_candidates=[_row(event_id=ESPN_ROW_ID)],
            sport_id=MLB_SPORT_ID,
        )

        event, created = await find_or_create_event(
            session,
            _identity("kalshi", TICKER_BOS, schedule_derived=False),
        )

        assert created is False
        assert event.id == ESPN_ROW_ID


class TestAnchorWritePath:
    """A channel nobody writes to stays at 0 rows forever."""

    @pytest.mark.asyncio
    async def test_creating_an_event_records_its_claim_anchor(self):
        session = _AnchorSession(sport_id=MLB_SPORT_ID)

        event, created = await find_or_create_event(
            session, _identity("kalshi", TICKER_BOS)
        )

        assert created is True
        assert (
            ("kalshi", SHARED_GAME_ANCHOR, ANCHOR_KIND_GAME) in session.anchors
        ), (
            "the created row must be reachable by the id that named it, or the "
            "next claim creates a third row"
        )
        assert session.anchors[
            ("kalshi", SHARED_GAME_ANCHOR, ANCHOR_KIND_GAME)
        ] == event.id

    @pytest.mark.asyncio
    async def test_first_attach_of_a_column_id_records_its_anchor(self):
        """An ESPN id arriving on a row that had none establishes a correspondence."""
        row = _row(event_id=STATPAL_ROW_ID, espn_id=None,
                   statpal_fixture_id=STATPAL_ID_SHORT,
                   commence_time_source="statpal")
        session = _AnchorSession(
            source_matches={},
            structured_candidates=[row],
            event_sports={STATPAL_ROW_ID: MLB_SPORT_ID},
            sport_id=MLB_SPORT_ID,
        )
        # An ESPN claim IS schedule-derived at its real call site, so it reaches
        # the structured matcher and lands on the StatPal row.
        event, created = await find_or_create_event(
            session, _identity("espn", "401816665", schedule_derived=True)
        )

        assert created is False
        assert event.id == STATPAL_ROW_ID
        assert ("espn", "401816665", ANCHOR_KIND_GAME) in session.anchors

    @pytest.mark.asyncio
    async def test_repeat_poll_of_an_attached_claim_writes_nothing(self):
        """32s Tier-1 polling must not buy a no-op INSERT every cycle."""
        row = _row(event_id=ESPN_ROW_ID, espn_id="401816665")
        session = _AnchorSession(
            source_matches={"401816665": row},
            structured_candidates=[row],
            event_sports={ESPN_ROW_ID: MLB_SPORT_ID},
            sport_id=MLB_SPORT_ID,
        )

        event, created = await find_or_create_event(
            session, _identity("espn", "401816665", schedule_derived=True)
        )

        assert created is False
        assert event.id == ESPN_ROW_ID
        assert session.anchor_writes == [], (
            "the id was already on the column — nothing was established, so "
            "nothing should be written"
        )


class TestCollisionIsTheDetector:
    """The unique index is the only proof of a duplicate this system has ever had."""

    @pytest.mark.asyncio
    async def test_second_event_claiming_a_bound_anchor_is_tagged(self):
        session = _AnchorSession(
            anchors={("kalshi", SHARED_GAME_ANCHOR, ANCHOR_KIND_GAME): ESPN_ROW_ID},
            event_sports={ESPN_ROW_ID: MLB_SPORT_ID},
            sport_id=MLB_SPORT_ID,
        )
        loser = _row(event_id=STATPAL_ROW_ID, tags=[])

        result = await record_anchor(
            session,
            event_id=loser.id,
            key=anchor_key_for_claim("kalshi", TICKER_MIA),
        )

        assert result.outcome == COLLISION
        assert result.canonical_event_id == ESPN_ROW_ID, (
            "first writer wins — a canonical that moves with poll order is not "
            "an identity"
        )

    @pytest.mark.asyncio
    async def test_incumbent_is_never_repointed(self):
        session = _AnchorSession(
            anchors={("kalshi", SHARED_GAME_ANCHOR, ANCHOR_KIND_GAME): ESPN_ROW_ID},
            event_sports={ESPN_ROW_ID: MLB_SPORT_ID},
            sport_id=MLB_SPORT_ID,
        )
        await record_anchor(
            session, event_id=STATPAL_ROW_ID,
            key=anchor_key_for_claim("kalshi", TICKER_MIA),
        )
        assert (
            session.anchors[("kalshi", SHARED_GAME_ANCHOR, ANCHOR_KIND_GAME)]
            == ESPN_ROW_ID
        )

    @pytest.mark.asyncio
    async def test_cross_sport_collision_does_not_tag_a_duplicate(self):
        """The one collision the registry can reach on real data — and it is a lie.

        Step 2 pre-empts the ordinary case: if an anchor is bound to a same-sport
        row, the cascade RETURNS that row and never reaches a create, so no
        conflict occurs. What survives to the write path is a conflict Step 2
        already refused — a cross-sport anchor — plus genuine create/create
        races. Tagging on the cross-sport one would record a duplicate
        relationship between two rows that are not the same game, which is the
        exact class ruling 048 exists to prevent, arrived at from the other side.
        """
        session = _AnchorSession(
            anchors={("kalshi", SHARED_GAME_ANCHOR, ANCHOR_KIND_GAME): ESPN_ROW_ID},
            event_sports={ESPN_ROW_ID: NBA_SPORT_ID},
            sport_id=MLB_SPORT_ID,
        )

        event, created = await find_or_create_event(
            session, _identity("kalshi", TICKER_BOS)
        )

        assert created is True, "a cross-sport anchor must not absorb"
        assert session.tagged == [], (
            "an anchor pointing into another sport is a data defect, not proof "
            "that two rows are one game"
        )

    @pytest.mark.asyncio
    async def test_reestablishing_the_same_pair_is_confirmed_not_collision(self):
        session = _AnchorSession(
            anchors={("kalshi", SHARED_GAME_ANCHOR, ANCHOR_KIND_GAME): ESPN_ROW_ID},
            event_sports={ESPN_ROW_ID: MLB_SPORT_ID},
            sport_id=MLB_SPORT_ID,
        )
        result = await record_anchor(
            session, event_id=ESPN_ROW_ID,
            key=anchor_key_for_claim("kalshi", TICKER_BOS),
        )
        assert result.outcome == CONFIRMED


# ══════════════════════════════════════════════════════════════════════════
# GREEN in both directions — the refusals (gotcha #43)
# ══════════════════════════════════════════════════════════════════════════

class TestTheRefusals:

    @pytest.mark.asyncio
    async def test_the_41_groups_are_not_absorbed_by_this_change(self):
        """The honest one. 0 of 41 pairs share a provider id; 21 conflict.

        The StatPal row carries a 6-digit fixture id and the ESPN row a 10-digit
        one, under a single column name. That is `INCOMPARABLE`, not `AGREE` and
        not `CONFLICT`, and `INCOMPARABLE` authorizes nothing. This asserts the
        duplicate SURVIVES — which is the correct outcome, because the only way
        to collapse it here would be to absorb on teams and a time window, which
        is what ruling 048 forbids by name in doubleheader season.
        """
        espn_row = _row(event_id=ESPN_ROW_ID, espn_id="401816665",
                        statpal_fixture_id=STATPAL_ID_LONG)
        session = _AnchorSession(
            anchors={
                ("statpal", f"s10:{STATPAL_ID_LONG}", ANCHOR_KIND_GAME): ESPN_ROW_ID,
            },
            event_sports={ESPN_ROW_ID: MLB_SPORT_ID},
            structured_candidates=[espn_row],
            sport_id=MLB_SPORT_ID,
        )

        event, created = await find_or_create_event(
            session, _identity("statpal", STATPAL_ID_SHORT)
        )

        assert created is True, (
            "a 6-digit StatPal claim must NOT absorb a row anchored at a "
            "10-digit StatPal id — different namespaces are no evidence, in "
            "either direction"
        )
        assert event.id != ESPN_ROW_ID

    @pytest.mark.asyncio
    async def test_market_kind_anchor_never_absorbs(self):
        """Tennis stays `market` by Alex's 2026-08-21 ruling, so it cannot match."""
        key = anchor_key_for_claim("kalshi", TICKER_TENNIS)
        assert key is not None and key.id_kind == ANCHOR_KIND_MARKET

        session = _AnchorSession(
            anchors={("kalshi", TICKER_TENNIS, ANCHOR_KIND_MARKET): ESPN_ROW_ID},
            event_sports={ESPN_ROW_ID: MLB_SPORT_ID},
            sport_id=MLB_SPORT_ID,
        )
        assert await find_event_by_anchor(session, key) is None

    @pytest.mark.asyncio
    async def test_container_kind_anchor_never_absorbs(self):
        key = anchor_key_for_claim(
            "polymarket", None, polymarket_event_id="21742"
        )
        assert key is not None and key.id_kind == ANCHOR_KIND_CONTAINER
        session = _AnchorSession(
            anchors={("polymarket", "21742", ANCHOR_KIND_CONTAINER): ESPN_ROW_ID},
            event_sports={ESPN_ROW_ID: MLB_SPORT_ID},
            sport_id=MLB_SPORT_ID,
        )
        assert await find_event_by_anchor(session, key) is None

    @pytest.mark.asyncio
    async def test_cross_sport_anchor_hit_is_refused(self):
        """An anchor is not a licence to absorb across sports."""
        session = _AnchorSession(
            anchors={("kalshi", SHARED_GAME_ANCHOR, ANCHOR_KIND_GAME): ESPN_ROW_ID},
            event_sports={ESPN_ROW_ID: NBA_SPORT_ID},
            sport_id=MLB_SPORT_ID,
        )
        assert await find_event_by_anchor(
            session,
            anchor_key_for_claim("kalshi", TICKER_BOS),
            expected_sport_id=MLB_SPORT_ID,
        ) is None

    @pytest.mark.asyncio
    async def test_unanchored_claim_with_no_anchor_still_creates(self):
        """Step 2 must not re-open Step 3 for the claims ruling 048 excluded."""
        candidate = _row(event_id=ESPN_ROW_ID)
        session = _AnchorSession(
            structured_candidates=[candidate],
            event_sports={ESPN_ROW_ID: MLB_SPORT_ID},
            sport_id=MLB_SPORT_ID,
        )
        event, created = await find_or_create_event(
            session, _identity("kalshi", "KXMLBGAME-26AUG25NYYTOR-NYY")
        )
        assert created is True
        assert event.id != ESPN_ROW_ID

    def test_synthetic_claim_id_cannot_produce_a_game_anchor(self):
        """The defect this file caught while being written, pinned so it stays caught.

        `prediction_market_matching` builds its claim id as
        `pm_{source}_{market.external_id}`. That prefix has no reader — Step 1
        ignores Kalshi, `_attach_claim` ignores Kalshi — so nothing ever noticed
        it was not Kalshi's own id. The anchor channel is the first reader, and
        a prefixed string carries no parseable game token, so it degrades to
        `market`: recorded, permanently unable to anchor, every test green, the
        rail resolving nothing.

        Both halves are asserted. The prefixed form must NOT be a game anchor,
        and the bare ticker must be — a test that only pinned the second half
        would have passed against the broken call site.
        """
        degraded = anchor_key_for_claim("kalshi", f"pm_kalshi_{TICKER_BOS}")
        assert degraded is not None
        assert degraded.id_kind == ANCHOR_KIND_MARKET
        assert degraded.may_anchor_absorption is False

        real = anchor_key_for_claim("kalshi", TICKER_BOS)
        assert real.id_kind == ANCHOR_KIND_GAME
        assert real.source_id == SHARED_GAME_ANCHOR

    def test_claim_exposes_the_provider_id_for_anchoring(self):
        """`anchor_source_id` prefers the provider's id over our synthesized one."""
        synthetic = EventClaim(
            "kalshi", f"pm_kalshi_{TICKER_BOS}", provider_id=TICKER_BOS
        )
        assert synthetic.source_id == f"pm_kalshi_{TICKER_BOS}"
        assert synthetic.anchor_source_id == TICKER_BOS

        plain = EventClaim("espn", "401816665")
        assert plain.anchor_source_id == "401816665", (
            "a call site that did not synthesize anything must be unaffected"
        )

    def test_the_prediction_market_call_site_passes_the_provider_id(self):
        """Read the real call site, not a copy of it.

        The registry cannot tell a synthesized id from a real one, so the
        correctness of the whole Kalshi half lives at ONE call site. An
        assertion about a value this test constructs itself would prove nothing
        about that call site, which is exactly how the defect survived being
        written.
        """
        import ast
        import inspect

        from app.tasks import prediction_market_matching

        tree = ast.parse(inspect.getsource(prediction_market_matching))
        claims = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "EventClaim"
        ]
        assert claims, "no EventClaim call found — has the call site moved?"
        for call in claims:
            kwargs = {k.arg for k in call.keywords}
            assert "provider_id" in kwargs, (
                "the prediction-market EventClaim must pass provider_id; its "
                "positional source_id is the synthetic pm_ form and cannot "
                "anchor (#2213)"
            )

    def test_unknown_statpal_namespace_yields_no_key(self):
        """A third namespace upstream must land as *unanchorable*, never guessed."""
        assert anchor_key_for_claim("statpal", "12345") is None       # 5 digits
        assert anchor_key_for_claim("statpal", "abc-99") is None
        assert anchor_key_for_claim("statpal", None) is None

    @pytest.mark.asyncio
    async def test_no_key_writes_nothing(self):
        session = _AnchorSession(sport_id=MLB_SPORT_ID)
        result = await record_anchor(session, event_id=1, key=None)
        assert result.outcome == NO_KEY
        assert session.anchor_writes == []

    def test_duplicate_tag_names_the_canonical(self):
        assert duplicate_tag(ESPN_ROW_ID) == f"provenance:duplicate-of:{ESPN_ROW_ID}"


# ══════════════════════════════════════════════════════════════════════════
# CERT-410 [P1] — a scalar-derived anchor is a COPY, and the column is the truth
# ══════════════════════════════════════════════════════════════════════════

#: The cert's executed specimen, verbatim: the anchor still names the old id,
#: the event has been re-keyed to a new one.
STALE_ESPN_ID = "401816665"
REKEYED_ESPN_ID = "401816999"


class TestAStaleScalarAnchorHasNoAuthority:
    """The finding that blocked this branch, turned into a permanent red.

    `event_provider_anchors` records `(source, source_id, id_kind)` and nothing
    about *when* the copy was taken. For Kalshi and Polymarket that is complete
    — no column exists to disagree with. For ESPN, StatPal and the Odds API the
    anchor is a cache of a mutable, non-unique column, and two live paths change
    it underneath: `repair_event_espn_id` re-keys it, and the source-intelligence
    collision sweep clears it to NULL. Before the fix the stale copy outranked
    the live column and absorbed a different game.
    """

    @pytest.mark.asyncio
    async def test_the_cert_specimen_no_longer_absorbs(self):
        """CERT-410's executed case: `espn:old-id -> 200` while 200 carries `new-id`.

        The claim arrives with the OLD id. Step 1 misses (no column holds it),
        the ruling 048 gate keeps an unanchored claim out of Step 3, so the
        anchor is the ONLY route to event 200 — which is what makes this a clean
        read of Step 2 rather than of the matcher.
        """
        rekeyed = _row(event_id=ESPN_ROW_ID, espn_id=REKEYED_ESPN_ID)
        session = _AnchorSession(
            anchors={("espn", STALE_ESPN_ID, ANCHOR_KIND_GAME): ESPN_ROW_ID},
            event_sports={ESPN_ROW_ID: MLB_SPORT_ID},
            structured_candidates=[rekeyed],
            sport_id=MLB_SPORT_ID,
        )

        assert await find_event_by_anchor(
            session,
            anchor_key_for_claim("espn", STALE_ESPN_ID),
            expected_sport_id=MLB_SPORT_ID,
        ) is None, (
            "the anchor was copied from events.espn_id, which now holds a "
            "different value — the copy has been disproven and may not absorb"
        )

        event, created = await find_or_create_event(
            session, _identity("espn", STALE_ESPN_ID)
        )
        assert created is True, (
            "an old-id claim resolving to a re-keyed event is an absorption of "
            "a DIFFERENT game — the cert's whole finding"
        )
        assert event.id != ESPN_ROW_ID

    @pytest.mark.asyncio
    async def test_a_cleared_column_voids_its_anchor(self):
        """The NULL transition, which is the source-intelligence sweep's own write.

        That sweep clears `espn_id` on *every* holder of a colliding id
        precisely because it has decided the linkage is wrong. An anchor that
        survives it re-asserts the linkage the sweep just withdrew.
        """
        cleared = _row(event_id=ESPN_ROW_ID, espn_id=None)
        session = _AnchorSession(
            anchors={("espn", STALE_ESPN_ID, ANCHOR_KIND_GAME): ESPN_ROW_ID},
            event_sports={ESPN_ROW_ID: MLB_SPORT_ID},
            structured_candidates=[cleared],
            sport_id=MLB_SPORT_ID,
        )
        assert await find_event_by_anchor(
            session,
            anchor_key_for_claim("espn", STALE_ESPN_ID),
            expected_sport_id=MLB_SPORT_ID,
        ) is None

    @pytest.mark.asyncio
    async def test_statpal_corroboration_is_namespace_qualified(self):
        """A raw string compare would read every live StatPal anchor as stale.

        The anchor's `source_id` is `s6:355372`; the column holds the bare
        `355372`. Corroboration therefore re-derives the key from the current
        column value instead of comparing strings — and this asserts BOTH
        directions, because a check that only refused would have passed the
        stale test above while silently disabling StatPal entirely.
        """
        live = _row(event_id=STATPAL_ROW_ID, statpal_fixture_id=STATPAL_ID_SHORT)
        session = _AnchorSession(
            anchors={("statpal", f"s6:{STATPAL_ID_SHORT}", ANCHOR_KIND_GAME): STATPAL_ROW_ID},
            event_sports={STATPAL_ROW_ID: MLB_SPORT_ID},
            structured_candidates=[live],
            sport_id=MLB_SPORT_ID,
        )
        assert await find_event_by_anchor(
            session,
            anchor_key_for_claim("statpal", STATPAL_ID_SHORT),
            expected_sport_id=MLB_SPORT_ID,
        ) == STATPAL_ROW_ID

        # Re-keyed into the OTHER namespace — the 21-group shape from queue 411.
        live.statpal_fixture_id = STATPAL_ID_LONG
        assert await find_event_by_anchor(
            session,
            anchor_key_for_claim("statpal", STATPAL_ID_SHORT),
            expected_sport_id=MLB_SPORT_ID,
        ) is None

    @pytest.mark.asyncio
    async def test_a_current_espn_anchor_still_absorbs(self):
        """The must-not-regress control (gotcha #43): refusing everything is not a fix."""
        current = _row(event_id=ESPN_ROW_ID, espn_id=STALE_ESPN_ID)
        session = _AnchorSession(
            anchors={("espn", STALE_ESPN_ID, ANCHOR_KIND_GAME): ESPN_ROW_ID},
            event_sports={ESPN_ROW_ID: MLB_SPORT_ID},
            structured_candidates=[current],
            sport_id=MLB_SPORT_ID,
        )
        assert await find_event_by_anchor(
            session,
            anchor_key_for_claim("espn", STALE_ESPN_ID),
            expected_sport_id=MLB_SPORT_ID,
        ) == ESPN_ROW_ID

    @pytest.mark.asyncio
    async def test_a_column_less_provider_is_never_corroborated(self):
        """Kalshi has no column, so there is nothing to corroborate against.

        Corroborating anyway would refuse every anchor the two providers that
        NEEDED this channel have — they were 99.61% of `NO_ANCHOR_CHANNEL`. The
        event row deliberately carries no ESPN or StatPal id at all: a check
        that leaked past its own source map would read that as stale and this
        would go red.
        """
        row = _row(event_id=ESPN_ROW_ID, espn_id=None, statpal_fixture_id=None)
        session = _AnchorSession(
            anchors={("kalshi", SHARED_GAME_ANCHOR, ANCHOR_KIND_GAME): ESPN_ROW_ID},
            event_sports={ESPN_ROW_ID: MLB_SPORT_ID},
            structured_candidates=[row],
            sport_id=MLB_SPORT_ID,
        )
        assert await find_event_by_anchor(
            session,
            anchor_key_for_claim("kalshi", TICKER_BOS),
            expected_sport_id=MLB_SPORT_ID,
        ) == ESPN_ROW_ID
        assert await anchor_is_current(
            session, anchor_key_for_claim("kalshi", TICKER_BOS), ESPN_ROW_ID
        ) is True

    @pytest.mark.asyncio
    async def test_a_missing_event_row_is_not_current(self):
        """"The row I would corroborate against is gone" is not evidence of currency."""
        session = _AnchorSession(sport_id=MLB_SPORT_ID)
        assert await anchor_is_current(
            session, anchor_key_for_claim("espn", STALE_ESPN_ID), 999_999
        ) is False


class TestCollisionTaggingSharesThePremise:
    """A COLLISION is a *proof*. A disproven incumbent proves nothing."""

    @pytest.mark.asyncio
    async def test_a_stale_incumbent_is_not_a_duplicate(self):
        """The second-order defect: a false duplicate tag on a live event.

        Read-side corroboration makes a stale anchor harmless to absorption but
        leaves it in the unique index. When the event that GENUINELY holds the
        id then establishes its correspondence, the INSERT conflicts with the
        lie — and the pre-fix path would brand the true holder a duplicate of a
        row that no longer has any claim to the id.
        """
        stale_holder = _row(event_id=ESPN_ROW_ID, espn_id=REKEYED_ESPN_ID)
        true_holder = _row(event_id=STATPAL_ROW_ID, espn_id=STALE_ESPN_ID)
        session = _AnchorSession(
            anchors={("espn", STALE_ESPN_ID, ANCHOR_KIND_GAME): ESPN_ROW_ID},
            event_sports={
                ESPN_ROW_ID: MLB_SPORT_ID, STATPAL_ROW_ID: MLB_SPORT_ID
            },
            structured_candidates=[stale_holder, true_holder],
            sport_id=MLB_SPORT_ID,
        )

        result = await record_anchor(
            session,
            event_id=STATPAL_ROW_ID,
            key=anchor_key_for_claim("espn", STALE_ESPN_ID),
        )

        assert result.outcome == STALE_INCUMBENT
        assert result.canonical_event_id is None, (
            "a disproven incumbent must not be reported as a canonical — a "
            "caller that tags against it records a duplicate that is not one"
        )
        assert session.tagged == []

    @pytest.mark.asyncio
    async def test_a_live_incumbent_is_still_a_collision(self):
        """The control: corroboration must not disarm the detector.

        The unique index is the only proof of a duplicate this system has ever
        had. Both events genuinely carry the id — `ix_events_espn_id` is not
        unique, which is how #1204's NCAA collisions exist — so this IS the
        real thing and must still be caught.
        """
        incumbent = _row(event_id=ESPN_ROW_ID, espn_id=STALE_ESPN_ID)
        loser = _row(event_id=STATPAL_ROW_ID, espn_id=STALE_ESPN_ID)
        session = _AnchorSession(
            anchors={("espn", STALE_ESPN_ID, ANCHOR_KIND_GAME): ESPN_ROW_ID},
            event_sports={
                ESPN_ROW_ID: MLB_SPORT_ID, STATPAL_ROW_ID: MLB_SPORT_ID
            },
            structured_candidates=[incumbent, loser],
            sport_id=MLB_SPORT_ID,
        )

        result = await record_anchor(
            session,
            event_id=STATPAL_ROW_ID,
            key=anchor_key_for_claim("espn", STALE_ESPN_ID),
        )
        assert result.outcome == COLLISION
        assert result.canonical_event_id == ESPN_ROW_ID

    @pytest.mark.asyncio
    async def test_the_stale_incumbent_is_not_repointed(self):
        """Refusing to tag is not licence to move an identity.

        The stale row is removed at the re-key site, where the transaction that
        made it false can delete it atomically — not here, where this path
        cannot distinguish a disproven incumbent from one whose column is
        mid-repair.
        """
        session = _AnchorSession(
            anchors={("espn", STALE_ESPN_ID, ANCHOR_KIND_GAME): ESPN_ROW_ID},
            event_sports={
                ESPN_ROW_ID: MLB_SPORT_ID, STATPAL_ROW_ID: MLB_SPORT_ID
            },
            structured_candidates=[
                _row(event_id=ESPN_ROW_ID, espn_id=REKEYED_ESPN_ID),
                _row(event_id=STATPAL_ROW_ID, espn_id=STALE_ESPN_ID),
            ],
            sport_id=MLB_SPORT_ID,
        )
        await record_anchor(
            session,
            event_id=STATPAL_ROW_ID,
            key=anchor_key_for_claim("espn", STALE_ESPN_ID),
        )
        assert (
            session.anchors[("espn", STALE_ESPN_ID, ANCHOR_KIND_GAME)] == ESPN_ROW_ID
        )


class TestInvalidationAtTheRekeySite:
    """Harmless is not the same as gone — the stale row still holds an index slot."""

    @pytest.mark.asyncio
    async def test_a_rekey_deletes_only_this_events_claim(self):
        """`ix_events_espn_id` is NOT unique, so another row may hold it legitimately."""
        session = _AnchorSession(
            anchors={("espn", STALE_ESPN_ID, ANCHOR_KIND_GAME): ESPN_ROW_ID},
            sport_id=MLB_SPORT_ID,
        )

        assert await invalidate_scalar_anchor(
            session, source="espn", source_id=STALE_ESPN_ID,
            event_id=STATPAL_ROW_ID,
        ) == 0, "another event's anchor is not ours to delete"
        assert ("espn", STALE_ESPN_ID, ANCHOR_KIND_GAME) in session.anchors

        assert await invalidate_scalar_anchor(
            session, source="espn", source_id=STALE_ESPN_ID,
            event_id=ESPN_ROW_ID,
        ) == 1
        assert ("espn", STALE_ESPN_ID, ANCHOR_KIND_GAME) not in session.anchors

    @pytest.mark.asyncio
    async def test_an_unscoped_clear_deletes_the_key(self):
        """The NULL sweep leaves no holder, so there is nobody left to scope to."""
        session = _AnchorSession(
            anchors={("espn", STALE_ESPN_ID, ANCHOR_KIND_GAME): ESPN_ROW_ID},
            sport_id=MLB_SPORT_ID,
        )
        assert await invalidate_scalar_anchor(
            session, source="espn", source_id=STALE_ESPN_ID
        ) == 1
        assert session.anchors == {}

    @pytest.mark.asyncio
    async def test_invalidation_is_namespace_qualified_like_the_writer(self):
        """A raw source_id would miss the row the writer actually wrote."""
        session = _AnchorSession(
            anchors={("statpal", f"s6:{STATPAL_ID_SHORT}", ANCHOR_KIND_GAME): STATPAL_ROW_ID},
            sport_id=MLB_SPORT_ID,
        )
        assert await invalidate_scalar_anchor(
            session, source="statpal", source_id=STATPAL_ID_SHORT
        ) == 1
        assert session.anchors == {}

    @pytest.mark.asyncio
    async def test_an_unanchorable_id_deletes_nothing(self):
        session = _AnchorSession(sport_id=MLB_SPORT_ID)
        assert await invalidate_scalar_anchor(
            session, source="statpal", source_id="12345"
        ) == 0
        assert await invalidate_scalar_anchor(
            session, source="espn", source_id=None
        ) == 0
        assert session.anchor_deletes == []

    def test_both_rekey_paths_invalidate(self):
        """Read the real call sites, not a copy of them.

        The lifecycle obligation lives at exactly two writers of
        `events.espn_id`. An assertion about a value this test constructs would
        prove nothing about them — which is how the original defect survived
        being written (see `test_the_prediction_market_call_site_passes_the_provider_id`).
        A third writer of the column must add itself here.
        """
        import inspect

        from app.routes import source_intelligence
        from app.tasks import repair_event_espn_id

        for module in (repair_event_espn_id, source_intelligence):
            src = inspect.getsource(module)
            assert "UPDATE events" in src and "espn_id" in src, (
                f"{module.__name__} is no longer an espn_id writer — has the "
                "call site moved?"
            )
            assert "invalidate_scalar_anchor" in src, (
                f"{module.__name__} re-keys or clears events.espn_id without "
                "invalidating the anchor copied from it (CERT-410 [P1])"
            )
