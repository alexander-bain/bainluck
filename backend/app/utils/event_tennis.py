"""Tennis adapter for the Event Concept framework — slice 2 (#999).

Unlike golf (which delegates to a bespoke aggregation), tennis has no existing
per-event page, so this adapter builds the generic envelope from scratch:
- winner-field: the tournament-winner market ("… Winner"/"Champion", many player
  outcomes) → primary block competitors.
- matchups: individual "X vs Y" match markets sharing the tournament → children.
- props: other same-tournament markets → children.

Data reality (verified live 2026-07-08): tournament-winner fields come from
Polymarket (e.g. "2026 Women's Wimbledon Winner", 52 outcomes, cat=tennis); Kalshi
tennis is per-match (kxatpmatch…). Association is by tournament-name token, since
cross-source event grouping (design §7 `group_type="event"`) is a later slice.

Pure helpers are unit-tested; the adapter's build_event is exercised via the route
test with a seeded winner market.
"""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.utils.settledness import (
    market_assigned_settled,
    price_converged,
    settled_under_assigned_state,
)

# L2-81: how long a concluded tournament's resolved winner market stays queryable
# so the event page survives the tournament ending (renders the settled state)
# instead of 404-ing the moment Polymarket flips the market to resolved/closed.
_RESOLVED_WINDOW_DAYS = 30

# L2-83: raw price at/above which a SETTLED winner-field outcome is the crowned
# champion during the is_winner grading-lag window. Matches the child "decided"
# threshold below (0.97) — a settled winner-market outcome priced this high is the
# resolved winner. Display-only; never authoritative (gotcha #21).
_WON_PRICE_THRESHOLD = 0.97

#: ATP/WTA TOUR TIERS. A tier says how many ranking points a tournament awards —
#: it is a PROPERTY of a tournament, never its identity, and no two tournaments
#: in one city differ only by tier. One source names its markets "ATP 1000
#: Montreal: Winner" while the other names the same tournament "ATP Montreal
#: Winner", and because `list_tennis_tournament_concepts` keys its groups on the
#: EXACT token set while `select_winner_field` matches by SUBSET, the two layers
#: disagreed: the rail printed both renderings as two separate tournaments, and
#: both cards opened the SAME event page. Measured in production 2026-08-29 —
#: `/hub/tennis` served 12 upcoming cards for 10 tournaments (ATP Montreal and
#: WTA Toronto each listed twice), and all four keys resolved to just two events.
#:
#: The set is CLOSED and externally defined (the tours publish it), so it is
#: vocabulary rather than a tuned threshold — the same shape as `_SLAM_PATTERNS`.
#: ⚠️ Only `1000` occurs in the corpus: a census of all 1,677 open tennis markets
#: on 2026-08-29 found it exactly TWICE, both of them the duplicate pair above,
#: and found no `125`/`250`/`500` at all. RE-MEASURED 2026-08-30 over 1,591 open
#: tennis markets (`truncated: false`) — unchanged: `1000` ×2 (ids 57718610 "ATP
#: 1000 Montreal: Winner" and 58076256 "WTA 1000 Toronto: Winner", both
#: `resolution_date = NULL`), `125`/`250`/`500` ×0. Those three are therefore a
#: strict no-op on the measured corpus and are listed because the naming
#: convention that produced "ATP 1000" produces "ATP 250" the week a 250-level
#: event is served. Numeric tokens ARE common elsewhere in the corpus (`2` ×199,
#: `1` ×119, `3` ×93, `16` ×87) but they live in match and prop titles, which
#: `is_winner_field` excludes before either caller sees them.
_TOUR_TIER_TOKENS = {"125", "250", "500", "1000"}

# Tokens stripped when deriving the tournament name from a market title.
_TENNIS_STOPWORDS = {
    "winner", "champion", "champ", "tennis", "atp", "wta", "mens", "men", "s",
    "womens", "women", "singles", "doubles", "the", "2024", "2025", "2026",
    "2027", "2028", "final", "title",
} | _TOUR_TIER_TOKENS

# A tournament's winner FIELD must have at least this many real competitors.
# Two is the definition of a field, not a tuned number: one outcome is a yes/no
# prop about a single named person. Measured production corpus 2026-08-12 —
# legitimate fields 4..89, novelty props exactly 1. See `is_winner_field`.
_MIN_FIELD_OUTCOMES = 2

_MATCHUP_RE = re.compile(r"\b(vs\.?|v\.?|def\.?|beats?)\b", re.IGNORECASE)
_WINNER_RE = re.compile(r"\b(winner|champion|champ|to win)\b", re.IGNORECASE)


# ── UX-P180 (#2167): tennis prop classification for the hub ──
#
# `_assign_section` routes EVERY `game_prop` in an individual sport to "matches",
# and `_PROP_CLASSIFIERS` (routes/hub.py) was registered for ufc and boxing only
# — so tennis had no way back out. Measured on production 2026-09-05, that put 55
# season-long ranking props ("Will X Make the Top 10 in the 2026 ATP end of year
# rankings") under a heading reading "MATCHES · 56".
#
# Matched as PHRASES anywhere in the name, never by splitting on the first colon:
# tennis market names carry a tournament PREFIX ("US Open ATP: A vs B") as often
# as a prop SUFFIX ("A vs. B: Total Sets O/U 3.5"), so a positional parse assigns
# the wrong half. A plain moneyline matches none of these and stays a match.
_TENNIS_PROP_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bexact\s+(match\s+)?score\b", re.IGNORECASE), "exact score"),
    (re.compile(r"\btotal\s+sets\b", re.IGNORECASE), "total sets"),
    (re.compile(r"\bset\s+\d+\s+games\b", re.IGNORECASE), "set games"),
    (re.compile(r"\b(match|total)\s+games?\b", re.IGNORECASE), "total games"),
    (re.compile(r"\bmatch\s+o/u\b", re.IGNORECASE), "total games"),
    # Prefix-shaped props: "Game Spread: Alcaraz (-6.5) vs Paul (+6.5)". These are
    # why the patterns are matched anywhere in the name rather than after a colon
    # — here the prop phrase leads and the players follow, the exact inverse of
    # "A vs. B: Total Sets O/U 3.5".
    (re.compile(r"\bhandicap\b", re.IGNORECASE), "handicap"),
    (re.compile(r"\bspread\b", re.IGNORECASE), "spread"),
    (re.compile(r"\btie\s?break\b", re.IGNORECASE), "tiebreak"),
    (re.compile(r"\bstraight\s+sets\b", re.IGNORECASE), "straight sets"),
    (re.compile(r"\bend[- ]of[- ]year\s+rankings?\b", re.IGNORECASE), "ranking"),
    (re.compile(r"\bmake\s+the\s+top\s+\d+\b", re.IGNORECASE), "ranking"),
    (re.compile(r"\bqualify\s+for\b", re.IGNORECASE), "qualification"),
    (re.compile(r"\bo/u\b", re.IGNORECASE), "over/under"),
)


def classify_tennis_prop(external_id: str | None, name: str | None) -> str | None:
    """Classify a tennis market as a prop kind, or None if it is a real match.

    Signature matches `classify_ufc_prop` / `classify_boxing_prop` so the hub's
    `_PROP_CLASSIFIERS` table stays one uniform shape. `external_id` is accepted
    for that contract and deliberately unused: tennis prop tickers are not a
    stable family the way `KXUFCMOV` is, and guessing at one would misfile real
    matches — the names carry the signal.
    """
    n = name or ""
    for pattern, prop_type in _TENNIS_PROP_PATTERNS:
        if pattern.search(n):
            return prop_type
    return None


def is_winner_market(name: str | None) -> bool:
    """True for a tournament-winner field (the parent), not a single match."""
    n = name or ""
    return bool(_WINNER_RE.search(n)) and not _MATCHUP_RE.search(n)


def is_matchup_market(name: str | None) -> bool:
    """True for an individual match market ('Player A vs Player B')."""
    return bool(_MATCHUP_RE.search(name or ""))


def tournament_tokens(name: str | None) -> set[str]:
    """Significant tournament-name tokens from a market title.

    "2026 Women's Wimbledon Winner" -> {"wimbledon"};
    "ATP S-Hertogenbosch Winner" -> {"hertogenbosch"} (len>=4 kept).
    Used to associate CHILD markets to the event.

    ⚠️ This is the CHILD-ASSOCIATION function (`shares_tournament`, and the
    entrant/token fallback in `build_event`). Do NOT widen it to fix a canonical
    resolution bug — that changes which props fold into every tennis event, a
    blast radius no resolution fix needs. Canonical resolution uses
    `canonical_tokens` below. (UX-P066 / #1793.)"""
    raw = re.sub(r"[^a-z0-9\s]", " ", (name or "").lower())
    toks = {t for t in raw.split() if len(t) >= 4 and t not in _TENNIS_STOPWORDS}
    return toks


def canonical_tokens(name: str | None) -> set[str]:
    """Tokens that IDENTIFY a tournament, for canonical slug resolution.

    Identical to `tournament_tokens` except it does NOT drop short tokens, and
    that difference is the entire point of this function.

    #1793: `tournament_tokens("US Open Men's Singles Winner")` is `{"open"}` —
    `us` is two characters so the `len >= 4` filter deletes it, `mens`/`singles`/
    `winner` are stopwords. The identity of the US Open was therefore NOT
    REPRESENTABLE: it reduced to the same single token as Cincinnati Open,
    French Open and Australian Open. Since matching is a subset test
    (`slug_tokens <= market_tokens`), a slug with FEWER tokens matches MORE
    tournaments — so degrading the slug WIDENED the blast radius instead of
    narrowing it, and `event:tennis:us-open-2026` served "Cincinnati Open"
    (measured in production 2026-08-12; Cincinnati's 78-player draw simply
    outranked the US Open's own 41).

    A length filter is a reasonable way to drop noise from a display name. It is
    not a safe way to derive an identity, because short words are exactly where
    short names live."""
    raw = re.sub(r"[^a-z0-9\s]", " ", (name or "").lower())
    return {t for t in raw.split() if t not in _TENNIS_STOPWORDS}


def canonical_slug_tokens(slug: str | None) -> set[str]:
    """`canonical_tokens` for a URL slug (hyphen-separated, already lowercase)."""
    return {t for t in (slug or "").split("-") if t and t not in _TENNIS_STOPWORDS}


def is_winner_field(name: str | None, real_outcome_count: int) -> bool:
    """True when a market can be a tournament's PRIMARY winner field.

    `is_winner_market` only asks whether the NAME sounds like a win, and its
    `to win` arm makes any prop about a named person eligible. That is how
    `event:tennis:wimbledon-2026` came to serve "Serena and Venus Williams to
    win Wimbledon Doubles this year", and how `/hub/tennis` came to link
    "Serena Williams to Win a Tournament in 2026" as though it were a
    tournament (both measured in production 2026-08-12).

    A FIELD needs a field: at least two competitors who could win it. This is a
    definition, not a tuned threshold — a one-outcome market is a yes/no prop
    about one named person, which is categorically not a tournament draw.
    Measured against the full production corpus the same day: every one of the
    26 legitimate tournament fields had **4 to 89** outcomes, and both novelty
    props had exactly **1**. (UX-P066 / #1793.)"""
    return is_winner_market(name) and real_outcome_count >= _MIN_FIELD_OUTCOMES


def shares_tournament(name: str | None, tokens: set[str]) -> bool:
    if not tokens:
        return False
    return bool(tournament_tokens(name) & tokens)


def select_winner_field(markets, slug: str, real_outcome_count):
    """Pick the market that IS the tournament named by `slug`, or None.

    Canonical resolution (L2-65 Item 2): collect every winner FIELD whose slug
    matches (exact `clean_slug` OR identity-token subset), then take the RICHEST.
    A bare or differently-named-per-source slug ("toronto", "wta-toronto-winner")
    therefore lands on the fullest field for THAT tournament — e.g. the Polymarket
    51-player draw rather than a sparse Kalshi one — so shared links converge. A
    gendered slug never crosses genders (the gender words are stopwords, so it is
    guarded explicitly).

    Extracted from `build_event` by UX-P066 so the identity rule can be driven
    directly, without a database, against a real production corpus. `markets` is
    any iterable of objects carrying `.name`, `.id` and `.volume_24h`;
    `real_outcome_count` is a callable returning a market's real competitor count.

    Returning None is a first-class answer and the whole point of #1793: a slug
    that names no tournament we hold must 404, never resolve to a neighbour.

    ONE MORE THING, AND IT IS THE REASON THIS DOCSTRING IS LONG. #1793 stated a
    root cause — "the adapter falls back to the nearest winner-field market rather
    than returning None; what is missing is a floor" — and it was WRONG in a way
    that would have produced the wrong fix. There was already a floor, it already
    worked, and nothing fell back; the defect was that the identity could not be
    REPRESENTED, so the resolver was choosing confidently among tournaments that
    should never have been comparable. A lane that had built the stated floor would
    have shipped, measured nothing, and left `us-open-2026` serving Cincinnati.

    That is why ruling 035 exists (`docs/rulings/035-…`): an issue's root-cause
    field is a HYPOTHESIS, and ratification approves the PRIORITY of a problem,
    never the diagnosis of it. Re-derive the mechanism from the running system
    before you fix anything here, however confidently the ticket states it, and
    whoever signed it.
    """
    from app.utils.name_normalization import clean_slug

    slug_gender = tennis_gender(slug)
    # #1793: IDENTITY tokens, not `tournament_tokens`. The child-association token
    # space drops short words, which deleted the only word identifying the US Open.
    slug_tokens = canonical_slug_tokens(slug)

    candidates = []
    for m in markets:
        if not is_winner_market(m.name):
            continue
        exact = clean_slug(m.name or "") == slug
        subset = bool(slug_tokens) and slug_tokens <= canonical_tokens(m.name)
        if not (exact or subset):
            continue
        # #1793: the field floor guards INFERENCE, not a direct request.
        #
        # An EXACT slug match is the caller naming this market — search and
        # typeahead both emit `event:tennis:{clean_slug(name)}` for any winner
        # market (`routes/events.py:3307`, `:4033`, `utils/concept_links.py:235`),
        # and production really does return
        # `event:tennis:serena-williams-to-win-a-tournament-in-2026` for the query
        # "serena". Refusing those would turn a wrong page into a DEAD link — a
        # broken shelf, which is not an improvement.
        #
        # A SUBSET match is the resolver INFERRING that this market represents the
        # tournament the slug named, and that is where the damage was: a
        # one-outcome novelty prop stood in as Wimbledon's primary, because
        # `is_winner_market` only reads the words in a name. Inference has to clear
        # the higher bar.
        if not exact and not is_winner_field(m.name, real_outcome_count(m)):
            continue
        if slug_gender:
            mg = tennis_gender(m.name)
            if mg and mg != slug_gender:
                continue
        candidates.append(m)

    if not candidates:
        return None

    # Richest wins: most real competitors, then higher 24h volume, then an
    # exact-slug match, then lowest id (stable / deterministic).
    #
    # ⚠️ THIS IS A TIE-BREAK, NEVER AN IDENTITY MECHANISM (ruling 031 — assigned
    # identity beats inferred). It is only sound because `candidates` has already
    # been filtered to markets that ARE the tournament the slug names. Among four
    # renderings of one tournament, "most competitors" picks the fullest draw and
    # that is the L2-65 alias-convergence feature working as designed.
    #
    # Weaken the identity filter above and this line silently becomes resolution
    # BY POPULARITY, which is the #1793 defect exactly: with the US Open reduced to
    # the token {"open"}, Cincinnati entered the candidate set and won here on a
    # 78-player draw against the US Open's own 41. Nothing was broken at this
    # line — it faithfully ranked a set that should never have contained
    # Cincinnati. That is why the fix went upstream into the token space and not
    # into `_rank`, and it is why a bigger draw must never be allowed to answer
    # the question "which tournament is this".
    #
    # Corollary, because it was the tempting wrong read on #1793: this does NOT
    # self-heal when the US Open's own draw fills out. Popularity that happens to
    # agree with identity is still not identity; it just stops being visibly wrong.
    def _rank(m):
        vol = float(getattr(m, "volume_24h", None) or getattr(m, "volume", None) or 0.0)
        return (real_outcome_count(m), vol, clean_slug(m.name or "") == slug, -(m.id or 0))

    return max(candidates, key=_rank)


def tennis_gender(text: str | None) -> str:
    """men / women / "" inferred from a market name or slug.

    Women is checked first so the "men" substring inside "women" never misfires.
    Used by canonical resolution (L2-65 Item 2) so a gendered slug
    ("…-men-s-…") can never resolve to the opposite-gender field even though the
    gender tokens are stripped from `tournament_tokens`.
    """
    t = (text or "").lower()
    if "women" in t or "wta" in t or "ladies" in t or "female" in t:
        return "women"
    if "men" in t or "atp" in t or "male" in t:
        return "men"
    return ""


def tennis_status(
    status: str | None, resolution_date, now, *, proximity_live: bool = False
) -> str:
    """upcoming / live / settled / unknown from status + resolution proximity.

    ═══ WHY A CALLER WITH NO EVIDENCE GETS "unknown", NOT "upcoming" (UX-P209) ═══

    UX-P208 made "live" opt-in (the reasoning is kept below, and it stands) but
    returned "upcoming" when the flag was off. CERT-519 blocked that, correctly:
    the rail had just finished stating that it cannot tell whether a tournament
    has begun, and then said one had not. `StatusPill` renders every non-live,
    non-settled status as a confident **Upcoming**, so the fix swapped a false
    LIVE claim for a false UPCOMING one — on the US Open, which was in its
    third day and had two matches in progress while the card announced it as
    forthcoming. One wrong affirmative for another is not a repair.

    Doctrine 1: could-not-check never renders as nothing-to-report. So the
    no-evidence case now has its own name. `unknown` is not a filtered-out
    state — those cards stay on the rail, keep their name, date and link, and
    simply do not claim a phase. `HubStatusPill` withholds the label for it.

    ═══ WHY "live" IS OPT-IN AND DEFAULTS TO OFF (UX-P208) ═══

    This returned "live" for anything resolving within 21 days, and `/hub/tennis`
    printed a pulsing LIVE dot over four cards dated up to a fortnight ahead —
    Alex, 2026-08-30, the defect-list item this fix answers. Reproduced on the
    live payload that evening: WTA Washington (resolving Sep 5), WTA Toronto
    (Sep 12), the Women's US Open (Sep 13) and ATP Montreal (Sep 13) all carried
    the dot, six to fourteen days out.

    Proximity to a resolution date is not liveness, and on this data it is not
    even proximity to a real END. Measured over all 314 open tennis winner
    markets on 2026-08-31: `commence_time == resolution_date` for **302 of the
    311** rows carrying both — gotcha #14, a Kalshi close-time artifact rather
    than a start. All seven tournament winner-field markets behind the rail
    carry `event_id IS NULL`, so there is no event row to consult either. No
    trustworthy tournament start signal is reachable from here.

    Golf's sibling classifier already states this rule, in these words:
    `_golf_status` returns "live" ONLY from an ASSERTED `schedule_status`
    ("in_progress"/"live"/"active") and warns that it does "NOT trust
    resolution_date here alone — it can carry a FUTURE Kalshi close-time
    artifact (gotcha #14)". Tennis has no schedule feed, so tennis has no
    assertion available, so tennis must not claim.

    Hence the default: silence means "we cannot tell", and a caller that wants
    the old inference has to name it. `TennisEventAdapter.build_event` passes
    `proximity_live=True` deliberately — see the note at that call site.

    `proximity_live` therefore carries BOTH halves of the authority: a caller
    that passes it is asserting that resolution proximity is a usable phase
    signal for its surface, which makes "live" available to it AND makes its
    "upcoming" a claim it is entitled to make. A caller that does not pass it
    has no phase signal at all, so it gets neither.
    """
    if (status or "").lower() in ("resolved", "closed", "settled", "final"):
        return "settled"
    if resolution_date is not None:
        try:
            if resolution_date < now:
                return "settled"
            if proximity_live:
                days = (resolution_date - now).total_seconds() / 86400
                if days <= 21:
                    return "live"
        except TypeError:
            pass
    # Not settled, and no evidence either way unless the caller supplied the
    # authority to read proximity as a phase (UX-P209 / CERT-519).
    return "upcoming" if proximity_live else "unknown"


#: The four Grand Slams. Tennis's majors are a CLOSED, stable set — unlike golf's
#: (which the source data flags for us) or combat's (which `card_label` derives
#: from numbering), there is nothing upstream to read, so the vocabulary is the
#: implementation. Roland Garros and the French Open are the same tournament under
#: two names and BOTH spellings are live in the corpus (measured 2026-08-29: two
#: separate winner markets, one per source), so both must be recognized.
_SLAM_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"\baustralian\s+open\b", re.I),
    re.compile(r"\b(?:french\s+open|roland\s+garros)\b", re.I),
    re.compile(r"\bwimbledon\b", re.I),
    re.compile(r"\bus\s+open\b", re.I),
)


def tennis_is_major(name: str | None) -> bool:
    """True when a tennis tournament name is one of the four Grand Slams.

    Both tennis concept sites hardcoded `is_major: False`, so `/hub/tennis`'s
    "★ Marquee" chip and `EventHeader`'s "Major" chip could never render for
    tennis — the US Open included, measured live 2026-08-29 (0 of 12 hub cards
    flagged, and 0 of 48 across all five hubs). Tennis was the only one of the
    four hub listers with no mechanism to express a major at all.

    ⚠️ The ` vs ` guard is not defensive padding — it is the measured population.
    A census of tennis-categorized winner markets the same day returned 14 rows,
    of which **three are football**: "Huddersfield vs Wimbledon: First Half
    Winner", "Wimbledon vs Newport", "Wimbledon vs Reading". AFC Wimbledon is a
    football club and those rows carry `llm_sport_category = 'tennis'`. A bare
    `%Wimbledon%` substring test badges a football match as a Grand Slam. Both
    call sites happen to gate on `is_winner_field` first, which excludes them
    today — this predicate does not inherit that gate and must not rely on it.
    """
    n = name or ""
    if re.search(r"\bvs\.?\b", n, re.I):
        return False
    return any(p.search(n) for p in _SLAM_PATTERNS)


async def list_tennis_tournament_concepts(
    db: AsyncSession,
    *,
    statuses: tuple[str, ...] = ("upcoming", "live", "unknown"),
    limit: int = 20,
) -> list[dict]:
    """Enumerate upcoming/live TENNIS tournament concepts for the /hub/tennis rail
    (L2-87 B6) — the winner-field analogue of `list_f1_gp_concepts`. Groups open
    tennis WINNER markets by tournament token (gender-split), then keys each group on
    the RICHEST field's `clean_slug(name)` so the emitted key converges with what
    `TennisEventAdapter.build_event` resolves to (it also canonicalizes on the
    richest winner market — L2-65). Read-only, best-effort.

    Returns {key, name, domain, status, start_date, is_major, entry_count}.
    """
    from datetime import datetime, timezone

    from app.models import FuturesMarket
    from app.utils.name_normalization import clean_slug
    from app.utils.outcome_display import (
        is_field_outcome,
        is_placeholder_outcome_name,
    )

    now = datetime.now(timezone.utc)
    q = (
        select(FuturesMarket)
        .options(selectinload(FuturesMarket.outcomes))
        .where(
            FuturesMarket.llm_sport_category == "tennis",
            FuturesMarket.status == "open",
        )
    )
    markets = list((await db.execute(q)).scalars().unique().all())

    def _real_count(m) -> int:
        return sum(
            1
            for o in (m.outcomes or [])
            if o.name
            and not is_field_outcome(o.name)
            and not is_placeholder_outcome_name(o.name)
        )

    # Group winner markets by tournament token + gender so a men's and women's event
    # (which share the token) stay distinct concepts with distinct slugs.
    groups: dict[frozenset, list] = {}
    for m in markets:
        # #1793, both directions: the hub must not LINK what the adapter will not
        # SERVE. `/hub/tennis` was linking "Serena Williams to Win a Tournament in
        # 2026" as a tournament (measured in production 2026-08-12); with the
        # primary guard in `build_event` and no guard here, that link would have
        # become a 404 — the broken shelf, arriving via the rail.
        if not is_winner_field(m.name, _real_count(m)):
            continue
        # Group on the IDENTITY tokens the adapter resolves with, so the key this
        # rail emits still converges with what `build_event` picks (L2-65).
        toks = set(canonical_tokens(m.name))
        if not toks:
            continue
        g = tennis_gender(m.name)
        if g:
            toks.add(f"g:{g}")
        groups.setdefault(frozenset(toks), []).append(m)

    def _rank(m):
        vol = float(getattr(m, "volume_24h", None) or getattr(m, "volume", None) or 0.0)
        return (_real_count(m), vol, -(m.id or 0))

    concepts: list[dict] = []
    for ms in groups.values():
        winner = max(ms, key=_rank)
        slug = clean_slug(winner.name or "")
        if not slug:
            continue
        # A group can hold one tournament as rendered by SEVERAL sources, and they
        # do not all know the same facts. `winner` is chosen for the fullest DRAW
        # (the L2-65 alias-convergence tie-break) — that decides identity, name and
        # slug, and it must keep deciding them. It does NOT follow that the richest
        # draw also carries the date: measured 2026-08-29, the two markets that the
        # tier-token fix merges are exactly the ones where it does not. "ATP 1000
        # Montreal: Winner" has 69 outcomes and `resolution_date = NULL`; "ATP
        # Montreal Winner" has 46 and knows the tournament ends 2026-09-13. Reading
        # the date off `winner` alone would have merged the duplicate card and, in
        # the same move, downgraded the survivor from `live` with a date to
        # `upcoming` with none — trading a visible duplicate for a silent
        # subtraction, which is a worse bug than the one being fixed.
        #
        # So identity comes from the winner and the DATE comes from the group: the
        # winner's own date when it has one, else the earliest a sibling knows.
        # This is not guessing a date we do not have — it is reading one we DO
        # have, off another rendering of the same tournament.
        end_at = winner.resolution_date
        if end_at is None:
            sibling_dates = [
                m.resolution_date for m in ms if m.resolution_date is not None
            ]
            if sibling_dates:
                end_at = min(sibling_dates)
        # UX-P208: no `proximity_live` here, so the rail never claims a
        # tournament has begun — it has no evidence either way (see
        # `tennis_status`). UX-P209/CERT-519: and it does not claim the opposite
        # either, so what it emits here is `unknown`, which is why `unknown` is
        # in the default `statuses`. Membership is deliberately untouched: every
        # card that appeared on the rail before still appears on it, in the same
        # order, with the same name and date. What changed is only what a card
        # is willing to assert about its own phase.
        status = tennis_status(winner.status, end_at, now)
        if status not in statuses:
            continue
        concepts.append(
            {
                "key": f"event:tennis:{slug}",
                "name": winner.name,
                "domain": "tennis",
                "status": status,
                # UX-P178: this value was served under `start_date`, and it is not
                # one. `end_at` is the GROUP's `resolution_date` (see the block
                # above) — when the winner market RESOLVES, i.e. at or after the
                # tournament ENDS. So `/hub/tennis` printed a date days in the
                # future under a card claiming the tournament was already on, while
                # `TennisEventAdapter.build_event` one click away served that
                # IDENTICAL timestamp as `end_date` with `start_date: None`. One
                # value, two opposite names, one click apart. The adapter's reading
                # is the correct one, so the rail adopts it and the two layers now
                # agree. Tennis was the sole outlier among the four hub listers:
                # ufc/boxing serve `latest_commence`, golf serves `start_date or
                # commence_time` — all genuine starts. We have no tournament start
                # date for tennis, and a date we do not have is absent, never
                # guessed. Membership and the printed value are unchanged; only the
                # NAME of the fact changes, and the card now labels it "Ends".
                "start_date": None,
                "end_date": (end_at.isoformat() if end_at is not None else None),
                "is_major": tennis_is_major(winner.name),
                "entry_count": _real_count(winner),
                "_sort": end_at,
            }
        )

    concepts.sort(
        key=lambda c: c.get("_sort") or datetime.max.replace(tzinfo=timezone.utc)
    )
    for c in concepts:
        c.pop("_sort", None)
    return concepts[:limit]


class TennisEventAdapter:
    domain = "tennis"

    async def build_event(self, slug: str, db: AsyncSession) -> dict | None:
        from datetime import datetime, timezone
        from app.utils.name_normalization import clean_slug
        from app.utils.outcome_display import (
            is_field_outcome,
            is_placeholder_outcome_name,
            normalize_display_probs,
        )
        from app.utils.tennis_population import (
            attach_outcomes,
            load_outcomes,
            load_population,
            winner_candidate_ids,
        )

        now = datetime.now(timezone.utc)
        # L2-81: keep OPEN markets (live/upcoming) AND recently-resolved ones, so a
        # tournament that just concluded still renders its settled state instead of
        # 404-ing. Polymarket flips the winner market to resolved/closed the moment
        # it settles; without this it drops out of the query and the page vanishes
        # right when the champion is crowned (Sunday night of a slam). Bounded by
        # resolution_date so ancient tournaments never resurface / clutter matching.
        #
        # LAT-P146: the SAME two arms, fetched differently. Loading them as ORM
        # rows with `selectinload(outcomes)` cost 23,101 markets and 50,842
        # outcomes in ~47 queries to render 1,307 children — measured 21.0 s on
        # the US Open, and 30.3 s (Heroku H12, an error page) on one of its alias
        # slugs. The open arm is now read fresh off its own partial index; the
        # resolved arm is a sequential scan of a 1.6 GB table that is identical
        # for every tennis key, so it is fetched once and shared, as a strict
        # superset whose window is re-applied here. Identity only: no price and
        # no grade is ever read from the shared half.
        # `app/utils/tennis_population.py` carries the measurements.
        markets = await load_population(
            db, now=now, window_days=_RESOLVED_WINDOW_DAYS
        )
        if not markets:
            return None

        # LAT-P146: outcomes for the winner CANDIDATES, and nothing else yet —
        # `winner_candidate_ids` is a superset of every market the resolver below
        # can ask a count about, derived from the same name-only tests it uses.
        attach_outcomes(
            markets, await load_outcomes(db, winner_candidate_ids(markets, slug))
        )

        def _real_outcome_count(m) -> int:
            return sum(
                1 for o in (m.outcomes or [])
                if o.name and not is_field_outcome(o.name)
                and not is_placeholder_outcome_name(o.name)
            )

        winner = select_winner_field(markets, slug, _real_outcome_count)
        if winner is None:
            return None

        # Canonical key from the WINNER's name so every alias slug (bare or
        # differently-named-per-source) reports the same event key.
        canonical_slug = clean_slug(winner.name or "") or slug

        # L2-83: compute the event status once, up front — the settled-winner crown
        # below references it, and the envelope reuses it (single source of truth).
        #
        # UX-P208: `proximity_live=True` keeps THIS surface bit-for-bit as it
        # was, and it is named rather than inherited so the debt stays visible.
        #
        # The inference is unsound here for exactly the reason it was unsound on
        # the hub rail. It is retained anyway because this page is the flagship
        # during the US Open, and flipping it to "upcoming" mid-tournament would
        # trade Alex's bug for a worse one on a busier surface. The honest repair
        # for this call site is a different repair: unlike the rail, this one HAS
        # the evidence — `children` below are the tournament's own match markets,
        # and a draw with played matches is a draw that started. That needs its
        # own measurement and guards, so it is parked (UX-P208-1) rather than
        # smuggled into a card fix.
        event_status = tennis_status(
            winner.status, winner.resolution_date, now, proximity_live=True
        )

        # Competitors = real players (drop the field-remainder "Other" + placeholders).
        competitors = []
        for o in winner.outcomes or []:
            if is_field_outcome(o.name) or is_placeholder_outcome_name(o.name):
                continue
            competitors.append({
                "name": o.name,
                "probability": (
                    round(float(o.current_probability), 4)
                    if o.current_probability is not None else None
                ),
                # L2-81: the authoritative settled winner (from resolution), so the
                # page can render "Won" instead of a stale probability once the
                # tournament concludes. getattr keeps it mock-safe in unit fixtures.
                "won": bool(getattr(o, "is_winner", False)),
            })

        # L2-83: crown the price-settled champion during the is_winner grading-lag
        # window. A concluded winner-market (status/date settled) whose top outcome
        # is priced ~1.0 IS the champion — but `normalize_display_probs` below scales
        # a dominant leader DOWN (women's Wimbledon: Nosková's raw 0.9995 → 0.888,
        # under the frontend's >=0.9 crown threshold → "Awaiting the final result" on
        # a decided tournament). So read the RAW price here (pre-normalize) and set
        # the display `won` flag on the single leader. Display-only: never writes
        # is_winner — authoritative grading stays Lane-1's (gotcha #21). No-op once
        # is_winner is graded (that path already set won=True above).
        if event_status == "settled" and not any(c["won"] for c in competitors):
            top = max(competitors, key=lambda c: (c["probability"] or -1), default=None)
            if top is not None and (top["probability"] or 0) >= _WON_PRICE_THRESHOLD:
                top["won"] = True

        # L2-88 render-gap fix: an OPEN winner-market marked "settled" ONLY because a
        # placeholder resolution_date passed is not actually decided. Polymarket sets a
        # tennis final's resolution_date to MIDNIGHT of finals day (e.g. men's Wimbledon
        # 2026-07-12 00:00), which `tennis_status` reads as past → "settled" while the
        # final is still being played (both source markets status='open', no graded
        # winner, top price 0.815 < 0.97). That renders an empty "Awaiting the final
        # result." crown on a live final. If no winner signal survived the crown block
        # (no graded is_winner AND no price-settled leader) and the chosen market is
        # still open, the event is NOT settled — treat it as live so the field renders.
        if (
            event_status == "settled"
            and (winner.status or "").lower() == "open"
            and not any(c["won"] for c in competitors)
        ):
            event_status = "live"

        # #23: independent candidate binaries can sum >100% (the raw Wimbledon
        # field did: 28.6+26.8+24.6+21.1…). Normalize the displayed field like
        # search/detail do, so the winner-field reads as a coherent distribution.
        normalize_display_probs(competitors)
        competitors.sort(key=lambda c: (c["probability"] or -1), reverse=True)

        # Children (L2-62): associate MATCH markets by ENTRANT-SET overlap — both
        # competitors must be in this event's draw (the winner field). This is the
        # concurrent-tournament guard: a Challenger match in the same date-window
        # whose players aren't in the slam draw is excluded. Non-match markets
        # (props) still associate by the tournament-name token (fallback).
        from app.utils.event_matcher import entrant_key_set, market_in_event
        entrant_keys = entrant_key_set([c["name"] for c in competitors])
        tokens = tournament_tokens(winner.name)

        # L2-63 association hierarchy (no auto-associate on weak signals — L2-61
        # precedent: mislabeling > missing):
        #   entrant  — both competitors in the draw (confident matchups)
        #   container— shares a source-native container (group_id) with a CONFIDENT
        #             sibling (winner or entrant matchup) → inherits (catches no-
        #             entrant tournament props when a source groups them)
        #   token    — name shares the tournament token (props naming the event)
        # Collect confident containers first (winner + entrant matchups).
        matched_containers = {winner.group_id} if winner.group_id else set()
        for m in markets:
            if m.id != winner.id and m.group_id and market_in_event(m.name, entrant_keys):
                matched_containers.add(m.group_id)

        # LAT-P146: association first, outcomes second. Every one of the three
        # methods above reads a NAME or a `group_id` — none of them needs a price
        # — so the children can be identified before anything is loaded, and then
        # their outcomes fetched in ONE query instead of the whole population's in
        # forty-seven. Measured on the US Open: 1,307 children out of a 23,101
        # market population, so ~94% of that load was never read.
        associated: list[tuple[object, str]] = []
        for m in markets:
            if m.id == winner.id:
                continue
            if market_in_event(m.name, entrant_keys):
                method = "entrant"
            elif m.group_id and m.group_id in matched_containers:
                method = "container"
            elif shares_tournament(m.name, tokens):
                method = "token"
            else:
                continue
            associated.append((m, method))

        attach_outcomes(
            (m for m, _ in associated),
            await load_outcomes(db, [m.id for m, _ in associated]),
        )

        matchup_ids, prop_ids, children = [], [], []
        for m, method in associated:
            outs = sorted(
                (m.outcomes or []),
                key=lambda o: float(o.current_probability or 0),
                reverse=True,
            )
            lead = outs[0] if outs else None
            lead_prob = (
                float(lead.current_probability)
                if lead and lead.current_probability is not None else None
            )
            # L2-63 Item 2: a match whose leader is at a dead extreme is DECIDED —
            # mark it settled so the page groups/de-emphasizes it instead of showing
            # a stale 99% as if live (mirrors the L2-53 settled ruling). Kalshi
            # settled markets stay status='open' (gotcha #33), so use the price.
            #
            # #1812 (#1803's blast radius): the price test was the ONLY signal, and
            # it fails on exactly the matches it most needs to grade — a three-set
            # thriller never converges, so the least cleanly resolved matches are the
            # ones that keep looking live. MEASURED: `event:tennis:wimbledon-2026`
            # returns `status: settled` with 47 of 75 children unsettled, 45 of them
            # in the mid-band. Two ASSIGNED terms, OR-ed, never substituted:
            #   * the tournament's own status — a concluded draw means every match
            #     was played (a slam is atomic in time), and `event_status` has
            #     ALREADY been demoted back to "live" above (the L2-88 block) in the
            #     one case it is known to lie, a placeholder resolution_date. That
            #     demotion is what makes it safe to trust here.
            #   * the match market's own status/grade, which is more precise still.
            # A tournament in play is unreachable by both: they are False there and
            # the value is bit-for-bit the old inference.
            settled = settled_under_assigned_state(
                inferred=price_converged(lead_prob),
                assigned_settled=(
                    event_status == "settled" or market_assigned_settled(m, outs)
                ),
            )
            child = {
                "market_id": m.id,
                "market_name": m.name,
                "source": m.source,  # data-only (audit per-source); NOT rendered (D1)
                "method": method,    # data-only (audit per-method)
                "settled": settled,
                "probability": round(lead_prob, 4) if lead_prob is not None else None,
                "outcomes": [
                    {"name": o.name, "probability": (
                        round(float(o.current_probability), 4)
                        if o.current_probability is not None else None)}
                    for o in outs[:4]
                ],
            }
            children.append(child)
            (matchup_ids if method == "entrant" else prop_ids).append(m.id)

        sections = [{"type": "winner", "label": "Winner", "market_ids": [winner.id]}]
        if matchup_ids:
            sections.append({"type": "matchup", "label": "Matchups", "market_ids": matchup_ids})
        if prop_ids:
            sections.append({"type": "prop", "label": "Props", "market_ids": prop_ids})

        envelope = {
            "event": {
                "key": f"event:tennis:{canonical_slug}",
                "domain": "tennis",
                "name": winner.name,
                "status": event_status,
                "start_date": None,
                "end_date": (
                    winner.resolution_date.isoformat()
                    if winner.resolution_date is not None else None
                ),
                "venue": None,
                "location": None,
                "is_major": tennis_is_major(winner.name),
            },
            "primary": {
                "kind": "winner_field",
                "label": "Winner",
                "competitors": competitors,
                "evolution_market_id": winner.id,
            },
            "sections": sections,
            "children": children,
            "movers": [],
        }

        # L2-71: attach compact per-competitor history from the envelope (drops the
        # separate history fetches). Shared helper; lazy-imported to avoid the
        # event_concept ↔ event_tennis import cycle. Best-effort.
        try:
            from app.utils.event_concept import attach_competitor_history
            await attach_competitor_history(db, winner.id, competitors)
        except Exception:
            pass

        return envelope
