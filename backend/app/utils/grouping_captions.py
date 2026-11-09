"""Model-written container captions under the no-number rule (#12233).

Implements the caption primitive from ``docs/design/grouping-primitives.md`` and
Decide 61-A / #12233:
- Containers carry a short line of editorial commentary a reader enjoys, written
  by a model (or verified definition voice) that **never writes a number** in
  prose.
- Every figure displayed alongside the caption is read directly from the
  container's resolved member set, labelled with when it is true
  (``observed_at`` / ``as_of_label``), and linked to its source member
  (``source`` + ``source_href`` — the ``/evals`` rule).
- Copies the frame writer's boundary check (``sanitize_cu_frame``,
  ``app/utils/cu_frame.py:191``) via ``value_appears_in_title``: any caption
  containing a number or figure value not literally present in the resolved set
  is refused and discarded.
- Enforces Decide 61-A model spend discipline: uses ``LEGACY_MODEL`` from
  ``app.services.llm_models``, prints the estimated cost before running, and
  enforces the ``$5.00`` per-run cap and ``$30.00`` November cap. Model calls
  never run during page loads.
"""

from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from app.services.llm_models import LEGACY_MODEL
from app.utils.cu_frame import value_appears_in_title

DEFAULT_CAPTION_MODEL = LEGACY_MODEL
CAPTION_RUN_CAP_USD = 5.00
CAPTION_MONTHLY_CAP_USD = 30.00

# GPT-4o-mini reference pricing ($0.15 / 1M input tokens, $0.60 / 1M output tokens)
_INPUT_COST_PER_1M_USD = 0.15
_OUTPUT_COST_PER_1M_USD = 0.60

CAPTION_MAX_CHARS = 220
MAX_CAPTION_FIGURES = 4

# Drop / refusal reasons (mirroring sanitize_cu_frame in app/utils/cu_frame.py)
DROP_EMPTY_COMMENTARY = "empty_commentary"
DROP_COMMENTARY_TOO_LONG = "commentary_too_long"
DROP_NUMBER_NOT_IN_SET = "number_not_in_set"
DROP_MODEL_WROTE_NUMBER = "model_wrote_number"
DROP_VALUE_NOT_IN_SET = "value_not_in_set"
DROP_MISSING_OBSERVED_AT = "missing_observed_at"
DROP_UNLINKED_SOURCE = "unlinked_source"
DROP_FORBIDDEN_QUESTION_WORD = "forbidden_question_word"
DROP_PROVIDER_NAME_IN_PROSE = "provider_name_in_prose"
DROP_BETTING_ADVICE = "betting_advice"

# Matches any digit-bearing token (e.g. "58%", "3", "14.5", "$100", "2026", "4-2")
_DIGIT_TOKEN_RE = re.compile(
    r"(?<![A-Za-z_])[$+-]?\d+(?:[.,:/-]\d+)*%?(?![A-Za-z_])"
)

# Spelled-out quantitative number words that models sometimes use to smuggle a figure
_NUMBER_WORD_RE = re.compile(
    r"\b(?:zero|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|"
    r"twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|"
    r"hundred|thousand|million|billion|percent|percentage)\b",
    re.IGNORECASE,
)

_FORBIDDEN_QUESTION_RE = re.compile(r"\bquestions?\b", re.IGNORECASE)
_FORBIDDEN_PROVIDER_RE = re.compile(
    r"\b(?:kalshi|polymarket|fanduel|draftkings|betmgm|caesars)\b",
    re.IGNORECASE,
)
_FORBIDDEN_BETTING_RE = re.compile(
    r"\b(?:bet now|lock of the|parlay|hammer the|free money|fade the|must-bet)\b",
    re.IGNORECASE,
)

CAPTION_SYSTEM_PROMPT = (
    "You write a single crisp editorial caption line for a Bain Luck container. "
    "STRICT NO-NUMBER RULE: Never write any digit, percentage, date number, count, "
    "or spelled-out number in the commentary sentence. Every figure is read from "
    "the container's member set and attached separately with its timestamp and "
    "source link. Never use the word 'question'. Never name betting venues in "
    "prose. Never give betting advice."
)


class CaptionSpendCapExceededError(RuntimeError):
    """Raised when a caption generation run would exceed Decide 61-A caps."""


def _normalize_timestamp_iso(value: Any, *, fallback: Optional[str] = None) -> str:
    """Normalize an observed_at timestamp to an ISO-8601 UTC string."""
    if isinstance(value, datetime):
        dt = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(value, str) and value.strip():
        text = value.strip()
        return text
    if fallback and str(fallback).strip():
        return str(fallback).strip()
    return ""


def format_observed_at_label(observed_at: Any) -> str:
    """Render a reader-facing timestamp label for when a set figure is true."""
    raw = _normalize_timestamp_iso(observed_at)
    if not raw:
        return ""
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        parsed_utc = parsed.astimezone(timezone.utc)
        return f"as of {parsed_utc.strftime('%b %d, %H:%M UTC')}"
    except ValueError:
        return f"as of {raw}"


def _member_destination_href(member: Mapping[str, Any]) -> str:
    """Extract or derive the canonical destination href for a set member."""
    for key in ("source_href", "destination_href", "href", "url"):
        val = member.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    dest = member.get("destination")
    if isinstance(dest, Mapping):
        dest_href = dest.get("href")
        if isinstance(dest_href, str) and dest_href.strip():
            return dest_href.strip()
        dest_kind = str(dest.get("kind") or "").strip().lower()
        dest_id = dest.get("id")
        if dest_id is not None:
            if dest_kind == "event":
                return f"/events/{dest_id}"
            if dest_kind in ("market", "futures"):
                return f"/futures/{dest_id}"
    card = member.get("card")
    if isinstance(card, Mapping):
        for key in ("source_href", "destination_href", "href", "url"):
            val = card.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    member_type = str(
        member.get("member_type")
        or member.get("type")
        or member.get("atom_type")
        or member.get("kind")
        or ""
    ).strip().lower()
    raw_id = (
        member.get("event_id")
        if member_type == "event" or member.get("event_id") is not None
        else member.get("market_id") or member.get("id") or member.get("member_id")
    )
    if raw_id is None and isinstance(card, Mapping):
        raw_id = card.get("event_id") or card.get("market_id") or card.get("id")
    if raw_id is None:
        return ""
    text_id = str(raw_id).strip()
    if text_id.startswith("event:"):
        return f"/events/{text_id.split(':', 1)[1]}"
    if text_id.startswith("market:") or text_id.startswith("futures:"):
        return f"/futures/{text_id.split(':', 1)[1]}"
    if member_type in ("event", "game", "matchup") or member.get("event_id") is not None:
        return f"/events/{text_id}"
    if member_type in ("market", "futures", "futures_market"):
        return f"/futures/{text_id}"
    return f"/events/{text_id}"


def _member_source_label(member: Mapping[str, Any]) -> str:
    """Extract a truthful source label for a figure read from a member."""
    for key in ("source_label", "source", "probability_source", "hero_probability_source"):
        val = member.get(key)
        if isinstance(val, str) and val.strip():
            s = val.strip()
            return "blended" if s == "blend" else s
    card = member.get("card")
    if isinstance(card, Mapping):
        for key in ("source_label", "source", "probability_source", "hero_probability_source"):
            val = card.get(key)
            if isinstance(val, str) and val.strip():
                s = val.strip()
                return "blended" if s == "blend" else s
    sources = member.get("sources") or member.get("win_probability_sources")
    if isinstance(sources, Mapping) and sources:
        if len(sources) > 1:
            return "blended"
        first_key = next(iter(sources.keys()))
        return str(first_key).strip()
    if isinstance(sources, Sequence) and not isinstance(sources, (str, bytes)) and sources:
        if len(sources) > 1:
            return "blended"
        return str(sources[0]).strip()
    return "blended"


def _member_observed_at(member: Mapping[str, Any], *, default_observed_at: Optional[str] = None) -> str:
    """Extract when a member's figure was observed."""
    for key in (
        "observed_at",
        "hero_probability_observed_at",
        "probability_updated_at",
        "updated_at",
        "as_of",
        "commence_time",
        "end_date",
    ):
        val = member.get(key)
        norm = _normalize_timestamp_iso(val)
        if norm:
            return norm
    card = member.get("card")
    if isinstance(card, Mapping):
        for key in (
            "observed_at",
            "hero_probability_observed_at",
            "probability_updated_at",
            "updated_at",
            "as_of",
            "commence_time",
            "end_date",
        ):
            val = card.get(key)
            norm = _normalize_timestamp_iso(val)
            if norm:
                return norm
    return _normalize_timestamp_iso(default_observed_at)


def _format_prob_pct(prob: Any) -> Optional[str]:
    """Convert a 0..1 or 0..100 probability into a canonical 'NN%' string."""
    if isinstance(prob, bool) or prob is None:
        return None
    if isinstance(prob, str):
        stripped = prob.strip()
        if stripped.endswith("%"):
            return stripped
        try:
            prob = float(stripped)
        except ValueError:
            return None
    if isinstance(prob, (int, float)):
        val = float(prob)
        if 0.0 <= val <= 1.0:
            return f"{round(val * 100)}%"
        if 1.0 < val <= 100.0:
            return f"{round(val)}%"
    return None


def extract_set_figures(
    members: Sequence[Mapping[str, Any]],
    *,
    default_observed_at: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Read canonical figures directly from the container's member set.

    Every returned figure is anchored to a specific member in the set,
    carries ``observed_at`` + ``as_of_label`` (when it is true), and carries
    ``source`` + ``source_href`` (linked to its source member).
    """
    figures: List[Dict[str, Any]] = []
    for member in members or []:
        if not isinstance(member, Mapping):
            continue
        card = member.get("card") if isinstance(member.get("card"), Mapping) else {}
        member_id = str(
            member.get("id")
            or member.get("member_id")
            or member.get("event_id")
            or member.get("market_id")
            or card.get("id")
            or card.get("event_id")
            or card.get("market_id")
            or ""
        ).strip()
        label = str(
            member.get("matchup_label")
            or member.get("short_label")
            or member.get("label")
            or member.get("opponent_label")
            or member.get("title")
            or member.get("name")
            or card.get("title")
            or card.get("name")
            or (
                f"{card.get('away_team')} @ {card.get('home_team')}"
                if card.get("away_team") and card.get("home_team")
                else ""
            )
            or member_id
        ).strip()
        # Probability / figure value read directly from the member
        raw_value = member.get("value") or member.get("formatted_value")
        rendered_pct = member.get("rendered_percent")
        prob_val = (
            rendered_pct
            if isinstance(rendered_pct, (int, float)) and not isinstance(rendered_pct, bool)
            else member.get("subject_win_prob")
            if member.get("subject_win_prob") is not None
            else member.get("probability")
            if member.get("probability") is not None
            else member.get("yes_probability")
            if member.get("yes_probability") is not None
            else member.get("home_win_prob")
            if member.get("home_win_prob") is not None
            else card.get("hero_probability")
            if card.get("hero_probability") is not None
            else card.get("probability")
        )
        value_str = (
            str(raw_value).strip()
            if isinstance(raw_value, str) and raw_value.strip()
            else f"{int(round(float(rendered_pct)))}%"
            if isinstance(rendered_pct, (int, float)) and not isinstance(rendered_pct, bool)
            else _format_prob_pct(prob_val)
        )
        if not value_str:
            continue
        observed_at = _member_observed_at(member, default_observed_at=default_observed_at)
        source_href = _member_destination_href(member)
        source_label = _member_source_label(member)
        figures.append(
            {
                "member_id": member_id,
                "label": label,
                "value": value_str,
                "observed_at": observed_at,
                "as_of_label": format_observed_at_label(observed_at),
                "source": source_label,
                "source_href": source_href,
            }
        )
    return figures


def build_set_value_corpus(
    members: Sequence[Mapping[str, Any]],
    *,
    default_observed_at: Optional[str] = None,
) -> str:
    """Build the text corpus of literal values present in the container's member set.

    Used with ``value_appears_in_title`` from ``app.utils.cu_frame`` so the
    caption sanitizer enforces the exact same boundary rules as the frame writer.
    """
    tokens: List[str] = []
    for member in members or []:
        if not isinstance(member, Mapping):
            continue
        card = member.get("card") if isinstance(member.get("card"), Mapping) else {}
        for source_map in (member, card):
            for key in (
                "title",
                "name",
                "label",
                "short_label",
                "matchup_label",
                "opponent_label",
                "date_label",
                "subtitle",
                "value",
                "formatted_value",
                "outcome_label",
            ):
                val = source_map.get(key)
                if isinstance(val, str) and val.strip():
                    tokens.append(val.strip())
            rendered_pct = source_map.get("rendered_percent")
            if isinstance(rendered_pct, (int, float)) and not isinstance(rendered_pct, bool):
                tokens.append(f"{int(round(float(rendered_pct)))}%")
            for prob_key in (
                "subject_win_prob",
                "probability",
                "yes_probability",
                "home_win_prob",
                "away_win_prob",
                "hero_probability",
                "hero_probability_away",
            ):
                pct = _format_prob_pct(source_map.get(prob_key))
                if pct:
                    tokens.append(pct)
    for fig in extract_set_figures(members, default_observed_at=default_observed_at):
        if fig.get("value"):
            tokens.append(str(fig["value"]))
        if fig.get("label"):
            tokens.append(str(fig["label"]))
    return " | ".join(tokens)


def extract_numbers_from_text(text: str) -> List[str]:
    """Extract all digit tokens and quantitative number words from text."""
    if not text or not isinstance(text, str):
        return []
    found: List[str] = []
    for match in _DIGIT_TOKEN_RE.finditer(text):
        token = match.group(0).strip()
        if token:
            found.append(token)
    for match in _NUMBER_WORD_RE.finditer(text):
        word = match.group(0).strip()
        if word:
            found.append(word)
    return found


def sanitize_grouping_caption(
    raw: Optional[Mapping[str, Any]],
    *,
    members: Sequence[Mapping[str, Any]],
    default_observed_at: Optional[str] = None,
    allow_set_numbers_in_prose: bool = False,
) -> Dict[str, Any]:
    """Validate and sanitize a container caption against its resolved member set.

    Copies the frame writer's check (``sanitize_cu_frame``, ``cu_frame.py:191``):
    1. Any number in ``commentary`` not literally in the set is refused with
       ``DROP_NUMBER_NOT_IN_SET``.
    2. Under the strict no-number rule (``allow_set_numbers_in_prose=False``,
       the default), any number written directly in ``commentary`` prose by the
       model is refused with ``DROP_MODEL_WROTE_NUMBER`` — figures belong in
       ``figures`` read from the set.
    3. Every figure in ``figures`` must have its ``value`` literally present in
       the set (via ``value_appears_in_title``), a non-empty ``observed_at``
       timestamp (when it is true), and a valid ``source`` + ``source_href``
       linked to a member of the set (the ``/evals`` rule). Any figure with a
       value not in the set refuses the caption with ``DROP_NUMBER_NOT_IN_SET``
       / ``DROP_VALUE_NOT_IN_SET``.
    """
    if not raw or not isinstance(raw, Mapping):
        return {
            "ok": False,
            "caption": None,
            "dropped_reason": DROP_EMPTY_COMMENTARY,
            "offending_numbers": [],
        }

    commentary = str(
        raw.get("commentary") or raw.get("text") or raw.get("line") or ""
    ).strip()
    if not commentary:
        return {
            "ok": False,
            "caption": None,
            "dropped_reason": DROP_EMPTY_COMMENTARY,
            "offending_numbers": [],
        }

    if len(commentary) > CAPTION_MAX_CHARS:
        return {
            "ok": False,
            "caption": None,
            "dropped_reason": DROP_COMMENTARY_TOO_LONG,
            "offending_numbers": [],
        }

    if _FORBIDDEN_QUESTION_RE.search(commentary):
        return {
            "ok": False,
            "caption": None,
            "dropped_reason": DROP_FORBIDDEN_QUESTION_WORD,
            "offending_numbers": [],
        }

    if _FORBIDDEN_PROVIDER_RE.search(commentary):
        return {
            "ok": False,
            "caption": None,
            "dropped_reason": DROP_PROVIDER_NAME_IN_PROSE,
            "offending_numbers": [],
        }

    if _FORBIDDEN_BETTING_RE.search(commentary):
        return {
            "ok": False,
            "caption": None,
            "dropped_reason": DROP_BETTING_ADVICE,
            "offending_numbers": [],
        }

    set_corpus = build_set_value_corpus(members, default_observed_at=default_observed_at)
    canonical_figures = extract_set_figures(members, default_observed_at=default_observed_at)
    allowed_hrefs = {
        fig["source_href"]
        for fig in canonical_figures
        if isinstance(fig.get("source_href"), str) and fig["source_href"].strip()
    }
    for member in members or []:
        if isinstance(member, Mapping):
            href = _member_destination_href(member)
            if href:
                allowed_hrefs.add(href)

    # Check numbers in commentary prose (frame writer's value_appears_in_title check)
    prose_numbers = extract_numbers_from_text(commentary)
    if prose_numbers:
        not_in_set = [
            num for num in prose_numbers if not value_appears_in_title(num, set_corpus)
        ]
        if not_in_set:
            return {
                "ok": False,
                "caption": None,
                "dropped_reason": DROP_NUMBER_NOT_IN_SET,
                "offending_numbers": not_in_set,
            }
        if not allow_set_numbers_in_prose:
            return {
                "ok": False,
                "caption": None,
                "dropped_reason": DROP_MODEL_WROTE_NUMBER,
                "offending_numbers": prose_numbers,
            }

    # Validate figures: if caller supplied figures, verify every one against the set;
    # otherwise populate directly from extract_set_figures(members).
    raw_figures = raw.get("figures")
    if raw_figures is None:
        source_figures = canonical_figures[:MAX_CAPTION_FIGURES]
    elif isinstance(raw_figures, Sequence) and not isinstance(raw_figures, (str, bytes)):
        source_figures = list(raw_figures)[:MAX_CAPTION_FIGURES]
    else:
        return {
            "ok": False,
            "caption": None,
            "dropped_reason": DROP_VALUE_NOT_IN_SET,
            "offending_numbers": [],
        }

    sanitized_figures: List[Dict[str, Any]] = []
    for item in source_figures:
        if not isinstance(item, Mapping):
            return {
                "ok": False,
                "caption": None,
                "dropped_reason": DROP_VALUE_NOT_IN_SET,
                "offending_numbers": [],
            }
        value = str(item.get("value") or "").strip()
        label = str(item.get("label") or "").strip()
        if not value or not label:
            return {
                "ok": False,
                "caption": None,
                "dropped_reason": DROP_VALUE_NOT_IN_SET,
                "offending_numbers": [value] if value else [],
            }
        if not value_appears_in_title(value, set_corpus):
            return {
                "ok": False,
                "caption": None,
                "dropped_reason": DROP_NUMBER_NOT_IN_SET,
                "offending_numbers": [value],
            }
        observed_at = _normalize_timestamp_iso(
            item.get("observed_at"), fallback=default_observed_at
        )
        if not observed_at:
            return {
                "ok": False,
                "caption": None,
                "dropped_reason": DROP_MISSING_OBSERVED_AT,
                "offending_numbers": [],
            }
        source = str(item.get("source") or "").strip()
        source_href = str(item.get("source_href") or "").strip()
        if (
            not source
            or not source_href
            or not source_href.startswith(("/events/", "/futures/", "/collections/", "/tournaments/", "https://"))
            or (allowed_hrefs and source_href not in allowed_hrefs)
        ):
            return {
                "ok": False,
                "caption": None,
                "dropped_reason": DROP_UNLINKED_SOURCE,
                "offending_numbers": [],
            }
        as_of_label = str(item.get("as_of_label") or "").strip() or format_observed_at_label(
            observed_at
        )
        sanitized_figures.append(
            {
                "member_id": str(item.get("member_id") or "").strip(),
                "label": label,
                "value": value,
                "observed_at": observed_at,
                "as_of_label": as_of_label,
                "source": source,
                "source_href": source_href,
            }
        )

    return {
        "ok": True,
        "dropped_reason": None,
        "offending_numbers": [],
        "caption": {
            "commentary": commentary,
            "no_number_verified": True,
            "figures": sanitized_figures,
        },
    }


def compose_container_caption(
    definition: Mapping[str, Any],
    *,
    members: Sequence[Mapping[str, Any]],
    default_observed_at: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Compose and sanitize a container's caption + set-linked figures.

    Reads the caption commentary from the container definition (or pre-generated
    caption payload) and pairs it with figures read directly from ``members``.
    Returns ``None`` if the caption is absent or fails the no-number / source-link
    sanitizer.
    """
    raw_caption = definition.get("caption")
    commentary_text: Optional[str] = None
    explicit_figures: Optional[Sequence[Mapping[str, Any]]] = None

    if isinstance(raw_caption, str) and raw_caption.strip():
        commentary_text = raw_caption.strip()
    elif isinstance(raw_caption, Mapping):
        commentary_text = str(
            raw_caption.get("commentary")
            or raw_caption.get("text")
            or raw_caption.get("line")
            or ""
        ).strip()
        if isinstance(raw_caption.get("figures"), Sequence):
            explicit_figures = raw_caption.get("figures")
    elif isinstance(definition.get("caption_commentary"), str):
        commentary_text = str(definition["caption_commentary"]).strip()

    if not commentary_text:
        return None

    figures = (
        list(explicit_figures)
        if explicit_figures is not None
        else extract_set_figures(members, default_observed_at=default_observed_at)
    )
    result = sanitize_grouping_caption(
        {
            "commentary": commentary_text,
            "figures": figures,
        },
        members=members,
        default_observed_at=default_observed_at,
        allow_set_numbers_in_prose=False,
    )
    if not result["ok"]:
        return None
    return result["caption"]


def estimate_caption_run_spend(
    container_count: int,
    *,
    model: str = DEFAULT_CAPTION_MODEL,
    avg_input_tokens: int = 450,
    avg_output_tokens: int = 90,
    prior_november_spend_usd: float = 0.0,
) -> Dict[str, Any]:
    """Estimate token usage and USD cost before running model caption generation (Decide 61-A)."""
    count = max(0, int(container_count))
    input_tokens = count * max(0, int(avg_input_tokens))
    output_tokens = count * max(0, int(avg_output_tokens))
    est_run_usd = round(
        (input_tokens / 1_000_000.0) * _INPUT_COST_PER_1M_USD
        + (output_tokens / 1_000_000.0) * _OUTPUT_COST_PER_1M_USD,
        6,
    )
    projected_monthly_usd = round(float(prior_november_spend_usd) + est_run_usd, 6)
    within_run_cap = est_run_usd <= CAPTION_RUN_CAP_USD
    within_monthly_cap = projected_monthly_usd <= CAPTION_MONTHLY_CAP_USD
    return {
        "model": model,
        "container_count": count,
        "estimated_input_tokens": input_tokens,
        "estimated_output_tokens": output_tokens,
        "estimated_run_cost_usd": est_run_usd,
        "run_cap_usd": CAPTION_RUN_CAP_USD,
        "prior_november_spend_usd": round(float(prior_november_spend_usd), 6),
        "projected_november_spend_usd": projected_monthly_usd,
        "monthly_cap_usd": CAPTION_MONTHLY_CAP_USD,
        "within_caps": bool(within_run_cap and within_monthly_cap),
    }


def format_caption_pre_run_spend_line(estimate: Mapping[str, Any]) -> str:
    """Format the mandatory Decide 61-A pre-run spend line."""
    return (
        f"[grouping-captions] model={estimate.get('model', DEFAULT_CAPTION_MODEL)} "
        f"containers={estimate.get('container_count', 0)} "
        f"est_run_cost=${float(estimate.get('estimated_run_cost_usd', 0.0)):.4f} "
        f"(cap=${ float(estimate.get('run_cap_usd', CAPTION_RUN_CAP_USD)):.2f}) "
        f"projected_november=${float(estimate.get('projected_november_spend_usd', 0.0)):.4f} "
        f"(cap=${float(estimate.get('monthly_cap_usd', CAPTION_MONTHLY_CAP_USD)):.2f})"
    )


def generate_container_captions(
    containers: Sequence[Mapping[str, Any]],
    *,
    llm_call: Optional[Callable[[Mapping[str, Any]], str]] = None,
    prior_november_spend_usd: float = 0.0,
    avg_input_tokens: int = 450,
    avg_output_tokens: int = 90,
    print_fn: Callable[[str], None] = print,
) -> Dict[str, Any]:
    """Generate and sanitize model-written captions offline under Decide 61-A.

    Prints the estimated spend before making any model call, enforces the $5/run
    and $30/Nov caps, and runs every candidate caption through
    ``sanitize_grouping_caption`` so no caption with an unverified or model-written
    number can ever survive.
    """
    estimate = estimate_caption_run_spend(
        len(containers),
        model=DEFAULT_CAPTION_MODEL,
        avg_input_tokens=avg_input_tokens,
        avg_output_tokens=avg_output_tokens,
        prior_november_spend_usd=prior_november_spend_usd,
    )
    spend_line = format_caption_pre_run_spend_line(estimate)
    print_fn(spend_line)

    if not estimate["within_caps"]:
        raise CaptionSpendCapExceededError(
            f"Caption run exceeds Decide 61-A spend cap: {spend_line}"
        )

    accepted: List[Dict[str, Any]] = []
    refused: List[Dict[str, Any]] = []

    for container in containers:
        cid = str(container.get("id") or "").strip()
        members = list(container.get("members") or [])
        default_observed_at = str(
            container.get("observed_at")
            or container.get("generated_at")
            or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        )
        raw_line = ""
        if llm_call is not None:
            raw_line = str(llm_call(container) or "").strip()
        else:
            raw_line = str(container.get("candidate_commentary") or "").strip()

        figures = extract_set_figures(members, default_observed_at=default_observed_at)
        verdict = sanitize_grouping_caption(
            {"commentary": raw_line, "figures": figures},
            members=members,
            default_observed_at=default_observed_at,
            allow_set_numbers_in_prose=False,
        )
        if verdict["ok"] and verdict["caption"] is not None:
            accepted.append(
                {
                    "container_id": cid,
                    "caption": verdict["caption"],
                }
            )
        else:
            refused.append(
                {
                    "container_id": cid,
                    "dropped_reason": verdict["dropped_reason"],
                    "offending_numbers": verdict["offending_numbers"],
                    "raw_commentary": raw_line,
                }
            )

    return {
        "spend_estimate": estimate,
        "pre_run_spend_line": spend_line,
        "accepted": accepted,
        "refused": refused,
    }
