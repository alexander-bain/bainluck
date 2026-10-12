"""One provider event, one collection — the pure half. #5343 (correction safety #5344).

PILLARS MATCHING · DISCOVER · TRUTH. SHIP: a source-backed politics, economics,
technology or entertainment event becomes a useful, complete collection on its
own, and the NEXT provider event uses this same code — no member list, no edition
declaration, no registry row. The NFL/MLB adapters and the theme registry are
untouched; this is a third, provider-shaped source of collections.

No database, no network, no clock: every rule below is gradeable from a fixture.
The writer is ``app.tasks.provider_event_collection_assembly``.

WHAT A PROVIDER EVENT PROVES, AND WHAT IT DOES NOT.

* Polymarket's immutable ``event.id`` is the identity. Ingestion already writes it
  twice: ``group_id = 'polymarket:{id}'`` on every row of the event, and
  ``market_metadata.polymarket_event_id`` on the parent and (since Queue 390) on
  each decomposed child. Both are read; when both are present they must agree.
* Sharing an event proves the markets are RELATED. It never proves they are
  mutually exclusive or that two of them ask the same question, so nothing here
  folds members, averages a price, or pairs a market with another provider's.
* The event title is the collection's LABEL. It never decides membership, so a
  renamed event keeps its slug and its members, and two events that share a title
  stay two collections.

COMPLETENESS NEEDS A ROSTER. A collection is complete only against the
provider's own full list of the event's markets, observed at one instant:
``market_metadata['polymarket_event_roster']`` on the parent row (contract in
``parse_roster``). ``market_count`` alone, or "some rows exist", is not a roster:
ingestion skips markets with no positive price, so the rows we hold can be fewer
than the event has, and the count cannot tell which. Without a usable roster a
collection still assembles from row evidence, but it is never complete and so
never eligible for publication.

WHAT A PASS MAY SUBTRACT. A member leaves only when (a) a correction withdrew it,
(b) its own row now names a different event, or (c) a usable roster — at least as
new as the last one applied — no longer lists it. An outage (no roster, an older
roster, an expired roster, a row we cannot see) never retires anything: the last
good membership is carried. A member a roster removed is not re-admitted until a
NEWER roster lists it again, so a regressed observation cannot resurrect it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping, Optional, Sequence

from app.utils.container_graph import CLASS_UNCLASSIFIED

# ---------------------------------------------------------------------------
# Policy constants. Adapter-wide; nothing here names an event.
# ---------------------------------------------------------------------------

#: Written on every decision row (``container_member_decisions.rule_version``,
#: VARCHAR(32)). Bump when a rule below changes what a pass decides.
RULE_VERSION = "provider-event-v1"

#: ``containers.kind``. The closed vocabulary has no provider-event kind;
#: ``theme`` ("a continuing subject collection") is the nearest existing word, and
#: no reader branches on it — the theme READ path keys on the slug, which this
#: adapter's slugs never match (see ``slug_for``).
CONTAINER_KIND = "theme"

#: ``event_edges.source``: the venue's own grouping.
EDGE_SOURCE = "venue_grouping"

#: A provider event proves membership, not a section. Members are shown as one
#: list; ``unclassified`` is the vocabulary's word for "we did not classify".
EDGE_CLASS = CLASS_UNCLASSIFIED

CHILD_TYPE = "market"

#: The domains this ship serves (``futures_markets.llm_sport_category``). Sports
#: events already have game pages and their own adapters; crypto is not ingested.
SUPPORTED_DOMAINS = frozenset(
    {"politics", "geopolitics", "economics", "tech", "entertainment"}
)

#: A collection of one card is that card.
MIN_MEMBERS = 2

#: Ingestion polls Polymarket hourly. A roster older than this still decides
#: membership (it is the newest word we have) but cannot make a collection
#: eligible for publication.
ROSTER_MAX_AGE = timedelta(hours=6)

#: How long after the provider's own window closes a finished collection stays
#: eligible for discovery. Its page and members are kept either way.
RETIRE_AFTER = timedelta(days=14)

#: Where ingestion is asked to stamp the roster (the parent row's metadata).
ROSTER_KEY = "polymarket_event_roster"

LABEL_MAX = 200

# ---------------------------------------------------------------------------
# Closed vocabulary. Outcomes match ``ck_cmd_outcome``; reasons fit VARCHAR(40).
# Ops vocabulary only — never reader text (notice 34).
# ---------------------------------------------------------------------------

OUTCOME_ADMITTED = "admitted"
OUTCOME_EXCLUDED = "excluded"
OUTCOME_WITHHELD = "withheld"

ADMITTED_ROSTER_MEMBER = "admitted_roster_member"
ADMITTED_ROW_IDENTITY = "admitted_row_identity"
CARRIED_ROW_ABSENT = "carried_member_row_absent"
CARRIED_DOMAIN_UNSUPPORTED = "carried_domain_unsupported"
EXCLUDED_GROUP_ANCHOR = "provider_group_anchor"
EXCLUDED_NOT_IN_ROSTER = "not_in_provider_roster"
EXCLUDED_IDENTITY_CONFLICT = "provider_identity_conflict"
EXCLUDED_IDENTITY_MOVED = "provider_identity_moved"
EXCLUDED_MALFORMED_MEMBER = "malformed_provider_member_id"
EXCLUDED_UNSUPPORTED_DOMAIN = "unsupported_domain"
EXCLUDED_WITHDRAWN = "container_member_withdrawn"
EXCLUDED_ROW_ABSENT = "member_row_absent"

MEMBER_REASONS = frozenset(
    {
        ADMITTED_ROSTER_MEMBER,
        ADMITTED_ROW_IDENTITY,
        CARRIED_ROW_ABSENT,
        CARRIED_DOMAIN_UNSUPPORTED,
        EXCLUDED_GROUP_ANCHOR,
        EXCLUDED_NOT_IN_ROSTER,
        EXCLUDED_IDENTITY_CONFLICT,
        EXCLUDED_IDENTITY_MOVED,
        EXCLUDED_MALFORMED_MEMBER,
        EXCLUDED_UNSUPPORTED_DOMAIN,
        EXCLUDED_WITHDRAWN,
        EXCLUDED_ROW_ABSENT,
    }
)

# Roster states.
ROSTER_USABLE = "usable"
ROSTER_ABSENT = "roster_absent"
ROSTER_MALFORMED = "roster_malformed"
ROSTER_OLDER_THAN_APPLIED = "roster_older_than_applied"

# Domain states.
DOMAIN_UNKNOWN = "domain_unknown"
DOMAIN_AMBIGUOUS = "domain_ambiguous"
DOMAIN_UNSUPPORTED = "domain_unsupported"

# Publication-eligibility refusals.
INELIGIBLE_ROSTER_EXPIRED = "roster_expired"
INELIGIBLE_ROSTER_UNSTORED = "roster_members_unstored"
INELIGIBLE_IDENTITY_CONFLICTS = "identity_conflicts"
INELIGIBLE_TOO_FEW_MEMBERS = "too_few_members"
INELIGIBLE_LABEL_ABSENT = "label_absent"
INELIGIBLE_RETIRED = "retired"
INELIGIBLE_PUBLICATION_WITHDRAWN = "publication_withdrawn"

# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------

PROVIDER_POLYMARKET = "polymarket"

_EVENT_ID_RE = re.compile(r"^[1-9][0-9]{0,17}$")
_CONDITION_ID_RE = re.compile(r"^0x[0-9a-f]{64}$")
_GROUP_PREFIX = "polymarket:"
_SLUG_PREFIX = "polymarket-event-"
_SLUG_RE = re.compile(r"^polymarket-event-([1-9][0-9]{0,17})$")


@dataclass(frozen=True)
class ProviderEventIdentity:
    """A provider-qualified event id. Construct through the parsers, which refuse
    anything that is not exactly the provider's own grammar."""

    provider: str
    event_id: str

    @property
    def group_id(self) -> str:
        return f"{_GROUP_PREFIX}{self.event_id}"

    @property
    def slug(self) -> str:
        return slug_for(self)

    def as_dict(self) -> dict:
        return {
            "provider": self.provider,
            "event_id": self.event_id,
            "group_id": self.group_id,
            "slug": self.slug,
        }


def _event_identity(raw: Any) -> Optional[ProviderEventIdentity]:
    if isinstance(raw, bool) or raw is None:
        return None
    value = str(raw)
    if not _EVENT_ID_RE.fullmatch(value):
        return None
    return ProviderEventIdentity(PROVIDER_POLYMARKET, value)


def identity_from_group_id(group_id: Any) -> Optional[ProviderEventIdentity]:
    """``'polymarket:42'`` → identity. Anything else (another provider's
    group, a blank, ``'polymarket:01'``, ``'polymarket:12:x'``) → None."""
    if not isinstance(group_id, str) or not group_id.startswith(_GROUP_PREFIX):
        return None
    return _event_identity(group_id[len(_GROUP_PREFIX) :])


def slug_for(identity: ProviderEventIdentity) -> str:
    """The collection's URL. Built from the id alone so a renamed event keeps it.

    ``polymarket-event-<id>`` cannot be an NFL/MLB slug (``nfl-``/``mlb-``) and is
    never a theme slug: the theme parser only answers for its registry's subjects
    and ``polymarket-event`` is not one, so ``edition_for_slug`` returns None and
    the route serves the simple published envelope.
    """
    return f"{_SLUG_PREFIX}{identity.event_id}"


def parse_collection_slug(slug: Any) -> Optional[ProviderEventIdentity]:
    """The identity a slug names, or None. Exact: the builder must reproduce it."""
    if not isinstance(slug, str):
        return None
    match = _SLUG_RE.match(slug)
    if not match:
        return None
    identity = _event_identity(match.group(1))
    return identity if identity is not None and slug_for(identity) == slug else None


def _condition_id(raw: Any) -> Optional[str]:
    if not isinstance(raw, str):
        return None
    value = raw.strip().lower()
    return value if _CONDITION_ID_RE.match(value) else None


# ---------------------------------------------------------------------------
# Rows, copied to plain data before any decision (gotcha #6)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProviderRow:
    id: int
    source: str
    external_id: str
    group_id: Optional[str]
    status: Optional[str]
    name: Optional[str]
    domain: Optional[str]
    commence_time: Optional[datetime]
    resolution_date: Optional[datetime]
    metadata_event_id: Optional[str]
    event_title: Optional[str]
    roster_raw: Any = None


def _get(obj: Any, name: str) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(name)
    return getattr(obj, name, None)


def provider_row(market: Any) -> ProviderRow:
    """A ``futures_markets`` row (ORM object, Row mapping or dict) as plain data."""
    meta = _get(market, "market_metadata")
    meta = meta if isinstance(meta, Mapping) else {}
    raw_eid = meta.get("polymarket_event_id")
    title = meta.get("event_title")
    domain = _get(market, "llm_sport_category")
    return ProviderRow(
        id=int(_get(market, "id")),
        source=str(_get(market, "source") or ""),
        external_id=str(_get(market, "external_id") or ""),
        group_id=_get(market, "group_id"),
        status=_get(market, "status"),
        name=_get(market, "name"),
        domain=(
            domain.strip().lower()
            if isinstance(domain, str) and domain.strip()
            else None
        ),
        commence_time=_get(market, "commence_time"),
        resolution_date=_get(market, "resolution_date"),
        metadata_event_id=(
            None
            if raw_eid is None or isinstance(raw_eid, bool)
            else str(raw_eid).strip()
        ),
        event_title=title.strip() if isinstance(title, str) and title.strip() else None,
        roster_raw=meta.get(ROSTER_KEY),
    )


# ---------------------------------------------------------------------------
# The roster contract
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RosterMember:
    external_id: str
    closed: Optional[bool]


@dataclass(frozen=True)
class ProviderEventRoster:
    """The provider's full list of one event's markets at one instant."""

    observed_at: datetime
    members: tuple[RosterMember, ...]
    event_closed: Optional[bool]

    @property
    def external_ids(self) -> frozenset:
        return frozenset(m.external_id for m in self.members)


def _parse_instant(raw: Any) -> Optional[datetime]:
    if isinstance(raw, datetime):
        value = raw
    elif isinstance(raw, str) and raw.strip():
        try:
            value = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    return value if value.tzinfo is not None else None


def _optional_bool(raw: Any) -> tuple[bool, Optional[bool]]:
    if raw is None:
        return True, None
    if isinstance(raw, bool):
        return True, raw
    return False, None


def parse_roster(raw: Any) -> tuple[Optional[ProviderEventRoster], Optional[str]]:
    """``(roster, None)`` or ``(None, reason)``. Fails closed on any doubt.

    The stored shape (one JSON object, so the list and its instant cannot drift)::

        {"observed_at": "2026-10-12T00:49:13Z",   # tz-aware ISO 8601
         "complete": true,                        # the payload was the whole event
         "event_closed": false,                   # the provider's own event flag
         "markets": [{"id": "0x…64 hex", "closed": false}, …]}

    ``complete`` must be literally ``true``: a writer that saw a page of the event
    must not be able to stamp a roster by omission. Every id must be a condition
    id, each at most once, and the list must not be empty.
    """
    if raw is None:
        return None, ROSTER_ABSENT
    if not isinstance(raw, Mapping):
        return None, ROSTER_MALFORMED
    observed_at = _parse_instant(raw.get("observed_at"))
    if observed_at is None or raw.get("complete") is not True:
        return None, ROSTER_MALFORMED
    ok, event_closed = _optional_bool(raw.get("event_closed"))
    markets = raw.get("markets")
    if not ok or not isinstance(markets, list) or not markets:
        return None, ROSTER_MALFORMED
    seen: set = set()
    members = []
    for entry in markets:
        if not isinstance(entry, Mapping):
            return None, ROSTER_MALFORMED
        external_id = _condition_id(entry.get("id"))
        ok, closed = _optional_bool(entry.get("closed"))
        if external_id is None or not ok or external_id in seen:
            return None, ROSTER_MALFORMED
        seen.add(external_id)
        members.append(RosterMember(external_id, closed))
    return (
        ProviderEventRoster(
            observed_at.astimezone(timezone.utc), tuple(members), event_closed
        ),
        None,
    )


# ---------------------------------------------------------------------------
# One pass's decisions for one event
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PriorDecision:
    """What the last pass recorded about a child (its decision row).

    ``applied_roster_at`` is the newest roster applied to the container as of that
    row — the evidence's ``applied_roster_at``."""

    child_id: int
    reason: Optional[str]
    external_id: Optional[str]
    applied_roster_at: Optional[datetime]


@dataclass(frozen=True)
class MemberDecision:
    child_id: int
    outcome: str
    reason: str
    keep_edge: bool
    evidence: dict


@dataclass(frozen=True)
class Header:
    name: Optional[str]
    category: Optional[str]
    status: Optional[str]
    window_start: Optional[datetime]
    window_end: Optional[datetime]


@dataclass(frozen=True)
class EventAssembly:
    identity: ProviderEventIdentity
    decisions: tuple[MemberDecision, ...]
    header: Header
    domain: Optional[str]
    domain_state: Optional[str]
    roster: Optional[ProviderEventRoster]
    roster_state: str
    roster_unstored: tuple[str, ...]
    identity_conflicts: tuple[int, ...]
    complete: bool

    @property
    def admitted(self) -> tuple[int, ...]:
        return tuple(
            d.child_id for d in self.decisions if d.outcome == OUTCOME_ADMITTED
        )

    @property
    def kept(self) -> dict:
        return {d.child_id: EDGE_CLASS for d in self.decisions if d.keep_edge}


def latest_roster_epoch(prior: Mapping[int, PriorDecision]) -> Optional[datetime]:
    """The newest roster any earlier pass applied to this container."""
    stamps = [
        p.applied_roster_at for p in prior.values() if p.applied_roster_at is not None
    ]
    return max(stamps) if stamps else None


def _event_domain(rows: Iterable[ProviderRow]) -> tuple[Optional[str], Optional[str]]:
    domains = {r.domain for r in rows if r.domain}
    if not domains:
        return None, DOMAIN_UNKNOWN
    if len(domains) > 1:
        return None, DOMAIN_AMBIGUOUS
    (domain,) = domains
    return domain, None if domain in SUPPORTED_DOMAINS else DOMAIN_UNSUPPORTED


def _label(
    parent: Optional[ProviderRow], children: Sequence[ProviderRow]
) -> Optional[str]:
    """The provider's title: the parent's, else one title every child agrees on."""
    own = (
        (parent.event_title or parent.name or "").strip() if parent is not None else ""
    )
    if own:
        return own[:LABEL_MAX]
    titles = {c.event_title for c in children if c.event_title}
    return next(iter(titles))[:LABEL_MAX] if len(titles) == 1 else None


def _status(
    roster: Optional[ProviderEventRoster], current: Optional[str]
) -> Optional[str]:
    """The provider's own event flag decides. No flag, no change (D27: never
    inferred from whichever children we happen to hold)."""
    if roster is None or roster.event_closed is None:
        return current
    return "final" if roster.event_closed else "scheduled"


def assemble_event(
    identity: ProviderEventIdentity,
    rows: Iterable[ProviderRow],
    *,
    edged: Iterable[int] = (),
    withdrawn: Iterable[int] = (),
    prior: Optional[Mapping[int, PriorDecision]] = None,
    current_status: Optional[str] = None,
) -> EventAssembly:
    """Decide every child this pass can see, plus every child already edged.

    ``rows`` are the provider's rows that claim this event's ``group_id`` and the
    rows behind the container's current edges (read in the same transaction).
    ``edged`` is the children holding this adapter's edge now; ``withdrawn`` the
    children whose latest correction is a withdrawal; ``prior`` the last pass's
    decision rows. Duplicate rows collapse by id; nothing collapses by name.
    """
    prior = dict(prior or {})
    edged_ids = frozenset(int(i) for i in edged)
    withdrawn_ids = frozenset(int(i) for i in withdrawn)
    by_id: dict[int, ProviderRow] = {}
    for row in rows:
        by_id.setdefault(int(row.id), row)

    def claims_event(r: ProviderRow) -> bool:
        return (
            r.source == PROVIDER_POLYMARKET
            and identity_from_group_id(r.group_id) == identity
        )

    claimants = [r for r in by_id.values() if claims_event(r)]
    parent = next((r for r in claimants if r.external_id == identity.event_id), None)
    children = [r for r in claimants if r is not parent]
    domain, domain_state = _event_domain(claimants)

    roster, roster_state = parse_roster(
        parent.roster_raw if parent is not None else None
    )
    applied = latest_roster_epoch(prior)
    if roster is not None and applied is not None and roster.observed_at < applied:
        roster, roster_state = None, ROSTER_OLDER_THAN_APPLIED
    else:
        roster_state = roster_state or ROSTER_USABLE
    roster_ids = roster.external_ids if roster is not None else frozenset()
    # The newest roster ever applied travels on every decision row, including the
    # rows a roster-less or older-roster pass writes — otherwise that pass would
    # erase the epoch and the pass after it would take a stale roster as new.
    applied_at = roster.observed_at if roster is not None else applied

    base = {
        "provider": identity.provider,
        "provider_event_id": identity.event_id,
        "group_id": identity.group_id,
        "rule_version": RULE_VERSION,
        "roster_state": roster_state,
        "roster_observed_at": roster.observed_at.isoformat() if roster else None,
        "applied_roster_at": applied_at.isoformat() if applied_at else None,
    }
    decisions: list[MemberDecision] = []
    conflicts: list[int] = []
    stored_ids: set = set()

    def decide(
        child_id: int, outcome: str, reason: str, keep: bool, **evidence
    ) -> None:
        decisions.append(
            MemberDecision(child_id, outcome, reason, keep, {**base, **evidence})
        )

    # A row that does not claim this event is only this event's business if it
    # was a member, or was decided here before (it may have moved away).
    considered = {r.id for r in claimants} | edged_ids | set(prior)
    for child_id in sorted(considered):
        row = by_id.get(child_id)
        was_edged = child_id in edged_ids
        before = prior.get(child_id)
        if row is None:
            # Gone from our store. Only a usable roster that no longer lists it may
            # retire the edge; anything less is an outage and the edge is carried.
            known = before.external_id if before else None
            if roster is not None and known and known not in roster_ids:
                decide(
                    child_id,
                    OUTCOME_EXCLUDED,
                    EXCLUDED_NOT_IN_ROSTER,
                    False,
                    external_id=known,
                    local_row="absent",
                )
            elif was_edged:
                decide(
                    child_id,
                    OUTCOME_WITHHELD,
                    CARRIED_ROW_ABSENT,
                    True,
                    external_id=known,
                    local_row="absent",
                )
            else:
                decide(
                    child_id,
                    OUTCOME_EXCLUDED,
                    EXCLUDED_ROW_ABSENT,
                    False,
                    external_id=known,
                    local_row="absent",
                )
            continue

        evidence = {
            "external_id": row.external_id,
            "row_status": row.status,
            "identity_signals": ["group_id"]
            + (["metadata_event_id"] if row.metadata_event_id else []),
        }
        if not claims_event(row):
            # An edged row whose own group now names another event (or no event).
            decide(
                child_id,
                OUTCOME_EXCLUDED,
                EXCLUDED_IDENTITY_MOVED,
                False,
                **evidence,
                row_group_id=row.group_id,
            )
            continue
        if row is parent:
            decide(child_id, OUTCOME_EXCLUDED, EXCLUDED_GROUP_ANCHOR, False, **evidence)
            continue
        if (
            row.metadata_event_id is not None
            and row.metadata_event_id != identity.event_id
        ):
            conflicts.append(child_id)
            decide(
                child_id,
                OUTCOME_EXCLUDED,
                EXCLUDED_IDENTITY_CONFLICT,
                False,
                **evidence,
                metadata_event_id=row.metadata_event_id,
            )
            continue
        external_id = _condition_id(row.external_id)
        if external_id is None:
            conflicts.append(child_id)
            decide(
                child_id, OUTCOME_EXCLUDED, EXCLUDED_MALFORMED_MEMBER, False, **evidence
            )
            continue
        stored_ids.add(external_id)
        evidence["external_id"] = external_id
        if child_id in withdrawn_ids:
            decide(child_id, OUTCOME_EXCLUDED, EXCLUDED_WITHDRAWN, False, **evidence)
            continue
        if domain_state is not None:
            if was_edged:  # a classification change is not membership evidence
                decide(
                    child_id,
                    OUTCOME_WITHHELD,
                    CARRIED_DOMAIN_UNSUPPORTED,
                    True,
                    **evidence,
                    domain_state=domain_state,
                )
            else:
                decide(
                    child_id,
                    OUTCOME_EXCLUDED,
                    EXCLUDED_UNSUPPORTED_DOMAIN,
                    False,
                    **evidence,
                    domain_state=domain_state,
                )
            continue
        if roster is not None:
            member = next(
                (m for m in roster.members if m.external_id == external_id), None
            )
            if member is None:
                decide(
                    child_id,
                    OUTCOME_EXCLUDED,
                    EXCLUDED_NOT_IN_ROSTER,
                    False,
                    **evidence,
                )
            else:
                decide(
                    child_id,
                    OUTCOME_ADMITTED,
                    ADMITTED_ROSTER_MEMBER,
                    True,
                    **evidence,
                    provider_closed=member.closed,
                )
            continue
        # No usable roster. A member an earlier roster removed stays out until a
        # newer roster lists it — this observation is not newer.
        if before is not None and before.reason == EXCLUDED_NOT_IN_ROSTER:
            decide(
                child_id,
                OUTCOME_EXCLUDED,
                EXCLUDED_NOT_IN_ROSTER,
                False,
                **evidence,
                held=True,
            )
            continue
        decide(child_id, OUTCOME_ADMITTED, ADMITTED_ROW_IDENTITY, True, **evidence)

    unstored = tuple(sorted(roster_ids - stored_ids)) if roster is not None else ()
    complete = (
        roster is not None and not unstored and not conflicts and domain_state is None
    )
    header = Header(
        name=_label(parent, children),
        category=domain,
        status=_status(roster, current_status),
        window_start=parent.commence_time if parent is not None else None,
        window_end=parent.resolution_date if parent is not None else None,
    )
    return EventAssembly(
        identity,
        tuple(decisions),
        header,
        domain,
        domain_state,
        roster,
        roster_state,
        unstored,
        tuple(conflicts),
        complete,
    )


# ---------------------------------------------------------------------------
# The pass plan
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PassPlan:
    upserts: tuple[int, ...]
    deletes: tuple[int, ...]
    membership_changed: bool
    receipt: dict


def plan_event_pass(
    assembly: EventAssembly,
    current_edges: Mapping[int, str],
    *,
    foreign_held: Iterable[int] = (),
) -> PassPlan:
    """Edges to write and remove. Only this adapter's edges are ever touched:
    a slot another source holds is left alone and is not counted as a change."""
    held = frozenset(int(i) for i in foreign_held)
    kept = assembly.kept
    upserts, deletes = [], []
    added = reclassified = 0
    for child_id, edge_class in sorted(kept.items()):
        if child_id in held:
            continue
        standing = current_edges.get(child_id)
        if standing is None:
            added += 1
            upserts.append(child_id)
        elif standing != edge_class:
            reclassified += 1
            upserts.append(child_id)
    for child_id in sorted(int(c) for c in current_edges):
        if child_id not in kept:
            deletes.append(child_id)
    reasons: dict = {}
    for d in assembly.decisions:
        reasons[d.reason] = reasons.get(d.reason, 0) + 1
    receipt = {
        "rule_version": RULE_VERSION,
        "prior_members": len(current_edges),
        "added": added,
        "reclassified": reclassified,
        "retired": len(deletes),
        "members_after": len(current_edges) + added - len(deletes),
        "reasons": dict(sorted(reasons.items())),
        "roster_state": assembly.roster_state,
        "roster_unstored": len(assembly.roster_unstored),
        "identity_conflicts": len(assembly.identity_conflicts),
    }
    return PassPlan(tuple(upserts), tuple(deletes), bool(upserts or deletes), receipt)


def header_changes(header: Header, current: Mapping[str, Any]) -> dict:
    """The container columns this pass would change. Never publication, never
    the slug; a value the pass does not know (None) never overwrites one it had."""
    changes = {}
    for column in ("name", "category", "status", "window_start", "window_end"):
        value = getattr(header, column)
        if value is not None and value != current.get(column):
            changes[column] = value
    return changes


# ---------------------------------------------------------------------------
# Structural publication eligibility
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Eligibility:
    eligible: bool
    reasons: tuple[str, ...]
    shown_members: int
    retire_at: Optional[datetime]

    def as_dict(self) -> dict:
        return {
            "eligible": self.eligible,
            "reasons": list(self.reasons),
            "shown_members": self.shown_members,
            "retire_at": self.retire_at.isoformat() if self.retire_at else None,
        }


def publication_eligibility(
    assembly: EventAssembly, *, now: datetime, publication_state: Optional[str] = None
) -> Eligibility:
    """May this collection be offered to readers? Every refusal is named.

    Structural only: the provider's complete roster, every listed market held,
    one supported domain, a label, at least ``MIN_MEMBERS`` members with rows, a
    fresh roster, and not past ``RETIRE_AFTER`` beyond a closed provider window.
    A withdrawn publication is never re-offered by this answer; lifting it is a
    named decision. Eligibility publishes nothing — the publication operator does.
    """
    reasons: list[str] = []
    if assembly.domain_state is not None:
        reasons.append(assembly.domain_state)
    if assembly.roster is None:
        reasons.append(assembly.roster_state)
    else:
        if now - assembly.roster.observed_at > ROSTER_MAX_AGE:
            reasons.append(INELIGIBLE_ROSTER_EXPIRED)
        if assembly.roster_unstored:
            reasons.append(INELIGIBLE_ROSTER_UNSTORED)
    if assembly.identity_conflicts:
        reasons.append(INELIGIBLE_IDENTITY_CONFLICTS)
    shown = sum(
        1 for d in assembly.decisions if d.outcome == OUTCOME_ADMITTED and d.keep_edge
    )
    if shown < MIN_MEMBERS:
        reasons.append(INELIGIBLE_TOO_FEW_MEMBERS)
    if not assembly.header.name:
        reasons.append(INELIGIBLE_LABEL_ABSENT)
    retire_at = None
    if assembly.header.window_end is not None and assembly.header.status == "final":
        retire_at = assembly.header.window_end + RETIRE_AFTER
        if now >= retire_at:
            reasons.append(INELIGIBLE_RETIRED)
    if publication_state == "withdrawn":
        reasons.append(INELIGIBLE_PUBLICATION_WITHDRAWN)
    return Eligibility(not reasons, tuple(reasons), shown, retire_at)
