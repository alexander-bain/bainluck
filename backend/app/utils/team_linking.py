"""
Futures outcome → Team linking utility.

Matches FuturesOutcome names to Team records using the canonical name
normalization from name_normalization.py.

Uses a conservative matching strategy (exact + suffix containment only,
no token overlap) because outcomes iterate through ALL teams and must
distinguish same-city teams like Lakers vs Clippers.
"""

import logging
import re
from typing import Optional

from app.utils.name_normalization import normalize_name as _normalize_name  # noqa: F401 — re-exported

# Re-export for backward compatibility — canonical location is market_label_normalization
from app.utils.market_label_normalization import compute_market_tier  # noqa: F401

logger = logging.getLogger(__name__)


# =============================================================================
# Name matching for futures outcomes
# =============================================================================


def _names_match(candidate: str, team_name: str, alt_names: Optional[list] = None) -> bool:
    """Check if a candidate string (futures outcome name) matches a team.

    Uses conservative matching (exact + substring ≥8 chars) because futures
    outcomes iterate through ALL teams and need to distinguish same-city teams
    (e.g., "Los Angeles Clippers" must NOT match "LA Lakers").

    For 1:1 event matching (where both teams are known), use the more
    aggressive names_match() from name_normalization.py instead.
    """
    candidate_norm = _normalize_name(candidate)
    if not candidate_norm:
        return False

    all_names = [team_name] + (alt_names or [])

    for name in all_names:
        name_norm = _normalize_name(name)
        if not name_norm:
            continue

        # Exact match
        if candidate_norm == name_norm:
            return True

        # Substring match (only if both strings are long enough to avoid
        # false positives like "LA" matching everything)
        if len(candidate_norm) >= 8 and len(name_norm) >= 8:
            if candidate_norm in name_norm:
                return True
            if name_norm in candidate_norm and not city_alias_names_someone_else(
                candidate, name, team_name
            ):
                return True

    return False


# One given name as a market prints it: "Parker", "A'Mauri", "Ja'Marr", "P.J.".
# An all-caps token ("UNC", "PIT") is an abbreviation, never a given name.
_GIVEN_NAME = re.compile(
    r"^(?:[A-Z][a-z]+(?:['-][A-Z]?[a-z]+)*|[A-Z]'[A-Z][a-z]+|(?:[A-Z]\.){1,3})$"
)
_NAME_SUFFIXES = frozenset({"jr", "jr.", "sr", "sr.", "ii", "iii", "iv"})


def given_name_before_city(candidate: str, alias: str, team_name: str) -> bool:
    """True when ``candidate`` is one given name and then the team's city alias (#9726).

    The Washington Huskies carry the alias "Washington", and "washington" is a
    substring of "parker washington", so the substring arm bound Parker, Darnell
    and Mike Washington Jr.'s NFL props to a college team page (and Matt
    Campbell to Campbell, Denzel Washington to the Wizards, "Georgia Southern"
    to Southern University). A city alias names the club only when it leads the
    outcome; one capitalised word in front of it makes it someone's surname, or
    another school ("Western Michigan").

    Only a CITY alias qualifies, i.e. a proper prefix of the team's name
    ("Washington" of "Washington Huskies"). A nickname alias ("Steelers" in "PIT
    Steelers D/ST") and a name that is all alias ("Athletics") are untouched.
    """
    alias_norm = _normalize_name(alias)
    if not alias_norm or not _normalize_name(team_name).startswith(alias_norm + " "):
        return False
    tokens = candidate.split()
    while tokens and tokens[-1].lower() in _NAME_SUFFIXES:
        tokens.pop()
    if len(tokens) < 2 or not _GIVEN_NAME.match(tokens[0]):
        return False
    return _normalize_name(" ".join(tokens[1:])) == alias_norm


# Fantasy-defense labels as venues print them: "Washington D/ST", "Minnesota D/ST: 1+".
_FANTASY_DEFENSE = frozenset({"d/st", "dst"})


def fantasy_defense_on_city(candidate: str, alias: str, team_name: str) -> bool:
    """True when ``candidate`` is the team's city alias and then "D/ST" (#9726).

    A D/ST is an NFL fantasy defense. "Washington D/ST" (the Commanders') bound to
    the Washington Huskies through the alias "Washington", and Cincinnati,
    Minnesota and Tennessee D/ST to the Bearcats, Golden Gophers and Volunteers.
    Venues name the NFL club's defense by nickname too ("WAS Commanders D/ST",
    "Steelers D/ST"), which this leaves alone; only a CITY alias qualifies, as in
    ``given_name_before_city``. Anything after a colon ("D/ST: 1+") is a line on
    the same defense.
    """
    alias_norm = _normalize_name(alias)
    if not alias_norm or not _normalize_name(team_name).startswith(alias_norm + " "):
        return False
    tokens = candidate.split(":", 1)[0].split()
    if len(tokens) < 2 or tokens[-1].lower() not in _FANTASY_DEFENSE:
        return False
    return _normalize_name(" ".join(tokens[:-1])) == alias_norm


def city_alias_names_someone_else(candidate: str, alias: str, team_name: str) -> bool:
    """True when the team's city alias sits in ``candidate`` as another thing's name (#9726):
    a person's surname ("Parker Washington") or an NFL fantasy defense ("Washington D/ST").
    """
    return given_name_before_city(candidate, alias, team_name) or fantasy_defense_on_city(
        candidate, alias, team_name
    )


def _normalized_names(team: dict) -> list[str]:
    """Every non-empty normalized name/alias a team answers to."""
    all_names = [team["name"]] + (team.get("alternate_names") or [])

    return [n for n in (_normalize_name(name) for name in all_names) if n]


def match_outcome_to_team(
    outcome_name: str,
    teams: list[dict],
) -> Optional[int]:
    """
    Match a futures outcome name to a team record.

    Args:
        outcome_name: The outcome name (e.g., "Boston Celtics", "Los Angeles Lakers")
        teams: List of team dicts with keys: id, name, alternate_names

    Returns:
        team_id if matched, None otherwise
    """
    if not outcome_name or outcome_name.lower() in ("yes", "no", "over", "under"):
        return None

    candidate_norm = _normalize_name(outcome_name)

    matched = []
    exact_team_ids = []
    for team in teams:
        if not _names_match(outcome_name, team["name"], team.get("alternate_names")):
            continue

        names_norm = _normalized_names(team)
        matched.append((team["id"], names_norm))
        if candidate_norm and candidate_norm in names_norm:
            exact_team_ids.append(team["id"])

    # An exact hit beats another row's substring hit. Production teams carry a
    # city-only alias ("New York" sits on both the Yankees and the Mets), and the
    # substring arm of _names_match fires that alias against every other club in
    # the same city — so without this "New York Yankees" read as ambiguous and
    # bound to nothing (#7188).
    #
    # The exception is a candidate that is itself a shortening of another matched
    # club's name: a bare "Los Angeles" is an exact alias of the Lakers and the
    # Clippers do not carry it, but it still names either club, so it must stay
    # ambiguous. Two exact hits (the preseason twin shares the name) and a
    # truncated fragment like "New York M" (no exact hit at all) also fall
    # through to the single-match rule below.
    if len(exact_team_ids) == 1:
        winner = exact_team_ids[0]
        shortens_a_sibling = any(
            team_id != winner and any(candidate_norm in n for n in names_norm)
            for team_id, names_norm in matched
        )
        if not shortens_a_sibling:
            return winner

    if len(matched) == 1:
        return matched[0][0]

    return None


def match_outcome_to_league_team(
    outcome_name: str,
    league_teams: list[dict],
) -> Optional[int]:
    """Bind an outcome to a team when the market's LEAGUE is already known (#9617).

    Kalshi names teams by city alone ("New York", "Minnesota", "Golden State").
    ``match_outcome_to_team`` is run over a whole sport category — basketball is
    NBA + WNBA + men's and women's college — so "New York" hits the Knicks AND
    the Liberty, reads ambiguous, and binds to nothing. Measured 2026-09-29: the
    open KXNBA champion market had 7 of 30 outcomes linked, KXWNBA 2 of 15. The
    ticker already says which league it is; inside that one league the city is
    usually unique.

    Two arms, both requiring exactly ONE team in ``league_teams``:

    * exact: the outcome equals one team's name or alias;
    * city: the outcome equals one team's own NAME minus its nickname (the last
      one or two words) — "Atlanta" for "Atlanta Falcons", "Portland" for
      "Portland Trail Blazers". Aliases are not shortened: "Penn State" is an
      alias, and dropping its last word would make "Penn" name Penn State.

    Either arm is refused when the outcome is a shortening of ANOTHER team's name
    in the league (a bare "Los Angeles" still names the Clippers). The substring
    arm of ``_names_match`` is deliberately not used here: scoped to one college
    league it would bind "Western Kentucky" to Kentucky.
    """
    candidate = _normalize_name(outcome_name)
    if not candidate:
        return None

    names_by_team = {team["id"]: _normalized_names(team) for team in league_teams}

    def _unique_unshadowed(hits: set) -> Optional[int]:
        if len(hits) != 1:
            return None
        winner = next(iter(hits))
        shortens_a_sibling = any(
            team_id != winner and any(candidate in n for n in names)
            for team_id, names in names_by_team.items()
        )
        return None if shortens_a_sibling else winner

    exact = {team_id for team_id, names in names_by_team.items() if candidate in names}
    if exact:
        winner = _unique_unshadowed(exact)
        if winner is None and len(exact) > 1:
            winner = _own_name_over_aliases(outcome_name, league_teams)
    else:
        city = set()
        for team in league_teams:
            words = (_normalize_name(team["name"]) or "").split()
            if any(len(words) > k and " ".join(words[:-k]) == candidate for k in (1, 2)):
                city.add(team["id"])
        winner = _unique_unshadowed(city)
    if winner is not None:
        return winner
    winner = _match_league_team_by_city_initials(outcome_name, league_teams)
    if winner is not None:
        return winner
    return _match_league_team_by_spelling(outcome_name, league_teams)


def _own_name_over_aliases(outcome_name: str, league_teams: list[dict]) -> Optional[int]:
    """The club whose own NAME is the outcome, when other rows only alias it (#9802).

    Five NHL clubs have a second, city-only row that lists the full name as an
    alias (115 "Toronto Maple Leafs" and 12715 "Toronto" → ["Toronto Maple Leafs"]),
    so the exact arm hit two rows and Kalshi's Stanley Cup, conference and playoff
    legs for them never linked. The row named for the club wins over a row that
    merely lists it; so does an alias that is another school's name (#8353's
    Akron row listing "Michigan Wolverines").

    Names are compared by the twin fold's key — the one the team page uses to
    join a club's rows (#7929) — so "St Louis Blues" 3705 is one club with 571
    and the page reaches whichever row is bound; the lowest id is taken. Refused
    when the outcome is a shortening of any other team's NAME.
    """
    from app.utils.event_twin_fold import team_name_fold_key

    key = team_name_fold_key(outcome_name or "")
    if not key:
        return None
    own = {t["id"] for t in league_teams if team_name_fold_key(t["name"] or "") == key}
    if not own:
        return None
    if any(
        t["id"] not in own and key in team_name_fold_key(t["name"] or "")
        for t in league_teams
    ):
        return None
    return min(own)


def _match_league_team_by_city_initials(outcome_name: str, league_teams: list[dict]) -> Optional[int]:
    """A two-club city written with the nickname's initials: "Los Angeles L" (#9617).

    Kalshi's boards tell a shared city's clubs apart by one or two capitals:
    "Los Angeles L" / "Los Angeles C" on KXNBA-27, "Chicago WS" on KXMLB-26,
    "New York G" / "New York J" on KXSB-27. The strict arms cannot read that:
    ``normalize_name`` strips a trailing " C" ("Los Angeles C" → "los angeles",
    which names both LA clubs) and keeps " L" ("los angeles l" names nothing),
    so the Lakers and the Clippers carried no Kalshi title odds at all.

    The RAW last token must be one or two capitals; the rest must equal a team's
    own name minus a one- or two-word nickname, and the capitals that nickname's
    initials. Exactly one team, as in every arm. A team row whose own nickname is
    a single capital is skipped: those are the #6974 fragment rows
    ("Los Angeles C" beside the real Clippers), never the club a page shows.
    """
    tokens = (outcome_name or "").split()
    if len(tokens) < 2:
        return None
    # Compared with a one- or two-word nickname's upper-case initials, so only
    # one or two capitals can ever match ("Los Angeles l", "USC", "A&M" cannot).
    initials = tokens[-1]
    city = _normalize_name(" ".join(tokens[:-1]))
    if not city:
        return None

    hits = set()
    for team in league_teams:
        words = (team.get("name") or "").split()
        if not words or (len(words[-1]) == 1 and words[-1].isupper()):
            continue
        for k in (1, 2):
            if (
                len(words) > k
                and "".join(w[0] for w in words[-k:]).upper() == initials
                and _normalize_name(" ".join(words[:-k])) == city
            ):
                hits.add(team["id"])
    return next(iter(hits)) if len(hits) == 1 else None


# Venue names for a school that no spelling rule reaches (#9663), keyed on
# `normalize_name` of the venue's outcome name. Each is the school our row names:
# Houston Christian was Houston Baptist until 2022; Kalshi keeps the "St." on
# Central Connecticut, whose row carries no "State".
_VENUE_SCHOOL_NAMES: dict[str, str] = {
    "tennessee-martin": "ut martin",
    "houston christian": "houston baptist",
    "university at albany": "albany",
    "central connecticut st.": "central connecticut",
    # Kalshi writes the Hurricanes "Miami (FL)"; the row is "Miami Hurricanes".
    # The RedHawks keep "(OH)" in their own name, so only Florida needs this —
    # the entry #8980 made for game matching, here for the team page (#9920).
    "miami (fl)": "miami hurricanes",
}


def _spelling_key(name: str) -> str:
    """One spelling of a college name: "St." is "State", "&" is "and", a hyphen a space."""
    from app.utils.name_normalization import normalize_team_name_for_matching

    key = normalize_team_name_for_matching(name.replace("&", " and ").replace("-", " "))
    return " ".join(key.split())


def _match_league_team_by_spelling(outcome_name: str, league_teams: list[dict]) -> Optional[int]:
    """The strict arms' fallback: the same school written the way a college feed writes it (#9663).

    Kalshi's FCS title board names "Montana St.", "South Carolina St.", "William &
    Mary", "Arkansas-Pine Bluff"; our rows say "Montana State Bobcats" (alias
    "Montana St"), "South Carolina State Bulldogs", "William and Mary Tribe". Both
    sides are compared through :func:`_spelling_key`, with the same two arms and
    the same one-team rule as :func:`match_outcome_to_league_team`. Reached only
    when those arms answer nothing, so no answer they give changes.

    Two differences, both about "State" being its own school:

    * a sibling whose name continues the candidate with "State" does not shadow
      it — "Montana" is the Grizzlies although "Montana State" starts with it;
    * a city form never drops a "State": "Idaho State Bengals" does not read as
      "Idaho".

    Any other continuation still shadows ("Miami" beside "Miami (OH)"), and a
    sibling that merely contains the candidate no longer does ("Tennessee St."
    beside "East Tennessee State").
    """
    raw = _normalize_name(outcome_name)
    if not raw:
        return None
    candidate = _spelling_key(_VENUE_SCHOOL_NAMES.get(raw, raw))
    if not candidate:
        return None

    keys_by_team = {
        team["id"]: [
            k for k in (_spelling_key(n) for n in [team["name"]] + (team.get("alternate_names") or []))
            if k
        ]
        for team in league_teams
    }

    def _unique_unshadowed(hits: set) -> Optional[int]:
        if len(hits) != 1:
            return None
        winner = next(iter(hits))
        prefix = candidate + " "
        for team_id, keys in keys_by_team.items():
            if team_id == winner:
                continue
            for k in keys:
                if k.startswith(prefix) and k[len(prefix):].split()[0] != "state":
                    return None
        return winner

    exact = {team_id for team_id, keys in keys_by_team.items() if candidate in keys}
    if exact:
        return _unique_unshadowed(exact)

    city = set()
    for team in league_teams:
        words = _spelling_key(team["name"]).split()
        for k in (1, 2):
            if len(words) > k and words[-k] != "state" and " ".join(words[:-k]) == candidate:
                city.add(team["id"])
    return _unique_unshadowed(city)


from app.utils.name_normalization import strip_diacritics as _strip_diacritics


def match_outcome_to_roster(
    outcome_name: str,
    team_rosters: dict[int, list[str]],
) -> Optional[int]:
    """
    Match a futures outcome name to a team via roster player names.

    Args:
        outcome_name: e.g., "Jaylen Brown" or "Aaron Judge Over 2.5 Hits"
        team_rosters: {team_id: ["Jayson Tatum", "Jaylen Brown", ...]}

    Returns:
        team_id if matched, None otherwise
    """
    if not outcome_name or len(outcome_name) < 4:
        return None

    # Skip generic outcomes
    name_lower = _strip_diacritics(outcome_name.lower().strip())
    if name_lower in ("yes", "no", "over", "under", "draw", "tie"):
        return None

    matched: list[int] = []
    for team_id, players in team_rosters.items():
        for player in players:
            player_lower = _strip_diacritics(player.lower())
            # Require the full player name (first + last) to appear in the outcome.
            # Do NOT match if only a first or last name matches — too many collisions
            # (e.g., "Austin Eckroat" should not match "Austin FC").
            # Only match if the player name has 2+ words (skip single-word names
            # to avoid "Santos" matching random things).
            if " " not in player_lower:
                continue
            if player_lower in name_lower:
                matched.append(team_id)
                break

    if not matched:
        return None
    # #8072: two clubs can carry the same name — the Dodgers' and the Athletics'
    # Max Muncy, the Rams' and the Eagles' Byron Young. Whichever roster came
    # first won, so "NL MVP Winner? — Max Muncy" was linked to the Athletics.
    # A name on two DIFFERENT clubs' rosters is no answer. Two rows for one club
    # carry the same roster, so they still resolve to the first, as before.
    first = _roster_key_set(team_rosters[matched[0]])
    for other in matched[1:]:
        if not _same_club_roster(first, _roster_key_set(team_rosters[other])):
            return None
    return matched[0]


def _roster_key_set(players: list[str]) -> set[str]:
    return {_strip_diacritics(p.lower()) for p in players}


def _same_club_roster(a: set[str], b: set[str]) -> bool:
    """Two team rows are one club's when they share more than half the smaller roster.

    A namesake shares one player; two rows for one club share (nearly) all of them.
    One shared player is never enough, however short the rosters.
    """
    shared = len(a & b)
    return shared >= 2 and shared * 2 > min(len(a), len(b))


# =============================================================================
# Sport category → sport key mapping (for scoping team search)
# =============================================================================

from app.utils.sport_keys import (  # noqa: E402
    LLM_CATEGORY_TO_SPORT_KEYS as SPORT_CATEGORY_TO_KEYS,  # noqa: F401 — re-exported
    get_sport_keys_for_category,  # noqa: F401 — re-exported
)


# =============================================================================
# Relevance scoring for related futures
# =============================================================================

# Tier score: lower tier = more relevant (championship is most important context)
_TIER_SCORES = {1: 1.0, 2: 0.7, 3: 0.5, 4: 0.3, 5: 0.1}

# Round-number thresholds that create narrative moments
_THRESHOLD_BOUNDARIES = [0.10, 0.20, 0.25, 0.33, 0.50, 0.67, 0.75, 0.80, 0.90]


def compute_relevance_score(
    market_tier: Optional[int],
    probability: Optional[float],
    probability_change_24h: Optional[float],
    days_to_resolution: Optional[float],
    bookmaker_count: int = 1,
) -> tuple[float, str]:
    """
    Compute a relevance score (0-100) for a related future.

    Returns (score, reason) where reason is a human-readable label
    explaining why this future is relevant.

    Weights:
        - tier_score:      25% — championship > conference > awards > division > props
        - movement_score:  30% — is this future reacting to current events?
        - probability_score: 15% — does the team/player have a real shot?
        - threshold_score: 15% — is the outcome near a significant boundary?
        - urgency_score:   10% — how soon does this resolve?
        - liquidity_score:  5% — how many sources contribute odds?
    """
    # Tier score (0-1)
    tier = market_tier or 5
    tier_s = _TIER_SCORES.get(tier, 0.1)

    # Movement score (0-1): absolute 24h change, capped at 5%
    change = abs(float(probability_change_24h or 0))
    movement_s = min(change / 0.05, 1.0)

    # Probability score (0-1): higher probability = more interesting
    # But very low probs (< 1%) are noise, and near-certainties (> 95%) are boring
    prob = float(probability or 0)
    if prob < 0.01:
        prob_s = 0.0
    elif prob > 0.95:
        prob_s = 0.3  # Still somewhat interesting but not exciting
    else:
        # Peak relevance around 0.3-0.5 range
        prob_s = min(prob / 0.3, 1.0) if prob <= 0.3 else 1.0

    # Threshold proximity score (0-1): near a round-number boundary
    threshold_s = 0.0
    if prob > 0:
        min_distance = min(abs(prob - b) for b in _THRESHOLD_BOUNDARIES)
        # Full score if within 2%, zero if > 5% away
        if min_distance < 0.05:
            threshold_s = 1.0 - (min_distance / 0.05)

    # Urgency score (0-1): resolves sooner = more relevant
    if days_to_resolution is not None and days_to_resolution > 0:
        urgency_s = max(0, 1.0 - (days_to_resolution / 180))  # 6 months = 0
    else:
        urgency_s = 0.3  # Unknown resolution = moderate

    # Liquidity score (0-1): more bookmakers = more reliable
    liquidity_s = min(bookmaker_count / 8, 1.0)

    # Weighted sum
    score = (
        0.25 * tier_s
        + 0.30 * movement_s
        + 0.15 * prob_s
        + 0.15 * threshold_s
        + 0.10 * urgency_s
        + 0.05 * liquidity_s
    ) * 100

    # Determine reason label
    reason = _determine_reason(tier, change, prob, threshold_s, days_to_resolution)

    return round(score, 1), reason


def _determine_reason(
    tier: int,
    change: float,
    prob: float,
    threshold_score: float,
    days_to_resolution: Optional[float],
) -> str:
    """Pick the most relevant reason label for why this future matters."""
    # Moving futures are the most interesting
    if change >= 0.02:
        return "moving today"
    if change >= 0.005:
        return "shifting"

    # Near a threshold boundary
    if threshold_score > 0.6 and prob > 0.05:
        if prob > 0.45 and prob < 0.55:
            return "near 50/50"
        return "near threshold"

    # Resolving soon
    if days_to_resolution is not None and days_to_resolution < 14:
        return "resolves soon"

    # Fall back to tier-based label
    tier_labels = {
        1: "championship context",
        2: "conference context",
        3: "award watch",
        4: "division context",
        5: "related market",
    }
    return tier_labels.get(tier, "related market")
