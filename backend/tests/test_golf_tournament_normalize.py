"""#950: golf tournament normalization — de-obfuscate scrambled major names so
Polymarket events merge onto the canonical major card instead of orphaning."""

from app.routes.golf import _normalize_tournament, _fix_scrambled_major


def test_scrambled_us_open_normalizes_to_us_open():
    # Polymarket's "uptspt Open" obfuscation must resolve to the same key as
    # the real name → cross-source merge onto one us_open card.
    assert _normalize_tournament("2026 uptspt Open First Round Leader") == "us_open"
    assert _normalize_tournament("uptspt Open: To Make the Cut") == "us_open"


def test_clean_us_open_names_still_normalize():
    # Kalshi + Polymarket clean names share the us_open key (regression guard).
    assert _normalize_tournament("2026 U.S. Open: Winner Nationality") == "us_open"
    assert _normalize_tournament("PGA Tour: U.S. Open Winner") == "us_open"
    assert _normalize_tournament("US Open Winner") == "us_open"


def test_fix_scrambled_major_is_noop_for_clean_names():
    # Must not mangle normal names (other majors unaffected).
    for nm in ["2026 PGA Championship Winner", "The Masters Top 5", "U.S. Open"]:
        assert _fix_scrambled_major(nm) == nm


def test_fix_scrambled_major_preserves_surrounding_text():
    out = _fix_scrambled_major("2026 uptspt Open First Round Leader")
    assert "U.S. Open" in out and out.startswith("2026 ") and out.endswith("Leader")
