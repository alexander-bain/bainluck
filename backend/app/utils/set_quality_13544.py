"""Set-quality gates, dated 196-A row context, and selection rationale (#13544)."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence


MEASURE_FAMILY_TIMING_LADDER = "timing_ladder"
MEASURE_FAMILY_REVIEW_SCORE = "review_score"
MEASURE_FAMILY_BOX_OFFICE = "box_office_gross"
MEASURE_FAMILY_PRICE_OR_COST = "price_or_cost"
MEASURE_FAMILY_PRICE_RECORD = "price_record"
MEASURE_FAMILY_MACRO_RATE = "macro_rate"
MEASURE_FAMILY_SHARE_OR_RATING = "share_or_rating"
MEASURE_FAMILY_PHYSICAL_QUANTITY = "physical_quantity"
MEASURE_FAMILY_RANKED_POSITION = "ranked_position"
MEASURE_FAMILY_EVENT_OR_WINNER = "event_or_winner"
# Backwards-compatible aliases kept for external callers
MEASURE_FAMILY_WINNER_FIELD = MEASURE_FAMILY_EVENT_OR_WINNER
MEASURE_FAMILY_BINARY_EVENT = MEASURE_FAMILY_EVENT_OR_WINNER

CU_FRAME_MIN_WRITER_REV = 7
CU_GROUNDED_SUBJECT_REV = 8

_CU_MEASURE_TO_FAMILY: dict[str, str] = {
    "rt_score": MEASURE_FAMILY_REVIEW_SCORE,
    "box_office_revenue": MEASURE_FAMILY_BOX_OFFICE,
    "price_record_high": MEASURE_FAMILY_PRICE_RECORD,
    "price_record_low": MEASURE_FAMILY_PRICE_RECORD,
    "asset_price": MEASURE_FAMILY_PRICE_OR_COST,
    "close_price": MEASURE_FAMILY_PRICE_OR_COST,
    "exchange_rate": MEASURE_FAMILY_PRICE_OR_COST,
    "index_close": MEASURE_FAMILY_PRICE_OR_COST,
    "market_cap": MEASURE_FAMILY_PRICE_OR_COST,
    "price_high": MEASURE_FAMILY_PRICE_OR_COST,
    "price_low": MEASURE_FAMILY_PRICE_OR_COST,
    "revenue": MEASURE_FAMILY_PRICE_OR_COST,
    "atp_points": MEASURE_FAMILY_PHYSICAL_QUANTITY,
    "daily_views": MEASURE_FAMILY_PHYSICAL_QUANTITY,
    "event_count": MEASURE_FAMILY_PHYSICAL_QUANTITY,
    "goals": MEASURE_FAMILY_PHYSICAL_QUANTITY,
    "high_temperature": MEASURE_FAMILY_PHYSICAL_QUANTITY,
    "low_temperature": MEASURE_FAMILY_PHYSICAL_QUANTITY,
    "magnitude": MEASURE_FAMILY_PHYSICAL_QUANTITY,
    "points": MEASURE_FAMILY_PHYSICAL_QUANTITY,
    "precipitation": MEASURE_FAMILY_PHYSICAL_QUANTITY,
    "runs": MEASURE_FAMILY_PHYSICAL_QUANTITY,
    "snowfall": MEASURE_FAMILY_PHYSICAL_QUANTITY,
    "subscriber_count": MEASURE_FAMILY_PHYSICAL_QUANTITY,
    "touchdowns": MEASURE_FAMILY_PHYSICAL_QUANTITY,
    "tweet_count": MEASURE_FAMILY_PHYSICAL_QUANTITY,
    "victory_margin": MEASURE_FAMILY_PHYSICAL_QUANTITY,
    "wins": MEASURE_FAMILY_PHYSICAL_QUANTITY,
    "economic_growth": MEASURE_FAMILY_MACRO_RATE,
    "employment": MEASURE_FAMILY_MACRO_RATE,
    "housing_starts": MEASURE_FAMILY_MACRO_RATE,
    "inflation_rate": MEASURE_FAMILY_MACRO_RATE,
    "interest_rate": MEASURE_FAMILY_MACRO_RATE,
    "unemployment_rate": MEASURE_FAMILY_MACRO_RATE,
    "approval_rating": MEASURE_FAMILY_SHARE_OR_RATING,
    "poll_share": MEASURE_FAMILY_SHARE_OR_RATING,
    "vote_share": MEASURE_FAMILY_SHARE_OR_RATING,
    "release_date": MEASURE_FAMILY_TIMING_LADDER,
    "ranking": MEASURE_FAMILY_RANKED_POSITION,
    "appointment": MEASURE_FAMILY_EVENT_OR_WINNER,
    "award_result": MEASURE_FAMILY_EVENT_OR_WINNER,
    "election_result": MEASURE_FAMILY_EVENT_OR_WINNER,
    "nomination": MEASURE_FAMILY_EVENT_OR_WINNER,
    "result": MEASURE_FAMILY_EVENT_OR_WINNER,
    "bankruptcy_filing": MEASURE_FAMILY_EVENT_OR_WINNER,
    "ceasefire": MEASURE_FAMILY_EVENT_OR_WINNER,
    "data_center_moratorium": MEASURE_FAMILY_EVENT_OR_WINNER,
}

_WINDOW_DATE_PRECISION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("day", re.compile(r"^\d{4}-\d{2}-\d{2}$")),
    ("month", re.compile(r"^\d{4}-\d{2}$")),
    ("year", re.compile(r"^\d{4}$")),
)

_TIMING_LADDER_RE = re.compile(
    r"(?:"
    r"\bby\s*(?:\.\.\.|…|_{2,})\??\s*$|"
    r"^(?:when|what\s+year|what\s+month)\s+will\b|"
    r"\b(?:released|announced|achieved|solved|launch(?:es|ed)?|proven|listed)\s+by\s*(?:\.\.\.|…|_{2,})\??\s*$"
    r")",
    re.IGNORECASE,
)
_REVIEW_SCORE_RE = re.compile(
    r"\b(?:rotten\s+tomatoes|metacritic|imdb\s+(?:score|rating)|cinema\s*score)\b",
    re.IGNORECASE,
)
_RANKED_POSITION_RE = re.compile(
    r"(?:"
    r"#[2-9]\b|#\d{2,}\b|"
    r"\b(?:2nd|3rd|[4-9]th|second|third|fourth|fifth)[-\s]+(?:largest|biggest|highest|best|most|place|seed)\b|"
    r"\brunner[-\s]?up\b|"
    r"\btop\s+(?:[2-9]|10|250)\b|"
    r"\bhot\s+100\s+rank\b|"
    r"\bwhere\s+will\s+20\d{2}\s+rank\b|"
    r"\bfinish(?:es|ing)?\s+(?:2nd|3rd|second|third|runner[-\s]?up)\b"
    r")",
    re.IGNORECASE,
)
_BOX_OFFICE_RE = re.compile(
    r"\b(?:"
    r"opening\s+weekend\s+(?:box\s+office|gross|total)|"
    r"gross\s+more\s+on\s+(?:their|its)\s+opening\s+weekend|"
    r"(?:total\s+)?(?:domestic|worldwide)\s+gross|"
    r"highest[-\s]grossing|top[-\s]grossing|box\s+office"
    r")\b",
    re.IGNORECASE,
)
_PRICE_RECORD_RE = re.compile(
    r"\b(?:all[-\s]?time\s+(?:high|low)|record\s+(?:high|low)|"
    r"break\s+(?:the\s+|an?\s+)?auction\s+record)\b",
    re.IGNORECASE,
)
_PRICE_OR_COST_RE = re.compile(
    r"\b(?:"
    r"gas\s+pric(?:e|es)|diesel\s+pric(?:e|es)|ticket\s+price|eggs?\s+price|"
    r"combo\s+price|sale\s+price|raises?\s+.*\bprice\b|"
    r"price\s+(?:in\s+20\d{2}|at\s+year[-\s]?end|of\s+.*)|"
    r"how\s+(?:high|low)\s+will\s+.*\bpric(?:e|es)\b|"
    r"market\s+cap|higher\s+valuation|valuation\s+on|how\s+rich\s+will"
    r")\b",
    re.IGNORECASE,
)
_PHYSICAL_QUANTITY_RE = re.compile(
    r"(?:"
    r"(?:^|\s)#\s*tweets\b|"
    r"\b(?:"
    r"how\s+much\s+will\s+it\s+(?:rain|snow)|rainfall|snowfall\s+total|wettest\s+month|"
    r"how\s+low\s+will\s+.*\bdrop\b|lowest\s+.*\blevel\b|peak\s+roni\s+value|"
    r"earthquake\s+magnitude|highest\s+earthquake|"
    r"how\s+many\s+.*(?:earthquakes|tweets|songs|units|tornadoes|hurricanes|eruptions|days|subscribers)|"
    r"oceanic\s+index|how\s+long\s+will|first\s+week\s+(?:sales|album\s+equivalent)|"
    r"album\s+equivalent\s+units|songs\s+on\s+.*\bradio\b|"
    r"hottest\s+year\s+rank|u\.s\.\s+tornadoes|cyclone\s+landfalls|7\.0\+\s+earthquakes|"
    r"vei\s*\d+\+?\s+volcano"
    r")\b"
    r")",
    re.IGNORECASE,
)

_ORDINAL_RANK_PATTERNS: tuple[tuple[int, re.Pattern[str]], ...] = (
    (
        1,
        re.compile(
            r"(?<!\w)(?:#1\b|1st\b|first\s+place\b|finishing\s+first\b|"
            r"top\b(?!\s+\d)|winner\b|largest\b|biggest\b|who\s+will\s+win\b)",
            re.IGNORECASE,
        ),
    ),
    (2, re.compile(r"(?<!\w)(?:#2|2nd|second)(?:\b|$)", re.IGNORECASE)),
    (3, re.compile(r"(?<!\w)(?:#3|3rd|third)(?:\b|$)", re.IGNORECASE)),
    (4, re.compile(r"(?<!\w)(?:top\s+5|top\s+3|top\s+10|4th|5th)(?:\b|$)", re.IGNORECASE)),
)

_CORE_STOPWORDS: frozenset[str] = frozenset(
    {
        "a",
        "an",
        "and",
        "at",
        "be",
        "become",
        "before",
        "by",
        "do",
        "end",
        "for",
        "from",
        "get",
        "have",
        "in",
        "is",
        "more",
        "most",
        "of",
        "on",
        "or",
        "place",
        "single",
        "the",
        "their",
        "these",
        "this",
        "to",
        "top",
        "what",
        "when",
        "where",
        "which",
        "who",
        "will",
        "win",
        "winner",
        "with",
    }
)
_RESTATEMENT_FILLER_TOKENS: frozenset[str] = frozenset(
    {
        "single",
        "actually",
        "officially",
        "ever",
        "any",
        "new",
        "next",
        "named",
        "crowned",
        "pick",
        "picked",
        "chosen",
        "question",
        "market",
        "overall",
        "total",
        "become",
    }
)
_RANK_STRIP_RE = re.compile(
    r"(?:"
    r"#[0-9]+\b|"
    r"\b(?:1st|2nd|3rd|[4-9]th|first|second|third|top\s+\d+|"
    r"largest|biggest|highest|most|place|runner[-\s]?up|winner|"
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?|"
    r"season\s+\d+|s\d+|20\d{2})\b"
    r")",
    re.IGNORECASE,
)


def _fold(text: str) -> str:
    cleaned = (text or "").replace("\u2019", "'").replace("\u2018", "'")
    decomposed = unicodedata.normalize("NFKD", cleaned)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).lower()


def _get_title(row: Any) -> str:
    if isinstance(row, Mapping):
        return str(row.get("title") or row.get("name") or "")
    return str(getattr(row, "title", "") or getattr(row, "name", "") or "")


def _get_meta(row: Any) -> Optional[Mapping[str, Any]]:
    if isinstance(row, Mapping):
        if (
            "market_metadata" not in row
            and "title" not in row
            and any(k in row for k in ("discover_llm", "measure_family", "row_context"))
        ):
            return row
        meta = row.get("market_metadata")
        return meta if isinstance(meta, Mapping) else None
    meta = getattr(row, "market_metadata", None)
    return meta if isinstance(meta, Mapping) else None


def _get_story_key(row: Any, cu: Optional[Mapping[str, Any]] = None) -> Optional[str]:
    candidates: list[Any] = []
    if isinstance(row, Mapping):
        candidates.append(row.get("story_key"))
    else:
        candidates.append(getattr(row, "story_key", None))
    if isinstance(cu, Mapping):
        candidates.append(cu.get("story_key"))
    for cand in candidates:
        cleaned = str(cand or "").strip()
        if cleaned:
            return cleaned
    return None


def parse_window_date_precision(raw: Any) -> tuple[Optional[str], Optional[str]]:
    """Preserve `#1809` ``window_date`` at its stated precision (year / month / day)."""
    if not isinstance(raw, str):
        return None, None
    cleaned = raw.strip()
    for precision, pattern in _WINDOW_DATE_PRECISION_PATTERNS:
        if pattern.match(cleaned):
            return cleaned, precision
    return None, None


def _parse_positive_int_rank(raw: Any) -> Optional[int]:
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw if raw >= 1 else None
    if isinstance(raw, str):
        tok = raw.strip()
        if tok.isdigit():
            val = int(tok)
            return val if val >= 1 else None
    return None


def extract_cu_frame_context(row_or_meta: Any) -> dict[str, Any]:
    """Read Builder B's `#1809` ``market_metadata["discover_llm"]`` contract when usable."""
    empty = {
        "writer_rev": None,
        "frame": None,
        "frame_drop_reason": None,
        "frame_slot_drops": {},
        "window_date": None,
        "window_date_precision": None,
        "grounded_subject_ref": None,
        "story_key": _get_story_key(row_or_meta),
    }
    meta = _get_meta(row_or_meta)
    if not meta:
        return empty
    cu = meta.get("discover_llm")
    if not isinstance(cu, Mapping):
        return empty

    writer_rev = cu.get("writer_rev")
    if (
        cu.get("schema_version") != 2
        or type(writer_rev) is not int
        or writer_rev < CU_FRAME_MIN_WRITER_REV
    ):
        return {**empty, "story_key": _get_story_key(row_or_meta, cu)}

    raw_drop = cu.get("frame_drop_reason")
    frame_drop_reason = str(raw_drop).strip() if raw_drop is not None and str(raw_drop).strip() else None
    raw_slot_drops = cu.get("frame_slot_drops")
    frame_slot_drops = dict(raw_slot_drops) if isinstance(raw_slot_drops, Mapping) else {}

    raw_frame = cu.get("frame")
    frame = (
        dict(raw_frame)
        if isinstance(raw_frame, Mapping) and frame_drop_reason is None
        else None
    )

    window_date: Optional[str] = None
    window_date_precision: Optional[str] = None
    if frame is not None and "window_date" not in frame_slot_drops:
        window_date, window_date_precision = parse_window_date_precision(frame.get("window_date"))

    raw_ref = str(cu.get("subject_ref") or "").strip()
    grounded_subject_ref = (
        raw_ref if raw_ref and not raw_ref.lower().startswith("unresolved:") else None
    )

    return {
        "writer_rev": writer_rev,
        "frame": frame,
        "frame_drop_reason": frame_drop_reason,
        "frame_slot_drops": frame_slot_drops,
        "window_date": window_date,
        "window_date_precision": window_date_precision,
        "grounded_subject_ref": grounded_subject_ref,
        "story_key": _get_story_key(row_or_meta, cu),
    }


def classify_market_measure_family(
    title: str,
    *,
    market_metadata: Optional[Mapping[str, Any]] = None,
) -> str:
    """Classify one market into a comparable measure family, reading `#1809` first (#13544)."""
    raw = _fold(title).strip()
    if not raw:
        return MEASURE_FAMILY_EVENT_OR_WINNER
    if isinstance(market_metadata, Mapping):
        explicit = str(market_metadata.get("measure_family") or "").strip().lower()
        if explicit:
            return explicit

    cu_ctx = extract_cu_frame_context(market_metadata)
    frame = cu_ctx["frame"]
    if isinstance(frame, Mapping):
        measure = str(frame.get("measure") or "").strip().lower()
        if measure == "ranking":
            rank_num = _parse_positive_int_rank(frame.get("value"))
            if rank_num == 1:
                return MEASURE_FAMILY_EVENT_OR_WINNER
            if rank_num is not None and rank_num >= 2:
                return MEASURE_FAMILY_RANKED_POSITION
            rank_fallback = _extract_rank_bucket(title)
            if (rank_fallback is not None and rank_fallback >= 2) or _RANKED_POSITION_RE.search(raw):
                return MEASURE_FAMILY_RANKED_POSITION
            if rank_fallback == 1:
                return MEASURE_FAMILY_EVENT_OR_WINNER
        elif measure in _CU_MEASURE_TO_FAMILY:
            if _RANKED_POSITION_RE.search(raw):
                return MEASURE_FAMILY_RANKED_POSITION
            if measure == "release_date" or (
                str(frame.get("horizon_kind") or "").strip().lower() == "open_ended"
                and _TIMING_LADDER_RE.search(raw)
            ):
                return MEASURE_FAMILY_TIMING_LADDER
            return _CU_MEASURE_TO_FAMILY[measure]

    if _TIMING_LADDER_RE.search(raw):
        return MEASURE_FAMILY_TIMING_LADDER
    if _REVIEW_SCORE_RE.search(raw):
        return MEASURE_FAMILY_REVIEW_SCORE
    if _RANKED_POSITION_RE.search(raw):
        return MEASURE_FAMILY_RANKED_POSITION
    if _BOX_OFFICE_RE.search(raw):
        return MEASURE_FAMILY_BOX_OFFICE
    if _PRICE_RECORD_RE.search(raw):
        return MEASURE_FAMILY_PRICE_RECORD
    if _PRICE_OR_COST_RE.search(raw):
        return MEASURE_FAMILY_PRICE_OR_COST
    if _PHYSICAL_QUANTITY_RE.search(raw):
        return MEASURE_FAMILY_PHYSICAL_QUANTITY

    return MEASURE_FAMILY_EVENT_OR_WINNER


def check_scout_single_measure_family(members: Sequence[Any]) -> Optional[str]:
    """Rule: every row in a set must share one kind of measure (#13544)."""
    if len(members) < 2:
        return None
    families: list[str] = []
    seen: set[str] = set()
    frame_measures: list[str] = []
    seen_measures: set[str] = set()
    for row in members:
        meta = _get_meta(row)
        fam = classify_market_measure_family(_get_title(row), market_metadata=meta)
        if fam not in seen:
            seen.add(fam)
            families.append(fam)
        cu_ctx = extract_cu_frame_context(meta)
        frame = cu_ctx["frame"]
        if isinstance(frame, Mapping):
            fm = str(frame.get("measure") or "").strip().lower()
            if fm in _CU_MEASURE_TO_FAMILY and fm not in seen_measures:
                seen_measures.add(fm)
                frame_measures.append(fm)
    if len(families) > 1:
        return f"mixed_measure_families:{'+'.join(families)}"
    if len(frame_measures) > 1:
        return f"mixed_frame_measures:{'+'.join(frame_measures)}"
    return None


def _singularize_token(tok: str) -> str:
    if len(tok) > 4 and tok.endswith("ies"):
        return tok[:-3] + "y"
    if len(tok) > 3 and tok.endswith("s") and not tok.endswith("ss"):
        return tok[:-1]
    return tok


def _extract_rank_bucket(title: str) -> Optional[int]:
    folded = _fold(title)
    # Match more specific higher numbers first so "#2"/"2nd" beats generic words
    for bucket, pat in sorted(_ORDINAL_RANK_PATTERNS, key=lambda x: -x[0]):
        if pat.search(folded):
            return bucket
    return None


def _normalized_core_tokens(title: str, *, strip_ranks: bool = True) -> tuple[str, ...]:
    folded = _fold(title)
    folded = re.sub(r"\b(\w+)'s\b", r"\1", folded)
    if strip_ranks:
        folded = _RANK_STRIP_RE.sub(" ", folded)
    raw_tokens = re.findall(r"[a-z0-9]+", folded)
    cleaned: list[str] = []
    for tok in raw_tokens:
        st = _singularize_token(tok)
        if len(st) <= 1 and not st.isdigit():
            continue
        if st in _CORE_STOPWORDS:
            continue
        cleaned.append(st)
    return tuple(dict.fromkeys(cleaned))


def check_scout_no_repeated_rows(members: Sequence[Any]) -> Optional[str]:
    """Rule: reject sets where any two rows ask the same thing or same-contest ranks (#13544)."""
    if len(members) < 2:
        return None

    parsed: list[tuple[str, Optional[int], tuple[str, ...], frozenset[str], dict[str, Any]]] = []
    for row in members:
        title = _get_title(row)
        cu_ctx = extract_cu_frame_context(row)
        frame = cu_ctx["frame"]
        rank_b: Optional[int] = None
        if isinstance(frame, Mapping) and str(frame.get("measure") or "").strip().lower() == "ranking":
            rank_b = _parse_positive_int_rank(frame.get("value"))
        if rank_b is None:
            rank_b = _extract_rank_bucket(title)
        core = _normalized_core_tokens(title, strip_ranks=True)
        full_tokens = frozenset(_normalized_core_tokens(title, strip_ranks=False))
        parsed.append((title, rank_b, core, full_tokens, cu_ctx))

    for i in range(len(parsed)):
        t_a, rank_a, core_a, full_a, ctx_a = parsed[i]
        set_a = frozenset(core_a)
        for j in range(i + 1, len(parsed)):
            t_b, rank_b, core_b, full_b, ctx_b = parsed[j]
            set_b = frozenset(core_b)

            # 0a. Identical non-empty story_key
            if ctx_a["story_key"] and ctx_a["story_key"] == ctx_b["story_key"]:
                return f"repeated_row_story_key:{t_a[:40]}~{t_b[:40]}"

            # 0b. Frame-grounded join using non-unresolved #1809 subject_ref + measure + window_date
            frame_a = ctx_a["frame"]
            frame_b = ctx_b["frame"]
            ref_a = ctx_a["grounded_subject_ref"]
            ref_b = ctx_b["grounded_subject_ref"]
            if (
                ref_a
                and ref_a == ref_b
                and isinstance(frame_a, Mapping)
                and isinstance(frame_b, Mapping)
            ):
                meas_a = str(frame_a.get("measure") or "").strip().lower()
                meas_b = str(frame_b.get("measure") or "").strip().lower()
                win_drop_a = "window_date" in ctx_a["frame_slot_drops"]
                win_drop_b = "window_date" in ctx_b["frame_slot_drops"]
                same_window = (
                    not win_drop_a
                    and not win_drop_b
                    and ctx_a["window_date"] == ctx_b["window_date"]
                )
                if meas_a and meas_a == meas_b and same_window:
                    if rank_a is not None and rank_b is not None and rank_a != rank_b:
                        return f"repeated_row_ordinal_siblings:{t_a[:40]}~{t_b[:40]}"
                    sig_a = (frame_a.get("comparator"), frame_a.get("value"), frame_a.get("unit"))
                    sig_b = (frame_b.get("comparator"), frame_b.get("value"), frame_b.get("unit"))
                    if meas_a == "ranking" or sig_a == sig_b:
                        return f"repeated_row_frame_duplicate:{t_a[:40]}~{t_b[:40]}"

            if not set_a or not set_b:
                continue

            # 1. Exact same core question once rank/scope/year wrappers are removed
            #    (catches "#1 Searched Movie on Google 2026?" vs "Top 5 Most Searched Movies on Google 2026").
            if core_a == core_b:
                if rank_a is not None and rank_b is not None and rank_a != rank_b:
                    return f"repeated_row_ordinal_siblings:{t_a[:40]}~{t_b[:40]}"
                return f"repeated_row_same_question:{t_a[:40]}~{t_b[:40]}"

            # 2. Subset containment only when every extra token is non-distinguishing filler
            #    (catches "TIME Person of the Year 2026" vs "Will a single person become TIME's 2026 Person of the Year?"
            #    without flagging distinct categories like "Best Actor" vs "Best Supporting Actor").
            inter = set_a & set_b
            union = set_a | set_b
            diff = set_a ^ set_b
            shorter_len = min(len(set_a), len(set_b))
            if (
                shorter_len >= 2
                and (set_a <= set_b or set_b <= set_a)
                and diff
                and diff <= _RESTATEMENT_FILLER_TOKENS
                and len(inter) / max(1, len(union)) >= 0.50
            ):
                if rank_a is not None and rank_b is not None and rank_a != rank_b:
                    return f"repeated_row_ordinal_siblings:{t_a[:40]}~{t_b[:40]}"
                return f"repeated_row_overlap:{t_a[:40]}~{t_b[:40]}"

            # 3. High content-token Jaccard on unstripped tokens (>= 0.85 with >= 4 tokens)
            if len(full_a) >= 4 and len(full_b) >= 4:
                jacc = len(full_a & full_b) / max(1, len(full_a | full_b))
                if jacc >= 0.85:
                    return f"repeated_row_near_duplicate:{t_a[:40]}~{t_b[:40]}"

    return None


@dataclass(frozen=True)
class RowContextLine:
    """Dated, sourced real-world context accompanying one set row (Ruling 196-A)."""

    text: str
    as_of: str
    source: str
    kind: str = "spot_reading"

    def to_dict(self) -> dict[str, str]:
        return {
            "text": self.text,
            "as_of": self.as_of,
            "source": self.source,
            "kind": self.kind,
        }


_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validate_row_context_196a(ctx: Optional[Mapping[str, Any]]) -> bool:
    """Ruling 196-A guard: every rendered context line carries text, ISO date, and source."""
    if ctx is None:
        return True
    if not isinstance(ctx, Mapping):
        return False
    text = str(ctx.get("text") or "").strip()
    as_of = str(ctx.get("as_of") or "").strip()
    source = str(ctx.get("source") or "").strip()
    return bool(text and _ISO_DATE_RE.match(as_of) and source)


def build_row_context_line(row: Any) -> Optional[dict[str, str]]:
    """Return dated factual context for one market row, or ``None`` if absent (196-A).

    Reads ONLY structured verified fields (`market_metadata['row_context']` or
    `market_metadata['current_reading']` / `spot_baseline` carrying both an explicit
    ISO `as_of` date and a non-empty `source`). Never invents or guesses real-world
    prices, rainfall, rankings, or statistics.
    """
    meta = _get_meta(row)
    if not meta:
        return None
    for key in ("row_context", "spot_baseline", "current_reading"):
        raw = meta.get(key)
        if not isinstance(raw, Mapping):
            continue
        text = str(raw.get("text") or "").strip()
        if not text:
            val = raw.get("value")
            unit = str(raw.get("unit") or "").strip()
            label = str(raw.get("label") or "Today").strip()
            if val is not None and str(val).strip():
                text = f"{label}: {val}{(' ' + unit) if unit else ''}".strip()
        as_of_raw = str(raw.get("as_of") or "").strip()[:10]
        source = str(raw.get("source") or "").strip()
        kind = str(raw.get("kind") or "spot_reading").strip() or "spot_reading"
        candidate = {
            "text": text,
            "as_of": as_of_raw,
            "source": source,
            "kind": kind,
        }
        if text and validate_row_context_196a(candidate):
            return candidate
    return None


def build_set_selection_explainer(
    *,
    shown_count: int,
    pool_size: int,
    slug: str,
    noun: str = "markets",
    criterion: str = "top_volume",
) -> dict[str, Any]:
    """Explain why these N markets were shown from a larger pool and link to the rest (#13544)."""
    k = max(0, int(shown_count))
    total = max(k, int(pool_size))
    clean_noun = (noun or "markets").strip() or "markets"
    if total > k:
        reason = (
            f"Top {k} by trading volume out of {total} open {clean_noun} in this group"
            if criterion == "top_volume"
            else f"Showing {k} of {total} open {clean_noun} in this group"
        )
        return {
            "shown_count": k,
            "pool_size": total,
            "criterion": criterion,
            "why_these": reason,
            "see_rest_label": f"See all {total} {clean_noun}",
            "see_rest_href": f"/collections/{slug}",
        }
    return {
        "shown_count": k,
        "pool_size": k,
        "criterion": "all_matching",
        "why_these": f"All {k} open {clean_noun} in this group",
        "see_rest_label": None,
        "see_rest_href": None,
    }


def audit_sets_13544(sets: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Audit a collection of sets against both #13544 gates and return exact counts."""
    mixed_failures: list[dict[str, Any]] = []
    repeat_failures: list[dict[str, Any]] = []
    either_slugs: set[str] = set()

    for s in sets:
        slug = str(s.get("slug") or s.get("name") or "")
        name = str(s.get("name") or s.get("title") or slug)
        members = list(s.get("members") or ())
        m_err = check_scout_single_measure_family(members)
        if m_err:
            families = [
                classify_market_measure_family(_get_title(m), market_metadata=_get_meta(m))
                for m in members
            ]
            mixed_failures.append(
                {"slug": slug, "name": name, "reason": m_err, "families": families}
            )
            either_slugs.add(slug)
        r_err = check_scout_no_repeated_rows(members)
        if r_err:
            repeat_failures.append({"slug": slug, "name": name, "reason": r_err})
            either_slugs.add(slug)

    return {
        "total_sets": len(sets),
        "mixed_measure_count": len(mixed_failures),
        "mixed_measure_failures": mixed_failures,
        "repeated_rows_count": len(repeat_failures),
        "repeated_rows_failures": repeat_failures,
        "either_failed_count": len(either_slugs),
        "clean_count": len(sets) - len(either_slugs),
    }
