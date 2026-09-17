"""#2563: a `/weather` card stops printing the price of its own question's NO.

Two rules that are each right on their own, and wrong together.
`_leader_outcome` takes the dearest outcome whatever it is called;
`_leader_outcome_name` then refuses to print "Yes"/"No", because on a genuine
binary those words only restate the question. Put the pair on a market whose
dearest leg is `No` and the number survives while its referent is deleted — the
price of the question's NEGATION sits under the question, in green, behind a
nearly full bar.

Measured on production 2026-09-17 (390px LOOK + `db-query` on
`futures_outcomes`), all three on one phone screen:

    prints  honest   question                                          outcomes
      98%     2.3%   Which cities face tornado risk on September 16?   No .977 + 25 cities + Yes .023
      96%     4.5%   Will a hurricane make landfall in Virginia …?     No .955, Yes .045, Virginia .045
      51%      23%   Will Tyra Hurricane Black / Noe Khlif advance …?  No .51, Yes .23

The second is the sharpest: 96% under a hurricane question is the most alarming
number on the page, and the market says 4.5%. The third is a tennis match that
reached the Hurricane card on a player's surname — the wrong-section half is a
matching defect (filed separately, D35); only its inverted number is this ship.

The fix is one seam. `_card_outcome` already exists precisely so the printed
number, the printed name and the sparkline cannot disagree about which outcome
a card is about, so teaching THAT to decline a leg that prices the NEGATION
repairs all three consumers at once.

THE TRAP THIS SHIP NEARLY WALKED INTO, and the reason `_prices_the_negation` is
its own predicate rather than a call to `_adds_to_the_question`: the existing
`TestNothingWorthNaming` suite already refuses to NAME three kinds of leg —
`Yes`/`No`, placeholders, and names the question already spells out. Reusing
that refusal wholesale to pick the NUMBER looks obviously right and is wrong on
the third kind:

    Will Tropical Storm Lowell strengthen to a hurricane?
        "Tropical Storm Lowell strengthen to a hurricane"  0.88   <- the answer
        "Stays a tropical storm"                           0.10

88% is exactly right; only its NAME is redundant. The first draft of this ship
demoted it to the 10% also-ran, and `test_a_leader_already_spelled_out_in_the_
question_is_not_repeated` caught it. Redundancy costs the reader a word and
suppresses the name; negation costs them the truth and is the only thing
allowed to move the number.

Scope, measured rather than assumed — over the whole served weather population
(405 open markets, 95 with `No` dearest), every one of the 95 has a non-negated
priced leg to fall to, so the final `or leader` has **0** production specimens.
It preserves today's number instead of shipping an unexercised withholding path
across four surfaces, and is pinned below as a manufactured specimen rather than
claimed as a repair.

What this file pins:

  1. each production specimen, through the REAL `get_events` builder, prints
     the honest number — asserted as an equality against the price the venue
     quotes, never as "not the wrong one" (a mutant returning 0 would pass
     that);
  2. the row is STILL SERVED. This ship moves a number DOWN, and a vanished row
     satisfies every "the wrong number is gone" assertion as happily as a fix
     does;
  3. the healthy rows beside them on the same card do not move;
  4. the three arms, each on its own;
  5. the seam holds — number, name and sparkline outcome are one outcome.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


from app.models.models import (  # noqa: E402
    Base,
    FuturesMarket,
    FuturesOddsSnapshot,
    FuturesOutcome,
)
from app.routes.weather import (  # noqa: E402
    _card_outcome,
    _card_prob,
    _card_probability,
    _leader_outcome,
    _leader_outcome_name,
    get_events,
)

NOW = datetime.now(timezone.utc)
FRESH = NOW - timedelta(hours=1)

# The production prices, to the cent the venue was quoting when this was filed.
TORNADO_CITIES = [
    ("No", 0.977),
    ("San Antonio, TX", 0.035),
    ("Denver, CO", 0.025),
    ("Memphis, TN", 0.025),
    ("Louisville, KY", 0.024),
    ("Yes", 0.023),
    ("Austin, TX", 0.0185),
    ("Birmingham, AL", 0.011),
]
VIRGINIA = [("No", 0.955), ("Yes", 0.045), ("Virginia", 0.045)]
TENNIS = [("No", 0.51), ("Yes", 0.23)]

# Healthy rows from the same two cards, which must not move.
MARIE = [("Category 1 or above", 0.995), ("Category 5 or above", 0.02)]
TORNADO_COUNT = [("Above 25", 0.995), ("Above 30", 0.4)]
HAWAII = [("Yes", 0.09), ("No", None)]
NEXT_ATLANTIC = [("Before Nov 15, 2026", 0.805), ("Before Nov 1, 2026", 0.07)]


@pytest.fixture(autouse=True)
def _sqlite_returns_aware_datetimes():
    """SQLite drops the tzinfo a `DateTime(timezone=True)` column carries and
    the builder subtracts `resolution_date - now`. Registered and removed per
    test so the listener cannot follow `FuturesMarket` into another module."""
    fields = ("resolution_date", "updated_at", "created_at", "last_updated")

    def _restore_utc(target, _context):  # pragma: no cover - sqlite shim
        for field in fields:
            value = getattr(target, field, None)
            if isinstance(value, datetime) and value.tzinfo is None:
                setattr(target, field, value.replace(tzinfo=timezone.utc))

    event.listen(FuturesMarket, "load", _restore_utc)
    try:
        yield
    finally:
        event.remove(FuturesMarket, "load", _restore_utc)


class AsyncDB:
    """Minimal async facade over a sync Session — the builder awaits only
    `db.execute(query)`, so the REAL statement runs against a real database."""

    def __init__(self, session: Session):
        self._session = session

    async def execute(self, query):
        return self._session.execute(query)


def _new_session() -> Session:
    eng = create_engine("sqlite://")
    Base.metadata.create_all(
        eng,
        tables=[
            FuturesMarket.__table__,
            FuturesOutcome.__table__,
            FuturesOddsSnapshot.__table__,
        ],
    )
    return Session(eng)


def _stub(session, mid, name, outcomes, *, source="polymarket"):
    session.add(
        FuturesMarket(
            id=mid,
            source=source,
            external_id=f"mkt-{mid}",
            name=name,
            status="open",
            llm_sport_category="weather",
            resolution_date=NOW + timedelta(days=30),
            updated_at=FRESH,
        )
    )
    for i, (label, prob) in enumerate(outcomes):
        session.add(
            FuturesOutcome(
                id=mid * 100 + i,
                market_id=mid,
                external_id=f"outcome-{mid}-{i}",
                name=label,
                current_probability=prob,
            )
        )


def _bare(name, outcomes, external_id="x") -> FuturesMarket:
    """A market object the pure scans can read, with no database behind it."""
    m = FuturesMarket(
        id=1, source="kalshi", external_id=external_id, name=name, status="open"
    )
    m.outcomes = [
        FuturesOutcome(
            id=i, market_id=1, external_id=f"o{i}", name=label, current_probability=prob
        )
        for i, (label, prob) in enumerate(outcomes)
    ]
    return m


def _rows(payload):
    """Every row of the `/events` payload, flattened across its three keys."""
    return [row for section in payload.values() for row in section]


def _row(payload, needle):
    hits = [r for r in _rows(payload) if needle in r["q"]]
    assert len(hits) == 1, f"expected exactly one row matching {needle!r}, got {hits}"
    return hits[0]


# ---------------------------------------------------------------------------
# 1 + 2. The production specimens, through the real builder — repaired AND
#        still on the page.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_three_production_specimens_print_the_honest_number():
    session = _new_session()
    _stub(session, 61217805, "Which cities face tornado risk on September 16?", TORNADO_CITIES)
    _stub(session, 59159633, "Will a hurricane make landfall in Virginia by November 30, 2026?", VIRGINIA)
    _stub(
        session,
        61079876,
        "Will Tyra Hurricane Black / Noe Khlif advance to the Round of 16 in "
        "Mixed Doubles at the 2026 Veolia Arizona Open?",
        TENNIS,
    )
    session.commit()

    payload = await get_events(AsyncDB(session))

    # The `which-cities` field market names its leading CITY — the same shape
    # the healthy "Number of tornadoes … / Above 25" row on this card already
    # has — rather than quoting the 97.7% that no city is hit.
    tornado = _row(payload, "Which cities face tornado risk")
    assert tornado["prob"] == 4
    assert tornado["probability"] == pytest.approx(0.035)
    assert tornado["leader"] == "San Antonio, TX"

    # A plainly binary question: the answer is the Yes price, 4.5%, not 95.5%.
    # No name — "Yes" under "Will a hurricane …?" only restates the question.
    virginia = _row(payload, "make landfall in Virginia")
    assert virginia["prob"] == 4
    assert virginia["probability"] == pytest.approx(0.045)
    assert virginia["leader"] is None

    tennis = _row(payload, "Tyra Hurricane Black")
    assert tennis["prob"] == 23
    assert tennis["probability"] == pytest.approx(0.23)
    assert tennis["leader"] is None


@pytest.mark.asyncio
async def test_the_repaired_rows_are_still_served():
    """The ship moves a number DOWN, and a dropped row passes every assertion
    above about the wrong number being gone. So: assert the surface is still a
    surface, by id, before believing any of it."""
    session = _new_session()
    _stub(session, 61217805, "Which cities face tornado risk on September 16?", TORNADO_CITIES)
    _stub(session, 59159633, "Will a hurricane make landfall in Virginia by November 30, 2026?", VIRGINIA)
    session.commit()

    payload = await get_events(AsyncDB(session))

    assert len(_rows(payload)) == 2
    assert len(payload["tornadoes"]) == 1
    assert len(payload["hurricane"]) == 1
    for row in _rows(payload):
        assert row["prob"] is not None
        assert row["probability"] is not None
        assert row["src"]
        assert row["q"]


# ---------------------------------------------------------------------------
# 3. The healthy rows on the same two cards do not move.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_healthy_rows_beside_them_are_untouched():
    session = _new_session()
    _stub(session, 1, "Hurricane Marie category?", MARIE, source="kalshi")
    _stub(session, 2, "Number of tornadoes in Sep 2026?", TORNADO_COUNT, source="kalshi")
    _stub(session, 3, "Will a hurricane make landfall in Hawaii in 2026?", HAWAII)
    _stub(session, 4, "When will the next Atlantic hurricane form?", NEXT_ATLANTIC, source="kalshi")
    session.commit()

    payload = await get_events(AsyncDB(session))

    marie = _row(payload, "Hurricane Marie")
    assert marie["prob"] == 100 and marie["leader"] == "Category 1 or above"

    count = _row(payload, "Number of tornadoes")
    assert count["prob"] == 100 and count["leader"] == "Above 25"

    # Only the Yes leg is priced; the unpriced `No` loses the scan as it always
    # did, and the honest 9% is unchanged.
    hawaii = _row(payload, "Hawaii")
    assert hawaii["prob"] == 9 and hawaii["leader"] is None

    nxt = _row(payload, "next Atlantic hurricane")
    assert nxt["prob"] == 80 and nxt["leader"] == "Before Nov 15, 2026"


def test_a_dearer_named_outcome_is_still_simply_the_leader():
    """The common path is untouched: when the dearest outcome can be named, it
    is the card's, and no fall-through runs."""
    m = _bare("Hurricane Marie category?", MARIE)
    assert _card_outcome(m) is _leader_outcome(m)
    assert _card_prob(m) == 100


# ---------------------------------------------------------------------------
# 4. The three arms, each on its own.
# ---------------------------------------------------------------------------


def test_named_arm_prefers_the_dearest_outcome_it_can_name():
    m = _bare("Which cities face tornado risk on September 16?", TORNADO_CITIES)
    assert _card_outcome(m).name == "San Antonio, TX"
    assert _card_probability(m) == pytest.approx(0.035)
    assert _leader_outcome_name(m) == "San Antonio, TX"


def test_yes_arm_answers_a_binary_with_its_yes_price():
    m = _bare("Will a hurricane make landfall in Virginia by November 30, 2026?", VIRGINIA)
    # `Virginia` is priced as high as `Yes` and is NOT the fall-through, because
    # the question already says Virginia — naming it would print the same word
    # twice in two type sizes and tell the reader nothing.
    assert _card_outcome(m).name == "Yes"
    assert _card_probability(m) == pytest.approx(0.045)
    assert _leader_outcome_name(m) is None


def test_yes_arm_fires_however_dear_the_no_leg_is():
    """The arm keys on the NAME, not on the margin: a 1%/99% split answers 1%."""
    m = _bare("Will a 9.0+ earthquake occur worldwide by September 30?",
              [("No", 0.992), ("Yes", 0.008)])
    assert _card_prob(m) == 1
    assert _card_probability(m) == pytest.approx(0.008)


def test_the_final_arm_has_no_production_specimen_and_preserves_todays_number():
    """Measured 2026-09-17: 0 of 405 served weather markets price `No` with
    neither a nameable outcome nor a priced `Yes`. Manufactured here so the
    decision is recorded — this arm is deliberately NOT a repair, and shipping
    a withholding path for an empty population is the thing being declined."""
    m = _bare("Will it rain tomorrow?", [("No", 0.6), ("Yes", None)])
    assert _card_outcome(m).name == "No"
    assert _card_prob(m) == 60
    # It still refuses to NAME the leg, exactly as it does today.
    assert _leader_outcome_name(m) is None


def test_a_placeholder_leg_cannot_be_the_card_either():
    """`_GARBAGE_OUTCOME_RE` names are not names, so they take the same exit as
    `No` — the scan falls through to the outcome that says something."""
    m = _bare("Which party wins?", [("Party A", 0.7), ("Labour", 0.2), ("Yes", 0.1)])
    assert _card_outcome(m).name == "Labour"
    assert _leader_outcome_name(m) == "Labour"


def test_a_redundant_name_keeps_its_number_and_only_loses_its_name():
    """The regression the first draft of this ship shipped, pinned where the
    ship lives rather than only in the suite that caught it.

    "Tropical Storm Lowell" is the live shape: the dearest leg repeats the
    question, so it is unnameable — and it is still the correct 88% answer. A
    fall-through keyed on nameability hands the card to "Stays a tropical storm"
    at 10% and calls the inversion a fix.
    """
    m = _bare(
        "Will Tropical Storm Lowell strengthen to a hurricane?",
        [
            ("Tropical Storm Lowell strengthen to a hurricane", 0.88),
            ("Stays a tropical storm", 0.10),
            ("Dissipates", 0.02),
        ],
    )
    assert _card_prob(m) == 88
    assert _card_outcome(m) is _leader_outcome(m)
    assert _leader_outcome_name(m) is None


def test_the_drought_market_names_its_dearest_state_not_its_no():
    """The 42-outcome production market from `TestNothingWorthNaming`, whose
    docstring predicted this exact row and guarded only its name."""
    m = _bare(
        "Exceptional drought (D4) by state — week of September 1, 2026",
        [("No", 0.925), ("Colorado", 0.900), ("Oklahoma", 0.879), ("Yes", 0.075)],
    )
    assert _card_prob(m) == 90
    assert _leader_outcome_name(m) == "Colorado"


# ---------------------------------------------------------------------------
# 5. The seam. Three consumers, one outcome.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "question,outcomes",
    [
        ("Which cities face tornado risk on September 16?", TORNADO_CITIES),
        ("Will a hurricane make landfall in Virginia by November 30, 2026?", VIRGINIA),
        ("Will Tyra Hurricane Black / Noe Khlif advance?", TENNIS),
        ("Hurricane Marie category?", MARIE),
        ("Number of tornadoes in Sep 2026?", TORNADO_COUNT),
        ("Will a hurricane make landfall in Hawaii in 2026?", HAWAII),
    ],
)
def test_the_printed_number_and_the_printed_name_are_one_outcome(question, outcomes):
    """`_card_outcome` is the single seam the number, the name and the sparkline
    all read. If it could disagree with itself the card would chart one outcome
    under another's percentage — strictly worse than printing no name at all."""
    m = _bare(question, outcomes)
    chosen = _card_outcome(m)
    assert _card_probability(m) == pytest.approx(float(chosen.current_probability))
    name = _leader_outcome_name(m)
    if name is not None:
        assert name == chosen.name


@pytest.mark.parametrize(
    "question,outcomes",
    [
        ("Which cities face tornado risk on September 16?", TORNADO_CITIES),
        ("Will a hurricane make landfall in Virginia by November 30, 2026?", VIRGINIA),
        ("Will Tyra Hurricane Black / Noe Khlif advance?", TENNIS),
    ],
)
def test_a_no_leg_never_wins_when_the_market_can_answer_its_question(question, outcomes):
    """The whole ship in one line, stated over the specimens as a class."""
    m = _bare(question, outcomes)
    assert _leader_outcome(m).name == "No", "specimen must actually have No dearest"
    assert _card_outcome(m).name != "No"
