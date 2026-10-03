"""#10319 — give ONE women's game (event 15321333, Parma Calcio v Ternana) its women's identity.

THE SHIP: Parma–Ternana identifies as women's Serie A Femminile and stops showing
men's competition context ("Bigger Picture" men's Conference League prop, "MORE
SOCCER" men's Serie A futures).

WHY ONE ROW
-----------

Kalshi's ``KXSERIEAWGAME`` (women's) prefix-matched the bare ``kxseriea`` key, so
this game was created under men's ``soccer_italy_serie_a``. PR #10337 (``f922659ba8``,
main v5447) stops new cases and seeds the women's Sport row 427850. It does not move
a row that already exists. This tool moves exactly that one row, and nothing else.
Two more games of the same shape (15321317, 15321298) are outside it: widening is a
separate admission (packet §7 P5).

WHAT IS WRITTEN: ``events`` id 15321333, four columns
-----------------------------------------------------

* ``sport_id``: the banked men's ``soccer_italy_serie_a`` id -> 427850;
* ``llm_gender``: ``men`` -> ``women``;
* ``llm_league``: ``Serie_A`` -> ``Serie_A_Femminile``;
* ``event_tags``: the exact banked array with four IN-PLACE substitutions
  (``gender:men``, ``league:serie_a``, ``tier:2``, ``class:international`` ->
  ``gender:women``, ``league:serie_a_femminile``, ``tier:4``, ``class:other``). Each
  old tag must occur exactly once and each new tag not at all; every other tag keeps
  its value and position. No taxonomy recompute.

Thirteen more event columns are FENCED (read, banked, compared, never written):
status, commence_time, completed_at, both names, both team FKs, both scores,
espn_id, external_id, llm_level, llm_importance. ``win_probability_sources`` is
banked and read back unchanged inside the write transaction; it is not a fence and
never written. Sport 427850, market 63152777 and the bound team rows are
corroboration reads, never writes.

IDENTITY (never club names, never kickoff)
------------------------------------------

Admission needs our own market 63152777 to assert it: ``event_id = 15321333``,
``source = 'kalshi'``, ``external_id`` in the ``KXSERIEAWGAME-26OCT03PARTER`` family,
``market_metadata->>'competition'`` = Serie A Femminile, and ``competition_scope``
NULL or ``Game``. The market's own sport is recorded, never judged or moved. The
linked set must be exactly ``{63152777}``; an extra linked row is P5 and refuses.

Team FKs (P3): a NULL FK, or a bound row ``binding_is_sound`` against the
PROPOSED women's sport, needs no ruling. A dangling, cross-club or wrong-sport
binding refuses with ``TEAM_BINDING_SCOPE_REQUIRED`` and writes nothing: the tool
never clears, retargets or invents a team.

THREE MODES, ONE FILE EACH WAY
------------------------------

``--preflight`` (default) runs R1–R5 inside one REPEATABLE READ READ ONLY
transaction and writes an immutable plan JSON (exclusive create, file + directory
fsync, read-only mode) with a detached ``<plan>.sha256`` sidecar. The plan carries
an embedded ``content_address`` over its canonical payload (``digest_fields``, the
address field itself excluded) — never a hash of its own final bytes.

``--apply`` consumes only that reviewed plan (``--plan-hash`` = the detached
final-byte SHA256). It re-derives nothing from the database. It banks a backup
file + sidecar BEFORE connecting, then in one bounded transaction locks the event
``FOR UPDATE`` (which also blocks any new ``futures_markets`` row being linked to it —
an FK insert takes ``FOR KEY SHARE`` on the event) and the Sport rows, the market,
the linked set and the bound teams ``FOR SHARE``; any drift from the plan refuses.
One compare-and-swap UPDATE writes the four columns, requires rowcount 1 and an
exact RETURNING post-image, and an in-transaction read back. After COMMIT a new
transaction verifies. A failure around COMMIT is classified from an exact-ID read
only (before = NOT_APPLIED, after = APPLIED, anything else = COMMIT_UNKNOWN) and
the tool STOPS; it never re-applies.

``--restore`` is the exact inverse of this tool's four-column write, from the
backup and its recorded detached hash. It compares the 17 columns this tool
names — the 4 written (must still equal the backup's post-image) and the 13 fenced
(must still equal its pre-image), tag order included — and refuses otherwise,
leaving the later state. It does not compare, and cannot detect, changes to other
event columns or to the market row, and never writes them. A row already exactly at
the before-image is reported NOT_APPLIED with no write.

INTERFACE (specimens only; executing any of them needs root's separate admission)
-------------------------------------------------------------------------------

    python3 scripts/repair_10319_event15321333_competition_identity.py --only 15321333 --preflight --plan-out /abs/plan.json
    python3 scripts/repair_10319_event15321333_competition_identity.py --only 15321333 --apply --plan /abs/plan.json --plan-hash <hex> --backup-out /abs/backup.json
    python3 scripts/repair_10319_event15321333_competition_identity.py --only 15321333 --restore --backup /abs/backup.json --backup-hash <hex>

Refuses unless ``HEROKU_APP_NAME`` is ``bainluck`` — a target fence, not approval.
Exit codes: 0 PLANNED / APPLIED / restore NOT_APPLIED (already at the before-image);
1 REFUSED or apply NOT_APPLIED; 2 usage; 3 COMMIT_UNKNOWN; 4 runtime harness error.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Callable

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

from app.utils.repair_apply_plan import digest_fields  # noqa: E402
from app.utils.team_binding_invariant import (  # noqa: E402
    binding_defect,
    binding_is_sound,
)

TOOL = "repair_10319_event15321333_competition_identity"
PRODUCTION_APPS = frozenset({"bainluck"})

PLAN_SCHEMA = "repair-10319-event15321333-plan/v1"
BACKUP_SCHEMA = "repair-10319-event15321333-backup/v1"
RECEIPT_SCHEMA = "repair-10319-event15321333-receipt/v1"
ADDRESS_NAMESPACE = "bainluck:repair:10319:event15321333"

#: The packet this tool implements (rev2, artifacts/10319-existing-event-repair/).
PACKET_PIN = {
    "packet_md_sha256": "7d80c02661d51873794e17b0973ec291648bd22ce6275faff8d3177fbc6563e6",
    "operations_sql_sha256": "7e27f67d6c65019ba4d217ee2b3e67dacd891d73cdb13ef610c665fba1efcc7e",
    "source_admission": "root 2026-10-03T18:04:51Z",
}

EVENT_ID = 15321333
MARKET_ID = 63152777
WOMEN_SPORT_ID = 427850
WOMEN_SPORT_KEY = "soccer_italy_serie_a_women"
WOMEN_SPORT_NAME = "Serie A Femminile - Italy (Women)"
SPORT_GROUP = "Soccer"
MEN_SPORT_KEY = "soccer_italy_serie_a"

OLD_GENDER, NEW_GENDER = "men", "women"
OLD_LEAGUE, NEW_LEAGUE = "Serie_A", "Serie_A_Femminile"
TAG_SUBSTITUTIONS: tuple[tuple[str, str], ...] = (
    ("gender:men", "gender:women"),
    ("league:serie_a", "league:serie_a_femminile"),
    ("tier:2", "tier:4"),
    ("class:international", "class:other"),
)

MARKET_SOURCE = "kalshi"
MARKET_SERIES = "KXSERIEAWGAME"
MARKET_EVENT_TICKER = "KXSERIEAWGAME-26OCT03PARTER"
MARKET_COMPETITION = "serie a femminile"  # compared lower/btrim; exact string banked
MARKET_SCOPES_ADMITTED = (None, "Game")
LINKED_SET = [MARKET_ID]

WRITTEN_COLUMNS = ("sport_id", "llm_gender", "llm_league", "event_tags")
FENCED_COLUMNS = (
    "status", "commence_time", "completed_at",
    "home_team_name", "away_team_name", "home_team_id", "away_team_id",
    "home_score", "away_score", "espn_id", "external_id",
    "llm_level", "llm_importance",
)
COMPARED_COLUMNS = WRITTEN_COLUMNS + FENCED_COLUMNS
BANKED_ONLY_COLUMN = "win_probability_sources"

#: SQL cast per compared column, so every bind is typed (NULL included).
_CASTS = {
    "sport_id": "integer", "llm_gender": "text", "llm_league": "text",
    "event_tags": "jsonb", "status": "text", "commence_time": "timestamptz",
    "completed_at": "timestamptz", "home_team_name": "text",
    "away_team_name": "text", "home_team_id": "integer", "away_team_id": "integer",
    "home_score": "integer", "away_score": "integer", "espn_id": "text",
    "external_id": "text", "llm_level": "text", "llm_importance": "text",
}
_TIMESTAMPS = frozenset({"commence_time", "completed_at"})

LOCK_TIMEOUT_MS = 5000
STATEMENT_TIMEOUT_MS = 10000

# States and exits.
PLANNED, APPLIED, NOT_APPLIED = "PLANNED", "APPLIED", "NOT_APPLIED"
REFUSED, COMMIT_UNKNOWN = "REFUSED", "COMMIT_UNKNOWN"
EXIT_OK, EXIT_REFUSED, EXIT_USAGE, EXIT_COMMIT_UNKNOWN, EXIT_RUNTIME = 0, 1, 2, 3, 4

TEAM_BINDING_SCOPE_REQUIRED = "TEAM_BINDING_SCOPE_REQUIRED"


class Refused(RuntimeError):
    """A gate refused. Nothing was written."""

    def __init__(self, reason: str, detail: Any = None):
        super().__init__(reason)
        self.reason = reason
        self.detail = detail


# --- pure: canonical values, tags, addresses ---------------------------------

def canon(value: Any) -> Any:
    """The one JSON form a value is banked, compared and addressed in."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise Refused("naive_timestamp", str(value))
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, dict):
        return {str(k): canon(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [canon(v) for v in value]
    return value


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def content_address(schema: str, payload: dict) -> str:
    """SHA256 over the canonical payload, encoded by the shared injective encoder."""
    body = {k: v for k, v in payload.items() if k != "content_address"}
    line = digest_fields(ADDRESS_NAMESPACE, schema, canonical_json(body))
    return hashlib.sha256(line.encode("utf-8")).hexdigest()


def substitute_tags(pre_tags: Any) -> list[str]:
    """The four in-place substitutions, or Refused. Pure."""
    if not isinstance(pre_tags, list) or not all(isinstance(t, str) for t in pre_tags):
        raise Refused("event_tags_not_a_string_array", pre_tags)
    post = list(pre_tags)
    for old, new in TAG_SUBSTITUTIONS:
        if pre_tags.count(old) != 1:
            raise Refused("old_tag_not_exactly_once", {"tag": old, "count": pre_tags.count(old)})
        if new in pre_tags:
            raise Refused("new_tag_already_present", {"tag": new})
        post[pre_tags.index(old)] = new
    return post


def post_image_of(pre: dict) -> dict:
    return {
        "sport_id": WOMEN_SPORT_ID,
        "llm_gender": NEW_GENDER,
        "llm_league": NEW_LEAGUE,
        "event_tags": substitute_tags(pre["event_tags"]),
    }


def _ticker_in_family(external_id: Any) -> bool:
    return isinstance(external_id, str) and (
        external_id == MARKET_EVENT_TICKER or external_id.startswith(MARKET_EVENT_TICKER + "-")
    )


def team_verdict(side: str, team_id: Any, row_name: Any, team: dict | None) -> dict:
    """P3 for one side, judged against the PROPOSED women's sport. Pure."""
    out = {"side": side, "team_id": team_id, "row_name": row_name, "team_row": team}
    if team_id is None:
        out["verdict"] = "NULL_FK"
    elif team is None:
        out["verdict"] = "DANGLING_FK"
    elif binding_is_sound(row_name, team.get("name"), team.get("sport_id"), WOMEN_SPORT_ID):
        out["verdict"] = "SOUND"
    else:
        out["verdict"] = (
            binding_defect(row_name, team.get("name"), team.get("sport_id"), WOMEN_SPORT_ID)
            or "UNSOUND"
        ).upper()
    return out


def admit(
    event: dict | None,
    sports: list[dict],
    market: dict | None,
    linked: list[int],
    teams: dict[int, dict],
) -> dict:
    """R1–R5 -> the plan body, or Refused. Pure: the unit file drives every branch.

    ``event``: the R1 row (compared columns + ``win_probability_sources``) or None.
    ``sports``: R2 rows ``{id, key, name, group, active}``.
    ``market``: R3 ``{id, event_id, source, external_id, competition,
    competition_scope, sport_id, sport_key}`` or None.
    ``linked``: R4 ids. ``teams``: R5 rows by team id ``{id, name, sport_id}``.
    """
    if event is None:
        raise Refused("event_missing", {"event_id": EVENT_ID})
    pre = {c: canon(event.get(c)) for c in COMPARED_COLUMNS}
    banked = canon(event.get(BANKED_ONLY_COLUMN))

    women = [s for s in sports if s.get("key") == WOMEN_SPORT_KEY]
    men = [s for s in sports if s.get("key") == MEN_SPORT_KEY]
    target = [s for s in sports if s.get("id") == WOMEN_SPORT_ID]
    if len(women) != 1 or len(target) != 1 or women[0] is not target[0]:
        raise Refused("target_sport_not_unique", sports)
    t = target[0]
    if (t.get("name"), t.get("group"), t.get("active")) != (WOMEN_SPORT_NAME, SPORT_GROUP, True):
        raise Refused("target_sport_mismatch", t)
    if len(men) != 1 or len(sports) != 2:
        raise Refused("men_sport_not_unique", sports)
    if pre["sport_id"] != men[0]["id"]:
        raise Refused(
            "event_not_on_men_sport", {"event_sport_id": pre["sport_id"], "men_sport_id": men[0]["id"]}
        )
    if pre["llm_gender"] != OLD_GENDER:
        raise Refused("event_gender_not_men", pre["llm_gender"])
    if pre["llm_league"] != OLD_LEAGUE:
        raise Refused("event_league_not_serie_a", pre["llm_league"])
    post = post_image_of(pre)

    if market is None:
        raise Refused("identity_missing:market", {"market_id": MARKET_ID})
    identity = {
        "id": market.get("id"),
        "event_id": market.get("event_id"),
        "source": market.get("source"),
        "external_id": market.get("external_id"),
        "competition": market.get("competition"),
        "competition_scope": market.get("competition_scope"),
    }
    if identity["id"] != MARKET_ID:
        raise Refused("identity_conflict:id", identity)
    if identity["event_id"] != EVENT_ID:
        raise Refused("identity_conflict:event_id", identity)
    if identity["source"] != MARKET_SOURCE:
        raise Refused("identity_conflict:source", identity)
    if not _ticker_in_family(identity["external_id"]):
        raise Refused("identity_conflict:external_id", identity)
    comp = identity["competition"]
    if not isinstance(comp, str) or comp.strip().lower() != MARKET_COMPETITION:
        raise Refused("identity_conflict:competition", identity)
    if identity["competition_scope"] not in MARKET_SCOPES_ADMITTED:
        raise Refused("identity_conflict:competition_scope", identity)
    recorded = {"sport_id": market.get("sport_id"), "sport_key": market.get("sport_key")}

    if sorted(linked) != LINKED_SET:
        raise Refused("linked_set_not_exact", {"linked": sorted(linked), "expected": LINKED_SET})

    sides = [
        team_verdict(side, pre[f"{side}_team_id"], pre[f"{side}_team_name"],
                     teams.get(pre[f"{side}_team_id"]) if pre[f"{side}_team_id"] is not None else None)
        for side in ("home", "away")
    ]
    if any(s["verdict"] not in ("NULL_FK", "SOUND") for s in sides):
        raise Refused(TEAM_BINDING_SCOPE_REQUIRED, sides)

    return {
        "event_id": EVENT_ID,
        "write_allowlist": {"table": "events", "id": EVENT_ID, "columns": list(WRITTEN_COLUMNS)},
        "fenced_columns": list(FENCED_COLUMNS),
        "pre_image": pre,
        "post_image": post,
        "banked_unwritten": {BANKED_ONLY_COLUMN: banked},
        "corroboration": {
            "sports": sorted((canon(s) for s in sports), key=lambda s: s["id"]),
            "market_identity": identity,
            "market_recorded": recorded,
            "linked_set": LINKED_SET,
        },
        "team_compatibility": sides,
    }


def diff_compared(row: dict, want_written: dict, want_fenced: dict) -> list[str]:
    """Columns whose current value differs from what this step requires."""
    bad = [c for c in WRITTEN_COLUMNS if canon(row.get(c)) != want_written[c]]
    bad += [c for c in FENCED_COLUMNS if canon(row.get(c)) != want_fenced[c]]
    return bad


def classify(row: dict | None, before: dict, after_written: dict) -> str:
    """Exact-ID read after an ambiguous COMMIT: before / after / anything else."""
    if row is None:
        return COMMIT_UNKNOWN
    pre_written = {c: before[c] for c in WRITTEN_COLUMNS}
    if not diff_compared(row, after_written, before):
        return APPLIED
    if not diff_compared(row, pre_written, before):
        return NOT_APPLIED
    return COMMIT_UNKNOWN


# --- pure: durable files ------------------------------------------------------

_fsync = os.fsync  # module seam: the unit file fails it to prove nothing is written


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _require_new_absolute(path: str, what: str) -> None:
    if not path or not os.path.isabs(path):
        raise Refused(f"{what}_path_not_absolute", path)
    for p in (path, path + ".sha256"):
        if os.path.lexists(p):
            raise Refused(f"{what}_path_exists", p)
    if not os.path.isdir(os.path.dirname(path)):
        raise Refused(f"{what}_directory_missing", os.path.dirname(path))


def _write_once(path: str, data: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view):]
        _fsync(fd)
    finally:
        os.close(fd)
    os.chmod(path, 0o444)
    dfd = os.open(os.path.dirname(path), os.O_RDONLY)
    try:
        _fsync(dfd)
    finally:
        os.close(dfd)


def write_artifact(path: str, schema: str, body: dict, what: str) -> dict:
    """Exclusive, fsynced, read-only JSON + detached ``<path>.sha256``. Returns hashes."""
    _require_new_absolute(path, what)
    payload = {"schema": schema, **body}
    payload["content_address"] = content_address(schema, payload)
    data = (canonical_json(payload) + "\n").encode("utf-8")
    digest = _sha256_hex(data)
    try:
        _write_once(path, data)
        _write_once(path + ".sha256", f"{digest}  {os.path.basename(path)}\n".encode())
    except OSError as exc:
        raise Refused(f"{what}_durability_failed", f"{type(exc).__name__}: {exc}") from exc
    with open(path, "rb") as fh:
        if _sha256_hex(fh.read()) != digest:
            raise Refused(f"{what}_readback_mismatch", path)
    return {"path": path, "sha256": digest, "content_address": payload["content_address"]}


def load_artifact(path: str, expected_hash: str, schema: str, what: str) -> dict:
    """Verify the detached hash, the sidecar, the schema and the embedded address."""
    if not path or not os.path.isabs(path):
        raise Refused(f"{what}_path_not_absolute", path)
    want = (expected_hash or "").strip().lower()
    if len(want) != 64 or any(ch not in "0123456789abcdef" for ch in want):
        raise Refused(f"{what}_hash_malformed", expected_hash)
    try:
        with open(path, "rb") as fh:
            data = fh.read()
        with open(path + ".sha256", "r", encoding="utf-8") as fh:
            sidecar = fh.read().split()
    except OSError as exc:
        raise Refused(f"{what}_missing", f"{type(exc).__name__}: {exc}") from exc
    got = _sha256_hex(data)
    if got != want:
        raise Refused(f"{what}_hash_mismatch", {"expected": want, "actual": got})
    if sidecar[:2] != [want, os.path.basename(path)]:
        raise Refused(f"{what}_sidecar_mismatch", sidecar)
    try:
        payload = json.loads(data)
    except ValueError as err:
        raise Refused(f"{what}_corrupt", str(err)) from err
    if not isinstance(payload, dict) or payload.get("schema") != schema:
        raise Refused(f"{what}_wrong_schema", payload.get("schema") if isinstance(payload, dict) else None)
    if payload.get("content_address") != content_address(schema, payload):
        raise Refused(f"{what}_address_mismatch", payload.get("content_address"))
    if payload.get("event_id") != EVENT_ID or payload.get("write_allowlist") != {
        "table": "events", "id": EVENT_ID, "columns": list(WRITTEN_COLUMNS)
    } or payload.get("fenced_columns") != list(FENCED_COLUMNS):
        raise Refused(f"{what}_scope_mismatch", payload.get("write_allowlist"))
    if post_image_of(payload["pre_image"]) != payload.get("post_image"):
        raise Refused(f"{what}_post_image_incoherent", payload.get("post_image"))
    return payload


def tool_pin() -> dict:
    with open(os.path.abspath(__file__), "rb") as fh:
        tool_sha = _sha256_hex(fh.read())
    return {
        "tool": TOOL,
        "tool_file_sha256": tool_sha,
        "source_version": os.environ.get("SOURCE_VERSION") or os.environ.get("HEROKU_SLUG_COMMIT"),
    }


# --- SQL (exact ids only; every statement is tagged for the unit file's fake) --

_R1 = text(
    "/* r10319:R1 */ SELECT id, " + ", ".join(COMPARED_COLUMNS) + f", {BANKED_ONLY_COLUMN} "
    "FROM events WHERE id = :eid"
)
_R1_LOCK = text(_R1.text.replace("r10319:R1", "r10319:R1_LOCK") + " FOR UPDATE")
_R2 = text(
    "/* r10319:R2 */ SELECT id, key, name, \"group\", active FROM sports "
    "WHERE id = :wid OR key IN (:wkey, :mkey) ORDER BY id"
)
_R2_LOCK = text(_R2.text.replace("r10319:R2", "r10319:R2_LOCK") + " FOR SHARE")
_R3 = text(
    "/* r10319:R3 */ SELECT f.id, f.event_id, f.source, f.external_id, "
    "f.market_metadata->>'competition' AS competition, "
    "f.market_metadata->>'competition_scope' AS competition_scope, "
    "f.sport_id, ms.key AS sport_key "
    "FROM futures_markets f LEFT JOIN sports ms ON ms.id = f.sport_id WHERE f.id = :mid"
)
_R3_LOCK = text(
    "/* r10319:R3_LOCK */ SELECT f.id, f.event_id, f.source, f.external_id, "
    "f.market_metadata->>'competition' AS competition, "
    "f.market_metadata->>'competition_scope' AS competition_scope "
    "FROM futures_markets f WHERE f.id = :mid FOR SHARE"
)
_R4 = text("/* r10319:R4 */ SELECT id FROM futures_markets WHERE event_id = :eid ORDER BY id")
_R4_LOCK = text(_R4.text.replace("r10319:R4", "r10319:R4_LOCK") + " FOR SHARE")
_R5 = text("/* r10319:R5 */ SELECT id, name, sport_id FROM teams WHERE id = ANY(:ids) ORDER BY id")
_R5_LOCK = text(_R5.text.replace("r10319:R5", "r10319:R5_LOCK") + " FOR SHARE")


def _fence_sql(prefix: str) -> str:
    return " AND ".join(
        f"{c} IS NOT DISTINCT FROM CAST(:{prefix}{c} AS {_CASTS[c]})" for c in COMPARED_COLUMNS
    )


_APPLY = text(
    "/* r10319:APPLY */ UPDATE events SET "
    "sport_id = CAST(:new_sport_id AS integer), llm_gender = CAST(:new_llm_gender AS text), "
    "llm_league = CAST(:new_llm_league AS text), event_tags = CAST(:new_event_tags AS jsonb) "
    "WHERE id = :eid AND " + _fence_sql("cas_") + " "
    "AND EXISTS (SELECT 1 FROM sports s WHERE s.id = CAST(:new_sport_id AS integer) "
    "AND s.key = :wkey AND s.active) "
    "AND EXISTS (SELECT 1 FROM futures_markets f WHERE f.id = :mid "
    "AND f.event_id = :eid AND f.source = :m_source AND f.external_id = :m_external_id "
    "AND f.market_metadata->>'competition' IS NOT DISTINCT FROM CAST(:m_competition AS text) "
    "AND f.market_metadata->>'competition_scope' IS NOT DISTINCT FROM CAST(:m_scope AS text)) "
    "RETURNING id, sport_id, llm_gender, llm_league, event_tags"
)
_RESTORE = text(
    "/* r10319:RESTORE */ UPDATE events SET "
    "sport_id = CAST(:new_sport_id AS integer), llm_gender = CAST(:new_llm_gender AS text), "
    "llm_league = CAST(:new_llm_league AS text), event_tags = CAST(:new_event_tags AS jsonb) "
    "WHERE id = :eid AND " + _fence_sql("cas_") + " "
    "RETURNING id, sport_id, llm_gender, llm_league, event_tags"
)


def _bind(column: str, value: Any) -> Any:
    if value is None:
        return None
    if column == "event_tags":
        return canonical_json(value)
    if column in _TIMESTAMPS:
        return datetime.fromisoformat(value)
    return value


def _cas_params(written: dict, fenced: dict) -> dict:
    params = {f"cas_{c}": _bind(c, written[c]) for c in WRITTEN_COLUMNS}
    params.update({f"cas_{c}": _bind(c, fenced[c]) for c in FENCED_COLUMNS})
    return params


def _new_params(target: dict) -> dict:
    return {f"new_{c}": _bind(c, target[c]) for c in WRITTEN_COLUMNS}


async def _rows(session, stmt, params: dict) -> list[dict]:
    result = await session.execute(stmt, params)
    return [dict(r) for r in result.mappings().all()]


async def _one(session, stmt, params: dict) -> dict | None:
    rows = await _rows(session, stmt, params)
    if len(rows) > 1:
        raise Refused("exact_id_read_not_unique", {"rows": len(rows)})
    return rows[0] if rows else None


_JSONB_COLUMNS = ("event_tags", BANKED_ONLY_COLUMN)


def _decode_jsonb(row: dict | None) -> dict | None:
    """asyncpg hands jsonb back as text through a bare ``text()`` select. Only the
    two jsonb columns are decoded — a name that happens to start with ``[`` is not."""
    if row is None:
        return None
    for c in _JSONB_COLUMNS:
        if isinstance(row.get(c), str):
            row[c] = json.loads(row[c])
    return row


async def _read_event(session, *, lock: bool) -> dict | None:
    return _decode_jsonb(await _one(session, _R1_LOCK if lock else _R1, {"eid": EVENT_ID}))


async def _read_all(session, *, lock: bool) -> tuple:
    event = await _read_event(session, lock=lock)
    sports = await _rows(
        session, _R2_LOCK if lock else _R2,
        {"wid": WOMEN_SPORT_ID, "wkey": WOMEN_SPORT_KEY, "mkey": MEN_SPORT_KEY},
    )
    market = await _one(session, _R3_LOCK if lock else _R3, {"mid": MARKET_ID})
    linked = [int(r["id"]) for r in await _rows(session, _R4_LOCK if lock else _R4, {"eid": EVENT_ID})]
    ids = [] if event is None else [
        event[c] for c in ("home_team_id", "away_team_id") if event.get(c) is not None
    ]
    teams = {}
    if ids:
        teams = {int(r["id"]): r for r in await _rows(session, _R5_LOCK if lock else _R5, {"ids": ids})}
    return event, sports, market, linked, teams


def _identity_drift(plan: dict, sports, market, linked, teams) -> str | None:
    corr = plan["corroboration"]
    if sorted((canon(s) for s in sports), key=lambda s: s["id"]) != corr["sports"]:
        return "identity_drift:sports"
    if market is None:
        return "identity_drift:market_missing"
    for field_name, banked in corr["market_identity"].items():
        if market.get(field_name) != banked:
            return f"identity_drift:{field_name}"
    if sorted(linked) != corr["linked_set"]:
        return "identity_drift:linked_set"
    for side in plan["team_compatibility"]:
        now = teams.get(side["team_id"]) if side["team_id"] is not None else None
        if (canon(now) if now else None) != side["team_row"]:
            return f"identity_drift:team_{side['side']}"
        if team_verdict(side["side"], side["team_id"], side["row_name"], now)["verdict"] not in (
            "NULL_FK", "SOUND"
        ):
            return f"identity_drift:team_{side['side']}"
    return None


# --- the three modes (session_factory: () -> async context manager of a session) --

SessionFactory = Callable[[], Any]


def _counts(written_rows: int = 0, drift: int = 0) -> dict:
    return {
        "event_id": EVENT_ID,
        "written_rows": written_rows,
        "written_columns": len(WRITTEN_COLUMNS) if written_rows else 0,
        "concurrent_drift": drift,
    }


def _result(mode: str, state: str, *, reason: str | None = None, detail: Any = None,
            written_rows: int = 0, drift: int = 0, **extra) -> dict:
    out = {"schema": RECEIPT_SCHEMA, "mode": mode, "state": state,
           "counts": _counts(written_rows, drift)}
    if reason is not None:
        out["reason"] = reason
    if detail is not None:
        out["detail"] = detail
    out.update(extra)
    return out


def _db_reason(exc: BaseException) -> str:
    orig = getattr(exc, "orig", None)
    code = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    if code is None and orig is not None:
        code = getattr(getattr(orig, "__cause__", None), "sqlstate", None)
    if code == "55P03":
        return "lock_timeout"
    if code == "57014":
        return "statement_timeout"
    return f"db_error:{type(exc).__name__}"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


async def run_preflight(session_factory: SessionFactory, *, plan_out: str,
                        clock: Callable[[], str] = _utcnow) -> dict:
    """R1–R5 in one REPEATABLE READ READ ONLY transaction; writes the plan file."""
    try:
        _require_new_absolute(plan_out, "plan")
        async with session_factory() as session:
            try:
                await session.execute(
                    text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
                )
                event, sports, market, linked, teams = await _read_all(session, lock=False)
            finally:
                await session.rollback()
        body = admit(event, sports, market, linked, teams)
    except Refused as exc:
        return _result("preflight", REFUSED, reason=exc.reason, detail=canon_safe(exc.detail))
    body.update({"pins": {**tool_pin(), "packet": PACKET_PIN}, "planned_at": clock()})
    try:
        written = write_artifact(plan_out, PLAN_SCHEMA, body, "plan")
    except Refused as exc:
        return _result("preflight", REFUSED, reason=exc.reason, detail=canon_safe(exc.detail))
    return _result(
        "preflight", PLANNED, plan=written,
        proposed_diff={c: {"from": body["pre_image"][c], "to": body["post_image"][c]}
                       for c in WRITTEN_COLUMNS},
        preserved=body["pre_image"], corroboration=body["corroboration"],
        team_compatibility=body["team_compatibility"],
    )


def canon_safe(value: Any) -> Any:
    try:
        return canon(value)
    except Exception:  # detail is diagnostic; never let it mask the refusal
        return repr(value)


async def _verify_new_transaction(session_factory, written_want: dict, fenced_want: dict) -> tuple:
    """Exact-ID read in a NEW transaction. Returns (row, columns that differ)."""
    async with session_factory() as session:
        try:
            row = await _read_event(session, lock=False)
        finally:
            await session.rollback()
    if row is None:
        return None, ["row_missing"]
    return row, diff_compared(row, written_want, fenced_want)


async def _write_step(session_factory, *, mode: str, plan: dict, stmt, from_written: dict,
                      to_written: dict, check_identity: bool, lock_timeout_ms: int,
                      statement_timeout_ms: int, extra: dict) -> dict:
    """One bounded transaction: lock, compare, CAS, RETURNING, read back, COMMIT, verify."""
    pre = plan["pre_image"]
    fenced = {c: pre[c] for c in FENCED_COLUMNS}
    committed = commit_attempted = False
    commit_error = ""
    try:
        async with session_factory() as session:
            try:
                await session.execute(text(f"SET LOCAL lock_timeout = '{int(lock_timeout_ms)}ms'"))
                await session.execute(
                    text(f"SET LOCAL statement_timeout = '{int(statement_timeout_ms)}ms'")
                )
                if check_identity:
                    event, sports, market, linked, teams = await _read_all(session, lock=True)
                else:
                    event = await _read_event(session, lock=True)
                if event is None:
                    raise Refused("event_missing", {"event_id": EVENT_ID})
                if mode == "restore" and not diff_compared(
                    event, {c: pre[c] for c in WRITTEN_COLUMNS}, fenced
                ):
                    await session.rollback()
                    return _result(mode, NOT_APPLIED, reason="already_at_before_image", **extra)
                drifted = diff_compared(event, from_written, fenced)
                if drifted:
                    raise Refused(
                        ("concurrent_drift" if mode == "apply" else "restore_after_drift")
                        + ":" + ",".join(drifted),
                        {c: canon_safe(event.get(c)) for c in drifted},
                    )
                if check_identity:
                    why = _identity_drift(plan, sports, market, linked, teams)
                    if why:
                        raise Refused(why)
                wps_locked = canon(event.get(BANKED_ONLY_COLUMN))
                params = {"eid": EVENT_ID, **_cas_params(from_written, fenced), **_new_params(to_written)}
                if check_identity:
                    ident = plan["corroboration"]["market_identity"]
                    params.update({
                        "wkey": WOMEN_SPORT_KEY, "mid": MARKET_ID,
                        "m_source": ident["source"], "m_external_id": ident["external_id"],
                        "m_competition": ident["competition"], "m_scope": ident["competition_scope"],
                    })
                result = await session.execute(stmt, params)
                returned = [_decode_jsonb(dict(r)) for r in result.mappings().all()]
                if result.rowcount != 1 or len(returned) != 1:
                    raise Refused("fence_lost", {"rowcount": result.rowcount, "returned": len(returned)})
                got = {c: canon(returned[0].get(c)) for c in WRITTEN_COLUMNS}
                if returned[0].get("id") != EVENT_ID or got != to_written:
                    raise Refused("post_write_mismatch", {"returned": got})
                back = await _read_event(session, lock=False)
                bad = diff_compared(back or {}, to_written, fenced)
                if back is None or bad or canon(back.get(BANKED_ONLY_COLUMN)) != wps_locked:
                    raise Refused("in_transaction_readback_mismatch",
                                  {"columns": bad, "row_missing": back is None})
            except BaseException:
                await session.rollback()
                raise
            commit_attempted = True
            try:
                await session.commit()
                committed = True
            except Exception as exc:  # the outcome of COMMIT is unknown: read, never re-apply
                commit_error = f"{type(exc).__name__}: {str(exc)[:160]}"
    except Refused as exc:
        drift = 1 if exc.reason.startswith(("concurrent_drift", "identity_drift", "restore_after_drift",
                                            "fence_lost")) else 0
        return _result(mode, REFUSED, reason=exc.reason, detail=canon_safe(exc.detail),
                       drift=drift, **extra)
    except Exception as exc:
        if not commit_attempted:  # lock/statement timeout or any DB error before COMMIT
            return _result(mode, REFUSED, reason=_db_reason(exc),
                           detail=f"{type(exc).__name__}: {str(exc)[:160]}", **extra)
        if committed:  # closing the session failed after a good COMMIT; verify below
            pass
        else:
            commit_error = commit_error or f"{type(exc).__name__}: {str(exc)[:160]}"

    before_written = from_written
    if not committed:
        try:
            row, _ = await _verify_new_transaction(session_factory, to_written, fenced)
            state = classify(row, {**fenced, **before_written}, to_written)
        except Exception as exc:
            row, state = None, COMMIT_UNKNOWN
            commit_error += f"; readback failed: {type(exc).__name__}"
        return _result(mode, state, reason="commit_ambiguous", detail=commit_error,
                       written_rows=1 if state == APPLIED else 0, **extra)
    try:
        row, bad = await _verify_new_transaction(session_factory, to_written, fenced)
    except Exception as exc:
        return _result(mode, COMMIT_UNKNOWN, reason="post_commit_verify_unreadable",
                       detail=f"{type(exc).__name__}: {str(exc)[:160]}", **extra)
    if bad:
        state = classify(row, {**fenced, **before_written}, to_written)
        return _result(mode, state, reason="post_commit_verify_mismatch", detail=bad,
                       written_rows=1 if state == APPLIED else 0, **extra)
    return _result(mode, APPLIED, written_rows=1,
                   verified={c: canon(row.get(c)) for c in COMPARED_COLUMNS}, **extra)


def _write_receipt(base: str, suffix: str, result: dict) -> dict:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = f"{base}.{suffix}-receipt.{stamp}.json"
    body = {"event_id": EVENT_ID, "write_allowlist": {"table": "events", "id": EVENT_ID,
            "columns": list(WRITTEN_COLUMNS)}, "fenced_columns": list(FENCED_COLUMNS),
            "result": result}
    try:
        return write_artifact(path, RECEIPT_SCHEMA, body, "receipt")
    except Refused as exc:
        return {"path": path, "error": exc.reason}


async def run_apply(session_factory: SessionFactory, *, plan_path: str, plan_hash: str,
                    backup_out: str, lock_timeout_ms: int = LOCK_TIMEOUT_MS,
                    statement_timeout_ms: int = STATEMENT_TIMEOUT_MS,
                    clock: Callable[[], str] = _utcnow) -> dict:
    """Consume the reviewed plan; bank the backup; one CAS write. Never re-derives."""
    try:
        plan = load_artifact(plan_path, plan_hash, PLAN_SCHEMA, "plan")
        backup_body = {k: plan[k] for k in (
            "event_id", "write_allowlist", "fenced_columns", "pre_image", "post_image",
            "banked_unwritten", "corroboration", "team_compatibility")}
        backup_body.update({
            "plan": {"path": plan_path, "sha256": plan_hash.strip().lower(),
                     "content_address": plan["content_address"], "pins": plan["pins"]},
            "pins": {**tool_pin(), "packet": PACKET_PIN},
            "written_at": clock(),
        })
        backup = write_artifact(backup_out, BACKUP_SCHEMA, backup_body, "backup")
        load_artifact(backup_out, backup["sha256"], BACKUP_SCHEMA, "backup")
    except Refused as exc:
        return _result("apply", REFUSED, reason=exc.reason, detail=canon_safe(exc.detail))
    pre = plan["pre_image"]
    result = await _write_step(
        session_factory, mode="apply", plan=plan, stmt=_APPLY,
        from_written={c: pre[c] for c in WRITTEN_COLUMNS}, to_written=plan["post_image"],
        check_identity=True, lock_timeout_ms=lock_timeout_ms,
        statement_timeout_ms=statement_timeout_ms,
        extra={"plan": {"path": plan_path, "sha256": plan_hash.strip().lower()}, "backup": backup},
    )
    result["receipt"] = _write_receipt(backup_out, "apply", result)
    return result


async def run_restore(session_factory: SessionFactory, *, backup_path: str, backup_hash: str,
                      lock_timeout_ms: int = LOCK_TIMEOUT_MS,
                      statement_timeout_ms: int = STATEMENT_TIMEOUT_MS) -> dict:
    """The exact inverse of this tool's four-column write, from the banked backup."""
    try:
        backup = load_artifact(backup_path, backup_hash, BACKUP_SCHEMA, "backup")
    except Refused as exc:
        return _result("restore", REFUSED, reason=exc.reason, detail=canon_safe(exc.detail))
    pre = backup["pre_image"]
    result = await _write_step(
        session_factory, mode="restore", plan=backup, stmt=_RESTORE,
        from_written=backup["post_image"], to_written={c: pre[c] for c in WRITTEN_COLUMNS},
        check_identity=False, lock_timeout_ms=lock_timeout_ms,
        statement_timeout_ms=statement_timeout_ms,
        extra={"backup": {"path": backup_path, "sha256": backup_hash.strip().lower()}},
    )
    result["receipt"] = _write_receipt(backup_path, "restore", result)
    return result


def exit_code(result: dict) -> int:
    state = result.get("state")
    if state in (PLANNED, APPLIED):
        return EXIT_OK
    if state == NOT_APPLIED and result.get("mode") == "restore" and \
            result.get("reason") == "already_at_before_image":
        return EXIT_OK
    if state == COMMIT_UNKNOWN:
        return EXIT_COMMIT_UNKNOWN
    return EXIT_REFUSED


# --- CLI ----------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        epilog="Attended only. Exits: 0 ok, 1 refused, 2 usage, 3 commit unknown, 4 runtime error.",
    )
    ap.add_argument("--only", type=int, action="append", required=True,
                    help=f"must be exactly {EVENT_ID}, once")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--preflight", action="store_true", help="read-only; the default")
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--restore", action="store_true")
    ap.add_argument("--plan-out")
    ap.add_argument("--plan")
    ap.add_argument("--plan-hash")
    ap.add_argument("--backup-out")
    ap.add_argument("--backup")
    ap.add_argument("--backup-hash")
    return ap


_MODE_ARGS = {
    "preflight": ("plan_out",),
    "apply": ("plan", "plan_hash", "backup_out"),
    "restore": ("backup", "backup_hash"),
}


def parse(argv: list[str]) -> tuple[str, argparse.Namespace]:
    ap = build_parser()
    args = ap.parse_args(argv)
    if args.only != [EVENT_ID]:
        ap.error(f"--only must be exactly {EVENT_ID}, given once; got {args.only}")
    mode = "apply" if args.apply else "restore" if args.restore else "preflight"
    for name in ("plan_out", "plan", "plan_hash", "backup_out", "backup", "backup_hash"):
        wanted = name in _MODE_ARGS[mode]
        if wanted and not getattr(args, name):
            ap.error(f"--{mode} needs --{name.replace('_', '-')}")
        if not wanted and getattr(args, name):
            ap.error(f"--{name.replace('_', '-')} does not belong to --{mode}")
    return mode, args


def refuse_unless_target(env: dict) -> None:
    app = env.get("HEROKU_APP_NAME", "")
    if app not in PRODUCTION_APPS:
        raise Refused("target_app_refused", {"HEROKU_APP_NAME": app, "accepted": sorted(PRODUCTION_APPS)})


@asynccontextmanager
async def _engine_factory() -> AsyncIterator[SessionFactory]:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.services.database import DATABASE_URL, build_connect_args

    engine = create_async_engine(
        DATABASE_URL, poolclass=NullPool,
        connect_args=build_connect_args(
            DATABASE_URL, statement_timeout_ms=STATEMENT_TIMEOUT_MS, lock_timeout_ms=LOCK_TIMEOUT_MS,
        ),
    )
    try:
        yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    finally:
        await engine.dispose()


async def main(argv: list[str] | None = None, env: dict | None = None) -> int:
    mode, args = parse(sys.argv[1:] if argv is None else argv)
    try:
        refuse_unless_target(dict(os.environ) if env is None else env)
    except Refused as exc:
        print(json.dumps(_result(mode, REFUSED, reason=exc.reason, detail=exc.detail), indent=2))
        return EXIT_REFUSED
    try:
        async with _engine_factory() as factory:
            if mode == "preflight":
                out = await run_preflight(factory, plan_out=args.plan_out)
            elif mode == "apply":
                out = await run_apply(factory, plan_path=args.plan, plan_hash=args.plan_hash,
                                      backup_out=args.backup_out)
            else:
                out = await run_restore(factory, backup_path=args.backup, backup_hash=args.backup_hash)
    except Exception as exc:
        print(json.dumps({"schema": RECEIPT_SCHEMA, "mode": mode, "state": "RUNTIME_ERROR",
                          "detail": f"{type(exc).__name__}: {str(exc)[:200]}",
                          "counts": _counts()}, indent=2))
        return EXIT_RUNTIME
    print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    return exit_code(out)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
