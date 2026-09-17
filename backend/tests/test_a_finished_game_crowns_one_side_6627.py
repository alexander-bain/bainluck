"""#6627 — a finished game stops crowning the side its own score beat.

`/events/15312858` finished **Colorado Rockies 9 – San Diego Padres 3** and
served one card, headed with the matchup, holding three rows::

    Colorado                 Won
    San Diego Padres         Won      <- a Polymarket weekly container for the
    San Diego                Lost        PREVIOUS night's fixture

Both sides crowned in the same game. `/events/15308640` printed the other
direction: Philadelphia 1 – Houston 2, and `Houston Astros — Lost`.

#6595's gate ends at the final whistle on purpose — "once the game is over the
question is the game's own AND answerable, and settled means settled". That is
right about the question and wrong about the row, because the row can be a
different game's. This suite pins the narrower statement: on a finished event
with a decisive score, a verdict that disagrees with that score is withheld.

THE MIS-ATTACHMENT IS NOT REPAIRED HERE. It is #6627's, under #2693, and no
serve-time gate can fix which event a market hangs on. What is fixed is that we
print a verdict our own scoreboard refutes, on the same screen as the scoreboard.

⭐ THE CONTROLS ARE THE SHIP. Of the 332 authoritative rows whose verdict
disagrees with their event's score, **318 are correct** — a player who won
`Set 1 Winner` and lost the match, a team that won `First Team to Score` and
lost the game. A gate that cannot tell those apart erases 318 true results to
fix 14. Every one of those shapes has a test below that asserts it SURVIVES.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.routes.events import (
    _settled_grade_fields,
    _verdict_contradicts_the_final_score,
)
from app.services.database import get_db, get_db_rw
from tests.integration.test_route_events_seeded import (
    _make_event,
    _make_event_detail_session,
    _make_futures_market,
    _make_outcome,
)

# The specimen, from production 2026-09-16.
HOME, AWAY = "Colorado Rockies", "San Diego Padres"
HOME_SCORE, AWAY_SCORE = 9, 3  # Colorado won


def _mkt(name, status="resolved"):
    market = MagicMock()
    market.name = name
    market.status = status
    market.settled_at = None  # the #6595 arm must not be what fires below
    return market


def _out(name, is_winner=True, resolution_source="api_settlement"):
    outcome = MagicMock()
    outcome.name = name
    outcome.is_winner = is_winner
    outcome.resolution_source = resolution_source
    return outcome


def _ctx(**over):
    ctx = {
        "event_is_finished": True,
        "home_team": HOME,
        "away_team": AWAY,
        "home_score": HOME_SCORE,
        "away_score": AWAY_SCORE,
    }
    ctx.update(over)
    return ctx


def _fires(market_name, outcome_name, *, is_winner=True, **over):
    return _verdict_contradicts_the_final_score(
        _mkt(market_name), _out(outcome_name, is_winner=is_winner), **_ctx(**over)
    )


# ── The specimen, both directions ───────────────────────────────────────────


def test_the_padres_do_not_win_a_game_they_lost_nine_three():
    """Market 60485359 on event 15312858."""
    assert _fires("San Diego Padres vs. Colorado Rockies", "San Diego Padres") is True


def test_the_astros_are_not_marked_lost_in_a_game_they_won():
    """Event 15308640, Philadelphia 1 – Houston 2, `Houston Astros` is_winner FALSE.

    The other direction of the same disagreement, and it renders just as loudly:
    a reader sees the winning side marked `Lost`. A gate written only around the
    crown would leave half the population.
    """
    assert (
        _verdict_contradicts_the_final_score(
            _mkt("Houston Astros vs. Philadelphia Phillies"),
            _out("Houston Astros", is_winner=False),
            event_is_finished=True,
            home_team="Philadelphia Phillies",
            away_team="Houston Astros",
            home_score=1,
            away_score=2,
        )
        is True
    )


def test_the_short_form_outcome_name_the_venue_writes_is_reached():
    """The venue writes `San Diego`; we store `San Diego Padres`.

    The gate consults `_fuzzy_team_match` on the OUTCOME name rather than
    comparing strings, and this is the row that proves it. An exact-name test
    would have sized this population at 3 rows instead of 15.
    """
    assert _fires("San Diego Padres vs. Colorado Rockies", "San Diego") is True


def test_a_market_titled_in_short_forms_is_out_of_reach_and_that_is_stated():
    """⭐ THE GATE'S KNOWN UNDER-COVERAGE, PINNED SO IT IS NOT REDISCOVERED.

    `outcome_name_is_the_whole_matchup` needs BOTH of our stored names to appear
    in the MARKET title, so a venue that titles a market in short forms is never
    reached. Event 15304908 is the specimen: we store `St.Louis Cardinals`
    (no space), Polymarket writes `St. Louis Cardinals`, St. Louis won 7-3 and
    the page still crowns the White Sox.

    Measured over the same 10 days: **3 such rows** — this one and two FCS
    football games. They are not fixed here and the test says so rather than the
    suite reading as if the class were closed.
    """
    assert (
        _verdict_contradicts_the_final_score(
            _mkt("Chicago White Sox vs. St. Louis Cardinals"),
            _out("Chicago White Sox"),
            event_is_finished=True,
            home_team="St.Louis Cardinals",
            away_team="Chicago White Sox",
            home_score=7,
            away_score=3,
        )
        is False
    )


@pytest.mark.parametrize(
    "market_name,outcome_name,home,away,hs,as_,why",
    [
        (
            "Platense vs Fluminense",
            "Platense advances",
            "Platense",
            "Fluminense-RJ",
            2,
            1,
            "winning the leg is not advancing on aggregate",
        ),
        (
            "CA Tigre vs. CA Rosario Central",
            "Draw (CA Tigre vs. CA Rosario Central)",
            "CA Tigre BA",
            "Rosario Central",
            0,
            1,
            "a draw leg correctly marked not-the-winner",
        ),
        (
            "Lausanne-Sport vs. Servette Geneva",
            "Draw (Lausanne-Sport vs. Servette Geneva)",
            "FC Lausanne-Sport",
            "Servette",
            0,
            1,
            "the same, with our name a superstring of the venue's",
        ),
    ],
)
def test_the_containment_requirement_is_also_a_safety_net(
    market_name, outcome_name, home, away, hs, as_, why
):
    """⭐ AND WHY THE UNDER-COVERAGE ABOVE IS NOT WORTH BUYING OUT.

    The obvious repair for the White Sox row is to match the market TITLE
    fuzzily too. These are the rows that answers: each one's outcome name
    fuzzy-matches one of our team names and not the other, so a title-fuzzy gate
    would read them as claiming a side and withhold a CORRECT verdict.

    Of the 9 rows the gate misses in the 10-day census, 3 are genuine misses and
    5 are these — rows it is right to refuse. A looser rule buys 3 and spends 5.
    """
    assert (
        _verdict_contradicts_the_final_score(
            _mkt(market_name),
            _out(outcome_name, is_winner=False),
            event_is_finished=True,
            home_team=home,
            away_team=away,
            home_score=hs,
            away_score=as_,
        )
        is False
    ), f"withheld a correct verdict: {why}"


def test_the_row_that_agrees_with_the_score_is_untouched():
    """`Colorado — Won` on the same card. Withholding is not erasing."""
    assert _fires("San Diego Padres vs. Colorado Rockies", "Colorado Rockies") is False


def test_the_loser_marked_lost_is_untouched():
    """`San Diego — Lost` is the true statement; the card keeps it."""
    assert _fires("Colorado vs San Diego", "San Diego", is_winner=False) is False


# ── ⭐ THE CONTROLS: 318 correct verdicts that must not move ────────────────


@pytest.mark.parametrize(
    "market_name,outcome_name,why",
    [
        (
            "Aryna Sabalenka vs Elena Rybakina: Set 2 Winner",
            "Aryna Sabalenka",
            "a player can win a set and lose the match",
        ),
        (
            "Crystal Palace vs Ipswich Town: First Team to Score",
            "Crystal Palace",
            "a team can score first and lose",
        ),
        (
            "Club Santos Laguna vs. FC Juárez - First Team to Score",
            "FC Juárez",
            "the ` - ` spelling of the same qualifier",
        ),
        (
            "Vancouver Whitecaps FC vs. Austin FC - 2nd Half First Team to Score",
            "Vancouver Whitecaps FC",
            "a half-scoped question",
        ),
        (
            "Cleveland vs Baltimore: First 5 Innings",
            "Cleveland",
            "a partial-game winner",
        ),
    ],
)
def test_a_question_the_score_cannot_answer_keeps_its_verdict(
    market_name, outcome_name, why
):
    """These are the 318. Each one names the losing side and each one is RIGHT.

    The market names here are production strings, and the teams are passed as the
    event stores them, so the refusal is the real predicate's on the real shape —
    not a hand-built string that happens to carry a colon.
    """
    home, away = market_name.split(" vs")[0].strip(), outcome_name
    assert (
        _verdict_contradicts_the_final_score(
            _mkt(market_name),
            _out(outcome_name),
            event_is_finished=True,
            home_team=home if home != outcome_name else "Some Other Team",
            away_team=away,
            home_score=5,
            away_score=1,
        )
        is False
    ), f"withheld a correct verdict: {why}"


def test_a_draw_leg_naming_both_sides_fails_open():
    """`Draw (VfB Stuttgart vs. Viking FK)` reaches BOTH team names.

    16 rows in the 10-day census. The row is not claiming either side, so the
    gate cannot say it disagrees — and #6604 is the ship that stops that leg
    being read as a team's price in the first place. Two defects, one string,
    and this one must not guess.
    """
    assert (
        _verdict_contradicts_the_final_score(
            _mkt("VfB Stuttgart vs. Viking FK"),
            _out("Draw (VfB Stuttgart vs. Viking FK)"),
            event_is_finished=True,
            home_team="VfB Stuttgart",
            away_team="Viking FK",
            home_score=2,
            away_score=1,
        )
        is False
    )


@pytest.mark.parametrize("outcome_name", ["Yes", "No", "Over", "Under", "Draw"])
def test_a_row_naming_neither_side_fails_open(outcome_name):
    """253 rows in the census. Nothing about them says which side they claim."""
    assert _fires("San Diego Padres vs. Colorado Rockies", outcome_name) is False


# ── Every missing signal fails open (CERT-2980's lesson, on the new arm) ────


@pytest.mark.parametrize(
    "over,why",
    [
        ({"event_is_finished": False}, "a live game — #6595's gate governs there"),
        ({"event_is_finished": None}, "we do not know whether it finished"),
        ({"home_score": None}, "no home score"),
        ({"away_score": None}, "no away score"),
        ({"home_score": 3, "away_score": 3}, "a draw is not a side to disagree with"),
        ({"home_team": None}, "no home name to match against"),
        ({"away_team": ""}, "no away name to match against"),
    ],
)
def test_a_missing_signal_never_strips_a_verdict(over, why):
    assert (
        _fires("San Diego Padres vs. Colorado Rockies", "San Diego Padres", **over)
        is False
    ), f"over-refused: {why}"


def test_an_unnamed_outcome_fails_open():
    assert (
        _verdict_contradicts_the_final_score(
            _mkt("San Diego Padres vs. Colorado Rockies"),
            _out(None),
            **_ctx(),
        )
        is False
    )


def test_a_suspended_game_with_a_partial_score_is_not_finished():
    """`_event_is_really_finished` admits only completed/closed, so the caller
    passes False here — pinned because a partial score is exactly the input that
    would look decisive and arbitrate a game that is still to be played.
    """
    assert (
        _fires(
            "San Diego Padres vs. Colorado Rockies",
            "San Diego Padres",
            event_is_finished=False,
        )
        is False
    )


# ── The gate is wired, and the two earlier gates still come first ───────────


def test_the_grade_function_withholds_the_contradicting_verdict():
    fields = _settled_grade_fields(
        _mkt("San Diego Padres vs. Colorado Rockies"),
        _out("San Diego Padres"),
        **_ctx(),
    )
    assert fields == {"is_winner": None, "resolution_source": None}


def test_the_payload_shape_never_varies():
    """Both keys always, whichever arm fires — a consumer reads shape, not arms."""
    for outcome_name in ("San Diego Padres", "Colorado Rockies", "Yes"):
        fields = _settled_grade_fields(
            _mkt("San Diego Padres vs. Colorado Rockies"), _out(outcome_name), **_ctx()
        )
        assert set(fields) == {"is_winner", "resolution_source"}


def test_an_unauthoritative_row_is_still_refused_first():
    """#2089's gate runs before this one and nothing here re-opens it."""
    fields = _settled_grade_fields(
        _mkt("San Diego Padres vs. Colorado Rockies"),
        _out("Colorado Rockies", resolution_source=None),
        **_ctx(),
    )
    assert fields["is_winner"] is None


def test_the_page_build_hands_every_grade_call_the_score():
    """The gate is only as wide as its adoption.

    `_grade_ctx` gained four keys; a serializer that kept an older dict would
    grade a finished game with no score and this ship would be inert exactly
    where it was measured. Read off the source, because an unconverted call site
    is invisible to every test that does not look for it.
    """
    import inspect

    from app.routes.events import _build_game_markets

    body = inspect.getsource(_build_game_markets)
    for key in ("home_team", "away_team", "home_score", "away_score"):
        assert f'"{key}": getattr(event, ' in body, (
            f"`_grade_ctx` no longer carries {key!r} — the finished-game gate "
            "cannot fire and every test above passes anyway"
        )
    assert body.count("_settled_grade_fields(market, o, **_grade_ctx)") == 5


def test_the_two_unconverted_call_sites_are_inert_for_a_stated_reason():
    """⭐ AN UNCONVERTED CALL SITE IS WHERE A GATE SILENTLY DOES NOT APPLY.

    Two callers of `_settled_grade_fields` pass no event context, so this gate
    cannot fire from them. #6595 could argue they were unreachable because they
    require a FINISHED event and its gate wanted an unfinished one. That argument
    inverts here — this gate wants a finished event — so each needs its own
    reason, and both are read off the source rather than assumed:

    * `_settled_margin_is_provable` ends on
      `proved is not None and proved is bool(grade["is_winner"])`, so it only
      returns True when the score and the venue AGREE. A contradicting row can
      never pass it, and firing this gate there would be redundant, not missing.
    * The #5771 predicate reads `resolution_source is None` to ask "is every
      outcome ungraded?". Withholding there would make a GRADED row read as
      ungraded and flip which markets that predicate calls settled — a behaviour
      change on a population this ship has not measured. Left on the raw grade
      deliberately.
    """
    import inspect

    from app.routes import events as events_module

    src = inspect.getsource(events_module)
    for call, guard, why in (
        (
            "grade = _settled_grade_fields(market, outcome)",
            'proved is not None and proved is bool(grade["is_winner"])',
            "the margin predicate no longer requires the score and the venue to "
            "agree, so a contradicting row can now reach it ungated",
        ),
        (
            '_settled_grade_fields(market, o)["resolution_source"] is None',
            "if not _event_is_really_finished(event, now):",
            "the #5771 predicate lost its finished-guard",
        ),
    ):
        assert call in src, (
            f"{call!r} has moved or been converted — if it now takes the event "
            f"context, re-measure it against this gate and delete its row here"
        )
        after = src.split(call, 1)[1]
        before = src.split(call, 1)[0]
        assert guard in after[:1200] or guard in before[-2000:], why


def test_the_gate_reuses_the_6604_predicate_rather_than_a_second_one():
    """One definition of "this market asks who won", not two.

    A locally-written variant here would drift from `find_moneyline_outcome`'s,
    and the two would disagree about the same string on the same page. Asserted
    on the source because the import is the whole point.
    """
    import inspect

    src = inspect.getsource(_verdict_contradicts_the_final_score)
    assert "outcome_name_is_the_whole_matchup" in src
    assert "_fuzzy_team_match" in src


# ── The route serves it, and the surface is still a surface ─────────────────


@pytest.fixture
async def finished_game_client():
    """Event 15312858's shape: a finished game carrying the previous night's
    Polymarket container beside its own correct Kalshi market, plus a
    sub-question market that must survive.
    """
    from app.main import app
    from app.routes.events import _game_markets_cache

    _game_markets_cache.clear()

    event = _make_event(
        id=15312858,
        home_team=HOME,
        away_team=AWAY,
        status="completed",
        sport_key="baseball_mlb",
        home_score=HOME_SCORE,
        away_score=AWAY_SCORE,
    )
    event.commence_time = datetime.now(timezone.utc) - timedelta(hours=6)
    event.completed_at = datetime.now(timezone.utc) - timedelta(hours=3)

    # The previous night's container, attached here one game late (#6627).
    stale = _make_futures_market(
        id=60485359, name="San Diego Padres vs. Colorado Rockies", source="polymarket"
    )
    # Our own market for this game, which is right.
    ours = _make_futures_market(
        id=60900811, name="San Diego vs Colorado", source="kalshi"
    )
    # A question the score cannot answer. It named the losing side and it is
    # correct; if this row loses its verdict the ship has eaten the 318.
    inning = _make_futures_market(
        id=60780234, name="San Diego vs Colorado: First Inning Run", source="kalshi"
    )
    for market in (stale, ours, inning):
        market.status = "resolved"
        market.event_id = event.id
        market.llm_sport_category = "baseball"
        market.settled_at = event.commence_time + timedelta(hours=3)
        market.resolution_date = event.commence_time + timedelta(hours=3)

    outcomes = [
        _make_outcome(
            id=1, market_id=60485359, name="San Diego Padres",
            probability=1.0, is_winner=True, resolution_source="api_settlement",
        ),
        _make_outcome(
            id=2, market_id=60900811, name="Colorado",
            probability=1.0, is_winner=True, resolution_source="api_settlement",
        ),
        _make_outcome(
            id=3, market_id=60900811, name="San Diego",
            probability=0.0, is_winner=False, resolution_source="api_settlement",
        ),
        _make_outcome(
            id=4, market_id=60780234, name="Yes",
            probability=0.99, is_winner=True, resolution_source="api_settlement",
        ),
    ]

    mock_session = _make_event_detail_session(
        event=event, futures=[stale, ours, inning], outcomes=outcomes
    )

    async def _mock_get_db():
        yield mock_session

    async def _mock_get_optional_user():
        return None

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_db_rw] = _mock_get_db
    app.dependency_overrides[get_optional_user] = _mock_get_optional_user

    with patch("app.main.init_db", new_callable=AsyncMock):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac

    _game_markets_cache.clear()
    app.dependency_overrides.clear()


def _all_rows(payload):
    rows = []
    for key in ("other", "spreads", "totals", "player_props"):
        rows.extend(payload.get(key) or [])
    for matchup in payload.get("matchups") or []:
        rows.extend(matchup.get("outcomes") or [])
    return rows


def _named(rows, needle):
    return [r for r in rows if needle in (r.get("outcome_name") or "")]


@pytest.mark.asyncio
async def test_the_finished_page_crowns_one_side(finished_game_client):
    resp = await finished_game_client.get("/api/events/15312858/game-markets")
    assert resp.status_code == 200
    rows = _all_rows(resp.json())

    # ⭐ PRESENCE FIRST. Every assertion below is vacuously true on an empty
    # payload, and a withholding gate is the kind of change that can empty one.
    assert rows, "the route served no outcome rows at all — this proves nothing"

    crowned = [r for r in rows if r.get("is_winner") is True]
    labels = sorted((r.get("outcome_name") or "") for r in crowned)
    assert "San Diego Padres" not in labels, (
        "the page still crowns the side its own scoreboard beat 9-3"
    )
    assert "Colorado" in labels, "the correct verdict was erased with the wrong one"


@pytest.mark.asyncio
async def test_the_withheld_row_keeps_its_name_and_its_price(finished_game_client):
    """Withheld, not dropped. A card whose only market is this one is still a card."""
    resp = await finished_game_client.get("/api/events/15312858/game-markets")
    padres = _named(_all_rows(resp.json()), "San Diego Padres")
    assert padres, "the row was DROPPED — the ship withholds the verdict, not the market"
    assert padres[0].get("is_winner") is None
    assert padres[0].get("resolution_source") is None
    assert padres[0].get("probability") is not None, "the price went with the verdict"


@pytest.mark.asyncio
async def test_the_losing_side_still_reads_lost(finished_game_client):
    """`San Diego — Lost` is true and is the card's other half."""
    resp = await finished_game_client.get("/api/events/15312858/game-markets")
    rows = _all_rows(resp.json())
    lost = [r for r in rows if r.get("is_winner") is False]
    assert any((r.get("outcome_name") or "") == "San Diego" for r in lost)


@pytest.mark.asyncio
async def test_the_sub_question_keeps_its_verdict_on_the_page(finished_game_client):
    """The route-level half of the 318 control.

    CERT-2980 blocked this gate's sibling because a unit test cleared a cohort
    the ROUTE did not, so the population that must survive is pinned where the
    reader meets it, not only where the predicate is called.
    """
    resp = await finished_game_client.get("/api/events/15312858/game-markets")
    yes_rows = [
        r for r in _all_rows(resp.json()) if (r.get("outcome_name") or "") == "Yes"
    ]
    assert yes_rows, "the First Inning Run market vanished from the page"
    assert yes_rows[0].get("is_winner") is True, (
        "a question the score cannot answer lost its verdict — this is the 318"
    )
