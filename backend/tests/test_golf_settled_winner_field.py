"""#225 Item 1 & 2 — the settled-tournament winner field.

Guards the class of bug Alex flagged on the settled The Open page:
  * the hero crowned an arbitrary golfer (or a settled prop) instead of the
    is_winner champion, because the field was pooled from every market type and
    pinned at 0.99 (gotcha #33 stale placement prices);
  * out-of-field names (the "Tiger Woods was a potential round leader" class)
    surfaced because the DataGolf field wasn't applied on settled pages.

Tests the pure assembler `_assemble_completed_winner_field`.
"""

from app.routes.golf import _assemble_completed_winner_field


class _Outcome:
    def __init__(self, name, cur=None, opening=None, cal=None, is_winner=False, american=None):
        self.name = name
        self.current_probability = cur
        self.opening_probability = opening
        self.calibration_probability = cal
        self.is_winner = is_winner
        self.current_american_odds = american


class _Market:
    def __init__(self, mid, name, source, outcomes):
        self.id = mid
        self.name = name
        self.source = source
        self.outcomes = outcomes


def _open_field(names, winner=None, source="datagolf"):
    """A ≥20-name winner market with opening lines but None current price (settled,
    gotcha #33). The winner carries is_winner even though its price is None."""
    return [
        _Outcome(n, cur=None, opening=0.05, is_winner=(n == winner))
        for n in names
    ]


FIELD = [f"Golfer {i:02d}" for i in range(25)]


def test_champion_crowned_from_is_winner_not_price():
    winner_mkt = _Market(
        1, "The Open Championship Winner", "datagolf", _open_field(FIELD, winner="Golfer 07")
    )
    golfers, *_ = _assemble_completed_winner_field([winner_mkt])
    champ = next(g for g in golfers if g["won"])
    assert champ["name"] == "Golfer 07"
    assert golfers[0]["name"] == "Golfer 07"  # champion sorts first
    assert golfers[0]["rank"] == 1
    # Only the graded winner is crowned.
    assert sum(1 for g in golfers if g.get("won")) == 1


def test_makecut_099_prices_never_pollute_the_field():
    # A settled Make-Cut market where the whole made-cut field resolved YES≈0.99.
    winner_mkt = _Market(
        1, "The Open Championship Winner", "datagolf", _open_field(FIELD, winner="Golfer 03")
    )
    makecut = _Market(
        2,
        "The Open Championship: To Make the Cut",
        "kalshi",
        [_Outcome(n, cur=0.99) for n in FIELD],
    )
    golfers, *_ = _assemble_completed_winner_field([winner_mkt, makecut])
    # No golfer should carry the 0.99 make-cut price as their win probability.
    assert all((g["probability"] or 0) < 0.9 for g in golfers), [
        (g["name"], g["probability"]) for g in golfers
    ]
    assert next(g for g in golfers if g["won"])["name"] == "Golfer 03"


def test_out_of_field_kalshi_name_dropped():
    # DataGolf field of 25 real entrants; Kalshi adds a speculative name (Tiger).
    dg = _Market(1, "The Open Championship - Winner", "datagolf", _open_field(FIELD, winner="Golfer 01"))
    kalshi = _Market(
        2,
        "The Open Championship Winner",
        "kalshi",
        [_Outcome("Tiger Woods", opening=0.02)] + [_Outcome(n, opening=0.03) for n in FIELD[:5]],
    )
    golfers, *_ = _assemble_completed_winner_field([dg, kalshi])
    names = {g["name"] for g in golfers}
    assert "Tiger Woods" not in names
    assert "Golfer 01" in names


def test_graded_winner_kept_even_if_outside_datagolf_field():
    # Champion graded only on the Kalshi market, absent from DataGolf's field —
    # must never be dropped by the field filter.
    dg = _Market(1, "The Open Championship - Winner", "datagolf", _open_field(FIELD))
    kalshi = _Market(
        2,
        "The Open Championship Winner",
        "kalshi",
        [_Outcome("Surprise Winner", opening=0.01, is_winner=True)],
    )
    golfers, *_ = _assemble_completed_winner_field([dg, kalshi])
    champ = next(g for g in golfers if g["won"])
    assert champ["name"] == "Surprise Winner"


def test_market_sources_collected_for_field_filter():
    dg = _Market(1, "The Open Championship - Winner", "datagolf", _open_field(FIELD, winner="Golfer 02"))
    kalshi = _Market(2, "The Open Championship Winner", "kalshi", [_Outcome("Golfer 02", opening=0.1)])
    _, market_ids, market_names, market_sources = _assemble_completed_winner_field([dg, kalshi])
    assert market_ids == [1, 2]
    assert "datagolf" in market_sources  # activates apply_field_filter downstream
    assert "kalshi" in market_sources


def test_placement_only_tournament_falls_back_not_empty():
    # No winner-type market at all — must not return an empty field.
    makecut = _Market(
        1,
        "The Open Championship: To Make the Cut",
        "kalshi",
        [_Outcome(n, cur=0.6) for n in FIELD],
    )
    golfers, *_ = _assemble_completed_winner_field([makecut])
    assert len(golfers) == len(FIELD)


def test_yes_no_outcomes_excluded():
    mkt = _Market(
        1,
        "The Open Championship Winner",
        "datagolf",
        _open_field(FIELD, winner="Golfer 00") + [_Outcome("Yes", cur=0.5), _Outcome("No", cur=0.5)],
    )
    golfers, *_ = _assemble_completed_winner_field([mkt])
    names = {g["name"] for g in golfers}
    assert "Yes" not in names and "No" not in names
