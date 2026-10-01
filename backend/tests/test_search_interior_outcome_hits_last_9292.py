"""#9292 — an option-only board whose option holds the query only mid-word yields.

`bainluck.com/search?q=hawks` (production 2026-09-28 04:4xZ) served the NFL
champion board as futures row 2, above the NBA champion board, because its
option "Seattle Seahawks" holds `hawks` mid-word and its volume is higher; the
Atlanta Hawks sit on the NBA board. `nets` (Alabama St Hornets), `rays`
(Grayson Rodriguez) and `mets` (Demon Slayer: Kimetsu no Yaiba) are the same
shape. Fixture ids, stored names, volumes and option names are the production
rows read the same hour.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.routes import events as events_route

STAMP = datetime.now(timezone.utc) - timedelta(hours=5)


class _Outcome:
    def __init__(self, id, name, p):
        self.id = id
        self.name = name
        self.current_probability = p
        self.last_updated = STAMP


class _Market:
    def __init__(self, id, name, volume, options, category="basketball", market_tier=1):
        self.id = id
        self.source = "polymarket"
        self.name = name
        self.market_tier = market_tier
        self.volume = volume
        # Contested legs (0.30 each + a filler), so #8726's decided-board
        # partition never fires here.
        self.outcomes = [
            _Outcome(id * 10 + i, n, 0.30) for i, n in enumerate(options)
        ] + [_Outcome(id * 10 + 9, "Field", 0.10)]
        self.canonical_market_key = None
        self.external_id = None
        self.llm_sport_category = category
        self.sport = None


def _ids(rows):
    return [m.id for m in rows]


def _rank(rows, query):
    return events_route._rerank_search_futures(rows, query)


def _hawks_rows():
    return [
        _Market(129037, "Pro Football: 2027 Champion", 61350993,
                ["Seattle Seahawks", "Buffalo Bills"], category="football"),
        _Market(20569230, "NBA: 2027 Champion", 22589879,
                ["Atlanta Hawks", "Oklahoma City Thunder"]),
        _Market(35961638, "NHL: 2027 Champion", 806106,
                ["Chicago Blackhawks", "Florida Panthers"], category="hockey"),
        _Market(11371619, "Japan NPB Champion", 23363,
                ["Fukuoka SoftBank Hawks", "Hanshin Tigers"], category="baseball"),
    ]


HAWKS = [("hawks", None)]


def test_precondition_the_volume_sort_alone_reproduces_the_production_page():
    by_volume = sorted(_hawks_rows(), key=events_route._market_volume, reverse=True)
    assert _ids(by_volume)[:2] == [129037, 20569230]
    for m in _hawks_rows():
        assert not events_route._query_name_match(m, HAWKS)


def test_hawks_puts_the_seahawks_and_blackhawks_boards_below_the_hawks_boards():
    assert _ids(_rank(_hawks_rows(), HAWKS)) == [
        20569230, 11371619, 129037, 35961638,
    ]


def test_nets_puts_the_hornets_board_below_the_brooklyn_nets_board():
    rows = [
        _Market(3, "NCAAB Championship Winner", 5_000_000,
                ["Alabama St Hornets", "Duke Blue Devils"]),
        _Market(60087209, "NBA Playoffs: Team to advance to Eastern Conference Semifinals",
                3400, ["Brooklyn Nets", "Boston Celtics"], market_tier=2),
    ]
    assert _ids(_rank(rows, [("nets", None)])) == [60087209, 3]


def test_mets_puts_the_animated_film_award_below_the_mets_boards():
    rows = [
        _Market(110753, "PGA Award for Best Animated Theatrical Motion Picture?", 900_000,
                ["KPop Demon Hunters", "Demon Slayer: Kimetsu no Yaiba Infinity Castle"],
                category="entertainment", market_tier=3),
        _Market(13689767, "MLB: Team to win 100+ games", 325463,
                ["New York Mets", "Los Angeles Dodgers"], category="baseball",
                market_tier=5),
    ]
    assert _ids(_rank(rows, [("mets", None)])) == [13689767, 110753]


def test_a_name_match_still_leads_every_option_only_row():
    rows = _hawks_rows() + [
        _Market(1, "Will the Atlanta Hawks make the playoffs?", 10, ["Yes", "No"]),
    ]
    assert _ids(_rank(rows, HAWKS))[0] == 1


def test_nets_sinks_the_hornets_board_below_the_nets_conference_boards_too():
    # The Hornets board is full-scope but not about the Nets at all, so it sinks
    # below the Nets' "Eastern Conference" board. #9996: that board names the
    # club, and no full-scope row's NAME holds `nets`, so `_demote_narrower_scope`
    # no longer sinks it below the Champion board either. On the served page the
    # headline lane hoists the Champion (tier 1, a real Nets contender) back to
    # row 0; this is the re-rank alone.
    rows = [
        _Market(20569230, "NBA: 2027 Champion", 22589879, ["Brooklyn Nets", "Boston Celtics"]),
        _Market(3, "NCAAB Championship Winner", 5_000_000,
                ["Alabama St Hornets", "Duke Blue Devils"]),
        _Market(61380772, "Will Brooklyn Nets advance to the Eastern Conference "
                "Semifinals in the 2027 NBA Playoffs?", None, ["Yes", "No"], market_tier=2),
    ]
    assert _ids(_rank(rows, [("nets", None)])) == [61380772, 20569230, 3]


def test_a_name_match_is_never_flagged_by_its_options():
    rows = [
        _Market(1, "Hawks vs Seahawks trivia night", 10, ["Seahawks fan wins", "Other"]),
        _Market(2, "NBA: 2027 Champion", 9000, ["Atlanta Hawks", "Other"]),
    ]
    assert _ids(_rank(rows, HAWKS)) == [1, 2]


def test_a_word_prefix_counts_as_a_word_start():
    # `yank` is someone still typing "Yankees" (#7381's rule), not a mid-word hit.
    rows = [
        _Market(1, "Big board", 9000, ["Tom Brodyankowski", "Other"], category="football"),
        _Market(2, "MLB: 2026 American League Champion", 10,
                ["New York Yankees", "Tampa Bay Rays"], category="baseball"),
    ]
    assert _ids(_rank(rows, [("yank", None)])) == [2, 1]


def test_an_expansion_at_a_word_start_counts():
    rows = [
        _Market(1, "Big board", 9000, ["Sampatsy", "Other"]),
        _Market(2, "Small board", 10, ["New England Patriots", "Other"], category="football"),
    ]
    assert _ids(_rank(rows, [("pats", "patriots")])) == [2, 1]


@pytest.mark.parametrize(
    "query, rows",
    [
        # Every option hit is mid-word: nothing to prefer, volume order stands.
        (
            [("9ers", None)],
            [(1, "Pro Football: 2027 Champion", 9000, ["San Francisco 49ers"]),
             (2, "NFC Champion", 10, ["San Francisco 49ers"])],
        ),
        # Every option hit starts a word.
        (
            [("hawks", None)],
            [(1, "NBA: 2027 Champion", 9000, ["Atlanta Hawks"]),
             (2, "Japan NPB Champion", 10, ["Fukuoka SoftBank Hawks"])],
        ),
        # A mid-word row beside a row reached by another arm (no option holds
        # the term, as a league-ticker or alias hit): neither kind is "word
        # start", so the rule has nothing to prefer and does not fire.
        (
            [("hawks", None)],
            [(1, "Pro Football: 2027 Champion", 9000, ["Seattle Seahawks"]),
             (2, "MVP Winner?", 10, ["Some Player"])],
        ),
    ],
)
def test_untouched_when_there_is_nothing_to_prefer(query, rows):
    markets = [_Market(i, n, v, opts) for i, n, v, opts in rows]
    assert _ids(_rank(markets, query)) == [m[0] for m in rows]


def test_a_multi_word_query_needs_every_term_in_one_option():
    # "red sox": the Boston option holds both terms at word starts; the other
    # board holds them only mid-word, in one option ("Shredded Soxhlet").
    rows = [
        _Market(1, "Big board", 9000, ["Shredded Soxhlet", "Other"]),
        _Market(2, "MLB World Series Champion 2026", 10,
                ["Boston Red Sox", "Other"], category="baseball"),
    ]
    assert _ids(_rank(rows, [("red", None), ("sox", None)])) == [2, 1]


def test_every_term_must_start_a_word_not_just_the_first():
    # "Red Ubersox": `red` starts a word, `sox` does not — still a mid-word hit.
    rows = [
        _Market(1, "Big board", 9000, ["Red Ubersox", "Other"]),
        _Market(2, "MLB World Series Champion 2026", 10,
                ["Boston Red Sox", "Other"], category="baseball"),
    ]
    assert _ids(_rank(rows, [("red", None), ("sox", None)])) == [2, 1]


def test_a_row_reached_by_another_arm_keeps_its_place():
    # A league-ticker/alias row holds no option with the term, so it is not a
    # mid-word hit and stays above the Seahawks board on a page that has an answer.
    rows = [
        _Market(1, "MVP Winner?", 9000, ["Some Player", "Other"]),
        _Market(20569230, "NBA: 2027 Champion", 10, ["Atlanta Hawks", "Other"]),
        _Market(129037, "Pro Football: 2027 Champion", 5, ["Seattle Seahawks", "Other"],
                category="football"),
    ]
    assert _ids(_rank(rows, HAWKS)) == [1, 20569230, 129037]


def test_helper_is_a_stable_partition_that_drops_nothing():
    rows = _hawks_rows()
    out = events_route._interior_outcome_hits_last(rows, [("hawks", "")])
    assert sorted(_ids(out)) == sorted(_ids(rows))
    assert _ids(out) == [20569230, 11371619, 129037, 35961638]
