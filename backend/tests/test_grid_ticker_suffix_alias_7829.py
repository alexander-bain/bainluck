"""#7829 — one id spelled two ways: Kalshi's `TXAM` and our `TA&M`.

#7821 settled ambiguous playoff-grid keys with the venue's own ticker suffix
matched against `Team.abbreviation`. That anchor is exact by design, so it
declines whenever the venue and we spell the same identifier differently — and
`texas a&m` was the one live NCAAB family it left unrepaired. The reader saw
Texas A&M Aggies with a championship price of 0.7% and all five bracket columns
blank, because the length answer (`texas a&m-cc islanders`) is not a served row.

THE TRAP THESE TESTS ARE BUILT AROUND: the tempting repair is a fuzzy or
substring comparison between suffix and abbreviation — `TXAM` "contains" `TAM`.
That reintroduces precisely the guessing #7821 removed, and it is unsafe here
because the abbreviation column is dirty on production: *California Golden
Bears* carries `MIA` and *Florida A&M Rattlers* carries `MSU`. So the fix is a
DECLARED equality, and the tests below are written to fail if anyone later
relaxes it into a comparison: `TAMU` is a near-miss that must keep declining.

MEASURED BLAST RADIUS (live grid data, 2026-09-21, all 14 grid-serving leagues):
`TXAM` is the canon ticker suffix of exactly two grid keys — NCAAB `texas a&m`
(2 candidates, so the resolver runs: this is the one binding that changes) and
NCAAF `texas a&m` (1 candidate, so the resolver is never called). Women's
college basketball ingests no Texas A&M outcome; no other grid league ingests
college markets. Candidate generation is untouched, so LOST=0 / ADDED=0 holds by
construction and CHANGED is that single key.
"""

import pytest

from app.routes.playoffs import (
    _TICKER_SUFFIX_ALIASES,
    _canon_ticker,
    _resolve_ambiguous_merge,
)

# The real abbreviations, as measured on production 2026-09-21.
# `texas a&m-cc islanders` genuinely has NO abbreviation on any of its three
# rows — that absence is data, and it is why the alias cannot produce a second
# hit in this family.
ABBREV = {
    "texas a&m aggies": "TA&M",
    "miami hurricanes": "MIA",
    "miami (oh) redhawks": "M-OH",
}

# Longest-first, exactly as the route builds it, so element 0 is the old answer.
TEXAS_AM = ["texas a&m-cc islanders", "texas a&m aggies"]
MIAMI = ["miami (oh) redhawks", "miami hurricanes"]


def _resolve(short, candidates, suffixes, abbrev=ABBREV):
    return _resolve_ambiguous_merge(short, candidates, {short: set(suffixes)}, abbrev)


# ---------------------------------------------------------------------------
# The ship
# ---------------------------------------------------------------------------

def test_declared_alias_settles_texas_am_onto_the_aggies():
    """The live NCAAB specimen: `TXAM` now reaches `TA&M`, so the Aggies bind.

    Before this fix the same inputs returned `texas a&m-cc islanders`, an
    unserved row, and the Aggies' five bracket cells were blank.
    """
    assert _resolve("texas a&m", TEXAS_AM, {"TXAM"}) == "texas a&m aggies"


def test_the_alias_is_what_does_the_work():
    """Strip the alias and the same call falls back — so the map is load-bearing.

    Without this, the test above would still pass if someone made the anchor
    loose enough to match `TXAM` to `TA&M` by other means, which is the outcome
    this whole file exists to prevent.
    """
    assert _TICKER_SUFFIX_ALIASES["TXAM"] == "TAM"
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.routes.playoffs._TICKER_SUFFIX_ALIASES", {}, raising=True)
        assert _resolve("texas a&m", TEXAS_AM, {"TXAM"}) == "texas a&m-cc islanders"


# ---------------------------------------------------------------------------
# The refusals the alias must NOT relax
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("near_miss", ["TAMU", "TXA", "TAM1", "XAM", "TEXASAM"])
def test_a_near_miss_suffix_still_declines(near_miss):
    """An undeclared suffix may not resolve, however much it looks like `TAM`.

    `TAMU` is the real Texas A&M University initialism and the exact string a
    substring or edit-distance rule would admit. Every one of these must keep
    returning `candidates[0]`.
    """
    assert _resolve("texas a&m", TEXAS_AM, {near_miss}) == "texas a&m-cc islanders"


def test_an_aliased_suffix_that_hits_two_candidates_still_fails_closed():
    """Widening the SET must not weaken the exactly-one-hit rule.

    If both candidates canon to the aliased value we still do not know which
    school the venue meant, so the answer stays `candidates[0]`.
    """
    both = {"texas a&m-cc islanders": "TAM", "texas a&m aggies": "TA&M"}
    assert _resolve("texas a&m", TEXAS_AM, {"TXAM"}, both) == "texas a&m-cc islanders"


def test_ncaaf_miami_still_declines_because_its_key_collects_two_schools():
    """#7829's other half, pinned as still-broken on purpose.

    On NCAAF the key `miami` carries BOTH `MIA` and `MOH`, because
    `_normalize_team_name` reduces the venue's `Miami (FL)` and `Miami (OH)` to
    the same string. Both candidates then hit, so the anchor fails closed. No
    alias can repair this: the key is collapsed upstream of the predicate, and
    the fix belongs to the grid register (one key per source outcome). A change
    that makes this assertion pass by picking a school is publishing Miami
    (OH)'s prices on Miami (FL) — a wrong number where today there is a blank.
    """
    assert _resolve("miami", MIAMI, {"MIA", "MOH"}) == "miami (oh) redhawks"


def test_unaliased_keys_are_untouched():
    """The ordinary #7821 path still behaves exactly as before."""
    assert _resolve("miami", MIAMI, {"MIA"}) == "miami hurricanes"
    assert _resolve("miami", MIAMI, set()) == "miami (oh) redhawks"


# ---------------------------------------------------------------------------
# The structural guard — the likeliest way to get the map wrong
# ---------------------------------------------------------------------------

def test_every_alias_entry_is_already_canonical():
    """A non-canonical entry would silently never match, and never fail loudly.

    `{"TXAM": "TA&M"}` reads correctly to a human and is dead code: the lookup
    is done on canon suffixes and the comparison is against canon abbreviations,
    so an `&` on either side of the map can never be hit. Assert the shape
    rather than trusting the next editor to remember.
    """
    for key, value in _TICKER_SUFFIX_ALIASES.items():
        assert _canon_ticker(key) == key, f"alias key {key!r} is not canonical"
        assert _canon_ticker(value) == value, f"alias value {value!r} is not canonical"
        assert key != value, f"alias {key!r} maps to itself and does nothing"
