"""#5511 — a reconstructed capture stamp never post-dates real time.

`_backfill_from_settled_events` Phase 2 stamps snapshots from a VENUE-SUPPLIED
time (`close_time`, falling back to `expiration_time`, and `open_time` on the
two prev-price paths). Those fields are schedule, not observation: Kalshi's
`expiration_time` is the *latest possible* expiry, so three production rows on
2026-09-12 were stamped 14.4h into the future, exactly equal to their market's
`expiration_time`.

A post-dated `captured_at` wins `latest_observed_at_subquery`'s
`ORDER BY captured_at DESC LIMIT 1` (no upper bound), so the served
`observed_at` becomes a negative age and renders as maximally fresh — the one
staleness error a reader cannot detect.

These tests pin BOTH sides. A clamp that also moved legitimate past stamps
would destroy the closing-price reconstruction this path exists to perform, so
"leaves a real past stamp alone" is asserted as hard as "pulls a future one
down".
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.latest_observation import clamp_capture_stamp

NOW = datetime(2026, 9, 12, 5, 23, 29, tzinfo=timezone.utc)


class TestClampsTheFutureDown:
    """The defect direction: a stamp ahead of `now` is pulled back to `now`."""

    def test_the_production_specimen_is_clamped(self):
        """The exact row from #5511: expiration_time 14.4h ahead of read time."""
        expiration_time = datetime(2026, 9, 12, 19, 45, tzinfo=timezone.utc)
        assert expiration_time > NOW  # the premise, stated so it cannot rot

        assert clamp_capture_stamp(expiration_time, NOW) == NOW

    @pytest.mark.parametrize(
        "ahead",
        [
            timedelta(microseconds=1),
            timedelta(seconds=1),
            timedelta(hours=14, minutes=24),
            timedelta(days=90),
        ],
    )
    def test_any_amount_ahead_is_clamped(self, ahead):
        """No tolerance band — a capture cannot happen in the future at all."""
        assert clamp_capture_stamp(NOW + ahead, NOW) == NOW

    def test_a_naive_future_stamp_is_clamped_not_crashed(self):
        """`dt_parse` returns naive for a stamp with no offset.

        Comparing naive to aware raises `TypeError`; an ingest path must not
        abort over a missing `Z`, and it must not let the naive value through
        unclamped either.
        """
        naive_future = datetime(2026, 9, 12, 19, 45)  # no tzinfo
        assert naive_future.tzinfo is None

        assert clamp_capture_stamp(naive_future, NOW) == NOW


class TestLeavesHonestStampsAlone:
    """The reconstruction this path exists for must survive the clamp."""

    @pytest.mark.parametrize(
        "behind",
        [
            timedelta(microseconds=1),
            timedelta(minutes=17),
            timedelta(days=3),
            timedelta(days=400),
        ],
    )
    def test_a_past_close_time_is_returned_verbatim(self, behind):
        """A genuinely settled market's close IS the honest capture time."""
        stamp = NOW - behind
        assert clamp_capture_stamp(stamp, NOW) == stamp

    def test_a_real_pregame_read_survives(self):
        """The specimen's own legitimate 09-09 snapshot must not move."""
        pregame = datetime(2026, 9, 9, 17, 25, tzinfo=timezone.utc)
        assert clamp_capture_stamp(pregame, NOW) == pregame

    def test_exactly_now_is_not_clamped_away(self):
        """The boundary is inclusive: `now` is a valid capture instant.

        Asserted because `<=` vs `<` is the kind of edge a mutation flips
        without any other test noticing.
        """
        assert clamp_capture_stamp(NOW, NOW) == NOW

    def test_a_naive_past_stamp_is_read_as_utc_and_kept(self):
        """Naive-past must not be silently dragged to `now` by the tz handling."""
        naive_past = datetime(2026, 9, 9, 17, 25)
        expected = naive_past.replace(tzinfo=timezone.utc)

        assert clamp_capture_stamp(naive_past, NOW) == expected


class TestAbsentTime:
    def test_none_means_we_read_it_just_now(self):
        """The venue gave no time; the honest stamp is `now`, not a crash.

        This mirrors what the close_time call site did before the clamp, so the
        behaviour is preserved rather than introduced.
        """
        assert clamp_capture_stamp(None, NOW) == NOW


class TestTheResultIsAlwaysUsable:
    """Whatever comes back is writable into a timestamptz column."""

    @pytest.mark.parametrize(
        "parsed",
        [
            None,
            NOW + timedelta(days=1),
            NOW - timedelta(days=1),
            datetime(2026, 9, 12, 19, 45),
        ],
    )
    def test_always_aware_and_never_ahead_of_now(self, parsed):
        result = clamp_capture_stamp(parsed, NOW)

        assert result.tzinfo is not None, "a naive stamp reaches Postgres ambiguous"
        assert result <= NOW, "the whole point: never post-dated"
