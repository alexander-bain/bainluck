"""Report-only public-set split-set audit (#13544 Ask 1).

Per Fable's coordination ruling (2026-11-25T05:27Z on #13580):
- Once Builder E's #13703 is accepted (`discover_fun_scout.detect_scout_split_set`),
  public-set split auditing delegates directly to `detect_scout_split_set` rather
  than running a second gating detector.
- Until #13703 lands, this helper runs strictly in **report-only** mode so public
  sets can be measured without altering Discover output or staging gates.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence

from app.utils import discover_fun_scout
from app.utils.discover_fun_scout import ScoutMarketRow

_SPLIT_NARROW_BRAND_SHOW_PLATFORM_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("spotify", re.compile(r"\bspotify\b", re.IGNORECASE)),
    ("billboard", re.compile(r"\bbillboard\b", re.IGNORECASE)),
    ("critics_choice", re.compile(r"\bcritics['\u2019]?\s+choice\b", re.IGNORECASE)),
    ("the_voice", re.compile(r"\bthe\s+voice(?:\s+season\s+\d+)?\b", re.IGNORECASE)),
    ("golden_globes", re.compile(r"\bgolden\s+globes?\b", re.IGNORECASE)),
    ("emmys", re.compile(r"\bemmys?\b", re.IGNORECASE)),
    ("grammys", re.compile(r"\bgrammys?\b", re.IGNORECASE)),
    ("snl", re.compile(r"\b(?:saturday\s+night\s+live|snl)\b", re.IGNORECASE)),
    ("netflix", re.compile(r"\bnetflix\b", re.IGNORECASE)),
    ("youtube", re.compile(r"\byoutube\b", re.IGNORECASE)),
    ("tiktok", re.compile(r"\btiktok\b", re.IGNORECASE)),
    ("disney_plus", re.compile(r"\bdisney\s*\+", re.IGNORECASE)),
    ("vogue", re.compile(r"\bvogue\b", re.IGNORECASE)),
    ("sports_illustrated", re.compile(r"\bsports\s+illustrated\b", re.IGNORECASE)),
)

_SPLIT_NON_PERSON_BIGRAMS: frozenset[str] = frozenset(
    {
        "album equivalent",
        "angry birds",
        "audio design",
        "avengers doomsday",
        "best actor",
        "best actress",
        "best director",
        "best picture",
        "big game",
        "box office",
        "cliff booth",
        "club festival",
        "comedy series",
        "cover model",
        "cover models",
        "critics choice",
        "drama series",
        "dune part",
        "earth gets",
        "elder scrolls",
        "equivalent units",
        "first week",
        "game awards",
        "game direction",
        "golden globe",
        "golden globes",
        "grand theft",
        "half life",
        "halftime show",
        "heritage festival",
        "human moon",
        "hunger games",
        "iron man",
        "james bond",
        "jazz heritage",
        "limited series",
        "live action",
        "los angeles",
        "major meteor",
        "miami vice",
        "miles morales",
        "millennium prize",
        "minnesota yacht",
        "mobile game",
        "new jersey",
        "new orleans",
        "new york",
        "night live",
        "open world",
        "opening weekend",
        "part three",
        "person year",
        "president united",
        "prime minister",
        "prize problem",
        "prize problems",
        "rotten tomatoes",
        "saturday night",
        "sports personality",
        "star wars",
        "stranger things",
        "super bowl",
        "swimsuit issue",
        "theft auto",
        "the emmys",
        "the oscars",
        "the voice",
        "united states",
        "winds winter",
        "word year",
        "world cup",
        "yacht club",
    }
)

_SPLIT_STOP_CAP_WORDS: frozenset[str] = frozenset(
    {
        "a",
        "album",
        "an",
        "and",
        "another",
        "are",
        "at",
        "awards",
        "best",
        "biggest",
        "by",
        "can",
        "cast",
        "could",
        "cover",
        "did",
        "does",
        "festival",
        "film",
        "first",
        "for",
        "has",
        "have",
        "how",
        "in",
        "is",
        "live",
        "most",
        "movie",
        "music",
        "new",
        "next",
        "of",
        "on",
        "opening",
        "or",
        "radio",
        "score",
        "season",
        "selling",
        "series",
        "song",
        "the",
        "to",
        "top",
        "was",
        "week",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "will",
        "would",
    }
)

_SPLIT_TITLE_SUBJECT_STOP_WORDS: frozenset[str] = (_SPLIT_STOP_CAP_WORDS - {"album", "song"}) | frozenset(
    {
        "america",
        "americas",
        "away",
        "back",
        "box",
        "cards",
        "chart",
        "charts",
        "come",
        "countdown",
        "drop",
        "earth",
        "ever",
        "festival",
        "five",
        "football",
        "gavel",
        "gets",
        "gold",
        "hardest",
        "headliners",
        "home",
        "it",
        "long",
        "milestones",
        "minus",
        "music",
        "night",
        "nominated",
        "office",
        "out",
        "problems",
        "pure",
        "put",
        "rattled",
        "ring",
        "rotten",
        "science",
        "sells",
        "shots",
        "showdown",
        "shows",
        "still",
        "summed",
        "takes",
        "thing",
        "things",
        "tv",
        "up",
        "uses",
        "wild",
        "winners",
        "wins",
        "year",
        "years",
    }
)

_SPLIT_SUBJECT_SYNONYMS: dict[str, tuple[str, ...]] = {
    "album": ("album", "albums", "lp", "record", "records"),
    "albums": ("album", "albums", "lp", "record", "records"),
    "record": ("album", "albums", "lp", "record", "records"),
    "records": ("album", "albums", "lp", "record", "records"),
    "moon": ("moon", "lunar"),
    "lunar": ("moon", "lunar"),
    "song": ("song", "songs"),
    "songs": ("song", "songs"),
    "film": ("film", "films", "movie", "movies"),
    "movie": ("film", "films", "movie", "movies"),
}

_SPLIT_UNIFIED_ENTITY_PATTERNS: tuple[str, ...] = (
    r"\boscars\b",
    r"\bgame\s+awards\b",
    r"\bbig\s+game\b",
    r"\bgoogle\b",
    r"\b(?:gta\s+vi|grand\s+theft\s+auto\s+vi)\b",
    r"\bspacex\b",
    r"\b(?:elon\s+musk|tesla|spacex|starship)\b",
    r"\beurovision\b",
    r"\bengaged\b",
)

_SPLIT_QUOTED_RELEASE_RE = re.compile(r"['\u2018][A-Z0-9][A-Z0-9\s-]{2,}['\u2019]")


def _is_unified_single_entity_set(name: str, titles: Sequence[str]) -> bool:
    if not titles:
        return False
    vs_m = re.match(r"^\s*(.+?)\s+vs\.?\s+(.+?)\s*$", name or "", re.IGNORECASE)
    if vs_m:
        a = re.sub(r"[^a-z0-9]", "", vs_m.group(1).lower())
        b = re.sub(r"[^a-z0-9]", "", vs_m.group(2).lower())
        if a and b and all(
            (
                a in re.sub(r"[^a-z0-9]", "", t.lower())
                or b in re.sub(r"[^a-z0-9]", "", t.lower())
            )
            for t in titles
        ):
            return True
    return any(all(re.search(pat, t, re.IGNORECASE) for t in titles) for pat in _SPLIT_UNIFIED_ENTITY_PATTERNS)


def _extract_subject_named_persons(title: str) -> set[str]:
    """Extract likely ``First Last`` person subjects, ignoring quoted titles and generic phrases."""
    cleaned = re.sub(r'["\u201c\u201d\'][^"\u201c\u201d\']{3,}["\u201c\u201d\']', " ", title or "")
    cleaned = re.sub(r"\([^)]{3,}\)", " ", cleaned)
    persons: set[str] = set()
    for match in re.finditer(r"(?=(\b[A-Z][a-z]+\s+[A-Z][a-z]+\b))", cleaned):
        w1, w2 = match.group(1).lower().split()
        if f"{w1} {w2}" in _SPLIT_NON_PERSON_BIGRAMS:
            continue
        if w1 in _SPLIT_STOP_CAP_WORDS or w2 in _SPLIT_STOP_CAP_WORDS:
            continue
        persons.add(f"{w1} {w2}")
    return persons


def _extract_title_subject_tokens(name: str) -> list[str]:
    """Extract concrete non-stop subject tokens from a set headline."""
    raw = re.sub(r"[\u2018\u2019']s\b", "", (name or "").lower())
    tokens: list[str] = []
    for tok in re.findall(r"[a-z]+", raw):
        if len(tok) < 3 or tok in _SPLIT_TITLE_SUBJECT_STOP_WORDS:
            continue
        if tok not in tokens:
            tokens.append(tok)
    return tokens


def _member_matches_subject_token(member_title: str, token: str) -> bool:
    aliases = _SPLIT_SUBJECT_SYNONYMS.get(token, (token,))
    for alias in aliases:
        if re.search(rf"\b{re.escape(alias)}\b", member_title, re.IGNORECASE):
            return True
    if token in {"album", "albums", "record", "records"} and _SPLIT_QUOTED_RELEASE_RE.search(member_title):
        return True
    return False


def _extract_colon_prefix(title: str) -> str | None:
    """Normalize a concrete multi-word prefix before the first colon (if any)."""
    if ":" not in (title or ""):
        return None
    left = title.split(":", 1)[0].strip().lower()
    left = re.sub(r"\b20\d\d\b|\bseason\s+\d+\b", "", left).strip(" .?!-\u00b7")
    words = [w for w in re.findall(r"[a-z0-9]+", left) if w not in {"the", "a", "an"}]
    if len(words) < 2:
        return None
    return " ".join(words[:3])


def _extract_colon_template_suffix(title: str) -> str | None:
    """Extract normalized 1-2 word structural suffix after the last colon (if any)."""
    if ":" not in (title or ""):
        return None
    right = title.rsplit(":", 1)[-1].strip().lower()
    right = re.sub(r"\b20\d\d\b", "", right).strip(" .?!-")
    words = re.findall(r"[a-z]+", right)
    if not words or len(words) > 3:
        return None
    if len(words) == 1 and words[0] in {"winner", "winners", "nominations", "score", "price"}:
        return None
    normalized = [w[:-1] if len(w) > 4 and w.endswith("s") and not w.endswith("ss") else w for w in words]
    return " ".join(normalized[:2])


def _interim_detect_split_set_report_only(
    name: str,
    members: Sequence[ScoutMarketRow | Mapping[str, Any]],
) -> str | None:
    """Interim report-only split detector used strictly for auditing until #13703 lands."""
    titles = [
        str(m.get("title") or m.get("name") or "") if isinstance(m, Mapping) else str(m.title or "")
        for m in members
    ]
    n = len(titles)
    if n < 3 or _is_unified_single_entity_set(name, titles):
        return None

    subject_tokens = _extract_title_subject_tokens(name)
    if subject_tokens:
        member_matched_any = [
            any(_member_matches_subject_token(t, tok) for tok in subject_tokens)
            for t in titles
        ]
        if not all(member_matched_any):
            for tok in subject_tokens:
                hits = sum(1 for t in titles if _member_matches_subject_token(t, tok))
                if 2 <= hits < n:
                    return f"split_set:title_subject_outlier:{tok}({hits}/{n})"

    person_counts: dict[str, int] = {}
    for t in titles:
        for person in _extract_subject_named_persons(t):
            person_counts[person] = person_counts.get(person, 0) + 1
    for person, count in sorted(person_counts.items()):
        if 2 <= count < n:
            return f"split_set:named_person_cluster:{person}({count}/{n})"

    prefix_counts: dict[str, int] = {}
    for t in titles:
        pref = _extract_colon_prefix(t)
        if pref:
            prefix_counts[pref] = prefix_counts.get(pref, 0) + 1
    for pref, count in sorted(prefix_counts.items()):
        if 2 <= count < n:
            return f"split_set:shared_prefix_cluster:{pref}({count}/{n})"

    for brand_name, pat in _SPLIT_NARROW_BRAND_SHOW_PLATFORM_PATTERNS:
        hits = sum(1 for t in titles if pat.search(t))
        if 2 <= hits < n:
            return f"split_set:narrower_brand_cluster:{brand_name}({hits}/{n})"

    suffix_counts: dict[str, int] = {}
    for t in titles:
        suf = _extract_colon_template_suffix(t)
        if suf:
            suffix_counts[suf] = suffix_counts.get(suf, 0) + 1
    for suf, count in sorted(suffix_counts.items()):
        if 2 <= count < n:
            return f"split_set:template_suffix_mismatch:{suf}({count}/{n})"

    rank_nums: list[int] = []
    for t in titles:
        tl = t.lower()
        if "rank among" in tl:
            continue
        if re.search(r"\b(?:biggest|highest|largest|most)\b", tl) and not re.search(
            r"\b\d+(?:st|nd|rd|th)\b", tl
        ):
            rank_nums.append(1)
        m_ord = re.search(r"\b(\d+)(?:st|nd|rd|th)\s+(?:biggest|highest|largest|most)\b", tl)
        if m_ord:
            rank_nums.append(int(m_ord.group(1)))
    if len(rank_nums) >= 2 and (max(rank_nums) - min(rank_nums) + 1) > len(set(rank_nums)):
        return f"split_set:ordinal_rank_gap:{sorted(rank_nums)}"

    return None


def _coerce_scout_rows(
    members: Sequence[ScoutMarketRow | Mapping[str, Any]],
) -> list[ScoutMarketRow]:
    fallback_dt = datetime.now(timezone.utc) + timedelta(days=90)
    rows: list[ScoutMarketRow] = []
    for idx, m in enumerate(members, 1):
        if isinstance(m, ScoutMarketRow):
            rows.append(m)
            continue
        rows.append(
            ScoutMarketRow(
                market_id=int(m.get("market_id") or m.get("id") or idx),
                source=str(m.get("source") or "kalshi"),
                title=str(m.get("title") or m.get("name") or ""),
                status=str(m.get("status") or "open"),
                category=str(m.get("category") or "culture"),
                resolution_date=m.get("resolution_date") if isinstance(m.get("resolution_date"), datetime) else fallback_dt,
                volume=float(m.get("volume") or 0.0),
                volume_24h=float(m.get("volume_24h") or 0.0),
                market_metadata=m.get("market_metadata") if isinstance(m.get("market_metadata"), Mapping) else None,
            )
        )
    return rows


def audit_public_set_split_report_only(
    set_title: str,
    members: Sequence[ScoutMarketRow | Mapping[str, Any]],
) -> dict[str, Any]:
    """Audit one public set strictly in report-only mode (#13544 Ask 1).

    Delegates to Builder E's ``discover_fun_scout.detect_scout_split_set`` when
    available (#13703); falls back to the interim report-only detector until then.
    Never rejects or mutates served sets.
    """
    builder_detector = getattr(discover_fun_scout, "detect_scout_split_set", None)
    if callable(builder_detector):
        rows = _coerce_scout_rows(members)
        finding = builder_detector(set_title, rows)
        reason = None if finding is None else str(getattr(finding, "reason", None) or finding)
        return {
            "mode": "report_only",
            "detector": "detect_scout_split_set",
            "is_split": finding is not None,
            "reason": reason,
            "shared_feature": getattr(finding, "shared_feature", None) if finding is not None else None,
        }

    reason = _interim_detect_split_set_report_only(set_title, members)
    return {
        "mode": "report_only",
        "detector": "interim_report_only",
        "is_split": reason is not None,
        "reason": reason,
        "shared_feature": None,
    }


def audit_served_public_sets_report_only(
    served_items: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Run report-only split-set audit across grouped bundles in a served Discover list."""
    findings: list[dict[str, Any]] = []
    for item in served_items:
        if not isinstance(item, Mapping) or item.get("type") != "bundle":
            continue
        data = item.get("data")
        if not isinstance(data, Mapping):
            continue
        set_title = str(data.get("title") or data.get("name") or item.get("headline") or "").strip()
        set_id = str(data.get("id") or data.get("slug") or "")
        members: list[Mapping[str, Any]] = []
        raw_items = data.get("items")
        if isinstance(raw_items, Sequence) and not isinstance(raw_items, (str, bytes)):
            for idx, entry in enumerate(raw_items, 1):
                if not isinstance(entry, Mapping):
                    continue
                inner = entry.get("data") if isinstance(entry.get("data"), Mapping) else entry
                title = str(inner.get("name") or inner.get("title") or "").strip()
                if title:
                    members.append({"market_id": inner.get("id") or idx, "title": title})
        if not members and isinstance(data.get("roundup"), Mapping):
            rows = data["roundup"].get("rows")
            if isinstance(rows, Sequence) and not isinstance(rows, (str, bytes)):
                for idx, row in enumerate(rows, 1):
                    if not isinstance(row, Mapping):
                        continue
                    title = str(row.get("title") or row.get("label") or "").strip()
                    if title:
                        members.append({"market_id": idx, "title": title})
        if len(members) < 3:
            continue
        res = audit_public_set_split_report_only(set_title, members)
        if res["is_split"]:
            findings.append({"set_id": set_id, "title": set_title, **res})
    return findings
