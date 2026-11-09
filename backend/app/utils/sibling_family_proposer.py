"""The ``sibling_family`` proposer: discovers sibling families from live markets and proposes selector-based definitions (#12372, Epic #12288).

PILLAR: DISCOVER / MATCHING / TRUTH · SHIP: a program, not a person, finds
sibling families in live markets and proposes ``sibling_family`` definitions.
Each proposal is a pattern (``title_ilike`` + ``template``) or a venue event
(``group_id`` + ``template``), never a list of IDs, and is checked by
``sibling_family``'s own truth checks (``select_sibling_family``) plus bounded
model verification under Decide 61-A (price printed before each run, $5 cap per
run, $30 cap for November; no model call during a page load).
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
from typing import Any, Callable, Mapping, Optional, Sequence
import urllib.request

from app.services.llm_models import LEGACY_MODEL
from app.utils.roundup_containers import (
    RoundupMembers,
    RoundupRefusal,
    validate_roundup_definition,
)
from app.utils.sibling_family import (
    DEFAULT_SIBLING_LEVEL,
    DEFAULT_SIBLING_RELATIONS,
    MEMBERSHIP_SIBLING_FAMILY,
    PRODUCER_KIND_SIBLING_FAMILY,
    _clean_subject_display,
    _extract_stated_deadline,
    _FORBIDDEN_NARRATIVE_RE,
    _tokenize_title,
    detect_sibling_template_pair,
    fold_template_key,
    select_sibling_family,
)
from app.utils.week_events import export_roundup_card_words_390px

__all__ = [
    "DEFAULT_BACKEND_DATA_JSON_OUT",
    "DEFAULT_JSON_OUT",
    "DEFAULT_MD_OUT",
    "DEFAULT_PROPOSER_MODEL",
    "HARD_RUN_COST_CAP_USD",
    "NOVEMBER_MONTHLY_CAP_USD",
    "REGISTERED_SIBLING_TEMPLATES",
    "build_family_verification_prompt",
    "build_proposed_sibling_definition",
    "enforce_proposer_cost_cap",
    "estimate_proposer_cost_usd",
    "format_grouping_candidates_markdown",
    "is_excluded_sibling_market",
    "nominate_sibling_families",
    "print_preflight_cost_banner",
    "propose_sibling_families",
    "verify_heading_from_market_words",
    "verify_word_for_word_quote",
    "write_grouping_candidate_reports",
]

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_JSON_OUT = REPO_ROOT / "docs" / "discover" / "grouping-candidates-2026-11.json"
DEFAULT_BACKEND_DATA_JSON_OUT = (
    REPO_ROOT / "backend" / "data" / "discover" / "grouping-candidates-2026-11.json"
)
DEFAULT_MD_OUT = REPO_ROOT / "docs" / "discover" / "grouping-candidates-2026-11.md"

# Decide 61-A spend caps ($5 per run, $30 for November; December requires Alex's word).
HARD_RUN_COST_CAP_USD = 5.00
NOVEMBER_MONTHLY_CAP_USD = 30.00

DEFAULT_PROPOSER_MODEL = LEGACY_MODEL
# Conservative pricing ($/1M tokens) used for pre-flight estimation.
DEFAULT_INPUT_COST_PER_MTOK_USD = 0.60
DEFAULT_OUTPUT_COST_PER_MTOK_USD = 2.40
DEFAULT_MAX_OUTPUT_TOKENS = 450

# Already-registered hand-built sibling_family templates in backend/data/containers/*.json
REGISTERED_SIBLING_TEMPLATES: frozenset[str] = frozenset(
    {
        "will * record snow",
        "will * be featured on gta vi the album",
        "* rotten tomatoes score",
        "will * announce a presidential run",
        "how many grand slam singles titles will * win",
    }
)

# Standing exclusions (#12221 Part 1 §2 guardrail 5; handoff §5; #11940 §4).
_EXCLUSION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "mention_or_statement",
        re.compile(
            r"\b(?:what\s+will\s+.+\s+say|say\s+during|mention(?:ed)?\s+(?:during|in|at|by)|how\s+many\s+(?:tweets|posts|truths)|press\s+conference|transcript|publicly\s+(?:praise|insult|criticize|attack))\b",
            re.IGNORECASE,
        ),
    ),
    (
        "daily_or_intraday",
        re.compile(
            r"\b(?:up\s+or\s+down|\d{1,2}:\d{2}\s*(?:am|pm)\s*-\s*\d{1,2}:\d{2}\s*(?:am|pm)|today\s+at\s+\d|intraday)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "financial_or_crypto",
        re.compile(
            r"\b(?:bitcoin|btc|ethereum|eth|solana|dogecoin|xrp|crypto|s&p\s*500|nasdaq|dow\s+jones|stock\s+price|share\s+price|market\s+cap|token\s+price|close\s+above\s+\$\d)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "combination_or_path",
        re.compile(
            r"\b(?:senate\s+combo|combo|parlay|win\s+both|both\s+.+\s+and\s+.+\s+win|exact\s+order|path\s+to)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "foreign_election",
        re.compile(
            r"\b(?:prime\s+minister\s+of|chancellor\s+of|bundestag|knesset|uk\s+general\s+election|canadian\s+(?:federal\s+)?election|french\s+presidential|german\s+(?:federal\s+)?election|australian\s+(?:federal\s+)?election|brazilian\s+presidential|mexican\s+presidential|spain\s+general\s+election|spanish\s+(?:general\s+)?election|italian\s+(?:general\s+)?election|japanese\s+(?:general\s+)?election|south\s+korean\s+(?:presidential\s+)?election|indian\s+general\s+election|dutch\s+(?:general\s+)?election|polish\s+(?:presidential\s+)?election)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "death_health_or_crime",
        re.compile(
            r"\b(?:pass\s+away|die\s+in|death\s+of|assassinated|arrested|indicted|convicted|sentenced|prison|jail|hospitalized|diagnosed\s+with|cancer|pardoned\s+from\s+prison)\b",
            re.IGNORECASE,
        ),
    ),
)

_ALLOWED_HEADING_FILLER_TOKENS: frozenset[str] = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "at",
        "be",
        "before",
        "by",
        "for",
        "from",
        "in",
        "into",
        "is",
        "it",
        "of",
        "on",
        "or",
        "the",
        "to",
        "what",
        "when",
        "where",
        "which",
        "who",
        "will",
        "with",
        "deadline",
        "cities",
        "city",
        "candidates",
        "candidate",
        "teams",
        "team",
        "players",
        "player",
        "movies",
        "movie",
        "films",
        "film",
        "states",
        "state",
        "people",
        "person",
        "artists",
        "artist",
        "countries",
        "country",
        "companies",
        "company",
        "drivers",
        "driver",
        "fighters",
        "fighter",
        "golfers",
        "golfer",
        "shows",
        "show",
        "games",
        "game",
        "races",
        "race",
        "contenders",
        "nominees",
        "clubs",
        "coach",
        "coaches",
    }
)


def is_excluded_sibling_market(
    name: str,
    *,
    category: Optional[str] = None,
    description: Optional[str] = None,
) -> tuple[bool, Optional[str]]:
    """Return ``(True, reason)`` when a market falls under #12221 Part 1 §2's standing exclusions."""
    text = str(name or "").strip()
    if not text:
        return True, "empty_title"
    cat = str(category or "").strip().lower()
    if cat in {"crypto", "finance", "stocks"}:
        return True, "financial_or_crypto"
    for reason, pattern in _EXCLUSION_PATTERNS:
        if pattern.search(text):
            return True, reason
    return False, None


def _norm_ws(text: str) -> str:
    return " ".join(str(text or "").split())


def verify_word_for_word_quote(quote: str, market: Mapping[str, Any]) -> bool:
    """Verify that ``quote`` appears word for word in ``market``'s description or title."""
    clean_quote = _norm_ws(quote)
    if len(clean_quote) < 12:
        return False
    desc = _norm_ws(str(market.get("description") or ""))
    name = _norm_ws(str(market.get("name") or ""))
    corpus = f"{name} {desc}".strip()
    return clean_quote in desc or clean_quote in name or clean_quote in corpus


def verify_heading_from_market_words(
    heading: str,
    markets: Sequence[Mapping[str, Any]],
    *,
    subject_unit: str = "",
) -> bool:
    """Verify that ``heading`` uses only words from ``markets``' own titles (plus ``{deadline}`` / ``subject_unit``) and no forbidden words."""
    clean = str(heading or "").strip()
    if not clean:
        return False
    if _FORBIDDEN_NARRATIVE_RE.search(clean):
        return False
    if "*" in clean or clean.endswith(":"):
        return False

    without_placeholder = clean.replace("{deadline}", " ")
    if "{" in without_placeholder or "}" in without_placeholder:
        return False
    heading_tokens = [f for _, f in _tokenize_title(without_placeholder)]
    if len(heading_tokens) < 3:
        return False

    market_vocab: set[str] = set(_ALLOWED_HEADING_FILLER_TOKENS)
    if subject_unit:
        for _, f in _tokenize_title(subject_unit):
            market_vocab.add(f)
    for m in markets:
        for _, f in _tokenize_title(str(m.get("name") or "")):
            market_vocab.add(f)

    for tok in heading_tokens:
        if tok not in market_vocab:
            return False
    return True


def _infer_subject_unit(category: str, template_key: str, subjects: Sequence[str]) -> str:
    cat = str(category or "").strip().lower()
    tk = template_key.lower()
    if "city" in tk or "snow" in tk or "rain" in tk or "degrees" in tk or "temperature" in tk or cat == "weather":
        return "cities"
    if "rotten tomatoes" in tk or "box office" in tk or "opening weekend" in tk:
        return "movies"
    if "album" in tk or "grammy" in tk or "song" in tk:
        return "artists"
    if "presidential" in tk or "senate" in tk or "governor" in tk or "nominee" in tk or cat == "politics":
        return "candidates"
    if cat in {"basketball", "football", "baseball", "hockey", "soccer", "nfl", "nba", "mlb", "nhl"}:
        if any(" " in s and any(w in s.lower() for w in ("fc", "united", "city", "celtics", "lakers", "chiefs", "bills", "eagles", "yankees", "dodgers")) for s in subjects):
            return "teams"
        return "contenders"
    return "subjects"


def _template_to_ilike_pattern(template_key: str, sample_titles: Sequence[str]) -> str:
    """Build a SQL ``ILIKE`` selector pattern from the family's shared prefix and suffix tokens."""
    if not sample_titles:
        return f"%{template_key.replace('*', '%')}%"
    stems = [_extract_stated_deadline(t).stem_text for t in sample_titles]
    tok_lists = [_tokenize_title(s) for s in stems if s]
    if not tok_lists:
        return f"%{template_key.replace('*', '%')}%"

    # Use raw tokens from the first stem where folded tokens match the template's prefix/suffix.
    words = template_key.split()
    if "*" not in words:
        return f"%{' '.join(words)}%"
    star_idx = words.index("*")
    prefix_folded = words[:star_idx]
    suffix_folded = words[star_idx + 1 :]

    first_toks = tok_lists[0]
    prefix_raw = " ".join(raw for raw, _ in first_toks[: len(prefix_folded)]).strip()
    suffix_raw = (
        " ".join(raw for raw, _ in first_toks[len(first_toks) - len(suffix_folded) :]).strip()
        if suffix_folded
        else ""
    )

    if prefix_raw and suffix_raw:
        return f"{prefix_raw} % {suffix_raw}%"
    if prefix_raw:
        return f"{prefix_raw} %"
    if suffix_raw:
        return f"% {suffix_raw}%"
    return f"%{template_key.replace('*', '%')}%"


def _build_default_heading(
    template_key: str,
    sample_titles: Sequence[str],
    *,
    subject_unit: str,
) -> str:
    """Construct a deterministic heading from the markets' own words (with ``{deadline}`` when titles state a deadline)."""
    has_stated_deadline = any(
        bool(_extract_stated_deadline(t).phrase) for t in sample_titles
    )
    if sample_titles:
        first_stem = _extract_stated_deadline(sample_titles[0]).stem_text.rstrip("?.!").strip()
        toks = _tokenize_title(first_stem)
        words = template_key.split()
        if "*" in words and toks:
            star_idx = words.index("*")
            prefix_len = star_idx
            suffix_len = len(words) - star_idx - 1
            prefix_raw = " ".join(raw for raw, _ in toks[:prefix_len]).strip()
            suffix_raw = (
                " ".join(raw for raw, _ in toks[len(toks) - suffix_len :]).strip()
                if suffix_len > 0
                else ""
            )
            replacement = subject_unit if subject_unit and subject_unit != "subjects" else "who"
            if prefix_raw.lower() == "will":
                replacement = f"which {subject_unit[:-1]}" if subject_unit.endswith("s") and subject_unit != "series" else "who"
            parts = [p for p in (prefix_raw, replacement, suffix_raw) if p]
            stem_heading = " ".join(parts)
            if has_stated_deadline:
                return f"{stem_heading} {{deadline}}?"
            return f"{stem_heading}?"
    base = template_key.replace("*", subject_unit or "who").strip()
    return f"{base.capitalize()} {{deadline}}?" if has_stated_deadline else f"{base.capitalize()}?"


def nominate_sibling_families(
    markets: Mapping[int, Mapping[str, Any]] | Sequence[Mapping[str, Any]],
    *,
    min_members: int = 3,
    exclude_registered: bool = True,
) -> list[dict[str, Any]]:
    """Discover candidate ``sibling_family`` sets from live markets using provider events and structural title templates."""
    seq = markets.values() if isinstance(markets, Mapping) else markets
    clean_markets: list[dict[str, Any]] = []
    seen_ids: set[int] = set()

    for m in seq:
        if not isinstance(m, Mapping):
            continue
        mid = m.get("id")
        if not isinstance(mid, int) or isinstance(mid, bool) or mid <= 0 or mid in seen_ids:
            continue
        status = str(m.get("status") or "open").strip().lower()
        if status != "open":
            continue
        src = str(m.get("source") or "").strip().lower()
        if not src:
            raw_srcs = m.get("sources")
            if isinstance(raw_srcs, Sequence) and not isinstance(raw_srcs, (str, bytes)) and raw_srcs:
                src = str(raw_srcs[0] or "").strip().lower()
        if src not in {"kalshi", "polymarket"}:
            continue
        name = str(m.get("name") or "").strip()
        cat = str(m.get("llm_sport_category") or m.get("category") or "other").strip().lower()
        excluded, _reason = is_excluded_sibling_market(
            name, category=cat, description=m.get("description")
        )
        if excluded:
            continue
        seen_ids.add(mid)
        entry = dict(m)
        entry["id"] = mid
        entry["source"] = src
        clean_markets.append(entry)

    # Group by source and discover structural templates on deadline-stripped stems.
    by_source: dict[str, list[dict[str, Any]]] = {}
    for m in clean_markets:
        by_source.setdefault(m["source"], []).append(m)

    nominated: list[dict[str, Any]] = []
    for src, src_markets in sorted(by_source.items()):
        stems = {
            int(m["id"]): _extract_stated_deadline(str(m.get("name") or "")).stem_text
            for m in src_markets
        }
        by_id = {int(m["id"]): m for m in src_markets}
        groups: dict[str, dict[int, str]] = {}

        # Bucket by shared prefix/suffix length + token hints so 5,000+ markets group fast without O(N^2) blowup.
        token_buckets: dict[tuple[str, str], list[int]] = {}
        for m in src_markets:
            mid = int(m["id"])
            toks = _tokenize_title(stems[mid])
            if len(toks) < 3:
                continue
            first_tok = toks[0][1]
            last_tok = toks[-1][1]
            token_buckets.setdefault((first_tok, last_tok), []).append(mid)
            # Also bucket by first two tokens for suffix-varying subjects, and last two tokens for prefix-varying subjects.
            token_buckets.setdefault((first_tok, toks[1][1]), []).append(mid)
            token_buckets.setdefault((toks[-2][1], last_tok), []).append(mid)

        compared_pairs: set[tuple[int, int]] = set()
        for bucket_mids in token_buckets.values():
            if len(bucket_mids) < 2 or len(bucket_mids) > 250:
                continue
            for i in range(len(bucket_mids)):
                id_i = bucket_mids[i]
                for j in range(i + 1, len(bucket_mids)):
                    id_j = bucket_mids[j]
                    pair_key = (id_i, id_j) if id_i < id_j else (id_j, id_i)
                    if pair_key in compared_pairs:
                        continue
                    compared_pairs.add(pair_key)
                    res, _err = detect_sibling_template_pair(stems[id_i], stems[id_j])
                    if res is None:
                        continue
                    t_key, subj_i, subj_j = res
                    # Reject subject slots that swallowed a predicate/ladder clause (>4 tokens or verb/ladder phrase).
                    if (
                        len(subj_i.split()) > 4
                        or len(subj_j.split()) > 4
                        or re.search(
                            r"\b(?:have\s+more\s+than|finish\s+in\s+the|finish\s+\d|ranked\s+team|top\s+\d+|players\s+to|teams\s+to)\b",
                            f"{subj_i} {subj_j}",
                            re.IGNORECASE,
                        )
                    ):
                        continue
                    fam = groups.setdefault(t_key, {})
                    fam.setdefault(id_i, subj_i)
                    fam.setdefault(id_j, subj_j)

        # Assign each market only to its most specific template (longest shared token count)
        # so broad super-templates never merge distinct thresholds or measures.
        best_template_by_mid: dict[int, tuple[int, str]] = {}
        for t_key, subj_map in groups.items():
            if len(subj_map) < min_members:
                continue
            specificity = len([w for w in t_key.split() if w != "*"])
            for mid in subj_map:
                prev = best_template_by_mid.get(mid)
                if prev is None or (specificity, t_key) > prev:
                    best_template_by_mid[mid] = (specificity, t_key)

        for t_key, raw_subj_map in sorted(groups.items()):
            if exclude_registered and fold_template_key(t_key) in REGISTERED_SIBLING_TEMPLATES:
                continue
            subj_map = {
                mid: subj
                for mid, subj in raw_subj_map.items()
                if best_template_by_mid.get(mid, (0, ""))[1] == t_key
            }
            if len(subj_map) < min_members:
                continue
            member_list = [by_id[mid] for mid in sorted(subj_map.keys())]
            # Check if all members share a non-empty provider group_id.
            gids = {
                str(m.get("group_id") or "").strip()
                for m in member_list
                if str(m.get("group_id") or "").strip()
            }
            shared_group_id = next(iter(gids)) if len(gids) == 1 and len(gids) == len([m for m in member_list if m.get("group_id")]) else None
            sample_titles = [str(m.get("name") or "") for m in member_list]
            title_ilike = _template_to_ilike_pattern(t_key, sample_titles)
            cat = str(
                member_list[0].get("llm_sport_category")
                or member_list[0].get("category")
                or "other"
            ).strip().lower()
            subjects = [
                _clean_subject_display(subj_map[mid], strip_state_suffix=False)
                for mid in sorted(subj_map.keys())
            ]
            unit = _infer_subject_unit(cat, t_key, subjects)
            slug_stem = re.sub(r"[^a-z0-9]+", "-", t_key.replace("*", unit)).strip("-")[:48]
            slug = f"proposed-{src}-{slug_stem}".strip("-")

            nominated.append(
                {
                    "slug": slug,
                    "source": src,
                    "template_key": t_key,
                    "group_id": shared_group_id,
                    "title_ilike": title_ilike,
                    "category": cat,
                    "subject_unit": unit,
                    "subjects": subjects,
                    "members": member_list,
                }
            )

    # Sort nominated families deterministically by (member count desc, slug asc).
    nominated.sort(key=lambda f: (-len(f["members"]), f["slug"]))
    return nominated


def build_proposed_sibling_definition(
    family: Mapping[str, Any],
    *,
    generated_at: str,
    model: str,
    card_heading: Optional[str] = None,
) -> dict[str, Any]:
    """Build a selector-based ``sibling_family`` container definition (never an ID list)."""
    members = list(family.get("members") or [])
    sample_titles = [str(m.get("name") or "") for m in members]
    t_key = str(family["template_key"])
    src = str(family["source"]).strip().lower()
    cat = str(family.get("category") or "other").strip().lower()
    unit = str(family.get("subject_unit") or "subjects").strip()

    heading = card_heading
    if not heading or not verify_heading_from_market_words(heading, members, subject_unit=unit):
        heading = _build_default_heading(t_key, sample_titles, subject_unit=unit)

    has_stated_deadline = "{deadline}" in heading
    display_name = heading.replace(" {deadline}", "").replace("{deadline}", "").strip()
    kicker_prefix = cat.upper().replace("_", " ") if cat != "other" else "SIBLING FAMILY"

    # Determine target outcome name from member outcomes.
    first_outs = (members[0].get("outcomes") or members[0].get("top_outcomes") or ()) if members else ()
    out_names = [
        str(o.get("name") or o.get("label") or "").strip()
        for o in first_outs
        if isinstance(o, Mapping)
    ]
    if set(n.lower() for n in out_names if n) <= {"yes", "no"} or not out_names:
        outcome_name = "Yes"
    else:
        outcome_name = "auto_shared_rung"

    rule: dict[str, Any] = {
        "producer": PRODUCER_KIND_SIBLING_FAMILY,
        "source": src,
        "template": t_key,
        "title_ilike": str(family["title_ilike"]),
        "title_template": heading,
        "kicker_prefix": kicker_prefix,
        "kicker_include_date": has_stated_deadline,
        "subject_unit": unit,
        "outcome_name": outcome_name,
        "lead_rule": "nearest_open_deadline",
        "min_numbered_members": 3,
        "card_rows": 5,
    }
    if family.get("group_id"):
        rule["group_id"] = str(family["group_id"])

    definition: dict[str, Any] = {
        "slug": str(family["slug"]),
        "name": display_name,
        "kind": "roundup",
        "category": cat,
        "tag": cat.upper().replace("_", " "),
        "kicker": kicker_prefix,
        "membership": MEMBERSHIP_SIBLING_FAMILY,
        "relations": list(DEFAULT_SIBLING_RELATIONS),
        "level": DEFAULT_SIBLING_LEVEL,
        "section_title": "By deadline",
        "footer": "Each row is its own market. They don't add up to 100%.",
        "authored_by": {
            "kind": "proposer",
            "proposer": "sibling_family_proposer",
            "model": model,
            "generated_at": generated_at,
            "licensed": False,
        },
        "rule": rule,
    }
    validate_roundup_definition(definition, path=str(family["slug"]))
    return definition


def _extract_default_rule_quote(market: Mapping[str, Any]) -> str:
    """Extract a verbatim word-for-word sentence from ``market``'s description or title."""
    desc = _norm_ws(str(market.get("description") or ""))
    if len(desc) >= 16:
        return desc[:220].strip()
    return _norm_ws(str(market.get("name") or ""))


def build_family_verification_prompt(family: Mapping[str, Any]) -> str:
    """Build the bounded verification prompt for one candidate ``sibling_family`` (#12221 Part 1 §2)."""
    members = list(family.get("members") or [])
    m_a = members[0]
    m_b = members[1]
    member_summaries = [
        {
            "id": int(m["id"]),
            "name": m.get("name"),
            "resolution_date": m.get("resolution_date"),
            "description": _norm_ws(str(m.get("description") or ""))[:360] or None,
        }
        for m in members[:10]
    ]
    return (
        "Verify this candidate sibling_family market group for Bain Luck Discover.\n"
        "Do three bounded jobs and return ONLY a JSON object with this exact schema:\n"
        "{\n"
        '  "only_subject_differs": true|false,\n'
        '  "only_subject_differs_reason": "one concise sentence",\n'
        '  "market_a_id": <int>,\n'
        '  "market_a_quote": "exact word-for-word substring copied from market_a description or name",\n'
        '  "market_b_id": <int>,\n'
        '  "market_b_quote": "exact word-for-word substring copied from market_b description or name",\n'
        '  "already_happened_market_ids": [<int>, ...],\n'
        '  "already_happened_reason": "empty string if none already happened, else concise reason",\n'
        '  "card_heading": "heading taken strictly from the markets\' own words (may include {deadline})"\n'
        "}\n\n"
        f"Template key: {family['template_key']}\n"
        f"Market A (id={m_a['id']}): name={m_a.get('name')!r}, description={_norm_ws(str(m_a.get('description') or ''))[:400]!r}\n"
        f"Market B (id={m_b['id']}): name={m_b.get('name')!r}, description={_norm_ws(str(m_b.get('description') or ''))[:400]!r}\n"
        f"Sample members:\n{json.dumps(member_summaries, indent=2)}\n"
    )


def estimate_proposer_cost_usd(
    prompts: Sequence[str],
    *,
    input_cost_per_mtok: float = DEFAULT_INPUT_COST_PER_MTOK_USD,
    output_cost_per_mtok: float = DEFAULT_OUTPUT_COST_PER_MTOK_USD,
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
) -> float:
    """Estimate worst-case USD spend for a list of verification prompts."""
    if not prompts:
        return 0.0
    total_in_tokens = sum(max(1, int(math.ceil(len(str(p)) / 3.5))) for p in prompts)
    total_out_tokens = len(prompts) * int(max_output_tokens)
    cost = (
        (total_in_tokens / 1_000_000.0) * float(input_cost_per_mtok)
        + (total_out_tokens / 1_000_000.0) * float(output_cost_per_mtok)
    )
    return round(cost, 4)


def print_preflight_cost_banner(
    family_count: int,
    estimated_cost_usd: float,
    *,
    november_spent_prior_usd: float = 0.0,
    now: Optional[datetime] = None,
) -> str:
    """Print and return the mandatory Decide 61-A pre-run spend line before any model call."""
    effective_now = now or datetime.now(timezone.utc)
    if effective_now.year > 2026 or (effective_now.year == 2026 and effective_now.month >= 12):
        raise ValueError(
            "Decide 61-A: a December model-spend cap requires Alex's word before running."
        )
    projected_nov = round(float(november_spent_prior_usd) + float(estimated_cost_usd), 4)
    banner = (
        f"[61-A] Sibling-family proposer pre-flight: families={family_count}, "
        f"estimated_run_cost=${estimated_cost_usd:.4f} (run cap ${HARD_RUN_COST_CAP_USD:.2f}), "
        f"november_cumulative=${projected_nov:.4f} / ${NOVEMBER_MONTHLY_CAP_USD:.2f}"
    )
    print(banner, flush=True)
    return banner


def enforce_proposer_cost_cap(
    prompts: Sequence[str],
    *,
    max_run_cost_usd: float = HARD_RUN_COST_CAP_USD,
    november_spent_prior_usd: float = 0.0,
    input_cost_per_mtok: float = DEFAULT_INPUT_COST_PER_MTOK_USD,
    output_cost_per_mtok: float = DEFAULT_OUTPUT_COST_PER_MTOK_USD,
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    now: Optional[datetime] = None,
) -> tuple[list[str], float]:
    """Enforce Decide 61-A's $5/run cap, $30/November cap, and December authorization gate."""
    effective_now = now or datetime.now(timezone.utc)
    if effective_now.year > 2026 or (effective_now.year == 2026 and effective_now.month >= 12):
        raise ValueError(
            "Decide 61-A: a December model-spend cap requires Alex's word before running."
        )
    run_cap = min(float(max_run_cost_usd), HARD_RUN_COST_CAP_USD)
    remaining_nov = NOVEMBER_MONTHLY_CAP_USD - float(november_spent_prior_usd)
    if remaining_nov <= 0:
        raise ValueError(
            f"Decide 61-A: November model-spend cap (${NOVEMBER_MONTHLY_CAP_USD:.2f}) already reached."
        )
    effective_cap = min(run_cap, remaining_nov)

    kept: list[str] = []
    for p in prompts:
        cand = kept + [p]
        c = estimate_proposer_cost_usd(
            cand,
            input_cost_per_mtok=input_cost_per_mtok,
            output_cost_per_mtok=output_cost_per_mtok,
            max_output_tokens=max_output_tokens,
        )
        if c > effective_cap:
            if not kept:
                raise ValueError(
                    f"Decide 61-A: single prompt cost (${c:.4f}) exceeds remaining November cap (${effective_cap:.4f})."
                )
            break
        kept.append(p)

    final_cost = estimate_proposer_cost_usd(
        kept,
        input_cost_per_mtok=input_cost_per_mtok,
        output_cost_per_mtok=output_cost_per_mtok,
        max_output_tokens=max_output_tokens,
    )
    return kept, final_cost


def _call_openai_json(
    prompt: str,
    *,
    api_key: str,
    model: str = DEFAULT_PROPOSER_MODEL,
    timeout: float = 30.0,
) -> tuple[dict[str, Any], int, int]:
    """Call OpenAI Chat Completions in JSON mode and return ``(parsed_json, prompt_tokens, completion_tokens)``."""
    payload = {
        "model": model,
        "response_format": {"type": "json_object"},
        "temperature": 0.0,
        "max_tokens": DEFAULT_MAX_OUTPUT_TOKENS,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You verify candidate sibling_family prediction market groups. "
                    "Quote market descriptions or titles word for word (exact character substring) and "
                    "never invent words outside the markets' own titles for card_heading."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    usage = body.get("usage") or {}
    in_toks = int(usage.get("prompt_tokens") or 0)
    out_toks = int(usage.get("completion_tokens") or 0)
    content = (
        ((body.get("choices") or [{}])[0].get("message") or {}).get("content") or "{}"
    )
    return json.loads(content), in_toks, out_toks


def propose_sibling_families(
    markets: Mapping[int, Mapping[str, Any]] | Sequence[Mapping[str, Any]],
    *,
    max_families: int = 25,
    min_members: int = 3,
    use_llm: bool = False,
    model: str = DEFAULT_PROPOSER_MODEL,
    api_key: Optional[str] = None,
    model_caller: Optional[Callable[[str], tuple[dict[str, Any], int, int]]] = None,
    november_spent_prior_usd: float = 0.0,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """Nominate sibling families, run bounded verification under Decide 61-A, and judge every proposal with ``select_sibling_family``."""
    effective_now = (
        now.astimezone(timezone.utc)
        if isinstance(now, datetime) and now.tzinfo is not None
        else datetime.now(timezone.utc)
    )
    generated_at = effective_now.strftime("%Y-%m-%dT%H:%M:%SZ")

    nominated = nominate_sibling_families(markets, min_members=min_members)[:max_families]
    prompts = [build_family_verification_prompt(fam) for fam in nominated]

    if use_llm or model_caller is not None:
        kept_prompts, est_cost = enforce_proposer_cost_cap(
            prompts,
            max_run_cost_usd=HARD_RUN_COST_CAP_USD,
            november_spent_prior_usd=november_spent_prior_usd,
            now=effective_now,
        )
        nominated = nominated[: len(kept_prompts)]
    else:
        est_cost = 0.0

    banner = print_preflight_cost_banner(
        family_count=len(nominated),
        estimated_cost_usd=est_cost,
        november_spent_prior_usd=november_spent_prior_usd,
        now=effective_now,
    )

    total_in_toks = 0
    total_out_toks = 0
    effective_model = model if (use_llm or model_caller is not None) else "rules-only"
    families_out: list[dict[str, Any]] = []

    for idx, fam in enumerate(nominated):
        members = fam["members"]
        m_a = members[0]
        m_b = members[1]
        default_quote_a = _extract_default_rule_quote(m_a)
        default_quote_b = _extract_default_rule_quote(m_b)

        only_subject_differs = True
        only_subject_reason = (
            f"Members share template '{fam['template_key']}' and differ only in their extracted row subject."
        )
        quote_a = default_quote_a
        quote_b = default_quote_b
        already_happened_ids: list[int] = []
        already_happened_reason = ""
        model_heading: Optional[str] = None

        if use_llm or model_caller is not None:
            caller = model_caller or (
                lambda p: _call_openai_json(
                    p, api_key=str(api_key or os.getenv("OPENAI_API_KEY") or ""), model=model
                )
            )
            parsed, in_t, out_t = caller(prompts[idx])
            total_in_toks += in_t
            total_out_toks += out_t
            only_subject_differs = bool(parsed.get("only_subject_differs", True))
            only_subject_reason = str(
                parsed.get("only_subject_differs_reason") or only_subject_reason
            ).strip()
            cand_qa = str(parsed.get("market_a_quote") or "").strip()
            cand_qb = str(parsed.get("market_b_quote") or "").strip()
            # Keep model quote if supplied; if model omitted it, use verbatim rule quote; if model fabricated a non-substring quote, keep it so verification catches it.
            quote_a = cand_qa if cand_qa else default_quote_a
            quote_b = cand_qb if cand_qb else default_quote_b
            raw_ah = parsed.get("already_happened_market_ids") or []
            if isinstance(raw_ah, list):
                already_happened_ids = [
                    int(x) for x in raw_ah if isinstance(x, int) and not isinstance(x, bool)
                ]
            already_happened_reason = str(parsed.get("already_happened_reason") or "").strip()
            model_heading = str(parsed.get("card_heading") or "").strip() or None

        qa_verified = verify_word_for_word_quote(quote_a, m_a)
        qb_verified = verify_word_for_word_quote(quote_b, m_b)
        quotes_verified = qa_verified and qb_verified

        defn = build_proposed_sibling_definition(
            fam,
            generated_at=generated_at,
            model=effective_model,
            card_heading=model_heading,
        )
        rule = defn["rule"]
        verdict_obj = select_sibling_family(
            members,
            expected_source=rule["source"],
            template=rule["template"],
            title_template=rule["title_template"],
            kicker_prefix=rule["kicker_prefix"],
            kicker_include_date=rule["kicker_include_date"],
            subject_unit=rule["subject_unit"],
            outcome_name=rule["outcome_name"],
            lead_rule=rule["lead_rule"],
            min_numbered_members=rule["min_numbered_members"],
            card_rows=rule["card_rows"],
            footer=defn["footer"],
            now=effective_now,
        )

        if isinstance(verdict_obj, RoundupMembers):
            kind_verdict = "serve"
            refusal_reasons: list[str] = []
            card_words = export_roundup_card_words_390px(verdict_obj, defn)
        else:
            kind_verdict = "refuse"
            reasons_raw = (
                list(verdict_obj.reasons)
                if isinstance(verdict_obj, RoundupRefusal)
                else []
            )
            reason_dict = dict(
                r for r in reasons_raw if isinstance(r, tuple) and len(r) == 2
            )
            refusal_reasons = [str(reason_dict.get("family") or "refused")]
            card_words = None

        trust_pass = (
            kind_verdict == "serve"
            and only_subject_differs
            and quotes_verified
            and len(already_happened_ids) == 0
        )

        member_rows: list[dict[str, Any]] = []
        for m, subj in zip(members, fam["subjects"]):
            outs = m.get("outcomes") or m.get("top_outcomes") or ()
            yes_prob = None
            for o in outs:
                if isinstance(o, Mapping) and str(o.get("name") or o.get("label") or "").strip().lower() == "yes":
                    p = o.get("probability") if "probability" in o else o.get("current_probability")
                    if isinstance(p, (int, float)) and not isinstance(p, bool):
                        yes_prob = round(float(p), 4)
                    break
            member_rows.append(
                {
                    "id": int(m["id"]),
                    "name": str(m.get("name") or ""),
                    "subject": subj,
                    "resolution_date": m.get("resolution_date"),
                    "yes_probability": yes_prob,
                }
            )

        families_out.append(
            {
                "slug": defn["slug"],
                "name": defn["name"],
                "source": fam["source"],
                "category": fam["category"],
                "template_key": fam["template_key"],
                "group_id": fam["group_id"],
                "title_ilike": fam["title_ilike"],
                "member_count": len(member_rows),
                "members": member_rows,
                "quotes": {
                    "market_a_id": int(m_a["id"]),
                    "market_a_name": str(m_a.get("name") or ""),
                    "market_a_quote": quote_a,
                    "market_b_id": int(m_b["id"]),
                    "market_b_name": str(m_b.get("name") or ""),
                    "market_b_quote": quote_b,
                    "quotes_verified": quotes_verified,
                },
                "only_subject_differs": only_subject_differs,
                "only_subject_differs_reason": only_subject_reason,
                "already_happened_market_ids": already_happened_ids,
                "already_happened_reason": already_happened_reason,
                "kind_verdict": kind_verdict,
                "refusal_reasons": refusal_reasons,
                "trust_pass": trust_pass,
                "card_words_390px": card_words,
                "proposed_definition": defn,
            }
        )

    actual_cost = (
        round(
            (total_in_toks / 1_000_000.0) * DEFAULT_INPUT_COST_PER_MTOK_USD
            + (total_out_toks / 1_000_000.0) * DEFAULT_OUTPUT_COST_PER_MTOK_USD,
            4,
        )
        if (use_llm or model_caller is not None)
        else 0.0
    )
    print(
        f"[61-A] Sibling-family proposer completed: families={len(families_out)}, "
        f"serve={sum(1 for f in families_out if f['kind_verdict'] == 'serve')}, "
        f"refuse={sum(1 for f in families_out if f['kind_verdict'] == 'refuse')}, "
        f"actual_cost=${actual_cost:.4f} (estimated=${est_cost:.4f})",
        flush=True,
    )

    from app.utils.grouping_licences import run_licensed_promotion_pass

    eligible_proposals = [
        f["proposed_definition"]
        for f in families_out
        if f["kind_verdict"] == "serve" and f["trust_pass"]
    ]
    promotion_pass = run_licensed_promotion_pass(
        PRODUCER_KIND_SIBLING_FAMILY,
        eligible_proposals,
        proposed_at=effective_now.strftime("%Y-%m-%d"),
    )

    return {
        "generated_at": generated_at,
        "proposer": "sibling_family_proposer",
        "kind": PRODUCER_KIND_SIBLING_FAMILY,
        "licence_status": promotion_pass["licence_status"],
        "promotion_pass": {
            "stopped": promotion_pass["stopped"],
            "stopped_reason": promotion_pass["stopped_reason"],
            "promoted_count": len(promotion_pass["promoted_definitions"]),
            "refused_slugs": promotion_pass["refused_slugs"],
        },
        "model": effective_model,
        "run_cost_cap_usd": HARD_RUN_COST_CAP_USD,
        "november_cost_cap_usd": NOVEMBER_MONTHLY_CAP_USD,
        "estimated_cost_usd": est_cost,
        "actual_cost_usd": actual_cost,
        "preflight_cost_banner": banner,
        "families_count": len(families_out),
        "serve_count": sum(1 for f in families_out if f["kind_verdict"] == "serve"),
        "refuse_count": sum(1 for f in families_out if f["kind_verdict"] == "refuse"),
        "trust_pass_count": sum(1 for f in families_out if f["trust_pass"]),
        "families": families_out,
    }


def _md_cell(text: str) -> str:
    return " ".join(str(text or "").replace("|", "\\|").split())


def format_grouping_candidates_markdown(report: Mapping[str, Any]) -> str:
    """Format the ``docs/discover/grouping-candidates-2026-11.md`` audit table."""
    families = list(report.get("families") or [])
    lines = [
        "# Sibling-Family Grouping Candidates — November 2026",
        "",
        "**PILLAR:** DISCOVER / MATCHING / TRUTH · **SHIP:** candidate `sibling_family` definitions proposed from live markets by `sibling_family_proposer` (#12372, Epic #12288), using selector patterns (`title_ilike` / `group_id` + `template`, never an ID list) and evaluated by `sibling_family`'s own truth checks (`select_sibling_family`) under Decide 61-A.",
        "",
        f"- **Generated at:** `{report['generated_at']}`",
        f"- **Model:** `{report['model']}`",
        f"- **Pre-flight cost line (61-A):** `{report['preflight_cost_banner']}`",
        f"- **Estimated cost:** `${float(report['estimated_cost_usd']):.4f}` · **Actual cost:** `${float(report['actual_cost_usd']):.4f}` (run cap `${float(report['run_cost_cap_usd']):.2f}`, November cap `${float(report['november_cost_cap_usd']):.2f}`)",
        f"- **Families proposed:** **{report['families_count']}** (`serve`: **{report['serve_count']}**, `refuse`: **{report['refuse_count']}**, `TRUST pass`: **{report['trust_pass_count']}**)",
        "",
        "| # | Proposed Family (`slug` · Selector) | Members (Sample Subjects & Prices) | Verbatim Rule Quotes (Market A / Market B) | `sibling_family` Verdict & TRUST |",
        "|---|---|---|---|---|",
    ]
    for idx, fam in enumerate(families, start=1):
        selector_desc = (
            f"group_id=`{fam['group_id']}`, title_ilike=`{fam['title_ilike']}`"
            if fam.get("group_id")
            else f"title_ilike=`{fam['title_ilike']}`"
        )
        fam_cell = _md_cell(
            f"**{fam['name']}** (`{fam['slug']}`) · `{fam['source']}` · template `{fam['template_key']}` · {selector_desc}"
        )
        sample_members = []
        for m in fam["members"][:5]:
            p_str = (
                f"{int(math.floor(float(m['yes_probability']) * 100.0 + 0.5))}%"
                if isinstance(m.get("yes_probability"), (int, float))
                else "unpriced"
            )
            sample_members.append(f"`{m['id']}` {m['subject']} ({p_str})")
        if len(fam["members"]) > 5:
            sample_members.append(f"+{len(fam['members']) - 5} more ({len(fam['members'])} total)")
        members_cell = _md_cell("; ".join(sample_members))

        q = fam["quotes"]
        quotes_cell = _md_cell(
            f"**`{q['market_a_id']}`:** \"{q['market_a_quote'][:140]}\" · "
            f"**`{q['market_b_id']}`:** \"{q['market_b_quote'][:140]}\" "
            f"(verified=`{q['quotes_verified']}`)"
        )

        verdict_str = (
            "**SERVE**"
            if fam["kind_verdict"] == "serve"
            else f"**REFUSE** (`{', '.join(fam['refusal_reasons'])}`)"
        )
        trust_str = "PASS" if fam["trust_pass"] else "FAIL"
        verdict_cell = _md_cell(f"{verdict_str} · TRUST: **{trust_str}**")
        lines.append(f"| {idx} | {fam_cell} | {members_cell} | {quotes_cell} | {verdict_cell} |")

    lines.append("")
    return "\n".join(lines)


def write_grouping_candidate_reports(
    report: Mapping[str, Any],
    *,
    json_out: Path = DEFAULT_JSON_OUT,
    backend_json_out: Path | None = DEFAULT_BACKEND_DATA_JSON_OUT,
    md_out: Path = DEFAULT_MD_OUT,
) -> None:
    """Write ``docs/discover/`` and ``backend/data/discover/`` candidate files together so they never drift."""
    encoded = json.dumps(dict(report), indent=2) + "\n"
    md_text = format_grouping_candidates_markdown(report)
    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(encoded, encoding="utf-8")
    if backend_json_out is not None:
        backend_json_out.parent.mkdir(parents=True, exist_ok=True)
        backend_json_out.write_text(encoded, encoding="utf-8")
    md_out.parent.mkdir(parents=True, exist_ok=True)
    md_out.write_text(md_text, encoding="utf-8")

