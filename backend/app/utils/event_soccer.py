"""Soccer tournament adapter for the Event Concept framework — #205 (World Cup
Emergency Assembly).

The FIFA World Cup IS a textbook event concept (design §3.1/§5): a CONTAINER whose
primary block is a WINNER FIELD (the trophy — national teams, a leaderboard like
golf/tennis) and whose children are the remaining BRACKET GAMES as DUELS. Unlike
every other registered adapter, the duels come from the ``events`` table (real
registry game rows the soccer source tasks already ingest), not from FuturesMarkets
— so this adapter fuses two data planes: the winner-field FUTURES + the game EVENTS.

Data reality (verified live 2026-07-15, the final week):
  * Winner field — three markets carry the trophy: odds_api ``FIFA World Cup Winner``
    (fresh, real country names), Kalshi ``KXMENWORLDCUP-26`` (real countries, staler),
    Polymarket ``World Cup Winner`` (anonymized "Team AM" placeholders). We pick the
    FRESHEST market that carries ≥2 real (non-placeholder) priced outcomes — the blend
    is the product, and freshness is what makes it honest during a live bracket.
  * Games — the bracket lives in ``events`` under sport key ``soccer_fifa_world_cup``
    (group stage through final). We surface the LIVE game + remaining scheduled games +
    recently-completed results as duels, each with its blended home win probability
    (``compute_aggregate_probability``) — settled-means-settled for finished games.
  * Entity linkage — competitor country names + duel team names resolve to ``teams``
    rows via name / abbreviation / alternate_names ("France" / "Les Bleus" class), so
    the page can carry canonical names + crests where a match exists (honest gap where
    it does not).

Emits the same generic envelope ``/event/{key}`` renders. Concept key:
``event:soccer:world-cup-2026`` (aliases: ``world-cup``, ``fifa-world-cup``,
``world-cup-final``, ``2026``).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.utils.nation_flags import flag_url as nation_flag_url
from app.utils.nation_flags import is_nation as nation_is_nation

# Raw price at/above which a SETTLED winner-field team is the crowned champion during
# the is_winner grading-lag window (parity with awards/election/tennis — display only).
_WON_PRICE_THRESHOLD = 0.97

# Winner-field competitor cap (the trophy field is ~48 nations; the UI renders the
# contenders — the rest are eliminated/null-priced and filtered out anyway).
_COMPETITOR_CAP = 48

# The matches section is the tournament's HISTORY, not just its future (#208 Item 1a:
# join ALL played group-stage/knockout matches, not just the last few days). A 48-team
# WC is 104 matches — cap generously so the whole bracket surfaces.
_MATCH_CAP = 160


@dataclass(frozen=True)
class SoccerTournamentConfig:
    """One soccer tournament "edition" — the winner-field analogue of a golf major."""

    slug: str  # canonical URL slug, e.g. "world-cup-2026"
    display: str  # human name, e.g. "2026 FIFA World Cup"
    sport_key: str  # events sport key, e.g. "soccer_fifa_world_cup"
    edition: int  # 4-digit edition year
    aliases: tuple[str, ...] = field(default_factory=tuple)
    # A phrase that must appear in a futures-market name for it to be this
    # tournament's WINNER field (so "World Cup Winner" matches but "Copa America
    # Winner" would not, once more tournaments are added).
    winner_name_re: re.Pattern = field(default=re.compile(r"world\s*cup", re.I))


SOCCER_TOURNAMENTS: dict[str, SoccerTournamentConfig] = {
    "world-cup-2026": SoccerTournamentConfig(
        slug="world-cup-2026",
        display="2026 FIFA World Cup",
        sport_key="soccer_fifa_world_cup",
        edition=2026,
        aliases=(
            "world-cup",
            "worldcup",
            "fifa-world-cup",
            "world-cup-final",
            "2026-world-cup",
            "2026-fifa-world-cup",
            "2026",
        ),
    ),
}

# slug (canonical + alias) -> config, built once.
_BY_SLUG: dict[str, SoccerTournamentConfig] = {}
for _cfg in SOCCER_TOURNAMENTS.values():
    _BY_SLUG[_cfg.slug] = _cfg
    for _a in _cfg.aliases:
        _BY_SLUG[_a] = _cfg


# ---------------------------------------------------------------------------
# Pure helpers — unit-tested.
# ---------------------------------------------------------------------------


def parse_soccer_slug(slug: str) -> SoccerTournamentConfig | None:
    """Resolve a soccer-tournament slug (canonical or alias) to its config, else None.

    "world-cup-2026" / "world-cup" / "fifa-world-cup" / "2026" -> the WC 2026 config."""
    s = (slug or "").strip().lower()
    return _BY_SLUG.get(s)


# Non-trophy World Cup markets that ride the "world cup" name but are NOT the overall
# winner field: individual awards (boot/glove/ball), group winners, novelties, hosts.
#
# Two guard classes live here:
#   1. Award / group / novelty markets of the FIFA WC itself (boot, glove, squad, ...).
#   2. OTHER-CODE "World Cup" competitions that carry the phrase but are a different
#      sport entirely — the "Esports World Cup Chess Finals Winner" (Kalshi
#      KXCHESSTOURNAMENT-26EWC, mis-tagged llm_sport_category="soccer") is a LIVE,
#      freshly-polled, coherent field, so before this guard it BEAT the real FIFA field
#      on freshness and crowned Magnus Carlsen as the "World Cup" favorite (L2-130
#      live-envelope forensic, 2026-07-15). Mirrors the search-side `_WORLD_CUP_NEG_RE`
#      vocabulary (routes/events.py) plus chess/esports/continent — a winner-field
#      market must be the men's FIFA trophy, not chess, cricket, rugby, a continent
#      bucket, or an age-group/women's edition.
_NON_WINNER_FIELD_RE = re.compile(
    r"\bgolden\b|\bsilver\b|\bbronze\b|\bboot\b|\bglove\b|\bball\b"
    r"|\bgroup\b|\bfirst\s+time\b|\bfair\s+play\b|\byoung\s+player\b"
    r"|\bhost\b|\bhalftime\b|\bsquad\b|\btrail\b|\bunbeaten\b|\bqualif\w+"
    r"|\bannouncers?\b|\bmention\b|\bremoved\b|\bcompete\b|\bT20\b|\bclub\b"
    r"|\bintercontinental\b|\bmessi\b|\bronaldo\b|\bpenalty\b|\bgoalie\b"
    r"|\bafc\b|\bworst\b|\bfurthest\b|\bsemifinals?\b"
    # other-code World Cups + non-team fields that would false-win the trophy slot:
    r"|\besports?\b|\bchess\b|\bcricket\b|\brugby\b|\bnetball\b|\bhockey\b"
    r"|\bcontinent\b|\bwomen'?s?\b|\bu-?\s?(?:17|19|20|21|23)\b",
    re.I,
)


def is_wc_winner_field_market(name: str | None) -> bool:
    """True when a futures-market name is the overall World Cup WINNER field (the
    trophy), not one of the award/group/novelty markets that share the "world cup"
    name. Requires "world cup" + a winner word, and no non-trophy keyword."""
    n = name or ""
    if not re.search(r"world\s*cup", n, re.I):
        return False
    if not re.search(r"\bwinner\b|\bchampion\b|\bto\s+win\b", n, re.I):
        return False
    return not _NON_WINNER_FIELD_RE.search(n)


# #208 Item 1d: the FUN props section. WC-named open markets that are NOT the trophy
# winner field and NOT the qualifier/round ladders (those belong to the bracket, not
# the props reel), and are NOT another-code "World Cup" (chess/cricket/rugby/women's/
# T20/club) that only rides the phrase. What survives is the genuinely fun stuff:
# halftime show, songs, announcer bingo, total goals, penalty shootouts, attendance,
# top-scorer / golden-boot awards, third place, Messi streaks.
_PROP_EXCLUDE_RE = re.compile(
    r"\bqualif\w+|\besports?\b|\bchess\b|\bcricket\b|\brugby\b|\bnetball\b"
    r"|\bwomen'?s?\b|\bu-?\s?(?:17|19|20|21|23)\b|\bclub\s+world\s+cup\b"
    r"|\bround\s+of\s+16\b|\bsemifinal\s+qualif\w+|\bquarterfinal\s+qualif\w+",
    re.I,
)


def is_wc_prop_market(name: str | None) -> bool:
    """True when a WC-named open market is a surface-worthy FUN prop (Item 1d):
    world-cup named, NOT the trophy winner field, NOT a qualifier/round ladder, NOT
    an other-code World Cup. Clubs/derivative ladders never qualify."""
    n = name or ""
    if not re.search(r"world\s*cup", n, re.I):
        return False
    if is_wc_winner_field_market(n):
        return False
    return not _PROP_EXCLUDE_RE.search(n)


def build_props_list(markets: list, cap: int = 14) -> list[dict]:
    """Curate the fun-props reel from open WC markets (Item 1d). Each entry carries
    the market identity + its top priced outcomes so Lane 2 can render a card without
    a second fetch. Ranked by 24h volume then total volume (the liveliest props
    first). Markets with no priced outcome are dropped (nothing to show)."""
    out: list[dict] = []
    for m in markets:
        if not is_wc_prop_market(getattr(m, "name", None)):
            continue
        priced = [
            o
            for o in (getattr(m, "outcomes", None) or [])
            if getattr(o, "current_probability", None) is not None
        ]
        if not priced:
            continue
        priced.sort(key=lambda o: float(o.current_probability or 0), reverse=True)
        top = [
            {
                "name": o.name,
                "probability": round(float(o.current_probability), 4),
            }
            for o in priced[:5]
        ]
        out.append(
            {
                "market_id": getattr(m, "id", None),
                "source": getattr(m, "source", None),
                "name": (getattr(m, "name", None) or "").strip(),
                "outcome_count": len(priced),
                "top_outcomes": top,
                "volume_24h": float(getattr(m, "volume_24h", None) or 0),
                "volume": float(getattr(m, "volume", None) or 0),
                "resolution_date": (
                    m.resolution_date.isoformat()
                    if getattr(m, "resolution_date", None) is not None
                    else None
                ),
            }
        )
    out.sort(key=lambda p: (p["volume_24h"], p["volume"]), reverse=True)
    return out[:cap]


def derive_soccer_concept(
    external_id: str | None,
    name: str | None,
    llm_sport_category: str | None = None,
) -> dict | None:
    """Map a soccer MARKET to its tournament event concept, or None if not a
    surfaced tournament's winner field. The discovery-entry helper
    (search/typeahead + breadcrumb), mirroring ``derive_election_concept``.

    Only the overall WINNER field surfaces the concept — award/group/novelty markets
    return None so they don't dead-link (they still reach the sport page)."""
    if (llm_sport_category or "").lower() not in ("soccer", "football_soccer", ""):
        # Soccer markets carry llm_sport_category="soccer"; be tolerant of blank.
        if llm_sport_category:
            return None
    if not is_wc_winner_field_market(name):
        return None
    # Only one tournament today; when more are added, disambiguate on winner_name_re.
    for cfg in SOCCER_TOURNAMENTS.values():
        if cfg.winner_name_re.search(name or ""):
            return {
                "key": f"event:soccer:{cfg.slug}",
                "name": cfg.display,
                "domain": "soccer",
            }
    return None


def _norm(s: str | None) -> str:
    """Diacritic-stripped, lowercased, whitespace-collapsed name key
    ("Côte d'Ivoire" -> "cote d'ivoire") for entity linkage."""
    n = re.sub(r"\s+", " ", (s or "").strip().lower())
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", n) if not unicodedata.combining(ch)
    )


def build_team_lookup(teams: list) -> dict[str, object]:
    """Build a name/abbreviation/alternate-name -> Team lookup (diacritic-insensitive).

    Powers "France"/"Les Bleus" class entity linkage: a competitor or duel side named
    by any known alias resolves to the canonical Team row. Pure over the passed rows."""
    lut: dict[str, object] = {}
    for t in teams or []:
        if t is None:
            continue
        for key in (getattr(t, "name", None), getattr(t, "abbreviation", None)):
            k = _norm(key)
            if k:
                lut.setdefault(k, t)
        alts = getattr(t, "alternate_names", None)
        if isinstance(alts, (list, tuple)):
            for a in alts:
                k = _norm(a)
                if k:
                    lut.setdefault(k, t)
    return lut


def _team_ref(t) -> dict | None:
    """Compact team-identity ref for the wire (canonical name + crest), or None."""
    if t is None:
        return None
    return {
        "team_id": getattr(t, "id", None),
        "name": getattr(t, "name", None),
        "slug": getattr(t, "slug", None),
        "abbreviation": getattr(t, "abbreviation", None),
        "logo": getattr(t, "logo_url_small", None) or getattr(t, "logo_url", None),
    }


# Anonymized WC winner-field slots ("Team AM", "Team AI") that the shared
# `is_placeholder_outcome_name` misses — its "Team X" guard is single-letter only, to
# spare real Olympic entrants ("Team GB"/"Team USA"). This adapter is soccer-only and
# WC entrants are always country names, so a 1-3 letter "Team XX" here is always the
# Polymarket anonymized placeholder and is safe to drop.
_ANON_TEAM_CODE_RE = re.compile(r"^team\s+[a-z]{1,3}$", re.I)


def _is_real_winner_outcome(name: str | None) -> bool:
    """True for a genuine national-team winner-field outcome (a country name), False
    for field/placeholder/anonymized slots."""
    from app.utils.outcome_display import is_field_outcome, is_placeholder_outcome_name

    n = (name or "").strip()
    if not n:
        return False
    if is_field_outcome(n) or is_placeholder_outcome_name(n):
        return False
    return not _ANON_TEAM_CODE_RE.match(n)


# (max-min)/max over the real priced field: a genuine winner field's favorite towers
# over its longshots (odds_api WC: Spain 0.54 vs France 0.07 → ~0.88 spread). A FLAT
# field is the #199 placeholder signature — the Polymarket WC market is mostly
# anonymized "Team AM" slots with a few live-polled real names all pinned at the same
# ~0.082, which after normalization crowns a nonsense favorite (the "Peru 47%" bug).
# Such a degenerate field is NOT a real winner field and is rejected.
_MIN_FIELD_SPREAD_RATIO = 0.10


# A genuine mutually-exclusive winner field's real prices sum to ~100% (odds_api WC
# sums to ~1.0; Kalshi's to ~1.0 ± overround). The broken Polymarket field is mostly
# stale zeros with a live-polled handful — its real prices sum to only ~0.17, so a
# hair-ahead "Peru" (0.082) normalizes into a nonsense 47% favorite. A field whose
# mass is largely MISSING is a stale/broken snapshot, not a real winner field.
_FIELD_SUM_MIN = 0.70
_FIELD_SUM_MAX = 1.60


def _field_has_real_spread(real_outcomes: list) -> bool:
    """True when the real priced field has meaningful dispersion (a real favorite),
    False for a flat placeholder field (#199). Requires ≥2 priced outcomes."""
    probs = [
        float(o.current_probability)
        for o in real_outcomes
        if o.current_probability is not None
    ]
    if len(probs) < 2:
        return False
    mx, mn = max(probs), min(probs)
    if mx <= 0:
        return False
    return (mx - mn) / mx >= _MIN_FIELD_SPREAD_RATIO


def _field_is_coherent(real_outcomes: list) -> bool:
    """True when the real prices sum near 100% — a complete mutually-exclusive winner
    field. Rejects a broken snapshot whose probability mass is mostly missing (stale
    zeros), the real cause of the "Peru 47%" bug."""
    total = sum(
        float(o.current_probability)
        for o in real_outcomes
        if o.current_probability is not None
    )
    return _FIELD_SUM_MIN <= total <= _FIELD_SUM_MAX


def _select_winner_field(markets: list):
    """Pick the best World Cup winner-field market: the FRESHEST market whose real
    (non-placeholder) priced field has genuine spread AND sums to a coherent ~100%.
    The spread + coherence gates reject the broken Polymarket field (the "Peru 47%"
    bug — mostly stale zeros) so a live-updated odds_api field wins over a stale
    Kalshi one and a broken Poly one never wins. If NO honest field exists, returns
    (None, []) — the concept renders duels-only rather than a fabricated favorite.
    Returns (market, real_outcomes)."""
    best = None
    best_key = None
    best_real: list = []
    for m in markets:
        real = [
            o
            for o in (m.outcomes or [])
            if _is_real_winner_outcome(o.name) and o.current_probability is not None
        ]
        if (
            len(real) < 2
            or not _field_has_real_spread(real)
            or not _field_is_coherent(real)
        ):
            continue
        freshness = max(
            (
                o.last_updated
                for o in real
                if getattr(o, "last_updated", None) is not None
            ),
            default=datetime.min.replace(tzinfo=timezone.utc),
        )
        if best is None or freshness > best_key:
            best, best_key, best_real = m, freshness, real
    return best, best_real


def _match_is_real(g) -> bool:
    """True for a match worth surfacing. Live/scheduled always count; a
    completed/closed match counts only when it carries a real score on BOTH sides.

    The ``soccer_fifa_world_cup`` sport key collects PHANTOM ``closed`` rows with
    NULL scores (stale scheduled duplicates — verified live 2026-07-15: "Panama vs
    England" 07-11, "Jordan vs Argentina" 07-12, an "Avalanche vs Trail Blazers"
    mis-link) that would otherwise pollute the history. The real-score gate drops
    them without needing round/stage metadata the events table doesn't carry.

    It ALSO drops MATCHING-CREATED PLACEHOLDERS: a mislinked Kalshi prop can spawn
    a teamless or wrong-date event that carries NO schedule-source id and NO
    win-prob data (verified live 2026-07-16: 25 teamless 06-25..07-15 rows each
    holding one mislinked market; a 07-29 "England vs Argentina" built from the
    07-15 semifinal's corner markets). Real WC fixtures come from the odds/schedule
    source (external_id set) and accrue win-prob; a row with neither is a phantom.
    """
    wps = getattr(g, "win_probability_sources", None)
    if getattr(g, "external_id", None) is None and not wps:
        return False
    st = (getattr(g, "status", None) or "").lower()
    if st in ("live", "scheduled"):
        return True
    if st in ("completed", "closed"):
        return getattr(g, "home_score", None) is not None and (
            getattr(g, "away_score", None) is not None
        )
    return False


def _completed_result(g, nation_norm: str) -> str | None:
    """Result ('win'/'loss'/'draw') of a completed match FROM ``nation_norm``'s
    perspective, or None if the nation didn't play it / it isn't a scored result."""
    st = (getattr(g, "status", None) or "").lower()
    if st not in ("completed", "closed"):
        return None
    hs, as_ = getattr(g, "home_score", None), getattr(g, "away_score", None)
    if hs is None or as_ is None:
        return None
    home = _norm(getattr(g, "home_team_name", None))
    away = _norm(getattr(g, "away_team_name", None))
    if nation_norm == home:
        mine, theirs = hs, as_
    elif nation_norm == away:
        mine, theirs = as_, hs
    else:
        return None
    if mine > theirs:
        return "win"
    if mine < theirs:
        return "loss"
    return "draw"


# WC-2026 round by a nation's cumulative match count. 48 teams / 12 groups of 4:
# 3 group games, then top-2 + 8-best-thirds → Round of 32 → R16 → QF → SF → Final.
# The round a nation EXITS in is the round of its Nth (last) completed match. This
# is a pure STRUCTURE signal (match count), never a price. (#210 Item 3.)
_WC_ROUND_BY_MATCH_COUNT = {
    1: "Group Stage",
    2: "Group Stage",
    3: "Group Stage",
    4: "Round of 32",
    5: "Round of 16",
    6: "Quarterfinal",
    7: "Semifinal",
    8: "Final",
}


def _wc_round_for_match_count(n: int) -> str | None:
    """The WC round a nation is in on its Nth match. <=3 is always Group Stage;
    beyond the known bracket depth returns None (honest-unknown, never guessed)."""
    if n <= 0:
        return None
    if n <= 3:
        return "Group Stage"
    return _WC_ROUND_BY_MATCH_COUNT.get(n)


def compute_nation_elimination(games: list) -> dict[str, dict]:
    """For each nation appearing in ``games``, derive its knockout survival state
    from the bracket results — STRUCTURE, never price (Alex's #210 ruling: a
    settled knockout loss is OUT, the round is recorded, price never decides).

    Returns ``{nation_norm: {"out": bool, "round": str | None,
    "eliminated_by": {opponent, score, date, event_id} | None}}``.

    A nation is OUT when its MOST-RECENT completed match was a LOSS: in the
    knockout stage your last game is your exit if you lost, and a still-alive side's
    last completed game was a win (it advanced) or it has yet to play. This is exact
    for the contenders that matter — the finalists' last games are wins, the beaten
    semi-finalists' are losses — and never false-eliminates a live team on a stale
    winner-field price (the "England 29% / France 7% after they lost" bug). ``round``
    is the round of that losing match, derived from the nation's cumulative match
    count (pure structure). Group-stage non-advancers whose last match was NOT a
    loss are handled by the caller's structure signal (played-out + no upcoming
    game), also without price."""
    # Bucket completed matches per nation, newest first.
    per_nation: dict[str, list] = {}
    for g in games:
        st = (getattr(g, "status", None) or "").lower()
        if st not in ("completed", "closed"):
            continue
        if getattr(g, "home_score", None) is None or getattr(g, "away_score", None) is None:
            continue
        for nm in (getattr(g, "home_team_name", None), getattr(g, "away_team_name", None)):
            k = _norm(nm)
            if k:
                per_nation.setdefault(k, []).append(g)

    out: dict[str, dict] = {}
    for k, gs in per_nation.items():
        gs.sort(
            key=lambda g: (getattr(g, "commence_time", None) or datetime.min.replace(tzinfo=timezone.utc)),
            reverse=True,
        )
        last = gs[0]
        res = _completed_result(last, k)
        eliminated = res == "loss"
        by = None
        rnd = None
        if eliminated:
            rnd = _wc_round_for_match_count(len(gs))
            home = _norm(getattr(last, "home_team_name", None))
            opp = (
                getattr(last, "away_team_name", None)
                if k == home
                else getattr(last, "home_team_name", None)
            )
            hs, as_ = getattr(last, "home_score", None), getattr(last, "away_score", None)
            mine, theirs = (hs, as_) if k == home else (as_, hs)
            ct = getattr(last, "commence_time", None)
            by = {
                "opponent": opp,
                "score": f"{mine}-{theirs}",
                "date": ct.isoformat() if ct else None,
                "event_id": getattr(last, "id", None),
                "round": rnd,
            }
        out[k] = {"out": eliminated, "round": rnd, "eliminated_by": by}
    return out


def _drop_slot_duplicate_phantoms(games: list, elim: dict[str, dict]) -> list:
    """Drop stale projected-final DUPLICATES from the match grid.

    When the bracket firms up, the source can leave behind scheduled placeholder
    fixtures for finals that can no longer happen: verified live 2026-07-19 the WC
    final slot carried three scheduled rows — the real Spain vs Argentina beside a
    stale Spain vs England and France vs England (England & France already knocked
    out). An ELIMINATED nation cannot play a future match (#210: elimination is a
    bracket FACT, not a price), so among matches sharing a commence slot we drop
    the ones with an eliminated side WHEN a both-alive match exists for that slot.

    Deliberately narrow to be false-drop-proof: it acts ONLY on a slot that has
    ≥2 scheduled/live rows AND a clean both-alive alternative — so it can never
    remove a unique real fixture (no group-stage exit mislabel can drop a lone
    scheduled match), and it never touches completed history. Fail-open when a
    slot has no all-alive row (keep all). Pairs with ``_match_is_real`` (the
    NULL-score phantom gate) as layered defense-in-depth."""
    from collections import defaultdict

    def _is_elim(nm) -> bool:
        return bool(elim.get(_norm(nm), {}).get("out"))

    slots: dict = defaultdict(list)
    for g in games:
        if (getattr(g, "status", None) or "").lower() in ("live", "scheduled"):
            slots[getattr(g, "commence_time", None)].append(g)

    drop = set()
    for slot, gs in slots.items():
        if slot is None or len(gs) < 2:
            continue
        has_alive = any(
            not _is_elim(getattr(g, "home_team_name", None))
            and not _is_elim(getattr(g, "away_team_name", None))
            for g in gs
        )
        if not has_alive:
            continue  # fail-open: no clean alternative at this slot
        for g in gs:
            if _is_elim(getattr(g, "home_team_name", None)) or _is_elim(
                getattr(g, "away_team_name", None)
            ):
                drop.add(id(g))
    return [g for g in games if id(g) not in drop]


def _apply_settled_crown(
    competitors: list[dict], status: str, price_threshold: float = _WON_PRICE_THRESHOLD
) -> None:
    """Crown the settled champion in place (display-only, never a data write —
    gotcha #21). No-op unless the tournament is settled and no competitor is already
    crowned (``is_winner`` already graded takes precedence — never double-crown).

    STRUCTURE-FIRST (Alex #210 — the bracket decides, not the price): when exactly
    ONE nation still survives elimination with a real (>0) price, it won the trophy
    by bracket result. The runner-up is OUT (its last match was the final it lost)
    and every other nation either lost earlier or never qualified (a 0%-priced
    phantom in the odds_api field). Crowning the sole survivor reads the AUTHORITATIVE
    official result off the settled bracket even though the odds_api winner market
    froze at pre-final prices and never graded to 100% (the "Spain 0.587 / Argentina
    0.435" fizzle, WC-2026) — it does not invent a result.

    Falls back to the raw-price crown (top >= ``price_threshold``) only when the
    field has NOT collapsed to a lone survivor — the grading-lag window where one
    team already sits near-certain. Assumes ``competitors`` is sorted with the top
    probability first (as build_event leaves it)."""
    if status != "settled" or not competitors:
        return
    if any(c.get("won") for c in competitors):
        return
    survivors = [
        c
        for c in competitors
        if not (c.get("eliminated") or {}).get("out") and (c.get("probability") or 0) > 0
    ]
    if len(survivors) == 1:
        survivors[0]["won"] = True
        survivors[0]["probability"] = 1.0
        return
    top = competitors[0]
    if (top.get("probability") or 0) >= price_threshold:
        top["won"] = True


class SoccerEventAdapter:
    """Event-concept adapter for soccer tournaments (winner_field). Resolves
    ``event:soccer:<slug>`` into the generic envelope: the trophy WINNER field as the
    primary block (national teams), the remaining bracket GAMES as duel children."""

    domain = "soccer"

    async def build_event(self, slug: str, db: AsyncSession) -> dict | None:
        from app.models import Event, FuturesMarket, Sport
        from app.utils.aggregation import compute_aggregate_probability
        from app.utils.outcome_display import normalize_display_probs

        cfg = parse_soccer_slug(slug)
        if cfg is None:
            return None

        now = datetime.now(timezone.utc)

        # --- Bracket games (duels) from the events table -------------------------
        # #208 Item 1a: the matches section is the tournament's HISTORY — join ALL
        # played group-stage + knockout matches, not just the final week's. Phantom
        # ``closed`` rows with NULL scores (stale scheduled dups, a stray mis-linked
        # NHL row) are dropped by _match_is_real, so no round/stage metadata needed.
        game_q = (
            select(Event)
            .options(
                selectinload(Event.home_team),
                selectinload(Event.away_team),
            )
            .join(Sport, Event.sport_id == Sport.id)
            .where(
                Sport.key == cfg.sport_key,
                Event.status.in_(["live", "scheduled", "completed", "closed"]),
            )
            .order_by(Event.commence_time)
        )
        all_games = list((await db.execute(game_q)).scalars().unique().all())
        games = [g for g in all_games if _match_is_real(g)]

        # Derive each nation's knockout survival state from the bracket results —
        # the evidence that grades stale winner-field prices on dead entrants to
        # TRUE 0 (Item 1b).
        elim = compute_nation_elimination(games)

        # Defense-in-depth: drop stale projected-final duplicates — an eliminated
        # side scheduled in the same slot as the real final (Spain-England /
        # France-England beside Spain-Argentina). Computed AFTER elim so the
        # bracket evidence is intact; filtered games feed everything downstream.
        games = _drop_slot_duplicate_phantoms(games, elim)

        # Nations still to play a match (live or scheduled). A nation that has
        # PLAYED but has NO upcoming game while the tournament continues is out on
        # structure (a group non-advancer) — never inferred from a 0% price
        # (Alex's #210 ruling). We track played nations + their match counts (for
        # the exit round) and whether the tournament is still ongoing.
        upcoming_nations = {
            _norm(nm)
            for g in games
            if (getattr(g, "status", None) or "").lower() in ("live", "scheduled")
            for nm in (getattr(g, "home_team_name", None), getattr(g, "away_team_name", None))
            if _norm(nm)
        }
        played_match_counts: dict[str, int] = {}
        for g in games:
            if (getattr(g, "status", None) or "").lower() not in ("completed", "closed"):
                continue
            if getattr(g, "home_score", None) is None or getattr(g, "away_score", None) is None:
                continue
            for nm in (getattr(g, "home_team_name", None), getattr(g, "away_team_name", None)):
                k = _norm(nm)
                if k:
                    played_match_counts[k] = played_match_counts.get(k, 0) + 1
        played_nations = set(played_match_counts)
        tournament_ongoing = bool(upcoming_nations)

        # --- Winner field (trophy) from futures ----------------------------------
        win_q = (
            select(FuturesMarket)
            .options(selectinload(FuturesMarket.outcomes))
            .where(
                FuturesMarket.status == "open",
                FuturesMarket.name.ilike("%world cup%"),
            )
        )
        all_wc_markets = list((await db.execute(win_q)).scalars().unique().all())
        candidate_markets = [
            m for m in all_wc_markets if is_wc_winner_field_market(m.name)
        ]
        winner_market, winner_outcomes = _select_winner_field(candidate_markets)

        # No trophy field AND no games → the tournament isn't ingested; honest 404.
        if winner_market is None and not games:
            return None

        # --- Entity linkage: one team lookup across the games' teams -------------
        team_rows = []
        for g in games:
            team_rows.append(getattr(g, "home_team", None))
            team_rows.append(getattr(g, "away_team", None))
        team_lut = build_team_lookup(team_rows)

        # --- Competitors (winner field) -----------------------------------------
        competitors: list[dict] = []
        as_of = None
        if winner_market is not None:
            ranked = sorted(
                winner_outcomes,
                key=lambda o: float(o.current_probability or 0),
                reverse=True,
            )[:_COMPETITOR_CAP]
            for o in ranked:
                nm = o.name
                nnorm = _norm(nm)
                team = team_lut.get(nnorm)
                state = elim.get(nnorm, {})
                # ELIMINATION FROM STRUCTURE — price NEVER decides (Alex, #210).
                # (1) settled knockout loss = OUT (round already recorded by
                #     compute_nation_elimination); (2) group non-advancer = OUT:
                #     the nation has played (has completed matches) but has NO
                #     upcoming live/scheduled game while the tournament continues
                #     for others — a structure fact (played-out + no next game),
                #     not a 0% price. We require its last result was NOT a win, so
                #     a side that advanced but whose next fixture isn't scheduled
                #     yet is never falsely knocked out.
                elim_out = bool(state.get("out"))
                elim_round = state.get("round")
                won = bool(getattr(o, "is_winner", False))
                if (
                    not elim_out
                    and not won
                    and nnorm in played_nations
                    and nnorm not in upcoming_nations
                    and tournament_ongoing
                ):
                    elim_out = True
                    elim_round = _wc_round_for_match_count(
                        played_match_counts.get(nnorm, 3)
                    ) or "Group Stage"
                display_name = team.name if team is not None else nm
                comp = {
                    "name": display_name,
                    "probability": (
                        round(float(o.current_probability), 4)
                        if o.current_probability is not None
                        else None
                    ),
                    "won": won,
                    "team": _team_ref(team),
                    "is_nation": nation_is_nation(display_name) or nation_is_nation(nm),
                    "eliminated": {"out": elim_out, "round": elim_round},
                    "eliminated_by": state.get("eliminated_by"),
                }
                # Read-side flag (Item 1c): the nation's crest is its flag; fill the
                # team ref's logo when the teams row has none (they all did, live).
                fl = nation_flag_url(display_name) or nation_flag_url(nm)
                if fl:
                    comp["flag"] = fl
                    if comp["team"] is not None and not comp["team"].get("logo"):
                        comp["team"]["logo"] = fl
                competitors.append(comp)

            # Grade eliminated nations to TRUE 0, then renormalize the STILL-ALIVE
            # field so the surviving contenders sum to ~100% (Spain/Argentina for the
            # final) instead of leaving mass stranded on dead entrants.
            alive = [c for c in competitors if not c["eliminated"]["out"]]
            for c in competitors:
                if c["eliminated"]["out"]:
                    c["probability"] = 0.0
            normalize_display_probs(
                alive, mutually_exclusive=bool(winner_market.mutually_exclusive)
            )
            # alive first (by prob desc), then eliminated (all zero, ranked as-was).
            competitors.sort(
                key=lambda c: (0 if not c["eliminated"]["out"] else 1, -(c["probability"] or 0))
            )
            as_of = max(
                (
                    o.last_updated
                    for o in winner_outcomes
                    if getattr(o, "last_updated", None) is not None
                ),
                default=None,
            )

        # --- Duel children -------------------------------------------------------
        def _game_rank(g) -> tuple:
            # live first, then upcoming (soonest), then completed (most recent).
            st = (g.status or "").lower()
            if st == "live":
                return (0, g.commence_time)
            if st == "scheduled":
                return (1, g.commence_time)
            return (2, -(g.commence_time.timestamp() if g.commence_time else 0))

        children: list[dict] = []
        upcoming_or_live = 0
        any_live = False

        def _side(name, team, prob):
            ref = {} if team is None else dict(_team_ref(team))
            fl = nation_flag_url(name) or (
                nation_flag_url(team.name) if team is not None else None
            )
            if fl and not ref.get("logo"):
                ref["logo"] = fl
            return {
                **ref,
                "name": name,
                "probability": round(float(prob), 4) if prob is not None else None,
                "flag": fl,
            }

        for g in sorted(games, key=_game_rank)[:_MATCH_CAP]:
            st = (g.status or "").lower()
            settled = st in ("completed", "closed")
            if st == "live":
                any_live = True
            if st in ("live", "scheduled"):
                upcoming_or_live += 1
            home_prob = compute_aggregate_probability(g, g.status)
            away_prob = (1 - float(home_prob)) if home_prob is not None else None
            home_name = getattr(g, "home_team_name", None)
            away_name = getattr(g, "away_team_name", None)
            home_team = getattr(g, "home_team", None) or team_lut.get(_norm(home_name))
            away_team = getattr(g, "away_team", None) or team_lut.get(_norm(away_name))
            outcomes = []
            if home_prob is not None:
                outcomes = [
                    {"name": home_name, "probability": round(float(home_prob), 4)},
                    {"name": away_name, "probability": round(float(away_prob), 4)},
                ]
            home_side = _side(home_name, home_team, home_prob)
            home_side["score"] = getattr(g, "home_score", None)
            away_side = _side(away_name, away_team, away_prob)
            away_side["score"] = getattr(g, "away_score", None)
            children.append(
                {
                    "kind": "matchup",
                    "event_id": g.id,
                    "market_name": f"{home_name} vs {away_name}",
                    "status": st,
                    "settled": settled,
                    "commence_time": (
                        g.commence_time.isoformat() if g.commence_time else None
                    ),
                    "home": home_side,
                    "away": away_side,
                    "outcomes": outcomes,
                }
            )

        # --- Tournament status ---------------------------------------------------
        if any_live:
            status = "live"
        elif upcoming_or_live > 0:
            status = "upcoming"
        else:
            status = "settled"

        # Crown the settled champion (display-only, never a data write — gotcha #21).
        _apply_settled_crown(competitors, status)

        # --- Fun props (Item 1d): census the WC prop markets, publish what exists -
        props = build_props_list(all_wc_markets)

        sections = []
        if competitors:
            alive_n = sum(1 for c in competitors if not c["eliminated"]["out"])
            sections.append(
                {
                    "type": "winner_field",
                    "label": "Winner",
                    "market_ids": [winner_market.id],
                    "total": len(competitors),
                    "still_alive": alive_n,
                }
            )
        match_ids = [c["event_id"] for c in children]
        if match_ids:
            sections.append(
                {
                    "type": "matches",
                    "label": "Matches",
                    "event_ids": match_ids,
                    "total": len(children),
                }
            )
        if props:
            sections.append(
                {
                    "type": "props",
                    "label": "Props",
                    "market_ids": [p["market_id"] for p in props],
                    "total": len(props),
                }
            )

        return {
            "event": {
                "key": f"event:soccer:{cfg.slug}",
                "slug": cfg.slug,
                "domain": "soccer",
                "name": cfg.display,
                "status": status,
                "start_date": None,
                "end_date": None,
                "venue": None,
                "location": None,
                "is_major": True,  # the World Cup is the marquee sporting event on earth
                "as_of": as_of.isoformat() if as_of is not None else None,
            },
            "primary": {
                "kind": "winner_field",
                "label": "Winner",
                "competitors": competitors,
                "evolution_market_id": (
                    winner_market.id if winner_market is not None else None
                ),
            },
            "sections": sections,
            "children": children,
            "props": props,
            "props_script": [],
            "movers": [],
        }
