"""MARKING A ROW RETIRED MUST TAKE IT OFF THE SITE — lane1/132.

═══ WHY THIS SUITE EXISTS ═══

``events.status`` has carried two retirement markers for months, both written by
shipped code and both with rows in the table:

    ``merged``  21 rows — ``routes/admin_backfill_linkage.py``,
                ``UPDATE events SET status = 'merged' WHERE id = :orphan_id``
    ``voided``  66 rows — the fixture will not be played

Measured on production 2026-09-05: all 87 are in the past (``future_n = 0`` in a
``GROUP BY status`` census), so nothing a reader wants today is behind this gate.

Every LIST-shaped surface reaches events through a hand-written status
ALLOWLIST — ``_SEARCH_STATUSES``, ``_SEARCH_STARTED_STATUSES``,
``EVENT_LIST_DEFAULT_STATUSES``, ``RECENT_RAIL_STATUSES`` — so all four have
excluded both words since the day they were written. **By omission, not on
purpose**, which is a different thing and is why half this file is about them.

The BY-ID read had no gate at all. ``GET /api/events/{event_id}`` selected on
the primary key and served whatever came back, so a row could be marked retired
and its page kept rendering, fully dressed. The specimen is event ``14751059``:
Denver Broncos at Arizona Cardinals, 2026-12-27, a game that will never be
played — Denver and Arizona are in different conferences and meet once a season,
on 2026-10-25, and the Cardinals are already playing New Orleans at that exact
minute. It renders with a price from one sportsbook, a countdown and a drawn
win-probability chart.

**The general clause, and it is the mirror of the one ``EVENT_SUSPENDED`` is
written under (CERT-786).** There, a new word in a vocabulary was not shipped
until every consumer had been shown it. Here, a word that means *stop showing
this* is not shipped until every consumer that can reach a row WITHOUT
consulting the vocabulary has been taught to ask. An allowlist asks by
construction. A primary-key lookup never asks at all — and a lookup is exactly
the read that a URL someone already has open goes through.

═══ WHAT IS TESTED HERE, AND WHAT IS NOT ═══

Everything runs the REAL object: the route function itself, and the four
allowlists imported from the modules the routes import them from — not copies.
A copy is how CERT-786 got through, and the copy that did it was in a test.

The two directions are both pinned and they are pinned separately, because a
suppression that is too wide is the same bug facing the other way:

  * :class:`TestTheRetiredRowIsRefused` — the ship;
  * :class:`TestTheLiveVocabularyIsUntouched` — every state a reader is
    entitled to see is still served, on the same route, through the same code.
    These are green in BOTH arms by construction (they route only through
    symbols that predate this change), so a red here means the fix is too wide,
    never that it is absent.

The frontend half — what a reader is told when the 410 arrives — is guarded in
``frontend/__tests__/lib/retiredRowIsGoneNotRefused.test.ts``.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import pathlib
import re

import pytest
from fastapi import HTTPException

from app.routes.events import (
    EVENT_LIST_DEFAULT_STATUSES,
    _SEARCH_STARTED_STATUSES,
    _SEARCH_STATUSES,
)
from app.utils.event_completion import (
    EVENT_SUSPENDED,
    RECENT_RAIL_STATUSES,
    RETIRED_STATUSES,
    SETTLED_STATUSES,
    is_retired_event_status,
)

UTC = dt.timezone.utc

# The production specimen, id for id (lane1/131, re-confirmed 2026-09-05).
GHOST = 14751059  # Cardinals v Broncos, 2026-12-27 18:00Z — never played
REAL_MEETING = 14750000  # stand-in id for the 2026-10-25 game that IS real
SPORT_NFL = 3

#: Every state a reader is entitled to be shown. Named here so a future widening
#: of :data:`RETIRED_STATUSES` cannot quietly eat one of them without this file
#: going red — the widening would have to delete a line, which review can see.
SERVABLE_STATUSES = ("scheduled", "live", EVENT_SUSPENDED, "completed", "closed")


# =============================================================================
# Part 0 — the predicate itself.
# =============================================================================


class TestThePredicate:
    def test_both_shipped_markers_are_retired(self):
        assert is_retired_event_status("merged")
        assert is_retired_event_status("voided")

    @pytest.mark.parametrize("status", SERVABLE_STATUSES)
    def test_no_servable_state_is_retired(self, status):
        """The set and the vocabulary do not overlap. Asserted per-word so the
        failure names which word was eaten."""
        assert not is_retired_event_status(status)

    def test_the_two_sets_are_disjoint(self):
        assert RETIRED_STATUSES.isdisjoint(SERVABLE_STATUSES)
        assert RETIRED_STATUSES.isdisjoint(SETTLED_STATUSES)

    @pytest.mark.parametrize("status", [None, "", "Merged", "MERGED", "archived", 7])
    def test_an_unrecognised_state_is_not_retired(self, status):
        """A row whose state we do not recognise is a row we have no standing to
        hide. `None` included: a NULL status must not blank a page.

        Case matters and is deliberate — the column is written by
        ``UPDATE ... SET status = 'merged'`` in lower case, and a predicate that
        quietly matched `Merged` would also be claiming to know about a writer
        that does not exist.
        """
        assert not is_retired_event_status(status)


# =============================================================================
# Part 1 — the four allowlists. They already exclude the retired words; this
# pins that they still do, on the objects the routes actually use.
#
# This is the "shared judgment needs a call-site guard" half. The predicate
# above protects the by-id read; nothing protects a LIST surface except its own
# allowlist, so the allowlists are the call sites and they are asserted here.
# =============================================================================

#: name → the real list object, imported from the module that spends it.
LIVE_ALLOWLISTS = {
    "events._SEARCH_STATUSES": _SEARCH_STATUSES,
    "events._SEARCH_STARTED_STATUSES": _SEARCH_STARTED_STATUSES,
    "events.EVENT_LIST_DEFAULT_STATUSES": EVENT_LIST_DEFAULT_STATUSES,
    "event_completion.RECENT_RAIL_STATUSES": RECENT_RAIL_STATUSES,
}


class TestTheListSurfacesNeverAdmitARetiredRow:
    @pytest.mark.parametrize("name", sorted(LIVE_ALLOWLISTS))
    def test_no_allowlist_contains_a_retired_status(self, name):
        allowlist = LIVE_ALLOWLISTS[name]
        leaked = RETIRED_STATUSES.intersection(allowlist)
        assert not leaked, (
            f"{name} admits {sorted(leaked)} — a retired row would render on "
            f"every surface that spends this list"
        )

    @pytest.mark.parametrize("name", sorted(LIVE_ALLOWLISTS))
    def test_every_allowlist_is_still_a_non_empty_allowlist(self, name):
        """The other direction. A list that has been emptied, or turned into a
        DENYlist, also passes the test above — and would hide everything."""
        allowlist = LIVE_ALLOWLISTS[name]
        assert allowlist, f"{name} is empty — every surface spending it is blank"
        assert set(allowlist).issubset(SERVABLE_STATUSES), (
            f"{name} contains a word that is neither servable nor retired; the "
            f"vocabulary grew and this file was not told"
        )

    def test_search_and_the_event_list_still_reach_every_servable_state(self):
        """`_SEARCH_STATUSES` and `EVENT_LIST_DEFAULT_STATUSES` are the two
        surfaces CERT-786 named twice. Nothing here may narrow them."""
        for name in ("events._SEARCH_STATUSES", "events.EVENT_LIST_DEFAULT_STATUSES"):
            missing = set(SERVABLE_STATUSES) - set(LIVE_ALLOWLISTS[name])
            assert not missing, f"{name} stopped reaching {sorted(missing)}"

    def test_the_started_arm_reaches_every_state_that_has_started(self):
        missing = set(SERVABLE_STATUSES) - {"scheduled"} - set(_SEARCH_STARTED_STATUSES)
        assert (
            not missing
        ), f"the started-only search arm stopped reaching {sorted(missing)}"


# =============================================================================
# Part 2 — the source-text call-site guard, matched on the NAME SHAPE.
#
# Parts 0 and 1 pin the lists that exist today. This one is about the list
# somebody writes next: a new route that hand-writes `Event.status.in_([...])`
# with "merged" in it re-opens the defect without touching a single symbol any
# test above imports.
# =============================================================================

_ROUTES_DIR = pathlib.Path(__file__).resolve().parents[1] / "app" / "routes"
_STATUS_IN_LITERAL = re.compile(
    r"Event\.status\.in_\(\s*\[(?P<body>[^\]]*)\]", re.DOTALL
)
_QUOTED = re.compile(r"""['"]([A-Za-z_]+)['"]""")

#: Admin routes are the ONE place a retired row must stay visible — an operator
#: reversing a retirement has to be able to see what they are reversing, and the
#: undo in Part 2 of this ship is exactly that. Scoped by filename prefix rather
#: than by an id list so a new admin route inherits the exemption.
_ADMIN_PREFIX = "admin"


class TestNoRouteHandWritesARetiredStatusIntoAStatusFilter:
    def test_every_user_facing_status_literal_is_clean(self):
        offenders = []
        scanned = 0
        for path in sorted(_ROUTES_DIR.glob("*.py")):
            if path.name.startswith(_ADMIN_PREFIX):
                continue
            source = path.read_text(encoding="utf-8")
            for match in _STATUS_IN_LITERAL.finditer(source):
                scanned += 1
                words = set(_QUOTED.findall(match.group("body")))
                leaked = RETIRED_STATUSES.intersection(words)
                if leaked:
                    line = source.count("\n", 0, match.start()) + 1
                    offenders.append(f"{path.name}:{line} admits {sorted(leaked)}")
        assert (
            not offenders
        ), "a user-facing status filter admits a retired row:\n  " + "\n  ".join(
            offenders
        )
        assert scanned >= 5, (
            f"the scanner matched only {scanned} `Event.status.in_([...])` "
            f"literals; the pattern has drifted off the code it guards and this "
            f"guard is now green for the wrong reason"
        )


# =============================================================================
# Part 3 — the ROUTE. What the reader is served.
#
# Parts 0-2 prove the vocabulary. This proves the wiring, which is the half that
# actually ships: a correct predicate the route never calls changes nothing.
#
# The harness is the one `test_market_born_duplicate_reads_as_canonical_q050`
# established — a fake session answering the route's own by-id select. Note what
# it does NOT do: it applies no status predicate of its own, because the route's
# query has none either. That is the reproduction. The row comes back whatever
# state it is in, and the ONLY thing between it and the reader is the check
# under test.
# =============================================================================


@pytest.fixture()
def route_harness(monkeypatch):
    from app.models.models import Event, Sport
    from app.routes import events as events_route

    events_route._event_detail_cache.clear()
    rows: dict[int, object] = {}

    def plant(event_id, status, *, commence, home, away, **kwargs):
        event = Event(
            id=event_id,
            sport_id=SPORT_NFL,
            home_team_name=home,
            away_team_name=away,
            commence_time=commence,
            commence_time_source="odds_api",
            status=status,
            **kwargs,
        )
        event.sport = Sport(id=SPORT_NFL, key="americanfootball_nfl", name="NFL")
        rows[event_id] = event
        return event

    class _Scalar:
        def __init__(self, value):
            self._value = value

        def scalar_one_or_none(self):
            return self._value

        def scalars(self):
            return self

        def all(self):
            return []

    class _FakeDb:
        """Answers only the by-id select. Deliberately status-blind."""

        def __init__(self):
            self.statements = []

        async def execute(self, stmt, *args, **kwargs):
            compiled = str(stmt)
            self.statements.append(compiled)
            is_event_by_id = (
                "FROM events" in compiled
                and "events.id = " in compiled
                and "odds_snapshots" not in compiled
            )
            if is_event_by_id:
                params = stmt.compile().params
                event_id = next(
                    (v for v in params.values() if isinstance(v, int)), None
                )
                return _Scalar(rows.get(event_id))
            return _Scalar(None)

    async def _no_percentiles(_db):
        return {}

    async def _no_teams(_db, _names):
        return {}

    async def _never_resolves(_db, _event_id):
        return None

    monkeypatch.setattr(events_route, "_load_gei_percentiles", _no_percentiles)
    monkeypatch.setattr(events_route, "_build_team_lookup", _no_teams)
    monkeypatch.setattr(events_route, "resolve_market_born_duplicate", _never_resolves)

    db = _FakeDb()
    return {
        "route": events_route,
        "db": db,
        "plant": plant,
        "serve": lambda event_id: asyncio.run(events_route.get_event(event_id, db=db)),
    }


def _kickoff(month, day, hour=18):
    return dt.datetime(2026, month, day, hour, tzinfo=UTC)


class TestTheRetiredRowIsRefused:
    """THE SHIP."""

    @pytest.mark.parametrize("marker", sorted(RETIRED_STATUSES))
    def test_the_ghost_url_is_gone_not_found(self, route_harness, marker):
        route_harness["plant"](
            GHOST,
            marker,
            commence=_kickoff(12, 27),
            home="Arizona Cardinals",
            away="Denver Broncos",
        )
        with pytest.raises(HTTPException) as raised:
            route_harness["serve"](GHOST)

        assert raised.value.status_code == 410, (
            "404 says 'you may have the wrong address' and every other 4xx says "
            "'the server refused the request'; neither is what happened"
        )
        assert "schedule" in str(raised.value.detail).lower(), (
            "the detail is the sentence the reader is shown — it has to say "
            "something true about the row, not just carry a code"
        )

    def test_the_query_the_route_issues_has_no_status_gate(self, route_harness):
        """The reproduction. The protection is NOT in the SQL — the row comes
        back whatever state it is in — so it can only be in the check. If a
        future edit moves the gate into the query this test is the one that
        notices, because then deleting the check would still pass everything
        else in this class."""
        route_harness["plant"](
            GHOST,
            "merged",
            commence=_kickoff(12, 27),
            home="Arizona Cardinals",
            away="Denver Broncos",
        )
        with pytest.raises(HTTPException):
            route_harness["serve"](GHOST)

        by_id = [s for s in route_harness["db"].statements if "events.id = " in s]
        assert by_id, "the route never issued its by-id select"
        # The WHERE clause only — `events.status` is in every one of these
        # statements as a SELECTED column, which says nothing about filtering.
        where = by_id[0].split("WHERE", 1)[1]
        assert where.strip() == "events.id = :id_1", (
            f"the by-id select grew a predicate ({where.strip()!r}); if that "
            f"predicate is on status the retired row would now 404 as 'not "
            f"found' instead of 410 'gone', and this suite's ship sentence "
            f"would be a lie"
        )

    def test_a_retired_row_is_never_cached_as_a_page(self, route_harness):
        """A refusal that leaves a servable body in the cache un-ships itself on
        the next request."""
        route_harness["plant"](
            GHOST,
            "voided",
            commence=_kickoff(12, 27),
            home="Arizona Cardinals",
            away="Denver Broncos",
        )
        with pytest.raises(HTTPException):
            route_harness["serve"](GHOST)
        assert GHOST not in route_harness["route"]._event_detail_cache


class TestTheLiveVocabularyIsUntouched:
    """The controls. Green in BOTH arms by construction — every one of these
    routes only through symbols that predate this change, so a failure here
    means the suppression is too WIDE, which is the same bug facing backwards.
    """

    @pytest.mark.parametrize("status", SERVABLE_STATUSES)
    def test_every_servable_state_still_renders(self, route_harness, status):
        # A kickoff consistent with the state, because the route normalises an
        # incoherent pair: a `live` row whose kickoff has not arrived is served
        # as `scheduled`. That is pre-existing behaviour and not what this
        # control is about, so the fixture does not walk into it.
        commence = _kickoff(10, 25) if status == "scheduled" else _kickoff(1, 5)
        route_harness["plant"](
            REAL_MEETING,
            status,
            commence=commence,
            home="Arizona Cardinals",
            away="Denver Broncos",
        )
        response = route_harness["serve"](REAL_MEETING)
        assert response["id"] == REAL_MEETING
        assert response["status"] == status

    def test_the_real_meeting_survives_the_ghosts_removal(self, route_harness):
        """The LOOK, as an assertion. Both Broncos-Cardinals rows exist; exactly
        one of them must disappear. A ship that removes both is a regression."""
        route_harness["plant"](
            GHOST,
            "merged",
            commence=_kickoff(12, 27),
            home="Arizona Cardinals",
            away="Denver Broncos",
        )
        route_harness["plant"](
            REAL_MEETING,
            "scheduled",
            commence=_kickoff(10, 25),
            home="Arizona Cardinals",
            away="Denver Broncos",
        )

        with pytest.raises(HTTPException) as raised:
            route_harness["serve"](GHOST)
        assert raised.value.status_code == 410

        survivor = route_harness["serve"](REAL_MEETING)
        assert survivor["id"] == REAL_MEETING
        assert survivor["commence_time"].startswith("2026-10-25")

    def test_an_unknown_future_state_still_renders(self, route_harness):
        """`is_retired_event_status` is an allowlist of things to HIDE. A state
        nobody has taught it about must fall through to the reader, not be
        swallowed — the failure mode this whole file exists to prevent is a row
        that vanishes without anyone deciding it should."""
        route_harness["plant"](
            REAL_MEETING,
            "postponed",
            commence=_kickoff(10, 25),
            home="Arizona Cardinals",
            away="Denver Broncos",
        )
        assert route_harness["serve"](REAL_MEETING)["status"] == "postponed"


class TestTheSettledCacheIsNoLongerImmortal:
    """`admin_backfill_linkage` stamps `merged` onto rows that went Final months
    ago. A `completed` entry cached with no expiry at all keeps answering 200
    with the full page after that stamp lands — the same defect wearing a cache.
    """

    def test_a_settled_entry_expires(self, route_harness):
        events_route = route_harness["route"]
        assert (
            events_route._EVENT_DETAIL_SETTLED_TTL > 0
        ), "a falsy ceiling restores the old `or` and the entry is immortal again"

        route_harness["plant"](
            REAL_MEETING,
            "completed",
            commence=_kickoff(1, 5),
            home="Arizona Cardinals",
            away="Denver Broncos",
            home_score=17,
            away_score=24,
        )
        route_harness["serve"](REAL_MEETING)
        assert REAL_MEETING in events_route._event_detail_cache

        # Age the entry past the ceiling, then retire the row underneath it.
        cached_at, cached_status, cached_resp = events_route._event_detail_cache[
            REAL_MEETING
        ]
        events_route._event_detail_cache[REAL_MEETING] = (
            cached_at - events_route._EVENT_DETAIL_SETTLED_TTL - 1,
            cached_status,
            cached_resp,
        )
        route_harness["plant"](
            REAL_MEETING,
            "merged",
            commence=_kickoff(1, 5),
            home="Arizona Cardinals",
            away="Denver Broncos",
            home_score=17,
            away_score=24,
        )

        with pytest.raises(HTTPException) as raised:
            route_harness["serve"](REAL_MEETING)
        assert raised.value.status_code == 410

    def test_a_fresh_settled_entry_is_still_served_from_cache(self, route_harness):
        """The control on the latency side. The ceiling must not turn the
        settled shortcut into a per-request recompute."""
        route_harness["plant"](
            REAL_MEETING,
            "closed",
            commence=_kickoff(1, 5),
            home="Arizona Cardinals",
            away="Denver Broncos",
            home_score=17,
            away_score=24,
        )
        first = route_harness["serve"](REAL_MEETING)
        before = len(route_harness["db"].statements)
        again = route_harness["serve"](REAL_MEETING)
        assert again is first
        assert (
            len(route_harness["db"].statements) == before
        ), "a fresh settled entry re-queried; the shortcut has been lost, not bounded"
