"""Guard for the settled-page FOREIGN-PROPS defense-in-depth filter (#209 Item 2).

A matching-pass gap linked foreign-game Kalshi markets to the wrong event
(exhibit: Iowa-Wisconsin's page also carried `-26FEB23AMCCSELA`/`-26FEB23HCUETAM`
moneylines; a teamless CS2 event became a dump for dozens of unrelated
`KXCS2MAP-…` markets). The game-markets endpoint now keeps only the markets whose
ticker game-id matches the event's game. These tests pin the pure helpers so the
filter never (a) drops the true game or (b) empties a page on ambiguity.
"""
from datetime import date

from app.utils.prediction_market_matching import (
    kalshi_game_id,
    kalshi_game_teams,
    filter_foreign_game_markets,
)


class _M:
    """Minimal market stub exposing external_id + an id for identity."""

    def __init__(self, external_id, mid=None):
        self.external_id = external_id
        self.id = mid if mid is not None else external_id


def test_kalshi_game_id_extraction():
    assert kalshi_game_id("KXNCAAMBGAME-26FEB22IOWAWIS") == "26FEB22IOWAWIS"
    assert kalshi_game_id("KXNCAAMBSPREAD-26FEB22IOWAWIS") == "26FEB22IOWAWIS"
    assert kalshi_game_id("KXCS2MAP-26FEB24OMEACE-1") == "26FEB24OMEACE"
    # MLB doubleheader ticker with an HHMM segment stays a single game-id.
    assert kalshi_game_id("KXMLBGAME-26APR291840COLCIN") == "26APR291840COLCIN"
    assert kalshi_game_id(None) is None
    assert kalshi_game_id("SOME-POLYMARKET-SLUG") is None


def test_kalshi_game_teams_strips_date():
    assert kalshi_game_teams("KXNCAAMBGAME-26FEB22IOWAWIS") == "IOWAWIS"
    assert kalshi_game_teams("KXNBAMENTION-26FEB20BOSGSW") == "BOSGSW"
    assert kalshi_game_teams("KXMLBGAME-26APR291840COLCIN") == "COLCIN"
    assert kalshi_game_teams(None) is None


def test_keeps_same_matchup_shifted_date_market():
    """A same-teams market with a +1-day (resolution-date) ticker — e.g.
    KXNBAMENTION — must NOT be treated as foreign."""
    real = [_M("KXNBAGAME-26FEB19BOSGSW", "r1"),
            _M("KXNBASPREAD-26FEB19BOSGSW", "r2")]
    mention = _M("KXNBAMENTION-26FEB20BOSGSW", "mention")
    kept = filter_foreign_game_markets(real + [mention], date(2026, 2, 19))
    assert {m.id for m in kept} == {"r1", "r2", "mention"}


def test_drops_foreign_game_keeps_true_game():
    """The exhibit: 7 real IOWAWIS markets + 2 foreign next-day moneylines."""
    real = [_M(f"KXNCAAMB{t}-26FEB22IOWAWIS", f"r{i}")
            for i, t in enumerate(("GAME", "SPREAD", "TOTAL", "1HWINNER"))]
    foreign = [_M("KXNCAAMBGAME-26FEB23AMCCSELA", "f1"),
               _M("KXNCAAMBGAME-26FEB23HCUETAM", "f2")]
    kept = filter_foreign_game_markets(real + foreign, date(2026, 2, 22))
    kept_ids = {m.id for m in kept}
    assert kept_ids == {m.id for m in real}
    assert "f1" not in kept_ids and "f2" not in kept_ids


def test_single_game_unchanged():
    """No foreign markets → the list is returned untouched."""
    real = [_M("KXNBAGAME-26FEB19BOSGSW"), _M("KXNBASPREAD-26FEB19BOSGSW")]
    kept = filter_foreign_game_markets(real, date(2026, 2, 19))
    assert kept == real


def test_polymarket_and_undated_always_kept():
    """Markets without a parseable game-id ride through even amid a mix."""
    poly = _M("polymarket-celtics-76ers-ou", "p1")
    real = _M("KXNBAGAME-26FEB19BOSGSW", "r1")
    foreign = _M("KXNBAGAME-26FEB20INDWAS", "f1")
    kept = filter_foreign_game_markets([poly, real, foreign], date(2026, 2, 19))
    kept_ids = {m.id for m in kept}
    assert "p1" in kept_ids       # undated poly kept
    assert "r1" in kept_ids       # true game kept
    assert "f1" not in kept_ids   # foreign next-day game dropped


def test_fail_open_when_no_gid_matches_event_date():
    """Timezone roll: neither game-id's date matches → keep everything, never
    empty the page."""
    a = _M("KXNBAGAME-26FEB19BOSGSW", "a")
    b = _M("KXNBAGAME-26FEB20INDWAS", "b")
    kept = filter_foreign_game_markets([a, b], date(2026, 1, 1))
    assert {m.id for m in kept} == {"a", "b"}


def test_missing_event_date_is_noop():
    markets = [_M("KXNBAGAME-26FEB19BOSGSW"), _M("KXNBAGAME-26FEB20INDWAS")]
    assert filter_foreign_game_markets(markets, None) is markets
