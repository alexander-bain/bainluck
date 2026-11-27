"""Generic deterministic Kit container-page composer (Decision 386: A, #12221).

Composes uncovered prediction-market families into multi-section preview pages
using only the shared Kit v1 layouts (`stack | grid | calendar | axis`) and
structural market patterns — with zero hardcoded slugs, topic names, or market IDs.
"""

from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
from typing import Any, Mapping, Sequence

from app.utils.discover_fun_scout import _SCOUT_NON_FUN_HARM_RE
from app.utils.discover_fun_tags import check_fun_taste_guard
from app.utils.feed_reasons import _display_pct
from app.utils.graded_card import rendered_percent
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
from app.utils.outcome_display import (
    drop_dominant_field_outcomes,
    is_field_outcome,
    normalize_display_probs,
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
    r"\b(Before\s+|by\s+|on\s+|in\s+)?"
    r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\b"
    r"(?:\s+(?!\d{4}\b)(\d{1,2}),?)?"
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
    "against", "publicly", "beyond", "within", "without", "over", "under", "into",
    "toward", "towards", "between", "during", "through", "around", "about",
    "would", "should", "could", "can", "may", "might", "insult", "praise", "visit",
})
_DANGLING_ROW_STARTERS = frozenset({
    "or", "and", "least", "most", "to", "of", "in", "for", "with", "be", "by", "been",
})
_BANNED_SECTION_HEADINGS = frozenset({
    "outcome matrix",
    "key timelines",
    "key deadlines",
    "shared odds scale",
    "near-term catalysts",
    "near-term deadlines",
    "long-shot odds",
    "open odds",
    "leading outcomes",
    "target dates",
    "key storylines",
    "this month",
    "outside scenarios",
    "open questions",
    "decision paths",
    "leading contenders",
})
_INTERROGATIVE_START_RE = re.compile(
    r"^(?:Will|Who|What|Which|When|Where|How|Does|Do|Did|Is|Are|Can|Could|Would|Should|Has|Have)\b",
    re.IGNORECASE,
)


def _slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s[:64] or "container-preview"


def _normalize_prob(raw: Any) -> float | None:
    """Normalize a raw probability into [0.0, 1.0] ONCE to prevent double-scaling."""
    if raw is None or isinstance(raw, bool):
        return None
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None
    if val > 1.0:
        val /= 100.0
    return max(0.0, min(1.0, val))


def _pct_int(prob_frac: float | None) -> int:
    """Whole percent computed via `rendered_percent` on a [0.0, 1.0] fraction."""
    if prob_frac is None:
        return 0
    val = rendered_percent(prob_frac)
    return 0 if val is None else int(val)


def _pct_display(prob_frac: float, pct: int | None = None) -> str:
    """Format a [0.0, 1.0] probability via shared `feed_reasons._display_pct` ('<1%' / '>99%')."""
    return f"{_display_pct(prob_frac, printed=pct)}%"


def _round_pct(prob: Any) -> int:
    """Backward-safe alias strictly over [0.0, 1.0] probabilities (uses rendered_percent)."""
    return _pct_int(_normalize_prob(prob))


def _passes_taste_and_harm(title: str | None, description: str | None = None) -> bool:
    """Reuse the scout's taste and severe-harm guards verbatim."""
    ok, _ = check_fun_taste_guard(title, description)
    if not ok:
        return False
    combined = " ".join(part for part in (title or "", description or "") if part).strip()
    if combined and _SCOUT_NON_FUN_HARM_RE.search(combined):
        return False
    return True


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
    items: list[dict[str, Any]] = []
    for o in raw:
        if not isinstance(o, Mapping):
            continue
        p_raw = o.get("current_probability")
        if p_raw is None:
            p_raw = o.get("probability")
        prob = _normalize_prob(p_raw)
        if prob is None:
            continue
        oid_raw = o.get("id")
        oid = int(oid_raw) if isinstance(oid_raw, int) and not isinstance(oid_raw, bool) else None
        items.append({
            "id": oid,
            "name": str(o.get("name") or "").strip(),
            "probability": prob,
            "is_winner": o.get("is_winner"),
            "resolution_source": o.get("resolution_source"),
            "_orig_rp": o.get("rendered_percent"),
        })
    if not items:
        return []
    has_named = any(not is_field_outcome(o.get("name")) for o in items)
    items = drop_dominant_field_outcomes(
        items,
        lambda o: o.get("name"),
        lambda o: 1.0 if has_named and o.get("probability") == 1.0 else None,
        is_winner_of=lambda o: bool(o.get("is_winner")) and o.get("resolution_source") is not None,
    )
    me_raw = market.get("mutually_exclusive")
    mutually_excl = True if me_raw is None else bool(me_raw)
    normalize_display_probs(
        items,
        key="probability",
        mutually_exclusive=mutually_excl,
        field_complete=True,
        question=str(market.get("name") or ""),
    )
    out: list[dict[str, Any]] = []
    for o in items:
        prob = float(o["probability"])
        rp = o.get("rendered_percent")
        if rp is None and o.get("_orig_rp") is not None:
            rp = int(o["_orig_rp"])
        out.append({
            "id": o["id"],
            "name": o["name"],
            "prob": prob,
            "rendered_percent": int(rp) if rp is not None else _pct_int(prob),
            "is_winner": bool(o.get("is_winner")),
        })
    out.sort(key=lambda r: (-r["prob"], r["name"]))
    return out


def _is_binary_market(market: Mapping[str, Any]) -> bool:
    raw = market.get("outcomes") or []
    raw_names = {
        str(o.get("name") or "").strip().lower()
        for o in raw
        if isinstance(o, Mapping)
    } - {""}
    if len(raw) >= 2 and (raw_names - {"yes", "no"}):
        return False
    outcomes = _sorted_outcomes(market)
    if not outcomes:
        return not bool(re.match(r"^\s*(?:when|who|what|where|which|how)\b", str(market.get("name") or ""), re.IGNORECASE))
    names = {o["name"].lower() for o in outcomes}
    return len(outcomes) <= 2 and names <= {"yes", "no"}


def _top_outcome_cell(market: Mapping[str, Any]) -> tuple[float, int | None, int]:
    """Return ``(prob_0_to_1, outcome_id, page_rendered_percent)`` matching market detail."""
    outcomes = _sorted_outcomes(market)
    if outcomes:
        yes = next((o for o in outcomes if o["name"].lower() == "yes"), None)
        if yes is not None:
            return float(yes["prob"]), yes.get("id"), int(yes["rendered_percent"])
        if len(outcomes) == 1 and outcomes[0]["name"].lower() == "no":
            frac = max(0.0, 1.0 - float(outcomes[0]["prob"]))
            rp = max(0, 100 - int(outcomes[0]["rendered_percent"]))
            return frac, outcomes[0].get("id"), rp
        return (
            float(outcomes[0]["prob"]),
            outcomes[0].get("id"),
            int(outcomes[0]["rendered_percent"]),
        )
    p = market.get("current_probability")
    if p is None:
        p = market.get("probability")
    frac = _normalize_prob(p)
    frac_val = 0.0 if frac is None else frac
    return frac_val, None, _pct_int(frac_val)


def _top_fraction_and_outcome(market: Mapping[str, Any]) -> tuple[float, int | None]:
    """Return (probability_in_0_to_1, outcome_id) for the market's displayed yes/top leg."""
    frac, oid, _ = _top_outcome_cell(market)
    return frac, oid


def _top_probability(market: Mapping[str, Any]) -> float:
    """Return probability in 0..100 scale for ordering comparisons only."""
    return _top_fraction_and_outcome(market)[0] * 100.0


def _sources_count(market: Mapping[str, Any]) -> int:
    raw = market.get("sources_count")
    if isinstance(raw, int) and raw > 0:
        return raw
    srcs = market.get("sources")
    if isinstance(srcs, (list, tuple, set)) and srcs:
        return len(srcs)
    return 1


_NORM_IES_VERB_RE = re.compile(r"\b([a-z]{3,})ies\b")
_NORM_ES_VERB_RE = re.compile(r"\b([a-z]{3,}(?:ch|sh|ss|x|z))es\b")


def _normalize_question_key(name: str) -> str:
    txt = (name or "").lower().strip()
    txt = txt.replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')
    txt = re.sub(r"^(?:will|does|do|is|are|can)\s+", "", txt)
    txt = re.sub(r"\bin\s+front\s+of\b", "before", txt)
    txt = re.sub(r"\b(?:the|a|an|publicly|officially|actually|ever|be)\b", " ", txt)
    txt = _NORM_IES_VERB_RE.sub(r"\1y", txt)
    txt = _NORM_ES_VERB_RE.sub(r"\1", txt)
    txt = re.sub(
        r"\b(fine|charge|announce|launch|report|release|cut|raise|hit|win|"
        r"testify|visit|resign|step|acquire|buy|sell|lose|reach|pass|fall|"
        r"drop|rise|exceed|top|break|close|open|start|end|join|leave|sign|"
        r"ban|sue|indict|approve|reject|veto|speak|say|mention|meet|call|"
        r"post|tweet|appear|host|perform|score|strike|attack|invade|annex|"
        r"deploy|publish|ship|unveil|debut|hold|pause|default|file|appoint|"
        r"nominate|confirm|elect|impeach|pardon|convict|marry|divorce|retire|"
        r"die|commit|delay|stay|wear)s\b",
        r"\1",
        txt,
    )
    txt = re.sub(r"[?!.,'\":()]+", "", txt)
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt


def _norm_outcome_phrase(name: str) -> str:
    low = re.sub(r"^(?:the|a|an)\s+", "", (name or "").lower().strip())
    low = re.sub(r"[^a-z0-9\s]+", " ", low)
    return re.sub(r"\s+", " ", low).strip()


def _binary_matches_multi_parent(binary_mkt: Mapping[str, Any], parent_outcomes: set[str]) -> bool:
    if not parent_outcomes or not _is_binary_market(binary_mkt):
        return False
    title_norm = f" {_norm_outcome_phrase(str(binary_mkt.get('name') or binary_mkt.get('title') or ''))} "
    if not title_norm.strip():
        return False
    return any(len(oname) >= 3 and f" {oname} " in title_norm for oname in parent_outcomes)


def _canonical_question_and_deadline(
    name: str,
    default_year: int,
    *,
    resolution_date: Any = None,
) -> tuple[str, str | None]:
    """Return `(dateless_stem_qkey, canonical_deadline_iso)` equating `before Jan 1, N+1` with `by Dec 31, N`."""
    raw = str(name or "").strip()
    dm = _parse_date_marker(raw, default_year=default_year)
    canon_date: str | None = None
    stem_text = raw
    if dm is not None:
        stem_text = str(dm.get("display_stem") or dm.get("stem") or raw)
        dt = dm["sort_dt"]
        phrase_low = str(dm.get("phrase") or "").lower()
        if phrase_low.startswith("before ") and dt.month == 1 and dt.day == 1:
            dt = dt - timedelta(days=1)
        canon_date = dt.date().isoformat()
    elif resolution_date is not None:
        rd = _parse_iso_dt(resolution_date)
        if rd is not None:
            canon_date = rd.date().isoformat()
    stem_qkey = _normalize_question_key(stem_text)
    if not stem_qkey:
        stem_qkey = _normalize_question_key(raw)
    return stem_qkey, canon_date


def _blend_binary_twin_bucket(bucket: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Pick lead twin and combine binary probabilities across distinct venues when sources disagree."""
    ordered = sorted(
        (dict(x) for x in bucket),
        key=lambda x: (-_sources_count(x), -int(x.get("volume_24h") or 0), int(x.get("id") or 0)),
    )
    lead = dict(ordered[0])
    sources = {str(x.get("source") or "kalshi").lower() for x in ordered}
    lead["sources_count"] = max(_sources_count(lead), len(sources))
    if len(sources) >= 2 and all(_is_binary_market(x) for x in ordered):
        by_src: dict[str, tuple[int, float]] = {}
        for x in ordered:
            src_k = str(x.get("source") or "kalshi").lower()
            vol = int(x.get("volume_24h") or 0)
            frac, _, _ = _top_outcome_cell(x)
            if src_k not in by_src or vol > by_src[src_k][0]:
                by_src[src_k] = (vol, frac)
        if len(by_src) >= 2:
            combined_prob = max(0.0, min(1.0, sum(v[1] for v in by_src.values()) / len(by_src)))
            combined_pct = rendered_percent(combined_prob)
            new_outs = []
            for o in lead.get("outcomes") or ():
                if not isinstance(o, Mapping):
                    continue
                oc = dict(o)
                oname = str(oc.get("name") or "").strip().lower()
                if oname == "yes":
                    oc["probability"] = combined_prob
                    oc["current_probability"] = combined_prob
                    oc["rendered_percent"] = combined_pct
                elif oname == "no":
                    no_p = max(0.0, min(1.0, 1.0 - combined_prob))
                    oc["probability"] = no_p
                    oc["current_probability"] = no_p
                    oc["rendered_percent"] = rendered_percent(no_p)
                else:
                    oc["probability"] = combined_prob
                    oc["current_probability"] = combined_prob
                    oc["rendered_percent"] = combined_pct
                new_outs.append(oc)
            if new_outs:
                lead["outcomes"] = new_outs
    return lead


def _dedupe_twins(markets: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Collapse cross-venue twins (including before Jan 1 / by Dec 31 equivalents) and same-group clones."""
    ref_now = datetime.now(timezone.utc)
    default_year = ref_now.year
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for m in markets:
        item = dict(m)
        gid = str(item.get("group_id") or "").strip()
        raw_name = str(item.get("name") or item.get("title") or "")
        qkey = _normalize_question_key(raw_name)
        if _is_binary_market(item):
            stem_qkey, canon_date = _canonical_question_and_deadline(
                raw_name,
                default_year,
                resolution_date=None,
            )
            if stem_qkey and canon_date:
                dedupe_key = f"bd:{stem_qkey}@{canon_date}"
            elif qkey:
                dedupe_key = f"q:{qkey}"
            else:
                dedupe_key = f"gid:{gid}:{item.get('id')}"
        else:
            dedupe_key = f"q:{qkey}" if qkey else f"gid:{gid}:{item.get('id')}"
        groups[dedupe_key].append(item)

    deduped = [_blend_binary_twin_bucket(bucket) for bucket in groups.values()]

    # Absorb binary markets duplicating a rung on a multi-outcome date-ladder market, combining distinct sources.
    multi_date_rungs: dict[tuple[str, str], tuple[dict[str, Any], dict[str, Any]]] = {}
    for m in deduped:
        if _is_binary_market(m):
            continue
        m_title = str(m.get("name") or m.get("title") or "")
        m_stem = _normalize_question_key(re.sub(r"\s+(?:by|before)\.\.\.\??$", "", m_title))
        if not m_stem:
            continue
        for o in m.get("outcomes") or ():
            if not isinstance(o, Mapping):
                continue
            _, rung_date = _canonical_question_and_deadline(
                str(o.get("name") or ""),
                default_year,
            )
            if rung_date:
                multi_date_rungs[(m_stem, rung_date)] = (m, o)  # type: ignore[assignment]

    if multi_date_rungs:
        absorbed_ids: set[int] = set()
        for m in deduped:
            if not _is_binary_market(m) or m.get("id") is None:
                continue
            b_stem, b_date = _canonical_question_and_deadline(
                str(m.get("name") or m.get("title") or ""),
                default_year,
            )
            if not b_stem or not b_date or (b_stem, b_date) not in multi_date_rungs:
                continue
            parent_m, rung_o = multi_date_rungs[(b_stem, b_date)]
            src_parent = str(parent_m.get("source") or "kalshi").lower()
            src_bin = str(m.get("source") or "kalshi").lower()
            if src_parent != src_bin:
                p_rung = _normalize_prob(rung_o.get("current_probability") if rung_o.get("current_probability") is not None else rung_o.get("probability"))
                p_bin, _, _ = _top_outcome_cell(m)
                if p_rung is not None:
                    blended = max(0.0, min(1.0, (p_rung + p_bin) / 2.0))
                    rung_o["probability"] = blended
                    rung_o["current_probability"] = blended
                    rung_o["rendered_percent"] = rendered_percent(blended)
                    parent_m["sources_count"] = max(_sources_count(parent_m), 2)
            absorbed_ids.add(int(m["id"]))
        if absorbed_ids:
            deduped = [m for m in deduped if m.get("id") not in absorbed_ids]

    # Collapse binary submarkets that share a group_id with an eligible multi-outcome parent
    # (e.g. "Will Clavicular visit Russia?" alongside "Which countries will Clavicular visit?").
    parent_outcomes_by_gid: dict[str, set[str]] = defaultdict(set)
    for m in deduped:
        gid = str(m.get("group_id") or "").strip()
        if not gid or _is_binary_market(m):
            continue
        outs = _eligible_multi_contender_outcomes(m, ref_now=ref_now, exclude_other=False)
        if len(outs) < 2:
            outs = [o for o in _sorted_outcomes(m) if not o.get("is_field")]
        if len(outs) >= 2:
            for o in outs:
                oname = _norm_outcome_phrase(str(o.get("name") or ""))
                if len(oname) >= 3:
                    parent_outcomes_by_gid[gid].add(oname)

    if not parent_outcomes_by_gid:
        return deduped

    collapsed: list[dict[str, Any]] = []
    for m in deduped:
        gid = str(m.get("group_id") or "").strip()
        if gid in parent_outcomes_by_gid and _binary_matches_multi_parent(m, parent_outcomes_by_gid[gid]):
            continue
        collapsed.append(m)
    return collapsed


_BARE_INFINITIVE_FRAG_RE = re.compile(
    r"(?:\bbe\b|\bjoin\b|\bpublish\b|\bannounce\b|\battend\b|\bcapture\b|\benter\b|\btarget\s+[A-Z]|\badmit(?:s)?\b|\brelease\b|\btestify\b)",
    re.IGNORECASE,
)
_DANGLING_TRAILING_PREP_RE = re.compile(
    r"\s+(?:by|before|in|on|at|for|to|with)\s*(?:\.\.\.|…)*[?!.:]*$",
    re.IGNORECASE,
)


def derive_common_headline(
    family_label: str | None,
    titles: Sequence[str],
) -> tuple[str | None, str | None]:
    """Derive a 2-4 word declarative common headline without stat noise, conjunctions, or taste violations."""
    candidates: list[str] = []
    single_entity_label: str | None = None
    if family_label:
        if not _passes_taste_and_harm(str(family_label)):
            return None, "refused_scout_taste_or_harm_guard"
        clean_fl = re.sub(r"[?!.:]+$", "", str(family_label)).strip()
        fl_words = clean_fl.split()
        if len(fl_words) == 1 and len(fl_words[0]) >= 3 and not _STAT_NOISE_RE.search(clean_fl):
            w0 = fl_words[0]
            single_entity_label = w0 if any(c.isupper() for c in w0) else w0.capitalize()
        candidates.append(str(family_label))
    candidates.extend(str(t) for t in titles if t)

    norm_titles_low = [str(t or "").lower() for t in titles if t]
    for idx_c, raw in enumerate(candidates):
        is_fam = family_label is not None and idx_c == 0
        if idx_c == 1 and single_entity_label and not _HAS_CONJUNCTION_RE.search(single_entity_label):
            hl_out = f"{single_entity_label} Outlook"
            if _passes_taste_and_harm(hl_out):
                return hl_out, None
        txt = raw.replace("{}", " ").strip()
        txt = _DANGLING_TRAILING_PREP_RE.sub("", txt).strip()
        txt = re.sub(r"[?!.:]+$", "", txt).strip()
        txt = re.sub(r"^(?:Will|Who\s+will|What\s+will|Which|When\s+will|Does|Is|Are)\s+", "", txt, flags=re.IGNORECASE)
        txt = _HEADLINE_STRIP_SUFFIX_RE.sub("", txt).strip()
        txt = _DANGLING_TRAILING_PREP_RE.sub("", txt).strip()
        txt = re.sub(r"\s+", " ", txt).strip(" -–—,:;")
        if not txt or _STAT_NOISE_RE.search(txt) or _HAS_CONJUNCTION_RE.search(txt):
            continue
        if not is_fam and _BARE_INFINITIVE_FRAG_RE.search(txt):
            continue
        words = [w for w in txt.split() if w]
        if 2 <= len(words) <= 4:
            last_low = words[-1].lower().strip("?!.,")
            if last_low in _DANGLING_HEADLINE_ENDINGS and not is_fam:
                continue
            if not is_fam and len(norm_titles_low) >= 2:
                # Single candidate title only wins if its core tokens actually fit >= half of siblings.
                sig_toks = [
                    w.lower() for w in words
                    if w.lower() not in _GENERIC_STOPWORDS and len(w) > 2
                ][:2]
                if sig_toks:
                    matched = sum(1 for nt in norm_titles_low if all(st in nt for st in sig_toks))
                    if matched < max(2, (len(norm_titles_low) + 1) // 2):
                        continue
            formatted = " ".join(w if any(c.isupper() for c in w) else w.capitalize() for w in words)
            if _passes_taste_and_harm(formatted):
                return formatted, None

    if single_entity_label and not _HAS_CONJUNCTION_RE.search(single_entity_label):
        hl_out = f"{single_entity_label} Outlook"
        if _passes_taste_and_harm(hl_out):
            return hl_out, None

    # Fallback: extract contiguous common prefix across titles (never glue disjoint bare verbs/nouns)
    if len(titles) >= 2:
        cleaned_lists = [
            _DANGLING_TRAILING_PREP_RE.sub(
                "",
                re.sub(r"^(?:Will|Who\s+will|What\s+will|When\s+will|Does|Is|Are)\s+", "", re.sub(r"[?!.:]+$", "", t or "").strip(), flags=re.IGNORECASE),
            ).strip().split()
            for t in titles
            if t
        ]
        if len(cleaned_lists) >= 2:
            prefix_words: list[str] = []
            seen_prefix_bases: set[str] = set()
            for words_at_i in zip(*cleaned_lists):
                if len({w.lower() for w in words_at_i}) == 1:
                    raw_w = words_at_i[0]
                    base = re.sub(r"[\'\u2019]s$", "", raw_w.lower()).strip("?!.,")
                    if not base or base in _GENERIC_STOPWORDS or base in seen_prefix_bases:
                        continue
                    seen_prefix_bases.add(base)
                    prefix_words.append(re.sub(r"[\'\u2019]s$", "", raw_w))
                else:
                    break
            while prefix_words and prefix_words[-1].lower().strip("?!.,") in (_GENERIC_STOPWORDS | _DANGLING_HEADLINE_ENDINGS):
                prefix_words.pop()
            if 2 <= len(prefix_words) <= 4:
                candidate = " ".join(w if any(c.isupper() for c in w) else w.capitalize() for w in prefix_words)
                if (
                    not _HAS_CONJUNCTION_RE.search(candidate)
                    and not _STAT_NOISE_RE.search(candidate)
                    and not _BARE_INFINITIVE_FRAG_RE.search(candidate)
                    and _passes_taste_and_harm(candidate)
                ):
                    return candidate, None
    return None, "refused_headline_not_2_to_4_common_thing"


_UPPER_PRESERVE = frozenset({
    "AI", "AGI", "IPO", "US", "UK", "CEO", "DOJ", "FAA", "FDA", "SEC", "NBA", "NFL", "NHL", "S&P", "TV",
})


_TITLE_MINOR_WORDS = frozenset({"to", "of", "in", "on", "at", "by", "for", "and", "or", "the", "a", "an"})


def _title_case_phrase(phrase: str) -> str:
    words = phrase.split()
    out: list[str] = []
    for idx, w in enumerate(words):
        if w.upper() in _UPPER_PRESERVE or any(c.isupper() for c in w) or w == "&":
            out.append(w)
        elif 0 < idx < len(words) - 1 and w.lower() in _TITLE_MINOR_WORDS:
            out.append(w.lower())
        else:
            out.append(w.capitalize())
    return " ".join(out)


_SECTION_THEME_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bpublicly\s+insult\b", re.I), "public insults"),
    (re.compile(r"\bpublicly\s+praise\b", re.I), "public praise"),
    (re.compile(r"\b(?:stage|keynote|conference|earnings call)\b", re.I), "stage remarks"),
    (re.compile(r"\b(?:say\s+(?:the\s+words?|\"|\u201c)|mention\s+[A-Z]|public\s+remarks?|public\s+statements?)\b", re.I), "public statements"),
    (re.compile(r"\b(?:token\s+price|output\s+token|api\s+pric\w*|frontier.*price)\b", re.I), "token pricing"),
    (re.compile(r"\b(?:visit|travel\s+to|tourist|tourism|countries\s+(?:will|to)\s+visit|destination)\b", re.I), "travel destinations"),
    (re.compile(r"\b(?:insult|praise|criticiz\w*|endorse\w*)\b", re.I), "public remarks"),
    (re.compile(r"\bapproval\s+rating\b", re.I), "approval rating"),
    (re.compile(r"\b(?:impeach\w*|pardon|veto|executive\s+order)\b", re.I), "executive actions"),
    (re.compile(r"\b(?:academy\s+awards?|oscar|golden\s+globes?|emmy|grammy|nomina\w*|best\s+picture|best\s+actor|best\s+actress|best\s+visual|best\s+sound|best\s+cinematography|person\s+of\s+the\s+year|nobel|pulitzer|prize)\b", re.I), "awards & honors"),
    (re.compile(r"\b(?:rotten\s+tomatoes|tomatometer|popcornmeter|metacritic)\b", re.I), "critic & fan scores"),
    (re.compile(r"\b(?:box\s+office|opening\s+weekend|gross)\b", re.I), "box office performance"),
    (re.compile(r"\b(?:when\s+will\b.*\bbe\s+released|be\s+released|be\s+delayed|premiere|opening\s+date)\b", re.I), "release timeline"),
    (re.compile(r"\b(?:criminally\s+charg\w*|fine[ds]?\b|indict\w*|sue[ds]?\b|lawsuit|prosecut\w*|criminal\s+investigat\w*|regulatory\s+investigat\w*|antitrust|subpoena|testify\s+(?:before|in)|(?:criminal|court|jury|federal|civil)\s+trial)\b", re.I), "legal & enforcement"),
    (re.compile(r"\b(?:outage|ground\s+stop|attributed\s+to|technical\s+failure|system\s+failure|cyberattack|hack)\b", re.I), "outage causes"),
    (re.compile(r"\b(?:sandbox\s+escape|training\s+pause|self-improvement|millennium\s+prize|#1\s+ai|frontier\s+model|humanity.?s\s+last\s+exam|benchmark|agi|superintelligence)\b", re.I), "AI & safety"),
    (re.compile(r"\b(?:earbuds|headphones|clip-on|hardware|wearable|(?:hardware|wearable|ai|consumer)\s+device|smart\s+glasses|headset)\b", re.I), "hardware & devices"),
    (re.compile(r"\b(?:valuation|market\s+cap|ipo|revenue|trillion|billion)\b", re.I), "market valuations"),
    (re.compile(r"\b(?:s&p\s+500|nasdaq|bankrupt\w*|default|acqui\w*|merger|spin[- ]?off|stock\s+split|auditor)\b", re.I), "corporate milestones"),
    (re.compile(r"\b(?:operate\s+in|expand\s+to|service\s+in\s+[A-Z])\b", re.I), "city expansion"),
    (re.compile(r"\b(?:join\s+a\s+new|found\s+a\s+new|resign|step\s+down|removed|removal|oust|ceo|chair|(?:join|leave|sit\s+on|appointed\s+to)\s+(?:the\s+)?board|board\s+of\s+directors)\b", re.I), "career & roles"),
    (re.compile(r"\b(?:halftime\s+show|super\s+bowl|coachella|big\s+game|meet\s+[A-Z]|concert|world\s+tour|eras\s+tour|perform\s+at|public\s+appearance)\b", re.I), "public appearances"),
    (re.compile(r"\b(?:studio\s+album|new\s+album|new\s+song|album\s+release|lead\s+single|billboard\s+(?:hot\s+100|200|chart)|spotify\s+(?:top|chart)|music\s+chart)\b", re.I), "charts & releases"),
    (re.compile(r"\b(?:military\s+action|ground\s+operation|airstrike|air\s+strike|drone\s+strike|missile\s+strike|strike\s+(?:on|against))\b", re.I), "military action"),
    (re.compile(r"\b(?:withdraw\w*|annex\w*|normaliz\w*|ceasefire|truce|peace\s+talks?|diploma\w*)\b", re.I), "borders & diplomacy"),
    (re.compile(r"\b(?:ceasefire|truce|peace\s+talks?|nato\s+summit|peace\s+summit|nuclear\s+(?:deal|test|strike|weapon))\b", re.I), "conflict & talks"),
    (re.compile(r"\b(?:(?:interest|policy|funds)\s+rate|rate\s+(?:cut|hike)|central\s+bank\s+(?:cut|hike|dissent)|bps\b|basis\s+points?|monetary\s+policy)\b", re.I), "policy decisions"),
    (re.compile(r"\b(?:product\s+launch|commercial\s+launch|official\s+trailer|official\s+teaser|box\s+office\s+sequel)\b", re.I), "upcoming launches"),
)

_THEME_SYNONYM_ALTS: dict[str, tuple[str, ...]] = {
    "public insults": ("insult targets", "insult odds"),
    "public praise": ("praise targets", "praise odds"),
    "military action": ("military operations",),
    "market valuations": ("valuation & IPO",),
}


def _short_subject_prefix(family_headline: str | None, max_words: int = 2) -> str:
    raw = re.sub(r"\b(?:Outlook|Timeline|Updates)\b", "", str(family_headline or ""), flags=re.IGNORECASE).strip()
    words = [w for w in raw.split() if w]
    return " ".join(words[:max_words])


def _subject_tokens_from_headline(family_headline: str | None) -> set[str]:
    return {
        t.lower()
        for t in re.findall(r"[A-Za-z0-9]+", str(family_headline or ""))
        if t.lower() not in {"outlook", "timeline", "updates", "markets", "the"}
    }


def _heading_base_key(headline: str, subject_tokens: set[str] | frozenset[str] = frozenset()) -> str:
    """Normalize a section heading after stripping page-subject tokens."""
    toks = [t for t in re.findall(r"[a-z0-9]+", (headline or "").lower()) if t not in subject_tokens]
    return " ".join(toks)


def _derive_single_market_field_headline(
    mkt_name: str,
    subject_tokens: set[str] | frozenset[str] = frozenset(),
    seen_headlines: set[str] | frozenset[str] = frozenset(),
) -> str:
    """Derive a concrete 2–4 word market-naming headline for a single multi-outcome field."""
    raw = str(mkt_name or "").strip()
    seen_low = {s.lower().strip() for s in seen_headlines if s} | _BANNED_SECTION_HEADINGS
    seen_base = {_heading_base_key(s, subject_tokens) for s in seen_headlines if s}

    def _ok(cand: str) -> bool:
        words = [w for w in cand.split() if w]
        low = cand.lower().strip()
        bkey = _heading_base_key(cand, subject_tokens)
        return (
            2 <= len(words) <= 4
            and low not in seen_low
            and not any(b in low for b in _BANNED_SECTION_HEADINGS)
            and (not bkey or bkey not in seen_base)
            and _passes_taste_and_harm(cand)
        )

    cands: list[str] = []
    if ":" in raw:
        rhs = re.sub(r"[?!.]+$", "", raw.split(":", 1)[1]).strip()
        if rhs:
            cands.append(_title_case_phrase(rhs))

    m_which = re.match(
        r"^(?:which|what)\s+([a-z][a-z\s]{1,24}?)\s+(?:will|does|do)\s+(.+?)\s+([a-z]{2,18})(?:\s+(?:in|by|before|during|for)\b|\?|$)",
        raw,
        re.IGNORECASE,
    )
    if m_which:
        noun = m_which.group(1).strip()
        verb = m_which.group(3).strip()
        if verb.lower() not in {"be", "have", "do", "make"}:
            cands.append(_title_case_phrase(f"{noun} to {verb}"))

    m_next = re.match(r"^who\s+will\s+be\s+(?:the\s+)?next\s+(.+?)(?:\?|$)", raw, re.IGNORECASE)
    if m_next:
        role = _BEFORE_DATE_RE.sub("", m_next.group(1)).strip(" ?.,")
        words = role.split()[:3]
        if words:
            cands.append(_title_case_phrase(f"next {' '.join(words)}"))

    m_winner = re.match(r"^who\s+will\s+win\s+(?:the\s+)?(.+?)(?:\s+(?:in|at)\s+20\d{2}|\?|$)", raw, re.IGNORECASE)
    if m_winner:
        prize = _BEFORE_DATE_RE.sub("", m_winner.group(1)).strip(" ?.,")
        words = prize.split()[:4]
        if len(words) >= 2:
            cands.append(_title_case_phrase(" ".join(words)))

    cleaned = _BEFORE_DATE_RE.sub("", raw)
    cleaned = re.sub(r"^(?:will|who\s+will|which|what\s+will|where\s+will|when\s+will)\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+(?:in|for|of)\s+20\d{2}\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[?!.]+$", "", cleaned).strip(" -–—:,")
    words = [w for w in cleaned.split() if w.lower().rstrip("'’s") not in subject_tokens]
    while words and words[0].lower() in {"be", "the", "a", "an", "to"}:
        words = words[1:]
    while words and words[-1].lower() in _DANGLING_HEADLINE_ENDINGS:
        words = words[:-1]
    if 2 <= len(words) <= 4:
        cands.append(_title_case_phrase(" ".join(words)))
    elif len(words) > 4:
        cands.append(_title_case_phrase(" ".join(words[:4])))

    for c in cands:
        if _ok(c):
            return c
    for fallback in ("Contender Odds", "Leading Contenders", "Field Breakdown"):
        if _ok(fallback):
            return fallback
    return "Contender Odds"


def _closing_deadline_dt(market: Mapping[str, Any]) -> datetime | None:
    dt = _parse_iso_dt(market.get("resolution_date") or market.get("close_time"))
    if dt is not None and dt.hour < 6:
        return dt - timedelta(hours=6)
    return dt


def _deadline_fallback_headlines(
    variant: str,
    titles_list: Sequence[str],
    rows_meta: Sequence[Mapping[str, Any]] | None,
    *,
    ref_year: int | None = None,
) -> list[str]:
    """Return 2–4 word headlines that are strictly true for 100% of rows."""
    cands: list[str] = []
    cur_year = ref_year if ref_year is not None else datetime.now(timezone.utc).year
    max_dt: datetime | None = None
    max_days: int | None = None
    all_pcts: list[int] = []
    if rows_meta:
        dts = [r["deadline_dt"] for r in rows_meta if isinstance(r.get("deadline_dt"), datetime)]
        if len(dts) == len(rows_meta) and dts:
            max_dt = max(dts)
        day_vals = [int(r["days"]) for r in rows_meta if r.get("days") is not None]
        if len(day_vals) == len(rows_meta) and day_vals:
            max_days = max(day_vals)
        all_pcts = [int(r["pct"]) for r in rows_meta if r.get("pct") is not None]

    # Low-odds cards always read clearest as "Long Shots" (true for every 1..15% row)
    if variant == "one_in_n" or (all_pcts and len(all_pcts) == len(rows_meta or []) and max(all_pcts) <= 15):
        cands.extend(["Long Shots", "Outside Bets", "Sub-15% Odds"])

    # Concrete shared deadline when every row falls on or before that exact cutoff date
    if max_dt is not None:
        mon_full = (
            "", "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December",
        )[max_dt.month]
        mon_abbr = _MONTH_ABBR[max_dt.month]
        if max_days is not None and max_days <= 7:
            cands.append("Closing This Week")
        if max_dt.year == cur_year and max_dt.month == 11 and max_dt.day == 30:
            cands.append("By November 30")
        elif max_dt.year == cur_year and max_dt.month == 12 and max_dt.day == 31:
            cands.append("By December 31")
            cands.append("Before Year End")
        elif max_days is not None and max_days <= 45 and max_dt.year == cur_year:
            cands.append(f"By {mon_abbr} {max_dt.day}")
            cands.append("Next 45 Days")
        else:
            cands.append(f"Through {mon_abbr} {max_dt.year}")
            cands.append(f"By {mon_full} {max_dt.year}")

    if variant == "countdown" and max_days is not None:
        if max_days <= 7:
            cands.append("Closing This Week")
        elif max_days <= 31:
            cands.append("Closing This Month")
        elif max_days <= 45:
            cands.append("Next 45 Days")

    if variant == "dated_tiles":
        cands.extend(["Active Deadlines", "Dated Outcomes"])
    elif variant == "countdown":
        cands.extend(["Next 45 Days", "Closing Soon", "Active Deadlines"])
    elif variant == "shared_scale":
        cands.extend(["Current Odds", "Open Markets", "Odds Comparison"])
    elif variant == "scoreboard_grid":
        cands.extend(["Contender Odds", "Active Markets"])
    else:
        cands.extend(["Open Markets", "Active Odds", "Current Races"])
    return cands


def _derive_section_headline(
    variant: str,
    titles: Sequence[str],
    family_headline: str | None = None,
    seen_headlines: set[str] | frozenset[str] = frozenset(),
    *,
    allow_subject_only: bool = False,
    subject_tokens: set[str] | frozenset[str] | None = None,
    rows_meta: Sequence[Mapping[str, Any]] | None = None,
) -> str:
    """Derive a 2–4 word section heading that is strictly true of EVERY row and unique after stripping subject."""
    eff_subj = set(subject_tokens) if subject_tokens is not None else _subject_tokens_from_headline(family_headline)
    seen_low = {s.lower().strip() for s in seen_headlines if s} | _BANNED_SECTION_HEADINGS
    seen_base = {_heading_base_key(s, eff_subj) for s in seen_headlines if s}
    subj2 = _short_subject_prefix(family_headline, max_words=2)
    titles_list = [str(t or "").strip() for t in titles if t and str(t).strip()]

    def _valid(cand: str) -> bool:
        words = [w for w in cand.split() if w]
        low = cand.lower().strip()
        bkey = _heading_base_key(cand, eff_subj)
        return (
            2 <= len(words) <= 4
            and low not in seen_low
            and not any(banned in low for banned in _BANNED_SECTION_HEADINGS)
            and (not bkey or bkey not in seen_base)
            and _passes_taste_and_harm(cand)
        )

    # 1. Domain/predicate theme: ONLY eligible when 100% of rows in the section match `pat`.
    if titles_list:
        matched_themes: list[tuple[int, str]] = []
        for idx, (pat, label) in enumerate(_SECTION_THEME_PATTERNS):
            if all(pat.search(t) for t in titles_list):
                matched_themes.append((idx, label))
        for _idx, label in matched_themes:
            candidates = []
            if label == "approval rating":
                ref_y = datetime.now(timezone.utc).year
                parsed_dates = [
                    _parse_date_marker(t, default_year=ref_y) for t in titles_list
                ]
                if parsed_dates and all(p is not None for p in parsed_dates):
                    unique_md = {
                        (p["sort_dt"].month, p["sort_dt"].day)
                        for p in parsed_dates
                        if p is not None
                    }
                    if len(unique_md) == 1:
                        mo, dy = next(iter(unique_md))
                        candidates.append(f"{_MONTH_ABBR[mo]} {dy} Approval Rating")
            candidates.append(_title_case_phrase(label))
            candidates.extend(_title_case_phrase(alt) for alt in _THEME_SYNONYM_ALTS.get(label, ()))
            for cand in candidates:
                if _valid(cand):
                    return cand

    # 2. Common multi-word tokens shared by 100% of section rows (no entity prefixing).
    hl, err = derive_common_headline(None, titles_list)
    if (
        not err
        and hl
        and not hl.lower().endswith(" outlook")
        and not re.search(r"\b(?:will|would|does|did)\b", hl, re.IGNORECASE)
        and hl.split()[-1].lower().strip("?!.,") not in _DANGLING_HEADLINE_ENDINGS
        and _valid(hl)
    ):
        sig_hl = [
            w.lower() for w in hl.split()
            if len(w) > 2 and w.lower() not in _GENERIC_STOPWORDS and w.lower() not in eff_subj
        ]
        titles_low = [t.lower() for t in titles_list]
        all_shared = bool(titles_low) and len(sig_hl) >= 2 and all(
            all(tok in tl for tl in titles_low)
            for tok in sig_hl
        )
        if all_shared and (allow_subject_only or hl.lower() != (subj2 or "").lower()):
            return hl

    # 3. 100%-true common-property / variant factual fallbacks (never glue subject names onto headings).
    for cand in _deadline_fallback_headlines(variant, titles_list, rows_meta):
        if _valid(cand):
            return cand

    return "Long Shots" if variant == "one_in_n" else "Open Markets"


def _caption_for_row(label: str, clause: str) -> str:
    """Format a grammatical stat caption that handles both yes/no questions and noun phrases (#13696 Point 3)."""
    cleaned = re.sub(r"[.!]+$", "", (label or "").strip())
    if not cleaned:
        return clause[:1].upper() + clause[1:]
    verb_phrase = clause
    if _INTERROGATIVE_START_RE.match(cleaned):
        q = cleaned if cleaned.endswith("?") else f"{cleaned}?"
        # Avoid "sits at" / "leads at" on full quoted question -> natural English "stands at" / existing verb
        verb_phrase = re.sub(r"^sits at\b", "stands at", verb_phrase)
        return f'"{q}" {verb_phrase}'
    return f"{cleaned} {verb_phrase}"


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


def _parse_date_marker(
    title: str,
    default_year: int,
    *,
    default_day_prep: str = "by",
) -> dict[str, Any] | None:
    """Extract embedded target date, preserving 'Before X' and 'on <day>' verbatim (#13696 Point 3)."""
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
        max_day = calendar.monthrange(year, mon_num)[1]
        day = min(max_day, int(day_tok)) if day_tok else max_day
        try:
            sort_dt = datetime(year, mon_num, day, tzinfo=timezone.utc)
        except ValueError:
            continue

        mon_str = _MONTH_ABBR[mon_num]
        yr_short = f"'{year % 100:02d}"
        prep_low = prefix_raw.lower()
        is_before = prep_low.startswith("before")
        is_on = prep_low.startswith("on")
        is_by = prep_low.startswith("by")
        day_prep = "before" if is_before else ("on" if is_on else ("by" if is_by else default_day_prep))
        if day_tok:
            prefix = "Before " if day_prep == "before" else ("on " if day_prep == "on" else "by ")
            period = f"{prefix}{mon_str} {int(day_tok)} {yr_short}".strip()
            phrase = f"{day_prep} {mon_str} {int(day_tok)}, {year}".strip()
        else:
            prefix = "Before " if is_before else ("by " if is_by else "")
            period = f"{prefix}{mon_str} {yr_short}".strip()
            phrase = f"{'before' if is_before else ('by' if is_by else 'in')} {mon_str} {year}".strip()

        raw_stem = (title[: m.start()] + title[m.end() :]).strip()
        raw_stem = re.sub(r"[?!.,'\s]+$", "", raw_stem).strip()
        raw_stem = re.sub(r"\s+(?:on|at|in|by|before)$", "", raw_stem, flags=re.IGNORECASE).strip()
        had_q = (title or "").strip().endswith("?")
        display_stem = raw_stem or (title or "").strip()
        if _INTERROGATIVE_START_RE.match(display_stem) and had_q and not display_stem.endswith("?"):
            display_stem = f"{display_stem}?"
        stem = re.sub(r"^(?:Will\s+)", "", raw_stem, flags=re.IGNORECASE).strip()
        norm_stem = re.sub(r"[^a-z0-9]+", " ", stem.lower()).strip()
        return {
            "period": period,
            "phrase": phrase,
            "sort_dt": sort_dt,
            "has_day": bool(day_tok),
            "stem": stem or title,
            "display_stem": display_stem,
            "norm_stem": norm_stem,
        }
    return None


def _short_label(text: str, limit: int = 80) -> str:
    """Return a clean full-text label preserving trailing '?' on questions, zero ellipsis."""
    stripped = (text or "").strip()
    keep_q = stripped.endswith("?")
    txt = re.sub(r"\s+", " ", re.sub(r"[?!\s]+$", "", stripped))
    if keep_q and _INTERROGATIVE_START_RE.match(txt) and not txt.endswith("?"):
        txt = f"{txt}?"
    return txt


def _distinguishing_row_label(title: str, all_titles: Sequence[str], *, max_len: int = 80) -> str:
    """Extract a readable distinguishing phrase without stranding bare infinitives (#13696 Point 3)."""
    orig = (title or "").strip()
    cleaned = _DANGLING_TRAILING_PREP_RE.sub("", re.sub(r"[?!.]+$", "", orig)).strip()
    if len(all_titles) < 2:
        keep_full = orig if orig.endswith("?") and _INTERROGATIVE_START_RE.match(orig) else cleaned
        return _short_label(keep_full, max_len)
    split_lists = [
        _DANGLING_TRAILING_PREP_RE.sub("", re.sub(r"[?!.]+$", "", t).strip()).strip().split()
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
    while len(diff_tokens) == 1 and re.fullmatch(r"\$?[0-9.,]+[%KMBQT+]*", diff_tokens[0], re.IGNORECASE) and prefix_len > 0:
        prefix_len -= 1
        diff_tokens = tokens[prefix_len:end_idx]
    while diff_tokens and diff_tokens[0].lower().strip("?!.,") in _DANGLING_ROW_STARTERS and prefix_len > 0:
        lead_low = diff_tokens[0].lower().strip("?!.,")
        prev_low = tokens[prefix_len - 1].lower().strip("?!.,")
        prefix_len -= 1
        diff_tokens = tokens[prefix_len:end_idx]
        if lead_low in {"least", "most"} and prev_low == "at":
            break

    # Point 3: never strip leading subject / "Will" into ungrammatical verb fragments
    # (e.g. "Criminally charges...", "6500 measles cases in the U.S. in") unless reducing cleanly to a compact value/threshold.
    joined_diff = " ".join(diff_tokens)
    is_pure_value = bool(
        len(diff_tokens) <= 4
        and re.fullmatch(
            r"(?:(?:at\s+(?:least|most)|over|under|above|below|more\s+than|less\s+than|up\s+to)\s+)?(?:\$?[0-9.,]+[%KMBQT+]*)(?:\s*[-–]\s*\$?[0-9.,]+[%KMBQT+]*)?",
            joined_diff,
            re.IGNORECASE,
        )
    )
    if prefix_len > 0 and diff_tokens and not is_pure_value:
        if (tokens and tokens[0].lower() in {"will", "does", "do", "did", "can", "could", "is", "are"}) or diff_tokens[0][0].islower():
            return _short_label(orig if orig.endswith("?") else cleaned, max_len)

    if prefix_len == 0 and len(diff_tokens) >= 4 and diff_tokens[0].lower() in {"is", "are"}:
        diff_tokens = diff_tokens[1:]
    diff = _DANGLING_TRAILING_PREP_RE.sub("", " ".join(diff_tokens)).strip(" -–—:,")
    if not diff:
        diff = orig if orig.endswith("?") and _INTERROGATIVE_START_RE.match(orig) else cleaned
    if diff and diff[0].islower():
        diff = diff[0].upper() + diff[1:]
    if prefix_len == 0 and orig.endswith("?") and _INTERROGATIVE_START_RE.match(diff) and not diff.endswith("?"):
        diff = f"{diff}?"
    return _short_label(diff, max_len)


def _dedupe_by_rendered_label(
    ordered_markets: Sequence[Mapping[str, Any]],
    *,
    limit: int,
    max_len: int = 80,
) -> tuple[list[tuple[Mapping[str, Any], str]], list[Mapping[str, Any]]]:
    """Select up to ``limit`` rows with unique rendered labels while returning all checked twins."""
    all_titles = [str(m.get("name") or "") for m in ordered_markets[:limit]]
    selected: list[tuple[Mapping[str, Any], str]] = []
    consumed: list[Mapping[str, Any]] = []
    seen_labels: set[str] = set()
    for m in ordered_markets:
        raw_title = str(m.get("name") or "")
        label = _distinguishing_row_label(raw_title, all_titles, max_len=max_len)
        lkey = re.sub(r"^(?:will|does|do)\s+", "", label.lower().strip()).rstrip("?.!")
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
        r"\bin\s+[A-Z][a-zA-Z.,'-]+(?:\s+[A-Z][a-zA-Z.,'-]+){0,3}(?=\s+(?:\{d\}|before|by|\?|$))",
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
    """Mark picked markets AND sibling twins/same-group children as consumed."""
    sigs = {_template_signature(m) for m in picked_markets}
    qkeys = {
        _normalize_question_key(str(m.get("name") or m.get("title") or ""))
        for m in picked_markets
        if str(m.get("name") or m.get("title") or "").strip()
    }
    def_y = datetime.now(timezone.utc).year
    canon_keys = {
        _canonical_question_and_deadline(
            str(m.get("name") or m.get("title") or ""),
            def_y,
        )
        for m in picked_markets
        if _is_binary_market(m) and str(m.get("name") or m.get("title") or "").strip()
    }
    canon_keys = {k for k in canon_keys if k[0] and k[1]}
    multi_gid_outcomes: dict[str, set[str]] = defaultdict(set)
    for m in picked_markets:
        if m.get("id") is not None:
            used_ids.add(int(m["id"]))
        gid = str(m.get("group_id") or "").strip()
        if gid and not _is_binary_market(m):
            for o in _sorted_outcomes(m):
                oname = _norm_outcome_phrase(str(o.get("name") or ""))
                if len(oname) >= 3:
                    multi_gid_outcomes[gid].add(oname)

    for m in all_markets:
        mid = m.get("id")
        if mid is None:
            continue
        raw_nm = str(m.get("name") or m.get("title") or "")
        qkey = _normalize_question_key(raw_nm)
        ckey = (
            _canonical_question_and_deadline(raw_nm, def_y)
            if _is_binary_market(m) and canon_keys
            else ("", None)
        )
        gid = str(m.get("group_id") or "").strip()
        if (
            _template_signature(m) in sigs
            or (qkey and qkey in qkeys)
            or (ckey[0] and ckey[1] and ckey in canon_keys)
            or (gid in multi_gid_outcomes and _binary_matches_multi_parent(m, multi_gid_outcomes[gid]))
        ):
            used_ids.add(int(mid))


_LOWER_BOUND_THRESHOLD_RE = re.compile(
    r"(?:\bbelow\b|\bunder\b|\bat\s+or\s+below\b|\bor\s+lower\b|\bless\s+than\b|"
    r"\bat\s+most\b|\bno\s+more\s+than\b|\(low\)|\bdip\b|\bfall\s+to\b|\btop\s+\d+|<=|<)",
    re.IGNORECASE,
)
_INDEX_OR_ORDINAL_MASK_RE = re.compile(
    r"(?:\bnasdaq[-\s]*100\b|\bs&p\s*500\b|\bfortune\s*500\b|\b\d+(?:st|nd|rd|th)\b|(?<!\w)#\d+\b|"
    r"\b(?:g7|g20|f1)\b|\b(?:in|of|for|by|before|until|through|on)\s+20\d{2}\b)",
    re.IGNORECASE,
)
_THRESHOLD_NUM_RE = re.compile(
    r"(?<![#\w])(\$?\s*\d+(?:,\d+)*(?:\.\d+)?\s*(?:trillion|billion|million|thousand|[tbmk])?%?\+?)(?![a-z0-9_])",
    re.IGNORECASE,
)
_UNIT_MULT = {
    "t": 1e12,
    "trillion": 1e12,
    "b": 1e9,
    "billion": 1e9,
    "m": 1e6,
    "million": 1e6,
    "k": 1e3,
    "thousand": 1e3,
}


def _extract_threshold_rung(
    text: str,
    *,
    strip_dates: bool = True,
) -> tuple[str, int, float] | None:
    """Extract (normalized_stem_with_{n}, polarity, hardness) if text has one numeric rung."""
    s = (text or "").lower().strip()
    if not s or re.search(r"\bbetween\s+\$?\d+(?:,\d+)*(?:\.\d+)?\s+and\s+\$?\d+", s):
        return None
    if strip_dates:
        s = _BEFORE_DATE_RE.sub(" {d} ", s)
    s = _INDEX_OR_ORDINAL_MASK_RE.sub(" {idx} ", s)

    matches = list(_THRESHOLD_NUM_RE.finditer(s))
    candidates: list[tuple[re.Match[str], float]] = []
    for m in matches:
        raw_tok = m.group(1).strip()
        num_m = re.match(
            r"^\$?\s*(\d+(?:,\d+)*(?:\.\d+)?)\s*(trillion|billion|million|thousand|[tbmk])?%?\+?$",
            raw_tok,
            re.IGNORECASE,
        )
        if not num_m:
            continue
        base_num = float(num_m.group(1).replace(",", ""))
        unit = (num_m.group(2) or "").lower()
        # Skip bare 4-digit years like 2026/2027 without $, %, +, or scale unit
        if (
            not raw_tok.startswith("$")
            and not unit
            and not raw_tok.endswith(("%", "+"))
            and 1990 <= base_num <= 2039
            and base_num == int(base_num)
        ):
            continue
        val = base_num * _UNIT_MULT.get(unit, 1.0)
        candidates.append((m, val))

    if len(candidates) != 1:
        return None

    tok_m, val = candidates[0]
    polarity = -1 if _LOWER_BOUND_THRESHOLD_RE.search(s) else 1
    stem = s[: tok_m.start()] + "{n}" + s[tok_m.end():]
    stem = _normalize_question_key(stem.replace("{n}", " __rung_placeholder__ ")).replace(
        "__rung_placeholder__", "{n}"
    )
    return (stem, polarity, float(polarity) * val)


def _drop_inverted_threshold_rows(
    entries: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Drop rows from any threshold family where a stricter rung reads higher than a looser rung."""
    items = [dict(e) for e in entries]
    rungs: dict[int, tuple[str, int, float]] = {}
    by_family: dict[tuple[str, int], list[int]] = defaultdict(list)
    for idx, entry in enumerate(items):
        rung = _extract_threshold_rung(str(entry.get("rung_text") or entry.get("label") or ""))
        if rung is not None:
            rungs[idx] = rung
            by_family[(rung[0], rung[1])].append(idx)

    dropped: set[int] = set()
    for idxs in by_family.values():
        active = [i for i in idxs if i not in dropped]
        while len(active) >= 2:
            conflicts: dict[int, int] = defaultdict(int)
            for p_idx, a in enumerate(active):
                for b in active[p_idx + 1:]:
                    ha = rungs[a][2]
                    hb = rungs[b][2]
                    if ha == hb:
                        continue
                    stricter, looser = (a, b) if ha > hb else (b, a)
                    p_str = items[stricter].get("pct_by_col") or {}
                    p_loo = items[looser].get("pct_by_col") or {}
                    shared_cols = [k for k in p_str if k in p_loo]
                    if any(int(p_str[k]) > int(p_loo[k]) for k in shared_cols):
                        conflicts[stricter] += 1
                        conflicts[looser] += 1
            if not conflicts:
                break
            # Drop the single weakest row among conflicting nodes (most conflicts, lowest consensus, highest hardness)
            victim = min(
                conflicts.keys(),
                key=lambda i: (
                    -conflicts[i],
                    items[i].get("consensus_key") or (0, 0),
                    -rungs[i][2],
                    i,
                ),
            )
            dropped.add(victim)
            active = [i for i in active if i != victim]

    return [entry for idx, entry in enumerate(items) if idx not in dropped]


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
    hl = str(card.get("common_headline") or "").strip()
    if not (2 <= len(hl.split()) <= 4):
        return None
    if hl.lower() in _BANNED_SECTION_HEADINGS or any(b in hl.lower() for b in _BANNED_SECTION_HEADINGS):
        return None
    if not _passes_taste_and_harm(hl, card.get("stat_caption")):
        return None
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
    family_headline: str | None = None,
    seen_headlines: set[str] | frozenset[str] = frozenset(),
    subject_tokens: set[str] | frozenset[str] | None = None,
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

    # Sort dated rows chronologically (earliest -> latest) and keep explicit 'YY year (#13696 Point 5).
    dated_markers: dict[int, dict[str, Any]] = {}
    for m, _ in chosen_group:
        parsed_dt = _parse_date_marker(str(m.get("name") or ""), default_year=ref_year)
        if parsed_dt is not None:
            dated_markers[int(m["id"])] = parsed_dt
    if len(dated_markers) >= 2:
        chosen_group = sorted(
            chosen_group,
            key=lambda pair: (
                dated_markers[int(pair[0]["id"])]["sort_dt"]
                if int(pair[0]["id"]) in dated_markers
                else datetime.max.replace(tzinfo=timezone.utc),
                int(pair[0]["id"]),
            ),
        )

    columns = [
        {"key": f"col_{i}_{_slugify(c)[:16]}", "label": _short_label(c, 56)}
        for i, c in enumerate(col_names_raw)
    ]
    all_titles = [str(m.get("name") or "") for m, _ in chosen_group]
    # Format rows: normalize dates when >= 2 rows are dated deadlines; keep uniform Deadline header (#13696 Point 3).
    all_titles = [str(m.get("name") or "") for m, _ in chosen_group]
    all_dated = len(dated_markers) == len(chosen_group) and len(dated_markers) >= 2
    eff_subj = set(subject_tokens) if subject_tokens is not None else _subject_tokens_from_headline(family_headline)

    # Derive a market-specific headline before falling back to generic "Contender Odds".
    scoreboard_hl: str | None = None
    seen_low = {s.lower().strip() for s in seen_headlines if s} | _BANNED_SECTION_HEADINGS
    seen_base = {_heading_base_key(s, eff_subj) for s in seen_headlines if s}

    def _sb_ok(cand: str) -> bool:
        words = [w for w in cand.split() if w]
        low = cand.lower().strip()
        bkey = _heading_base_key(cand, eff_subj)
        return (
            2 <= len(words) <= 4
            and low not in seen_low
            and not any(banned in low for banned in _BANNED_SECTION_HEADINGS)
            and (not bkey or bkey not in seen_base)
            and _passes_taste_and_harm(cand)
        )

    cleaned_sb = [
        _BEFORE_DATE_RE.sub(
            "",
            re.sub(
                r"^(?:Will|Which|What|Who)\s+",
                "",
                re.sub(r"[?!.:]+$", "", str(t or "")).strip(),
                flags=re.IGNORECASE,
            ),
        ).strip()
        for t in all_titles
        if t
    ]
    hl_direct, err_direct = derive_common_headline(None, cleaned_sb)
    if not err_direct and hl_direct and not hl_direct.lower().endswith(" outlook") and _sb_ok(hl_direct):
        scoreboard_hl = hl_direct
    if scoreboard_hl is None:
        # Stem-normalized common content tokens (e.g. capture/captures/captured + city/cities -> Cities Russia Captures).
        tok_sets = [
            [
                w.rstrip("s") if len(w) > 4 else w
                for w in re.findall(r"[a-z]+", c.lower())
                if w not in _GENERIC_STOPWORDS and len(w) > 2
            ]
            for c in cleaned_sb
            if c
        ]
        if tok_sets:
            common_order = []
            for tok in tok_sets[0]:
                if tok not in common_order and all(
                    any(t.startswith(tok[:5]) if len(tok) >= 5 else t == tok for t in ts)
                    for ts in tok_sets[1:]
                ):
                    common_order.append(tok)
            if 2 <= len(common_order) <= 4:
                cand_sb = _title_case_phrase(" ".join(common_order))
                if _sb_ok(cand_sb):
                    scoreboard_hl = cand_sb

    headline = scoreboard_hl or _derive_section_headline(
        "scoreboard_grid",
        all_titles,
        family_headline,
        seen_headlines,
        subject_tokens=eff_subj,
    )

    rows: list[dict[str, Any]] = []
    lead_caption = None
    best_pct = -1

    for m, outs in chosen_group:
        mid = int(m["id"])
        by_name = {
            o["name"].lower().strip(): (float(o["prob"]), o.get("id"), int(o["rendered_percent"]))
            for o in outs
        }
        dm = dated_markers.get(mid)
        if all_dated and dm is not None:
            dt = dm["sort_dt"]
            phrase_low = str(dm.get("phrase") or "").lower()
            prep_word = "Before" if phrase_low.startswith("before") else ("On" if phrase_low.startswith("on") else ("In" if phrase_low.startswith("in") else "By"))
            if dm.get("has_day"):
                row_label = f"{prep_word} {_MONTH_ABBR[dt.month]} {dt.day}, {dt.year}"
            else:
                row_label = f"{prep_word} {_MONTH_ABBR[dt.month]} {dt.year}"
        else:
            row_label = _distinguishing_row_label(str(m.get("name") or ""), all_titles, max_len=80)
            if dm is not None:
                yr_tok = f"'{dm['sort_dt'].year % 100:02d}"
                yr_full = str(dm["sort_dt"].year)
                if yr_tok not in row_label and yr_full not in row_label:
                    row_label = f"{row_label} {yr_tok}".strip()
        cells: list[dict[str, Any]] = []
        row_probs = [by_name.get(cname.lower().strip(), (0.0, None, 0))[0] for cname in col_names_raw]
        row_max = max(row_probs) if row_probs else 0.0
        for col, cname in zip(columns, col_names_raw):
            clow = cname.lower().strip()
            if clow in by_name:
                prob, oid, pct = by_name[clow]
                pct_str = _pct_display(prob, pct)
                is_best_in_row = prob > 0 and prob >= row_max - 1e-6 and pct >= 20
                cells.append({
                    "column_key": col["key"],
                    "provenance": {"market_id": mid, "outcome_id": oid},
                    "marks": [_mark_tile(
                        shade=max(0.02, min(1.0, prob)),
                        center_label=pct_str,
                        muted=not is_best_in_row,
                        highlight_role="leader" if is_best_in_row else None,
                    )],
                })
                if pct > best_pct:
                    best_pct = pct
                    if all_dated:
                        lead_caption = f"{cname} is highest for {headline.lower()} ({row_label}) at {pct_str}"
                    elif _INTERROGATIVE_START_RE.match(row_label):
                        lead_caption = f'{cname} leads on "{row_label}" at {pct_str}'
                    else:
                        lead_caption = f"{cname} leads {row_label} at {pct_str}"
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
            "id": f"{slug}-sb-{mid}",
            "leading": [_mark_word(row_label, style="row", tone="primary", align="left", width="flex", bold=True)],
            "cells": cells,
        })

    src_count = max(_sources_count(m) for m, _ in chosen_group)
    card = _finalize_section(_make_kit_card(
        card_id=f"{slug}-scoreboard",
        layout="grid",
        variant="scoreboard_grid",
        kicker=f"{kicker} · OUTCOMES",
        common_headline=headline,
        stat_caption=lead_caption or f"Compared across {len(rows)} markets",
        source_count=src_count,
        route_slug=slug,
        body={
            "leading_label": "Deadline" if all_dated else "Market",
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


_SINGLE_DAY_EVENT_RE = re.compile(
    r"\b(?:on\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)|military\s+action|airstrike|ground\s+operation|strike\s+on|visit\s+|meet\s+)\b",
    re.IGNORECASE,
)


def _infer_binary_default_prep(title_str: str) -> str:
    if re.search(r"\b(?:by|before|until|through)\b", title_str, re.I):
        return "by"
    if re.search(r"\b(?:withdraw\w*|resign\w*|impeach\w*|oust\w*|removed|step\s+down|out\s+as|join\s+|ipo\b)\b", title_str, re.I):
        return "by"
    if re.search(r"\b(?:Dec(?:ember)?\s+31|Mar(?:ch)?\s+31|Jun(?:e)?\s+30|Sep(?:tember)?\s+30)\b", title_str, re.I) and not re.search(r"\bon\s+", title_str, re.I):
        return "by"
    return "on"


def _build_dated_tiles_section(
    slug: str,
    kicker: str,
    markets: Sequence[Mapping[str, Any]],
    used_ids: set[int],
    *,
    now: datetime,
    family_headline: str | None = None,
    seen_headlines: set[str] | frozenset[str] = frozenset(),
    subject_tokens: set[str] | frozenset[str] | None = None,
) -> dict[str, Any] | None:
    """Grid section for binary or multi-outcome open-future date ladders (Condition 5 strict)."""
    today_d = now.date()
    by_stem: dict[str, list[tuple[Mapping[str, Any], dict[str, Any]]]] = defaultdict(list)
    for m in markets:
        mid = int(m["id"])
        if mid in used_ids or not _is_binary_market(m):
            continue
        title_str = str(m.get("name") or "")
        default_prep = _infer_binary_default_prep(title_str)
        parsed = _parse_date_marker(title_str, default_year=now.year, default_day_prep=default_prep)
        if not parsed or len(parsed["norm_stem"]) < 4:
            continue
        if parsed["sort_dt"].date() < today_d:
            continue
        stem_qkey = _normalize_question_key(parsed.get("display_stem") or parsed["stem"]) or parsed["norm_stem"]
        by_stem[stem_qkey].append((m, parsed))

    binary_ladders = [grp for grp in by_stem.values() if len({p["period"] for _, p in grp}) >= 2]
    binary_ladders.sort(key=lambda g: (-len(g), min(p["sort_dt"] for _, p in g)))

    # Multi-outcome date-rung markets ("Event by...?" with strictly open future date outcomes)
    multi_date_entries: list[tuple[Mapping[str, Any], list[tuple[dict[str, Any], float, int | None, int]]]] = []
    for m in markets:
        mid = int(m["id"])
        if mid in used_ids or _is_binary_market(m):
            continue
        res_dt = _parse_iso_dt(m.get("resolution_date") or m.get("close_time"))
        m_title = str(m.get("name") or "")
        parent_prep = "on" if (re.search(r"\bon\b", m_title, re.I) and not re.search(r"\b(?:by|before|until)\b", m_title, re.I)) else "by"
        parsed_rungs: dict[str, tuple[dict[str, Any], float, int | None, int]] = {}
        for o in _sorted_outcomes(m):
            p = _parse_date_marker(o["name"], default_year=now.year, default_day_prep=parent_prep)
            if p is None:
                continue
            # If month-day wrapped into next year per resolution_date, resolve cleanly preserving preposition
            if p["sort_dt"].date() < today_d and res_dt is not None and res_dt.year > now.year:
                max_wrap_day = calendar.monthrange(res_dt.year, p["sort_dt"].month)[1]
                cand_dt = datetime(
                    res_dt.year,
                    p["sort_dt"].month,
                    min(max_wrap_day, p["sort_dt"].day),
                    tzinfo=timezone.utc,
                )
                if cand_dt <= res_dt + timedelta(days=35) and cand_dt.date() >= today_d:
                    mon_str = _MONTH_ABBR[cand_dt.month]
                    yr_short = f"'{cand_dt.year % 100:02d}"
                    old_prep = p["phrase"].split()[0].lower() if p.get("phrase") else parent_prep
                    new_prefix = "Before " if p["period"].lower().startswith("before") else ("on " if old_prep == "on" else "by ")
                    p = {
                        **p,
                        "sort_dt": cand_dt,
                        "period": f"{new_prefix}{mon_str} {cand_dt.day} {yr_short}".strip(),
                        "phrase": f"{old_prep} {mon_str} {cand_dt.day}, {cand_dt.year}",
                    }
            if p["sort_dt"].date() < today_d:
                continue
            parsed_rungs[p["period"]] = (p, float(o["prob"]), o.get("id"), int(o["rendered_percent"]))
        if len(parsed_rungs) >= 2:
            ordered_rungs = sorted(parsed_rungs.values(), key=lambda x: (x[0]["sort_dt"], x[0]["period"]))
            multi_date_entries.append((m, ordered_rungs))
    multi_date_entries.sort(key=lambda x: (-len(x[1]), int(x[0]["id"])))

    if not binary_ladders and not multi_date_entries:
        return None

    def _norm_stem_key(txt: str) -> str:
        return _normalize_question_key(txt)

    candidate_entries: list[dict[str, Any]] = []
    seen_norm_stems: set[str] = set()

    for ladder in binary_ladders[:8]:
        ranked_ladder = sorted(
            ladder,
            key=lambda mp: (
                -_sources_count(mp[0]),
                -int(mp[0].get("volume_24h") or 0),
                int(mp[0].get("id") or 0),
            ),
        )
        by_period: dict[str, tuple[Mapping[str, Any], dict[str, Any]]] = {}
        for m, p in ranked_ladder:
            key = p["period"]
            if key not in by_period:
                by_period[key] = (m, p)
        ordered = sorted(by_period.values(), key=lambda mp: (mp[1]["sort_dt"], mp[1]["period"]))
        if len(ordered) > 3:
            ordered = [ordered[0], ordered[len(ordered) // 2], ordered[-1]]
        best_title = ranked_ladder[0][1].get("display_stem") or ordered[0][1].get("display_stem") or ordered[0][1]["stem"]
        stem_title = _short_label(best_title, 80)
        stem_key = _norm_stem_key(stem_title)
        if stem_key in seen_norm_stems:
            continue
        seen_norm_stems.add(stem_key)

        fracs_oids = [_top_outcome_cell(m) for m, _ in ordered]
        probs = [pct for _, _, pct in fracs_oids]
        peak_pct = max(probs) if probs else 0
        pct_by_period = {p["period"]: pct for (_, p), (_, _, pct) in zip(ordered, fracs_oids)}
        max_src = max(_sources_count(m) for m, _ in ordered)
        max_vol = max(int(m.get("volume_24h") or 0) for m, _ in ordered)

        cells: list[dict[str, Any]] = []
        best_row_frac = -1.0
        row_lead_caption = None
        for idx_c, ((m, p), (frac, oid, pct)) in enumerate(zip(ordered, fracs_oids)):
            pct_str = _pct_display(frac, pct)
            is_accent = pct > 0 and pct >= max(10, peak_pct - 10)
            cells.append({
                "column_key": f"d_{idx_c}",
                "provenance": {"market_id": int(m["id"]), "outcome_id": oid},
                "marks": [_mark_tile(
                    shade=max(0.02, frac),
                    top_label=p["period"],
                    center_label=pct_str,
                    muted=not is_accent,
                    highlight_role="peak" if pct == peak_pct and peak_pct > 0 else None,
                )],
            })
            if frac > best_row_frac or (frac == best_row_frac and idx_c == len(ordered) - 1):
                best_row_frac = frac
                row_lead_caption = _caption_for_row(stem_title, f"sits at {pct_str} {p['phrase']}")

        candidate_entries.append({
            "kind": "binary",
            "row": {
                "id": f"{slug}-dt-{ordered[0][0]['id']}",
                "leading": [_mark_word(stem_title, style="row", tone="primary", align="left", width="flex", bold=True)],
                "cells": cells,
            },
            "stem_title": stem_title,
            "rung_text": stem_title,
            "pct_by_col": pct_by_period,
            "consensus_key": (max_src, max_vol),
            "picked": [m for m, _ in ordered],
            "consume": [m for m, _ in ladder],
            "num_cols": len(ordered),
            "best_frac": best_row_frac,
            "lead_caption": row_lead_caption,
            "deadline_dt": max(p["sort_dt"] for _, p in ordered),
            "peak_pct": peak_pct,
        })

    for m, rungs in multi_date_entries[:4]:
        stem_title = _short_label(re.sub(r"\s+(?:by|before)\.\.\.\??$", "", str(m.get("name") or "")), 80)
        stem_key = _norm_stem_key(stem_title)
        if stem_key in seen_norm_stems:
            continue
        seen_norm_stems.add(stem_key)
        ordered_r = rungs
        if len(ordered_r) > 3:
            ordered_r = [ordered_r[0], ordered_r[len(ordered_r) // 2], ordered_r[-1]]
        r_pcts = [pct for _, _, _, pct in ordered_r]
        peak_pct = max(r_pcts) if r_pcts else 0
        pct_by_period = {p["period"]: pct for p, _, _, pct in ordered_r}
        cells = []
        best_row_frac = -1.0
        row_lead_caption = None
        for idx_c, (p, frac, oid, pct) in enumerate(ordered_r):
            pct_str = _pct_display(frac, pct)
            is_accent = pct > 0 and pct >= max(10, peak_pct - 10)
            cells.append({
                "column_key": f"d_{idx_c}",
                "provenance": {"market_id": int(m["id"]), "outcome_id": oid},
                "marks": [_mark_tile(
                    shade=max(0.02, frac),
                    top_label=p["period"],
                    center_label=pct_str,
                    muted=not is_accent,
                    highlight_role="peak" if pct == peak_pct and peak_pct > 0 else None,
                )],
            })
            if frac > best_row_frac or (frac == best_row_frac and idx_c == len(ordered_r) - 1):
                best_row_frac = frac
                row_lead_caption = _caption_for_row(stem_title, f"sits at {pct_str} {p['phrase']}")

        candidate_entries.append({
            "kind": "multi",
            "row": {
                "id": f"{slug}-dtm-{m['id']}",
                "leading": [_mark_word(stem_title, style="row", tone="primary", align="left", width="flex", bold=True)],
                "cells": cells,
            },
            "stem_title": stem_title,
            "rung_text": stem_title,
            "pct_by_col": pct_by_period,
            "consensus_key": (_sources_count(m), int(m.get("volume_24h") or 0)),
            "picked": [m],
            "num_cols": len(ordered_r),
            "best_frac": best_row_frac,
            "lead_caption": row_lead_caption,
            "deadline_dt": max(p["sort_dt"] for p, _, _, _ in ordered_r),
            "peak_pct": peak_pct,
        })

    # Drop any inverted threshold rungs (e.g. $1.5T > $1.4T) before choosing the top 3 rows.
    monotonic_entries = _drop_inverted_threshold_rows(candidate_entries)[:3]
    if not monotonic_entries:
        return None

    rows: list[dict[str, Any]] = []
    picked_markets: list[Mapping[str, Any]] = []
    consume_markets: list[Mapping[str, Any]] = []
    all_titles: list[str] = []
    rows_meta: list[dict[str, Any]] = []
    max_cols = 0
    best_lead_frac = -1.0
    lead_caption = None
    for entry in monotonic_entries:
        rows.append(entry["row"])
        picked_markets.extend(entry["picked"])
        consume_markets.extend(entry.get("consume") or entry["picked"])
        all_titles.append(entry["stem_title"])
        rows_meta.append({"deadline_dt": entry["deadline_dt"], "pct": entry["peak_pct"]})
        max_cols = max(max_cols, int(entry["num_cols"]))
        if entry["best_frac"] >= best_lead_frac:
            best_lead_frac = entry["best_frac"]
            lead_caption = entry["lead_caption"]

    columns = [{"key": f"d_{i}", "label": f"Date {i + 1}"} for i in range(max_cols)]
    headline = _derive_section_headline(
        "dated_tiles",
        all_titles,
        family_headline,
        seen_headlines,
        subject_tokens=subject_tokens,
        rows_meta=rows_meta,
    )
    src_count = max(_sources_count(m) for m in picked_markets)
    card = _finalize_section(_make_kit_card(
        card_id=f"{slug}-dated-tiles",
        layout="grid",
        variant="dated_tiles",
        kicker=f"{kicker} · MILESTONES",
        common_headline=headline,
        stat_caption=lead_caption or "Probabilities across upcoming target dates",
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
    _consume_templates(consume_markets, markets, used_ids)
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
    family_headline: str | None = None,
    seen_headlines: set[str] | frozenset[str] = frozenset(),
    subject_tokens: set[str] | frozenset[str] | None = None,
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
    chosen_pool = max(clusters, key=len, default=pool)
    monotonic_chosen = _drop_inverted_threshold_rows([
        {
            "market": m,
            "rung_text": str(m.get("name") or ""),
            "pct_by_col": {"p": _top_outcome_cell(m)[2]},
            "consensus_key": (_sources_count(m), int(m.get("volume_24h") or 0)),
        }
        for m in chosen_pool
    ])
    chosen_pool = [e["market"] for e in monotonic_chosen]
    if len(chosen_pool) < 3:
        return None
    pcts = [_top_outcome_cell(m)[2] for m in chosen_pool]
    if (max(pcts) - min(pcts)) < 10:
        return None

    ranked_all = sorted(chosen_pool, key=lambda m: (-_top_probability(m), int(m["id"])))
    selected_rows, consumed_rows = _dedupe_by_rendered_label(ranked_all, limit=5, max_len=80)
    if len(selected_rows) < 3:
        return None
    ranked = [m for m, _ in selected_rows]
    ranked_titles = [str(m.get("name") or "") for m in ranked]
    top_frac, _, top_pct = _top_outcome_cell(ranked[0])
    top_pct_str = _pct_display(top_frac, top_pct)
    top_title = selected_rows[0][1]
    caption_label = top_title
    if len(top_title.split()) <= 3 and re.match(
        r"^(?:below|above|over|under|at\s+least|\$|\d)",
        top_title,
        re.IGNORECASE,
    ):
        caption_label = _short_label(str(ranked[0].get("name") or top_title), 120)
    series: list[dict[str, Any]] = []
    rows_meta: list[dict[str, Any]] = []
    for m, title in selected_rows:
        frac, oid, pct = _top_outcome_cell(m)
        pct_str = _pct_display(frac, pct)
        series.append({
            "id": f"{slug}-ax-{m['id']}",
            "provenance": {"market_id": int(m["id"]), "outcome_id": oid},
            "leading": [_mark_word(title, style="row", tone="primary", align="left", width="flex", bold=True)],
            "marks": [
                _mark_bar_single(frac, width="flex"),
                _mark_number(pct, pct_str, unit="%", tone="primary", prominence="primary", align="right", width="sm"),
            ],
        })
        rows_meta.append({
            "pct": pct,
            "deadline_dt": _closing_deadline_dt(m),
        })

    eff_subj = set(subject_tokens) if subject_tokens is not None else set(entity_tokens)
    headline = _derive_section_headline(
        "shared_scale",
        ranked_titles,
        family_headline,
        seen_headlines,
        subject_tokens=eff_subj,
        rows_meta=rows_meta,
    )
    src_count = max(_sources_count(m) for m in ranked)
    card = _finalize_section(_make_kit_card(
        card_id=f"{slug}-shared-scale",
        layout="axis",
        variant="shared_scale",
        kicker=f"{kicker} · OVERVIEW",
        common_headline=headline,
        stat_caption=_caption_for_row(caption_label, f"stands at {top_pct_str}"),
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
    family_headline: str | None = None,
    seen_headlines: set[str] | frozenset[str] = frozenset(),
    subject_tokens: set[str] | frozenset[str] | None = None,
) -> dict[str, Any] | None:
    """Stack section for >= 2 remaining open markets closing within 1..45 days."""
    eff_subj = set(subject_tokens) if subject_tokens is not None else _subject_tokens_from_headline(family_headline)
    seen_base = {_heading_base_key(s, eff_subj) for s in seen_headlines if s}
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
    monotonic_near = _drop_inverted_threshold_rows([
        {
            "market": t[2],
            "rung_text": str(t[2].get("name") or ""),
            "pct_by_col": {"p": _top_outcome_cell(t[2])[2]},
            "consensus_key": (_sources_count(t[2]), int(t[2].get("volume_24h") or 0)),
        }
        for t in near
    ])
    near_markets = [e["market"] for e in monotonic_near]
    all_unique, all_consumed = _dedupe_by_rendered_label(
        near_markets,
        limit=max(12, len(near_markets)),
        max_len=80,
    )
    if len(all_unique) < 2:
        return None

    selected_rows = all_unique[:4]
    consumed_rows: list[Mapping[str, Any]] = []
    top4_titles = [str(m.get("name") or "") for m, _ in selected_rows]
    top4_has_full_theme = any(
        all(pat.search(t) for t in top4_titles)
        and _heading_base_key(_title_case_phrase(label), eff_subj) not in seen_base
        for pat, label in _SECTION_THEME_PATTERNS
    )
    # Split out homogeneous thematic sub-clusters (e.g. praise without mixing an insult, or RT scores)
    # only when the natural top-4 mix would have to fall back to a generic deadline.
    if not top4_has_full_theme and len(all_unique) >= 3:
        best_cluster: list[tuple[Mapping[str, Any], str]] | None = None
        best_score: tuple[int, int] = (0, 0)
        for idx, (pat, label) in enumerate(_SECTION_THEME_PATTERNS):
            bkey = _heading_base_key(_title_case_phrase(label), eff_subj)
            if bkey in seen_base or _title_case_phrase(label).lower() in _BANNED_SECTION_HEADINGS:
                continue
            matched = [(m, lbl) for m, lbl in all_unique if pat.search(str(m.get("name") or ""))]
            if len(matched) >= 2:
                score = (min(4, len(matched)), -idx)
                if score > best_score:
                    best_score = score
                    best_cluster = matched[:4]
        if best_cluster is not None:
            selected_rows = best_cluster
            consumed_rows = [m for m, _ in selected_rows]

    if not consumed_rows:
        picked_ids = {int(m["id"]) for m, _ in selected_rows}
        consumed_rows = [
            m for m in all_consumed
            if int(m["id"]) in picked_ids
            or _normalize_question_key(str(m.get("name") or ""))
            in {_normalize_question_key(str(pm.get("name") or "")) for pm, _ in selected_rows}
        ]

    picked = [m for m, _ in selected_rows]
    picked_titles = [str(m.get("name") or "") for m in picked]
    items: list[dict[str, Any]] = []
    rows_meta: list[dict[str, Any]] = []
    first_days = 1
    for idx_r, (m, title) in enumerate(selected_rows):
        res_dt = _parse_iso_dt(m.get("resolution_date") or m.get("close_time"))
        days = int((res_dt - now).total_seconds() // 86400) if res_dt else 1
        if idx_r == 0:
            first_days = days
        frac, oid, pct = _top_outcome_cell(m)
        pct_str = _pct_display(frac, pct)
        items.append({
            "id": f"{slug}-cd-{m['id']}",
            "provenance": {"market_id": int(m["id"]), "outcome_id": oid},
            "marks": [
                _mark_word(title, style="row", tone="primary", align="left", width="flex"),
                _mark_number(days, f"{days}d", unit="days", tone="muted", prominence="secondary", align="right", width="auto"),
                _mark_number(pct, pct_str, unit="%", tone="primary", prominence="primary", align="right", width="auto"),
            ],
        })
        rows_meta.append({"days": days, "pct": pct, "deadline_dt": _closing_deadline_dt(m)})

    first_frac, _, first_pct = _top_outcome_cell(picked[0])
    first_pct_str = _pct_display(first_frac, first_pct)
    first_title = selected_rows[0][1]
    headline = _derive_section_headline(
        "countdown",
        picked_titles,
        family_headline,
        seen_headlines,
        subject_tokens=eff_subj,
        rows_meta=rows_meta,
    )
    src_count = max(_sources_count(m) for m in picked)
    card = _finalize_section(_make_kit_card(
        card_id=f"{slug}-countdown",
        layout="stack",
        variant="countdown",
        kicker=f"{kicker} · SOON",
        common_headline=headline,
        stat_caption=_caption_for_row(first_title, f"stands at {first_pct_str} with {first_days} days left"),
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
    *,
    family_headline: str | None = None,
    seen_headlines: set[str] | frozenset[str] = frozenset(),
    subject_tokens: set[str] | frozenset[str] | None = None,
) -> dict[str, Any] | None:
    """Stack section translating >= 2 binary open long-shots (1..15%) into '1 in N' odds (#13696 Point 2)."""
    longshots: list[tuple[int, Mapping[str, Any]]] = []
    for m in markets:
        mid = int(m["id"])
        if mid in used_ids or not _is_binary_market(m):
            continue
        _, _, pct = _top_outcome_cell(m)
        if 1 <= pct <= 15:
            longshots.append((pct, m))
    if len(longshots) < 2:
        return None
    longshots.sort(key=lambda pm: (-pm[0], int(pm[1]["id"])))
    monotonic_ls = _drop_inverted_threshold_rows([
        {
            "market": pm[1],
            "rung_text": str(pm[1].get("name") or ""),
            "pct_by_col": {"p": pm[0]},
            "consensus_key": (_sources_count(pm[1]), int(pm[1].get("volume_24h") or 0)),
        }
        for pm in longshots
    ])
    selected_rows, consumed_rows = _dedupe_by_rendered_label(
        [e["market"] for e in monotonic_ls],
        limit=4,
        max_len=80,
    )
    if len(selected_rows) < 2:
        return None
    picked = [m for m, _ in selected_rows]
    picked_titles = [str(m.get("name") or "") for m in picked]

    items: list[dict[str, Any]] = []
    rows_meta: list[dict[str, Any]] = []
    for m, title in selected_rows:
        frac, oid, pct = _top_outcome_cell(m)
        n_val = compute_one_in_n(pct)
        pct_str = _pct_display(frac, pct)
        items.append({
            "id": f"{slug}-oin-{m['id']}",
            "provenance": {"market_id": int(m["id"]), "outcome_id": oid},
            "marks": [
                _mark_word(title, style="row", tone="primary", align="left", width="flex"),
                _mark_number(n_val, f"1 in {n_val}", unit="one_in_n", tone="accent", prominence="primary", align="right", width="auto"),
                _mark_number(pct, pct_str, unit="%", tone="muted", prominence="secondary", align="right", width="auto"),
            ],
        })
        rows_meta.append({
            "pct": pct,
            "deadline_dt": _closing_deadline_dt(m),
        })

    lead_frac, _, lead_pct = _top_outcome_cell(picked[0])
    lead_pct_str = _pct_display(lead_frac, lead_pct)
    lead_n = compute_one_in_n(lead_pct)
    lead_title = selected_rows[0][1]
    headline = _derive_section_headline(
        "one_in_n",
        picked_titles,
        family_headline,
        seen_headlines,
        subject_tokens=subject_tokens,
        rows_meta=rows_meta,
    )
    src_count = max(_sources_count(m) for m in picked)
    card = _finalize_section(_make_kit_card(
        card_id=f"{slug}-one-in-n",
        layout="stack",
        variant="one_in_n",
        kicker=f"{kicker} · OUTSIDE SHOTS",
        common_headline=headline,
        stat_caption=_caption_for_row(lead_title, f"carries a 1 in {lead_n} ({lead_pct_str}) chance"),
        source_count=src_count,
        route_slug=slug,
        body={"header_layout": "none", "header_marks": [], "items": items},
    ))
    if card is None:
        return None
    _consume_templates(consumed_rows, markets, used_ids)
    return card


_OUTCOME_DATE_PREFIX_RE = re.compile(
    r"^\s*(?:before|by|after|in)\s+(?:20\d{2}|jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?|q[1-4])\b",
    re.IGNORECASE,
)


def _eligible_multi_contender_outcomes(
    market: Mapping[str, Any],
    *,
    ref_now: datetime,
    exclude_other: bool = False,
) -> list[dict[str, Any]]:
    """Return active non-date contender outcomes for stack sections (filtering winners & date ladders)."""
    if re.match(r"^\s*when\s+will\b", str(market.get("name") or ""), re.IGNORECASE):
        return []
    raw_outs = _sorted_outcomes(market)
    if len(raw_outs) < 2:
        return []
    if any(_OUTCOME_DATE_PREFIX_RE.match(str(o.get("name") or "")) for o in raw_outs):
        return []
    date_cnt = sum(
        1
        for o in raw_outs
        if _parse_date_marker(str(o.get("name") or ""), default_year=ref_now.year) is not None
        and len(str(o.get("name") or "").split()) <= 5
    )
    if date_cnt >= 2:
        return []
    outs = raw_outs
    if exclude_other:
        outs = [o for o in outs if o["name"].lower() not in {"yes", "no", "other"}]
    if market.get("mutually_exclusive") is False:
        outs = [o for o in outs if not o.get("is_winner") and float(o["prob"]) < 0.999]
    outs = outs[:4]
    if len(outs) < 2 or all(o.get("is_winner") or float(o["prob"]) >= 0.999 for o in outs):
        return []
    return outs


def _build_casting_sheet_section(
    slug: str,
    kicker: str,
    markets: Sequence[Mapping[str, Any]],
    used_ids: set[int],
    *,
    now: datetime | None = None,
    family_headline: str | None = None,
    seen_headlines: set[str] | frozenset[str] = frozenset(),
    subject_tokens: set[str] | frozenset[str] | None = None,
) -> dict[str, Any] | None:
    """Stack casting_sheet section ONLY when every printed contender row has verified HTTPS art."""
    ref_now = _parse_iso_dt(now) or datetime.now(timezone.utc)
    eff_subj = set(subject_tokens) if subject_tokens is not None else _subject_tokens_from_headline(family_headline)
    art_map = _verified_art_by_key()
    for m in sorted(markets, key=lambda x: (-int(x.get("volume_24h") or 0), int(x["id"]))):
        mid = int(m["id"])
        if mid in used_ids or _is_binary_market(m):
            continue
        outs = _eligible_multi_contender_outcomes(m, ref_now=ref_now, exclude_other=True)
        if not outs:
            continue
        pics = [_lookup_subject_art(o["name"], art_map) for o in outs]
        if not all(p is not None and p.get("url", "").split("/")[2] in ALLOWED_KIT_IMAGE_HOSTS for p in pics):
            continue
        items = []
        for idx_o, (o, pic) in enumerate(zip(outs, pics)):
            prob = float(o["prob"])
            pct = int(o["rendered_percent"])
            pct_str = _pct_display(prob, pct)
            items.append({
                "id": f"{slug}-cs-{mid}-{idx_o}",
                "provenance": {"market_id": mid, "outcome_id": o.get("id")},
                "marks": [
                    pic,
                    _mark_word(o["name"], style="row", tone="primary", align="left", width="flex", bold=(idx_o == 0)),
                    _mark_number(pct, pct_str, unit="%", tone="primary", prominence="primary", align="right", width="auto"),
                ],
            })
        top_o = outs[0]
        top_pct_str = _pct_display(float(top_o["prob"]), int(top_o["rendered_percent"]))
        headline = _derive_single_market_field_headline(
            str(m.get("name") or ""),
            eff_subj,
            seen_headlines,
        )
        card = _finalize_section(_make_kit_card(
            card_id=f"{slug}-casting-sheet",
            layout="stack",
            variant="casting_sheet",
            kicker=f"{kicker} · CONTENDERS",
            common_headline=headline,
            stat_caption=f"{top_o['name']} is the favorite for {headline} at {top_pct_str}",
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
    family_headline: str | None = None,
    seen_headlines: set[str] | frozenset[str] = frozenset(),
    subject_tokens: set[str] | frozenset[str] | None = None,
) -> dict[str, Any] | None:
    """388: A last-resort bar stack section, used ONLY when < 3 structured sections fit."""
    ref_now = _parse_iso_dt(now) or datetime.now(timezone.utc)
    eff_subj = set(subject_tokens) if subject_tokens is not None else _subject_tokens_from_headline(family_headline)
    # Prefer an unused multi-outcome contender market first, otherwise >= 2 binary markets
    for m in sorted(markets, key=lambda x: (-int(x.get("volume_24h") or 0), int(x["id"]))):
        mid = int(m["id"])
        if mid in used_ids or _is_binary_market(m):
            continue
        outs = _eligible_multi_contender_outcomes(m, ref_now=ref_now, exclude_other=False)
        if not outs:
            continue
        items = []
        for idx_o, o in enumerate(outs):
            prob = float(o["prob"])
            pct = int(o["rendered_percent"])
            pct_str = _pct_display(prob, pct)
            items.append({
                "id": f"{slug}-bar-m-{mid}-{idx_o}",
                "provenance": {"market_id": mid, "outcome_id": o.get("id")},
                "marks": [
                    _mark_word(o["name"], style="row", tone="primary", align="left", width="flex", bold=(idx_o == 0)),
                    _mark_bar_single(prob, width="sm"),
                    _mark_number(pct, pct_str, unit="%", tone="primary", prominence="primary", align="right", width="auto"),
                ],
            })
        top_o = outs[0]
        top_pct_str = _pct_display(float(top_o["prob"]), int(top_o["rendered_percent"]))
        headline = _derive_single_market_field_headline(
            str(m.get("name") or ""),
            eff_subj,
            seen_headlines,
        )
        card = _finalize_section(_make_kit_card(
            card_id=f"{slug}-plain-bars",
            layout="stack",
            variant="plain_bar_stack",
            kicker=f"{kicker} · RACE",
            common_headline=headline,
            stat_caption=f"{top_o['name']} is the favorite for {headline} at {top_pct_str}",
            source_count=_sources_count(m),
            route_slug=slug,
            body={"header_layout": "none", "header_marks": [], "items": items},
        ))
        if card is not None:
            _consume_templates([m], markets, used_ids)
            return card

    rem_bin = [m for m in markets if int(m["id"]) not in used_ids and _is_binary_market(m)]
    rem_bin.sort(key=lambda m: (-_top_probability(m), int(m["id"])))
    monotonic_bin = _drop_inverted_threshold_rows([
        {
            "market": m,
            "rung_text": str(m.get("name") or ""),
            "pct_by_col": {"p": _top_outcome_cell(m)[2]},
            "consensus_key": (_sources_count(m), int(m.get("volume_24h") or 0)),
        }
        for m in rem_bin
    ])
    rem_bin = [e["market"] for e in monotonic_bin]
    if len(rem_bin) < 2:
        return None
    selected_rows, consumed_rows = _dedupe_by_rendered_label(rem_bin, limit=4, max_len=80)
    if len(selected_rows) < 2:
        return None
    picked = [m for m, _ in selected_rows]
    picked_titles = [str(m.get("name") or "") for m in picked]
    items = []
    rows_meta: list[dict[str, Any]] = []
    for m, title in selected_rows:
        frac, oid, pct = _top_outcome_cell(m)
        pct_str = _pct_display(frac, pct)
        items.append({
            "id": f"{slug}-bar-b-{m['id']}",
            "provenance": {"market_id": int(m["id"]), "outcome_id": oid},
            "marks": [
                _mark_word(title, style="row", tone="primary", align="left", width="flex"),
                _mark_bar_single(frac, width="sm"),
                _mark_number(pct, pct_str, unit="%", tone="primary", prominence="primary", align="right", width="auto"),
            ],
        })
        rows_meta.append({
            "pct": pct,
            "deadline_dt": _closing_deadline_dt(m),
        })
    lead_m = picked[0]
    lead_frac, _, lead_pct = _top_outcome_cell(lead_m)
    lead_pct_str = _pct_display(lead_frac, lead_pct)
    lead_title = selected_rows[0][1]
    headline = _derive_section_headline(
        "plain_bar_stack",
        picked_titles,
        family_headline,
        seen_headlines,
        subject_tokens=eff_subj,
        rows_meta=rows_meta,
    )
    card = _finalize_section(_make_kit_card(
        card_id=f"{slug}-plain-bars",
        layout="stack",
        variant="plain_bar_stack",
        kicker=f"{kicker} · MARKETS",
        common_headline=headline,
        stat_caption=_caption_for_row(lead_title, f"stands at {lead_pct_str}"),
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

    if family_label and not _passes_taste_and_harm(family_label):
        return {
            "accepted": False,
            "refusal_reason": "refused_scout_taste_or_harm_guard",
            "family_fingerprint": family_fingerprint,
            "market_count": len(raw_list),
            "sections_built": 0,
            "variants": [],
        }

    safe_list = [
        m for m in raw_list
        if _passes_taste_and_harm(m.get("name") or m.get("title"), m.get("description"))
    ]
    if len(safe_list) < len(raw_list) and len(safe_list) < 5:
        return {
            "accepted": False,
            "refusal_reason": "refused_scout_taste_or_harm_guard",
            "family_fingerprint": family_fingerprint,
            "market_count": len(safe_list),
            "sections_built": 0,
            "variants": [],
        }

    clean_markets = _dedupe_twins(safe_list)
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
    seen_headlines: set[str] = {headline.lower()}

    entity_tokens = _subject_tokens_from_headline(headline)
    seen_base_keys: set[str] = {_heading_base_key(headline, entity_tokens)}

    def _section_row_texts(card_obj: dict[str, Any]) -> list[str]:
        body = card_obj.get("body") or {}
        out_texts: list[str] = []
        for coll_key in ("rows", "series", "items"):
            for entry in body.get(coll_key) or ():
                if not isinstance(entry, Mapping):
                    continue
                for mk in entry.get("leading") or entry.get("marks") or ():
                    if isinstance(mk, Mapping) and mk.get("mark") == "word" and mk.get("text"):
                        out_texts.append(str(mk["text"]))
                        break
        return out_texts

    def _try_append(builder_fn: Any, *args: Any, **kwargs: Any) -> None:
        if len(sections) >= 5:
            return
        sec = builder_fn(
            *args,
            family_headline=headline,
            seen_headlines=seen_headlines,
            subject_tokens=entity_tokens,
            **kwargs,
        )
        if sec is None:
            return
        variant = str(sec.get("variant") or "")
        if not variant or variant in seen_variants:
            return
        sec_hl = str(sec.get("common_headline") or "").strip()
        sec_bkey = _heading_base_key(sec_hl, entity_tokens)
        row_texts = _section_row_texts(sec)
        if (
            not sec_hl
            or not (2 <= len(sec_hl.split()) <= 4)
            or sec_hl.lower() in seen_headlines
            or sec_hl.lower() in _BANNED_SECTION_HEADINGS
            or (sec_bkey and sec_bkey in seen_base_keys)
        ):
            # Single-market casting/contender cards cannot re-derive from contender names;
            # keep them only if their own heading did not collide.
            mids = set()
            for it in (sec.get("body") or {}).get("items") or ():
                mid = (it.get("provenance") or {}).get("market_id")
                if mid is not None:
                    mids.add(int(mid))
            if variant == "casting_sheet" or (variant == "plain_bar_stack" and len(mids) == 1):
                return
            topical_hl = _derive_section_headline(
                variant,
                row_texts or [str(sec.get("stat_caption") or "")],
                headline,
                seen_headlines,
                subject_tokens=entity_tokens,
            )
            topical_bkey = _heading_base_key(topical_hl, entity_tokens)
            if (
                topical_hl.lower() in seen_headlines
                or (topical_bkey and topical_bkey in seen_base_keys)
            ):
                return
            sec = {**sec, "common_headline": topical_hl}
            sec_hl = topical_hl
            sec_bkey = topical_bkey
        seen_headlines.add(sec_hl.lower())
        if sec_bkey:
            seen_base_keys.add(sec_bkey)
        seen_variants.add(variant)
        sections.append(sec)

    # Order prioritizes structural variety first; plain_bar_stack is strictly last resort (388: A).
    _try_append(_build_scoreboard_grid_section, slug, resolved_kicker, clean_markets, used_ids, now=ref_now)
    _try_append(_build_dated_tiles_section, slug, resolved_kicker, clean_markets, used_ids, now=ref_now)
    _try_append(_build_shared_scale_section, slug, resolved_kicker, clean_markets, used_ids, require_cluster=True, entity_tokens=entity_tokens)
    _try_append(_build_countdown_section, slug, resolved_kicker, clean_markets, used_ids, now=ref_now)
    _try_append(_build_one_in_n_section, slug, resolved_kicker, clean_markets, used_ids)
    _try_append(_build_casting_sheet_section, slug, resolved_kicker, clean_markets, used_ids, now=ref_now)

    if len(sections) < 3 and "shared_scale" not in seen_variants:
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

    page_fp_payload = {
        "slug": slug,
        "title": headline,
        "kicker": resolved_kicker,
        "family_fingerprint": family_fingerprint,
        "covered_market_ids": sorted(used_ids),
        "sections": sections,
    }
    page_fingerprint = hashlib.sha256(
        json.dumps(page_fp_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:16]

    page = {
        "kit_page_version": 1,
        "state": "preview",
        "slug": slug,
        "title": headline,
        "kicker": resolved_kicker,
        "caption": f"{len(sections)} disjoint views across {len(used_ids)} open markets",
        "family_fingerprint": family_fingerprint,
        "page_fingerprint": page_fingerprint,
        "snapshot_captured_at": ref_now.isoformat(),
        "covered_market_ids": sorted(used_ids),
        "market_count": len(used_ids),
        "section_count": len(sections),
        "variants": [str(s["variant"]) for s in sections],
        "sections": sections,
    }
    return {"accepted": True, "refusal_reason": None, "page": page}


def _parse_rendered_pct_value(text: str) -> int | None:
    s = (text or "").strip()
    if s == "<1%":
        return 0
    if s == ">99%":
        return 100
    m = re.fullmatch(r"(\d{1,3})\s*%", s)
    return int(m.group(1)) if m else None


def audit_container_page_invariants(
    page: Mapping[str, Any],
    *,
    markets_by_id: Mapping[int, Mapping[str, Any]] | None = None,
) -> list[str]:
    """Return a list of invariant violations for a proposed Kit container page (#13696 rework)."""
    violations: list[str] = []
    sections = page.get("sections") or []
    subject_tokens = _subject_tokens_from_headline(str(page.get("title") or ""))
    seen_base_headings: dict[str, str] = {}
    seen_market_sections: dict[int, str] = {}
    seen_binary_qkeys: dict[str, str] = {}
    seen_canon_deadlines: dict[tuple[str, str], str] = {}
    theme_by_label = {label.lower(): pat for pat, label in _SECTION_THEME_PATTERNS}

    ref_year = datetime.now(timezone.utc).year
    snap = _parse_iso_dt(page.get("snapshot_captured_at"))
    if snap is not None:
        ref_year = snap.year

    def _record_market_canon(m_id: int | None, fallback_text: str, sec_id_val: str) -> None:
        src_title = (
            str(markets_by_id[int(m_id)].get("name") or fallback_text)
            if (m_id is not None and markets_by_id and int(m_id) in markets_by_id)
            else fallback_text
        )
        stem_q, canon_d = _canonical_question_and_deadline(src_title, ref_year)
        if stem_q and canon_d:
            key = (stem_q, canon_d)
            if key in seen_canon_deadlines and seen_canon_deadlines[key] != sec_id_val:
                violations.append(
                    f"{sec_id_val}: canonical event+deadline {key!r} repeats {seen_canon_deadlines[key]}"
                )
            else:
                seen_canon_deadlines[key] = sec_id_val

    for sec in sections:
        sec_id = str(sec.get("id") or sec.get("variant") or "section")
        variant = str(sec.get("variant") or "")
        hl = str(sec.get("common_headline") or "").strip()
        hl_low = hl.lower()
        body = sec.get("body") or {}

        # 5b & 6. Headline shape, banned check, and stripped-subject uniqueness
        if not (2 <= len(hl.split()) <= 4):
            violations.append(f"{sec_id}: headline word count out of 2..4 range ({hl!r})")
        if hl_low in _BANNED_SECTION_HEADINGS or any(b in hl_low for b in _BANNED_SECTION_HEADINGS):
            violations.append(f"{sec_id}: banned headline ({hl!r})")
        bkey = _heading_base_key(hl, subject_tokens)
        if bkey in seen_base_headings:
            violations.append(
                f"{sec_id}: stripped heading {bkey!r} ({hl!r}) repeats {seen_base_headings[bkey]!r}"
            )
        elif bkey:
            seen_base_headings[bkey] = hl

        # Gather rows + provenance market_ids + displayed numbers
        section_market_ids: set[int] = set()
        section_row_entries: list[dict[str, Any]] = []
        raw_texts_for_theme: list[str] = []

        if variant == "dated_tiles":
            for row in body.get("rows") or ():
                lead_word = next(
                    (
                        str(mk.get("text") or "")
                        for mk in (row.get("leading") or ())
                        if isinstance(mk, Mapping) and mk.get("mark") == "word"
                    ),
                    "",
                )
                row_dts: list[tuple[str, datetime]] = []
                row_pcts: dict[str, int] = {}
                row_mids: set[int] = set()
                for cell in row.get("cells") or ():
                    mid = (cell.get("provenance") or {}).get("market_id")
                    if mid is not None:
                        row_mids.add(int(mid))
                        section_market_ids.add(int(mid))
                    for mk in cell.get("marks") or ():
                        if not isinstance(mk, Mapping) or mk.get("mark") != "tile":
                            continue
                        t_lbl = str(mk.get("top_label") or "").strip()
                        c_lbl = str(mk.get("center_label") or "").strip()
                        pct_v = _parse_rendered_pct_value(c_lbl)
                        if t_lbl and pct_v is not None:
                            row_pcts[t_lbl] = pct_v
                        pm = _parse_date_marker(t_lbl, default_year=ref_year)
                        if pm is not None:
                            row_dts.append((t_lbl, pm["sort_dt"]))
                            t_low = t_lbl.lower()
                            if not t_low.startswith(("by ", "before ", "on ", "in ")):
                                violations.append(
                                    f"{sec_id}: dated_tiles tile {t_lbl!r} missing 'by'/'before'/'on' prefix"
                                )
                        _record_market_canon(mid, f"{lead_word} {t_lbl}".strip(), sec_id)
                for idx_d in range(len(row_dts) - 1):
                    if row_dts[idx_d][1] > row_dts[idx_d + 1][1]:
                        violations.append(
                            f"{sec_id}: date tiles out of order {row_dts[idx_d][0]!r} > {row_dts[idx_d + 1][0]!r}"
                        )
                qk = _normalize_question_key(lead_word)
                if qk and len(row_mids) >= 1:
                    if qk in seen_binary_qkeys and seen_binary_qkeys[qk] != sec_id:
                        violations.append(f"{sec_id}: duplicate normalized question {qk!r}")
                    elif qk in seen_binary_qkeys:
                        violations.append(f"{sec_id}: duplicate row within dated_tiles {qk!r}")
                    seen_binary_qkeys[qk] = sec_id
                rung_source = lead_word
                if markets_by_id and len(row_mids) == 1:
                    m_obj = markets_by_id.get(next(iter(row_mids)))
                    if m_obj and m_obj.get("name"):
                        rung_source = str(m_obj["name"])
                section_row_entries.append({
                    "rung_text": rung_source,
                    "label": lead_word,
                    "pct_by_col": row_pcts,
                })
                raw_texts_for_theme.append(rung_source)

        elif variant in ("shared_scale", "countdown", "one_in_n", "plain_bar_stack", "casting_sheet"):
            seq = body.get("series") if variant == "shared_scale" else body.get("items")
            row_items = list(seq or ())
            single_market_field = len({
                (it.get("provenance") or {}).get("market_id")
                for it in row_items
                if (it.get("provenance") or {}).get("market_id") is not None
            }) == 1 and len(row_items) >= 2 and variant in ("casting_sheet", "plain_bar_stack")

            if single_market_field:
                if any(g in hl_low.split() for g in ("milestones", "developments", "watch", "watchlist")):
                    violations.append(f"{sec_id}: generic field heading ({hl!r})")
                if row_items:
                    lead_marks = row_items[0].get("marks") or ()
                    lead_num_txt = next(
                        (
                            str(mk.get("display") or mk.get("text") or "")
                            for mk in lead_marks
                            if isinstance(mk, Mapping) and mk.get("mark") == "number" and mk.get("unit") == "%"
                        ),
                        None,
                    )
                    cap = str(sec.get("stat_caption") or "")
                    if lead_num_txt and lead_num_txt not in cap:
                        violations.append(
                            f"{sec_id}: caption {cap!r} does not show lead row {lead_num_txt!r}"
                        )

            for it in row_items:
                mid = (it.get("provenance") or {}).get("market_id")
                if mid is not None:
                    section_market_ids.add(int(mid))
                marks = list(it.get("leading") or ()) + list(it.get("marks") or ())
                lbl = next(
                    (str(mk.get("text") or "") for mk in marks if isinstance(mk, Mapping) and mk.get("mark") == "word"),
                    "",
                )
                pct_val = next(
                    (
                        _parse_rendered_pct_value(str(mk.get("display") or mk.get("text") or ""))
                        for mk in marks
                        if isinstance(mk, Mapping) and mk.get("mark") == "number" and mk.get("unit") == "%"
                    ),
                    None,
                )
                if not single_market_field:
                    if mid is not None and markets_by_id and int(mid) in markets_by_id:
                        full_name = str(markets_by_id[int(mid)].get("name") or lbl)
                    else:
                        full_name = lbl
                    qk = _normalize_question_key(full_name)
                    if qk:
                        if qk in seen_binary_qkeys:
                            violations.append(f"{sec_id}: duplicate normalized question {qk!r}")
                        seen_binary_qkeys[qk] = sec_id
                    _record_market_canon(mid, full_name, sec_id)
                    if pct_val is not None:
                        section_row_entries.append({
                            "rung_text": full_name,
                            "label": lbl,
                            "pct_by_col": {"p": pct_val},
                        })
                    raw_texts_for_theme.append(full_name)

        elif variant == "scoreboard_grid":
            for row in body.get("rows") or ():
                for cell in row.get("cells") or ():
                    mid = (cell.get("provenance") or {}).get("market_id")
                    if mid is not None:
                        section_market_ids.add(int(mid))

        for mid in section_market_ids:
            if mid in seen_market_sections:
                violations.append(f"{sec_id}: market_id {mid} repeated across {seen_market_sections[mid]} and {sec_id}")
            seen_market_sections[mid] = sec_id

        # 2. Check numeric threshold rung monotonicity
        if len(section_row_entries) >= 2:
            filtered = _drop_inverted_threshold_rows(section_row_entries)
            if len(filtered) < len(section_row_entries):
                violations.append(f"{sec_id}: inverted numeric threshold rung detected")

        # 5a. Check 100%-row-match when a thematic label from _SECTION_THEME_PATTERNS is used
        theme_lookup_key = "approval rating" if hl_low.endswith("approval rating") else hl_low
        if len(raw_texts_for_theme) >= 2 and theme_lookup_key in theme_by_label:
            pat = theme_by_label[theme_lookup_key]
            if not all(pat.search(t) for t in raw_texts_for_theme):
                violations.append(
                    f"{sec_id}: thematic headline {hl!r} not true for all {len(raw_texts_for_theme)} rows"
                )

    return violations
