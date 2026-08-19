"""The StatPal listing is not a dereference either — ruling 048's gate must fire
for BOTH StatPal ingestion call sites (#1989, queue 374).

This is the sibling of ``test_odds_listing_is_not_a_dereference.py``, on a second
provider, and it is the reason the Odds fix alone did not restore the slate.

The mechanism is identical. Both StatPal sites passed
``schedule_derived=bool(fixture.fixture_id)``, which is true whenever a fixture
carries an id — i.e. always, for MLB — so ruling 048's reachability gate never
fired, so a NEW statpal fixture id reached the +/-28h structured matcher and
absorbed onto a row that already held a DIFFERENT statpal fixture id. #1946's
shape: a flag that is always true is not a gate.

Neither endpoint is a dereference. ``:186`` reads ``get_fixtures(sport)`` and
``:342`` reads ``get_live_scores(sport)`` — both ask by SPORT and get rows back.
Arm B is for the case where the provider was handed an id and asked "what game
is this?", and neither of these is that.

Measured (queue 373 item 3, read-only replay of the real matcher's predicate
against production MLB rows 2026-08-17 -> 2026-08-28):

    :186 season-schedule  population 94   40 step-1,  54 absorptions, 54/54 conflict
    :342 livescores       population  8    0 step-1,   8 absorptions,  8/8 conflict

62 of 62. Unanchored, the same populations produce 54 and 8 CREATEs and zero
absorptions. Arm B was doing no legitimate work on this path.

``:342`` is the MORE dangerous site because of its own pre-check: it skips any
event matching on exact team names within +/-6h, which strips the same-game case
and leaves mostly the wrong-game band. Its eight survivors sat at +21.92h,
-24.00h, +4.00h, -24.00h, +22.00h, -20.00h, -20.00h, -20.00h.

Note the +4.00h one. It is inside the +/-6h pre-check and survived anyway, which
means the pre-check did not match it — it compares EXACT lowercase team names, so
any spelling difference between the livescores feed and the stored row defeats
it. The +/-6h filter is therefore a same-game-AND-identically-spelled filter, not
a same-game filter. The reachability gate closes all eight either way; the hole
is recorded here rather than fixed, so nobody later cites the pre-check as sound.

Gotcha #43 — the guard asserts BOTH directions. The absorber stops AND the two
things that must survive are pinned: Step 1 still reunites a claim with its own
fixture id (repeat polls untouched), and a cross-source claim still joins the row
StatPal created.
"""
import ast
import inspect
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.services.event_registry import (
    EventClaim,
    EventIdentity,
    STATPAL_LISTING_IS_NOT_A_DEREFERENCE,
    find_or_create_event,
    _sport_id_cache,
)
from tests.test_event_registry import _FakeRegistrySession

MLB_SPORT_ID = 53232


def _utc(s):
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


# ── The headline specimen, documented on #1989 (measured 2026-08-18) ────────
#
# StatPal's own season schedule distinguishes these two games by id:
#     fixture 355284 = Tigers @ Pirates 2026-08-18T22:40Z
#     fixture 355299 = Tigers @ Pirates 2026-08-19T16:35Z
#
# Production row 15199901 holds fixture 355284 (Tuesday) but its commence_time
# had already been dragged to Wednesday's 16:35Z by the Odds absorber. So the
# 355299 claim finds it at dt = +0.00h and absorbs it, writing StatPal's second
# id onto a row that already carries StatPal's first.
#
# That dt of exactly zero is the trap, and it is why this file exists: a 0.00h
# reading is not evidence of a same-game match, it is evidence that a previous
# absorption already COMPLETED. The two absorbers fed each other.
SPECIMEN_ROW_ID = 15199901
SPECIMEN_HELD_FIXTURE = "355284"
SPECIMEN_CLAIM_FIXTURE = "355299"
SPECIMEN_AWAY = "Detroit Tigers"
SPECIMEN_HOME = "Pittsburgh Pirates"
SPECIMEN_CLAIM_TIME = "2026-08-19T16:35:00"

# The eight :342 survivors' measured offsets, in hours, from the shadow read.
# Every one is the adjacent game in the same series — the annulus the +/-6h
# pre-check leaves behind after it removes the same-game case.
LIVESCORES_MEASURED_OFFSETS_H = (
    21.92, -24.00, 4.00, -24.00, 22.00, -20.00, -20.00, -20.00,
)


def _row(*, event_id, away, home, commence, status, fixture_id):
    return SimpleNamespace(
        id=event_id, sport_id=MLB_SPORT_ID,
        away_team_name=away, home_team_name=home,
        commence_time=_utc(commence) if isinstance(commence, str) else commence,
        status=status, external_id=None, espn_id=None,
        statpal_fixture_id=fixture_id, commence_time_source="statpal",
        completed_at=None, event_tags=[],
    )


def _session(rows):
    return _FakeRegistrySession(
        source_matches={r.statpal_fixture_id: r for r in rows if r.statpal_fixture_id},
        structured_candidates=list(rows),
        sport_id=MLB_SPORT_ID,
    )


def _identity(fixture_id, away, home, commence, *, schedule_derived, status="scheduled"):
    return EventIdentity(
        sport_key="baseball_mlb",
        home_team_name=home, away_team_name=away,
        commence_time=_utc(commence) if isinstance(commence, str) else commence,
        claim=EventClaim("statpal", fixture_id, schedule_derived=schedule_derived),
        commence_time_source="statpal", status=status,
    )


@pytest.fixture(autouse=True)
def _seed_sport_cache():
    _sport_id_cache["baseball_mlb"] = MLB_SPORT_ID
    yield
    _sport_id_cache.pop("baseball_mlb", None)


def _specimen_rows():
    return [_row(
        event_id=SPECIMEN_ROW_ID, away=SPECIMEN_AWAY, home=SPECIMEN_HOME,
        commence=SPECIMEN_CLAIM_TIME, status="live",
        fixture_id=SPECIMEN_HELD_FIXTURE,
    )]


class TestTheAbsorber:
    """The measured defect, and that the shipped claim value ends it."""

    @pytest.mark.asyncio
    async def test_specimen_absorbs_as_deployed(self):
        """AS DEPLOYED — pinned so it cannot come back quietly.

        The claim carries fixture 355299; the row already holds 355284. StatPal
        itself says those are two different games, so absorbing here uses the
        provider's authority to merge two rows that same provider distinguishes.
        """
        rows = _specimen_rows()
        event, was_created = await find_or_create_event(
            _session(rows),
            _identity(SPECIMEN_CLAIM_FIXTURE, SPECIMEN_AWAY, SPECIMEN_HOME,
                      SPECIMEN_CLAIM_TIME, schedule_derived=True),
        )
        assert not was_created, "as deployed, this claim absorbs rather than creates"
        assert event.id == SPECIMEN_ROW_ID
        assert event.statpal_fixture_id == SPECIMEN_HELD_FIXTURE, (
            "the absorbed row KEEPS its own fixture id — the claim's id is "
            "silently dropped on the floor, which is why the symptom is a "
            "MISSING row rather than a colliding one"
        )

    @pytest.mark.asyncio
    async def test_specimen_creates_under_the_shipped_value(self):
        """SHIPPED — ruling 048's gate fires; the claim creates its own row."""
        rows = _specimen_rows()
        event, was_created = await find_or_create_event(
            _session(rows),
            _identity(SPECIMEN_CLAIM_FIXTURE, SPECIMEN_AWAY, SPECIMEN_HOME,
                      SPECIMEN_CLAIM_TIME,
                      schedule_derived=STATPAL_LISTING_IS_NOT_A_DEREFERENCE),
        )
        assert was_created, "the gate must fire — a StatPal listing claim creates"
        assert event.id != SPECIMEN_ROW_ID
        assert event.statpal_fixture_id == SPECIMEN_CLAIM_FIXTURE, (
            "the created row carries the claim's own fixture id"
        )
        assert "provenance:unanchored" in event.event_tags, (
            "ruling 048: the create is a REPAIRABLE FACT — the unanchored tag is "
            "what the duplicate meter reads and reconciliation drains against"
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("offset_h", LIVESCORES_MEASURED_OFFSETS_H)
    async def test_livescores_annulus_absorbs_as_deployed(self, offset_h):
        """The :342 band. Every measured survivor is the adjacent game.

        The offsets are the measured ones; the club pair is the specimen's,
        standing in for the eight real pairs so the band itself is what is under
        test. All eight are inside the matcher's +/-28h window.

        Seven of the eight also sit outside the site's own +/-6h pre-check, which
        is the expected shape: the pre-check removes the same-game case and
        leaves the wrong-game annulus.

        The eighth is at +4.00h and is INSIDE that pre-check — so the pre-check
        did not remove it. It cannot have, because the pre-check matches on
        EXACT lowercase team names, and an exact-string comparison is defeated by
        any spelling difference between StatPal's livescores feed and the row's
        stored names. That is worth stating plainly: the +/-6h filter is not a
        same-game filter, it is a same-game-AND-identically-spelled filter, and
        the gap between those two is a hole a wrong-game claim fits through at
        dt as small as four hours. Narrowing that hole is NOT this fix — the
        reachability gate closes all eight regardless — but it should not be
        recorded as if the pre-check were sound.
        """
        assert abs(offset_h) <= 28.0, "outside the matcher's window"

        held = _utc(SPECIMEN_CLAIM_TIME)
        claim_time = held + _hours(offset_h)
        rows = [_row(
            event_id=SPECIMEN_ROW_ID, away=SPECIMEN_AWAY, home=SPECIMEN_HOME,
            commence=held, status="live", fixture_id=SPECIMEN_HELD_FIXTURE,
        )]
        event, was_created = await find_or_create_event(
            _session(rows),
            _identity("355901", SPECIMEN_AWAY, SPECIMEN_HOME, claim_time,
                      schedule_derived=True, status="live"),
        )
        assert not was_created, f"as deployed, the {offset_h:+.2f}h claim absorbs"
        assert event.id == SPECIMEN_ROW_ID

    @pytest.mark.asyncio
    @pytest.mark.parametrize("offset_h", LIVESCORES_MEASURED_OFFSETS_H)
    async def test_livescores_annulus_creates_under_the_shipped_value(self, offset_h):
        held = _utc(SPECIMEN_CLAIM_TIME)
        claim_time = held + _hours(offset_h)
        rows = [_row(
            event_id=SPECIMEN_ROW_ID, away=SPECIMEN_AWAY, home=SPECIMEN_HOME,
            commence=held, status="live", fixture_id=SPECIMEN_HELD_FIXTURE,
        )]
        event, was_created = await find_or_create_event(
            _session(rows),
            _identity("355901", SPECIMEN_AWAY, SPECIMEN_HOME, claim_time,
                      schedule_derived=STATPAL_LISTING_IS_NOT_A_DEREFERENCE,
                      status="live"),
        )
        assert was_created, f"the {offset_h:+.2f}h claim must create, not absorb"
        assert event.id != SPECIMEN_ROW_ID

    @pytest.mark.asyncio
    async def test_no_window_query_is_issued_at_all_under_the_shipped_value(self):
        """The gate is on REACHABILITY, not a refusal inside the matcher.

        Ruling 048 chose reachability precisely because a refusal is a behaviour
        the next patch can tune. Assert the matcher is never entered.
        """
        session = _session(_specimen_rows())
        await find_or_create_event(
            session,
            _identity(SPECIMEN_CLAIM_FIXTURE, SPECIMEN_AWAY, SPECIMEN_HOME,
                      SPECIMEN_CLAIM_TIME,
                      schedule_derived=STATPAL_LISTING_IS_NOT_A_DEREFERENCE),
        )
        emitted = [str(s) for s in session.statements]
        assert not any("commence_time BETWEEN" in s for s in emitted), (
            "the structured matcher was reached — the gate did not fire"
        )
        assert not any("pg_advisory_xact_lock" in s for s in emitted)
        assert session.structured_params is None


class TestWhatMustSurvive:
    """Gotcha #43: a cap's guard asserts BOTH directions."""

    @pytest.mark.asyncio
    async def test_step_1_still_reunites_a_claim_with_its_own_fixture_id(self):
        """Repeat polls are untouched. This is the whole point of Step 1.

        The claim carries the fixture id the row already holds, so it resolves
        with no window and no name comparison — even though the times differ by
        more than the matcher's window would allow.
        """
        rows = [_row(
            event_id=SPECIMEN_ROW_ID, away=SPECIMEN_AWAY, home=SPECIMEN_HOME,
            commence="2026-08-18T22:40:00", status="live",
            fixture_id=SPECIMEN_HELD_FIXTURE,
        )]
        session = _session(rows)
        event, was_created = await find_or_create_event(
            session,
            _identity(SPECIMEN_HELD_FIXTURE, SPECIMEN_AWAY, SPECIMEN_HOME,
                      "2026-08-21T22:40:00",  # +72h, far outside +/-28h
                      schedule_derived=STATPAL_LISTING_IS_NOT_A_DEREFERENCE),
        )
        assert not was_created, "a claim on its OWN id must find its row"
        assert event.id == SPECIMEN_ROW_ID
        assert session.structured_params is None, (
            "Step 1 resolved it — the window matcher was never needed"
        )

    @pytest.mark.asyncio
    async def test_an_espn_claim_can_still_join_the_row_statpal_created(self):
        """The cross-source join arm B actually exists for is not disturbed.

        This fix narrows STATPAL's claims only. An ESPN claim that genuinely
        dereferences still reaches the matcher and joins.
        """
        rows = [_row(
            event_id=SPECIMEN_ROW_ID, away=SPECIMEN_AWAY, home=SPECIMEN_HOME,
            commence=SPECIMEN_CLAIM_TIME, status="scheduled",
            fixture_id=SPECIMEN_HELD_FIXTURE,
        )]
        identity = EventIdentity(
            sport_key="baseball_mlb",
            home_team_name=SPECIMEN_HOME, away_team_name=SPECIMEN_AWAY,
            commence_time=_utc(SPECIMEN_CLAIM_TIME),
            claim=EventClaim("espn", "401816587", schedule_derived=True),
            commence_time_source="espn", status="scheduled",
        )
        event, was_created = await find_or_create_event(_session(rows), identity)
        assert not was_created, (
            "a genuinely dereferenced ESPN claim must still find the StatPal row "
            "— that join is what arm B is FOR"
        )
        assert event.id == SPECIMEN_ROW_ID


class TestTheCallSitesStayHonest:
    """Source-shape assertions — the fails-first anchor.

    By AST and not by grep, deliberately, and now twice-learned (Fable ruling
    (a), 2026-08-19): guards walk ASTs, not text. A textual scan of this module
    double-counts ``commence_time_source="statpal"`` two lines below the claim,
    and reads a wrapped call differently from a one-line one — so it can pass on
    the formatting rather than on the code, which is the exact failure mode this
    whole file is about.
    """

    STATPAL_MODULES = ("app.tasks.statpal_sync",)

    def _statpal_claim_sites(self):
        import importlib

        sites = []
        for mod_name in self.STATPAL_MODULES:
            mod = importlib.import_module(mod_name)
            tree = ast.parse(inspect.getsource(mod))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                fn = node.func
                name = getattr(fn, "id", None) or getattr(fn, "attr", None)
                if name != "EventClaim" or not node.args:
                    continue
                first = node.args[0]
                if not (isinstance(first, ast.Constant) and first.value == "statpal"):
                    continue
                kw = {k.arg: k.value for k in node.keywords}
                sites.append(SimpleNamespace(
                    module=mod_name, lineno=node.lineno, keywords=kw,
                    schedule_derived=kw.get("schedule_derived"),
                ))
        return sites

    def test_both_statpal_call_sites_exist_and_are_accounted_for(self):
        sites = self._statpal_claim_sites()
        assert len(sites) == 2, (
            f"expected exactly 2 statpal EventClaim sites, found {len(sites)}: "
            f"{[(s.module, s.lineno) for s in sites]}. A NEW StatPal ingestion "
            "call site is the moment to answer the provenance question (ruling "
            "048) — add it here deliberately, do not raise the count to pass."
        )

    def test_no_statpal_call_site_asserts_arm_b(self):
        for site in self._statpal_claim_sites():
            node = site.schedule_derived
            is_true = isinstance(node, ast.Constant) and node.value is True
            assert not is_true, (
                f"{site.module}:{site.lineno} asserts ruling 048 arm B on a "
                "statpal claim. Both StatPal endpoints are LISTINGS — we asked "
                "by SPORT. Measured cost: 62 of 62 window absorptions landed on "
                "a row already holding a DIFFERENT statpal fixture id."
            )

    def test_no_statpal_call_site_derives_arm_b_from_the_id_being_present(self):
        """``bool(fixture.fixture_id)`` is the exact defect, not a near miss.

        It reads as a guard and is not one: it is true of every record StatPal
        has ever emitted for MLB. #1946's shape. Pin the SHAPE, because the next
        person to re-add it will write it as a call, not as ``True``.
        """
        for site in self._statpal_claim_sites():
            node = site.schedule_derived
            assert not isinstance(node, ast.Call), (
                f"{site.module}:{site.lineno} computes schedule_derived at the "
                "call site. A flag that is always true is not a gate — cite the "
                "named constant instead."
            )

    def test_every_statpal_call_site_cites_the_named_reason(self):
        for site in self._statpal_claim_sites():
            node = site.schedule_derived
            cited = isinstance(node, ast.Name) and (
                node.id == "STATPAL_LISTING_IS_NOT_A_DEREFERENCE"
            )
            assert cited, (
                f"{site.module}:{site.lineno} passes a bare literal or a "
                "computed value. Cite the named constant: a named False carries "
                "its reason to whoever reads it next."
            )

    def test_the_named_constant_is_false(self):
        assert STATPAL_LISTING_IS_NOT_A_DEREFERENCE is False


def _hours(h):
    from datetime import timedelta
    return timedelta(hours=h)
