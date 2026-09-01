"""THE AUTHORITY NAMES THE PLAYERS (Q503, EVENT-GRAPH-DOCTRINE rules 1-3).

Measured on production 2026-09-01 ~15:20 PT, against the live US Open register
(version 12) and ESPN's tennis scoreboard:

* 96 of the register's 124 matchups carry an ESPN competition id pinned at the
  draw ceremony. **Four of those 96 name a pairing ESPN's own competition
  contradicts** — and in every one of the four, exactly one side is a player
  who is not in the tournament at all:

  | competition | we said                          | ESPN says                        |
  |-------------|----------------------------------|----------------------------------|
  | 182673      | Rublev vs **Cilic** (Final)      | Rublev vs Otto Virtanen          |
  | 182703      | Jodar vs **Kokkinakis** (7:05pm) | Bu Yunchaokete vs Jodar          |
  | 182710      | Cerundolo vs **Ruud** (3rd set)  | Arthur Gea vs Cerundolo          |
  | 182650      | Potapova vs **Valentova** (2nd)  | Darja Semenistaja vs Potapova    |

* The cause is one line in the register: each of those matchups was ``"pinned
  after the draw ingest, which recorded this source as missing because no match
  market existed at ceremony time"`` — i.e. **a Kalshi market's name became the
  pairing**.  Kalshi wrote ``Cerundolo vs Ruud`` before Ruud withdrew and never
  updated it; the ceremony census then anchored that pairing to the real
  competition.  Markets are supposed to ATTACH to a fixture, never to name one.

* What a reader saw: the top card of the schedule read **"Casper Ruud 60% /
  Juan Manuel Cerundolo 40% — 3rd Set"** while Cerundolo was on court against
  Arthur Gea.  The clock was ESPN's and correct.  The player was the market's
  and wrong.  A chimera: right match, right clock, wrong player.

The rule these tests pin: **where the scoreboard names the competitors, it is
the authority on who is playing**, and a fixture whose register pairing
contradicts it is withheld with a named reason — never rendered, and never
silently dropped.  Doctrine rule 1 chose this direction explicitly: an
unresolvable claim goes to a visible quarantine, never a phantom.

WHY WITHHELD RATHER THAN RE-NAMED: two of the four real players (Arthur Gea, Bu
Yunchaokete) entered after the ceremony and are absent from the register, so
there is no identity to render them with — and the market that priced the row
is a market for a match that is not being played, so its numbers may not be
carried onto the real pairing under a new name.  Rendering ESPN's pairing as a
first-class unpriced card is the next slice; it needs player identity from the
authority, which this one deliberately does not invent.

THE COMPARISON IS DELIBERATELY TOLERANT, because the cost of a false positive
is deleting a real match from the card — a worse defect than the one being
fixed.  Two names agree when one's tokens are all covered by the other's (a
prefix counts as cover) **and** they share one token of at least three
characters.  So ``Bu Yunchaokete``/``Yunchaokete Bu`` (word order), ``Juan
Manuel Cerundolo``/``Juan Cerundolo`` (dropped middle name) and ``J.J.
Wolf``/``JJ Wolf`` (initialism) all agree, while ``Francisco Cerundolo`` and
``Juan Manuel Cerundolo`` — both in this draw — do not.

The three-character anchor is not decoration: without it a one-letter token is
a WILDCARD under the prefix rule, and sweeping all 378 registered players found
it made ``Christopher O'Connell`` and ``Oleksandra Oliynykova`` agree.  That
sweep is itself a test here, because a looser rule has to survive every pair of
real players in a real draw and not just the ones a test author imagined.

Replayed over all 124 live matchups and ESPN's real 625-competition scoreboard,
this rule refuses exactly the four above — three on today's card, one already
decided — and keeps the other 120.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services.espn_tennis import parse_results
from app.utils.tournament_register import SCHEMA_VERSION
from app.utils.tournament_slate import _names_agree, build_slate, pairing_agrees

NOW = datetime(2026, 9, 1, 22, 0, tzinfo=timezone.utc)
SOON = (NOW + timedelta(hours=2)).isoformat()
COMP = "182710"


def _register(**overrides):
    register = {
        "schema_version": SCHEMA_VERSION,
        "tournament": "us-open",
        "season": "2026",
        "version": 12,
        "generated_at": NOW.isoformat(),
        "draw_released": True,
        "players": [
            {
                "entity_key": "juan-manuel-cerundolo",
                "display_name": "Juan Manuel Cerundolo",
                "draw": "mens-singles",
                "role": "participant",
                "seed": None,
                "country": "Argentina",
                "draw_slot": None,
                "section": None,
                "sources": [],
            },
            {
                "entity_key": "casper-ruud",
                "display_name": "Casper Ruud",
                "draw": "mens-singles",
                "role": "contender",
                "seed": None,
                "country": "Norway",
                "draw_slot": None,
                "section": None,
                "sources": [],
            },
        ],
        "matchups": [_matchup()],
    }
    register.update(overrides)
    return register


def _matchup(**overrides):
    matchup = {
        "matchup_key": "mens-singles:casper-ruud-vs-juan-manuel-cerundolo:2026-08-30",
        "draw": "mens-singles",
        "round": "R128",
        "scheduled_date": SOON,
        "players": ["juan-manuel-cerundolo", "casper-ruud"],
        # The ceremony anchor. Correct — it names the competition that really is
        # being played. It is the PAIRING that is wrong, which is why an
        # id-presence check cannot catch this class.
        "evidence": {
            "kind": "draw-ceremony-espn",
            "espn_competition_id": COMP,
            "espn_round": "Round 1",
            "observed_at": NOW.isoformat(),
        },
        "sources": [
            {
                "source": "kalshi",
                "kind": "match",
                "market_id": 59693744,
                "outcome_id": 900001,
                "status": "live",
                "terminal_result": None,
                "evidence": {
                    "kind": "kalshi-match-market-census",
                    "observed_at": NOW.isoformat(),
                    "market_name": "Cerundolo vs Ruud",
                },
                "sides": {
                    "juan-manuel-cerundolo": {
                        "outcome_id": 900001,
                        "source_label": "Juan Manuel Cerundolo",
                    },
                    "casper-ruud": {
                        "outcome_id": 900002,
                        "source_label": "Casper Ruud",
                    },
                },
            }
        ],
    }
    matchup.update(overrides)
    return matchup


def _prices():
    at = NOW - timedelta(minutes=10)
    return {
        900001: {"probability": 0.4, "opening_probability": 0.32, "observed_at": at},
        900002: {"probability": 0.6, "opening_probability": 0.68, "observed_at": at},
    }


def _listed(players, comp_id=COMP, state="in_progress", **overrides):
    entry = {
        "espn_competition_id": comp_id,
        "draw": "mens-singles",
        "state": state,
        "start_at": SOON,
        "start_is_tbd": False,
        "status_detail": "3rd Set",
        "espn_round": "Round 1",
        "players": players,
    }
    entry.update(overrides)
    return {comp_id: entry}


# ---------------------------------------------------------------------------
# CONTROLS — these must be green in BOTH arms. If the refusal is over-eager it
# deletes real matches from the card, which is a worse defect than the one
# being fixed.
# ---------------------------------------------------------------------------


def test_control_a_pairing_the_scoreboard_confirms_is_kept():
    slate = build_slate(
        _register(),
        prices=_prices(),
        now=NOW,
        order_of_play=_listed(["Juan Manuel Cerundolo", "Casper Ruud"]),
    )
    # `.get` so this control is green in BOTH arms — it asserts the match is
    # kept, which was true before this ship and must stay true after it.
    assert slate["count"] == 1
    assert (slate.get("withheld_pairings") or []) == []


def test_control_a_scoreboard_that_names_nobody_is_not_a_disagreement():
    """Absence is a fact about the read, never about the match (gotcha #53)."""
    slate = build_slate(
        _register(),
        prices=_prices(),
        now=NOW,
        order_of_play=_listed([]),
    )
    assert slate["count"] == 1
    assert (slate.get("withheld_pairings") or []) == []


def test_control_no_scoreboard_entry_at_all_changes_nothing():
    slate = build_slate(_register(), prices=_prices(), now=NOW, order_of_play={})
    assert slate["count"] == 1


@pytest.mark.parametrize(
    "ours,theirs",
    [
        # Word order — ESPN and the register disagree on which token leads for
        # several Chinese names. `Bu Yunchaokete` is a real entrant.
        ("Bu Yunchaokete", "Yunchaokete Bu"),
        # A middle name one side carries and the other drops.
        ("Juan Manuel Cerundolo", "Juan Cerundolo"),
        # Punctuation and case — the register's own normalisation rule.
        ("Felix Auger-Aliassime", "Felix Auger Aliassime"),
        ("JJ Wolf", "J.J. Wolf"),
        # Diacritics.
        ("Alexander Zverev", "Alexander Zverev"),
    ],
)
def test_control_innocuous_name_variants_agree(ours, theirs):
    assert pairing_agrees([ours, "Same Player"], [theirs, "Same Player"]) is True


def test_an_initial_does_not_act_as_a_wildcard():
    """MEASURED, not hypothetical, and found by sweeping my own rule.

    Prefix matching lets a one-letter token cover every token beginning with
    that letter, so ``Christopher O'Connell``'s ``o`` covered BOTH
    ``Oleksandra`` and ``Oliynykova``. Across all 378 registered players that
    was the single pair of genuinely different people the rule called the same.
    A false agreement only fails silent — it is the safe direction — but the
    surname anchor closes it at no cost to the benign cases.
    """
    assert _names_agree("Christopher O'Connell", "Oleksandra Oliynykova") is False


def test_two_players_sharing_a_surname_are_not_one_player():
    """Both Cerundolos are in this draw and both are in the mismatch table."""
    assert _names_agree("Francisco Cerundolo", "Juan Manuel Cerundolo") is False


def test_the_rule_does_not_collapse_the_field():
    """The sweep itself, pinned. Anything that makes the comparison looser has
    to survive every pair of real players in a real draw, not just the handful
    a test author thought of."""
    import itertools

    from app.utils.tournament_register import load_register

    register = load_register("us-open", "2026")
    if register is None:  # pragma: no cover — the register is committed
        pytest.skip("us-open register unavailable")
    names = sorted(
        {
            p["display_name"]
            for p in register.get("players") or []
            if p.get("display_name")
        }
    )
    assert len(names) > 300, "the committed register should carry the full field"
    collisions = {
        frozenset((a, b))
        for a, b in itertools.combinations(names, 2)
        if _names_agree(a, b)
    }
    # The only permitted hits are ONE PERSON listed twice under both word
    # orders — which is exactly what the word-order tolerance is for.
    assert collisions == {
        frozenset(("Juncheng Shang", "Shang Juncheng")),
        frozenset(("Wang Xiyu", "Xiyu Wang")),
    }, sorted(tuple(sorted(c)) for c in collisions)


def test_control_the_pair_is_matched_without_regard_to_side_order():
    assert (
        pairing_agrees(
            ["Casper Ruud", "Juan Manuel Cerundolo"],
            ["Juan Manuel Cerundolo", "Casper Ruud"],
        )
        is True
    )


# ---------------------------------------------------------------------------
# THE DEFECT
# ---------------------------------------------------------------------------


def test_a_pairing_the_scoreboard_contradicts_is_withheld():
    """The measured card: Ruud, who is not in the draw, live in the 3rd set."""
    slate = build_slate(
        _register(),
        prices=_prices(),
        now=NOW,
        order_of_play=_listed(["Arthur Gea", "Juan Manuel Cerundolo"]),
    )
    assert slate["count"] == 0
    assert slate["dropped"].get("PAIRING_DISAGREES") == 1


def test_the_withheld_pairing_is_named_not_merely_counted():
    """A count is a shrug. The quarantine has to say WHO (doctrine rule 6)."""
    slate = build_slate(
        _register(),
        prices=_prices(),
        now=NOW,
        order_of_play=_listed(["Arthur Gea", "Juan Manuel Cerundolo"]),
    )
    assert len(slate["withheld_pairings"]) == 1
    entry = slate["withheld_pairings"][0]
    assert entry["espn_competition_id"] == COMP
    assert entry["registered"] == ["Juan Manuel Cerundolo", "Casper Ruud"]
    assert entry["authority"] == ["Arthur Gea", "Juan Manuel Cerundolo"]
    assert entry["matchup_key"] == (
        "mens-singles:casper-ruud-vs-juan-manuel-cerundolo:2026-08-30"
    )


def test_the_market_price_never_reaches_the_reader_under_the_real_pairing():
    """The whole point. The Kalshi market is for a match nobody is playing, so
    its 60/40 may not be re-labelled onto Gea vs Cerundolo."""
    slate = build_slate(
        _register(),
        prices=_prices(),
        now=NOW,
        order_of_play=_listed(["Arthur Gea", "Juan Manuel Cerundolo"]),
    )
    rendered = str(slate["matches"])
    assert "Arthur Gea" not in rendered
    assert "Casper Ruud" not in rendered


def test_a_decided_competition_is_still_reported_as_decided_first():
    """DECIDED belongs to `build_results` and keeps precedence — a finished
    match must not be re-labelled as a pairing dispute."""
    slate = build_slate(
        _register(),
        prices=_prices(),
        now=NOW,
        order_of_play=_listed(["Arthur Gea", "Juan Manuel Cerundolo"], state="decided"),
    )
    assert slate["dropped"].get("DECIDED") == 1
    assert "PAIRING_DISAGREES" not in slate["dropped"]


# ---------------------------------------------------------------------------
# The authority has to publish the names for any of the above to be possible.
# ---------------------------------------------------------------------------


def _scoreboard(state="in", names=("Arthur Gea", "Juan Manuel Cerundolo")):
    return {
        "events": [
            {
                "id": "189-2026",
                "name": "US Open",
                "groupings": [
                    {
                        "grouping": {"slug": "mens-singles"},
                        "competitions": [
                            {
                                "id": COMP,
                                "date": "2026-09-01T22:00Z",
                                "round": {"displayName": "Round 1"},
                                "status": {
                                    "type": {
                                        "state": state,
                                        "shortDetail": "3rd",
                                        "detail": "3rd Set",
                                    }
                                },
                                "competitors": [
                                    {"athlete": {"displayName": n}} for n in names
                                ],
                            }
                        ],
                    }
                ],
            }
        ]
    }


def test_the_order_of_play_publishes_who_is_playing():
    """Before Q503 the map carried state, start and round — but not the
    competitors, so no consumer could notice it was rendering the wrong two
    people under ESPN's own clock."""
    parsed = parse_results([_scoreboard()], event_name="US Open")
    entry = parsed["order_of_play"][COMP]
    assert entry["players"] == ["Arthur Gea", "Juan Manuel Cerundolo"]


def test_the_names_are_published_for_matches_still_being_played():
    """The `post`-only path already extracted names. The live and upcoming
    competitions are exactly the ones the schedule card renders, and they
    `continue` before that code — which is why the map had no names at all."""
    for state in ("in", "pre"):
        parsed = parse_results([_scoreboard(state=state)], event_name="US Open")
        entry = parsed["order_of_play"][COMP]
        assert entry["players"] == ["Arthur Gea", "Juan Manuel Cerundolo"], state


def test_a_doubles_competition_names_a_team_and_publishes_no_pairing():
    """A team-named competition must publish no players rather than a
    half-pair, so the slate reads it as silence and not as a disagreement."""
    board = _scoreboard()
    board["events"][0]["groupings"][0]["competitions"][0]["competitors"] = [
        {"team": {"displayName": "Bopanna/Ebden"}},
        {"team": {"displayName": "Granollers/Zeballos"}},
    ]
    parsed = parse_results([board], event_name="US Open")
    assert parsed["order_of_play"][COMP]["players"] == []
