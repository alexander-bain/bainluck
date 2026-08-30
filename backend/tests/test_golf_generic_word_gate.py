"""Q446 — a generic tournament word is not a sport claim.

THE DEFECT, measured on production 2026-08-29. `GET /api/golf` returned seven
tournaments. Two of them were not golf:

    New Zealand Darts Masters   tour=pga   15 "golfers"
        Simon Whitlock .064 · Ben Robb .064 · Kayden Milne .064 · Haupai Puha .064
        Raymond Smith .064 · James Wade .063   (a PDC darts field)

    Asia Masters 2026           tour=pga    4 "golfers"
        Dplus Challengers .216 · T1 Esports Academy .123 · NS Challengers .058
        KT Challengers .019                    (a League of Legends bracket)

Neither name contains a darts or an esports token, so `_NON_GOLF_RE` could not
refuse them, and `_GOLF_SIGNAL_RE` accepted both on the bare word `masters`.

THE RULE. `masters`, `open`, `classic`, `invitational` and `major` are generic
English tournament words. A market whose ONLY golf signal is one of those must
corroborate golf somewhere our own classifier did not write it — the tour encoded
in the Kalshi ticker, a named golf event, a golf market shape, or one of the two
ambiguous majors via its own disambiguator.

MONOTONE. The gate runs AFTER `_GOLF_SIGNAL_RE`, never instead of it, so it can
only reject. Measured over the full 7,622-row golf-identity population on
2026-08-29: 17 markets rejected, **0 admitted**. `test_gate_never_admits` is that
property as a test rather than as a claim.

Every specimen below is a real production row, with its real id and external_id.
"""

import types

import pytest

from app.routes.golf import (
    _GOLF_SIGNAL_RE,
    _is_golf_market,
)


def _market(name, *, source="polymarket", external_id="0"):
    return types.SimpleNamespace(source=source, external_id=external_id, name=name)


# --------------------------------------------------------------------------
# 1 — the specimens the ship is named after
# --------------------------------------------------------------------------

#: (name, source, external_id) — production rows, measured 2026-08-29.
NOT_GOLF = [
    # id 58416367 — a PDC darts field on the PGA Tour section of /api/golf
    ("New Zealand Darts Masters: Winner", "polymarket", "801410"),
    # id 38277227 — a League of Legends bracket, ditto
    ("Asia Masters 2026 Winner", "polymarket", "601916"),
    # id 35418786 — Valorant. 63 outcomes, every one of them ~0.4996
    ("Most kills on a single map at Masters London 2026?", "polymarket", "584437"),
    # id 55686991 — chess
    ("Chennai Grand Masters Winner", "kalshi", "KXCHESSTOURNAMENT-26CHGM"),
    ("Chess: Will Magnus Carlsen lose any regular game in the 2022 Tata Steel "
     "Masters?", "polymarket", "3679"),
    # ids 58723721 / 58730005 — Philippine Basketball Association
    ("Phoenix Fuel Masters vs Blackwater Bossing", "kalshi",
     "KXPBAGAME-26AUG050515PFMBLE"),
    ("Phoenix Fuel Masters vs Timplados Hotshots", "kalshi",
     "KXPBAGAME-26AUG120730PFMHOT"),
    # id 59718728 — NCAA men's soccer. "The Masters" is a university here
    ("Cal State Northridge Matadors vs The Masters Mustangs", "kalshi",
     "KXNCAAMSOCCERGAME-26AUG27CAL"),
    # id 16757782 — a film
    ('"Masters of the Universe" Rotten Tomatoes score?', "kalshi", "KXRT-MAS"),
    # id 17411169 — "Masters" is a surname
    ("Will Chad Masters / Jace Helton win Team Roping at The American Rodeo 2026 "
     "Championship Weekend?", "polymarket", "0x5bfed39723cb831f774147a6ed"),
    # ids 26898095 / 26899801 / 57771241 — Polymarket's own in-house events
    ("The Polymarket Open: Big John vs. Cheddy", "polymarket", "517340"),
    ("The Polymarket Open: Will Big John cover -3.5 spread?", "polymarket", "520569"),
    ("The Polymarket Classic: Winner", "polymarket", "777018"),
    # id 58015857 — "Open" as an ADJECTIVE, the case `_is_the_open` was written for
    ("Will Anthropic sign the Open Weights and American AI Leadership letter?",
     "kalshi", "KXCOMPANYACTIONANTH-27"),
    # id 10607400 — a press-conference word market that happens to name the winner
    ("What will Masters winner say during the Champion’s Press Conference?",
     "kalshi", "KXPERSONMENTION-26APR12"),
]


@pytest.mark.parametrize("name,source,external_id", NOT_GOLF)
def test_generic_word_alone_does_not_make_a_market_golf(name, source, external_id):
    assert _is_golf_market(_market(name, source=source, external_id=external_id)) is False


def test_the_two_specimens_reach_the_gate_rather_than_the_blocklist():
    """RED-FIRST ANCHOR: both offenders pass every check that existed before Q446.

    Without this the suite could go green on a blocklist edit, which is the fix
    this queue's comment argues against. If either name starts matching
    `_NON_GOLF_RE`, that is a different fix and this file should be re-read.
    """
    for name in ("New Zealand Darts Masters: Winner", "Asia Masters 2026 Winner"):
        assert _GOLF_SIGNAL_RE.search(name), "the old allowlist accepted this"


# --------------------------------------------------------------------------
# 2 — the controls. Real golf whose name says only a generic word.
# --------------------------------------------------------------------------

IS_GOLF = [
    # id 59759220 — real DP World Tour golf. Survives on the KALSHI TICKER alone;
    # its name ("Omega European Masters Winner") is weak-only. The first cut of
    # this rule dropped it, which is why the ticker arm exists.
    ("Omega European Masters Winner", "kalshi", "KXDPWORLDTOUR-OMEM26"),
    # ids 59172993-5 — real LPGA golf, name says only "Open"
    ("CPKC Women's Open End of Round 2 Leader", "kalshi", "KXLPGAR2LEAD-CPKWO26"),
    # id 59173004 — real PGA Champions Tour golf, name says only "Classic"
    ("Rogers Charity Classic End of Round 1 Leader", "kalshi",
     "KXCHAMPTOURR1LEAD-ROCC26"),
    # id 8432750 — real Korn Ferry Tour golf
    ("LECOM Suncoast Classic Winner", "kalshi", "KXKFTOUR-LESC26"),
    # id 56947477 — real PGA Tour golf. Survives on the MARKET SHAPE ("albatross")
    ("3M Open: Albatross?", "polymarket", "741504"),
    # id 16631195 — real golf. Survives on the market shape, not on "Classic"
    ("Will Zach Bauchou finish in the Top 5 at the 2026 ONEflight Myrtle Beach "
     "Classic?", "polymarket", "0xc37ddc884e36dc43d9c04cf3a5"),
    # id 38587904 — the golf U.S. Open (last polled 2026-06-18, the golf window)
    ("U.S. Open: First Time Winner?", "polymarket", "602824"),
    # id 34493720 — Augusta. `_is_the_masters` will NOT vouch for this one, because
    # "us" is not one of the two words it allows in front of `Masters`; the full
    # event name is what carries it.
    ("Will Tiger Woods play in the 2022 US Masters Tournament?", "polymarket", "3099"),
    # The unambiguous majors, untouched by any of this
    ("The Masters Winner", "kalshi", "KXPGATOUR-MAS26"),
    ("The Open Championship Winner", "polymarket", "12345"),
]


@pytest.mark.parametrize("name,source,external_id", IS_GOLF)
def test_real_golf_with_only_a_generic_word_survives(name, source, external_id):
    assert _is_golf_market(_market(name, source=source, external_id=external_id)) is True


# --------------------------------------------------------------------------
# 3 — the monotonicity property itself
# --------------------------------------------------------------------------


def test_gate_never_admits():
    """Anything `_GOLF_SIGNAL_RE` refuses, `_is_golf_market` still refuses.

    The property that makes this change safe to ship without re-auditing the
    completed-tournament path: it cannot put a market on the golf page that is not
    there today. An earlier cut of this fix promoted "finish in the top N" into the
    outer allowlist and admitted 2,197 markets; this test is what caught it.
    """
    names = [n for n, _, _ in NOT_GOLF + IS_GOLF] + [
        "Cadillac Championship Winner",
        "Will Jordan Spieth finish in the Top 10 at the 2026 Cadillac Championship?",
        "Wimbledon Winner",
        "Some Market With No Signal At All",
    ]
    for name in names:
        for source, ext in (("kalshi", "KXFOO-1"), ("polymarket", "999")):
            market = _market(name, source=source, external_id=ext)
            if not _GOLF_SIGNAL_RE.search(name):
                assert _is_golf_market(market) is False, (
                    f"{name!r} has no golf signal but the gate admitted it"
                )


def test_datagolf_and_odds_api_are_untouched():
    """Both bypass the name rules entirely and must keep doing so."""
    assert _is_golf_market(
        _market("New Zealand Darts Masters: Winner", source="datagolf", external_id="x")
    ) is True
    assert _is_golf_market(
        _market("Anything At All", source="odds_api", external_id="golf_pga_championship")
    ) is True
    assert _is_golf_market(
        _market("Anything At All", source="odds_api", external_id="tennis_atp")
    ) is False
