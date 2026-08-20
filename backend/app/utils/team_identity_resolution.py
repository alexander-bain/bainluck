"""#2001 — resolve an outcome row to a TEAM ID, or refuse. Never by name shape.

THE DEFECT. Kalshi truncates team names in outcome display strings, so the
cross-source merge (#1986) never fires on them:

    nl_west   kalshi "Los Angeles D" 0.97    polymarket "Los Angeles Dodgers" 0.9845

Both rows satisfy every other merge condition and fail only `entities_compatible`,
whose token-subset containment correctly refuses `{los, angeles, d}` against
`{los, angeles, dodgers}`. So one question renders as two rows reading 97% and
98.45%.

WHY THE OBVIOUS FIXES ARE BOTH UNSAFE — MEASURED, NOT ASSUMED (2026-08-19):

**1. A prefix rule fuses city siblings.** `Los Angeles D` prefix-matches the
Dodgers; `Los Angeles A` prefix-matches the Angels; and the class generalizes to
every two-team city. A wrong merge silently invents a number, which is strictly
worse than the two rows it replaces.

**2. `futures_outcomes.team_id` — the field that LOOKS like the answer — is
crosswise on exactly this class.** Censused against the Kalshi ticker suffix
across the 903 outcomes of event 15200831's related markets:

    kalshi outcomes with a ticker-derivable team AND a stored team_id:  86
      stored team_id AGREES with the ticker                            76
      stored team_id DISAGREES                                         10   (11.6%)

    'Chicago C'      KXMLBPLAYOFFS-26-CHC   stored=Chicago White Sox  ticker=Chicago Cubs
    'Los Angeles D'  KXMLBPLAYOFFS-26-LAD   stored=Los Angeles Angels ticker=Los Angeles Dodgers
    'New York M'     KXMLBPLAYOFFS-26-NYM   stored=New York Yankees   ticker=New York Mets

Every disagreement names the truncated team's OWN CITY SIBLING. So a merge that
matched on the stored `team_id` would pair Kalshi's Dodgers row with Polymarket's
Angels row — it would COMMIT the Angels/Athletics catastrophe through the very
field that was supposed to prevent it. The write-side defect is routed; this
module refuses to read it.

**3. `team_identity_mapping` is worse, and it MOVES.** Agreement rate for MLB,
measured the same day: espn 32/32 (100%), kalshi 8/54 (14.8%), polymarket 1/32
(3.1%). `Los Angeles D` → kalshi → *Arizona Diamondbacks*. Lane1's queue-369 note
records the poison as "live and moving ... in two clean 2-cycles", so a predicate
built on it would blend a different wrong number from one hour to the next.

WHAT IS TRUSTWORTHY, AND ALL THIS MODULE USES:

- the canonical `teams` rows for the sport (name / location / abbreviation /
  alternate_names), verified self-consistent 33/33 for MLB; and
- the Kalshi **ticker suffix** (`KXMLBNLWEST-26-LAD` → `LAD`), which gotcha #16
  already names as authoritative over display abbreviations.

THE TWO REFUSALS THAT MAKE IT SAFE:

- **An alias shared by two teams is DROPPED, not guessed.** `alternate_names`
  carries "Los Angeles" on BOTH the Angels and the Dodgers, so that string
  resolves to nothing. Same for a duplicated abbreviation (MLB currently carries
  two `STL` team rows).
- **Only EXACT normalized alias equality resolves.** No prefixes, no containment,
  no fuzz. A truncated name therefore cannot resolve by name at all — it resolves
  through its ticker or not at all, which is the property that makes the whole
  thing safe by construction rather than by hoping the alias list is complete.

Resolution is deliberately allowed to return ``None``. An unresolved row falls
back to the caller's existing predicate; it never becomes a guess.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional

__all__ = [
    "TeamAliasIndex",
    "build_team_alias_index",
    "kalshi_ticker_abbrev",
    "resolve_row_team_id",
    "row_entity_is_ambiguous",
]

# Kalshi outcome tickers end in the team's canonical abbreviation:
#   KXMLBNLWEST-26-LAD, KXMLB-26-HOU, KXMLBPLAYOFFS-26-CHC
# Two to four uppercase letters, anchored to the end, after a hyphen.
_TICKER_TEAM_SUFFIX = re.compile(r"-([A-Z]{2,4})$")

_PUNCT = re.compile(r"[^\w\s]")
_WS = re.compile(r"\s+")


def _norm(value: Optional[str]) -> str:
    """Lowercase, strip punctuation, collapse whitespace.

    Matches `futures_source_merge._norm_entity` so the two predicates agree about
    what "the same string" means. "St. Louis" and "St Louis" normalize together.
    """
    return _WS.sub(" ", _PUNCT.sub(" ", (value or "").lower())).strip()


@dataclass(frozen=True)
class TeamAliasIndex:
    """Exact-match alias → team_id, with every ambiguous key already removed.

    `ambiguous_aliases` / `ambiguous_abbrevs` are kept rather than discarded so a
    caller (or a test) can assert WHICH strings were refused. "Los Angeles"
    landing in `ambiguous_aliases` is the evidence that the Angels/Dodgers hazard
    was disarmed, not merely unencountered.

    They are also load-bearing, not just diagnostic. "This string names two
    teams" is a DIFFERENT fact from "I have never heard this string", and only
    the first justifies vetoing a merge — so the two must be distinguishable at
    the call site. See `is_ambiguous`.
    """

    by_alias: Mapping[str, int]
    by_abbrev: Mapping[str, int]
    ambiguous_aliases: frozenset
    ambiguous_abbrevs: frozenset

    def alias_team(self, name: Optional[str]) -> Optional[int]:
        return self.by_alias.get(_norm(name))

    def abbrev_team(self, abbrev: Optional[str]) -> Optional[int]:
        if not abbrev:
            return None
        return self.by_abbrev.get(abbrev.strip().upper())

    def is_ambiguous(self, name: Optional[str]) -> bool:
        """Does this string name MORE THAN ONE team in this sport?

        True only for a string we positively know is shared — never for an
        unrecognised one.
        """
        return _norm(name) in self.ambiguous_aliases


def build_team_alias_index(teams: Iterable[Mapping[str, Any]]) -> TeamAliasIndex:
    """Build the index from canonical team rows.

    Each team contributes `name`, `location`, `abbreviation` and every entry of
    `alternate_names`. A key claimed by two DIFFERENT teams is poisoned and
    removed from the index entirely — it is not resolved to the first, the
    lowest, or the most recent.

    **"Different teams" means different NAMES, not different ids.** Production
    carries duplicate rows for one club — MLB has `St. Louis Cardinals` (10740)
    and `St.Louis Cardinals` (13437), which normalize to the same string and both
    claim `STL`. Keying ambiguity on the raw id would declare `STL` poisoned and
    veto every legitimate Cardinals merge, turning a known duplicate-row defect
    (#1204's territory) into a second, silent one on this surface. So rows are
    folded to a canonical id by normalized name first, and only genuinely
    distinct clubs can poison a key.
    """
    # Fold duplicate team rows onto one canonical id before anything claims a
    # key. Lowest id wins — arbitrary but stable, and every alias of every
    # duplicate row still lands on the same team.
    canonical: dict[str, Any] = {}
    for team in teams:
        tid = team.get("id")
        key = _norm(team.get("name"))
        if tid is None or not key:
            continue
        if key not in canonical or tid < canonical[key]:
            canonical[key] = tid

    def _canonical_id(team: Mapping[str, Any]) -> Optional[Any]:
        return canonical.get(_norm(team.get("name")), team.get("id"))

    alias_claims: dict[str, set] = {}
    abbrev_claims: dict[str, set] = {}

    for team in teams:
        tid = _canonical_id(team)
        if tid is None:
            continue

        for key in ("name", "location"):
            k = _norm(team.get(key))
            if k:
                alias_claims.setdefault(k, set()).add(tid)

        alts = team.get("alternate_names") or []
        if isinstance(alts, (list, tuple)):
            for alt in alts:
                k = _norm(alt if isinstance(alt, str) else None)
                if k:
                    alias_claims.setdefault(k, set()).add(tid)

        abbreviation = (team.get("abbreviation") or "").strip().upper()
        if abbreviation:
            abbrev_claims.setdefault(abbreviation, set()).add(tid)
            # An abbreviation is also a legitimate display string on some
            # sources, so it earns an alias slot too — under the same
            # ambiguity rule.
            k = _norm(abbreviation)
            if k:
                alias_claims.setdefault(k, set()).add(tid)

    by_alias = {k: next(iter(v)) for k, v in alias_claims.items() if len(v) == 1}
    by_abbrev = {k: next(iter(v)) for k, v in abbrev_claims.items() if len(v) == 1}
    return TeamAliasIndex(
        by_alias=by_alias,
        by_abbrev=by_abbrev,
        ambiguous_aliases=frozenset(k for k, v in alias_claims.items() if len(v) > 1),
        ambiguous_abbrevs=frozenset(k for k, v in abbrev_claims.items() if len(v) > 1),
    )


def kalshi_ticker_abbrev(external_id: Optional[str]) -> Optional[str]:
    """The team abbreviation at the end of a Kalshi outcome ticker, or None.

    Returns None for the many Kalshi tickers that do not end in a team — player
    props, date-stamped game tickers (`KXMLBRFI-26AUG202010LAAHOU`), threshold
    ladders. None means "this ticker does not name a team", never "no team".
    """
    if not external_id:
        return None
    match = _TICKER_TEAM_SUFFIX.search(external_id.strip())
    return match.group(1) if match else None


def _ticker_team_segments(external_id: Optional[str], index: TeamAliasIndex) -> set:
    """Every hyphen segment of a ticker that is a known team abbreviation.

    Used only to REFUSE. A matchup ticker like `KXNBA-26-BOS-CHA` names two
    teams, and the tail regex would happily return one of them — picking the
    loser of a game as the subject of the market. Counting them first turns that
    into a refusal instead of a coin flip.
    """
    if not external_id:
        return set()
    found = set()
    for segment in external_id.strip().split("-"):
        seg = segment.strip().upper()
        if seg and seg in index.by_abbrev:
            found.add(seg)
    return found


def resolve_row_team_id(
    row: Mapping[str, Any], index: Optional[TeamAliasIndex]
) -> Optional[int]:
    """Which team does this outcome row name? ``None`` when not certain.

    Order matters. The **ticker is consulted first** for Kalshi rows, because it
    is the only signal on a truncated row that carries the whole team, and
    gotcha #16 already rules it authoritative over the display string. The exact
    alias path then covers every untruncated source (Polymarket's full
    "Los Angeles Dodgers", Kalshi's untruncated "Houston").

    Deliberately NOT consulted: the row's own stored `team_id`. It is wrong on
    11.6% of ticker-derivable Kalshi outcomes and wrong toward the city sibling
    every time — see this module's header census.
    """
    if index is None:
        return None

    source = (row.get("source") or "").strip().lower()
    if source == "kalshi":
        external_id = row.get("external_id")
        # A ticker that names TWO teams names no subject. Refuse before reading
        # the tail, or `KXNBA-26-BOS-CHA` resolves to whichever team sorts last
        # in the string — a property of Kalshi's formatting, not of the market.
        if len(_ticker_team_segments(external_id, index)) < 2:
            by_ticker = index.abbrev_team(kalshi_ticker_abbrev(external_id))
            if by_ticker is not None:
                return by_ticker

    return index.alias_team(row.get("outcome_name"))


def row_entity_is_ambiguous(
    row: Mapping[str, Any], index: Optional[TeamAliasIndex]
) -> bool:
    """Does this row's name POSITIVELY name more than one team?

    The distinction this draws is the whole reason it exists. `resolve_row_team_id`
    returns ``None`` for two very different rows:

      - **"Waterloo Road FC"** — never heard of it. Says nothing; the caller
        should fall back to its name predicate.
      - **"Los Angeles"** — an `alternate_names` entry on BOTH the Angels and the
        Dodgers in production. This one is a positive statement that the string
        does not identify a team, and merging on it is a coin flip decided by row
        order.

    Only the second returns True, and it earns a veto. A row that resolves
    cleanly is never ambiguous, so the ticker path short-circuits it.
    """
    if index is None:
        return False
    if resolve_row_team_id(row, index) is not None:
        return False
    return index.is_ambiguous(row.get("outcome_name"))
