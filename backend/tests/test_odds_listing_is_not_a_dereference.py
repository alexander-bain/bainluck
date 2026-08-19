"""The Odds listing is not a dereference — ruling 048's gate must fire for Odds
ingestion (#1989, upstream half of #1981).

Every specimen below is a production row or a live Odds API record measured on
2026-08-18. The mechanism, in one sentence: all four Odds ingestion call sites
passed ``schedule_derived=True``, so ruling 048's reachability gate never fired,
so a NEW odds_api id reached the +/-28h structured matcher and absorbed onto a
row that already held a DIFFERENT odds_api id — a row the provider's own
schedule distinguishes from the claim.

The measured before/after (22 live MLB records, real ``find_or_create_event``
driven over a snapshot of production rows):

    as deployed   6 step-1 hits, 16 window absorptions, 16/16 ID-CONFLICT, 0 creates
    shipped       6 step-1 hits,  0 window absorptions,               16 creates

ZERO of the 16 were the legitimate no-id cross-source join that arm B exists
for. Arm B was doing no legitimate work on this path; it was 100% absorber.

Gotcha #43 — the guard asserts BOTH directions. The absorber stops AND the two
things that must survive are pinned: Step 1 still reunites a claim with its own
id (repeat polls are untouched), and an ESPN claim still joins the row Odds API
created (the cross-source join arm B was actually written for).
"""
import ast
import inspect
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.services.event_registry import (
    EventClaim,
    EventIdentity,
    ODDS_LISTING_IS_NOT_A_DEREFERENCE,
    find_or_create_event,
    _sport_id_cache,
)
from tests.test_event_registry import _FakeRegistrySession

MLB_SPORT_ID = 53232


def _utc(s):
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


# ── Production rows, read 2026-08-18 ────────────────────────────────────────
# Each is the sibling the corresponding Aug-19 claim absorbed onto, with the
# odds_api id it already held.
_PROD_ROWS = [
    # (event_id, away, home, commence_time, status, external_id, espn_id)
    (15199901, "Detroit Tigers", "Pittsburgh Pirates",
     "2026-08-19T16:35:00", "live", "f7e02d88c3c8adff188802734b303bb7", "401816572"),
    (15199884, "Chicago White Sox", "Chicago Cubs",
     "2026-08-19T18:20:00", "live", "8ccc90357b1b20ca35a6c2da51638dbc", None),
    (15200818, "Toronto Blue Jays", "Tampa Bay Rays",
     "2026-08-20T17:10:00", "live", "8d5f120fc3ea67377d7def8efef256ea", None),
    (15200817, "New York Yankees", "Baltimore Orioles",
     "2026-08-20T22:35:00", "live", "125ac4ae06bb1ca6b1fcc189bd321490", None),
]

# ── The pop-3 claims, from the live Odds API MLB slate ──────────────────────
# Every one is a real Aug-19 game whose id production holds on no row at all.
# commence_time is the provider's own value, verbatim from the live response.
_POP3_CLAIMS = [
    # (odds_api id, away, home, commence_time, absorbed_onto)
    ("c0a1041457ba1cf76c5f2a1ac9eb70bc", "Detroit Tigers", "Pittsburgh Pirates",
     "2026-08-19T16:36:00", 15199901),
    ("1b3b4a290694391bf3fe17adc8693cbd", "Chicago White Sox", "Chicago Cubs",
     "2026-08-19T00:06:00", 15199884),
    ("d6738463ee902306e2e71f297603b26e", "Toronto Blue Jays", "Tampa Bay Rays",
     "2026-08-19T22:40:00", 15200818),
    ("e1c63fd17f608a04657ea391d6e50645", "New York Yankees", "Baltimore Orioles",
     "2026-08-19T22:36:00", 15200817),
]


def _candidates():
    return [
        SimpleNamespace(
            id=eid, sport_id=MLB_SPORT_ID, away_team_name=away, home_team_name=home,
            commence_time=_utc(ct), status=status, external_id=ext, espn_id=espn,
            statpal_fixture_id=None, commence_time_source="odds_api",
            completed_at=None, event_tags=[],
        )
        for eid, away, home, ct, status, ext, espn in _PROD_ROWS
    ]


def _session():
    cands = _candidates()
    return _FakeRegistrySession(
        source_matches={c.external_id: c for c in cands if c.external_id},
        structured_candidates=cands,
        sport_id=MLB_SPORT_ID,
    )


def _identity(oid, away, home, ct, *, schedule_derived):
    return EventIdentity(
        sport_key="baseball_mlb",
        home_team_name=home, away_team_name=away, commence_time=_utc(ct),
        claim=EventClaim("odds_api", oid, schedule_derived=schedule_derived),
        commence_time_source="odds_api", status="scheduled",
    )


@pytest.fixture(autouse=True)
def _seed_sport_cache():
    _sport_id_cache["baseball_mlb"] = MLB_SPORT_ID
    yield
    _sport_id_cache.pop("baseball_mlb", None)


class TestTheAbsorber:
    """The measured defect, and that the shipped claim value ends it."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("oid,away,home,ct,onto", _POP3_CLAIMS)
    async def test_pop3_claim_absorbs_a_sibling_when_the_claim_lies(
        self, oid, away, home, ct, onto
    ):
        """AS DEPLOYED. This is the bug, pinned so it cannot come back quietly.

        The claim carries a brand-new odds_api id; the row it lands on already
        holds a different one. Absorbing here uses the provider's authority to
        merge two games that same provider distinguishes.
        """
        event, was_created = await find_or_create_event(
            _session(), _identity(oid, away, home, ct, schedule_derived=True)
        )
        assert not was_created, "as deployed, this claim absorbs rather than creates"
        assert event.id == onto
        assert event.external_id != oid, (
            "the absorbed row KEEPS its own external_id — _attach_claim does not "
            "overwrite — so the claim's id is silently dropped on the floor"
        )
        # It reached the row THROUGH the window. The gap is not asserted to a
        # hand-copied figure — it is a derived quantity that keeps moving,
        # because _update_fields_by_priority drags the absorbed row's
        # commence_time onto the claim's on the very next poll. That drag is why
        # a row first absorbed at +18h reads +0.00h an hour later, and why "the
        # times match now" is evidence the absorption COMPLETED, not evidence it
        # was right.
        gap = abs((event.commence_time - _utc(ct)).total_seconds()) / 3600.0
        assert gap <= 28.0, f"outside the +/-28h match window: {gap:.2f}h"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("oid,away,home,ct,onto", _POP3_CLAIMS)
    async def test_pop3_claim_creates_under_the_shipped_value(
        self, oid, away, home, ct, onto
    ):
        """SHIPPED. Ruling 048's gate fires; the claim creates its own row."""
        session = _session()
        event, was_created = await find_or_create_event(
            session,
            _identity(oid, away, home, ct,
                      schedule_derived=ODDS_LISTING_IS_NOT_A_DEREFERENCE),
        )
        assert was_created, "the gate must fire — an Odds listing claim creates"
        assert event.id != onto
        assert event.external_id == oid, "the created row carries the claim's own id"
        assert "provenance:unanchored" in event.event_tags, (
            "ruling 048: the create is a REPAIRABLE FACT — the unanchored tag is "
            "what the duplicate meter reads and what reconciliation drains against"
        )

    @pytest.mark.asyncio
    async def test_no_window_query_is_issued_at_all_under_the_shipped_value(self):
        """The gate is on REACHABILITY, not on a refusal inside the matcher.

        Ruling 048 chose reachability precisely because a refusal is a behaviour
        the next patch can tune. So assert the matcher is never entered: no
        +/-28h candidate query is emitted, and no advisory lock is taken.
        """
        oid, away, home, ct, _ = _POP3_CLAIMS[0]
        session = _session()
        await find_or_create_event(
            session,
            _identity(oid, away, home, ct,
                      schedule_derived=ODDS_LISTING_IS_NOT_A_DEREFERENCE),
        )
        emitted = [str(s) for s in session.statements]
        assert not any("commence_time BETWEEN" in s for s in emitted), (
            "the structured matcher was reached — the gate did not fire"
        )
        assert not any("pg_advisory_xact_lock" in s for s in emitted)
        assert session.structured_params is None


class TestWhatMustSurvive:
    """Gotcha #43: a cap's guard asserts BOTH directions.

    Six of the 22 measured records resolved at Step 1 and must keep doing so,
    and the cross-source join arm B was actually written for must keep working.
    """

    @pytest.mark.asyncio
    async def test_step1_still_reunites_a_claim_with_its_own_id(self):
        """Repeat polls are untouched: Step 1 needs no window and no names."""
        row = _PROD_ROWS[0]
        eid, away, home, ct, _, ext, _ = row
        event, was_created = await find_or_create_event(
            _session(),
            _identity(ext, away, home, ct,
                      schedule_derived=ODDS_LISTING_IS_NOT_A_DEREFERENCE),
        )
        assert not was_created
        assert event.id == eid, (
            "a claim whose id is already on a row must still find it — the gate "
            "sits on Step 3, and Step 1 runs before it"
        )

    @pytest.mark.asyncio
    async def test_an_espn_claim_still_joins_the_row_odds_api_created(self):
        """Arm B survives for the source it exists for.

        ESPN dereferences: it is handed an espn_id and answers with that game's
        teams and date. That claim must still find the odds_api-created row
        rather than duplicating it.
        """
        eid, away, home, ct, _, _, espn = _PROD_ROWS[0]
        session = _session()
        identity = EventIdentity(
            sport_key="baseball_mlb",
            home_team_name=home, away_team_name=away, commence_time=_utc(ct),
            claim=EventClaim("espn", "401816572", schedule_derived=True),
            commence_time_source="espn", status="live",
        )
        event, was_created = await find_or_create_event(session, identity)
        assert not was_created, (
            "ruling 048 arm B is a CROSS-source arm and must keep working — "
            "narrowing the Odds claim must not narrow ESPN's"
        )
        assert event.id == eid

    @pytest.mark.asyncio
    async def test_a_genuinely_new_game_still_creates(self):
        """No candidate, no absorption question — the create path is unchanged."""
        event, was_created = await find_or_create_event(
            _session(),
            _identity("brand-new-id", "Seattle Mariners", "Milwaukee Brewers",
                      "2026-08-19T18:10:00",
                      schedule_derived=ODDS_LISTING_IS_NOT_A_DEREFERENCE),
        )
        assert was_created
        assert event.external_id == "brand-new-id"


class TestTheCallSitesStayHonest:
    """Source-shape assertions — the fails-first anchor.

    These are what make the fix a fix rather than an edit. The defect was not a
    wrong value in one place; it was FOUR call sites all asserting arm B on an
    argument ("id and teams arrive together") that is true of every listing any
    provider has ever emitted. #1946's shape: a flag that is always true is not
    a gate. So pin the call sites, not just the behaviour.
    """

    ODDS_MODULES = ("app.tasks.odds_polling", "app.tasks.sports")

    def _odds_claim_sites(self):
        """Every ``EventClaim("odds_api", ...)`` construction, found structurally.

        By AST and not by grep, deliberately. A textual scan of this file
        double-counts ``commence_time_source="odds_api"`` two lines below the
        claim, and it reads a wrapped call differently from a one-line one — so
        it can pass on the formatting rather than on the code, which is the
        exact failure mode this whole test file is about.
        """
        import ast
        import importlib

        sites = []
        for mod_name in self.ODDS_MODULES:
            mod = importlib.import_module(mod_name)
            src = inspect.getsource(mod)
            tree = ast.parse(src)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                fn = node.func
                name = getattr(fn, "id", None) or getattr(fn, "attr", None)
                if name != "EventClaim":
                    continue
                if not node.args:
                    continue
                first = node.args[0]
                if not (isinstance(first, ast.Constant) and first.value == "odds_api"):
                    continue
                kw = {k.arg: k.value for k in node.keywords}
                sites.append(SimpleNamespace(
                    module=mod_name,
                    lineno=node.lineno,
                    keywords=kw,
                    schedule_derived=kw.get("schedule_derived"),
                ))
        return sites

    def test_all_four_odds_call_sites_exist_and_are_accounted_for(self):
        sites = self._odds_claim_sites()
        assert len(sites) == 4, (
            f"expected exactly 4 odds_api EventClaim sites, found {len(sites)}: "
            f"{[(s.module, s.lineno) for s in sites]}. A NEW Odds ingestion call "
            "site is the moment to answer the provenance question (ruling 048) — "
            "add it here deliberately, do not raise the count to make this pass."
        )

    def test_no_odds_call_site_asserts_arm_b(self):
        for site in self._odds_claim_sites():
            node = site.schedule_derived
            is_true = isinstance(node, ast.Constant) and node.value is True
            assert not is_true, (
                f"{site.module}:{site.lineno} asserts ruling 048 arm B on an odds_api "
                "claim. The Odds /v4/sports/{sport}/odds response is a LISTING, "
                "not a dereference: we asked by SPORT and the id is the row's "
                "primary key. Measured cost of this assertion — 16 of 16 window "
                "absorptions landed on a row already holding a DIFFERENT "
                "odds_api id, and event 15199901 ended up a FINAL Aug-18 game "
                "sitting at Aug-19's first pitch marked live."
            )

    def test_every_odds_call_site_cites_the_named_reason(self):
        for site in self._odds_claim_sites():
            node = site.schedule_derived
            cited = isinstance(node, ast.Name) and (
                node.id == "ODDS_LISTING_IS_NOT_A_DEREFERENCE"
            )
            assert cited, (
                f"{site.module}:{site.lineno} passes a bare literal. Cite the named "
                "constant: the bare literal is exactly what got flipped to True, "
                "and a named False carries its reason to whoever reads it next."
            )

    def test_the_named_constant_is_false(self):
        assert ODDS_LISTING_IS_NOT_A_DEREFERENCE is False


class TestTheSpecimenIsRealAndStaysDescribed:
    """The end-to-end symptom, recorded so the issue body cannot drift from it.

    Event 15199901 held espn_id 401816572 (ESPN: 2026-08-18T22:40Z,
    STATUS_FINAL) while its commence_time had been dragged to 2026-08-19T16:35Z
    — a DIFFERENT game, ESPN 401816587, STATUS_SCHEDULED — and its status set to
    live. The real Wednesday game had no row in production at all.
    """

    def test_the_absorbed_row_carries_a_different_games_espn_id(self):
        row = next(r for r in _PROD_ROWS if r[0] == 15199901)
        _, _, _, commence, status, _, espn = row
        assert espn == "401816572"
        assert commence == "2026-08-19T16:35:00", (
            "the row sits at the Aug-19 game's first pitch while identifying, by "
            "espn_id, as the Aug-18 game that already finished"
        )
        assert status == "live"

    def test_the_two_espn_ids_are_a_day_apart(self):
        """Sanity on the specimen's own arithmetic — 401816572 vs 401816587."""
        aug18 = _utc("2026-08-18T22:40:00")
        aug19 = _utc("2026-08-19T16:35:00")
        assert timedelta(hours=17) < (aug19 - aug18) < timedelta(hours=18)
