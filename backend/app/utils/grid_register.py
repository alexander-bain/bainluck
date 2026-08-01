"""Explicit, versioned championship-grid registers (Queue 295).

A *register* is the answer to one question, written down instead of guessed at
request time: **which market identity feeds this grid cell?**

Before this module the five championship grids resolved every cell by fuzzy
matching at serve time — ILIKE ticker prefixes, name regexes, a stage
classifier, then four successive team-name merge passes (see
``routes/playoffs.py::get_playoff_grid``).  That pipeline fails *silently*: when
a source renames a market, splits a series, or rotates to a new event, the fuzzy
matcher keeps returning *something*, and the wrong number lands in the blend
with no error anywhere.  The 2026-08-01 baseline census measured the cost —
610 of 735 golf cells (83%) were fed by a Kalshi market for a **different
tournament**, and 47 cells merged to a value strictly outside their own source
envelope (Patrick Cantlay's make-cut showed 0.5% from a settled Genesis Scottish
Open market blended against a live DataGolf 100%).

An explicit register fails LOUDLY instead: the identity is pinned to a
``market_id``/``outcome_id``, a source that no longer carries it becomes
``missing`` (an honest empty cell, never a silent 50%), and the daily sentinel
diffs the register against live inventory so drift is caught the same day.

This module is identity only.  It deliberately contains no probability, blend,
weighting, or stage-taste logic — those semantics stay exactly where they are.

The vocabulary here (field names, status values, finding codes, classification
and action names) is fixed by the C108 contract corpus at
``backend/tests/evals/fixtures/grid_register_contract.json``.
``tests/test_grid_register.py`` asserts this module and that corpus agree case
for case, so the contract cannot drift away from the implementation.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "grid-register/v1"

ALLOWED_SOURCES = ("odds_api", "kalshi", "polymarket", "datagolf")

#: Register-entry lifecycle.  ``missing`` is a first-class, *honest* state: the
#: cell is registered but the source does not currently carry the identity.
REGISTER_STATUSES = ("live", "settled", "missing")

#: Terminal outcomes for a settled entry.  A settled entry without one is
#: invalid — "settled" with no result is how stale live numbers used to linger.
TERMINAL_RESULTS = ("won", "eliminated")

REQUIRED_REGISTER_FIELDS = frozenset(
    {"schema_version", "league", "season", "version", "generated_at", "entries"}
)
REQUIRED_ENTRY_FIELDS = frozenset(
    {"stage", "entity_key", "entity_name", "source", "status", "evidence"}
)

#: Where committed registers live.  ``backend/data/grid_registers/<league>-<season>.json``.
REGISTER_DIR = Path(__file__).resolve().parents[2] / "data" / "grid_registers"


# ---------------------------------------------------------------------------
# Findings -> classification
# ---------------------------------------------------------------------------

#: Findings that mean "this register must not be served or published at all".
_HARD_INVALID_PREFIXES = (
    "REGISTER_", "INVALID_", "UNKNOWN_", "DUPLICATE_", "IDENTITY_REUSED", "CROSS_",
)

#: Drift a machine must NOT resolve on its own — routed to a human as P2.
AMBIGUOUS_FINDINGS = frozenset({
    "AMBIGUOUS_CANDIDATES",
    "IDENTITY_DRIFT_AMBIGUOUS",
    "NEXT_OR_OTHER_SEASON_CANDIDATE",
    "REGISTERED_IDENTITY_NOT_OBSERVED",
    "POISON_CANDIDATE",
})

#: Drift that a deterministic rule *can* resolve into a new register version.
UNAMBIGUOUS_FINDINGS = frozenset({
    "UNAMBIGUOUS_RENAME_DRIFT",
    "UNAMBIGUOUS_SETTLEMENT_DRIFT",
})

#: Render-contract breaches — the register is fine but what would be shown is not.
RENDER_FINDINGS = frozenset({
    "MISSING_RENDERED_AS_PROBABILITY",
    "SETTLED_RENDERED_AS_LIVE",
    "LIVE_RENDER_NOT_NUMERIC",
    "LIVE_PROBABILITY_OUT_OF_RANGE",
    "UNREGISTERED_RENDER_CELL",
    "POISON_RENDER_CELL",
})


def is_iso8601(value: Any) -> bool:
    """Whether ``value`` is a parseable ISO-8601 timestamp string."""
    if not isinstance(value, str):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_entry(
    entry: Any,
    *,
    league: str,
    season: str,
    stages: set[str],
    sources: set[str],
) -> list[str]:
    """Validate one register entry.  Returns finding codes (empty == clean)."""
    if not isinstance(entry, dict):
        return ["REGISTER_ENTRY_WRONG_SHAPE"]

    findings: list[str] = []
    if REQUIRED_ENTRY_FIELDS - entry.keys():
        return ["REGISTER_ENTRY_MISSING_FIELDS"]

    # An entry may restate its league/season; if it does, it must agree. This is
    # the guard against a next-season entry being pasted into a current file.
    if entry.get("league", league) != league or entry.get("season", season) != season:
        findings.append("CROSS_SEASON_OR_LEAGUE_ENTRY")
    if entry["stage"] not in stages:
        findings.append("UNKNOWN_STAGE")
    if entry["source"] not in sources:
        findings.append("UNKNOWN_SOURCE")
    if entry["status"] not in REGISTER_STATUSES:
        findings.append("UNKNOWN_REGISTER_STATUS")

    evidence = entry.get("evidence")
    if (
        not isinstance(evidence, dict)
        or not evidence.get("kind")
        or not is_iso8601(evidence.get("observed_at"))
    ):
        findings.append("INVALID_EVIDENCE")

    if entry["status"] == "missing":
        # A missing entry must not carry a stale identity — that is how a
        # dropped market keeps rendering yesterday's number.
        if entry.get("market_id") is not None or entry.get("outcome_id") is not None:
            findings.append("MISSING_ENTRY_HAS_IDENTITY")
    elif entry.get("market_id") is None or entry.get("outcome_id") is None:
        findings.append("MAPPED_ENTRY_MISSING_IDENTITY")

    if entry["status"] == "settled" and entry.get("terminal_result") not in TERMINAL_RESULTS:
        findings.append("SETTLED_WITHOUT_RESULT")

    return findings


def validate_register(register: Any, contract: dict[str, Any]) -> list[str]:
    """Validate a whole register against a league contract.

    ``contract`` carries ``register_schema_version``, ``allowed_sources`` and
    ``league_contracts`` (league -> ``{season, entity_kind, stages}``).
    Returns sorted, de-duplicated finding codes.
    """
    if not isinstance(register, dict):
        return ["REGISTER_WRONG_SHAPE"]
    if REQUIRED_REGISTER_FIELDS - register.keys():
        return ["REGISTER_MISSING_FIELDS"]

    league = register.get("league")
    league_spec = contract.get("league_contracts", {}).get(league)
    if not league_spec:
        return ["UNKNOWN_LEAGUE"]

    findings: list[str] = []
    if register.get("schema_version") != contract.get("register_schema_version"):
        findings.append("REGISTER_SCHEMA_MISMATCH")
    if register.get("season") != league_spec.get("season"):
        findings.append("REGISTER_SEASON_MISMATCH")
    if not isinstance(register.get("version"), int) or register["version"] < 1:
        findings.append("INVALID_REGISTER_VERSION")
    if not is_iso8601(register.get("generated_at")):
        findings.append("INVALID_GENERATED_AT")

    entries = register.get("entries")
    if not isinstance(entries, list):
        return sorted(set(findings + ["REGISTER_ENTRIES_WRONG_SHAPE"]))

    stages = set(league_spec.get("stages", []))
    sources = set(contract.get("allowed_sources", ()))

    cell_keys: set[tuple] = set()
    identity_keys: dict[tuple, tuple] = {}
    for entry in entries:
        findings.extend(validate_entry(
            entry,
            league=league,
            season=register.get("season"),
            stages=stages,
            sources=sources,
        ))
        if not isinstance(entry, dict) or not REQUIRED_ENTRY_FIELDS <= entry.keys():
            continue

        # One entry per (stage, entity, source): two rows for the same cell and
        # source means the generator could not decide, which is exactly the
        # ambiguity the register exists to eliminate.
        cell = (entry["stage"], entry["entity_key"], entry["source"])
        if cell in cell_keys:
            findings.append("DUPLICATE_CELL_SOURCE")
        cell_keys.add(cell)

        # The same market outcome must not back two different cells — that is
        # the "one team's number shown for another team" class.
        if entry["status"] != "missing":
            identity = (entry["source"], entry.get("market_id"), entry.get("outcome_id"))
            prior = identity_keys.get(identity)
            if prior is not None and prior != cell:
                findings.append("IDENTITY_REUSED_ACROSS_CELLS")
            identity_keys[identity] = cell

    return sorted(set(findings))


def classify(findings: list[str], *, transition_ok: bool | None = None) -> dict[str, Any]:
    """Map finding codes to ``(classification, action, publish)``.

    ``transition_ok`` is whether a proposed next version validated cleanly;
    pass ``None`` when no transition was proposed.
    """
    hard_invalid = any(f.startswith(_HARD_INVALID_PREFIXES) for f in findings)
    ambiguous = any(f in AMBIGUOUS_FINDINGS for f in findings)
    unambiguous = any(f in UNAMBIGUOUS_FINDINGS for f in findings)
    render_bad = any(f in RENDER_FINDINGS for f in findings)

    # Order matters and encodes the safety posture: a structurally invalid
    # register is rejected outright; ambiguity is routed to a human before any
    # render concern; a render breach blocks release even when the register
    # itself is well-formed; only then may unambiguous drift publish.
    if hard_invalid:
        return {"classification": "invalid", "action": "reject_register", "publish": False}
    if ambiguous:
        return {"classification": "needs_ruling", "action": "file_p2_needs_triage", "publish": False}
    if render_bad:
        return {"classification": "render_contract_failure", "action": "block_release", "publish": False}
    if unambiguous:
        return {
            "classification": "unambiguous_drift",
            "action": "publish_new_version",
            "publish": bool(transition_ok),
        }
    return {"classification": "clean", "action": "no_change", "publish": False}


def validate_transition(register: dict[str, Any], proposed: Any, contract: dict[str, Any]) -> list[str]:
    """Validate a proposed next version of ``register``.

    A transition must be a valid register, exactly one version newer, the same
    scope, and explicitly linked back to what it supersedes.
    """
    if proposed is None:
        return []
    findings = validate_register(proposed, contract)
    if not isinstance(proposed, dict):
        return sorted(set(findings))
    if proposed.get("version") != register.get("version", 0) + 1:
        findings.append("NON_MONOTONIC_VERSION")
    if proposed.get("league") != register.get("league") or proposed.get("season") != register.get("season"):
        findings.append("TRANSITION_CHANGED_SCOPE")
    if proposed.get("supersedes_version") != register.get("version"):
        findings.append("MISSING_SUPERSEDES_LINK")
    return sorted(set(findings))


# ---------------------------------------------------------------------------
# Drift detection (the sentinel's comparison core)
# ---------------------------------------------------------------------------

def diff_against_inventory(
    register: dict[str, Any],
    candidates: Any,
) -> list[str]:
    """Compare registered identities against currently observed source inventory.

    ``candidates`` is a list of observed rows, each
    ``{stage, entity_key, source, season, market_id, outcome_id, external_id,
    status, terminal_result}``.  Returns finding codes.

    The deliberate asymmetry: a *rename* or a *settlement* that keeps the same
    pinned identity is unambiguous and may be auto-versioned; anything that
    changes which market backs a cell is ambiguous and gets routed to a human.
    """
    if not isinstance(candidates, list):
        return ["CANDIDATES_WRONG_SHAPE"]
    if any(not isinstance(row, dict) for row in candidates):
        # One malformed row poisons publication for this league only — it must
        # never be silently dropped, and it must not stop sibling leagues.
        return ["POISON_CANDIDATE"]

    findings: list[str] = []
    season = register.get("season")

    for entry in register.get("entries", []):
        if not isinstance(entry, dict) or entry.get("status") == "missing":
            continue
        matches = [
            row for row in candidates
            if row.get("stage") == entry.get("stage")
            and row.get("entity_key") == entry.get("entity_key")
            and row.get("source") == entry.get("source")
            and row.get("season") == season
        ]
        if len(matches) > 1:
            findings.append("AMBIGUOUS_CANDIDATES")
            continue
        if not matches:
            findings.append("REGISTERED_IDENTITY_NOT_OBSERVED")
            continue

        row = matches[0]
        same_identity = (
            row.get("market_id") == entry.get("market_id")
            and row.get("outcome_id") == entry.get("outcome_id")
        )
        if not same_identity:
            findings.append("IDENTITY_DRIFT_AMBIGUOUS")
        elif row.get("status") == "settled" and entry.get("status") == "live":
            if row.get("terminal_result") not in TERMINAL_RESULTS:
                findings.append("SETTLEMENT_WITHOUT_RESULT")
            else:
                findings.append("UNAMBIGUOUS_SETTLEMENT_DRIFT")
        elif row.get("external_id") != entry.get("external_id"):
            findings.append("UNAMBIGUOUS_RENAME_DRIFT")

    # A next-season market set appearing is never an in-place replacement for
    # the current season — season rollover is a human call.
    if any(row.get("season") not in (None, season) for row in candidates):
        findings.append("NEXT_OR_OTHER_SEASON_CANDIDATE")

    return sorted(set(findings))


def check_rendered_cells(register: dict[str, Any], rendered: Any) -> list[str]:
    """Verify rendered cells honour their registered status.

    This is the "settled means settled" enforcement point: a settled entry must
    render its terminal result with no probability, a missing entry must render
    an honest empty state, and only a live entry may show a number.
    """
    if not isinstance(rendered, list):
        return ["RENDERED_WRONG_SHAPE"]

    findings: list[str] = []
    by_cell = {
        (e.get("stage"), e.get("entity_key"), e.get("source")): e
        for e in register.get("entries", []) if isinstance(e, dict)
    }
    for row in rendered:
        if not isinstance(row, dict):
            findings.append("POISON_RENDER_CELL")
            continue
        entry = by_cell.get((row.get("stage"), row.get("entity_key"), row.get("source")))
        if entry is None:
            findings.append("UNREGISTERED_RENDER_CELL")
            continue

        status = entry.get("status")
        state = row.get("state")
        probability = row.get("probability")
        if status == "missing":
            if state != "missing" or probability is not None:
                findings.append("MISSING_RENDERED_AS_PROBABILITY")
        elif status == "settled":
            if state != entry.get("terminal_result") or probability is not None:
                findings.append("SETTLED_RENDERED_AS_LIVE")
        elif status == "live":
            if state != "live" or not isinstance(probability, (int, float)):
                findings.append("LIVE_RENDER_NOT_NUMERIC")
            elif not 0 <= float(probability) <= 1:
                findings.append("LIVE_PROBABILITY_OUT_OF_RANGE")

    return sorted(set(findings))


# ---------------------------------------------------------------------------
# Loading + lookup (the serving path)
# ---------------------------------------------------------------------------

def register_filename(league: str, season: str) -> str:
    return f"{league}-{season}.json"


def load_register(
    league: str,
    season: str,
    *,
    directory: Path | None = None,
) -> dict[str, Any] | None:
    """Load a committed register, or ``None`` when there is no file.

    Returning ``None`` is meaningful and safe: a league with no register keeps
    its existing behaviour untouched, so the cutover is per-league and
    incremental rather than a five-league big bang.  A file that exists but is
    unreadable or malformed also returns ``None`` (logged loudly) — a broken
    register must degrade to the prior reader, never to a wrong number.
    """
    path = (directory or REGISTER_DIR) / register_filename(league, season)
    try:
        if not path.is_file():
            return None
        return json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        logger.error("Grid register %s unreadable — falling back to prior reader: %s", path, exc)
        return None


class GridRegister:
    """Read-only lookup view over a validated register.

    Built once per request.  Every method is a dict lookup — there is no
    matching, normalization, or scoring here by design.
    """

    def __init__(self, data: dict[str, Any]):
        self.data = data
        self.league: str = data.get("league", "")
        self.season: str = data.get("season", "")
        self.version: int = data.get("version", 0)
        self.generated_at: str = data.get("generated_at", "")

        self.entries: list[dict[str, Any]] = [
            e for e in data.get("entries", []) if isinstance(e, dict)
        ]
        # (market_id, outcome_id) -> entry.  The serving path walks the outcomes
        # it loaded and asks "is this identity registered?" — anything not in
        # here simply does not enter the grid.
        self.by_identity: dict[tuple, dict[str, Any]] = {
            (e.get("market_id"), e.get("outcome_id")): e
            for e in self.entries
            if e.get("status") != "missing"
            and e.get("market_id") is not None
            and e.get("outcome_id") is not None
        }
        self.by_cell: dict[tuple, dict[str, Any]] = {
            (e.get("stage"), e.get("entity_key"), e.get("source")): e
            for e in self.entries
        }

    @property
    def market_ids(self) -> list[int]:
        """Distinct market ids the register pins, for a bounded targeted load."""
        return sorted({
            e["market_id"] for e in self.entries
            if isinstance(e.get("market_id"), int)
        })

    def entry_for_identity(self, market_id: Any, outcome_id: Any) -> dict[str, Any] | None:
        return self.by_identity.get((market_id, outcome_id))

    def settled_entries(self) -> list[dict[str, Any]]:
        return [e for e in self.entries if e.get("status") == "settled"]

    def missing_entries(self) -> list[dict[str, Any]]:
        return [e for e in self.entries if e.get("status") == "missing"]

    def entity_names(self) -> dict[str, str]:
        """``entity_key`` -> display name (first entry wins, deterministically)."""
        names: dict[str, str] = {}
        for entry in self.entries:
            key = entry.get("entity_key")
            if key and key not in names:
                names[key] = entry.get("entity_name") or key
        return names

    def counters(self) -> dict[str, int]:
        counts: Counter = Counter()
        for entry in self.entries:
            counts[entry.get("status", "invalid")] += 1
        return dict(sorted(counts.items()))


def build_contract(league_specs: dict[str, Any]) -> dict[str, Any]:
    """Assemble a validation contract from league specs."""
    return {
        "register_schema_version": SCHEMA_VERSION,
        "allowed_sources": list(ALLOWED_SOURCES),
        "league_contracts": league_specs,
    }
