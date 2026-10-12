"""#1541 — a championship the provider withdrew is served as unavailable, never final.

THE REVIEW BLOCKER (PR #10938, exact ``7f7dd7bb82``). The first cut resolved a
provider-dropped board as ``status='resolved'``, and ``/futures/[id]`` keys its
"Final Results" heading and settled hero on exactly that status. A FUTURE
championship the provider stops listing for eight days met the same rule, so a
competition still ahead would have read as finished. A listing gap plus quote
silence proves the market is unavailable, not that anything ended.

So the task now writes ``status='withdrawn'`` and this is the reader seam: what
``_format_market_detail`` serves for that row. Three boards, same shape:

* the counterexample — the 2027 NBA Finals board, withdrawn after eight quiet
  unlisted days: served ``withdrawn``, every price withheld, its live-era hook
  withheld, no lead pick;
* the SAME board still open (the control that makes the withholding arm
  non-vacuous): prices served;
* an actually concluded champion — resolved, the winner graded by a venue:
  served ``resolved`` with its prices, unchanged by this ship.

The page half (``withdrawn`` → "This market is no longer offered.", never
"Final Results") is ``frontend/__tests__/aWithdrawnMarketIsNotSettled1541.test.ts``.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

NOW = datetime.now(timezone.utc)
EIGHT_DAYS = NOW - timedelta(days=8)
FRESH = NOW - timedelta(hours=4)

#: What the 2027 board's provider identity looks like on production today
#: (market 2, read 2026-10-12): the Finals are eight months away.
FUTURE_IDENTITY = {
    "scope": "current_quotes_only",
    "event_id": "bfb75c30bceadf7a0e5277f59ec11eac",
    "sport_key": "basketball_nba_championship_winner",
    "commence_time": "2027-06-19T00:40:00+00:00",
}

_HOOK = "Who wins the 2027 NBA title? The market's view is shifting."


def _outcome(oid, name, prob, seen, *, is_winner=False, source=None):
    return SimpleNamespace(
        id=oid,
        name=name,
        external_id=name,
        current_probability=prob,
        current_american_odds=None,
        rank=oid,
        rank_change_24h=None,
        probability_change_24h=None,
        opening_probability=prob,
        opening_american_odds=None,
        is_winner=is_winner,
        resolution_source=source,
        last_updated=seen,
        team_id=None,
    )


def _board(status, *, seen, external_id="basketball_nba_championship_winner", graded=False):
    return SimpleNamespace(
        id=2,
        name="NBA Championship Winner",
        description=None,
        category="championship",
        source="odds_api",
        external_id=external_id,
        status=status,
        sport=None,
        sport_id=None,
        event_id=None,
        market_type=None,
        market_tier=1,
        llm_sport_category="basketball",
        mutually_exclusive=True,
        commence_time=None,
        resolution_date=None,
        created_at=None,
        updated_at=seen,
        group_id=None,
        canonical_market_key=None,
        hook_description=_HOOK,
        hook_generated_at=seen,
        hook_leader_at_generation="Oklahoma City Thunder",
        image_url=None,
        category_tags=[],
        market_metadata={"odds_api_current_event": FUTURE_IDENTITY},
        outcomes=[
            _outcome(21, "Oklahoma City Thunder", 0.31, seen,
                     is_winner=graded, source="api_settlement" if graded else None),
            _outcome(22, "Denver Nuggets", 0.12, seen,
                     is_winner=False, source="api_settlement" if graded else None),
            _outcome(23, "Boston Celtics", 0.09, seen,
                     is_winner=False, source="api_settlement" if graded else None),
        ],
    )


def _serve(board):
    from app.routes.futures import _format_market_detail

    return _format_market_detail(board, None, set())


def _prices(detail):
    return {o["name"]: o["probability"] for o in detail["outcomes"]}


class TestTheFutureCounterexampleIsUnavailableNotFinal:
    def test_it_is_served_withdrawn_never_resolved(self):
        detail = _serve(_board("withdrawn", seen=EIGHT_DAYS,
                               external_id="basketball_nba_championship_winner:retired:2026-10-04"))
        assert detail["status"] == "withdrawn"
        assert detail["status"] != "resolved"

    def test_no_price_on_it_is_served(self):
        detail = _serve(_board("withdrawn", seen=EIGHT_DAYS))
        assert set(_prices(detail).values()) == {None}, _prices(detail)
        assert detail["prices_withheld"] == 3
        for o in detail["outcomes"]:
            assert o["american_odds"] is None and o["movement"] is None

    def test_the_rows_stay_so_the_field_is_still_readable(self):
        detail = _serve(_board("withdrawn", seen=EIGHT_DAYS))
        assert set(_prices(detail)) == {"Oklahoma City Thunder", "Denver Nuggets", "Boston Celtics"}

    def test_no_leg_is_shown_as_a_winner_or_a_loser(self):
        detail = _serve(_board("withdrawn", seen=EIGHT_DAYS))
        assert all(o.get("resolution_source") is None for o in detail["outcomes"])

    def test_its_live_era_hook_stands_down_on_status_alone(self):
        """Isolated like #8729's arm: a fresh, current-policy hook naming no
        outcome passes every staleness rule, so only `withdrawn` can refuse it.
        The open twin publishes it (anti-vacuity)."""
        from app.utils.hook_staleness import CURRENT_HOOK_POLICY_VERSION, HOOK_POLICY_METADATA_KEY

        def fresh_hook(board):
            board.hook_generated_at = NOW - timedelta(hours=6)
            board.market_metadata = {**board.market_metadata, HOOK_POLICY_METADATA_KEY: CURRENT_HOOK_POLICY_VERSION}
            return board

        withdrawn = _serve(fresh_hook(_board("withdrawn", seen=EIGHT_DAYS)))
        assert withdrawn["hook_description"] is None and withdrawn["hook_withheld"] is True
        live = _serve(fresh_hook(_board("open", seen=FRESH)))
        assert live["hook_description"] == _HOOK and live["hook_withheld"] is False

    def test_no_lead_pick_is_offered(self):
        detail = _serve(_board("withdrawn", seen=EIGHT_DAYS))
        assert detail["lead_outcome_id"] is None


class TestControls:
    def test_the_same_board_open_serves_its_prices(self):
        """Anti-vacuity: same rows, same clock shape, only status differs."""
        detail = _serve(_board("open", seen=FRESH))
        assert detail["status"] == "open"
        assert detail["prices_withheld"] == 0
        assert _prices(detail)["Oklahoma City Thunder"] is not None

    def test_a_concluded_champion_still_reads_as_a_result(self):
        """An actually finished championship — resolved, winner graded by a
        venue — is untouched: served `resolved`, prices shown as what ran."""
        detail = _serve(_board("resolved", seen=EIGHT_DAYS, graded=True))
        assert detail["status"] == "resolved"
        assert detail["prices_withheld"] == 0
        champion = next(o for o in detail["outcomes"] if o["name"] == "Oklahoma City Thunder")
        assert champion["probability"] is not None

    @pytest.mark.parametrize("status", ["open", "resolved"])
    def test_withholding_is_keyed_on_withdrawn_alone(self, status):
        detail = _serve(_board(status, seen=FRESH, graded=status == "resolved"))
        assert detail["prices_withheld"] == 0
