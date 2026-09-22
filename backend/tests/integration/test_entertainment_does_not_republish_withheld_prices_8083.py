"""#8083 — `/entertainment` asks the same price refusal the market's own page asks.

THE DEFECT. `/api/entertainment` built its cards straight off the stored
`current_probability` column. Withholding is a SERVE-TIME decision layered on a
column that stays non-null, so reading the column directly bypassed it and the
page published prices `/api/futures/{id}` refuses in the same minute:

    Who will win The Bachelorette Season 22?
    Doug 93% · Shane 5% · Lew 2% · Matt 2% · Trenten 2% · Brandon 1%
    ● KALSHI

    GET /api/futures/1154050  ->  prices_withheld: 22, all 22 outcomes null

Tapping that card landed on "No prices in the last 30 days · Try a longer
range." with no outcomes at all — Doug is gone. The outcome rows' own
`last_updated` was 2026-03-19, six months stale, and the card showed no volume,
no resolution date and no age.

WHICH FAMILY IT IS IN, because three nearby rails want different repairs.
This is NOT #8046 (the SCALE rail — a themed route serving raw prices where the
detail route normalizes) and NOT #7000 (the SETTLED rail — graded-then-retracted
rows carrying `resolution_source='ungradeable_result'`; both specimens here are
`resolution_source: None` with no venue result at all). It is #6993's exact
discriminator at a fourth route: #6993 hung the five arms on one hook and wired
`futures.py`, `events.py` and `league_futures.py` to it, and the themed
dashboards were not swept.

WHY THE ARMS BELOW PATCH THE HELPER RATHER THAN BUILD ITS INPUTS. The ship here
is that this route ASKS — the five arms themselves are #6993's and are tested
where they live. Building real snapshot rows to make a genuine arm fire would
test `futures.py` through `entertainment.py` and would still not notice the one
way this ship can regress, which is the call going away. So the helper is
replaced with a fake whose answer DEPENDS ON THE MARKET, and
`TestTheRouteAsksTheSharedHelperAndNotACopy` pins the symbol to the real one so
a local re-spelling — the "fifth spelling" the helper's own docstring was
written to prevent — fails here rather than shipping.

  ⚠️ WHAT WOULD MAKE THIS FILE VACUOUS, and the arm that catches it.
  Every assertion below is of the form "this number is absent". A route that
  served an empty payload, a fixture that classified into no theme, or a fake
  that withheld everything would satisfy all of them while measuring nothing.
  `TestTheGuardCanFail` re-runs the SAME fixture with the refusal returning the
  empty set and asserts the withheld numbers ARE published — so every absence
  above is known to be the ship's doing and not the fixture's. The control
  market, which nothing withholds, is asserted present and complete in both
  directions for the same reason.

  ⚠️ ONE THING THIS FILE DELIBERATELY DOES NOT ASSERT. `_leader_prob`, which
  feeds `should_exclude_from_featured`, still reads the raw column. That gate
  only decides whether a market is CONSIDERED; it publishes nothing, and a
  market whose every leg is withheld is refused by `_market_row` immediately
  after. Making it withhold-aware would change which markets the page considers
  — a ranking change nobody asked for, and #8083 did not ask for it.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.routes import entertainment as entertainment_module
from app.routes import futures as futures_module


# ---------------------------------------------------------------------------
# Mocks — the shared idiom from
# test_entertainment_sidebar_count_is_the_rows_it_sits_over_7432
# ---------------------------------------------------------------------------


class _MockScalars:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items

    def first(self):
        return self._items[0] if self._items else None

    def unique(self):
        return self


class _MockResult:
    def __init__(self, items):
        self._scalars = _MockScalars(items)

    def scalars(self):
        return self._scalars

    def all(self):
        return self._scalars.all()

    def first(self):
        return self._scalars.first()


def _outcome(outcome_id, name, probability):
    return SimpleNamespace(
        id=outcome_id,
        name=name,
        current_probability=probability,
        probability_change_24h=0,
        rank=1,
        is_winner=None,
        resolution_source=None,
    )


def _market(*, market_id, name, outcomes):
    """A multi-outcome entertainment market landing in the `other` theme.

    Three outcomes, not two: `_is_interesting` drops
    ``outcome_count <= 2 and prob > 95``, and the withheld leader below is 93%,
    so a binary fixture would be dropped for a reason that has nothing to do
    with this ship.
    """
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=market_id,
        name=name,
        external_id=f"mock{market_id}",
        source="kalshi",
        category="news",
        llm_sport_category="entertainment",
        outcomes=outcomes,
        market_metadata=None,
        resolution_date=now + timedelta(days=30),
        updated_at=now,
        volume_24h=1000,
        image_url=None,
        hook_description=None,
        status="open",
    )


# ---------------------------------------------------------------------------
# The fixture — the two specimens on the issue, plus a control
# ---------------------------------------------------------------------------

# Specimen A's shape: every leg withheld. The card must be withdrawn, because a
# market with nothing servable has no honest headline to print.
ALL_WITHHELD_ID = 700
ALL_WITHHELD_LEGS = [
    _outcome(7001, "Doug", 0.93),
    _outcome(7002, "Shane", 0.05),
    _outcome(7003, "Lew", 0.02),
]

# Specimen B's shape: the LEADER is withheld and the tail is supported. Chosen
# over withholding a tail rung on purpose — it proves the published headline
# moves, which is the number a reader actually reads.
PARTIAL_ID = 710
PARTIAL_WITHHELD_LEG = 7101
PARTIAL_LEGS = [
    _outcome(PARTIAL_WITHHELD_LEG, "Withheld leader", 0.93),
    _outcome(7102, "Supported runner up", 0.40),
    _outcome(7103, "Supported third", 0.25),
]

# The control: nothing about it is withheld, so it must survive untouched.
CONTROL_ID = 720
CONTROL_LEGS = [
    _outcome(7201, "Control leader", 0.55),
    _outcome(7202, "Control second", 0.30),
    _outcome(7203, "Control third", 0.15),
]

WITHHELD_IDS = {7001, 7002, 7003, PARTIAL_WITHHELD_LEG}


def _fixture():
    return [
        _market(
            market_id=ALL_WITHHELD_ID,
            name="Will the documentary be released before December?",
            outcomes=ALL_WITHHELD_LEGS,
        ),
        _market(
            market_id=PARTIAL_ID,
            name="Will the festival announce its lineup by November?",
            outcomes=PARTIAL_LEGS,
        ),
        _market(
            market_id=CONTROL_ID,
            name="Will the museum extend its exhibit into spring?",
            outcomes=CONTROL_LEGS,
        ),
    ]


def _install_refusal(monkeypatch, withheld: set[int]):
    """Replace the refusal with a fake that answers PER MARKET.

    Returns the call log. The answer depends on the market's own legs rather
    than being a constant, so a route that called this once for the whole page
    and applied one market's answer to another would not be satisfied by it.
    """
    calls = []

    async def _fake(db, market):
        calls.append(market.id)
        return {o.id for o in market.outcomes if o.id in withheld}

    monkeypatch.setattr(
        entertainment_module, "_withheld_price_outcome_ids", _fake
    )
    return calls


async def _payload(client, mock_db, markets=None):
    mock_db.execute.return_value = _MockResult(
        _fixture() if markets is None else markets
    )
    resp = await client.get("/api/entertainment")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "themes" in body, (
        "the route fell through to its timeout/error shape, so every assertion "
        f"below would be vacuously true: {body}"
    )
    return body


def _all_rows(payload):
    """Every market row anywhere in the payload, at any nesting depth.

    A row that vanishes from `cultural_moments` but survives in `trending` or
    the cross-source spotlight is still on the reader's screen, so the arms
    below walk the whole document rather than one section.
    """
    found = []

    def _walk(node):
        if isinstance(node, dict):
            if "market_id" in node and "top_outcomes" in node:
                found.append(node)
            for value in node.values():
                _walk(value)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(payload)
    return found


def _rows_for(payload, market_id):
    return [r for r in _all_rows(payload) if r["market_id"] == market_id]


def _published_leg_names(payload, market_id):
    names = set()
    for row in _rows_for(payload, market_id):
        for leg in row["top_outcomes"]:
            names.add(leg["name"])
    return names


# ---------------------------------------------------------------------------
# Arms
# ---------------------------------------------------------------------------


class TestTheFixtureLandsWhereItClaims:
    """Before an absence means anything, the rows have to reach the page."""

    def test_every_market_classifies_into_a_rendered_theme(self):
        for market in _fixture():
            theme = entertainment_module._classify_theme(market)
            assert theme != "excluded", (
                f"{market.name!r} classifies as `excluded`, so it never "
                "reaches a builder and every assertion that its numbers are "
                "absent would pass against the defect itself."
            )

    async def test_the_control_is_published_in_full(self, client, mock_db, monkeypatch):
        _install_refusal(monkeypatch, WITHHELD_IDS)
        payload = await _payload(client, mock_db)
        rows = _rows_for(payload, CONTROL_ID)
        assert rows, (
            "the control market is absent from the payload, so this file "
            "cannot distinguish 'the refusal works' from 'the page rendered "
            "nothing'."
        )
        assert _published_leg_names(payload, CONTROL_ID) == {
            "Control leader",
            "Control second",
            "Control third",
        }


class TestAWithheldLegIsNotPublished:
    """The ship, on Specimen B's shape."""

    async def test_the_withheld_leader_is_absent_from_every_rendered_row(
        self, client, mock_db, monkeypatch
    ):
        _install_refusal(monkeypatch, WITHHELD_IDS)
        payload = await _payload(client, mock_db)
        rows = _rows_for(payload, PARTIAL_ID)
        assert rows, "the partially-withheld market vanished entirely; it has two supported legs and should still render"
        assert "Withheld leader" not in _published_leg_names(payload, PARTIAL_ID), (
            "`/entertainment` is publishing a price `/api/futures/{id}` "
            "withholds — the #8083 bypass, one tap from the page that refuses "
            "the same number."
        )

    async def test_the_headline_becomes_the_best_supported_leg(
        self, client, mock_db, monkeypatch
    ):
        _install_refusal(monkeypatch, WITHHELD_IDS)
        payload = await _payload(client, mock_db)
        for row in _rows_for(payload, PARTIAL_ID):
            assert row["prob"] == 40.0, (
                "the card still headlines the withheld leader's 93%. The "
                "headline is built from `priced[0]`, so a withheld leg left in "
                "that list re-publishes the refused number as the one figure a "
                f"reader is most likely to read: {row['prob']}"
            )

    async def test_the_supported_legs_survive(self, client, mock_db, monkeypatch):
        _install_refusal(monkeypatch, WITHHELD_IDS)
        payload = await _payload(client, mock_db)
        assert _published_leg_names(payload, PARTIAL_ID) == {
            "Supported runner up",
            "Supported third",
        }, (
            "withholding one leg dropped the legs nothing refused. The rail is "
            "per-outcome; it is not a market-level blackout."
        )


class TestAMarketWhoseEveryLegIsWithheldIsWithdrawn:
    """The ship, on Specimen A's shape — the Bachelorette card."""

    async def test_the_card_is_absent_from_the_whole_payload(
        self, client, mock_db, monkeypatch
    ):
        _install_refusal(monkeypatch, WITHHELD_IDS)
        payload = await _payload(client, mock_db)
        assert _rows_for(payload, ALL_WITHHELD_ID) == [], (
            "a market whose every price we refuse is still on the page. There "
            "is no honest headline available for it — this is the card that "
            "printed `Doug 93%` and opened on 'No prices in the last 30 days'."
        )


class TestTheGuardCanFail:
    """Anti-vacuity, in the other direction.

    Without this class every arm above would still pass if the route served an
    empty payload, if the fixture classified nowhere, or if the fake withheld
    everything. Re-running the identical fixture with the refusal returning the
    empty set has to PUBLISH the very numbers asserted absent above.
    """

    async def test_with_nothing_withheld_the_refused_numbers_are_published(
        self, client, mock_db, monkeypatch
    ):
        _install_refusal(monkeypatch, set())
        payload = await _payload(client, mock_db)

        assert _rows_for(payload, ALL_WITHHELD_ID), (
            "with nothing withheld this market must render — if it does not, "
            "`TestAMarketWhoseEveryLegIsWithheldIsWithdrawn` is passing for "
            "some reason other than the refusal and is not measuring the ship."
        )
        assert "Doug" in _published_leg_names(payload, ALL_WITHHELD_ID)
        assert "Withheld leader" in _published_leg_names(payload, PARTIAL_ID), (
            "with nothing withheld the leader must be published — otherwise "
            "`test_the_withheld_leader_is_absent_from_every_rendered_row` is "
            "asserting an absence the fixture creates on its own."
        )
        for row in _rows_for(payload, PARTIAL_ID):
            assert row["prob"] == 93.0


class TestTheRouteAsksTheSharedHelperAndNotACopy:
    """The one way this ship regresses is the call going away."""

    def test_the_symbol_is_the_one_futures_py_defines(self):
        assert (
            entertainment_module._withheld_price_outcome_ids
            is futures_module._withheld_price_outcome_ids
        ), (
            "`entertainment.py` is no longer pointing at the shared refusal. "
            "Adding an arm to `_withheld_price_outcome_ids` is supposed to "
            "reach this page for free; a local copy is the fifth spelling that "
            "helper's docstring exists to prevent."
        )

    async def test_it_is_awaited_for_every_market_the_page_considers(
        self, client, mock_db, monkeypatch
    ):
        calls = _install_refusal(monkeypatch, WITHHELD_IDS)
        await _payload(client, mock_db)
        assert set(calls) == {ALL_WITHHELD_ID, PARTIAL_ID, CONTROL_ID}, (
            "the refusal was not asked once per considered market. It is "
            "computed over `featured_eligible`, which is the superset of every "
            f"market that reaches a builder: {sorted(set(calls))}"
        )


class TestTheUnitDefaultDoesNotSilentlyDisableTheRail:
    """`withheld_ids` is defaulted, so the default itself is a hazard."""

    def test_market_row_called_without_the_argument_publishes_everything(self):
        row = entertainment_module._market_row(
            _market(
                market_id=PARTIAL_ID,
                name="Will the festival announce its lineup by November?",
                outcomes=PARTIAL_LEGS,
            )
        )
        assert row is not None
        assert {leg["name"] for leg in row["top_outcomes"]} == {
            "Withheld leader",
            "Supported runner up",
            "Supported third",
        }, (
            "the default is supposed to degrade to pre-#8083 behaviour, which "
            "is why the route-level arms above are the ones that hold the "
            "ship. If this ever changes, the wiring arms are no longer the "
            "only thing standing between the page and the bypass."
        )
