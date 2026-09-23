"""#7829 part 1 — the helpers behind "Miami (FL) and Miami (OH) are two rows".

🔴 THIS FILE IS NOT THE PROOF. The proof is
``tests/integration/test_grid_miami_identity_7829_pg.py``, which drives the
real route on real PostgreSQL and is red on base. A helper can be perfect and
uncalled; that gate is what says the route calls it. This file pins the
helpers' refusals so that a later edit which relaxes one fails loudly here
with a sentence attached, instead of failing there with a payload diff.

THE TRAP THESE TESTS ARE BUILT AROUND: the tempting fix was to make ``miami``
resolve — by preferring a candidate, by loosening the exactly-one-hit rule, or
by a fuzzier abbreviation comparison. Every one of those publishes Miami
(OH)'s prices on Miami (FL) (the #7821 defect re-created) and none of them
touches the cause, which is that the two schools shared one key before any
resolver ran. So:

* :func:`_resolve_ambiguous_merge` is BYTE-FOR-BYTE unchanged in behaviour —
  the pooled-input control from ``test_grid_ticker_suffix_alias_7829.py``
  still declines, and it is re-asserted here so the two files cannot drift.
* :func:`_grid_identity_key` keeps ONLY a trailing two-letter US state code.
  ``(W)`` and ``(Res)`` are still stripped; an interior parenthetical is still
  untouched; every name without a trailing state code keys exactly as before.
* :func:`_resolve_qualified_merge` never returns ``candidates[0]`` for being
  first. It returns an identity — textual or ticker — or ``None``.
"""

import pytest

from app.routes.playoffs import (
    _grid_identity_key,
    _normalize_team_name,
    _qualified_key_base,
    _resolve_ambiguous_merge,
    _resolve_qualified_merge,
    _ticker_anchor_hits,
)

# Real production abbreviations, 2026-09-21, dirt included.
ABBREV = {
    "miami hurricanes": "MIA",
    "miami (oh) redhawks": "M-OH",
    "california golden bears": "MIA",   # yes, really
    "ohio state buckeyes": "PSU",       # yes, really
    "michigan state spartans": "WMU",   # yes, really
    "florida a&m rattlers": "MSU",      # yes, really
    "texas a&m aggies": "TA&M",
    "north carolina tar heels": "UNC",
}
MIAMI = ["miami (oh) redhawks", "miami hurricanes"]  # longest-first, as the route builds it


def _q(short, cands, suffixes, abbrev=ABBREV):
    return _resolve_qualified_merge(short, cands, {short: set(suffixes)}, abbrev)


# ---------------------------------------------------------------------------
# the key
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "name,expected",
    [
        ("Miami (FL)", "miami (fl)"),
        ("Miami (OH)", "miami (oh)"),
        ("miami (fl)", "miami (fl)"),
        ("Loyola (IL)", "loyola (il)"),
        ("St. Francis (PA)", "st francis (pa)"),
    ],
)
def test_a_trailing_state_qualifier_survives_the_key(name, expected):
    assert _grid_identity_key(name) == expected
    # ...and it is a genuinely different key from the unqualified spelling.
    assert _grid_identity_key(name) != _normalize_team_name(name)


@pytest.mark.parametrize(
    "name",
    [
        "Miami (OH) RedHawks",          # interior parenthetical: untouched, as before
        "Borussia Dortmund (Res)",      # reserve marker: stripped, as before
        "Chelsea (W)",                  # women's marker: stripped, as before
        "Team (XX)",                    # not a US state: stripped, as before
        "Miami Hurricanes",
        "St. Louis Cardinals",
        "Texas A&M Aggies",
        "North Carolina",
        "Miami",
    ],
)
def test_every_other_name_keys_exactly_as_it_always_has(name):
    """The blast radius is the set of names ending in a real state code. For
    everything else the key is byte-identical to `_normalize_team_name`, so no
    other key in any grid moves."""
    assert _grid_identity_key(name) == _normalize_team_name(name)


def test_qualified_key_base_reads_the_qualifier_and_nothing_else():
    assert _qualified_key_base("miami (fl)") == "miami"
    assert _qualified_key_base("miami (oh)") == "miami"
    assert _qualified_key_base("miami (oh) redhawks") is None
    assert _qualified_key_base("miami") is None
    assert _qualified_key_base("team (xx)") is None
    assert _qualified_key_base("borussia dortmund (res)") is None


# ---------------------------------------------------------------------------
# the qualified resolver — identities only
# ---------------------------------------------------------------------------

def test_miami_fl_binds_to_the_hurricanes_by_its_own_ticker():
    """The live NCAAF specimen, per key: `miami (fl)` carries ONLY `MIA`."""
    assert _q("miami (fl)", MIAMI, {"MIA"}) == "miami hurricanes"


def test_miami_oh_binds_to_the_redhawks_by_its_own_text():
    """`miami (oh)` is a prefix of exactly one candidate; no abbreviation needed."""
    assert _q("miami (oh)", MIAMI, set()) == "miami (oh) redhawks"
    assert _q("miami (oh)", MIAMI, {"MOH"}) == "miami (oh) redhawks"
    # Even with a corrupt abbreviation column, the text wins.
    assert _q("miami (oh)", MIAMI, {"MOH"}, {}) == "miami (oh) redhawks"


def test_no_anchor_means_no_merge_never_the_longest():
    """The refusal that stops #7821 being re-created.

    `candidates[0]` is Miami (OH). A qualified key with nothing to anchor on
    may not bind to it because it is longest, and may not bind to the
    Hurricanes because it is shorter. It binds to nothing.
    """
    assert _q("miami (fl)", MIAMI, set()) is None
    assert _q("miami (fl)", MIAMI, {"ZZZ"}) is None
    assert _q("miami (fl)", MIAMI, set(), {}) is None


def test_two_ticker_hits_still_fail_closed():
    """The exactly-one-hit rule is inherited, not relaxed."""
    both = {"miami (oh) redhawks": "MIA", "miami hurricanes": "MIA"}
    assert _q("miami (fl)", MIAMI, {"MIA"}, both) is None


def test_a_lone_wrong_candidate_is_refused():
    """Miami (OH) absent from the other source: `miami (oh)`'s only candidate
    is the Hurricanes. Base bound a single candidate unconditionally; here the
    ticker says MOH, the Hurricanes say MIA, and the leg stays unbound."""
    assert _q("miami (oh)", ["miami hurricanes"], {"MOH"}) is None
    # ...while the same lone candidate WITH a matching identity does bind.
    assert _q("miami (fl)", ["miami hurricanes"], {"MIA"}) == "miami hurricanes"


@pytest.mark.parametrize("dirty_suffix", ["PSU", "WMU", "MSU", "CAL"])
def test_dirty_abbreviations_cannot_reach_outside_the_name_family(dirty_suffix):
    """California carries `MIA`, Ohio State `PSU`, Michigan State `WMU`,
    Florida A&M `MSU`. None is a Miami candidate, so no suffix can pull one in;
    the abbreviation only ever chooses among candidates a NAME rule produced."""
    assert _q("miami (fl)", MIAMI, {dirty_suffix}) is None
    assert "california golden bears" not in MIAMI


def test_texas_am_alias_still_flows_through_the_shared_hit_predicate():
    """#7829 part 2's declared alias is one predicate for both resolvers."""
    cands = ["texas a&m-cc islanders", "texas a&m aggies"]
    assert _ticker_anchor_hits("texas a&m", cands, {"texas a&m": {"TXAM"}}, ABBREV) == [
        "texas a&m aggies"
    ]
    assert _ticker_anchor_hits("texas a&m", cands, {"texas a&m": {"TAMU"}}, ABBREV) == []


# ---------------------------------------------------------------------------
# the old resolver is untouched — the control from the alias file, re-pinned
# ---------------------------------------------------------------------------

def test_the_pooled_input_control_still_declines():
    """If someone "fixes" Miami by making the OLD resolver pick a school on the
    pooled `miami` key, this fails — and so does the alias file's control."""
    pooled = {"miami": {"MIA", "MOH"}}
    assert _resolve_ambiguous_merge("miami", MIAMI, pooled, ABBREV) == "miami (oh) redhawks"
    assert _resolve_ambiguous_merge("miami", MIAMI, {"miami": {"MIA"}}, ABBREV) == "miami hurricanes"
    assert _resolve_ambiguous_merge("miami", MIAMI, {}, ABBREV) == "miami (oh) redhawks"


def test_the_old_resolver_and_the_hit_helper_agree_on_every_shape():
    """`_ticker_anchor_hits` was lifted out of `_resolve_ambiguous_merge`; the
    old function must still equal `hits[0] if len(hits) == 1 else cands[0]`."""
    for suffixes in (set(), {"MIA"}, {"MOH"}, {"MIA", "MOH"}, {"ZZZ"}, {"TXAM"}):
        hits = _ticker_anchor_hits("miami", MIAMI, {"miami": suffixes}, ABBREV)
        expected = hits[0] if len(hits) == 1 else MIAMI[0]
        assert _resolve_ambiguous_merge("miami", MIAMI, {"miami": suffixes}, ABBREV) == expected
