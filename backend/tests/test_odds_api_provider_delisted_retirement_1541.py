"""#1541 — the pure decisions behind withdrawing a provider-dropped odds_api row.

The round trip (real task, real Postgres) is
``tests/integration/test_provider_delisted_championship_retires_1541_pg.py``;
this file pins the rule itself so every arm can be mutated in isolation.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.odds_api_retirement import (
    GRADED,
    LISTED,
    NO_EVIDENCE,
    NOT_LIVE_STATUSES,
    PROVIDER_DELISTED_QUIET_DAYS,
    RECENTLY_QUOTED,
    RETIRE,
    RETIREMENT_METADATA_KEY,
    STALE_LISTED,
    STALE_UNSETTLED_VERDICTS,
    WITHDRAWN_REASON,
    WITHDRAWN_STATUS,
    classify_board,
    listing_is_usable,
    retired_external_id,
    retirement_metadata,
    same_edition_reopens,
)

CLOCK = datetime(2026, 10, 12, 14, 30, tzinfo=timezone.utc)
WC = "soccer_fifa_world_cup_winner"
# The specimen's real last write (production, read 2026-09-15 and 2026-10-12).
WC_LAST_QUOTE = datetime(2026, 7, 19, 20, 30, 8, tzinfo=timezone.utc)
WC_PARENT = datetime(2026, 7, 19, 20, 38, 32, tzinfo=timezone.utc)
LISTED_KEYS = frozenset({"golf_masters_tournament_winner", "basketball_nba_championship_winner"})


def verdict(external_id=WC, *, leg=WC_LAST_QUOTE, parent=WC_PARENT, graded=False, listed=LISTED_KEYS):
    return classify_board(
        external_id=external_id,
        listed_keys=listed,
        poll_clock=CLOCK,
        newest_leg_at=leg,
        parent_touched_at=parent,
        has_graded_leg=graded,
    )


class TestTheSpecimenRetires:
    def test_market_10_unlisted_and_unquoted_since_the_final_retires(self):
        assert verdict() == RETIRE

    def test_a_future_championship_dropped_for_eight_days_gets_the_same_verdict(self):
        """THE REVIEW COUNTEREXAMPLE (PR #10938). The 2027 NBA Finals board,
        unlisted and unquoted for eight days. The classifier has no event-end
        input and cannot tell it from market 10 — which is why RETIRE may only
        ever mean WITHDRAWN, never resolved. The transition is pinned below and
        on real Postgres."""
        eight = CLOCK - timedelta(days=8)
        assert verdict("basketball_nba_championship_winner", leg=eight, parent=eight, listed=frozenset({"golf_masters_tournament_winner"})) == RETIRE

    def test_naive_stamps_are_read_as_utc_not_refused(self):
        assert verdict(leg=WC_LAST_QUOTE.replace(tzinfo=None), parent=WC_PARENT.replace(tzinfo=None)) == RETIRE


class TestHealthyControls:
    def test_a_listed_live_championship_is_never_retired(self):
        """The 2027 Masters field: listed, priced this poll."""
        fresh = CLOCK - timedelta(hours=4)
        assert verdict("golf_masters_tournament_winner", leg=fresh, parent=fresh) == LISTED

    def test_a_listed_board_is_never_retired_however_quiet(self):
        """Listing is the provider saying the question is open. Flag, never close."""
        out = verdict("golf_masters_tournament_winner")
        assert out == STALE_LISTED
        assert out != RETIRE
        assert out in STALE_UNSETTLED_VERDICTS

    def test_an_unlisted_board_quoted_inside_the_window_waits(self):
        """A just-finished tournament, or a one-poll listing blip."""
        recent = CLOCK - timedelta(days=PROVIDER_DELISTED_QUIET_DAYS - 1)
        assert verdict(leg=recent, parent=recent) == RECENTLY_QUOTED

    @pytest.mark.parametrize("which", ["leg", "parent"])
    def test_both_clocks_must_be_quiet(self, which):
        """#8011's lesson: either clock alone admits a live board."""
        recent = CLOCK - timedelta(days=1)
        kwargs = {which: recent}
        assert verdict(**kwargs) == RECENTLY_QUOTED

    def test_the_window_boundary_is_exclusive(self):
        edge = CLOCK - timedelta(days=PROVIDER_DELISTED_QUIET_DAYS)
        assert verdict(leg=edge, parent=edge) == RECENTLY_QUOTED
        past = edge - timedelta(seconds=1)
        assert verdict(leg=past, parent=past) == RETIRE


class TestNoEvidenceAndContradictions:
    @pytest.mark.parametrize("leg,parent", [(None, WC_PARENT), (WC_LAST_QUOTE, None), (None, None), ("2026-07-19", WC_PARENT)])
    def test_silence_is_not_closure(self, leg, parent):
        out = verdict(leg=leg, parent=parent)
        assert out == NO_EVIDENCE
        assert out in STALE_UNSETTLED_VERDICTS

    def test_a_board_with_a_graded_leg_is_not_this_writers_question(self):
        out = verdict(graded=True)
        assert out == GRADED
        assert out in STALE_UNSETTLED_VERDICTS

    def test_an_empty_listing_cannot_testify(self):
        assert listing_is_usable([], 5) is False
        assert listing_is_usable(None, 5) is False

    def test_a_poll_that_wrote_nothing_cannot_testify(self):
        assert listing_is_usable(["golf_masters_tournament_winner"], 0) is False
        assert listing_is_usable(["golf_masters_tournament_winner"], 1) is True


class TestTheTransitionSaysWhatItIs:
    def test_withdrawn_is_not_a_settlement_word(self):
        """Every reader keys "Final Results"/settled language on `resolved`, and
        the web Discover/collection cards and native read `closed` as settled.
        A listing gap proves unavailable, not finished."""
        assert WITHDRAWN_STATUS not in {"resolved", "closed", "settled", "finalized", "final", "completed"}
        assert WITHDRAWN_STATUS == "withdrawn"

    def test_not_live_names_both_resolved_and_withdrawn(self):
        assert set(NOT_LIVE_STATUSES) == {"resolved", WITHDRAWN_STATUS}
        assert "open" not in NOT_LIVE_STATUSES

    def test_the_withdrawal_records_its_reason_and_no_resolution_gate(self):
        meta = retirement_metadata(rolling_key=WC, last_observed_at=WC_LAST_QUOTE, checked_at=CLOCK)
        assert meta[RETIREMENT_METADATA_KEY]["reason"] == WITHDRAWN_REASON
        assert "resolution_gate" not in meta

    def test_the_rolling_key_is_released_with_its_prefix_intact(self):
        new = retired_external_id(WC, WC_LAST_QUOTE)
        assert new == "soccer_fifa_world_cup_winner:retired:2026-07-19"
        assert new != WC and new.startswith(WC)

    def test_the_metadata_keeps_the_original_key(self):
        meta = retirement_metadata(rolling_key=WC, last_observed_at=WC_LAST_QUOTE, checked_at=CLOCK)
        record = meta[RETIREMENT_METADATA_KEY]
        assert record["rolling_key"] == WC
        assert record["last_observed_at"].startswith("2026-07-19T20:30:08")


class TestSameEditionReopens:
    def test_the_same_provider_event_reopens(self):
        assert same_edition_reopens({"event_id": "abc"}, {"event_id": "abc"}) is True

    @pytest.mark.parametrize("retired,incoming", [
        ({"event_id": "abc"}, {"event_id": "next"}),
        (None, {"event_id": "abc"}),
        ({"event_id": "abc"}, None),
        (None, None),
        ({"event_id": ""}, {"event_id": ""}),
        ({}, {}),
    ])
    def test_a_different_or_unknown_edition_does_not(self, retired, incoming):
        assert same_edition_reopens(retired, incoming) is False


class TestTheLeagueGridsDoNotListAWithdrawnRow:
    """The two readers that filtered `status != 'resolved'` would have listed a
    withdrawn row as live. Compiled, so the assertion is on the SQL they run."""

    def test_the_golf_candidate_filter_excludes_withdrawn(self):
        from sqlalchemy.dialects import postgresql

        from app.config.league_configs import LEAGUE_CONFIGS
        from app.routes.playoffs import _build_golf_candidate_filters

        golf = next(c for c in LEAGUE_CONFIGS.values() if c.slug == "golf")
        sql = " ".join(
            str(f.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
            for f in _build_golf_candidate_filters(golf)
        )
        assert "futures_markets.status != 'resolved'" in sql, sql
        assert "futures_markets.status != 'withdrawn'" in sql, sql

    def test_the_team_progression_query_excludes_withdrawn(self):
        import inspect

        from app.routes import playoffs

        src = inspect.getsource(playoffs._get_team_progression_for_event_uncached)
        assert "FuturesMarket.status != WITHDRAWN_STATUS" in src
