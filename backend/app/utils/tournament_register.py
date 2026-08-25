"""Explicit, versioned tournament registers for player-field events (UX-P130).

A *register* answers one question, written down instead of guessed at request
time: **which market identity feeds this row?**  ``utils/grid_register.py``
established the pattern for championship grids, whose unit is a *team in a
stage*.  This module carries the same doctrine to tournaments whose unit is a
**player in a draw** — the US Open being the first, shipping for main-draw
Sunday 2026-08-30.

Why a second module rather than a wider ``grid_register``: the grid's cell is
``(stage, entity, source)`` and its entity identity comes from the ``teams``
table.  A tennis draw has no teams table to anchor to, its rows carry
draw/seed/draw-slot state a grid cell has no place for, and its daily slate is a
*pair* of registered players sharing one market.  Forking the shape while
**importing the vocabulary** (statuses, terminal results, finding
classification, evidence rules) keeps the two registers saying the same words
about the same situations, which is the part that must not drift.  Nothing here
is wired into the shipped grid path.

The 2026-08-24 US Open census is why every field below exists:

* ``llm_gender`` is ``NULL`` for **all 861,809** rows of ``futures_markets`` —
  the column is dead, so ``draw`` is register-owned and never read from it.
* ``llm_sport_category`` puts **every** US Open singles match market under
  ``table_tennis`` (298 rows for this tournament; 12,766 platform-wide, of which
  **zero** name table tennis), and puts 26 celebrity-attendance markets under
  ``tennis``.  Category is therefore never a membership test.
* Polymarket's men's and women's winner fields each carry an ``Other`` bucket
  pinned at ``probability = 1.000`` since 2026-05-12.  Sorted by probability it
  is the **first row of both boards**.  An aggregate bucket is not a player, so
  it gets no entry and cannot render — see ``INVALID_NON_PLAYER_ENTITY``.
* 15 Kalshi match markets for matches **played on 2026-08-19** are still
  ``status='open'`` with ``resolution_date`` inside US Open week (gotcha #33).
  Any date-window slate query pulls them in; a register keyed on matchups cannot.
* ``futures_outcomes.last_updated`` is not a freshness signal: the Polymarket
  men's field reads ``2026-07-21`` on every outcome while its snapshots ran to
  ``2026-08-10``.  Freshness is read from ``futures_odds_snapshots.captured_at``
  and stored as ``price_observed_at`` — see ``check_freshness``.

Identity only.  No probability, blend, weighting or ordering logic lives here.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.utils.grid_register import (
    AMBIGUOUS_FINDINGS as GRID_AMBIGUOUS_FINDINGS,
    REGISTER_STATUSES,
    TERMINAL_RESULTS,
    _HARD_INVALID_PREFIXES,
    is_iso8601,
)

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "tournament-register/v1"

#: Only two sources carry US Open tennis.  Measured 2026-08-24: ``odds_api``
#: holds **zero** tennis futures of any kind, and DataGolf is golf-only, so the
#: blend on this page has exactly two contributors and no sportsbook column.
ALLOWED_SOURCES = ("kalshi", "polymarket")

#: The two singles draws.  Register-owned because ``llm_gender`` is dead.
DRAWS = ("mens-singles", "womens-singles")

#: Rounds, qualifying through the final.  ``qualifying`` is one bucket rather
#: than Q1/Q2/Q3 because the sources do not distinguish them by name.
ROUNDS = ("qualifying", "R128", "R64", "R32", "R16", "QF", "SF", "F")

REQUIRED_REGISTER_FIELDS = frozenset(
    {"schema_version", "tournament", "season", "version", "generated_at",
     "draw_released", "players", "matchups"}
)
REQUIRED_PLAYER_FIELDS = frozenset({"entity_key", "display_name", "draw", "sources"})
REQUIRED_MATCHUP_FIELDS = frozenset(
    {"matchup_key", "draw", "round", "scheduled_date", "players", "sources"}
)
REQUIRED_SOURCE_FIELDS = frozenset({"source", "status", "evidence"})

#: Where committed registers live: ``backend/data/tournament_registers/<t>-<season>.json``.
REGISTER_DIR = Path(__file__).resolve().parents[2] / "data" / "tournament_registers"

#: A live row whose price is older than this must not render as live.  The
#: census measured 34 days on the highest-liquidity market of the tournament, so
#: this bound is the difference between an honest empty board and a board of
#: month-old numbers presented as today's.
STALE_PRICE_HOURS = 6.0

#: Names that are aggregate buckets, not players.  Registering one would let a
#: 100%-pinned bucket lead a board (the measured Polymarket case).
NON_PLAYER_NAMES = frozenset({
    "other", "others", "any other", "field", "the field", "any other player",
    "no winner", "none of the above", "any other man", "any other woman",
})

#: Drift that means "a number would be shown that must not be" — same posture as
#: ``grid_register.RENDER_FINDINGS``: the register may be well-formed and the
#: release still blocked.
FRESHNESS_FINDINGS = frozenset({"LIVE_PRICE_STALE", "LIVE_PRICE_NEVER_OBSERVED"})

RENDER_FINDINGS = frozenset({
    "MISSING_RENDERED_AS_PROBABILITY",
    "SETTLED_RENDERED_AS_LIVE",
    "LIVE_RENDER_NOT_NUMERIC",
    "LIVE_PROBABILITY_OUT_OF_RANGE",
    "UNREGISTERED_RENDER_ROW",
    "POISON_RENDER_ROW",
    "RENDERED_WRONG_SHAPE",
}) | FRESHNESS_FINDINGS

UNAMBIGUOUS_FINDINGS = frozenset({
    "UNAMBIGUOUS_RENAME_DRIFT",
    "UNAMBIGUOUS_SETTLEMENT_DRIFT",
})

#: Ambiguity the grid register never had to name.  ``SETTLEMENT_WITHOUT_RESULT``
#: is gotcha #33's shape at the register boundary: the source says the market is
#: over but no winner is knowable, so neither "keep rendering it live" nor "grade
#: it" is safe.  Without this entry it fell through ``classify`` to ``clean`` —
#: the board would have kept printing a live probability for a finished match
#: and nobody would have been told.  A finding that is emitted but classified by
#: nothing is worse than no finding at all: it reads as green.
#: ``CANDIDATES_WRONG_SHAPE`` joins it for the same reason: the sentinel was
#: handed something it cannot compare against, so "no drift found" would be a
#: statement about the harness, not about the register.
AMBIGUOUS_FINDINGS = GRID_AMBIGUOUS_FINDINGS | {
    "SETTLEMENT_WITHOUT_RESULT",
    "CANDIDATES_WRONG_SHAPE",
}

#: Structural findings that ``_HARD_INVALID_PREFIXES`` does not spell.
#:
#: Prefix-matching is a naming convention doing a classifier's job: a finding is
#: severe because of what it means, and a name that happens not to start with
#: ``INVALID_`` silently becomes ``clean``.  Every entry below is emitted by a
#: validator, reaches ``classify``, and read as clean before this set existed —
#: a malformed matchup would have published.  Names are kept identical to
#: ``grid_register``'s on purpose so findings stay greppable across both
#: registers; the classification is made explicit here instead.
#:
#: The same hole is live in ``grid_register`` itself (#2198).
STRUCTURAL_FINDINGS = frozenset({
    "MAPPED_ENTRY_MISSING_IDENTITY",
    "MISSING_ENTRY_HAS_IDENTITY",
    "SETTLED_WITHOUT_RESULT",
    "MATCHUP_NOT_A_PAIR",
    "MATCHUP_PLAYER_NOT_REGISTERED",
    "MATCHUP_PLAYER_REPEATED",
    "MATCHUP_SIDES_MISMATCH",
    "MATCHUP_SIDE_MISSING_IDENTITY",
})

#: Findings from ``validate_transition`` only.  These never reach ``classify``:
#: they gate publication through its ``transition_ok`` argument, because they
#: describe the *move* from one version to the next, not the register itself.
TRANSITION_ONLY_FINDINGS = frozenset({
    "NON_MONOTONIC_VERSION",
    "MISSING_SUPERSEDES_LINK",
    "TRANSITION_CHANGED_SCOPE",
    "INVALID_DRAW_RELEASED_UNLATCH",
})


def normalize_player_name(name: Any) -> str:
    """Collapse a source's spelling to a comparison key.

    Spaces are dropped, not merely punctuation.  The census specimen: Kalshi
    writes ``Felix Auger-Aliassime`` and Polymarket writes ``Felix Auger
    Aliassime``.  Under a punctuation-only normalizer those are two keys, and
    the 11th-most-likely man in the men's draw renders as **two board rows**.
    Dropping spaces joins them; 19 of the men's field's 37 union rows then carry
    both sources instead of 18.
    """
    if not isinstance(name, str):
        return ""
    return "".join(ch for ch in name.lower() if ch.isalnum())


def is_non_player(name: Any) -> bool:
    """Whether ``name`` is an aggregate bucket rather than a competitor."""
    if not isinstance(name, str):
        return False
    return name.strip().lower() in NON_PLAYER_NAMES


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_source_entry(entry: Any, *, sources: set[str]) -> list[str]:
    """Validate one per-source identity block.  Returns finding codes."""
    if not isinstance(entry, dict):
        return ["REGISTER_SOURCE_WRONG_SHAPE"]
    if REQUIRED_SOURCE_FIELDS - entry.keys():
        return ["REGISTER_SOURCE_MISSING_FIELDS"]

    findings: list[str] = []
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
        # A missing source must not keep a stale identity — that is how a
        # delisted market keeps rendering last week's number.
        if entry.get("market_id") is not None or entry.get("outcome_id") is not None:
            findings.append("MISSING_ENTRY_HAS_IDENTITY")
    elif entry.get("market_id") is None or entry.get("outcome_id") is None:
        findings.append("MAPPED_ENTRY_MISSING_IDENTITY")

    if entry["status"] == "settled" and entry.get("terminal_result") not in TERMINAL_RESULTS:
        findings.append("SETTLED_WITHOUT_RESULT")

    if entry.get("price_observed_at") is not None and not is_iso8601(entry["price_observed_at"]):
        findings.append("INVALID_PRICE_OBSERVED_AT")

    return findings


def validate_player(player: Any, *, draw_released: bool, sources: set[str]) -> list[str]:
    """Validate one player entry.  Returns finding codes (empty == clean)."""
    if not isinstance(player, dict):
        return ["REGISTER_PLAYER_WRONG_SHAPE"]
    if REQUIRED_PLAYER_FIELDS - player.keys():
        return ["REGISTER_PLAYER_MISSING_FIELDS"]

    findings: list[str] = []
    if player["draw"] not in DRAWS:
        findings.append("UNKNOWN_DRAW")
    if is_non_player(player.get("display_name")) or is_non_player(player.get("entity_key")):
        findings.append("INVALID_NON_PLAYER_ENTITY")

    seed = player.get("seed")
    if seed is not None and (not isinstance(seed, int) or isinstance(seed, bool) or not 1 <= seed <= 32):
        findings.append("INVALID_SEED")

    slot = player.get("draw_slot")
    if slot is not None:
        # Before the ceremony there is no draw, so a slot is a guess wearing the
        # authority of a fact.  Empty-until-released is enforced, not documented.
        if not draw_released:
            findings.append("INVALID_DRAW_SLOT_BEFORE_RELEASE")
        elif not isinstance(slot, int) or isinstance(slot, bool) or not 1 <= slot <= 128:
            findings.append("INVALID_DRAW_SLOT")

    source_blocks = player.get("sources")
    if not isinstance(source_blocks, list) or not source_blocks:
        findings.append("REGISTER_PLAYER_NO_SOURCES")
        return findings

    seen_sources: set[str] = set()
    for block in source_blocks:
        findings.extend(validate_source_entry(block, sources=sources))
        if isinstance(block, dict):
            name = block.get("source")
            if name in seen_sources:
                findings.append("DUPLICATE_SOURCE_FOR_PLAYER")
            seen_sources.add(name)

    return findings


def validate_matchup(matchup: Any, *, entity_keys: set[str], sources: set[str]) -> list[str]:
    """Validate one daily-slate matchup entry."""
    if not isinstance(matchup, dict):
        return ["REGISTER_MATCHUP_WRONG_SHAPE"]
    if REQUIRED_MATCHUP_FIELDS - matchup.keys():
        return ["REGISTER_MATCHUP_MISSING_FIELDS"]

    findings: list[str] = []
    if matchup["draw"] not in DRAWS:
        findings.append("UNKNOWN_DRAW")
    if matchup["round"] not in ROUNDS:
        findings.append("UNKNOWN_ROUND")
    if not is_iso8601(matchup.get("scheduled_date")):
        findings.append("INVALID_SCHEDULED_DATE")

    players = matchup.get("players")
    if not isinstance(players, list) or len(players) != 2:
        findings.append("MATCHUP_NOT_A_PAIR")
    else:
        # A matchup may only name players the register already carries.  This is
        # what keeps a stale Cincinnati market from becoming a slate row: it has
        # no matchup entry, and it could not get one without both players.
        for key in players:
            if key not in entity_keys:
                findings.append("MATCHUP_PLAYER_NOT_REGISTERED")
        if players[0] == players[1]:
            findings.append("MATCHUP_PLAYER_REPEATED")

    source_blocks = matchup.get("sources")
    if not isinstance(source_blocks, list) or not source_blocks:
        findings.append("REGISTER_MATCHUP_NO_SOURCES")
        return findings

    for block in source_blocks:
        if not isinstance(block, dict):
            findings.append("REGISTER_SOURCE_WRONG_SHAPE")
            continue
        findings.extend(validate_source_entry(block, sources=sources))
        if block.get("status") == "missing":
            continue
        sides = block.get("sides")
        if not isinstance(sides, dict) or set(sides) != set(players if isinstance(players, list) else []):
            findings.append("MATCHUP_SIDES_MISMATCH")
            continue
        for side in sides.values():
            if not isinstance(side, dict) or side.get("outcome_id") is None:
                findings.append("MATCHUP_SIDE_MISSING_IDENTITY")

    return findings


def validate_register(register: Any, contract: dict[str, Any]) -> list[str]:
    """Validate a whole tournament register.  Returns sorted unique findings."""
    if not isinstance(register, dict):
        return ["REGISTER_WRONG_SHAPE"]
    if REQUIRED_REGISTER_FIELDS - register.keys():
        return ["REGISTER_MISSING_FIELDS"]

    spec = contract.get("tournament_contracts", {}).get(register.get("tournament"))
    if not spec:
        return ["UNKNOWN_TOURNAMENT"]

    findings: list[str] = []
    if register.get("schema_version") != contract.get("register_schema_version"):
        findings.append("REGISTER_SCHEMA_MISMATCH")
    if register.get("season") != spec.get("season"):
        findings.append("REGISTER_SEASON_MISMATCH")
    if not isinstance(register.get("version"), int) or register["version"] < 1:
        findings.append("INVALID_REGISTER_VERSION")
    if not is_iso8601(register.get("generated_at")):
        findings.append("INVALID_GENERATED_AT")
    if not isinstance(register.get("draw_released"), bool):
        findings.append("INVALID_DRAW_RELEASED")

    players = register.get("players")
    matchups = register.get("matchups")
    if not isinstance(players, list) or not isinstance(matchups, list):
        return sorted(set(findings + ["REGISTER_COLLECTIONS_WRONG_SHAPE"]))

    draw_released = register.get("draw_released") is True
    sources = set(contract.get("allowed_sources", ()))

    entity_keys: set[str] = set()
    slots: set[tuple] = set()
    name_keys: dict[tuple, str] = {}
    identities: dict[tuple, str] = {}

    for player in players:
        findings.extend(validate_player(player, draw_released=draw_released, sources=sources))
        if not isinstance(player, dict) or not REQUIRED_PLAYER_FIELDS <= player.keys():
            continue

        key = player["entity_key"]
        if key in entity_keys:
            findings.append("DUPLICATE_ENTITY_KEY")
        entity_keys.add(key)

        # Two entity_keys normalizing to one name is the two-rows-for-one-player
        # defect stated as a rule instead of hoped away.
        nkey = (player["draw"], normalize_player_name(player.get("display_name")))
        prior = name_keys.get(nkey)
        if prior is not None and prior != key:
            findings.append("DUPLICATE_PLAYER_ACROSS_KEYS")
        name_keys[nkey] = key

        slot = player.get("draw_slot")
        if slot is not None:
            cell = (player["draw"], slot)
            if cell in slots:
                findings.append("DUPLICATE_DRAW_SLOT")
            slots.add(cell)

        for block in player.get("sources") or []:
            if not isinstance(block, dict) or block.get("status") == "missing":
                continue
            identity = (block.get("source"), block.get("market_id"), block.get("outcome_id"))
            if None in identity:
                continue
            owner = identities.get(identity)
            if owner is not None and owner != key:
                findings.append("IDENTITY_REUSED_ACROSS_PLAYERS")
            identities[identity] = key

    matchup_keys: set[str] = set()
    for matchup in matchups:
        findings.extend(validate_matchup(matchup, entity_keys=entity_keys, sources=sources))
        if not isinstance(matchup, dict) or "matchup_key" not in matchup:
            continue
        if matchup["matchup_key"] in matchup_keys:
            findings.append("DUPLICATE_MATCHUP_KEY")
        matchup_keys.add(matchup["matchup_key"])

    return sorted(set(findings))


def classify(findings: list[str], *, transition_ok: bool | None = None) -> dict[str, Any]:
    """Map finding codes to ``(classification, action, publish)``.

    Deliberately the same order and the same words as
    ``grid_register.classify``: structurally invalid is rejected outright,
    ambiguity is routed to a human before any render concern, a render or
    freshness breach blocks release even when the register itself is
    well-formed, and only then may unambiguous drift publish.
    """
    hard_invalid = any(
        f.startswith(_HARD_INVALID_PREFIXES) or f in STRUCTURAL_FINDINGS for f in findings
    )
    ambiguous = any(f in AMBIGUOUS_FINDINGS for f in findings)
    unambiguous = any(f in UNAMBIGUOUS_FINDINGS for f in findings)
    render_bad = any(f in RENDER_FINDINGS for f in findings)

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
    """Validate a proposed next version: valid, one newer, same scope, linked back.

    One tennis-specific clause on top of the grid rules: ``draw_released`` is a
    **latch**.  It may go false->true when the ceremony happens; true->false
    would silently make every committed draw slot unvalidated again.
    """
    if proposed is None:
        return []
    findings = validate_register(proposed, contract)
    if not isinstance(proposed, dict):
        return sorted(set(findings))
    if proposed.get("version") != register.get("version", 0) + 1:
        findings.append("NON_MONOTONIC_VERSION")
    if (
        proposed.get("tournament") != register.get("tournament")
        or proposed.get("season") != register.get("season")
    ):
        findings.append("TRANSITION_CHANGED_SCOPE")
    if proposed.get("supersedes_version") != register.get("version"):
        findings.append("MISSING_SUPERSEDES_LINK")
    if register.get("draw_released") is True and proposed.get("draw_released") is not True:
        findings.append("INVALID_DRAW_RELEASED_UNLATCH")
    return sorted(set(findings))


# ---------------------------------------------------------------------------
# Drift detection (the daily sentinel's comparison core)
# ---------------------------------------------------------------------------

def _observed_index(candidates: list[dict[str, Any]]) -> dict[tuple, list[dict[str, Any]]]:
    index: dict[tuple, list[dict[str, Any]]] = {}
    for row in candidates:
        index.setdefault((row.get("source"), row.get("market_id"), row.get("outcome_id")), []).append(row)
    return index


def diff_against_inventory(register: dict[str, Any], candidates: Any) -> list[str]:
    """Compare registered identities against live source inventory.

    ``candidates`` is a list of observed rows, each ``{source, market_id,
    outcome_id, outcome_name, status, terminal_result, season}``.

    The asymmetry is inherited from the grid register on purpose: a **rename**
    or a **settlement** that keeps the pinned identity is unambiguous and may be
    auto-versioned; anything that changes *which market backs a row* is
    ambiguous and goes to a human.
    """
    if not isinstance(candidates, list):
        return ["CANDIDATES_WRONG_SHAPE"]
    if any(not isinstance(row, dict) for row in candidates):
        # One malformed row poisons publication for this tournament only, and it
        # is never silently dropped.
        return ["POISON_CANDIDATE"]

    findings: list[str] = []
    season = register.get("season")
    index = _observed_index(candidates)

    for player in register.get("players", []):
        if not isinstance(player, dict):
            continue
        for block in player.get("sources") or []:
            if not isinstance(block, dict) or block.get("status") == "missing":
                continue
            key = (block.get("source"), block.get("market_id"), block.get("outcome_id"))
            matches = index.get(key, [])
            if len(matches) > 1:
                findings.append("AMBIGUOUS_CANDIDATES")
                continue
            if not matches:
                findings.append("REGISTERED_IDENTITY_NOT_OBSERVED")
                continue

            row = matches[0]
            if row.get("status") == "settled" and block.get("status") == "live":
                if row.get("terminal_result") not in TERMINAL_RESULTS:
                    findings.append("SETTLEMENT_WITHOUT_RESULT")
                else:
                    findings.append("UNAMBIGUOUS_SETTLEMENT_DRIFT")
            elif (
                row.get("outcome_name") is not None
                and normalize_player_name(row.get("outcome_name"))
                != normalize_player_name(block.get("source_name"))
            ):
                findings.append("UNAMBIGUOUS_RENAME_DRIFT")

    if any(row.get("season") not in (None, season) for row in candidates):
        findings.append("NEXT_OR_OTHER_SEASON_CANDIDATE")

    return sorted(set(findings))


def check_freshness(register: dict[str, Any], now: datetime, *, max_age_hours: float = STALE_PRICE_HOURS) -> list[str]:
    """Verify every ``live`` identity has a recently observed price.

    Read from ``price_observed_at``, which the writer fills from
    ``futures_odds_snapshots.captured_at`` — **not** from
    ``futures_outcomes.last_updated``, which the census proved unreliable (the
    Polymarket men's field read 2026-07-21 on all 23 outcomes while its
    snapshots ran to 2026-08-10).  A board is only allowed to be rich; it is not
    allowed to be confident about a number nobody has seen since July.
    """
    findings: list[str] = []
    cutoff = now - timedelta(hours=max_age_hours)
    for player in register.get("players", []):
        if not isinstance(player, dict):
            continue
        for block in player.get("sources") or []:
            if not isinstance(block, dict) or block.get("status") != "live":
                continue
            observed = block.get("price_observed_at")
            if not is_iso8601(observed):
                findings.append("LIVE_PRICE_NEVER_OBSERVED")
                continue
            if datetime.fromisoformat(str(observed).replace("Z", "+00:00")) < cutoff:
                findings.append("LIVE_PRICE_STALE")
    return sorted(set(findings))


def check_rendered_rows(register: dict[str, Any], rendered: Any) -> list[str]:
    """Verify rendered rows honour their registered status.

    "Settled means settled" enforced at the render boundary, and the membership
    rule enforced in the one direction that matters: a row the register does not
    carry is ``UNREGISTERED_RENDER_ROW`` — *a market not in the register does
    not render*.
    """
    if not isinstance(rendered, list):
        return ["RENDERED_WRONG_SHAPE"]

    findings: list[str] = []
    by_row: dict[tuple, dict[str, Any]] = {}
    for player in register.get("players", []):
        if not isinstance(player, dict):
            continue
        for block in player.get("sources") or []:
            if isinstance(block, dict):
                by_row[(player.get("entity_key"), block.get("source"))] = block

    for row in rendered:
        if not isinstance(row, dict):
            findings.append("POISON_RENDER_ROW")
            continue
        block = by_row.get((row.get("entity_key"), row.get("source")))
        if block is None:
            findings.append("UNREGISTERED_RENDER_ROW")
            continue

        status = block.get("status")
        state = row.get("state")
        probability = row.get("probability")
        if status == "missing":
            if state != "missing" or probability is not None:
                findings.append("MISSING_RENDERED_AS_PROBABILITY")
        elif status == "settled":
            if state != block.get("terminal_result") or probability is not None:
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

def register_filename(tournament: str, season: str) -> str:
    return f"{tournament}-{season}.json"


def load_register(
    tournament: str,
    season: str,
    *,
    directory: Path | None = None,
) -> dict[str, Any] | None:
    """Load a committed register, or ``None`` when there is no readable file.

    ``None`` is meaningful and safe: no register means the page has no rows to
    render, which is an honest empty state.  A file that exists but is
    unreadable also returns ``None``, logged loudly — a broken register degrades
    to nothing, never to a wrong number.
    """
    path = (directory or REGISTER_DIR) / register_filename(tournament, season)
    try:
        if not path.is_file():
            return None
        return json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        logger.error("Tournament register %s unreadable — rendering nothing: %s", path, exc)
        return None


class TournamentRegister:
    """Read-only lookup view over a validated register.

    Built once per request.  Every method is a dict lookup; there is no
    matching, normalization or scoring on the serving path by design.
    """

    def __init__(self, data: dict[str, Any]):
        self.data = data
        self.tournament: str = data.get("tournament", "")
        self.season: str = data.get("season", "")
        self.version: int = data.get("version", 0)
        self.generated_at: str = data.get("generated_at", "")
        self.draw_released: bool = data.get("draw_released") is True

        self.players: list[dict[str, Any]] = [
            p for p in data.get("players", []) if isinstance(p, dict)
        ]
        self.matchups: list[dict[str, Any]] = [
            m for m in data.get("matchups", []) if isinstance(m, dict)
        ]

        # (source, market_id, outcome_id) -> (entity_key, source block).  The
        # serving path walks the outcomes it loaded and asks "is this identity
        # registered?"; anything absent never enters the board.
        self.by_identity: dict[tuple, tuple[str, dict[str, Any]]] = {}
        for player in self.players:
            for block in player.get("sources") or []:
                if not isinstance(block, dict) or block.get("status") == "missing":
                    continue
                identity = (block.get("source"), block.get("market_id"), block.get("outcome_id"))
                if None in identity:
                    continue
                self.by_identity[identity] = (player.get("entity_key", ""), block)

        self.by_entity: dict[str, dict[str, Any]] = {
            p.get("entity_key", ""): p for p in self.players
        }

    def draw_players(self, draw: str) -> list[dict[str, Any]]:
        return [p for p in self.players if p.get("draw") == draw]

    def market_ids(self, source: str | None = None) -> list[int]:
        """Distinct market ids the register pins, for a bounded targeted load."""
        ids = set()
        for player in self.players:
            for block in player.get("sources") or []:
                if not isinstance(block, dict):
                    continue
                if source is not None and block.get("source") != source:
                    continue
                if isinstance(block.get("market_id"), int):
                    ids.add(block["market_id"])
        for matchup in self.matchups:
            for block in matchup.get("sources") or []:
                if not isinstance(block, dict):
                    continue
                if source is not None and block.get("source") != source:
                    continue
                if isinstance(block.get("market_id"), int):
                    ids.add(block["market_id"])
        return sorted(ids)

    def entry_for_identity(self, source: str, market_id: Any, outcome_id: Any):
        return self.by_identity.get((source, market_id, outcome_id))

    def matchups_on(self, date_iso: str) -> list[dict[str, Any]]:
        return [m for m in self.matchups if str(m.get("scheduled_date", "")).startswith(date_iso)]

    def source_coverage(self) -> dict[str, int]:
        """How many players carry 1 source vs 2 — the blend-richness number."""
        counts: Counter = Counter()
        for player in self.players:
            live = [
                b for b in (player.get("sources") or [])
                if isinstance(b, dict) and b.get("status") != "missing"
            ]
            counts[f"{len(live)}_source"] += 1
        return dict(sorted(counts.items()))

    def counters(self) -> dict[str, int]:
        counts: Counter = Counter()
        for player in self.players:
            counts[f"players_{player.get('draw', 'unknown')}"] += 1
            for block in player.get("sources") or []:
                if isinstance(block, dict):
                    counts[f"source_{block.get('status', 'invalid')}"] += 1
        counts["matchups"] = len(self.matchups)
        counts["seeded"] = sum(1 for p in self.players if p.get("seed") is not None)
        counts["draw_slotted"] = sum(1 for p in self.players if p.get("draw_slot") is not None)
        return dict(sorted(counts.items()))


def build_contract(tournament_specs: dict[str, Any]) -> dict[str, Any]:
    """Assemble a validation contract from tournament specs."""
    return {
        "register_schema_version": SCHEMA_VERSION,
        "allowed_sources": list(ALLOWED_SOURCES),
        "draws": list(DRAWS),
        "rounds": list(ROUNDS),
        "tournament_contracts": tournament_specs,
    }


def us_open_2026_contract() -> dict[str, Any]:
    """The contract this program ships against."""
    return build_contract({"us-open": {"season": "2026", "entity_kind": "player"}})


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
