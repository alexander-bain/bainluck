"""Market families for the grouping sentinel (#12231): a plain selector C5 can reuse.

PILLAR: DISCOVER / TRUTH · SHIP: a venue product no grouping covers arrives as
a weekly count on #12221 (and, from Nov 26, as an issue), not as something Alex
has to notice.

A **family** is a set of open markets that a venue sells as one product line.
Fable's 9:28 PM answer on #12231 fixes the keys, and this module applies them in
this order of precedence:

``kalshi_series``
    The Kalshi series code: the ticker before its first ``-``, exactly as
    ``kalshi_api.event_series_ticker`` reads it (``KXHIGHNY-26NOV07`` →
    ``KXHIGHNY``). Kalshi stores one row per event, and every row has its own
    ``group_id`` (``kalshi:<ticker>``), so the series code is Kalshi's family.
``polymarket_event``
    The Polymarket event, ``group_id`` = ``polymarket:{event id}``: the
    candidates of one election, the players of one stat ladder.
``title_template``
    Polymarket events whose titles differ only in one run of words and share
    an outcome name, detected by ``prop_template_family`` (the codebase's one
    definition of a template, ruling 145). This merges a recurring or
    threshold-varied product into one family: "NHL: Players to Record 80+
    Points" and "… 100+ Points" are one family, not two, and a daily weather
    event is one family rather than one per day.

Markets with none of these keys are left out of every family. A lone market is
a card, not a family.

Nothing here is a hand list: the function is the selector (Fable, 9:28 PM).
It is pure, with no DB, no Redis and no network, so C5's finder can call it
on whatever population it reads.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, Mapping

from app.utils.prop_template_family import _tokens, detect_template_families

__all__ = [
    "Atom",
    "BLOCK_CAP",
    "Family",
    "Grouping",
    "KIND_KALSHI_SERIES",
    "KIND_POLYMARKET_EVENT",
    "KIND_TITLE_TEMPLATE",
    "build_families",
    "family_fingerprint",
    "kalshi_series_code",
    "primary_key",
    "uncovered_families",
]

KIND_KALSHI_SERIES = "kalshi_series"
KIND_POLYMARKET_EVENT = "polymarket_event"
KIND_TITLE_TEMPLATE = "title_template"

#: The template detector is pairwise (it was written for curated sets of single
#: digits), so events are compared only inside blocks that could hold a pair,
#: and a block larger than this is narrowed by one more token before it is
#: compared. 400 events is 79,800 pairs, well under a second.
BLOCK_CAP = 400

#: How far a block may be narrowed. A block still over the cap at this depth
#: is left uncompared and counted (``Grouping.unblocked_events``), never
#: silently dropped.
_MAX_BLOCK_DEPTH = 5

#: Outcome names carried per event into the template detector. Pairing needs
#: one shared name. A 99-player ladder's full list adds cost and nothing else.
_OUTCOMES_PER_EVENT = 40


@dataclass(frozen=True, slots=True)
class Atom:
    """One market as the selector sees it."""

    market_id: int
    source: str
    external_id: str
    group_id: str | None
    title: str
    event_title: str | None
    outcome_names: tuple[str, ...]
    created_at: datetime


@dataclass(frozen=True)
class Family:
    """A family's identity, its members and its label for a reader."""

    kind: str
    key: str
    label: str
    member_ids: tuple[int, ...]
    first_created_at: datetime
    #: The Polymarket events a title template merged (empty for other kinds).
    event_keys: tuple[str, ...] = field(default_factory=tuple)

    @property
    def size(self) -> int:
        return len(self.member_ids)

    @property
    def fingerprint(self) -> str:
        return family_fingerprint(self.kind, self.key)


@dataclass(frozen=True)
class Grouping:
    """``build_families``' answer, with the events it could not compare."""

    families: tuple[Family, ...]
    unblocked_events: int = 0


def family_fingerprint(kind: str, key: str) -> str:
    """The dedupe fingerprint a family will be filed under: kind + key, so Nov 26
    is a switch, not a rewrite (Fable, 9:28 PM). It is
    ``sha1("grouping:<kind>:<key>")[:12]``, the other sentinels' form with a
    ``grouping:`` prefix. Never change it once filing starts (Nov 26): every
    open issue is found by it."""
    return hashlib.sha1(f"grouping:{kind}:{key}".encode("utf-8")).hexdigest()[:12]


def kalshi_series_code(external_id: str | None) -> str | None:
    """``KXHIGHNY-26NOV07`` → ``KXHIGHNY``; ``APPLEUS`` → ``APPLEUS``; empty → None.

    The same split as ``kalshi_api.event_series_ticker``: on the first ``-``,
    never a prefix test. ``KXMLBGAME`` is not ``KXMLB``.
    """
    head = (external_id or "").split("-", 1)[0].strip().upper()
    return head or None


def primary_key(atom: Atom) -> tuple[str, str] | None:
    """The family an atom belongs to before template merging, or None."""
    if atom.source == "kalshi":
        code = kalshi_series_code(atom.external_id)
        return (KIND_KALSHI_SERIES, code) if code else None
    if atom.source == "polymarket" and atom.group_id:
        return (KIND_POLYMARKET_EVENT, atom.group_id)
    return None


def _event_items(atoms_by_event: Mapping[str, list[Atom]]) -> list[dict]:
    """One template-detector item per Polymarket event: its title and its outcomes."""
    items = []
    for event_key, members in atoms_by_event.items():
        title = next((a.event_title for a in members if a.event_title), None) or members[0].title
        names: set[str] = set()
        for a in members:
            names.update(n for n in a.outcome_names if n)
            if len(names) >= _OUTCOMES_PER_EVENT:
                break
        items.append(
            {
                "market_ext": event_key,
                "market_name": title,
                "source": "polymarket",
                "outcomes": sorted(names)[:_OUTCOMES_PER_EVENT],
            }
        )
    return items


def _blocks(items: list[dict]) -> tuple[list[list[dict]], int]:
    """Blocks that could hold a template pair, each at most ``BLOCK_CAP`` items.

    Two titles pair only when they share at least two tokens around one run of
    difference (``MIN_SHARED_TOKENS``). So a pair shares its first two tokens,
    or its last two, or its first and last one. Each item goes into those three
    blocks, and a block over the cap is split by one more token on the same
    side. Returns the blocks and the number of items left in an over-cap block
    at full depth.
    """
    tokenized = [(item, _tokens(item.get("market_name"))) for item in items]
    out: list[list[dict]] = []
    unblocked: set[str] = set()

    def split(group: list[tuple[dict, list[str]]], side: str, depth: int) -> None:
        if len(group) < 2:
            return
        if len(group) <= BLOCK_CAP:
            out.append([item for item, _ in group])
            return
        if depth >= _MAX_BLOCK_DEPTH or side == "ends":
            unblocked.update(str(item["market_ext"]) for item, _ in group)
            return
        sub: dict[tuple[str, ...], list] = defaultdict(list)
        for item, toks in group:
            key = tuple(toks[: depth + 1]) if side == "head" else tuple(toks[-(depth + 1):])
            if len(key) == depth + 1:
                sub[key].append((item, toks))
        for sub_group in sub.values():
            split(sub_group, side, depth + 1)

    for side in ("head", "tail", "ends"):
        grouped: dict[tuple[str, ...], list] = defaultdict(list)
        for item, toks in tokenized:
            if len(toks) < 2:
                continue
            if side == "head":
                key = tuple(toks[:2])
            elif side == "tail":
                key = tuple(toks[-2:])
            else:
                key = (toks[0], toks[-1])
            grouped[key].append((item, toks))
        for group in grouped.values():
            split(group, side, 2)
    return out, len(unblocked)


def _common_skeleton(titles: list[str]) -> str:
    """The words every title shares at its start and its end, with ``{}`` between.

    This is the family's key, so it must depend only on WHICH events are in the
    family, never on which pair the detector happened to find first. Otherwise
    the same family would be filed under a new fingerprint whenever its members
    were read in a different order. Returns "" when the titles share fewer than
    two words around the slot, and the caller then falls back to the
    detector's own skeleton.
    """
    toks = [_tokens(t) for t in titles if t]
    if len(toks) < 2:
        return ""
    shortest = min(len(t) for t in toks)
    head = 0
    while head < shortest and all(t[head] == toks[0][head] for t in toks):
        head += 1
    tail = 0
    while tail < shortest - head and all(t[-1 - tail] == toks[0][-1 - tail] for t in toks):
        tail += 1
    if head + tail < 2:
        return ""
    prefix = toks[0][:head]
    suffix = toks[0][len(toks[0]) - tail:] if tail else []
    return " ".join([*prefix, "{}", *suffix]).strip()


def build_families(atoms: Iterable[Atom]) -> Grouping:
    """Every family in ``atoms``, largest first.

    Kalshi series and Polymarket events come straight from their keys. Then
    Polymarket events that ``prop_template_family`` pairs are merged into one
    ``title_template`` family, keyed by the words all its titles share
    ("nhl players to record {} points"). An event merges at most once: the
    union is transitive across blocks, as it is inside the detector.
    """
    by_key: dict[tuple[str, str], list[Atom]] = defaultdict(list)
    for atom in atoms:
        key = primary_key(atom)
        if key is not None:
            by_key[key].append(atom)
    # Members in market-id order: an event's title (when no member carries the
    # event title), its outcome sample and every label read the first members,
    # so this is what keeps a family the same whatever order atoms arrive in.
    for members in by_key.values():
        members.sort(key=lambda a: a.market_id)

    events = {k[1]: v for k, v in by_key.items() if k[0] == KIND_POLYMARKET_EVENT}
    blocks, unblocked = _blocks(_event_items(events))

    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    detector_skeleton: dict[str, str] = {}
    for block in blocks:
        for fam in detect_template_families(block):
            exts = [m.market_ext for m in fam.members]
            for ext in exts:
                detector_skeleton.setdefault(ext, fam.skeleton)
            root = find(exts[0])
            for ext in exts[1:]:
                other = find(ext)
                if other != root:
                    parent[other] = root

    merged: dict[str, list[str]] = defaultdict(list)
    for ext in list(parent):
        merged[find(ext)].append(ext)

    titles = {item["market_ext"]: item["market_name"] for item in _event_items(events)}
    families: list[Family] = []
    absorbed: set[str] = set()
    for exts in merged.values():
        if len(exts) < 2:
            continue
        exts = sorted(exts)
        members = [a for ext in exts for a in events.get(ext, ())]
        if not members:
            continue
        skeleton = _common_skeleton([titles.get(e, "") for e in exts]) or next(
            (detector_skeleton[e] for e in exts if e in detector_skeleton), ""
        )
        absorbed.update(exts)
        families.append(
            Family(
                kind=KIND_TITLE_TEMPLATE,
                key=skeleton,
                label=skeleton,
                member_ids=tuple(sorted(a.market_id for a in members)),
                first_created_at=min(a.created_at for a in members),
                event_keys=tuple(sorted(exts)),
            )
        )

    for (kind, key), members in by_key.items():
        if kind == KIND_POLYMARKET_EVENT and key in absorbed:
            continue
        label = next((a.event_title for a in members if a.event_title), None) or members[0].title
        families.append(
            Family(
                kind=kind,
                key=key,
                label=label,
                member_ids=tuple(sorted(a.market_id for a in members)),
                first_created_at=min(a.created_at for a in members),
            )
        )

    families.sort(key=lambda f: (-f.size, f.kind, f.key))
    return Grouping(families=tuple(families), unblocked_events=unblocked)


def uncovered_families(
    families: Iterable[Family],
    *,
    covered: frozenset[int] | set[int],
    eligible: frozenset[int] | set[int],
    min_markets: int,
) -> list[Family]:
    """Families no grouping admits: at least ``min_markets`` eligible members and
    no member covered.

    ``eligible`` is the caller's population rule (72-A: open, priced, alive 48
    hours, not excluded by a ruling). ``covered`` is the union of every coverage
    source. One covered member is enough to call a family covered, because a
    definition that admits one market of a series names the series.
    """
    out = []
    for fam in families:
        if any(mid in covered for mid in fam.member_ids):
            continue
        if sum(1 for mid in fam.member_ids if mid in eligible) >= min_markets:
            out.append(fam)
    return out
