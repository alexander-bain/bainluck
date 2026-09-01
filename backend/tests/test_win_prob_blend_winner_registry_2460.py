"""#2460 — the win-prob blend gate keys on a declared winner-line registry.

The gate used to ask whether a Kalshi ticker's prefix ended in the letters
``game``. That is a spelling test standing in for a semantic one, and it
silently excluded every sport whose winner line is spelled ``…match`` — tennis
above all, where 28,809 linked match-winner markets could never reach the blend
and so every tennis match page drew its Win Probability line with Kalshi
structurally absent (#2444).

These guards pin three things:

1. the sports the old rule dropped are admitted, and the props around them
   still are not;
2. the admitted set for the sports that already worked is BYTE-IDENTICAL to
   what the old rule produced — this fix must not move a single team sport;
3. a sport can no longer drop out of the blend by SILENCE. It drops out only by
   being named in ``SPORTS_WITH_NO_DECLARED_WINNER_LINE`` with a reason.

Honest limit, recorded so nobody reads more into (3) than it carries: the
completeness guard would NOT have caught tennis. ``kxatpgame`` is in the ticker
registry and the old suffix rule admitted it, so ``tennis_atp`` looked covered
while its real winner line (``kxatpmatch``) was dropped. What removes that
failure mode is deleting the heuristic that let a phantom entry masquerade as
coverage — the guard's job is to stop the NEXT sport from dropping silently.
No CI guard can prove a declared prefix is live; that needs a production
census.
"""

import pytest

from app.utils.prediction_market_matching import (
    COMBAT_FIGHT_WINNER_PREFIXES,
    KALSHI_WIN_PROB_WINNER_PREFIXES,
    SPORTS_WITH_NO_DECLARED_WINNER_LINE,
    WINNER_PREFIXES_WITH_NO_SPORT_KEY,
    feeds_win_prob_blend,
)
from app.utils.sport_keys import (
    KALSHI_TICKER_TO_SPORT_KEY,
    get_sport_key_from_ticker,
)


def _tk(prefix: str) -> str:
    """A realistic ticker for a prefix: Kalshi's date-token shape."""
    return f"{prefix.upper()}-26APR04AANDJDUJ"


# ── 1. The sports the old rule dropped ───────────────────────────────────────

# Every one of these is a bare "X vs Y" two-sided winner line, verified against
# production market names before being admitted (#2460).
DROPPED_WINNER_LINES = [
    # tennis — 28,809 of the 29,320 linked markets the old rule dropped
    ("kxatpmatch", "tennis_atp"),
    ("kxwtamatch", "tennis_wta"),
    ("kxatpchallengermatch", "tennis_atp"),
    ("kxwtachallengermatch", "tennis_wta"),
    ("kxitfmatch", "tennis_itf"),
    ("kxitfwmatch", "tennis_itf_w"),
    ("kxatpdoubles", "tennis_atp"),
    ("kxwtadoubles", "tennis_wta"),
    ("kxitfdoubles", "tennis_itf"),
    ("kxitfwdoubles", "tennis_itf_w"),
    ("kxatpchallengerdoubles", "tennis_atp"),
    # the rest of the class
    ("kxt20match", "cricket_t20"),
    ("kxwt20match", "cricket_t20"),
    ("kxcrickettestmatch", "cricket"),
    ("kxrugbynrlmatch", "rugby_nrl"),
    ("kxrugbyeslmatch", "rugby_nrl"),
    ("kxchessmatch", "chess"),
]


@pytest.mark.parametrize("prefix,sport", DROPPED_WINNER_LINES)
def test_winner_lines_the_old_suffix_rule_dropped_are_admitted(prefix, sport):
    assert (
        feeds_win_prob_blend(_tk(prefix)) is True
    ), f"{prefix} is {sport}'s two-sided winner line and must feed the blend"
    # The defect in one assertion: the old rule's question, still answering no.
    assert not prefix.endswith("game"), (
        f"{prefix} would have been admitted by the old suffix rule; it is not "
        f"evidence of this fix"
    )


@pytest.mark.parametrize(
    "prefix",
    [
        # tennis props that share the match's date token
        "kxatpsetwinner",
        "kxwtasetwinner",
        "kxatpanyset",
        "kxwtaanyset",
        "kxatpexactmatch",
        "kxwtaexactmatch",
        "kxatpexactsets",
        "kxatptotalsets",
        "kxatpgamespread",
        "kxatpgametotal",
        "kxatpgspread",
        "kxatpgtotal",
        # a tennis "game" is a scoring unit inside a set, NOT the match
        "kxatpgame",
        "kxwtagame",
        # other sports' props
        "kxt20teamtotal",
        "kxiplsix",
        "kxiplfour",
        "kxucltotal",
        "kxuclspread",
        "kxmlbspread",
        "kxmlbtotal",
        "kxnflspread",
        "kxnbatotal",
        # combat props sharing the card's date token
        "kxufcmof",
        "kxufcrounds",
        "kxufcdistance",
        "kxufcvicround",
        "kxufcmov",
        "kxboxingrounds",
        "kxboxingdistance",
        "kxboxingknockout",
        # esports per-map props (the series winner is kxcs2game / kxlolgame)
        "kxcs2map",
        "kxcs2mapwinner",
        "kxcs2totalmaps",
        "kxlolmap",
        "kxloltotalmaps",
        "kxvalorantmap",
    ],
)
def test_props_are_still_excluded(prefix):
    assert (
        feeds_win_prob_blend(_tk(prefix)) is False
    ), f"{prefix} is a prop and must never write into win_probability_sources"


def test_a_tennis_game_is_not_a_tennis_match():
    """The phantom that made tennis_atp look covered.

    ``kxatpgame`` sits in KALSHI_TICKER_TO_SPORT_KEY and the old suffix rule
    admitted it, which is why a completeness check over the registry would have
    reported tennis as fine. It has zero rows in production. Excluding it is a
    no-op today and correct the day such a market appears.
    """
    for phantom in ("kxatpgame", "kxwtagame"):
        assert phantom in KALSHI_TICKER_TO_SPORT_KEY, (
            f"{phantom} was removed from the ticker registry; this guard's "
            f"premise is gone and it must be rewritten, not deleted"
        )
        assert phantom.endswith("game")  # the old rule said yes
        assert feeds_win_prob_blend(_tk(phantom)) is False  # the registry says no


# ── 2. The sports that already worked must not move ──────────────────────────


def _old_gate(prefix: str) -> bool:
    """The pre-#2460 rule, reproduced verbatim as the regression oracle."""
    return prefix.endswith("game") or prefix in COMBAT_FIGHT_WINNER_PREFIXES


def test_no_team_sport_changes_its_admission():
    """Across every prefix in the ticker registry, the only admission changes
    are ADDITIONS of winner lines plus the two deliberate tennis phantoms.

    This is the guard that makes the fix safe to ship: a registry typo that
    dropped, say, ``kxnflgame`` would fail here rather than silently emptying
    the NFL blend.
    """
    removed, added = set(), set()
    for prefix in KALSHI_TICKER_TO_SPORT_KEY:
        before, after = _old_gate(prefix), feeds_win_prob_blend(_tk(prefix))
        if before and not after:
            removed.add(prefix)
        elif after and not before:
            added.add(prefix)

    assert removed == {
        "kxatpgame",
        "kxwtagame",
    }, f"this fix must only ADD winner lines; it removed {sorted(removed)}"
    # Everything added must be a winner line, never a prop.
    for prefix in added:
        assert prefix in KALSHI_WIN_PROB_WINNER_PREFIXES
        assert prefix.endswith("match") or prefix.endswith(
            "doubles"
        ), f"{prefix} was newly admitted but is not a …match/…doubles winner line"


def test_combat_bout_winners_still_feed_the_blend():
    """``kxboxing`` is the LIVE boxing prefix (299 markets / 225 linked).

    The registry map spells boxing ``kxboxingfight``, which has zero rows.
    Deleting the bare entry to "match the map" would silently remove boxing
    from the blend — the exact class of defect #2460 is about.
    """
    for prefix in COMBAT_FIGHT_WINNER_PREFIXES:
        assert (
            feeds_win_prob_blend(_tk(prefix)) is True
        ), f"{prefix} must feed the blend"
        assert prefix in KALSHI_WIN_PROB_WINNER_PREFIXES
    assert "kxboxing" in COMBAT_FIGHT_WINNER_PREFIXES
    assert feeds_win_prob_blend("KXBOXING-26APR04AANDJDUJ") is True


# ── 3. A sport may not drop out of the blend by silence ──────────────────────


def _sports_with_a_declared_winner_line() -> set:
    resolved = {
        get_sport_key_from_ticker(_tk(prefix))
        for prefix in KALSHI_WIN_PROB_WINNER_PREFIXES
    }
    resolved.discard(None)
    return resolved


def test_every_sport_declares_a_winner_line_or_is_listed_here():
    """THE COMPLETENESS GUARD.

    Add a sport to KALSHI_TICKER_TO_SPORT_KEY without declaring which of its
    tickers is the two-sided winner line and this fails. Before #2460 that
    sport would simply have been absent from every blend, with nothing
    anywhere reporting it.
    """
    uncovered = (
        set(KALSHI_TICKER_TO_SPORT_KEY.values()) - _sports_with_a_declared_winner_line()
    )
    undeclared = uncovered - SPORTS_WITH_NO_DECLARED_WINNER_LINE
    assert not undeclared, (
        f"{sorted(undeclared)} have no winner line in "
        f"KALSHI_WIN_PROB_WINNER_PREFIXES. Either declare the prefix that "
        f"carries the two-sided winner, or add the sport to "
        f"SPORTS_WITH_NO_DECLARED_WINNER_LINE with the reason. A sport must "
        f"never leave the blend by silence (#2460)."
    )


def test_the_exemption_list_has_no_stale_entries():
    """A sport that has GAINED a winner line must leave the exemption list,
    otherwise the list rots into a place where real sports hide."""
    stale = SPORTS_WITH_NO_DECLARED_WINNER_LINE & _sports_with_a_declared_winner_line()
    assert not stale, (
        f"{sorted(stale)} now declare a winner line and must be removed from "
        f"SPORTS_WITH_NO_DECLARED_WINNER_LINE"
    )


def test_unmapped_winner_prefixes_are_declared_not_discovered():
    """Winner prefixes that resolve to no sport key are listed explicitly.

    They are admitted on the strength of their market names being bare
    "X vs Y" lines. Keeping the list explicit stops the completeness guard
    above from being quietly satisfied by prefixes nobody has classified.
    """
    unmapped = {
        prefix
        for prefix in KALSHI_WIN_PROB_WINNER_PREFIXES
        if get_sport_key_from_ticker(_tk(prefix)) is None
    }
    assert unmapped == WINNER_PREFIXES_WITH_NO_SPORT_KEY, (
        f"undeclared: {sorted(unmapped - WINNER_PREFIXES_WITH_NO_SPORT_KEY)}, "
        f"stale: {sorted(WINNER_PREFIXES_WITH_NO_SPORT_KEY - unmapped)}"
    )


def test_the_gate_is_a_registry_lookup_not_a_spelling_rule():
    """The regression that would undo #2460.

    A prefix ending in ``game`` that is NOT in the registry must be refused. If
    someone reinstates ``endswith("game")`` this fails.
    """
    assert "kxfakesportgame" not in KALSHI_WIN_PROB_WINNER_PREFIXES
    assert feeds_win_prob_blend("KXFAKESPORTGAME-26APR04XX") is False
    assert feeds_win_prob_blend("KXNBAGAME-26APR04XX") is True


@pytest.mark.parametrize("bad", [None, "", "-", "NOTAKALSHITICKER", "kx"])
def test_malformed_tickers_are_refused(bad):
    assert feeds_win_prob_blend(bad) is False
