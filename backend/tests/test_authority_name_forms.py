"""The widened identity rule agrees with more real teams and fuses none. #2792.

Three kinds of test, and the middle one is the only one that would have caught
the two defects this module shipped with:

1. **The motivating cases** — the vocabulary differences measured on production
   that used to read as ``teams_disagree``. Necessary, and by themselves worth
   little: they are the cases the rule was written from.

2. **The corpus sweep** (:func:`test_no_new_fusion_across_the_real_corpus`) —
   every distinct team name we hold, per sport, bucketed by canonical form, with
   every collision between two different names asserted against a pinned list.
   Run before this module was finished, it produced two fusions nobody had
   thought of: a trailing-year rule that made ``Iberia 1999`` and ``Iberia 2010``
   one Georgian club, and an affix rule that made ``Barcelona SC`` of Guayaquil
   into FC Barcelona. Both are now impossible, and this test is why.

3. **Asymmetric pairs** (:func:`test_the_affix_list_is_observable`) — the
   widening normalises BOTH sides through one helper, which makes every word
   list inside it invisible to a symmetric test case: feed both sides the same
   affix and they align whether or not it is listed. A mutation that empties
   ``CLUB_INITIALISMS`` survives a suite full of symmetric cases. Only a pair
   where ONE side carries the affix can observe the list.

═══ THE CENSUS THESE NUMBERS COME FROM (production, 2026-09-03) ═══

685 anchored, unfinished rows inside the rail's 120-day window, one ESPN
``summary?event=`` call each. **Both rules were run over the same rows and the
same fetched payloads in one pass** — two separate census runs cannot be
compared, because the window moves and ESPN's answers flake, and the delta
would be measuring that instead of the rule:

                        narrow    widened
    agrees                 561        595
    authority_moves_us      24         25
    teams_disagree          52         17
    no_answer               48         48

35 rows rescued, and ``no_answer`` identical in both columns, which is what
says the two arms saw the same authority.

(#2792 records this population as 194 rows with 10 moves. That was a
``limit=200`` run against a 685-row window — a truncated pass reporting like a
complete one, which is its own defect and is fixed in
``reconcile_anchor_schedule``: ``eligible`` and ``truncated`` are now always
reported.)

The 17 that remain are the ones no structural rule reaches — genuine synonyms
(``App State``/``Appalachian State``, ``Athletic Bilbao``/``Athletic Club``), a
university that renamed itself (``Houston Baptist``/``Houston Christian``), and
**one real mis-anchor**, E416569, which is the row #2792 is titled for and which
:func:`test_the_mis_anchor_2792_still_disagrees` exists to keep out forever.
"""

from __future__ import annotations

import gzip
import json
from collections import defaultdict
from pathlib import Path

import pytest

from app.utils.authority_id_collisions import (
    AuthorityRecord,
    CandidateRow,
    _teams_agree,
    authority_names,
)
from app.utils.authority_name_forms import (
    CLUB_INITIALISMS,
    CONTESTED_RESIDUALS,
    EXPECTED_COLLISIONS,
    canonical_forms,
    composed_forms,
    synonym_forms,
)
from app.utils.name_normalization import normalize_team_name_for_matching

CORPUS = (
    Path(__file__).parent / "fixtures" / "authority_team_name_corpus_20260903.json.gz"
)

#: The affix list as this suite expects to find it, declared HERE as a literal
#: rather than read from the module under test.
#:
#: A GUARD MAY NOT ITERATE THE THING IT IS GUARDING. The first version of
#: ``test_the_affix_list_is_observable`` looped over ``CLUB_INITIALISMS``
#: itself, so emptying that constant emptied the loop, the body never ran, and
#: the test PASSED — measured, not supposed: with ``CLUB_INITIALISMS =
#: frozenset()`` the guard written to catch exactly that exited 0. The mutation
#: battery scored the mutant killed only because a different test caught it.
#:
#: Iterating this literal fixes it twice over: the loop body runs whatever the
#: production constant says, and the equality assertion below fails the moment
#: the two lists differ in either direction — an affix deleted, or one added
#: without a real row to justify it (see the constant's own comment).
EXPECTED_CLUB_INITIALISMS = frozenset({"fc", "sc", "ac", "bc", "cf", "ca", "rc"})


def _record(home: dict, away: dict, **kwargs) -> AuthorityRecord:
    """An ESPN record built the way the production path builds one.

    Goes through :func:`authority_names` rather than taking name sets directly,
    so a test of the widened vocabulary actually exercises the widening instead
    of asserting against a set the test itself wrote.
    """
    return AuthorityRecord(
        authority_id=kwargs.pop("authority_id", "401000000"),
        home_names=authority_names({"team": home}),
        away_names=authority_names({"team": away}),
        label=f"{home.get('displayName')} v {away.get('displayName')}",
        **kwargs,
    )


def _row(home: str, away: str) -> CandidateRow:
    return CandidateRow(
        event_id=1,
        sport_key="americanfootball_ncaaf",
        home_team_name=home,
        away_team_name=away,
    )


# ── 1. THE MOTIVATING CASES ─────────────────────────────────────────────────
# Each pair is a row that read `teams_disagree` on production on 2026-09-03,
# with ESPN's competitor block as ESPN actually published it.

# Copied from ESPN's live summary for event 1133701 on 2026-09-03, INCLUDING
# the field layout, which is the point: the AFL puts the PLACE in `name` and the
# MASCOT in `nickname`, the reverse of NCAAF. A tidied-up fixture that pretended
# `location` was populated would have hidden the defect these two rows found.
AFL_HAWTHORN = {
    "displayName": "Hawthorn",
    "shortDisplayName": None,
    "location": None,
    "name": "Hawthorn",
    "nickname": "Hawks",
    "abbreviation": "HAW",
}
AFL_FREMANTLE = {
    "displayName": "Fremantle",
    "shortDisplayName": None,
    "location": None,
    "name": "Fremantle",
    "nickname": "Dockers",
    "abbreviation": "FRE",
}
UMASS = {
    "displayName": "Massachusetts Minutemen",
    "shortDisplayName": "Massachusetts",
    "location": "Massachusetts",
    "name": "Minutemen",
    "nickname": "UMass",
    "abbreviation": "MASS",
}
LIU = {
    "displayName": "Long Island University Sharks",
    "shortDisplayName": "Long Island University",
    "location": "Long Island University",
    "name": "Sharks",
    "nickname": "Long Island",
    "abbreviation": "LIU",
}
RUTGERS = {
    "displayName": "Rutgers Scarlet Knights",
    "shortDisplayName": "Rutgers",
    "location": "Rutgers",
    "name": "Scarlet Knights",
    "abbreviation": "RUTG",
}


@pytest.mark.parametrize(
    "ours,espn_block",
    [
        # The AFL: ESPN's displayName is the LOCATION alone, so nothing it
        # publishes is the name every feed uses.
        ("Hawthorn Hawks", AFL_HAWTHORN),
        ("Fremantle Dockers", AFL_FREMANTLE),
        # nickname + name, and abbreviation + name.
        ("UMass Minutemen", UMASS),
        ("LIU Sharks", LIU),
    ],
)
def test_composition_reaches_names_espn_implies_but_never_prints(ours, espn_block):
    assert canonical_forms(ours) & (
        authority_names({"team": espn_block}) | composed_forms(espn_block)
    )


def test_composition_does_not_double_the_mascot():
    """``Rutgers Scarlet Knights`` + ``Scarlet Knights`` is nobody's name.

    Composing ``location`` with ``name`` legitimately reproduces ESPN's own
    ``displayName`` here, and that is fine — it is the same string, so the set
    does not grow. What must never appear is a place form that ALREADY ends in
    the mascot getting the mascot again.
    """
    composed = composed_forms(RUTGERS)
    assert "rutgers scarlet knights" in composed
    assert not any(
        form.endswith("scarlet knights scarlet knights") for form in composed
    )

    # The shape the guard is really for: a feed whose location field is the
    # full name. Composing it must be skipped, not appended to.
    full_in_location = {
        "displayName": "Rutgers Scarlet Knights",
        "location": "Rutgers Scarlet Knights",
        "name": "Scarlet Knights",
    }
    assert composed_forms(full_in_location) == frozenset()


@pytest.mark.parametrize(
    "ours,theirs",
    [
        # Punctuation and spelling.
        ("Arkansas Pine Bluff Golden Lions", "Arkansas-Pine Bluff Golden Lions"),
        ("Hawaii Rainbow Warriors", "Hawai'i Rainbow Warriors"),
        ("Louisiana Ragin Cajuns", "Louisiana Ragin' Cajuns"),
        ("Brighton and Hove Albion", "Brighton & Hove Albion"),
        # A leading article.
        ("Citadel Bulldogs", "The Citadel Bulldogs"),
        # Club initialisms, in both directions and both positions.
        ("Houston Dynamo", "Houston Dynamo FC"),
        ("Chicago Fire", "Chicago Fire FC"),
        ("Columbus Crew SC", "Columbus Crew"),
        ("Vancouver Whitecaps FC", "Vancouver Whitecaps"),
        ("Atalanta BC", "Atalanta"),
        ("Le Mans FC", "Le Mans"),
        ("Le Havre", "Le Havre AC"),
        ("Elche CF", "Elche"),
        ("CA Osasuna", "Osasuna"),
        ("RC Lens", "Lens"),
        ("FC Schalke 04", "Schalke 04"),
    ],
)
def test_the_same_club_spelled_two_ways_agrees(ours, theirs):
    assert canonical_forms(ours) & canonical_forms(theirs)


# ── 2. THE FUSIONS THE SWEEP FOUND, PINNED SO THEY CANNOT RETURN ────────────


def test_the_mis_anchor_2792_still_disagrees():
    """E416569 — the one real finding among 52 disagreements. Must never agree.

    Our row is Ohio State @ Texas; the anchor it wears is Texas v Texas State.
    ``Texas`` matches ``Texas``, so the whole verdict rests on the rule keeping
    ``Ohio State Buckeyes`` away from ``Texas State Bobcats`` — which is exactly
    what a token-overlap or shared-prefix rule would fail to do.
    """
    record = _record(
        {
            "displayName": "Texas Longhorns",
            "location": "Texas",
            "name": "Longhorns",
            "shortDisplayName": "Texas",
            "abbreviation": "TEX",
        },
        {
            "displayName": "Texas State Bobcats",
            "location": "Texas State",
            "name": "Bobcats",
            "shortDisplayName": "Texas St",
            "abbreviation": "TXST",
        },
    )
    agrees, _inverted, _channel = _teams_agree(
        _row("Texas Longhorns", "Ohio State Buckeyes"), record
    )
    assert agrees is False


@pytest.mark.parametrize(
    "one,other",
    [
        # The trailing-year rule that shipped in the first draft, and the two
        # Georgian clubs that killed it. Nothing may reduce these together.
        ("Iberia 1999", "Iberia 2010"),
        # FC Barcelona is not Barcelona SC of Guayaquil.
        ("Barcelona", "Barcelona SC"),
        # Paris FC is not Paris Saint-Germain.
        ("Paris FC", "Paris Saint-Germain"),
        # Two schools that share a mascot and a word.
        ("Ohio State Buckeyes", "Texas State Bobcats"),
        ("Michigan Wolverines", "Michigan State Spartans"),
        ("Air Force Falcons", "Atlanta Falcons"),
        ("Eastern Kentucky Colonels", "Kentucky Wildcats"),
    ],
)
def test_two_different_teams_never_share_a_form(one, other):
    assert not (canonical_forms(one) & canonical_forms(other))


#: ESPN's real competitor blocks for the three groups where the widening
#: changes what gets written, copied from production on 2026-09-03. The
#: composition that rescues each row is the `nickname`/`abbreviation` one, which
#: only a real block carries — a tidied fixture would make this test pass for
#: the wrong reason.
CSU_NORTHRIDGE = {
    "displayName": "Cal State Northridge Matadors",
    "shortDisplayName": None,
    "location": "Cal State Northridge",
    "name": "Matadors",
    "nickname": "CSU Northridge",
    "abbreviation": "CSUN",
}
LIU_SHARKS = {
    "displayName": "Long Island University Sharks",
    "shortDisplayName": None,
    "location": "Long Island University",
    "name": "Sharks",
    "nickname": "Long Island",
    "abbreviation": "LIU",
}


@pytest.mark.parametrize(
    "authority_id,espn_block,ours_shell,ours_real",
    [
        (
            "401856329",
            CSU_NORTHRIDGE,
            "Cal State Northridge Matadors",
            "CSU Northridge Matadors",
        ),
        ("401869703", LIU_SHARKS, "Long Island University Sharks", "LIU Sharks"),
        ("401869705", LIU_SHARKS, "Long Island University Sharks", "LIU Sharks"),
    ],
)
def test_the_widening_moves_the_anchor_off_the_empty_duplicate(
    authority_id, espn_block, ours_shell, ours_real
):
    """The vocabulary gap was giving the authority id to the wrong twin.

    Each of these groups holds two rows for one game: a bare shell spelled ESPN's
    way, with no external id and no dependents, and the row a source actually
    created — carrying the odds snapshots and futures markets a user sees —
    spelled the short way (``CSU Northridge``, ``LIU``).

    Under the exact rule only the shell was eligible to keep the id, because the
    real row's name was not in ESPN's vocabulary. So the repair would have
    unstamped the row with 42 dependents and anchored the one with none. With
    both rows eligible the ordinary keeper tie-break runs and the sourced,
    dependent-carrying row wins.

    This is the widening paying out somewhere it was not aimed: it was built for
    the schedule rail, and it fixes a write in the collisions rail.
    """
    from app.utils.authority_id_collisions import decide_group

    opponent = {
        "displayName": "Fairleigh Dickinson Knights",
        "location": "Fairleigh Dickinson",
        "name": "Knights",
        "nickname": "FDU",
        "abbreviation": "FDU",
    }
    espn = AuthorityRecord(
        authority_id=authority_id,
        home_names=authority_names({"team": espn_block}),
        away_names=authority_names({"team": opponent}),
        label=f"{espn_block['displayName']} v Fairleigh Dickinson Knights",
    )
    shell = CandidateRow(
        event_id=1,
        sport_key="baseball_ncaa",
        home_team_name=ours_shell,
        away_team_name="Fairleigh Dickinson Knights",
        weight=0,
        has_external_id=False,
    )
    real = CandidateRow(
        event_id=2,
        sport_key="baseball_ncaa",
        home_team_name=ours_real,
        away_team_name="Fairleigh Dickinson Knights",
        weight=42,
        has_external_id=True,
    )

    decision = decide_group(espn, [shell, real], authority_id=authority_id)
    assert (
        decision.keep_event_id == 2
    ), "the anchor must stay on the row with the markets"
    assert decision.unstamp_event_ids == (1,)


def test_a_name_is_never_reduced_away_entirely():
    """A form set may be empty, but it may never contain the empty string.

    Two names both reduced to ``""`` would compare equal, which is the worst
    possible fusion: every blank matches every other blank.
    """
    for name in ("FC", "The", "SC", "the fc", "", "   ", None):
        assert "" not in canonical_forms(name)


def test_reduction_stops_before_it_eats_the_last_token():
    """The invariant the previous test cannot see, because two guards overlap.

    ``canonical_forms`` drops a falsy reduction before adding it, so a stripper
    that happily consumed every token would still never emit ``""`` — and a
    mutation removing the last-token guard SURVIVED a green suite on exactly
    that redundancy. What is actually observable is the reduction that should
    have been produced going MISSING: ``The FC`` must still offer ``fc``.
    """
    assert canonical_forms("The FC") == frozenset({"the fc", "fc"})
    assert canonical_forms("FC") == frozenset({"fc"})


def test_contested_residuals_are_refused_not_produced():
    for residual in CONTESTED_RESIDUALS:
        assert residual not in canonical_forms(f"{residual} FC")
        assert residual not in canonical_forms(f"FC {residual}")


# ── 3. THE SWEEP, AND THE ASYMMETRIC CASES THAT OBSERVE THE WORD LISTS ──────


def _load_corpus() -> dict[str, list[str]]:
    with gzip.open(CORPUS, "rt") as handle:
        return json.load(handle)


def test_no_new_fusion_across_the_real_corpus():
    """Every distinct team name on production, per sport. The real guard.

    Bucketed by canonical form rather than compared pairwise — a collision is a
    bucket reached by two names that did NOT already normalize the same, which
    is O(n) instead of 23,563 choose 2. Re-derive the fixture and this list with
    ``scripts/audit_authority_name_forms.py``.
    """
    corpus = _load_corpus()
    assert (
        sum(len(v) for v in corpus.values()) > 20000
    ), "the fixture is the guard; a short one proves nothing"

    found: dict[str, set[str]] = defaultdict(set)
    for sport, names in corpus.items():
        buckets: dict[str, set[str]] = defaultdict(set)
        for name in names:
            base = normalize_team_name_for_matching(name)
            if not base:
                continue
            for form in canonical_forms(name) | synonym_forms(name, sport):
                buckets[form].add(base)
        for form, bases in buckets.items():
            if len(bases) > 1:
                found[form] |= bases

    unexpected = {
        f: sorted(b) for f, b in found.items() if f not in EXPECTED_COLLISIONS
    }
    assert not unexpected, (
        "the widening fused names that were distinct. Each one is either two "
        f"spellings of one team (add it to EXPECTED_COLLISIONS) or a bug: {unexpected}"
    )
    widened = {
        f: sorted(b) for f, b in found.items() if set(b) != EXPECTED_COLLISIONS[f]
    }
    assert (
        not widened
    ), f"a known collision now covers more names than it did: {widened}"


def test_the_affix_list_is_observable():
    """An ASYMMETRIC pair per initialism — the only shape that can see the list.

    Both sides of ``_teams_agree`` go through ``canonical_forms``, so a case
    that gives both sides the same affix agrees whether or not the affix is
    listed. Emptying ``CLUB_INITIALISMS`` must fail this test; it would survive
    a suite of symmetric cases untouched.

    The iteration is over :data:`EXPECTED_CLUB_INITIALISMS`, the test file's own
    literal, and NOT over the production constant — see that literal's comment
    for the vacuity this avoids and for the measurement that found it.
    """
    assert CLUB_INITIALISMS == EXPECTED_CLUB_INITIALISMS, (
        "the shipped affix list no longer matches the one this suite proves. "
        "Every entry needs a production row that exercises it — re-derive with "
        "scripts/audit_authority_name_forms.py, then update the literal here"
    )
    for affix in EXPECTED_CLUB_INITIALISMS:
        assert canonical_forms(f"{affix.upper()} Rovers") & canonical_forms(
            "Rovers"
        ), affix
        assert canonical_forms(f"Rovers {affix.upper()}") & canonical_forms(
            "Rovers"
        ), affix
    # And the control: a token that is NOT a club initialism must keep them apart.
    assert not (canonical_forms("United Rovers") & canonical_forms("Rovers"))


def test_composed_keys_are_observable():
    """One asymmetric case per composable key, for the same reason."""
    for key in ("location", "shortDisplayName", "nickname", "abbreviation"):
        block = {"name": "Sharks", key: "Bayside", "displayName": "Something Else"}
        assert "bayside sharks" in composed_forms(block), key


def test_composition_is_order_insensitive():
    """Because ESPN's own field layout is not consistent between leagues.

    NCAAF: ``name`` is the mascot. AFL: ``name`` is the place and ``nickname``
    is the mascot. A composition that assumed one layout emitted ``hawks
    hawthorn`` for Hawthorn and left both AFL rows disagreeing through a census
    that was supposed to have fixed them.
    """
    ncaaf = {"location": "Massachusetts", "name": "Minutemen", "nickname": "UMass"}
    afl = {"name": "Hawthorn", "nickname": "Hawks"}
    assert "massachusetts minutemen" in composed_forms(ncaaf)
    assert "umass minutemen" in composed_forms(ncaaf)
    assert "hawthorn hawks" in composed_forms(afl)


def test_composition_never_stutters_a_repeated_part():
    """A part that already contains the other is not composed with it."""
    block = {
        "displayName": "Rutgers Scarlet Knights",
        "location": "Rutgers",
        "shortDisplayName": "Rutgers",
        "name": "Scarlet Knights",
    }
    for form in composed_forms(block):
        parts = form.split()
        assert len(parts) == len(set(parts)) or "rutgers rutgers" not in form
    assert not any(form.count("scarlet knights") > 1 for form in composed_forms(block))


def test_the_widening_only_ever_adds_agreement():
    """No name loses the agreement the exact rule already gave it.

    Every form set contains the plain normalized name, so a row that matched
    ESPN exactly before still does. Asserted over the whole corpus rather than
    argued, because "it can only add" is the kind of claim that stops being
    true one refactor later.
    """
    for names in _load_corpus().values():
        for name in names:
            base = normalize_team_name_for_matching(name)
            if base:
                assert base in canonical_forms(name), name
