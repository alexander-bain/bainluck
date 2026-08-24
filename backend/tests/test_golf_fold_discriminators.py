"""UX-P126 / F4 — golf requires a tour/gender/level discriminator before folding
two markets onto one tournament card.

THE LIVE SPECIMEN (production, 2026-08-24). `_normalize_tournament`'s Priority-1
patterns are SUBSTRING matches, so key `masters` claimed 17 open markets spanning
six distinct real-world events: the Augusta major, the Husqvarna British Masters
(DP World Tour, 6 markets), the same event as Polymarket's "DP World Tour: British
Masters" (7), Asia Masters 2026, Valorant's Masters London 2026, and the New Zealand
Darts Masters.

The user-visible cost was not a messy card — it was a MISSING one. The folded key
inherits Augusta's DataGolf schedule entry (end_date 2026-04-12, status
"completed"), so `_filter_stale_tournaments` dropped the whole group. On 2026-08-24
`/api/golf` served five tournaments and the British Masters — teeing off in three
days with 13 open markets across three sources — was absent entirely, while the TOUR
Championship (identical Aug-27..30 dates) rendered.

Every test here asserts BOTH directions (gotcha #43): the contaminant is refused AND
the real event still folds.
"""

import pytest

from app.routes.golf import (
    MAJOR_TOURNAMENTS,
    _WOMENS_RE,
    _declared_tour,
    _is_the_masters,
    _is_the_open,
    _normalize_tournament,
    _strip_market_chrome,
)


# ---------------------------------------------------------------------------
# LEVEL — "Masters"
# ---------------------------------------------------------------------------

MASTERS_CONTAMINANTS = [
    "Husqvarna British Masters hosted by Sir Nick Faldo - Winner",
    "Husqvarna British Masters hosted by Sir Nick Faldo Winner",
    "DP World Tour: British Masters Winner",
    "DP World Tour: British Masters First Round Leader",
    "Asia Masters 2026 Winner",
    "Most kills on a single map at Masters London 2026?",
    "Highest first-kill rate at Masters London 2026",
    "New Zealand Darts Masters: Winner",
    "Hitpoint Masters 2026 Summer: Winner",
    '"Masters of the Universe" Opening Weekend Box Office',
]

REAL_MASTERS = [
    "Masters Tournament Winner",
    "The Masters",
    "The Masters Top 5",
    "2027 Masters Winner",
    "Masters 2027 Winner",
    "Will Scottie Scheffler win the Masters?",
    "PGA Tour: Masters Tournament Top 10",
]


@pytest.mark.parametrize("name", MASTERS_CONTAMINANTS)
def test_qualified_masters_is_not_the_major(name):
    assert _is_the_masters(name) is False, name
    assert _normalize_tournament(name) != "masters", name


@pytest.mark.parametrize("name", REAL_MASTERS)
def test_augusta_still_folds_onto_masters(name):
    assert _is_the_masters(name) is True, name
    assert _normalize_tournament(name) == "masters", name


def test_british_masters_gets_its_own_key_not_augustas():
    # The whole point: a real DP World Tour event must not inherit Augusta's
    # schedule, because that schedule is what deletes the card.
    key = _normalize_tournament("DP World Tour: British Masters Winner")
    assert key == "british_masters"
    assert key not in MAJOR_TOURNAMENTS


def test_all_four_polymarket_british_masters_market_types_share_one_key():
    # Cross-market-type folding within one source — 7 markets, one card.
    names = [
        "DP World Tour: British Masters Winner",
        "DP World Tour: British Masters Top 5",
        "DP World Tour: British Masters Top 10",
        "DP World Tour: British Masters Top 20",
        "DP World Tour: British Masters First Round Leader",
        "DP World Tour: British Masters Second Round Leader",
        "DP World Tour: British Masters Third Round Leader",
    ]
    keys = {_normalize_tournament(n) for n in names}
    assert keys == {"british_masters"}, keys


# ---------------------------------------------------------------------------
# LEVEL — "the Open"
# ---------------------------------------------------------------------------


def test_open_as_an_adjective_is_not_the_open_championship():
    name = ("Will Anthropic sign the Open Weights and American AI Leadership "
            "letter?")
    assert _is_the_open(name) is False
    assert _normalize_tournament(name) != "the_open"


@pytest.mark.parametrize("name", [
    "The Open Winner",
    "The Open Championship - Winner",
    "The Open Championship End of Round 1 Leader",
    "British Open Winner",
    "Will Rory McIlroy win the Open?",
    "The Open at Royal Portrush",
])
def test_the_open_championship_still_folds(name):
    assert _is_the_open(name) is True, name
    assert _normalize_tournament(name) == "the_open", name


# ---------------------------------------------------------------------------
# TOUR
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name,external_id,expected", [
    ("Husqvarna British Masters - Winner", "datagolf:euro:2026133:win", "dp_world"),
    ("Husqvarna British Masters Winner", "KXDPWORLDTOUR-HUBMHBSNF26", "dp_world"),
    ("DP World Tour: British Masters Top 5", "904533", "dp_world"),
    ("Liv Golf New York: Top 5 Finishers", "KXLIVTOP5-YOR26", "liv"),
    ("Simmons Bank Open - Winner", "datagolf:kft:2026120:win", "korn_ferry"),
    # Declares nothing — must stay permissive, or cross-source folding breaks.
    ("Masters Tournament Winner", "golf_masters_tournament_winner", None),
    ("US Open Winner", "golf_us_open_winner", None),
])
def test_declared_tour(name, external_id, expected):
    assert _declared_tour(name, external_id) == expected


def test_pga_tour_prefix_does_not_block_a_major():
    # Polymarket prefixes majors with "PGA Tour:". A major IS on the PGA Tour, so
    # this must NOT read as a contradiction — otherwise the U.S. Open card splits.
    assert _normalize_tournament("PGA Tour: U.S. Open Winner") == "us_open"
    assert _normalize_tournament("PGA Tour: TOUR Championship Winner") == "tour_championship"


def test_lpga_is_not_a_major_blocking_tour_gender_handles_that_instead():
    # Gender is the `_womens` suffix's job, and `us_open_womens` is a real card, so
    # `lpga` must stay OUT of the tour-contradiction set — otherwise a women's major
    # would be refused its key by the tour discriminator instead of being separated
    # by the gender one.
    from app.routes.golf import _MAJOR_EXCLUSIVE_TOURS
    assert "lpga" not in _MAJOR_EXCLUSIVE_TOURS
    assert "pga" not in _MAJOR_EXCLUSIVE_TOURS
    assert _normalize_tournament("U.S. Open Winner") == "us_open"
    assert _normalize_tournament("LPGA: U.S. Open Winner") == "us_open"


def test_lpga_prefix_no_longer_forks_a_key_from_its_own_datagolf_twin():
    # Pre-existing and unchanged: "U.S. Women's Open" does not match the `us_open`
    # pattern (the "Women's" sits between "U.S." and "Open"), so it earns its own
    # key. What F4 fixes is that the two SOURCES agreed on that key — before, the
    # Polymarket name kept its "LPGA:" prefix and forked into `lpga_u_s_women_s_open`
    # while DataGolf produced `u_s_women_s_open`. Two cards, one tournament.
    poly = _normalize_tournament("LPGA: U.S. Women's Open Winner")
    datagolf = _normalize_tournament("U.S. Women's Open - Winner")
    assert poly == datagolf == "u_s_women_s_open"
    assert bool(_WOMENS_RE.search("LPGA: U.S. Women's Open Winner")) is True


# ---------------------------------------------------------------------------
# GENDER — one regex, not two
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", [
    "LPGA: FM Championship Winner",
    "CPKC Women's Open End of Round 1 Leader",
    "AIG Women's Open - Winner",
    "Ladies European Tour Winner",
    "The Chevron Championship - Winner",
    "Amundi Evian Championship - Winner",
])
def test_one_womens_regex_covers_every_signal_both_callers_used(name):
    # The fold key used `_WOMENS_RE` (lpga|women's|ladies); the completed-tournament
    # path used an inline `women|lpga|chevron|amundi`. A Chevron Championship market
    # therefore folded onto a MEN'S key on one surface while reporting
    # `is_womens: true` on the other. One regex, one answer.
    assert bool(_WOMENS_RE.search(name)) is True, name


@pytest.mark.parametrize("name", [
    "Masters Tournament Winner",
    "TOUR Championship - Winner",
    "The Open Championship - Winner",
    "Liv Golf Indianapolis End of Round 1 Leader",
])
def test_mens_events_are_not_flagged_womens(name):
    assert bool(_WOMENS_RE.search(name)) is False, name


# ---------------------------------------------------------------------------
# The market-type tail — one tournament, one key
# ---------------------------------------------------------------------------


def test_tour_championship_thirteen_markets_one_key():
    # Measured live 2026-08-24: these 13 open markets produced 7 keys, and the card
    # `/api/golf` served carried only the 6 that happened to use a dash separator.
    names = [
        "TOUR Championship - Winner",
        "TOUR Championship - Top 5 Finish",
        "TOUR Championship - Top 10 Finish",
        "TOUR Championship - Top 20 Finish",
        "TOUR Championship - Make the Cut",
        "TOUR Championship: Hole-in-One",
        "PGA Tour: TOUR Championship Winner",
        "PGA Tour: TOUR Championship Top 5",
        "PGA Tour: TOUR Championship Top 10",
        "PGA Tour: TOUR Championship Top 20",
        "PGA Tour: TOUR Championship First Round Leader",
        "PGA Tour: TOUR Championship Second Round Leader",
        "PGA Tour: TOUR Championship Third Round Leader",
    ]
    keys = {_normalize_tournament(n) for n in names}
    assert keys == {"tour_championship"}, keys


def test_lpga_fm_championship_seven_markets_one_key():
    names = [
        "LPGA: FM Championship Winner",
        "LPGA: FM Championship Top 5",
        "LPGA: FM Championship Top 10",
        "LPGA: FM Championship Top 20",
        "LPGA: FM Championship First Round Leader",
        "LPGA: FM Championship Second Round Leader",
        "LPGA: FM Championship Third Round Leader",
    ]
    keys = {_normalize_tournament(n) for n in names}
    assert len(keys) == 1, keys
    assert "fm_championship" in keys.pop()


@pytest.mark.parametrize("name,expected", [
    ("TOUR Championship - Top 5 Finish", "TOUR Championship"),
    ("Liv Golf New York: Top 5 Finishers", "Liv Golf New York"),
    ("Nexo Championship: To Make the Cut", "Nexo Championship"),
    ("Rogers Charity Classic End of Round 1 Leader", "Rogers Charity Classic"),
    ("PGA Tour: TOUR Championship Third Round Leader", "TOUR Championship"),
    # Nothing to strip — must be a no-op, not a truncation.
    ("Tiger Woods to compete in any PGA event in 2026",
     "Tiger Woods to compete in any PGA event in 2026"),
    ("Golfers to win a PGA Tour Major before 2030",
     "Golfers to win a PGA Tour Major before 2030"),
])
def test_strip_market_chrome(name, expected):
    assert _strip_market_chrome(name) == expected


# ---------------------------------------------------------------------------
# Regression guards on the keys that already worked
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name,key", [
    ("US Open Winner", "us_open"),
    ("U.S. Open: First Time Winner?", "us_open"),
    ("PGA Championship Winner", "pga_championship"),
    ("2027 Ryder Cup Winner", "ryder_cup"),
    ("Presidents Cup Winner", "presidents_cup"),
    ("Liv Golf Indianapolis End of Round 1 Leader", "liv"),
    ("Simmons Bank Open for the Snedeker Foundation - Winner",
     "simmons_bank_open_for_the_snedeker_foundation"),
])
def test_unaffected_keys_are_unchanged(name, key):
    assert _normalize_tournament(name) == key, name


def test_senior_open_still_does_not_fold_into_the_open():
    # L2-90 regression — the pre-existing `_NOT_THE_OPEN_RE` guard must survive.
    assert _normalize_tournament("U.S. Senior Open Championship Winner") != "the_open"
    assert _normalize_tournament("The Senior Open Championship - Winner") != "the_open"
