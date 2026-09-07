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
it ages. `isStale` reads `commence_time`; `completed_at` is the intuitive
choice, is `None` in the served payload, and would give a different answer for
any game longer than the difference. So this file pins the field too.

RED ARM — run, not asserted.

* `CLIENT_COMPLETED_MAX_AGE_HOURS = 12` in the backend module:
  `test_the_backend_mirror_equals_the_frontend_constant` FAILED, everything
  else green. The message names both numbers and both files.
* `commence_time` -> `completed_at` in the frontend `isStale` body (reverted):
  `test_the_frontend_still_ages_on_commence_time` FAILED and the threshold test
  stayed GREEN, which is exactly the split that justifies having two tests.
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
    headline: str = "Recent upset",
) -> dict:
    return {
        "type": "event",
        "headline": headline,
        "data": {"id": 1, "status": status, "commence_time": commence_time},
    }


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

    def test_the_frontend_still_ages_on_commence_time(self):
        """The field, not just the number.

        Pinned separately because a threshold guard cannot see this change at
        all: swap `commence_time` for `completed_at` upstream and the constant
        still matches while every answer moves by the length of a game.
        """
        source = _source()
        body = source[source.index("export function isStale") :]
        event_arm = body[body.index('item.type === "event"') :]
        assert "commence_time" in event_arm, (
            "isStale's event arm no longer reads `commence_time`. The backend "
            "mirror in `client_deletes_finished_card` reads that field on "
            "purpose (`completed_at` is None in the served payload); if the "
            "client has moved to another field, move the mirror with it."
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
