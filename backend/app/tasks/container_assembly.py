"""Container assembly — membership, proved rather than curated. #2927 Phase 2.

Spec §6. One container per run. Read-only against every existing table: this
job writes `containers`' own edges and receipts and touches nothing else, so it
is D51-reversible by deleting the rows it wrote (the undo line is on
``UNDO_LINE`` below and is quoted in the alex-inbox note).

WHAT IT DOES.

1. **Resolve the container** by its `container_provider_anchors`.
2. **Gather candidates** from every source that can name a member.
3. **Test each candidate**, and write EITHER a `contains` edge with a class, a
   source and a confidence, OR a receipt naming the test it failed.
4. **Never absorb.** Assembly writes `contains` and nothing else. Ruling 048 is
   untouched: an id-less claim never absorbs, `same_as` is the drain's ledger
   and is not this job's to write, and twins stay lane1's under #2693 / D39.
   The rule is enforced by ``ASSEMBLY_WRITABLE_KINDS``, not left as prose.

MEMBERSHIP KEYS ON PROVIDER IDS, NEVER ON NAMES. This is the ordering
constraint spec §6 names and it is the single most important line in this file.
Name matching is what the register does today and ARTIFACT-M-20260903-I
measured its cost: 340 unmatched rows, 79 of them doubles slash-teams that
*"never match 2-name rows"*, and token-fallback catching 30+ false
doubles→singles hits. A doubles fixture matched by name onto a singles row is a
wrong answer that looks like a right one. Every gatherer below therefore yields
a candidate carrying an id we already hold — the register's own `market_id`,
a provider id from an anchor — and names are used only to CLASSIFY a candidate
that some id already admitted, never to find one.

EVERY CANDIDATE NOT EDGED GETS A RECEIPT. Membership is never a curated list,
and the receipt is how that is proved rather than asserted. A market rejected
from a container is `market_match_receipts` with `container_id` set,
`outcome='rejected'` and a `reject_reason` naming the test it failed.

ONE BAD CANDIDATE NEVER WIPES A PASS (gotcha #42). Per-item try/except around
every candidate, and the failure is recorded as
`container_attempt_error` rather than swallowed.

WHAT IT DELIBERATELY DOES NOT DO.
* It does not create events. A container cannot contain an event that does not
  exist; Kalshi's `KXATPMATCH-26SEP02AUGKHA` (FAA–Khachanov, two winner legs
  active, no event of ours) is lane1's under #2693 and this job reports it as a
  receipt rather than papering over it.
* It does not resolve twins, merge rows, or write `same_as`.
* It does not write receipts for non-market candidates. `market_match_receipts`
  is keyed on `market_id` with a real FK, so an event candidate that fails has
  nowhere to go in that table; those land in the run report's `unresolved` list
  instead, and that asymmetry is stated here rather than discovered later.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from sqlalchemy import text

from app.utils.container_class import MemberEvidence, classify_member
from app.utils.container_graph import (
    ASSEMBLY_WRITABLE_KINDS,
    EDGE_NODE_TABLES,
    ContainerVocabularyError,
    normalize_anchor_sport,
    validate_anchor_id_kind,
    validate_anchor_provider,
    validate_confidence,
    validate_edge_kind_and_class,
    validate_edge_source,
    validate_node_type,
)
from app.utils.match_receipts import (
    PHASE_CONTAINER_ASSEMBLY,
    REJECT_CONTAINER_ATTEMPT_ERROR,
    REJECT_CONTAINER_CHILD_MISSING,
    REJECT_CONTAINER_NOT_A_MEMBER,
    MatchReceipt,
    flush_receipts,
)

logger = logging.getLogger(__name__)

#: D51. What to run to undo one assembly pass. Quoted in the alex-inbox note
#: alongside the pass's own counts, so the undo is never reconstructed from
#: memory at the moment it is needed.
UNDO_LINE = (
    "DELETE FROM event_edges WHERE parent_type = 'container' "
    "AND parent_id = :container_id AND source = :source; "
    "UPDATE market_match_receipts SET container_id = NULL "
    "WHERE container_id = :container_id"
)

#: How confident each source is that its candidate is a member. These are
#: confidences about MEMBERSHIP, not about price or identity.
#:
#: The register and a provider id are both 1.0 and that is not laziness: both
#: are id-keyed. The register carries our own `futures_markets.id`, and a venue
#: grouping carries the venue's own event id. Neither is a guess. A source that
#: guessed would sit below 1.0, and there is deliberately no such source in
#: this file — see the module docstring's ordering constraint.
SOURCE_CONFIDENCE = {
    "register": 1.0,
    "venue_grouping": 1.0,
    "authority_tournament_id": 1.0,
}


# ---------------------------------------------------------------------------
# Candidates
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Candidate:
    """One thing that MIGHT be a member, and the id that says so.

    ``child_id`` is always an id we already hold. A gatherer that cannot
    produce one does not produce a candidate — it produces nothing, and the
    absence shows up in the completeness needle rather than as a name-matched
    guess.
    """

    child_type: str
    child_id: int
    source: str
    evidence: MemberEvidence
    #: Carried for the receipt, so "why is KXATPMATCH-… reachable from
    #: nowhere" is answerable without a join.
    external_id: Optional[str] = None
    market_source: Optional[str] = None

    @property
    def name(self) -> Optional[str]:
        return self.evidence.name


@dataclass
class AssemblyReport:
    """What one pass did. Returned, logged, and quoted in the alex-inbox note.

    ``by_class`` is the number the completeness needle reads. ``unresolved``
    holds candidates that could not even be receipted (non-market ids), so a
    zero-member pass is never indistinguishable from a container with no
    members — the failure mode gotcha #53 names.
    """

    container_id: int
    slug: str
    edges_written: int = 0
    receipts_written: int = 0
    by_class: dict = field(default_factory=dict)
    rejected: dict = field(default_factory=dict)
    unresolved: list = field(default_factory=list)
    errors: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "container_id": self.container_id,
            "slug": self.slug,
            "edges_written": self.edges_written,
            "receipts_written": self.receipts_written,
            "by_class": dict(sorted(self.by_class.items())),
            "rejected": dict(sorted(self.rejected.items())),
            "unresolved": self.unresolved[:50],
            "errors": self.errors[:20],
        }


# ---------------------------------------------------------------------------
# Gatherer: the register (spec §5 M4)
# ---------------------------------------------------------------------------


@dataclass
class RegisterHarvest:
    """What the register yielded, AND what it pinned that yielded nothing.

    ``unpriced`` IS THE HALF THAT MUST NOT BE DROPPED, and it is not a
    hypothetical. Measured against the committed US Open register on
    2026-09-05: **448 `reaches` rows carry only 336 market ids, and 124
    `matchups` rows carry only 116** — so 112 advancement ladders and 8 fixtures
    are pinned by the register with no market of ours behind them. Every one is
    a row the hub renders today and that the graph, on its own, would not.

    Spec §5 M4 is explicit that this is a RED and not a graceful degradation:
    *"if assembly yields less than the register did, that is a RED"*. Returning
    only the candidates would have made that impossible to see — the pass would
    report 458 happy members and the 120 missing rows would be nowhere, which
    is the silent loss this whole program exists to end. The hub cannot flip to
    reading the graph until this list is empty or explained.
    """

    candidates: list = field(default_factory=list)
    #: Register rows pinning a member we hold no market for. Each carries the
    #: kind, the draw and the register's own key, so the gap is diagnosable
    #: without re-reading the JSON.
    unpriced: list = field(default_factory=list)

    def summary(self) -> dict:
        counts: dict = {}
        for row in self.unpriced:
            counts[row["kind"]] = counts.get(row["kind"], 0) + 1
        return {"candidates": len(self.candidates), "unpriced_by_kind": counts}


def gather_register_candidates(register: dict) -> RegisterHarvest:
    """Every member the committed register already pins, keyed on OUR ids.

    Pure — takes the parsed JSON, returns candidates, touches no database. That
    is what makes the "container output ⊇ register output" comparison in spec
    §5 M4 gradeable without a tournament running.

    WHY THIS GATHERER EXISTS AT ALL, given the register already renders the
    hub. Because the hub's current content has to be reproducible FROM THE
    GRAPH before anything switches to reading the graph. Until that holds, a
    flip is a bet. And the register must never become the fallback that quietly
    hides an assembly failure: if assembly yields less than the register did,
    that is a RED, not a graceful degradation — which is a comparison you can
    only make if both sides are expressed as edges.

    EVERY ROW HERE CARRIES `market_id`, our own `futures_markets.id`. That is
    why the register is an id-keyed source and not a name-matched one, and it
    is the reason this gatherer can be trusted at confidence 1.0.
    """
    harvest = RegisterHarvest()
    seen: set[tuple] = set()

    def add(market_id: Any, evidence: MemberEvidence, external_id=None, src=None) -> bool:
        # A register row can name the same market from two source blocks (a
        # matchup priced on both venues). The edge's unique key would collapse
        # them anyway; deduping here keeps the receipt count honest.
        try:
            market_id = int(market_id)
        except (TypeError, ValueError):
            # No id: the register pins this member but we hold no market for
            # it. NOT silently skipped — the caller records it as unpriced.
            return False
        key = ("market", market_id)
        if key in seen:
            return True
        seen.add(key)
        harvest.candidates.append(
            Candidate(
                child_type="market",
                child_id=market_id,
                source="register",
                evidence=evidence,
                external_id=external_id,
                market_source=src,
            )
        )
        return True

    def note_unpriced(kind: str, key: Any, draw: Any) -> None:
        harvest.unpriced.append({"kind": kind, "key": key, "draw": draw})

    for matchup in register.get("matchups") or []:
        if not isinstance(matchup, dict):
            continue
        name = matchup.get("matchup_key")
        draw = matchup.get("draw")
        got = False
        for block in matchup.get("sources") or []:
            if not isinstance(block, dict):
                continue
            got |= add(
                block.get("market_id"),
                MemberEvidence(
                    node_type="market",
                    name=name,
                    register_kind="matchup",
                    draw=draw,
                    external_id=block.get("market_external_id"),
                ),
                external_id=block.get("market_external_id"),
                src=block.get("source"),
            )
        if not got:
            note_unpriced("matchup", name, draw)

    for reach in register.get("reaches") or []:
        if not isinstance(reach, dict):
            continue
        draw = reach.get("draw")
        got = False
        for block in reach.get("sources") or []:
            if not isinstance(block, dict):
                continue
            got |= add(
                block.get("market_id"),
                MemberEvidence(
                    node_type="market",
                    # The register stores the venue's own question text, which
                    # is a better classification input than a synthesised name.
                    name=block.get("question") or reach.get("entity_key"),
                    register_kind="reach",
                    draw=draw,
                    external_id=block.get("market_external_id"),
                ),
                external_id=block.get("market_external_id"),
                src=block.get("source"),
            )
        if not got:
            note_unpriced(
                "reach",
                f"{reach.get('entity_key')}@{reach.get('round')}",
                draw,
            )

    for prop in register.get("props") or []:
        if not isinstance(prop, dict):
            continue
        evidence_for = MemberEvidence(
            node_type="market",
            name=prop.get("title"),
            register_kind="prop",
            draw=prop.get("draw"),
            external_id=prop.get("market_external_id"),
        )
        # `markets` is the plural form; `market_id` is the singular legacy one.
        # Both are read, because a prop that lost its section because we only
        # looked at one spelling is precisely the silent loss this job exists
        # to end.
        got = False
        for block in prop.get("markets") or []:
            if isinstance(block, dict):
                got |= add(
                    block.get("market_id"),
                    evidence_for,
                    external_id=block.get("market_external_id"),
                    src=prop.get("source"),
                )
        got |= add(
            prop.get("market_id"),
            evidence_for,
            external_id=prop.get("market_external_id"),
            src=prop.get("source"),
        )
        if not got:
            note_unpriced("prop", prop.get("key"), prop.get("draw"))

    return harvest


# ---------------------------------------------------------------------------
# The sanctioned anchor writer (CERT-2006's follow-up)
# ---------------------------------------------------------------------------


class AnchorCollision(Exception):
    """Another container already owns this provider id in this namespace.

    D55: a collision **raises or tags — it never silently no-ops.** Raising is
    the whole value of the unique index; swallowing the conflict would turn the
    detector into a no-op and let two draws quietly become one hub.
    """

    def __init__(self, provider: str, sport, id_kind: str, provider_id: str, owner: int):
        self.owner_container_id = owner
        super().__init__(
            f"{provider}/{sport}/{id_kind}/{provider_id} is already claimed by "
            f"container {owner}"
        )


async def claim_container_anchor(
    session,
    *,
    container_id: int,
    provider: str,
    provider_id: str,
    id_kind: str,
    sport=None,
    claim_context: Optional[dict] = None,
) -> bool:
    """Bind one provider id to one container. THE sanctioned write path.

    Exists so that CERT-2006's follow-up cannot be forgotten by the next
    caller: ``sport`` is folded through
    :func:`~app.utils.container_graph.normalize_anchor_sport` HERE, once, on
    the only path that inserts. The index is ``NULLS NOT DISTINCT``, which
    makes NULL one namespace — but ``''`` is not NULL and ``'Tennis'`` is not
    ``'tennis'``, so a caller spelling "no sport" its own way would open a
    second namespace and defeat the constraint. A validator nobody is obliged
    to call is a validator that gets skipped; this is the obligation.

    Returns ``True`` when a row was written, ``False`` when this exact
    ``(container, provider, sport, id_kind, provider_id)`` was already bound —
    an idempotent re-claim by the same owner, which is what a nightly
    re-discovery does and is not a collision.

    Raises :class:`AnchorCollision` when a DIFFERENT container owns the key.
    """
    from app.models.models import ContainerProviderAnchor  # noqa: F401

    sport = normalize_anchor_sport(sport)
    validate_anchor_provider(provider)
    validate_anchor_id_kind(id_kind)

    existing = (
        await session.execute(
            text(
                "SELECT container_id FROM container_provider_anchors "
                "WHERE provider = :provider AND id_kind = :id_kind "
                "  AND provider_id = :provider_id "
                "  AND sport IS NOT DISTINCT FROM :sport"
            ),
            {
                "provider": provider,
                "id_kind": id_kind,
                "provider_id": provider_id,
                "sport": sport,
            },
        )
    ).fetchone()

    if existing is not None:
        owner = int(existing[0])
        if owner == container_id:
            return False
        raise AnchorCollision(provider, sport, id_kind, provider_id, owner)

    await session.execute(
        text(
            "INSERT INTO container_provider_anchors "
            "(container_id, provider, sport, provider_id, id_kind, claim_context) "
            "VALUES (:container_id, :provider, :sport, :provider_id, :id_kind, "
            "        CAST(:claim_context AS jsonb))"
        ),
        {
            "container_id": container_id,
            "provider": provider,
            "sport": sport,
            "provider_id": provider_id,
            "id_kind": id_kind,
            "claim_context": json.dumps(claim_context) if claim_context else None,
        },
    )
    return True


# ---------------------------------------------------------------------------
# Gatherer: venue grouping
# ---------------------------------------------------------------------------

#: Which `futures_markets` column an anchor's `id_kind` addresses. Explicit,
#: because inferring it from the shape of the id is the D55 mistake — a Kalshi
#: series ticker and a Polymarket slug are both bare strings.
_ANCHOR_KIND_TO_PREDICATE = {
    # A Kalshi series ticker prefixes every market ticker in the series:
    # `KXATPMATCH` -> `KXATPMATCH-26SEP02AUGKHA`. Anchored LIKE, so it is
    # index-servable and cannot match mid-string.
    "series": "fm.external_id LIKE :pattern",
    # Polymarket groups its sub-markets under one `group_id`.
    "event_slug": "fm.group_id = :exact",
    "tag": "fm.group_id = :exact",
}


async def gather_venue_candidates(session, anchors: Iterable) -> list[Candidate]:
    """Markets the venue itself groups under one of the container's anchors.

    Id-keyed by construction: the anchor holds the venue's own series ticker or
    event slug, and this asks the venue's own grouping column for its members.
    No name is read to FIND anything here.

    NOTE ON `LIKE`. The pattern is built with an explicit trailing `-%` and the
    literal is escaped, because an unescaped `_` in a ticker is a single-char
    wildcard in `LIKE` and `KXATP_MATCH` would silently widen to every
    six-letter prefix. Binding it as a parameter is also what keeps it out of
    gotcha #45's trap, where a `LIKE '%:x'` inside `text()` parses as a bind.
    """
    candidates: list[Candidate] = []
    seen: set[int] = set()

    for anchor in anchors:
        predicate = _ANCHOR_KIND_TO_PREDICATE.get(anchor.id_kind)
        if predicate is None:
            # An anchor kind that names no grouping column is not an error —
            # a `tournament` or `league` anchor is for the authority gatherer.
            continue

        escaped = (
            anchor.provider_id.replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
        )
        params = {"pattern": f"{escaped}-%", "exact": anchor.provider_id}
        sql = text(
            "SELECT fm.id, fm.name, fm.external_id, fm.source, fm.market_type "
            "FROM futures_markets fm "
            f"WHERE {predicate} "
            "  AND fm.status <> 'resolved' "
            "LIMIT 5000"
        )
        # No explicit ESCAPE clause: backslash is PostgreSQL's default LIKE
        # escape character, which is what the escaping above relies on.
        result = await session.execute(sql, params)
        for row in result.fetchall():
            market_id = int(row[0])
            if market_id in seen:
                continue
            seen.add(market_id)
            candidates.append(
                Candidate(
                    child_type="market",
                    child_id=market_id,
                    source="venue_grouping",
                    evidence=MemberEvidence(
                        node_type="market",
                        name=row[1],
                        market_shape=row[4],
                        external_id=row[2],
                    ),
                    external_id=row[2],
                    market_source=row[3],
                )
            )
    return candidates


# ---------------------------------------------------------------------------
# The pass
# ---------------------------------------------------------------------------


async def _live_ids(session, child_type: str, ids: set[int]) -> set[int]:
    """Which of these ids actually exist, as rows of the declared type.

    THE INTEGRITY THE MISSING FOREIGN KEY CANNOT GIVE (spec §2). `event_edges`
    has no FK on `child_id` because the type varies, so this check runs BEFORE
    the edge is written rather than as a nightly cleanup. An edges table
    without it is a second place for dangling ids to hide, and #2914 already
    shows what unreachable rows cost.

    The table name comes from `EDGE_NODE_TABLES`, never from a hand-written
    CASE, so a new node type cannot be added without this learning about it in
    the same commit.
    """
    if not ids:
        return set()
    table = EDGE_NODE_TABLES[validate_node_type(child_type, "child_type")]
    result = await session.execute(
        text(f"SELECT id FROM {table} WHERE id = ANY(:ids)"),
        {"ids": list(ids)},
    )
    return {int(r[0]) for r in result.fetchall()}


async def assemble_container(session, container, candidates: list[Candidate]) -> AssemblyReport:
    """Write the `contains` edges for one container, and receipt the rest.

    Idempotent. The edge's unique key `(parent_type, parent_id, child_type,
    child_id, kind)` is the ON CONFLICT target, so a nightly re-run updates the
    class and confidence in place instead of doubling every member — which is
    the failure that would make the hub grow without bound and look, from the
    outside, like the container was working unusually well.
    """
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.models.models import EventEdge

    report = AssemblyReport(container_id=container.id, slug=container.slug)
    now = datetime.now(timezone.utc)

    # One existence query per child type, not one per candidate. A COUNT in a
    # loop re-scans the whole table when the key is a Join Filter rather than
    # an Index Cond; `id = ANY(:ids)` on the primary key is one index scan.
    by_type: dict[str, set[int]] = {}
    for candidate in candidates:
        by_type.setdefault(candidate.child_type, set()).add(candidate.child_id)
    live: dict[str, set[int]] = {}
    for child_type, ids in by_type.items():
        live[child_type] = await _live_ids(session, child_type, ids)

    rows: list[dict] = []
    receipts: list[MatchReceipt] = []

    for candidate in candidates:
        try:
            receipt = None
            if candidate.child_type == "market":
                receipt = MatchReceipt(
                    market_id=candidate.child_id,
                    source=candidate.market_source or candidate.source,
                    external_id=candidate.external_id,
                    market_name=candidate.name,
                    phase=PHASE_CONTAINER_ASSEMBLY,
                    attempted_at=now,
                    container_id=container.id,
                )

            if candidate.child_id not in live.get(candidate.child_type, ()):
                # The id does not resolve. A container cannot contain a row
                # that does not exist — report it, never paper over it.
                if receipt is not None:
                    receipt.reject(
                        REJECT_CONTAINER_CHILD_MISSING,
                        child_type=candidate.child_type,
                        child_id=candidate.child_id,
                    )
                    receipts.append(receipt)
                else:
                    report.unresolved.append(
                        {
                            "child_type": candidate.child_type,
                            "child_id": candidate.child_id,
                            "name": candidate.name,
                            "source": candidate.source,
                        }
                    )
                report.rejected[REJECT_CONTAINER_CHILD_MISSING] = (
                    report.rejected.get(REJECT_CONTAINER_CHILD_MISSING, 0) + 1
                )
                continue

            member_class = classify_member(candidate.evidence)
            source = validate_edge_source(candidate.source)
            confidence = validate_confidence(SOURCE_CONFIDENCE.get(source, 0.5))
            kind, member_class = validate_edge_kind_and_class("contains", member_class)
            assert kind in ASSEMBLY_WRITABLE_KINDS  # enforced, not assumed

            rows.append(
                {
                    "parent_type": "container",
                    "parent_id": container.id,
                    "child_type": candidate.child_type,
                    "child_id": candidate.child_id,
                    "kind": kind,
                    "class": member_class,
                    "source": source,
                    "confidence": confidence,
                }
            )
            report.by_class[member_class] = report.by_class.get(member_class, 0) + 1

            if receipt is not None:
                receipt.outcome = "linked"
                receipt.reject_reason = None
                receipt.detail.update(
                    {"container_slug": container.slug, "member_class": member_class}
                )
                receipts.append(receipt)

        except ContainerVocabularyError as exc:
            # A vocabulary error is a bug in this file, not bad data — record
            # it loudly and keep going, so one wrong class cannot cost a pass.
            report.errors.append(f"{candidate.child_type}:{candidate.child_id}: {exc}")
            logger.error("container assembly vocabulary error: %s", exc)
        except Exception as exc:  # noqa: BLE001 — gotcha #42
            report.errors.append(f"{candidate.child_type}:{candidate.child_id}: {exc!r}")
            logger.exception("container assembly candidate failed")
            if candidate.child_type == "market":
                failed = MatchReceipt(
                    market_id=candidate.child_id,
                    source=candidate.market_source or candidate.source,
                    external_id=candidate.external_id,
                    market_name=candidate.name,
                    phase=PHASE_CONTAINER_ASSEMBLY,
                    attempted_at=now,
                    container_id=container.id,
                )
                failed.reject(REJECT_CONTAINER_ATTEMPT_ERROR, error=repr(exc))
                receipts.append(failed)
            report.rejected[REJECT_CONTAINER_ATTEMPT_ERROR] = (
                report.rejected.get(REJECT_CONTAINER_ATTEMPT_ERROR, 0) + 1
            )

    # Deduplicate on the edge's own unique key before the upsert: Postgres
    # refuses an ON CONFLICT statement that hits one key twice in a command
    # ("cannot affect row a second time"), and two gatherers CAN legitimately
    # find the same market.
    deduped: dict[tuple, dict] = {}
    for row in rows:
        deduped[
            (row["parent_type"], row["parent_id"], row["child_type"], row["child_id"], row["kind"])
        ] = row
    ordered = list(deduped.values())

    for start in range(0, len(ordered), 500):
        batch = ordered[start : start + 500]
        stmt = pg_insert(EventEdge).values(batch)
        stmt = stmt.on_conflict_do_update(
            index_elements=["parent_type", "parent_id", "child_type", "child_id", "kind"],
            set_={
                "class": stmt.excluded["class"],
                "source": stmt.excluded.source,
                "confidence": stmt.excluded.confidence,
            },
        )
        await session.execute(stmt)
        report.edges_written += len(batch)

    if receipts:
        report.receipts_written = await flush_receipts(session, receipts)

    return report


# ---------------------------------------------------------------------------
# Bootstrap: the container tree a tournament needs before assembly can run
# ---------------------------------------------------------------------------

#: The draws a tennis tournament has. Named, not inferred, and this list is the
#: ONLY hand-written thing in the whole program — the spec's promise is that
#: nobody writes a list of MEMBERS, not that nobody names the draws a Slam has.
#: Each becomes a child container with its own anchor and its own status, which
#: is what lets Men's Doubles go `final` while Mixed is still `live`.
TENNIS_DRAWS = (
    ("mens-singles", "Men's Singles"),
    ("womens-singles", "Women's Singles"),
    ("mens-doubles", "Men's Doubles"),
    ("womens-doubles", "Women's Doubles"),
    ("mixed-doubles", "Mixed Doubles"),
)


@dataclass(frozen=True)
class PlannedContainer:
    """One row `bootstrap_container_tree` would write. A PLAN, not a write."""

    slug: str
    name: str
    kind: str
    parent_slug: Optional[str] = None
    category: Optional[str] = None


def plan_container_tree(
    tournament: str, season: str, display_name: str, draws=TENNIS_DRAWS
) -> list[PlannedContainer]:
    """The parent container and one child per draw. Pure — returns a plan.

    SEPARATED FROM THE WRITE ON PURPOSE. A plan that can be printed, diffed and
    tested without a database is a plan somebody will actually read before it
    runs, and D51's shape is "say what you did and the undo line" — which is
    much easier to honour when the *intent* was reviewable first. It is also
    what lets the slug contract below be tested at all.

    SLUGS ARE DERIVED, NEVER TYPED. `us-open` + `2026` + `mens-doubles` →
    `us-open-2026-mens-doubles`, always. The slug is the public URL and the
    unique key, so a hand-typed one is a 404 waiting for a typo — and because
    it is derived, a re-run produces the same slugs and the bootstrap is
    idempotent for free.
    """
    root = f"{tournament}-{season}"
    plan = [
        PlannedContainer(slug=root, name=display_name, kind="tournament")
    ]
    for draw_slug, draw_name in draws:
        plan.append(
            PlannedContainer(
                slug=f"{root}-{draw_slug}",
                name=f"{display_name} — {draw_name}",
                kind="tournament",
                parent_slug=root,
            )
        )
    return plan


async def apply_container_tree(session, plan: list[PlannedContainer]) -> dict:
    """Create the planned containers if they do not exist. Idempotent.

    Never updates an existing row. A container that is already there may have
    had its `status` set by its authority (D27) or its window corrected, and a
    bootstrap re-run must not stamp over that — the job's purpose is to make
    the tree EXIST, not to own it afterwards.

    Parents are created before children in one pass, which is safe because
    `plan_container_tree` always emits the root first; the lookup below does
    not assume it, so a hand-built plan in the wrong order fails loudly on the
    missing parent instead of silently orphaning a draw.
    """
    created: list[str] = []
    existing: list[str] = []
    by_slug: dict[str, int] = {}

    for planned in plan:
        row = (
            await session.execute(
                text("SELECT id FROM containers WHERE slug = :slug"),
                {"slug": planned.slug},
            )
        ).fetchone()
        if row is not None:
            by_slug[planned.slug] = int(row[0])
            existing.append(planned.slug)
            continue

        parent_id = None
        if planned.parent_slug is not None:
            parent_id = by_slug.get(planned.parent_slug)
            if parent_id is None:
                parent_row = (
                    await session.execute(
                        text("SELECT id FROM containers WHERE slug = :slug"),
                        {"slug": planned.parent_slug},
                    )
                ).fetchone()
                if parent_row is None:
                    raise ValueError(
                        f"{planned.slug!r} names parent {planned.parent_slug!r}, "
                        "which does not exist and is not earlier in the plan"
                    )
                parent_id = int(parent_row[0])

        new_row = (
            await session.execute(
                text(
                    "INSERT INTO containers "
                    "(kind, name, slug, category, parent_container_id) "
                    "VALUES (:kind, :name, :slug, :category, :parent_id) "
                    "RETURNING id"
                ),
                {
                    "kind": planned.kind,
                    "name": planned.name,
                    "slug": planned.slug,
                    "category": planned.category,
                    "parent_id": parent_id,
                },
            )
        ).fetchone()
        by_slug[planned.slug] = int(new_row[0])
        created.append(planned.slug)

    return {"created": created, "existing": existing, "ids": by_slug}


#: D51. Undo for one bootstrap, and it is deliberately narrow: it removes only
#: containers that hold NO edges, so a re-run after assembly cannot delete a
#: populated hub. The slugs to pass are the `created` list the apply returned —
#: never `existing`, which the bootstrap did not create and must not remove.
BOOTSTRAP_UNDO_LINE = (
    "DELETE FROM containers c WHERE c.slug = ANY(:created_slugs) "
    "AND NOT EXISTS (SELECT 1 FROM event_edges e "
    "                WHERE e.parent_type = 'container' AND e.parent_id = c.id)"
)


# ---------------------------------------------------------------------------
# The invariant check — part of the ship, not a follow-up (spec §2)
# ---------------------------------------------------------------------------


async def find_dangling_edges(session, limit: int = 500) -> list[dict]:
    """Every `contains` edge whose child does not resolve to a live row.

    Spec §2 is explicit that this is part of the ship: *"an edges table without
    it is a second place for dangling ids to hide, and we already have #2914 to
    show what unreachable rows cost."* Assembly checks before it writes, but a
    row can be deleted afterwards — a settled market purged, a twin cleanup
    removing an event — and nothing else in the schema would notice, because
    `child_id` carries no foreign key.

    The type→table map comes from `EDGE_NODE_TABLES`, so this cannot fall
    behind a new node type.
    """
    findings: list[dict] = []
    for child_type, table in sorted(EDGE_NODE_TABLES.items()):
        result = await session.execute(
            text(
                "SELECT e.id, e.parent_id, e.child_id, e.class "
                "FROM event_edges e "
                f"LEFT JOIN {table} t ON t.id = e.child_id "
                "WHERE e.kind = 'contains' AND e.child_type = :ct "
                "  AND t.id IS NULL "
                "LIMIT :limit"
            ),
            {"ct": child_type, "limit": limit},
        )
        for row in result.fetchall():
            findings.append(
                {
                    "edge_id": int(row[0]),
                    "parent_id": int(row[1]),
                    "child_type": child_type,
                    "child_id": int(row[2]),
                    "class": row[3],
                }
            )
    return findings


def container_chain_has_cycle(parent_of: dict, start: int) -> bool:
    """Would following `parent_container_id` from ``start`` loop forever?

    The one-hop case is a CHECK constraint; a longer cycle cannot be expressed
    as one and lives here, exactly as the spec says (§1). Floyd's tortoise and
    hare so a cycle costs no allocation and a long legitimate chain costs one
    pass.
    """
    slow = fast = start
    while True:
        slow = parent_of.get(slow)
        fast = parent_of.get(parent_of.get(fast)) if parent_of.get(fast) else None
        if slow is None or fast is None:
            return False
        if slow == fast:
            return True
