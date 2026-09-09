"""Server-side composition for Discover comparison bundles."""

from __future__ import annotations

import logging
import re
from typing import Any

from app.utils.feed_market_quality import _story_key as compute_story_key

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


def _item_id(item: dict[str, Any]) -> str:
    data = item.get("data") if isinstance(item.get("data"), dict) else {}
    return f"{item.get('type')}:{data.get('id')}"


def _bundle_id(theme: str, items: list[dict[str, Any]]) -> str:
    ids = "-".join(str((_futures_data(item)).get("id")) for item in items)
    return f"comparison:{theme}:{ids}"


def _bundle_subtitle(theme: str, count: int) -> str:
    """The comparison bundle's shared question (D1 clause c, #4066).

    These four themes already knew what their members had in common — the old
    strings said it as a count and a basis ("4 IPO markets compared by valuation
    range"). Said as the question the members are answers to, the same fact
    tells a reader what they will learn by opening it. The count is not lost: it
    is the member list the card renders directly underneath.
    """
    if theme == "ipo_valuation":
        return "Which of these companies is priced highest to list?"
    if theme == "commodity_ranges":
        return "Where do these commodity prices land?"
    if theme == "rotten_tomatoes_scores":
        return "Which of these lands best with the critics?"
    if theme == "weather_distributions":
        return "How warm does it get in these cities?"
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


def _make_bundle_item(theme: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    score = max(float(item.get("score") or 0) for item in items)
    sort_time = max(float(item.get("_sort_time") or 0) for item in items)
    title = _THEME_TITLES.get(theme, "Comparable market ranges")
    member_ids = [(_futures_data(item)).get("id") for item in items]
    entities = [
        _market_entity_name(str((_futures_data(item)).get("name") or ""), theme)
        for item in items
    ]
    return {
        "type": "bundle",
        "score": score,
        "reason": _bundle_subtitle(theme, len(items)),
        "headline": title,
        "context_summary": _THEME_REASONS.get(theme),
        "data": {
            "id": _bundle_id(theme, items),
            "title": title,
            "kind": "comparison",
            "shared_question": _bundle_subtitle(theme, len(items)),
            "comparison_theme": theme,
            "item_count": len(items),
            "member_ids": member_ids,
            "items": [_public_member_item(item) for item in items],
            "entities": entities,
            "debug_bundles": {
                "grouped_by": "discover_card.comparison_theme",
                "theme": theme,
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
    """

    groups: dict[str, list[dict[str, Any]]] = {}
    seen_entities: dict[str, set[str]] = {}
    for item in items:
        theme = _theme_for_item(item)
        if theme is None:
            continue
        name = str(_futures_data(item).get("name") or "")
        entity = _market_entity_name(name, theme).lower()
        if not entity:
            continue
        seen_entities.setdefault(theme, set())
        if entity in seen_entities[theme]:
            continue
        seen_entities[theme].add(entity)
        groups.setdefault(theme, []).append(item)

    bundle_items_by_theme: dict[str, list[dict[str, Any]]] = {}
    represented_ids: set[str] = set()
    for theme, candidates in groups.items():
        if len(candidates) < min_items:
            continue
        top_candidates = candidates[:max_items_per_bundle]
        if len(top_candidates) < min_items:
            continue
        bundles = [_make_bundle_item(theme, top_candidates)]
        bundle_items_by_theme[theme] = bundles[:max_bundles_per_theme]
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


def _make_theme_bundle_item(
    story_key: str, items: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """The folded bundle, or None when the family shares no statable question.

    Returns None rather than folding on "N related markets" (D1 clause c):
    a group that cannot say what its members have in common is not a story, and
    its members are better off competing for their own slots — which is exactly
    where they were before this bundler ran.
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
    if not question:
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
    """
    from app.utils.cross_source_matching import is_same_question

    kept: list[dict[str, Any]] = []
    folded: list[dict[str, Any]] = []
    for item in members:
        data = _futures_data(item)
        name = str(data.get("name") or "")
        source = str(data.get("source") or "")
        duplicate = any(
            str(_futures_data(k).get("source") or "") != source
            and is_same_question(str(_futures_data(k).get("name") or ""), name)
            for k in kept
        )
        (folded if duplicate else kept).append(item)
    return kept, folded


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


def _make_awards_bundle_item(
    group_id: str, members: list[dict[str, Any]]
) -> dict[str, Any]:
    ranked = sorted(members, key=lambda it: float(it.get("score") or 0), reverse=True)
    score = max(float(item.get("score") or 0) for item in ranked)
    sort_time = max(float(item.get("_sort_time") or 0) for item in ranked)
    member_ids = [_futures_data(item).get("id") for item in ranked]
    names = [str(_futures_data(item).get("name") or "") for item in ranked]
    label = _derive_race_label(names)
    # D1 clause c (#4066): an awards cluster's shared question is the race its
    # members literally share, which `_derive_race_label` already extracted —
    # "Best Actor at the 99th Academy Awards" becomes "Who wins Best Actor at
    # the 99th Academy Awards?". Nothing else here changes.
    question = f"Who wins {label}?"
    return {
        "type": "bundle",
        "score": score,
        "reason": question,
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
