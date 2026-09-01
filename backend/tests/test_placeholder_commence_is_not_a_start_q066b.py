"""A session-start default is not a first serve — and a provider may revise its
own record (q066b).

PILLAR: TRUTH.  SHIP: a US Open match that has not been played stops showing as
finished, and its page stops printing a start time it was never given.

## The specimen, measured on production 2026-09-01

The Odds API publishes the whole of the NEXT day's US Open at one session-start
default, because no order of play exists yet::

    /v4/sports/tennis_atp_us_open/events   2026-09-02T15:00:00Z  x21
    /v4/sports/tennis_wta_us_open/events   2026-09-02T15:00:00Z  x20

and then STAGGERS THE SAME EVENT IDS to real times once it is published.  The
same two endpoints, read in the same breath, for the day already under way::

    15:00 x5   16:10 x3   16:40 x2   17:20 x2   17:50 x3
    19:00 x1   20:30 x1   21:00 x1   23:00 x1   00:10 x1

There is no placeholder field in the payload — the response carries exactly
``id, sport_key, sport_title, commence_time, home_team, away_team``.  The ONLY
thing that distinguishes the default from the truth is that the provider sent
the truth later.

## Why it never healed

``_update_fields_by_priority`` gated the write on ``incoming > current``, and the
incoming source IS the current source: ``odds_api`` cannot outrank ``odds_api``.
So the first value the provider ever published was frozen forever, and every
downstream clock read it as a start:

* ``transition_event_statuses`` (every 60s) promotes ``scheduled -> live`` on
  ``commence_time <= now`` alone, so all 42 flip to live at the session default;
* ``odds_polling.detect_and_close_stale_events`` arms at ``commence + 1.5h`` and
  fires after 30 minutes of stale odds;
* ``espn_sync._transition_event_statuses_impl`` fires at ``commence + 6.5h``.

Measured outcome, 2026-09-01T12:09Z: **35 US Open matches marked ``closed`` with
no score while bookmakers were actively pricing them** (18 ATP, 17 WTA, odds
refreshed inside the preceding 90 minutes).  Nine of them were being played the
FOLLOWING day, and the Odds API was already carrying their real times against
the very ``external_id`` values our rows hold — including
``3d7f79c659068620c150b46dd0d6bded`` (Stoiana v Eala), which our row dated
2026-08-31T15:00Z and marked finished while the provider had it at
2026-09-02T00:40Z, unplayed.  Issue #2446 ("Three inconsistent times on one event
page": header 8:00 AM PDT, chart starting 8:40) is the display half of this
defect — 8:00 AM PDT is 15:00:00Z, the session default.

## THE GUARD THIS FILE DOES *NOT* WRITE

The queue asked for: *"assert that a sport's events on one calendar day do not
all share one ``commence_time`` to the second."*  **That guard is wrong and it is
not written here.**  Measured over 14 days of production, events-per-day >= 8,
the worst share-on-one-timestamp per sport::

    soccer_other              130 on one stamp   share 1.00
    tennis_wta_us_open         48 on one stamp   share 1.00
    soccer_germany_dfb_pokal   18 on one stamp   share 1.00
    soccer_england_league2     12 on one stamp   share 1.00
    soccer_epl                 22 on one stamp   share 0.85
    soccer_germany_bundesliga  20 on one stamp   share 0.67

A Saturday 3pm English kickoff card genuinely IS ten matches starting at the
same second, and so is a cup round.  The proposed assertion fires hardest on the
sport where the behaviour is correct, and tennis is not even separable by
magnitude: ESPN's own real order of play gives 15:05Z to three US Open matches
at once (the first wave on three courts).  Clustering is not the signature.

The signature is that **the provider revised the value and we refused the
revision**.  So the guard is on the behaviour, not on the shape of a day, and
none of it binds on a date.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models import Event
from app.services.event_registry import (
    EventClaim,
    EventIdentity,
    _update_fields_by_priority,
    claim_is_same_record,
    commence_time_write_authorized,
)
from app.utils.event_completion import settlement_is_a_staleness_artifact

UTC = timezone.utc

#: The real ids and stamps off the 2026-09-01 read, so the fixture is the
#: specimen rather than a re-description of it.
ODDS_ID = "3d7f79c659068620c150b46dd0d6bded"
PLACEHOLDER = datetime(2026, 8, 31, 15, 0, 0, tzinfo=UTC)
REAL_START = datetime(2026, 9, 2, 0, 40, 0, tzinfo=UTC)
NET_CLOSED_AT = datetime(2026, 8, 31, 19, 39, 44, tzinfo=UTC)


def _identity(commence, *, source="odds_api", odds_id=ODDS_ID):
    return EventIdentity(
        sport_key="tennis_wta_us_open",
        home_team_name="Mary Stoiana",
        away_team_name="Alexandra Eala",
        commence_time=commence,
        claim=EventClaim(source, odds_id, schedule_derived=False),
        commence_time_source=source,
    )


def _row(**overrides):
    """The production row, as `detect_and_close_stale_events` left it."""
    event = Event()
    event.id = 15295875
    event.home_team_name = "Mary Stoiana"
    event.away_team_name = "Alexandra Eala"
    event.commence_time = PLACEHOLDER
    event.commence_time_source = "odds_api"
    event.external_id = ODDS_ID
    event.status = "closed"
    event.completed_at = NET_CLOSED_AT
    event.home_score = None
    event.away_score = None
    for key, value in overrides.items():
        setattr(event, key, value)
    return event


class TestAProviderMayReviseItsOwnRecord:
    """A tie loses between two RIVALS.  One record read twice is not two rivals."""

    def test_a_tie_still_loses_by_default(self):
        """The #2018 rule is unchanged for every caller that does not opt in.

        The exemption is a keyword with a False default precisely so that adding
        it cannot silently re-license the writes #2018 exists to refuse.
        """
        assert commence_time_write_authorized("odds_api", "odds_api")[0] is False
        assert commence_time_write_authorized("espn", "espn")[0] is False

    def test_a_tie_wins_when_it_is_the_same_record(self):
        ok, reason = commence_time_write_authorized(
            "odds_api", "odds_api", same_record_revision=True
        )
        assert ok is True
        assert "revision" in reason

    def test_a_revision_is_scoped_to_the_SAME_source_not_merely_to_parity(self):
        """Two providers that happen to rank equal are still two authorities.

        `kalshi` and `polymarket` both rank 0.  Without the equality test they
        would each be able to "revise" the other's reading, which is the tie rule
        deleted rather than narrowed.
        """
        ok, _ = commence_time_write_authorized(
            "kalshi", "polymarket", same_record_revision=True
        )
        assert ok is False

    def test_an_unknown_source_cannot_revise(self):
        """Same reason it cannot outrank: it has no authority to correct."""
        assert commence_time_write_authorized(
            "mystery", "mystery", same_record_revision=True
        )[0] is False

    def test_a_revision_never_beats_a_higher_ranked_source(self):
        """`odds_api` revising its own record still loses to an `espn`-owned row.

        The exemption lifts a TIE.  It does not lift the ladder — otherwise the
        US Open fix would quietly hand the Odds API authority over every row ESPN
        and StatPal own.
        """
        ok, _ = commence_time_write_authorized(
            "espn", "odds_api", same_record_revision=True
        )
        assert ok is False


class TestSameRecordMeansSameId:
    """`claim_is_same_record` is an EXACT id identity and nothing looser."""

    def test_the_providers_own_id_already_on_the_row(self):
        assert claim_is_same_record(_row(), EventClaim("odds_api", ODDS_ID)) is True

    def test_a_different_id_from_the_same_provider_is_not_a_revision(self):
        """This is the doubleheader / wrong-sibling arm.

        A second Odds API id arriving at a row that already holds a different one
        is the #1989 absorber shape, not a correction, and it must not acquire a
        write it never had.
        """
        assert claim_is_same_record(_row(), EventClaim("odds_api", "other-id")) is False

    def test_an_empty_column_is_not_a_revision(self):
        """Nothing to revise: the provider has never written here."""
        assert claim_is_same_record(
            _row(external_id=None), EventClaim("odds_api", ODDS_ID)
        ) is False

    @pytest.mark.parametrize("source", ["kalshi", "polymarket"])
    def test_a_provider_with_no_id_column_can_never_assert_a_revision(self, source):
        """They reach rows through the anchor channel, not through a column.

        Answering optimistically would hand the revision right to the two sources
        ranked 0 — the ones the ladder exists to keep off `commence_time`.
        """
        assert claim_is_same_record(_row(), EventClaim(source, ODDS_ID)) is False


class TestVoidingAStalenessArtifact:
    """An unscored row a wall-clock net closed is not a finished game."""

    def test_the_specimen_is_an_artifact(self):
        assert settlement_is_a_staleness_artifact(
            "closed", None, None, REAL_START, NET_CLOSED_AT
        ) is True

    def test_a_scored_row_is_never_an_artifact(self):
        """A real result outranks any schedule correction (gotcha #21).

        Both arms, because a walkover writes one score and not the other.
        """
        assert settlement_is_a_staleness_artifact(
            "closed", 3, 0, REAL_START, NET_CLOSED_AT
        ) is False
        assert settlement_is_a_staleness_artifact(
            "closed", None, 2, REAL_START, NET_CLOSED_AT
        ) is False

    def test_a_live_or_scheduled_row_is_not_an_artifact(self):
        for status in ("scheduled", "live"):
            assert settlement_is_a_staleness_artifact(
                status, None, None, REAL_START, NET_CLOSED_AT
            ) is False

    def test_a_correction_that_does_not_invert_is_not_an_artifact(self):
        """No inversion, no evidence.

        A settled unscored row whose corrected start still precedes its recorded
        completion is an ordinary ordering; this predicate must not reach for it,
        or it becomes a licence to un-settle anything unscored.
        """
        assert settlement_is_a_staleness_artifact(
            "closed", None, None,
            NET_CLOSED_AT - timedelta(hours=2), NET_CLOSED_AT,
        ) is False

    def test_no_completion_recorded_is_not_an_artifact(self):
        assert settlement_is_a_staleness_artifact(
            "closed", None, None, REAL_START, None
        ) is False


class TestTheProductionRowHeals:
    """End to end on `_update_fields_by_priority`, the function that runs."""

    def test_the_placeholder_is_replaced_by_the_providers_real_time(self):
        event = _row()
        _update_fields_by_priority(event, _identity(REAL_START))
        assert event.commence_time == REAL_START
        assert event.commence_time_source == "odds_api"

    def test_the_unplayed_match_stops_showing_as_finished(self):
        """The ship. `closed` with no result, on a match being played tomorrow."""
        event = _row()
        _update_fields_by_priority(event, _identity(REAL_START))
        assert event.status == "scheduled"
        assert event.completed_at is None

    def test_before_the_fix_this_row_did_not_move(self):
        """The control arm — the defect, reproduced through the same function.

        Strip the one thing the fix adds (the provider's id on the row, which is
        what makes the claim a revision) and the write is refused exactly as it
        was in production.  Without this the two arms would not be distinguishable
        and the test above would pass on a no-op.
        """
        event = _row(external_id="a-different-odds-api-id")
        _update_fields_by_priority(event, _identity(REAL_START))
        assert event.commence_time == PLACEHOLDER
        assert event.status == "closed"
        assert event.completed_at == NET_CLOSED_AT

    def test_a_scored_result_survives_a_schedule_correction(self):
        """A finished match keeps its finish.

        The #46 inversion guard still owns this case: the row is scored, so it is
        not an artifact, so the forward move is refused and the settlement stands.
        """
        event = _row(status="completed", home_score=1, away_score=2)
        _update_fields_by_priority(event, _identity(REAL_START))
        assert event.commence_time == PLACEHOLDER
        assert event.status == "completed"
        assert event.completed_at == NET_CLOSED_AT

    def test_team_names_are_not_rewritten_by_a_revision(self):
        """Scope: this queue ships a START TIME.

        A same-record revision deliberately does not carry a name rewrite — that
        is a different blast radius and no evidence here asks for it.  Names still
        follow the unchanged priority ladder.
        """
        event = _row()
        identity = _identity(REAL_START)
        identity.home_team_name = "WRONG"
        identity.away_team_name = "ALSO WRONG"
        _update_fields_by_priority(event, identity)
        assert event.home_team_name == "Mary Stoiana"
        assert event.away_team_name == "Alexandra Eala"
        assert event.commence_time == REAL_START

    def test_a_repeat_poll_of_the_unchanged_placeholder_is_a_no_op(self):
        """Idempotence: the same value re-read must not un-settle anything.

        Tomorrow's 42 rows are polled every 30 seconds against a stamp that will
        not move until the order of play publishes.  If a revision that changes
        nothing could still void a settlement, this fix would itself become a
        producer.
        """
        event = _row(status="closed", completed_at=NET_CLOSED_AT)
        _update_fields_by_priority(event, _identity(PLACEHOLDER))
        assert event.commence_time == PLACEHOLDER
        assert event.status == "closed"
        assert event.completed_at == NET_CLOSED_AT


class TestSimultaneousStartsAreNotADefect:
    """The anti-guard: clustering is legitimate and must not be disturbed.

    Ten League Two matches at exactly 14:00:00Z is a Saturday, not a bug — and
    130 rows on one stamp in `soccer_other` is the measured worst case.  Nothing
    in this fix keys off how many rows share a timestamp, and this states that as
    a rule so a future "obvious" clustering heuristic has to delete a test to get
    in.
    """

    def test_a_saturday_kickoff_card_is_untouched(self):
        kickoff = datetime(2026, 9, 5, 14, 0, 0, tzinfo=UTC)
        card = []
        for n in range(10):
            event = Event()
            event.id = 900_000 + n
            event.home_team_name = f"Home {n}"
            event.away_team_name = f"Away {n}"
            event.commence_time = kickoff
            event.commence_time_source = "odds_api"
            event.external_id = f"efl-{n}"
            event.status = "scheduled"
            card.append(event)

        for n, event in enumerate(card):
            identity = EventIdentity(
                sport_key="soccer_england_league2",
                home_team_name=f"Home {n}",
                away_team_name=f"Away {n}",
                commence_time=kickoff,
                claim=EventClaim("odds_api", f"efl-{n}", schedule_derived=False),
                commence_time_source="odds_api",
            )
            _update_fields_by_priority(event, identity)

        assert {e.commence_time for e in card} == {kickoff}
        assert {e.status for e in card} == {"scheduled"}
        assert all(e.completed_at is None for e in card)
