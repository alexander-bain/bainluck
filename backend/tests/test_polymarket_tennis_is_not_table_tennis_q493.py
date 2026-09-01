"""Q493 — a US Open match is tennis, not table tennis.

Measured on production at `c3143bc2`: **639 open Polymarket markets carrying an
unambiguous real-tennis marker (`US Open ATP:`, `US Open WTA:`, `ATP`, `WTA`) were
stored with `llm_sport_category = 'table_tennis'`** — the entire live US Open main
draw among them, plus ITF M15 futures. They are on the wrong category page and in
the wrong calibration cohort, and `table_tennis` has no tile at all, so they are
invisible on the surface that exists to show what exists.

THE MECHANISM, read off the live Gamma event `945997`
(`US Open ATP: Ben Shelton vs Hubert Hurkacz`, tags `['Tennis', 'Sports', 'Games']`):
its 26 sub-markets include per-SET games totals — `Shelton vs. Hurkacz: Set 1 Games
O/U 8.5`. `_detect_racquet_game_stat` splits table tennis from tennis on a games
threshold of 10, which is right for a MATCH total (tennis runs 20-45) and wrong for a
SET total (a tennis set is 6-13 games). So a child prop parsed to `table_tennis`,
`detect_table_tennis_group` went True, and arm 1 of the cascade relabelled the whole
group — **overruling the `Tennis` tag Polymarket had already supplied.**

🔴 THE POINT, AND IT IS NOT ABOUT TENNIS. **The source told us the truth on BOTH
sides and neither answer was read.** Real Setka/TT-Cup events are tagged
`Table Tennis` + `Setka`; real ATP/WTA events are tagged `Tennis`. `table tennis`
was simply absent from `_TAG_TO_CATEGORY`, so a Setka event fell through to the
`sports` catch-all and could only ever be rescued by a numeric heuristic on its
child props — and that same heuristic, unguarded, then ate real tennis. Q493 reads
the tag on both sides, which makes #1230 STRONGER: Setka no longer depends on a
threshold at all.

Arm 1 keeps its job for the case it was actually written for — a bare
`Player vs. Player` title with NO usable tag, where the fallback would otherwise
guess baseball from summer seasonal inference (#1230's "baseball 7.4% link rate").
It is now gated on precisely that stated precondition.

GUARD DESIGN (Q491's lesson: delete the thing that would have retried anyway).
Each test below removes the OTHER half's ambient recovery, so a partial revert
cannot pass:
  * the Setka-tag tests pass a group whose child props CANNOT trip the heuristic
    (asserted in-test), so only the tag can produce the answer;
  * the tennis tests pass a group that DOES trip the heuristic, so only the gate
    can produce the answer.
"""

import pytest

from app.tasks.polymarket import (
    _SPORT_CATEGORIES,
    _TAG_TO_CATEGORY,
    _tags_to_category,
    resolve_event_category,
)
from app.utils.futures_categorization import detect_table_tennis_group


def _resolve(tags, title, group_names):
    """Drive the cascade the way `_process_polymarket_events` does."""
    category, sport = _tags_to_category(tags)
    cat, sport, arm = resolve_event_category(category, sport, title, group_names)
    return cat, sport, arm


# Verbatim from Gamma event 945997, 2026-09-01. The `Set 1 Games O/U 8.5` line is
# the one that trips the threshold; it is real tennis and it is why the whole draw
# was mislabelled.
US_OPEN_GROUP = [
    "US Open ATP: Ben Shelton vs Hubert Hurkacz",
    "Shelton vs. Hurkacz: Set 1 Games O/U 8.5",
    "Game Spread: Shelton (-3.5) vs Hurkacz (+3.5)",
    "Shelton vs. Hurkacz: Match O/U 40.5",
    "Set 1 Winner: Shelton vs Hurkacz",
]

# Verbatim from Gamma event 945534 — a genuine Setka Cup Moldova match.
SETKA_GROUP = [
    "Salaru Nicolae vs. Urechean Vadim",
    "Salaru Nicolae vs. Urechean Vadim: Total Games O/U 3.5",
    "Salaru Nicolae vs. Urechean Vadim: Total Games O/U 4.5",
]


# --------------------------------------------------------------------------
# The ship — real tennis stops being filed as table tennis
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tags,title",
    [
        # Tag order varies between events; all three orderings observed live.
        (["Tennis", "Sports", "Games"], "US Open ATP: Ben Shelton vs Hubert Hurkacz"),
        (["Sports", "Games", "Tennis"], "US Open ATP: Jaime Faria vs Carlos Alcaraz"),
        (["Games", "Tennis", "Sports"], "M15 Kursumlijska Banja: Maksim Despotovic"),
    ],
)
def test_a_tennis_tagged_match_is_tennis_even_with_a_small_set_games_prop(tags, title):
    """The exact production defect: 639 open markets, the whole US Open draw."""
    # The heuristic DOES fire on this group — that is the point. Only the gate
    # can produce the right answer, so this guard cannot pass by accident.
    assert detect_table_tennis_group(US_OPEN_GROUP) is True

    category, sport, arm = _resolve(tags, title, US_OPEN_GROUP)

    assert sport == "tennis"
    assert category == "championship"
    # And the ops counter stays honest: the TAG decided, not the heuristic.
    assert arm == "tag"


def test_the_swiatek_match_that_started_this_is_tennis():
    """`US Open WTA: Iga Swiatek vs Nadia Podoroska` — market 59970465, the row
    Q492 fixed the label on and this queue found sitting in the wrong sport."""
    group = [
        "US Open WTA: Iga Swiatek vs Nadia Podoroska",
        "Swiatek vs. Podoroska: Set 1 Games O/U 8.5",
        "US Open WTA: Iga Swiatek vs Nadia Podoroska Match O/U 21.5",
    ]
    assert detect_table_tennis_group(group) is True
    _, sport, _ = _resolve(
        ["Tennis", "Sports", "Games"],
        "US Open WTA: Iga Swiatek vs Nadia Podoroska",
        group,
    )
    assert sport == "tennis"


# --------------------------------------------------------------------------
# #1230 is not weakened — it is moved onto the source's own tag
# --------------------------------------------------------------------------


def test_a_setka_match_is_table_tennis_from_its_tag_with_no_heuristic_available():
    """Removes the heuristic's ambient recovery: this group cannot trip it.

    A bare parent title with no games props is exactly the shape that used to fall
    through to summer seasonal inference and land on BASEBALL. Only the
    `Table Tennis` tag can classify it, so reverting the `_TAG_TO_CATEGORY` entry
    fails here — it cannot be rescued by arm 1.
    """
    bare_group = ["Salaru Nicolae vs. Urechean Vadim"]
    assert detect_table_tennis_group(bare_group) is False

    category, sport, arm = _resolve(
        ["Sports", "Games", "Table Tennis", "Setka", "Setka Cup Moldova Men"],
        "Salaru Nicolae vs. Urechean Vadim",
        bare_group,
    )

    assert sport == "table_tennis"
    # Not ("table_tennis", "table_tennis") — the internal category must stay
    # `championship`, which is what arm 1 has always returned. This is the
    # assertion that catches dropping `table_tennis` from `_SPORT_CATEGORIES`.
    assert category == "championship"
    assert arm == "tag"


def test_an_untagged_setka_match_is_still_rescued_by_the_1230_heuristic():
    """Arm 1's real job, unchanged: no usable tag, child props carry the tell."""
    category, sport, arm = _resolve(["Sports"], SETKA_GROUP[0], SETKA_GROUP)
    assert sport == "table_tennis"
    assert category == "championship"
    assert arm == "table_tennis"


def test_a_wholly_untagged_setka_match_is_still_rescued():
    """The #1230 case with no tags at all — the baseball-guess path."""
    _, sport, arm = _resolve([], SETKA_GROUP[0], SETKA_GROUP)
    assert sport == "table_tennis"
    assert arm == "table_tennis"


# --------------------------------------------------------------------------
# The two vocabularies must agree
# --------------------------------------------------------------------------


def test_the_table_tennis_tag_is_mapped_at_all():
    """The absence of this key is the whole root cause; name it so it stays."""
    assert _TAG_TO_CATEGORY["table tennis"] == "table_tennis"
    assert _TAG_TO_CATEGORY["setka"] == "table_tennis"


def test_every_sport_the_tag_map_emits_yields_the_championship_category():
    """A sport tag that is missing from `_SPORT_CATEGORIES` silently sets the
    internal category to the sport's own name instead of `championship`. That is
    invisible until a page filters on `category` and comes back empty."""
    from app.tasks.polymarket import NON_SPORT_CATEGORIES

    for tag, mapped in _TAG_TO_CATEGORY.items():
        if mapped in NON_SPORT_CATEGORIES:
            continue
        assert mapped in _SPORT_CATEGORIES, (
            f"tag {tag!r} maps to {mapped!r}, which is neither a non-sport shelf "
            f"nor a member of _SPORT_CATEGORIES, so it will not get "
            f"category='championship'"
        )


def test_the_sub_market_upsert_repairs_the_sport_on_reingest():
    """Half the ship lives here, and it is not reachable from the cascade.

    The sport is only corrected for a user when the ROW changes. The parent
    market's conflict clause has always carried `llm_sport_category`; the
    sub-market's did not — so a group whose sport was fixed kept its children on
    the stale value forever. **306 of the 639 mis-filed US Open rows measured on
    production `c3143bc2` were children.**

    Asserted by AST rather than substring so a mention in a comment or docstring
    cannot satisfy it, and RAISING when the anchor is absent so a rename fails
    loudly instead of passing vacuously.
    """
    import ast
    import pathlib

    src = pathlib.Path(
        __file__
    ).resolve().parents[1] / "app" / "tasks" / "polymarket.py"
    tree = ast.parse(src.read_text())

    assigned: dict[str, set[str]] = {"sub_set": set(), "update_set": set()}
    seen_dict_literal = set()

    for node in ast.walk(tree):
        # `sub_set = {...}` / `update_set = {...}` — the anchors themselves.
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id in assigned:
                    if isinstance(node.value, ast.Dict):
                        seen_dict_literal.add(tgt.id)
                # `x["key"] = ...`
                if (
                    isinstance(tgt, ast.Subscript)
                    and isinstance(tgt.value, ast.Name)
                    and tgt.value.id in assigned
                    and isinstance(tgt.slice, ast.Constant)
                    and isinstance(tgt.slice.value, str)
                ):
                    assigned[tgt.value.id].add(tgt.slice.value)

    for name in ("sub_set", "update_set"):
        if name not in seen_dict_literal:
            raise AssertionError(
                f"anchor lost: no `{name} = {{...}}` literal in polymarket.py — "
                f"this guard can no longer see what it is guarding, so it must "
                f"fail rather than pass silently"
            )

    assert "llm_sport_category" in assigned["sub_set"], (
        "the sub-market conflict clause does not update llm_sport_category, so "
        "existing child rows keep a stale sport forever (Q493)"
    )
    assert "llm_sport_category" in assigned["update_set"], (
        "the parent conflict clause stopped updating llm_sport_category"
    )


def test_table_tennis_is_still_out_of_the_link_rate_denominator():
    """#1230 requires it: we schedule no table-tennis events to link to. Adding
    it to `_SPORT_CATEGORIES` must not leak it into the link-rate population."""
    from app.routes.admin_matching import _LINK_RATE_SPORT_CATEGORIES

    assert "table_tennis" not in _LINK_RATE_SPORT_CATEGORIES
    assert "tennis" in _LINK_RATE_SPORT_CATEGORIES
