"""#3836 — the backend's copy of the client's 8h deletion rule cannot drift.

WHY A GUARD AND NOT A COMMENT
------------------------------
`swap_client_deleted_finished_off_first_page` trades first-page slots away on
the strength of a prediction: *the browser is going to delete this card.* The
prediction is only as good as the copy of the rule it is made from, and the rule
lives in TypeScript — `frontend/lib/discover/feedFreshness.ts` — where nothing
in the Python suite would notice it changing.

The failure this guards is silent in the worst direction. Raise the frontend's
threshold to 12h and the backend keeps trading away cards the client would have
rendered: the page gets *shorter* in a way that looks like a thin slate, with
every test green. There is no error, no log, no user complaint that names the
cause. So the number is READ from the frontend file rather than restated here.

TWO NUMBERS, NOT ONE — and the second is the one a lazy guard misses. A mirror
that pins only the threshold still breaks if the frontend switches which FIELD
it ages, because the answer then moves by the length of a game with the constant
still matching. So this file pins the field too.

WHICH FIELD, AND WHY IT CHANGED (#4776, 2026-09-10). This guard used to pin
`commence_time`, on the stated grounds that the intuitive alternative
`completed_at` "is `None` in the served payload". That was true of
`completed_at` and false of the fact: D109/#4676 added `ended_at`, which is
present on 39 of 39 served finished rows. Ageing a *completed* event from its
kickoff charged every card for its own duration — a measured median 2.26h of an
eight-hour life, 3.11h for NFL — and retired the NFL season opener from Discover
at 1:20AM PT, which is why #4681's marquee-final arm had never had a morning it
could fire on. Both sides now read one anchor: `ended_at`, falling back to
`commence_time` because D109 requires the stamp stay optional.

RED ARM — run, not asserted.

* `CLIENT_COMPLETED_MAX_AGE_HOURS = 12` in the backend module:
  `test_the_backend_mirror_equals_the_frontend_constant` FAILED, everything
  else green. The message names both numbers and both files.
* `ended_at` dropped from `finishedEventAgeAnchor` in the frontend (reverted):
  `test_the_frontend_still_ages_from_the_end_then_the_start` FAILED and the
  threshold test stayed GREEN, which is exactly the split that justifies having
  two tests.
* the `commence_time` fallback dropped from the same function (reverted): the
  same test FAILED on its second assertion — the half a one-sided guard misses.
* `finished_event_age_anchor` reverted to `data.get("commence_time")` in the
  backend: `TestTheClockStartsAtTheWhistle` reds 4, and the frontend-source
  tests stay GREEN, which is why the behaviour is pinned as well as the text.
* `isStale`'s event arm inlining `ed.commence_time` instead of calling the
  anchor: red now, and GREEN in the first draft of this file — the assertion
  was a bare substring and the COMMENT above the call satisfied it. `_without_
  comments` is that survivor's fix; the guard reads code, never prose about it.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.utils.sports_first_page_rails import (
    CLIENT_COMPLETED_MAX_AGE_HOURS,
    client_deletes_finished_card,
)

#: Resolved from THIS FILE, never from the working directory. `pytest` run from
#: the repo root and from `backend/` must reach the same file, and a cwd-
#: relative path is a known way to fake a FileNotFoundError in this suite.
FEED_FRESHNESS_TS = (
    Path(__file__).resolve().parents[2]
    / "frontend"
    / "lib"
    / "discover"
    / "feedFreshness.ts"
)

NOW = datetime(2026, 9, 7, 12, 0, 0, tzinfo=timezone.utc)


def _without_comments(source: str) -> str:
    """TypeScript with its comments removed, so a source assertion cannot be
    satisfied by prose ABOUT the code instead of the code.

    Caught in the red arm and not by reasoning: the first draft of
    ``test_the_frontend_still_ages_from_the_end_then_the_start`` asserted
    ``"finishedEventAgeAnchor" in event_arm``, and the mutation that made
    ``isStale`` inline ``ed.commence_time`` again SURVIVED it — the comment two
    lines above the call still named the function. A guard that reads a
    docstring is a guard that passes when the code is wrong, which is the exact
    failure mode this whole file exists to prevent one level up.
    """
    without_block = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", "", without_block)


def _source() -> str:
    # Deliberately NOT `pytest.skip` on a missing file. A guard that excuses
    # itself when it cannot find its subject is a guard that reports green for
    # the one condition it exists to detect — the frontend file being moved or
    # renamed is a drift, not an exemption.
    assert FEED_FRESHNESS_TS.is_file(), (
        f"{FEED_FRESHNESS_TS} is missing. The backend mirrors this file's "
        "deletion rule; if it moved, move this guard with it — do not delete "
        "the guard."
    )
    return FEED_FRESHNESS_TS.read_text(encoding="utf-8")


def _event(
    *,
    status: str = "completed",
    commence_time: str | None,
    ended_at: object = None,
    headline: str = "Recent upset",
) -> dict:
    data: dict = {"id": 1, "status": status, "commence_time": commence_time}
    if ended_at is not None:
        data["ended_at"] = ended_at
    return {"type": "event", "headline": headline, "data": data}


def _iso(hours_ago: float) -> str:
    return (NOW - timedelta(hours=hours_ago)).isoformat()


class TestTheMirrorHolds:
    def test_the_backend_mirror_equals_the_frontend_constant(self):
        match = re.search(
            r"COMPLETED_EVENT_MAX_AGE_HOURS\s*=\s*(\d+(?:\.\d+)?)", _source()
        )
        assert match, (
            "COMPLETED_EVENT_MAX_AGE_HOURS is no longer declared in "
            f"{FEED_FRESHNESS_TS.name}. The backend's swap pass predicts what "
            "the client deletes; if the client stopped using a named constant, "
            "the prediction has no source and the pass must be re-derived."
        )
        frontend_hours = float(match.group(1))
        assert frontend_hours == float(CLIENT_COMPLETED_MAX_AGE_HOURS), (
            f"{FEED_FRESHNESS_TS.name} says {frontend_hours}h but "
            f"app/utils/sports_first_page_rails.py says "
            f"{CLIENT_COMPLETED_MAX_AGE_HOURS}h. The backend trades first-page "
            "slots away on this prediction, so a mismatch either strands cards "
            "the client renders or keeps cards it deletes — silently, and "
            "looking like a thin slate either way."
        )

    def test_the_frontend_still_ages_from_the_end_then_the_start(self):
        """The field, not just the number — and since #4776 it is two fields.

        Pinned separately because a threshold guard cannot see this change at
        all: swap the anchor upstream and the constant still matches while every
        answer moves by the length of a game. That is not hypothetical — it is
        the defect #4776 fixed, in this direction: ageing from `commence_time`
        alone charged a finished card for its own duration and cost a measured
        median 2.26h of an eight-hour window.

        BOTH halves are asserted, because each alone is a hole. Lose `ended_at`
        and the 2.26h comes back silently; lose the `commence_time` fallback and
        every row without the optional stamp (D109 requires it stay optional)
        reads as unreadable, which this module treats as "keep" — no error, no
        log, just finished cards outliving their window.
        """
        source = _source()
        anchor = source[source.index("export function finishedEventAgeAnchor") :]
        anchor_body = _without_comments(anchor[: anchor.index("}")])
        assert "ended_at" in anchor_body, (
            "finishedEventAgeAnchor no longer prefers `ended_at`. The backend "
            "mirror in `finished_event_age_anchor` does (#4776: a completed "
            "event's age starts at the whistle, not the kickoff); if the client "
            "has moved back to the kickoff, move the mirror with it."
        )
        assert "commence_time" in anchor_body, (
            "finishedEventAgeAnchor no longer falls back to `commence_time`. "
            "D109/#4676 requires `ended_at` stay OPTIONAL — it is absent on "
            "every unsettled row and a cached payload can predate it — so the "
            "fallback is the contract, not a defensive extra."
        )

        body = source[source.index("export function isStale") :]
        event_arm = _without_comments(body[body.index('item.type === "event"') :])
        assert "finishedEventAgeAnchor(" in event_arm, (
            "isStale's event arm no longer routes through "
            "`finishedEventAgeAnchor`, so the anchor test above is now pinning "
            "a function the client does not use. Both sides read one anchor on "
            "purpose; if the arm inlined its own field, re-derive the mirror."
        )

    def test_the_frontend_still_treats_both_terminal_statuses(self):
        """`FINISHED_STATUSES` is the other half of the shared vocabulary."""
        source = _source()
        assert '"completed"' in source and '"closed"' in source, (
            "isStale no longer names both terminal statuses; the backend's "
            "FINISHED_STATUSES pair is a mirror of them."
        )


class TestTheComparisonIsTheClientsComparison:
    def test_exactly_at_the_threshold_is_rendered_not_deleted(self):
        """`hoursAgo > MAX`, strictly. A `>=` here would trade away a card the
        reader is about to see, which is the one error this pass must never
        make — it costs a slot AND removes a card that was fine."""
        item = _event(commence_time=_iso(CLIENT_COMPLETED_MAX_AGE_HOURS))
        assert client_deletes_finished_card(item, now=NOW) is False

    def test_a_hair_past_the_threshold_is_deleted(self):
        item = _event(commence_time=_iso(CLIENT_COMPLETED_MAX_AGE_HOURS + 0.01))
        assert client_deletes_finished_card(item, now=NOW) is True

    @pytest.mark.parametrize("status", ["completed", "closed", "COMPLETED", " Closed "])
    def test_both_terminal_statuses_in_any_casing(self, status):
        item = _event(status=status, commence_time=_iso(20))
        assert client_deletes_finished_card(item, now=NOW) is True

    @pytest.mark.parametrize("status", ["live", "scheduled", "suspended", ""])
    def test_a_game_that_is_not_finished_is_never_deleted_however_old(self, status):
        """Mirrors the client, and also protects the hoist: a live game is
        never a candidate for this swap no matter what its commence_time says.
        `suspended` is in this list on purpose — live/048 put paused matches in
        the pool precisely so they keep a place on the page."""
        item = _event(status=status, commence_time=_iso(400))
        assert client_deletes_finished_card(item, now=NOW) is False


class TestTheClockStartsAtTheWhistle:
    """#4776. Every specimen here is a real production row from
    ``GET /api/feed?mode=sports&limit=250`` at 2026-09-10T12:19Z, so the numbers
    are the ones that actually retired these cards, not invented ones."""

    def test_the_nfl_opener_is_kept_at_the_hour_the_kickoff_clock_deleted_it(self):
        """Event 14780138, SEA 13-10 NE. Kickoff 00:20Z, ended 03:26:32Z.

        This is the whole ship in one assertion. At 09:00Z the game is 8.67h
        past kickoff and 5.56h past the whistle: deleted by the old rule, kept
        by the new one. On production it retired at 08:20Z — 1:20AM Pacific,
        before any American reader woke up — which is why #4681's marquee arm
        shipped, certed and live, and served nobody.
        """
        item = _event(
            commence_time="2026-09-10T00:20:00+00:00",
            ended_at="2026-09-10T03:26:32.075760+00:00",
        )
        nine_am_z = datetime(2026, 9, 10, 9, 0, 0, tzinfo=timezone.utc)
        assert client_deletes_finished_card(item, now=nine_am_z) is False

    def test_the_same_game_is_still_deleted_once_it_is_eight_hours_past_the_end(self):
        """The fix moves the deadline, it does not remove it. 11:30Z is 8.06h
        after the whistle — a card Discover should no longer be spending a slot
        on, and the arm must still say so or this is a leak, not a fix."""
        item = _event(
            commence_time="2026-09-10T00:20:00+00:00",
            ended_at="2026-09-10T03:26:32.075760+00:00",
        )
        half_eleven_z = datetime(2026, 9, 10, 11, 30, 0, tzinfo=timezone.utc)
        assert client_deletes_finished_card(item, now=half_eleven_z) is True

    def test_a_row_with_no_ended_at_behaves_exactly_as_it_does_today(self):
        """D109 requires `ended_at` stay OPTIONAL — absent on unsettled rows,
        and absent from any payload cached before the backend that added it. An
        unstamped row must age on `commence_time` with the old answer, or this
        change is a silent behaviour flip for every such row."""
        old = _event(commence_time=_iso(20))
        fresh = _event(commence_time=_iso(1))
        assert client_deletes_finished_card(old, now=NOW) is True
        assert client_deletes_finished_card(fresh, now=NOW) is False

    def test_the_anchor_can_only_ever_keep_a_card_never_newly_delete_one(self):
        """The safety property `finished_event_age_anchor` is built on, asserted
        rather than asserted-in-prose: a game ends after it starts, so across
        the real served spread of durations (1.90h to 8.41h) the new rule is a
        superset of the old one's keeps. If this ever reds, the swap pass in
        #3836 is trading away cards the client renders and must be re-derived.
        """
        for duration in (1.90, 2.26, 2.78, 3.11, 8.41):
            for hours_since_kickoff in (4, 8, 9, 10, 12, 16):
                item = _event(
                    commence_time=_iso(hours_since_kickoff),
                    ended_at=_iso(max(hours_since_kickoff - duration, 0.0)),
                )
                old_rule = _event(commence_time=_iso(hours_since_kickoff))
                if client_deletes_finished_card(old_rule, now=NOW) is False:
                    assert client_deletes_finished_card(item, now=NOW) is False, (
                        f"a {duration}h game {hours_since_kickoff}h past kickoff "
                        "was kept by the kickoff clock and deleted by the "
                        "whistle clock — the anchor is not monotone"
                    )

    def test_the_mlb_slate_the_old_clock_hid(self):
        """Not one specimen — the shape. All 15 completed MLB rows served at
        12:19Z were past 8h from first pitch; measured median duration 2.78h.
        A 2.78h game that ended 6h ago started 8.78h ago: gone under the old
        rule, present under the new one, and it is the ordinary case, not an
        edge."""
        item = _event(commence_time=_iso(8.78), ended_at=_iso(6.0))
        assert client_deletes_finished_card(item, now=NOW) is False

    @pytest.mark.parametrize("junk", ["", "   ", 1757260800, {"t": 1}, [], None])
    def test_a_malformed_ended_at_falls_back_instead_of_answering_from_junk(
        self, junk
    ):
        """The preference is typed (non-empty string) so the two languages agree
        on the shapes JS truthiness and Python truthiness disagree about. A junk
        stamp must not become the anchor and must not change the verdict."""
        item = _event(commence_time=_iso(20), ended_at=junk)
        assert client_deletes_finished_card(item, now=NOW) is True
        fresh = _event(commence_time=_iso(1), ended_at=junk)
        assert client_deletes_finished_card(fresh, now=NOW) is False

    def test_an_unreadable_ended_at_string_is_kept_not_fallen_back_from(self):
        """A non-empty but unparseable string IS the anchor, in both languages:
        `new Date("not a date")` is NaN and `NaN > 8` is false, so the client
        keeps the card. Falling back to an old `commence_time` here would delete
        a card the browser paints — the one error this module must never make.
        """
        item = _event(commence_time=_iso(20), ended_at="not a date")
        assert client_deletes_finished_card(item, now=NOW) is False

    def test_exactly_at_the_threshold_from_the_end_is_rendered(self):
        """The strict `>` survives the anchor change, on the new field."""
        item = _event(
            commence_time=_iso(20),
            ended_at=_iso(CLIENT_COMPLETED_MAX_AGE_HOURS),
        )
        assert client_deletes_finished_card(item, now=NOW) is False


class TestUnreadableIsRendered:
    """`new Date(undefined)` is NaN and `NaN > 8` is FALSE, so the client keeps
    the card. Reading an unparseable stamp as "old" would be the expensive
    direction of this error: the backend would trade away cards that are about
    to appear on screen."""

    @pytest.mark.parametrize(
        "value", [None, "", "   ", "not a date", 1757260800, {"t": 1}, []]
    )
    def test_an_unreadable_commence_time_is_kept(self, value):
        item = _event(commence_time=value)  # type: ignore[arg-type]
        assert client_deletes_finished_card(item, now=NOW) is False

    def test_a_naive_stamp_is_read_as_utc_not_as_local_time(self):
        """Everything else in this payload is UTC. Reading a naive stamp as
        local time makes the answer depend on the host's offset, so the same
        card would be deleted on one dyno and kept on another."""
        naive = (NOW - timedelta(hours=20)).replace(tzinfo=None).isoformat()
        assert client_deletes_finished_card(_event(commence_time=naive), now=NOW) is True
        fresh_naive = (NOW - timedelta(hours=1)).replace(tzinfo=None).isoformat()
        assert (
            client_deletes_finished_card(_event(commence_time=fresh_naive), now=NOW)
            is False
        )

    def test_a_zulu_suffix_parses(self):
        """The served payload uses `+00:00`, but `Z` is the same instant and a
        parser that refuses it would silently mark every card renderable."""
        zulu = (NOW - timedelta(hours=20)).strftime("%Y-%m-%dT%H:%M:%SZ")
        assert client_deletes_finished_card(_event(commence_time=zulu), now=NOW) is True


class TestOnlyEventCardsAreJudged:
    @pytest.mark.parametrize("card_type", ["futures", "concept", "bundle", None])
    def test_a_non_event_card_is_never_judged_by_this_rule(self, card_type):
        """`isStale`'s futures arm keys on `resolution_date`, which this pass
        does not model. Judging a futures card by an event rule it does not
        follow would trade away markets for no reason."""
        item = {
            "type": card_type,
            "headline": "x",
            "data": {"id": 2, "status": "completed", "commence_time": _iso(99)},
        }
        assert client_deletes_finished_card(item, now=NOW) is False

    @pytest.mark.parametrize("item", [None, "event", 7, [], {"type": "event"}])
    def test_a_malformed_item_is_kept_rather_than_traded_away(self, item):
        assert client_deletes_finished_card(item, now=NOW) is False  # type: ignore[arg-type]
