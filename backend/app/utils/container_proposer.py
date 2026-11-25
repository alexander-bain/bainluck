"""Uncovered-family container proposer (Decision 386: A, #12221 Item 10).

Discovers uncovered prediction-market families using ``grouping_families`` plus
frame/stem fallback clustering, scores them by reader interest rather than raw
market count (putting entertainment/culture/oddities ahead of macro/politics per
Condition 3), and emits up to N ``preview`` Kit container pages plus an audit
trail of evaluated top candidates and refusals (Condition 2).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import re
from typing import Any, Iterable, Mapping, Sequence

from app.utils.grouping_families import (
    Atom,
    Family,
    build_families,
    uncovered_families,
)
from app.utils.kit_container_page_builder import (
    _parse_iso_dt,
    is_settled_market,
    propose_container_page_for_family,
    resolve_kicker,
)
from app.utils.market_interestingness import score_market_interestingness

_CATEGORY_MIX_BONUS: dict[str, float] = {
    "entertainment": 18.0,
    "movies": 18.0,
    "music": 18.0,
    "tv": 18.0,
    "culture": 18.0,
    "pop_culture": 18.0,
    "tech": 14.0,
    "science": 14.0,
    "ai": 14.0,
    "weather": 10.0,
    "crypto": 4.0,
    "economics": 0.0,
    "politics": 0.0,
    "geopolitics": 0.0,
    "sports": -10.0,
    "awards": -4.0,
}

_QUESTION_STARTERS = frozenset({
    "will", "who", "what", "which", "when", "where", "why", "how",
    "does", "do", "did", "is", "are", "was", "were", "can", "could",
    "would", "should", "has", "have", "had",
})

_NON_ENTITY_PROPER = frozenset({
    "the", "a", "an", "another", "next", "before", "after", "by", "in", "on", "at",
    "from", "with", "during", "through", "into", "over", "under", "between", "end",
    "more", "than", "above", "below", "high", "low", "first", "second", "third", "last",
    "new", "top", "best", "big", "major", "any", "all", "yes", "no", "up", "down",
    "highest", "lowest", "largest", "biggest", "smallest", "most", "fewest",
    "longest", "shortest", "fastest", "slowest", "which", "where", "sectors",
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december", "jan", "feb", "mar", "apr",
    "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
    "rotten", "tomatoes", "tomatometer", "metacritic", "arena", "leaderboard",
    "score", "price", "market", "model", "nominees", "winner", "beige", "book",
    "keynote", "act", "popular", "vote", "initiative", "series", "season",
    "edition", "final", "open", "total", "average", "rate", "rates", "index",
    "conditions", "week", "pure", "sales", "streams", "units", "equivalent",
})

_GENERIC_SINGLE_NOUNS = frozenset({
    "united", "states", "president", "world", "national", "global", "international",
    "year", "month", "week", "day", "company", "companies", "people", "person",
    "movie", "film", "song", "album", "game", "cup", "league", "award", "awards",
    "federal", "public", "government", "report", "market", "humanity",
    "highest", "lowest", "largest", "biggest", "smallest", "most", "fewest",
    "longest", "shortest", "fastest", "slowest", "sectors",
})

_ACRONYM_ENTITY_SKIP = frozenset({
    "IPO", "GDP", "CPI", "API", "CEO", "CFO", "USA", "USD", "ETF", "GPT", "ET", "PT", "UTC",
})

_LOCATION_PREPS = frozenset({"in", "at", "from", "near", "across"})

_HYPHEN_PAIR_SKIP = frozenset({
    "pre", "sub", "anti", "non", "multi", "semi", "co", "re", "ex", "pro",
    "mid", "all", "self", "full", "half", "well", "term", "year", "sci", "tech",
})

_STEM_STOPWORDS = frozenset({
    "will", "the", "a", "an", "be", "in", "on", "of", "to", "for", "by", "or",
    "and", "before", "after", "at", "from", "with", "what", "who", "which",
    "above", "below", "over", "under", "between", "end", "more", "than",
    "yes", "no", "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
    "another", "next", "during", "through", "least", "most", "other", "another",
    "its", "his", "her", "their", "our", "say", "make", "close", "get", "hit",
    "have", "has", "take", "keep", "hold", "score", "scores", "at", "into",
})


def _canonical_entity_pair(tokens: Sequence[str]) -> tuple[str, str]:
    clean_words = [w for w in tokens if w]
    norm_tokens = [re.sub(r"[^a-z0-9]", "", w.lower()) for w in clean_words]
    while len(norm_tokens) > 1 and norm_tokens[0] in {"the", "a", "an"}:
        norm_tokens.pop(0)
    canon = "_".join(t for t in norm_tokens if t)
    label = " ".join(clean_words[:4])
    return canon, label


def normalize_market_record(row: Any) -> dict[str, Any]:
    """Normalize a FuturesMarket ORM object or API dict into proposer format."""
    if isinstance(row, Mapping):
        data = dict(row)
    else:
        meta = getattr(row, "market_metadata", None) or {}
        outcomes_raw = getattr(row, "outcomes", None) or []
        outcomes = [
            {
                "name": getattr(o, "name", ""),
                "current_probability": (
                    float(o.current_probability)
                    if getattr(o, "current_probability", None) is not None
                    else None
                ),
                "probability_change_24h": getattr(o, "probability_change_24h", None),
            }
            for o in outcomes_raw
        ]
        data = {
            "id": getattr(row, "id", None),
            "source": getattr(row, "source", "") or "",
            "external_id": getattr(row, "external_id", "") or "",
            "group_id": getattr(row, "group_id", None),
            "name": getattr(row, "name", "") or "",
            "event_title": meta.get("event_title") if isinstance(meta, Mapping) else None,
            "category": getattr(row, "category", None),
            "llm_sport_category": getattr(row, "llm_sport_category", None),
            "resolution_date": getattr(row, "resolution_date", None),
            "created_at": getattr(row, "created_at", None),
            "status": getattr(row, "status", "open") or "open",
            "settled_at": getattr(row, "settled_at", None),
            "volume_24h": getattr(row, "volume_24h", None),
            "max_movement_24h": getattr(row, "max_movement_24h", None),
            "market_metadata": meta,
            "outcomes": outcomes,
        }

    meta = data.get("market_metadata")
    if isinstance(meta, Mapping) and not data.get("frame"):
        llm_block = meta.get("discover_llm")
        if isinstance(llm_block, Mapping) and isinstance(llm_block.get("frame"), Mapping):
            data["frame"] = dict(llm_block["frame"])

    # Normalize public futures API shapes (`top_outcomes`, `probability`, `movement`, `source_count`)
    if not data.get("outcomes") and isinstance(data.get("top_outcomes"), Sequence):
        mapped_outcomes: list[dict[str, Any]] = []
        for outcome in data["top_outcomes"]:
            if not isinstance(outcome, Mapping):
                continue
            prob = outcome.get("current_probability")
            if prob is None:
                prob = outcome.get("probability")
            move = outcome.get("probability_change_24h")
            if move is None:
                move = outcome.get("movement")
            mapped_outcomes.append({
                "name": str(outcome.get("name") or ""),
                "current_probability": float(prob) if prob is not None else None,
                "probability_change_24h": float(move) if move is not None else None,
            })
        if mapped_outcomes:
            data["outcomes"] = mapped_outcomes

    if data.get("sources_count") is None and data.get("source_count") is not None:
        try:
            data["sources_count"] = int(data["source_count"])
        except (TypeError, ValueError):
            pass

    if data.get("max_movement_24h") is None and isinstance(data.get("outcomes"), Sequence):
        moves = [
            abs(float(o["probability_change_24h"]))
            for o in data["outcomes"]
            if isinstance(o, Mapping) and o.get("probability_change_24h") is not None
        ]
        if moves:
            data["max_movement_24h"] = max(moves)

    return data


def _generic_stem_key(market: Mapping[str, Any]) -> tuple[str, str] | None:
    """Generic cluster key from #1809 content frame or primary entity phrase (zero hardcoded topics)."""
    frame = market.get("frame")
    if isinstance(frame, Mapping):
        topic = str(frame.get("topic_key") or frame.get("topic") or "").strip().lower()
        entity = str(frame.get("entity_key") or frame.get("subject_key") or "").strip().lower()
        if topic and len(re.split(r"[\s_]+", topic)) >= 2:
            return (topic.replace(" ", "_"), topic.replace("_", " ").title())
        if entity and len(re.split(r"[\s_]+", entity)) >= 1:
            return (entity.replace(" ", "_"), entity.replace("_", " ").title())

    title = str(market.get("name") or market.get("title") or "").strip()
    if not title:
        return None

    # Priority 2a: Explicit structured separator prefix ("Subject: Detail" or "Subject · Metric")
    m_dot = re.match(r"^([^?]{3,42}?)\s+·\s+", title)
    if m_dot:
        prefix = m_dot.group(1).strip(" \"'")
        words = prefix.split()
        if words and words[0].lower() not in _QUESTION_STARTERS and "$" not in prefix:
            canon, label = _canonical_entity_pair(words)
            if canon and canon not in _GENERIC_SINGLE_NOUNS:
                return (canon, label)

    m_col = re.match(
        r"^([^:?]{3,42}(?::\s+(?:Part|Vol\.?|Chapter|Season|Episode)\s+[A-Za-z0-9]+)?):\s+(.+)$",
        title,
    )
    if m_col:
        prefix = m_col.group(1).strip(" \"'")
        words = prefix.split()
        if words and words[0].lower() not in _QUESTION_STARTERS and "$" not in prefix:
            canon, label = _canonical_entity_pair(words)
            if canon and canon not in _GENERIC_SINGLE_NOUNS:
                return (canon, label)

    # Priority 2b: Quoted primary title subject (excluding quoted single spoken words after 'say')
    for m_q in re.finditer(r'["\u201c\']([^"\u201d\']{4,42})["\u201d\']', title):
        before = title[:m_q.start()].lower()
        if re.search(r"\bsay\s*$", before):
            continue
        inner = m_q.group(1).strip()
        words = inner.split()
        if len(words) >= 2 or (len(words) == 1 and len(inner) >= 6 and words[0][0].isupper()):
            canon, label = _canonical_entity_pair(words)
            if canon and canon not in _GENERIC_SINGLE_NOUNS:
                return (canon, label)

    # Priority 3a: Bilateral entity pair ("EntityA x EntityB", "Will EntityA and EntityB", or "EntityA-EntityB")
    m_bilat = re.search(r"\b([A-Z][A-Za-z]{1,})\s+x\s+([A-Z][A-Za-z]{1,})\b", title)
    if not m_bilat:
        m_bilat = re.search(r"^(?:Will|Do|Does)\s+([A-Z][A-Za-z]{2,})\s+and\s+([A-Z][A-Za-z]{2,})\b", title)
    if not m_bilat:
        for cand_h in re.finditer(r"\b([A-Z][A-Za-z]{1,})-([A-Z][A-Za-z]{2,})\b", title):
            h1, h2 = cand_h.group(1), cand_h.group(2)
            if (
                h1.lower() not in _NON_ENTITY_PROPER
                and h2.lower() not in _NON_ENTITY_PROPER
                and h1.lower() not in _HYPHEN_PAIR_SKIP
                and h2.lower() not in _HYPHEN_PAIR_SKIP
            ):
                m_bilat = cand_h
                break
    if m_bilat:
        e1, e2 = m_bilat.group(1), m_bilat.group(2)
        if e1.lower() not in _NON_ENTITY_PROPER and e2.lower() not in _NON_ENTITY_PROPER:
            canon = "_".join(sorted([e1.lower(), e2.lower()]))
            return (canon, f"{e1}\u2013{e2}")

    # Priority 3b: First strong capitalized proper-noun span (ignoring question starters & prep-locations)
    raw_words = title.split()
    cleaned_words: list[str] = []
    for w in raw_words:
        tok = re.sub(r"^(?:['\"\u201c(]+)|(?:['\"\u201d),:;?!.]+)$", "", w)
        tok = re.sub(r"[\'\u2019]s$", "", tok)
        cleaned_words.append(tok)

    spans: list[list[str]] = []
    cur: list[str] = []
    for idx, tok in enumerate(cleaned_words):
        if not tok or not tok[0].isalpha():
            if cur:
                spans.append(cur)
                cur = []
            continue
        low = tok.lower()
        prev_low = cleaned_words[idx - 1].lower() if idx > 0 else ""
        is_cap = tok[0].isupper()
        is_roman = bool(re.fullmatch(r"(?:II|III|IV|VI|VII|VIII|IX|X)", tok))
        is_excluded = (
            low in _QUESTION_STARTERS
            or low in _NON_ENTITY_PROPER
            or (idx == 0 and low in {"another", "next", "will", "the", "a", "an"})
            or (tok in _ACRONYM_ENTITY_SKIP)
            or (not cur and prev_low in _LOCATION_PREPS and len(cleaned_words) > 4)
        )
        if (is_cap or is_roman) and not is_excluded and len(tok) >= 2:
            cur.append(tok)
            if len(cur) >= 3:
                spans.append(cur)
                cur = []
        else:
            if cur:
                spans.append(cur)
                cur = []
    if cur:
        spans.append(cur)

    # Strip stray punctuation from subtitle colons inside entity tokens cleanly
    if spans:
        pass
    for span in spans:
        span = [t.rstrip(":") for t in span if t.rstrip(":")]
        if len(span) == 1 and (span[0].lower() in _GENERIC_SINGLE_NOUNS or len(span[0]) < 3):
            continue
        canon, label = _canonical_entity_pair(span)
        if canon and canon not in _GENERIC_SINGLE_NOUNS:
            return (canon, label)

    # Priority 3c: Predicate noun fallback for lowercase natural-phenomena/event series
    tokens = [
        tok for tok in re.findall(r"[a-z]{4,}", title.lower())
        if tok not in _STEM_STOPWORDS
    ]
    if len(tokens) < 2:
        return None
    key_tokens = tokens[:2]
    return ("_".join(sorted(key_tokens)), " ".join(w.capitalize() for w in key_tokens))


def discover_candidate_families(
    markets: Iterable[Any],
    *,
    covered_ids: frozenset[int] | set[int] = frozenset(),
    now: datetime | None = None,
    min_markets: int = 5,
    min_age_hours: float = 0.0,
) -> tuple[list[Family], dict[int, dict[str, Any]]]:
    """Build uncovered candidate families via ``grouping_families`` plus generic frame/stem groups."""
    ref_now = _parse_iso_dt(now) or datetime.now(timezone.utc)
    normalized: dict[int, dict[str, Any]] = {}
    atoms: list[Atom] = []
    eligible_ids: set[int] = set()

    for raw in markets:
        m = normalize_market_record(raw)
        mid = m.get("id")
        if mid is None:
            continue
        title_str = str(m.get("name") or m.get("title") or "")
        if (
            str(m.get("category") or "").lower() == "game_prop"
            or m.get("event_id") is not None
            or re.search(r"\bvs\.?\s+", title_str, re.IGNORECASE)
        ):
            continue
        mid_int = int(mid)
        normalized[mid_int] = m

        # Keep markets even if settled on eligible check? Condition 5 rejects settled families;
        # exclude dead non-priced markets from eligibility while checking settled status in proposer.
        outcomes = m.get("outcomes") or []
        has_price = any(
            (o.get("current_probability") if isinstance(o, Mapping) else None) is not None
            for o in outcomes
        ) or m.get("current_probability") is not None or m.get("probability") is not None
        if not has_price:
            continue
        created_dt = _parse_iso_dt(m.get("created_at")) or ref_now
        if min_age_hours > 0 and (ref_now - created_dt).total_seconds() < min_age_hours * 3600:
            continue
        eligible_ids.add(mid_int)

        out_names = tuple(
            str(o.get("name") or "") for o in outcomes if isinstance(o, Mapping) and o.get("name")
        )[:40]
        atoms.append(Atom(
            market_id=mid_int,
            source=str(m.get("source") or "kalshi").lower(),
            external_id=str(m.get("external_id") or ""),
            group_id=str(m.get("group_id")) if m.get("group_id") else None,
            title=str(m.get("name") or m.get("title") or ""),
            event_title=str(m.get("event_title")) if m.get("event_title") else None,
            outcome_names=out_names,
            created_at=created_dt,
        ))

    grouping = build_families(atoms)
    candidates = uncovered_families(
        grouping.families,
        covered=covered_ids,
        eligible=eligible_ids,
        min_markets=min_markets,
    )

    claimed_ids = {mid for fam in candidates for mid in fam.member_ids}
    # Second generic pass for uncovered markets lacking identical series/event keys
    stem_buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    stem_labels: dict[str, str] = {}
    for mid_int in sorted(eligible_ids):
        if mid_int in covered_ids or mid_int in claimed_ids:
            continue
        m = normalized[mid_int]
        stem = _generic_stem_key(m)
        if stem is None:
            continue
        skey, slabel = stem
        stem_buckets[skey].append(m)
        stem_labels.setdefault(skey, slabel)

    for skey, rows in sorted(stem_buckets.items()):
        if len(rows) < min_markets:
            continue
        members = tuple(sorted(int(r["id"]) for r in rows))
        first_dt = min((_parse_iso_dt(r.get("created_at")) or ref_now) for r in rows)
        candidates.append(Family(
            kind="topic_stem",
            key=skey,
            label=stem_labels[skey],
            member_ids=members,
            first_created_at=first_dt,
        ))

    return candidates, normalized


def score_family_interest(
    family: Family,
    markets_by_id: Mapping[int, Mapping[str, Any]],
    *,
    now: datetime | None = None,
    dismissed_keys: Iterable[str] = (),
) -> float:
    """Score a family by top-5 reader interest (NEVER raw market count above floor)."""
    ref_now = _parse_iso_dt(now) or datetime.now(timezone.utc)
    members = [markets_by_id[mid] for mid in family.member_ids if mid in markets_by_id]
    if not members:
        return 0.0

    member_scores: list[float] = []
    sources: set[str] = set()
    max_move = 0.0
    near_catalyst = False

    for m in members:
        sources.add(str(m.get("source") or "").lower())
        if int(m.get("sources_count") or 1) >= 2:
            sources.update({"kalshi", "polymarket"})
        res = score_market_interestingness(dict(m), now=ref_now)
        member_scores.append(res.score)

        mv = float(m.get("max_movement_24h") or 0.0)
        if abs(mv) > max_move:
            max_move = abs(mv)

        res_dt = _parse_iso_dt(m.get("resolution_date") or m.get("close_time"))
        if res_dt is not None:
            days = (res_dt - ref_now).total_seconds() / 86400.0
            if 1.0 <= days <= 30.0:
                near_catalyst = True

    top_k = sorted(member_scores, reverse=True)[:5]
    base_mean = sum(top_k) / max(1, len(top_k))
    cross_venue_bonus = 8.0 if len({s for s in sources if s}) >= 2 else 0.0
    move_bonus = min(12.0, (max_move * 100.0 if max_move <= 1.0 else max_move) * 0.8)
    catalyst_bonus = 6.0 if near_catalyst else 0.0

    kicker_low = resolve_kicker(members, default="markets").lower()
    mix_bonus = _CATEGORY_MIX_BONUS.get(kicker_low, 4.0)

    dismissed = {str(k).strip().lower() for k in dismissed_keys if k}
    dismiss_penalty = (
        -25.0
        if (family.fingerprint.lower() in dismissed or family.key.lower() in dismissed)
        else 0.0
    )

    total = base_mean + cross_venue_bonus + move_bonus + catalyst_bonus + mix_bonus + dismiss_penalty
    return round(max(0.0, total), 2)


def propose_top_containers(
    markets: Iterable[Any],
    *,
    covered_ids: frozenset[int] | set[int] = frozenset(),
    now: datetime | None = None,
    max_proposals: int = 5,
    audit_top_n: int = 15,
    min_markets: int = 5,
    dismissed_keys: Iterable[str] = (),
) -> dict[str, Any]:
    """Rank uncovered families by interest and compose top ``preview`` Kit pages + full audit."""
    ref_now = _parse_iso_dt(now) or datetime.now(timezone.utc)
    families, by_id = discover_candidate_families(
        markets,
        covered_ids=covered_ids,
        now=ref_now,
        min_markets=min_markets,
    )

    scored: list[tuple[float, Family]] = [
        (score_family_interest(fam, by_id, now=ref_now, dismissed_keys=dismissed_keys), fam)
        for fam in families
    ]
    # Strict descending interest score (NEVER size-first)
    scored.sort(key=lambda item: (-item[0], item[1].fingerprint, item[1].label))

    pages: list[dict[str, Any]] = []
    audit: list[dict[str, Any]] = []
    used_slugs: set[str] = set()

    for rank_idx, (interest, fam) in enumerate(scored[:max(audit_top_n, max_proposals * 3)], 1):
        members = [by_id[mid] for mid in fam.member_ids if mid in by_id]
        kicker = resolve_kicker(members)
        if any(is_settled_market(m, ref_now) for m in members):
            outcome: dict[str, Any] = {
                "accepted": False,
                "refusal_reason": "refused_contains_settled_member",
                "sections_built": 0,
                "variants": [],
            }
        else:
            outcome = propose_container_page_for_family(
                fam.label,
                members,
                now=ref_now,
                kicker=kicker,
                family_fingerprint=fam.fingerprint,
            )

        entry: dict[str, Any] = {
            "rank": rank_idx,
            "family_fingerprint": fam.fingerprint,
            "kind": fam.kind,
            "key": fam.key,
            "label": fam.label,
            "kicker": kicker,
            "interest_score": interest,
            "family_size": fam.size,
            "accepted": bool(outcome.get("accepted")),
            "selected_for_preview": False,
            "refusal_reason": outcome.get("refusal_reason"),
            "variants": outcome.get("variants") or (outcome.get("page", {}).get("variants") or []),
        }
        if outcome.get("accepted") and len(pages) < max_proposals:
            page = dict(outcome["page"])
            page["interest_score"] = interest
            if page["slug"] not in used_slugs:
                used_slugs.add(page["slug"])
                pages.append(page)
                entry["selected_for_preview"] = True
                entry["slug"] = page["slug"]
                entry["headline"] = page["title"]
            else:
                entry["accepted"] = False
                entry["refusal_reason"] = "refused_duplicate_page_slug"
        audit.append(entry)

    return {
        "kit_page_version": 1,
        "snapshot_captured_at": ref_now.isoformat(),
        "uncovered_family_count": len(families),
        "count": len(pages),
        "pages": pages,
        "ranked_audit": audit,
    }
