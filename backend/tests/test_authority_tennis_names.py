"""The tennis name join, proved on the real field rather than on chosen cases. #2867 step 4.

The method is the point, and it is the one `r_prefix_token_match_makes` paid for:
**a widened name comparison is not tested by the cases that motivated it.** Every
tolerance here is swept over all 7,731 distinct tennis names production actually
holds (`tests/fixtures/tennis_name_corpus_20260905.json`), so a future loosening
has to survive the whole field and not just the examples in its commit message.

The two collisions that gave the rule its shape are pinned by name below, both
from real draws: `Christopher O'Connell` against `Oleksandra Oliynykova` (the
one-letter-token wildcard) and `Francisco Cerundolo` against `Juan Manuel
Cerundolo` (two players, one surname, in the same tournament).
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import pytest

from app.utils.authority_tennis_names import (
    AMBIGUOUS,
    MATCHED,
    NO_CANDIDATE,
    UNREADABLE,
    doubles_key,
    fold_tennis_name,
    is_doubles_name,
    looks_like_a_player,
    _tokens,
    our_tennis_keys,
    resolve_tennis_name,
    statpal_tennis_key,
    tennis_names_agree,
)

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def corpus() -> list[str]:
    doc = json.loads(
        (FIXTURES / "tennis_name_corpus_20260905.json").read_text(encoding="utf-8")
    )
    names = doc["names"]
    # The fixture's own count must match what it carries: a corpus that lost rows
    # on the way into the file would make every collision number below a quiet
    # under-count.
    assert len(names) == doc["count"] == 7731
    return names


# ─────────────────────────────────────────────────────────────────────────────
# The two shapes, read off the real vendor payloads
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "name,expected",
    [
        ("C. Alcaraz", ("alcaraz", "c")),
        ("Y. Wu", ("wu", "y")),
        ("Y. Bu", ("bu", "y")),
        ("M. Zheng", ("zheng", "m")),
        # The surname is EVERYTHING after the initials, not the last token.
        ("B. Van De Zandschulp", ("van de zandschulp", "b")),
        ("D. Merida Aguilar", ("merida aguilar", "d")),
        # Two initials: the first one is the given name's.
        ("T. M. Etcheverry", ("etcheverry", "t")),
        ("J. M. Cerundolo", ("cerundolo", "j")),
    ],
)
def test_statpal_serves_initials_then_a_possibly_multi_token_surname(name, expected):
    assert statpal_tennis_key(name) == expected


def test_a_statpal_name_that_is_only_initials_is_refused_not_guessed():
    """Initials with no surname join to whatever shares a letter, so they do not
    join at all. `None` is a report, not a silent skip."""
    assert statpal_tennis_key("J. M.") is None
    assert resolve_tennis_name("J. M.", ["Juan Manuel Cerundolo"]).outcome == UNREADABLE


def test_our_bare_surnames_produce_a_key_with_no_initial():
    """A third of the field. `(surname, None)` is a real key — the given name is
    unknown, which is not the same as absent-and-therefore-unmatchable."""
    assert our_tennis_keys("Hrazdil") == frozenset({("hrazdil", None)})
    assert our_tennis_keys("Gaston") == frozenset({("gaston", None)})


def test_a_missing_initial_never_becomes_a_disagreement():
    assert tennis_names_agree("Alcaraz", "C. Alcaraz")
    assert tennis_names_agree("Monfils", "G. Monfils")


# ─────────────────────────────────────────────────────────────────────────────
# The order problem — the artifact's binding requirement
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "ours,theirs",
    [
        # Surname FIRST. A surname-last rule reads `Yibing` as the surname and
        # reports a permanent false miss on every Chinese player.
        ("Wu Yibing", "Y. Wu"),
        ("Bu Yunchaokete", "Y. Bu"),
        ("Liang En-shuo", "E. Liang"),
        ("Zheng Qinwen", "Q. Zheng"),
        # The same players as our register ALSO spells them — surname last.
        ("Yibing Wu", "Y. Wu"),
        ("Yunchaokete Bu", "Y. Bu"),
        ("En-Shuo Liang", "E. Liang"),
        # Ordinary Western order, which must keep working.
        ("Carlos Alcaraz", "C. Alcaraz"),
        ("Marie Bouzkova", "M. Bouzkova"),
        ("Juan Manuel Cerundolo", "J. M. Cerundolo"),
        ("Botic Van De Zandschulp", "B. Van De Zandschulp"),
    ],
)
def test_both_word_orders_join(ours, theirs):
    assert tennis_names_agree(ours, theirs)


def test_diacritics_and_case_are_one_player():
    assert tennis_names_agree("Anna Bondár", "A. Bondar")
    assert tennis_names_agree("Daria KHOMUTSIANSKAYA", "D. Khomutsianskaya")


# ─────────────────────────────────────────────────────────────────────────────
# The collisions the rule exists to refuse
# ─────────────────────────────────────────────────────────────────────────────


def test_the_one_letter_token_wildcard_does_not_reappear():
    """`Christopher O'Connell` compared equal to `Oleksandra Oliynykova` when a
    tolerant matcher let the `o` split out of `O'Connell` cover both. Surnames
    here are matched whole and exact, so it cannot happen — in either reading."""
    assert not tennis_names_agree("Christopher O'Connell", "O. Oliynykova")
    assert not tennis_names_agree("Oleksandra Oliynykova", "C. O'Connell")


def test_two_players_sharing_a_surname_are_separated_by_the_initial():
    """Both were in the same US Open draw."""
    assert tennis_names_agree("Juan Manuel Cerundolo", "J. M. Cerundolo")
    assert not tennis_names_agree("Francisco Cerundolo", "J. M. Cerundolo")
    assert tennis_names_agree("Francisco Cerundolo", "F. Cerundolo")


def test_a_short_surname_is_not_a_wildcard():
    """`Wu` is two characters and a real surname; the older `>=3`-character
    anchor rule would have refused it. It is only dangerous under prefix
    matching, which this module does not do."""
    assert tennis_names_agree("Wu Yibing", "Y. Wu")
    assert not tennis_names_agree("Wu Yibing", "Y. Wutkowski")
    assert not tennis_names_agree("Wutkowski", "Y. Wu")


def test_two_candidates_that_are_different_people_are_refused_by_name():
    got = resolve_tennis_name("A. Martin", ["Adam Martin", "Andrej Martin"])
    assert got.outcome == AMBIGUOUS
    assert got.candidates == ("Adam Martin", "Andrej Martin")
    assert got.matched is None


def test_one_player_our_register_lists_in_both_orders_is_not_ambiguous():
    """The case the order tolerance exists for. Two ROWS, one player — refusing
    it would refuse exactly what the widening was for."""
    got = resolve_tennis_name("Y. Wu", ["Wu Yibing", "Yibing Wu"])
    assert got.outcome == MATCHED
    got = resolve_tennis_name("J. Shang", ["Shang Juncheng", "Juncheng Shang"])
    assert got.outcome == MATCHED


def test_no_candidate_and_ambiguous_are_different_answers():
    assert resolve_tennis_name("C. Alcaraz", []).outcome == NO_CANDIDATE
    assert resolve_tennis_name("C. Alcaraz", ["Jannik Sinner"]).outcome == NO_CANDIDATE


# ─────────────────────────────────────────────────────────────────────────────
# Doubles
# ─────────────────────────────────────────────────────────────────────────────


def test_doubles_fold_across_our_two_separator_spellings_and_either_order():
    assert tennis_names_agree("Barrientos / Behar", "Barrientos/ Behar")
    assert tennis_names_agree("Bagaric/Moratelli", "Bagaric/ Moratelli")
    assert tennis_names_agree("Rojer / Winegar", "Winegar/Rojer")


def test_a_doubles_pair_never_matches_a_singles_player():
    """Doubles outnumber singles better than 2:1 on a US Open day, so conflating
    the draws is how a denominator grows a phantom gap."""
    assert not tennis_names_agree("Aoyama/Liang", "E. Liang")
    assert not tennis_names_agree("Liang En-shuo", "Aoyama/ Liang")


def test_a_malformed_pair_is_unreadable_rather_than_half_matched():
    assert doubles_key("Galloway/") is None
    assert doubles_key("A/B/C") is None
    assert resolve_tennis_name("Galloway/", ["Galloway / Goransson"]).outcome == (
        UNREADABLE
    )


# ─────────────────────────────────────────────────────────────────────────────
# The sweep: every name in the real field
# ─────────────────────────────────────────────────────────────────────────────


def test_the_field_has_the_four_vocabularies_the_module_claims(corpus):
    """The header's shape table, asserted. If production's tennis names change
    shape, the reasoning built on these proportions is stale and this says so."""
    shapes: dict[str, int] = defaultdict(int)
    for name in corpus:
        if is_doubles_name(name):
            shapes["doubles"] += 1
            continue
        n = len(fold_tennis_name(name).split())
        shapes["bare" if n == 1 else ("two" if n == 2 else "three-plus")] += 1

    assert shapes["doubles"] == 1674
    assert shapes["bare"] == 2516
    assert shapes["two"] == 2851
    assert shapes["three-plus"] == 690
    # A third of the field carries no given name: the fact that makes the
    # initial a disambiguator and never a requirement.
    assert shapes["bare"] / len(corpus) > 0.32


def test_no_two_different_players_collide_on_a_full_key(corpus):
    """The sweep. Bucket the whole field by every key each name can answer to and
    look at every bucket holding more than one name — O(n), the cheap form of the
    all-pairs sweep.

    Collisions exist and are NOT a bug: 577 keys are claimed by more than one
    name, because two people really can be `A. Martin`. What is asserted is that
    the resolver never silently picks one of them — every genuine collision comes
    back AMBIGUOUS, by name.
    """
    buckets: dict[tuple, set[str]] = defaultdict(set)
    for name in corpus:
        for key in our_tennis_keys(name):
            buckets[key].add(name)

    contested = {k: v for k, v in buckets.items() if len(v) > 1}
    # Pinned so that a loosening which multiplies the collisions has to say so.
    assert len(buckets) == 10617
    assert len(contested) == 572

    # Every contested key, resolved against its own claimants, must refuse.
    unexpressable = 0
    for (surname, initial), names in contested.items():
        theirs = f"{initial.upper()}. {surname}" if initial else surname
        got = resolve_tennis_name(theirs, sorted(names))
        if got.outcome == UNREADABLE:
            # A one-character surname cannot be written in StatPal's
            # initials-then-surname form at all — `A. d` reads as two initials
            # and no surname. These come from apostrophe splitting
            # (`D'Estree Colalancia` -> `d estree colalancia`), so the key is
            # unreachable from their side rather than wrongly resolved.
            assert len(surname) == 1, (surname, initial, sorted(names))
            unexpressable += 1
            continue
        assert got.outcome in (AMBIGUOUS, MATCHED)
        if got.outcome == MATCHED:
            # The only permitted MATCH on a contested key is one player our
            # register spells more than one way.
            token_sets = {frozenset(fold_tennis_name(n).split()) for n in names}
            assert len(token_sets) == 1, (surname, initial, sorted(names))

    # Bounded rather than ignored: if this grows, our column is accumulating a
    # new punctuation shape and the join is quietly losing reach.
    assert unexpressable <= 12


def test_admitting_the_asian_reading_costs_what_the_header_says(corpus):
    """The trade, pinned. Surname-last alone is cheaper in collisions and leaves
    more players unreachable; the module takes the second column deliberately, so
    both numbers are asserted rather than the chosen one."""

    def keys(name: str, *, both_ends: bool) -> set[tuple]:
        # The module's own tokenisation, so the two arms differ ONLY in the
        # reading under test. Re-splitting the name here instead would have the
        # arms disagree about generational suffixes and market titles too, and
        # the difference would be attributed to the reading.
        if is_doubles_name(name) or not looks_like_a_player(name):
            return set()
        toks = _tokens(name)
        if not toks:
            return set()
        if len(toks) == 1:
            return {(toks[0], None)}
        out = set()
        for cut in range(1, len(toks)):
            out.add((" ".join(toks[cut:]), toks[0][0]))
            if both_ends:
                out.add((" ".join(toks[:cut]), toks[cut][0]))
        return out

    for both_ends, n_keys, n_contested in ((False, 6674, 208), (True, 10617, 572)):
        buckets: dict[tuple, set[str]] = defaultdict(set)
        for name in corpus:
            for key in keys(name, both_ends=both_ends):
                buckets[key].add(name)
        assert len(buckets) == n_keys, both_ends
        assert sum(1 for v in buckets.values() if len(v) > 1) == n_contested, both_ends


def test_doubles_fold_repairs_our_own_duplicate_spellings(corpus):
    """1,674 stored doubles names are 1,515 real pairs. Every one of the 159
    'collisions' is one TEAM stored twice — 157 under both separator spellings
    and 2 with the partners reversed — never two different teams, so the fold is
    a repair and not a tolerance."""
    pairs: dict[frozenset, set[str]] = defaultdict(set)
    unreadable = 0
    for name in corpus:
        if not is_doubles_name(name):
            continue
        key = doubles_key(name)
        if key is None:
            unreadable += 1
            continue
        pairs[key].add(name)

    assert unreadable == 0
    assert sum(len(v) for v in pairs.values()) == 1674
    assert len(pairs) == 1515
    collisions = {k: v for k, v in pairs.items() if len(v) > 1}
    assert len(collisions) == 159
    separator_only = sum(
        1 for v in collisions.values() if len({fold_tennis_name(n) for n in v}) == 1
    )
    # The split is stated rather than glossed: 2 of the 159 are the same pair with
    # the partners the other way round, which a separator-only claim would have
    # quietly mis-described.
    assert separator_only == 157
    assert len(collisions) - separator_only == 2
    for key, names in collisions.items():
        # Whatever the spelling, every claimant is the SAME unordered pair —
        # which is what makes collapsing them a repair and not a fusion.
        assert all(doubles_key(n) == key for n in names)


def _statpal_tennis_names(filename: str, root: str) -> list[str]:
    doc = json.loads((FIXTURES / filename).read_text(encoding="utf-8"))
    out: list[str] = []
    for tourn in doc[root]["tournament"]:
        matches = tourn["match"]
        for match in matches if isinstance(matches, list) else [matches]:
            for player in match.get("player") or []:
                if player.get("name"):
                    out.append(player["name"])
    return out


@pytest.mark.parametrize(
    "filename,root",
    [
        ("statpal_tennis_daily_20260903.json", "scores"),
        ("statpal_tennis_livescores_20260903.json", "livescores"),
    ],
)
def test_every_name_in_the_real_vendor_payload_is_readable(filename, root):
    """The venue's own bytes, not examples retyped from them. A name this module
    cannot read is a fixture the tennis row could never join, so an unreadable
    one has to fail here rather than become a silent miss in the denominator."""
    names = _statpal_tennis_names(filename, root)
    assert names, filename
    for name in names:
        if is_doubles_name(name):
            assert doubles_key(name) is not None, name
        else:
            key = statpal_tennis_key(name)
            assert key is not None, name
            surname, initial = key
            assert len(surname) >= 2, name
            assert initial is not None, name


def test_the_real_payload_carries_both_draws_and_they_stay_apart():
    """Doubles outnumber singles on a US Open day; the livescores fixture holds
    both draws, and no name from one may resolve against the other."""
    names = _statpal_tennis_names(
        "statpal_tennis_livescores_20260903.json", "livescores"
    )
    singles = [n for n in names if not is_doubles_name(n)]
    doubles = [n for n in names if is_doubles_name(n)]
    assert singles and doubles
    for pair in doubles:
        assert resolve_tennis_name(pair, singles).outcome == NO_CANDIDATE
    for one in singles:
        assert resolve_tennis_name(one, doubles).outcome == NO_CANDIDATE


def test_the_named_us_open_join_from_the_artifact_holds():
    """`Y. Wu` against `Wu Yibing` is the case
    `ARTIFACT-AUTHORITY-20260903-TENNIS.md` says must be resolved before any
    tennis number is published — it was reported as a permanent false miss."""
    theirs = _statpal_tennis_names(
        "statpal_tennis_livescores_20260903.json", "livescores"
    )
    assert "Y. Wu" in theirs and "C. Alcaraz" in theirs
    ours = ["Wu Yibing", "Carlos Alcaraz", "Yunchaokete Bu", "Mackenzie McDonald"]
    assert resolve_tennis_name("Y. Wu", ours).matched == "Wu Yibing"
    assert resolve_tennis_name("C. Alcaraz", ours).matched == "Carlos Alcaraz"


def test_market_titles_in_the_player_column_are_not_players(corpus):
    """Futures market names have leaked into the tennis team-name column. They
    fold to keys like `('winner', 'b')` that collide with each other and match no
    real player, so they are excluded by shape."""
    assert not looks_like_a_player("Black Desert Resort (Men's Doubles) Winner")
    assert looks_like_a_player("Carlos Alcaraz")
    assert (
        our_tennis_keys("Black Desert Resort (Women's Singles) Winner") == frozenset()
    )
    leaked = [n for n in corpus if not looks_like_a_player(n)]
    # Present, and bounded: if this grows, the column is being written by
    # something new and the join's denominator is drifting.
    assert 0 < len(leaked) <= 200
