"""THE CARD SHOWS THE MATCH THAT IS ON (Q505, EVENT-GRAPH-DOCTRINE rule 1).

Q503 established that a market may not NAME a fixture, and withheld the four US
Open fixtures whose register pairing ESPN's own competition contradicts.  This
is the other half of the same repair, and the half a reader can see.

What a reader saw at 15:38 PT on 2026-09-01, at the top of
``https://bainluck.com/tournaments/us-open`` — screenshotted, not inferred:

    Casper Ruud  60%   /   Juan Manuel Cerundolo  40%
    1:20 PM · MEN'S SINGLES

Cerundolo was on court.  His opponent was **Arthur Gea**.  Casper Ruud is not
in the tournament — he appears nowhere in ESPN's 625-competition draw.  Fable's
lane1/043 directive, verbatim: *"A user watching 'Ruud vs Cerundolo' live on
our site right now is watching a match that is not happening."*

With Q503 alone that row DISAPPEARS.  That is strictly better than a lie, and
it is not the ship: three matches that really are being played would then be
absent from the day's card, which is doctrine rule 1's other failure — "every
match exactly once" — reached from the other side.  The directive names the
whole acceptance: *"our slate must show ESPN's pairings (presumably
Cerundolo-Gea, Potapova-Semenistaja, Jodar-Bu) and the fabricated ones must be
quarantined/repaired."*

THE RULE THESE TESTS PIN: where the authority contradicts the register's
pairing, the fixture is re-rendered with **the authority's two people and no
price**.  Only the names were ever in dispute — the ESPN competition anchor is
correct on all four, so the draw, round, clock and state are facts about a
fixture we have correctly identified.

AND THE PRICE IS THE PART THAT MAY NOT SURVIVE.  Q503 declined to re-label at
all, on the grounds that carrying a 60/40 quoted for a match nobody is playing
onto the two who really are "would be the same fabrication wearing better
names".  That objection is to the NUMBER, and it is right: so ``priced`` is
``False``, both probabilities are ``None``, and the pinned Kalshi outcome ids
are not read.  ``test_the_authority_row_carries_no_price_from_the_market``
below is the guard that keeps it that way, and it is the most important test in
this file — a future refactor that "helpfully" joins the register's prices onto
the authority's names would re-create the exact defect Q503 fixed, wearing
better names, and every other assertion here would still pass.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.espn_tennis import parse_results
from app.utils.tournament_register import SCHEMA_VERSION, TournamentRegister
from app.utils.tournament_slate import build_match_row, build_slate

# `authority_match_row` is imported INSIDE the one test that calls it directly.
# At module scope it makes the whole file uncollectable against the pre-fix
# tree — exit 2, an ImportError, a story about the harness rather than a
# result (gotcha #124). Every other test here reaches the new behaviour through
# `build_slate`, which exists in both arms, so the red-first arm runs the
# assertions instead of failing to start.

NOW = datetime(2026, 9, 1, 22, 0, tzinfo=timezone.utc)
SOON = (NOW + timedelta(hours=2)).isoformat()
COMP = "182710"

GEA_FLAG = "https://a.espncdn.com/i/teamlogos/countries/500/fra.png"
CERUNDOLO_FLAG = "https://a.espncdn.com/i/teamlogos/countries/500/arg.png"


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
                # NOT IN THE TOURNAMENT. He is in the register because a Kalshi
                # market title put him there.
                "entity_key": "casper-ruud",
                "display_name": "Casper Ruud",
                "draw": "mens-singles",
                "role": "contender",
                "seed": 12,
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
    """The real, live, wrong price — 60/40 on a match nobody is playing."""
    at = NOW - timedelta(minutes=10)
    return {
        900001: {"probability": 0.4, "opening_probability": 0.32, "observed_at": at},
        900002: {"probability": 0.6, "opening_probability": 0.68, "observed_at": at},
    }


def _competitor(name, espn_id, flag, order, *, determined=True):
    """One side of an ESPN competition, in `_competitor_view`'s shape."""
    return {
        "name": name,
        "espn_athlete_id": espn_id if determined else None,
        "flag_url": flag if determined else None,
        "country": (
            ("France" if flag == GEA_FLAG else "Argentina") if determined else None
        ),
        "determined": determined,
        "order": order,
    }


#: ESPN's competition 182710 as it really read: Gea listed first, Cerundolo
#: second, and no Casper Ruud anywhere.
GEA_V_CERUNDOLO = [
    _competitor("Arthur Gea", 5177231, GEA_FLAG, 1),
    _competitor("Juan Manuel Cerundolo", 4381513, CERUNDOLO_FLAG, 2),
]


def _listed(players, competitors=None, comp_id=COMP, state="in_progress", **overrides):
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
    if competitors is not None:
        entry["competitors"] = competitors
    entry.update(overrides)
    return {comp_id: entry}


def _slate(**kwargs):
    return build_slate(_register(), prices=_prices(), now=NOW, **kwargs)


def _the_row(slate):
    rows = [r for r in slate["matches"] if r.get("pairing_source") == "authority"]
    assert len(rows) == 1, slate["matches"]
    return rows[0]


# ---------------------------------------------------------------------------
# THE SHIP
# ---------------------------------------------------------------------------


def test_the_card_names_the_two_people_who_are_playing():
    slate = _slate(
        order_of_play=_listed(["Arthur Gea", "Juan Manuel Cerundolo"], GEA_V_CERUNDOLO)
    )
    assert slate["count"] == 1
    names = [side["display_name"] for side in _the_row(slate)["sides"]]
    assert names == ["Arthur Gea", "Juan Manuel Cerundolo"]


def test_the_player_who_is_not_in_the_tournament_is_nowhere_on_the_card():
    """The whole defect, stated as an absence over the WHOLE payload.

    Not "the row was replaced" — that is a claim about one row. A reader's
    complaint is that Casper Ruud is on this page at all.
    """
    slate = _slate(
        order_of_play=_listed(["Arthur Gea", "Juan Manuel Cerundolo"], GEA_V_CERUNDOLO)
    )
    rendered = [
        side["display_name"] for row in slate["matches"] for side in row["sides"]
    ]
    assert "Casper Ruud" not in rendered
    assert rendered == ["Arthur Gea", "Juan Manuel Cerundolo"]


def test_the_authority_row_carries_no_price_from_the_market():
    """═══ THE ONE THAT MATTERS ═══

    The register pins live Kalshi outcomes for this matchup and ``_prices``
    supplies a real 60/40 for them. That quote is for ``Cerundolo vs Ruud`` — a
    match that is not being played — so it may not appear beside Gea's name in
    any form: not as a probability, not as an opening price, not as a move, and
    not as a ``priced`` row that would make a renderer print a percent column.

    Every other assertion in this file would still pass if a refactor joined
    those prices on. This one would not.
    """
    row = _the_row(
        _slate(
            order_of_play=_listed(
                ["Arthur Gea", "Juan Manuel Cerundolo"], GEA_V_CERUNDOLO
            )
        )
    )
    assert row["priced"] is False
    assert row["price_state"] == "unpriced"
    assert row["probability_is_live"] is False
    assert row["coherent"] is False
    assert row["favourite"] is None
    assert row["raw_sum"] is None
    assert row["source_count"] == 0
    for side in row["sides"]:
        assert side["probability"] is None
        assert side["opening_probability"] is None
        assert side["move"] is None
        assert side["raw_probability"] is None
        assert side["raw_opening_probability"] is None
        assert side["price_state"] == "unpriced"


def test_the_authority_row_does_not_link_to_the_fabricated_pairing():
    """``build_match_detail`` is passed no ``order_of_play`` (Q503 carry-forward
    1), so a match page still renders the register's pairing. A null
    ``event_id`` is what makes the card unclickable — see ``matchHref``."""
    row = _the_row(
        _slate(
            order_of_play=_listed(
                ["Arthur Gea", "Juan Manuel Cerundolo"], GEA_V_CERUNDOLO
            )
        )
    )
    assert row["event_id"] is None


def test_the_authority_row_is_keyed_on_the_competition_not_the_matchup():
    """Two different pairings must never share one id."""
    row = _the_row(
        _slate(
            order_of_play=_listed(
                ["Arthur Gea", "Juan Manuel Cerundolo"], GEA_V_CERUNDOLO
            )
        )
    )
    assert row["matchup_key"] == f"espn:{COMP}"
    assert row["matchup_key"] != _matchup()["matchup_key"]


def test_the_fixture_facts_survive_because_the_anchor_was_never_wrong():
    row = _the_row(
        _slate(
            order_of_play=_listed(
                ["Arthur Gea", "Juan Manuel Cerundolo"], GEA_V_CERUNDOLO
            )
        )
    )
    assert row["draw"] == "mens-singles"
    assert row["round"] == "R128"
    assert row["live_state"] == "in_progress"
    assert row["status_detail"] == "3rd Set"
    assert row["scheduled_date"] == SOON
    assert row["start_is_tbd"] is False


def test_a_side_gets_its_flag_and_never_a_face():
    """`PlayerAvatar` step two. The verified-photograph census is keyed on
    register entities and ESPN's own headshots failed it (40%/28%); the flag is
    on the same record as the name at 100%."""
    row = _the_row(
        _slate(
            order_of_play=_listed(
                ["Arthur Gea", "Juan Manuel Cerundolo"], GEA_V_CERUNDOLO
            )
        )
    )
    gea = row["sides"][0]
    assert gea["image"] == {"url": None, "flag_url": GEA_FLAG}
    assert gea["country"] == "France"
    assert gea["entity_key"] == "espn:athlete:5177231"


def test_a_side_carries_no_seed_from_the_register():
    """The register seeds Ruud [12]. Printing a 12 beside Gea would be the same
    class of borrowed fact as printing Ruud's price."""
    row = _the_row(
        _slate(
            order_of_play=_listed(
                ["Arthur Gea", "Juan Manuel Cerundolo"], GEA_V_CERUNDOLO
            )
        )
    )
    assert [side["seed"] for side in row["sides"]] == [None, None]


def test_the_sides_are_in_the_scoreboards_order():
    """With no probabilities there is no favourite to lead with, and the
    register's side order describes a pairing that is wrong."""
    reversed_order = [
        _competitor("Juan Manuel Cerundolo", 4381513, CERUNDOLO_FLAG, 2),
        _competitor("Arthur Gea", 5177231, GEA_FLAG, 1),
    ]
    row = _the_row(
        _slate(
            order_of_play=_listed(
                ["Juan Manuel Cerundolo", "Arthur Gea"], reversed_order
            )
        )
    )
    assert [s["display_name"] for s in row["sides"]] == [
        "Arthur Gea",
        "Juan Manuel Cerundolo",
    ]


def test_the_quarantine_says_what_replaced_the_withheld_pairing():
    """Doctrine rule 6: the quarantine is the instrument. "3 withheld" and "3
    withheld, 3 repaired on the card" are different states of this page."""
    slate = _slate(
        order_of_play=_listed(["Arthur Gea", "Juan Manuel Cerundolo"], GEA_V_CERUNDOLO)
    )
    assert slate["authority_pairings"] == 1
    (withheld,) = slate["withheld_pairings"]
    assert withheld["registered"] == ["Juan Manuel Cerundolo", "Casper Ruud"]
    assert withheld["authority"] == ["Arthur Gea", "Juan Manuel Cerundolo"]
    assert withheld["replaced_by"] == f"espn:{COMP}"
    # Still counted as a drop: the register row is still wrong and still needs
    # repairing. The card being right is not the register being right.
    assert slate["dropped"]["PAIRING_DISAGREES"] == 1


def test_the_row_has_exactly_the_shape_an_ordinary_row_has():
    """A renderer reads one shape. A field added to ``build_match_row`` and not
    here is a `KeyError` — or worse, an `undefined` — on the one row on the
    page that is there because something was already wrong.
    """
    ordinary, reason = build_match_row(
        TournamentRegister(_register()),
        _matchup(),
        prices=_prices(),
        now=NOW,
        cutoff=None,
    )
    assert reason is None and ordinary is not None
    row = _the_row(
        _slate(
            order_of_play=_listed(
                ["Arthur Gea", "Juan Manuel Cerundolo"], GEA_V_CERUNDOLO
            )
        )
    )
    assert set(row) - set(ordinary) == {"pairing_source"}
    assert set(ordinary) - set(row) == set()
    for side, ordinary_side in zip(row["sides"], ordinary["sides"]):
        assert set(side) == set(ordinary_side)


# ---------------------------------------------------------------------------
# CONTROLS — green in BOTH arms. Over-firing here puts a phantom pairing on the
# card, which is the defect this exists to remove.
# ---------------------------------------------------------------------------


def test_control_a_pairing_the_scoreboard_confirms_keeps_its_price():
    slate = _slate(
        order_of_play=_listed(
            ["Juan Manuel Cerundolo", "Casper Ruud"],
            [
                _competitor("Juan Manuel Cerundolo", 4381513, CERUNDOLO_FLAG, 1),
                _competitor("Casper Ruud", 3902144, GEA_FLAG, 2),
            ],
        )
    )
    assert slate["count"] == 1
    (row,) = slate["matches"]
    assert row.get("pairing_source") is None
    assert row["priced"] is True
    assert row["coherent"] is True
    assert (slate.get("withheld_pairings") or []) == []
    assert slate.get("authority_pairings", 0) == 0


def test_control_no_scoreboard_entry_at_all_produces_no_authority_row():
    slate = _slate(order_of_play={})
    assert slate["count"] == 1
    assert slate.get("authority_pairings", 0) == 0


# ---------------------------------------------------------------------------
# A HALF-READ IS SILENCE — the caller must never invent a side.
# ---------------------------------------------------------------------------


def test_a_doubles_competition_names_a_team_and_gets_no_authority_row():
    """No athlete on either side, so nothing to render. Q503's plain withhold
    stands and the reader loses a row rather than gaining a fabricated one."""
    slate = _slate(
        order_of_play=_listed(
            ["Arthur Gea", "Juan Manuel Cerundolo"],
            [
                _competitor("", None, None, 1, determined=False),
                _competitor("", None, None, 2, determined=False),
            ],
        )
    )
    assert slate["count"] == 0
    assert slate["withheld_pairings"][0]["replaced_by"] is None


def test_an_undetermined_side_gets_no_authority_row():
    """A qualifier slot ESPN calls ``TBD`` carries a non-positive athlete id.
    One real person and one placeholder is not a pairing."""
    slate = _slate(
        order_of_play=_listed(
            ["Arthur Gea", "Juan Manuel Cerundolo"],
            [
                _competitor("Arthur Gea", 5177231, GEA_FLAG, 1),
                _competitor("TBD", None, None, 2, determined=False),
            ],
        )
    )
    assert slate["count"] == 0
    assert slate["withheld_pairings"][0]["replaced_by"] is None


def test_a_scoreboard_entry_with_no_competitors_key_at_all_is_silence():
    """The pre-Q505 payload shape, and the shape of the results cache for the
    ~3 minutes after a deploy before ``sync-tournament-results`` refills it. It
    must read as silence, not as a reason to invent a pairing."""
    slate = _slate(order_of_play=_listed(["Arthur Gea", "Juan Manuel Cerundolo"]))
    assert slate["count"] == 0
    assert slate["withheld_pairings"][0]["replaced_by"] is None


def test_a_decided_match_is_a_result_and_never_an_authority_row():
    """Q503's ordering, preserved: ``DECIDED`` is checked before the pairing
    comparison, because a finished match belongs to ``build_results`` whatever
    else is wrong with it. Competition 182673 (Rublev vs Cilic/Virtanen) is the
    real instance — it is in the mismatch table and NOT on the card."""
    slate = _slate(
        order_of_play=_listed(
            ["Arthur Gea", "Juan Manuel Cerundolo"],
            GEA_V_CERUNDOLO,
            state="decided",
        )
    )
    assert slate["count"] == 0
    assert slate["dropped"] == {"DECIDED": 1}
    assert slate["withheld_pairings"] == []


def test_a_scoreboard_entry_with_no_start_produces_no_row():
    """Every row on this card sorts on its start and every renderer prints one.
    The register's own stamp is the fallback; with neither, there is no row."""
    from app.utils.tournament_slate import authority_match_row

    row = authority_match_row(
        _matchup(scheduled_date=None),
        _listed(
            ["Arthur Gea", "Juan Manuel Cerundolo"], GEA_V_CERUNDOLO, start_at=None
        )[COMP],
        now=NOW,
    )
    assert row is None


# ---------------------------------------------------------------------------
# THE SOURCE READ — identity must reach the slate for every state, not just
# the finished ones. This is the Q503 hoist, extended.
# ---------------------------------------------------------------------------


def _payload(state, detail):
    return {
        "events": [
            {
                "name": "US Open",
                "groupings": [
                    {
                        "grouping": {"slug": "mens-singles"},
                        "competitions": [
                            {
                                "id": COMP,
                                "date": SOON,
                                "round": {"displayName": "Round 1"},
                                "status": {
                                    "type": {"state": state, "detail": detail},
                                    "shortDetail": detail,
                                },
                                "competitors": [
                                    {
                                        "id": "5177231",
                                        "order": 1,
                                        "athlete": {
                                            "displayName": "Arthur Gea",
                                            "flag": {
                                                "href": GEA_FLAG,
                                                "alt": "France",
                                            },
                                        },
                                    },
                                    {
                                        "id": "4381513",
                                        "order": 2,
                                        "athlete": {
                                            "displayName": "Juan Manuel Cerundolo",
                                            "flag": {
                                                "href": CERUNDOLO_FLAG,
                                                "alt": "Argentina",
                                            },
                                        },
                                    },
                                ],
                            }
                        ],
                    }
                ],
            }
        ]
    }


def test_the_scoreboard_read_publishes_identity_for_a_live_competition():
    parsed = parse_results([_payload("in", "3rd Set")], event_name="US Open")
    entry = parsed["order_of_play"][COMP]
    assert entry["players"] == ["Arthur Gea", "Juan Manuel Cerundolo"]
    assert [c["espn_athlete_id"] for c in entry["competitors"]] == [5177231, 4381513]
    assert [c["flag_url"] for c in entry["competitors"]] == [GEA_FLAG, CERUNDOLO_FLAG]
    assert all(c["determined"] for c in entry["competitors"])


def test_the_scoreboard_read_publishes_identity_for_an_upcoming_competition():
    parsed = parse_results([_payload("pre", "7:05 PM")], event_name="US Open")
    entry = parsed["order_of_play"][COMP]
    assert [c["name"] for c in entry["competitors"]] == [
        "Arthur Gea",
        "Juan Manuel Cerundolo",
    ]


def test_identity_and_the_name_list_are_read_separately():
    """``determined`` is stricter than "has a display name" — it also demands a
    positive athlete id. The pairing COMPARISON must not inherit that: a real
    player published without an id would drop out of ``players``, shorten it to
    one, and turn a contradiction into silence.
    """
    payload = _payload("in", "3rd Set")
    competition = payload["events"][0]["groupings"][0]["competitions"][0]
    competition["competitors"][0]["id"] = "0"

    entry = parse_results([payload], event_name="US Open")["order_of_play"][COMP]
    # The comparison still sees two names, so the contradiction is still caught.
    assert entry["players"] == ["Arthur Gea", "Juan Manuel Cerundolo"]
    # Identity does not, so no authority row is invented for it.
    assert entry["competitors"][0]["determined"] is False
    slate = _slate(order_of_play={COMP: entry})
    assert slate["count"] == 0
    assert slate["withheld_pairings"][0]["replaced_by"] is None


def test_the_whole_path_from_espn_payload_to_the_card():
    """End to end through the shipped readers, no hand-built ``order_of_play``.

    The unit fixtures above all hand ``build_slate`` a map I wrote. This one
    starts at an ESPN payload and ends at a rendered pairing, so a change that
    keeps both halves internally consistent while breaking the join between
    them cannot pass.
    """
    parsed = parse_results([_payload("in", "3rd Set")], event_name="US Open")
    slate = build_slate(
        _register(),
        prices=_prices(),
        now=NOW,
        order_of_play=parsed["order_of_play"],
    )
    assert [s["display_name"] for s in _the_row(slate)["sides"]] == [
        "Arthur Gea",
        "Juan Manuel Cerundolo",
    ]
    assert _the_row(slate)["priced"] is False
