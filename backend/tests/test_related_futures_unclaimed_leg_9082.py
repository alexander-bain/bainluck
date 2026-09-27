"""#9082 — a `Tie` is never printed as one club's chance in Bigger Picture.

WHAT A READER SAW. `/events/14870012` (Clemson v Miami, Oct 3, pregame), 390px,
production 2026-09-27 06:50Z. Bigger Picture → Game props drew two groups headed
"1ST HALF WINNER (1)": **"Tie 1st Half" 6%** in Clemson's half, "Miami (FL) wins
1st Half" 77% in Miami's. Market `62398698` (`KXNCAAF1H-26OCT03MIACLEM`) stores
MIA .765 / CLEM .155 / TIE .055, and Clemson's own leg was nowhere.

THE MECHANISM, read off production rather than guessed. The `-CLEM` leg's ticker
attributes it to Clemson correctly. `/api/futures/62398698` then refuses its price
(`prices_withheld: 1`, `probability: null`), so #9008 drops it from the rail —
correctly, the rail agrees with the market's own page. The `Tie` names neither
club; it reached a side only because the market TITLE names both, and "prefer
home" put it under Clemson. With Clemson's leg gone it stood there alone.

The specimen rows below are the served payload's own ids and prices.

CONTROLS, because a re-siding rule's failure is moving something it was never
meant to move:

  * `test_a_complete_three_way_is_unchanged` — every leg priced: the page keeps
    today's layout exactly.
  * `test_a_market_no_club_claims_is_untouched` — a game prop whose legs are all
    `Over`/`Under` has ONLY its title for attribution; nothing to align with.
  * `test_a_club_claimed_leg_is_never_moved` — only title-placed legs move.
"""

from app.routes.events import _side_unclaimed_matchup_legs

MARKET = 62398698
NAME = "Miami (FL) vs Clemson: 1st Half Winner"
MIA, CLEM, TIE = 235771640, 235771641, 235771642


def _row(outcome_id, outcome_name, probability, market_id=MARKET, market_name=NAME):
    return {
        "market_id": market_id,
        "market_name": market_name,
        "outcome_id": outcome_id,
        "outcome_name": outcome_name,
        "probability": probability,
    }


def _ids(rows):
    return [r["outcome_id"] for r in rows]


def test_the_photographed_tie_leaves_clemsons_half_for_miamis():
    # As served after #9008 dropped the refused `-CLEM` leg (home = Clemson).
    home = [_row(TIE, "Tie 1st Half", 0.055)]
    away = [_row(MIA, "Miami (FL) wins 1st Half", 0.765)]

    kept_home, kept_away = _side_unclaimed_matchup_legs(
        home, away, unclaimed_leg_ids={TIE}, team_leg_market_ids={MARKET}
    )

    assert _ids(kept_home) == [], "the Tie is still printed as Clemson's chance"
    assert _ids(kept_away) == [MIA, TIE], "the Tie must stand beside Miami's leg"


def test_a_complete_three_way_is_unchanged():
    home = [_row(CLEM, "Clemson wins 1st Half", 0.155), _row(TIE, "Tie 1st Half", 0.055)]
    away = [_row(MIA, "Miami (FL) wins 1st Half", 0.765)]

    kept_home, kept_away = _side_unclaimed_matchup_legs(
        home, away, unclaimed_leg_ids={TIE}, team_leg_market_ids={MARKET}
    )

    assert _ids(kept_home) == [CLEM, TIE]
    assert _ids(kept_away) == [MIA]


def test_home_club_leg_alone_keeps_the_tie_at_home():
    # Miami's leg refused instead: the Tie already stands beside Clemson's.
    home = [_row(CLEM, "Clemson wins 1st Half", 0.155), _row(TIE, "Tie 1st Half", 0.055)]

    kept_home, kept_away = _side_unclaimed_matchup_legs(
        home, [], unclaimed_leg_ids={TIE}, team_leg_market_ids={MARKET}
    )

    assert _ids(kept_home) == [CLEM, TIE]
    assert kept_away == []


def test_no_club_leg_left_means_no_bare_tie():
    # Both club legs refused: a lone "Tie 6%" answers nothing a reader can see.
    home = [_row(TIE, "Tie 1st Half", 0.055)]

    kept_home, kept_away = _side_unclaimed_matchup_legs(
        home, [], unclaimed_leg_ids={TIE}, team_leg_market_ids={MARKET}
    )

    assert kept_home == [] and kept_away == []


def test_a_market_no_club_claims_is_untouched():
    # Title-only attribution with no club leg ever admitted: nothing to align to.
    rebounds = "Boston at Golden State: Rebounds"
    home = [
        _row(1, "Over 218.5", 0.52, market_id=77, market_name=rebounds),
        _row(2, "Under 218.5", 0.48, market_id=77, market_name=rebounds),
    ]

    kept_home, kept_away = _side_unclaimed_matchup_legs(
        home, [], unclaimed_leg_ids={1, 2}, team_leg_market_ids=set()
    )

    assert _ids(kept_home) == [1, 2]
    assert kept_away == []


def test_a_club_claimed_leg_is_never_moved():
    # The market's only surviving club leg is away; a DIFFERENT market's club-
    # claimed home row must stay where its club put it.
    other = _row(9, "Clemson Over 24.5", 0.4, market_id=88, market_name="Clemson team total")
    home = [other, _row(TIE, "Tie 1st Half", 0.055)]
    away = [_row(MIA, "Miami (FL) wins 1st Half", 0.765)]

    kept_home, kept_away = _side_unclaimed_matchup_legs(
        home, away, unclaimed_leg_ids={TIE}, team_leg_market_ids={MARKET, 88}
    )

    assert _ids(kept_home) == [9]
    assert _ids(kept_away) == [MIA, TIE]


def test_nothing_unclaimed_returns_the_lists_as_given():
    home = [_row(CLEM, "Clemson wins 1st Half", 0.155)]
    away = [_row(MIA, "Miami (FL) wins 1st Half", 0.765)]

    kept_home, kept_away = _side_unclaimed_matchup_legs(
        home, away, unclaimed_leg_ids=set(), team_leg_market_ids={MARKET}
    )

    assert kept_home is home and kept_away is away


def test_the_build_sides_unclaimed_legs_after_the_9008_drop_and_before_the_fold():
    # Order is the whole fix: before the #9008 drop the refused club leg still
    # anchors the Tie at home; after the #4646 fold / merges a leg can speak for
    # a market it did not come from.
    import inspect

    from app.routes import events

    src = inspect.getsource(events._build_related_futures)
    drop = src.index("rail_withheld = await _related_futures_withheld_ids")
    side = src.index("_side_unclaimed_matchup_legs(")
    fold = src.index("_fold_event_match_winner_futures(")
    assert drop < side < fold


def test_the_build_records_which_legs_only_the_title_placed():
    # The helper is inert unless the loop feeds it: `claimed_by_a_club` must be
    # taken BEFORE the market-name fallback, and both sets filled at append time.
    import inspect

    from app.routes import events

    src = inspect.getsource(events._build_related_futures)
    claimed = src.index("claimed_by_a_club = is_home or is_away")
    fallback = src.index("# Fall back to name matching on MARKET name")
    assert claimed < fallback
    append = src.index("row_markets[market.id] = market")
    tail = src[append : append + 400]
    assert "team_leg_market_ids.add(market.id)" in tail
    assert "unclaimed_leg_ids.add(outcome.id)" in tail
