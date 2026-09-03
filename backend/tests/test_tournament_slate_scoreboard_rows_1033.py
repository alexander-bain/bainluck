"""THE HUB SHOWS EVERY MATCH THAT IS ON, NOT ONLY THE ONES THE CEREMONY PINNED.

ux/1033 · PILLAR: TRUTH · SHIP: the US Open hub stops saying "No matches
scheduled" while nine second-round matches are on court.

═══ WHAT WAS MEASURED, AND WHY THE FIRST DIAGNOSIS WAS WRONG ═══

The queue arrived reading *"the slate builder reads a stale observation source
(stuck at 18:50Z) and classifies live matches as ALREADY_PLAYED/DECIDED"*.
Measured against production at 2026-09-03T00:28Z, ``GET /api/tournaments/
us-open`` published::

    count 0 · in_progress 0 · order_of_play_listed 625
    dropped {ALREADY_PLAYED: 28, DECIDED: 96} · newest_observed_at None

and ESPN's two live scoreboards, read at the same second, listed **nine US Open
competitions in state ``in``** — all of them Round 2 — with an open Kalshi market
against every one::

    182775 Tsitsipas v Harris    4th Set    KXATPMATCH-26SEP02HARTSI  open
    182759 Wu v Duckworth        3rd Set    KXATPMATCH-26SEP02DUCYIB  open
    182720 Navone v Berrettini   3rd Set    KXATPMATCH-26SEP02BERNAV  open
    182742 Tiafoe v Sakamoto     2nd Set    KXATPMATCH-26SEP02SAKTIA  open
    182693 Majchrzak v Vacherot  2nd Set    KXATPMATCH-26SEP02VACMAJ  open
    182779 Mannarino v Bublik    2nd Set    KXATPMATCH-26SEP02BUBMAN  open
    182761 Paul v Prizmic        1st Set    KXATPMATCH-26SEP02PRIPAU  open
    182584 Vekic v Li            2nd Set    KXWTAMATCH-26SEP02ANNVEK  open
    182546 Joint v Svitolina     1st Set    KXWTAMATCH-26SEP02SVIJOI  open

**Every one of those 124 drops was CORRECT.**  The register is a ceremony
artefact — ``ingest_tournament_draw`` runs once, at the draw, and pins the first
round: 96 R128 fixtures and 28 qualifiers.  Those 96 first-round matches really
are decided and those 28 qualifiers really were played.  The card was not
dropping the matches in play.  **It had never heard of them**, and no rule inside
``build_slate`` could have shown a second-round match however healthy it was.

The "stale observation source" is the same story read from its shadow.
``newest_observed_at`` is a max over the freshest side of the rows that
SURVIVED; with one row it is that row's price, and with none it is ``None``.  It
was never a stale read — it was a one-row sample of a card that had lost the
tournament.

═══ THE SECOND DEFECT, WHICH WOULD HAVE MADE THE FIRST FIX LOOK BROKEN ═══

``authority_match_row`` can already draw a fixture the scoreboard names, and
``tournament_matchup_linker`` already resolves a Kalshi market against the two
players ESPN publishes — for EVERY competition on the scoreboard, not only the
contradicted ones.  So the prices for those nine matches should have been there
for the taking, and they were not.

``_load_candidates`` selected the task's whole candidate pool with
``LIMIT 2000`` and **no ``ORDER BY``**.  Measured on production 2026-09-02, the
two series hold 5,113 rows going back to 2026-02-19, so the cap kept whichever
2,000 the scan reached first — physical order, insertion order, OLDEST FIRST.
Replayed against the live table, the surviving pool's newest ticker date was
``26MAR20``: not one September market was in it.  That is gotcha #41 exactly, and
it is invisible from every downstream signal — a refusal, ``resolved: 0`` and an
unpriced card read identically whether the market is absent or merely unloaded.

Both halves are guarded here.  ``test_the_candidate_query_*`` is the second one;
everything else is the first.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.tournament_register import SCHEMA_VERSION, TournamentRegister
from app.utils.tournament_slate import build_slate

NOW = datetime(2026, 9, 3, 0, 28, tzinfo=timezone.utc)

#: The register's own first-round fixture, and the only one it holds. Its ESPN
#: competition is `post` by now, which is the true and healthy state.
R1_COMP = "182703"
#: Round two. The register has never heard of it and never will.
LIVE_COMP = "182775"
SOON_COMP = "182764"

FLAG = "https://a.espncdn.com/i/teamlogos/countries/500/gre.png"


def _competitor(name, espn_id, order, *, determined=True):
    """One side of an ESPN competition, in ``_competitor_view``'s shape."""
    return {
        "name": name,
        "espn_athlete_id": espn_id if determined else None,
        "flag_url": FLAG if determined else None,
        "country": "Greece" if determined else None,
        "determined": determined,
        "order": order,
    }


TSITSIPAS_V_HARRIS = [
    _competitor("Stefanos Tsitsipas", 2863, 1),
    _competitor("Lloyd Harris", 2869, 2),
]
ALCARAZ_V_FARIA = [
    _competitor("Carlos Alcaraz", 3782, 1),
    _competitor("Jaime Faria", 10219, 2),
]
#: A doubles competition names a TEAM and no athlete; a later-round slot names
#: the qualifier who has not qualified. Both are silence, not half a pairing.
UNDETERMINED = [
    _competitor("TBD", None, 1, determined=False),
    _competitor("Ben Shelton", 4879, 2),
]


def _listed(comp_id, competitors, *, state="in_progress", start_at, **overrides):
    entry = {
        "espn_competition_id": comp_id,
        "draw": "mens-singles",
        "state": state,
        "start_at": start_at,
        "start_is_tbd": False,
        "status_detail": "4th Set" if state == "in_progress" else "Wed at 8:35 PM EDT",
        "espn_round": "Round 2",
        "players": [c["name"] for c in competitors],
        "competitors": competitors,
    }
    entry.update(overrides)
    return entry


def _register(**overrides):
    """The register as the ceremony wrote it: one round, and it is over."""
    register = {
        "schema_version": SCHEMA_VERSION,
        "tournament": "us-open",
        "season": "2026",
        "version": 14,
        "generated_at": NOW.isoformat(),
        "draw_released": True,
        "players": [
            {
                "entity_key": "rafael-jodar",
                "display_name": "Rafael Jodar",
                "draw": "mens-singles",
                "role": "participant",
                "seed": None,
                "country": "Spain",
                "draw_slot": None,
                "section": None,
                "sources": [],
            },
            {
                "entity_key": "bu-yunchaokete",
                "display_name": "Bu Yunchaokete",
                "draw": "mens-singles",
                "role": "participant",
                "seed": None,
                "country": "China",
                "draw_slot": None,
                "section": None,
                "sources": [],
            },
        ],
        "matchups": [
            {
                "matchup_key": "mens-singles:bu-yunchaokete-vs-rafael-jodar:2026-08-30",
                "draw": "mens-singles",
                "round": "R128",
                "scheduled_date": "2026-08-30T04:00:00+00:00",
                "players": ["rafael-jodar", "bu-yunchaokete"],
                "evidence": {
                    "kind": "draw-ceremony-espn",
                    "espn_competition_id": R1_COMP,
                    "espn_round": "Round 1",
                    "observed_at": NOW.isoformat(),
                },
                "sources": [],
            }
        ],
    }
    register.update(overrides)
    return register


def _order_of_play(**overrides):
    """The scoreboard: the register's fixture finished, round two under way."""
    listed = {
        R1_COMP: _listed(
            R1_COMP,
            [_competitor("Rafael Jodar", 12657, 1), _competitor("Bu Yunchaokete", 4419, 2)],
            state="decided",
            start_at="2026-09-01T17:00:00+00:00",
            espn_round="Round 1",
        ),
        LIVE_COMP: _listed(
            LIVE_COMP, TSITSIPAS_V_HARRIS, start_at="2026-09-02T21:20:00+00:00"
        ),
        SOON_COMP: _listed(
            SOON_COMP,
            ALCARAZ_V_FARIA,
            state="upcoming",
            start_at="2026-09-03T00:35:00+00:00",
        ),
    }
    listed.update(overrides)
    return listed


#: The Kalshi market for the pairing ESPN names, as `resolve_authority_links`
#: mints it: keyed `espn:<comp id>|<source>`, sides keyed `espn:athlete:<id>`.
def _link(comp_id, first_id, second_id):
    return {
        f"espn:{comp_id}|kalshi": {
            "source": "kalshi",
            "kind": "match",
            "market_id": 61000001,
            "outcome_id": 910001,
            "status": "live",
            "sides": {
                f"espn:athlete:{first_id}": {"outcome_id": 910001},
                f"espn:athlete:{second_id}": {"outcome_id": 910002},
            },
        }
    }


def _prices(at=None):
    at = at or NOW - timedelta(minutes=1)
    return {
        910001: {"probability": 0.82, "opening_probability": 0.74, "observed_at": at},
        910002: {"probability": 0.18, "opening_probability": 0.26, "observed_at": at},
    }


def _slate(*, register=None, prices=None, order_of_play=None, **kwargs):
    return build_slate(
        register if register is not None else _register(),
        prices=prices if prices is not None else {},
        now=NOW,
        order_of_play=_order_of_play() if order_of_play is None else order_of_play,
        order_of_play_complete=True,
        **kwargs,
    )


def _by_key(slate):
    return {row["matchup_key"]: row for row in slate["matches"]}


# ---------------------------------------------------------------------------
# THE SHIP
# ---------------------------------------------------------------------------


def test_a_live_match_the_register_never_held_is_on_the_card():
    """THE DEFECT, in one assertion.

    The register knows one fixture and it is finished.  Before ux/1033 this
    slate was ``count: 0`` — the honest, complete, correct output of every rule
    in the module, and the reader's night session was "No matches scheduled".
    """
    slate = _slate()

    assert slate["in_progress"] == 1
    row = _by_key(slate)[f"espn:{LIVE_COMP}"]
    assert [side["display_name"] for side in row["sides"]] == [
        "Stefanos Tsitsipas",
        "Lloyd Harris",
    ]
    assert row["live_state"] == "in_progress"
    assert row["status_detail"] == "4th Set"


def test_a_live_match_is_never_in_dropped():
    """The queue's acceptance sentence, held as a property.

    ``dropped`` may still count the register's finished first round — that is a
    true statement about fixtures nobody is playing.  What it may never contain
    is a competition the scoreboard says is in progress.
    """
    slate = _slate()

    keys = set(_by_key(slate))
    for comp_id, listed in _order_of_play().items():
        if listed["state"] == "in_progress":
            assert f"espn:{comp_id}" in keys, (comp_id, slate["dropped"])


def test_the_upcoming_half_of_the_card_is_there_too():
    """"What is on" is the day, not the minute — an unstarted match is still on."""
    slate = _slate()

    row = _by_key(slate)[f"espn:{SOON_COMP}"]
    assert row["live_state"] == "upcoming"
    assert row["draw"] == "mens-singles"


def test_a_decided_competition_stays_off_the_card():
    """CERT-517's word, on the new path too.

    A finished match belongs to ``build_results``.  Reached here through the
    register's own fixture, whose competition is ``decided`` — so this also pins
    that the second pass cannot resurrect a row the first pass legitimately
    dropped.
    """
    slate = _slate()

    assert f"espn:{R1_COMP}" not in _by_key(slate)
    assert slate["dropped"] == {"DECIDED": 1}


def test_a_competition_the_register_claims_never_gets_a_second_row():
    """EVERY MATCH EXACTLY ONCE (doctrine rule 1), from the duplicate side.

    The register's fixture is claimed by its pinned competition id, and it stays
    claimed even when the row was dropped.  Here the drop is ``ALREADY_PLAYED``
    rather than ``DECIDED`` — a qualifying matchup with no scoreboard entry — and
    the scoreboard then lists that same competition as live.  A second pass that
    keyed on "did a row survive" instead of "does the register claim this id"
    would put the fixture on the card twice, under two keys and two states.
    """
    register = _register()
    register["matchups"][0]["evidence"]["espn_competition_id"] = LIVE_COMP

    slate = _slate(register=register)

    keys = [row["matchup_key"] for row in slate["matches"]]
    assert keys.count(f"espn:{LIVE_COMP}") <= 1
    assert len(keys) == len(set(keys))


def test_a_competition_without_two_identified_people_yields_nothing():
    """Silence stays silence.

    126 doubles competitions and every unfilled later-round slot travel in the
    same map as the nine live singles, and none of them may become a row.  This
    is the rule that keeps the card from filling with "TBD v Shelton" the moment
    a draw sheet publishes its skeleton.
    """
    listed = _order_of_play()
    listed["182900"] = _listed(
        "182900", UNDETERMINED, start_at="2026-09-04T04:00:00+00:00"
    )

    slate = _slate(order_of_play=listed)

    assert "espn:182900" not in _by_key(slate)


def test_no_scoreboard_means_no_scoreboard_rows():
    """The control, and it is the first rollout state (a cold results cache).

    A caller with no ``order_of_play`` gets exactly what it got before ux/1033:
    the register's own rows and nothing invented for it.  The register's own
    fixture is still here — CERT-544 keeps a pinned fixture off the clock's
    retirement inside the ceremony window — and that is the point: the second
    pass adds rows, it does not replace the first.
    """
    slate = build_slate(_register(), prices={}, now=NOW)

    assert slate["scoreboard_pairings"] == 0
    assert [row["matchup_key"] for row in slate["matches"]] == [
        "mens-singles:bu-yunchaokete-vs-rafael-jodar:2026-08-30"
    ]


# ---------------------------------------------------------------------------
# THE ROUND, IN THE REGISTER'S OWN VOCABULARY
# ---------------------------------------------------------------------------


def test_the_round_is_published_as_a_register_key_not_espns_words():
    """"Round 2" IS NOT A ROUND KEY, and publishing it raw is a real defect.

    The client's ``slateRoundKey`` recognises the register's vocabulary and files
    anything else under **Qualifying** — so 43 second-round fixtures would have
    arrived on the card sitting behind the Qual pill.  ``R64`` is only derivable
    with the draw's size, and the size is read off the register's own largest
    numbered round rather than assumed to be 128.
    """
    slate = _slate()

    assert _by_key(slate)[f"espn:{LIVE_COMP}"]["round"] == "R64"


def test_a_draw_whose_size_the_register_cannot_name_publishes_no_round():
    """No size, no guess.

    With only a qualifying bucket in the register there is no ``R<n>`` to read a
    draw size from, and "Round 2" then means nothing at all.  ``None`` is the
    honest answer; inventing ``R64`` for a draw we cannot measure is the
    wrong-question defect this module exists to refuse.
    """
    register = _register()
    register["matchups"][0]["round"] = "qualifying"

    slate = _slate(register=register)

    assert _by_key(slate)[f"espn:{LIVE_COMP}"]["round"] is None


# ---------------------------------------------------------------------------
# THE PRICE
# ---------------------------------------------------------------------------


def test_a_scoreboard_row_carries_the_price_resolved_for_its_own_pairing():
    """lane1/047's rule, on the population that is now most of the card.

    "Nobody is quoting this match" printed over a market we hold open is the
    most expensive sentence a probability product has.
    """
    slate = _slate(prices=_prices(), authority_links=_link(LIVE_COMP, 2863, 2869))

    row = _by_key(slate)[f"espn:{LIVE_COMP}"]
    assert row["priced"] is True
    assert [side["probability"] for side in row["sides"]] == [0.82, 0.18]
    assert row["coherent"] is True
    assert slate["scoreboard_priced"] == 1


def test_a_link_for_another_competition_never_reaches_this_row():
    """The lookup is keyed on the row's OWN competition, and that is the guard.

    A link map is one dict for the whole tournament.  If the key were ever
    loosened — to the draw, to the market, to "the only link we have" — a price
    quoted for one match would print under two other people's names, which is
    the fabrication this whole file's ancestry exists to refuse.
    """
    slate = _slate(prices=_prices(), authority_links=_link(SOON_COMP, 2863, 2869))

    row = _by_key(slate)[f"espn:{LIVE_COMP}"]
    assert row["priced"] is False
    assert [side["probability"] for side in row["sides"]] == [None, None]
    assert row["price_state"] == "unpriced"


def test_an_unpriced_scoreboard_row_still_renders():
    """UX-P142: a fixture nobody prices is still a fixture.

    The whole point of the second pass is that the card survives the market
    being silent — otherwise a linker outage empties the tournament again.
    """
    slate = _slate()

    row = _by_key(slate)[f"espn:{LIVE_COMP}"]
    assert row["priced"] is False
    assert row["price_state"] == "unpriced"
    assert [side["display_name"] for side in row["sides"]] == [
        "Stefanos Tsitsipas",
        "Lloyd Harris",
    ]


def test_the_slates_freshness_is_the_scoreboard_rows_price():
    """``newest_observed_at`` was never stale — it was a one-row sample.

    With the card restored it reports the freshest price on it, which for a live
    tournament is seconds old rather than the 25 minutes the empty card reported.
    """
    at = NOW - timedelta(seconds=40)
    slate = _slate(
        prices=_prices(at), authority_links=_link(LIVE_COMP, 2863, 2869)
    )

    assert slate["newest_observed_at"] == at.isoformat()
    assert slate["price_state"] == "live"


# ---------------------------------------------------------------------------
# ORDERING
# ---------------------------------------------------------------------------


def test_a_live_match_sorts_above_one_that_has_not_started():
    """LIVE FIRST — and the case that makes it necessary is the refuted row.

    lane1/054: ESPN's tennis ``state`` lags by SETS, so a match in its fourth set
    can still carry the scheduled start ESPN published for it, and that start can
    be in the FUTURE.  Five such rows were measured at 2026-09-02T18:50Z.  Under
    a pure ``scheduled_date`` sort every one of them sorted BELOW matches nobody
    had walked on court for.

    Constructed so that the clock alone would get it wrong: the live match is
    stamped an hour later than the upcoming one.
    """
    listed = {
        LIVE_COMP: _listed(
            LIVE_COMP,
            TSITSIPAS_V_HARRIS,
            state="in_progress",
            start_at="2026-09-03T02:00:00+00:00",
        ),
        SOON_COMP: _listed(
            SOON_COMP,
            ALCARAZ_V_FARIA,
            state="upcoming",
            start_at="2026-09-03T01:00:00+00:00",
        ),
    }

    slate = _slate(order_of_play=listed)

    assert [
        row["matchup_key"]
        for row in slate["matches"]
        if row.get("pairing_source") == "scoreboard"
    ] == [f"espn:{LIVE_COMP}", f"espn:{SOON_COMP}"]
    # AND IT LEADS THE WHOLE CARD, not just its own half. A live match sorting
    # below the register's finished-first-round leftovers is the same defect.
    assert slate["matches"][0]["matchup_key"] == f"espn:{LIVE_COMP}"


def test_within_a_half_the_clock_still_orders():
    """The control for the test above.

    Only the live/not-live split is hoisted.  If the sort had been replaced
    wholesale the card would stop reading as a schedule, and the test above would
    pass just the same.
    """
    listed = {
        SOON_COMP: _listed(
            SOON_COMP,
            ALCARAZ_V_FARIA,
            state="upcoming",
            start_at="2026-09-03T02:00:00+00:00",
        ),
        "182900": _listed(
            "182900",
            [_competitor("Taylor Fritz", 3833, 1), _competitor("Mattia Bellucci", 5090, 2)],
            state="upcoming",
            start_at="2026-09-03T01:00:00+00:00",
        ),
    }

    slate = _slate(order_of_play=listed)

    assert [
        row["matchup_key"]
        for row in slate["matches"]
        if row.get("pairing_source") == "scoreboard"
    ] == ["espn:182900", f"espn:{SOON_COMP}"]


# ---------------------------------------------------------------------------
# THE COUNTERS
# ---------------------------------------------------------------------------


def test_scoreboard_rows_do_not_inflate_the_authority_repair_backlog():
    """Two populations, two counters.

    ``authority_pairings`` is a REPAIR QUEUE — every one is a register row naming
    somebody who is not in the draw.  A round the ceremony could not have known
    about is not a defect in anything, and folding the two together would make a
    healthy slam read as 50 outstanding register repairs.
    """
    slate = _slate()

    assert slate["scoreboard_pairings"] == 2
    assert slate["authority_pairings"] == 0
    assert slate["authority_priced"] == 0


def test_an_empty_scoreboard_card_is_still_diagnosable():
    """A short card must say which kind of short it is (gotcha #53).

    ``scoreboard_pairings: 0`` against ``order_of_play_listed`` in the hundreds is
    the alarm this queue existed to make readable: the scoreboard was read, it
    named plenty, and none of it reached the card.
    """
    listed = {
        "182900": _listed(
            "182900", UNDETERMINED, start_at="2026-09-04T04:00:00+00:00"
        )
    }

    slate = _slate(order_of_play=listed)

    assert slate["scoreboard_pairings"] == 0
    assert slate["order_of_play_listed"] == 1


# ---------------------------------------------------------------------------
# THE CANDIDATE POOL — the second defect
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("series", [("KXATPMATCH", "KXWTAMATCH"), ("KXATPMATCH",)])
def test_the_candidate_query_bounds_itself_by_recency_and_orders_by_it(series):
    """THE UNORDERED CAP, held by the statement that runs.

    Every other test of the linker monkeypatches ``_load_candidates`` whole,
    which is precisely how ``LIMIT 2000`` over 5,113 rows went six months
    unnoticed.  Compiled rather than read as source: a comment claiming an
    ``ORDER BY`` is not an ``ORDER BY``.
    """
    from sqlalchemy.dialects import postgresql

    from app.tasks.tournament_matchup_linker import (
        CANDIDATE_WINDOW_DAYS,
        MAX_CANDIDATE_MARKETS,
        candidate_query,
    )

    sql = str(
        candidate_query(series, now=NOW).compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )

    assert "ORDER BY futures_markets.id DESC" in sql
    assert f"LIMIT {MAX_CANDIDATE_MARKETS}" in sql
    # The window is a real instant computed from the caller's clock, not a
    # placeholder: the pool that broke this had no lower bound at all.
    floor = (NOW - timedelta(days=CANDIDATE_WINDOW_DAYS)).isoformat(sep=" ")
    assert f"futures_markets.created_at >= '{floor}'" in sql
    for name in series:
        assert f"LIKE '{name}-%" in sql


def test_the_candidate_window_covers_the_lead_a_slam_is_quoted_on():
    """The bound has to be a MEASUREMENT, not a round number.

    Measured on production 2026-09-02: Kalshi publishes a slam's match markets
    about two days ahead (26AUG30's tickers were created 26AUG28), and the two
    series hold 546 rows in the last 7 days and 589 in 14.  The window must clear
    the lead comfortably and still leave the cap an order of magnitude of slack —
    if it is ever tightened below the lead, the pool loses tomorrow's markets and
    the card goes unpriced the night before play.
    """
    from app.tasks.tournament_matchup_linker import (
        CANDIDATE_WINDOW_DAYS,
        MAX_CANDIDATE_MARKETS,
    )

    assert CANDIDATE_WINDOW_DAYS >= 7
    assert MAX_CANDIDATE_MARKETS >= 2000
