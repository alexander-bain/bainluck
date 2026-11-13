"""Dynamic ``headliners_and_hosts`` grouped-card producer (#12288 Wave 1, Idea #11).

PILLAR: DISCOVER · MATCHING · TRUTH
SHIP: Stage, halftime, festival, and casting contender container (e.g., 2027 Big
Game Halftime Show performers, festival headliners, ceremony hosts, major film
casting) that preserves non-normalized independent probabilities whenever
multiple performers/guests can appear (outcome sum > 1.15 or
``mutually_exclusive is False``), blends cross-source performer twins via
``futures_source_merge.blend_with_verdict``, and states explicitly in
``context_line`` whether multiple artists can appear or one choice settles Yes.

Publication gate: candidate definition lives in ``backend/data/discover/candidates/``
and is NOT registered in ``ROUNDUP_PRODUCERS`` until licensed via the Discover
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
    "CANDIDATE_HEADLINERS_AND_HOSTS_PATH",
    "PRODUCER_KIND_HEADLINERS_AND_HOSTS",
    "StageContender",
    "build_headliners_and_hosts_grading_candidate",
    "build_headliners_and_hosts_producer",
    "compose_headliners_card_and_container",
    "load_candidate_definition",
    "produce_headliners_and_hosts",
    "select_headliners_and_hosts",
]

PRODUCER_KIND_HEADLINERS_AND_HOSTS = "headliners_and_hosts"

CANDIDATE_HEADLINERS_AND_HOSTS_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "discover"
    / "candidates"
    / "roundup-headliners-and-hosts.json"
)

_FORBIDDEN_COPY_RE = re.compile(
    r"\b(?:questions?|stale|venues?|kalshi|polymarket|opened)\b",
    re.IGNORECASE,
)

_STAGE_FAMILY_PATTERNS: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    (
        "big_game_halftime_performers",
        "2027 Big Game halftime stage",
        re.compile(
            r"(?:big\s+game\s+halftime\s+show|championship\s+halftime\s+show)(?!.*song)",
            re.IGNORECASE,
        ),
    ),
    (
        "ceremony_host",
        "Ceremony host contenders",
        re.compile(
            r"\b(?:host\s+the\s+\d*(?:st|nd|rd|th)?\s*(?:oscars|academy\s+awards|grammys|emmys|golden\s+globes)|oscars\s+host)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "festival_headliners",
        "Festival headliner watch",
        re.compile(r"\b(?:coachella|glastonbury|lollapalooza)\b.*\bheadlin", re.IGNORECASE),
    ),
)

_ARTIST_ALIASES: dict[str, str] = {
    "jay z": "JAY-Z",
    "jay-z": "JAY-Z",
    "beyonce": "Beyoncé",
    "beyoncé": "Beyoncé",
    "pharrell": "Pharrell Williams",
    "pharrell williams": "Pharrell Williams",
    "miley cyrus": "Miley Cyrus",
    "justin bieber": "Justin Bieber",
    "kendrick lamar": "Kendrick Lamar",
    "rihanna": "Rihanna",
    "taylor swift": "Taylor Swift",
}


@dataclass(frozen=True)
class StageContender:
    artist: str
    probability: float
    primary_market_id: int


def _assert_clean_copy(text: str) -> str:
    cleaned = " ".join(str(text or "").split())
    if _FORBIDDEN_COPY_RE.search(cleaned):
        raise ValueError(f"Forbidden copy token in reader text: {cleaned!r}")
    return cleaned


def _canonical_artist(raw: Any) -> Optional[str]:
    cleaned = re.sub(r"\s+", " ", str(raw or "").strip())
    low = cleaned.lower()
    if not low or low in {"other", "none", "field", "yes", "no"}:
        return None
    return _ARTIST_ALIASES.get(low, cleaned)


def _match_stage_family(
    market: Mapping[str, Any],
    family_key: str,
) -> Optional[str]:
    title = str(market.get("name") or market.get("title") or "").strip()
    if not title:
        return None
    for key, card_title, pat in _STAGE_FAMILY_PATTERNS:
        if key == family_key and pat.search(title):
            return card_title
    return None


def select_headliners_and_hosts(
    markets: Sequence[Mapping[str, Any]],
    *,
    family: str = "big_game_halftime_performers",
    min_contenders: int = 3,
    max_card_rows: int = 5,
    min_prob: float = 0.05,
    max_prob: float = 0.995,
) -> RoundupMembers | RoundupRefusal:
    matched_markets: list[Mapping[str, Any]] = []
    card_title = "Headliners & hosts"
    for m in markets:
        if not isinstance(m, Mapping) or not isinstance(m.get("id"), int):
            continue
        if str(m.get("status") or "open").strip().lower() != "open":
            continue
        matched_title = _match_stage_family(m, family)
        if matched_title is not None:
            card_title = matched_title
            matched_markets.append(m)

    if not matched_markets:
        return RoundupRefusal([("no_matching_stage_family", family)])

    by_source: dict[str, tuple[Mapping[str, Any], dict[str, float], bool]] = {}
    for m in matched_markets:
        src = str(m.get("source") or "").strip().lower()
        if not src:
            continue
        artists: dict[str, float] = {}
        raw_sum = 0.0
        for out in m.get("outcomes") or ():
            if not isinstance(out, Mapping):
                continue
            art = _canonical_artist(out.get("name"))
            if not art:
                continue
            p_raw = out.get("probability")
            if p_raw is None:
                continue
            try:
                p = float(p_raw)
            except (TypeError, ValueError):
                continue
            if p <= 0.0 or p > 1.0:
                continue
            raw_sum += p
            if art not in artists or p > artists[art]:
                artists[art] = p
        if not artists:
            continue
        multi_appear = (m.get("mutually_exclusive") is False) or (raw_sum > 1.15)
        if src not in by_source or len(artists) > len(by_source[src][1]):
            by_source[src] = (m, artists, multi_appear)

    if not by_source:
        return RoundupRefusal([("no_priced_contenders", family)])

    sources_sorted = sorted(by_source.keys())
    multi_appearance = any(info[2] for info in by_source.values())
    primary_src = "kalshi" if "kalshi" in by_source else sources_sorted[0]
    primary_market = dict(by_source[primary_src][0])
    primary_id = int(primary_market["id"])
    contrib_ids = [int(by_source[s][0]["id"]) for s in sources_sorted]

    all_artists: set[str] = set()
    for _, art_map, _ in by_source.values():
        all_artists.update(art_map.keys())

    contenders: list[StageContender] = []
    for artist in sorted(all_artists):
        rows_for_blend = [
            {"source": s, "probability": by_source[s][1][artist]}
            for s in sources_sorted
            if artist in by_source[s][1]
        ]
        if len(rows_for_blend) >= 2:
            val, divergence, rule_name = blend_with_verdict(rows_for_blend)
            if divergence is not None or rule_name == "divergence_gate" or val is None:
                continue
            prob = float(val)
        else:
            src_only = rows_for_blend[0]["source"]
            prob = float(rows_for_blend[0]["probability"])
            mkt_id = int(by_source[src_only][0]["id"])
            if min_prob <= prob <= max_prob:
                contenders.append(StageContender(artist=artist, probability=prob, primary_market_id=mkt_id))
            continue

        if min_prob <= prob <= max_prob:
            contenders.append(StageContender(artist=artist, probability=prob, primary_market_id=primary_id))

    if len(contenders) < max(2, int(min_contenders)):
        return RoundupRefusal([("insufficient_contenders", len(contenders), int(min_contenders))])

    # Never normalize independent chances to 100%!
    contenders.sort(key=lambda c: (-c.probability, c.artist))
    shown = contenders[: max(2, int(max_card_rows))]
    top = shown[0]
    if multi_appearance:
        context_line = _assert_clean_copy(
            f"Artists priced at {int(round(min_prob * 100))}% or higher to appear on the "
            f"{card_title} — multiple guests can share the stage, so chances are independent "
            f"and do not add to 100%."
        )
        footer = _assert_clean_copy(
            f"Independent appearance chances · multiple performers can settle Yes"
        )
    else:
        context_line = _assert_clean_copy(
            f"Leading contenders for {card_title}, ordered by current chance — "
            f"{top.artist} leads at {int(round(top.probability * 100))}% and one choice settles Yes."
        )
        footer = _assert_clean_copy("Single-winner market · chances sum to 100%")

    rows = [
        {
            "market_id": c.primary_market_id,
            "label": _assert_clean_copy(c.artist),
            "artist": c.artist,
            "probability": round(c.probability, 4),
            "rendered_percent": int(round(c.probability * 100)),
            "independent": multi_appearance,
            "destination": market_destination(c.primary_market_id),
        }
        for c in shown
    ]
    members = [
        {"id": int(by_source[s][0]["id"]), "type": "futures", "card": dict(by_source[s][0])}
        for s in sources_sorted
    ]
    return RoundupMembers(
        members=members,
        rows=rows,
        footer=footer,
        count_line=f"{len(contenders)} contenders",
        title=_assert_clean_copy(card_title),
        kicker="CULTURE · STAGE & CASTING",
        revision_ids=contrib_ids,
        sections=(
            {
                "title": f"All {card_title} contenders",
                "context_line": context_line,
                "member_ids": contrib_ids,
            },
        ),
    )


async def produce_headliners_and_hosts(
    db: Any,
    *,
    rule: Optional[Mapping[str, Any]] = None,
    now: Optional[datetime] = None,
) -> RoundupMembers | RoundupRefusal:
    _ = now or datetime.now(timezone.utc)
    cfg_rule = dict(rule or {})
    if isinstance(db, (list, tuple)):
        return select_headliners_and_hosts(
            db,
            family=str(cfg_rule.get("family") or "big_game_halftime_performers"),
            min_contenders=int(cfg_rule.get("min_contenders") or 3),
            max_card_rows=int(cfg_rule.get("max_card_rows") or 5),
            min_prob=float(cfg_rule.get("min_prob") or 0.05),
            max_prob=float(cfg_rule.get("max_prob") or 0.995),
        )
    return RoundupRefusal([("unsupported_session", type(db).__name__)])


def load_candidate_definition(
    path: Path = CANDIDATE_HEADLINERS_AND_HOSTS_PATH,
) -> dict[str, Any]:
    defn = json.loads(path.read_text(encoding="utf-8"))
    validate_roundup_definition(defn)
    return defn


def build_headliners_and_hosts_producer(
    defn: Optional[Mapping[str, Any]] = None,
) -> RoundupProducer:
    resolved = dict(defn) if defn is not None else load_candidate_definition()
    validate_roundup_definition(resolved)
    rule = dict(resolved.get("rule") or {})

    async def _produce(db: Any) -> RoundupMembers | RoundupRefusal:
        return await produce_headliners_and_hosts(db, rule=rule)

    return RoundupProducer(
        slug=str(resolved["slug"]),
        name=str(resolved["name"]),
        kind=str(resolved.get("kind") or "roundup"),
        category=str(resolved["category"]),
        section_title=str(resolved["section_title"]),
        footer=str(resolved["footer"]),
        produce=_produce,
        membership=str(resolved.get("membership") or PRODUCER_KIND_HEADLINERS_AND_HOSTS),
        relations=tuple(resolved["relations"]),
        level=str(resolved["level"]),
        rule=rule,
        tag=resolved.get("tag"),
        kicker=str(resolved.get("kicker") or "CULTURE · STAGE & CASTING"),
        score=float(resolved.get("score") or 91.0),
    )


def compose_headliners_card_and_container(
    producer: RoundupProducer,
    members: RoundupMembers,
) -> tuple[dict[str, Any], dict[str, Any]]:
    feed_item = compose_roundup_feed_item(producer, members)
    container = compose_roundup_container(producer, members)
    if feed_item is None:
        raise ValueError("Expected non-empty RoundupMembers")
    context_line = _assert_clean_copy(str(members.sections[0].get("context_line") or ""))
    feed_item["context_summary"] = context_line
    feed_item["data"]["roundup"]["context_line"] = context_line
    container["context_line"] = context_line
    return feed_item, container


def build_headliners_and_hosts_grading_candidate(
    producer: RoundupProducer,
    members: RoundupMembers,
) -> dict[str, Any]:
    feed_item, _ = compose_headliners_card_and_container(producer, members)
    roundup = feed_item["data"]["roundup"]
    rows = list(roundup["rows"])
    best_row = min(rows, key=lambda r: abs(float(r["probability"]) - 0.5))
    return {
        "item_key": producer.slug,
        "kind": PRODUCER_KIND_HEADLINERS_AND_HOSTS,
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
            "subject": str(best_row["artist"]),
            "rendered_percent": int(best_row["rendered_percent"]),
        },
    }
