"""#237 Item 3 — "Your Teams' Odds" prefers coherent fields over illiquid Kalshi
independent-binary award ladders.

The observed defect: for a roster player (Drake Maye) a team's "Your Teams' Odds"
surfaced illiquid Kalshi independent-binary award/prop markets — fields whose YES
prices sum far past 100% (e.g. "Pro Football Championship MVP?" summing 19.67, a
passing-yards ladder summing 11.51) — which sorted above the team's coherent
odds_api championship field on raw probability and crowded it out. These guards
assert both directions: illiquid Kalshi is suppressed when a coherent alternative
exists, and the coherent field always survives (a followed team is never emptied).
"""

from app.routes.user import (
    _is_illiquid_binary_field,
    _many_winner_series_key,
    _prefer_coherent_team_items,
)


class TestIsIlliquidBinaryField:
    def test_kalshi_overrounded_field_is_illiquid(self):
        # "Pro Football Championship MVP?" field summed 19.67 in production.
        assert _is_illiquid_binary_field("kalshi", 19.67) is True

    def test_kalshi_slightly_over_band_is_illiquid(self):
        assert _is_illiquid_binary_field("kalshi", 1.61) is True

    def test_kalshi_coherent_field_is_not_illiquid(self):
        # A coherent Kalshi field (e.g. a 2-way market summing ~0.99) is fine.
        assert _is_illiquid_binary_field("kalshi", 0.99) is False

    def test_kalshi_at_band_edge_is_not_illiquid(self):
        assert _is_illiquid_binary_field("kalshi", 1.60) is False

    def test_odds_api_is_never_illiquid(self):
        # odds_api fields are single coherent markets — never suppressed.
        assert _is_illiquid_binary_field("odds_api", 19.67) is False

    def test_missing_sum_fails_open(self):
        assert _is_illiquid_binary_field("kalshi", None) is False


class TestPreferCoherentTeamItems:
    def _coherent(self, mid, prob):
        return {"market_id": mid, "probability": prob, "_illiquid_binary": False}

    def _illiquid(self, mid, prob):
        return {"market_id": mid, "probability": prob, "_illiquid_binary": True}

    def test_illiquid_dropped_when_coherent_alternative_exists(self):
        # The Maye case: an illiquid Kalshi MVP ladder outranks the team's coherent
        # odds_api Super Bowl outcome on raw probability, but must be dropped.
        per_team = {
            1: [self._illiquid(479, 0.5), self._coherent(10, 0.08)],
        }
        _prefer_coherent_team_items(per_team)
        surviving = [it["market_id"] for it in per_team[1]]
        assert surviving == [10]  # only the coherent field survives

    def test_coherent_field_always_survives(self):
        per_team = {1: [self._coherent(10, 0.08), self._illiquid(479, 0.5)]}
        _prefer_coherent_team_items(per_team)
        assert any(it["market_id"] == 10 for it in per_team[1])

    def test_team_never_emptied_when_only_illiquid(self):
        # No coherent alternative — keep the illiquid item rather than empty the team.
        per_team = {1: [self._illiquid(479, 0.5), self._illiquid(7595941, 0.38)]}
        _prefer_coherent_team_items(per_team)
        assert len(per_team[1]) == 2

    def test_all_coherent_unchanged(self):
        per_team = {1: [self._coherent(10, 0.4), self._coherent(11, 0.2)]}
        _prefer_coherent_team_items(per_team)
        assert len(per_team[1]) == 2

    def test_private_flag_stripped_from_survivors(self):
        per_team = {
            1: [self._coherent(10, 0.4), self._illiquid(479, 0.5)],
            2: [self._illiquid(479, 0.5)],  # kept (only option)
        }
        _prefer_coherent_team_items(per_team)
        for items in per_team.values():
            for it in items:
                assert "_illiquid_binary" not in it


class TestLiquidLegOnManyWinnerBoard:
    """#10078 — a many-winner board sums to its winner count, not 1. Kalshi's
    College Football Playoff Qualifiers (12 slots) summed 11.30 in production and
    Miami's leg traded 0.83/0.84; every team page dropped it (and every NFL/NBA/NHL
    playoff-qualifier leg) as an "illiquid ladder". #237's specimen, market 479,
    quoted bid 0.00 / ask 1.00 on every leg — that class must stay suppressed."""

    def test_tight_leg_on_playoff_qualifiers_board_is_not_illiquid(self):
        assert _is_illiquid_binary_field("kalshi", 11.30, 0.83, 0.84) is False

    def test_decimal_quotes_as_stored(self):
        from decimal import Decimal

        assert (
            _is_illiquid_binary_field(
                "kalshi", Decimal("11.30"), Decimal("0.8300"), Decimal("0.8400")
            )
            is False
        )

    def test_spread_at_ceiling_is_liquid(self):
        assert _is_illiquid_binary_field("kalshi", 11.30, 0.80, 0.85) is False

    def test_spread_past_ceiling_stays_illiquid(self):
        assert _is_illiquid_binary_field("kalshi", 11.30, 0.80, 0.86) is True

    def test_market_479_unquoted_leg_stays_illiquid(self):
        # bid 0.00 / ask 1.00: no book at all, the 0.50 is a midpoint of nothing.
        assert _is_illiquid_binary_field("kalshi", 19.67, 0.0, 1.0) is True

    def test_missing_bid_stays_illiquid(self):
        assert _is_illiquid_binary_field("kalshi", 11.30, None, 0.84) is True

    def test_missing_ask_stays_illiquid(self):
        assert _is_illiquid_binary_field("kalshi", 11.30, 0.83, None) is True

    def test_crossed_quote_stays_illiquid(self):
        assert _is_illiquid_binary_field("kalshi", 11.30, 0.84, 0.83) is True

    def test_coherent_board_unaffected_by_quote(self):
        assert _is_illiquid_binary_field("kalshi", 0.99, 0.0, 1.0) is False

    def test_playoff_leg_survives_beside_a_coherent_field(self):
        # The page-level effect: the qualifier leg is no longer dropped by
        # _prefer_coherent_team_items when the team also has a coherent field.
        per_team = {
            15264: [
                {
                    "market_id": 227,
                    "probability": 0.835,
                    "_illiquid_binary": _is_illiquid_binary_field(
                        "kalshi", 11.30, 0.83, 0.84
                    ),
                },
                {
                    "market_id": 479,
                    "probability": 0.5,
                    "_illiquid_binary": _is_illiquid_binary_field(
                        "kalshi", 19.67, 0.0, 1.0
                    ),
                },
                {"market_id": 10, "probability": 0.09, "_illiquid_binary": False},
            ]
        }
        _prefer_coherent_team_items(per_team)
        assert [it["market_id"] for it in per_team[15264]] == [227, 10]

    def test_call_site_passes_the_served_legs_quote(self):
        # The rule is only as good as its inputs: the team-futures loop must hand
        # it the outcome's own bid/ask, or every over-sum leg reads "no quote".
        import ast
        import inspect

        import app.routes.user as user_mod

        tree = ast.parse(inspect.getsource(user_mod))
        calls = [
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and getattr(n.func, "id", None) == "_is_illiquid_binary_field"
        ]
        assert len(calls) == 1
        args = [ast.unparse(a) for a in calls[0].args]
        assert args[2:] == [
            "getattr(outcome, 'current_yes_bid', None)",
            "getattr(outcome, 'current_yes_ask', None)",
            "outcome.current_probability",
        ]

    def test_near_certain_liquid_leg_stays_suppressed(self):
        # Miami's "Top 25 Ranked Teams on Oct 11 AP Poll": 0.985, bid 0.97 / ask
        # 1.00, board sum 24.76 — a ladder's bottom rung, eight of them by date.
        assert _is_illiquid_binary_field("kalshi", 24.76, 0.97, 1.0, 0.985) is True
        assert _is_illiquid_binary_field("kalshi", 22.86, 0.96, 0.99, 0.975) is True

    def test_just_under_near_certain_is_served(self):
        assert _is_illiquid_binary_field("kalshi", 11.30, 0.93, 0.96, 0.945) is False

    def test_playoff_leg_with_its_probability_is_served(self):
        assert _is_illiquid_binary_field("kalshi", 11.30, 0.83, 0.84, 0.835) is False


class TestManyWinnerSeriesCap:
    """#10078 — one served over-sum leg per Kalshi series per team. Measured
    2026-10-01: without it one NFL page gains 12 KXNFLFFLEADERTOP fantasy rows and
    Miami six dated KXNCAAFTOPAPRANK poll rows."""

    def test_series_key_for_served_over_sum_leg(self):
        assert (
            _many_winner_series_key("kalshi", "KXNCAAFPLAYOFF-26", 11.30, False)
            == "KXNCAAFPLAYOFF"
        )

    def test_no_key_for_illiquid_leg(self):
        assert _many_winner_series_key("kalshi", "KXNFLSBMVP-26", 19.67, True) is None

    def test_no_key_for_single_winner_board(self):
        # The CFP "#1 Ranked Team" boards sum ~1: never capped by this rule.
        assert _many_winner_series_key("kalshi", "KXNCAAFCFPPOLL-26NOV03", 1.02, False) is None

    def test_no_key_off_kalshi_or_without_ids(self):
        assert _many_winner_series_key("polymarket", "abc-1", 11.3, False) is None
        assert _many_winner_series_key("kalshi", None, 11.3, False) is None
        assert _many_winner_series_key("kalshi", "KXA-1", None, False) is None

    def _item(self, mid, series):
        return {
            "market_id": mid,
            "_illiquid_binary": False,
            "_many_winner_series": series,
        }

    def test_one_leg_per_series_highest_first(self):
        per_team = {
            15264: [
                self._item(1, "KXNCAAFTOPAPRANK"),  # highest-priced, kept
                self._item(227, "KXNCAAFPLAYOFF"),
                self._item(2, "KXNCAAFTOPAPRANK"),
                self._item(10, None),
                self._item(3, "KXNCAAFTOPAPRANK"),
                self._item(11, None),
            ]
        }
        _prefer_coherent_team_items(per_team)
        assert [it["market_id"] for it in per_team[15264]] == [1, 227, 10, 11]
        assert all("_many_winner_series" not in it for it in per_team[15264])

    def test_cap_is_per_team(self):
        per_team = {
            1: [self._item(5, "KXNFLPLAYOFF")],
            2: [self._item(5, "KXNFLPLAYOFF")],
        }
        _prefer_coherent_team_items(per_team)
        assert [len(v) for v in per_team.values()] == [1, 1]

    def test_call_site_keys_the_series_on_the_served_verdict(self):
        # A constant here silently disables the cap (or caps illiquid legs).
        import ast
        import inspect

        import app.routes.user as user_mod

        tree = ast.parse(inspect.getsource(user_mod))
        calls = [
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and getattr(n.func, "id", None) == "_many_winner_series_key"
        ]
        assert len(calls) == 1
        assert [ast.unparse(a) for a in calls[0].args] == [
            "market.source",
            "getattr(market, 'external_id', None)",
            "field_prob_sum",
            "_illiquid",
        ]
