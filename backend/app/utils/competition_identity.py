"""Competition identity — the standing competition an edition belongs to.

UX-P065, #1744 step 2a (epic #1741). Sibling of `majors_calendar.py`, reading the
same file through the same loader so there is one parser and one config.

## What was missing

Nothing on disk modelled *"an edition of"*. `entities` has no `parent_entity_id`,
no concept adapter config carries a parent slug, and the three mechanisms that
faked one disagree with each other:

1. **awards** keep a standing slug and parse a year suffix back off it —
   the inverse of a parent pointer;
2. **cycling aliases** hard-pin a standing name (`tour-de-france`) to ONE
   edition (`tour-de-france-2026`), so the standing name goes stale the day
   that edition ends;
3. **golf** deliberately uses year-less slugs, in a file that also writes
   `masters-2027` and `ryder-cup-2027`.

The visible cost: on 2026-08-12 `event:golf:the-masters` served April's settled
Masters — Rory McIlroy, correct and four months old — with nothing anywhere
saying the 2027 edition exists. A major is between editions ~51 weeks a year, so
that is the DEFAULT state of the page, not an edge case.

## ASSIGNED, NEVER INFERRED — standing doctrine, and the whole point of this module

A parent is read from the edition's `competition:` field. **Nothing here derives a
parent from the shape of a slug.** There is no year regex, no suffix strip, no
"if it ends in four digits" anywhere in this file, and `test_competition_identity`
asserts that by inspecting the source — because the doctrine is the deliverable,
and an implementation that quietly re-adds inference would still pass every
behavioural test written against today's twenty-one rows.

A wrong assignment is one wrong line, visible in a diff, fixable by anyone. A
wrong inference is a rule that is subtly wrong everywhere at once and belongs to
nobody — which is exactly how three mechanisms came to disagree without any of
them being *the* bug.

## Purity

No DB, no network, no Redis. YAML at call time, defensive-empty on every failure,
same contract as `majors_calendar.load_calendar`: a bad edit to the config can
never crash a beat or blank a page. Deliberately uncached, like its sibling —
the file is small, the callers are cache-fronted, and a module-level cache is a
second copy of a config with its own lifetime (gotcha #120).
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from app.utils.majors_calendar import _as_utc_date, load_calendar

_CALENDAR_PATH = Path(__file__).resolve().parent.parent / "config" / "majors_calendar.yaml"


def load_competitions(path: str | Path | None = None) -> list[dict]:
    """Load the standing-competition register. Returns [] on any failure."""
    p = Path(path) if path else _CALENDAR_PATH
    try:
        import yaml  # declared in requirements.txt (Queue #223)
    except Exception:  # pragma: no cover - dep guard
        return []
    try:
        with open(p, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
    except Exception:
        return []
    entries = raw.get("competitions") if isinstance(raw, dict) else None
    if not isinstance(entries, list):
        return []
    return [e for e in entries if isinstance(e, dict) and e.get("slug")]


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def resolve_competition(
    name_or_slug: str, path: str | Path | None = None
) -> dict[str, Any] | None:
    """The register row for a standing slug or one of its declared aliases.

    Exact match on the normalized token only. No fuzzy matching: the tennis
    adapter's token-tolerant resolution is why `event:tennis:us-open-2026`
    served "Cincinnati Open" in production, and a register that guesses is
    worse than one that says it does not know.
    """
    token = _norm(name_or_slug)
    if not token:
        return None
    rows = load_competitions(path)
    for row in rows:
        if _norm(row.get("slug")) == token:
            return row
    for row in rows:
        aliases = row.get("aliases") or []
        if isinstance(aliases, list) and any(_norm(a) == token for a in aliases):
            return row
    return None


def editions_of(slug: str, path: str | Path | None = None) -> list[dict[str, Any]]:
    """Every calendar edition ASSIGNED to this competition, oldest first.

    Rows with an unparseable start sort last rather than being dropped — an
    edition with a bad date is still an edition, and hiding it would make the
    config error invisible at exactly the surface that should show it.
    """
    token = _norm(slug)
    if not token:
        return []
    rows = [e for e in load_calendar(path) if _norm(e.get("competition")) == token]
    return sorted(rows, key=lambda e: (_as_utc_date(e.get("start")) or date.max))


def competition_of(
    concept_key: str, path: str | Path | None = None
) -> dict[str, Any] | None:
    """The standing competition a concept key belongs to, or None.

    Matches an edition's own `concept_key` first, then a competition's
    `standing_concept_key` — the year-less key some competitions already resolve
    at today. Both are declared values; neither is derived from the key's text.
    """
    key = _norm(concept_key)
    if not key:
        return None
    for entry in load_calendar(path):
        if _norm(entry.get("concept_key")) == key:
            return resolve_competition(str(entry.get("competition") or ""), path)
    for row in load_competitions(path):
        if _norm(row.get("standing_concept_key")) == key:
            return row
    return None


def _today(now: datetime | None) -> date:
    if now is None:
        now = datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc).date()


def next_edition(
    slug: str, now: datetime | None = None, path: str | Path | None = None
) -> dict[str, Any] | None:
    """The soonest edition that has not finished yet (an in-progress one counts).

    Inclusive of the end DAY, matching `marquee_pin_state`: an edition finishing
    today is still the current edition, not a past one.
    """
    day = _today(now)
    for entry in editions_of(slug, path):
        end = _as_utc_date(entry.get("end")) or _as_utc_date(entry.get("start"))
        if end is not None and end >= day:
            return entry
    return None


def last_edition(
    slug: str, now: datetime | None = None, path: str | Path | None = None
) -> dict[str, Any] | None:
    """The most recent edition that has already finished, or None.

    Usually None today: the calendar is a FORWARD-looking horizon file, so a
    competition's past editions are mostly absent from it. That is honest — the
    page already renders the settled edition it is on — and it is why the strip
    leads with "returns", not with a history it does not have.
    """
    day = _today(now)
    finished = [
        e
        for e in editions_of(slug, path)
        if (_as_utc_date(e.get("end")) or _as_utc_date(e.get("start")) or date.max) < day
    ]
    return finished[-1] if finished else None


def _edition_block(entry: dict[str, Any] | None) -> dict[str, Any] | None:
    if not entry:
        return None
    start = _as_utc_date(entry.get("start"))
    end = _as_utc_date(entry.get("end"))
    return {
        "name": entry.get("name"),
        "slug": entry.get("slug"),
        "concept_key": entry.get("concept_key"),
        "start": start.isoformat() if start else None,
        "end": end.isoformat() if end else None,
    }


def competition_block(
    concept_key: str, now: datetime | None = None, path: str | Path | None = None
) -> dict[str, Any] | None:
    """The `competition` envelope block for a concept key, or None when unmapped.

    ⚠️ ABSOLUTE DATES ONLY — never a countdown integer. This block is stamped
    into an envelope that is mirrored for up to 24h and served stale on a miss,
    so a baked "240 days" is wrong for most of its life. The client owns the
    countdown because only the client knows what time it is when it renders.
    """
    row = competition_of(concept_key, path)
    if not row:
        return None
    slug = str(row.get("slug") or "")
    nxt = _edition_block(next_edition(slug, now, path))
    lst = _edition_block(last_edition(slug, now, path))
    if nxt is None and lst is None:
        # A competition we can name but have no edition for tells the reader
        # nothing they cannot already see. Honest-empty (ruling 027).
        return None
    return {
        "slug": slug,
        "name": row.get("name"),
        "domain": row.get("domain"),
        "next_edition": nxt,
        "last_edition": lst,
    }
