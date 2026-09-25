"""Queue #246 Item 1a — curated team-alias union merge is order-preserving,
case-insensitively deduped, and idempotent."""
from app.config.team_aliases import CURATED_TEAM_ALIASES
from scripts.backfill_curated_team_aliases import merge_aliases


def test_appends_new_alias_preserving_existing():
    assert merge_aliases(["Patriots"], ["pats"]) == ["Patriots", "pats"]


def test_none_existing():
    assert merge_aliases(None, ["revs"]) == ["revs"]


def test_case_insensitive_dedup():
    assert merge_aliases(["New England", "Revs"], ["revs"]) == ["New England", "Revs"]


def test_idempotent():
    once = merge_aliases(["Patriots"], ["pats"])
    twice = merge_aliases(once, ["pats"])
    assert once == twice == ["Patriots", "pats"]


def test_curated_map_is_franchise_scoped_and_wellformed():
    # Every key is (sport_key, name); every alias is a non-empty lowercase string.
    for key, aliases in CURATED_TEAM_ALIASES.items():
        assert isinstance(key, tuple) and len(key) == 2
        sport_key, name = key
        assert sport_key and name
        assert aliases and all(a and a == a.lower() for a in aliases)


def test_no_alias_collides_across_franchises():
    """An alias may name ONE club in several sports; never two different clubs.

    #8084 sharpened this from "no alias appears twice". `north carolina state` is
    the same school's own formal name on three rows — `basketball_wncaab`,
    `americanfootball_ncaaf`, `basketball_ncaab` — all spelled `NC State Wolfpack`
    and all anchored to espn 152, so it is one club with three sport rows rather
    than the cross-franchise fan-out this guard exists to stop. The protection that
    matters is unchanged and still asserted below: two DIFFERENT team names sharing
    an alias remains a failure, which is the case that would make search worse
    (the file's own "multiple Patriots" example).
    """
    seen: dict[str, str] = {}
    for (sport_key, name), aliases in CURATED_TEAM_ALIASES.items():
        for a in aliases:
            if a in seen:
                assert seen[a] == name, (
                    f"alias {a!r} maps to two different clubs: "
                    f"{seen[a]!r} and {name!r}"
                )
            seen[a] = name


def test_an_alias_claimed_by_two_clubs_still_fails_the_guard():
    """The guard above must still catch the case it was written for.

    Asserted on a constructed map rather than by trusting the real one to stay
    clean: a guard whose failing branch is never exercised is a guard that passes
    because the population is currently innocent, not because it works.
    """
    fake = {
        ("americanfootball_nfl", "New England Patriots"): ["pats"],
        ("basketball_ncaab", "George Mason Patriots"): ["pats"],
    }
    seen: dict[str, str] = {}
    collided = False
    for (_sport_key, name), aliases in fake.items():
        for a in aliases:
            if a in seen and seen[a] != name:
                collided = True
            seen[a] = name
    assert collided, "two different clubs sharing an alias must be a failure"


def test_nicknames_two_franchises_share_are_not_curated_8685():
    """#8685 added eleven nicknames and deliberately refused six.

    Each of these is how fans of TWO franchises type their team — `avs` is the
    Colorado Avalanche and AVS Futebol, `caps` the Capitals and the Whitecaps,
    `cavs` Cleveland and Virginia, `canes` Carolina and Miami, `bolts` the
    Lightning and the Chargers, `wolves` Minnesota and Wolverhampton. A curated
    alias is scoped to ONE franchise, so adding any of them hands one fan base's
    word to the other. This file's rule: an alias that matches two franchises
    makes search worse, not better.
    """
    curated = {a.lower() for aliases in CURATED_TEAM_ALIASES.values() for a in aliases}
    for shared in ("avs", "caps", "cavs", "canes", "bolts", "wolves"):
        assert shared not in curated, f"{shared!r} names two franchises"
