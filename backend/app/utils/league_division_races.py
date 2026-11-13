"""Dynamic ``league_division_races`` grouped-card producer (#12288 Wave 1, Idea #1).

PILLAR: DISCOVER · MATCHING · TRUTH
SHIP: Dynamic division-winner container across active sports leagues (NBA, NHL,
NFL, MLB) that selects open division-winner markets, blends two-source twins via
``futures_source_merge.blend_with_verdict`` (refusing 40+ pt divergence), drops
the brittle all-8-or-nothing gate in favour of ``>= min_divisions`` (default 4),
orders card rows from tightest race to clearest lock, and emits a dynamic
``context_line`` clarifying how rows were chosen and how to read the chances.

Publication gate: candidate definitions live in ``backend/data/discover/candidates/``
and are NOT registered in ``ROUNDUP_PRODUCERS`` until licensed via the Discover
exam and ``/grade/groupings``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from app.utils.container_presentation import market_destination
from app.utils.futures_source_merge import blend_with_verdict
from app.utils.roundup_containers import (
    RoundupMembers,
    RoundupProducer,
    RoundupRefusal,
    compose_roundup_container,
    compose_roundup_feed_item,
    validate_roundup_definition,
)

__all__ = [
    "CANDIDATE_NBA_DIVISION_RACES_PATH",
    "LEAGUE_DIVISIONS",
    "PRODUCER_KIND_LEAGUE_DIVISION_RACES",
    "DivisionStanding",
    "build_division_races_grading_candidate",
    "build_league_division_races_producer",
    "compose_division_races_card_and_container",
    "load_candidate_definition",
    "produce_league_division_races",
    "select_league_division_races",
]

PRODUCER_KIND_LEAGUE_DIVISION_RACES = "league_division_races"

CANDIDATE_NBA_DIVISION_RACES_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "discover"
    / "candidates"
    / "roundup-nba-division-races.json"
)

_FORBIDDEN_COPY_RE = re.compile(
    r"\b(?:questions?|stale|venues?|kalshi|polymarket|opened)\b",
    re.IGNORECASE,
)

_NON_WINNER_SUBTYPE_RE = re.compile(
    r"\b(?:exact\s+order|total\s+wins|win\s+total|runner[- ]?up|second\s+place|"
    r"last\s+place|make\s+playoffs|playoff\s+berth|seed|margin)\b",
    re.IGNORECASE,
)

LEAGUE_DIVISIONS: dict[str, dict[str, Any]] = {
    "basketball_nba": {
        "label": "NBA",
        "sport_tokens": ("nba", "pro basketball", "basketball_nba"),
        "divisions": (
            "Atlantic",
            "Central",
            "Southeast",
            "Northwest",
            "Pacific",
            "Southwest",
        ),
        "club_aliases": {
            "boston": "Celtics",
            "boston celtics": "Celtics",
            "brooklyn": "Nets",
            "brooklyn nets": "Nets",
            "new york": "Knicks",
            "new york knicks": "Knicks",
            "philadelphia": "76ers",
            "philadelphia 76ers": "76ers",
            "toronto": "Raptors",
            "toronto raptors": "Raptors",
            "chicago": "Bulls",
            "chicago bulls": "Bulls",
            "cleveland": "Cavaliers",
            "cleveland cavaliers": "Cavaliers",
            "detroit": "Pistons",
            "detroit pistons": "Pistons",
            "indiana": "Pacers",
            "indiana pacers": "Pacers",
            "milwaukee": "Bucks",
            "milwaukee bucks": "Bucks",
            "atlanta": "Hawks",
            "atlanta hawks": "Hawks",
            "charlotte": "Hornets",
            "charlotte hornets": "Hornets",
            "miami": "Heat",
            "miami heat": "Heat",
            "orlando": "Magic",
            "orlando magic": "Magic",
            "washington": "Wizards",
            "washington wizards": "Wizards",
            "denver": "Nuggets",
            "denver nuggets": "Nuggets",
            "minnesota": "Timberwolves",
            "minnesota timberwolves": "Timberwolves",
            "oklahoma city": "Thunder",
            "oklahoma city thunder": "Thunder",
            "portland": "Trail Blazers",
            "portland trail blazers": "Trail Blazers",
            "utah": "Jazz",
            "utah jazz": "Jazz",
            "golden state": "Warriors",
            "golden state warriors": "Warriors",
            "los angeles clippers": "Clippers",
            "la clippers": "Clippers",
            "los angeles lakers": "Lakers",
            "la lakers": "Lakers",
            "phoenix": "Suns",
            "phoenix suns": "Suns",
            "sacramento": "Kings",
            "sacramento kings": "Kings",
            "dallas": "Mavericks",
            "dallas mavericks": "Mavericks",
            "houston": "Rockets",
            "houston rockets": "Rockets",
            "memphis": "Grizzlies",
            "memphis grizzlies": "Grizzlies",
            "new orleans": "Pelicans",
            "new orleans pelicans": "Pelicans",
            "san antonio": "Spurs",
            "san antonio spurs": "Spurs",
        },
    },
    "icehockey_nhl": {
        "label": "NHL",
        "sport_tokens": ("nhl", "pro hockey", "icehockey_nhl"),
        "divisions": ("Atlantic", "Metropolitan", "Central", "Pacific"),
        "club_aliases": {
            "boston bruins": "Bruins",
            "buffalo sabres": "Sabres",
            "detroit red wings": "Red Wings",
            "florida panthers": "Panthers",
            "montreal canadiens": "Canadiens",
            "ottawa senators": "Senators",
            "tampa bay lightning": "Lightning",
            "toronto maple leafs": "Maple Leafs",
            "carolina hurricanes": "Hurricanes",
            "columbus blue jackets": "Blue Jackets",
            "new jersey devils": "Devils",
            "new york islanders": "Islanders",
            "new york rangers": "Rangers",
            "philadelphia flyers": "Flyers",
            "pittsburgh penguins": "Penguins",
            "washington capitals": "Capitals",
            "chicago blackhawks": "Blackhawks",
            "colorado avalanche": "Avalanche",
            "dallas stars": "Stars",
            "minnesota wild": "Wild",
            "nashville predators": "Predators",
            "st. louis blues": "Blues",
            "st louis blues": "Blues",
            "utah hockey club": "Utah HC",
            "winnipeg jets": "Jets",
            "anaheim ducks": "Ducks",
            "calgary flames": "Flames",
            "edmonton oilers": "Oilers",
            "los angeles kings": "Kings",
            "san jose sharks": "Sharks",
            "seattle kraken": "Kraken",
            "vancouver canucks": "Canucks",
            "vegas golden knights": "Golden Knights",
        },
    },
    "americanfootball_nfl": {
        "label": "NFL",
        "sport_tokens": ("nfl", "pro football", "americanfootball_nfl"),
        "divisions": (
            "AFC East",
            "AFC North",
            "AFC South",
            "AFC West",
            "NFC East",
            "NFC North",
            "NFC South",
            "NFC West",
        ),
        "club_aliases": {
            "buffalo": "Bills",
            "buffalo bills": "Bills",
            "miami": "Dolphins",
            "miami dolphins": "Dolphins",
            "new england": "Patriots",
            "new england patriots": "Patriots",
            "new york jets": "Jets",
            "baltimore": "Ravens",
            "baltimore ravens": "Ravens",
            "cincinnati": "Bengals",
            "cincinnati bengals": "Bengals",
            "cleveland": "Browns",
            "cleveland browns": "Browns",
            "pittsburgh": "Steelers",
            "pittsburgh steelers": "Steelers",
            "houston": "Texans",
            "houston texans": "Texans",
            "indianapolis": "Colts",
            "indianapolis colts": "Colts",
            "jacksonville": "Jaguars",
            "jacksonville jaguars": "Jaguars",
            "tennessee": "Titans",
            "tennessee titans": "Titans",
            "denver": "Broncos",
            "denver broncos": "Broncos",
            "kansas city": "Chiefs",
            "kansas city chiefs": "Chiefs",
            "las vegas": "Raiders",
            "las vegas raiders": "Raiders",
            "los angeles chargers": "Chargers",
            "dallas": "Cowboys",
            "dallas cowboys": "Cowboys",
            "new york giants": "Giants",
            "philadelphia": "Eagles",
            "philadelphia eagles": "Eagles",
            "washington": "Commanders",
            "washington commanders": "Commanders",
            "chicago": "Bears",
            "chicago bears": "Bears",
            "detroit": "Lions",
            "detroit lions": "Lions",
            "green bay": "Packers",
            "green bay packers": "Packers",
            "minnesota": "Vikings",
            "minnesota vikings": "Vikings",
            "atlanta": "Falcons",
            "atlanta falcons": "Falcons",
            "carolina": "Panthers",
            "carolina panthers": "Panthers",
            "new orleans": "Saints",
            "new orleans saints": "Saints",
            "tampa bay": "Buccaneers",
            "tampa bay buccaneers": "Buccaneers",
            "arizona": "Cardinals",
            "arizona cardinals": "Cardinals",
            "los angeles rams": "Rams",
            "san francisco": "49ers",
            "san francisco 49ers": "49ers",
            "seattle": "Seahawks",
            "seattle seahawks": "Seahawks",
        },
    },
}


@dataclass(frozen=True)
class DivisionStanding:
    division: str
    leader_club: str
    leader_probability: float
    runner_up_club: Optional[str]
    runner_up_probability: Optional[float]
    gap_points: float
    primary_market_id: int
    contributing_market_ids: tuple[int, ...]
    blend_rule: str
    primary_card: dict[str, Any]


def _assert_clean_copy(text: str) -> str:
    cleaned = " ".join(str(text or "").split())
    if _FORBIDDEN_COPY_RE.search(cleaned):
        raise ValueError(f"Forbidden copy token in reader text: {cleaned!r}")
    return cleaned


def _norm(s: Any) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s.]", " ", str(s or "").lower())).strip()


def _canonical_club(raw_name: Any, aliases: Mapping[str, str]) -> Optional[str]:
    normed = _norm(raw_name)
    if not normed or normed in {"other", "field", "tie", "none"}:
        return None
    if normed in aliases:
        return aliases[normed]
    raw_clean = str(raw_name or "").strip()
    return raw_clean if raw_clean else None


def _match_league_and_division(
    market: Mapping[str, Any],
    sport_key: str,
) -> Optional[str]:
    cfg = LEAGUE_DIVISIONS.get(sport_key)
    if cfg is None:
        return None
    title = str(market.get("name") or market.get("title") or "").strip()
    if not title or _NON_WINNER_SUBTYPE_RE.search(title):
        return None
    title_low = title.lower()
    if "division" not in title_low and not any(
        d.lower() in title_low and ("champion" in title_low or "winner" in title_low)
        for d in cfg["divisions"]
    ):
        return None
    if not any(tok in title_low for tok in ("winner", "champion", "win the")):
        return None

    sport_col = str(
        market.get("sport") or market.get("llm_sport_category") or market.get("category") or ""
    ).lower()
    haystack = f"{title_low} {sport_col}"
    if not any(tok in haystack for tok in cfg["sport_tokens"]):
        return None

    for div in cfg["divisions"]:
        div_low = div.lower()
        if re.search(rf"\b{re.escape(div_low)}\b", title_low):
            return div
    return None


def _extract_priced_clubs(
    market: Mapping[str, Any],
    aliases: Mapping[str, str],
) -> dict[str, float]:
    status = str(market.get("status") or "open").strip().lower()
    if status != "open":
        return {}
    clubs: dict[str, float] = {}
    for out in market.get("outcomes") or ():
        if not isinstance(out, Mapping):
            continue
        club = _canonical_club(out.get("name"), aliases)
        if not club:
            continue
        prob_raw = out.get("probability")
        if prob_raw is None:
            continue
        try:
            p = float(prob_raw)
        except (TypeError, ValueError):
            continue
        if not (0.0 < p <= 1.0):
            continue
        if club not in clubs or p > clubs[club]:
            clubs[club] = p
    return clubs


def _resolve_single_division(
    division: str,
    source_markets: Sequence[Mapping[str, Any]],
    aliases: Mapping[str, str],
) -> Optional[DivisionStanding]:
    by_source: dict[str, tuple[Mapping[str, Any], dict[str, float]]] = {}
    for m in source_markets:
        src = str(m.get("source") or "").strip().lower()
        if not src:
            continue
        clubs = _extract_priced_clubs(m, aliases)
        if len(clubs) < 2:
            continue
        # Keep the richest market per source
        if src not in by_source or len(clubs) > len(by_source[src][1]):
            by_source[src] = (m, clubs)

    if not by_source:
        return None

    sources_sorted = sorted(by_source.keys())
    all_clubs: set[str] = set()
    for _, clubs in by_source.values():
        all_clubs.update(clubs.keys())

    blended_clubs: list[tuple[str, float, str]] = []
    for club in sorted(all_clubs):
        rows_for_blend = [
            {"source": src, "probability": by_source[src][1][club]}
            for src in sources_sorted
            if club in by_source[src][1]
        ]
        if len(rows_for_blend) >= 2:
            val, divergence, rule_name = blend_with_verdict(rows_for_blend)
            if divergence is not None or rule_name == "divergence_gate" or val is None:
                # 40+ pt cross-source disagreement refuses the division (never print a bad blend)
                return None
            blended_clubs.append((club, float(val), rule_name))
        elif len(by_source) == 1:
            blended_clubs.append((club, float(rows_for_blend[0]["probability"]), "single_source"))

    if len(blended_clubs) < 2:
        return None

    blended_clubs.sort(key=lambda item: (-item[1], item[0]))
    leader_club, leader_prob, lead_rule = blended_clubs[0]
    runner_club, runner_prob, _ = blended_clubs[1]
    gap_pts = round((leader_prob - runner_prob) * 100.0, 1)

    primary_src = "kalshi" if "kalshi" in by_source else sources_sorted[0]
    primary_market = dict(by_source[primary_src][0])
    primary_id = int(primary_market["id"])
    contrib_ids = tuple(sorted(int(by_source[s][0]["id"]) for s in sources_sorted))

    return DivisionStanding(
        division=division,
        leader_club=leader_club,
        leader_probability=leader_prob,
        runner_up_club=runner_club,
        runner_up_probability=runner_prob,
        gap_points=gap_pts,
        primary_market_id=primary_id,
        contributing_market_ids=contrib_ids,
        blend_rule=lead_rule,
        primary_card=primary_market,
    )


def _compose_context_line(
    league_label: str,
    card_standings: Sequence[DivisionStanding],
    all_standings: Sequence[DivisionStanding],
) -> str:
    total_n = len(all_standings)
    shown_n = len(card_standings)
    first = card_standings[0]
    first_pct = int(round(first.leader_probability * 100))
    if shown_n < total_n:
        second = card_standings[1]
        second_pct = int(round(second.leader_probability * 100))
        text = (
            f"{shown_n} tightest of {total_n} {league_label} division races, ordered by "
            f"closest lead — {first.leader_club} ({first_pct}% in {first.division}) and "
            f"{second.leader_club} ({second_pct}% in {second.division}) sit tightest."
        )
    else:
        last = card_standings[-1]
        last_pct = int(round(last.leader_probability * 100))
        text = (
            f"All {total_n} {league_label} division front-runners, ordered from closest "
            f"race ({first.leader_club} {first_pct}% in {first.division}) to clearest "
            f"favorite ({last.leader_club} {last_pct}% in {last.division})."
        )
    return _assert_clean_copy(text)


def select_league_division_races(
    markets: Sequence[Mapping[str, Any]],
    *,
    sport: str = "basketball_nba",
    min_divisions: int = 4,
    max_card_rows: int = 4,
) -> RoundupMembers | RoundupRefusal:
    cfg = LEAGUE_DIVISIONS.get(sport)
    if cfg is None:
        return RoundupRefusal([("unsupported_sport", sport)])

    grouped: dict[str, list[Mapping[str, Any]]] = {d: [] for d in cfg["divisions"]}
    for m in markets:
        if not isinstance(m, Mapping) or not isinstance(m.get("id"), int):
            continue
        div = _match_league_and_division(m, sport)
        if div is not None:
            grouped[div].append(m)

    standings: list[DivisionStanding] = []
    for div in cfg["divisions"]:
        if not grouped[div]:
            continue
        resolved = _resolve_single_division(div, grouped[div], cfg["club_aliases"])
        if resolved is not None:
            standings.append(resolved)

    if len(standings) < max(2, int(min_divisions)):
        return RoundupRefusal(
            [("insufficient_divisions", sport, len(standings), int(min_divisions))]
        )

    # Order from tightest race (smallest leader-to-runner-up gap, then closest to 50%)
    # to clearest runaway favorite.
    standings.sort(
        key=lambda s: (s.gap_points, abs(s.leader_probability - 0.5), s.division)
    )
    card_standings = standings[: max(2, int(max_card_rows))]
    league_label = str(cfg["label"])
    context_line = _compose_context_line(league_label, card_standings, standings)
    footer = _assert_clean_copy(
        f"One winner per division · {len(card_standings)} of {len(standings)} "
        f"{league_label} divisions shown"
        if len(card_standings) < len(standings)
        else f"One winner per division · all {len(standings)} {league_label} divisions"
    )

    rows: list[dict[str, Any]] = []
    for s in card_standings:
        pct = int(round(s.leader_probability * 100))
        sub = (
            f"{s.runner_up_club} {int(round(s.runner_up_probability * 100))}%"
            if s.runner_up_club and s.runner_up_probability is not None
            else None
        )
        row: dict[str, Any] = {
            "market_id": s.primary_market_id,
            "label": _assert_clean_copy(f"{s.division} · {s.leader_club}"),
            "division": s.division,
            "leader": s.leader_club,
            "probability": round(s.leader_probability, 4),
            "rendered_percent": pct,
            "gap_points": s.gap_points,
            "destination": market_destination(s.primary_market_id),
        }
        if sub:
            row["runner_up_label"] = _assert_clean_copy(sub)
        rows.append(row)

    members = [
        {
            "id": s.primary_market_id,
            "type": "futures",
            "card": dict(s.primary_card),
        }
        for s in standings
    ]
    rev_ids: list[int] = []
    for s in standings:
        for mid in s.contributing_market_ids:
            if mid not in rev_ids:
                rev_ids.append(mid)

    title = _assert_clean_copy(f"{league_label} division races")
    kicker = _assert_clean_copy(f"{league_label} · DIVISIONS")
    feed_stub = {
        "score": 92.0,
        "context_line": context_line,
    }
    return RoundupMembers(
        members=members,
        rows=rows,
        footer=footer,
        count_line=f"{len(standings)} divisions",
        title=title,
        kicker=kicker,
        revision_ids=rev_ids,
        feed_item=None,
        sections=(
            {
                "title": f"All {len(standings)} {league_label} divisions",
                "context_line": context_line,
                "member_ids": [s.primary_market_id for s in standings],
            },
        ),
    )


async def produce_league_division_races(
    db: Any,
    *,
    rule: Optional[Mapping[str, Any]] = None,
    now: Optional[datetime] = None,
) -> RoundupMembers | RoundupRefusal:
    _ = now or datetime.now(timezone.utc)
    cfg_rule = dict(rule or {})
    sport = str(cfg_rule.get("sport") or "basketball_nba")
    min_divs = int(cfg_rule.get("min_divisions") or 4)
    max_rows = int(cfg_rule.get("max_card_rows") or 4)

    if isinstance(db, (list, tuple)):
        return select_league_division_races(
            db, sport=sport, min_divisions=min_divs, max_card_rows=max_rows
        )

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import selectinload

    if not isinstance(db, AsyncSession):
        return RoundupRefusal([("unsupported_session", type(db).__name__)])

    from app.models.models import FuturesMarket

    stmt = (
        select(FuturesMarket)
        .options(selectinload(FuturesMarket.outcomes))
        .where(
            FuturesMarket.status == "open",
            FuturesMarket.name.ilike("%division%"),
        )
    )
    res = await db.execute(stmt)
    orm_rows = res.scalars().all()
    serialized = [
        {
            "id": int(m.id),
            "name": m.name,
            "status": m.status,
            "source": m.source,
            "sport": getattr(m, "sport", None),
            "category": m.category,
            "llm_sport_category": m.llm_sport_category,
            "outcomes": [
                {"name": o.name, "probability": o.probability}
                for o in (m.outcomes or [])
            ],
        }
        for m in orm_rows
    ]
    return select_league_division_races(
        serialized, sport=sport, min_divisions=min_divs, max_card_rows=max_rows
    )


def load_candidate_definition(
    path: Path = CANDIDATE_NBA_DIVISION_RACES_PATH,
) -> dict[str, Any]:
    defn = json.loads(path.read_text(encoding="utf-8"))
    validate_roundup_definition(defn)
    return defn


def build_league_division_races_producer(
    defn: Optional[Mapping[str, Any]] = None,
) -> RoundupProducer:
    resolved = dict(defn) if defn is not None else load_candidate_definition()
    validate_roundup_definition(resolved)
    rule = dict(resolved.get("rule") or {})

    async def _produce(db: Any) -> RoundupMembers | RoundupRefusal:
        return await produce_league_division_races(db, rule=rule)

    return RoundupProducer(
        slug=str(resolved["slug"]),
        name=str(resolved["name"]),
        kind=str(resolved.get("kind") or "roundup"),
        category=str(resolved["category"]),
        section_title=str(resolved["section_title"]),
        footer=str(resolved["footer"]),
        produce=_produce,
        membership=str(resolved.get("membership") or PRODUCER_KIND_LEAGUE_DIVISION_RACES),
        relations=tuple(resolved["relations"]),
        level=str(resolved["level"]),
        rule=rule,
        tag=resolved.get("tag"),
        kicker=str(resolved.get("kicker") or "DIVISIONS"),
        score=float(resolved.get("score") or 92.0),
    )


def compose_division_races_card_and_container(
    producer: RoundupProducer,
    members: RoundupMembers,
) -> tuple[dict[str, Any], dict[str, Any]]:
    feed_item = compose_roundup_feed_item(producer, members)
    container = compose_roundup_container(producer, members)
    if feed_item is None:
        raise ValueError("Expected non-empty RoundupMembers for feed_item composition")
    context_line = ""
    if members.sections and isinstance(members.sections[0], Mapping):
        context_line = str(members.sections[0].get("context_line") or "")
    context_line = _assert_clean_copy(context_line)
    feed_item["context_summary"] = context_line
    feed_item["data"]["roundup"]["context_line"] = context_line
    container["context_line"] = context_line
    return feed_item, container


def build_division_races_grading_candidate(
    producer: RoundupProducer,
    members: RoundupMembers,
) -> dict[str, Any]:
    """Return a ``/grade/groupings``-compatible candidate item (proposed_card + best_single)."""
    feed_item, _ = compose_division_races_card_and_container(producer, members)
    roundup = feed_item["data"]["roundup"]
    rows = list(roundup["rows"])
    best_row = min(rows, key=lambda r: abs(float(r["probability"]) - 0.5))
    return {
        "item_key": producer.slug,
        "kind": PRODUCER_KIND_LEAGUE_DIVISION_RACES,
        "kind_verdict": "serve",
        "licence_status": "HELD",
        "reader_reachable": False,
        "proposed_card": {
            "slug": producer.slug,
            "title": feed_item["data"]["title"],
            "kicker": roundup["kicker"],
            "context_line": roundup["context_line"],
            "rows": rows,
            "footer": roundup["footer"],
        },
        "best_single": {
            "id": int(best_row["market_id"]),
            "name": str(best_row["label"]),
            "subject": str(best_row["leader"]),
            "rendered_percent": int(best_row["rendered_percent"]),
        },
    }
