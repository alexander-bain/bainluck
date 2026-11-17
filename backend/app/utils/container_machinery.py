"""Topic-free grouping & container machinery (`#12288`, Direction 223 & Decision 224).

PILLAR: DISCOVER · FORMATTING · MATCHING · TRUTH
SHIP: One declarative definition produces BOTH the Discover card and the multi-section
container page, with zero hand-placed market or event IDs, choosing each section's
visual form automatically from the shape of its numbers and attaching verified
subject imagery (team crests, athlete headshots, film posters, candidate portraits,
or deterministic monograms — never stock photos).

Publication gate: candidate definitions live in ``backend/data/discover/candidates/``
and ``container_machinery_enabled()`` defaults to ``False`` until turned on by Fable/Alex.
"""

from __future__ import annotations

import copy
import json
import math
import os
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from app.utils.container_presentation import (
    MEMBER_EVENT,
    MEMBER_MARKET,
    event_destination,
    market_destination,
)

__all__ = [
    "CANDIDATE_2028_PRESIDENTIAL_PATH",
    "CANDIDATE_FED_AND_MACRO_PATH",
    "CANDIDATE_NFL_WEEK_PATH",
    "CANDIDATE_OSCARS_BEST_PICTURE_PATH",
    "MACHINERY_CANDIDATE_PATHS",
    "MACHINERY_FORM_IDS",
    "PRODUCER_KIND_CONTAINER_MACHINERY",
    "SubjectArtResolver",
    "build_container_machinery_producer",
    "choose_section_form",
    "compute_visual_diversity_report",
    "container_machinery_enabled",
    "discover_machinery_candidate_paths",
    "evaluate_machinery_candidates_preview",
    "is_machinery_candidate_slug",
    "load_machinery_definition",
    "produce_container_machinery",
    "register_machinery_slice1_candidates",
    "serve_machinery_candidate_preview",
]

PRODUCER_KIND_CONTAINER_MACHINERY = "container_machinery"

MACHINERY_FORM_IDS: frozenset[str] = frozenset(
    {
        "paired_stage_bars",
        "coin_flip_matchups",
        "matchup_slate",
        "duel_bar",
        "contender_spotlight",
        "sibling_fields_grid",
        "benchmark_strip",
    }
)

_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_CANDIDATES_DIR = _DATA_DIR / "groupings" / "candidates"
_VERIFIED_ART_PATH = _DATA_DIR / "discover" / "verified_discover_art.json"
_PAIRED_REGISTER_PATH = _DATA_DIR / "groupings" / "paired_metric_register.json"
_SUBJECT_ART_PATH = _DATA_DIR / "groupings" / "machinery_subject_art.json"

CANDIDATE_NFL_WEEK_PATH = _CANDIDATES_DIR / "machinery-nfl-week.json"
CANDIDATE_OSCARS_BEST_PICTURE_PATH = _CANDIDATES_DIR / "machinery-oscars-best-picture.json"
CANDIDATE_2028_PRESIDENTIAL_PATH = _CANDIDATES_DIR / "machinery-2028-presidential.json"
CANDIDATE_FED_AND_MACRO_PATH = _CANDIDATES_DIR / "machinery-fed-and-macro.json"

MACHINERY_CANDIDATE_PATHS: tuple[Path, ...] = (
    CANDIDATE_NFL_WEEK_PATH,
    CANDIDATE_OSCARS_BEST_PICTURE_PATH,
    CANDIDATE_2028_PRESIDENTIAL_PATH,
)

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_PLACEHOLDER_OUTCOME_RE = re.compile(
    r"^(?:other|any\s+other|field|none(?:\s+of\s+the\s+above)?|someone\s+else|tbd)$",
    re.IGNORECASE,
)
_LOWER_PROPER_NAME_RE = re.compile(r"^[A-Z][a-z'’-]+(?:\s+[A-Za-z'’-]+)+$")
_NON_NAME_TAIL_WORDS: frozenset[str] = frozenset(
    {
        "party",
        "maintains",
        "rate",
        "rates",
        "cuts",
        "cut",
        "hikes",
        "hike",
        "holds",
        "hold",
        "wins",
        "win",
        "of",
        "the",
        "in",
        "and",
        "to",
        "for",
        "at",
        "by",
        "or",
    }
)
_FORBIDDEN_COPY_QUESTION_RE = re.compile(r"\bquestions?\b", re.IGNORECASE)


def _proper_case_outcome_label(label: str) -> str:
    """Capitalize miscased proper names (e.g. ``'Anne hathaway'`` -> ``'Anne Hathaway'``)
    without altering numeric brackets, units, or plain sentence outcomes."""
    trimmed = label.strip()
    if not _LOWER_PROPER_NAME_RE.match(trimmed):
        return trimmed
    parts = trimmed.split(" ")
    if any(p.lower() in _NON_NAME_TAIL_WORDS for p in parts[1:]):
        return trimmed
    fixed: list[str] = [parts[0]]
    for tok in parts[1:]:
        if len(tok) >= 2 and tok.islower():
            fixed.append(tok[0].upper() + tok[1:])
        else:
            fixed.append(tok)
    return " ".join(fixed)

_PALETTE_FALLBACK: tuple[str, ...] = (
    "#059669",
    "#2563EB",
    "#D97706",
    "#7C3AED",
    "#DC2626",
    "#0891B2",
)


def container_machinery_enabled() -> bool:
    """Strictly switched OFF unless explicitly enabled via env flag."""
    return os.environ.get("CONTAINER_MACHINERY_SLICE1_ENABLED", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _half_up_pct(prob: float) -> int:
    clamped = max(0.0, min(1.0, float(prob)))
    pct = int(
        (Decimal(str(clamped)) * Decimal("100")).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )
    if pct <= 0 and clamped > 0:
        return 1
    if pct >= 100 and clamped < 1:
        return 99
    return pct


def _norm_key(text: str | None) -> str:
    if not text:
        return ""
    return _NON_ALNUM_RE.sub(" ", text.lower()).strip()


def _initials(label: str) -> str:
    words = [w for w in re.split(r"\s+", label.strip()) if w]
    if not words:
        return "?"
    if len(words) == 1:
        return words[0][:2].upper()
    return (words[0][0] + words[-1][0]).upper()


def _fallback_color(label: str) -> str:
    key = _norm_key(label)
    if "democrat" in key:
        return "#2563EB"
    if "republican" in key or key == "gop":
        return "#DC2626"
    h = sum(ord(ch) for ch in key)
    return _PALETTE_FALLBACK[h % len(_PALETTE_FALLBACK)]


class SubjectArtResolver:
    """Unified verified-art resolver across teams, people, and films/series (#12659, #12850)."""

    def __init__(self) -> None:
        self._by_norm: dict[str, dict[str, Any]] = {}
        self._load_catalogs()

    def _register(self, aliases: Sequence[str], record: dict[str, Any]) -> None:
        for raw in aliases:
            nk = _norm_key(raw)
            if nk and nk not in self._by_norm:
                self._by_norm[nk] = record

    def _load_catalogs(self) -> None:
        # 1. Dedicated machinery subject art (ESPN headshots, NFL crests, verified Commons portraits)
        if _SUBJECT_ART_PATH.exists():
            raw = json.loads(_SUBJECT_ART_PATH.read_text(encoding="utf-8"))
            for item in raw.get("subjects") or ():
                if not isinstance(item, Mapping) or not item.get("url"):
                    continue
                rec = {
                    "url": str(item["url"]),
                    "kind": str(item.get("kind") or "person"),
                    "detail": str(item.get("detail") or ""),
                    "accent_color": str(item.get("accent_color") or ""),
                    "author": item.get("author"),
                    "license": item.get("license"),
                    "source_page": item.get("source_page"),
                }
                self._register(list(item.get("aliases") or ()) + [str(item.get("key") or "")], rec)
            for team_name, meta in (raw.get("nfl_teams") or {}).items():
                if not isinstance(meta, Mapping):
                    continue
                abbr = str(meta.get("abbr") or "").lower()
                color = str(meta.get("color") or "#1E293B")
                if not abbr:
                    continue
                short_name = team_name.split()[-1]
                city_only = " ".join(team_name.split()[:-1])
                aliases = [team_name, short_name]
                if city_only and city_only not in {"New York", "Los Angeles"}:
                    aliases.append(city_only)
                self._register(
                    aliases,
                    {
                        "url": f"https://a.espncdn.com/i/teamlogos/nfl/500/{abbr}.png",
                        "kind": "team_logo",
                        "detail": abbr.upper(),
                        "accent_color": color,
                    },
                )

        # 2. Paired metric register (vetted TMDB posters/headshots & NHL/NBA/NFL logos; horror/doc-crime excluded)
        if _PAIRED_REGISTER_PATH.exists():
            pm = json.loads(_PAIRED_REGISTER_PATH.read_text(encoding="utf-8"))
            for pset in (pm.get("sets") or {}).values():
                if not isinstance(pset, Mapping):
                    continue
                for entry in pset.get("entries") or ():
                    if not isinstance(entry, Mapping):
                        continue
                    art = entry.get("art")
                    if not isinstance(art, Mapping) or not art.get("url"):
                        continue
                    if art.get("adult") is True:
                        continue
                    genres = set(art.get("genre_ids") or ())
                    if 27 in genres or {99, 80}.issubset(genres):
                        continue
                    subj = str(entry.get("subject") or "").strip()
                    if not subj:
                        continue
                    self._register(
                        [subj],
                        {
                            "url": str(art["url"]),
                            "kind": str(art.get("kind") or "tmdb_poster"),
                            "detail": str(entry.get("detail") or ""),
                            "accent_color": "#0F172A",
                        },
                    )

        # 3. Verified Discover art register (Wikimedia Commons & TVMaze vetted entries)
        if _VERIFIED_ART_PATH.exists():
            va = json.loads(_VERIFIED_ART_PATH.read_text(encoding="utf-8"))
            for entry in va.get("entries") or ():
                if not isinstance(entry, Mapping) or not entry.get("url"):
                    continue
                aliases = [str(a) for a in (entry.get("aliases") or ()) if a]
                if entry.get("entity_key"):
                    aliases.append(str(entry["entity_key"]))
                self._register(
                    aliases,
                    {
                        "url": str(entry["url"]),
                        "kind": str(entry.get("kind") or "person"),
                        "detail": str(entry.get("verified_subject") or "")[:44],
                        "accent_color": "",
                        "author": entry.get("author"),
                        "license": entry.get("license"),
                        "source_page": entry.get("source_page"),
                    },
                )

    def resolve(
        self,
        subject: str,
        *,
        explicit_url: Optional[str] = None,
        explicit_color: Optional[str] = None,
    ) -> dict[str, Any]:
        nk = _norm_key(subject)
        hit = self._by_norm.get(nk)
        url = explicit_url or (hit["url"] if hit else None)
        color = explicit_color or (hit.get("accent_color") if hit else None) or _fallback_color(subject)
        return {
            "url": url,
            "kind": (hit.get("kind") if hit else ("explicit" if url else "monogram")),
            "detail": (hit.get("detail") if hit else "") or "",
            "accent_color": color,
            "initials": _initials(subject),
        }


@lru_cache(maxsize=1)
def _default_art_resolver() -> SubjectArtResolver:
    return SubjectArtResolver()


def choose_section_form(
    atoms_kind: str,
    selected_items: Sequence[Mapping[str, Any]],
) -> str:
    """Choose a section's visual form strictly from the shape of its atoms (zero topic checks)."""
    if atoms_kind == "paired_stage":
        return "paired_stage_bars"

    if atoms_kind == "events":
        if len(selected_items) >= 2 and all(
            0.34 <= float(it.get("fav_prob") or 0.5) <= 0.66 for it in selected_items
        ):
            return "coin_flip_matchups"
        return "matchup_slate"

    if atoms_kind == "markets":
        if len(selected_items) == 1:
            outcomes = selected_items[0].get("outcomes") or ()
            if len(outcomes) == 2:
                return "duel_bar"
            if len(outcomes) >= 3:
                return "contender_spotlight"
            return "benchmark_strip"
        if len(selected_items) >= 2 and all(
            len(it.get("outcomes") or ()) >= 2 for it in selected_items
        ):
            return "sibling_fields_grid"
        return "benchmark_strip"

    return "sibling_fields_grid"


def _clean_section_market_label(name: str) -> str:
    cleaned = re.sub(
        r"^(?:NFL:\s*|Oscar\s+Winner:\s*|Oscar\s+winner:\s*|2028\s+U\.S\.\s*|2028\s+)",
        "",
        name.strip(),
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s*\?\s*$", "", cleaned)
    cleaned = re.sub(r"\s+2028$", "", cleaned)
    return cleaned.strip() or name.strip()


_CUMULATIVE_OUTCOME_RE = re.compile(
    r"^(?:above|below|over|under|at\s+least|more\s+than|fewer\s+than)\b",
    re.IGNORECASE,
)


def _market_matches_query(market: Mapping[str, Any], query: Mapping[str, Any]) -> bool:
    status = str(market.get("status") or "open").lower()
    if status not in {"open", "active"}:
        return False
    title_low = str(market.get("name") or "").lower()
    if not title_low:
        return False

    req_tokens = [str(t).lower() for t in (query.get("title_all_tokens") or ()) if str(t).strip()]
    if any(tok not in title_low for tok in req_tokens):
        return False

    any_tokens = [str(t).lower() for t in (query.get("any_tokens") or ()) if str(t).strip()]
    if any_tokens and not any(tok in title_low for tok in any_tokens):
        return False

    excl_tokens = [str(t).lower() for t in (query.get("exclude_tokens") or ()) if str(t).strip()]
    if any(tok in title_low for tok in excl_tokens):
        return False

    raw_outcomes = market.get("top_outcomes") or market.get("outcomes") or ()
    priced = [
        o
        for o in raw_outcomes
        if isinstance(o, Mapping)
        and isinstance(o.get("probability"), (int, float))
        and 0.0 < float(o["probability"]) < 1.0
        and not _PLACEHOLDER_OUTCOME_RE.match(str(o.get("name") or "").strip())
    ]
    if not priced:
        return False

    shape = str(query.get("shape") or "any").lower()
    if shape == "two_way" and len(priced) != 2:
        return False
    if shape == "field" and len(priced) < 3:
        return False
    if shape == "field" and not query.get("allow_cumulative"):
        cum_hits = sum(
            1
            for o in priced
            if _CUMULATIVE_OUTCOME_RE.match(str(o.get("name") or "").strip())
        )
        if cum_hits >= 2:
            return False
    if shape == "binary" and len(priced) > 2:
        # Binary yes/no markets carry 1 ("Yes") or 2 ("Yes"/"No") outcomes
        names = {str(o.get("name") or "").strip().lower() for o in priced}
        if not ("yes" in names or len(priced) == 1):
            return False
    if shape == "binary":
        names = {str(o.get("name") or "").strip().lower() for o in priced}
        if "yes" not in names and len(priced) != 1:
            return False

    return True


def _hydrate_market_visual_item(
    market: Mapping[str, Any],
    *,
    max_outcomes: int,
    resolver: SubjectArtResolver,
) -> dict[str, Any]:
    mid = int(market["id"])
    raw_outcomes = market.get("top_outcomes") or market.get("outcomes") or ()
    valid = [
        o
        for o in raw_outcomes
        if isinstance(o, Mapping)
        and isinstance(o.get("probability"), (int, float))
        and 0.0 < float(o["probability"]) < 1.0
        and not _PLACEHOLDER_OUTCOME_RE.match(str(o.get("name") or "").strip())
    ]
    valid.sort(key=lambda o: (-float(o["probability"]), str(o.get("name") or "").casefold()))

    shape_is_yes = (
        len(valid) <= 2
        and any(str(o.get("name") or "").strip().lower() == "yes" for o in valid)
    )
    if shape_is_yes:
        yes_row = next(
            (o for o in valid if str(o.get("name") or "").strip().lower() == "yes"),
            valid[0],
        )
        p = float(yes_row["probability"])
        outcomes_out = [
            {
                "outcome_id": int(yes_row.get("id") or (mid * 10 + 1)),
                "name": "Yes",
                "probability": p,
                "rendered_percent": _half_up_pct(p),
                "art": {
                    "url": None,
                    "kind": "none",
                    "detail": "",
                    "accent_color": "",
                    "initials": "",
                },
            }
        ]
    else:
        outcomes_out = []
        for idx, o in enumerate(valid[:max_outcomes]):
            o_name = _proper_case_outcome_label(str(o.get("name") or "").strip())
            p = float(o["probability"])
            art = resolver.resolve(
                o_name,
                explicit_url=(str(o["image_url"]) if o.get("image_url") else None),
            )
            outcomes_out.append(
                {
                    "outcome_id": int(o.get("id") or (mid * 100 + idx + 1)),
                    "name": o_name,
                    "probability": p,
                    "rendered_percent": _half_up_pct(p),
                    "art": art,
                }
            )

    lead_prob = float(outcomes_out[0]["probability"]) if outcomes_out else 0.0
    return {
        "market_id": mid,
        "title": _clean_section_market_label(str(market.get("name") or "")),
        "raw_title": str(market.get("name") or ""),
        "href": f"/futures/{mid}",
        "source": str(market.get("source") or ""),
        "lead_prob": lead_prob,
        "closeness_to_50": abs(lead_prob - 0.5),
        "outcomes": outcomes_out,
        "card": dict(market),
    }


def _hydrate_event_visual_item(
    event: Mapping[str, Any],
    *,
    resolver: SubjectArtResolver,
) -> Optional[dict[str, Any]]:
    eid = int(event["id"])
    status = str(event.get("status") or "scheduled").lower()
    if status in {"cancelled", "postponed"}:
        return None
    odds = event.get("current_odds") if isinstance(event.get("current_odds"), Mapping) else {}
    home_p = event.get("hero_probability")
    away_p = event.get("hero_probability_away")
    if home_p is None:
        home_p = odds.get("home_probability")
    if away_p is None:
        away_p = odds.get("away_probability")

    pre = event.get("prematch_odds") if isinstance(event.get("prematch_odds"), Mapping) else {}
    if status in {"completed", "final", "closed"} and (home_p is None or away_p is None):
        home_p = pre.get("home_probability")
        away_p = pre.get("away_probability")

    if not isinstance(home_p, (int, float)) or not isinstance(away_p, (int, float)):
        return None
    hp = float(home_p)
    ap = float(away_p)
    if hp <= 0.0 and ap <= 0.0:
        return None

    home_team = str(event.get("home_team") or "").strip()
    away_team = str(event.get("away_team") or "").strip()
    home_td = event.get("home_team_data") if isinstance(event.get("home_team_data"), Mapping) else {}
    away_td = event.get("away_team_data") if isinstance(event.get("away_team_data"), Mapping) else {}

    home_art = resolver.resolve(
        home_team,
        explicit_url=home_td.get("logo_small") or home_td.get("logo_large") or event.get("home_image_url"),
        explicit_color=home_td.get("primary_color"),
    )
    away_art = resolver.resolve(
        away_team,
        explicit_url=away_td.get("logo_small") or away_td.get("logo_large") or event.get("away_image_url"),
        explicit_color=away_td.get("primary_color"),
    )

    fav_prob = max(hp, ap)
    return {
        "event_id": eid,
        "href": f"/events/{eid}",
        "status": status,
        "commence_time": str(event.get("commence_time") or ""),
        "sport": str(event.get("sport") or ""),
        "home_team": home_team,
        "away_team": away_team,
        "home_short": home_team.split()[-1] if home_team else "",
        "away_short": away_team.split()[-1] if away_team else "",
        "home_prob": hp,
        "away_prob": ap,
        "home_pct": _half_up_pct(hp),
        "away_pct": _half_up_pct(ap),
        "home_score": event.get("home_score"),
        "away_score": event.get("away_score"),
        "home_art": home_art,
        "away_art": away_art,
        "fav_prob": fav_prob,
        "closeness_to_50": abs(hp - 0.5),
        "card": dict(event),
    }


async def _load_snapshot_from_db(
    db: Any,
    definition: Mapping[str, Any],
    now_dt: datetime,
) -> dict[str, Any]:
    """Load candidate events, open futures markets, and paired sets for ``definition``."""
    if isinstance(db, Mapping) and ("events" in db or "markets" in db or "paired_sets" in db):
        return {
            "events": list(db.get("events") or ()),
            "markets": list(db.get("markets") or ()),
            "paired_sets": dict(db.get("paired_sets") or {}),
        }

    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.models.models import Event, FuturesMarket
    from app.services.paired_metric_register import load_live_paired_metric_sets

    sections_cfg = (definition.get("rule") or {}).get("sections") or ()
    events_out: list[dict[str, Any]] = []
    markets_out: list[dict[str, Any]] = []
    paired_out: dict[str, dict[str, Any]] = {}

    sport_keys = {
        str(sec["atom_query"]["sport_key"])
        for sec in sections_cfg
        if isinstance(sec, Mapping)
        and isinstance(sec.get("atom_query"), Mapping)
        and sec["atom_query"].get("kind") == "events"
        and sec["atom_query"].get("sport_key")
    }
    if sport_keys:
        horizon = now_dt + timedelta(days=9)
        recent_floor = now_dt - timedelta(hours=6)
        stmt = (
            select(Event)
            .where(
                Event.sport.in_(sorted(sport_keys)),
                Event.commence_time >= recent_floor,
                Event.commence_time <= horizon,
            )
            .order_by(Event.commence_time.asc())
            .limit(40)
        )
        rows = (await db.execute(stmt)).scalars().all()
        for ev in rows:
            wps = ev.win_probability_sources if isinstance(ev.win_probability_sources, Mapping) else {}
            agg = wps.get("_aggregate") if isinstance(wps.get("_aggregate"), Mapping) else {}
            events_out.append(
                {
                    "id": ev.id,
                    "sport": ev.sport,
                    "sport_name": ev.sport.upper(),
                    "home_team": ev.home_team,
                    "away_team": ev.away_team,
                    "commence_time": ev.commence_time.isoformat() if ev.commence_time else "",
                    "status": ev.status or "scheduled",
                    "home_score": ev.home_score,
                    "away_score": ev.away_score,
                    "current_odds": {
                        "home_probability": agg.get("home_win_prob"),
                        "away_probability": agg.get("away_win_prob"),
                    },
                }
            )

    ceremonies = {
        str(sec["atom_query"].get("ceremony") or "").lower()
        for sec in sections_cfg
        if isinstance(sec, Mapping)
        and isinstance(sec.get("atom_query"), Mapping)
        and sec["atom_query"].get("kind") == "paired_stage"
        and sec["atom_query"].get("ceremony")
    }
    if ceremonies:
        all_paired = await load_live_paired_metric_sets(db)
        paired_out.update(all_paired)

    needs_markets = any(
        isinstance(sec, Mapping)
        and isinstance(sec.get("atom_query"), Mapping)
        and sec["atom_query"].get("kind") == "markets"
        for sec in sections_cfg
    )
    if needs_markets:
        m_stmt = (
            select(FuturesMarket)
            .options(selectinload(FuturesMarket.outcomes))
            .where(FuturesMarket.status == "open")
            .order_by(FuturesMarket.volume.desc().nullslast())
            .limit(800)
        )
        m_rows = (await db.execute(m_stmt)).scalars().all()
        for fm in m_rows:
            markets_out.append(
                {
                    "id": fm.id,
                    "name": fm.name,
                    "status": fm.status,
                    "source": fm.source,
                    "volume": float(fm.volume or 0.0),
                    "image_url": fm.image_url,
                    "llm_sport_category": fm.llm_sport_category,
                    "top_outcomes": [
                        {
                            "id": o.id,
                            "name": o.outcome_name,
                            "probability": float(o.implied_probability)
                            if o.implied_probability is not None
                            else None,
                            "image_url": getattr(o, "image_url", None),
                        }
                        for o in (fm.outcomes or ())
                        if o.implied_probability is not None
                    ],
                }
            )

    return {"events": events_out, "markets": markets_out, "paired_sets": paired_out}


def _match_paired_set(
    paired_sets: Mapping[str, Mapping[str, Any]],
    query: Mapping[str, Any],
) -> Optional[dict[str, Any]]:
    ceremony = str(query.get("ceremony") or "").strip().lower()
    cat_name = str(query.get("category_name") or "").strip().lower()
    slug_token = _norm_key(cat_name).replace(" ", "-")
    for set_id, pset in paired_sets.items():
        sid = str(set_id).lower()
        title = str(pset.get("title") or "").lower()
        kicker = str(pset.get("kicker") or "").lower()
        if ceremony and ceremony not in sid and ceremony not in kicker:
            continue
        if slug_token and slug_token not in sid and cat_name not in title and cat_name not in kicker:
            continue
        return copy.deepcopy(dict(pset))
    return None


def _dedupe_twin_markets(markets: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the highest-liquidity canonical market when two venues list the same cleaned title."""
    seen_titles: set[str] = set()
    out: list[dict[str, Any]] = []
    for m in markets:
        norm_t = _norm_key(m["title"])
        if norm_t in seen_titles:
            continue
        seen_titles.add(norm_t)
        out.append(m)
    return out


async def produce_container_machinery(
    db: Any,
    definition: Mapping[str, Any],
    *,
    now: Optional[datetime] = None,
) -> Any:
    """Evaluate a declarative ``container_machinery`` definition into card + multi-section container."""
    from app.utils.roundup_containers import RoundupMembers, RoundupRefusal

    now_dt = now or datetime.now(timezone.utc)
    resolver = _default_art_resolver()
    rule = definition.get("rule") if isinstance(definition.get("rule"), Mapping) else {}
    sections_cfg = rule.get("sections") or ()
    if not isinstance(sections_cfg, Sequence) or not sections_cfg:
        return RoundupRefusal((("container_machinery", "empty_sections"),))

    snapshot = await _load_snapshot_from_db(db, definition, now_dt)
    all_events = snapshot["events"]
    all_markets = snapshot["markets"]
    paired_sets = snapshot["paired_sets"]

    built_sections: list[dict[str, Any]] = []
    all_member_envelopes: list[dict[str, Any]] = []
    seen_member_keys: set[tuple[str, int]] = set()
    lead_paired_set: Optional[dict[str, Any]] = None

    for sec_cfg in sections_cfg:
        if not isinstance(sec_cfg, Mapping):
            continue
        sec_key = str(sec_cfg.get("key") or "section")
        sec_title = str(sec_cfg.get("title") or definition.get("section_title") or "Markets")
        sec_note = str(sec_cfg.get("note") or "").strip() or None
        aq = sec_cfg.get("atom_query") if isinstance(sec_cfg.get("atom_query"), Mapping) else {}
        aq_kind = str(aq.get("kind") or "markets")
        min_items = int(aq.get("min_items", 1))
        max_items = int(aq.get("max_items", 6))
        max_outcomes = int(aq.get("max_outcomes", 6))

        if aq_kind == "paired_stage":
            pset = _match_paired_set(paired_sets, aq)
            if pset is None:
                return RoundupRefusal((("container_machinery", f"missing_paired_stage:{sec_key}"),))
            entries = [
                dict(e)
                for e in (pset.get("entries") or ())
                if isinstance(e, Mapping)
                and isinstance(e.get("stage_2_probability"), (int, float))
                and math.isfinite(float(e["stage_2_probability"]))
            ]
            if len(entries) < min_items:
                return RoundupRefusal((("container_machinery", f"too_few_paired_entries:{sec_key}"),))
            pset["entries"] = entries[:max_items]
            form_id = choose_section_form("paired_stage", pset["entries"])
            s2_meta = pset.get("stage_2_market") if isinstance(pset.get("stage_2_market"), Mapping) else {}
            s1_meta = pset.get("stage_1_market") if isinstance(pset.get("stage_1_market"), Mapping) else {}
            sec_members: list[dict[str, Any]] = []
            for m_meta in (s2_meta, s1_meta):
                mid = int(m_meta.get("id") or 0)
                if mid <= 0:
                    continue
                synthetic_card = {
                    "id": mid,
                    "name": str(m_meta.get("name") or sec_title),
                    "status": "open",
                    "source": str(m_meta.get("source") or "kalshi"),
                    "top_outcomes": [
                        {
                            "name": str(e.get("subject") or ""),
                            "probability": float(e.get("stage_2_probability") or 0.0),
                        }
                        for e in pset["entries"][:5]
                    ],
                }
                env = {
                    "type": MEMBER_MARKET,
                    "id": mid,
                    "destination": market_destination(mid),
                    "card": synthetic_card,
                }
                sec_members.append(env)
                if (MEMBER_MARKET, mid) not in seen_member_keys:
                    seen_member_keys.add((MEMBER_MARKET, mid))
                    all_member_envelopes.append(env)
            if lead_paired_set is None:
                lead_paired_set = copy.deepcopy(pset)
            built_sections.append(
                {
                    "class": sec_key,
                    "title": sec_title,
                    "note": sec_note,
                    "layout": form_id,
                    "members": sec_members,
                    "visual_block": {
                        "form_id": form_id,
                        "paired_metric_set": pset,
                        "items": [],
                    },
                }
            )
            continue

        if aq_kind == "events":
            sport_req = str(aq.get("sport_key") or "").lower()
            include_completed = bool(aq.get("include_completed", False))
            band = aq.get("probability_band")
            band_lo = float(band[0]) if isinstance(band, Sequence) and len(band) == 2 else 0.0
            band_hi = float(band[1]) if isinstance(band, Sequence) and len(band) == 2 else 1.0
            ev_items: list[dict[str, Any]] = []
            for raw_ev in all_events:
                if sport_req and str(raw_ev.get("sport") or "").lower() != sport_req:
                    continue
                ev_status = str(raw_ev.get("status") or "").strip().lower()
                if not include_completed and ev_status in {"completed", "final", "closed"}:
                    continue
                if (MEMBER_EVENT, int(raw_ev["id"])) in seen_member_keys:
                    continue
                hyd = _hydrate_event_visual_item(raw_ev, resolver=resolver)
                if hyd is None:
                    continue
                if not (band_lo <= hyd["home_prob"] <= band_hi):
                    continue
                ev_items.append(hyd)
            order_by = str(aq.get("order_by") or "kickoff_asc")
            if order_by == "closeness_to_50":
                ev_items.sort(key=lambda x: (x["closeness_to_50"], x["commence_time"]))
            else:
                ev_items.sort(key=lambda x: x["commence_time"])
            ev_items = ev_items[:max_items]
            if len(ev_items) < min_items:
                return RoundupRefusal((("container_machinery", f"too_few_events:{sec_key}"),))
            form_id = choose_section_form("events", ev_items)
            sec_members = []
            for it in ev_items:
                eid = it["event_id"]
                env = {
                    "type": MEMBER_EVENT,
                    "id": eid,
                    "destination": event_destination(eid),
                    "card": it["card"],
                    "event_id": eid,
                }
                sec_members.append(env)
                if (MEMBER_EVENT, eid) not in seen_member_keys:
                    seen_member_keys.add((MEMBER_EVENT, eid))
                    all_member_envelopes.append(env)
            built_sections.append(
                {
                    "class": sec_key,
                    "title": sec_title,
                    "note": sec_note,
                    "layout": form_id,
                    "members": sec_members,
                    "visual_block": {
                        "form_id": form_id,
                        "items": [
                            {k: v for k, v in it.items() if k != "card"}
                            for it in ev_items
                        ],
                    },
                }
            )
            continue

        # aq_kind == "markets"
        matched = [
            _hydrate_market_visual_item(m, max_outcomes=max_outcomes, resolver=resolver)
            for m in all_markets
            if (MEMBER_MARKET, int(m["id"])) not in seen_member_keys
            and _market_matches_query(m, aq)
        ]
        matched = _dedupe_twin_markets(matched)
        order_by = str(aq.get("order_by") or "lead_prob_desc")
        if order_by == "closeness_to_50":
            matched.sort(key=lambda x: (x["closeness_to_50"], -x["lead_prob"]))
        else:
            matched.sort(key=lambda x: (-x["lead_prob"], x["title"].casefold()))
        matched = matched[:max_items]
        if len(matched) < min_items:
            return RoundupRefusal((("container_machinery", f"too_few_markets:{sec_key}"),))

        form_id = choose_section_form("markets", matched)
        sec_members = []
        for it in matched:
            mid = it["market_id"]
            env = {
                "type": MEMBER_MARKET,
                "id": mid,
                "destination": market_destination(mid),
                "card": it["card"],
            }
            sec_members.append(env)
            if (MEMBER_MARKET, mid) not in seen_member_keys:
                seen_member_keys.add((MEMBER_MARKET, mid))
                all_member_envelopes.append(env)

        built_sections.append(
            {
                "class": sec_key,
                "title": sec_title,
                "note": sec_note,
                "layout": form_id,
                "members": sec_members,
                "visual_block": {
                    "form_id": form_id,
                    "items": [
                        {k: v for k, v in it.items() if k != "card"}
                        for it in matched
                    ],
                },
            }
        )

    if not built_sections or not all_member_envelopes:
        return RoundupRefusal((("container_machinery", "no_sections_built"),))

    # Build the compact Discover card from the designated card section (or section 0)
    card_rows_limit = int(rule.get("card_rows", 5))
    preferred_card_key = str(rule.get("card_section_key") or "").strip()
    card_sec = next(
        (s for s in built_sections if s["class"] == preferred_card_key),
        built_sections[0],
    )
    vb = card_sec["visual_block"]
    vb_form = vb["form_id"]

    rows_out: list[dict[str, Any]] = []
    card_visual_rows: list[dict[str, Any]] = []

    if vb_form == "paired_stage_bars" and isinstance(vb.get("paired_metric_set"), Mapping):
        pset = vb["paired_metric_set"]
        w_mid = int((pset.get("stage_2_market") or {}).get("id") or 1)
        for idx, e in enumerate((pset.get("entries") or ())[:card_rows_limit]):
            win_p = float(e.get("stage_2_probability") or 0.0)
            nom_p = e.get("stage_1_probability")
            row_d: dict[str, Any] = {
                "market_id": w_mid,
                "outcome_id": int(e.get("stage_2_outcome_id") or (w_mid * 100 + idx + 1)),
                "label": str(e.get("subject") or ""),
                "probability": win_p,
                "rendered_percent": _half_up_pct(win_p),
            }
            if isinstance(nom_p, (int, float)):
                row_d["secondary_probability"] = float(nom_p)
                row_d["secondary_rendered_percent"] = _half_up_pct(float(nom_p))
            rows_out.append(row_d)
    elif vb_form in {"coin_flip_matchups", "matchup_slate"}:
        for it in (vb.get("items") or ())[:card_rows_limit]:
            eid = int(it["event_id"])
            fav_is_home = it["home_prob"] >= it["away_prob"]
            fav_pct = it["home_pct"] if fav_is_home else it["away_pct"]
            fav_p = it["home_prob"] if fav_is_home else it["away_prob"]
            rows_out.append(
                {
                    "event_id": eid,
                    "label": f"{it['away_short']} at {it['home_short']}",
                    "probability": fav_p,
                    "rendered_percent": fav_pct,
                }
            )
            card_visual_rows.append(it)
    else:
        lead_market = (vb.get("items") or [{}])[0]
        mid = int(lead_market.get("market_id") or 1)
        for o in (lead_market.get("outcomes") or ())[:card_rows_limit]:
            rows_out.append(
                {
                    "market_id": mid,
                    "outcome_id": int(o["outcome_id"]),
                    "label": str(o["name"]),
                    "probability": float(o["probability"]),
                    "rendered_percent": int(o["rendered_percent"]),
                }
            )
            card_visual_rows.append(
                {
                    "market_id": mid,
                    "href": lead_market.get("href") or f"/futures/{mid}",
                    **o,
                }
            )

    slug = str(definition["slug"])
    dest_href = f"/collections/{slug}"
    machinery_card = {
        "slug": slug,
        "form_id": vb_form,
        "kicker": str(definition.get("kicker") or "ROUND-UP"),
        "title": str(definition.get("name") or slug),
        "subtitle": str(card_sec.get("note") or definition.get("footer") or ""),
        "footer": str(definition.get("footer") or ""),
        "section_count": len(built_sections),
        "destination_href": dest_href,
        "rows": card_visual_rows,
    }

    return RoundupMembers(
        all_member_envelopes,
        rows_out,
        footer=str(definition.get("footer") or ""),
        title=str(definition.get("name") or slug),
        kicker=str(definition.get("kicker") or "ROUND-UP"),
        destination_href=dest_href,
        sections=built_sections,
        parent_slug=definition.get("parent_slug"),
        parent_name=definition.get("parent_name"),
        paired_metric_set=lead_paired_set if vb_form == "paired_stage_bars" else None,
        machinery_card=machinery_card,
    )


def discover_machinery_candidate_paths() -> tuple[Path, ...]:
    """Discover all ``machinery-*.json`` definitions in ``data/groupings/candidates/``."""
    return tuple(sorted(_CANDIDATES_DIR.glob("machinery-*.json")))


def load_machinery_definition(path: Path | str) -> dict[str, Any]:
    from app.utils.roundup_containers import validate_roundup_definition

    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    validated = validate_roundup_definition(raw, path=path)
    if validated["rule"].get("producer") != PRODUCER_KIND_CONTAINER_MACHINERY:
        raise ValueError(f"Expected producer='container_machinery' at {path}")
    copy_fields: list[str] = [
        str(validated.get("name") or ""),
        str(validated.get("kicker") or ""),
        str(validated.get("section_title") or ""),
        str(validated.get("footer") or ""),
    ]
    for sec in validated["rule"].get("sections") or ():
        if isinstance(sec, Mapping):
            copy_fields.append(str(sec.get("title") or ""))
            copy_fields.append(str(sec.get("note") or ""))
    for text_val in copy_fields:
        if _FORBIDDEN_COPY_QUESTION_RE.search(text_val):
            raise ValueError(
                f"Definition {path} calls a market a 'question' ({text_val!r}); say 'market(s)'."
            )
    return validated


def build_container_machinery_producer(
    definition: Mapping[str, Any],
    *,
    enabled: Optional[Any] = None,
) -> Any:
    from app.utils.roundup_containers import RoundupProducer, validate_roundup_definition

    validated = validate_roundup_definition(definition)

    async def _produce(db: Any, *, now: Optional[datetime] = None) -> Any:
        return await produce_container_machinery(db, validated, now=now)

    return RoundupProducer(
        slug=validated["slug"],
        name=str(validated.get("name") or validated["slug"]),
        kind="roundup",
        category=str(validated.get("category") or "other"),
        section_title=str(validated.get("section_title") or "Markets"),
        footer=str(validated.get("footer") or ""),
        produce=_produce,
        membership=str(validated.get("membership") or "computed-produced"),
        relations=validated["relations"],
        level=validated["level"],
        rule=validated["rule"],
        tag=validated.get("tag"),
        kicker=str(validated.get("kicker") or "ROUND-UP"),
        parent_slug=validated.get("parent_slug"),
        parent_name=validated.get("parent_name"),
        enabled=enabled if enabled is not None else container_machinery_enabled,
    )


def register_machinery_slice1_candidates(*, enabled: Optional[Any] = None) -> list[str]:
    """Register all ``machinery-*.json`` candidate definitions into ``ROUNDUP_PRODUCERS``."""
    from app.utils.roundup_containers import register_roundup_producer

    slugs: list[str] = []
    for path in discover_machinery_candidate_paths():
        defn = load_machinery_definition(path)
        prod = build_container_machinery_producer(defn, enabled=enabled)
        register_roundup_producer(prod)
        slugs.append(prod.slug)
    return slugs


_SLICE1_ORDER: tuple[str, ...] = (
    "machinery-nfl-week",
    "machinery-oscars-best-picture",
    "machinery-2028-presidential",
    "machinery-fed-and-macro",
)


def _ordered_machinery_candidate_paths() -> tuple[Path, ...]:
    by_slug = {p.stem: p for p in discover_machinery_candidate_paths()}
    ordered: list[Path] = []
    for s in _SLICE1_ORDER:
        if s in by_slug:
            ordered.append(by_slug.pop(s))
    for s in sorted(by_slug):
        ordered.append(by_slug[s])
    return tuple(ordered)


def is_machinery_candidate_slug(slug: str) -> bool:
    """True when ``slug`` corresponds to a ``machinery-*.json`` candidate definition."""
    if not slug or "/" in slug or "\\" in slug or ".." in slug:
        return False
    return any(p.stem == slug for p in discover_machinery_candidate_paths())


def _has_verified_art(obj: Mapping[str, Any]) -> bool:
    art = obj.get("art")
    if isinstance(art, Mapping) and str(art.get("url") or "").strip():
        return True
    if str(obj.get("poster_url") or "").strip():
        return True
    away_art = obj.get("away_art")
    home_art = obj.get("home_art")
    if isinstance(away_art, Mapping) and str(away_art.get("url") or "").strip():
        return True
    if isinstance(home_art, Mapping) and str(home_art.get("url") or "").strip():
        return True
    return False


def _visual_block_units(vb: Mapping[str, Any]) -> tuple[str, list[tuple[float, int]]]:
    """Return ``(form_id, [(unit_height_px_at_390, verified_picture_count), ...])``
    for each consecutive row/card unit rendered inside ``vb`` at 390 px width."""
    form = str(vb.get("form_id") or vb.get("form") or "")
    units: list[tuple[float, int]] = []
    if form == "paired_stage_bars":
        pms = vb.get("paired_metric_set") or {}
        for row in pms.get("entries") or pms.get("rows") or ():
            if isinstance(row, Mapping):
                pics = 1 if _has_verified_art(row) else 0
                units.append((76.0, pics))
    elif form in {"coin_flip_matchups", "matchup_slate"}:
        for it in vb.get("items") or ():
            if isinstance(it, Mapping):
                pics = 0
                if isinstance(it.get("away_art"), Mapping) and str(it["away_art"].get("url") or "").strip():
                    pics += 1
                if isinstance(it.get("home_art"), Mapping) and str(it["home_art"].get("url") or "").strip():
                    pics += 1
                units.append((114.0, pics))
    elif form == "duel_bar":
        for it in vb.get("items") or ():
            if isinstance(it, Mapping):
                pics = sum(
                    1
                    for s in (it.get("sides") or ())
                    if isinstance(s, Mapping) and _has_verified_art(s)
                )
                units.append((108.0, pics))
    elif form == "contender_spotlight":
        for it in vb.get("items") or ():
            if isinstance(it, Mapping):
                for o in it.get("outcomes") or ():
                    if isinstance(o, Mapping):
                        units.append((70.0, 1 if _has_verified_art(o) else 0))
    elif form == "sibling_fields_grid":
        for it in vb.get("items") or ():
            if isinstance(it, Mapping):
                pics = sum(
                    1
                    for o in (it.get("outcomes") or ())
                    if isinstance(o, Mapping) and _has_verified_art(o)
                )
                units.append((148.0, pics))
    elif form == "benchmark_strip":
        for it in vb.get("items") or ():
            if isinstance(it, Mapping):
                units.append((64.0, 1 if _has_verified_art(it) else 0))
    return form, units


def _estimate_screen_picture_counts_390px(sections: Sequence[Mapping[str, Any]]) -> list[int]:
    """Estimate verified picture counts per 390x844 phone screen from rendered unit heights."""
    screen_h = 844.0
    y = 148.0  # container title + subtitle + count header at 390 px
    unit_boxes: list[tuple[float, float, int]] = []
    for sec in sections:
        vb = sec.get("visual_block")
        if not isinstance(vb, Mapping):
            continue
        y += 64.0  # section title + subtitle + vertical gap
        _form, units = _visual_block_units(vb)
        for h, pics in units:
            unit_boxes.append((y, y + h, pics))
            y += h + 8.0
        y += 16.0
    total_h = max(y, screen_h)
    num_screens = max(1, int(math.ceil(total_h / screen_h)))
    counts: list[int] = []
    for idx in range(num_screens):
        top = idx * screen_h
        bot = (idx + 1) * screen_h
        pics_on_screen = sum(
            pics for (u0, u1, pics) in unit_boxes if pics > 0 and u1 > top + 12.0 and u0 < bot - 12.0
        )
        counts.append(pics_on_screen)
    return counts


def _classify_member_content_kind(member: Mapping[str, Any]) -> str:
    mtype = str(member.get("type") or "")
    if mtype == "event":
        return "games"
    if mtype == "history":
        return "history"
    item = member.get("item") if isinstance(member.get("item"), Mapping) else {}
    futures_obj = item.get("futures") if isinstance(item.get("futures"), Mapping) else item
    m_kind = str(futures_obj.get("market_type") or "").lower()
    if "prop" in m_kind or (futures_obj.get("event_id") is not None and "player" in m_kind):
        return "props"
    return "futures"


def compute_visual_diversity_report(
    definition: Mapping[str, Any],
    feed_item: Optional[Mapping[str, Any]],
    container_payload: Mapping[str, Any],
    *,
    screen_picture_counts_390px: Optional[Sequence[int]] = None,
) -> dict[str, Any]:
    """Compute Ruling 227-A report-only visual diversity metrics (points 1–4)
    for both the Discover card and the multi-section container page."""
    fi_data = (feed_item or {}).get("data") if isinstance((feed_item or {}).get("data"), Mapping) else {}
    rc = (
        fi_data.get("roundup")
        or (feed_item or {}).get("roundup_contract")
        or {}
    )
    if not isinstance(rc, Mapping):
        rc = {}
    mc = rc.get("machinery_card") if isinstance(rc.get("machinery_card"), Mapping) else {}
    card_form = str(mc.get("form_id") or "roundup")
    card_rows = list(mc.get("rows") or ())
    pms = rc.get("paired_metric_set") if isinstance(rc.get("paired_metric_set"), Mapping) else None
    if card_form == "paired_stage_bars" and pms:
        all_pms_entries = list(pms.get("entries") or pms.get("rows") or ())
        # AwardCategoryPairedCard on Discover collapses to top 5 rows by default.
        pms_rows = all_pms_entries[:5]
        card_row_count = len(pms_rows)
        card_pics = sum(
            1 for r in pms_rows if isinstance(r, Mapping) and _has_verified_art(r)
        )
    else:
        card_row_count = len(card_rows)
        card_pics = 0
        for r in card_rows:
            if not isinstance(r, Mapping):
                continue
            if card_form in {"coin_flip_matchups", "matchup_slate"}:
                if isinstance(r.get("away_art"), Mapping) and str(r["away_art"].get("url") or "").strip():
                    card_pics += 1
                if isinstance(r.get("home_art"), Mapping) and str(r["home_art"].get("url") or "").strip():
                    card_pics += 1
            elif _has_verified_art(r):
                card_pics += 1

    card_kind = "games" if card_form in {"coin_flip_matchups", "matchup_slate"} else "futures"
    card_failing: list[str] = []
    if card_pics < 1:
        card_failing.append("point_1_picture_on_screen")
    if card_row_count > 3:
        card_failing.append("point_2_no_long_runs")

    card_report = {
        "surface": "discover_card",
        "form_id": card_form,
        "point_1_pictures_per_screen_390px": {
            "screens": [card_pics],
            "min_pictures_per_screen": card_pics,
            "passes": card_pics >= 1,
        },
        "point_2_longest_form_run": {
            "longest_row_run": card_row_count,
            "max_allowed": 3,
            "passes": card_row_count <= 3,
        },
        "point_3_forms": {
            "distinct_forms": [card_form],
            "form_count": 1,
            "note": "Single Discover card contributes 1 form toward Discover's first-10 >=4 requirement.",
            "passes": True,
        },
        "point_4_content_mix": {
            "content_kinds": {card_kind: card_row_count},
            "kind_count": 1 if card_row_count else 0,
            "largest_kind": card_kind if card_row_count else None,
            "largest_kind_share": 1.0 if card_row_count else 0.0,
            "note": "Card summarizes lead section; content-mix threshold applies at page/feed level.",
            "passes": True,
        },
        "overall_passes": len(card_failing) == 0,
        "failing_points": card_failing,
    }

    sections = [
        s for s in (container_payload.get("sections") or ()) if isinstance(s, Mapping)
    ]
    screens = (
        [int(x) for x in screen_picture_counts_390px]
        if screen_picture_counts_390px is not None
        else _estimate_screen_picture_counts_390px(sections)
    )
    if not screens:
        screens = [0]
    min_pics = min(screens)
    p1_pass = min_pics >= 1

    longest_row_run = 0
    current_row_run = 0
    longest_sec_run = 0
    current_sec_run = 0
    prev_form: Optional[str] = None
    distinct_forms: list[str] = []
    for sec in sections:
        vb = sec.get("visual_block")
        if not isinstance(vb, Mapping):
            continue
        form, units = _visual_block_units(vb)
        unit_count = len(units)
        if form and form not in distinct_forms:
            distinct_forms.append(form)
        if form == prev_form:
            current_row_run += unit_count
            current_sec_run += 1
        else:
            current_row_run = unit_count
            current_sec_run = 1
            prev_form = form
        longest_row_run = max(longest_row_run, current_row_run)
        longest_sec_run = max(longest_sec_run, current_sec_run)

    p2_pass = longest_row_run <= 3
    member_count = int(container_payload.get("member_count") or 0)
    form_count = len(distinct_forms)
    p3_pass = True if member_count < 6 else form_count >= 3

    kind_counts: dict[str, int] = {}
    for sec in sections:
        for m in sec.get("members") or ():
            if isinstance(m, Mapping):
                k = _classify_member_content_kind(m)
                kind_counts[k] = kind_counts.get(k, 0) + 1
    total_members_typed = sum(kind_counts.values())
    if total_members_typed > 0:
        largest_kind = max(sorted(kind_counts), key=lambda k: kind_counts[k])
        largest_share = round(kind_counts[largest_kind] / total_members_typed, 4)
    else:
        largest_kind = None
        largest_share = 0.0

    category = str(definition.get("category") or "").lower()
    is_sports_topic = (
        "games" in kind_counts
        or category in {"sports", "football", "basketball", "baseball", "hockey", "soccer", "tennis", "golf", "mma"}
    )
    available_topic_kinds = (
        ["games", "futures", "props", "history"]
        if is_sports_topic
        else ["futures", "history"]
    )
    multi_kind_topic = len(available_topic_kinds) > 1
    p4_pass = (
        (len(kind_counts) >= 2 and largest_share <= 0.60)
        if multi_kind_topic
        else True
    )

    page_failing: list[str] = []
    if not p1_pass:
        page_failing.append("point_1_picture_on_every_screen")
    if not p2_pass:
        page_failing.append("point_2_no_long_runs")
    if not p3_pass:
        page_failing.append("point_3_several_forms")
    if not p4_pass:
        page_failing.append("point_4_content_mix")

    page_report = {
        "surface": "container_page",
        "member_count": member_count,
        "section_count": len(sections),
        "point_1_pictures_per_screen_390px": {
            "screens": screens,
            "screen_count": len(screens),
            "min_pictures_per_screen": min_pics,
            "passes": p1_pass,
        },
        "point_2_longest_form_run": {
            "longest_row_run": longest_row_run,
            "longest_section_form_run": longest_sec_run,
            "max_allowed": 3,
            "passes": p2_pass,
        },
        "point_3_forms": {
            "member_count": member_count,
            "distinct_forms": distinct_forms,
            "form_count": form_count,
            "min_required": 3 if member_count >= 6 else 1,
            "passes": p3_pass,
        },
        "point_4_content_mix": {
            "content_kinds": kind_counts,
            "available_topic_kinds": available_topic_kinds,
            "kind_count": len(kind_counts),
            "largest_kind": largest_kind,
            "largest_kind_share": largest_share,
            "max_allowed_share": 0.60,
            "passes": p4_pass,
        },
        "overall_passes": len(page_failing) == 0,
        "failing_points": page_failing,
    }

    return {
        "standard": "227-A",
        "report_only": True,
        "slug": str(definition.get("slug") or ""),
        "name": str(definition.get("name") or ""),
        "category": str(definition.get("category") or ""),
        "card": card_report,
        "page": page_report,
        "overall_passes": bool(card_report["overall_passes"] and page_report["overall_passes"]),
    }


async def serve_machinery_candidate_preview(
    slug: str,
    db: Any,
    *,
    include_children: bool = True,
    now: Optional[datetime] = None,
) -> Optional[dict[str, Any]]:
    """Evaluate a single ``machinery-*.json`` candidate definition for an authenticated
    admin preview without enabling the global ``CONTAINER_MACHINERY_SLICE1_ENABLED`` flag."""
    from app.utils.roundup_containers import evaluate_roundup_producer

    target_path = next(
        (p for p in _ordered_machinery_candidate_paths() if p.stem == slug),
        None,
    )
    if target_path is None:
        return None
    defn = load_machinery_definition(target_path)
    producer = build_container_machinery_producer(defn, enabled=lambda: True)
    feed_item, payload = await evaluate_roundup_producer(producer, db, now=now)
    if payload is None:
        return None
    out = copy.deepcopy(payload)
    if not include_children:
        out["children"] = []
    report = compute_visual_diversity_report(defn, feed_item, out)
    return {
        "slug": slug,
        "definition": {
            "slug": defn["slug"],
            "name": defn.get("name"),
            "category": defn.get("category"),
            "kicker": defn.get("kicker"),
            "footer": defn.get("footer"),
        },
        "feed_item": feed_item,
        "container": out,
        "diversity_report": report,
    }


async def evaluate_machinery_candidates_preview(
    db: Any,
    *,
    slugs: Optional[Sequence[str]] = None,
    now: Optional[datetime] = None,
) -> list[dict[str, Any]]:
    """Evaluate all (or selected) ``machinery-*.json`` candidates for Alex's private preview."""
    wanted = set(slugs) if slugs is not None else None
    items: list[dict[str, Any]] = []
    for path in _ordered_machinery_candidate_paths():
        if wanted is not None and path.stem not in wanted:
            continue
        res = await serve_machinery_candidate_preview(path.stem, db, now=now)
        if res is not None:
            items.append(res)
    return items
