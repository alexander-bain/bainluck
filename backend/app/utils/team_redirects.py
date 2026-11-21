"""#13229 / 314-B: retired-team redirects and same-league team creation guards.

Two jobs live here so every route and every ``Team(...)`` creation site shares
one consistent, ambiguity-safe contract:

1. **Read/write redirects** (``resolve_retired_team_id``,
   ``resolve_retired_team_by_identifier``, ``resolve_retired_team_ids_batch``):
   When a duplicate team row is folded into its canonical club, a row in
   ``retired_team_redirects`` records ``retired_team_id``, ``retired_slug``,
   ``retired_name``, ``sport_id``, and ``canonical_team_id``. Team pages
   (``/api/teams/{identifier}``) and favorites (``POST/DELETE /api/me/favorites``)
   follow the redirect transparently instead of 404ing on cached 1.0.8 IDs or
   old bookmarks.

2. **Anti-recreation guards** (``find_existing_team_in_sport``,
   ``unambiguous_short_spelling_match``, ``distinguishing_tokens_agree``):
   Called before ``Team(...)`` at all three creation sites
   (``espn_helpers.upsert_team``, ``tasks/sports.py``, ``routes/user.py``).
   Checks ``retired_team_redirects``, ``team_identity_mapping``, same-league
   ``espn_id``, ``Team.alternate_names``, and unambiguous same-league short
   spellings (e.g. ``"Tottenham"`` -> ``"Tottenham Hotspur"``, ``"Ottawa"`` ->
   ``"Ottawa Senators"``) while refusing reserve/women's collapses (#13202,
   286: B), ambiguous shared cities/mascots, and school-modifier traps.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterable, Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.name_normalization import shared_token_rivals

_MAX_REDIRECT_HOPS = 5

# #13202: trailing squad qualifiers that distinguish a reserve, B, or women's
# side from a club's first team. Must match on both sides before collapsing.
_RESERVE_OR_WOMENS_SUFFIXES = frozenset({
    "ii",
    "iii",
    "b",
    "c",
    "women",
    "womens",
    "reserves",
    "reserve",
})

# Gender markers anywhere in the name (e.g. "Massachusetts Minutewomen" vs
# "Massachusetts Minutemen", "Lady Vols" vs "Vols").
_WOMENS_ANYWHERE_TOKENS = frozenset({
    "women",
    "womens",
    "ladies",
    "lady",
    "minutewomen",
})

# Second words that turn a single-word state/school name into a DIFFERENT
# institution (e.g. "Georgia" != "Georgia Tech", "Michigan" != "Michigan State",
# "Louisiana" != "Louisiana Tech", "Texas" != "Texas A&M").
_SCHOOL_MODIFIER_WORDS = frozenset({
    "state",
    "tech",
    "am",
    "southern",
    "northern",
    "eastern",
    "western",
    "central",
    "atlantic",
    "international",
    "poly",
    "christian",
    "baptist",
    "methodist",
    "college",
    "university",
    "st",
    "saint",
    "valley",
    "coast",
    "bay",
    "beach",
    "metro",
})


def _as_int(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _plain_tokens(name: str | None) -> list[str]:
    if not name or not isinstance(name, str):
        return []
    folded = unicodedata.normalize("NFKD", name)
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    folded = folded.lower().replace("'", "").replace("\u2019", "")
    return re.findall(r"[a-z0-9]+", folded)


def _norm_text(name: str | None) -> str:
    return " ".join(_plain_tokens(name))


def distinguishing_tokens(
    name: str | None,
) -> tuple[tuple[str, ...], tuple[str, ...], bool]:
    """Numeric, trailing reserve/women's, and gender markers that must agree."""
    raw = name or ""
    numbers = tuple(re.findall(r"\d+", raw))
    tokens = _plain_tokens(raw)
    has_womens = any(tok in _WOMENS_ANYWHERE_TOKENS for tok in tokens)
    trailing: list[str] = []
    scan = list(tokens)
    while scan and scan[-1] in _RESERVE_OR_WOMENS_SUFFIXES:
        trailing.append(scan.pop())
    trailing.reverse()
    return (numbers, tuple(trailing), has_womens)


def distinguishing_tokens_agree(name_a: str | None, name_b: str | None) -> bool:
    """True only when neither name adds/drops a reserve, numeric, or women's marker."""
    return distinguishing_tokens(name_a) == distinguishing_tokens(name_b)


def _unique_teams(teams: Iterable[Any]) -> list[Any]:
    seen: set[Any] = set()
    out: list[Any] = []
    for team in teams:
        tid = getattr(team, "id", None)
        key = ("id", tid) if _as_int(tid) is not None else ("obj", id(team))
        if key not in seen:
            seen.add(key)
            out.append(team)
    return out


def unambiguous_short_spelling_match(
    candidate_name: str,
    existing_teams: Sequence[Any],
) -> Any | None:
    """Return the sole matching team in ``existing_teams``, or ``None``.

    Checks two fail-closed tiers within one league:
      1. Exact normalized match on ``Team.name`` or ``Team.alternate_names``
         (sole match with agreeing distinguishing tokens).
      2. Strict word-boundary prefix match where ``candidate_name`` is a short
         spelling of ``Team.name`` (e.g. ``"Tottenham"`` -> ``"Tottenham Hotspur"``,
         ``"Ottawa"`` -> ``"Ottawa Senators"``), requiring agreeing distinguishing
         tokens, no school-modifier trap, no shared-token rival conflict, and a
         single unambiguous match across the league.
    """
    cand_tokens = _plain_tokens(candidate_name)
    if not cand_tokens:
        return None
    cand_norm = " ".join(cand_tokens)
    pool = _unique_teams(existing_teams)
    if not pool:
        return None

    # Tier 1: exact normalized name or alternate_names match (sole match only).
    exact_hits: list[Any] = []
    for team in pool:
        t_name = getattr(team, "name", None)
        if not t_name or not distinguishing_tokens_agree(candidate_name, t_name):
            continue
        labels = [t_name]
        alts = getattr(team, "alternate_names", None)
        if isinstance(alts, list):
            labels.extend(a for a in alts if isinstance(a, str))
        if any(_norm_text(lbl) == cand_norm for lbl in labels):
            exact_hits.append(team)
    if len(exact_hits) == 1:
        return exact_hits[0]
    if len(exact_hits) > 1:
        return None

    # Tier 2: unambiguous word-boundary prefix match (short spelling -> full club name).
    if len(cand_tokens) == 1 and len(cand_tokens[0]) < 4:
        return None

    prefix_candidates: list[tuple[Any, str, list[str]]] = []
    for team in pool:
        t_name = getattr(team, "name", None)
        if not t_name or not distinguishing_tokens_agree(candidate_name, t_name):
            continue
        ex_tokens = _plain_tokens(t_name)
        if len(ex_tokens) <= len(cand_tokens):
            continue
        if ex_tokens[: len(cand_tokens)] != cand_tokens:
            continue
        prefix_candidates.append((team, t_name, ex_tokens))

    # Ambiguity check BEFORE school-word / rival filtering: a row set aside by
    # the school-word rule (e.g. "Paris Saint-Germain" alongside "Paris FC" for
    # "Paris") must still count as a second match rather than disappearing and
    # turning the remaining club into a false sole match.
    if len(prefix_candidates) != 1:
        return None

    team, t_name, ex_tokens = prefix_candidates[0]
    # School-modifier guard at ANY incoming name length (not only 1-word names),
    # so "North Dakota" never collapses onto "North Dakota State Bison" and
    # "North Carolina" never collapses onto "North Carolina State Wolfpack".
    next_idx = len(cand_tokens)
    next_tok = ex_tokens[next_idx]
    if next_tok in _SCHOOL_MODIFIER_WORDS:
        return None
    if ex_tokens[next_idx : next_idx + 2] in (["a", "m"], ["a", "t"]):
        return None
    if shared_token_rivals(candidate_name, t_name):
        return None
    return team


async def resolve_retired_team_id(db: Any, team_id: int) -> int:
    """Follow ``retired_team_redirects`` from ``team_id`` to its surviving canonical id."""
    if not isinstance(db, AsyncSession):
        return team_id

    from app.models.models import RetiredTeamRedirect

    current = team_id
    visited: set[int] = {current}
    for _ in range(_MAX_REDIRECT_HOPS):
        raw = (
            await db.execute(
                select(RetiredTeamRedirect.canonical_team_id).where(
                    RetiredTeamRedirect.retired_team_id == current
                )
            )
        ).scalar_one_or_none()
        nxt = _as_int(raw)
        if nxt is None or nxt in visited:
            break
        visited.add(nxt)
        current = nxt
    return current


async def resolve_retired_team_ids_batch(
    db: Any, team_ids: Iterable[int]
) -> dict[int, int]:
    """Batch-resolve a set of ``team_id``s through ``retired_team_redirects``."""
    unique_ids = sorted({tid for tid in team_ids if _as_int(tid) is not None})
    if not unique_ids or not isinstance(db, AsyncSession):
        return {tid: tid for tid in unique_ids}

    from app.models.models import RetiredTeamRedirect

    mapping = {tid: tid for tid in unique_ids}
    frontier = set(unique_ids)
    for _ in range(_MAX_REDIRECT_HOPS):
        if not frontier:
            break
        rows = (
            await db.execute(
                select(
                    RetiredTeamRedirect.retired_team_id,
                    RetiredTeamRedirect.canonical_team_id,
                ).where(RetiredTeamRedirect.retired_team_id.in_(sorted(frontier)))
            )
        ).all()
        hop_map = {
            r_id: c_id
            for r_id, c_id in rows
            if _as_int(r_id) is not None and _as_int(c_id) is not None
        }
        if not hop_map:
            break
        next_frontier: set[int] = set()
        for orig, cur in list(mapping.items()):
            nxt = hop_map.get(cur)
            if nxt is not None and nxt != cur:
                mapping[orig] = nxt
                next_frontier.add(nxt)
        frontier = next_frontier
    return mapping


async def resolve_retired_team_by_identifier(
    db: Any, identifier: str
) -> int | None:
    """Resolve a retired numeric team id or retired slug to its canonical team id."""
    if not identifier or not isinstance(db, AsyncSession):
        return None

    from app.models.models import RetiredTeamRedirect

    try:
        numeric_id = int(identifier)
        cond = or_(
            RetiredTeamRedirect.retired_team_id == numeric_id,
            RetiredTeamRedirect.retired_slug == identifier,
        )
    except ValueError:
        cond = RetiredTeamRedirect.retired_slug == identifier

    raw = (
        await db.execute(
            select(RetiredTeamRedirect.canonical_team_id).where(cond).limit(1)
        )
    ).scalar_one_or_none()
    canonical = _as_int(raw)
    if canonical is None:
        return None
    return await resolve_retired_team_id(db, canonical)


async def resolve_retired_team_by_name(
    db: Any, team_name: str, sport_id: int
) -> int | None:
    """Resolve a retired team's spelling within ``sport_id`` to its canonical team id."""
    if not team_name or not isinstance(db, AsyncSession):
        return None

    from app.models.models import RetiredTeamRedirect

    cleaned = team_name.strip().lower()
    if not cleaned:
        return None

    rows = (
        await db.execute(
            select(
                RetiredTeamRedirect.retired_name,
                RetiredTeamRedirect.canonical_team_id,
            ).where(
                RetiredTeamRedirect.sport_id == sport_id,
                RetiredTeamRedirect.retired_name.isnot(None),
            )
        )
    ).all()

    cand_norm = _norm_text(team_name)
    matched_ids: set[int] = set()
    for retired_name, canonical_id in rows:
        cid = _as_int(canonical_id)
        if cid is None or not retired_name:
            continue
        if (
            retired_name.strip().lower() == cleaned
            or _norm_text(retired_name) == cand_norm
        ) and distinguishing_tokens_agree(team_name, retired_name):
            matched_ids.add(cid)

    if len(matched_ids) != 1:
        return None
    return await resolve_retired_team_id(db, next(iter(matched_ids)))


async def find_existing_team_in_sport(
    db: Any,
    team_name: str,
    sport_id: int,
    *,
    espn_id: str | None = None,
    existing_teams: Sequence[Any] | None = None,
    allow_espn_id_match: bool = True,
) -> Any | None:
    """Guard called before ``Team(...)`` to avoid recreating a folded/existing club.

    Checks, within ``sport_id`` only and preserving reserve/women's separation:
      1. ``retired_team_redirects`` (retired name in ``sport_id``)
      2. ``team_identity_mapping`` (same-league ``source_name``)
      3. Same-league ``espn_id`` (when supplied and ``allow_espn_id_match`` is True)
      4. Same-league ``Team.name``, ``Team.alternate_names``, and unambiguous
         short-spelling prefix via :func:`unambiguous_short_spelling_match`.
    """
    from app.models.models import Team, TeamIdentityMapping

    if not team_name or not team_name.strip():
        return None

    # 1. Retired-team redirect by (sport_id, retired_name).
    retired_canonical_id = await resolve_retired_team_by_name(
        db, team_name, sport_id
    )
    if retired_canonical_id is not None and isinstance(db, AsyncSession):
        canonical_team = (
            await db.execute(
                select(Team).where(
                    Team.id == retired_canonical_id,
                    Team.sport_id == sport_id,
                )
            )
        ).scalar_one_or_none()
        if canonical_team is not None and distinguishing_tokens_agree(
            team_name, canonical_team.name
        ):
            return canonical_team

    # 2. Same-league team_identity_mapping lookup by source_name.
    if isinstance(db, AsyncSession):
        cleaned = team_name.strip().lower()
        mapped_rows = (
            await db.execute(
                select(Team)
                .join(TeamIdentityMapping, TeamIdentityMapping.team_id == Team.id)
                .where(
                    Team.sport_id == sport_id,
                    func.lower(TeamIdentityMapping.source_name) == cleaned,
                )
            )
        ).scalars().all()
        valid_mapped = [
            t
            for t in _unique_teams(mapped_rows)
            if distinguishing_tokens_agree(team_name, getattr(t, "name", None))
        ]
        if len(valid_mapped) == 1:
            return valid_mapped[0]

    # Load same-league Team pool when not already provided by the caller.
    pool: Sequence[Any]
    if existing_teams is not None:
        pool = existing_teams
    elif isinstance(db, AsyncSession):
        pool = list(
            (
                await db.execute(select(Team).where(Team.sport_id == sport_id))
            )
            .scalars()
            .all()
        )
    else:
        pool = ()

    # 3. Same-league ESPN id anchor (gated by caller when identity corresponds).
    clean_espn = str(espn_id).strip() if espn_id is not None else ""
    if clean_espn and allow_espn_id_match:
        espn_hits = [
            t
            for t in _unique_teams(pool)
            if getattr(t, "espn_id", None) is not None
            and str(t.espn_id).strip() == clean_espn
            and distinguishing_tokens_agree(team_name, getattr(t, "name", None))
        ]
        if len(espn_hits) == 1:
            return espn_hits[0]

    # 4. Same-league alternate_names + unambiguous short-spelling match.
    return unambiguous_short_spelling_match(team_name, pool)
