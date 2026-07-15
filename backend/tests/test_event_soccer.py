"""#205 (World Cup Emergency Assembly): soccer tournament adapter pure helpers.

Proves the "config drop" grammar over the real World Cup market/name shapes verified
live 2026-07-15 (odds_api "FIFA World Cup Winner" fresh, Kalshi "KXMENWORLDCUP-26"
staler, Polymarket "World Cup Winner" anonymized "Team AM" placeholders). The
adapter's async build_event is exercised end-to-end against production after deploy
(the live-proof gate); these unit tests lock the pure selection/linkage logic that
decides which winner field wins and how entities resolve."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.utils.event_soccer import (
    SOCCER_TOURNAMENTS,
    _is_real_winner_outcome,
    _select_winner_field,
    build_team_lookup,
    derive_soccer_concept,
    is_wc_winner_field_market,
    parse_soccer_slug,
)


class TestParseSoccerSlug:
    def test_canonical(self):
        cfg = parse_soccer_slug("world-cup-2026")
        assert cfg is not None and cfg.slug == "world-cup-2026"
        assert cfg.edition == 2026
        assert cfg.sport_key == "soccer_fifa_world_cup"

    def test_aliases_resolve(self):
        assert parse_soccer_slug("world-cup").slug == "world-cup-2026"
        assert parse_soccer_slug("fifa-world-cup").slug == "world-cup-2026"
        assert parse_soccer_slug("world-cup-final").slug == "world-cup-2026"
        assert parse_soccer_slug("2026").slug == "world-cup-2026"
        assert parse_soccer_slug("WORLD-CUP").slug == "world-cup-2026"  # case-insensitive

    def test_unknown_is_none(self):
        assert parse_soccer_slug("euro-2028") is None
        assert parse_soccer_slug("") is None


class TestIsWcWinnerFieldMarket:
    def test_trophy_winner_fields(self):
        assert is_wc_winner_field_market("World Cup Winner ")
        assert is_wc_winner_field_market("FIFA World Cup Winner")
        assert is_wc_winner_field_market("2026 Men's World Cup Winner")

    def test_non_trophy_markets_excluded(self):
        # Awards / group / novelty markets share the "world cup" name but are NOT the
        # overall trophy field — they must not derive the concept.
        assert not is_wc_winner_field_market("World Cup: Golden Boot Winner")
        assert not is_wc_winner_field_market("World Cup: Golden Glove Winner")
        assert not is_wc_winner_field_market("World Cup: Golden Ball Winner")
        assert not is_wc_winner_field_market("World Cup Group C Winner")
        assert not is_wc_winner_field_market("World Cup: First Time Winner")
        assert not is_wc_winner_field_market("World Cup Winner to Never Trail in a Match")
        assert not is_wc_winner_field_market("World Cup: Unbeaten Champion?")
        assert not is_wc_winner_field_market("Group to Win the World Cup")
        assert not is_wc_winner_field_market("T20 World Cup Final: India vs New Zealand")
        assert not is_wc_winner_field_market("Who will host the 2029 Men's FIFA Club World Cup?")

    def test_needs_winner_word(self):
        assert not is_wc_winner_field_market("World Cup halftime show performer")
        assert not is_wc_winner_field_market("Random market")
        assert not is_wc_winner_field_market(None)


class TestDeriveSoccerConcept:
    def test_trophy_market_surfaces_concept(self):
        c = derive_soccer_concept("KXMENWORLDCUP-26", "2026 Men's World Cup Winner", "soccer")
        assert c is not None
        assert c["key"] == "event:soccer:world-cup-2026"
        assert c["domain"] == "soccer"
        assert c["name"] == "2026 FIFA World Cup"

    def test_odds_api_and_poly_shapes(self):
        assert derive_soccer_concept("soccer_fifa_world_cup_winner", "FIFA World Cup Winner", "soccer")
        assert derive_soccer_concept("30615", "World Cup Winner ", "soccer")

    def test_award_market_is_none(self):
        assert derive_soccer_concept("x", "World Cup: Golden Boot Winner", "soccer") is None
        assert derive_soccer_concept("x", "World Cup Group C Winner", "soccer") is None

    def test_wrong_category_is_none(self):
        # A cricket/other market that happens to say "world cup winner" but is tagged a
        # non-soccer category must not surface the soccer concept.
        assert derive_soccer_concept("x", "World Cup Winner", "cricket") is None

    def test_none_is_safe(self):
        assert derive_soccer_concept(None, None, None) is None


class TestIsRealWinnerOutcome:
    def test_countries_are_real(self):
        assert _is_real_winner_outcome("France")
        assert _is_real_winner_outcome("Spain")
        assert _is_real_winner_outcome("Côte d'Ivoire")

    def test_anonymized_and_field_dropped(self):
        # Polymarket anonymized slots (the shared placeholder guard misses 2-letter).
        assert not _is_real_winner_outcome("Team AM")
        assert not _is_real_winner_outcome("Team AI")
        assert not _is_real_winner_outcome("Team A")
        assert not _is_real_winner_outcome("Other")
        assert not _is_real_winner_outcome("The Field")
        assert not _is_real_winner_outcome("")
        assert not _is_real_winner_outcome(None)


def _mk_outcome(name, prob, updated):
    return SimpleNamespace(
        name=name, current_probability=prob, last_updated=updated, is_winner=False
    )


def _mk_market(mid, source, outcomes):
    return SimpleNamespace(id=mid, source=source, mutually_exclusive=True, outcomes=outcomes)


class TestSelectWinnerField:
    def test_freshest_real_field_wins(self):
        now = datetime.now(timezone.utc)
        stale = now - timedelta(days=30)
        # Kalshi: real countries, but stale.
        kalshi = _mk_market(
            297, "kalshi",
            [_mk_outcome("Spain", 0.14, stale), _mk_outcome("France", 0.13, stale)],
        )
        # odds_api: real countries, fresh → should win.
        odds = _mk_market(
            10, "odds_api",
            [_mk_outcome("Spain", 0.54, now), _mk_outcome("England", 0.22, now)],
        )
        # Polymarket: anonymized placeholders, fresh but not real → must be skipped.
        poly = _mk_market(
            112892, "polymarket",
            [_mk_outcome("Team AM", 0.08, now), _mk_outcome("Team AI", 0.08, now)],
        )
        market, real = _select_winner_field([kalshi, poly, odds])
        assert market is not None and market.id == 10
        assert {o.name for o in real} == {"Spain", "England"}

    def test_poly_only_placeholders_yields_nothing(self):
        now = datetime.now(timezone.utc)
        poly = _mk_market(
            112892, "polymarket",
            [_mk_outcome("Team AM", 0.08, now), _mk_outcome("Team AI", 0.08, now)],
        )
        market, real = _select_winner_field([poly])
        assert market is None and real == []

    def test_null_priced_outcomes_excluded(self):
        now = datetime.now(timezone.utc)
        m = _mk_market(
            10, "odds_api",
            [_mk_outcome("Spain", 0.54, now), _mk_outcome("Ghana", None, now)],
        )
        market, real = _select_winner_field([m])
        # only Spain is priced → < 2 real priced → not selected
        assert market is None


class TestBuildTeamLookup:
    def test_name_abbrev_and_alt_names_resolve(self):
        france = SimpleNamespace(
            id=1, name="France", abbreviation="FRA",
            alternate_names=["Les Bleus", "Équipe de France"],
            slug="france", logo_url_small="fra.png", logo_url=None,
        )
        lut = build_team_lookup([france, None])
        assert lut.get("france") is france
        assert lut.get("fra") is france
        assert lut.get("les bleus") is france
        # diacritic-insensitive
        assert lut.get("equipe de france") is france

    def test_empty_is_empty(self):
        assert build_team_lookup([]) == {}


class TestConfig:
    def test_edition_is_four_digit(self):
        for cfg in SOCCER_TOURNAMENTS.values():
            assert 2020 <= cfg.edition <= 2100
            assert cfg.display and cfg.sport_key
