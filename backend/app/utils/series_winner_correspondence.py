"""#10407 A1 — one MLB series winner question across Kalshi and Polymarket.

PILLARS: MATCHING / TRUTH. A playoff game page asks "who wins the series" once,
with one blended number, and each venue keeps its own no-winner rules.

THE DEFECT, on screen. Event 15322539 (Yankees at Rays, ALDS Game 1) served
three Series questions: Kalshi "Series Winner" (TB .63 / NYY .365), Polymarket
"Who Will Win Series?" (Rays .645 / Yankees .355), and Polymarket's series
spread. The first two ask the same thing, so the reader saw it twice.

THE RULE IS #9387's, PORTED, NOT A SECOND ONE. `futures_verified_title` already
decides when two venues answer one title question; this module applies the
same clauses to the series family:

  clause        Kalshi                              Polymarket
  membership    event ticker `KXMLBSERIES-YY…ROUND`  event id + slug
                (any stored `kalshi_event_ticker`   `mlb-playoffs-who-will-win-series-`,
                equal to it), exactly two legs      one market, exactly two outcomes
  edition       ticker year == `resolution_date`    `resolution_date` year (the slug
                year                                has none)
  teams         each LEG's own ticker               outcome name, shared alias refused
  settlement    `resolution_date` (expected         stated no-winner cutoff, read from
                expiration) is the dated instant    the rule text at ingest
                                                    (`polymarket_no_winner_cutoff`)

Exclusivity on the Polymarket side is proved by the structure (one market, two
outcomes, two distinct clubs), never by `neg_risk`, which a one-market event
never carries. The concatenated event code (`NYYTB`) is never split. Kalshi
`commence_time` (its close time, gotcha #14) is never read. Polymarket's 50-50
branch is never mapped to a team: the pair composes only while Kalshi's dated
instant falls before Polymarket's cutoff, and refuses on its own past it.

TEAMS. Every row resolves through ONE roster index — the page's own sport's
teams, city aliases removed (`title_team_index`). So "same roster sport" is a
property of the input, not a check that could be skipped.

REFUSE, NEVER PICK. Two rows from one venue for one series, a disagreeing round
label, a leg that is settled or withheld, a market settled before the game, a
missing or later cutoff, an unpriced leg, or two venues beyond the divergence
gate: the pair stays two questions exactly as today.

ARITHMETIC. `futures_source_merge.blend_with_verdict`, unchanged, per team.

Pure: plain values in, plain values out. No I/O, no clock read.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Mapping, Optional

from app.utils.futures_source_merge import blend_with_verdict
from app.utils.futures_verified_title import _row_team_id, parse_aware, title_team_index
from app.utils.polymarket_no_winner_cutoff import (
    MLB_SERIES_WINNER_FAMILY,
    NO_WINNER_CUTOFF_KEY,
    RULES_TEXT_SOURCE,
    is_mlb_series_winner_slug,
)
from app.utils.team_identity_resolution import TeamAliasIndex
from app.utils.venue_competition import POLYMARKET_EVENT_SLUG_KEY

__all__ = [
    "SERIES_BLEND_BASIS",
    "KALSHI_SERIES_TICKER_RE",
    "SeriesLeg",
    "SeriesMarketFacts",
    "SeriesMember",
    "SeriesTeamBlend",
    "SeriesPair",
    "series_member",
    "compose_series_pairs",
    "series_question_key",
]

#: The `published.basis` a composed option carries (contract rider 10407-R1).
SERIES_BLEND_BASIS = "verified_series_blend"

KALSHI_SERIES_TICKER_RE = re.compile(r"^KXMLBSERIES-(\d{2})[A-Z]+(ALDS|NLDS|ALCS|NLCS|WS)$")

# Membership refusals (one market).
NOT_SERIES_WINNER = "not_series_winner"
EVENT_TICKER_MISMATCH = "event_ticker_mismatch"
EVENT_ID_MISMATCH = "event_id_mismatch"
NOT_ONE_MARKET = "not_one_market"
LEG_COUNT = "leg_count"
LEG_NOT_OF_EVENT = "leg_not_of_event"
TEAM_UNRESOLVED = "team_unresolved"
TEAMS_NOT_DISTINCT = "teams_not_distinct"
NO_SEASON = "no_season"
SEASON_MISMATCH = "season_mismatch"

# Pair refusals.
SINGLE_VENUE = "single_venue"
DUPLICATE_PER_VENUE = "duplicate_per_venue"
ROUND_LABEL_DISAGREES = "round_label_disagrees"
NOT_OPEN = "not_open"
SETTLED_BEFORE_THE_GAME = "settled_before_the_game"
LEG_SETTLED = "leg_settled"
LEG_WITHHELD = "leg_withheld"
SETTLEMENT_RULE_REFUSED = "settlement_rule_refused"
UNPRICED_LEG = "unpriced_leg"
DIVERGENCE_GATE = "divergence_gate"


@dataclass(frozen=True)
class SeriesLeg:
    """One stored outcome, as the route loaded it."""

    outcome_id: int
    name: Optional[str]
    external_id: Optional[str]
    #: The leg's own stored price (0.0 is real; None is unpriced).
    probability: Optional[float]
    is_winner: Optional[bool]
    #: In the route's refusal set (`_related_futures_withheld_ids`).
    withheld: bool


@dataclass(frozen=True)
class SeriesMarketFacts:
    market_id: int
    source: Optional[str]
    external_id: Optional[str]
    status: Optional[str]
    resolution_date: Optional[datetime]
    market_metadata: Mapping[str, Any]
    #: The route's own `_settled_before_the_game` answer for this market.
    settled_before_the_game: bool
    legs: tuple[SeriesLeg, ...]


@dataclass(frozen=True)
class SeriesMember:
    source: str
    market_id: int
    season: int
    team_pair: tuple[int, int]
    round_label: Optional[str]
    leg_by_team: Mapping[int, SeriesLeg]
    #: Kalshi: its dated instant (`resolution_date`). Polymarket: None.
    instant: Optional[datetime]
    #: Polymarket: its stated no-winner cutoff. Kalshi: None.
    deadline: Optional[datetime]


@dataclass(frozen=True)
class SeriesTeamBlend:
    team_id: int
    #: The roster's own name for the club ("Tampa Bay Rays"), when it has one.
    name: Optional[str]
    value: float
    rule: str
    #: (kalshi outcome id, polymarket outcome id).
    contributor_outcome_ids: tuple[int, int]


@dataclass(frozen=True)
class SeriesPair:
    """One series (season + two clubs) and what became of it."""

    season: int
    team_pair: tuple[int, int]
    #: Every member market seen for this series, ascending.
    market_ids: tuple[int, ...]
    refusal: Optional[str]
    question_key: Optional[str] = None
    #: (`m:<kalshi>`, `m:<polymarket>`) when composed.
    merged_question_keys: tuple[str, ...] = ()
    #: (kalshi market id, polymarket market id) when composed.
    contributor_market_ids: tuple[int, ...] = ()
    teams: tuple[SeriesTeamBlend, ...] = ()

    @property
    def composed(self) -> bool:
        return self.refusal is None


def series_question_key(season: int, team_pair: tuple[int, int]) -> str:
    lo, hi = sorted(team_pair)
    return f"q:series_winner:{season}:{lo}-{hi}"


def _legs_by_team(
    source: str, legs: tuple[SeriesLeg, ...], index: TeamAliasIndex
) -> dict[int, SeriesLeg] | str:
    if len(legs) != 2:
        return LEG_COUNT
    by_team: dict[int, SeriesLeg] = {}
    for leg in legs:
        tid = _row_team_id(source, leg.external_id, leg.name, index)
        if tid is None:
            return TEAM_UNRESOLVED
        if tid in by_team:
            return TEAMS_NOT_DISTINCT
        by_team[tid] = leg
    return by_team


def _kalshi_member(facts: SeriesMarketFacts, index: TeamAliasIndex) -> SeriesMember | str:
    ticker = facts.external_id or ""
    match = KALSHI_SERIES_TICKER_RE.match(ticker)
    if match is None:
        return NOT_SERIES_WINNER
    stored = facts.market_metadata.get("kalshi_event_ticker")
    if stored is not None and stored != ticker:
        return EVENT_TICKER_MISMATCH
    if len(facts.legs) != 2:
        return LEG_COUNT
    if any(not (leg.external_id or "").startswith(f"{ticker}-") for leg in facts.legs):
        return LEG_NOT_OF_EVENT
    by_team = _legs_by_team("kalshi", facts.legs, index)
    if isinstance(by_team, str):
        return by_team
    instant = parse_aware(facts.resolution_date)
    if instant is None:
        return NO_SEASON
    season = 2000 + int(match.group(1))
    if instant.year != season:
        return SEASON_MISMATCH
    return SeriesMember(
        source="kalshi",
        market_id=facts.market_id,
        season=season,
        team_pair=tuple(sorted(by_team)),
        round_label=match.group(2),
        leg_by_team=by_team,
        instant=instant,
        deadline=None,
    )


def _stated_cutoff(meta: Mapping[str, Any]) -> Optional[datetime]:
    cutoff = meta.get(NO_WINNER_CUTOFF_KEY)
    if not isinstance(cutoff, Mapping):
        return None
    if cutoff.get("source") != RULES_TEXT_SOURCE or cutoff.get("family") != MLB_SERIES_WINNER_FAMILY:
        return None
    return parse_aware(cutoff.get("at"))


def _polymarket_member(facts: SeriesMarketFacts, index: TeamAliasIndex) -> SeriesMember | str:
    meta = facts.market_metadata
    if not is_mlb_series_winner_slug(meta.get(POLYMARKET_EVENT_SLUG_KEY)):
        return NOT_SERIES_WINNER
    event_id = meta.get("polymarket_event_id")
    if event_id is None or str(event_id) != str(facts.external_id):
        return EVENT_ID_MISMATCH
    if meta.get("market_count") not in (None, 1):
        return NOT_ONE_MARKET
    by_team = _legs_by_team("polymarket", facts.legs, index)
    if isinstance(by_team, str):
        return by_team
    dated = parse_aware(facts.resolution_date)
    if dated is None:
        return NO_SEASON
    return SeriesMember(
        source="polymarket",
        market_id=facts.market_id,
        season=dated.year,
        team_pair=tuple(sorted(by_team)),
        round_label=None,  # Polymarket stores no round label
        leg_by_team=by_team,
        instant=None,
        deadline=_stated_cutoff(meta),
    )


def series_member(facts: SeriesMarketFacts, index: TeamAliasIndex) -> SeriesMember | str:
    """This market as a series-winner member, or the reason it is not one."""
    source = (facts.source or "").lower()
    if source == "kalshi":
        return _kalshi_member(facts, index)
    if source == "polymarket":
        return _polymarket_member(facts, index)
    return NOT_SERIES_WINNER


def _lifecycle_refusal(facts: SeriesMarketFacts) -> Optional[str]:
    if facts.status != "open":
        return NOT_OPEN
    if facts.settled_before_the_game:
        return SETTLED_BEFORE_THE_GAME
    if any(leg.is_winner is not None for leg in facts.legs):
        return LEG_SETTLED
    if any(leg.withheld for leg in facts.legs):
        return LEG_WITHHELD
    return None


def _compose(
    season: int,
    team_pair: tuple[int, int],
    members: list[SeriesMember],
    facts_by_id: Mapping[int, SeriesMarketFacts],
    name_by_id: Mapping[Any, Optional[str]],
) -> SeriesPair:
    market_ids = tuple(sorted(m.market_id for m in members))

    def refuse(reason: str) -> SeriesPair:
        return SeriesPair(season=season, team_pair=team_pair, market_ids=market_ids, refusal=reason)

    kalshi = [m for m in members if m.source == "kalshi"]
    poly = [m for m in members if m.source == "polymarket"]
    if len(kalshi) > 1 or len(poly) > 1:
        return refuse(DUPLICATE_PER_VENUE)
    if not kalshi or not poly:
        return refuse(SINGLE_VENUE)
    (k,), (p,) = kalshi, poly
    if k.round_label and p.round_label and k.round_label != p.round_label:
        return refuse(ROUND_LABEL_DISAGREES)
    for m in (k, p):
        reason = _lifecycle_refusal(facts_by_id[m.market_id])
        if reason is not None:
            return refuse(reason)
    # Settlement (#9387): Polymarket's named-team legs ask our question only
    # while Kalshi's dated instant falls before Polymarket's stated cutoff.
    if k.instant is None or p.deadline is None or not k.instant < p.deadline:
        return refuse(SETTLEMENT_RULE_REFUSED)

    teams: list[SeriesTeamBlend] = []
    for tid in team_pair:
        k_leg, p_leg = k.leg_by_team[tid], p.leg_by_team[tid]
        if k_leg.probability is None or p_leg.probability is None:
            return refuse(UNPRICED_LEG)
        value, divergence, rule = blend_with_verdict([
            {"probability": k_leg.probability, "source": "kalshi"},
            {"probability": p_leg.probability, "source": "polymarket"},
        ])
        if divergence is not None or value is None:
            return refuse(DIVERGENCE_GATE)
        teams.append(SeriesTeamBlend(
            team_id=tid,
            name=name_by_id.get(tid),
            value=value,
            rule=rule,
            contributor_outcome_ids=(k_leg.outcome_id, p_leg.outcome_id),
        ))
    return SeriesPair(
        season=season,
        team_pair=team_pair,
        market_ids=market_ids,
        refusal=None,
        question_key=series_question_key(season, team_pair),
        merged_question_keys=(f"m:{k.market_id}", f"m:{p.market_id}"),
        contributor_market_ids=(k.market_id, p.market_id),
        teams=tuple(teams),
    )


def compose_series_pairs(
    markets: Iterable[SeriesMarketFacts],
    teams: Iterable[Mapping[str, Any]],
) -> list[SeriesPair]:
    """Every series the given markets name, composed or refused, in key order.

    ``teams`` is the page's own sport roster (``id``, ``name``,
    ``abbreviation``, ``alternate_names``; ``location`` is dropped). A market
    that is not a series-winner member contributes to no pair.
    """
    teams = list(teams)
    index = title_team_index(teams)
    # Resolution returns the lowest id among a club's duplicate rows, which is
    # a real row's id, so its own name is the club's.
    name_by_id = {t.get("id"): t.get("name") for t in teams}
    facts_by_id: dict[int, SeriesMarketFacts] = {}
    groups: dict[tuple[int, tuple[int, int]], list[SeriesMember]] = {}
    for facts in markets:
        facts_by_id[facts.market_id] = facts
        member = series_member(facts, index)
        if isinstance(member, SeriesMember):
            groups.setdefault((member.season, member.team_pair), []).append(member)
    return [
        _compose(season, pair, members, facts_by_id, name_by_id)
        for (season, pair), members in sorted(groups.items())
    ]
