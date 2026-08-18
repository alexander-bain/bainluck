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


# ── #1947: arm A is NECESSARY, and it is not SUFFICIENT ───────────────────────
#
# Ruling 048 arm A says a shared provider id establishes identity. Production
# says otherwise, and it was measured rather than argued: of the 13 pairs
# sharing an ``espn_id`` in a 60-day window, at least three are GENUINELY
# DIFFERENT GAMES.
#
#     401816142   Dodgers @ Yankees   /   Dodgers @ Mets
#     401882919   Real Sociedad @ Real Madrid   /   Real Betis @ Real Sociedad
#     401856667   Ohio State @ Texas   /   Texas State @ Texas
#
# Arm A alone licenses deleting one of each pair. The only thing that has ever
# stopped it is ``ABS(Δcommence) < 21600`` in ONE caller's SELECT — a number
# that is not part of the invariant, is absent from the other rails, and is one
# hand-edit from not existing. That is the whole of #1947: the safety was real
# but it was accidental, and it lived in the wrong place.
#
# So the corroboration moves HERE, next to arm A, and it is re-verified inside
# the delete transaction (``app/utils/event_absorption_guard.py``). A caller
# that drops its window no longer drops the safety with it.
#
# Two arms, and each was chosen against a specimen it must refuse:
#
#  * MATCHUP AGREEMENT refuses the three pairs above — they share an id and
#    disagree about who is playing.
#  * BOUNDED SEPARATION refuses the ordinary SERIES shape, which matchup
#    agreement cannot: Blue Jays @ Red Sox on Jul 24 and Jul 26 share an
#    ``espn_id``, agree on both clubs, and are two real games 42.3h apart. This
#    is the specimen this module's own docstring already cites.
#
# What this deliberately does NOT do: drain the four MLB rows that render live
# 40-51h early (queue 364 item 2). They agree on matchup and are 45-51h apart,
# so the separation arm refuses them — correctly, on the evidence available,
# because nothing here can distinguish "one game with a wrong commence_time"
# from "two games in a series". Whether to admit them is a policy question with
# an issue attached (#1947), not something to smuggle in as a widened constant.

#: The largest ``commence_time`` gap two rows may show and still be treated as
#: one event. Promoted verbatim from ``_merge_duplicate_events_impl``'s SQL,
#: where it was load-bearing safety disguised as a query-tuning constant.
#:
#: Lowering it is safe. RAISING it is a ruling-048 amendment, because the first
#: thing above this line is a real game: the tightest true-series pair measured
#: in 60 days is 42.0h (White Sox @ Orioles, Jun 29 / Jul 1).
MAX_ABSORPTION_SEPARATION_SECONDS = 21600  # 6h


def _matchup_of(row: Any) -> tuple[str, str] | None:
    """``(home, away)`` lowercased, preferring the normalized names."""
    def _field(name: str):
        if isinstance(row, Mapping):
            return row.get(name)
        return getattr(row, name, None)

    home = _field("home_team_normalized") or _field("home_team_name")
    away = _field("away_team_normalized") or _field("away_team_name")
    if home is None or away is None:
        return None
    return (str(home).strip().lower(), str(away).strip().lower())


def matchup_agrees(a: Any, b: Any) -> bool | None:
    """Do these rows name the same two participants? ``None`` when unknowable.

    Either orientation counts — home/away disagreement between providers is
    ordinary and is not evidence of two different games.

    The three-valued return is deliberate. A row that carries no team labels
    cannot ASSERT agreement, and the one reading that must never happen is the
    ``NULL == NULL`` merge this module already refuses one function up. Callers
    treat ``None`` as "no corroboration", never as "fine".
    """
    ma, mb = _matchup_of(a), _matchup_of(b)
    if ma is None or mb is None:
        return None
    return ma == mb or ma == (mb[1], mb[0])


def _separation_seconds(a: Any, b: Any) -> float | None:
    def _field(row):
        if isinstance(row, Mapping):
            return row.get("commence_time")
        return getattr(row, "commence_time", None)

    ta, tb = _field(a), _field(b)
    if ta is None or tb is None:
        return None
    try:
        return abs((ta - tb).total_seconds())
    except (TypeError, AttributeError):
        return None


def corroboration_reason(a: Any, b: Any) -> str | None:
    """Why a SHARED-ID pair still may not be absorbed — or ``None`` if it may.

    Assumes arm A already passed; this is the second half, not a replacement.
    """
    agrees = matchup_agrees(a, b)
    if agrees is None:
        return (
            "shared provider id, but at least one row carries no team labels — "
            "the id cannot be corroborated, and an uncorroborated id is the "
            "#1947 collision class"
        )
    if not agrees:
        ma, mb = _matchup_of(a), _matchup_of(b)
        return (
            f"shared provider id, but the rows name DIFFERENT participants: "
            f"{ma[1]} @ {ma[0]} vs {mb[1]} @ {mb[0]} — production holds espn_id "
            "values shared by genuinely different games (#1947)"
        )
    gap = _separation_seconds(a, b)
    if gap is None:
        return (
            "shared provider id and matching participants, but at least one "
            "row has no commence_time, so the series case cannot be excluded"
        )
    if gap > MAX_ABSORPTION_SEPARATION_SECONDS:
        return (
            f"shared provider id and matching participants, but the rows are "
            f"{gap / 3600:.1f}h apart (> {MAX_ABSORPTION_SEPARATION_SECONDS / 3600:.0f}h) "
            "— that is the ordinary series/doubleheader shape, which is two real games"
        )
    return None


class UncorroboratedMergeRefused(UnanchoredMergeRefused):
    """A shared id that is not corroborated by the rest of the row (#1947).

    Subclasses :class:`UnanchoredMergeRefused` on purpose: every rail already
    catches that and skips the pair, so this arrives as a refusal rather than as
    an unhandled crash in a task that must keep draining (gotcha #42).
    """


def assert_absorbable(a: Any, b: Any, *, context: str) -> None:
    """Both arms: a shared provider id, AND corroboration that it means identity.

    This is what a DELETE requires. :func:`assert_mergeable` is arm A alone and
    remains available for callers reasoning about candidate SETS, but nothing
    should destroy a row on arm A by itself — see the #1947 block above.
    """
    assert_mergeable(a, b, context=context)
    reason = corroboration_reason(a, b)
    if reason is None:
        return
    raise UncorroboratedMergeRefused(
        f"{context}: refusing to absorb events "
        f"{getattr(a, 'id', None) if not isinstance(a, Mapping) else a.get('id')} and "
        f"{getattr(b, 'id', None) if not isinstance(b, Mapping) else b.get('id')} — "
        f"{reason}. Ruling 048 arm A is necessary and not sufficient: a shared id "
        "is evidence of identity, not proof of it."
    )


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
