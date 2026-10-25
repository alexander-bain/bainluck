"""#5349 — an award category's result is announced only by an independent settlement.

PILLARS: TRUTH / MATCHING / DISCOVER.
SHIP: People see an announced category result only when an identifiable authority
named it; a price crown, a clock rule, a guess or a retracted grade never reads as
a winner, and one category never settles a sibling or the ceremony.

Specimen provenance (packet `artifacts/fable-awards-5349-next-slice-20261024/`):

* SOURCED-VENUE rows copy what production's public market API served on
  2026-10-25 04:00-04:22Z (Sat Oct 24, 9:00-9:22 PM PT) for the named market ids:
  status, outcome names, prices, `is_winner` and `resolution_source`. Only the
  rows a test needs are kept.
* SOURCED-OFFICIAL notes cite the Television Academy's own winners releases
  (Sept 5, 6 and 14, 2026). They are evaluation context, never adapter input.
* SYNTHETIC rows are labelled mutations of a sourced row.

Nothing here reads a provider, a database, a calendar or a clock.
"""

from types import SimpleNamespace

import pytest

from app.utils.event_awards import (
    EVIDENCE_NONE,
    EVIDENCE_RETRACTED_GRADE,
    EVIDENCE_UNCONFIRMED_GRADE,
    EVIDENCE_VENUE_SETTLEMENT,
    RESULT_ANNOUNCED,
    RESULT_CLOSED,
    RESULT_PENDING,
    AwardsEventAdapter,
    category_result,
    is_result_grade,
)


def _o(name, probability, won=False, source=None):
    return SimpleNamespace(
        name=name,
        current_probability=probability,
        is_winner=won,
        resolution_source=source,
        last_updated=None,
    )


def _market(id_, name, ticker, outcomes, *, status="open"):
    return SimpleNamespace(
        id=id_,
        name=name,
        external_id=ticker,
        status=status,
        source="kalshi",
        resolution_date=None,
        outcomes=list(outcomes),
    )


class _Result:
    def __init__(self, markets):
        self.markets = markets

    def scalars(self):
        return self

    def unique(self):
        return self

    def all(self):
        return self.markets


class _DB:
    def __init__(self, markets):
        self.markets = markets

    async def execute(self, query):
        return _Result(self.markets)


async def _build(markets, slug):
    return await AwardsEventAdapter().build_event(slug, _DB(markets))


def _children(body):
    return {c["market_id"]: c for c in body["children"]}


def _won(child):
    return [o["name"] for o in child["outcomes"] if o["won"]]


def _reader_state(child):
    """The web reader's own rule, `frontend/lib/eventConceptDisplay.ts`
    `awardsResult` (2f18107550a5:1143-1146), restated so the served `result.state`
    is pinned to what the page already derives from `won` and `settled`."""
    if any(o.get("won") is True and (o.get("name") or "").strip() for o in child["outcomes"]):
        return "announced"
    return "closed" if child.get("settled") is True else "pending"


# SOURCED-VENUE: 9750359 KXEMMYDSERIES-26SEP14, resolved. SOURCED-OFFICIAL: the
# Television Academy's Sept 14, 2026 release names THE PITT Outstanding Drama Series.
def _emmys_drama_series(winner_source="api_settlement"):
    return _market(
        9750359,
        "Emmy Winner: Outstanding Drama Series",
        "KXEMMYDSERIES-26SEP14",
        [
            _o("The Pitt", 1.0, True, winner_source),
            _o("Euphoria", 0.0, False, "api_settlement"),
            _o("Task", 0.0, False, "api_settlement"),
            _o("The Morning Show", 0.0, False, "api_settlement"),
            _o("The Testaments", 0.0, False, "api_settlement"),
            _o("Tie", 0.0, False, "api_settlement"),
        ],
        status="resolved",
    )


# SOURCED-VENUE: 59172874 KXEMMY-GADS26SEP14 (Creative Arts night 2, Sept 6;
# the venue's own settlement is stamped 2026-09-07T22:05:48Z).
def _emmys_guest_actor_drama():
    return _market(
        59172874,
        "Emmy winner: Outstanding Guest Actor in a Drama Series",
        "KXEMMY-GADS26SEP14",
        [
            _o("Ernest Harden, Jr.", 1.0, True, "api_settlement"),
            _o("Jonathan Pryce", 0.0, False, "api_settlement"),
            _o("Jeff Hiller", 0.0, False, "api_settlement"),
        ],
        status="resolved",
    )


# SOURCED-VENUE: 33284725 KXEMMYNOMS-26-DS, the venue's nominations market. It
# listed 13 programs and settled 7 as nominated; the Academy's July 8, 2026 list
# also nominated "Your Friends & Neighbors", which this market never listed.
def _emmys_drama_nominations():
    nominated = [
        "Pluribus", "The Diplomat", "A Knight of the Seven Kingdoms",
        "The Gilded Age", "The Pitt", "Slow Horses", "Paradise",
    ]
    not_nominated = [
        "Task", "Industry", "Euphoria", "The Morning Show", "The Testaments",
        "Stranger Things",
    ]
    return _market(
        33284725,
        "Emmy nominees: Outstanding Drama Series",
        "KXEMMYNOMS-26-DS",
        [_o(n, 0.99, True, "api_settlement") for n in nominated]
        + [_o(n, 0.02, False, "api_settlement") for n in not_nominated],
        status="resolved",
    )


# SOURCED-VENUE: 59164593 KXOSCARVIS-27, titled "Oscar Winner: Best Makeup and
# Hairstyling", resolved, every leg retracted (`ungradeable_result`). #11334
# (calibration) owns its stored status; this test only pins how it is served.
def _oscars_retracted_category():
    return _market(
        59164593,
        "Oscar Winner: Best Makeup and Hairstyling",
        "KXOSCARVIS-27",
        [
            _o("The Odyssey", 0.285, False, "ungradeable_result"),
            _o("Dune: Part Three", 0.25, False, "ungradeable_result"),
            _o("Project Hail Mary", 0.115, False, "ungradeable_result"),
        ],
        status="resolved",
    )


# SOURCED-VENUE: 6173044 KXOSCARPIC-27, open; 38 legs carry `ungradeable_result`
# and 3 carry no source. Only a few legs are kept.
def _oscars_best_picture_open():
    return _market(
        6173044,
        "Oscar Winner: Best Picture",
        "KXOSCARPIC-27",
        [
            _o("The Odyssey", 0.445, False, "ungradeable_result"),
            _o("You Can See Everything", 0.315, False, None),
            _o("The Black Ball", 0.06, False, "ungradeable_result"),
        ],
    )


# SOURCED-VENUE: 59164596, open, the real Makeup and Hairstyling market.
def _oscars_makeup_open():
    return _market(
        59164596,
        "Oscar Winner: Best Makeup and Hairstyling",
        "KXOSCARMAKEUP-27",
        [_o("Werwulf", 0.36), _o("Digger", 0.18)],
    )


def test_only_an_independent_settlement_is_a_result_grade():
    assert is_result_grade(_o("A", 1.0, True, "api_settlement"))
    assert not is_result_grade(_o("A", 1.0, False, "api_settlement"))
    # Tier 3 but price-derived; tier 1 price crown; clock; guesses; retraction;
    # unknown and missing sources. None of them is an announcement.
    for source in (
        "settlement_sync", "clean_resolution", "date_passed", "all_losers",
        "multi_max_prob", "binary_higher_wins", "pass2_guess", "pass3_threshold",
        "ungradeable_result", "a_source_nobody_classified", None,
    ):
        assert not is_result_grade(_o("A", 1.0, True, source)), source
    # A partially loaded row fails closed.
    assert not is_result_grade(SimpleNamespace(name="A"))
    assert not is_result_grade(SimpleNamespace(name="A", is_winner=True))
    assert not is_result_grade(SimpleNamespace(name="A", resolution_source="api_settlement"))
    # Missing or blank outcome names fail closed so `result.state` never claims
    # `announced` when the reader has no named winner to display.
    for bad_name in (None, "", "   ", "\t\n"):
        assert not is_result_grade(_o(bad_name, 1.0, True, "api_settlement"))


async def test_venue_settlement_announces_and_names_the_venue():
    body = await _build([_emmys_drama_series(), _emmys_guest_actor_drama()], "emmys-2026")
    children = _children(body)
    drama = children[9750359]
    assert drama["result"] == {
        "state": RESULT_ANNOUNCED,
        "evidence_kind": EVIDENCE_VENUE_SETTLEMENT,
        "venue": "kalshi",
    }
    assert drama["graded_winner"] == "The Pitt" and _won(drama) == ["The Pitt"]
    assert children[59172874]["graded_winner"] == "Ernest Harden, Jr."
    assert body["event"]["status"] == "unknown"


@pytest.mark.parametrize(
    "source",
    ["clean_resolution", "settlement_sync", "date_passed", "multi_max_prob", None],
)
async def test_a_stored_crown_without_settlement_never_reads_as_a_winner(source):
    """SYNTHETIC: the sourced Drama Series row with its winner re-stamped. The
    market is resolved, so the reader shows "Trading closed · Result not yet
    confirmed", never "Winner The Pitt"."""
    body = await _build([_emmys_drama_series(winner_source=source)], "emmys-2026")
    child = body["children"][0]
    assert child["settled"] is True
    assert child["graded_winner"] is None and _won(child) == []
    assert child["result"] == {
        "state": RESULT_CLOSED,
        "evidence_kind": EVIDENCE_UNCONFIRMED_GRADE,
        "venue": None,
    }
    assert not any(c["won"] for c in body["primary"]["competitors"])
    assert _reader_state(child) == "closed"


async def test_a_stale_crown_beside_the_venue_answer_is_not_a_joint_winner():
    """SYNTHETIC: a price crown left on one leg when the venue settled another
    (the ticker-mismatch shape the Kalshi graders count but cannot repair). The
    venue's answer is the only winner; the page never prints "Joint winners"."""
    market = _emmys_drama_series()
    market.outcomes[1] = _o("Euphoria", 0.97, True, "clean_resolution")
    body = await _build([market], "emmys-2026")
    child = body["children"][0]
    assert child["graded_winner"] == "The Pitt" and _won(child) == ["The Pitt"]
    assert child["result"]["evidence_kind"] == EVIDENCE_VENUE_SETTLEMENT


async def test_closed_retracted_and_open_retracted_stay_unannounced():
    retracted_sound = _market(
        99013,
        "Oscar Winner: Best Sound",
        "KXOSCARSOUND-27",
        [
            _o("The Odyssey", 0.285, False, "ungradeable_result"),
            _o("Dune: Part Three", 0.25, False, "ungradeable_result"),
        ],
        status="resolved",
    )
    body = await _build(
        [
            _oscars_best_picture_open(),
            _oscars_makeup_open(),
            retracted_sound,
            _oscars_retracted_category(),
        ],
        "oscars-2027",
    )
    children = _children(body)
    # 59164593 (KXOSCARVIS-27 titled "Oscar Winner: Best Makeup and Hairstyling")
    # is held off the category list under N1 (C07/C19 venue_title_conflict), while
    # its own category_result remains closed/retracted_grade:
    assert 59164593 not in children
    assert category_result(_oscars_retracted_category(), settled=True) == {
        "state": RESULT_CLOSED,
        "evidence_kind": EVIDENCE_RETRACTED_GRADE,
        "venue": None,
    }
    retracted = children[99013]
    assert retracted["settled"] is True and _won(retracted) == []
    assert retracted["result"] == {
        "state": RESULT_CLOSED,
        "evidence_kind": EVIDENCE_RETRACTED_GRADE,
        "venue": None,
    }
    best_picture = children[6173044]
    assert best_picture["settled"] is False
    assert best_picture["result"]["state"] == RESULT_PENDING
    assert best_picture["result"]["evidence_kind"] == EVIDENCE_RETRACTED_GRADE
    makeup = children[59164596]
    assert makeup["result"] == {
        "state": RESULT_PENDING, "evidence_kind": EVIDENCE_NONE, "venue": None,
    }
    assert body["event"]["status"] == "unknown" and body["event"]["end_date"] is None


async def test_nominations_follow_the_same_rule_and_never_name_one_winner():
    body = await _build(
        [_emmys_drama_series(), _emmys_guest_actor_drama(), _emmys_drama_nominations()],
        "emmys-2026",
    )
    noms = _children(body)[33284725]
    assert noms["prop_type"] == "nominations"
    assert noms["graded_winner"] is None
    assert noms["result"]["state"] == RESULT_ANNOUNCED
    assert set(_won(noms)) == {
        "Pluribus", "The Diplomat", "A Knight of the Seven Kingdoms",
        "The Gilded Age", "The Pitt", "Slow Horses", "Paradise",
    }
    # A nomination is not the award: the category keeps its own result.
    assert _children(body)[9750359]["graded_winner"] == "The Pitt"


async def test_one_category_never_settles_a_sibling_or_the_ceremony():
    comedy = _market(
        9750362,
        "Emmy Winner: Outstanding Comedy Series",
        "KXEMMYCSERIES-26SEP14",
        [_o("Widow's Bay", 0.6), _o("Hacks", 0.3)],
    )
    body = await _build([_emmys_drama_series(), comedy], "emmys-2026")
    children = _children(body)
    assert children[9750359]["result"]["state"] == RESULT_ANNOUNCED
    assert children[9750362]["result"]["state"] == RESULT_PENDING
    assert children[9750362]["settled"] is False and _won(children[9750362]) == []
    assert body["event"]["status"] == "unknown"


async def test_result_transition_replay_for_one_category():
    """Replays the stored states one Oscar category can pass through and asserts
    the served state at each step. Siblings and the ceremony never move.

    0 open -> 1 trading closed, no grade -> 2 price crown (withheld) ->
    3 venue settlement -> 4 attended retraction of a wrong grade ->
    5 the venue's corrected answer."""
    sibling = _market(2, "Oscar winner: Best Director", "KXOSCARDIR-31",
                      [_o("Director A", 0.5), _o("Director B", 0.4)])

    def picture(status, a, b):
        return _market(1, "Oscar winner: Best Picture", "KXOSCARPIC-31",
                       [_o("Film A", *a), _o("Film B", *b)], status=status)

    steps = [
        (picture("open", (0.62, False, None), (0.38, False, None)),
         RESULT_PENDING, EVIDENCE_NONE, []),
        (picture("closed", (0.97, False, None), (0.03, False, None)),
         RESULT_CLOSED, EVIDENCE_NONE, []),
        (picture("resolved", (0.97, True, "clean_resolution"), (0.03, False, "clean_resolution")),
         RESULT_CLOSED, EVIDENCE_UNCONFIRMED_GRADE, []),
        (picture("resolved", (1.0, True, "api_settlement"), (0.0, False, "api_settlement")),
         RESULT_ANNOUNCED, EVIDENCE_VENUE_SETTLEMENT, ["Film A"]),
        (picture("resolved", (1.0, False, "ungradeable_result"), (0.0, False, "ungradeable_result")),
         RESULT_CLOSED, EVIDENCE_RETRACTED_GRADE, []),
        (picture("resolved", (0.0, False, "api_settlement"), (1.0, True, "api_settlement")),
         RESULT_ANNOUNCED, EVIDENCE_VENUE_SETTLEMENT, ["Film B"]),
    ]
    for market, state, evidence, winners in steps:
        body = await _build([market, sibling], "oscars-2031")
        children = _children(body)
        child = children[1]
        assert child["result"]["state"] == state, (state, evidence)
        assert child["result"]["evidence_kind"] == evidence, (state, evidence)
        assert _won(child) == winners
        assert _reader_state(child) == state
        assert children[2]["result"]["state"] == RESULT_PENDING
        assert body["event"]["status"] == "unknown"


async def test_joint_winners_are_kept_when_the_venue_settles_both():
    """SYNTHETIC: a tie (AMPAS Rule Five, paragraph 8) or a multi-winner area award
    (the Academy's Jan 28, 2026 Outstanding Variety Series ruling) settled by the
    venue. Both names are served; no single graded winner is invented."""
    market = _market(
        59172865, "Emmy winner: Outstanding Variety Series", "KXEMMY-OVS26SEP14",
        [_o("Show A", 1.0, True, "api_settlement"), _o("Show B", 1.0, True, "api_settlement"),
         _o("Show C", 0.0, False, "api_settlement")],
        status="resolved",
    )
    body = await _build([market], "emmys-2026")
    child = body["children"][0]
    assert child["graded_winner"] is None
    assert _won(child) == ["Show A", "Show B"]
    assert child["result"]["state"] == RESULT_ANNOUNCED


@pytest.mark.parametrize(
    "markets,slug",
    [
        ([_emmys_drama_series(), _emmys_guest_actor_drama(), _emmys_drama_nominations()], "emmys-2026"),
        ([_oscars_best_picture_open(), _oscars_makeup_open(), _oscars_retracted_category()], "oscars-2027"),
    ],
)
async def test_served_state_is_the_state_the_reader_already_derives(markets, slug):
    body = await _build(markets, slug)
    for child in body["children"]:
        assert child["result"]["state"] == _reader_state(child), child["market_id"]
        assert (child["result"]["venue"] is not None) == (
            child["result"]["state"] == RESULT_ANNOUNCED
        )


def test_category_result_reads_only_its_own_rows():
    """Pure: the same rows give the same answer whatever the siblings hold."""
    settled_market = _emmys_drama_series()
    assert category_result(settled_market, settled=True)["state"] == RESULT_ANNOUNCED
    open_market = _oscars_makeup_open()
    assert category_result(open_market, settled=False) == {
        "state": RESULT_PENDING, "evidence_kind": EVIDENCE_NONE, "venue": None,
    }


def test_evidence_precedence_and_dynamic_venue_source():
    """Invariant I5: unconfirmed_grade outranks retracted_grade when both exist on
    the same market, and announced venue reads market.source dynamically."""
    mixed = _market(
        99001,
        "Oscar Winner: Best Editing",
        "KXOSCAREDIT-27",
        [
            _o("Film Alpha", 0.15, False, "ungradeable_result"),
            _o("Film Bravo", 0.96, True, "clean_resolution"),
        ],
        status="resolved",
    )
    assert category_result(mixed, settled=True) == {
        "state": RESULT_CLOSED,
        "evidence_kind": EVIDENCE_UNCONFIRMED_GRADE,
        "venue": None,
    }
    poly_market = SimpleNamespace(
        id=99002,
        name="Oscar Winner: Best Cinematography",
        external_id="KXOSCARCINE-27",
        status="resolved",
        source="polymarket",
        resolution_date=None,
        outcomes=[_o("Film Charlie", 1.0, True, "clob_authoritative")],
    )
    assert category_result(poly_market, settled=True) == {
        "state": RESULT_ANNOUNCED,
        "evidence_kind": EVIDENCE_VENUE_SETTLEMENT,
        "venue": "polymarket",
    }


async def test_preview_extension_rescues_only_result_grades_outside_top_limit():
    """Site 1 (`_outcomes`): an outcome beyond the 8-row category preview (or a
    field 'Other' row) is appended only when `is_result_grade(o)` is True, never
    on a price crown (`clean_resolution`)."""
    base_contenders = [
        _o(f"Contender {idx}", round(0.18 - idx * 0.01, 3), False, None)
        for idx in range(1, 10)
    ]
    # Unconfirmed price crown on the 10th outcome (priceless / below preview cutoff):
    crowned_outside = _market(
        99003,
        "Oscar Winner: Best Original Score",
        "KXOSCARSCORE-27",
        base_contenders + [_o("Unconfirmed Tenth", None, True, "clean_resolution")],
        status="resolved",
    )
    body_crowned = await _build([crowned_outside], "oscars-2027")
    child_crowned = body_crowned["children"][0]
    shown_names_crowned = [o["name"] for o in child_crowned["outcomes"]]
    assert "Unconfirmed Tenth" not in shown_names_crowned
    assert len(shown_names_crowned) == 8

    # Independent venue settlement on the 10th outcome IS rescued into preview:
    settled_outside = _market(
        99004,
        "Oscar Winner: Best Original Score",
        "KXOSCARSCORE-27",
        base_contenders + [_o("Venue Settled Tenth", None, True, "api_settlement")],
        status="resolved",
    )
    body_settled = await _build([settled_outside], "oscars-2027")
    child_settled = body_settled["children"][0]
    shown_names_settled = [o["name"] for o in child_settled["outcomes"]]
    assert "Venue Settled Tenth" in shown_names_settled
    assert _won(child_settled) == ["Venue Settled Tenth"]


@pytest.mark.parametrize("blank_name", [None, "", "   "])
async def test_blank_or_missing_winner_name_never_announces_result(blank_name):
    """Point B: when the only `api_settlement` winner row has a missing or blank
    name, neither `outcomes[].won`, `graded_winner`, `primary.competitors`, nor
    `result.state` may claim `announced` while the reader has no named winner."""
    market = _market(
        99005,
        "Oscar Winner: Best Picture",
        "KXOSCARPIC-27",
        [
            _o(blank_name, 1.0, True, "api_settlement"),
            _o("The Odyssey", 0.45, False, "api_settlement"),
            _o("Dune: Part Three", 0.35, False, "api_settlement"),
        ],
        status="resolved",
    )
    body = await _build([market], "oscars-2027")
    child = body["children"][0]
    assert child["settled"] is True
    assert child["graded_winner"] is None
    assert _won(child) == []
    assert not any(c["won"] for c in body["primary"]["competitors"])
    assert child["result"] == {
        "state": RESULT_CLOSED,
        "evidence_kind": EVIDENCE_UNCONFIRMED_GRADE,
        "venue": None,
    }
    assert child["result"]["state"] == _reader_state(child) == "closed"


@pytest.mark.parametrize(
    "market_source,res_source",
    [
        ("the_odds_api", "api_settlement"),
        ("espn", "api_settlement"),
        (None, "api_settlement"),
        ("", "api_settlement"),
        ("kalshi", "clob_authoritative"),
        ("kalshi", "datagolf_settlement"),
    ],
)
def test_listing_provider_or_mismatched_source_preserves_venue_uncertainty(
    market_source, res_source
):
    """Point A: `result.venue` names the settling venue only when `market.source`
    is a verified settling authority for the winning `resolution_source`. A listing
    provider or mismatched source preserves uncertainty (`venue: None`)."""
    mkt = SimpleNamespace(
        id=99006,
        name="Oscar Winner: Best Director",
        external_id="KXOSCARDIR-27",
        status="resolved",
        source=market_source,
        resolution_date=None,
        outcomes=[_o("Director Alpha", 1.0, True, res_source)],
    )
    assert category_result(mkt, settled=True) == {
        "state": RESULT_ANNOUNCED,
        "evidence_kind": EVIDENCE_VENUE_SETTLEMENT,
        "venue": None,
    }


async def test_event_concept_route_serves_r1_result_authority(monkeypatch):
    """Point C: Route-level verification through `GET /api/event/{key}` (`get_event_concept`
    -> `get_adapter("awards")` -> `build_and_cache` -> `AwardsEventAdapter.build_event`)
    confirming the endpoint serves the R1 result object and settled/winner fields."""
    from app.routes.event import get_event_concept

    monkeypatch.setattr("app.routes.event.get_client", lambda: None)

    venue_settled_director = _market(
        99010,
        "Oscar Winner: Best Director",
        "KXOSCARDIR-27",
        [
            _o("Christopher Nolan", 1.0, True, "api_settlement"),
            _o("Denis Villeneuve", 0.0, False, "api_settlement"),
        ],
        status="resolved",
    )
    price_crowned_actor = _market(
        99011,
        "Oscar Winner: Best Actor",
        "KXOSCARACTO-27",
        [
            _o("Matt Damon", 0.97, True, "clean_resolution"),
            _o("Timothée Chalamet", 0.03, False, "clean_resolution"),
        ],
        status="resolved",
    )
    missing_source_actress = _market(
        99012,
        "Oscar Winner: Best Actress",
        "KXOSCARACTR-27",
        [
            _o("Zendaya", 1.0, True, None),
            _o("Anne Hathaway", 0.0, False, None),
        ],
        status="resolved",
    )

    retracted_sound = _market(
        99013,
        "Oscar Winner: Best Sound",
        "KXOSCARSOUND-27",
        [
            _o("The Odyssey", 0.285, False, "ungradeable_result"),
            _o("Dune: Part Three", 0.25, False, "ungradeable_result"),
        ],
        status="resolved",
    )

    body = await get_event_concept(
        "event:awards:oscars-2027",
        db=_DB(
            [
                _oscars_best_picture_open(),
                venue_settled_director,
                price_crowned_actor,
                missing_source_actress,
                retracted_sound,
                _oscars_retracted_category(),
                _oscars_makeup_open(),
            ]
        ),
    )

    assert body["event"]["key"] == "event:awards:oscars-2027"
    assert body["event"]["status"] == "unknown"
    children = _children(body)
    assert 59164593 not in children

    # 1. Venue-settled category -> announced with venue="kalshi"
    assert children[99010]["result"] == {
        "state": RESULT_ANNOUNCED,
        "evidence_kind": EVIDENCE_VENUE_SETTLEMENT,
        "venue": "kalshi",
    }
    assert children[99010]["graded_winner"] == "Christopher Nolan"
    assert _won(children[99010]) == ["Christopher Nolan"]

    # 2. Price-crowned category -> closed with unconfirmed_grade, no winner
    assert children[99011]["result"] == {
        "state": RESULT_CLOSED,
        "evidence_kind": EVIDENCE_UNCONFIRMED_GRADE,
        "venue": None,
    }
    assert children[99011]["graded_winner"] is None
    assert _won(children[99011]) == []

    # 3. Missing-source winner -> closed with unconfirmed_grade, no winner
    assert children[99012]["result"] == {
        "state": RESULT_CLOSED,
        "evidence_kind": EVIDENCE_UNCONFIRMED_GRADE,
        "venue": None,
    }
    assert children[99012]["graded_winner"] is None
    assert _won(children[99012]) == []

    # 4. Retracted closed category -> closed with retracted_grade, no winner
    assert children[99013]["result"] == {
        "state": RESULT_CLOSED,
        "evidence_kind": EVIDENCE_RETRACTED_GRADE,
        "venue": None,
    }
    assert _won(children[99013]) == []

    # 5. Open retracted category (Best Picture) -> pending with retracted_grade
    assert children[6173044]["result"] == {
        "state": RESULT_PENDING,
        "evidence_kind": EVIDENCE_RETRACTED_GRADE,
        "venue": None,
    }

    # 6. Open clean category (Makeup) -> pending with none
    assert children[59164596]["result"] == {
        "state": RESULT_PENDING,
        "evidence_kind": EVIDENCE_NONE,
        "venue": None,
    }



