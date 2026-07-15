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
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

# Raw price at/above which a SETTLED winner-field team is the crowned champion during
# the is_winner grading-lag window (parity with awards/election/tennis — display only).
_WON_PRICE_THRESHOLD = 0.97

# How far back a completed game still shows as a RESULT duel (settled-means-settled,
# but the final week's just-played games are the story). Live + scheduled always show.
_RESULT_LOOKBACK_DAYS = 4

# Winner-field competitor cap (the trophy field is ~48 nations; the UI renders the
# contenders — the rest are eliminated/null-priced and filtered out anyway).
_COMPETITOR_CAP = 48
_DUEL_CAP = 32


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
        cutoff = now - timedelta(days=_RESULT_LOOKBACK_DAYS)
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
                Event.commence_time >= cutoff,
            )
            .order_by(Event.commence_time)
        )
        games = list((await db.execute(game_q)).scalars().unique().all())

        # --- Winner field (trophy) from futures ----------------------------------
        win_q = (
            select(FuturesMarket)
            .options(selectinload(FuturesMarket.outcomes))
            .where(
                FuturesMarket.status == "open",
                FuturesMarket.name.ilike("%world cup%"),
            )
        )
        candidate_markets = [
            m
            for m in (await db.execute(win_q)).scalars().unique().all()
            if is_wc_winner_field_market(m.name)
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
                team = team_lut.get(_norm(o.name))
                competitors.append(
                    {
                        "name": (team.name if team is not None else o.name),
                        "probability": (
                            round(float(o.current_probability), 4)
                            if o.current_probability is not None
                            else None
                        ),
                        "won": bool(getattr(o, "is_winner", False)),
                        "team": _team_ref(team),
                    }
                )
            normalize_display_probs(
                competitors, mutually_exclusive=bool(winner_market.mutually_exclusive)
            )
            competitors.sort(key=lambda c: (c["probability"] or -1), reverse=True)
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
        for g in sorted(games, key=_game_rank)[:_DUEL_CAP]:
            st = (g.status or "").lower()
            settled = st in ("completed", "closed")
            if st == "live":
                any_live = True
            if st in ("live", "scheduled"):
                upcoming_or_live += 1
            home_prob = compute_aggregate_probability(g, g.status)
            home_name = getattr(g, "home_team_name", None)
            away_name = getattr(g, "away_team_name", None)
            home_team = getattr(g, "home_team", None) or team_lut.get(_norm(home_name))
            away_team = getattr(g, "away_team", None) or team_lut.get(_norm(away_name))
            outcomes = []
            if home_prob is not None:
                outcomes = [
                    {"name": home_name, "probability": round(float(home_prob), 4)},
                    {"name": away_name, "probability": round(1 - float(home_prob), 4)},
                ]
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
                    "home": {
                        **({} if home_team is None else _team_ref(home_team)),
                        "name": home_name,
                        "probability": (
                            round(float(home_prob), 4) if home_prob is not None else None
                        ),
                        "score": getattr(g, "home_score", None),
                    },
                    "away": {
                        **({} if away_team is None else _team_ref(away_team)),
                        "name": away_name,
                        "probability": (
                            round(1 - float(home_prob), 4)
                            if home_prob is not None
                            else None
                        ),
                        "score": getattr(g, "away_score", None),
                    },
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

        # Crown a price-settled champion during the grading-lag window (display-only).
        if status == "settled" and competitors and not any(c["won"] for c in competitors):
            top = competitors[0]
            if (top.get("probability") or 0) >= _WON_PRICE_THRESHOLD:
                top["won"] = True

        sections = []
        if competitors:
            sections.append(
                {
                    "type": "winner_field",
                    "label": "Winner",
                    "market_ids": [winner_market.id],
                    "total": len(competitors),
                }
            )
        match_ids = [c["event_id"] for c in children]
        if match_ids:
            sections.append(
                {
                    "type": "matches",
                    "label": "Matches",
                    "event_ids": match_ids,
                    "total": len(games),
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
            "props_script": [],
            "movers": [],
        }
