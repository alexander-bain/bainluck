"""#3987 defects 2 and 3 — the "Right now" movers chip names a thing, on a
league a person has heard of.

WHAT A PERSON SAW. `GET /api/events/search-suggestions`, production, 2026-09-08
18:12Z, after defect 1 shipped:

    {"query": "Cut more than 25bps",
     "label": "Surging +94.5% — Bank of Korea rate decision...",
     "type": "futures", "market_id": 59699799}

The filed instance was `Completed Match`; the live one that afternoon was
`Cut more than 25bps`. Different string, same hole — which is the filing's own
point about #3675: that queue fixed its instance and not its grammar. Tapping it
is not an empty page, which would at least be legible: `/search?q=Cut more than
25bps` tokenises to `cut` / `rate decision` and returns a scatter of
rate-decision markets that does NOT contain the Bank of Korea market the chip
was about.

And defect 3, from the same filing: the movers section had no tier gate, so an
ITF M25 futures tennis match reached the row on the day of the US Open men's
final — #3685's complaint arriving through the other door.

THE FIX IS IN TWO PLACES BECAUSE THE DEFECT IS OF TWO KINDS, AND THE SPLIT IS
THE PART TO PRESERVE.

  * A MARKET SHAPE is a fact about the market, so it is an ELIGIBILITY rule and
    it goes in the query, inside the pool: `quantity`, `unshaped` and
    `container_member` markets cannot produce a chip (their outcome names are
    ladder rungs and the word `Yes`), and refusing them at display time would
    spend the statement's `LIMIT 5` on rows that were never candidates. Same
    argument as defect 1's settled gate, which is next door in the same list.
  * AN OUTCOME NAME is a fact about one row, so it is a DISPLAY rule and it goes
    in `_suggestion_entity_name`: a token that begins with a digit is a
    threshold, not a name. This catches the threshold outcomes that live inside
    `field` markets — `Category 5 or above`, `3+ Trophies`,
    `Cut more than 25bps` — which no shape filter can see.

THE CORPUS BELOW IS PRODUCTION, NOT INVENTION. Every string in `_LADDER_NAMES`,
`_ENTITY_NAMES` and `_GLUED_DIGIT_NAMES` was read out of `futures_outcomes` on
2026-09-08 by LAT-P269 and LAT-P270 (top 40 event-less movers, then every
field/duel mover whose name carries a digit). `_GLUED_DIGIT_NAMES` is the one
that pays for itself: `deadmau5`, `GENER8ION`, `T1` and `T1 Esports Academy` are
real entities in open markets, and they are the reason the rule is
token-initial rather than the tempting "contains a digit".
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session


# SQLite cannot render Postgres-native column types. DDL rendering for the
# sqlite dialect ONLY — production is Postgres and never reaches them.
@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


from datetime import datetime, timedelta, timezone  # noqa: E402
from types import SimpleNamespace  # noqa: E402

from app.models.models import (  # noqa: E402
    Base,
    Event,
    FuturesMarket,
    FuturesOutcome,
    Sport,
)
from app.routes import events as events_routes  # noqa: E402
from app.routes.events import (  # noqa: E402
    _SUGGESTION_MOVERS_EXCLUDED_SHAPES,
    _build_suggestion_movers_query,
    _mover_chips,
    _suggestion_entity_name,
)

#: Both arms, every time. The eligibility lives in one helper that both arms
#: read, and the legacy arm is the live rollback path (`..._POOLED=0`) — a gate
#: that only holds on the fast arm is a gate that switches off under load.
BOTH_ARMS = pytest.mark.parametrize("pooled", [True, False], ids=["pooled", "legacy"])

#: Wide enough that the POOL never explains an absence in this file.
#: `..._movers_pool_lat_p151.py` owns the bound; the one test here that narrows
#: the pool does it explicitly and says why.
TEST_POOL = 50


# ---------------------------------------------------------------------------
# the production corpus
# ---------------------------------------------------------------------------

#: Ladder rungs and scorelines. Every one of these was a candidate chip on
#: 2026-09-08; `Cut more than 25bps` was SERVED.
_LADDER_NAMES = (
    "Cut more than 25bps",
    "Hike 25bps",
    "Hike 1-25bps",
    "32°C",
    "Category 5 or above",
    "Category 4 or above",
    "Category 3 or above",
    "At least 7%",
    "At least 10%",
    "At least 20%",
    "At least 40%",
    "At least 45%",
    "At least 48%",
    "At least 55%",
    "6 to 8 points",
    "4 to 5 points",
    "15+ points",
    "Above 20K",
    "Above 10K",
    "Above 90",
    "Above 11",
    "3+ Trophies",
    "Richard Neal, ≥10%",
    "Stephen Lynch, ≥8%",
    "Iran (5+ times)",
    "Valur Reykjavik 3 - 1 Thor Akureyri",
)

#: Real entities in the same read, in the same ranking, often in the same
#: market. A rule that removes the block above and any of these is not the rule.
_ENTITY_NAMES = (
    "Enzo Fernandez",
    "Rayan Cherki",
    "Florian Wirtz",
    "Kylian Mbappe",
    "Wout Van Aert",
    "Caleb Williams",
    "Gavin Freeman",
    "Joao Cunha Cunha",
    "Scott Timko",
    "Brandon Dukes",
    "Madonna",
    "Lincoln, Nebraska",
    "Charlottesville, Virginia",
    "Lexington, Kentucky",
    "Missouri",
    "Siena",
    "Murray St.",
    "Philadelphia Flyers",
)

#: 🔴 THE MEASUREMENT THAT CHOSE THE RULE. A digit GLUED after letters is part of
#: a name. All four are outcome names in open `field` markets on production, and
#: "the name contains a digit" refuses all four.
_GLUED_DIGIT_NAMES = ("deadmau5", "GENER8ION", "T1", "T1 Esports Academy")

#: The trade, written down as a test rather than as a hope that nobody notices.
#: `25bps` and `76ers` are not structurally distinguishable, so a franchise whose
#: name starts a token with a digit goes with the ladders. Neither is in the
#: moving pool today; both were checked before the rule was written.
_KNOWN_COST_NAMES = ("Philadelphia 76ers", "San Francisco 49ers")


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _wide_pool(monkeypatch):
    monkeypatch.setattr(events_routes, "_SUGGESTION_MOVERS_POOL", TEST_POOL)


@pytest.fixture()
def engine():
    eng = create_engine("sqlite://")
    Base.metadata.create_all(
        eng,
        tables=[
            FuturesMarket.__table__,
            FuturesOutcome.__table__,
            Event.__table__,
            Sport.__table__,
        ],
    )
    return eng


def _sport(session, sid, key):
    session.add(Sport(id=sid, key=key, name=key))
    return sid


def _event(session, eid, *, sport_id, home="Home Team", away="Away Team"):
    session.add(
        Event(
            id=eid,
            sport_id=sport_id,
            home_team_name=home,
            away_team_name=away,
            commence_time=datetime.now(timezone.utc) - timedelta(hours=1),
        )
    )
    return eid


def _add(session, oid, *, change, shape=None, event_id=None, name=None, mid=None):
    """One outcome in its own market. `max_movement_24h` is DERIVED from the
    outcome's own change — a fixture that states it independently can be wrong
    in the same direction as the code."""
    mid = mid if mid is not None else oid
    session.add(
        FuturesMarket(
            id=mid,
            source="kalshi",
            external_id=f"MKT-{mid}",
            name=f"market {mid}",
            status="open",
            market_type=shape,
            event_id=event_id,
            max_movement_24h=abs(change),
        )
    )
    session.add(
        FuturesOutcome(
            id=oid,
            market_id=mid,
            external_id=f"OUT-{oid}",
            name=name if name is not None else f"outcome {oid}",
            current_probability=0.5,
            probability_change_24h=change,
        )
    )
    return oid


def _run(engine, *, pooled):
    with Session(engine) as s:
        return [r.id for r in s.execute(_build_suggestion_movers_query(pooled=pooled)).unique().scalars().all()]


def _chip_row(name, *, market_name="EPL Playmaker Award", market_id=1, change=0.5, event=None):
    return SimpleNamespace(
        name=name,
        market_id=market_id,
        probability_change_24h=change,
        market=SimpleNamespace(id=market_id, name=market_name, event=event),
    )


# ---------------------------------------------------------------------------
# 0 — the corpus is not self-serving
# ---------------------------------------------------------------------------


def test_the_corpus_separates_two_classes_and_not_one_string():
    """Before trusting any refusal below, prove the fixture is a CLASS.

    #3675 was closed on `Yes`, and its grammar then served `Completed Match`,
    and that was closed and the grammar served `Cut more than 25bps`. A file
    that tests one string is how that happens; these are 26 ladder rungs and 18
    entities read from the same production ranking on the same afternoon.
    """
    assert len(_LADDER_NAMES) >= 20 and len(_ENTITY_NAMES) >= 15
    assert not set(_LADDER_NAMES) & set(_ENTITY_NAMES)
    assert "Cut more than 25bps" in _LADDER_NAMES, "the SERVED instance must be in the corpus"
    # Every ladder name is short and alphabetic enough to pass every refusal
    # #3675 shipped — i.e. the old grammar admitted all of them, which is why
    # this file exists rather than a widened `_SUGGESTION_SIDE_LABELS`.
    for name in _LADDER_NAMES:
        assert len(name) <= 40
        assert ":" not in name and " vs " not in name.lower()


# ---------------------------------------------------------------------------
# 1 — defect 2, the display half: an outcome name that is a threshold
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", _LADDER_NAMES)
def test_a_ladder_rung_is_not_an_entity(name):
    assert _suggestion_entity_name(name) is None, (
        f"{name!r} would be served as a chip query — tapping it runs "
        f"/search?q={name}, which does not lead back to the market it names"
    )


@pytest.mark.parametrize("name", _ENTITY_NAMES)
def test_a_real_entity_still_names_itself(name):
    assert _suggestion_entity_name(name) == name, (
        f"{name!r} is a person, a team or a place from the same production "
        "ranking; a rule that removes it has removed the section's reason to exist"
    )


@pytest.mark.parametrize("name", _GLUED_DIGIT_NAMES)
def test_a_digit_glued_inside_a_word_is_part_of_the_name(name):
    """🔴 THE RULE IS TOKEN-INITIAL, AND THIS IS WHY.

    `deadmau5`, `GENER8ION` and `T1` are outcome names in open production
    markets. The tempting one-liner — "refuse a name containing a digit" —
    refuses all three while catching nothing this file's ladder corpus does not
    already catch. If this test is failing, someone widened the regex.
    """
    assert _suggestion_entity_name(name) == name


@pytest.mark.parametrize("name", _KNOWN_COST_NAMES)
def test_the_cost_of_the_rule_is_stated_rather_than_discovered(name):
    """The franchises the rule cannot keep. Asserted, not apologised for.

    `25bps` and `76ers` differ in no property this layer can read, so the trade
    was taken deliberately: two team names lost from ONE section against a class
    of chips that lead nowhere. Both remain reachable everywhere else on the row
    — sections 1, 2 and 4 name teams from the EVENT, never from an outcome name.
    If a later queue finds a spelling that keeps these AND refuses the corpus
    above, this is the test to delete, and deleting it should be deliberate.
    """
    assert _suggestion_entity_name(name) is None


def test_the_served_production_chip_is_gone_and_the_section_is_not():
    """Both halves in one assertion, because either alone is a wrong fix.

    Deleting section 3 would also remove `Cut more than 25bps`. #2286's disease
    is a section nobody notices is dead, so the honest proof is that the junk
    row is refused IN THE SAME CALL that keeps the entity row.
    """
    chips = _mover_chips(
        [
            _chip_row(
                "Cut more than 25bps",
                market_name="Bank of Korea rate decision in October",
                market_id=59699799,
                change=0.945,
            ),
            _chip_row("Rayan Cherki", market_id=59164820, change=-0.94),
        ]
    )
    assert [c["query"] for c in chips] == ["Rayan Cherki"]
    assert chips[0]["label"] == "Falling -94 points — EPL Playmaker Award"


# ---------------------------------------------------------------------------
# 2 — defect 2, the structural half: shapes that cannot produce a chip
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("shape", _SUGGESTION_MOVERS_EXCLUDED_SHAPES)
@BOTH_ARMS
def test_a_market_shape_whose_names_are_never_entities_is_not_ranked(engine, shape, pooled):
    with Session(engine) as s:
        excluded = _add(s, 1, change=0.99, shape=shape)
        eligible = _add(s, 2, change=0.10, shape="field")
        s.commit()
    assert _run(engine, pooled=pooled) == [eligible], (
        f"a {shape!r} market outranked every real mover; on production those "
        "three shapes are 3,173 of the 5,569 open markets carrying movement"
    )
    assert excluded not in _run(engine, pooled=pooled)


@BOTH_ARMS
def test_an_unshaped_market_does_not_spend_a_limit_slot(engine, pooled):
    """Defect 1's argument, applied to defect 2. The statement asks for five.

    A display-time refusal of an ineligible row leaves the `LIMIT` already
    spent, so a ranking whose top five are all `Yes` legs serves NOTHING — which
    is what production did before this gate. Five excluded rows above five
    eligible ones must still yield five chips' worth of rows.
    """
    with Session(engine) as s:
        for i in range(5):
            _add(s, 100 + i, change=0.99 - 0.001 * i, shape="container_member")
        eligible = [_add(s, 200 + i, change=0.50 - 0.01 * i, shape="field") for i in range(5)]
        s.commit()
    assert _run(engine, pooled=pooled) == eligible


@pytest.mark.parametrize("shape", [None, "participation", "field", "duel"])
@BOTH_ARMS
def test_an_unknown_or_unwritten_shape_stays_eligible(engine, shape, pooled):
    """🔴 THE GATE IS A DENYLIST AND THAT IS THE DELIBERATE DIRECTION.

    `market_type` is nullable and its backfill lags: 39 open markets had a NULL
    shape when this shipped and ALL 39 were created that same day — i.e. exactly
    the brand-new markets most likely to be moving. `participation` is a sixth
    value already in production that the model's own comment does not list. An
    allowlist of `('field','duel')` reads tidier and silently deletes both
    classes; this fails OPEN into `_mover_chips`, which is a real defense.
    """
    with Session(engine) as s:
        oid = _add(s, 1, change=0.5, shape=shape)
        s.commit()
    assert _run(engine, pooled=pooled) == [oid]


def test_the_eligibility_is_inside_the_pool_and_not_applied_to_its_output(engine, monkeypatch):
    """🔴 THE POSITION OF THE FILTER, WHICH NO BEHAVIOURAL TEST AT A WIDE POOL CAN SEE.

    `market_id IN pool AND eligible` and `market_id IN (pool of eligible)`
    return the same rows on every fixture whose pool is bigger than its corpus,
    and they are different queries: the first ranks the whole population and
    then throws most of it away. Measured on production the day this shipped, of
    the top 400 markets by `max_movement_24h` only 42 were event-attached — so
    the wrong position would have discarded ~97% of that gate's population.

    Driven at `pool_size=1` because that is the only size at which the two
    spellings disagree: one excluded market with the biggest movement either
    IS the pool (wrong) or is not in it (right).
    """
    monkeypatch.setattr(events_routes, "_SUGGESTION_MOVERS_POOL", 1)
    with Session(engine) as s:
        _add(s, 1, change=0.99, shape="quantity")
        eligible = _add(s, 2, change=0.10, shape="field")
        s.commit()
    assert _run(engine, pooled=True) == [eligible], (
        "the pool was cut from the whole population and the gate was applied "
        "afterwards, so the one slot went to a market that can never be a chip"
    )


# ---------------------------------------------------------------------------
# 3 — defect 3, the tier gate sections 1 and 2 have always had
# ---------------------------------------------------------------------------


@BOTH_ARMS
def test_a_game_market_below_tier_2_is_not_a_mover(engine, pooled):
    """The filed row: an ITF M25 tennis match on the row on US Open final day.

    `tennis_other` is where every ITF/challenger row in `events` lands — 143 open
    markets with movement on the day this shipped, against 24 for
    `tennis_atp_us_open`.
    """
    with Session(engine) as s:
        _sport(s, 1, "tennis_other")
        _sport(s, 2, "baseball_mlb")
        itf = _event(s, 10, sport_id=1, home="Toby Martin", away="Loic Namigandet Tenguere")
        mlb = _event(s, 11, sport_id=2, home="New York Yankees", away="Red Sox")
        low = _add(s, 1, change=0.99, shape="field", event_id=itf)
        marquee = _add(s, 2, change=0.10, shape="field", event_id=mlb)
        s.commit()
    got = _run(engine, pooled=pooled)
    assert got == [marquee], f"the ITF row ranked first and reached the row: {got}"
    assert low not in got


@BOTH_ARMS
def test_a_market_with_no_event_is_the_sections_whole_contribution(engine, pooled):
    """🔴 `event_id IS NULL` IS AN ARM OF THE GATE, NOT AN OVERSIGHT.

    A league tier is a fact about a game. Every chip section 3 served in the
    measured production sample was event-LESS — `EPL Playmaker Award`,
    `Vuelta a Espana: Green Jersey Winner`, `College GameDay Week 6 Location`,
    `MTV Video Music Awards` — and nothing else on the row can show them:
    sections 1, 2 and 4 are event sections and section 5 ranks by volume.
    Dropping this arm does not tighten the gate, it deletes the section.
    """
    with Session(engine) as s:
        award = _add(s, 1, change=0.94, shape="field")
        s.commit()
    assert _run(engine, pooled=pooled) == [award]


@pytest.mark.parametrize("key", ["tennis_atp_us_open", "tennis_wta_us_open", "baseball_mlb"])
@BOTH_ARMS
def test_the_marquee_spellings_events_actually_uses_are_eligible(engine, key, pooled):
    """🔴 #2552 IN SET FORM — the reason the gate calls `tier_12_sport_keys()`.

    `LEAGUE_TIERS` spells the slams `tennis_us_open`; every US Open match in
    `events` is keyed `tennis_atp_us_open`. The obvious comprehension over the
    table is a NARROWER predicate than the function it looks equivalent to, and
    it excludes every Grand Slam match — which on US Open final weekend is the
    one thing this row must never do (the marquee rule).
    """
    with Session(engine) as s:
        _sport(s, 1, key)
        ev = _event(s, 10, sport_id=1, home="Carlos Alcaraz", away="Jannik Sinner")
        oid = _add(s, 1, change=0.5, shape="field", event_id=ev)
        s.commit()
    assert _run(engine, pooled=pooled) == [oid]


@BOTH_ARMS
def test_a_tier_1_game_market_still_supplies_its_teams_name(engine, pooled):
    """The gate keeps the marquee game rows it is supposed to keep, and the chip
    they produce still comes from the EVENT — #3675's resolution order."""
    with Session(engine) as s:
        _sport(s, 1, "americanfootball_nfl")
        ev = _event(s, 10, sport_id=1, home="Los Angeles Rams", away="San Francisco 49ers")
        oid = _add(s, 1, change=0.5, shape="field", event_id=ev, name="Los Angeles R reaches 7 points first")
        s.commit()
    assert _run(engine, pooled=pooled) == [oid]

    chips = _mover_chips(
        [
            _chip_row(
                "Los Angeles R reaches 7 points first",
                market_name="San Francisco vs Los Angeles R: Race to 7 Points",
                change=0.5,
                event=SimpleNamespace(
                    id=10,
                    home_team_name="Los Angeles Rams",
                    away_team_name="San Francisco 49ers",
                ),
            )
        ]
    )
    assert [c["query"] for c in chips] == ["Los Angeles Rams"], (
        "an event-attached row takes its query from the event, so the outcome "
        "name's digits never reach the display rule — and must not have to"
    )
