"""#7107 — a complete field stops being withheld for being wider than the fixture.

WHAT WENT WRONG, AND IT IS A PREMISE AND NOT A LINE OF CODE. #7068 carried door
one's completeness test onto `/related-futures` verbatim — the count of rows the
page DREW against `venue_leg_count`. That test is sound on door one, which draws
a game's own markets: every stored leg reaches the page, so a short render means
a short field.

It is not sound here. This door asks *which futures are relevant to these two
teams* and selects outcomes by `team_id`, by the outcome naming a team, or by the
MARKET naming one. An 82-nation World Cup field can never render more than the
two nations playing. So `rendered < declared` is true of every tournament-wide
market by construction, whatever the state of our data, and the rule withheld
them all.

THE COST ON PRODUCTION, 2026-09-19. `/api/events/15195325/related-futures`
(Germany v Greece) went from 12 Bigger Picture rows to 4 — corner markets and one
unpriced row — having dropped "Germany to win Euro 2028" (30 legs stored of 30),
the 2030 World Cup (82 of 82), the 2027 Women's World Cup (32 of 32) and the
Champions League (16 of 16). Across the eight banked payloads: 252 rows -> 110,
where 159 is right.

THE REPAIR IS A CHANGE OF BASIS, NOT OF PREDICATE: the same `venue_leg_count`,
asked about the legs we HOLD rather than the legs this door chose to draw. On
the banked corpus that splits the 54 judgeable markets with no overlap — 26 hold
the venue's whole field and return, 28 are genuinely short and stay withheld.

THE CONTROLS ARE THE POINT OF THIS FILE. A relaxation's characteristic failure
is walking the original ship back, so `test_reported_two_of_seventeen_stays_withheld`
and the part-stored league-winner control both fail against a version that simply
stops withholding. And `test_missing_stored_count_falls_back_to_rendered` pins
the direction of the fallback: absent knowledge, this must behave as it did
before, never more permissively.
"""

from types import SimpleNamespace

from app.routes.events import (
    _judgeable_field_market_ids,
    _withhold_partial_field_futures,
)


def _market(market_id, name, *, declared=None, event_title=None, mex=True):
    meta = {}
    if event_title is not None:
        meta["event_title"] = event_title
    if declared is not None:
        meta["market_count"] = declared
    return SimpleNamespace(
        id=market_id, name=name, mutually_exclusive=mex, market_metadata=meta
    )


def _row(market_id, outcome_name):
    return {"market_id": market_id, "outcome_name": outcome_name}


EURO = "2028 UEFA Euros Champion"
WC = "2030 FIFA World Cup Champion"
EXACT = "Germany vs. Greece - Exact Score"
SWISS = "Swiss Super League: 2026-27 Winner"


def _names(rows):
    return [r["outcome_name"] for r in rows]


# ── The ship ────────────────────────────────────────────────────────────────


def test_one_leg_of_a_complete_thirty_nation_field_survives():
    """The headline: Germany's Euro 2028 price is context, not a field claim.

    30 legs stored of 30 declared. The page draws one because one of the thirty
    nations is playing tonight — that is this door's selection, not a hole in
    the field.
    """
    home = [_row(55674162, "Germany")]
    markets = {55674162: _market(55674162, EURO, declared=30, event_title=EURO)}

    home_out, away_out = _withhold_partial_field_futures(
        home, [], markets, stored_leg_counts={55674162: 30}
    )

    assert _names(home_out) == ["Germany"]
    assert away_out == []


def test_two_legs_of_a_complete_eighty_two_nation_field_survive_across_sides():
    """Both fixture participants, drawn from a field we hold whole — 2 of 82."""
    home = [_row(56775477, "Germany")]
    away = [_row(56775477, "Greece")]
    markets = {56775477: _market(56775477, WC, declared=82, event_title=WC)}

    home_out, away_out = _withhold_partial_field_futures(
        home, away, markets, stored_leg_counts={56775477: 82}
    )

    assert _names(home_out) == ["Germany"]
    assert _names(away_out) == ["Greece"]


def test_a_field_we_hold_whole_survives_however_few_rows_it_draws():
    """The reach is what was wrong, so the guard is stated over the reach.

    One row of a 15-leg field and one row of an 82-leg field are the same shape;
    neither leg count may decide it. A rule reinstated as "exempt when declared
    >= N" passes the 82 case and fails this one.
    """
    markets = {}
    home = []
    for market_id, declared in ((23500, 15), (19529219, 16), (128718, 31), (56775477, 82)):
        name = f"field-{market_id}"
        markets[market_id] = _market(market_id, name, declared=declared, event_title=name)
        home.append(_row(market_id, "the one team playing"))
    stored = {mid: m.market_metadata["market_count"] for mid, m in markets.items()}

    home_out, _ = _withhold_partial_field_futures(home, [], markets, stored_leg_counts=stored)

    assert len(home_out) == 4


# ── Controls: the original ship must not be walked back ─────────────────────


def test_reported_two_of_seventeen_stays_withheld():
    """#7068's own specimen. 2 legs STORED of 17 — short at the source, still gone.

    Fails against any version that stops withholding, and against one that
    keys the exemption on "the door drew fewer rows than the field declares",
    which is true here too.
    """
    home = [_row(61032702, "Germany 3 - 2 Greece"), _row(61032702, "Germany 2 - 1 Greece")]
    markets = {61032702: _market(61032702, EXACT, declared=17, event_title=EXACT)}

    home_out, away_out = _withhold_partial_field_futures(
        home, [], markets, stored_leg_counts={61032702: 2}
    )

    assert home_out == []
    assert away_out == []


def test_a_part_stored_league_winner_is_still_short():
    """The population that makes this a basis change and not a market-type exemption.

    `58867278` Swiss Super League is a league-winner future — the same SHAPE the
    ship reinstates — but we hold 11 legs of 28. It stays withheld, which a rule
    written as "tournament winners are exempt" would get wrong.
    """
    home = [_row(58867278, "Young Boys Bern")]
    markets = {58867278: _market(58867278, SWISS, declared=28, event_title=SWISS)}

    home_out, _ = _withhold_partial_field_futures(
        home, [], markets, stored_leg_counts={58867278: 11}
    )

    assert home_out == []


def test_a_short_field_is_withheld_even_when_every_stored_leg_renders():
    """stored == rendered and both below declared: the honest short field.

    This is the exact-score case at full render (16 stored of 17, all 16 drawn)
    and it is the one a naive "rendered < stored" exemption would let through.
    """
    home = [_row(60298968, f"score {i}") for i in range(16)]
    name = "Angers SCO vs. ES Troyes AC - Exact Score"
    markets = {60298968: _market(60298968, name, declared=17, event_title=name)}

    home_out, _ = _withhold_partial_field_futures(
        home, [], markets, stored_leg_counts={60298968: 16}
    )

    assert home_out == []


# ── The fallback has a direction ────────────────────────────────────────────


def test_missing_stored_count_falls_back_to_rendered():
    """No count for this market ⇒ pre-#7107 behaviour, never something laxer.

    A direct caller passing nothing, or a market absent from the aggregate, must
    land on the stricter of the two bases. `rendered` is never greater than the
    stored count, so this can only withhold more.
    """
    home = [_row(55674162, "Germany")]
    markets = {55674162: _market(55674162, EURO, declared=30, event_title=EURO)}

    assert _withhold_partial_field_futures(home, [], markets) == ([], [])
    assert _withhold_partial_field_futures(
        home, [], markets, stored_leg_counts={}
    ) == ([], [])
    assert _withhold_partial_field_futures(
        home, [], markets, stored_leg_counts={99999: 30}
    ) == ([], [])


def test_a_market_venue_leg_count_refuses_is_never_judged():
    """Unchanged: no `event_title` identity ⇒ the row is not the venue's ladder.

    A stored count must not turn a market the predicate refuses into one it
    judges — that would size an ordinary two-leg moneyline against its parent's
    sibling count.
    """
    home = [_row(777, "Over")]
    markets = {777: _market(777, "Germany vs. Greece: O/U 11.5", declared=40, event_title=None)}

    home_out, _ = _withhold_partial_field_futures(
        home, [], markets, stored_leg_counts={777: 2}
    )

    assert _names(home_out) == ["Over"]


# ── The scoping helper ──────────────────────────────────────────────────────


def test_judgeable_ids_are_only_the_markets_the_predicate_can_size():
    """The count query must not widen to markets whose answer cannot matter."""
    markets = {
        55674162: _market(55674162, EURO, declared=30, event_title=EURO),
        777: _market(777, "Germany vs. Greece: O/U 11.5", declared=40, event_title=None),
        888: _market(888, "a duel", declared=2, event_title="a duel", mex=False),
    }

    assert _judgeable_field_market_ids(markets) == [55674162]


def test_judgeable_ids_are_empty_when_no_field_is_sizeable():
    """A page with nothing to judge issues no query at all."""
    markets = {777: _market(777, "O/U 11.5", declared=40, event_title=None)}

    assert _judgeable_field_market_ids(markets) == []
