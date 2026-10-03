"""Theme collection definitions — #9935 slice P1 (pure, inert).

PILLARS MATCHING · DISCOVER · TRUTH. SHIP (#9935): an AI or Oscars preview opens
the same complete, correctly scoped collection on a URL that still works when
membership changes. This module is the inert rider of that queued ship: it
changes nothing a reader sees on its own. Nothing here writes, schedules,
routes, publishes or executes SQL. The contract is Authority's
``docs/theme-collection-producer-contract-9935.md`` (v3.1); section numbers
below refer to it.

What lives here:

* ``ThemeDefinition`` + ``REGISTRY`` — a registry of SUBJECTS (finite
  ``oscars-2027``, continuing ``ai``), never a list of members (the
  ``TENNIS_DRAWS`` precedent: nobody writes a list of members, not that nobody
  names the draws).
* ``build_theme_slug`` / ``parse_theme_slug`` — the canonical slug and its
  byte-for-byte round-trip parser (§1). P2's ``edition_for_slug`` calls the
  parser after its NFL/MLB branches.
* ``decide(market, now=...)`` for ``oscars-edition@1`` and ``ai-subject@1``
  (§3): own-row clauses in order, a closed reason enum and clause-by-clause
  evidence. ``now`` is always explicit.
* ``candidate_population`` — the §4 gather arms as Core ``select()``
  expressions. They are BUILT, never executed, in P1. The prior-decision arm
  names the proposed ``container_member_decisions`` table through a lightweight
  ``table()`` clause: no model, no import of a future module, nothing
  initialised at startup.
* ``resolve_collection_target`` — §5 steps 1–3 over candidate rows the caller
  supplies. Publication is never read here: publication can REMOVE a link
  (step 4, P2) but never REDIRECT one.

Read-only imports: ``event_awards.CEREMONIES`` / ``classify_market`` /
``edition_year`` (its ticker arm only) and
``futures_liveness.market_reads_settled``. Neither module is edited. This
module does not import ``discover_bundles``: the hydration gate and the fold
are P2's, called there by identity.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Mapping, Optional

from app.utils.event_awards import CEREMONIES, classify_market, edition_year
from app.utils.futures_liveness import market_reads_settled

# ---------------------------------------------------------------------------
# Closed vocabulary (§3). Admitted / excluded / withheld are decision-row
# reasons; hydration withholds are computed at read time (P2) and never written
# as decision rows.
# ---------------------------------------------------------------------------

OUTCOME_ADMITTED = "admitted"
OUTCOME_EXCLUDED = "excluded"
OUTCOME_WITHHELD = "withheld"
OUTCOMES = frozenset({OUTCOME_ADMITTED, OUTCOME_EXCLUDED, OUTCOME_WITHHELD})

ADMITTED_TICKER_EDITION = "admitted_ticker_edition"
ADMITTED_TITLE_EDITION = "admitted_title_edition"
ADMITTED_VENUE_EVENT_EDITION = "admitted_venue_event_edition"
ADMITTED_ENTITY_SIGNAL = "admitted_entity_signal"

NOT_THIS_CEREMONY = "not_this_ceremony"
# The AI analogue of `not_this_ceremony`: the row carries no entity term at all.
# A first-pass gather never offers such a row (the entity pattern IS the gather),
# but the prior-decision arm re-decides a renamed row, and its exclusion needs a
# reason that does not claim a false friend was seen.
NOT_THIS_SUBJECT = "not_this_subject"
WRONG_CATEGORY = "wrong_category"
OTHER_EDITION = "other_edition"
LEXICAL_FALSE_FRIEND = "lexical_false_friend"
RESOLVED_BEYOND_RETENTION = "resolved_beyond_retention"
RESOLVED_SETTLE_TIME_UNKNOWN = "resolved_settle_time_unknown"
CONTAINER_MEMBER_WITHDRAWN = "container_member_withdrawn"

EDITION_UNKNOWN = "edition_unknown"

ADMITTED_REASONS = frozenset(
    {
        ADMITTED_TICKER_EDITION,
        ADMITTED_TITLE_EDITION,
        ADMITTED_VENUE_EVENT_EDITION,
        ADMITTED_ENTITY_SIGNAL,
    }
)
EXCLUDED_REASONS = frozenset(
    {
        NOT_THIS_CEREMONY,
        NOT_THIS_SUBJECT,
        WRONG_CATEGORY,
        OTHER_EDITION,
        LEXICAL_FALSE_FRIEND,
        RESOLVED_BEYOND_RETENTION,
        RESOLVED_SETTLE_TIME_UNKNOWN,
        CONTAINER_MEMBER_WITHDRAWN,
    }
)
WITHHELD_REASONS = frozenset({EDITION_UNKNOWN})
DECISION_REASONS = ADMITTED_REASONS | EXCLUDED_REASONS | WITHHELD_REASONS

#: Read-time withholds (P2 hydration). Listed so the vocabulary is closed in one
#: place; never emitted by ``decide()``.
HYDRATION_WITHHOLDS = frozenset(
    {
        "row_missing",
        "unserializable",
        "suppressed",
        "low_quality",
        "public_source_disagreement",
    }
)

#: Retention reasons only a continuing definition may emit (§3, repair B).
CONTINUING_ONLY_REASONS = frozenset(
    {RESOLVED_BEYOND_RETENTION, RESOLVED_SETTLE_TIME_UNKNOWN}
)

# §5 resolver reasons (ops debug only, never reader text — notice 34).
SWINGS_NOT_A_COLLECTION = "swings_not_a_collection"
PREVIEW_EMPTY = "preview_empty"
MAPPED_TARGET_ABSENT = "mapped_target_absent"
MAPPED_TARGET_AMBIGUOUS = "mapped_target_ambiguous"
PREVIEW_SPANS_COLLECTIONS = "preview_spans_collections"
NO_MAP_ENTRY_AMBIGUOUS = "no_map_entry_ambiguous"
TARGET_SLUG_NOT_THEME = "target_slug_not_theme"
RESOLVER_REASONS = frozenset(
    {
        SWINGS_NOT_A_COLLECTION,
        PREVIEW_EMPTY,
        MAPPED_TARGET_ABSENT,
        MAPPED_TARGET_AMBIGUOUS,
        PREVIEW_SPANS_COLLECTIONS,
        NO_MAP_ENTRY_AMBIGUOUS,
        TARGET_SLUG_NOT_THEME,
    }
)

#: The swings bundler's feed key (``discover_bundles``: ``story_key: "swings"``,
#: grouped by price movement across subjects). A swings bundle never carries a
#: collection ref, even when every member happens to sit in one collection.
SWINGS_FEED_KEY = "swings"

SCOPE_FINITE = "finite"
SCOPE_CONTINUING = "continuing"

#: Continuing-scope retention (§3 ``ai-subject@1`` clause 3; Discover's N).
AI_RETENTION_DAYS = 14

# ---------------------------------------------------------------------------
# Patterns.
# ---------------------------------------------------------------------------

_OSCARS = CEREMONIES["oscars"]

#: Clause 1's title-structural ceremony form: the title BEGINS with the ceremony
#: word ("Oscars 2027: …") or names an ordinal edition ("… at the 99th Academy
#: Awards"). The bare substring "oscar" anywhere in a name is never sufficient.
#: Python flavour; ``OSCARS_STRUCTURAL_PG`` is the same pattern for Postgres
#: ``~*``, where ``\b`` is a BACKSPACE and the word boundary is ``\y``.
OSCARS_STRUCTURAL_RE = re.compile(
    r"^(oscars?|academy awards?)\b|\b\d{1,3}(st|nd|rd|th) academy awards?\b",
    re.IGNORECASE,
)
OSCARS_STRUCTURAL_PG = OSCARS_STRUCTURAL_RE.pattern.replace(r"\b", r"\y")

_CEREMONY_WORD = r"(?:oscars?|academy awards?)"
# (b) a year adjacent to the ceremony word, either side: "Oscars 2027", "2026 Oscar".
_YEAR_ADJACENT_RE = re.compile(
    rf"\b(?:{_CEREMONY_WORD}\s*[:(,\-]?\s*((?:19|20)\d{{2}})\b"
    rf"|((?:19|20)\d{{2}})\s+{_CEREMONY_WORD}\b)",
    re.IGNORECASE,
)
# (c) "99th Academy Awards" -> 1928 + 99.
_ORDINAL_RE = re.compile(r"\b(\d{1,3})(?:st|nd|rd|th)\s+academy awards?\b", re.IGNORECASE)


def _other_ceremony_pattern() -> re.Pattern:
    terms: set[str] = set()
    for key, cfg in CEREMONIES.items():
        if key == "oscars":
            continue
        for term in (cfg.slug, *cfg.aliases):
            t = term.replace("-", " ").strip().lower()
            if t.startswith("the "):
                t = t[4:]
            terms.add(re.escape(t))
    alt = "|".join(sorted(terms, key=len, reverse=True))
    return re.compile(rf"^(?:the\s+)?(?:{alt})s?\b", re.IGNORECASE)


#: A title that structurally names a DIFFERENT ceremony ("Grammys 2027: …").
#: Derived from ``CEREMONIES`` so a new ceremony is covered without an edit here.
OTHER_CEREMONY_STRUCTURAL_RE = _other_ceremony_pattern()

#: Kalshi Oscars category codes whose title keyword is unambiguous. A code here
#: whose title names a category but lacks the keyword is a ``venue_title_conflict``
#: FLAG (clause 5, never an exclusion). Categories, not members; an unknown code
#: is recorded as unchecked, never guessed.
_OSCAR_TICKER_CATEGORY_KEYWORDS: Mapping[str, re.Pattern] = {
    "PIC": re.compile(r"\bpicture\b", re.IGNORECASE),
    "ACTO": re.compile(r"\bactor\b", re.IGNORECASE),
    "ACTR": re.compile(r"\bactress\b", re.IGNORECASE),
    "DIR": re.compile(r"\bdirect(?:or|ing)\b", re.IGNORECASE),
    "VIS": re.compile(r"\bvisual effects?\b", re.IGNORECASE),
}

#: ``ai-subject@1`` clause 1. ``claude`` carries the #8742 deny clause;
#: ``gemini`` is handled separately because it counts only with ADJACENT context.
_AI_ENTITY_RE = re.compile(
    r"\b(openai|anthropic|claude|gpt-?\d|chatgpt|deepseek|grok|xai|ai model|best ai|agi)\b",
    re.IGNORECASE,
)
_CLAUDE_DENY_RE = re.compile(
    r"(?:\bjean[\s-]+claude\b|\bclaude\s+(?:monet|debussy|makelele|puel|lelouch)\b)",
    re.IGNORECASE,
)
_GEMINI_RE = re.compile(r"\bgemini\b", re.IGNORECASE)
_GEMINI_ADJACENT_RE = re.compile(
    r"\bgoogle\s+gemini\b|\bgemini\s+\d|\bgemini\s+(?:pro|flash|ultra|app|model)\b",
    re.IGNORECASE,
)
#: A Kalshi series stem whose own ticker names the entity (clause 2's second arm).
AI_KALSHI_ENTITY_STEMS = ("KXCLAUDE", "KXGEMINI", "KXOPUS", "KXOAIANTH", "KXIPOOPENAI")
AI_SECOND_SIGNAL_CATEGORIES = frozenset({"tech", "economics"})
#: The gather's entity pattern (§4 arm a), Postgres flavour of clause 1's terms.
AI_ENTITY_PG = (
    r"\y(openai|anthropic|claude|gpt-?\d|chatgpt|deepseek|gemini|grok|xai|ai model|best ai|agi)\y"
)

# ---------------------------------------------------------------------------
# Decision + evidence.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Decision:
    outcome: str
    reason: str
    rule_version: str
    #: ``event_edges.class`` for an admitted member; None otherwise.
    edge_class: Optional[str]
    evidence: dict

    @property
    def admitted(self) -> bool:
        return self.outcome == OUTCOME_ADMITTED


def _attr(market: Any, name: str, default: Any = None) -> Any:
    return getattr(market, name, default)


def _metadata(market: Any) -> dict:
    meta = _attr(market, "market_metadata")
    return meta if isinstance(meta, dict) else {}


def _iso(value: Any) -> Any:
    return value.isoformat() if isinstance(value, datetime) else value


def _aware(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


class _Evidence:
    def __init__(self, market: Any) -> None:
        self.clauses: list[dict] = []
        self.flags: list[str] = []
        self.fields: dict[str, str] = {}
        self.inputs = {
            "id": _attr(market, "id"),
            "external_id": _attr(market, "external_id"),
            "source": _attr(market, "source"),
            "llm_sport_category": _attr(market, "llm_sport_category"),
            "canonical_market_key": _attr(market, "canonical_market_key"),
            "resolution_date": _iso(_attr(market, "resolution_date")),
            "name": _attr(market, "name"),
            "event_title": _metadata(market).get("event_title"),
            "status": _attr(market, "status"),
            "settled_at": _iso(_attr(market, "settled_at")),
        }

    def clause(self, clause: str, input: Any, result: Any) -> None:
        self.clauses.append({"clause": clause, "input": input, "result": result})

    def flag(self, name: str) -> None:
        if name not in self.flags:
            self.flags.append(name)

    def build(self) -> dict:
        return {
            "clauses": list(self.clauses),
            "inputs": dict(self.inputs),
            "fields": dict(self.fields),
            "flags": list(self.flags),
        }


def _decision(defn: "ThemeDefinition", outcome: str, reason: str, ev: _Evidence,
              edge_class: Optional[str] = None) -> Decision:
    return Decision(outcome, reason, defn.rule_version, edge_class, ev.build())


# ---------------------------------------------------------------------------
# oscars-edition@1 (finite). No retention clause and no settled_at read: a
# settled member is admitted with its result however long ago it settled.
# ---------------------------------------------------------------------------


def _is_kalshi_oscars_ticker(market: Any) -> bool:
    return (_attr(market, "source") == "kalshi"
            and (_attr(market, "external_id") or "").upper().startswith(_OSCARS.ticker))


def _title_edition(text: Optional[str]) -> Optional[tuple[int, str]]:
    """(year, rule) from a title: (b) a year adjacent to the ceremony word, else
    (c) the ordinal Academy Awards. None when the title states neither."""
    if not text:
        return None
    m = _YEAR_ADJACENT_RE.search(text)
    if m:
        return int(m.group(1) or m.group(2)), "title_year_adjacent"
    m = _ORDINAL_RE.search(text)
    if m:
        return 1928 + int(m.group(1)), "ordinal_academy_awards"
    return None


def _ticker_category_code(external_id: str) -> str:
    code = external_id.upper()[len(_OSCARS.ticker):].split("-", 1)[0]
    return code[3:] if code.startswith("NOM") else code


def _decide_oscars(defn: "ThemeDefinition", market: Any, *, now: datetime) -> Decision:
    del now  # finite scope: the clock never enters an Oscars decision
    ev = _Evidence(market)
    name = _attr(market, "name") or ""
    event_title = _metadata(market).get("event_title") or ""
    is_ticker = _is_kalshi_oscars_ticker(market)

    # Clause 1 — ceremony. The row's own name wins over the venue's event title.
    name_structural = bool(OSCARS_STRUCTURAL_RE.search(name))
    name_other = bool(OTHER_CEREMONY_STRUCTURAL_RE.search(name))
    title_structural = bool(event_title and OSCARS_STRUCTURAL_RE.search(event_title))
    if is_ticker:
        ev.fields["ceremony"] = "external_id"
    elif name_other:
        if title_structural:
            ev.flag("venue_title_conflict")
        ev.fields["ceremony"] = "name"
        ev.clause("ceremony", {"name": name, "event_title": event_title or None},
                  "other_ceremony_in_name")
        return _decision(defn, OUTCOME_EXCLUDED, NOT_THIS_CEREMONY, ev)
    elif name_structural:
        ev.fields["ceremony"] = "name"
    elif title_structural:
        ev.fields["ceremony"] = "event_title"
    else:
        ev.clause("ceremony", {"external_id": _attr(market, "external_id"), "name": name,
                               "event_title": event_title or None}, "fail")
        return _decision(defn, OUTCOME_EXCLUDED, NOT_THIS_CEREMONY, ev)
    ev.clause("ceremony", ev.fields["ceremony"], "pass")

    # Clause 2 — category gate (second independent signal).
    category = _attr(market, "llm_sport_category")
    if category != "entertainment":
        ev.clause("category_gate", category, "fail")
        return _decision(defn, OUTCOME_EXCLUDED, WRONG_CATEGORY, ev)
    ev.clause("category_gate", category, "pass")

    # Clause 3 — edition, strict precedence: ticker (a), then the name's (b)/(c),
    # then the venue event title's (b)/(c). Name beats event title clause by
    # clause; a disagreement is flagged, never resolved toward the title.
    external_id = _attr(market, "external_id") or ""
    ticker_year = edition_year(external_id, None) if is_ticker else None
    name_ed = _title_edition(name)
    title_ed = _title_edition(event_title)
    year: Optional[int] = None
    if ticker_year is not None:
        year, rule, ev.fields["edition"] = 2000 + ticker_year, "ticker_token", "external_id"
        if name_ed and name_ed[0] != year:
            ev.flag("venue_title_conflict")
    elif name_ed is not None:
        (year, rule), ev.fields["edition"] = name_ed, "name"
    elif title_ed is not None:
        (year, rule), ev.fields["edition"] = title_ed, "event_title"
    if year is not None and title_ed is not None and title_ed[0] != year:
        ev.flag("venue_title_conflict")
    if year is None:
        ev.clause("edition", {"ticker": None, "name": None, "event_title": None}, "unknown")
        return _decision(defn, OUTCOME_WITHHELD, EDITION_UNKNOWN, ev)

    # The resolution date is a consistency check only, never edition evidence.
    resolution_date = _aware(_attr(market, "resolution_date"))
    if resolution_date is not None and year == defn.edition:
        placeholder = (resolution_date.month, resolution_date.day) == (12, 31)
        if not placeholder and resolution_date > defn.edition_backstop:
            ev.clause("edition", {"year": year, "rule": rule,
                                  "resolution_date": resolution_date.isoformat()},
                      "inconsistent_with_backstop")
            return _decision(defn, OUTCOME_WITHHELD, EDITION_UNKNOWN, ev)
    if year != defn.edition:
        ev.clause("edition", {"year": year, "rule": rule}, "other_edition")
        return _decision(defn, OUTCOME_EXCLUDED, OTHER_EDITION, ev)
    ev.clause("edition", {"year": year, "rule": rule}, "pass")

    # Clause 4 — class (a section, never an exclusion).
    kind = classify_market(external_id, name)
    edge_class = {"category": "title", "nominations": "advancement"}.get(kind, "side_question")
    ev.clause("class", kind, edge_class)

    # Clause 5 — ticker category vs title (flag only).
    if is_ticker:
        code = _ticker_category_code(external_id)
        keyword = _OSCAR_TICKER_CATEGORY_KEYWORDS.get(code)
        if keyword is None:
            ev.clause("venue_title_conflict", code, "unchecked")
        elif kind == "category" and not keyword.search(name):
            ev.flag("venue_title_conflict")
            ev.clause("venue_title_conflict", code, "conflict")
        else:
            ev.clause("venue_title_conflict", code, "agree")

    if "event_title" in (ev.fields.get("ceremony"), ev.fields.get("edition")):
        reason = ADMITTED_VENUE_EVENT_EDITION
    elif ev.fields["edition"] == "external_id":
        reason = ADMITTED_TICKER_EDITION
    else:
        reason = ADMITTED_TITLE_EDITION
    return _decision(defn, OUTCOME_ADMITTED, reason, ev, edge_class)


# ---------------------------------------------------------------------------
# ai-subject@1 (continuing).
# ---------------------------------------------------------------------------


def ai_entity_hits(name: str) -> tuple[list[str], list[str]]:
    """(admitting terms, denied terms) for clause 1."""
    hits: list[str] = []
    denied: list[str] = []
    for m in _AI_ENTITY_RE.finditer(name):
        term = m.group(1).lower()
        if term == "claude" and _CLAUDE_DENY_RE.search(name):
            denied.append(term)
        else:
            hits.append(term)
    if _GEMINI_RE.search(name):
        if _GEMINI_ADJACENT_RE.search(name):
            hits.append("gemini")
        else:
            denied.append("gemini")
    return hits, denied


def _decide_ai(defn: "ThemeDefinition", market: Any, *, now: datetime) -> Decision:
    ev = _Evidence(market)
    name = _attr(market, "name") or ""

    hits, denied = ai_entity_hits(name)
    if not hits:
        ev.clause("entity", {"name": name, "denied": denied}, "fail")
        reason = LEXICAL_FALSE_FRIEND if denied else NOT_THIS_SUBJECT
        return _decision(defn, OUTCOME_EXCLUDED, reason, ev)
    ev.clause("entity", {"hits": hits, "denied": denied}, "pass")

    category = _attr(market, "llm_sport_category")
    external_id = (_attr(market, "external_id") or "").upper()
    stem = next((s for s in AI_KALSHI_ENTITY_STEMS
                 if _attr(market, "source") == "kalshi" and external_id.startswith(s)), None)
    if category in AI_SECOND_SIGNAL_CATEGORIES:
        ev.clause("second_signal", {"llm_sport_category": category}, "pass")
    elif stem is not None:
        ev.clause("second_signal", {"kalshi_entity_stem": stem}, "pass")
    else:
        ev.clause("second_signal", {"llm_sport_category": category}, "fail")
        return _decision(defn, OUTCOME_EXCLUDED, WRONG_CATEGORY, ev)

    # Clause 3 — retention. The clock is settled_at and nothing else; the
    # resolution date is a schedule and is never read here.
    settled_arm: Optional[str] = None
    if _attr(market, "status") == "resolved":
        settled_arm = "status_resolved"
    elif market_reads_settled(market, now=now):
        settled_arm = "market_reads_settled"
    if settled_arm is None:
        ev.clause("retention", {"settled": False}, "open")
        return _decision(defn, OUTCOME_ADMITTED, ADMITTED_ENTITY_SIGNAL, ev, "side_question")
    settled_at = _aware(_attr(market, "settled_at"))
    if settled_at is None:
        ev.clause("retention", {"settled_arm": settled_arm, "settled_at": None},
                  "settle_time_unknown")
        return _decision(defn, OUTCOME_EXCLUDED, RESOLVED_SETTLE_TIME_UNKNOWN, ev)
    within = settled_at >= _aware(now) - timedelta(days=defn.retention_days)
    ev.clause("retention", {"settled_arm": settled_arm, "settled_at": settled_at.isoformat(),
                            "retention_days": defn.retention_days},
              "within" if within else "beyond")
    if not within:
        return _decision(defn, OUTCOME_EXCLUDED, RESOLVED_BEYOND_RETENTION, ev)
    return _decision(defn, OUTCOME_ADMITTED, ADMITTED_ENTITY_SIGNAL, ev, "side_question")


# ---------------------------------------------------------------------------
# Candidate populations (§4). Built, never executed, in P1.
# ---------------------------------------------------------------------------


def _prior_decision_arm(container_id: int):
    from sqlalchemy import column, select, table

    decisions = table(
        "container_member_decisions",
        column("container_id"),
        column("child_type"),
        column("child_id"),
    )
    return select(decisions.c.child_id.label("id")).where(
        decisions.c.container_id == container_id,
        decisions.c.child_type == "market",
    )


def _oscars_population(defn: "ThemeDefinition", *, container_id: int, now: datetime) -> dict:
    """(K) the ceremony's own ticker family + (P) structurally titled Polymarket
    rows, any status, no settled/created/resolution cutoff, + prior decisions."""
    del now  # finite scope has no time cutoff
    from sqlalchemy import or_, select

    from app.models.models import FuturesMarket as FM

    return {
        "kalshi_ticker_family": select(FM.id).where(
            FM.source == "kalshi", FM.external_id.like(f"{_OSCARS.ticker}%")
        ),
        "polymarket_structural_title": select(FM.id).where(
            FM.source == "polymarket",
            or_(
                FM.name.regexp_match(OSCARS_STRUCTURAL_PG, flags="i"),
                FM.market_metadata["event_title"].astext.regexp_match(
                    OSCARS_STRUCTURAL_PG, flags="i"
                ),
            ),
        ),
        "prior_decision": _prior_decision_arm(container_id),
    }


def _ai_population(defn: "ThemeDefinition", *, container_id: int, now: datetime) -> dict:
    """(a) open entity rows ∪ (b) resolved entity rows settled within retention,
    any category, + prior decisions (which is how retirement is re-decided)."""
    from sqlalchemy import select

    from app.models.models import FuturesMarket as FM

    entity = FM.name.regexp_match(AI_ENTITY_PG, flags="i")
    return {
        "open_entity": select(FM.id).where(entity, FM.status == "open"),
        "resolved_within_retention": select(FM.id).where(
            entity,
            FM.status == "resolved",
            FM.settled_at >= _aware(now) - timedelta(days=defn.retention_days),
        ),
        "prior_decision": _prior_decision_arm(container_id),
    }


def candidate_population(defn: "ThemeDefinition", *, container_id: int, now: datetime) -> dict:
    """The definition's own gather arms, name -> Core ``select`` of market ids.
    The writer (P2) unions them and pages by id cursor; P1 never executes them."""
    return defn.population(defn, container_id=container_id, now=now)


# ---------------------------------------------------------------------------
# Definitions + registry (§1).
# ---------------------------------------------------------------------------


def build_theme_slug(subject: str, scope: str, edition: Optional[int] = None) -> str:
    if scope == SCOPE_FINITE:
        if edition is None:
            raise ValueError("a finite theme needs an edition")
        return f"{subject}-{edition}"
    if scope == SCOPE_CONTINUING:
        if edition is not None:
            raise ValueError("a continuing theme has no edition")
        return subject
    raise ValueError(f"unknown scope {scope!r}")


@dataclass(frozen=True)
class ThemeDefinition:
    subject: str
    scope: str
    rule_version: str
    container_kind: str
    category: str
    display_name: str
    decider: Callable[..., Decision]
    population: Callable[..., dict]
    edition: Optional[int] = None
    #: Finite only: the edition's resolution backstop (a deadline bound, never a
    #: published date).
    edition_backstop: Optional[datetime] = None
    #: Continuing only.
    retention_days: Optional[int] = None
    #: ``story_key`` values that map to this subject (§5). Never a group_id.
    feed_keys: tuple[str, ...] = field(default_factory=tuple)

    def slug(self) -> str:
        return build_theme_slug(self.subject, self.scope, self.edition)

    def decide(self, market: Any, *, now: datetime) -> Decision:
        return self.decider(self, market, now=now)


OSCARS_2027 = ThemeDefinition(
    subject="oscars",
    scope=SCOPE_FINITE,
    edition=2027,
    edition_backstop=datetime(2027, 12, 31, 23, 59, 59, tzinfo=timezone.utc),
    rule_version="oscars-edition@1",
    container_kind="award_show",
    category="awards",
    display_name="Oscars 2027",
    decider=_decide_oscars,
    population=_oscars_population,
)

AI = ThemeDefinition(
    subject="ai",
    scope=SCOPE_CONTINUING,
    retention_days=AI_RETENTION_DAYS,
    rule_version="ai-subject@1",
    container_kind="theme",
    category="ai",
    display_name="AI",
    decider=_decide_ai,
    population=_ai_population,
    feed_keys=("story:ai",),
)


def build_registry(definitions: Iterable[ThemeDefinition]) -> dict[str, ThemeDefinition]:
    """slug -> definition. Refuses duplicate slugs and a scope disagreement
    between two definitions of one subject."""
    registry: dict[str, ThemeDefinition] = {}
    scopes: dict[str, str] = {}
    for defn in definitions:
        slug = defn.slug()
        if slug in registry:
            raise ValueError(f"duplicate theme slug {slug!r}")
        if scopes.setdefault(defn.subject, defn.scope) != defn.scope:
            raise ValueError(f"subject {defn.subject!r} declared with two scopes")
        registry[slug] = defn
    return registry


def build_feed_key_map(registry: Mapping[str, ThemeDefinition]) -> dict[str, str]:
    """feed key -> subject. Refuses a key claimed by two subjects, the swings
    key, and anything that is not a ``story:`` key (a group_id entry would be a
    member list in disguise)."""
    out: dict[str, str] = {}
    for defn in registry.values():
        for key in defn.feed_keys:
            if key == SWINGS_FEED_KEY or not key.startswith("story:"):
                raise ValueError(f"feed key {key!r} may not map to a collection")
            if out.setdefault(key, defn.subject) != defn.subject:
                raise ValueError(f"feed key {key!r} claimed by two subjects")
    return out


REGISTRY: dict[str, ThemeDefinition] = build_registry([OSCARS_2027, AI])
FEED_KEY_MAP: dict[str, str] = build_feed_key_map(REGISTRY)

_FINITE_SLUG_RE = re.compile(r"^([a-z][a-z0-9]*(?:-[a-z][a-z0-9]*)*)-(\d{4})$")


def parse_theme_slug(
    slug: Optional[str], registry: Optional[Mapping[str, ThemeDefinition]] = None
) -> Optional[dict]:
    """``{"kind": "theme_edition", "subject", "edition"}`` /
    ``{"kind": "theme_continuing", "subject"}``, or None.

    Accepted only when the registry's own slug builder reproduces the slug byte
    for byte. A finite subject parses for any edition year (``oscars-2031``
    parses; whether a container exists is the reader's question, answered 404),
    but never a continuing subject with a year (``ai-2026``) or a non-canonical
    spelling (``oscars-27``, ``Oscars-2027``)."""
    if not isinstance(slug, str) or not slug:
        return None
    reg = REGISTRY if registry is None else registry
    scopes = {d.subject: d.scope for d in reg.values()}
    if scopes.get(slug) == SCOPE_CONTINUING and build_theme_slug(slug, SCOPE_CONTINUING) == slug:
        return {"kind": "theme_continuing", "subject": slug}
    m = _FINITE_SLUG_RE.match(slug)
    if m and scopes.get(m.group(1)) == SCOPE_FINITE:
        subject, edition = m.group(1), int(m.group(2))
        if build_theme_slug(subject, SCOPE_FINITE, edition) == slug:
            return {"kind": "theme_edition", "subject": subject, "edition": edition}
    return None


# ---------------------------------------------------------------------------
# §5 steps 1–3: the DETERMINED target. Publication is not an input.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CandidateContainer:
    """One theme container as the caller read it: the ids it admits through a
    ``theme_rule`` edge, in whatever publication state it is in. The state rides
    along for the caller's step-4 checks and is never read by the resolver."""

    container_id: int
    slug: str
    theme_rule_member_ids: frozenset
    publication_state: Optional[str] = None


def resolve_collection_target(
    feed_key: Optional[str],
    preview_ids: Iterable[int],
    candidates: Iterable[CandidateContainer],
    *,
    registry: Optional[Mapping[str, ThemeDefinition]] = None,
    feed_key_map: Optional[Mapping[str, str]] = None,
) -> tuple[Optional[CandidateContainer], Optional[str]]:
    """(intended target, None) or (None, reason).

    0. Swings is never a collection (v3.2): refused on the feed key alone,
       before C is read and before the map or the single-candidate arm. Without
       it an all-AI swings bundle with |C| = 1 resolves to ``ai``.
    1. Feed key: ``story_key`` for story bundles, ``group_id`` for awards.
    2. C = candidates admitting EVERY preview id, in any publication state.
    3. A mapped key names exactly one subject in C (zero or many -> no ref, and
       never a fallback to another member of C). An unmapped key resolves only
       when exactly one container in C exists (R4e, resolved by root).

    Step 4 (published, snapshot at the live revision, preview ⊆ shown ∪ folded,
    nothing withheld) runs on the returned target only, in P2. It can remove
    the link; it can never choose a different one."""
    reg = REGISTRY if registry is None else registry
    fmap = FEED_KEY_MAP if feed_key_map is None else feed_key_map

    if feed_key == SWINGS_FEED_KEY:
        return None, SWINGS_NOT_A_COLLECTION
    preview = frozenset(preview_ids)
    if not preview:
        return None, PREVIEW_EMPTY
    admitting = [c for c in candidates if preview <= frozenset(c.theme_rule_member_ids)]

    mapped_subject = fmap.get(feed_key) if feed_key is not None else None
    if mapped_subject is not None:
        hits = [c for c in admitting
                if (parse_theme_slug(c.slug, reg) or {}).get("subject") == mapped_subject]
        if not hits:
            return None, MAPPED_TARGET_ABSENT
        if len(hits) > 1:
            return None, MAPPED_TARGET_AMBIGUOUS
        return hits[0], None

    if not admitting:
        return None, PREVIEW_SPANS_COLLECTIONS
    if len(admitting) > 1:
        return None, NO_MAP_ENTRY_AMBIGUOUS
    if parse_theme_slug(admitting[0].slug, reg) is None:
        return None, TARGET_SLUG_NOT_THEME
    return admitting[0], None
