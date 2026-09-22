"""#2127 — BTTS gets a vocabulary, and the ticker is NOT allowed to supply it.

The capture census tripped on `soccer_usa_mls/other`: the shared classifier had
no both-teams-to-score vocabulary, so the Kalshi ": BTTS" suffix fell through to
`other` while the Polymarket ": Both Teams to Score" suffix was swallowed by the
player-prop "to score" arm (frozen as the `soccer-btts` known mismatch). Both are
a both-sides game derivative -> `team_prop`.

🔴 WHY THERE IS NO TICKER ARM, AND WHY THAT IS THE HALF WORTH GUARDING.
The obvious companion to the name arm is a ticker arm mirroring the spread/total
one immediately above the moneyline catch (`"btts" in external_id ->
team_prop`). It is measured WRONG. `btts` is not a series token; it is a
substring that real GAME tickers hit inside their trailing TEAM-CODE pair. On
production 2026-09-22, of 10,833 Kalshi rows whose ticker contains "btts":

  * 10,830 also carry BTTS in the NAME  -> the name arm already has them;
  *      3 do not, and all three are basketball MONEYLINES whose team pair ends
         in those letters ("… vs Turk Telekom", `KXBSLGAME-…MBBTTS`).

So a ticker arm buys zero genuine BTTS rows and costs three real game winners
their `moneyline` class. That class is not cosmetic — FOUR consumers key on the
exact string "moneyline", and all three of those rows are `resolved` and pass
`feeds_win_prob_blend`. The name arm carries none of that risk: 34,865 rows name
BTTS and 0 of them sit on a `*GAME-` ticker.

The consumer tests below are the scope guards: they pin the `moneyline` boundary
in both directions — the BTTS rows never cross it (so the move is inert for
settlement and the blend) and the basketball rows never lose it.
"""
import pytest

from app.utils.game_market_class import classify_game_market_class as classify

# Verbatim production rows (2026-09-22), not invented shapes.
KALSHI_BTTS = ("Agropecuario vs Salta: BTTS", "KXARGNACBBTTS-26SEP20CAAGYT")
KALSHI_1H_BTTS = (
    "Venados vs Tepatitlan: First Half BTTS",
    "KXLIGAEXP1HBTTS-26SEP12VDSTEP",
)
POLYMARKET_BTTS = ("LA Galaxy vs. Seattle Sounders: Both Teams to Score", "0xabc124")

#: The three production rows whose TICKER contains "btts" and whose name does
#: not — every one a basketball game winner, not a BTTS market.
TEAM_CODE_COLLISIONS = [
    ("Mersin Buyuksehir Belediyesi vs Turk Telekom", "KXBSLGAME-26MAR220830MBBTTS"),
    ("JL Bourg Basket vs Turk Telekom", "KXEUROCUPGAME-26APR031300JLBTTS"),
    (
        "Merkezefendi Belediyesi Denizli Basket vs Turk Telekom",
        "KXBSLGAME-26APR181100YMBTTS",
    ),
]


class _M:
    """The two attributes every consumer under test reads off a market."""

    def __init__(self, name, external_id=None, source="kalshi"):
        self.name = name
        self.external_id = external_id
        self.source = source


# ── The ship: BTTS leaves `other` and `player_prop` ──────────────────────────


def test_kalshi_btts_suffix_is_team_prop_not_other():
    assert classify(*KALSHI_BTTS, "soccer_usa_mls") == "team_prop"


def test_kalshi_first_half_btts_is_team_prop():
    # Coarse class only; period scope is the consumers' job, not this module's.
    assert classify(*KALSHI_1H_BTTS, "soccer_usa_mls") == "team_prop"


def test_polymarket_btts_suffix_is_team_prop_not_player_prop():
    assert classify(*POLYMARKET_BTTS, "soccer_usa_mls") == "team_prop"


def test_spelled_out_question_phrasing_is_also_team_prop():
    assert (
        classify("Will both teams score in the LA Galaxy-Seattle game?", None, None)
        == "team_prop"
    )


def test_real_player_score_props_are_not_swallowed():
    # The name arm sits ahead of `_PLAYER_PROP_RE`, so it must not be greedy.
    assert classify("Lionel Messi to score", None, "soccer_usa_mls") == "player_prop"
    assert (
        classify("LA Galaxy vs Seattle: Messi anytime goalscorer", None, None)
        == "player_prop"
    )


# ── The scope guard: the ticker may never decide BTTS ────────────────────────


@pytest.mark.parametrize("name,ticker", TEAM_CODE_COLLISIONS)
def test_btts_inside_a_team_code_never_costs_a_game_winner_its_moneyline(name, ticker):
    assert classify(name, ticker, "basketball_other") == "moneyline"


def test_the_ticker_is_not_consulted_for_btts_at_all():
    """The strawman: identical names, one ticker carrying the letters.

    A ticker arm passes every test above except this one, which is why it is
    written as a difference rather than as a value.
    """
    name = "Mersin Buyuksehir Belediyesi vs Turk Telekom"
    assert classify(name, "KXBSLGAME-26MAR220830MBBTTS") == classify(
        name, "KXBSLGAME-26MAR220830MBTTX"
    )


def test_the_sibling_ticker_arms_still_decide_their_own_kinds():
    """The precedent this change declines to follow still holds for spread/total."""
    bare = "LA Galaxy at Seattle Sounders"
    assert classify(bare, "KXMLSGAME-26MAR01-LA-SEA", "soccer_usa_mls") == "moneyline"
    assert classify(bare, "KXMLSSPREAD-26MAR01-LA-SEA", "soccer_usa_mls") == "spread"
    assert classify(bare, "KXMLSTOTAL-26MAR01-LA-SEA", "soccer_usa_mls") == "total"


# ── Consumer boundary: the four gates that key on the string "moneyline" ─────


def test_live_blend_speaker_eligibility_is_unmoved():
    """`_class_says_game_winner` decides whether a row may speak the win prob."""
    from app.utils.live_blend import _class_says_game_winner

    # BTTS was never a speaker (it was `other`/`player_prop`) and still is not.
    assert _class_says_game_winner(_M(*KALSHI_BTTS)) is False
    assert _class_says_game_winner(_M(*POLYMARKET_BTTS, source="polymarket")) is False
    # …and the collision rows keep the eligibility they have today.
    for name, ticker in TEAM_CODE_COLLISIONS:
        assert _class_says_game_winner(_M(name, ticker)) is True, name


def test_the_blend_admission_ticker_rule_is_untouched():
    """`feeds_win_prob_blend` is a ticker rule; the classifier cannot move it."""
    from app.utils.prediction_market_matching import feeds_win_prob_blend

    for _, ticker in TEAM_CODE_COLLISIONS:
        assert feeds_win_prob_blend(ticker) is True, ticker
    assert feeds_win_prob_blend(KALSHI_BTTS[1]) is False


def test_venue_settlement_still_reads_the_collision_rows_and_still_skips_btts():
    """`choose_settled_winner` admits a row only when its class is `moneyline`."""
    from app.utils.venue_settlement import choose_settled_winner

    name, ticker = TEAM_CODE_COLLISIONS[0]
    assert (
        choose_settled_winner([(name, ticker, "Turk Telekom")], "Mersin", "Turk Telekom")
        is not None
    )
    # A BTTS row grades Yes/No and must never be read as a match verdict.
    assert (
        choose_settled_winner(
            [(KALSHI_BTTS[0], KALSHI_BTTS[1], "Yes")], "Agropecuario", "Salta"
        )
        is None
    )


def test_the_settlement_gate_still_ends_the_match_on_a_collision_row():
    """espn_sync feeds this the classifier's answer; only `moneyline` ends it."""
    from app.utils.event_completion import venue_settlement_ends_the_match

    name, ticker = TEAM_CODE_COLLISIONS[0]
    assert venue_settlement_ends_the_match(
        classify(name, ticker), "resolved", "api_settlement", True
    ) is True
    assert venue_settlement_ends_the_match(
        classify(*KALSHI_BTTS), "resolved", "api_settlement", True
    ) is False


def test_the_polymarket_refresh_budget_membership_is_unmoved():
    """`_is_headline` admits moneyline|spread|total; BTTS was never in it."""
    for probe in (KALSHI_BTTS, POLYMARKET_BTTS, KALSHI_1H_BTTS):
        assert classify(*probe) not in ("moneyline", "spread", "total")
    for name, ticker in TEAM_CODE_COLLISIONS:
        assert classify(name, ticker) in ("moneyline", "spread", "total")


def test_content_understanding_persists_the_new_type_without_moving_agreement():
    """`semantic_type` is STORED, so it is a consumer even when no branch reads it."""
    from app.utils.content_understanding import build_content_understanding

    btts = build_content_understanding(
        name=KALSHI_BTTS[0], external_id=KALSHI_BTTS[1], sports_market_type="btts"
    )
    assert btts["semantic_type"] == "team_prop"
    # Neither side calls it a winner, so the venue agreement is unchanged.
    assert btts["agreement"] == "corroborated"

    name, ticker = TEAM_CODE_COLLISIONS[0]
    winner = build_content_understanding(
        name=name, external_id=ticker, sports_market_type="moneyline"
    )
    assert winner["semantic_type"] == "moneyline"
    assert winner["agreement"] == "corroborated"
