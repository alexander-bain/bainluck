"""THE ROUTE ITSELF PUTS THE QUESTION — driven through ``_build_sections`` (#3903).

ux/1127 · PILLAR: TRUTH · SHIP: tapping a match on the US Open hub no longer
changes the percentage or flips the move arrow.

═══ WHY THIS FILE EXISTS, IN ONE PARAGRAPH ═══

CERT-2234 granted #3903 its token and named a follow-up it judged non-blocking:
``HUB-MATCH-PARITY-REAL-ROUTE-GUARD-3903`` — *"the present tests inject the blend
map"*.  CERT-2235 then blocked the same sha for a defect living in exactly that
untested gap: ``_load_blends`` selected ``Event.home_team`` (a ``relationship()``,
compiling to a boolean comparison in an unnamed result key) instead of
``Event.home_team_name``, so every linked row refused by name.  The repair
landed, was graded GREEN, merged, deployed — and the hub still disagreed with the
match page, because a SECOND seam in the same route was equally unguarded.

Measured on production ``c0f46f3b`` at 11:00Z on 2026-09-08, rendered and read::

    hub   Carlos Alcaraz 79%  ▲+2   "Carlos Alcaraz opened at 77%."
    page  24% – 76%                 "Opened 24% – 76%"   (11 sportsbooks)

Twice now the mechanism has been correct and the WIRING has been wrong, and both
times every unit test passed.  So the guard stops injecting anything: it builds
the first screen through the real ``_build_sections``, with a fake session that
answers real SQL, and asserts on the payload the route returns.

═══ WHAT IS FAKED, AND WHY EACH ONE IS NOT THE SUBJECT ═══

The register file, the Redis link overlay, the price loader, the matchup
resolver, the ESPN scoreboard and the ESPN competition linker.  Every one is an
INPUT to the ordering under test — none of them is the ordering.  The two things
this file refuses to fake are the ones that broke: the ``events`` read
(``_load_blends`` runs its real ``select()`` against a session that answers it by
column name, so a relationship column would come back unnamed here exactly as it
did in production) and the sequence of calls inside ``_build_sections``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from app.routes import tournaments as route
from app.utils.tournament_register import SCHEMA_VERSION
from app.utils.tournament_slate import PRICE_BASIS_BLEND, PRICE_BASIS_VENUE

COMP = "182777"
EVENT_ID = 15306813
HOME, AWAY = "Ben Shelton", "Carlos Alcaraz"
HOME_ID, AWAY_ID = 2708, 5992

#: The two production readings above, as probabilities for the HOME side.
#: Venue 21.5% opening 23.5% (down); event 23.81% opening 23.81% (flat). The
#: level differs AND the direction differs, so a row that kept its venue numbers
#: cannot pass by coincidence on either axis.
VENUE_NOW, VENUE_OPEN = 0.215, 0.235
EVENT_NOW, EVENT_OPEN = 0.2381, 0.2381


class _Row:
    """What ``session.execute(select(cols))`` yields — attributes by column name.

    Deliberately NOT a dict and NOT an ORM object: a `Row` answers `getattr` for
    precisely the labels the `select()` asked for, and the CERT-2235 defect was
    that a `relationship()` column produces no such label. Building this from the
    statement's own `column_descriptions` (below) rather than from a fixed
    signature is what lets that mistake reappear as a red test here.
    """

    def __init__(self, values: dict[str, Any]) -> None:
        for key, value in values.items():
            setattr(self, key, value)


class _Result:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def all(self) -> list[Any]:
        return self._rows

    def scalars(self) -> "_Result":
        return self

    def unique(self) -> "_Result":
        return self


class _Session:
    """Answers the two real queries ``_build_sections`` still makes on this path.

    Records every ``events`` id list it is asked for, which is how the tests
    below prove the SECOND load happened and covered exactly the ids the ESPN
    linker had just resolved.
    """

    def __init__(self, event_columns: dict[str, Any]) -> None:
        self.event_columns = event_columns
        self.blend_id_batches: list[list[int]] = []
        #: The labels the REAL `select()` asked for, captured off the statement
        #: rather than restated here — this is the only place the CERT-2235
        #: mistake is visible, and asserting on a fixture instead would be a
        #: guard that cannot fail.
        self.blend_labels: list[str] = []

    async def execute(self, stmt: Any) -> _Result:
        labels = [desc["name"] for desc in stmt.column_descriptions]
        if labels == ["Event"]:
            # The #3729 blank-row fill. Nothing on this card is blank, so the
            # route should never get here; answering honestly rather than
            # raising keeps this fake from asserting a fact by accident.
            return _Result([])

        requested = sorted(
            {
                int(value)
                for value in stmt.whereclause.right.value
                if isinstance(value, int)
            }
        )
        self.blend_id_batches.append(requested)
        self.blend_labels = labels
        if EVENT_ID not in requested:
            return _Result([])
        # Built from the labels the statement actually asked for. A `select()`
        # naming `Event.home_team` yields the label `home_team`, so `home_team_name`
        # would be MISSING here and `resolve_hero`/`orient_event_blend` would fail
        # by name — the CERT-2235 defect, reproduced rather than papered over.
        return _Result([_Row({label: self.event_columns.get(label) for label in labels})])


def _event_columns() -> dict[str, Any]:
    """The `events` row behind the hero, in the columns `resolve_hero` reads."""
    return {
        "id": EVENT_ID,
        "home_team_name": HOME,
        "away_team_name": AWAY,
        "status": "scheduled",
        "home_score": None,
        "away_score": None,
        "completed_at": None,
        "win_probability_sources": {
            "betting": {
                "value": EVENT_NOW,
                "updated_at": "2026-09-08T10:40:00+00:00",
            },
            "betting_book_count": 11,
        },
        "espn_win_prob_home": None,
        "opening_home_probability": EVENT_OPEN,
        "opening_away_probability": round(1 - EVENT_OPEN, 4),
    }


def _competitor(name: str, athlete_id: int, order: int) -> dict[str, Any]:
    return {
        "name": name,
        "espn_athlete_id": athlete_id,
        "flag_url": None,
        "country": "USA",
        "determined": True,
        "order": order,
    }


def _register() -> dict[str, Any]:
    """A register with NO matchups — the scoreboard is the only source of rows.

    This is the shape that produces the defect: with no register pairing there is
    nothing for ``resolve_matchup_events`` to resolve, so the first blend load
    runs on an EMPTY id list and the event is reachable only through the ESPN
    linker that runs later.
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "tournament": "us-open",
        "season": "2026",
        "version": 14,
        "generated_at": "2026-09-08T10:50:00+00:00",
        "draw_released": True,
        "players": [],
        "matchups": [],
    }


@pytest.fixture
def wired(monkeypatch: pytest.MonkeyPatch) -> _Session:
    """Everything around the ordering, stubbed; the ordering itself, real."""
    now = datetime.now(timezone.utc)
    observed = now - timedelta(minutes=1)

    monkeypatch.setattr(route, "load_register", lambda slug, season: _register())

    async def _read_links(slug: str) -> dict[str, Any]:
        return {
            "links": {},
            "authority_links": {
                f"espn:{COMP}|kalshi": {
                    "source": "kalshi",
                    "kind": "match",
                    "market_id": 61000001,
                    "outcome_id": 910001,
                    "status": "live",
                    "sides": {
                        f"espn:athlete:{HOME_ID}": {"outcome_id": 910001},
                        f"espn:athlete:{AWAY_ID}": {"outcome_id": 910002},
                    },
                }
            },
        }

    async def _load_prices(db, ids, *, now):  # noqa: ANN001
        return {
            910001: {
                "probability": VENUE_NOW,
                "opening_probability": VENUE_OPEN,
                "observed_at": observed,
            },
            910002: {
                "probability": round(1 - VENUE_NOW, 4),
                "opening_probability": round(1 - VENUE_OPEN, 4),
                "observed_at": observed,
            },
        }

    async def _load_series(db, ids, *, now):  # noqa: ANN001
        return {}

    async def _resolve_matchup_events(db, register):  # noqa: ANN001
        # No register matchups, so no ids — the situation, not a simplification.
        return {"by_event": {}, "by_matchup": {}, "reason_counts": {}}

    async def _espn_results(slug: str) -> dict[str, Any]:
        return {
            "scoreboard": "live",
            "order_of_play_complete": True,
            "order_of_play": {
                COMP: {
                    "espn_competition_id": COMP,
                    "draw": "mens-singles",
                    "state": "pre",
                    "start_at": "2026-09-08T21:30:00+00:00",
                    "start_is_tbd": False,
                    "status_detail": "5:30 PM",
                    "espn_round": "Quarterfinal",
                    "players": [HOME, AWAY],
                    "competitors": [
                        _competitor(HOME, HOME_ID, 1),
                        _competitor(AWAY, AWAY_ID, 2),
                    ],
                }
            },
        }

    async def _resolve_espn(db, comp_ids, sport_keys):  # noqa: ANN001
        # THE LINKER IS THE WHOLE POINT: it is the only thing that ever names
        # this event id, and it runs AFTER the slate was built.
        return {"by_espn": {COMP: EVENT_ID}, "reason_counts": {}}

    monkeypatch.setattr(route, "read_links", _read_links)
    monkeypatch.setattr(route, "_load_prices", _load_prices)
    monkeypatch.setattr(route, "_load_series", _load_series)
    monkeypatch.setattr(route, "resolve_matchup_events", _resolve_matchup_events)
    monkeypatch.setattr(route, "_espn_results", _espn_results)
    monkeypatch.setattr(route, "resolve_espn_competition_events", _resolve_espn)
    return _Session(_event_columns())


async def _first_screen(session: _Session) -> dict[str, Any]:
    sections = await route._build_sections(
        "us-open",
        route.REGISTERED_TOURNAMENTS["us-open"],
        session,  # type: ignore[arg-type]
        groups=(route.SECTION_FIRST,),
    )
    return sections[route.SECTION_FIRST]


def _the_row(first: dict[str, Any]) -> dict[str, Any]:
    """The vacuity gate. Every assertion below reads a row off this list."""
    rows = first["slate"]["matches"]
    assert len(rows) == 1, f"route built no scoreboard row; matches={rows}"
    return rows[0]


# ---------------------------------------------------------------------------
# The ship, through the real route
# ---------------------------------------------------------------------------


async def test_the_route_serves_the_event_number_on_a_linker_only_row(wired):
    """The one assertion that would have failed on production this morning."""
    row = _the_row(await _first_screen(wired))

    assert row["pairing_source"] == "scoreboard"
    assert row["event_id"] == EVENT_ID
    assert row["price_basis"] == PRICE_BASIS_BLEND
    assert row["blend_refusal"] is None
    assert row["sides"][0]["probability"] == pytest.approx(EVENT_NOW)
    # And it is genuinely not the venue's number, on the level...
    assert row["sides"][0]["probability"] != pytest.approx(VENUE_NOW)
    # ...nor on the direction: the venue moved DOWN, the event has not moved.
    assert VENUE_NOW - VENUE_OPEN < 0
    assert row["sides"][0]["move"] == pytest.approx(0.0)


async def test_the_route_asks_the_database_for_the_id_only_the_linker_knew(wired):
    """The seam, named: a second load, covering exactly the newly linked ids.

    Without it the overlay would run against a map that cannot contain this
    event and would refuse every row by name — changing the refusal from silent
    to stated and the number not at all.
    """
    await _first_screen(wired)

    # EXACTLY ONE `events` READ, FOR EXACTLY THE LINKER'S ID. The first-screen
    # load is driven by register matchups, of which this register has none, and
    # `_load_blends` returns `{}` on an empty id list WITHOUT touching the
    # session — so the only statement that reaches the database here is the
    # second one, and its id list is the whole ship.
    assert wired.blend_id_batches == [[EVENT_ID]]


async def test_the_second_load_is_skipped_when_the_linker_finds_nothing_new(
    wired, monkeypatch
):
    """The bound. A register that pins its own ids must not pay for a second read.

    Asserted as a COST property because that is what it is: the extra query is
    justified only by being conditional, and a version that always fired would
    pass every other test in this file.
    """

    async def _no_links(db, comp_ids, sport_keys):  # noqa: ANN001
        return {"by_espn": {}, "reason_counts": {}}

    monkeypatch.setattr(route, "resolve_espn_competition_events", _no_links)
    row = _the_row(await _first_screen(wired))

    # No `events` statement at all: nothing to load first (no register
    # matchups), and nothing newly linked to load second.
    assert wired.blend_id_batches == []
    assert row["event_id"] is None
    assert row["price_basis"] == PRICE_BASIS_VENUE


# ---------------------------------------------------------------------------
# The CERT-2235 defect, kept dead through the real loader
# ---------------------------------------------------------------------------


async def test_a_row_whose_names_do_not_orient_says_why_on_the_payload(wired):
    """`price_basis: "venue"` beside `blend_refusal: null` is what hid this twice.

    A linked row that still shows a venue price has to account for itself. This
    is also the guard that keeps the CERT-2235 class dead: selecting the
    `relationship()` columns again would deliver rows with no `home_team_name`,
    which lands here — a STATED refusal — rather than in a silent pass.
    """
    wired.event_columns["home_team_name"] = "Someone Else"
    wired.event_columns["away_team_name"] = "Another Person"
    row = _the_row(await _first_screen(wired))

    assert row["event_id"] == EVENT_ID
    assert row["price_basis"] == PRICE_BASIS_VENUE
    assert row["blend_refusal"] is not None
    assert row["sides"][0]["probability"] == pytest.approx(VENUE_NOW)


async def test_the_loader_selects_columns_that_carry_the_names(wired):
    """The SELECT half of CERT-2235, asserted where the route actually runs it.

    `Event.home_team` is a `relationship()`. It compiles without error into a
    boolean comparison landing in an unnamed key, so the mistake is invisible
    until a row is read. This reads the labels off the statement the route
    actually issued — asserting on this file's own fixture instead would be a
    guard that could never fail.
    """
    await _first_screen(wired)

    labels = set(wired.blend_labels)
    assert labels, "the route issued no `events` statement to inspect"
    assert {"home_team_name", "away_team_name"} <= labels
    assert not {"home_team", "away_team"} & labels


async def test_an_event_with_no_hero_leaves_the_row_on_the_venue_price(wired):
    """Zverev v van de Zandschulp on 2026-09-08: the event page had NO number.

    The hub still held a venue price and must go on showing it — a linked event
    that cannot answer is a reason to keep the venue quote, never to blank a card
    that had one.
    """
    wired.event_columns["win_probability_sources"] = {}
    wired.event_columns["opening_home_probability"] = None
    wired.event_columns["opening_away_probability"] = None
    row = _the_row(await _first_screen(wired))

    assert row["priced"] is True
    assert row["price_basis"] == PRICE_BASIS_VENUE
    assert row["sides"][0]["probability"] == pytest.approx(VENUE_NOW)
    assert row["blend_refusal"] is not None
