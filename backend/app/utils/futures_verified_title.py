"""#9387 — one verified current number for a title question, or source mode.

THE DEFECT, on screen. `/futures/86832` (*NFL Super Bowl Winner*) heroed
"Buffalo Bills 11% · Sportsbooks" while Kalshi's KXSB-27 and Polymarket's
event 202857 — the same question about the same game — sat on their own
pages at 13% and 13.5%. The detail route reads exactly one market row, so a
reader opening the title question saw one venue presented as the answer.

WHY THIS IS NOT A CANONICAL-KEY JOIN. `football::championship:2027` also keys
MVP, coach-of-the-year and playoff-qualifier markets, and the sportsbook row's
key carries no season at all. Membership here is decided only by each venue's
OWN structure:

  venue       identity                         edition              title-game instant
  odds_api    sport key (exact)                commence year of     provider commence_time
              + `odds_api_current_event`       the retained event
  kalshi      event ticker `KXSB-YY` (exact)   ticker year          expected expiration
                                                                    (`resolution_date`)
  polymarket  provider event id + slug         slug year            none — a WINDOW whose end
              `pro-football-YYYY-champion`                          is the no-winner cutoff
                                                                    (`resolution_date`)

The sportsbook anchor is CURRENT-QUOTES-ONLY: it was observed alongside one
poll batch (`futures_quote_identity`), so only an outcome refreshed at or after
that poll may use it. An older leg never inherits a newly observed edition.

SETTLEMENT. Polymarket resolves to `Other` if nobody wins by its cutoff;
Kalshi's latest expiration is a tail date years out. For the NAMED teams the
question is the same only while the title game falls inside Polymarket's
window, so a Polymarket row is a member only when a dated venue puts the game
before that cutoff. `Other` is never mapped to a team.

TEAMS. Correspondence is by team id from the canonical roster
(`team_identity_resolution`), with every shared alias already refused. A Kalshi
row resolves through its own ticker only — its display string is a bare city —
and a name that resolves to a DIFFERENT club vetoes it. City strings
(`Team.location`) are not admitted as aliases here at all.

ARITHMETIC. `futures_source_merge.blend_with_verdict`, unchanged — this module
decides WHICH rows answer one question, never a second way to combine them. A
venue is one voice however many sportsbooks stand behind it.

Everything here is pure: plain values in, plain values out. The route module
owns the reads and hands this module the boards it already serves.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping, Optional

from app.utils.futures_source_merge import blend_with_verdict
from app.utils.market_staleness import OBSERVATION_LAG_DAYS
from app.utils.outcome_display import is_field_outcome
from app.utils.team_identity_resolution import (
    TeamAliasIndex,
    build_team_alias_index,
    ticker_team_ids,
)

__all__ = [
    "SOURCE",
    "VERIFIED_TITLE",
    "CONTRIBUTOR_SOURCES",
    "ANCHOR_MAX_AGE",
    "TitleQuestion",
    "NFL_TITLE",
    "TITLE_QUESTIONS",
    "MarketFacts",
    "Member",
    "Refusal",
    "BoardRow",
    "OutcomeOverlay",
    "Composition",
    "parse_aware",
    "question_for",
    "member_of",
    "compose_members",
    "title_team_index",
    "compose_outcomes",
]

SOURCE = "source"
VERIFIED_TITLE = "verified_title"

#: The only wire keys a contributor may carry. A venue is one voice: eight
#: sportsbooks behind one Odds API row are `odds_api`, once.
CONTRIBUTOR_SOURCES = ("odds_api", "kalshi", "polymarket")

#: How old a retained sportsbook anchor may be and still name the CURRENT
#: edition. The Odds API futures poll runs every 4 hours
#: (`poll-futures-every-4h`); three missed polls is no longer "current", and a
#: quota-guard pause longer than that sends the page back to source mode
#: rather than dating today's quote by a stale batch.
ANCHOR_MAX_AGE = timedelta(hours=12)

#: Clock skew tolerated before a stamp "from the future" is refused.
_FUTURE_SKEW = timedelta(minutes=5)


@dataclass(frozen=True)
class TitleQuestion:
    """One title question, named by every venue's own structure."""

    competition: str
    question: str
    #: `Sport.key` whose `teams` rows are the roster for correspondence.
    team_sport_key: str
    odds_api_sport_key: str
    kalshi_series: str
    #: Polymarket event slug prefix; the full slug is
    #: ``{prefix}-{YYYY}-champion`` with an optional numeric creation suffix.
    polymarket_slug_prefix: str
    #: How far apart two venues' dated instants for the title game may be.
    instant_tolerance: timedelta = timedelta(hours=6)

    def kalshi_event_ticker(self, edition: str) -> str:
        return f"{self.kalshi_series}-{edition[-2:]}"

    def polymarket_slug_stem(self, edition: str) -> str:
        return f"{self.polymarket_slug_prefix}-{edition}-champion"

    def kalshi_edition(self, ticker: Optional[str]) -> Optional[str]:
        m = re.fullmatch(
            rf"{re.escape(self.kalshi_series)}-(\d{{2}})", (ticker or "").strip()
        )
        return f"20{m.group(1)}" if m else None

    def polymarket_edition(self, slug: Any) -> Optional[str]:
        if not isinstance(slug, str):
            return None
        m = re.fullmatch(
            rf"{re.escape(self.polymarket_slug_prefix)}-(\d{{4}})-champion(?:-\d+)?",
            slug.strip(),
        )
        return m.group(1) if m else None


NFL_TITLE = TitleQuestion(
    competition="NFL",
    question="league_championship_winner",
    team_sport_key="americanfootball_nfl",
    odds_api_sport_key="americanfootball_nfl_super_bowl_winner",
    kalshi_series="KXSB",
    polymarket_slug_prefix="pro-football",
)

#: Bounded on purpose: a question enters only with its own venue identities
#: written down, never by inference from a market name or the calendar.
TITLE_QUESTIONS: tuple[TitleQuestion, ...] = (NFL_TITLE,)


@dataclass(frozen=True)
class MarketFacts:
    """The columns membership reads, copied off a row as plain data."""

    market_id: int
    source: str
    external_id: str
    status: Optional[str]
    mutually_exclusive: Optional[bool]
    resolution_date: Optional[datetime]
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Member:
    source: str
    market_id: int
    edition: str
    #: The title game's dated instant, where this venue dates it.
    instant: Optional[datetime] = None
    #: Polymarket's no-winner cutoff — the end of its window.
    deadline: Optional[datetime] = None
    #: Sportsbook anchor batch clock: outcomes older than this may not use it.
    support_since: Optional[datetime] = None


@dataclass(frozen=True)
class Refusal:
    reason: str


def parse_aware(value: Any) -> Optional[datetime]:
    """An aware UTC datetime from a datetime or ISO string, else None."""
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str) and value.strip():
        try:
            dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if dt.tzinfo is None or dt.utcoffset() is None:
        return None
    return dt.astimezone(timezone.utc)


def question_for(facts: MarketFacts) -> Optional[TitleQuestion]:
    """The title question this row's own venue identity names, if any."""
    source = (facts.source or "").lower()
    for spec in TITLE_QUESTIONS:
        if source == "odds_api" and facts.external_id == spec.odds_api_sport_key:
            return spec
        if source == "kalshi" and spec.kalshi_edition(facts.external_id):
            return spec
        if source == "polymarket" and spec.polymarket_edition(
            (facts.metadata or {}).get("polymarket_event_slug")
        ):
            return spec
    return None


def member_of(
    spec: TitleQuestion, facts: MarketFacts, now: datetime
) -> Member | Refusal:
    """Is this row a current member of ``spec``, and for which edition?"""
    if facts.status != "open":
        return Refusal("not_open")
    if facts.mutually_exclusive is False:
        return Refusal("not_single_winner")
    meta = facts.metadata if isinstance(facts.metadata, Mapping) else {}
    source = (facts.source or "").lower()

    if source == "odds_api":
        if facts.external_id != spec.odds_api_sport_key:
            return Refusal("not_this_question")
        anchor = meta.get("odds_api_current_event")
        if not isinstance(anchor, Mapping):
            return Refusal("anchor_missing")
        event_id = anchor.get("event_id")
        if (
            anchor.get("scope") != "current_quotes_only"
            or anchor.get("sport_key") != facts.external_id
            or not isinstance(event_id, str)
            or not event_id.strip()
        ):
            return Refusal("anchor_malformed")
        commence = parse_aware(anchor.get("commence_time"))
        polled = parse_aware(anchor.get("polled_at"))
        if commence is None or polled is None:
            return Refusal("anchor_malformed")
        if polled > now + _FUTURE_SKEW or now - polled > ANCHOR_MAX_AGE:
            return Refusal("anchor_stale")
        return Member(
            "odds_api", facts.market_id, str(commence.year),
            instant=commence, support_since=polled,
        )

    if source == "kalshi":
        edition = spec.kalshi_edition(facts.external_id)
        if edition is None:
            return Refusal("not_this_question")
        stored_ticker = meta.get("kalshi_event_ticker")
        if stored_ticker is not None and stored_ticker != facts.external_id:
            return Refusal("ticker_mismatch")
        # Expected expiration, which is the game. The 2029 latest expiration
        # (`commence_time`) is the tail rule and is never read as the edition.
        instant = parse_aware(facts.resolution_date)
        if instant is None:
            return Refusal("edition_instant_missing")
        if str(instant.year) != edition:
            return Refusal("edition_mismatch")
        return Member("kalshi", facts.market_id, edition, instant=instant)

    if source == "polymarket":
        edition = spec.polymarket_edition(meta.get("polymarket_event_slug"))
        if edition is None:
            return Refusal("not_this_question")
        if meta.get("polymarket_event_id") != facts.external_id:
            return Refusal("provider_id_mismatch")
        deadline = parse_aware(facts.resolution_date)
        if deadline is None:
            return Refusal("settlement_deadline_missing")
        if str(deadline.year) != edition:
            return Refusal("edition_mismatch")
        return Member("polymarket", facts.market_id, edition, deadline=deadline)

    return Refusal("unsupported_source")


def compose_members(
    spec: TitleQuestion,
    requested: Member,
    candidates: Iterable[Member],
) -> list[Member] | Refusal:
    """The venues answering the requested row's question, requested first.

    Refuses rather than picks: two rows from one venue for one edition drop
    that venue, and if the venue is the requested row's own the whole request
    returns to source mode.
    """
    by_source: dict[str, list[Member]] = {requested.source: [requested]}
    for c in candidates:
        if c.market_id == requested.market_id or c.edition != requested.edition:
            continue
        by_source.setdefault(c.source, []).append(c)
    if len(by_source[requested.source]) > 1:
        return Refusal("ambiguous_requested_venue")
    members = [requested]
    for src in CONTRIBUTOR_SOURCES:
        rows = by_source.get(src, [])
        if src != requested.source and len(rows) == 1:
            members.append(rows[0])

    instants = [m.instant for m in members if m.instant is not None]
    if instants and max(instants) - min(instants) > spec.instant_tolerance:
        return Refusal("edition_instant_conflict")
    game_at = min(instants) if instants else None

    accepted: list[Member] = []
    for m in members:
        if m.source == "polymarket":
            # Settlement: Polymarket's named-team legs ask our question only
            # while a dated venue puts the game inside its window.
            if game_at is None or m.deadline is None or not game_at < m.deadline:
                if m is requested:
                    return Refusal("settlement_rule_refused")
                continue
        accepted.append(m)
    if len(accepted) < 2:
        return Refusal("no_corroborating_venue")
    return accepted


def title_team_index(teams: Iterable[Mapping[str, Any]]) -> TeamAliasIndex:
    """The roster index WITHOUT city aliases: a bare city never names a team."""
    return build_team_alias_index(
        [{k: v for k, v in t.items() if k != "location"} for t in teams]
    )


def _row_team_id(
    source: str,
    external_id: Optional[str],
    name: Optional[str],
    index: TeamAliasIndex,
) -> Optional[int]:
    if is_field_outcome(name):
        return None
    by_name = None if index.is_ambiguous(name) else index.alias_team(name)
    if source == "kalshi":
        ids = ticker_team_ids(external_id, index)
        if len(ids) != 1:
            return None
        (tid,) = ids
        if by_name is not None and by_name != tid:
            return None
        return tid
    return by_name


@dataclass(frozen=True)
class BoardRow:
    """One outcome as its own venue's detail board serves it."""

    outcome_id: int
    name: Optional[str]
    external_id: Optional[str]
    probability: Optional[float]
    observed_at: Optional[datetime]


@dataclass(frozen=True)
class OutcomeOverlay:
    probability: Optional[float]
    contributing_sources: list[str]
    observed_at: Optional[str]
    aggregation_rule: str
    #: False only when the value IS the requested source's own served value,
    #: so its opening and movement still describe the same estimator.
    changed: bool


@dataclass(frozen=True)
class Composition:
    question_identity: dict
    overlay: dict[int, OutcomeOverlay]
    contributing_sources: list[str]


def _usable(row: BoardRow, member: Member, now: datetime) -> bool:
    if row.probability is None or row.observed_at is None:
        return False
    if row.observed_at < now - timedelta(days=OBSERVATION_LAG_DAYS):
        return False
    if member.support_since is not None and row.observed_at < member.support_since:
        return False
    return True


def compose_outcomes(
    spec: TitleQuestion,
    members: list[Member],
    boards: Mapping[int, list[BoardRow]],
    index: TeamAliasIndex,
    now: datetime,
) -> Composition | Refusal:
    """Map every venue's current value back onto the requested board by id.

    ``members[0]`` is the requested row; ``boards`` is keyed by market id and
    holds each venue's rows exactly as its own detail board serves them.
    """
    requested = members[0]
    team_maps: dict[int, dict[int, BoardRow]] = {}
    for m in members:
        claims: dict[int, list[BoardRow]] = {}
        for row in boards.get(m.market_id, []):
            tid = _row_team_id(m.source, row.external_id, row.name, index)
            if tid is not None:
                claims.setdefault(tid, []).append(row)
        # Two rows claiming one club inside one venue: neither speaks for it.
        team_maps[m.market_id] = {
            t: rows[0] for t, rows in claims.items() if len(rows) == 1
        }

    own_team = {row.outcome_id: t for t, row in team_maps[requested.market_id].items()}
    # One fixed venue order for every page, so the divergence gate's tiebreak
    # (and the contributor list) cannot depend on which venue's page was opened.
    voices = sorted(members, key=lambda m: CONTRIBUTOR_SOURCES.index(m.source))
    overlay: dict[int, OutcomeOverlay] = {}
    multi = False
    for row in boards.get(requested.market_id, []):
        tid = own_team.get(row.outcome_id)
        picks: list[tuple[str, BoardRow]] = []
        if tid is None:
            if _usable(row, requested, now):
                picks.append((requested.source, row))
        else:
            for m in voices:
                other = team_maps[m.market_id].get(tid)
                if other is not None and _usable(other, m, now):
                    picks.append((m.source, other))

        if not picks:
            overlay[row.outcome_id] = OutcomeOverlay(None, [], None, "unsupported", True)
            continue
        if len(picks) == 1:
            value, rule, used = picks[0][1].probability, "single_source", picks
        else:
            value, divergence, rule = blend_with_verdict(
                [{"source": s, "probability": r.probability} for s, r in picks]
            )
            # The divergence gate prints ONE venue's own number; only that
            # venue contributed to what the reader sees.
            used = (
                [p for p in picks if p[0] == divergence.primary_source]
                if divergence is not None
                else picks
            )
        sources = [s for s, _ in used]
        multi = multi or len(sources) > 1
        overlay[row.outcome_id] = OutcomeOverlay(
            probability=value,
            contributing_sources=sources,
            observed_at=min(r.observed_at for _, r in used).isoformat(),
            aggregation_rule=rule,
            changed=sources != [requested.source],
        )

    if not multi:
        return Refusal("no_multi_source_outcome")
    used_sources = {s for o in overlay.values() for s in o.contributing_sources}
    return Composition(
        question_identity={
            "competition": spec.competition,
            "edition": requested.edition,
            "question": spec.question,
        },
        overlay=overlay,
        contributing_sources=[s for s in CONTRIBUTOR_SOURCES if s in used_sources],
    )
