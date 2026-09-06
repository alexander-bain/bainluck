"""#3675 — the "Right now" row on `/search` stops offering a chip that says "Yes".

🔴 THE FIXTURE IS THE PRODUCTION ROW, NOT AN INVENTION, AND THAT IS LOAD-BEARING.

Every mover string below is copied verbatim out of
`.claude/handoff/_lat251-before-suggestions.json` — the eight chips
`GET /api/events/search-suggestions` served at 2026-09-06T20:31:57Z, captured by
the latency lane before any of this was written. Three of them share market
`60333165`, and that is the ONLY reason defect 3 is visible at all: a fabricated
fixture with one row per market cannot see a per-market cap that is missing,
because `_add`'s query-string dedup already hides the collision whenever the
strings differ — which three different handicap lines guarantee.

The row as production served it:

    1 Minnesota Twins      Starts in 1h                         §2
    2 Ole Miss Rebels      Starts in 2h                         §2
    3 Wisconsin Badgers    Starts in 2h                         §2
    4 Map Handicap: K27 (-1.5) vs Nordic Partners Gaming  (+1.5) §3  market 60333165
    5 Map 1 Rounds Handicap: K27 (-6.5) vs …                     §3  market 60333165
    6 Map 2 Rounds Handicap: K27 (-6.5) vs …                     §3  market 60333165
    7 Match Winner                                               §3  market 60337874
    8 Yes                                                        §3  market 60340114

Three defects, all section 3's own, and one test class each:

  1. the chip's `query` was `outcome.name` — so a binary prop shipped the word
     `Yes` as a search query, and a handicap shipped its whole market title;
  2. prop / handicap / total / map-line rows reached a discovery row at all;
  3. no per-market cap — one market took three of the eight slots.
"""

import re
from types import SimpleNamespace

import pytest

from app.routes.events import (
    _MAX_SUGGESTIONS,
    _SUGGESTION_MOVERS_LIMIT,
    _mover_chips,
    _suggestion_entity_name,
    _suggestion_is_prop_text,
)

# --------------------------------------------------------------------------
# the production rows
# --------------------------------------------------------------------------

_CS_FIXTURE = (
    "Counter-Strike: K27 vs Nordic Partners Gaming  (BO3) - PGL Masters "
    "Bucharest: European Open Qualifier #2 Playoffs"
)


def _outcome(name, *, market_id, market_name, change, event=None):
    return SimpleNamespace(
        name=name,
        market_id=market_id,
        probability_change_24h=change,
        market=SimpleNamespace(id=market_id, name=market_name, event=event),
    )


#: Chips 4-8 of the production row above, in the order the ranking returned them.
#: `_SUGGESTION_MOVERS_LIMIT` rows, because that is what the query asks for.
def _production_movers():
    return [
        _outcome(
            "Map Handicap: K27 (-1.5) vs Nordic Partners Gaming  (+1.5)",
            market_id=60333165,
            market_name=_CS_FIXTURE,
            change=0.999,
            # This market IS linked to an event — deliberately kept, because a
            # linked event is exactly the thing that could tempt an
            # implementation into printing a team name for a handicap row.
            event=SimpleNamespace(
                id=15306029,
                home_team_name="K27",
                away_team_name="Nordic Partners Gaming",
            ),
        ),
        _outcome(
            "Map 1 Rounds Handicap: K27 (-6.5) vs Nordic Partners Gaming  (+6.5)",
            market_id=60333165,
            market_name=_CS_FIXTURE,
            change=0.905,
            event=SimpleNamespace(
                id=15306029,
                home_team_name="K27",
                away_team_name="Nordic Partners Gaming",
            ),
        ),
        _outcome(
            "Map 2 Rounds Handicap: K27 (-6.5) vs Nordic Partners Gaming  (+6.5)",
            market_id=60333165,
            market_name=_CS_FIXTURE,
            change=0.810,
            event=SimpleNamespace(
                id=15306029,
                home_team_name="K27",
                away_team_name="Nordic Partners Gaming",
            ),
        ),
        _outcome(
            "Match Winner",
            market_id=60337874,
            market_name=(
                "Counter-Strike: KUUSAMO.gg vs Misa Esports (BO3) - ESL "
                "Challenger League Europe Cup #6 Group C"
            ),
            change=0.760,
        ),
        _outcome(
            "Yes",
            market_id=60340114,
            market_name="Map Handicap: HERO (-1.5) vs 1WIN (+1.5)",
            change=-0.722,
        ),
    ]


# --------------------------------------------------------------------------
# driving the real route (#3684)
# --------------------------------------------------------------------------

#: The eight live events section 1 rendered on production at 2026-09-06T20:50Z,
#: `home_team_name` / `away_team_name` exactly as `events` stores them. Five of
#: these eight collided under the old length-vs-probability split.
_PRODUCTION_LIVE_ROW = [
    ("Chicago Fire", "Vancouver Whitecaps FC"),
    ("Platense", "Deportivo Riestra"),
    ("Albuquerque Isotopes", "Tacoma Rainiers"),
    ("AFC Whyteleafe", "Crowborough Athletic FC"),
    ("Pumas", "León"),
    ("Memphis Redbirds", "Durham Bulls"),
    ("Round Rock Express", "Oklahoma City Comets"),
    ("El Paso Chihuahuas", "Las Vegas Aviators"),
]


class _Rows:
    def __init__(self, rows):
        self._rows = list(rows)

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class _DB:
    """Hands back queued results in call order, and RAISES on an unexpected one.

    Eight tight games fill the eight-slot window in section 1, so sections 2-5
    are skipped and exactly one statement runs. A double that returned an empty
    result for a statement the test did not expect would hide that.
    """

    def __init__(self, results):
        self._results = list(results)
        self.executed = []

    async def execute(self, q):
        self.executed.append(q)
        if not self._results:
            raise AssertionError(
                f"db.execute called {len(self.executed)} times; the fixture "
                f"queued {len(self.executed) - 1}"
            )
        return self._results.pop(0)


class _NoCacheRedis:
    """Always a miss, and accepts the write — the route must BUILD."""

    def get(self, key):
        return None

    def setex(self, key, ttl, payload):
        pass

    def delete(self, key):
        pass


def _run_route(pairs, *, blend=0.5):
    """Build the row from `pairs` through `search_suggestions` itself."""
    import asyncio

    import app.tasks.redis_state as redis_state
    from app.routes.events import search_suggestions

    live = [
        SimpleNamespace(
            id=i + 1,
            status="live",
            home_team_name=home,
            away_team_name=away,
            # Inside the 0.35-0.65 tight-game band, in the flat production shape
            # (see #3671 — the nested shape reads as no blend at all).
            win_probability_sources={"betting": blend},
            opening_home_probability=None,
            espn_win_prob_home=None,
        )
        for i, (home, away) in enumerate(pairs)
    ]

    original = redis_state.get_redis_client
    redis_state.get_redis_client = lambda: _NoCacheRedis()
    try:
        return asyncio.run(search_suggestions(db=_DB([_Rows(live)])))
    finally:
        redis_state.get_redis_client = original


#: The five outcome-label strings #3675's acceptance names by hand, plus the
#: shapes a market title takes. Asserted against every chip, not just §3's.
_FORBIDDEN_QUERIES = {"yes", "no", "match winner", "over", "under"}


def _looks_like_a_market_title(query: str) -> bool:
    return bool(
        ":" in query
        or " vs " in query.lower()
        or re.search(r"\(\s*[-+]\s*\d", query)
        or len(query) > 40
    )


# --------------------------------------------------------------------------
# 0 — certify the fixture before trusting what it proves
# --------------------------------------------------------------------------


def test_the_fixture_is_the_production_row_and_not_a_convenience():
    rows = _production_movers()
    assert len(rows) == _SUGGESTION_MOVERS_LIMIT, (
        "the fixture must be the full ask of the query, or 'section 3 emitted "
        "nothing' could just mean 'the fixture ran out'"
    )
    from collections import Counter

    per_market = Counter(r.market_id for r in rows)
    assert per_market[60333165] == 3, (
        "defect 3 is invisible without three rows from ONE market — that is the "
        "whole point of copying the production row instead of writing one"
    )
    assert {r.name for r in rows} >= {"Yes", "Match Winner"}, (
        "the two chips #3675 was filed about must be in the fixture"
    )
    assert len({r.name for r in rows}) == len(rows), (
        "all five strings differ, which is why `_add`'s query dedup could never "
        "have caught the market collision"
    )


def test_the_old_behaviour_would_fail_this_file():
    """The pre-fix loop emitted `outcome.name`. Prove that row is now refused.

    Without this, every assertion below could be satisfied by a function that
    returns an empty list for reasons unrelated to the three defects.
    """
    for row in _production_movers():
        assert row.name.lower() in _FORBIDDEN_QUERIES or _looks_like_a_market_title(
            row.name
        ), f"fixture row {row.name!r} was not one of the strings #3675 objected to"


# --------------------------------------------------------------------------
# 1 — the three acceptance clauses, over the production row
# --------------------------------------------------------------------------


def test_no_chip_query_is_an_outcome_label_or_a_market_title():
    """Acceptance clause 1. `Yes`, `Match Winner`, and the three handicap titles."""
    for chip in _mover_chips(_production_movers()):
        assert chip["query"].lower() not in _FORBIDDEN_QUERIES, (
            f"chip query {chip['query']!r} is an outcome label — tapping it runs "
            f"/search?q={chip['query']}"
        )
        assert not _looks_like_a_market_title(chip["query"]), (
            f"chip query {chip['query']!r} is a market title, not something a "
            "person would type"
        )


def test_no_market_id_contributes_more_than_one_chip():
    """Acceptance clause 2. Market 60333165 took chips 4, 5 and 6 of eight.

    Driven with a corpus where the shared market SURVIVES the display rule, so
    the cap is proved on its own rather than as a side effect of the refusal.
    """
    rows = [
        _outcome("Cormac Sharvin", market_id=1, market_name="Amgen Irish Open Winner", change=-0.29),
        _outcome("Connor Syme", market_id=1, market_name="Amgen Irish Open Winner", change=-0.29),
        _outcome("Dan Bradbury", market_id=1, market_name="Amgen Irish Open Winner", change=-0.29),
        _outcome("Daniel Brown", market_id=1, market_name="Amgen Irish Open Winner", change=-0.29),
        _outcome("Denver", market_id=2, market_name="Where will it rain this weekend?", change=-0.41),
    ]
    chips = _mover_chips(rows)
    market_ids = [c["market_id"] for c in chips]
    assert len(market_ids) == len(set(market_ids)), (
        f"one market supplied more than one chip: {market_ids}. `_add` dedups on "
        "the query STRING and four different golfers defeat it trivially"
    )
    assert [c["query"] for c in chips] == ["Cormac Sharvin", "Denver"], (
        "the cap must keep the FIRST (biggest-moving) row of a market, not drop "
        f"the market: {[c['query'] for c in chips]}"
    )


@pytest.mark.parametrize(
    "text",
    [
        "Map Handicap: K27 (-1.5) vs Nordic Partners Gaming  (+1.5)",
        "Map 1 Rounds Handicap: K27 (-6.5) vs Nordic Partners Gaming  (+6.5)",
        "Map 2 Rounds Handicap: K27 (-6.5) vs Nordic Partners Gaming  (+6.5)",
        "Map Handicap: HERO (-1.5) vs 1WIN (+1.5)",
        "Counter-Strike: Heroic vs 1WIN - Map 2 Winner",
        "Games Total: O/U 2.5",
        "O/U 2.5 Games",
        "Map 3 Total Rounds: Over/Under 21.5",
        "Map 1 Winner",
        "Alternate Spread",
    ],
)
def test_prop_and_handicap_rows_are_refused(text):
    """Acceptance clause 3, on BOTH sides of the row.

    Production had it both ways round in the same read: outcome
    `Map Handicap: HERO (-1.5) vs 1WIN (+1.5)` under market `Counter-Strike:
    Heroic vs 1WIN`, and outcome `Yes` under market `Map Handicap: HERO (-1.5)
    vs 1WIN (+1.5)`. A rule applied to one side passes half of them through.
    """
    assert _suggestion_is_prop_text(text), f"{text!r} must be refused as a prop row"

    as_outcome = _mover_chips([_outcome(text, market_id=1, market_name="Some Market", change=0.9)])
    assert as_outcome == [], f"{text!r} reached a chip as an OUTCOME name"

    as_market = _mover_chips([_outcome("Real Entity", market_id=1, market_name=text, change=0.9)])
    assert as_market == [], f"{text!r} reached a chip as a MARKET name"


def test_the_production_row_yields_no_section_3_chips_at_all():
    """All five of production's movers are refused, and that is the correct answer.

    Not a happy accident and not a broken filter — see the constant block above
    `_SUGGESTION_SIDE_LABELS` for why widening the scan until something survives
    was considered and rejected. The five freed slots go to section 5, which
    ranks by `volume_24h` rather than by thinness.
    """
    assert _mover_chips(_production_movers()) == []


# --------------------------------------------------------------------------
# 2 — the section is filtered, NOT switched off (#2286's disease, avoided)
# --------------------------------------------------------------------------


def test_a_mover_that_names_an_entity_still_becomes_a_chip():
    chips = _mover_chips(
        [_outcome("Cormac Sharvin", market_id=7, market_name="Amgen Irish Open Winner", change=-0.29)]
    )
    assert chips == [
        {
            "query": "Cormac Sharvin",
            "label": "Falling -29.0% — Amgen Irish Open Winner",
            "market_id": 7,
        }
    ]


def test_a_linked_event_supplies_the_team_name_the_way_sections_1_2_and_4_do():
    """The entity comes from the EVENT first — `Match Winner` is not printable,
    but the game it belongs to is, and that is the resolution order #3675 asked
    for. Shorter of the two names, identical to `_shorter_team`."""
    chips = _mover_chips(
        [
            _outcome(
                "Match Winner",
                market_id=9,
                market_name="Red Sox at Yankees — Winner",
                change=0.12,
                event=SimpleNamespace(
                    id=1, home_team_name="New York Yankees", away_team_name="Red Sox"
                ),
            )
        ]
    )
    assert [c["query"] for c in chips] == ["Red Sox"]


def test_a_prop_row_is_refused_even_when_its_event_could_have_named_a_team():
    """Order matters: the display rule runs BEFORE the entity lookup.

    Market 60333165 is linked to event 15306029, so an implementation that
    resolved the entity first would happily print `K27` for a rounds-handicap
    row — a real team name on a chip that must not exist.
    """
    assert _mover_chips(_production_movers()[:3]) == []


def test_the_chip_cap_is_the_sections_own_limit():
    rows = [
        _outcome(f"Player {i}", market_id=i, market_name=f"Open {i} Winner", change=0.9 - i / 100)
        for i in range(_SUGGESTION_MOVERS_LIMIT + 3)
    ]
    assert len(_mover_chips(rows)) == _SUGGESTION_MOVERS_LIMIT
    assert _SUGGESTION_MOVERS_LIMIT < _MAX_SUGGESTIONS, (
        "section 3 must never be able to fill the window on its own — that is "
        "how sections 4 and 5 got nothing on 2026-09-06"
    )


# --------------------------------------------------------------------------
# 3 — the entity rule itself
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name", ["Yes", "No", "yes", "  Over  ", "Under", "Match Winner", "Draw", "Winner"]
)
def test_side_labels_never_name_an_entity(name):
    assert _suggestion_entity_name(name) is None


@pytest.mark.parametrize(
    "name",
    [
        "W15 Porto Velho: Maayan Laron vs Ana Candiotto",
        "Counter-Strike: KUUSAMO.gg vs Misa Esports (BO3) - ESL Challenger League",
        "Will Alexandra Eala advance to the Round of 16 at the 2026 US Open?",
    ],
)
def test_market_titles_never_name_an_entity(name):
    assert _suggestion_entity_name(name) is None


@pytest.mark.parametrize(
    "name", ["Cormac Sharvin", "Maayan Laron", "Denver", "Houston", "Boston Red Sox"]
)
def test_real_entities_survive(name):
    assert _suggestion_entity_name(name) == name


def test_whitespace_is_collapsed_not_rejected():
    """Production names carry doubled spaces (`Nordic Partners Gaming  (+1.5)`)."""
    assert _suggestion_entity_name("  Cormac   Sharvin ") == "Cormac Sharvin"


def test_an_empty_or_numeric_outcome_names_nothing():
    for name in ["", "   ", "2.5", "-1.5", None]:
        assert _suggestion_entity_name(name) is None


# --------------------------------------------------------------------------
# 4 — the display rule is not the matcher's rule
# --------------------------------------------------------------------------


def test_the_display_rule_is_written_here_and_not_borrowed_from_the_matcher():
    """🔴 A MATCHER HELPER IS PERMISSIVE BY DESIGN AND IS THE WRONG TOOL HERE.

    The matcher's prop helpers exist to ACCEPT a prop row so it can be linked to
    its market. This surface has to REFUSE exactly those rows. Importing one
    here would look like reuse and would silently invert the requirement the
    first time the matcher was loosened to link one more prop shape — a change
    that has every reason to happen and no reason to consider `/search`.

    So: `_suggestion_is_prop_text` must not delegate. Asserted on the source,
    because the coupling is the defect and a behavioural test cannot see it.
    """
    import inspect

    src = inspect.getsource(_suggestion_is_prop_text)
    for forbidden in ("prediction_market_matching", "cross_source_matching", "import "):
        assert forbidden not in src, (
            f"`_suggestion_is_prop_text` reaches for {forbidden!r}. A display "
            "rule owns its own list; see the comment on _SUGGESTION_PROP_MARKERS"
        )


def test_no_section_1_chip_says_a_team_is_playing_itself():
    """#3684 — `León  Live — tight game vs León`, live on production 20:50Z.

    Found by the post-deploy LOOK on #2286's own repair, in five of the eight
    chips. Section 1 picked the chip's text by NAME LENGTH and the opponent by
    PROBABILITY, and whenever the two rules landed on the same side the chip
    named one team twice.

    The eight pairs below are the events the row actually rendered, read out of
    `events` at the same minute — so this fixture is the production row and not
    a constructed collision. `home` first, as stored.

    Driven through the ROUTE rather than through a re-derivation of its two
    lines: a test that recomputes `short` and `opponent` itself would stay green
    no matter what the route went on to render, which is the failure mode that
    let this ship in the first place.
    """
    resp = _run_route(_PRODUCTION_LIVE_ROW)
    labels = [s["label"] for s in resp["suggestions"]]
    assert len(labels) == len(_PRODUCTION_LIVE_ROW), (
        f"section 1 must produce a chip per tight game: {labels}"
    )
    for chip in resp["suggestions"]:
        opponent = chip["label"].split(" vs ", 1)[1]
        assert opponent != chip["query"], (
            f"chip reads {chip['query']!r} — {chip['label']!r}: a team playing "
            "itself"
        )


def test_an_ordinary_market_name_is_not_mistaken_for_a_prop():
    """The refusal list must not eat section 3's remaining reason to exist."""
    for ok in [
        "Amgen Irish Open Winner",
        "US Open Men's Singles Winner",
        "Presidential Election Winner 2028",
        "Where will it rain this weekend (Sep 5 - Sep 6)?",
        "College Football National Championship",
    ]:
        assert not _suggestion_is_prop_text(ok), f"{ok!r} is not a prop row"
