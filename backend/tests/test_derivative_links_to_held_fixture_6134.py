"""#6134 — a Polymarket prop attaches to the fixture we already hold.

SHIP (pillar MATCHING / TRUTH). An event page shows the Halftime Result, Exact
Score, First Team to Score, Second Half Result and Total Corners markets
Polymarket lists for that match, instead of only the match winner.

THE DEFECT WAS HALF A CONTRACT. `is_derivative_market_name`'s docstring says
such a row "may link to a fixture we already hold, but it must never mint one".
Only the refusal was ever built. `extract_matchup` splits on " vs. ", so the
market type stays glued to team_b — `"UD Las Palmas - Exact Score"` — and every
team comparison in `_find_matching_event` runs against a string no event row
carries, so the away side never verifies.

Measured on production 2026-09-14 10:15Z: fixture `SD Eibar vs. UD Las Palmas`
had its moneyline (market 61019304) linked to event 15312462 while five sibling
parents for the SAME match sat at `event_id IS NULL`, each with its own
`polymarket_event_id` — so #5821's container-sibling channel, which keys on a
SHARED provider event id, could not reach them either. Over a 1,000-row sample
of unattached open Polymarket rows in (-2d, +14d), 930 recover their away team
across 204 distinct fixtures, and 191 of those fixtures already hold an event.

THE THREE GUARDS THIS MUST NOT BREAK are each pinned below, because the fix is
one line at a call site and the obvious "simplification" — clean the name
instead of the search copy — silently defeats all three:
  * #2871 auto-create, which stamps `matchup.team_b` as the away team's name;
  * the G3 kill, which reads "winner" out of "- First 5 Innings Winner";
  * #5031's blend admission, which keeps an Exact Score price out of the hero.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.prediction_market_matching import (  # noqa: E402
    extract_matchup,
    is_derivative_market_name,
    is_game_level_market,
    matchup_for_link_search,
)

FIXTURE = "SD Eibar vs. UD Las Palmas"

#: The five sibling parents production held unattached on the specimen fixture.
LIVE_SPECIMENS = [
    f"{FIXTURE} - Exact Score",
    f"{FIXTURE} - Halftime Result",
    f"{FIXTURE} - First Team to Score",
    f"{FIXTURE} - Second Half Result",
    f"{FIXTURE} - Total Corners",
]


class TestTheAwayTeamIsRecoveredForSearch:
    """The half of the contract that was never reachable."""

    @pytest.mark.parametrize("name", LIVE_SPECIMENS)
    def test_search_copy_carries_the_real_away_team(self, name):
        raw = extract_matchup(name)
        assert raw is not None, f"{name!r} must still parse"

        search = matchup_for_link_search(raw, name)

        assert search.team_a == "SD Eibar"
        assert search.team_b == "UD Las Palmas", (
            "the search copy must name the away team the EVENT row carries; "
            f"got {search.team_b!r}, which no event's away_team_name equals"
        )

    @pytest.mark.parametrize("name", LIVE_SPECIMENS)
    def test_the_raw_matchup_is_left_alone(self, name):
        """Auto-create reads the RAW one. Cleaning it re-opens #2871."""
        raw = extract_matchup(name)
        assert raw.team_b.endswith(name.rsplit(" - ", 1)[1]), (
            "extract_matchup's own output must still carry the suffix — "
            "test_the_suffix_is_left_on_the_parsed_name pins this contract "
            "and _create_event_from_prediction_market depends on it"
        )

    def test_the_yes_team_follows_the_rewritten_side(self):
        """A stale yes_team pointing at the old string would resolve to nobody."""
        name = f"{FIXTURE} - Exact Score"
        raw = extract_matchup(name)
        search = matchup_for_link_search(raw, name)

        if raw.yes_team == raw.team_b:
            assert search.yes_team == search.team_b
        else:
            assert search.yes_team == raw.yes_team, "an unrelated yes_team moved"


class TestTheRuleSleepsOnEverythingElse:
    """A non-derivative is handed back untouched — identity, not a copy."""

    @pytest.mark.parametrize(
        "name",
        [
            FIXTURE,
            "FC Thun vs. Lausanne-Sport",  # hyphen INSIDE a club name
            "CF Estrela da Amadora vs. FC Porto - More Markets",
            "Mets vs. Dodgers - Game 4",
        ],
    )
    def test_non_derivative_matchups_are_returned_unchanged(self, name):
        raw = extract_matchup(name)
        assert raw is not None
        assert matchup_for_link_search(raw, name) is raw, (
            f"{name!r} is not a derivative — the rule must sleep on it"
        )

    def test_a_series_game_number_is_never_stripped(self):
        """'- Game 4' designates a DISTINCT REAL GAME.

        Stripping it would search Games 1-5 as one fixture and attach five
        different games' props to whichever event answered first — a
        data-destroying merge, the opposite of this fix.
        """
        for n in (1, 2, 3, 4, 5):
            name = f"Mets vs. Dodgers - Game {n}"
            assert not is_derivative_market_name(name)
            search = matchup_for_link_search(extract_matchup(name), name)
            assert search.team_b == f"Dodgers - Game {n}", (
                "the game number must survive into the search, or two "
                "different games become one"
            )

    def test_a_hyphenated_club_name_survives(self):
        name = "FC Thun vs. Lausanne-Sport - Total Corners"
        search = matchup_for_link_search(extract_matchup(name), name)
        assert search.team_b == "Lausanne-Sport", (
            "only the market type comes off; the club's own hyphen stays"
        )

    def test_none_and_one_sided_matchups_pass_through(self):
        assert matchup_for_link_search(None, "anything") is None

        one_sided = extract_matchup("Will SD Eibar win?")
        if one_sided is not None and not one_sided.team_b:
            assert matchup_for_link_search(one_sided, "Will SD Eibar win?") is one_sided

    def test_never_trades_a_real_name_for_an_empty_one(self):
        """A title that is nothing BUT a market type must not empty team_b."""

        class _M:
            team_a, team_b, yes_team, format_type = "A", "Exact Score", "A", "vs"

        name = "A vs. Exact Score"
        out = matchup_for_link_search(_M(), name)
        assert out.team_b, "team_b was emptied — the search would match anything"


class TestTheThreeGuardsSurvive:
    """Each of these is why the fix is at the SEARCH seam and nowhere else."""

    @pytest.mark.parametrize(
        "name",
        [
            "Boston Red Sox vs. Miami Marlins - First 5 Innings Winner",
            "A vs. B - Map 2 Winner",
        ],
    )
    def test_g3_the_period_market_never_reaches_the_matcher(self, name):
        """`_MATCHUP_NON_GAME_KEYWORDS` reads 'winner' out of the glued team_b.

        This runs on the NAME, before any search copy exists, so the helper
        cannot reach it — asserted here so a future move of the strip into
        `_normalize_variants` fails loudly instead of admitting period markets
        into the full-game blend.
        """
        assert is_game_level_market(name) is False

    @pytest.mark.parametrize("name", LIVE_SPECIMENS)
    def test_2871_auto_create_still_refuses_every_specimen(self, name):
        """The mint gate reads the RAW name, so the search copy cannot reach it."""
        assert is_derivative_market_name(name) is True

    @pytest.mark.parametrize("name", LIVE_SPECIMENS)
    def test_5031_an_attached_derivative_still_may_not_speak_for_the_blend(self, name):
        """THE REASON ATTACHING THESE IS SAFE AT ALL.

        Linking sets `event_id`, and the 15-minute matcher stamps
        `Event.win_probability_sources` from linked markets. If the class
        recognizer admitted these, an Exact Score price would land in the hero
        — #5031's exact failure (event 15301219 held 0.070 off a `2 - 2` leg).
        """
        from app.utils.live_blend import _class_says_game_winner

        class _M:
            def __init__(self, n):
                self.name = n
                self.external_id = None

        assert _class_says_game_winner(_M(name)) is False, (
            f"{name!r} became admissible as a blend speaker — attaching it "
            "would put a derivative's price on the event hero"
        )

    def test_the_real_moneyline_is_still_admitted(self):
        """The negative above is only meaningful if the positive holds."""
        from app.utils.live_blend import _class_says_game_winner

        class _M:
            name, external_id = FIXTURE, None

        assert _class_says_game_winner(_M()) is True


class TestTheCallSiteIsWiredTheRightWayRound:
    """The whole fix is WHICH matchup goes to WHICH callee.

    Swapping them compiles, passes every test above, and re-opens #2871 — so
    the wiring itself is asserted against the running function.
    """

    @pytest.mark.asyncio
    async def test_search_gets_the_clean_copy_and_link_gets_the_raw_one(
        self, monkeypatch
    ):
        from collections import defaultdict
        from datetime import datetime, timezone

        from app.tasks import prediction_market_matching as task

        market_name = f"{FIXTURE} - Exact Score"
        seen = {}

        async def _fake_find(session, matchup, market, now, **kw):
            seen["search"] = matchup
            return None

        async def _fake_link(session, market, matchup, matched, stats, *a, **kw):
            seen["link"] = matchup

        monkeypatch.setattr(task, "_find_matching_event", _fake_find)
        monkeypatch.setattr(task, "_try_link_market", _fake_link)

        class _Market:
            id = 61019284
            name = market_name
            source = "polymarket"
            category = "championship"
            external_id = "1021305"

        class _Receipt:
            def reject(self, *a, **kw):
                pass

        stats = {"funnel": defaultdict(int)}
        stats["funnel"]["sample_not_game_level"] = []

        await task._run_one_attempt(
            None,
            _Market(),
            _Receipt(),
            stats,
            datetime(2026, 9, 14, tzinfo=timezone.utc),
            [],
            lambda: 9999,
        )

        assert seen["search"].team_b == "UD Las Palmas", (
            "_find_matching_event was handed the polluted matchup — the market "
            "will never verify against the event's away_team_name"
        )
        assert seen["link"].team_b == "UD Las Palmas - Exact Score", (
            "_try_link_market was handed the CLEAN matchup — it forwards this "
            "to _create_event_from_prediction_market, which stamps team_b as "
            "the away team's name. That is #2871's phantom-event hole."
        )
