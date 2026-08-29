"""Q438 — a game that has not kicked off may not read LIVE, anywhere.

THE SPECIMEN, from production on 2026-08-29. Two NFL games, hours before kickoff:

    15292756  Colts vs Lions    commence 2026-08-29T17:00Z   DB status 'live', 0-0
    15292757  Titans vs Bears   commence 2026-08-29T22:00Z   DB status 'live', 0-0
    14969919  Fire vs Whitecaps commence 2026-10-06T18:00Z   DB status 'live', 0-0

`GET /api/leagues/americanfootball_nfl` served all of them under `upcoming_games`
with `"status": "live"` — a LIVE badge on the league page for a game three hours
away, and for one five weeks away. `GET /api/events/15292756` served the SAME row
as `"scheduled"`. One row, two answers.

This file pins the three separate defects that produced that, because they fail
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

    #: `app/routes/golf.py` IS a fifth site and is deliberately absent. Its
    #: upcoming rail serves a raw `e.status` today, and Q438 fixed it — then
    #: reverted the fix, because `program/ux-122` DELETES that block wholesale:
    #: the rail is being rebuilt from the DataGolf schedule
    #: (`_upcoming_from_schedule`) rather than the `events` table, so there is
    #: no event-row status left to repair. Guarding it here would have bought a
    #: guaranteed merge conflict against code on its way out. If ux-122 is
    #: abandoned, golf.py needs adding to the list above — that is the carry
    #: this comment exists to keep alive rather than leave to memory.

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
