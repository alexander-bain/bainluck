"""#9925: a Discover theme card links to its full collection page.

PILLARS DISCOVER · MATCHING · TRUTH · FORMATTING. SHIP (#9925): tap "View
collection" on a genuinely eligible Discover theme, browse its complete
automatically maintained page, open a member, and come back to the same place.

This module produces the feed's ``collection_ref`` (Authority's producer
contract for #9935, §5 and §6.1). It writes nothing, publishes nothing and
adds no flag: a ref can only exist for a container a person has already
published, so publication stays the only switch.

THE TARGET IS DETERMINED, NEVER SEARCHED FOR. ``resolve_collection_target``
(``theme_definitions``, steps 0–3) chooses the one intended container from the
bundle's own feed key and the containers that admit EVERY preview id, in any
publication state. Only then do the step-4 checks below run, on that target
alone. They can remove the link. They can never choose another one. Nothing
here infers a destination from a title, a header or a member id.

STEP 4, ON THE TARGET ONLY (each a reason for ops, never reader text):

* ``target_unpublished``: the container is not ``published`` (unpublished,
  withdrawn, anything else).
* ``target_not_maintained``: the slug has no registry definition, so no
  assembly keeps it complete.
* ``target_revision_moved``: the live revision is not the one this page is
  cached under (the published read at the top of the request). The page and
  its cache key always name the same revision.
* ``snapshot_stale``: no readable snapshot at the live revision. This covers
  the "building" window after a publish or a correction. It is read through the
  hub's own reader, so card and page cannot disagree about it.
* ``snapshot_partial``: the snapshot's inventory is not complete. A stricter
  reading than the contract's list. The publication operator demands a complete
  inventory, and a card promising "the whole collection" must too.
* ``preview_member_not_admitted``: a preview id is in neither the snapshot's
  shown ids nor its folded ids (contract R-5: shown ∪ folded, so one question
  with two venues is not a false refusal).
* ``preview_member_withheld``: a preview id is withheld on the page.

BOUNDED. When nothing is published there is no read at all. Otherwise there
is one statement over ``event_edges`` keyed by the page's preview ids
(``ix_event_edge_child``), and at most one snapshot GET per resolved target,
all inside ``THEME_REF_READ_BUDGET_SECONDS``. No inventory scan, no LLM, no
assembly. The containers' published read is one statement over the registry's
few slugs, inside ``THEME_PUBLICATION_READ_BUDGET_SECONDS``. It is reused
process-wide for at most five seconds, like ``feed_collections_cache_fingerprint``.

OWN SESSION. Both reads are optional enrichment, so neither runs on the
request's session. Each takes its own short-lived session (``_side_read``). The
request waits at most the budget and never waits on cleanup. A read it stopped
waiting for is cancelled, and its session is released off the request path: a
rollback, then invalidation if that does not land, each step bounded. A
timed-out or failed read therefore cannot leave the feed's transaction aborted,
or its connection waiting on a cancelled query. It only costs the link (and, for
the publication read, the cache).

CACHE. ``compose_collections_fingerprint`` folds the published themes'
``id:revision`` into the response-cache key the route already has
(``collections=``). A publish, withdrawal, correction or assembly bumps the
revision, so a page built under one publication state is read back only under
that state. When no theme is published, the key is byte-identical to today's.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Iterable, Mapping, Optional

from sqlalchemy import bindparam, text

from app.utils.container_corrections import PUBLICATION_COLUMN, REVISION_COLUMN
from app.utils.theme_definitions import (
    REGISTRY,
    CandidateContainer,
    resolve_collection_target,
)

logger = logging.getLogger(__name__)

THEME_REF_READ_BUDGET_SECONDS = 0.25
#: The publication read gates the response cache, so a timeout costs a cold
#: build, not just a link. It gets a little more room than the per-build read.
THEME_PUBLICATION_READ_BUDGET_SECONDS = 0.5
#: Each cleanup step (rollback/close, then invalidate) on a read's own session.
#: Off the request path, so this only bounds how long a connection is held.
THEME_REF_CLEANUP_STEP_SECONDS = 1.0
PUBLISHED = "published"
EDGE_SOURCE = "theme_rule"

# Step-4 reasons (ops debug only — notice 34).
TARGET_UNPUBLISHED = "target_unpublished"
TARGET_NOT_MAINTAINED = "target_not_maintained"
TARGET_REVISION_MOVED = "target_revision_moved"
SNAPSHOT_STALE = "snapshot_stale"
SNAPSHOT_PARTIAL = "snapshot_partial"
PREVIEW_MEMBER_NOT_ADMITTED = "preview_member_not_admitted"
PREVIEW_MEMBER_WITHHELD = "preview_member_withheld"
# Before resolution: a preview member without an integer id cannot be checked.
PREVIEW_ID_INVALID = "preview_id_invalid"
# The bounded read failed or ran out of budget: no ref, ordinary card.
READ_FAILED = "read_failed"
EMITTED = "emitted"

#: Where the reason rides, beside the bundler's own ``grouped_by`` evidence.
DEBUG_KEY = "collection_ref"


@dataclass(frozen=True)
class PublishedTheme:
    container_id: int
    slug: str
    revision: int


@dataclass(frozen=True)
class PublishedThemes:
    """The published theme containers this request is cached under."""

    themes: tuple[PublishedTheme, ...] = ()

    def revision_of(self, container_id: int) -> Optional[int]:
        for theme in self.themes:
            if theme.container_id == container_id:
                return theme.revision
        return None

    def fingerprint(self) -> Optional[str]:
        """None when nothing is published (the cache key stays as it was)."""
        if not self.themes:
            return None
        raw = ",".join(f"{t.container_id}:{t.revision}" for t in self.themes)
        return hashlib.sha256(f"theme-v1|{raw}".encode()).hexdigest()[:16]


def theme_collection_refs_enabled(*, mode: Optional[str], include_futures: bool) -> bool:
    """A Discover request that carries futures, while the page reader serves.

    No new flag: with the hub reader off the link would open a 404, and with no
    container published there is nothing to link to.
    """
    from app.routes.containers import containers_read_enabled

    return (
        (mode or "discover").lower() == "discover"
        and include_futures
        and containers_read_enabled()
    )


# ---------------------------------------------------------------------------
# The reads' own sessions: bounded wait, bounded cleanup, nothing escapes.
# ---------------------------------------------------------------------------

SessionFactory = Callable[[], Any]


def _default_session_factory():
    from app.services.database import async_session_maker

    return async_session_maker()


#: Reads the request stopped waiting for, held until their bounded cleanup
#: ends. The loop keeps only a weak reference to a task.
_abandoned_reads: set = set()


async def _dispose_session(session, *, clean: bool) -> str:
    """Release a read's own session within two bounded steps. Never raises
    anything but cancellation, and only after both steps have run.

    Step one closes the session, after a rollback when the read did not finish
    (``clean`` False). A cancelled asyncpg query leaves its connection waiting
    for the server's cancel to land, so that step may not. Step two then
    invalidates the connection instead of returning it to the pool in an
    unknown state: the same two steps as the route's
    ``_release_cancelled_review_session``.
    Returns ``closed`` / ``rolled_back`` / ``invalidated`` / ``abandoned``.
    """
    cancelled = False
    try:
        async with asyncio.timeout(THEME_REF_CLEANUP_STEP_SECONDS):
            if not clean:
                await session.rollback()
            await session.close()
        return "closed" if clean else "rolled_back"
    except asyncio.CancelledError:
        cancelled = True
    except Exception:  # noqa: BLE001 — cleanup must never become the failure
        logger.warning(
            "Discover theme read: session release did not land inside %.1fs; "
            "invalidating its connection",
            THEME_REF_CLEANUP_STEP_SECONDS,
            exc_info=True,
        )
    outcome = "abandoned"
    try:
        async with asyncio.timeout(THEME_REF_CLEANUP_STEP_SECONDS):
            await session.invalidate()
        outcome = "invalidated"
    except asyncio.CancelledError:
        cancelled = True
    except Exception:  # noqa: BLE001 — there is nothing further to try
        logger.warning(
            "Discover theme read: could not invalidate its connection", exc_info=True
        )
    if cancelled:
        raise asyncio.CancelledError
    return outcome


async def _side_read(
    work: Callable[[Any], Awaitable[Any]],
    *,
    budget_seconds: float,
    session_factory: Optional[SessionFactory],
    what: str,
) -> tuple[bool, Any]:
    """``(True, work(session))`` on a session of its own, or ``(False, None)``.

    The caller waits at most ``budget_seconds``, including the session's
    release. Past that, the read is cancelled and left to release its session
    on its own (``_dispose_session``, itself bounded), while the caller goes on
    without it. A failure or timeout is logged and returned, never raised.
    Cancelling the caller cancels the read and propagates.
    """
    factory = session_factory or _default_session_factory

    async def _job():
        session = factory()
        try:
            value = await work(session)
        except BaseException:
            await _dispose_session(session, clean=False)
            raise
        await _dispose_session(session, clean=True)
        return value

    task = asyncio.ensure_future(_job())
    try:
        await asyncio.wait({task}, timeout=max(0.0, budget_seconds))
    except asyncio.CancelledError:
        task.cancel()
        _abandon(task)
        raise
    if not task.done():
        task.cancel()
        _abandon(task)
        logger.warning(
            "Discover theme %s read did not finish inside %.0f ms; going on without it",
            what,
            budget_seconds * 1000,
        )
        return False, None
    if task.cancelled():
        return False, None
    exc = task.exception()
    if exc is not None:
        logger.warning(
            "Discover theme %s read failed; going on without it", what, exc_info=exc
        )
        return False, None
    return True, task.result()


def _abandon(task) -> None:
    _abandoned_reads.add(task)

    def _done(t) -> None:
        _abandoned_reads.discard(t)
        if not t.cancelled() and t.exception() is not None:
            logger.debug("Discover theme read ended after it was abandoned", exc_info=t.exception())

    task.add_done_callback(_done)


def maintained_slugs() -> list[str]:
    return sorted(REGISTRY)


_PUBLISHED_SQL = text(
    f"SELECT id, slug, {REVISION_COLUMN} FROM containers "
    f"WHERE {PUBLICATION_COLUMN} = :published AND slug IN :slugs "
    "ORDER BY id"
).bindparams(bindparam("slugs", expanding=True))

_published_cache: Optional[tuple[float, PublishedThemes]] = None


async def read_published_themes(
    *,
    max_age_seconds: float = 0.0,
    budget_seconds: float = THEME_PUBLICATION_READ_BUDGET_SECONDS,
    session_factory: Optional[SessionFactory] = None,
) -> Optional[PublishedThemes]:
    """The published, registry-maintained theme containers, or None.

    None means "could not tell": the caller must not cache the page and emits
    no ref, so a failure costs speed, never truth. The statement runs on its
    own session inside ``budget_seconds`` (capped at
    ``THEME_PUBLICATION_READ_BUDGET_SECONDS``), so neither a failure (an
    un-migrated database has no ``publication_state``) nor a stall can touch
    the request's transaction or hold up its cache gate past the budget.
    """
    global _published_cache
    now = time.monotonic()
    max_age_seconds = min(max(0.0, max_age_seconds), 5.0)
    if (
        max_age_seconds > 0
        and _published_cache is not None
        and now - _published_cache[0] < max_age_seconds
    ):
        return _published_cache[1]
    budget = min(budget_seconds, THEME_PUBLICATION_READ_BUDGET_SECONDS)
    if budget <= 0:
        return None

    async def _read(session):
        return (
            await session.execute(
                _PUBLISHED_SQL, {"published": PUBLISHED, "slugs": maintained_slugs()}
            )
        ).fetchall()

    ok, rows = await _side_read(
        _read, budget_seconds=budget, session_factory=session_factory, what="publication"
    )
    if not ok:
        # Logged by _side_read: serving uncached, no collection links.
        return None
    published = PublishedThemes(
        tuple(PublishedTheme(int(r[0]), str(r[1]), int(r[2])) for r in rows)
    )
    if max_age_seconds > 0:
        _published_cache = (now, published)
    return published


def compose_collections_fingerprint(
    collections: Optional[str], published: Optional[PublishedThemes]
) -> Optional[str]:
    """The route's ``collections=`` cache-key part, with the published themes.

    Unchanged when no theme is published, so shipping this cold-starts no key.
    """
    theme = published.fingerprint() if published is not None else None
    if theme is None:
        return collections
    return f"{collections or ''}|theme:{theme}"


# ---------------------------------------------------------------------------
# The per-build read and the pure decision.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CandidateRow:
    """One ``theme_rule`` edge from a preview id to a container, with that
    container's state, as one statement read them together."""

    container_id: int
    slug: str
    name: str
    publication_state: Optional[str]
    revision: int
    child_id: int


_CANDIDATES_SQL = text(
    "SELECT c.id, c.slug, c.name, "
    f"       c.{PUBLICATION_COLUMN}, c.{REVISION_COLUMN}, e.child_id "
    "FROM event_edges e JOIN containers c ON c.id = e.parent_id "
    "WHERE e.child_type = 'market' AND e.child_id = ANY(:ids) "
    "  AND e.kind = 'contains' AND e.parent_type = 'container' "
    "  AND e.source = :source"
)


async def read_candidate_rows(db, preview_ids: Iterable[int]) -> list[CandidateRow]:
    ids = sorted({int(i) for i in preview_ids})
    if not ids:
        return []
    rows = (
        await db.execute(_CANDIDATES_SQL, {"ids": ids, "source": EDGE_SOURCE})
    ).fetchall()
    return [
        CandidateRow(int(r[0]), str(r[1]), str(r[2]), r[3], int(r[4]), int(r[5]))
        for r in rows
    ]


def _is_theme_bundle(item: Any) -> bool:
    return (
        isinstance(item, dict)
        and item.get("type") == "bundle"
        and isinstance(item.get("data"), dict)
        and item["data"].get("kind") == "theme"
    )


def bundle_feed_key(data: Mapping[str, Any]) -> Optional[str]:
    """§5 step 1: ``story_key`` for story (and swings) bundles, else ``group_id``."""
    key = data.get("story_key") or data.get("group_id")
    return str(key) if key is not None else None


def bundle_preview_ids(data: Mapping[str, Any]) -> Optional[list[int]]:
    """The ids the card previews, or None when any is not an integer id."""
    ids = data.get("member_ids")
    if not isinstance(ids, list) or not ids:
        return None
    if not all(type(i) is int for i in ids):
        return None
    return list(ids)


def candidates_for(rows: Iterable[CandidateRow]) -> dict[int, tuple[CandidateContainer, CandidateRow]]:
    """container id → (resolver input, that container's state row)."""
    members: dict[int, set[int]] = {}
    head: dict[int, CandidateRow] = {}
    for row in rows:
        members.setdefault(row.container_id, set()).add(row.child_id)
        head.setdefault(row.container_id, row)
    return {
        cid: (
            CandidateContainer(
                container_id=cid,
                slug=head[cid].slug,
                theme_rule_member_ids=frozenset(ids),
                publication_state=head[cid].publication_state,
            ),
            head[cid],
        )
        for cid, ids in members.items()
    }


def snapshot_checks(snapshot: Optional[Mapping[str, Any]], slug: str, preview: list[int]) -> Optional[str]:
    """The snapshot half of step 4: a reason, or None when the preview is wholly
    represented on the page at this revision."""
    if snapshot is None or snapshot.get("slug") != slug:
        return SNAPSHOT_STALE
    folded = snapshot.get("folded_ids", [])
    if not isinstance(folded, list) or not all(type(i) is int for i in folded):
        return SNAPSHOT_STALE
    if snapshot.get("inventory_complete") is not True:
        return SNAPSHOT_PARTIAL
    withheld = set()
    for ids in (snapshot.get("withheld") or {}).values():
        withheld.update(ids)
    if any(i in withheld for i in preview):
        return PREVIEW_MEMBER_WITHHELD
    represented = set(snapshot["shown_ids"]) | set(folded)
    if not all(i in represented for i in preview):
        return PREVIEW_MEMBER_NOT_ADMITTED
    return None


SnapshotReader = Callable[[int, int], Awaitable[Optional[dict]]]


async def _hub_snapshot(container_id: int, revision: int) -> Optional[dict]:
    """The page's own snapshot read (bounded shared client, fails closed).
    Used by identity so the card can only link to what the page would serve."""
    from app.routes.containers import _read_theme_snapshot

    return await _read_theme_snapshot(container_id, revision)


async def resolve_bundle_ref(
    data: Mapping[str, Any],
    candidates: Mapping[int, tuple[CandidateContainer, CandidateRow]],
    *,
    published: PublishedThemes,
    read_snapshot: SnapshotReader,
) -> tuple[Optional[dict], str]:
    """(collection_ref, EMITTED) or (None, reason) for one theme bundle."""
    preview = bundle_preview_ids(data)
    if preview is None:
        return None, PREVIEW_ID_INVALID
    target, reason = resolve_collection_target(
        bundle_feed_key(data), preview, [c for c, _ in candidates.values()]
    )
    if target is None:
        return None, str(reason)
    row = candidates[target.container_id][1]
    if row.publication_state != PUBLISHED:
        return None, TARGET_UNPUBLISHED
    if row.slug not in REGISTRY:
        return None, TARGET_NOT_MAINTAINED
    if published.revision_of(row.container_id) != row.revision:
        return None, TARGET_REVISION_MOVED
    snapshot = await read_snapshot(row.container_id, row.revision)
    refusal = snapshot_checks(snapshot, row.slug, preview)
    if refusal is not None:
        return None, refusal
    return (
        {
            "slug": row.slug,
            "name": row.name,
            "revision": row.revision,
            "collection_count": int(snapshot["shown_count"]),
        },
        EMITTED,
    )


def _with_ref(item: dict, ref: Optional[dict], reason: str) -> dict:
    """A copy of the bundle carrying (or not carrying) the ref. The original is
    never mutated: bundle dicts can be shared with cached build artifacts."""
    data = {k: v for k, v in item["data"].items() if k != "collection_ref"}
    if ref is not None:
        data["collection_ref"] = ref
    debug = data.get("debug_bundles")
    if isinstance(debug, dict):
        data["debug_bundles"] = {**debug, DEBUG_KEY: reason}
    return {**item, "data": data}


async def attach_theme_collection_refs(
    items: list,
    *,
    published: Optional[PublishedThemes],
    budget_seconds: float = THEME_REF_READ_BUDGET_SECONDS,
    read_snapshot: Optional[SnapshotReader] = None,
    observe: Optional[Callable[[dict], None]] = None,
    session_factory: Optional[SessionFactory] = None,
) -> list:
    """Give each eligible theme bundle its ``collection_ref``.

    Returns ``items`` itself (no copy, no read) when nothing is published, there
    is no theme bundle, or the budget is spent. Otherwise returns a new list in
    which every theme bundle is a copy carrying its §5 reason in
    ``debug_bundles`` and, when every check passed, ``collection_ref``.
    ``observe`` receives ``{bundle id: reason}``. The reads run on their own
    session (``_side_read``), never the request's.
    """
    bundles = [i for i, item in enumerate(items) if _is_theme_bundle(item)]
    if not bundles or published is None or not published.themes or budget_seconds <= 0:
        return items
    reader = read_snapshot or _hub_snapshot
    preview_union: set[int] = set()
    for i in bundles:
        preview_union.update(bundle_preview_ids(items[i]["data"]) or ())

    async def _decide(session) -> dict[int, tuple[Optional[dict], str]]:
        rows = await read_candidate_rows(session, preview_union)
        candidates = candidates_for(rows)
        memo: dict[tuple[int, int], Optional[dict]] = {}

        async def _snapshot(cid: int, rev: int) -> Optional[dict]:
            if (cid, rev) not in memo:
                memo[(cid, rev)] = await reader(cid, rev)
            return memo[(cid, rev)]

        out = {}
        for i in bundles:
            out[i] = await resolve_bundle_ref(
                items[i]["data"], candidates, published=published, read_snapshot=_snapshot
            )
        return out

    ok, decided = await _side_read(
        _decide,
        budget_seconds=min(budget_seconds, THEME_REF_READ_BUDGET_SECONDS),
        session_factory=session_factory,
        what="collection",
    )
    if not ok:
        # Keeping every card, without a link (logged by _side_read).
        decided = {i: (None, READ_FAILED) for i in bundles}

    out = list(items)
    report = {}
    for i, (ref, reason) in decided.items():
        out[i] = _with_ref(items[i], ref, reason)
        report[str(items[i]["data"].get("id"))] = reason
    if observe is not None:
        observe(report)
    return out


def _reset_published_cache_for_tests() -> None:
    global _published_cache
    _published_cache = None
