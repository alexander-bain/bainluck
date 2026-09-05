"""Q438 — a game that has not kicked off may not read LIVE, anywhere.

THE SPECIMEN, from production on 2026-08-29. Two NFL games, hours before kickoff:

    15292756  Colts vs Lions    commence 2026-08-29T17:00Z   DB status 'live', 0-0
    15292757  Titans vs Bears   commence 2026-08-29T22:00Z   DB status 'live', 0-0
    14969919  Fire vs Whitecaps commence 2026-10-06T18:00Z   DB status 'live', 0-0

`GET /api/leagues/americanfootball_nfl` served all of them under `upcoming_games`
with `"status": "live"` — a LIVE badge on the league page for a game three hours
away, and for one five weeks away. `GET /api/events/15292756` served the SAME row
as `"scheduled"`. One row, two answers.

RE-MEASURED 2026-09-05, on the rescue of this branch. Two of the three rows have
rolled to `completed`; **14969919 is still `live` in the database with a kickoff a
month away**, and `/api/leagues/soccer_usa_mls` still serves it as `"live"` in
`upcoming_games[0]` while `/api/events/14969919` serves the same row as
`"scheduled"`. Ten weeks on, one row, still two answers.

This file pins the four separate defects that produced that, because they fail
independently and each one alone is enough to put the badge back.

1. THE SERVED VALUE (the ship)
------------------------------
`app/utils/lifecycle.served_event_status` is the invariant, and it was already
correct. `app/routes/events.py` and `app/routes/teams.py` consumed it; the league
rail, the bracket, the futures event list, the golf rail and typeahead's fuzzy
arm did not. `test_event_live_before_start.py` had a guard for exactly this —
`PUBLIC_SURFACES` — listing two files. The guard was right and its list was short,
which is the same failure it was written to catch one level up: a rule with no
consumer is a document, and a consumer list that does not enumerate the consumers
is a document too.

2. THE DETECTOR (why nobody knew for twelve days)
-------------------------------------------------
The Flow Sentinel HAS a `live_before_commence` limb. On the morning of 08-29 it
reported `[]` while all three rows were live in the database.

It samples `/api/events?status=live`, which **SELECTS on the raw column and SERVES
the repaired one**. So the offending rows came back in the payload — presented as
`scheduled` — and the limb's own `if e["status"] != "live": continue` dropped every
one. Queue 364 wired `served_event_status` into `events.py` and, in the same
stroke, made this limb structurally incapable of ever firing again.

The proof it is the repair and not an empty population: the sibling limb
`future_settled` fired the same run, on event 14958839, because
`served_event_status` only ever rewrites `live` — never `completed`. Two limbs,
one payload, one repaired field, and exactly the limb reading that field went
silent. `_build_dup_key`'s comment meanwhile still named this limb as the
compensating control for its own doubleheader blind spot.

3. THE WRITER (where the rows come from)
-----------------------------------------
`statpal_sync`'s "create events for live games missing from DB" path stamps
`status="live"` on creation. Measured on production 2026-08-29, that path had
created **48 events since 2026-05-15 and all 48 were created before their own
commence_time** — it has never once created a game that was in progress. The
sibling SCORE write ten lines above already refused on `live_write_is_premature`
(#1945); the CREATE did not.

4. THE POSITION (found by LOOKing at the page, 2026-09-05)
-----------------------------------------------------------
Repairing §1 fixes what the card SAYS and not where it SITS. Both league rails
ordered on `case((Event.status == "live", 0), else_=1)` — the raw column, with no
time half — so 14969919 held the first slot of `/sport/soccer/mls` above eight
matches kicking off that evening, and had done since 2026-06-30. `event_rails`'
own docstring names this exposure and banks on the staleness nets; those nets
measure age PAST commence, so they catch a row that is live too long and can
never catch one that is live too early. `live_first_order(now)` is the ORDER BY
twin of `upcoming_rail_condition(now)`, and the two rails plus both typeahead
pools now share it.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.tasks.flow_sentinel import live_before_commence_events
from app.utils.game_pairing import live_write_is_premature
from app.utils.lifecycle import EVENT_NOT_STARTED, served_event_status

NOW = datetime(2026, 8, 29, 14, 0, tzinfo=timezone.utc)


def _row(event_id, commence, *, served, sport="americanfootball_nfl",
         home="Indianapolis Colts", away="Detroit Lions"):
    """One row exactly as `/api/events?status=live` presents it."""
    return {
        "id": event_id,
        "sport": sport,
        "home_team": home,
        "away_team": away,
        "status": served,
        "commence_time": commence.isoformat(),
    }


# The production payload: selected by `status=live`, served as `scheduled`.
COLTS = _row(15292756, datetime(2026, 8, 29, 17, 0, tzinfo=timezone.utc),
             served="scheduled")
TITANS = _row(15292757, datetime(2026, 8, 29, 22, 0, tzinfo=timezone.utc),
              served="scheduled", home="Tennessee Titans", away="Chicago Bears")
FIRE = _row(14969919, datetime(2026, 10, 6, 18, 0, tzinfo=timezone.utc),
            served="scheduled", sport="soccer_usa_mls",
            home="Chicago Fire", away="Vancouver Whitecaps FC")


def _raw_status_sites_in(module_name: str, source: str) -> list[tuple[str, str, str]]:
    """Every dict literal in `source` that prints a raw ``<name>.status`` beside
    a ``commence_time`` key, outside a ``/debug`` route.

    The pair is the point. A payload that carries only a status states nothing
    checkable; a payload that carries the status AND the kickoff it contradicts
    is the shape of the 08-29 specimen, and is what a reader (or a sentinel)
    could have caught. Serialising through ``served_event_status`` turns the
    value into a ``Call`` rather than an ``Attribute``, so a repaired site drops
    out of this scan by construction and cannot be re-admitted by an allowlist
    entry that has gone stale.

    AST, not a regex: `"status": event.status` spans lines, hides inside
    comprehensions, and appears in strings and comments that must not count.
    """
    import ast

    hits: list[tuple[str, str, str]] = []
    tree = ast.parse(source)
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        paths = [
            d.args[0].value
            for d in fn.decorator_list
            if isinstance(d, ast.Call) and d.args
            and isinstance(d.args[0], ast.Constant)
            and isinstance(d.args[0].value, str)
        ]
        if any("/debug" in p for p in paths):
            continue
        for node in ast.walk(fn):
            if not isinstance(node, ast.Dict):
                continue
            keys = {
                k.value for k in node.keys
                if isinstance(k, ast.Constant) and isinstance(k.value, str)
            }
            if "commence_time" not in keys:
                continue
            for key, value in zip(node.keys, node.values):
                if not (isinstance(key, ast.Constant) and key.value == "status"):
                    continue
                if isinstance(value, ast.Attribute) and value.attr == "status":
                    base = (
                        value.value.id
                        if isinstance(value.value, ast.Name)
                        else "<expr>"
                    )
                    hits.append((module_name, fn.name, f"{base}.status"))
    return hits


class TestTheDetectorWasBlind:
    """The limb read its own repair. This is the red-first gate for §2."""

    def test_the_production_payload_is_caught_when_the_selector_is_declared(self):
        """RED before the fix: returns [] on all three real rows."""
        found = live_before_commence_events(
            [COLTS, TITANS, FIRE], NOW, selected_as="live"
        )
        assert {f["event_id"] for f in found} == {15292756, 15292757, 14969919}

    def test_the_served_value_alone_finds_nothing_and_that_is_the_bug(self):
        """Pins the failure itself, so the mechanism cannot be re-introduced
        quietly. Without the selector there is nothing in the payload that says
        `live`, so an honest reading of the served field IS empty — which is
        precisely why the selector has to be the authority."""
        assert live_before_commence_events([COLTS, TITANS, FIRE], NOW) == []

    def test_the_disagreement_is_recorded_as_evidence(self):
        """A finding that says only "it is live" cannot be reconciled against an
        API response that says `scheduled`. The report has to carry both."""
        found = live_before_commence_events([COLTS], NOW, selected_as="live")
        assert found[0]["served_status"] == "scheduled"
        assert found[0]["starts_in_hours"] == 3.0

    def test_a_started_game_is_not_a_finding(self):
        """The limb must not fire on the ordinary case: the live filter returns
        genuinely-live games too, and they are the overwhelming majority."""
        started = _row(1, NOW - timedelta(hours=1), served="live")
        assert live_before_commence_events([started], NOW, selected_as="live") == []

    def test_an_unfiltered_sample_keeps_the_served_reading(self):
        """Callers that did not sample through a status filter have no selector
        to trust, so the served value stays the authority for them."""
        raw_live = _row(2, NOW + timedelta(hours=3), served="live")
        assert len(live_before_commence_events([raw_live], NOW)) == 1

    def test_the_sentinel_actually_passes_the_selector(self):
        """The capability is worthless unwired, which is this queue's whole
        thesis restated: `served_event_status` was correct and unconsumed for a
        week, and this limb was capable and unfed for twelve days. So the guard
        is on the CALL, not on the function — asserted against the shipping
        source, because a kwarg dropped in a refactor restores the silence with
        every unit test still green.
        """
        import pathlib

        src = (
            pathlib.Path(__file__).resolve().parents[1]
            / "app/tasks/flow_sentinel.py"
        ).read_text()
        assert 'live_before_commence_events(live, now, selected_as="live")' in src

    def test_the_sibling_limb_explains_why_only_this_one_went_quiet(self):
        """`served_event_status` rewrites `live` and nothing else. That
        asymmetry is the whole diagnosis, so it is asserted rather than
        described."""
        future = NOW + timedelta(days=2)
        assert served_event_status("live", future, NOW) == EVENT_NOT_STARTED
        assert served_event_status("completed", future, NOW) == "completed"


class TestEveryPublicSurfaceConsumesTheInvariant:
    """§1. The list is the guard — an unlisted serializer is an unguarded one."""

    #: Every route module that emits an event row's `status` to the public.
    #: Extending this list is how a new surface is admitted; a new public
    #: serializer that skips the invariant fails here rather than in production.
    PUBLIC_SURFACES = (
        "app/routes/events.py",
        "app/routes/teams.py",
        # Added by Q438, each one measured serving a raw status:
        "app/routes/league_futures.py",   # the league rail — the 08-29 specimen
        "app/routes/march_madness.py",    # bracket slots
        "app/routes/futures.py",          # the futures event list
    )

    #: `app/routes/golf.py` was the fifth site, and its absence from the tuple
    #: above is what CERT-440 blocked this ship on:
    #:
    #:     BLOCK, 2026-08-29 16:54Z, `backend/app/routes/golf.py:2161` — "the
    #:     public `GET /api/golf` overview selects upcoming golf events with an
    #:     explicit `Event.status == "live"` arm and serializes each as
    #:     `"status": e.status`. […] G6 asks for every public raw-status
    #:     serializer." Fix-sketch: "route this serializer through
    #:     `served_event_status` […] or restage on a base that actually removes
    #:     the endpoint."
    #:
    #: It is the second branch of that sketch that discharged it, and by the
    #: base rather than by an edit here. `b44b3778` (UX-P169, "the golf page
    #: stops hiding what's coming up") is an ancestor of this commit and was NOT
    #: an ancestor of the cert's base `d9b76e9b` — which is the whole difference
    #: from the cert's reading, since it refused the same argument while the
    #: deletion sat on an unmerged neighbour. `_upcoming_from_schedule` now
    #: builds that rail from the DataGolf schedule, emits **no `status` key at
    #: all**, and filters `start <= now` away, so there is no event-row status
    #: left on any public golf surface to repair.
    #:
    #: The hand-maintained tuple above is not how that is kept true. A list of
    #: consumers that a human extends is the mechanism that lost golf in the
    #: first place — the docstring at the top of this file says so about the
    #: guard this one replaced, and then this class did it again one level down.
    #: `test_no_public_surface_serializes_a_raw_event_status` DERIVES the set
    #: instead, so the next golf fails here.

    #: Public serializers that emit a raw `.status` beside a `commence_time` and
    #: are nonetheless correct: the status is a MARKET's (`open`/`closed`/
    #: `settled`), which has no `live` value and so cannot state the
    #: contradiction this file exists to remove. Keyed by (module, function) so
    #: the inventory survives line drift. A site that is not here fails.
    MARKET_STATUS_SERIALIZERS = {
        ("feed.py", "build_effective_settlement_followup_item"),
        ("futures.py", "_format_market_detail"),
        ("futures.py", "get_group"),
    }

    #: Deliberately NOT repaired: an operator debugging a contradictory row must
    #: SEE the contradiction. Repairing the admin/debug read is what would have
    #: hidden this queue's own specimens.
    RAW_BY_DESIGN = (
        "app/routes/admin_events.py",
    )

    def _source(self, rel):
        import pathlib

        return (pathlib.Path(__file__).resolve().parents[1] / rel).read_text()

    @pytest.mark.parametrize("rel", PUBLIC_SURFACES)
    def test_public_serializer_routes_through_it(self, rel):
        assert "served_event_status" in self._source(rel), (
            f"{rel} emits an event status without the lifecycle invariant"
        )

    @pytest.mark.parametrize("rel", RAW_BY_DESIGN)
    def test_operator_surfaces_deliberately_do_not(self, rel):
        assert "served_event_status" not in self._source(rel)

    def test_the_league_rail_specimen_is_repaired_at_the_source(self):
        """The narrow assertion the ship rests on: the shared event card's
        formatter no longer hands out `event.status` unread."""
        src = self._source("app/routes/league_futures.py")
        assert '"status": event.status,' not in src
        assert "served_event_status(" in src

    # -- the derived guard (CERT-440's repair) -----------------------------

    def test_the_scanner_can_fire_on_the_block_it_was_written_for(self):
        """RED-first, against the REAL blocked code rather than a fixture.

        A scanner guard that selects nothing passes forever, so this pins that
        it fires — on the literal serializer CERT-440 named, lifted verbatim
        from `golf.py` as it stood at the cert's base `d9b76e9b`."""
        blocked = '''
async def get_golf(db=None):
    events_query = (
        select(Event)
        .where(or_(Event.status == "live", Event.commence_time.between(a, b)))
    )
    upcoming_events = [
        {
            "id": e.id,
            "name": e.home_team_name,
            "commence_time": e.commence_time.isoformat() if e.commence_time else None,
            "status": e.status,
        }
        for e in events_result.scalars().all()
    ]
'''
        found = _raw_status_sites_in("golf.py", blocked)
        assert found == [("golf.py", "get_golf", "e.status")], found

    def test_the_golf_rail_that_replaced_it_cannot_state_the_contradiction(self):
        """The discharge, asserted rather than described. Not just "the line is
        gone" — the rail that replaced it has no status to be wrong with, and
        drops anything that has already started, so a not-yet-begun tournament
        has nothing on it that could read LIVE."""
        src = self._source("app/routes/golf.py")
        assert "_upcoming_from_schedule" in src
        assert '"status": e.status' not in src
        # The replacement is schedule-derived and status-free.
        rail = src.split("def _upcoming_from_schedule")[1].split("\ndef ")[0]
        assert '"status"' not in rail
        assert "if start <= now:" in rail

    def test_no_public_surface_serializes_a_raw_event_status(self):
        """G6, derived. Every dict on a public route that prints a raw
        `<x>.status` beside a `commence_time` — the two fields whose
        disagreement IS the defect — must either route through the invariant or
        be a known market serializer. Operator surfaces are exempt, and the
        exemption is read off the ROUTE (an `admin_*` module, or a `/debug`
        path), never off a list of filenames."""
        import pathlib

        routes = pathlib.Path(__file__).resolve().parents[1] / "app/routes"
        offenders = []
        for path in sorted(routes.glob("*.py")):
            if path.name.startswith("admin_"):
                continue
            for site in _raw_status_sites_in(path.name, path.read_text()):
                if (site[0], site[1]) not in self.MARKET_STATUS_SERIALIZERS:
                    offenders.append(site)
        assert not offenders, (
            "public serializer(s) emit a raw status beside a commence_time: "
            f"{offenders}. Route the value through "
            "`app.utils.lifecycle.served_event_status`, or — if it is a market "
            "status, which has no `live` value — add (module, function) to "
            "MARKET_STATUS_SERIALIZERS with the reason."
        )


class TestThePositionAgreesWithTheLabel:
    """§4 — found by LOOKing at the shipped page, not by reading the diff.

    Repairing the SERVED status fixes the badge and leaves the row where it was.
    On 2026-09-05 `/sport/soccer/mls` led with Chicago Fire vs Vancouver
    Whitecaps — kickoff 2026-10-06 — above eight matches starting that evening,
    because the rail's ORDER BY still read the raw column. The heading said
    "LIVE & UPCOMING" for a league with nothing live in it.

    So the label and the position have to answer to one predicate. These run the
    REAL `live_first_order` clause as real SQL rather than asserting on its
    source, because the whole class of bug here is an expression that looks
    right and sorts wrong.
    """

    NOW = datetime(2026, 9, 5, 18, 0, tzinfo=timezone.utc)

    #: id, status, commence — the production specimen plus its two neighbours.
    ROWS = (
        (1, "live", "2026-10-06 18:00:00.000000"),      # 14969919, a month out
        (2, "scheduled", "2026-09-05 23:30:00.000000"),  # kicks off tonight
        (3, "live", "2026-09-05 17:00:00.000000"),      # genuinely being played
    )

    def _order_under(self, clause, rows=None):
        """Execute the clause against a real `events` table and return the ids.

        The models' JSONB columns cannot be created under SQLite, so the table
        is the three columns this ORDER BY actually touches. The EXPRESSION is
        the shipping one — it renders `events.status` / `events.commence_time`
        by name, so it binds to this table unchanged.
        """
        from sqlalchemy import (
            Column, DateTime, Integer, MetaData, String, Table,
            create_engine, select,
        )

        from app.models.models import Event

        md = MetaData()
        Table(
            "events", md,
            Column("id", Integer, primary_key=True),
            Column("status", String),
            Column("commence_time", DateTime(timezone=True)),
        )
        engine = create_engine("sqlite://")
        md.create_all(engine)
        with engine.begin() as conn:
            conn.exec_driver_sql(
                "INSERT INTO events (id,status,commence_time) VALUES (?,?,?)",
                list(self.ROWS if rows is None else rows),
            )
            stmt = select(Event.id).order_by(clause, Event.commence_time.asc())
            return [row[0] for row in conn.execute(stmt)]

    def test_the_premature_row_no_longer_leads_the_rail(self):
        from app.utils.event_rails import live_first_order

        assert self._order_under(live_first_order(self.NOW)) == [3, 2, 1]

    def test_a_genuinely_live_game_still_leads_it(self):
        """The fix must not cost the thing the live-first sort is FOR."""
        from app.utils.event_rails import live_first_order

        assert self._order_under(live_first_order(self.NOW))[0] == 3

    def test_the_clause_this_replaced_sorted_it_second(self):
        """RED, executed rather than asserted: the raw-column clause put a
        fixture a month away above a match kicking off in five hours."""
        from sqlalchemy import case

        from app.models.models import Event

        raw = case((Event.status == "live", 0), else_=1)
        assert self._order_under(raw) == [3, 1, 2]

    #: The four classes CERT-1924 requires the three-way clause to separate.
    #: id, status, commence, and the status a public surface must PRINT.
    FOUR_CLASSES = (
        (10, "live", "2026-09-05 17:00:00.000000", "live"),       # being played
        (11, "scheduled", "2026-09-05 23:30:00.000000", "scheduled"),  # tonight
        (12, "live", "2026-09-11 18:00:00.000000", "scheduled"),  # premature
        (13, "completed", "2026-09-04 23:30:00.000000", "completed"),  # finished
    )

    def test_the_futures_week_list_sorts_the_four_classes_correctly(self):
        """CERT-1924's required regression. Live, then upcoming — with the
        premature row among the upcoming games in DATE order, not ahead of
        them — then completed last."""
        from app.utils.event_rails import live_scheduled_settled_order

        rows = [(i, s, c) for i, s, c, _ in self.FOUR_CLASSES]
        assert self._order_under(
            live_scheduled_settled_order(self.NOW), rows=rows
        ) == [10, 11, 12, 13]

    def test_the_clause_it_replaced_promoted_the_premature_row(self):
        """RED, executed: the raw three-way CASE put a game six days out ahead
        of one kicking off in five hours — and then printed it `scheduled`."""
        from sqlalchemy import case

        from app.models.models import Event

        raw = case(
            (Event.status == "live", 0),
            (Event.status == "scheduled", 1),
            else_=2,
        )
        rows = [(i, s, c) for i, s, c, _ in self.FOUR_CLASSES]
        assert self._order_under(raw, rows=rows) == [10, 12, 11, 13]

    def test_the_position_matches_the_printed_status_for_every_class(self):
        """The two halves stated together, which is the ship: what each row is
        SERVED as, beside where it SITS. The premature row prints `scheduled`
        and sits with the scheduled games."""
        from app.utils.event_rails import live_scheduled_settled_order

        served = {
            row_id: served_event_status(
                status, datetime.fromisoformat(commence).replace(tzinfo=timezone.utc),
                self.NOW,
            )
            for row_id, status, commence, _ in self.FOUR_CLASSES
        }
        assert served == {i: expected for i, _, _, expected in self.FOUR_CLASSES}

        order = self._order_under(
            live_scheduled_settled_order(self.NOW),
            rows=[(i, s, c) for i, s, c, _ in self.FOUR_CLASSES],
        )
        # Every row printed `scheduled` sits in one contiguous block, in date
        # order, after the live one and before the completed one.
        printed_scheduled = [i for i in order if served[i] == "scheduled"]
        assert printed_scheduled == [11, 12]
        assert order.index(10) < order.index(11)
        assert order.index(13) == len(order) - 1

    def test_no_route_still_orders_on_the_raw_column(self):
        """Every live-first sort goes through a shared clause.

        🔴 THIS TEST'S FIRST VERSION WAS A SUBSTRING MATCH FOR
        `case((Event.status == "live", 0)` AND CERT-1924 BLOCKED ON WHAT IT
        MISSED. `futures.py`'s "Games This Week" list spelled the same sentence
        as a MULTILINE `case(...)`, so it survived both the repair and the guard
        written to catch the repair — a raw-live row a week out was promoted
        above nearer scheduled games and then serialized as `scheduled`.

        A formatting difference must not decide whether a guard sees a defect,
        so this is an AST scan: any `case(...)` whose FIRST branch tests
        `Event.status == "live"` is the raw ordering, however it is laid out.
        """
        import ast
        import pathlib

        routes = pathlib.Path(__file__).resolve().parents[1] / "app/routes"
        offenders = []
        for path in sorted(routes.glob("*.py")):
            if path.name.startswith("admin_"):
                continue
            for node in ast.walk(ast.parse(path.read_text())):
                if not (isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Name)
                        and node.func.id == "case"
                        and node.args):
                    continue
                first = node.args[0]
                if not (isinstance(first, ast.Tuple) and len(first.elts) == 2):
                    continue
                test = first.elts[0]
                if (isinstance(test, ast.Compare)
                        and isinstance(test.left, ast.Attribute)
                        and test.left.attr == "status"
                        and isinstance(test.comparators[0], ast.Constant)
                        and test.comparators[0].value == "live"):
                    offenders.append((path.name, test.lineno))
        assert offenders == [], (
            f"{offenders} lead a CASE with a raw `status == 'live'` test. Use "
            "`app.utils.event_rails.live_first_order(now)` (two-way) or "
            "`live_scheduled_settled_order(now)` (three-way, completed last)."
        )


class TestTheWriterStopsMintingThem:
    """§3. The create path's own predicate, as it is now applied."""

    def test_a_future_start_is_premature(self):
        assert live_write_is_premature(NOW + timedelta(days=3), NOW) is True

    def test_a_started_game_is_not(self):
        assert live_write_is_premature(NOW - timedelta(minutes=30), NOW) is False

    def test_the_create_site_branches_on_the_shared_predicate(self):
        """Asserted against the shipping source: a second copy of this judgement
        is a second matcher, and the score path 100 lines up already owns it."""
        import pathlib

        src = (
            pathlib.Path(__file__).resolve().parents[1]
            / "app/tasks/statpal_sync.py"
        ).read_text()
        assert 'status="scheduled" if premature_create else "live",' in src
        assert "premature_create = live_write_is_premature(" in src
        # The counter is reported unconditionally — 0 is a reading (gotcha #53).
        assert '"premature_live_created_as_scheduled":' in src

    def test_the_created_row_carries_no_score_when_premature(self):
        """A `scheduled` row holding a live score is the same contradiction one
        field over."""
        import pathlib

        src = (
            pathlib.Path(__file__).resolve().parents[1]
            / "app/tasks/statpal_sync.py"
        ).read_text()
        assert "if not premature_create:" in src
