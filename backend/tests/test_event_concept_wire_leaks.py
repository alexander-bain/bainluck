"""L2-118 Item 3: the concept-page competitor payload must never ship odds.

L2-48 thesis: Bain Luck is probability-only. Golf competitors pick up
`american_odds` from the shared tournament builder (routes/golf.py); the concept
envelope strips it at the boundary so no adapter leaks a betting artifact onto
the wire. Guards `strip_competitor_wire_leaks`.
"""

from app.utils.event_concept import strip_competitor_wire_leaks


def test_strips_american_odds_from_competitors():
    envelope = {
        "primary": {
            "kind": "winner_field",
            "competitors": [
                {"name": "Scottie Scheffler", "probability": 0.31, "american_odds": 220},
                {"name": "Rory McIlroy", "probability": 0.14, "american_odds": 600},
            ],
        },
    }
    out = strip_competitor_wire_leaks(envelope)
    for c in out["primary"]["competitors"]:
        assert "american_odds" not in c
    # Probability-only fields survive.
    assert out["primary"]["competitors"][0]["name"] == "Scottie Scheffler"
    assert out["primary"]["competitors"][0]["probability"] == 0.31


def test_returns_same_envelope_for_chaining():
    envelope = {"primary": {"competitors": [{"name": "x", "american_odds": 100}]}}
    assert strip_competitor_wire_leaks(envelope) is envelope


def test_no_competitors_is_noop():
    assert strip_competitor_wire_leaks({"primary": {}}) == {"primary": {}}
    assert strip_competitor_wire_leaks({}) == {}


def test_none_envelope_is_safe():
    assert strip_competitor_wire_leaks(None) is None


def test_tolerates_non_dict_competitor_entries():
    envelope = {"primary": {"competitors": [None, "junk", {"american_odds": 5, "name": "y"}]}}
    out = strip_competitor_wire_leaks(envelope)
    assert "american_odds" not in out["primary"]["competitors"][2]


def test_competitor_without_odds_unchanged():
    envelope = {"primary": {"competitors": [{"name": "z", "probability": 0.5}]}}
    out = strip_competitor_wire_leaks(envelope)
    assert out["primary"]["competitors"][0] == {"name": "z", "probability": 0.5}
