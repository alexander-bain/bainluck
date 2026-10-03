"""#10305 D2 — an ESPN-anchored game ESPN has named stops printing "TBD".

THE SHIP: Aces at Golden State (row 15322561, ESPN 401918296) was minted before
the matchup was known, so both sides read ``TBD`` with no team link. The row
already carries ESPN's own game id, and ESPN's scheduled board names both
clubs — but nothing on the scheduled pass ever writes a NAME onto a row:
``apply_espn_respelling`` only respells a side that already names a club, and
``upsert_team("TBD", …)`` resolves nothing and (correctly) refuses to mint.

WHAT THIS DOES
--------------

On the scheduled pass's OWN-ID arm only (the row's stored ``espn_id`` is the
board game's id — ruling 048's anchor, never a name match), a row whose two
sides are both placeholders, unbound and untouched takes ESPN's two clubs, as
the team rows that already carry ESPN's team ids. It never mints a team, never
reads orientation from the parser's ``else`` arm, and never overwrites a side
that names anybody:

* **Orientation comes only from ESPN's literal ``homeAway``** per competitor
  (``ESPNEvent.competitor_sides``). Missing, null, unrecognised, duplicated or
  not exactly two sides is a plain refusal. A payload that disagrees with
  itself, or with a side that is already occupied, is routed to authority.
* **Each side resolves to EXACTLY ONE team row** in the event's sport carrying
  ESPN's team id, whose identity corresponds to ESPN's competitor. The written
  name is that row's own name, so #1918's ``row_name ↔ FK`` holds by
  construction.
* **The pass's name-keyed arms do not re-resolve a filled row.** The helper
  hands back the two rows it wrote and the seam uses them in place of
  ``apply_espn_respelling``/``upsert_team``: the pass's team cache is keyed by
  ``(name, sport)``, so a second same-name row can stand in it for the anchored
  one and be bound under ESPN's id — a FK the receipt does not hold.
* **One Core UPDATE writes all seven columns** with every current-state fence
  in its WHERE (gotcha #4: never an ORM assignment to JSONB), and the ORM is
  synced only from what the statement RETURNED.
* **The receipt is the fill tag** — every prior and every written value,
  canonically encoded — so ``scripts/restore_espn_participant_fill.py`` can put
  the row back byte-for-byte with nothing defaulted.

THE DURABLE REFUSAL IS CODE, NOT A TAG
--------------------------------------

Every taxonomy writer is an ORM read-modify-write of ``event_tags`` from a value
it loaded earlier (``get_task_session`` is ``expire_on_commit=False``; the LLM
enricher commits per chunk), so a refusal kept only in ``event_tags`` can be
erased by a stale pre-fill value — which is, by definition, the eligible state.
:data:`RESTORED_FILL_EVENT_IDS` is the refusal no automated writer can touch:
the verdict checks it FIRST, and the restore tool refuses to run until the id
is in it in the code it runs from. Adding or removing an id is a reviewed PR.
The restored marker stays as a record the pass also honours, but nothing
depends on it.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Sequence
from urllib.parse import quote, unquote

from sqlalchemy import text
from sqlalchemy.orm.attributes import set_committed_value

from app.utils.authority_agreement import is_placeholder
from app.utils.team_binding_invariant import binding_is_sound

logger = logging.getLogger(__name__)

#: The receipt. ``provenance:`` so the taxonomy REPLACE carries it (#8422).
FILL_TAG_PREFIX = "provenance:espn-participant-fill:"
#: What restore swaps the receipt for, at the same index, carrying it verbatim.
RESTORED_TAG_PREFIX = "provenance:espn-participant-fill-restored:"

#: Event ids whose fill was undone. The verdict refuses them FIRST, whatever the
#: row's tags say, and the restore tool refuses to run for an id not listed here
#: in the slug it runs from. Ships empty; every change is a reviewed lane1 PR.
RESTORED_FILL_EVENT_IDS: frozenset[int] = frozenset()

#: The seven columns the fill writes — exactly the ones the UPDATE returns and
#: the ORM is synced from.
FILL_COLUMNS = (
    "home_team_name",
    "away_team_name",
    "home_team_id",
    "away_team_id",
    "home_team_normalized",
    "away_team_normalized",
    "event_tags",
)

FILL = "fill"
REFUSE = "refuse"
CONFLICT = "conflict"

_TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_PCT_ESCAPE_RE = re.compile(r"%(?![0-9A-Fa-f]{2})")
_RECEIPT_KEYS = {"after", "filled_at", "prior"}
_AFTER_KEYS = {"away_name", "away_tid", "home_name", "home_tid"}
_PRIOR_KEYS = {"away_name", "away_norm", "home_name", "home_norm"}


class FillPostWriteMismatch(RuntimeError):
    """The UPDATE returned something other than what it was told to write."""


class ReceiptInvalid(ValueError):
    """A fill tag that is not a complete, canonical receipt."""

    def __init__(self, reason: str):
        super().__init__(f"receipt_invalid:{reason}")
        self.reason = f"receipt_invalid:{reason}"


@dataclass(frozen=True)
class FillVerdict:
    action: str
    reason: str
    home_team: Any = None
    away_team: Any = None
    home_espn_tid: Optional[str] = None
    away_espn_tid: Optional[str] = None
    #: Authority rule 2's summary-vs-scoreboard arm cannot run here — the
    #: scheduled pass holds only the board. Recorded, never read as missing.
    summary_arm: str = "not_exercised"


@dataclass(frozen=True)
class FillReceipt:
    espn_event_id: str
    away_espn_tid: str
    home_espn_tid: str
    prior_home_name: str
    prior_away_name: str
    prior_home_norm: Optional[str]
    prior_away_norm: Optional[str]
    after_home_name: str
    after_away_name: str
    after_home_tid: int
    after_away_tid: int
    filled_at: str


def build_team_index(teams: Sequence[Any]) -> dict[str, list[Any]]:
    """``str(espn_id) -> [team rows]`` for rows that carry an ESPN id."""
    index: dict[str, list[Any]] = {}
    for team in teams:
        espn_id = getattr(team, "espn_id", None)
        if espn_id is None or str(espn_id) == "":
            continue
        index.setdefault(str(espn_id), []).append(team)
    return index


def _refuse(reason: str, **kw) -> FillVerdict:
    return FillVerdict(action=REFUSE, reason=reason, **kw)


def _conflict(reason: str, **kw) -> FillVerdict:
    return FillVerdict(action=CONFLICT, reason=reason, **kw)


def _tag_ids(tag: str, prefix: str) -> Optional[tuple[str, str]]:
    """The ``(away, home)`` ESPN team ids a fill tag or restored marker names."""
    parts = tag[len(prefix):].split(":")
    if len(parts) < 3 or not parts[1].startswith("away=") or not parts[2].startswith("home="):
        return None
    return parts[1][len("away="):], parts[2][len("home="):]


def _payload_ids(sides) -> Optional[tuple[str, str]]:
    """``(away, home)`` from the literal sides, or None unless exactly one of each."""
    if not isinstance(sides, tuple) or len(sides) != 2:
        return None
    by_side = {}
    for side in sides:
        if not isinstance(side, tuple) or len(side) != 2:
            return None
        by_side.setdefault(side[1], []).append(side[0])
    if set(by_side) != {"away", "home"} or any(len(v) != 1 for v in by_side.values()):
        return None
    return by_side["away"][0], by_side["home"][0]


def _empty_alt(value) -> bool:
    return value is None or value == []


def _team_name_fields(espn_team) -> list:
    return [getattr(espn_team, f, None) for f in ("name", "display_name", "short_name")]


def participant_fill_verdict(event, ee, team_index: Mapping[str, Sequence[Any]]) -> FillVerdict:
    """Fill, refuse or route this row. Pure: reads the loaded row and the payload."""
    if event.id in RESTORED_FILL_EVENT_IDS:
        return _refuse("restore_denylisted")

    from app.utils import espn_helpers as _eh

    if not event.espn_id or ee.espn_id != event.espn_id:
        return _refuse("not_id_anchored")
    if event.status != "scheduled":
        return _refuse("not_scheduled")

    sides = getattr(ee, "competitor_sides", ())
    payload_ids = _payload_ids(sides)

    for tag in event.event_tags or []:
        if not isinstance(tag, str):
            continue
        for prefix, plain in (
            (FILL_TAG_PREFIX, "prior_fill_present"),
            (RESTORED_TAG_PREFIX, "restored_fill_present"),
        ):
            if tag.startswith(prefix):
                ids = _tag_ids(tag, prefix)
                if ids is not None and payload_ids is not None and ids != payload_ids:
                    return _conflict(f"{plain}_other_teams")
                return _refuse(plain)

    home_name, away_name = event.home_team_name, event.away_team_name
    both_placeholder = is_placeholder(home_name) and is_placeholder(away_name)
    home_fk, away_fk = event.home_team_id, event.away_team_id
    if not both_placeholder or home_fk is not None or away_fk is not None:
        orientation = _eh.espn_orientation_verdict(event, ee)
        if orientation == _eh.ESPN_ORIENTATION_SWAPPED:
            return _conflict("occupied_side_swapped")
        if (
            orientation == _eh.ESPN_ORIENTATION_UNRESOLVED
            and not is_placeholder(home_name)
            and not is_placeholder(away_name)
            and home_name
            and away_name
        ):
            return _conflict("occupied_side_unresolved")
        if not both_placeholder:
            return _refuse("not_both_placeholder")
        teams_by_pk = {
            getattr(t, "id", None): t for rows in team_index.values() for t in rows
        }
        for fk, ours, theirs in (
            (home_fk, ee.home_team, ee.away_team),
            (away_fk, ee.away_team, ee.home_team),
        ):
            team = teams_by_pk.get(fk) if fk is not None else None
            if (
                team is not None
                and theirs is not None
                and _eh.espn_identity_corresponds(
                    team.name, getattr(team, "alternate_names", None), theirs
                )
                and not (
                    ours is not None
                    and _eh.espn_identity_corresponds(
                        team.name, getattr(team, "alternate_names", None), ours
                    )
                )
            ):
                return _conflict("fk_opposite_side")
        return _refuse("fk_occupied")

    for norm in (event.home_team_normalized, event.away_team_normalized):
        if norm is not None and not is_placeholder(norm):
            return _refuse("stale_normalized")
    if not _empty_alt(event.home_team_alt_names) or not _empty_alt(event.away_team_alt_names):
        return _refuse("alt_names_present")

    if not sides:
        return _refuse("no_side_evidence")
    if not isinstance(sides, tuple) or len(sides) != 2:
        return _refuse("side_count")
    values = [s[1] if isinstance(s, tuple) and len(s) == 2 else None for s in sides]
    if any(v not in ("home", "away") for v in values):
        return _refuse("side_invalid")
    if values[0] == values[1]:
        return _refuse("side_duplicate")
    by_side = {s[1]: s[0] for s in sides}
    home_tid, away_tid = by_side["home"], by_side["away"]
    if not isinstance(home_tid, str) or not isinstance(away_tid, str) or not home_tid or not away_tid:
        return _refuse("side_placeholder")
    if home_tid == away_tid:
        return _refuse("side_duplicate_team")
    if ee.home_team is None or ee.away_team is None:
        return _refuse("parsed_slot_missing")
    if any(is_placeholder(n) for t in (ee.home_team, ee.away_team) for n in _team_name_fields(t)):
        return _refuse("side_placeholder")
    if str(ee.home_team.espn_id) != home_tid or str(ee.away_team.espn_id) != away_tid:
        return _conflict("payload_self_disagreement")

    resolved = {}
    for side, tid, competitor in (
        ("home", home_tid, ee.home_team),
        ("away", away_tid, ee.away_team),
    ):
        rows = [t for t in team_index.get(tid, ()) if t.sport_id == event.sport_id]
        if not rows:
            return _refuse("no_team_row")
        if len(rows) > 1:
            return _refuse("ambiguous_team_row")
        team = rows[0]
        if not team.name or is_placeholder(team.name):
            return _refuse("team_name_placeholder")
        if not _eh.espn_identity_corresponds(
            team.name, getattr(team, "alternate_names", None), competitor
        ):
            return _refuse("identity_mismatch")
        if not binding_is_sound(team.name, team.name, team.sport_id, event.sport_id):
            return _refuse("binding_unsound")
        resolved[side] = team
    if resolved["home"].id == resolved["away"].id:
        return _refuse("side_duplicate_team")

    return FillVerdict(
        action=FILL,
        reason="fill",
        home_team=resolved["home"],
        away_team=resolved["away"],
        home_espn_tid=home_tid,
        away_espn_tid=away_tid,
    )


# ── Receipt ──────────────────────────────────────────────────────────────────


def _canonical_pct(receipt: dict) -> str:
    return quote(
        json.dumps(receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
        safe="",
    )


def encode_fill_tag(espn_event_id: str, away_espn_tid: str, home_espn_tid: str, receipt: dict) -> str:
    """The fill tag: oriented ids in r1's positions, then the canonical receipt."""
    for value in (espn_event_id, away_espn_tid, home_espn_tid):
        if not isinstance(value, str) or not value or ":" in value:
            raise ValueError(f"unencodable id {value!r}")
    return (
        f"{FILL_TAG_PREFIX}{espn_event_id}:away={away_espn_tid}:home={home_espn_tid}"
        f":r1={_canonical_pct(receipt)}"
    )


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def parse_fill_tag(tag) -> FillReceipt:
    """Strict, default-free receipt parse. Any failure raises :class:`ReceiptInvalid`."""
    if not isinstance(tag, str):
        raise ReceiptInvalid("not_a_string")
    if not tag.startswith(FILL_TAG_PREFIX):
        raise ReceiptInvalid("prefix")
    parts = tag[len(FILL_TAG_PREFIX):].split(":")
    if len(parts) != 4:
        raise ReceiptInvalid("r1" if len(parts) == 3 else "shape")
    espn_event_id, away_part, home_part, r1_part = parts
    if not espn_event_id:
        raise ReceiptInvalid("espn_event_id")
    if not away_part.startswith("away=") or not away_part[len("away="):]:
        raise ReceiptInvalid("away")
    if not home_part.startswith("home=") or not home_part[len("home="):]:
        raise ReceiptInvalid("home")
    away_tid, home_tid = away_part[len("away="):], home_part[len("home="):]
    if away_tid == home_tid:
        raise ReceiptInvalid("same_ids")
    if not r1_part.startswith("r1="):
        raise ReceiptInvalid("r1")
    pct = r1_part[len("r1="):]
    if not pct:
        raise ReceiptInvalid("r1")
    if _PCT_ESCAPE_RE.search(pct):
        raise ReceiptInvalid("percent")
    try:
        decoded = unquote(pct, errors="strict")
    except UnicodeDecodeError:
        raise ReceiptInvalid("percent")
    try:
        receipt = json.loads(decoded)
    except (ValueError, RecursionError):
        raise ReceiptInvalid("json")
    if not isinstance(receipt, dict) or set(receipt) != _RECEIPT_KEYS:
        raise ReceiptInvalid("keys")
    after, prior, filled_at = receipt["after"], receipt["prior"], receipt["filled_at"]
    if not isinstance(after, dict) or set(after) != _AFTER_KEYS:
        raise ReceiptInvalid("keys")
    if not isinstance(prior, dict) or set(prior) != _PRIOR_KEYS:
        raise ReceiptInvalid("keys")
    if not (
        isinstance(after["home_name"], str)
        and isinstance(after["away_name"], str)
        and _is_int(after["home_tid"])
        and _is_int(after["away_tid"])
        and isinstance(prior["home_name"], str)
        and isinstance(prior["away_name"], str)
        and (prior["home_norm"] is None or isinstance(prior["home_norm"], str))
        and (prior["away_norm"] is None or isinstance(prior["away_norm"], str))
        and isinstance(filled_at, str)
    ):
        raise ReceiptInvalid("types")
    if not _TS_RE.match(filled_at):
        raise ReceiptInvalid("filled_at")
    try:
        datetime.strptime(filled_at, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise ReceiptInvalid("filled_at")
    if not (is_placeholder(prior["home_name"]) and is_placeholder(prior["away_name"])):
        raise ReceiptInvalid("prior_name")
    for norm in (prior["home_norm"], prior["away_norm"]):
        if norm is not None and not is_placeholder(norm):
            raise ReceiptInvalid("prior_norm")
    for name in (after["home_name"], after["away_name"]):
        if not name or is_placeholder(name):
            raise ReceiptInvalid("after_name")
    if after["home_tid"] == after["away_tid"]:
        raise ReceiptInvalid("after_tids")
    if _canonical_pct(receipt) != pct:
        raise ReceiptInvalid("non_canonical")
    return FillReceipt(
        espn_event_id=espn_event_id,
        away_espn_tid=away_tid,
        home_espn_tid=home_tid,
        prior_home_name=prior["home_name"],
        prior_away_name=prior["away_name"],
        prior_home_norm=prior["home_norm"],
        prior_away_norm=prior["away_norm"],
        after_home_name=after["home_name"],
        after_away_name=after["away_name"],
        after_home_tid=after["home_tid"],
        after_away_tid=after["away_tid"],
        filled_at=filled_at,
    )


# ── The write ────────────────────────────────────────────────────────────────

#: Every current-state fence is in the WHERE, including the team rows and their
#: uniqueness, re-judged at write time (a same-id row minted earlier in the same
#: pass is visible here after the flush and fails the fence). Prefix tests are
#: bound parameters, never an inline ``LIKE`` (gotcha #45).
FILL_SQL = """
UPDATE events SET
  home_team_name = :home_name, away_team_name = :away_name,
  home_team_id = :home_tid, away_team_id = :away_tid,
  home_team_normalized = NULL, away_team_normalized = NULL,
  event_tags = COALESCE(event_tags, '[]'::jsonb) || CAST(:tag_array AS jsonb)
WHERE id = :eid AND espn_id = :espn_id AND status = 'scheduled'
  AND home_team_name = :prior_home_name AND away_team_name = :prior_away_name
  AND home_team_id IS NULL AND away_team_id IS NULL
  AND home_team_normalized IS NOT DISTINCT FROM CAST(:prior_home_norm AS varchar)
  AND away_team_normalized IS NOT DISTINCT FROM CAST(:prior_away_norm AS varchar)
  AND COALESCE(home_team_alt_names, '[]'::jsonb) = '[]'::jsonb
  AND COALESCE(away_team_alt_names, '[]'::jsonb) = '[]'::jsonb
  AND NOT EXISTS (SELECT 1 FROM jsonb_array_elements_text(COALESCE(event_tags, '[]'::jsonb)) t
                  WHERE left(t, length(:fill_prefix)) = :fill_prefix
                     OR left(t, length(:restored_prefix)) = :restored_prefix)
  AND EXISTS (SELECT 1 FROM teams h WHERE h.id = :home_tid AND h.sport_id = events.sport_id
              AND h.espn_id = :home_espn_tid AND h.name = :home_name)
  AND EXISTS (SELECT 1 FROM teams a WHERE a.id = :away_tid AND a.sport_id = events.sport_id
              AND a.espn_id = :away_espn_tid AND a.name = :away_name)
  AND NOT EXISTS (SELECT 1 FROM teams o WHERE o.sport_id = events.sport_id
                  AND o.espn_id = :home_espn_tid AND o.id <> :home_tid)
  AND NOT EXISTS (SELECT 1 FROM teams o WHERE o.sport_id = events.sport_id
                  AND o.espn_id = :away_espn_tid AND o.id <> :away_tid)
RETURNING id, home_team_name, away_team_name, home_team_id, away_team_id,
          home_team_normalized, away_team_normalized, event_tags
"""


def _utcnow() -> datetime:
    """The helper's clock — the receipt's ``filled_at`` (audit only; nothing reads it)."""
    return datetime.now(timezone.utc)


def _count(stats: dict, key: str) -> None:
    bucket = stats.setdefault("participant_fill", {})
    bucket[key] = bucket.get(key, 0) + 1


def _self_check(returned: Mapping[str, Any], params: Mapping[str, Any], tag: str) -> None:
    for col, key in (
        ("home_team_name", "home_name"),
        ("away_team_name", "away_name"),
        ("home_team_id", "home_tid"),
        ("away_team_id", "away_tid"),
    ):
        if returned[col] != params[key]:
            raise FillPostWriteMismatch(f"{col} returned {returned[col]!r}, wrote {params[key]!r}")
    if returned["home_team_normalized"] is not None or returned["away_team_normalized"] is not None:
        raise FillPostWriteMismatch("normalized returned non-NULL")
    tags = returned["event_tags"]
    if not isinstance(tags, list) or tags.count(tag) != 1:
        raise FillPostWriteMismatch("fill tag not returned exactly once")
    if any(isinstance(t, str) and t.startswith(RESTORED_TAG_PREFIX) for t in tags):
        raise FillPostWriteMismatch("restored marker returned")


async def maybe_fill_participants(session, event, ee, team_index, stats) -> Optional[tuple]:
    """Fill one id-anchored placeholder row, or leave it exactly as it is.

    Returns the ``(home, away)`` team rows the fill wrote — exactly the two its
    receipt records — or ``None`` when nothing was written.

    The exception contract, in order (plan §3.6):

    1. The verdict and receipt are pure; an exception there is counted
       ``verdict_error`` and absorbed — nothing has been written.
    2. Not a fill: count the reason and return. No flush, no savepoint.
    3. ``session.flush()`` runs OUTSIDE any try, so a sibling's pending failure
       propagates to the sport ``_step_savepoint`` exactly as today's next
       autoflush would. The fill catch never sees it.
    4. The UPDATE, its self-check and the ORM sync run inside a SAVEPOINT; any
       exception there is rolled back to it before it leaves the block.
    5. Then the seven attributes are re-read from the database, OUTSIDE any try
       (a savepoint rollback does not expire ``set_committed_value`` writes, so
       the ORM would otherwise keep claiming the fill). If that refresh fails it
       propagates — today's semantics: the sport step rolls back.
    """
    try:
        verdict = participant_fill_verdict(event, ee, team_index)
        if verdict.action == FILL:
            home, away = verdict.home_team, verdict.away_team
            receipt = {
                "after": {
                    "away_name": away.name,
                    "away_tid": away.id,
                    "home_name": home.name,
                    "home_tid": home.id,
                },
                "filled_at": _utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                "prior": {
                    "away_name": event.away_team_name,
                    "away_norm": event.away_team_normalized,
                    "home_name": event.home_team_name,
                    "home_norm": event.home_team_normalized,
                },
            }
            tag = encode_fill_tag(
                str(event.espn_id), verdict.away_espn_tid, verdict.home_espn_tid, receipt
            )
            params = {
                "home_name": home.name,
                "away_name": away.name,
                "home_tid": home.id,
                "away_tid": away.id,
                "tag_array": json.dumps([tag]),
                "eid": event.id,
                "espn_id": event.espn_id,
                "prior_home_name": event.home_team_name,
                "prior_away_name": event.away_team_name,
                "prior_home_norm": event.home_team_normalized,
                "prior_away_norm": event.away_team_normalized,
                "fill_prefix": FILL_TAG_PREFIX,
                "restored_prefix": RESTORED_TAG_PREFIX,
                "home_espn_tid": verdict.home_espn_tid,
                "away_espn_tid": verdict.away_espn_tid,
            }
    except Exception as exc:  # noqa: BLE001 — nothing written; plan §3.6 step 1
        _count(stats, "verdict_error")
        logger.warning(
            "participant fill: verdict failed for event %s: %r",
            getattr(event, "id", None), exc,
        )
        return None

    if verdict.action == CONFLICT:
        _count(stats, "orientation_conflict")
        logger.warning(
            "participant fill: route=authority event=%s espn_id=%s reason=%s",
            event.id, event.espn_id, verdict.reason,
        )
        return None
    if verdict.action != FILL:
        _count(stats, f"refused_{verdict.reason}")
        return None

    await session.flush()

    fence_lost = False
    try:
        async with session.begin_nested():
            result = await session.execute(text(FILL_SQL), params)
            rows = result.mappings().all()
            if not rows:
                fence_lost = True
            else:
                if len(rows) > 1:
                    raise FillPostWriteMismatch(f"{len(rows)} rows updated for one id")
                returned = rows[0]
                _self_check(returned, params, tag)
                for col in FILL_COLUMNS:
                    value = returned[col]
                    if col == "event_tags":
                        value = list(value)
                    set_committed_value(event, col, value)
    except Exception as exc:  # noqa: BLE001 — rolled back to the savepoint above
        await session.refresh(event, attribute_names=list(FILL_COLUMNS))
        _count(stats, "post_write_rolled_back")
        logger.warning(
            "participant fill: rolled back for event %s after the write: %r",
            event.id, exc,
        )
        return None

    if fence_lost:
        _count(stats, "fence_lost")
        return None

    _count(stats, "filled")
    logger.info("participant fill: event=%s tag=%s", event.id, tag)
    return verdict.home_team, verdict.away_team

