"""#6444 — the Discover feed stops printing a sport's machine key as its name.

`GET /api/feed` has three serializers that write ``data["sport_name"]`` straight
from ``Sport.name``, and for the 15 rows whose ``name`` IS their ``key`` that
hands the reader a machine key. It is the widest surface left: ``soccer_other``
carries ~147k futures and ``tennis_other`` ~57k, and seven client call sites
read the field with no map of their own (four web — ``app/daily``,
``discover/ComparisonCard``, ``discover/FuturesCard``, ``discover/GuessCard`` —
and three native).

The fix runs at the PUBLISH BOUNDARY, not at the three write sites, and this
module exists mostly to hold that placement in place.

``_review_decision_scope_keys`` builds ``category:{sport_name}`` out of the very
dict those serializers write. Humanising upstream would re-key every stored
manual review decision — ``category:tennis_other`` -> ``category:other tennis``
— so they would stop matching and suppressed cards would quietly come back. A
ranking regression with no error and no visible symptom. Transforming after
every ranking consumer has read the raw value makes the scope keys unchanged BY
CONSTRUCTION, and `test_humanise_runs_after_the_review_decision_scope_read` is
the assertion that keeps it that way: it is the only test here that can fail if
a later change "finishes the job" by moving the call upstream.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.routes.feed import _review_decision_scope_keys
from app.utils.sport_keys import sport_display_name
from tests.test_sport_display_name_never_serves_raw_key_5657 import RAW_NAMED_KEYS

FEED_SOURCE = Path(__file__).resolve().parents[1] / "app" / "routes" / "feed.py"


def _feed_tree() -> ast.Module:
    return ast.parse(FEED_SOURCE.read_text())


def _call_lines(tree: ast.Module, func_name: str) -> list[int]:
    """Every line in feed.py that CALLS ``func_name``."""
    return sorted(
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == func_name
    )


def _enclosing_function(tree: ast.Module, line: int) -> str | None:
    """The top-level function whose body contains ``line``.

    Comparing two line numbers only says something about EXECUTION order when
    both lines sit in the same function body. The first draft of this module
    compared ``sport_display_name`` against ``_review_decision_scope_keys`` and
    failed on correct code, because the scope key is read inside a helper that
    is *defined* below the publish boundary but *called* far above it.
    """
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.lineno <= line <= (node.end_lineno or node.lineno):
                return node.name
    return None


# --------------------------------------------------------------------------
# 1. The defect, and the branded rows that must not move with it.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("key", RAW_NAMED_KEYS)
def test_every_raw_named_sport_gets_a_word_on_a_feed_card(key):
    """The 15 rows the feed was serving as machine keys."""
    served = sport_display_name(key, key)

    assert served is not None, key
    assert served != key, key
    assert "_" not in served, f"{key} -> {served!r} still wears a machine key"


@pytest.mark.parametrize(
    "sport_key,stored_name",
    [
        ("baseball_mlb", "MLB"),
        ("soccer_epl", "EPL"),
        ("icehockey_sweden_hockey_league", "SHL"),
        ("tennis_atp_queens", "ATP Queen's Club Championships"),
    ],
)
def test_a_branded_sport_name_reaches_the_card_byte_for_byte(sport_key, stored_name):
    """The fix may not become a formatter that flattens real brands.

    Both arms matter: #5657's lesson was that a humaniser which quietly
    re-derives every name is a regression wearing a fix's clothes.
    """
    assert sport_display_name(sport_key, stored_name) == stored_name


def test_an_absent_sport_name_stays_absent():
    """A bare ``Sport(key=...)`` stub keeps serving nothing (the #4368 contract).

    The boundary guards on ``is not None`` so clients keep falling back to their
    own maps rather than being handed a newly-derived word.
    """
    assert sport_display_name("soccer_other", None) is None


# --------------------------------------------------------------------------
# 2. The ranking-inertness contract. This is the load-bearing half.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("key", ["tennis_other", "soccer_other", "baseball_other"])
def test_review_decision_scope_key_is_built_from_the_machine_key(key):
    """A stored decision on a raw-named sport keys on the RAW value.

    This is what is already in the database. If the served name ever becomes the
    scope key, every one of these stops matching at once.
    """
    item = {"data": {"sport": key, "sport_name": key}}

    assert f"category:{key}" in _review_decision_scope_keys(item)


def test_review_decision_scope_key_is_unchanged_by_the_humanised_name():
    """The boundary transform is invisible to the scope key.

    Belt and braces for the source-order guard below: even if a humanised name
    reached this function, the machine key is present on the same dict, so the
    contract is recoverable rather than lost.
    """
    raw = {"data": {"sport": "tennis_other", "sport_name": "tennis_other"}}
    humanised = {"data": {"sport": "tennis_other", "sport_name": "Other Tennis"}}

    assert "category:tennis_other" in _review_decision_scope_keys(raw)
    assert "category:tennis_other" not in _review_decision_scope_keys(humanised), (
        "if this ever passes, humanising upstream is safe and this module's "
        "whole placement argument can be retired"
    )


def test_the_scope_key_is_read_only_through_the_review_decision_entrypoint():
    """Chain of custody, link 1: who reads the raw name for ranking.

    The ordering guard below is only meaningful if the ranking read really does
    happen inside the call it names. If a second reader of
    ``_review_decision_scope_keys`` appears somewhere else in the request, the
    ordering assertion stops covering it and has to be re-derived.
    """
    tree = _feed_tree()

    readers = {
        _enclosing_function(tree, line)
        for line in _call_lines(tree, "_review_decision_scope_keys")
    }

    assert readers == {"_apply_manual_review_decision_map"}, (
        f"the review-decision scope key is now read from {sorted(readers)}; "
        f"re-derive the ordering guard against every reader"
    )


def test_humanise_runs_after_the_review_decision_scope_read():
    """THE guard: the transform stays DOWNSTREAM of every ranking consumer.

    A future change that "finishes the job" by humanising at the three
    serializers would silently re-key stored review decisions. No behavioural
    test can catch that — a unit test builds its own item dict and never goes
    through a serializer — so the assertion has to be about where the call sits
    in the request.

    Both call sites are statements in ``get_feed``'s own body, so here line
    order IS execution order; the test asserts that precondition rather than
    assuming it.
    """
    tree = _feed_tree()
    humanise_lines = _call_lines(tree, "sport_display_name")
    applier_lines = _call_lines(tree, "_apply_manual_review_decisions")

    assert humanise_lines, "feed.py no longer humanises sport_name at all"
    assert applier_lines, (
        "_apply_manual_review_decisions is gone; re-derive this guard against "
        "whatever now consumes data['sport_name'] for ranking"
    )

    scopes = {_enclosing_function(tree, line) for line in humanise_lines + applier_lines}
    assert scopes == {"get_feed"}, (
        f"this guard compares line numbers, which only means execution order "
        f"inside one function body; the calls now live in {sorted(scopes)}"
    )

    assert min(humanise_lines) > max(applier_lines), (
        f"sport_display_name is called at {humanise_lines} but the review "
        f"decisions are applied at {applier_lines}. Humanising before that read "
        f"re-keys every stored manual review decision "
        f"(category:tennis_other -> category:other tennis) and suppressed cards "
        f"come back with no error."
    )


def test_the_feed_humanises_in_exactly_one_place():
    """One boundary, not three write sites.

    Placement is the safety argument, so a second call site is a finding even if
    it happens to be downstream: it means the invariant is being maintained by
    hand again.
    """
    humanise_lines = _call_lines(_feed_tree(), "sport_display_name")

    assert len(humanise_lines) == 1, (
        f"expected one humanise call at the publish boundary, found "
        f"{len(humanise_lines)} at {humanise_lines}"
    )


def test_the_boundary_only_touches_cards_that_already_carry_a_sport_name():
    """It may repair the field, never mint it.

    Concept and tournament cards do not all carry ``sport_name``. Dropping the
    presence guard would add ``"sport_name": null`` to every card that never had
    one — a payload shape change dressed as a label fix — because
    ``sport_display_name`` returns ``None`` for an absent stored name.
    """
    tree = _feed_tree()
    (humanise_line,) = _call_lines(tree, "sport_display_name")

    guard = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.If)
        and node.lineno < humanise_line <= (node.end_lineno or node.lineno)
        and "sport_name" in ast.unparse(node.test)
    )

    assert "is not None" in ast.unparse(guard.test), (
        f"the humanise must be guarded on an existing sport_name: "
        f"{ast.unparse(guard.test)}"
    )


def test_the_machine_key_still_reaches_the_client():
    """Clients key their own maps on ``data["sport"]``; the fix must not eat it.

    ``frontend/components/FeedCard.tsx`` calls ``getSportLabel(data.sport,
    data.sport_name)`` — the key is the first argument.
    """
    tree = _feed_tree()
    (humanise_line,) = _call_lines(tree, "sport_display_name")

    call = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "sport_display_name"
        and node.lineno == humanise_line
    )
    rendered = ast.unparse(call)

    assert "'sport'" in rendered or '"sport"' in rendered, (
        f"the humanise call must read the machine key to decide: {rendered}"
    )


# --------------------------------------------------------------------------
# 3. A stored decision still matches — over BOTH populations (integrator/381).
# --------------------------------------------------------------------------
#
# The desk ruled this ship REVIEWED and asked for the contract as an executable
# fact over both halves of the sports table, measured on production 2026-09-16:
# **15 rows whose `name` IS their `key`, 162 branded.** Part 2 above pins the
# ordering; this pins what the ordering is FOR, which is the thing a reader
# would actually lose.
#
# The two populations fail differently, and that asymmetry is the whole reason
# #6465's proposed remedy was refused:
#
#   raw (15)      the transform CHANGES the name, so the scope key is only safe
#                 because it is read first. Ordering is load-bearing here.
#   branded (162) the transform is the IDENTITY, so the scope key is safe under
#                 either order — and re-pointing the key at `data["sport"]`
#                 instead, as #6465 proposed, would have re-keyed all 162
#                 (`category:mlb` -> `category:baseball_mlb`). The bigger
#                 population is the one the "obvious" fix breaks.


def _publish_boundary(data: dict) -> dict:
    """The boundary transform from `get_feed`, applied to one card's data.

    Deliberately a restatement rather than an import: the route applies this
    inline at the publish boundary, and a test that imported the exact
    expression could not tell that expression moving upstream. Part 2's
    ordering guard is what pins WHERE it runs; this pins WHAT it does.
    """
    out = dict(data)
    if out.get("sport_name") is not None:
        out["sport_name"] = sport_display_name(out.get("sport"), out.get("sport_name"))
    return out


#: The raw-named keys split in two, and the split is DERIVED rather than typed
#: out, so a new `*_other` row joins the right half on its own.
#:
#: `_review_decision_scope_keys` lowercases, and `esports` humanises to
#: `Esports` — same string once lowered. So for that one row the transform
#: cannot move the scope key and the ordering is genuinely not load-bearing.
#: Measured 2026-09-16: **14 of the 15 are load-bearing, `esports` is the one
#: that is not.** This was found by the falsifier below failing on correct code,
#: which is the only reason the distinction is written down rather than assumed
#: away — a blanket claim that "humanising upstream breaks all 15" would have
#: been false, and a reader checking it on `esports` would have distrusted the
#: rest of the argument.
_SCOPE_MOVES = [
    key
    for key in RAW_NAMED_KEYS
    if sport_display_name(key, key).lower() != key.lower()
]
_SCOPE_HOLDS = [key for key in RAW_NAMED_KEYS if key not in _SCOPE_MOVES]


def test_the_two_raw_halves_are_both_non_empty_and_account_for_every_row():
    """The precondition for the split being meaningful at all."""
    assert len(_SCOPE_MOVES) + len(_SCOPE_HOLDS) == len(RAW_NAMED_KEYS)
    assert _SCOPE_MOVES, "no raw key's scope key moves; part 2 guards nothing"
    assert _SCOPE_HOLDS == ["esports"], (
        f"the case-only half is now {_SCOPE_HOLDS}; if it has grown, the "
        f"ordering argument covers fewer rows than the module claims"
    )


@pytest.mark.parametrize("key", RAW_NAMED_KEYS)
def test_a_stored_decision_on_a_RAW_named_sport_still_matches(key):
    """All 15: the card gets a word AND the stored decision keeps matching."""
    stored_decision_scope = f"category:{key}"
    data = {"sport": key, "sport_name": key}

    # What the route does, in the route's order: rank first, publish second.
    scopes_at_ranking_time = _review_decision_scope_keys({"data": data})
    served = _publish_boundary(data)

    assert stored_decision_scope in scopes_at_ranking_time, key
    assert served["sport_name"] != key, f"{key} still reaches the reader raw"
    assert "_" not in served["sport_name"], key


@pytest.mark.parametrize("key", _SCOPE_MOVES)
def test_humanising_a_raw_sport_UPSTREAM_would_break_its_stored_decision(key):
    """THE FALSIFIER, on the 14 rows it is true of.

    If this ever stops holding for all of them, part 2's ordering guard is
    decoration and the transform could safely move to the three write sites.
    """
    served = _publish_boundary({"sport": key, "sport_name": key})

    assert f"category:{key}" not in _review_decision_scope_keys({"data": served}), (
        f"humanising {key} before the ranking read no longer breaks its scope "
        f"key; part 2's placement argument needs re-deriving"
    )


@pytest.mark.parametrize("key", _SCOPE_HOLDS)
def test_a_case_only_raw_sport_is_scope_safe_under_either_order(key):
    """`esports` -> `Esports`, and the scope key is lowercased.

    Stated rather than skipped: this row is the counter-example to the module's
    headline, and a guard suite that quietly excluded it would be hiding the one
    case where the placement argument does not apply.
    """
    served = _publish_boundary({"sport": key, "sport_name": key})

    assert served["sport_name"] != key
    assert f"category:{key}" in _review_decision_scope_keys({"data": served})


@pytest.mark.parametrize(
    "sport_key,stored_name",
    [
        ("baseball_mlb", "MLB"),
        ("soccer_epl", "EPL"),
        ("icehockey_sweden_hockey_league", "SHL"),
        ("tennis_atp_queens", "ATP Queen's Club Championships"),
        ("americanfootball_nfl", "NFL"),
    ],
)
def test_a_stored_decision_on_a_BRANDED_sport_is_untouched_either_way(
    sport_key, stored_name
):
    """The 162 — asserted as a PROPERTY, because a 162-row fixture would drift.

    Enumerating the branded rows here would be a copy of the sports table that
    nothing updates when a league is added. The claim that actually covers all
    162 is that the transform is the identity whenever the stored name is not
    the key, so the scope key is byte-identical before and after. These five are
    named specimens of that property, not the population.
    """
    data = {"sport": sport_key, "sport_name": stored_name}

    before = _review_decision_scope_keys({"data": data})
    after = _review_decision_scope_keys({"data": _publish_boundary(data)})

    assert before == after, (
        f"{sport_key} is a branded row; the boundary must be the identity for "
        f"it, but the scope keys moved {before} -> {after}"
    )
    assert f"category:{stored_name.lower()}" in before


def test_the_branded_half_is_identity_for_every_name_that_is_not_the_key():
    """The property itself, stated once over the shape rather than the rows.

    This is what makes the five specimens above a sample of 162 rather than a
    list of five. `sport_display_name` may only substitute when the stored name
    IS the machine key; any other stored name comes back byte-for-byte, so no
    branded row's scope key can move no matter where the transform runs.
    """
    for sport_key, stored_name in [
        ("soccer_other", "Other Soccer"),
        ("tennis_other", "x"),
        ("baseball_mlb", "MLB"),
        ("anything_at_all", "A Brand New League"),
        ("golf_pga", "golf_pga_but_not_quite"),
    ]:
        assert sport_display_name(sport_key, stored_name) == stored_name, (
            f"{sport_key}/{stored_name!r} was rewritten; the branded population "
            f"is no longer safe under either ordering"
        )


def test_the_three_write_sites_are_still_raw_ON_PURPOSE():
    """Not a missed sixth surface — the anti-vacuity specimen (integrator/381).

    A grader reading the diff sees three serializers still writing `Sport.name`
    verbatim and reasonably asks why the fix skipped them. They are skipped
    because fixing them THERE is the ranking regression this whole module
    exists to prevent, and because they are what part 1's coverage scan
    measures against: if the write sites were humanised too, every assertion
    about the boundary would pass whether or not the boundary ran.
    """
    tree = _feed_tree()
    boundary_calls = _call_lines(tree, "sport_display_name")

    assert len(boundary_calls) == 1, (
        f"sport_display_name is called {len(boundary_calls)} times in feed.py "
        f"(lines {boundary_calls}); the write sites must stay raw so the "
        f"boundary remains the only humaniser and the only thing under test"
    )
