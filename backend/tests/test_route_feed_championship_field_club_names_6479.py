"""The FEED card on a championship board spells the club (#6479, feed half).

#6479 repaired the two surfaces that render a board's rungs as a LIST (the detail
ladder and the search card) and #6513 repaired the chart legend. The feed is the
FOURTH reader path — and the only one on page one.

WHAT THE READER SAW, ON PRODUCTION, 2026-09-16
==============================================

`https://bainluck.com/sports`, futures section::

    2027 Pro Football Champion
    Los Angeles R leads at 11%          ← the card's own headline
      Los Angeles R   11%
      Buffalo          9%

and, further down, `Pro Baseball Champion` headlined `Los Angeles D leads at
31%`. Neither `Los Angeles R` nor `Los Angeles D` is a club.

Measured against the served payload the same morning: of 330 feed-surfaced
outcomes across `mode=sports`, `mode=discover` and the default edition, **3** are
rows the shipped engine repairs and the feed did not — `KXSB-27-LAR`,
`KXMLB-26-LAD`, `KXMLB-26-NYY` — and **2 of the 3 reached the card headline**.
Behind them the two boards carry 10 repairable rungs (40533: 4, 275: 6), which is
what the distribution (top 8) and the `remaining_outcome_count` ladder draw from.

WHY THE GUARD STANDS AT THE SCORER AND NOT AT `_card_outcome_name`
==================================================================

Because the defect was never in the engine — the engine has been correct and
unit-tested since #6479 (`test_championship_field_club_names_6479`). The defect
was that seven label sites in two serializers did not call it. A test of the
helper passes just as happily with every call site reverted, which is precisely
the state production was in this morning. So these tests run the real scorers and
read the served dict, the same lesson `test_score_futures_serves_no_diagnostic_
headline_4160` records: **a repair on a producer is not a repair on a surface.**

THE CONTROLS, AND WHY THEY ARE NOT DECORATION
=============================================

An over-reaching fix — "complete every label" — is a worse bug than the one it
replaces, because a wrong club name is invisible where a short one is not. Three
controls fail under that mutant:

* `Buffalo` / `Baltimore` — real names, must survive byte for byte.
* `Chicago C` on ticker `KXMLB-26-CWS` — the shipped text says Cubs and the
  ticker says White Sox, so the engine refuses and the rung STAYS truncated.
* an outcome with no ticker at all (`external_id=None`) — the Polymarket shape.

THE ASSERTION THAT IS NOT ABOUT THE LABEL
=========================================

Repairing a name is only safe if nothing MATCHES on it. The dedup key
(`drop_dominant_field_outcomes`), the saved-team predicate (`_team_name_matches`)
and the feature-token derivations all read `o.name` off the ORM and deliberately
still do — they are compared against provider text, not read by anyone. The last
test pins that split so a later "tidy-up" cannot quietly route them through the
repair as well.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routes.feed import _score_futures, _score_sports_mode_futures
from app.utils.personalization import PersonalizationContext

SUPER_BOWL_KEY = "football::championship:2027"

#: `(id, ticker, shipped name, probability)` — the production rows of
#: `futures_markets` 40533 (`KXSB-27`), read 2026-09-16. `Buffalo` and
#: `Baltimore` are controls: real names that must survive byte for byte, and
#: proof the predicate is not simply never firing.
SUPER_BOWL_RUNGS = [
    (643828, "KXSB-27-LAR", "Los Angeles R", 0.1086),
    (643833, "KXSB-27-BUF", "Buffalo", 0.086),
    (643841, "KXSB-27-BAL", "Baltimore", 0.0679),
    (643832, "KXSB-27-LAC", "Los Angeles C", 0.035),
]

#: The completions the engine makes, asserted by name rather than by shape so a
#: mutant that returns "Los Angeles" or "Los Angeles RAMS" is caught.
EXPECTED = {
    "Los Angeles R": "Los Angeles Rams",
    "Los Angeles C": "Los Angeles Chargers",
    "Los Angeles D": "Los Angeles Dodgers",
    "New York Y": "New York Yankees",
}

#: Left alone by the engine, for three different reasons: already a club, and
#: (below) a ticker that contradicts the shipped text.
UNTOUCHED = ["Buffalo", "Baltimore"]


class _Outcome:
    def __init__(self, id, name, probability, external_id):
        self.id = id
        self.name = name
        self.external_id = external_id
        self.current_probability = probability
        self.probability_change_24h = 0.0
        self.opening_probability = None
        self.rank = None
        self.rank_change_24h = None
        self.team_id = None
        self.calibration_probability = None
        self.current_yes_bid = None
        self.current_yes_ask = None


class _Market:
    """A real object so `__dict__.get(...)` reads work, as in #250's harness."""

    def __init__(self, id, *, outcomes, name, key, category="football"):
        now = datetime.now(timezone.utc)
        self.id = id
        self.name = name
        self.source = "kalshi"
        self.external_id = "KXSB-27"
        self.sport_id = None
        self.sport = None
        self.category = "sports"
        self.llm_sport_category = category
        self.market_tier = 1
        self.canonical_market_key = key
        self.group_id = None
        self.group_type = None
        self.image_url = None
        self.hook_description = None
        self.hook_generated_at = None
        self.hook_leader_at_generation = None
        self.market_metadata = {}
        self.curation_score_adj = 0
        self.volume_24h = 250000
        self.updated_at = now
        self.commence_time = now - timedelta(days=1)
        self.resolution_date = now + timedelta(days=120)
        self.status = "open"
        self.created_at = now - timedelta(days=10)
        self.llm_league = None
        self.llm_gender = None
        self.llm_level = None
        self.outcomes = outcomes


def _board(rungs=SUPER_BOWL_RUNGS, *, name="2027 Pro Football Champion"):
    return _Market(
        40533,
        outcomes=[_Outcome(i, n, p, t) for i, t, n, p in rungs],
        name=name,
        key=SUPER_BOWL_KEY,
    )


def _mock_db(markets):
    db = AsyncMock()

    def make_result(*a, **k):
        r = MagicMock()
        scalars = MagicMock()
        scalars.all.return_value = [m.id for m in markets]
        unique = MagicMock()
        unique.all.return_value = markets
        scalars.unique.return_value = unique
        r.scalars.return_value = scalars
        r.all.return_value = []
        return r

    db.execute = AsyncMock(side_effect=make_result)
    return db


async def _serve_discover(markets):
    with (
        patch(
            "app.routes.feed._external_curator_recall_market_ids",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "app.routes.feed._get_canonical_source_counts",
            new=AsyncMock(return_value={SUPER_BOWL_KEY: 2}),
        ),
        patch(
            "app.tasks.redis_state.get_async_redis_client",
            side_effect=Exception("no redis in test"),
        ),
    ):
        return await _score_futures(
            _mock_db(markets),
            datetime.now(timezone.utc),
            None,
            PersonalizationContext(),
        )


async def _serve_sports(markets):
    with (
        patch(
            "app.routes.feed._get_canonical_source_counts",
            new=AsyncMock(return_value={SUPER_BOWL_KEY: 2}),
        ),
        patch(
            "app.tasks.redis_state.get_async_redis_client",
            side_effect=Exception("no redis in test"),
        ),
    ):
        return await _score_sports_mode_futures(
            _mock_db(markets),
            datetime.now(timezone.utc),
            None,
            PersonalizationContext(),
        )


def _card(items):
    assert items, "the fixture board did not survive scoring — the rig, not the ship"
    return items[0]


def _labels(item) -> list[str]:
    """Every outcome string the card prints, from all three label surfaces."""
    data = item["data"]
    out = [o["name"] for o in (data.get("top_outcomes") or [])]
    dc = data.get("discover_card") or {}
    out += [o["label"] for o in (dc.get("distribution_outcomes") or [])]
    return out


def _prose(item) -> str:
    data = item["data"]
    return " | ".join(
        str(v or "")
        for v in (
            item.get("headline"),
            item.get("reason"),
            data.get("context_summary"),
        )
    )


# ─────────────────────────────────────────────────────────────────────────────
# THE SHIP: the four reader surfaces of a feed card name the club
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("serve", [_serve_discover, _serve_sports])
async def test_a_feed_cards_mini_list_names_the_club_6479(serve):
    card = _card(await serve([_board()]))
    printed = [o["name"] for o in card["data"]["top_outcomes"]]

    assert "Los Angeles Rams" in printed
    assert "Los Angeles R" not in printed


@pytest.mark.asyncio
@pytest.mark.parametrize("serve", [_serve_discover, _serve_sports])
async def test_a_feed_cards_headline_names_the_club_6479(serve):
    """The defect's loudest surface: `Los Angeles R leads at 11%`."""
    prose = _prose(_card(await serve([_board()])))

    assert "Los Angeles Rams" in prose
    # Substring, deliberately: `Los Angeles R` is a PREFIX of the repaired name,
    # so the test has to look for it where it is NOT followed by the completion.
    assert "Los Angeles R " not in prose.replace("Los Angeles Rams", "«ok»")
    assert not prose.replace("Los Angeles Rams", "«ok»").endswith("Los Angeles R")


@pytest.mark.asyncio
@pytest.mark.parametrize("serve", [_serve_discover, _serve_sports])
async def test_the_distribution_labels_name_the_club_6479(serve):
    card = _card(await serve([_board()]))
    dc = card["data"].get("discover_card") or {}
    labels = [o["label"] for o in (dc.get("distribution_outcomes") or [])]

    assert labels, "no distribution drawn — the archetype changed, re-pin the rig"
    assert "Los Angeles R" not in labels
    assert "Los Angeles Rams" in labels


@pytest.mark.asyncio
@pytest.mark.parametrize("serve", [_serve_discover, _serve_sports])
async def test_every_truncated_rung_on_the_board_is_completed_6479(serve):
    """Not just the leader — `Los Angeles C` is four rungs down and also a lie."""
    labels = _labels(_card(await serve([_board()])))

    assert "Los Angeles Chargers" in labels
    assert "Los Angeles C" not in labels


@pytest.mark.asyncio
async def test_the_my_teams_list_names_the_club_6479():
    """`matched_outcomes` — a reader's OWN team, printed half-named.

    Reachable because `names_match("Los Angeles Rams", "Los Angeles R")` is True
    (the city carries it), so a reader who saved the Rams DID match this rung and
    was then shown `Los Angeles R` back as the thing they follow. This surface is
    behind a session, so it cannot be photographed (notice 49) — which is exactly
    why it needs a test rather than a LOOK.
    """
    with (
        patch(
            "app.routes.feed._external_curator_recall_market_ids",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "app.routes.feed._get_canonical_source_counts",
            new=AsyncMock(return_value={SUPER_BOWL_KEY: 2}),
        ),
        patch(
            "app.tasks.redis_state.get_async_redis_client",
            side_effect=Exception("no redis in test"),
        ),
    ):
        items = await _score_futures(
            _mock_db([_board()]),
            datetime.now(timezone.utc),
            None,
            # `user_team_ids` is read off `team_relations`, and the branch is
            # gated on `my_teams_only AND user_team_ids` — a name-only reader
            # never reaches it, so both have to be present for the rig to fire.
            PersonalizationContext(team_relations={4242: "follow"}),
            my_teams_only=True,
            my_team_names=["Los Angeles Rams"],
        )

    matched = _card(items)["data"].get("matched_outcomes")
    assert matched, "the my-teams branch did not fire — the rig, not the ship"
    names = [o["name"] for o in matched]
    assert "Los Angeles Rams" in names
    assert "Los Angeles R" not in names


# ─────────────────────────────────────────────────────────────────────────────
# THE CONTROLS: an over-reaching completion fails all three
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("serve", [_serve_discover, _serve_sports])
async def test_a_real_club_name_survives_byte_for_byte_6479(serve):
    labels = _labels(_card(await serve([_board()])))

    for control in UNTOUCHED:
        assert control in labels, f"{control!r} was rewritten by an over-reaching fix"


@pytest.mark.asyncio
async def test_a_rung_whose_ticker_contradicts_its_text_stays_truncated_6479():
    """`Chicago C` under ticker `CWS`: shipped says Cubs, ticker says White Sox.

    The engine refuses without both signals, and the feed must not paper over
    that refusal. A short name is visibly short; a wrong one is not.
    """
    board = _Market(
        275,
        outcomes=[
            _Outcome(700005, "Chicago C", 0.31, "KXMLB-26-CWS"),
            _Outcome(700002, "New York Y", 0.2, "KXMLB-26-NYY"),
            _Outcome(700009, "St. Louis", 0.1, "KXMLB-26-STL"),
        ],
        name="Pro Baseball Champion",
        key=SUPER_BOWL_KEY,
        category="baseball",
    )
    labels = _labels(_card(await _serve_discover([board])))

    assert "Chicago C" in labels
    assert "Chicago Cubs" not in labels
    assert "Chicago White Sox" not in labels
    # …while its sibling on the same board, whose ticker AGREES, is completed.
    # Without this the test passes on a fix that was simply reverted.
    assert "New York Yankees" in labels
    assert "New York Y" not in labels


@pytest.mark.asyncio
async def test_an_outcome_with_no_ticker_ships_what_the_venue_sent_6479():
    """The Polymarket shape: no Kalshi rung ticker, so nothing to resolve."""
    board = _Market(
        99,
        outcomes=[
            _Outcome(1, "Los Angeles R", 0.4, None),
            _Outcome(2, "Buffalo", 0.3, None),
        ],
        name="2027 Pro Football Champion",
        key=SUPER_BOWL_KEY,
    )
    labels = _labels(_card(await _serve_discover([board])))

    assert "Los Angeles R" in labels
    assert "Los Angeles Rams" not in labels


# ─────────────────────────────────────────────────────────────────────────────
# THE SPLIT: label sites repair, matching sites do not
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("serve", [_serve_discover, _serve_sports])
async def test_completing_a_club_does_not_change_the_card_format_6479(serve):
    """The repair is a label change, not a ranking or archetype change.

    `classify_discover_card_archetype` re-derives its own labels through
    `display_outcome_names` (#4151) and picks the card format off
    `_threshold_points`, which parses NUMBERS out of outcome names. Neither
    `Los Angeles R` nor `Los Angeles Rams` carries one, so the chosen format must
    be identical with and without the completion — asserted here rather than
    argued in the commit message, because "it cannot matter" is how the threshold
    ladder in #4226 got parsed out of model version numbers.
    """
    repaired = _card(await serve([_board()]))["data"]["discover_card"]
    raw_rungs = [(i, t, n, p) for i, t, n, p in SUPER_BOWL_RUNGS]
    with patch("app.routes.feed._card_outcome_name", side_effect=lambda o: o.name):
        unrepaired = _card(await serve([_board(raw_rungs)]))["data"]["discover_card"]

    assert repaired["suggested_format"] == unrepaired["suggested_format"]
    assert sorted(repaired["reasons"]) == sorted(unrepaired["reasons"])
    assert repaired["threshold_points"] == unrepaired["threshold_points"]
    assert len(repaired["distribution_outcomes"]) == len(
        unrepaired["distribution_outcomes"]
    )
    assert [o["probability"] for o in repaired["distribution_outcomes"]] == [
        o["probability"] for o in unrepaired["distribution_outcomes"]
    ]
    # …and the labels DID move, so this is not two identical payloads agreeing.
    assert [o["label"] for o in repaired["distribution_outcomes"]] != [
        o["label"] for o in unrepaired["distribution_outcomes"]
    ]


def test_the_matching_predicates_still_read_the_raw_provider_name_6479():
    """`_card_outcome_name` is for PRINTED values only.

    `drop_dominant_field_outcomes` dedups on the shipped string and
    `_team_name_matches` compares a reader's saved team against it; both are
    matched against provider text, so routing them through the repair would
    change what a card SURFACES, not merely what it says. This asserts the two
    stay on `o.name` — the property the helper's docstring claims.
    """
    import inspect
    import re

    from app.routes import feed as feed_module

    for fn_name in ("_score_futures", "_score_sports_mode_futures"):
        src = inspect.getsource(getattr(feed_module, fn_name))
        assert re.search(
            r"drop_dominant_field_outcomes\(\s*\n?\s*[\w\[\]:.]+,\s*\n?\s*lambda o: o\.name,",
            src,
        ), f"{fn_name}: the dedup key stopped reading the raw provider name"
        assert "_team_name_matches(team_name, o.name)" in src, (
            f"{fn_name}: the saved-team predicate stopped reading the raw name"
        )
