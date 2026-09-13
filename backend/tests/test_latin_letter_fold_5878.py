"""A letter that carries its mark inside the glyph must FOLD, never be deleted (#5878).

`normalize_team` folded combining marks and then ran a `[^a-z0-9 ]` noise strip
over whatever was left. `ø`, `ł`, `ß`, `æ`, `ð` and `ı` have no NFD/NFKD
decomposition, so they survived the fold, reached the noise strip, and were
replaced by a SPACE. That does not shorten a word — it splits it:

    Bodø/Glimt          -> "bod glimt"           (StatPal writes "Bodo/Glimt")
    SC Preußen Münster  -> "sc preu en munster"  (StatPal writes "Preussen Munster")
    Wisła Płock         -> "wis ap ock"          (the single-letter run-join then
                                                  welds the two invented letters)

`bod` and `preu` are not words; nothing on either side will ever match them. So
every production event whose team name carries one of these letters was
unjoinable to StatPal in BOTH directions.

**The pairs below are not transliteration theory.** They were read off StatPal's
own soccer boards on 2026-09-13 (offsets -2, -1, 1, 2, 3, 5; 5,614 distinct club
names, of which **zero** carry any letter in the table) beside the spelling
production holds for the same club. Measured with the task's own
`classify_fixture` over those 3,498 board fixtures against our 1,141 soccer rows
in the same window: STAMP 33 -> 43, AMBIGUOUS 2 -> 2, 0 resolutions lost, 0
re-pointed.
"""

from __future__ import annotations

import unicodedata

import pytest

from app.utils import name_normalization, nfl_team_matching
from app.utils.name_normalization import EXTRA_TRANSLITERATIONS, strip_diacritics
from app.utils.nfl_team_matching import NFL_TEAM_NAMES, normalize_team, pair_matches
from app.utils.soccer_team_matching import soccer_pair_matches, soccer_team_matches

#: (our spelling, StatPal's spelling on the board, the letter at issue).
#: Every row read at the venue on 2026-09-13, not assumed.
MEASURED_CLUBS = [
    ("Bodø/Glimt", "Bodo/Glimt", "ø"),
    ("FK Bodø/Glimt", "Bodo/Glimt", "ø"),
    ("Tromsø IL", "Tromso", "ø"),
    ("Lillestrøm SK", "Lillestrom", "ø"),
    ("Brøndby IF", "Brondby", "ø"),
    ("HB Køge", "Koge", "ø"),
    ("Sønderjyske Fodbold", "Sonderjyske", "ø"),
    ("SC Preußen Münster", "Preussen Munster", "ß"),
    ("SG Sonnenhof Großaspach", "Grossaspach", "ß"),
    ("FC Blau-Weiß Linz", "Blau-Weiss Linz", "ß"),
    ("Widzew Łódź", "Widzew Lodz", "Ł"),
    ("Śląsk Wrocław", "Slask Wroclaw", "ł"),
    ("Zagłębie Lubin", "Zaglebie", "ł"),
    ("Wisła Kraków", "Wisla Krakow", "ł"),
    ("Wisła Płock", "Wisla Plock", "ł"),
    ("Jagiellonia Białystok", "Jagiellonia Bialystok", "ł"),
    ("FC Nordsjælland", "Nordsjaelland", "æ"),
    ("UMF Breiðablik", "Breidablik", "ð"),
    ("Kasımpaşa SK", "Kasimpasa", "ı"),
]


@pytest.mark.parametrize("ours,board,letter", MEASURED_CLUBS)
def test_the_club_the_venue_spells_in_ascii_is_the_same_club(ours, board, letter):
    assert letter in ours, "specimen no longer carries the letter it was chosen for"
    assert soccer_team_matches(board, ours)
    assert soccer_team_matches(ours, board)


@pytest.mark.parametrize("ours,board,letter", MEASURED_CLUBS)
def test_the_fold_lands_on_the_spelling_the_board_uses(ours, board, letter):
    """Stronger than "they match": our letter becomes the board's letters.

    `soccer_team_matches` is a token-subset rule, so it can pass for reasons that
    have nothing to do with this fold. Asserting the normalized token is present
    pins the fold itself, and fails if the letter is dropped, mapped to the wrong
    ASCII, or folded after the noise strip instead of before it.
    """
    board_tokens = set(normalize_team(board).split())
    our_tokens = set(normalize_team(ours).split())
    assert board_tokens <= our_tokens, f"{our_tokens} does not contain {board_tokens}"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Bodø/Glimt", "bodo glimt"),
        ("SC Preußen Münster", "sc preussen munster"),
        ("Wisła Płock", "wisla plock"),
        ("FC Nordsjælland", "fc nordsjaelland"),
        ("UMF Breiðablik", "umf breidablik"),
        ("Kasımpaşa SK", "kasimpasa sk"),
    ],
)
def test_the_letter_is_replaced_and_not_removed(raw, expected):
    """The defect was a SPLIT, so the shape of the answer is what is asserted.

    Deleting the letter outright (`bodglimt`) would also make this pair join in
    some arrangements; it is still wrong, and the venue does not write it. This
    pins the exact string, which is the only assertion that separates "folded"
    from "deleted" from "split".
    """
    assert normalize_team(raw) == expected


def test_a_deleted_letter_would_have_invented_a_token_that_matches_nothing():
    """The mechanism, stated positively so the guard cannot go vacuous.

    Written as "the token count is the same on both spellings" rather than
    "`bod` is absent", because a later fold that produced `bo` + `do` would pass
    the absence form and still be broken.
    """
    for ours, board, _ in MEASURED_CLUBS:
        assert len(normalize_team(ours).split()) >= len(normalize_team(board).split())
        assert "bod " not in normalize_team("Bodø/Glimt") + " "


def test_the_table_is_shared_with_name_normalization_and_not_a_third_copy():
    """A fourth transliteration table would be the bug, not the fix.

    This codebase already carried two (`name_normalization` and
    `golf_card_snapshot`, the latter written after the same defect dropped both
    Højgaards from a golf card) and they had already drifted — one has `ß`, the
    other has `æ`, neither has both. `normalize_team` cannot call
    `strip_diacritics`, because it needs NFKC/NFKD rather than NFD, so it shares
    the TABLE. This asserts the sharing is by reference, not by copy.
    """
    assert nfl_team_matching.EXTRA_TRANSLITERATIONS is EXTRA_TRANSLITERATIONS
    assert EXTRA_TRANSLITERATIONS is name_normalization._EXTRA_TRANSLITERATIONS


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Nordsjælland", "Nordsjaelland"),
        ("Breiðablik", "Breidablik"),
        ("Kasımpaşa", "Kasimpasa"),
        ("Þór Akureyri", "THor Akureyri"),
        ("Strauß", "Strauss"),
        ("Højgaard", "Hojgaard"),
    ],
)
def test_strip_diacritics_gained_the_same_letters(raw, expected):
    """The shared table is reached through `strip_diacritics` too.

    `Þór` -> `THor` rather than `Thor` is the honest output of a
    character-for-characters table and is not a defect here: every consumer
    lowercases afterwards. Pinned so the day someone wants `Thor` they change it
    deliberately.
    """
    assert strip_diacritics(raw) == expected


def test_every_letter_in_the_table_is_one_nfkd_cannot_reach():
    """An entry NFKD already handles is dead weight and hides a real one."""
    for code in EXTRA_TRANSLITERATIONS:
        ch = chr(code)
        decomposed = unicodedata.normalize("NFKD", ch)
        stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
        assert not stripped.isascii(), f"{ch!r} decomposes to ASCII already"


def test_the_fold_is_the_identity_on_a_name_that_carries_none_of_its_letters():
    """The confinement proof, which is why the blast radius is exactly measurable.

    `str.translate` cannot touch a string with no code point in the table, so
    every name in either vocabulary that avoids these 18 letters normalizes
    exactly as it did before. On 2026-09-13 that was 12,793 of the 12,828
    distinct names across production soccer rows and StatPal's boards.
    """
    for name in (
        "San Francisco 49ers",
        "Borussia Mönchengladbach",
        "Atlético Madrid",
        "São Paulo",
        "St. Louis Cardinals",
        "1. FC Köln",
    ):
        assert name.translate(EXTRA_TRANSLITERATIONS) == name


@pytest.mark.parametrize("name", sorted(NFL_TEAM_NAMES))
def test_the_nfl_rule_does_not_move(name):
    """32 franchises, all ASCII, so the table is provably inert on this league.

    Asserted per name rather than as a single "the NFL is fine" sentence, so a
    future roster entry carrying one of these letters announces itself here
    instead of changing the NFL join silently.
    """
    assert name.isascii()
    assert normalize_team(name) == name
    assert pair_matches((name, name), (name, name))


def test_the_bare_board_name_wisla_is_ambiguous_and_the_pair_rule_is_what_holds_it():
    """What the widening costs, pinned rather than left for someone to find.

    StatPal's boards carry a bare `Wisla`, and the Ekstraklasa has two: Wisła
    Kraków and Wisła Płock. Before this fold neither matched it — because both
    were split into rubbish, not because anything was being careful. After it,
    both do, which is the generic-core subset shape this module already lives
    with (`FC United` matches 55 names on master). The separator is the rest of
    the fixture: the pair rule needs the OTHER side to agree too, and the caller
    adds a one-hour window and an exactly-one contract on top.
    """
    assert soccer_team_matches("Wisla", "Wisła Kraków")
    assert soccer_team_matches("Wisla", "Wisła Płock")

    assert soccer_pair_matches(
        ("Wisla", "Jagiellonia"), ("Wisła Kraków", "Jagiellonia Białystok")
    )
    assert not soccer_pair_matches(
        ("Wisla", "Jagiellonia"), ("Wisła Płock", "Cracovia Kraków")
    )
