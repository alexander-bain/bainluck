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
