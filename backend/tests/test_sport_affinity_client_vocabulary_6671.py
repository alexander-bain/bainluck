"""The key vocabulary a client must use to read and write sport affinities (#6671).

`GET /api/me/preferences` does not serve what is stored: it serves
`_compress_sport_affinities(...)`, whose keys are the *categories* of
``SPORT_KEY_TO_CATEGORY`` (``nfl``, ``college_football``, ``golf_pga`` ...), not
the backend sport keys (``americanfootball_nfl``, ``golf_us_open_winner`` ...)
and not whatever spelling a client happens to use in its own grid.

A client that looks a sport up under a key this endpoint never serves gets
``None`` and renders its "no opinion" state — silently, for every user, because
a missing key in a dict is not an error. That is #6671: the iPhone Settings grid
reads ``football``/``cfb``/``basketball``/``cbb``/``golf``/``aussierules`` and so
shows "Nah" on six tiles whatever the reader actually picked. The repair is
client-side (the web onboarding already sends this vocabulary), which is exactly
why the vocabulary itself needs to be written down somewhere that fails when it
moves — prose in an issue cannot do that.

These are contract tests, not a snapshot of a defect: all three pass today.
"""

import pytest

from app.routes.user import (
    SPORT_AFFINITY_MAPPING,
    SPORT_KEY_TO_CATEGORY,
    _compress_sport_affinities,
    _expand_sport_affinities,
)
from app.utils.personalization import _lookup_sport_affinity

#: Every key `GET /api/me/preferences` can put in `sport_affinities`. This is the
#: list a client's preference grid must be keyed on. Adding a sport means adding
#: it here deliberately — and a client that has not adopted the new key will show
#: its "no opinion" state for it, which is the cost this list exists to make visible.
SERVED_AFFINITY_VOCABULARY = {
    # sports — note the pro/college splits and the four golf tours
    "nfl",
    "college_football",
    "nba",
    "college_basketball",
    "baseball",
    "hockey",
    "soccer",
    "tennis",
    "golf_pga",
    "golf_dp_world",
    "golf_lpga",
    "golf_liv",
    "mma",
    "boxing",
    "cricket",
    "rugby",
    "aussierules",
    "motorsport",
    "esports",
    # beyond sports
    "politics",
    "entertainment",
    "crypto",
    "economics",
    "tech",
    "weather",
    "geopolitics",
    "culture",
}


def test_served_vocabulary_is_exactly_this_list():
    """The keys a client can read are pinned, so adding a sport is a decision."""
    assert set(SPORT_KEY_TO_CATEGORY.values()) == SERVED_AFFINITY_VOCABULARY


def test_every_served_key_is_accepted_back_on_write():
    """Read/write closure: a client PUTs the dict it GOT, so every served key must expand.

    `_expand_sport_affinities` passes an unrecognised key through verbatim
    (`user.py:172-174`), storing a key no feed lookup can ever reach — a write
    that returns 200 and changes nothing. A served key that is not also an
    accepted key is that bug waiting for the next `PUT`.
    """
    unaccepted = sorted(k for k in SERVED_AFFINITY_VOCABULARY if k not in SPORT_AFFINITY_MAPPING)
    assert unaccepted == []


def test_saving_the_served_dict_unchanged_does_not_move_a_stored_value():
    """A Settings screen that saves without edits must be a no-op on the feed's input.

    The round trip is lossy by construction — compression takes the MAX over each
    category, and `PUT` replaces the stored dict rather than merging it
    (`user.py:1053-1065`) — so "GET, change nothing, PUT" is the case that proves
    a save cannot quietly raise or drop a sport the reader never touched. Mixed
    values within one category (the four golf tours, the two college basketball
    keys) are the ones that would show it.
    """
    served = {
        "nfl": 1.0,
        "college_football": 0.1,
        "nba": 1.0,
        "college_basketball": 0.0,
        "baseball": 1.0,
        "hockey": 0.3,
        "soccer": 0.1,
        "tennis": 0.3,
        "golf_pga": 1.0,
        "golf_dp_world": 0.0,
        "golf_lpga": 0.0,
        "golf_liv": 0.0,
        "mma": 0.0,
        "boxing": 0.0,
        "cricket": 0.0,
        "rugby": 0.0,
        "politics": 1.0,
        "weather": 0.0,
    }
    stored = _expand_sport_affinities(served)
    resaved = _expand_sport_affinities(_compress_sport_affinities(stored))
    assert resaved == stored


#: Every `aussierules` sport_key an event can actually carry: the two in
#: `utils/sport_keys.py` plus the women's code, which is live (18 rows read
#: 2026-09-15, `tasks/polymarket.py:203`) without being in that map.
_LIVE_AUSSIERULES_SPORT_KEYS = [
    "aussierules_afl",
    "aussierules_aflw",
    "aussierules_other",
]


@pytest.mark.parametrize("sport_key", _LIVE_AUSSIERULES_SPORT_KEYS)
def test_giving_aussierules_a_mapping_does_not_move_what_the_feed_reads(sport_key):
    """Adding the category is a DISPLAY repair, so ranking must read the same.

    Before the mapping existed, `_expand_sport_affinities` passed `aussierules`
    through verbatim (`user.py`, the unrecognised-key branch) and the feed found
    it through `_lookup_sport_affinity`'s `affinity_key == root` fallback — so
    AFL already ranked correctly and only Settings was blind. With the mapping,
    the same tap stores three exact keys instead. Both shapes must answer the
    same for every live key, or a display fix has quietly become a ranking
    change (#6671).
    """
    before = _lookup_sport_affinity(sport_key, {"aussierules": 0.3})
    after = _lookup_sport_affinity(sport_key, _expand_sport_affinities({"aussierules": 0.3}))
    assert before == 0.3, "the pre-mapping pass-through shape must still be readable"
    assert after == before


def test_a_stored_aussierules_affinity_is_served_back_to_the_client():
    """The defect itself: the tile could be set and never read back.

    `_compress_sport_affinities` skips backend keys absent from
    `SPORT_KEY_TO_CATEGORY`, so before the mapping every `aussierules_*` key was
    dropped on the way out and the iPhone Settings tile rendered "Nah" for a
    reader who had rated AFL. Discriminating: delete the mapping entry and
    `compressed` is `{}`.
    """
    stored = _expand_sport_affinities({"aussierules": 0.3})
    assert set(stored) == set(_LIVE_AUSSIERULES_SPORT_KEYS)
    assert _compress_sport_affinities(stored) == {"aussierules": 0.3}
