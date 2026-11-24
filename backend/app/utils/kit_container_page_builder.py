"""Generic deterministic Kit container-page composer (Decision 386: A, #12221).

Composes uncovered prediction-market families into multi-section preview pages
using only the shared Kit v1 layouts (`stack | grid | calendar | axis`) and
structural market patterns — with zero hardcoded slugs, topic names, or market IDs.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import re
from typing import Any, Iterable, Mapping, Sequence

from app.utils.kit_v1_spec import (
    ALLOWED_KIT_IMAGE_HOSTS,
    _is_valid_image_url,
    _make_kit_card,
    _mark_bar_single,
    _mark_number,
    _mark_picture,
    _mark_tile,
    _mark_word,
    _verified_art_by_key,
    compute_one_in_n,
    validate_kit_v1_card,
)

try:
    from app.utils.kit_v1_spec import _team_logo
except ImportError:  # pragma: no cover - defensive fallback
    def _team_logo(name: str, *, kind: str = "team") -> tuple[str, str]:
        return ("", "")

_MONTH_NUM: dict[str, int] = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
_MONTH_ABBR = [
    "", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]

_BEFORE_DATE_RE = re.compile(
    r"\b(Before\s+|by\s+|in\s+)?"
    r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\b"
    r"(?:\s+(\d{1,2}),?)?"
    r"(?:\s+(?:(\d{4})|'(\d{2})))?",
    re.IGNORECASE,
)

_HAS_CONJUNCTION_RE = re.compile(r"(?:\s+and\s+|\s*&\s*)", re.IGNORECASE)
_STAT_NOISE_RE = re.compile(
    r"(%|\bis at\b|\bleads\b|\bheadlines\b|\bfell\b|\brose\b|\blikeliest\b|\bpoints?\b)",
    re.IGNORECASE,
)
_HEADLINE_STRIP_SUFFIX_RE = re.compile(
    r"\s+(?:by|before|in|on|during)\s+(?:\d{4}|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec).*$",
    re.IGNORECASE,
)
_GENERIC_STOPWORDS = frozenset({
    "will", "the", "a", "an", "be", "in", "on", "of", "to", "for", "by", "or",
    "before", "after", "at", "from", "with", "this", "that", "who", "what", "which",
    "when", "where", "how", "more", "than", "any", "next", "end", "market", "open",
    "another", "during", "through", "least", "most", "its", "his", "her", "their",
    "our", "my", "say", "make", "close", "score", "scores", "hits", "hit",
    "added", "been", "being", "announce", "announces", "announced",
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december", "jan", "feb", "mar", "apr",
    "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
})
_DANGLING_HEADLINE_ENDINGS = frozenset({
    "its", "his", "her", "their", "our", "my", "the", "a", "an", "of", "in", "on",
    "to", "for", "by", "at", "with", "from", "say", "make", "close", "be", "has",
    "have", "will", "least", "all", "is", "are", "was", "were", "above", "below",
})
_DANGLING_ROW_STARTERS = frozenset({
    "or", "and", "least", "most", "to", "of", "in", "for", "with", "be", "by", "been",
})
_SECTION_FALLBACK_TITLES: dict[str, str] = {
    "scoreboard_grid": "Outcome Matrix",
    "dated_tiles": "Key Timelines",
    "shared_scale": "Shared Odds Scale",
    "countdown": "Near-Term Catalysts",
    "one_in_n": "Long-Shot Odds",
    "casting_sheet": "Top Contenders",
    "plain_bar_stack": "Open Odds",
}


def _slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s[:64] or "container-preview"


def _round_pct(prob: Any) -> int:
    if prob is None:
        return 0
    val = float(prob)
    if 0.0 <= val <= 1.0:
        val *= 100.0
    val = max(0.0, min(100.0, val))
    return int(Decimal(str(val)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _parse_iso_dt(val: Any) -> datetime | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val if val.tzinfo is not None else val.replace(tzinfo=timezone.utc)
    raw = str(val).strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def is_settled_market(market: Mapping[str, Any], now: datetime) -> bool:
    """Return True if a market is settled, closed past settlement, or resolved."""
    status = str(market.get("status") or "open").strip().lower()
    if status != "open":
        return True
    if market.get("settled_at") is not None:
        return True
    if bool(market.get("is_settled")) or bool(market.get("resolved_outcome")):
        return True
    res_dt = _parse_iso_dt(market.get("resolution_date") or market.get("close_time"))
    if res_dt is not None and (now - res_dt).total_seconds() > 3600:
        top_pct = _top_probability(market)
        if top_pct >= 99.5 or top_pct <= 0.5:
            return True
    if _is_binary_market(market):
        parsed = _parse_date_marker(str(market.get("name") or market.get("title") or ""), default_year=now.year)
        if parsed is not None and (now - parsed["sort_dt"]).total_seconds() > 86400:
            top_pct = _top_probability(market)
            if top_pct >= 99.5 or top_pct <= 0.5:
                return True
    return False


def _sorted_outcomes(market: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = market.get("outcomes") or []
    out: list[dict[str, Any]] = []
    for o in raw:
        if not isinstance(o, Mapping):
            continue
        p_raw = o.get("current_probability")
        if p_raw is None:
            p_raw = o.get("probability")
        if p_raw is None:
            continue
        prob = float(p_raw)
        if prob > 1.0:
            prob /= 100.0
        out.append({"name": str(o.get("name") or "").strip(), "prob": prob})
    out.sort(key=lambda r: (-r["prob"], r["name"]))
    return out


def _is_binary_market(market: Mapping[str, Any]) -> bool:
    outcomes = _sorted_outcomes(market)
    if not outcomes:
        return True
    names = {o["name"].lower() for o in outcomes}
    if len(outcomes) <= 2 and names <= {"yes", "no"}:
        return True
    return len(outcomes) == 1


def _top_probability(market: Mapping[str, Any]) -> float:
    outcomes = _sorted_outcomes(market)
    if outcomes:
        yes = next((o for o in outcomes if o["name"].lower() == "yes"), None)
        if yes is not None:
            return float(yes["prob"]) * 100.0
        if len(outcomes) == 1 and outcomes[0]["name"].lower() == "no":
            return max(0.0, (1.0 - float(outcomes[0]["prob"])) * 100.0)
        return float(outcomes[0]["prob"]) * 100.0
    p = market.get("current_probability") or market.get("probability") or 0.0
    val = float(p)
    return val * 100.0 if val <= 1.0 else val


def _sources_count(market: Mapping[str, Any]) -> int:
    raw = market.get("sources_count")
    if isinstance(raw, int) and raw > 0:
        return raw
    srcs = market.get("sources")
    if isinstance(srcs, (list, tuple, set)) and srcs:
        return len(srcs)
    return 1


def _normalize_question_key(name: str) -> str:
    txt = (name or "").lower().strip()
    txt = txt.replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')
    txt = re.sub(r"^(?:will|does|do)\s+", "", txt)
    txt = re.sub(r"\bbe\b", " ", txt)
    txt = re.sub(r"[?!.,'\":()]+", "", txt)
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt


def _dedupe_twins(markets: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Collapse cross-venue twin questions while preserving combined source count."""
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for m in markets:
        item = dict(m)
        gid = str(item.get("group_id") or "").strip()
        qkey = _normalize_question_key(str(item.get("name") or item.get("title") or ""))
        dedupe_key = f"gid:{gid}:{qkey}" if gid else f"q:{qkey}"
        groups[dedupe_key].append(item)

    deduped: list[dict[str, Any]] = []
    for bucket in groups.values():
        bucket.sort(key=lambda x: (-_sources_count(x), -int(x.get("volume_24h") or 0), int(x.get("id") or 0)))
        lead = dict(bucket[0])
        sources = {str(x.get("source") or "kalshi").lower() for x in bucket}
        lead["sources_count"] = max(_sources_count(lead), len(sources))
        deduped.append(lead)
    return deduped


def derive_common_headline(
    family_label: str | None,
    titles: Sequence[str],
) -> tuple[str | None, str | None]:
    """Derive a 2-4 word declarative common headline without stat noise or conjunctions."""
    candidates: list[str] = []
    single_entity_label: str | None = None
    if family_label:
        clean_fl = re.sub(r"[?!.:]+$", "", str(family_label)).strip()
        fl_words = clean_fl.split()
        if len(fl_words) == 1 and len(fl_words[0]) >= 3 and not _STAT_NOISE_RE.search(clean_fl):
            w0 = fl_words[0]
            single_entity_label = w0 if any(c.isupper() for c in w0) else w0.capitalize()
        candidates.append(str(family_label))
    candidates.extend(str(t) for t in titles if t)

    for idx_c, raw in enumerate(candidates):
        is_fam = family_label is not None and idx_c == 0
        if idx_c == 1 and single_entity_label and not _HAS_CONJUNCTION_RE.search(single_entity_label):
            return f"{single_entity_label} Outlook", None
        txt = raw.replace("{}", " ").strip()
        txt = re.sub(r"[?!.:]+$", "", txt).strip()
        txt = re.sub(r"^(?:Will|Who\s+will|What\s+will|Which|When\s+will|Does|Is|Are)\s+", "", txt, flags=re.IGNORECASE)
        txt = _HEADLINE_STRIP_SUFFIX_RE.sub("", txt).strip()
        txt = re.sub(r"\s+", " ", txt).strip(" -–—,:;")
        if not txt or _STAT_NOISE_RE.search(txt) or _HAS_CONJUNCTION_RE.search(txt):
            continue
        words = [w for w in txt.split() if w]
        if 2 <= len(words) <= 4:
            last_low = words[-1].lower().strip("?!.,")
            if last_low in _DANGLING_HEADLINE_ENDINGS and not is_fam:
                continue
            formatted = " ".join(w if any(c.isupper() for c in w) else w.capitalize() for w in words)
            return formatted, None

    if single_entity_label and not _HAS_CONJUNCTION_RE.search(single_entity_label):
        return f"{single_entity_label} Outlook", None

    # Fallback: extract top 2-3 shared non-stopword content tokens across titles
    token_counts: dict[str, int] = defaultdict(int)
    first_order: dict[str, int] = {}
    orig_case: dict[str, str] = {}
    for t in titles:
        seen_in_t: set[str] = set()
        for tok in re.findall(r"[A-Za-z0-9'\u2019]+", t):
            base = re.sub(r"[\'\u2019]s$", "", tok.lower())
            if not base or base in _GENERIC_STOPWORDS or base in _DANGLING_HEADLINE_ENDINGS or len(base) <= 2 or base.isdigit():
                continue
            if base not in first_order:
                first_order[base] = len(first_order)
            clean_tok = re.sub(r"[\'\u2019]s$", "", tok)
            if (any(c.isupper() for c in clean_tok) and not clean_tok.isupper()) or (clean_tok.isupper() and len(clean_tok) <= 4):
                orig_case.setdefault(base, clean_tok)
            if base not in seen_in_t:
                token_counts[base] += 1
                seen_in_t.add(base)
    threshold = max(2, len(titles) // 2) if len(titles) >= 2 else 1
    shared = [t for t, cnt in token_counts.items() if cnt >= threshold]
    shared.sort(key=lambda t: (-token_counts[t], first_order.get(t, 999)))
    chosen = shared[:3]
    if len(chosen) >= 2:
        headline = " ".join(orig_case.get(w, w.capitalize()) for w in chosen)
        if not _HAS_CONJUNCTION_RE.search(headline) and not _STAT_NOISE_RE.search(headline):
            return headline, None
    return None, "refused_headline_not_2_to_4_common_thing"


def resolve_kicker(markets: Sequence[Mapping[str, Any]], default: str = "MARKETS") -> str:
    """Resolve the display category kicker from market categories (never sports noise first)."""
    counts: dict[str, int] = defaultdict(int)
    for m in markets:
        cat = str(m.get("llm_sport_category") or m.get("category") or "").strip().lower()
        if cat and cat not in {"championship", "prop", "unknown", "futures", "other"}:
            counts[cat] += 1
    if not counts:
        return default
    top_cat = max(counts.items(), key=lambda kv: (kv[1], kv[0]))[0]
    return top_cat.upper()


def _parse_date_marker(title: str, default_year: int) -> dict[str, Any] | None:
    """Extract embedded target date, keeping 'Before X' phrasing intact verbatim."""
    for m in _BEFORE_DATE_RE.finditer(title or ""):
        prefix_raw = (m.group(1) or "").strip()
        mon_tok = m.group(2)
        day_tok = m.group(3)
        yr4 = m.group(4)
        yr2 = m.group(5)
        if not (day_tok or yr4 or yr2):
            continue
        mon_num = _MONTH_NUM.get(mon_tok.lower())
        if not mon_num:
            continue
        year = int(yr4) if yr4 else (2000 + int(yr2) if yr2 else default_year)
        day = int(day_tok) if day_tok else 28
        try:
            sort_dt = datetime(year, mon_num, min(28, day), tzinfo=timezone.utc)
        except ValueError:
            continue

        mon_str = _MONTH_ABBR[mon_num]
        yr_short = f"'{year % 100:02d}"
        is_before = prefix_raw.lower().startswith("before")
        prefix = "Before " if is_before else ("by " if prefix_raw.lower().startswith("by") else "")
        if day_tok:
            period = f"{prefix}{mon_str} {int(day_tok)} {yr_short}".strip()
            phrase = f"{'before' if is_before else 'by'} {mon_str} {int(day_tok)}, {year}".strip()
        else:
            period = f"{prefix}{mon_str} {yr_short}".strip()
            phrase = f"{'before' if is_before else 'in'} {mon_str} {year}".strip()

        stem = (title[: m.start()] + title[m.end() :]).strip()
        stem = re.sub(r"[?!.,'\s]+$", "", stem).strip()
        stem = re.sub(r"^(?:Will\s+)", "", stem, flags=re.IGNORECASE).strip()
        stem = re.sub(r"\s+(?:on|at|in|by|before)$", "", stem, flags=re.IGNORECASE).strip()
        norm_stem = re.sub(r"[^a-z0-9]+", " ", stem.lower()).strip()
        return {
            "period": period,
            "phrase": phrase,
            "sort_dt": sort_dt,
            "stem": stem or title,
            "norm_stem": norm_stem,
        }
    return None


def _short_label(text: str, limit: int = 58) -> str:
    txt = re.sub(r"[?!\s]+$", "", (text or "").strip())
    if len(txt) <= limit:
        return txt
    return txt[: limit - 1].rstrip() + "…"


def _distinguishing_row_label(title: str, all_titles: Sequence[str], *, max_len: int = 44) -> str:
    """Extract the minimal distinguishing phrase across sibling market titles."""
    cleaned = re.sub(r"[?!.]+$", "", (title or "").strip())
    cleaned = re.sub(r"^(?:Will|Does|Do|Is|Are)\s+", "", cleaned, flags=re.IGNORECASE).strip()
    if len(all_titles) < 2:
        return _short_label(cleaned, max_len)
    split_lists = [
        re.sub(r"^(?:Will|Does|Do|Is|Are)\s+", "", re.sub(r"[?!.]+$", "", t).strip(), flags=re.IGNORECASE).split()
        for t in all_titles
    ]
    prefix_len = 0
    for words in zip(*split_lists):
        if len({w.lower() for w in words}) == 1:
            prefix_len += 1
        else:
            break
    suffix_len = 0
    for words in zip(*(reversed(s) for s in split_lists)):
        if len({w.lower() for w in words}) == 1:
            suffix_len += 1
        else:
            break
    tokens = cleaned.split()
    end_idx = len(tokens) - suffix_len if suffix_len > 0 else len(tokens)
    if prefix_len >= end_idx:
        prefix_len = max(0, end_idx - 2)
    diff_tokens = tokens[prefix_len:end_idx]
    # First keep 1-2 leading context tokens if stripping collapsed to a bare number
    while len(diff_tokens) == 1 and re.fullmatch(r"\$?[0-9.,]+[%KMBQT+]*", diff_tokens[0], re.IGNORECASE) and prefix_len > 0:
        prefix_len -= 1
        diff_tokens = tokens[prefix_len:end_idx]
    # Then step back cleanly if the label begins mid-connector ("Or ...", "Least 36.0" -> "At least 36.0")
    while diff_tokens and diff_tokens[0].lower().strip("?!.,") in _DANGLING_ROW_STARTERS and prefix_len > 0:
        lead_low = diff_tokens[0].lower().strip("?!.,")
        prev_low = tokens[prefix_len - 1].lower().strip("?!.,")
        prefix_len -= 1
        diff_tokens = tokens[prefix_len:end_idx]
        if lead_low in {"least", "most"} and prev_low == "at":
            break
    diff = " ".join(diff_tokens).strip(" -–—:,")
    if not diff:
        diff = cleaned
    if diff and diff[0].islower():
        diff = diff[0].upper() + diff[1:]
    return _short_label(diff, max_len)


def _dedupe_by_rendered_label(
    ordered_markets: Sequence[Mapping[str, Any]],
    *,
    limit: int,
    max_len: int = 44,
) -> tuple[list[tuple[Mapping[str, Any], str]], list[Mapping[str, Any]]]:
    """Select up to ``limit`` rows with unique rendered labels while returning all checked twins."""
    all_titles = [str(m.get("name") or "") for m in ordered_markets[:limit]]
    selected: list[tuple[Mapping[str, Any], str]] = []
    consumed: list[Mapping[str, Any]] = []
    seen_labels: set[str] = set()
    for m in ordered_markets:
        raw_title = str(m.get("name") or "")
        label = _distinguishing_row_label(raw_title, all_titles, max_len=max_len)
        lkey = label.lower().strip()
        consumed.append(m)
        if lkey in seen_labels:
            continue
        seen_labels.add(lkey)
        selected.append((m, label))
        if len(selected) >= limit:
            break
    return selected, consumed


def _template_signature(market: Mapping[str, Any]) -> str:
    """Return a generic structural template key so one ladder never splits into 3 sections."""
    raw = str(market.get("name") or market.get("title") or "").strip()
    low = raw.lower()

    # Multi-outcome vs binary threshold-twin equivalence for shared metric types
    for marker, tag in (
        ("rotten tomatoes", "rt"),
        ("tomatometer", "rt"),
        ("metacritic", "mc"),
        ("valuation", "val"),
    ):
        if marker in low:
            subj = low
            subj = re.sub(r"^(?:will|what|which)\s+", "", subj)
            subj = re.split(r"(?:\s+·\s+|\brotten\s+tomatoes\b|\btomatometer\b|\bmetacritic\b|\bvaluation\b|\bscore\b)", subj)[0]
            subj = re.sub(r"\b(?:hit|hits|close|open|at\s+least)\b", " ", subj)
            subj = re.sub(r"[?!.,'\u2019\"\u201c\u201d:()]+", " ", subj)
            subj_tokens = [t for t in subj.split() if t not in {"s", "the", "a", "an", "on", "of", "by", "in"}]
            if subj_tokens:
                return f"metric_{tag}:{'_'.join(subj_tokens[:5])}"

    sig = raw
    sig = _BEFORE_DATE_RE.sub(" {d} ", sig)
    sig = re.sub(r"\bby\.\.\.\??", " {d} ", sig, flags=re.IGNORECASE)
    sig = re.sub(r"\((?:high|low)\)", " ", sig, flags=re.IGNORECASE)
    sig = re.sub(r'["\u201c\'][^"\u201d\']+["\u201d\']', " {q} ", sig)
    sig = re.sub(r"\$?\d+(?:,\d+)*(?:\.\d+)?[kmbqtKMBQT]?\+?%?", " {n} ", sig)
    # Generic location slot after "in <Place>" before date marker or end
    sig = re.sub(
        r"\bin\s+[A-Z][a-zA-Z.'-]+(?:\s+[A-Z][a-zA-Z.'-]+){0,2}(?=\s+(?:\{d\}|before|by|\?|$))",
        " in {place}",
        sig,
    )
    tokens = re.findall(r"[a-z0-9]+", sig.lower())
    return f"tpl:{'_'.join(tokens[:16])}"


def _consume_templates(
    picked_markets: Sequence[Mapping[str, Any]],
    all_markets: Sequence[Mapping[str, Any]],
    used_ids: set[int],
) -> None:
    """Mark picked markets AND all sibling markets sharing their template signature as consumed."""
    sigs = {_template_signature(m) for m in picked_markets}
    for m in picked_markets:
        if m.get("id") is not None:
            used_ids.add(int(m["id"]))
    for m in all_markets:
        if m.get("id") is not None and _template_signature(m) in sigs:
            used_ids.add(int(m["id"]))


def _is_threshold_or_date_outcome_set(outs: Sequence[Mapping[str, Any]], default_year: int) -> bool:
    """Reject threshold brackets and pure date rungs from scoreboard contender matrices."""
    if not outs:
        return True
    thresh_cnt = 0
    date_cnt = 0
    for o in outs:
        nm = str(o.get("name") or "").strip()
        low = nm.lower()
        if (
            re.match(r"^(?:above|below|over|under|[↑↓]|[<>]=?|\$?\d)", low)
            or re.search(r"\$\d", low)
        ):
            thresh_cnt += 1
        parsed_dt = _parse_date_marker(nm, default_year=default_year)
        if parsed_dt is not None and len(nm.split()) <= 5 and len(parsed_dt["norm_stem"]) <= 3:
            date_cnt += 1
    return thresh_cnt >= 2 or date_cnt >= 2


def _lookup_subject_art(name: str, art_map: Mapping[str, Mapping[str, Any]]) -> dict[str, Any] | None:
    low = (name or "").strip().lower()
    if low in art_map:
        entry = art_map[low]
        url = str(entry.get("url") or entry.get("image_url") or "")
        if _is_valid_image_url(url):
            return _mark_picture(
                url=url,
                alt=name,
                subject_kind=str(entry.get("subject_kind") or "person"),
                size="sm",
                contain=True,
            )
    try:
        logo_url, kind = _team_logo(name)
    except (ValueError, KeyError, LookupError):
        return None
    if logo_url and _is_valid_image_url(logo_url):
        return _mark_picture(
            url=logo_url,
            alt=name,
            subject_kind=kind or "team",
            size="sm",
            contain=True,
        )
    return None


def _finalize_section(card: dict[str, Any]) -> dict[str, Any] | None:
    ok, _ = validate_kit_v1_card(card)
    if not ok:
        return None
    ok_unk, _ = validate_kit_v1_card({**card, "variant": "future_unknown_variant"})
    if not ok_unk:
        return None
    return card


def _build_scoreboard_grid_section(
    slug: str,
    kicker: str,
    markets: Sequence[Mapping[str, Any]],
    used_ids: set[int],
    *,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """Grid section for >= 2 sibling multi-outcome markets sharing contender columns (Direction 228)."""
    ref_year = now.year if now is not None else datetime.now(timezone.utc).year
    candidates: list[tuple[Mapping[str, Any], list[dict[str, Any]], tuple[str, ...]]] = []
    for m in markets:
        mid = int(m["id"])
        if mid in used_ids or _is_binary_market(m):
            continue
        outs = [o for o in _sorted_outcomes(m) if o["name"].lower() not in {"yes", "no", "other"}]
        if not (2 <= len(outs) <= 8):
            continue
        if _is_threshold_or_date_outcome_set(outs, ref_year):
            continue
        col_sig = tuple(sorted(o["name"].lower() for o in outs if o["name"]))
        if len(col_sig) < 2:
            continue
        total_pct = sum(o["prob"] for o in outs)
        if total_pct > 1.35 or total_pct < 0.45:
            continue
        candidates.append((m, outs, col_sig))

    if len(candidates) < 2:
        return None

    by_sig: dict[tuple[str, ...], list[tuple[Mapping[str, Any], list[dict[str, Any]]]]] = defaultdict(list)
    for m, outs, sig in candidates:
        by_sig[sig].append((m, outs))

    best_group = max(by_sig.values(), key=lambda g: len(g), default=[])
    col_names_raw: list[str] = []
    chosen_group: list[tuple[Mapping[str, Any], list[dict[str, Any]]]] = []

    if len(best_group) >= 2:
        chosen_group = best_group[:4]
        col_names_raw = [o["name"] for o in chosen_group[0][1]][:4]
    else:
        # Fallback: find top 2-4 shared contender names appearing across >= 2 distinct sibling markets
        freq: dict[str, int] = defaultdict(int)
        max_prob: dict[str, float] = defaultdict(float)
        display_for_low: dict[str, str] = {}
        for _, outs, _ in candidates:
            seen_low: set[str] = set()
            for o in outs:
                low = o["name"].lower().strip()
                if not low or low in seen_low:
                    continue
                seen_low.add(low)
                freq[low] += 1
                max_prob[low] = max(max_prob[low], float(o["prob"]))
                display_for_low.setdefault(low, o["name"])
        shared_cols = [
            low for low, cnt in freq.items() if cnt >= 2
        ]
        shared_cols.sort(key=lambda low: (-freq[low], -max_prob[low], low))
        top_cols_low = shared_cols[:4]
        if len(top_cols_low) >= 2:
            top_col_set = set(top_cols_low)
            matching = [
                (m, outs, len({o["name"].lower().strip() for o in outs} & top_col_set))
                for m, outs, _ in candidates
            ]
            matching = [item for item in matching if item[2] >= 2]
            if len(matching) >= 2:
                matching.sort(key=lambda item: (-item[2], int(item[0]["id"])))
                chosen_group = [(m, outs) for m, outs, _ in matching[:4]]
                col_names_raw = [display_for_low[low] for low in top_cols_low]

    if len(chosen_group) < 2 or len(col_names_raw) < 2:
        return None

    columns = [{"key": f"col_{i}_{_slugify(c)[:16]}", "label": _short_label(c, 16)} for i, c in enumerate(col_names_raw)]
    all_titles = [str(m.get("name") or "") for m, _ in chosen_group]
    rows: list[dict[str, Any]] = []
    lead_caption = None
    best_pct = -1

    for m, outs in chosen_group:
        by_name = {o["name"].lower().strip(): o["prob"] for o in outs}
        row_label = _distinguishing_row_label(str(m.get("name") or ""), all_titles, max_len=36)
        cells: list[dict[str, Any]] = []
        row_probs = [by_name.get(cname.lower().strip(), 0.0) for cname in col_names_raw]
        row_max = max(row_probs) if row_probs else 0.0
        for col, cname in zip(columns, col_names_raw):
            clow = cname.lower().strip()
            if clow in by_name:
                prob = by_name[clow]
                pct = _round_pct(prob)
                is_best_in_row = prob > 0 and prob >= row_max - 1e-6 and pct >= 20
                cells.append({
                    "column_key": col["key"],
                    "marks": [_mark_tile(
                        shade=max(0.02, min(1.0, prob)),
                        center_label=f"{pct}%",
                        muted=not is_best_in_row,
                        highlight_role="leader" if is_best_in_row else None,
                    )],
                })
                if pct > best_pct:
                    best_pct = pct
                    lead_caption = f"{cname} leads {row_label} at {pct}%"
            else:
                cells.append({
                    "column_key": col["key"],
                    "marks": [_mark_tile(
                        shade=0.02,
                        center_label="—",
                        muted=True,
                        highlight_role=None,
                    )],
                })
        rows.append({
            "id": f"{slug}-sb-{m['id']}",
            "leading": [_mark_word(row_label, style="row", tone="primary", align="left", width="flex", bold=True)],
            "cells": cells,
        })

    headline, err = derive_common_headline(None, all_titles)
    if err or not headline:
        headline = "Outcome Matrix"
    src_count = max(_sources_count(m) for m, _ in chosen_group)
    card = _finalize_section(_make_kit_card(
        card_id=f"{slug}-scoreboard",
        layout="grid",
        variant="scoreboard_grid",
        kicker=f"{kicker} · MATRIX",
        common_headline=headline,
        stat_caption=lead_caption or f"Compared across {len(rows)} markets",
        source_count=src_count,
        route_slug=slug,
        body={
            "leading_label": "Market",
            "show_column_headers": True,
            "row_layout": "matrix",
            "columns": columns,
            "rows": rows,
        },
    ))
    if card is None:
        return None
    _consume_templates([m for m, _ in chosen_group], markets, used_ids)
    return card


def _build_dated_tiles_section(
    slug: str,
    kicker: str,
    markets: Sequence[Mapping[str, Any]],
    used_ids: set[int],
    *,
    now: datetime,
) -> dict[str, Any] | None:
    """Grid section for binary or multi-outcome open-future date ladders (Condition 5 strict)."""
    today_d = now.date()
    by_stem: dict[str, list[tuple[Mapping[str, Any], dict[str, Any]]]] = defaultdict(list)
    for m in markets:
        mid = int(m["id"])
        if mid in used_ids or not _is_binary_market(m):
            continue
        parsed = _parse_date_marker(str(m.get("name") or ""), default_year=now.year)
        if not parsed or len(parsed["norm_stem"]) < 4:
            continue
        if parsed["sort_dt"].date() < today_d:
            continue
        by_stem[parsed["norm_stem"]].append((m, parsed))

    binary_ladders = [grp for grp in by_stem.values() if len({p["period"] for _, p in grp}) >= 2]
    binary_ladders.sort(key=lambda g: (-len(g), min(p["sort_dt"] for _, p in g)))

    # Multi-outcome date-rung markets ("Event by...?" with strictly open future date outcomes)
    multi_date_entries: list[tuple[Mapping[str, Any], list[tuple[dict[str, Any], int]]]] = []
    for m in markets:
        mid = int(m["id"])
        if mid in used_ids or _is_binary_market(m):
            continue
        res_dt = _parse_iso_dt(m.get("resolution_date") or m.get("close_time"))
        parsed_rungs: dict[str, tuple[dict[str, Any], int]] = {}
        for o in _sorted_outcomes(m):
            p = _parse_date_marker(o["name"], default_year=now.year)
            if p is None:
                continue
            # If month-day wrapped into next year per resolution_date, resolve cleanly
            if p["sort_dt"].date() < today_d and res_dt is not None and res_dt.year > now.year:
                cand_dt = datetime(res_dt.year, p["sort_dt"].month, p["sort_dt"].day, tzinfo=timezone.utc)
                if cand_dt <= res_dt + timedelta(days=35) and cand_dt.date() >= today_d:
                    mon_str = _MONTH_ABBR[cand_dt.month]
                    yr_short = f"'{cand_dt.year % 100:02d}"
                    p = {
                        **p,
                        "sort_dt": cand_dt,
                        "period": f"{mon_str} {cand_dt.day} {yr_short}",
                        "phrase": f"by {mon_str} {cand_dt.day}, {cand_dt.year}",
                    }
            if p["sort_dt"].date() < today_d:
                continue
            parsed_rungs[p["period"]] = (p, _round_pct(o["prob"]))
        if len(parsed_rungs) >= 2:
            ordered_rungs = sorted(parsed_rungs.values(), key=lambda x: x[0]["sort_dt"])
            multi_date_entries.append((m, ordered_rungs))
    multi_date_entries.sort(key=lambda x: (-len(x[1]), int(x[0]["id"])))

    if not binary_ladders and not multi_date_entries:
        return None

    rows: list[dict[str, Any]] = []
    picked_markets: list[Mapping[str, Any]] = []
    max_cols = 0
    lead_caption = None
    best_lead_pct = -1
    all_titles: list[str] = []
    seen_norm_stems: set[str] = set()

    def _norm_stem_key(txt: str) -> str:
        s = re.sub(r"\bbe\b", " ", (txt or "").lower())
        return re.sub(r"[^a-z0-9]+", " ", s).strip()

    for ladder in binary_ladders[:3]:
        by_period: dict[str, tuple[Mapping[str, Any], dict[str, Any]]] = {}
        for m, p in ladder:
            key = p["period"]
            if key not in by_period:
                by_period[key] = (m, p)
        ordered = sorted(by_period.values(), key=lambda mp: mp[1]["sort_dt"])
        if len(ordered) > 3:
            ordered = [ordered[0], ordered[len(ordered) // 2], ordered[-1]]
        stem_title = _short_label(ordered[0][1]["stem"], 54)
        stem_key = _norm_stem_key(stem_title)
        for m, _ in ladder:
            picked_markets.append(m)
        if stem_key in seen_norm_stems:
            continue
        seen_norm_stems.add(stem_key)
        max_cols = max(max_cols, len(ordered))
        all_titles.append(stem_title)
        cells: list[dict[str, Any]] = []
        probs = [_round_pct(_top_probability(m)) for m, _ in ordered]
        peak_pct = max(probs) if probs else 0

        for idx_c, ((m, p), pct) in enumerate(zip(ordered, probs)):
            is_accent = pct > 0 and pct >= max(10, peak_pct - 10)
            cells.append({
                "column_key": f"d_{idx_c}",
                "marks": [_mark_tile(
                    shade=max(0.02, pct / 100.0),
                    top_label=p["period"],
                    center_label=f"{pct}%",
                    muted=not is_accent,
                    highlight_role="peak" if pct == peak_pct and peak_pct > 0 else None,
                )],
            })
            if pct > best_lead_pct or (pct == best_lead_pct and idx_c == len(ordered) - 1):
                best_lead_pct = pct
                lead_caption = f"{stem_title} sits at {pct}% {p['phrase']}"

        rows.append({
            "id": f"{slug}-dt-{ordered[0][0]['id']}",
            "leading": [_mark_word(stem_title, style="row", tone="primary", align="left", width="flex", bold=True)],
            "cells": cells,
        })

    rem_slots = max(0, 3 - len(rows))
    for m, rungs in multi_date_entries:
        stem_title = _short_label(re.sub(r"\s+by\.\.\.\??$", "", str(m.get("name") or "")), 54)
        stem_key = _norm_stem_key(stem_title)
        picked_markets.append(m)
        if stem_key in seen_norm_stems:
            continue
        if rem_slots <= 0:
            break
        seen_norm_stems.add(stem_key)
        rem_slots -= 1
        ordered_r = rungs
        if len(ordered_r) > 3:
            ordered_r = [ordered_r[0], ordered_r[len(ordered_r) // 2], ordered_r[-1]]
        max_cols = max(max_cols, len(ordered_r))
        all_titles.append(stem_title)
        peak_pct = max(pct for _, pct in ordered_r)
        cells = []
        for idx_c, (p, pct) in enumerate(ordered_r):
            is_accent = pct > 0 and pct >= max(10, peak_pct - 10)
            cells.append({
                "column_key": f"d_{idx_c}",
                "marks": [_mark_tile(
                    shade=max(0.02, pct / 100.0),
                    top_label=p["period"],
                    center_label=f"{pct}%",
                    muted=not is_accent,
                    highlight_role="peak" if pct == peak_pct and peak_pct > 0 else None,
                )],
            })
            if pct > best_lead_pct or (pct == best_lead_pct and idx_c == len(ordered_r) - 1):
                best_lead_pct = pct
                lead_caption = f"{stem_title} sits at {pct}% {p['phrase']}"
        rows.append({
            "id": f"{slug}-dtm-{m['id']}",
            "leading": [_mark_word(stem_title, style="row", tone="primary", align="left", width="flex", bold=True)],
            "cells": cells,
        })

    if not rows:
        return None

    columns = [{"key": f"d_{i}", "label": f"Date {i + 1}"} for i in range(max_cols)]
    headline, err = derive_common_headline(None, all_titles)
    if err or not headline:
        headline = "Key Deadlines"
    src_count = max(_sources_count(m) for m in picked_markets)
    card = _finalize_section(_make_kit_card(
        card_id=f"{slug}-dated-tiles",
        layout="grid",
        variant="dated_tiles",
        kicker=f"{kicker} · TIMELINES",
        common_headline=headline,
        stat_caption=lead_caption or "Probability across upcoming target dates",
        source_count=src_count,
        route_slug=slug,
        body={
            "show_column_headers": False,
            "row_layout": "stacked_cells",
            "columns": columns,
            "rows": rows,
        },
    ))
    if card is None:
        return None
    _consume_templates(picked_markets, markets, used_ids)
    return card


def _predicate_tokens(name: str, *, entity_tokens: set[str] | frozenset[str] = frozenset()) -> set[str]:
    low = _BEFORE_DATE_RE.sub("", (name or "").lower())
    return {
        tok for tok in re.findall(r"[a-z]+", low)
        if tok not in _GENERIC_STOPWORDS and tok not in entity_tokens and len(tok) > 2
    }


def _build_shared_scale_section(
    slug: str,
    kicker: str,
    markets: Sequence[Mapping[str, Any]],
    used_ids: set[int],
    *,
    require_cluster: bool = True,
    entity_tokens: set[str] | frozenset[str] = frozenset(),
) -> dict[str, Any] | None:
    """Axis section comparing >= 3 open binary markets sharing a predicate with >= 10 pt spread."""
    pool = [m for m in markets if int(m["id"]) not in used_ids and _is_binary_market(m)]
    if len(pool) < 3:
        return None

    # Prefer markets sharing >= 2 non-stopword predicate tokens BEYOND the entity name itself
    clusters: list[list[Mapping[str, Any]]] = []
    tok_map = {int(m["id"]): _predicate_tokens(str(m.get("name") or ""), entity_tokens=entity_tokens) for m in pool}
    for seed_m in pool:
        seed_toks = tok_map[int(seed_m["id"])]
        if not seed_toks:
            continue
        grp = [m for m in pool if len(seed_toks & tok_map[int(m["id"])]) >= min(2, len(seed_toks))]
        if len(grp) >= 3:
            clusters.append(grp)
    if require_cluster and not clusters:
        return None
    chosen_pool = max(clusters, key=lambda g: len(g), default=pool)
    pcts = [_round_pct(_top_probability(m)) for m in chosen_pool]
    if len(chosen_pool) < 3 or (max(pcts) - min(pcts)) < 10:
        return None

    ranked_all = sorted(chosen_pool, key=lambda m: (-_top_probability(m), int(m["id"])))
    selected_rows, consumed_rows = _dedupe_by_rendered_label(ranked_all, limit=5, max_len=44)
    if len(selected_rows) < 3:
        return None
    ranked = [m for m, _ in selected_rows]
    ranked_titles = [str(m.get("name") or "") for m in ranked]
    top_pct = _round_pct(_top_probability(ranked[0]))
    top_title = selected_rows[0][1]
    series: list[dict[str, Any]] = []
    for m, title in selected_rows:
        pct = _round_pct(_top_probability(m))
        series.append({
            "id": f"{slug}-ax-{m['id']}",
            "leading": [_mark_word(title, style="row", tone="primary", align="left", width="flex", bold=True)],
            "marks": [
                _mark_bar_single(pct / 100.0, width="flex"),
                _mark_number(pct, f"{pct}%", unit="%", tone="primary", prominence="primary", align="right", width="sm"),
            ],
        })

    headline, err = derive_common_headline(None, ranked_titles)
    if err or not headline:
        headline = "Shared Odds Scale"
    src_count = max(_sources_count(m) for m in ranked)
    card = _finalize_section(_make_kit_card(
        card_id=f"{slug}-shared-scale",
        layout="axis",
        variant="shared_scale",
        kicker=f"{kicker} · SCALE",
        common_headline=headline,
        stat_caption=f"{top_title} leads at {top_pct}% on the shared 0–100% scale",
        source_count=src_count,
        route_slug=slug,
        body={
            "scale": {
                "scale_kind": "percent",
                "unit": "%",
                "min": 0,
                "max": 100,
                "ticks": [
                    {"x": 0, "label": "0%"},
                    {"x": 50, "label": "50%"},
                    {"x": 100, "label": "100%"},
                ],
            },
            "series": series,
        },
    ))
    if card is None:
        return None
    _consume_templates(consumed_rows, markets, used_ids)
    return card


def _build_countdown_section(
    slug: str,
    kicker: str,
    markets: Sequence[Mapping[str, Any]],
    used_ids: set[int],
    *,
    now: datetime,
) -> dict[str, Any] | None:
    """Stack section for >= 2 remaining open markets closing within 1..45 days."""
    near: list[tuple[int, float, Mapping[str, Any]]] = []
    for m in markets:
        mid = int(m["id"])
        if mid in used_ids or not _is_binary_market(m):
            continue
        res_dt = _parse_iso_dt(m.get("resolution_date") or m.get("close_time"))
        if res_dt is None:
            continue
        days = int((res_dt - now).total_seconds() // 86400)
        if 1 <= days <= 45:
            near.append((days, -_top_probability(m), m))
    if len(near) < 2:
        return None
    near.sort(key=lambda t: (t[0], t[1], int(t[2]["id"])))
    selected_rows, consumed_rows = _dedupe_by_rendered_label([t[2] for t in near], limit=4, max_len=44)
    if len(selected_rows) < 2:
        return None
    picked = [m for m, _ in selected_rows]
    picked_titles = [str(m.get("name") or "") for m in picked]

    items: list[dict[str, Any]] = []
    first_days = 1
    for idx_r, (m, title) in enumerate(selected_rows):
        res_dt = _parse_iso_dt(m.get("resolution_date") or m.get("close_time"))
        days = int((res_dt - now).total_seconds() // 86400) if res_dt else 1
        if idx_r == 0:
            first_days = days
        pct = _round_pct(_top_probability(m))
        items.append({
            "id": f"{slug}-cd-{m['id']}",
            "marks": [
                _mark_word(title, style="row", tone="primary", align="left", width="flex"),
                _mark_number(days, f"{days}d", unit="count", tone="muted", prominence="secondary", align="right", width="auto"),
                _mark_number(pct, f"{pct}%", unit="%", tone="primary", prominence="primary", align="right", width="auto"),
            ],
        })

    first_pct = _round_pct(_top_probability(picked[0]))
    first_title = selected_rows[0][1]
    headline, err = derive_common_headline(None, picked_titles)
    if err or not headline:
        headline = "Near-Term Deadlines"
    src_count = max(_sources_count(m) for m in picked)
    card = _finalize_section(_make_kit_card(
        card_id=f"{slug}-countdown",
        layout="stack",
        variant="countdown",
        kicker=f"{kicker} · COUNTDOWN",
        common_headline=headline,
        stat_caption=f"{first_title} sits at {first_pct}% with {first_days} days left",
        source_count=src_count,
        route_slug=slug,
        body={"header_layout": "none", "header_marks": [], "items": items},
    ))
    if card is None:
        return None
    _consume_templates(consumed_rows, markets, used_ids)
    return card


def _build_one_in_n_section(
    slug: str,
    kicker: str,
    markets: Sequence[Mapping[str, Any]],
    used_ids: set[int],
) -> dict[str, Any] | None:
    """Stack section translating >= 2 open long-shots (1..15%) into '1 in N' odds."""
    longshots: list[tuple[int, Mapping[str, Any]]] = []
    for m in markets:
        mid = int(m["id"])
        if mid in used_ids:
            continue
        pct = _round_pct(_top_probability(m))
        if 1 <= pct <= 15:
            longshots.append((pct, m))
    if len(longshots) < 2:
        return None
    longshots.sort(key=lambda pm: (-pm[0], int(pm[1]["id"])))
    selected_rows, consumed_rows = _dedupe_by_rendered_label([pm[1] for pm in longshots], limit=4, max_len=44)
    if len(selected_rows) < 2:
        return None
    picked = [m for m, _ in selected_rows]
    picked_titles = [str(m.get("name") or "") for m in picked]

    items: list[dict[str, Any]] = []
    for m, title in selected_rows:
        pct = _round_pct(_top_probability(m))
        n_val = compute_one_in_n(pct)
        items.append({
            "id": f"{slug}-oin-{m['id']}",
            "marks": [
                _mark_word(title, style="row", tone="primary", align="left", width="flex"),
                _mark_number(n_val, f"1 in {n_val}", unit="one_in_n", tone="accent", prominence="primary", align="right", width="auto"),
                _mark_number(pct, f"{pct}%", unit="%", tone="muted", prominence="secondary", align="right", width="auto"),
            ],
        })

    lead_pct = _round_pct(_top_probability(picked[0]))
    lead_n = compute_one_in_n(lead_pct)
    lead_title = selected_rows[0][1]
    headline, err = derive_common_headline(None, picked_titles)
    if err or not headline:
        headline = "Long-Shot Odds"
    src_count = max(_sources_count(m) for m in picked)
    card = _finalize_section(_make_kit_card(
        card_id=f"{slug}-one-in-n",
        layout="stack",
        variant="one_in_n",
        kicker=f"{kicker} · TAIL ODDS",
        common_headline=headline,
        stat_caption=f"{lead_title} carries a 1 in {lead_n} ({lead_pct}%) chance",
        source_count=src_count,
        route_slug=slug,
        body={"header_layout": "none", "header_marks": [], "items": items},
    ))
    if card is None:
        return None
    _consume_templates(consumed_rows, markets, used_ids)
    return card


def _build_casting_sheet_section(
    slug: str,
    kicker: str,
    markets: Sequence[Mapping[str, Any]],
    used_ids: set[int],
) -> dict[str, Any] | None:
    """Stack casting_sheet section ONLY when every printed contender row has verified HTTPS art."""
    art_map = _verified_art_by_key()
    for m in sorted(markets, key=lambda x: (-int(x.get("volume_24h") or 0), int(x["id"]))):
        mid = int(m["id"])
        if mid in used_ids or _is_binary_market(m):
            continue
        outs = [o for o in _sorted_outcomes(m) if o["name"].lower() not in {"yes", "no", "other"}][:4]
        if len(outs) < 2:
            continue
        pics = [_lookup_subject_art(o["name"], art_map) for o in outs]
        if not all(p is not None and p.get("url", "").split("/")[2] in ALLOWED_KIT_IMAGE_HOSTS for p in pics):
            continue
        items = []
        for idx_o, (o, pic) in enumerate(zip(outs, pics)):
            pct = _round_pct(o["prob"])
            items.append({
                "id": f"{slug}-cs-{mid}-{idx_o}",
                "marks": [
                    pic,
                    _mark_word(o["name"], style="row", tone="primary", align="left", width="flex", bold=(idx_o == 0)),
                    _mark_number(pct, f"{pct}%", unit="%", tone="primary", prominence="primary", align="right", width="auto"),
                ],
            })
        top_o = outs[0]
        top_pct = _round_pct(top_o["prob"])
        headline, err = derive_common_headline(str(m.get("name") or ""), [str(m.get("name") or "")])
        if err or not headline:
            headline = "Top Contenders"
        card = _finalize_section(_make_kit_card(
            card_id=f"{slug}-casting-sheet",
            layout="stack",
            variant="casting_sheet",
            kicker=f"{kicker} · CONTENDERS",
            common_headline=headline,
            stat_caption=f"{top_o['name']} leads at {top_pct}%",
            source_count=_sources_count(m),
            route_slug=slug,
            body={"header_layout": "none", "header_marks": [], "items": items},
        ))
        if card is not None:
            _consume_templates([m], markets, used_ids)
            return card
    return None


def _build_plain_bar_stack_section(
    slug: str,
    kicker: str,
    markets: Sequence[Mapping[str, Any]],
    used_ids: set[int],
    *,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """388: A last-resort bar stack section, used ONLY when < 3 structured sections fit."""
    ref_now = _parse_iso_dt(now) or datetime.now(timezone.utc)
    # Prefer an unused multi-outcome contender market first, otherwise >= 2 binary markets
    for m in sorted(markets, key=lambda x: (-int(x.get("volume_24h") or 0), int(x["id"]))):
        mid = int(m["id"])
        if mid in used_ids or _is_binary_market(m):
            continue
        outs = _sorted_outcomes(m)[:4]
        if len(outs) < 2:
            continue
        # Never render multi-outcome date-rung markets in plain bars (past settled 0% dates leak under Condition 5)
        date_cnt = sum(
            1
            for o in outs
            if _parse_date_marker(str(o.get("name") or ""), default_year=ref_now.year) is not None
            and len(str(o.get("name") or "").split()) <= 5
        )
        if date_cnt >= 2:
            continue
        items = []
        for idx_o, o in enumerate(outs):
            pct = _round_pct(o["prob"])
            items.append({
                "id": f"{slug}-bar-m-{mid}-{idx_o}",
                "marks": [
                    _mark_word(o["name"], style="row", tone="primary", align="left", width="flex", bold=(idx_o == 0)),
                    _mark_bar_single(pct / 100.0, width="sm"),
                    _mark_number(pct, f"{pct}%", unit="%", tone="primary", prominence="primary", align="right", width="auto"),
                ],
            })
        top_o = outs[0]
        top_pct = _round_pct(top_o["prob"])
        headline, err = derive_common_headline(str(m.get("name") or ""), [str(m.get("name") or "")])
        if err or not headline:
            headline = "Leading Outcomes"
        card = _finalize_section(_make_kit_card(
            card_id=f"{slug}-plain-bars",
            layout="stack",
            variant="plain_bar_stack",
            kicker=f"{kicker} · ODDS",
            common_headline=headline,
            stat_caption=f"{top_o['name']} leads at {top_pct}%",
            source_count=_sources_count(m),
            route_slug=slug,
            body={"header_layout": "none", "header_marks": [], "items": items},
        ))
        if card is not None:
            _consume_templates([m], markets, used_ids)
            return card

    rem_bin = [m for m in markets if int(m["id"]) not in used_ids and _is_binary_market(m)]
    rem_bin.sort(key=lambda m: (-_top_probability(m), int(m["id"])))
    if len(rem_bin) < 2:
        return None
    selected_rows, consumed_rows = _dedupe_by_rendered_label(rem_bin, limit=4, max_len=44)
    if len(selected_rows) < 2:
        return None
    picked = [m for m, _ in selected_rows]
    picked_titles = [str(m.get("name") or "") for m in picked]
    items = []
    for m, title in selected_rows:
        pct = _round_pct(_top_probability(m))
        items.append({
            "id": f"{slug}-bar-b-{m['id']}",
            "marks": [
                _mark_word(title, style="row", tone="primary", align="left", width="flex"),
                _mark_bar_single(pct / 100.0, width="sm"),
                _mark_number(pct, f"{pct}%", unit="%", tone="primary", prominence="primary", align="right", width="auto"),
            ],
        })
    lead_m = picked[0]
    lead_pct = _round_pct(_top_probability(lead_m))
    lead_title = selected_rows[0][1]
    headline, err = derive_common_headline(None, picked_titles)
    if err or not headline:
        headline = "Open Odds"
    card = _finalize_section(_make_kit_card(
        card_id=f"{slug}-plain-bars",
        layout="stack",
        variant="plain_bar_stack",
        kicker=f"{kicker} · ODDS",
        common_headline=headline,
        stat_caption=f"{lead_title} leads at {lead_pct}%",
        source_count=max(_sources_count(m) for m in picked),
        route_slug=slug,
        body={"header_layout": "none", "header_marks": [], "items": items},
    ))
    if card is None:
        return None
    _consume_templates(consumed_rows, markets, used_ids)
    return card


def propose_container_page_for_family(
    family_label: str | None,
    markets: Sequence[Mapping[str, Any]],
    *,
    now: datetime | None = None,
    kicker: str | None = None,
    family_fingerprint: str | None = None,
) -> dict[str, Any]:
    """Compose a multi-section Kit preview page purely from one family's market structure."""
    ref_now = _parse_iso_dt(now) or datetime.now(timezone.utc)
    raw_list = [dict(m) for m in markets if m.get("id") is not None]
    if any(is_settled_market(m, ref_now) for m in raw_list):
        return {
            "accepted": False,
            "refusal_reason": "refused_contains_settled_member",
            "family_fingerprint": family_fingerprint,
            "market_count": len(raw_list),
            "sections_built": 0,
            "variants": [],
        }

    clean_markets = _dedupe_twins(raw_list)
    if len(clean_markets) < 5:
        return {
            "accepted": False,
            "refusal_reason": "refused_too_few_markets",
            "family_fingerprint": family_fingerprint,
            "market_count": len(clean_markets),
            "sections_built": 0,
            "variants": [],
        }

    titles = [str(m.get("name") or m.get("title") or "") for m in clean_markets]
    headline, h_err = derive_common_headline(family_label, titles)
    if h_err or not headline:
        return {
            "accepted": False,
            "refusal_reason": h_err or "refused_headline_not_2_to_4_common_thing",
            "family_fingerprint": family_fingerprint,
            "market_count": len(clean_markets),
            "sections_built": 0,
            "variants": [],
        }

    slug = _slugify(headline)
    resolved_kicker = (kicker or resolve_kicker(clean_markets)).upper()
    used_ids: set[int] = set()
    sections: list[dict[str, Any]] = []
    seen_variants: set[str] = set()

    entity_tokens = {
        t.lower() for t in re.findall(r"[A-Za-z0-9]+", headline)
        if t.lower() not in {"outlook", "timeline", "updates"}
    }

    def _try_append(builder_fn: Any, *args: Any, **kwargs: Any) -> None:
        if len(sections) >= 5:
            return
        sec = builder_fn(*args, **kwargs)
        if sec is None:
            return
        variant = str(sec.get("variant") or "")
        if not variant or variant in seen_variants:
            return
        sec_hl = str(sec.get("common_headline") or "").strip()
        if not sec_hl or sec_hl.lower() == headline.lower():
            sec = {**sec, "common_headline": _SECTION_FALLBACK_TITLES.get(variant, sec_hl or headline)}
        seen_variants.add(variant)
        sections.append(sec)

    # Order prioritizes structural variety first; plain_bar_stack is strictly last resort (388: A).
    _try_append(_build_scoreboard_grid_section, slug, resolved_kicker, clean_markets, used_ids, now=ref_now)
    _try_append(_build_dated_tiles_section, slug, resolved_kicker, clean_markets, used_ids, now=ref_now)
    _try_append(_build_shared_scale_section, slug, resolved_kicker, clean_markets, used_ids, require_cluster=True, entity_tokens=entity_tokens)
    _try_append(_build_countdown_section, slug, resolved_kicker, clean_markets, used_ids, now=ref_now)
    _try_append(_build_one_in_n_section, slug, resolved_kicker, clean_markets, used_ids)
    _try_append(_build_casting_sheet_section, slug, resolved_kicker, clean_markets, used_ids)

    if len(sections) < 3:
        _try_append(_build_shared_scale_section, slug, resolved_kicker, clean_markets, used_ids, require_cluster=False, entity_tokens=entity_tokens)
    if len(sections) < 3:
        _try_append(_build_plain_bar_stack_section, slug, resolved_kicker, clean_markets, used_ids, now=ref_now)

    if len(sections) < 3:
        return {
            "accepted": False,
            "refusal_reason": "refused_too_few_distinct_sections",
            "family_fingerprint": family_fingerprint,
            "headline": headline,
            "slug": slug,
            "kicker": resolved_kicker,
            "market_count": len(clean_markets),
            "sections_built": len(sections),
            "variants": [str(s.get("variant") or "") for s in sections],
        }

    page = {
        "kit_page_version": 1,
        "state": "preview",
        "slug": slug,
        "title": headline,
        "kicker": resolved_kicker,
        "caption": f"{len(sections)} disjoint views across {len(used_ids)} open markets",
        "family_fingerprint": family_fingerprint,
        "snapshot_captured_at": ref_now.isoformat(),
        "covered_market_ids": sorted(used_ids),
        "market_count": len(used_ids),
        "section_count": len(sections),
        "variants": [str(s["variant"]) for s in sections],
        "sections": sections,
    }
    return {"accepted": True, "refusal_reason": None, "page": page}
