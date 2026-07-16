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
    _completed_result,
    _is_real_winner_outcome,
    _match_is_real,
    _norm,
    _select_winner_field,
    build_props_list,
    build_team_lookup,
    compute_nation_elimination,
    derive_soccer_concept,
    is_wc_prop_market,
    is_wc_winner_field_market,
    parse_soccer_slug,
)
from app.utils.nation_flags import flag_url, is_nation, nation_iso


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

    def test_other_code_world_cups_excluded(self):
        # L2-130 live-envelope forensic (2026-07-15): "Esports World Cup Chess Finals
        # Winner" (mis-tagged llm_sport_category="soccer") is a LIVE, freshly-polled,
        # coherent field, so before this guard it BEAT the real FIFA field on freshness
        # and crowned a chess grandmaster the "World Cup" favorite. Other-code World
        # Cups + non-team (continent) fields must never occupy the trophy slot.
        assert not is_wc_winner_field_market("Esports World Cup Chess Finals Winner")
        assert not is_wc_winner_field_market("Chess World Cup Winner")
        assert not is_wc_winner_field_market("Rugby World Cup Winner")
        assert not is_wc_winner_field_market("Cricket World Cup Winner")
        assert not is_wc_winner_field_market("Netball World Cup Winner")
        assert not is_wc_winner_field_market("Hockey World Cup Winner")
        assert not is_wc_winner_field_market("Continent to Win the Men's World Cup")
        assert not is_wc_winner_field_market("Which continent will win the World Cup?")
        assert not is_wc_winner_field_market("Women's World Cup Winner")
        assert not is_wc_winner_field_market("U-20 World Cup Winner")
        # ...but the real men's FIFA trophy fields still surface:
        assert is_wc_winner_field_market("FIFA World Cup Winner")
        assert is_wc_winner_field_market("2026 Men's World Cup Winner")

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


def _odds_field(ts):
    # A coherent, honest winner field (sums ~1.0, real spread).
    return [
        _mk_outcome("Spain", 0.54, ts),
        _mk_outcome("England", 0.22, ts),
        _mk_outcome("Argentina", 0.18, ts),
        _mk_outcome("France", 0.06, ts),
    ]


def _kalshi_field(ts):
    return [
        _mk_outcome("Spain", 0.30, ts),
        _mk_outcome("France", 0.28, ts),
        _mk_outcome("Brazil", 0.22, ts),
        _mk_outcome("England", 0.20, ts),
    ]


class TestSelectWinnerField:
    def test_freshest_coherent_field_wins(self):
        now = datetime.now(timezone.utc)
        stale = now - timedelta(days=30)
        kalshi = _mk_market(297, "kalshi", _kalshi_field(stale))  # coherent but stale
        odds = _mk_market(10, "odds_api", _odds_field(now))       # coherent + fresh → wins
        poly = _mk_market(
            112892, "polymarket",
            [_mk_outcome("Team AM", 0.08, now), _mk_outcome("Team AI", 0.08, now)],
        )
        market, real = _select_winner_field([kalshi, poly, odds])
        assert market is not None and market.id == 10
        assert {o.name for o in real} == {"Spain", "England", "Argentina", "France"}

    def test_coherent_stale_wins_when_only_option(self):
        # Kalshi (coherent, stale) is a valid fallback if odds_api is absent.
        stale = datetime.now(timezone.utc) - timedelta(days=30)
        kalshi = _mk_market(297, "kalshi", _kalshi_field(stale))
        market, _ = _select_winner_field([kalshi])
        assert market is not None and market.id == 297

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

    def test_incoherent_broken_field_rejected_over_coherent_stale(self):
        # The real "Peru 47%" bug: Polymarket's field is mostly stale ZEROS with a
        # live-polled handful — real prices sum to ~0.17 (mass missing), so a
        # hair-ahead Peru would normalize to a nonsense favorite. It must be REJECTED
        # (incoherent) even though it is fresher than the coherent odds_api field.
        now = datetime.now(timezone.utc)
        older = now - timedelta(hours=3)
        poly_broken = _mk_market(
            112892, "polymarket",
            [
                _mk_outcome("Team AM", 0.082, now),  # placeholder → filtered
                _mk_outcome("Peru", 0.082, now),      # fresh, but nonsense favorite
                _mk_outcome("Spain", 0.048, now),
                _mk_outcome("England", 0.019, now),
                _mk_outcome("Germany", 0.0, now),     # stale zeros — mass is missing
                _mk_outcome("Italy", 0.0, now),
                _mk_outcome("USA", 0.0, now),
            ],  # real sum ≈ 0.149 → incoherent
        )
        odds = _mk_market(10, "odds_api", _odds_field(older))  # coherent
        market, real = _select_winner_field([poly_broken, odds])
        assert market is not None and market.id == 10
        assert "Peru" not in {o.name for o in real}

    def test_all_incoherent_yields_nothing(self):
        # If the ONLY field is broken/incoherent, show no winner field (duels-only) —
        # never a fabricated favorite.
        now = datetime.now(timezone.utc)
        poly_broken = _mk_market(
            112892, "polymarket",
            [
                _mk_outcome("Peru", 0.082, now),
                _mk_outcome("Spain", 0.048, now),
                _mk_outcome("Germany", 0.0, now),
                _mk_outcome("Italy", 0.0, now),
            ],  # sum ≈ 0.13
        )
        market, real = _select_winner_field([poly_broken])
        assert market is None and real == []


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


# ---------------------------------------------------------------------------
# #208 Item 1a/1b: match join + elimination grading.
# ---------------------------------------------------------------------------


def _mk_match(mid, home, away, hs, as_, status, dt):
    return SimpleNamespace(
        id=mid,
        home_team_name=home,
        away_team_name=away,
        home_score=hs,
        away_score=as_,
        status=status,
        commence_time=dt,
    )


class TestMatchIsReal:
    def test_live_and_scheduled_always_real(self):
        t = datetime.now(timezone.utc)
        assert _match_is_real(_mk_match(1, "Spain", "Argentina", None, None, "scheduled", t))
        assert _match_is_real(_mk_match(2, "Mexico", "USA", None, None, "live", t))

    def test_completed_needs_scores(self):
        t = datetime.now(timezone.utc)
        assert _match_is_real(_mk_match(3, "France", "Spain", 0, 2, "completed", t))
        # phantom closed row with NULL scores (the "Panama vs England" / mis-linked
        # NHL rows) is dropped
        assert not _match_is_real(_mk_match(4, "Panama", "England", None, None, "closed", t))
        assert not _match_is_real(
            _mk_match(5, "Avalanche", "Trail Blazers", None, None, "closed", t)
        )


class TestNationElimination:
    def _bracket(self):
        # The real 2026 semifinal week: France & England LOST their semis, Spain &
        # Argentina WON theirs and meet in the final.
        d = lambda day: datetime(2026, 7, day, 19, tzinfo=timezone.utc)
        return [
            _mk_match(101, "France", "Morocco", 2, 0, "completed", d(9)),   # France won QF
            _mk_match(102, "France", "Spain", 0, 2, "completed", d(14)),    # France lost SF
            _mk_match(103, "England", "Argentina", 1, 2, "completed", d(15)),  # Eng lost SF
            _mk_match(104, "Portugal", "Spain", 0, 1, "completed", d(6)),   # Spain won
            _mk_match(105, "Spain", "France", 2, 0, "completed", d(14)),    # Spain won SF
            _mk_match(106, "Argentina", "England", 2, 1, "completed", d(15)),  # Arg won SF
            _mk_match(107, "Spain", "Argentina", None, None, "scheduled", d(19)),  # FINAL
        ]

    def test_beaten_semifinalists_eliminated(self):
        elim = compute_nation_elimination(self._bracket())
        assert elim[_norm("France")]["eliminated"] is True
        assert elim[_norm("England")]["eliminated"] is True

    def test_finalists_alive(self):
        elim = compute_nation_elimination(self._bracket())
        assert elim[_norm("Spain")]["eliminated"] is False
        assert elim[_norm("Argentina")]["eliminated"] is False

    def test_eliminated_by_evidence(self):
        elim = compute_nation_elimination(self._bracket())
        by = elim[_norm("France")]["eliminated_by"]
        assert by is not None
        assert _norm(by["opponent"]) == _norm("Spain")
        assert by["score"] == "0-2"  # from France's perspective
        assert by["event_id"] == 102

    def test_win_then_no_loss_is_alive(self):
        # A nation whose most recent completed match was a win is never eliminated.
        d = lambda day: datetime(2026, 7, day, tzinfo=timezone.utc)
        games = [
            _mk_match(1, "Spain", "Portugal", 1, 0, "completed", d(6)),
            _mk_match(2, "Spain", "France", 2, 0, "completed", d(14)),
        ]
        assert compute_nation_elimination(games)[_norm("Spain")]["eliminated"] is False

    def test_completed_result_perspective(self):
        d = datetime(2026, 7, 14, tzinfo=timezone.utc)
        m = _mk_match(1, "France", "Spain", 0, 2, "completed", d)
        assert _completed_result(m, _norm("France")) == "loss"
        assert _completed_result(m, _norm("Spain")) == "win"
        assert _completed_result(m, _norm("Brazil")) is None  # didn't play


# ---------------------------------------------------------------------------
# #208 Item 1c: nation flags (clubs untouched).
# ---------------------------------------------------------------------------


class TestNationFlags:
    def test_known_nations_resolve(self):
        assert nation_iso("Spain") == "es"
        assert nation_iso("Argentina") == "ar"
        assert flag_url("Spain") == "https://flagcdn.com/w160/es.png"

    def test_uk_home_nations_use_subdivision_codes(self):
        assert nation_iso("England") == "gb-eng"
        assert nation_iso("Scotland") == "gb-sct"
        assert nation_iso("Wales") == "gb-wls"

    def test_diacritics_and_alternates(self):
        assert nation_iso("Côte d'Ivoire") == "ci"
        assert nation_iso("Ivory Coast") == "ci"
        assert nation_iso("Türkiye") == "tr"
        assert nation_iso("USA") == "us"
        assert nation_iso("United States") == "us"

    def test_clubs_untouched(self):
        # The whole safety of a curated map: a club NEVER gets a flag.
        for club in ("Real Madrid", "Boca Juniors", "Manchester United", "PSG"):
            assert nation_iso(club) is None
            assert flag_url(club) is None
            assert is_nation(club) is False

    def test_is_nation(self):
        assert is_nation("Brazil") is True
        assert is_nation(None) is False


# ---------------------------------------------------------------------------
# #208 Item 1d: fun props census.
# ---------------------------------------------------------------------------


class TestWcPropMarket:
    def test_fun_props_qualify(self):
        assert is_wc_prop_market("World Cup Final Halftime Show: Songs")
        assert is_wc_prop_market("FIFA World Cup: Total Goals")
        assert is_wc_prop_market("World Cup: Longest Penalty Shootout")
        assert is_wc_prop_market("World Cup: Third-Place Finisher")

    def test_winner_field_is_not_a_prop(self):
        assert not is_wc_prop_market("FIFA World Cup Winner")
        assert not is_wc_prop_market("2026 Men's World Cup Winner")

    def test_qualifier_ladders_and_other_code_excluded(self):
        assert not is_wc_prop_market("World Cup Round of 16 Qualifiers")
        assert not is_wc_prop_market("FIFA World Cup Semifinals Qualifiers")
        assert not is_wc_prop_market("Esports World Cup Chess Finals Winner")
        assert not is_wc_prop_market("Women's T20 World Cup Final: Australia vs England")

    def test_build_props_list_ranks_and_shapes(self):
        m1 = SimpleNamespace(
            id=1, source="kalshi", name="World Cup: Total Goals",
            outcomes=[_mk_outcome("Over 150", 0.6, None), _mk_outcome("Under 150", 0.4, None)],
            volume_24h=100.0, volume=500.0, resolution_date=None,
        )
        m2 = SimpleNamespace(
            id=2, source="kalshi", name="World Cup Final Halftime Show: Songs",
            outcomes=[_mk_outcome("Song A", 0.3, None)],
            volume_24h=999.0, volume=10.0, resolution_date=None,
        )
        winner = SimpleNamespace(
            id=3, source="odds_api", name="FIFA World Cup Winner",
            outcomes=[_mk_outcome("Spain", 0.5, None)],
            volume_24h=5000.0, volume=5000.0, resolution_date=None,
        )
        props = build_props_list([m1, m2, winner])
        ids = [p["market_id"] for p in props]
        assert 3 not in ids  # winner field excluded
        assert ids[0] == 2  # higher volume_24h ranks first
        assert props[0]["top_outcomes"][0]["name"] == "Song A"
