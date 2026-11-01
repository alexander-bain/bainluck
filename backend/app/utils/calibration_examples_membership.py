"""#994 — the exact DataGolf members behind a PUBLISHED Accuracy curve.

The Accuracy drill-in used to answer "what is in this DataGolf bucket?" by
re-running the canonical population chain per click — roster plus ~20 chunk
statements, a full-cohort read against a 22 s request budget, and rows evaluated
NOW rather than the rows the published curve was built from. The staged build
already computes exactly those rows for every unit; until #994 it kept only
their mass.

This module is the PURE half of carrying the members through to the reader. It
holds no database, no Redis and no clock:

* **Producer** — :func:`verify_cells_against_fold` checks the per-unit member
  strings the staged bank collected against the very fold the curve is
  finalized from (every DataGolf group: same n, same winners, same summed price,
  every price inside its bucket, no outcome counted twice). Then
  :func:`build_published_membership` binds the verified cells to ONE published
  payload — its ``generated_at``, versions, predicate fingerprint and the SHA-256
  of the exact bytes published — and checks the cells again against that
  payload's own ``buckets``. Anything that disagrees publishes NOTHING, and the
  drill-in falls back to its existing bounded path labelled unverified.
* **Reader** — :func:`parse_published_membership` re-validates a stored
  artifact, :func:`membership_matches_served` decides whether it belongs to the
  curve being served, and :func:`select_members` returns the COMPLETE known
  membership of one (bucket, cohort) so the caller can draw a uniform sample
  from all of it.

Nothing here truncates a membership to fit. A membership larger than
:data:`MAX_MEMBERS` / :data:`MAX_MEMBER_BYTES` is refused whole — an honest
"unverified" beats a sample drawn from part of a bucket.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any, NamedTuple, Optional, Sequence

#: The published artifact's own version. Bump when its SHAPE changes.
PUBLISHED_SCHEMA = "calibration-examples-membership/v1"
#: ``durable_state_snapshots`` identity. One row, replaced by every publish
#: (generation-guarded), so an abandoned membership can never accumulate.
DURABLE_IDENTITY = "calibration:examples_membership:datagolf"
#: The one source whose members are retained (mirrors the staged module).
SOURCE = "datagolf"

#: Refuse-whole bounds. DataGolf published 23,397 outcomes on 2026-10-13; the
#: bound is ~10x that, so it fires on a population change worth looking at, not
#: on growth. Exceeding it publishes nothing — never a truncated membership.
MAX_MEMBERS = 250_000
MAX_MEMBER_BYTES = 16 * 1024 * 1024

#: How the bucket and the truth were taken — stated on the artifact so a reader
#: can check them against the curve's own methodology without reading code.
BUCKET_RULE = "LEAST(FLOOR(adj_opening_probability * 10), 9)"
TRUTH_RULE = "CASE WHEN is_winner THEN 1 ELSE 0"
RECORD_FORMAT = "market_id,outcome_id,adj_opening_probability,winner"

RECORD_SEPARATOR = ";"
FIELD_SEPARATOR = ","

#: Tolerance on a cell's summed price against the fold's ``sum_prob``. The fold
#: sums ``adj_opening_probability::float`` in the database; this re-sums the
#: same NUMERIC text in Python — the same addends, reassociated.
_SUM_PROB_ABS_TOL = 1e-6

# Reason tokens — short stable literals, never request text (CodeQL
# py/log-injection), so they can be logged and counted.
COMPLETE = "complete"
REASON_NOT_COMPUTED = "not_computed"
REASON_FOLD_MISMATCH = "fold_mismatch"
REASON_PAYLOAD_MISMATCH = "payload_mismatch"
REASON_MALFORMED_RECORD = "malformed_record"
REASON_DUPLICATE_MEMBER = "duplicate_member"
REASON_TOO_LARGE = "too_large"
REASON_IDENTITY_MISSING = "identity_missing"
REASON_ABSENT = "absent"
REASON_MALFORMED = "malformed"
REASON_GENERATION_MISMATCH = "generation_mismatch"
REASON_READER_GENERATION_MISMATCH = "reader_generation_mismatch"
REASON_SERVED_UNREADABLE = "served_unreadable"


class Member(NamedTuple):
    market_id: int
    outcome_id: int
    #: The published ``adj_opening_probability``, exact (NUMERIC text).
    price: Decimal
    #: The published grade as the curve counted it.
    winner: bool


def parse_record(record: str) -> Optional[Member]:
    """One ``market_id,outcome_id,price,winner`` record, or ``None`` if malformed."""
    fields = record.split(FIELD_SEPARATOR)
    if len(fields) != 4 or fields[3] not in ("0", "1"):
        return None
    try:
        market_id = int(fields[0])
        outcome_id = int(fields[1])
        price = Decimal(fields[2])
    except (ValueError, InvalidOperation):
        return None
    if not price.is_finite() or price < 0 or price > 1:
        return None
    return Member(market_id, outcome_id, price, fields[3] == "1")


def bucket_of_price(price: Decimal) -> int:
    """The curve's bucket rule, on the exact NUMERIC value."""
    return min(int(math.floor(price * 10)), 9)


def _cell_parts(cell_key: str) -> Optional[tuple[Any, Any, Any, Any]]:
    try:
        parts = json.loads(cell_key)
    except (TypeError, ValueError):
        return None
    if not isinstance(parts, list) or len(parts) != 4:
        return None
    bucket, category, price_moved, bundle = parts
    if not isinstance(bucket, int) or isinstance(bucket, bool) or not 0 <= bucket <= 9:
        return None
    if price_moved is not None and not isinstance(price_moved, bool):
        return None
    return bucket, category, price_moved, bundle


def _read(row: Any, name: str) -> Any:
    if isinstance(row, Mapping):
        return row.get(name)
    mapping = getattr(row, "_mapping", None)
    if mapping is not None:
        return mapping.get(name)
    return getattr(row, name, None)


def _cell_key(bucket: Any, category: Any, price_moved: Any, bundle: Any) -> str:
    # Must equal calibration_staged_futures.membership_cell_key byte for byte.
    return json.dumps([bucket, category, price_moved, bundle], separators=(",", ":"))


def _check_cell(
    bucket: int, records: Sequence[str], seen: set[int]
) -> tuple[Optional[tuple[int, int, float]], str]:
    """``(n, winners, summed price)`` of a cell's records, or why not."""
    n = winners = 0
    total = 0.0
    for record in records:
        member = parse_record(record)
        if member is None or bucket_of_price(member.price) != bucket:
            return None, REASON_MALFORMED_RECORD
        if member.outcome_id in seen:
            return None, REASON_DUPLICATE_MEMBER
        seen.add(member.outcome_id)
        n += 1
        winners += member.winner
        total += float(member.price)
    return (n, winners, total), COMPLETE


def verify_cells_against_fold(
    cells: Mapping[str, Sequence[str]], fold_rows: Sequence[Any]
) -> tuple[Optional[dict[str, dict[str, Any]]], str]:
    """The collected DataGolf members checked against the finalized fold.

    ``cells`` is :func:`~app.utils.calibration_staged_futures.collect_unit_members`'s
    output (cell key -> the member strings of each contributing unit) and
    ``fold_rows`` the merged rows the curve is built from. Returns
    ``({cell key: {"n", "winners", "members"}}, "complete")`` or
    ``(None, reason)``.

    Every DataGolf group in the fold must have a cell with exactly its ``n`` and
    ``winners`` and a summed price within float reassociation of its
    ``sum_prob``; there may be no cell the fold does not have; every price must
    satisfy the bucket rule of its cell; and no outcome may be a member twice.
    Count equality alone would not establish member equality — the fold's rows
    and these members come from the same GROUP BY of the same statement, which
    is what the real-Postgres gate pins; this re-checks everything the two
    representations share.
    """
    expected: dict[str, Any] = {}
    for row in fold_rows or ():
        if _read(row, "source") != SOURCE or _read(row, "bucket_idx") is None:
            continue
        key = _cell_key(
            _read(row, "bucket_idx"),
            _read(row, "category"),
            _read(row, "price_moved"),
            _read(row, "is_nonexclusive_bundle"),
        )
        if key in expected:
            return None, REASON_FOLD_MISMATCH
        expected[key] = row
    present = {key for key, values in cells.items() if any(values)}
    nonzero = {key for key, row in expected.items() if int(_read(row, "n") or 0) > 0}
    if present != nonzero:
        return None, REASON_FOLD_MISMATCH
    seen: set[int] = set()
    verified: dict[str, dict[str, Any]] = {}
    for key in sorted(nonzero):
        parts = _cell_parts(key)
        if parts is None:
            return None, REASON_MALFORMED_RECORD
        records = [
            record
            for value in cells.get(key, ())
            for record in (value.split(RECORD_SEPARATOR) if value else ())
        ]
        counted, reason = _check_cell(parts[0], records, seen)
        if counted is None:
            return None, reason
        n, winners, total = counted
        row = expected[key]
        if n != int(_read(row, "n") or 0) or winners != int(_read(row, "winners") or 0):
            return None, REASON_FOLD_MISMATCH
        sum_prob = float(_read(row, "sum_prob") or 0.0)
        if abs(total - sum_prob) > _SUM_PROB_ABS_TOL + 1e-12 * n:
            return None, REASON_FOLD_MISMATCH
        verified[key] = {
            "n": n,
            "winners": winners,
            "members": RECORD_SEPARATOR.join(records),
        }
    if len(seen) > MAX_MEMBERS:
        return None, REASON_TOO_LARGE
    return verified, COMPLETE


def _payload_cells(buckets: Any) -> Optional[dict[tuple, tuple[int, int]]]:
    """The served ``buckets`` list's DataGolf (bucket, category, moved) -> (n, winners)."""
    if not isinstance(buckets, list):
        return None
    out: dict[tuple, tuple[int, int]] = {}
    for bucket in buckets:
        if not isinstance(bucket, Mapping) or bucket.get("source") != SOURCE:
            continue
        key = (bucket.get("bucket_idx"), bucket.get("category"), bucket.get("price_moved"))
        n, w = out.get(key, (0, 0))
        try:
            out[key] = (n + int(bucket.get("n") or 0), w + int(bucket.get("winners") or 0))
        except (TypeError, ValueError):
            return None
    return {key: value for key, value in out.items() if value[0] > 0}


def _cells_by_payload_key(cells: Mapping[str, Mapping[str, Any]]) -> Optional[dict]:
    """Artifact cells merged on the payload's key (the bundle flag dropped)."""
    out: dict[tuple, tuple[int, int]] = {}
    for key, cell in cells.items():
        parts = _cell_parts(key)
        if parts is None or not isinstance(cell, Mapping):
            return None
        bucket, category, price_moved, _bundle = parts
        pkey = (bucket, category, price_moved)
        n, w = out.get(pkey, (0, 0))
        try:
            out[pkey] = (n + int(cell.get("n")), w + int(cell.get("winners")))
        except (TypeError, ValueError):
            return None
    return {key: value for key, value in out.items() if value[0] > 0}


def cells_agree_with_payload(
    cells: Mapping[str, Mapping[str, Any]], payload: Mapping[str, Any]
) -> bool:
    """Whether the cells' counts are EXACTLY the payload's DataGolf buckets."""
    served = _payload_cells(payload.get("buckets"))
    mine = _cells_by_payload_key(cells)
    return served is not None and mine is not None and served == mine


def build_published_membership(
    verified: Mapping[str, Mapping[str, Any]],
    *,
    response: Mapping[str, Any],
    payload_sha256: str,
    staged_unit_fingerprint: Optional[str],
    bank: Optional[Mapping[str, Any]] = None,
) -> tuple[Optional[dict[str, Any]], str]:
    """Bind fold-verified cells to the ONE payload being published.

    ``response`` is the payload dict and ``payload_sha256`` the SHA-256 of the
    exact serialized bytes the publisher writes; both are carried so a reader
    can prove which curve the membership belongs to without decoding it.
    Refuses (``None``) when the payload carries no generation identity, when its
    own DataGolf buckets disagree with the cells, or when the membership is
    over the refuse-whole bounds.
    """
    generated_at = response.get("generated_at")
    population_version = response.get("population_version")
    if not isinstance(generated_at, str) or not generated_at or not population_version:
        return None, REASON_IDENTITY_MISSING
    if not isinstance(payload_sha256, str) or len(payload_sha256) != 64:
        return None, REASON_IDENTITY_MISSING
    if not cells_agree_with_payload(verified, response):
        return None, REASON_PAYLOAD_MISMATCH
    total = sum(int(cell["n"]) for cell in verified.values())
    size = sum(len(cell["members"]) for cell in verified.values())
    if total > MAX_MEMBERS or size > MAX_MEMBER_BYTES:
        return None, REASON_TOO_LARGE
    cells = []
    for key in sorted(verified):
        bucket, category, price_moved, bundle = _cell_parts(key)  # type: ignore[misc]
        cell = verified[key]
        cells.append({
            "bucket_idx": bucket,
            "category": category,
            "price_moved": price_moved,
            "is_nonexclusive_bundle": bundle,
            "n": int(cell["n"]),
            "winners": int(cell["winners"]),
            "members": cell["members"],
        })
    return {
        "schema": PUBLISHED_SCHEMA,
        "source": SOURCE,
        "generated_at": generated_at,
        "population_version": population_version,
        "population_predicate_fingerprint": response.get("population_predicate_fingerprint"),
        "staged_unit_fingerprint": staged_unit_fingerprint,
        "payload_sha256": payload_sha256,
        "bank": dict(bank or {}),
        "methodology": {
            "bucket_rule": BUCKET_RULE,
            "truth": TRUTH_RULE,
            "record": RECORD_FORMAT,
        },
        "members_total": total,
        "cells": cells,
    }, COMPLETE


class PublishedMembership(NamedTuple):
    generated_at: str
    population_version: str
    population_predicate_fingerprint: Optional[str]
    payload_sha256: str
    #: cell key -> (n, winners, member string)
    cells: dict[str, tuple[int, int, str]]
    members_total: int


def parse_published_membership(payload: Any) -> tuple[Optional[PublishedMembership], str]:
    """A stored artifact, re-validated in full, or ``(None, reason)``.

    Re-checks every cell's record count and winner count and every record's
    shape and bucket — the stored bytes vouch for nothing until read back.
    """
    if not isinstance(payload, Mapping):
        return None, REASON_MALFORMED
    if payload.get("schema") != PUBLISHED_SCHEMA or payload.get("source") != SOURCE:
        return None, REASON_MALFORMED
    generated_at = payload.get("generated_at")
    version = payload.get("population_version")
    digest = payload.get("payload_sha256")
    if not isinstance(generated_at, str) or not isinstance(version, str):
        return None, REASON_IDENTITY_MISSING
    if not isinstance(digest, str) or len(digest) != 64:
        return None, REASON_IDENTITY_MISSING
    raw_cells = payload.get("cells")
    if not isinstance(raw_cells, list):
        return None, REASON_MALFORMED
    cells: dict[str, tuple[int, int, str]] = {}
    total = 0
    for cell in raw_cells:
        if not isinstance(cell, Mapping):
            return None, REASON_MALFORMED
        bucket = cell.get("bucket_idx")
        key = _cell_key(
            bucket, cell.get("category"), cell.get("price_moved"),
            cell.get("is_nonexclusive_bundle"),
        )
        members = cell.get("members")
        if _cell_parts(key) is None or not isinstance(members, str) or key in cells:
            return None, REASON_MALFORMED
        # Counts, grades and record shape only. Every record was parsed, bucket-
        # checked and de-duplicated against the fold before publication, and the
        # durable envelope's checksum covers these bytes; re-parsing 23k prices
        # here would hold the event loop ~0.1 s for no new evidence. A sampled
        # record that still fails :func:`parse_record` refuses at use.
        records = members.split(RECORD_SEPARATOR) if members else []
        n = len(records)
        winners = 0
        for record in records:
            tail = record[-2:]
            if tail == ",1":
                winners += 1
            elif tail != ",0":
                return None, REASON_MALFORMED_RECORD
        if n != cell.get("n") or winners != cell.get("winners") or n == 0:
            return None, REASON_MALFORMED
        cells[key] = (n, winners, members)
        total += n
    if total != payload.get("members_total") or total > MAX_MEMBERS:
        return None, REASON_MALFORMED
    fingerprint = payload.get("population_predicate_fingerprint")
    return PublishedMembership(
        generated_at=generated_at,
        population_version=version,
        population_predicate_fingerprint=fingerprint if isinstance(fingerprint, str) else None,
        payload_sha256=digest,
        cells=cells,
        members_total=total,
    ), COMPLETE


def membership_matches_served(
    membership: PublishedMembership,
    *,
    served_sha256: Optional[str] = None,
    served_payload: Optional[Mapping[str, Any]] = None,
    reader_generation: Optional[str] = None,
) -> tuple[bool, str]:
    """Whether ``membership`` is the membership of the curve being served.

    Two ways to prove it, strongest first:

    * ``served_sha256`` — the SHA-256 of the raw bytes the shared store is
      serving. Equal to the artifact's ``payload_sha256`` means byte-identical
      to the payload the membership was verified against at publish time.
    * ``served_payload`` — a decoded payload (the durable tier): same
      ``generated_at``, version and predicate fingerprint, and its own DataGolf
      buckets agree with every cell's counts.

    ``reader_generation`` is the ``generated_at`` of the curve the reader is
    actually looking at, when the client sends it; it must match too. A page
    left open across a publish is looking at an older curve than the one now
    served, and the membership of the new one is not the membership of the
    curve on that screen.
    """
    if reader_generation is not None and reader_generation != membership.generated_at:
        return False, REASON_READER_GENERATION_MISMATCH
    if served_sha256 is not None:
        if served_sha256 == membership.payload_sha256:
            return True, COMPLETE
        return False, REASON_GENERATION_MISMATCH
    if isinstance(served_payload, Mapping):
        if (
            served_payload.get("generated_at") != membership.generated_at
            or served_payload.get("population_version") != membership.population_version
            or served_payload.get("population_predicate_fingerprint")
            != membership.population_predicate_fingerprint
        ):
            return False, REASON_GENERATION_MISMATCH
        counts = {key: {"n": n, "winners": w} for key, (n, w, _m) in membership.cells.items()}
        if not cells_agree_with_payload(counts, served_payload):
            return False, REASON_PAYLOAD_MISMATCH
        return True, COMPLETE
    return False, REASON_SERVED_UNREADABLE


def select_members(
    membership: PublishedMembership, *, bucket: int, moved_only: bool
) -> list[str]:
    """EVERY known member record of one (bucket, cohort), across all categories.

    ``moved_only`` is the drill-in's well-traded cohort (``price_moved`` true —
    the page's default); otherwise both values of ``price_moved``. The caller
    samples from the whole list, so a sample is uniform over the entire bucket.
    """
    records: list[str] = []
    for key in sorted(membership.cells):
        parts = _cell_parts(key)
        if parts is None or parts[0] != bucket:
            continue
        if moved_only and parts[2] is not True:
            continue
        members = membership.cells[key][2]
        if members:
            records.extend(members.split(RECORD_SEPARATOR))
    return records
