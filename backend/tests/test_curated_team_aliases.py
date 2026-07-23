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
    # An alias mapping to two different franchises would make search worse.
    seen: dict[str, tuple] = {}
    for key, aliases in CURATED_TEAM_ALIASES.items():
        for a in aliases:
            assert a not in seen, f"alias {a!r} maps to {seen[a]} and {key}"
            seen[a] = key
