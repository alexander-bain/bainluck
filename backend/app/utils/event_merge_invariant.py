"""Ruling 048's invariant, in ONE place: nothing merges two events without a shared id.

#1801 R6, from codex ``C-CERT-1801-R5``'s BLOCK. Ruling 048 says:

    An id-less claim NEVER absorbs into an existing event — no time window, no
    name match, no heuristic. Absorption requires at least one shared or
    confirming provider id. Everything else CREATES, with the claim's
    provenance recorded, and id-keyed reconciliation drains the duplicates when
    ids later arrive.

R5 implemented that at the **registry boundary** and it held there. The
certification then found the same absorption alive one layer down, in the rails
that DELETE: a duplicate drained by name and a time window is absorption with
extra steps, and it destroys the row instead of merely mis-joining it.

## Why this is a module and not three careful predicates

The R5 attempt wrote the rule into the drain's SQL directly, and the SQL grew a
second arm: *a shared id, OR one side is id-less and no THIRD row shares the
window*. The second arm reads like a safety check and is not one.

Codex's specimen, which is an ordinary Tuesday in baseball: row A is the
Odds-anchored BOS@TOR game 1 at 13:05, row B is the newly created, id-less
BOS@TOR game 2 at 18:35. **That is the whole doubleheader — two rows, 5.5 hours
apart.** The "no third row" test excludes A and B themselves, finds nothing,
and reports the pair unambiguous. The drain then deletes game 2, which the
registry had just correctly created.

The lesson generalises past this bug: **uniqueness is not identity.** "I can
find no evidence of a second game" and "these two rows are the same game" are
different claims, and only the second licenses a delete. Every id-less matcher
that has ever shipped here was some restatement of the first.

So the invariant moves OUT of each caller's SQL and into this module, in two
forms that cannot drift apart, because the alternative is what R1–R5 were:
five careful predicates, each correct-looking, in five places.

* :func:`shared_provider_id_sql` — for the SELECT that finds candidates.
* :func:`assert_mergeable` — for the moment before the DELETE.

Both are required. The SQL keeps the candidate set honest and cheap; the
assertion is what makes a drifted, hand-edited or newly-added query fail loudly
instead of quietly deleting a game. A guard that only exists in a query string
is one refactor away from not existing.

## "Shared or CONFIRMING"

Only the *shared* half is implemented, deliberately. A confirming id would be a
second provider independently asserting that two rows are one event — an
identity-graph edge, which is what the universal-matching engine is for and
which is still shadow-mode. Until that rail is live, "confirming" has no
implementation, and the one thing it must never be quietly redefined as is a
name-and-window heuristic, since that is the exact thing ruling 048 forbids.
:data:`CONFIRMING_RAIL_AVAILABLE` exists so a future caller extends this module
rather than re-deriving a local exception.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

#: The provider-id columns on ``events``. Order is irrelevant; presence is not.
#:
#: To add a provider, add its column here — every rail picks it up at once,
#: which is the entire point of the module. A rail that names these columns
#: itself has re-created the drift this replaces.
PROVIDER_ID_COLUMNS: tuple[str, ...] = (
    "external_id",
    "espn_id",
    "statpal_fixture_id",
)

#: No identity-graph/confirming-id rail exists yet. See the module docstring.
CONFIRMING_RAIL_AVAILABLE = False


class UnanchoredMergeRefused(RuntimeError):
    """Raised when a caller is about to merge two events with no shared id.

    Deliberately an exception and not a ``False`` return. A destructive rail
    that gets a falsy answer can carry on by omission — one un-checked branch,
    one ``if not guard: pass`` — whereas this stops the delete and names the
    pair in the traceback. #1575 is the local precedent for what an unnoticed
    destructive path costs: nine files, unrecoverable.
    """


def shared_provider_id_sql(a: str = "a", b: str = "b") -> str:
    """SQL predicate: aliases ``a`` and ``b`` share at least one provider id.

    Returns a parenthesised expression safe to ``AND`` into any join. Aliases
    are restricted to identifier-shaped strings because this is string-composed
    into SQL; they are never user input in this codebase, and the check is here
    so that stays true by construction rather than by convention.
    """
    for alias in (a, b):
        if not alias.replace("_", "").isalnum():
            raise ValueError(f"unsafe SQL alias: {alias!r}")
    arms = " OR ".join(
        f"({a}.{col} IS NOT NULL AND {a}.{col} = {b}.{col})"
        for col in PROVIDER_ID_COLUMNS
    )
    return f"({arms})"


def _ids_of(row: Any) -> dict[str, Any]:
    """Provider ids off an ORM object, a Row, or a mapping — whichever a caller has."""
    out: dict[str, Any] = {}
    for col in PROVIDER_ID_COLUMNS:
        if isinstance(row, Mapping):
            value = row.get(col)
        else:
            value = getattr(row, col, None)
        out[col] = value
    return out


def shared_provider_ids(a: Any, b: Any) -> set[str]:
    """The provider-id columns on which ``a`` and ``b`` genuinely agree.

    Both sides must be non-null. Two rows that are both missing an id do not
    "agree" on it — that reading is how ``NULL == NULL`` becomes a merge, and
    it is the shape of the Case B clause this module exists to delete.
    """
    ids_a, ids_b = _ids_of(a), _ids_of(b)
    return {
        col for col in PROVIDER_ID_COLUMNS
        if ids_a[col] is not None and ids_a[col] == ids_b[col]
    }


def may_merge(a: Any, b: Any) -> bool:
    """True when these two event rows may be merged under ruling 048."""
    return bool(shared_provider_ids(a, b))


def refusal_reason(a: Any, b: Any) -> str | None:
    """A human-readable reason, or ``None`` when the merge is permitted."""
    if may_merge(a, b):
        return None
    ids_a, ids_b = _ids_of(a), _ids_of(b)
    anchored_a = {k: v for k, v in ids_a.items() if v is not None}
    anchored_b = {k: v for k, v in ids_b.items() if v is not None}
    if not anchored_a and not anchored_b:
        return "neither row carries any provider id"
    if not anchored_a or not anchored_b:
        return "one row is unanchored; an id-less row never absorbs (ruling 048)"
    return (
        f"no shared provider id: {sorted(anchored_a)} vs {sorted(anchored_b)} "
        "disagree on every column they both carry"
    )


def assert_mergeable(a: Any, b: Any, *, context: str) -> None:
    """Refuse, loudly, unless ``a`` and ``b`` share a provider id.

    Call this immediately before the DELETE, in every rail, even when the
    SELECT already used :func:`shared_provider_id_sql`. The redundancy is the
    design: the query proves the candidate set was chosen correctly *today*,
    and this proves the row in hand is safe to destroy *now*.
    """
    reason = refusal_reason(a, b)
    if reason is None:
        return
    raise UnanchoredMergeRefused(
        f"{context}: refusing to merge events "
        f"{getattr(a, 'id', None)} and {getattr(b, 'id', None)} — {reason}. "
        "Ruling 048: absorption requires a shared or confirming provider id; "
        "a name match inside a time window is not identity, and a doubleheader "
        "is two real games that satisfy it."
    )


def partition_mergeable(pairs: Iterable[tuple[Any, Any]]) -> tuple[list, list]:
    """``(mergeable, refused)`` — for rails that must keep draining past a bad pair.

    A refusal is not an error condition to abort on: the correct behaviour when
    one pair is unanchored is to leave that pair alone and drain the rest, then
    report the refusals. One bad item must never wipe the pass (gotcha #42).
    """
    ok, refused = [], []
    for a, b in pairs:
        (ok if may_merge(a, b) else refused).append((a, b))
    return ok, refused
