"""Server-side composition for Discover comparison bundles."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

from app.utils.feed_market_quality import GOLF_TOURNAMENT_STORY_PREFIX
from app.utils.feed_market_quality import _story_key as compute_story_key
from app.utils.feed_market_quality import golf_tournament_display_name

logger = logging.getLogger(__name__)

PUBLIC_COMPARISON_BUNDLE_THEMES = {
    "ipo_valuation",
    "commodity_ranges",
    "rotten_tomatoes_scores",
    "weather_distributions",
}

# Theme-grouping: authored display labels per story_key (see
# feed_market_quality._story_key for the full key vocabulary). A feed that
# scatters N same-story markets across separate cards is folded into ONE
# expandable theme bundle instead.
#
# Queue 307 generalized this from a two-key geopolitics ALLOWLIST to an
# eligibility predicate over ANY story_key. This map is now presentation only:
# an unlisted key still bundles, it just renders a derived title (and logs once
# so the unnamed key surfaces in ops). Adding a label here is never required to
# make a story fold — it only makes it read better.
AUTHORED_STORY_TITLES = {
    # Geopolitics (the original slice-1 pair — labels intentionally unchanged).
    "story:middle_east_conflict": "Middle East",
    "story:russia_ukraine": "Russia–Ukraine",
    # Politics / government
    "story:us_2028_election": "2028 Election",
    "story:regional_us_elections": "US Local Elections",
    # #1885. "State Races" rather than "US State Races" — the feed's US-default
    # voice, matching "Washington Power" beside it. "Around the World" rather
    # than a literal "Foreign Local Elections": the family is Brazilian state
    # governors, Taiwanese county magistrates and Russian oblast parliaments, and
    # naming the mechanism ("sub-national", "foreign local") describes our
    # taxonomy rather than the reader's interest.
    "story:us_state_races": "State Races",
    "story:foreign_local_elections": "Elections Around the World",
    "story:us_federal_power": "Washington Power",
    "story:us_government_stakes": "Government Stakes",
    # Economics / markets
    "story:macro_rates": "Fed & Rates",
    "story:oil": "Oil",
    "story:single_stock_earnings": "Earnings",
    "story:ipo_markets": "IPOs",
    "story:spacex_ipo": "SpaceX IPO",
    # Tech / science
    "story:ai": "AI",
    "story:spacex_launches": "SpaceX Launches",
    "story:aliens_disclosure": "Aliens & UFOs",
    # Culture / entertainment
    "story:major_entertainment_events": "Awards Season",
    "story:music_charts": "Music Charts",
    "story:drake_iceman": "Drake",
    # Sport
    "story:fifa_world_cup": "World Cup",
    "story:basketball_finals_path": "NBA Finals",
    "story:ufc_events": "UFC",
    "story:grand_slam_tennis": "Grand Slam Tennis",
    "story:golf_truist_championship": "Truist Championship",
}

# Back-compat alias: slice 1 shipped this name and it is the geopolitics subset.
GEOPOLITICS_STORY_KEYS = {
    key: AUTHORED_STORY_TITLES[key]
    for key in ("story:middle_east_conflict", "story:russia_ukraine")
}

# Tokens that must render upper-case in a derived title ("us_2028_election" ->
# "2028 Election", "ai" -> "AI"). Keep lower-cased keys.
_TITLE_ACRONYMS = {
    "ai", "us", "usa", "uk", "eu", "un", "ipo", "ufo", "ufc", "nba", "wnba",
    "nfl", "mlb", "nhl", "cpi", "ppi", "wti", "ecb", "fbi", "gdp", "tv",
}

# One structured log line per unknown story_key per PROCESS lifetime, so a newly
# minted key surfaces in ops without spamming every feed request.
_UNKNOWN_STORY_KEYS_LOGGED: set[str] = set()


def _derive_story_title(story_key: str) -> str:
    """Human title for an unauthored story_key (``story:macro_rates`` -> ``Macro Rates``)."""
    slug = story_key.split(":", 1)[-1]
    words = [w for w in slug.replace("-", "_").split("_") if w]
    if not words:
        return "Related markets"
    out: list[str] = []
    for word in words:
        if word.lower() in _TITLE_ACRONYMS:
            out.append(word.upper())
        elif word.isdigit():
            out.append(word)
        else:
            out.append(word[:1].upper() + word[1:])
    return " ".join(out)


def _resolve_story_title(story_key: str) -> tuple[str, str]:
    """``(label, title_source)`` where ``title_source`` is ``authored``/``fallback``."""
    authored = AUTHORED_STORY_TITLES.get(story_key)
    if authored:
        return authored, "authored"
    if story_key not in _UNKNOWN_STORY_KEYS_LOGGED:
        _UNKNOWN_STORY_KEYS_LOGGED.add(story_key)
        logger.info(
            "discover_bundle: unknown story_key fallback",
            extra={"story_key": story_key},
        )
    return _derive_story_title(story_key), "fallback"


# ── A GROUP'S REASON IS ITS SHARED QUESTION (D1 clause c, #4066) ─────────────
#
# Seven of the twenty items served on production 2026-09-08 21:07Z were bundles,
# and every one of them gave the same reason: "2 related markets", "3 related
# markets", "4 related markets" — rendered on the card as "· 2 related". That is
# a count of inventory. It tells a reader how many rows are behind a chevron and
# nothing about why the rows belong together, which is the only thing that makes
# a group worth a slot instead of its members taking their own.
#
# The plan Alex commissioned puts it exactly: "'Awards Season · 5 related' is
# navigation. 'Which of this month's releases is best positioned for awards
# attention?' is an editorial question." Rulings 143/145 want the same thing.
#
# So each story family gets ONE authored sentence, phrased as the question its
# members are all answers to. Authored rather than derived because the shared
# question is an editorial judgement about a family — "Middle East" covers
# ceasefires, strikes and hostage releases, and no token-overlap heuristic
# recovers "Where is the Middle East conflict heading?" from those names.
#
# A family with no authored question falls back to the phrase its members
# literally share (the awards path's `_derive_race_label`); a family with
# neither shares no question we can state, and does not get a bundle slot — its
# members compete individually, which is where they were before folding.
AUTHORED_STORY_QUESTIONS = {
    # Geopolitics
    "story:middle_east_conflict": "Where is the Middle East conflict heading?",
    "story:russia_ukraine": "How does the war in Ukraine end?",
    # Politics / government
    "story:us_2028_election": "Who wins in 2028?",
    "story:regional_us_elections": "Who wins this year's US local races?",
    "story:us_state_races": "Who wins the big state races?",
    "story:foreign_local_elections": "Who wins the elections nobody is covering?",
    "story:us_federal_power": "Who holds power in Washington?",
    "story:us_government_stakes": "What is Washington about to do?",
    # Economics / markets
    "story:macro_rates": "What does the Fed do next?",
    "story:oil": "Where is the oil price going?",
    "story:single_stock_earnings": "Who beats their earnings number?",
    "story:ipo_markets": "Who goes public, and at what price?",
    "story:spacex_ipo": "Does SpaceX go public, and at what valuation?",
    # Tech / science
    "story:ai": "Which AI model comes out on top?",
    "story:spacex_launches": "What does SpaceX launch next?",
    "story:aliens_disclosure": "Does anyone confirm we are not alone?",
    # Culture / entertainment
    "story:major_entertainment_events": "Who wins awards season?",
    "story:music_charts": "Who tops the charts?",
    "story:drake_iceman": "How does the Drake record land?",
    # Sport
    "story:fifa_world_cup": "Who wins the World Cup?",
    "story:basketball_finals_path": "Who reaches the NBA Finals?",
    "story:ufc_events": "Who wins on the next card?",
    "story:grand_slam_tennis": "Who wins the Slam?",
    "story:golf_truist_championship": "Who wins the Truist Championship?",
}


def resolve_story_question(
    story_key: str, member_names: list[str]
) -> tuple[str | None, str]:
    """``(question, source)`` for a story family, or ``(None, "none")``.

    ``source`` is ``authored`` / ``derived`` / ``none`` and rides the bundle's
    debug block, so a family folding on a derived phrase is visible in ops
    rather than having to be inferred from the copy.

    🔴 THE DERIVED PATH USES `_shared_member_phrase`, NOT `_derive_race_label`,
    AND THE DIFFERENCE IS THE WHOLE GUARD. `_derive_race_label` falls back to
    the SHORTEST MEMBER NAME when the members share no phrase — correct for the
    awards bundler, whose members are already known to be one race by
    `group_id`, and catastrophic here, where the fallback would manufacture a
    shared question out of one member's title. Two markets with nothing in
    common ("Oil above $90 in December?", "Taylor Swift engaged by New Year?")
    came back as "Who wins Oil above $90?" while this called the label helper —
    a group asserting a common question that does not exist. No shared phrase
    means no question means no bundle.
    """
    authored = AUTHORED_STORY_QUESTIONS.get(story_key)
    if authored:
        return authored, "authored"
    shared = _shared_member_phrase(member_names)
    if shared:
        return f"Who wins {shared}?", "derived"
    # A story_key is itself an assertion that these markets are one story
    # (`feed_market_quality._story_key` computed it from their names and
    # categories), so a family we simply have not written a sentence for still
    # has a question — a weaker one. This tier exists so clause (c) does not
    # quietly undo Queue 307's generalization, which made ANY story_key
    # foldable: every key on page one today is authored, so this is the tail,
    # and `_resolve_story_title` already logs each unknown key once so the tail
    # can be authored rather than guessed at.
    title, title_source = _resolve_story_title(story_key)
    if title_source == "fallback" and title != "Related markets":
        return f"What's the latest on {title}?", "story_title"
    return None, "none"


_THEME_TITLES = {
    "ipo_valuation": "IPO valuation ranges",
    "commodity_ranges": "Commodity price ranges",
    "rotten_tomatoes_scores": "Rotten Tomatoes score ranges",
    "weather_distributions": "Weather ranges",
}

_THEME_REASONS = {
    "ipo_valuation": "Compare valuation range probabilities across IPO markets.",
    "commodity_ranges": "Compare price range probabilities across commodity markets.",
    "rotten_tomatoes_scores": "Compare score range probabilities across entertainment markets.",
    "weather_distributions": "Compare forecast range probabilities across weather markets.",
}


def _futures_data(item: dict[str, Any]) -> dict[str, Any]:
    if item.get("type") != "futures":
        return {}
    data = item.get("data")
    return data if isinstance(data, dict) else {}


def _discover_card(data: dict[str, Any]) -> dict[str, Any]:
    card = data.get("discover_card")
    return card if isinstance(card, dict) else {}


def _theme_for_item(item: dict[str, Any]) -> str | None:
    data = _futures_data(item)
    card = _discover_card(data)
    theme = card.get("comparison_theme")
    if theme not in PUBLIC_COMPARISON_BUNDLE_THEMES:
        return None
    if not card.get("bundle_candidate"):
        return None
    if card.get("suggested_format") != "threshold_heatmap":
        return None
    if card.get("public_source_disagreement"):
        return None
    points = card.get("threshold_points") or []
    if len(points) < 2:
        return None
    return str(theme)


def _market_entity_name(name: str, theme: str) -> str:
    compact = re.sub(r"\s+", " ", name or "").strip()
    compact = compact.rstrip("?")
    if theme == "ipo_valuation":
        compact = re.sub(r"\bClosing Market Cap\b", "", compact, flags=re.I)
        compact = re.sub(r"\bIPO\b.*$", "IPO", compact, flags=re.I)
    elif theme == "commodity_ranges":
        compact = re.sub(r"^Will\s+", "", compact, flags=re.I)
        compact = re.sub(r"\b(hit|be|close|settle|end)\b.*$", "", compact, flags=re.I)
    elif theme == "rotten_tomatoes_scores":
        compact = re.sub(r"\bRotten Tomatoes\b", "RT", compact, flags=re.I)
        compact = re.sub(r"\bscore\b", "", compact, flags=re.I)
    elif theme == "weather_distributions":
        compact = re.sub(r"\bon .*$", "", compact, flags=re.I)
    return compact.strip() or name


#: The three weather measures we can state a question about, and the shape that
#: identifies each one. Read off the market NAME for the two temperature
#: measures (the name is what says highest vs lowest) and off the OUTCOME LABELS
#: for the other two (the labels are what say "3+ consecutive days" or
#: "Category 4 or above").
_WEATHER_HIGH_RE = re.compile(r"\bhighest\s+temperature\b", re.I)
_WEATHER_LOW_RE = re.compile(r"\blowest\s+temperature\b", re.I)
_WEATHER_STREAK_RE = re.compile(r"\bconsecutive\s+days?\b", re.I)
_WEATHER_STORM_CATEGORY_RE = re.compile(r"\bcategory\s*\d", re.I)
#: The threshold a heat streak counts days above ("… above 90°F …"). Two cities
#: counting days over different temperatures are not one comparison.
_WEATHER_STREAK_THRESHOLD_RE = re.compile(r"\babove\s*(\d+)\s*°?\s*([cf])?\b", re.I)


def _threshold_labels(data: dict[str, Any]) -> list[str]:
    points = _discover_card(data).get("threshold_points") or []
    return [
        str(point.get("label") or "") for point in points if isinstance(point, dict)
    ]


def _temperature_unit(labels: list[str]) -> str:
    """The unit the OUTCOME LABELS state, never one inferred from them.

    "13°C or below" (Seoul) and "66° or below" (Washington DC) are three keys,
    not two: `°C`, `°F` and a bare degree sign. Reading the bare one as
    Fahrenheit would be right for every US city on the board today and wrong the
    first morning a venue lists an unqualified Celsius market — and the failure
    would be a heatmap silently comparing 13 against 66.
    """
    joined = " ".join(labels).lower()
    if "°c" in joined or "celsius" in joined:
        return "°C"
    if "°f" in joined or "fahrenheit" in joined:
        return "°F"
    if "°" in joined or "degree" in joined:
        return "deg"
    return "unitless"


def _measure_key(theme: str, data: dict[str, Any]) -> str | None:
    """What this market measures — the thing its bundle's question is about.

    #4785. `comparison_theme` is a CATEGORY, not a measure: `weather_distributions`
    is every weather market with two threshold points, and on production
    2026-09-10 that let one card ask "How warm does it get in these cities?" over
    a hurricane category, two counts of consecutive days above 90°F and one
    overnight low — true of none of its four members. The theme cannot narrow it,
    because the theme is exactly what those four have in common.

    So the bundle groups on this instead: what is measured, and in what unit.
    Returning None means we cannot state the measure, and a member we cannot
    state does not join a card that claims a shared question — it competes on its
    own, which is where it was before the bundler ran (#4147, option b).

    The other three public themes are single-measure by construction (an IPO's
    valuation, a commodity's price, a film's critic score), so they keep the
    theme as their key and their behaviour is unchanged.
    """
    if theme != "weather_distributions":
        return theme

    name = str(data.get("name") or "")
    labels = _threshold_labels(data)
    if _WEATHER_HIGH_RE.search(name):
        return f"weather:temp_high:{_temperature_unit(labels)}"
    if _WEATHER_LOW_RE.search(name):
        return f"weather:temp_low:{_temperature_unit(labels)}"
    if any(_WEATHER_STREAK_RE.search(label) for label in labels):
        match = _WEATHER_STREAK_THRESHOLD_RE.search(name)
        threshold = (
            f"{match.group(1)}{(match.group(2) or '').upper()}" if match else "unstated"
        )
        return f"weather:heat_streak_days:{threshold}"
    if sum(bool(_WEATHER_STORM_CATEGORY_RE.search(label)) for label in labels) >= 2:
        return "weather:storm_category"
    return None


def _item_id(item: dict[str, Any]) -> str:
    data = item.get("data") if isinstance(item.get("data"), dict) else {}
    return f"{item.get('type')}:{data.get('id')}"


def _bundle_id(theme: str, items: list[dict[str, Any]]) -> str:
    ids = "-".join(str((_futures_data(item)).get("id")) for item in items)
    return f"comparison:{theme}:{ids}"


def _bundle_subtitle(measure: str, count: int) -> str:
    """The comparison bundle's shared question (D1 clause c, #4066).

    These four themes already knew what their members had in common — the old
    strings said it as a count and a basis ("4 IPO markets compared by valuation
    range"). Said as the question the members are answers to, the same fact
    tells a reader what they will learn by opening it. The count is not lost: it
    is the member list the card renders directly underneath.

    #4785 — KEYED ON THE MEASURE, NOT THE THEME. A theme's question is only the
    members' question when the theme has one measure in it. Three of the four do;
    `weather_distributions` holds temperatures, durations and storm categories,
    and its one authored sentence was false of all four members it shipped over.
    Each weather measure now answers for itself, and the grouping in
    :func:`_measure_key` is what makes each sentence true of every member under it.
    """
    if measure == "ipo_valuation":
        return "Which of these companies is priced highest to list?"
    if measure == "commodity_ranges":
        return "Where do these commodity prices land?"
    if measure == "rotten_tomatoes_scores":
        return "Which of these lands best with the critics?"
    if measure.startswith("weather:temp_high:"):
        return "How hot does it get in these cities?"
    if measure.startswith("weather:temp_low:"):
        return "How cold does it get in these cities?"
    if measure.startswith("weather:heat_streak_days:"):
        return "How long does the hot stretch run in these cities?"
    if measure == "weather:storm_category":
        return "How strong do these storms get?"
    return f"What do these {count} markets say together?"


def _public_member_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in item.items()
        if not key.startswith("_")
        and key
        not in {
            "personalization_trace",
            "_review_decision",
            "_review_decision_scope",
            "_review_decision_scope_key",
            "_review_decision_penalty",
        }
    }


def _make_bundle_item(
    theme: str, measure: str, items: list[dict[str, Any]]
) -> dict[str, Any]:
    score = max(float(item.get("score") or 0) for item in items)
    sort_time = max(float(item.get("_sort_time") or 0) for item in items)
    title = _THEME_TITLES.get(theme, "Comparable market ranges")
    member_ids = [(_futures_data(item)).get("id") for item in items]
    entities = [
        _market_entity_name(str((_futures_data(item)).get("name") or ""), theme)
        for item in items
    ]
    subtitle = _bundle_subtitle(measure, len(items))
    return {
        "type": "bundle",
        "score": score,
        "reason": subtitle,
        "headline": title,
        "context_summary": _THEME_REASONS.get(theme),
        "data": {
            "id": _bundle_id(theme, items),
            "title": title,
            "kind": "comparison",
            "shared_question": subtitle,
            "comparison_theme": theme,
            "item_count": len(items),
            "member_ids": member_ids,
            "items": [_public_member_item(item) for item in items],
            "entities": entities,
            "debug_bundles": {
                "grouped_by": "discover_card.comparison_theme+measure",
                "theme": theme,
                "measure": measure,
                "member_ids": member_ids,
                "member_names": [(_futures_data(item)).get("name") for item in items],
                "public_source_disagreement": False,
            },
        },
        "_sort_time": sort_time,
    }


def assemble_discover_comparison_bundles(
    items: list[dict[str, Any]],
    *,
    min_items: int = 2,
    max_items_per_bundle: int = 4,
    max_bundles_per_theme: int = 1,
) -> list[dict[str, Any]]:
    """Replace safe related futures with explicit comparison bundle feed items.

    Bundles are intentionally narrow: they require deterministic card metadata,
    at least two threshold points per represented market, and a public allowlisted
    comparison theme. Source disagreement remains QA-only and is never a public
    grouping theme.

    #4785 — CANDIDATES ARE GROUPED BY (THEME, MEASURE), NOT BY THEME. A theme is a
    category; the card's one sentence is about a measure, and where the two came
    apart the sentence was false of every member (see :func:`_measure_key`). A
    market whose measure cannot be stated is not a candidate at all. Still at most
    one bundle per theme, so a theme holding several measures serves its
    best-scoring one and the rest compete as individual cards.
    """

    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    seen_entities: dict[tuple[str, str], set[str]] = {}
    for item in items:
        theme = _theme_for_item(item)
        if theme is None:
            continue
        measure = _measure_key(theme, _futures_data(item))
        if measure is None:
            continue
        name = str(_futures_data(item).get("name") or "")
        entity = _market_entity_name(name, theme).lower()
        if not entity:
            continue
        key = (theme, measure)
        seen_entities.setdefault(key, set())
        if entity in seen_entities[key]:
            continue
        seen_entities[key].add(entity)
        groups.setdefault(key, []).append(item)

    # One bundle per theme, chosen by the same yardstick the bundle competes on:
    # its score (its best member), then its member count. Ties keep the group
    # whose first member ranks earliest, because `groups` is in feed order.
    best_by_theme: dict[str, tuple[tuple[float, int], list[dict[str, Any]], str]] = {}
    for (theme, measure), candidates in groups.items():
        top_candidates = candidates[:max_items_per_bundle]
        if len(top_candidates) < min_items:
            continue
        rank = (
            max(float(item.get("score") or 0) for item in top_candidates),
            len(top_candidates),
        )
        incumbent = best_by_theme.get(theme)
        if incumbent is None or rank > incumbent[0]:
            best_by_theme[theme] = (rank, top_candidates, measure)

    bundle_items_by_theme: dict[str, list[dict[str, Any]]] = {}
    represented_ids: set[str] = set()
    for theme, (_rank, top_candidates, measure) in best_by_theme.items():
        bundles = [_make_bundle_item(theme, measure, top_candidates)]
        bundle_items_by_theme[theme] = bundles[:max_bundles_per_theme]
        if not bundle_items_by_theme[theme]:
            continue
        represented_ids.update(_item_id(item) for item in top_candidates)

    if not represented_ids:
        return items

    emitted_themes: set[str] = set()
    output: list[dict[str, Any]] = []
    for item in items:
        item_id = _item_id(item)
        if item_id not in represented_ids:
            output.append(item)
            continue
        theme = _theme_for_item(item)
        if theme is None or theme in emitted_themes:
            continue
        emitted_themes.add(theme)
        output.extend(bundle_items_by_theme.get(theme, []))

    return output


# ── Theme bundles (geopolitics archetype — Phase 1, slice 1) ──────────────────


def _theme_story_key(item: dict[str, Any]) -> str | None:
    """Story key for a feed item, or None if it is not foldable into a theme.

    Prefers the ``_quality_story_key`` the scoring pass already attached, because
    that is the key the upstream diversity caps grouped on AND the one that
    honours a ``persisted_story_key`` override (``classify_market_quality`` ->
    ``enrich_markets``). Falling out of step with the caps would let the bundler
    group on a different key than the one that decided how many members survived.

    Falls back to recomputing from the public name/category when the field is
    absent or not a real key — the serving path pops ``_quality_story_key``
    later, so this keeps the bundler decoupled from field lifecycle (and makes
    the function safe to call on already-cleaned items).
    """
    data = _futures_data(item)
    if not data:
        return None
    carried = item.get("_quality_story_key")
    if isinstance(carried, str) and carried.startswith("story:"):
        return carried
    name = str(data.get("name") or "")
    if not name:
        return None
    category = data.get("llm_sport_category") or data.get("sport") or ""
    return compute_story_key(name, str(category))


def _theme_member_eligible(item: dict[str, Any]) -> bool:
    """Whether a candidate may be folded into a theme bundle.

    Theme bundles carry no threshold points (unlike comparison bundles), so the
    gates that apply are the two that decide whether a card is publishable at
    all: source disagreement is a data bug we never surface as a feature ("the
    blend is the product"), and a low-quality family is suppressed rather than
    promoted into a bundle.
    """
    if item.get("_quality_class") == "low_quality":
        return False
    card = _discover_card(_futures_data(item))
    if card.get("public_source_disagreement"):
        return False
    return True


# Back-compat alias for slice-1 callers/tests.
_geopolitics_story_key = _theme_story_key


def _theme_bundle_id(story_key: str, items: list[dict[str, Any]]) -> str:
    ids = "-".join(str(_futures_data(item).get("id")) for item in items)
    return f"theme:{story_key}:{ids}"


# ── A SHARED QUESTION IS A CLAIM ABOUT THE MEMBERS (#4147) ───────────────────
#
# `resolve_story_question` reads AUTHORED_STORY_QUESTIONS by `story_key` alone
# and never looks at who is in the group, so an authored sentence bypasses the
# guard the derived path already carries ("No shared phrase means no question
# means no bundle"). Served on production 2026-09-10 20:36Z:
#
#     Who wins the World Cup?
#       · 2027 FIFA Women's World Cup Champion   soccer:FIFA_WC:championship:2027
#       · 2030 FIFA World Cup Champion           soccer:FIFA_WC:championship:2030
#
# Two tournaments three years apart under one question in the singular. A reader
# who restates the header — the D1 bar — is handed Spain at 20% and France at
# 12% and cannot tell which one answers it. Neither does.
#
# THE AXIS IS SEASON, NOT COHORT, AND THAT IS A MEASUREMENT RATHER THAN A TASTE.
# The obvious key ("men's and women's are different cohorts") was checked against
# all nine theme bundles served at that timestamp and is WRONG: it would also
# split `story:grand_slam_tennis`, whose members are the US Open men's and
# women's singles — `tennis::championship:2026` for both, the same tournament in
# the same season, and a group a reader wants kept. Season splits the World Cup
# and touches nothing else: 1 of the 9 changes, and it is the defect.
#
# AN UNKNOWN SEASON NEVER SPLITS. Four of those nine (ai, macro_rates,
# middle_east_conflict, russia_ukraine) carry members with no canonical key at
# all, so reading "unknown" as disagreement would dissolve four honest bundles on
# missing data — the fix would cost more than the bug. Only two members that both
# STATE a season, and state different ones, are evidence the question is false.
#
# Season comes from the canonical key and not from `resolution_date`: the 2030
# World Cup resolves 2031-01-15, so the date's year is not the season.

#: `futures_categorization.compute_canonical_market_key` builds exactly
#: ``{sport}:{league}:{category}:{season}`` — always four parts, any of which may
#: be empty. Read positionally, so a malformed key degrades to "season unknown"
#: rather than raising inside the feed (gotcha #42).
_CANONICAL_KEY_PARTS = 4
_CANONICAL_KEY_SEASON_INDEX = 3


def _member_season(item: dict[str, Any]) -> str | None:
    """The season a member states, or ``None`` when it does not state one."""
    key = _futures_data(item).get("canonical_market_key")
    if not isinstance(key, str):
        return None
    parts = key.split(":")
    if len(parts) != _CANONICAL_KEY_PARTS:
        return None
    return parts[_CANONICAL_KEY_SEASON_INDEX].strip() or None


def _members_span_multiple_seasons(items: list[dict[str, Any]]) -> bool:
    """Whether two members state seasons that disagree.

    False when every member is silent about its season, and false when only one
    of them speaks — see the block above for why silence is not disagreement.
    """
    seasons = {season for season in map(_member_season, items) if season}
    return len(seasons) > 1


# ── A DERIVED KEY CANNOT BE AUTHORED, SO ITS COPY IS CUT FROM THE MEMBERS ────
#
# #6423 mints one story key PER GOLF TOURNAMENT, which means the key did not
# exist when this file was written and can never appear in AUTHORED_STORY_TITLES
# or AUTHORED_STORY_QUESTIONS. Both fallbacks below it are wrong here:
#
#   `_derive_story_title` un-slugifies the key   -> "Golf Tournament:bmw PGA Championship"
#   `_shared_member_phrase` lower-cases and stri -> "nationwide children s hospital championship"
#
# and either would be the bundle's HEADLINE on a reader's screen (notice 34).
# So the tournament is cut verbatim out of a member's own name by the same
# grammar that minted the key, and the question is authored once for the
# prefix.
#
# 🔴 THE QUESTION IS "WHAT HAPPENS AT", NOT "WHO WINS", AND THAT IS #4147's
# RULE APPLIED BEFORE IT COULD BITE. A shared question is a claim about the
# members, and these members are not all about winning: the family is winner,
# the cut, top-5/10/20, each round's leader, a hole-in-one, a playoff and an
# albatross. "Who wins the BMW PGA Championship?" — the phrasing the neighbouring
# authored golf key uses — is false of the hole-in-one row sitting right under
# it. "What happens at the BMW PGA Championship?" is true of every member, which
# is the bar clause (c) actually sets.
def _golf_tournament_bundle_copy(
    story_key: str, member_names: list[str]
) -> tuple[str, str] | None:
    """``(label, question)`` for a derived golf-tournament family, or None."""
    names = [
        tournament
        for tournament in (golf_tournament_display_name(n) for n in member_names)
        if tournament
    ]
    if not names:
        # Fail closed: no member states a tournament we can name, so there is
        # no honest headline and the members compete on their own.
        return None
    # Members of one key slugify identically, so this only ever picks between
    # spellings of the same tournament; the most common wins, ties by first
    # appearance (i.e. by the best-scoring member).
    label = max(names, key=lambda t: (names.count(t), -names.index(t)))
    article = "" if _LABEL_LEAD_RE.match(label) else "the "
    return label, f"What happens at {article}{label}?"


def _make_theme_bundle_item(
    story_key: str, items: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """The folded bundle, or None when the family shares no statable question.

    Returns None rather than folding on "N related markets" (D1 clause c):
    a group that cannot say what its members have in common is not a story, and
    its members are better off competing for their own slots — which is exactly
    where they were before this bundler ran.

    #4147 adds a second way to have no statable question: the family HAS an
    authored sentence, but its members span more than one season, so the
    sentence is false of the set. The outcome is deliberately the same
    `None` — clause (c) already says what to do with a group that cannot
    honestly say what its members have in common, and re-wording the header
    ("World Cup markets") would keep a card whose two rows answer two different
    questions. Splitting hands the reader "2030 FIFA World Cup Champion —
    France 12%", which is true.
    """
    # Members ranked by feed score (most feed-worthy leads the mini-ranked-peek);
    # the bundle competes for ONE slot scored by its best member.
    ranked = sorted(items, key=lambda it: float(it.get("score") or 0), reverse=True)
    score = max(float(item.get("score") or 0) for item in ranked)
    sort_time = max(float(item.get("_sort_time") or 0) for item in ranked)
    label, title_source = _resolve_story_title(story_key)
    member_ids = [_futures_data(item).get("id") for item in ranked]
    member_names = [str(_futures_data(item).get("name") or "") for item in ranked]
    question, question_source = resolve_story_question(story_key, member_names)
    if story_key.startswith(GOLF_TOURNAMENT_STORY_PREFIX):
        resolved = _golf_tournament_bundle_copy(story_key, member_names)
        if resolved is None:
            return None
        label, question = resolved
        title_source = question_source = "golf_tournament"
    if not question:
        return None
    if _members_span_multiple_seasons(ranked):
        # Logged rather than silent: a family folding away is invisible on the
        # page (its members simply compete on their own), so ops needs the
        # reason or the next reader has to re-derive it from an absence.
        logger.info(
            "discover_bundle: refused a shared question across seasons",
            extra={
                "story_key": story_key,
                "question_source": question_source,
                "member_ids": member_ids,
                "seasons": sorted(
                    {s for s in map(_member_season, ranked) if s}
                ),
            },
        )
        return None
    return {
        "type": "bundle",
        "score": score,
        "reason": question,
        "headline": label,
        "data": {
            "id": _theme_bundle_id(story_key, ranked),
            "title": label,
            "kind": "theme",
            "story_key": story_key,
            "shared_question": question,
            "item_count": len(ranked),
            "member_ids": member_ids,
            "items": [_public_member_item(item) for item in ranked],
            "debug_bundles": {
                "grouped_by": "story_key",
                "story_key": story_key,
                "title_source": title_source,
                "question_source": question_source,
                "member_ids": member_ids,
                "member_names": [
                    _futures_data(item).get("name") for item in ranked
                ],
            },
        },
        "_sort_time": sort_time,
    }


#: A trailing parenthetical qualifier on a market title (#4479).
#:
#: Polymarket disambiguates its own catalogue in parentheses — "2026 Men's US Open
#: Winner (Tennis)" exists because it also lists a golf US Open. That suffix is
#: bookkeeping about the VENUE's catalogue, not part of the question, and Kalshi's
#: listing of the same question has no equivalent. It costs the pair a token on one
#: side only, which is a pure penalty in a Jaccard.
_TRAILING_QUALIFIER_RE = re.compile(r"\s*\(([^()]{1,24})\)\s*$")

#: A leading edition year on a market title (#4479).
_LEADING_YEAR_RE = re.compile(r"^\s*(19|20)\d{2}\s+")

#: Any four-digit year anywhere in a title — used only to ask "does the OTHER side
#: name a year at all", never to decide that two years are the same.
_ANY_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


#: Two rows resolving closer together than this cannot be two consecutive annual
#: editions of one title, which is the whole hazard removal 3 has to exclude
#: (#6537). Half a year, DERIVED from the yearly repeat it must separate and not
#: tuned against a specimen: the pair it admits resolves 90 days apart (a midterm
#: settles on election night at one venue and at the seating of Congress at the
#: other), the pair it must refuse — this year's Masters beside next year's —
#: resolves 365.
_SAME_CYCLE_MAX_DAYS = 182


def _resolution_year(data: dict[str, Any]) -> int | None:
    """The year a market resolves in, or None if it does not say."""
    raw = data.get("resolution_date")
    if not raw:
        return None
    match = _ANY_YEAR_RE.search(str(raw))
    return int(match.group(0)) if match else None


def _resolution_date(data: dict[str, Any]) -> datetime | None:
    """The instant a market resolves, or None if it does not say it parseably."""
    raw = data.get("resolution_date")
    if not raw:
        return None
    if isinstance(raw, datetime):
        return raw
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None


def _resolve_within_one_cycle(data: dict[str, Any], other: dict[str, Any]) -> bool:
    """Do these two rows settle the SAME edition of a yearly question? (#6537)

    Answered from the two resolution dates and nothing else: if they are less
    than :data:`_SAME_CYCLE_MAX_DAYS` apart they cannot be consecutive annual
    editions, whatever their titles say. A row that does not state a parseable
    resolution date answers False — an absent date is not evidence.
    """
    left, right = _resolution_date(data), _resolution_date(other)
    if left is None or right is None:
        return False
    if (left.tzinfo is None) != (right.tzinfo is None):
        return False
    return abs((left - right).days) < _SAME_CYCLE_MAX_DAYS


def _priced_outcome_names(data: dict[str, Any]) -> frozenset[str]:
    """The names of the outcomes a card actually PRICES, lowercased (#6537).

    PRICED, not all: Polymarket's "Which party will win the House in 2026?"
    carries seven legs a reader never sees — ``Party A`` … ``Party F`` and
    ``Other``, every one with a NULL probability — beside the two it prices. A
    naive "same outcomes" test reads that as a different question; the card
    renders a single 88% hero off its priced legs, and so does its Kalshi twin.
    """
    names = set()
    for outcome in data.get("top_outcomes") or ():
        if not isinstance(outcome, dict) or outcome.get("probability") is None:
            continue
        name = str(outcome.get("name") or "").strip().lower()
        if name:
            names.add(name)
    return frozenset(names)


def _comparison_title(data: dict[str, Any], other: dict[str, Any]) -> str:
    """The title to hand the matcher, with two venue artefacts removed (#4479).

    A PAIRWISE function, not a normalizer: what may be dropped from one title
    depends on what the other title says. Both removals are conservative in the
    direction that matters — a deduper that over-pairs DELETES a card the reader
    wanted, so each one is gated on evidence from the other row rather than
    applied unconditionally.

    1. **A trailing parenthetical qualifier**, always. ``(Tennis)`` on Polymarket's
       "2026 Men's US Open Winner (Tennis)" disambiguates that venue's own
       catalogue against its golf US Open; Kalshi's listing of the identical
       question carries nothing equivalent. Dropped on both sides so the rule is
       symmetric.

    2. **A leading edition year, but ONLY when the other title names no year at
       all AND both rows resolve in that same year.** The year is load-bearing
       whenever both sides carry one: "2027 FIFA Women's World Cup Champion"
       beside "2030 FIFA World Cup Champion" is two different tournaments, and
       the matcher's own ``left_num != right_num`` guard refuses it. That guard
       is untouched here — this only reaches the case where one venue dates its
       title and the other leaves the edition implicit, and the resolution dates
       agree that they mean the same edition. Without the resolution-date check
       an undated "Masters Winner" for next year's edition would fold onto a
       dated one for this year's.

    3. **A year ANYWHERE in the title, on four gates that must all hold** (#6537).
       Removal 2 reaches an edition PREFIX; a year can also sit inside the
       sentence as a qualifier, and then it is not naming an edition at all:
       Kalshi's "Which party will win the U.S. House?" and Polymarket's "Which
       party will win the House **in 2026**?" are one question — same midterms,
       same two priced parties, 86% beside 88% two cards apart on one Discover
       load — and the matcher's ``left_num != right_num`` guard refuses them
       because one side carries ``2026`` and the other carries nothing.

       That guard is still untouched, and deliberately: it is what keeps "Fed
       rate hike in 2026?" apart from "Fed rate hike in 2027?" and every
       ``Above 40`` rung apart from ``Above 50``. This reaches only the case
       where one side is SILENT about the year, and it must clear all four:

       * the title names exactly one year, and the other title names none —
         two stated years are two questions, always;
       * the dated row's own resolution year is that year or the next, so the
         venue's date agrees with the venue's title;
       * the two rows resolve inside one cycle (:func:`_resolve_within_one_cycle`)
         — this is what refuses the undated "Masters Winner" beside a dated one
         a year later, the hazard removal 2's tighter date check exists for;
       * the two rows price the SAME outcome names, non-empty — the independent,
         row-level second signal a title match is only a candidate without.

       The four rows on the same page that come closest to this shape all stay
       refused, three of them on the first gate alone: ``#1 Paid App`` beside
       ``#2``, the 2027 Women's World Cup beside the 2030 men's, the U.S. House
       beside the U.S. Senate, Ankara's high temperature beside Dallas's.

    WHY THIS IS NOT A THRESHOLD MOVE, measured on the 23 same-bundle pairs served
    on page one at 13:30 PT 2026-09-09:

    ==========================================  =======  ===========  ==========
    pair                                        jaccard  containment  verdict
    ==========================================  =======  ===========  ==========
    2026 Men's US Open Winner (Tennis)
      vs US Open Men's Singles Winner             0.625        0.833  DUPLICATE
    US Open Men's Singles Winner
      vs US Open Women's Singles Winner           0.714        0.833  must refuse
    ==========================================  =======  ===========  ==========

    **The duplicate scores LOWER than the control that must never fold.** No
    relaxation of the 0.72 / 0.85 thresholds can separate them; one that admits
    0.625 admits 0.714 and deletes the women's draw. Only making the two titles
    comparable BEFORE they are scored does. After this function the same three
    pairs read 0.833 (duplicate, folds) / 0.714 (men-vs-women, unchanged and
    refused) / 0.571 (dated men's vs women's, refused), which is separation with
    room in it rather than a tuned threshold.

    Deliberately at the bundler and not inside ``is_same_question``: that function
    is shared with the category-page spotlight, #4446 recorded that widening it
    "would move three category pages", and it takes two strings — it cannot see
    the resolution dates that gate removal 2. The blast radius of this stays
    inside the one caller that has the evidence.
    """
    title = str(data.get("name") or "")
    other_title = str(other.get("name") or "")

    title = _TRAILING_QUALIFIER_RE.sub("", title)
    other_stripped = _TRAILING_QUALIFIER_RE.sub("", other_title)

    if _LEADING_YEAR_RE.match(title) and not _ANY_YEAR_RE.search(other_stripped):
        year = int(_LEADING_YEAR_RE.match(title).group(0).strip())
        if _resolution_year(data) == year and _resolution_year(other) == year:
            title = _LEADING_YEAR_RE.sub("", title, count=1)

    if _ANY_YEAR_RE.search(title) and not _ANY_YEAR_RE.search(other_stripped):
        years = {match.group(0) for match in _ANY_YEAR_RE.finditer(title)}
        if len(years) == 1:
            year = int(years.pop())
            priced = _priced_outcome_names(data)
            if (
                _resolution_year(data) in (year, year + 1)
                and _resolve_within_one_cycle(data, other)
                and priced
                and priced == _priced_outcome_names(other)
            ):
                title = _ANY_YEAR_RE.sub("", title).strip()

    return title


def _dedupe_same_question_members(
    members: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split a story cluster into (kept, folded): one row per question.

    #4446 — a card whose whole job is to fold a family was serving the family's
    duplicates. On production 2026-09-09 the World Cup bundle carried BOTH
    Kalshi's "2027 FIFA Women's World Cup Champion" and Polymarket's "FIFA
    Women's World Cup 2027 Winner", two rows apart, in the collapsed peek (all
    three members render above the fold at ``PEEK_COUNT = 5``); the Fed & Rates
    bundle carried the same shape. That is the standing ruling read backwards —
    "the blend is the product: one number per question" — and the feed audit
    target is ``duplicate-family-rate@20=0``.

    Two gates, and BOTH are required:

    * the venues differ. Two questions from ONE venue are that venue's own
      distinct listings, and folding them is not ours to do.
    * :func:`is_same_question` pairs the titles — the matcher's own two passes,
      whose discrimination against the neighbours this bundler actually serves
      is measured in that function's docstring and bound by its tests.

    Why not ``canonical_market_key``, which is on the wire and looks purpose-built:
    it is a ``category:league:type:year`` BUCKET, not a question key, and the
    census that checked said so loudly. Of the 8 keys served more than once on
    page one that day, exactly ONE pair was a real duplicate; the same key held
    the Oscar beside the Grammy, the Texas Senate beside the New York Governor,
    three different NASCAR series, and — inside a single bundle — the men's US
    Open beside the women's. Deduping on it would have deleted the women's US
    Open from the Grand Slam card.

    The FIRST member of a matched pair survives: ``members`` arrives in feed
    rank order, so the survivor is the better-ranked row, which is also the one
    the bundle's own question and score were derived from.

    #4479 — THE TITLES ARE COMPARED AFTER :func:`_comparison_title`, not raw. The
    first read taken after #4446 deployed found the next instance of this class one
    bundle over: the Grand Slam card rendered the men's US Open TWICE, Polymarket's
    "2026 Men's US Open Winner (Tennis)" at Zverev 46% beside Kalshi's "US Open
    Men's Singles Winner" at Zverev 30%, two rows apart under "Who wins the Slam?".
    Two numbers for one question, sixteen points apart, both rows advertising
    ``sources: [kalshi, polymarket]``. The raw titles are refused by the matcher and
    correctly so — the pair scores 0.625 while the men's-vs-women's pair that must
    NEVER fold scores 0.714, so no threshold separates them. See that function.
    """
    from app.utils.cross_source_matching import is_same_question

    kept: list[dict[str, Any]] = []
    folded: list[dict[str, Any]] = []
    for item in members:
        data = _futures_data(item)
        source = str(data.get("source") or "")
        duplicate = any(
            str(_futures_data(k).get("source") or "") != source
            and is_same_question(
                _comparison_title(_futures_data(k), data),
                _comparison_title(data, _futures_data(k)),
            )
            for k in kept
        )
        (folded if duplicate else kept).append(item)
    return kept, folded


def fold_same_question_cards(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop a standalone card that asks a question an earlier card already asked.

    #6400 — :func:`_dedupe_same_question_members` above has folded cross-venue
    duplicates INSIDE a bundle since #4446, and the standalone card list has
    never been asked the same question. On production 2026-09-15 Discover dealt
    Polymarket's "Brazil Presidential Election" (Flávio Bolsonaro 52%) and
    Kalshi's "Brazil Presidential election winner?" (Flávio Bolsonaro 54%) as
    two cards 1,156 px apart on one load, ranks 6 and 7 of the served payload.
    Polymarket's own Gamma record for event 45915 settles that they are one
    question — *"resolve according to the listed candidate that wins this
    election … includes any potential second round"* — which is exactly what
    Kalshi's ``KXBRPRES-26`` asks.

    The two caps that DO run on this list cannot see such a pair, and neither is
    broken: ``diversify_quality_families(exact_family_cap=1)`` keys on the
    normalized NAME, so one trailing word ("winner") is a second family, and the
    story cap cannot fire because ``_subnational_election_story_key`` returns
    ``None`` for anything presidential — a national race deliberately is not a
    local election. An exact-name cap is a same-WORDING cap, and a cross-venue
    duplicate is by definition differently worded.

    Same two gates as the bundle sibling, for the same reasons, and BOTH are
    required: the venues differ, and :func:`is_same_question` pairs the titles
    after :func:`_comparison_title`. Not a third mechanism — the discrimination
    this leans on is the one measured in that predicate's docstring and bound by
    its tests, and the standing ruling behind both is one number per question.

    Differences from the sibling, which is why this is not the same function:

    * it walks a MIXED list — events, bundles, concepts and tournaments pass
      through untouched, and only ``type: "futures"`` items are compared;
    * it runs on a list two orders of magnitude longer than a bundle's members,
      so it carries :func:`could_be_same_question` as a prefilter (see there for
      why excluding on shared tokens cannot hide a pair);
    * one malformed card must never wipe the pass (#1091 / gotcha 42), so a
      comparison that raises KEEPS the card and moves on.

    ``items`` arrives in rank order, so the survivor is the better-ranked card —
    the same contract the sibling states.
    """
    from app.utils.cross_source_matching import (
        could_be_same_question,
        is_same_question,
        same_question_tokens,
    )

    kept: list[dict[str, Any]] = []
    # Parallel to `kept`, holding (source, tokens, data) for the futures entries
    # only — `None` for every other card type, so indexes stay aligned and a
    # non-futures card is skipped by a single identity check.
    kept_keys: list[tuple[str, frozenset[str], dict[str, Any]] | None] = []

    for item in items:
        data = _futures_data(item)
        if not data:
            kept.append(item)
            kept_keys.append(None)
            continue

        source = str(data.get("source") or "")
        tokens = same_question_tokens(str(data.get("name") or ""))

        duplicate = False
        for key in kept_keys:
            if key is None:
                continue
            kept_source, kept_tokens, kept_data = key
            if kept_source == source:
                continue
            if not could_be_same_question(kept_tokens, tokens):
                continue
            try:
                duplicate = is_same_question(
                    _comparison_title(kept_data, data),
                    _comparison_title(data, kept_data),
                )
            except Exception:  # pragma: no cover - defensive, see docstring
                logger.warning(
                    "Discover: same-question fold skipped a pair (%r vs %r)",
                    kept_data.get("name"),
                    data.get("name"),
                    exc_info=True,
                )
                duplicate = False
            if duplicate:
                break

        if duplicate:
            continue
        kept.append(item)
        kept_keys.append((source, tokens, data))

    return kept


def assemble_story_theme_bundles(
    items: list[dict[str, Any]],
    *,
    min_items: int = 2,
    max_items_per_bundle: int = 6,
) -> list[dict[str, Any]]:
    """Cap-and-FOLD ANY eligible story cluster into one expandable theme bundle.

    Replaces the scatter (N separate same-story cards) with ONE ``type:bundle``
    item (``kind="theme"``) that carries the members ranked for a mini-ranked-peek
    and full expansion. The bundle takes a single feed slot scored by its best
    member. A cluster with fewer than ``min_items`` eligible members is left
    untouched.

    Queue 307 generalized this from a two-key geopolitics allowlist to an
    eligibility predicate: a cluster folds iff its ``story_key`` is non-null
    (:func:`_theme_story_key`) and its members pass :func:`_theme_member_eligible`.
    Orthogonal to the comparison bundler and to the awards/``group_id`` bundler;
    a market belongs to at most one.

    On ``min_items`` — WHY THE DEFAULT IS 2, NOT 3
    ----------------------------------------------
    Queue 307 specified ``min_items=3``. That is not reachable for most stories,
    because this bundler runs at ``feed.py:2168``, i.e. AFTER the per-story
    diversity caps have already thinned the tail at ``feed.py:6972-6977``
    (``diversify_quality_families``). Those caps are the binding constraint, and
    several are BELOW 3::

        story:us_2028_election    cap 2  -> a 3-pack can never form
        story:russia_ukraine      cap 2  -> a 3-pack can never form
        story:ai                  cap 2  -> a 3-pack can never form
        story:macro_rates         cap 3
        story:middle_east_conflict cap 4
        (unlisted keys)           cap 5  (story_family_cap default)

    So ``min_items=3`` would BREAK the existing ``story:russia_ukraine`` bundle
    (which folds at 2 today) and would never produce the ``story:us_2028_election``
    pack the queue named as its headline payoff. Keeping the default at 2
    preserves current behaviour exactly and lets every newly-eligible key fold.
    Raising it is a one-argument change once the upstream caps are revisited.
    """
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        if not _theme_member_eligible(item):
            continue
        story_key = _theme_story_key(item)
        if story_key is None:
            continue
        groups.setdefault(story_key, []).append(item)

    bundle_by_story: dict[str, dict[str, Any]] = {}
    represented_ids: set[str] = set()
    for story_key, members in groups.items():
        if len(members) < min_items:
            continue
        # The same question from two venues is ONE row (#4446). Folded BEFORE the
        # cap so a duplicate does not spend a member slot the next distinct
        # question could have had.
        members, folded = _dedupe_same_question_members(members)
        if len(members) < min_items:
            continue
        chosen = members[:max_items_per_bundle]
        if len(chosen) < min_items:
            continue
        bundle = _make_theme_bundle_item(story_key, chosen)
        if bundle is None:
            # No statable shared question — leave the members unfolded rather
            # than spend a slot on "N related markets" (D1 clause c, #4066).
            continue
        bundle_by_story[story_key] = bundle
        represented_ids.update(_item_id(item) for item in chosen)
        # A folded duplicate is REPRESENTED by the row that survived it, not
        # dropped: without this it would fall through the emit loop below and
        # come back as its own standalone card, which moves the duplicate down
        # the page instead of removing it. Only claimed once the bundle actually
        # formed — a cluster that could not state a shared question keeps every
        # member, duplicate included, because there is no surviving row to
        # represent it.
        represented_ids.update(_item_id(item) for item in folded)

    if not represented_ids:
        return items

    emitted: set[str] = set()
    output: list[dict[str, Any]] = []
    for item in items:
        if _item_id(item) not in represented_ids:
            output.append(item)
            continue
        story_key = _theme_story_key(item)
        bundle = bundle_by_story.get(story_key) if story_key else None
        if bundle is None:
            # Defensive (gotcha #42): a member we can no longer resolve to its
            # bundle is emitted as its own card rather than silently dropped.
            output.append(item)
            continue
        if story_key in emitted:
            continue
        emitted.add(story_key)
        output.append(bundle)

    return output


# Back-compat alias: slice 1 shipped this name and ``feed.py`` imports it.
# Kept so the generalization needs no import churn at the call site.
assemble_geopolitics_theme_bundles = assemble_story_theme_bundles


# ── Theme bundles (awards / competition archetype — Phase 1, slice 3) ──────────
#
# Entertainment award/competition futures (e.g. "Who wins Best Picture?" with N
# nominee sub-markets) already share a ``FuturesMarket.group_id`` (set during
# Polymarket polling as ``polymarket:{event_id}``). Today ``_dedupe_futures_by_
# group_id`` collapses the whole race to ONE surviving card and DROPS the rest —
# the multi-angle richness is lost. This bundler folds the full race into one
# expandable ``type:bundle`` ``kind="theme"`` item (same shape slice 1 emits),
# keyed on ``group_id`` instead of ``story_key``.
#
# The dropped same-group siblings are preserved by the dedupe step on the
# surviving item under the private ``_grouped_members`` key (stripped from the
# default-feed response); this bundler reconstructs the full race from the
# survivor + its stashed siblings. Discover-mode only, like slice 1.


def _is_entertainment(item: dict[str, Any]) -> bool:
    data = _futures_data(item)
    category = data.get("llm_sport_category") or data.get("sport") or ""
    return str(category).strip().lower() == "entertainment"


def _grouped_members(item: dict[str, Any]) -> list[dict[str, Any]]:
    members = item.get("_grouped_members")
    return members if isinstance(members, list) else []


def _award_members_for(item: dict[str, Any]) -> list[dict[str, Any]] | None:
    """Full race member set for an entertainment group_id survivor, or None.

    Returns ``[survivor] + dropped_siblings`` when this item is the surviving
    card of an entertainment ``group_id`` cluster with at least one dropped
    sibling (≥2 members total). Non-entertainment / no-group / single-member
    items return None.
    """
    if not _is_entertainment(item):
        return None
    data = _futures_data(item)
    if not data.get("group_id"):
        return None
    siblings = _grouped_members(item)
    if not siblings:
        return None
    return [item, *siblings]


_LABEL_LEAD_RE = re.compile(r"^(will|the|a|an)\s+", re.I)


def _name_tokens(name: str) -> list[str]:
    return re.sub(r"[^\w\s]", " ", (name or "").lower()).split()


def _contains_subseq(tokens: list[str], seq: list[str]) -> bool:
    n = len(seq)
    if n == 0 or n > len(tokens):
        return False
    return any(tokens[i : i + n] == seq for i in range(len(tokens) - n + 1))


def _shared_member_phrase(names: list[str]) -> str | None:
    """The longest contiguous word run present in EVERY member name, or None.

    The strict half of `_derive_race_label`: a phrase the members demonstrably
    share, with no fallback to one member's own title. Runs shorter than two
    words are not evidence of a shared subject ("the", "2026"), so they return
    None. Factored out for `resolve_story_question`, which must be able to tell
    "these belong together and here is why" from "these were adjacent".
    """
    cleaned = [n.strip() for n in names if n and n.strip()]
    if len(cleaned) < 2:
        return None
    token_lists = [_name_tokens(n) for n in cleaned]
    base = min(token_lists, key=len)
    best: list[str] = []
    for i in range(len(base)):
        for j in range(len(base), i + len(best), -1):
            seq = base[i:j]
            if len(seq) <= len(best):
                break
            if all(_contains_subseq(tl, seq) for tl in token_lists):
                best = seq
                break
    if len(best) < 2:
        return None
    phrase = _LABEL_LEAD_RE.sub("", " ".join(best)).rstrip("? ").strip()
    return phrase or None


def _derive_race_label(names: list[str]) -> str:
    """Derive a race/group label from member names.

    Uses the longest contiguous word run shared by ALL member names (the common
    race phrase, e.g. "best actor at the 99th academy awards"); falls back to the
    shortest member name. Best-effort — the mini-ranked-peek members disambiguate.

    🔴 THE FALLBACK MAKES THIS WRONG FOR ANY CALLER THAT HAS NOT ALREADY PROVEN
    ITS MEMBERS BELONG TOGETHER. Callers keying on `group_id` have; a story-key
    cluster has not. Those want `_shared_member_phrase` above.

    🔴 AND "BELONG TOGETHER" WAS NEVER ENOUGH TO NAME A CONTEST. The paragraph
    above cleared `group_id` callers, and that clearance was read as licence to
    wrap this label in `f"Who wins {label}?"`. Proving the members are one
    Polymarket event does NOT prove the phrase they share is a noun phrase
    naming something anyone WINS: measured over all 48 live entertainment
    clusters, this returns "Have a" (24 members), "In 2026", "1", "Be evicted"
    and "Mark Ruffalo as Hulk" (the shortest-member fallback, inside a
    `group_id` caller). So this stays what it is — a SHORT CHIP LABEL, best
    effort — and no caller may build a sentence out of it. The question comes
    from `_award_group_question`, which reads the venue's own parent market.
    """
    cleaned = [n.strip() for n in names if n and n.strip()]
    if not cleaned:
        return "Related markets"
    shared = _shared_member_phrase(cleaned)
    if shared:
        label = shared
    else:
        label = min(cleaned, key=len)
    label = _LABEL_LEAD_RE.sub("", label).rstrip("? ").strip()
    if not label:
        return "Related markets"
    label = label[:80].strip()
    return label[:1].upper() + label[1:]


def _award_group_question(members: list[dict[str, Any]]) -> str | None:
    """The VENUE'S OWN question for a Polymarket event cluster, or None.

    A Polymarket event stores its question once, on the parent row
    (`group_type="polymarket_event"`), and prices it on the children
    (`polymarket_sub_market`). That parent name is the question the members are
    all answers to, authored by the venue — "Who will be evicted from Big
    Brother? (Week 10)", "Which characters will appear in Avengers: Doomsday?",
    "Oscars 2027: Best Actor Nominations". We never have to derive it, and any
    derivation we attempt is strictly worse than reading it.

    🔴 THIS REPLACES `f"Who wins {label}?"`, WHICH WAS A CLAIM WE MANUFACTURED
    AND MOST OF THESE MARKETS CONTRADICT. Of the 48 live entertainment clusters
    (production, 2026-09-15), the template asserted a contest-with-a-winner over
    markets pricing who is EVICTED, who DIES ("Who wins Witcher season 5?"), who
    is merely NOMINATED, who PARTICIPATES and who is CAST — and it read as
    nonsense on the fragments `_derive_race_label` returns ("Who wins Have a?",
    "Who wins 1?"). The live specimen was "Who wins Be evicted?" on Discover
    page one, over four Big Brother eviction markets, with the most-likely
    EVICTEE shown at 62% under the word "wins".

    Why the discriminator is `group_type` and not `market_type`: the parent is
    whichever row carries the Polymarket EVENT id in `external_id` while the
    children carry condition hashes, and `group_type` records exactly that.
    `market_type` does not — it reads `unshaped` on the "#1 Show on Netflix"
    parent and `field` on that cluster's child, picking the wrong row. Measured
    over the same 48 clusters: `group_type` names exactly one parent in 47 and
    agrees with the `external_id` anchor on 47/47; the 48th has no parent row at
    all, and that is the `None` below.

    None means we cannot state the question, NOT that the bundle dies: the
    caller still folds, and both bundle cards already render the member count
    when `shared_question` is absent. #4147 ruled that trade explicitly — an
    uninformative count is honest, a wrong sentence is not.
    """
    authored = [
        _futures_data(item).get("name")
        for item in members
        if str(_futures_data(item).get("group_type") or "") == "polymarket_event"
    ]
    names = [str(name).strip() for name in authored if name and str(name).strip()]
    if len(names) != 1:
        return None
    return names[0]


def _make_awards_bundle_item(
    group_id: str, members: list[dict[str, Any]]
) -> dict[str, Any]:
    ranked = sorted(members, key=lambda it: float(it.get("score") or 0), reverse=True)
    score = max(float(item.get("score") or 0) for item in ranked)
    sort_time = max(float(item.get("_sort_time") or 0) for item in ranked)
    member_ids = [_futures_data(item).get("id") for item in ranked]
    names = [str(_futures_data(item).get("name") or "") for item in ranked]
    # The chip's short subject. Best effort and NOT a sentence — see the 🔴 on
    # `_derive_race_label`. The chip is `whitespace-nowrap`, so the venue's full
    # question cannot go here; it goes in the heading below.
    label = _derive_race_label(names)
    # D1 clause c (#4066): the heading is the one sentence saying why these
    # members belong together. It is the venue's own parent question, or absent.
    question = _award_group_question(ranked)
    return {
        "type": "bundle",
        "score": score,
        "reason": question or "",
        "headline": label,
        "data": {
            "id": f"theme:{group_id}:{'-'.join(str(m) for m in member_ids)}",
            "title": label,
            "kind": "theme",
            "shared_question": question,
            "group_id": group_id,
            "item_count": len(ranked),
            "member_ids": member_ids,
            "items": [_public_member_item(item) for item in ranked],
            "debug_bundles": {
                "grouped_by": "group_id",
                "group_id": group_id,
                "member_ids": member_ids,
                "member_names": names,
                # Mirrors `resolve_story_question`'s `source`: a cluster folding
                # with no stateable question is visible in ops rather than
                # having to be inferred from a missing heading.
                "question_source": "venue_parent" if question else "none",
            },
        },
        "_sort_time": sort_time,
    }


def assemble_awards_theme_bundles(
    items: list[dict[str, Any]],
    *,
    min_items: int = 2,
    max_items_per_bundle: int = 8,
) -> list[dict[str, Any]]:
    """Cap-and-FOLD entertainment award/competition group_id clusters into one
    expandable theme bundle.

    Mirrors :func:`assemble_geopolitics_theme_bundles` but keys on ``group_id``
    (reconstructed from the dedupe-preserved ``_grouped_members``) and is scoped
    to entertainment award/competition futures. Orthogonal to the geopolitics
    bundler (that keys on ``story_key``); a market belongs to at most one.
    """
    bundle_by_group: dict[str, dict[str, Any]] = {}
    survivor_ids: set[str] = set()
    for item in items:
        members = _award_members_for(item)
        if members is None or len(members) < min_items:
            continue
        group_id = str(_futures_data(item).get("group_id"))
        chosen = members[:max_items_per_bundle]
        bundle_by_group[group_id] = _make_awards_bundle_item(group_id, chosen)
        survivor_ids.add(_item_id(item))

    if not bundle_by_group:
        return items

    output: list[dict[str, Any]] = []
    for item in items:
        if _item_id(item) not in survivor_ids:
            output.append(item)
            continue
        group_id = str(_futures_data(item).get("group_id"))
        output.append(bundle_by_group[group_id])

    return output


# ── Theme bundles (today's biggest swings — Phase 1, slice 6) ──────────────────
#
# Cap-and-FOLD the feed's biggest GUARDED 24h movers into ONE expandable
# ``type:bundle`` ``kind="theme"`` "Today's biggest swings" card, instead of
# scattering N high-movement cards. Folds items ALREADY in ``feed_items`` (the
# per-outcome ``probability_change_24h`` is in-feed at feed.py:1948-1962) — NO
# new DB pool. Discover-mode only, like slices 1/3.
#
# GUARD (Alex design round 2 — a naive biggest-mover is net-negative): exclude
# resolved/settled markets, exclude probability-extreme / settlement-jump end
# states (a leader sitting at ~100% is a settlement, not a live story), and
# require a sustained move above a threshold. Scoped to FUTURES items (where the
# swing stories live; ``_futures_data`` returns {} for non-futures, so events
# are naturally excluded and the ThemeBundleCard's futures members render
# cleanly). Gotcha #23: un-normalized candidate binaries that sum >100% can show
# a spurious near-100% leader — the extreme-prob guard excludes those too.

SWINGS_THEME_LABEL = "Today's biggest swings"
SWINGS_MIN_SWING = 0.15  # sustained 24h move ≥ 15pp to count as a "swing"
SWINGS_EXTREME = 0.95    # leader at/above this = near-settled/settlement-jump → exclude
_SWINGS_RESOLVED_STATUSES = {"resolved", "closed", "settled", "finalized"}


def _swing_magnitude(
    item: dict[str, Any], *, min_swing: float, extreme: float
) -> float | None:
    """Guarded swing magnitude (max |24h change|) for a FUTURES feed item, or
    None if it fails the guard (non-futures / resolved / extreme / no real move).
    """
    data = _futures_data(item)
    if not data:
        return None
    # GUARD: never surface a resolved/settled market as a "swing".
    if str(data.get("status") or "").strip().lower() in _SWINGS_RESOLVED_STATUSES:
        return None
    outcomes = data.get("top_outcomes")
    if not isinstance(outcomes, list) or not outcomes:
        return None
    probs = [
        float(o["probability"])
        for o in outcomes
        if isinstance(o, dict) and o.get("probability") is not None
    ]
    # GUARD: exclude probability-extreme / near-settled (settlement jump, not a
    # live story) — also catches un-normalized candidate-binary leaders (#23).
    if probs and max(probs) >= extreme:
        return None
    changes = [
        abs(float(o["probability_change_24h"]))
        for o in outcomes
        if isinstance(o, dict) and o.get("probability_change_24h") is not None
    ]
    if not changes:
        return None
    mag = max(changes)
    return mag if mag >= min_swing else None


def _make_swings_bundle_item(scored: list[tuple[float, dict[str, Any]]]) -> dict[str, Any]:
    # Members ranked by swing magnitude (biggest mover leads the mini-ranked-peek).
    ranked = [it for _, it in scored]
    score = max(float(it.get("score") or 0) for it in ranked)
    sort_time = max(float(it.get("_sort_time") or 0) for it in ranked)
    member_ids = [_futures_data(it).get("id") for it in ranked]
    names = [str(_futures_data(it).get("name") or "") for it in ranked]
    return {
        "type": "bundle",
        "score": score,
        # D1 clause c (#4066): this one already named a signal rather than
        # inventory — the members share "what moved most today", which IS the
        # question. Phrased as one.
        "reason": "What moved most today?",
        "headline": SWINGS_THEME_LABEL,
        "data": {
            "id": f"theme:swings:{'-'.join(str(m) for m in member_ids)}",
            "title": SWINGS_THEME_LABEL,
            "kind": "theme",
            "shared_question": "What moved most today?",
            "story_key": "swings",
            "item_count": len(ranked),
            "member_ids": member_ids,
            "items": [_public_member_item(it) for it in ranked],
            "debug_bundles": {
                "grouped_by": "swing_magnitude",
                "member_ids": member_ids,
                "member_names": names,
                "swings_pp": [round(mag * 100, 1) for mag, _ in scored],
            },
        },
        "_sort_time": sort_time,
    }


def assemble_swings_theme_bundles(
    items: list[dict[str, Any]],
    *,
    min_items: int = 2,
    max_items_per_bundle: int = 6,
    min_swing: float = SWINGS_MIN_SWING,
    extreme: float = SWINGS_EXTREME,
) -> list[dict[str, Any]]:
    """Fold the biggest GUARDED 24h movers into ONE "Today's biggest swings"
    bundle (Discover-mode only). Fewer than ``min_items`` qualifiers → untouched.
    """
    scored: list[tuple[float, dict[str, Any]]] = []
    for item in items:
        mag = _swing_magnitude(item, min_swing=min_swing, extreme=extreme)
        if mag is not None:
            scored.append((mag, item))
    if len(scored) < min_items:
        return items
    scored.sort(key=lambda x: x[0], reverse=True)
    chosen = scored[:max_items_per_bundle]
    chosen_ids = {_item_id(it) for _, it in chosen}
    bundle = _make_swings_bundle_item(chosen)

    output: list[dict[str, Any]] = []
    emitted = False
    for item in items:
        if _item_id(item) in chosen_ids:
            if not emitted:
                output.append(bundle)
                emitted = True
            continue
        output.append(item)
    return output
