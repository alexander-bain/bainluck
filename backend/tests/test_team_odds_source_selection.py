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
