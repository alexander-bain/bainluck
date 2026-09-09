"""#4153 at the route — Alex's verification sentence, run against the endpoint.

From the issue: *"`curl "$BAINLUCK_API/api/futures/grouped-feed?sports_only=true&limit=20"`
and assert no `group_id` appears on more than one card in `feed`. Today that
assertion fails 4 ways."*

`test_no_group_id_appears_on_more_than_one_card` IS that assertion. It is driven
through the real `grouped_feed` coroutine with a stub session rather than
through the pure detector, because the defect was never in the detector — it was
in the assembly, where 84 container legs walked past every grouping pass and
came out as 84 cards. A unit test of the fold would have passed on the broken
build.

RED-FIRST (verified 2026-09-08 before the fix landed): with the fold removed
from the route, this file reports
``AssertionError: group_id polymarket:910235 appears on 5 cards`` and
``polymarket:811116 appears on 3 cards``. The fixture is a shrunk copy of the
production pool measured that night.
"""

import collections

import pytest

from app.routes.futures import grouped_feed

# ── the stub session ───────────────────────────────────────────────────────
#
# The route makes three reads in order: the candidate pool (consumed as
# `.scalars().unique().all()`), the container groups' parent rows and their full
# membership (both consumed as `.all()`). A queue of canned results keeps the
# test honest about that order — a fourth read, or a reordering, fails loudly
# here rather than silently serving a stale shape.


class _StubResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def unique(self):
        return self

    def all(self):
        return list(self._rows)


class _StubSession:
    def __init__(self, results):
        self._results = list(results)
        self.calls = 0
        self.statements = []

    async def execute(self, _stmt):
        self.calls += 1
        self.statements.append(_stmt)
        if not self._results:
            raise AssertionError(
                f"the route made {self.calls} reads; the fixture canned "
                f"{self.calls - 1}"
            )
        return _StubResult(self._results.pop(0))


class _Outcome:
    def __init__(self, oid, name, probability):
        self.id = oid
        self.name = name
        self.probability = probability
        self.american_odds = None


class _Market:
    def __init__(self, mid, name, group_id, market_type, outcomes, sport="tennis"):
        self.id = mid
        self.name = name
        self.source = "polymarket"
        self.category = "game_prop"
        self.llm_sport_category = sport
        self.status = "open"
        self.group_id = group_id
        self.group_type = "polymarket_sub_market"
        self.market_type = market_type
        self.outcomes = outcomes


class _Request:
    scope: dict = {}


class _Response:
    def __init__(self):
        self.headers = {}


# ── the fixture: a shrunk copy of the pool measured on 2026-09-08 ──────────

_FINAL = "Will {} advance to the Final in Women's Singles at the 2026 US Open?"
_BALLON = "Will {} finish in the top 5 of the 2026 Ballon d'Or?"

_US_OPEN = [
    ("Belinda Bencic", 0.833),
    ("Maria Sakkari", 0.480),
    ("Coco Gauff", 0.425),
    ("Elena Rybakina", 0.385),
    ("Iga Swiatek", 0.230),
]
_BALLON_DOR = [
    ("Rodri", 0.765),
    ("Erling Haaland", 0.100),
    ("Achraf Hakimi", 0.034),
]


def _pool():
    """What `ORDER BY updated_at DESC LIMIT 100` actually returns: the legs.

    The parent `field` rows are NOT here, and that is the mechanism — they are
    priced once and then sit still while their members are polled, so they never
    reach the top of an `updated_at` ordering.
    """
    markets = []
    mid = 1
    for template, group, members in (
        (_FINAL, "polymarket:910235", _US_OPEN),
        (_BALLON, "polymarket:811116", _BALLON_DOR),
    ):
        for entity, probability in members:
            markets.append(
                _Market(
                    mid,
                    template.format(entity),
                    group,
                    "container_member",
                    [
                        _Outcome(mid * 100, "Yes", probability),
                        _Outcome(mid * 100 + 1, "No", 1 - probability),
                    ],
                )
            )
            mid += 1
    # One market that is a whole question on its own — the control. It must
    # still arrive as its own card.
    markets.append(
        _Market(
            999,
            "Will there be at least 1 run scored in the first inning?",
            "polymarket:13338",
            "container_member",
            [_Outcome(99900, "Yes", 0.62), _Outcome(99901, "No", 0.38)],
            sport="baseball",
        )
    )
    return markets


def _parents():
    return [
        ("polymarket:910235", "US Open 2026: To Reach the Final (Women's Singles)"),
        ("polymarket:811116", "Ballon d'Or Top 5 Finish 2026"),
    ]


def _members(complements=None):
    """Both legs of every member, the shape the route reads since #4203.

    ``complements`` overrides the No leg for a named entity; anything not named
    gets the coherent ``1 - Yes`` a healthy market has.
    """
    complements = complements or {}
    rows = []
    mid = 1
    for template, group, members in (
        (_FINAL, "polymarket:910235", _US_OPEN),
        (_BALLON, "polymarket:811116", _BALLON_DOR),
    ):
        for entity, probability in members:
            name = template.format(entity)
            no_leg = complements.get(entity, 1 - probability)
            rows.append((group, mid, name, "polymarket", "Yes", probability))
            if no_leg is not None:
                rows.append((group, mid, name, "polymarket", "No", no_leg))
            mid += 1
    return rows


async def _serve(limit=20, complements=None):
    session = _StubSession([_pool(), _parents(), _members(complements)])
    return await grouped_feed(
        request=_Request(),
        response=_Response(),
        category=None,
        sport=None,
        sports_only=True,
        limit=limit,
        db=session,
    )


def _group_ids_on_card(card):
    """Every group a card speaks for, however it carries it."""
    if card.get("type") != "market":
        return set()
    outcomes = (card.get("market") or {}).get("outcomes") or []
    return {o["group_id"] for o in outcomes if o.get("group_id")}


# ── Alex's assertion ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_no_group_id_appears_on_more_than_one_card():
    payload = await _serve()
    seen = collections.Counter()
    for card in payload["feed"]:
        for group_id in _group_ids_on_card(card):
            seen[group_id] += 1
    offenders = {g: n for g, n in seen.items() if n > 1}
    assert not offenders, "; ".join(
        f"group_id {g} appears on {n} cards" for g, n in offenders.items()
    )


@pytest.mark.asyncio
async def test_the_wall_of_eight_becomes_two_cards():
    payload = await _serve()
    titles = [c["market"]["name"] for c in payload["feed"] if c.get("type") == "market"]
    assert "US Open 2026: To Reach the Final (Women's Singles)" in titles
    assert "Ballon d'Or Top 5 Finish 2026" in titles
    # Not one "Will <player> …?" leg survives as its own card.
    assert not [t for t in titles if t.startswith("Will ") and "advance" in t]
    assert not [t for t in titles if t.startswith("Will ") and "Ballon" in t]


@pytest.mark.asyncio
async def test_the_folded_card_ranks_the_field_leader_first():
    payload = await _serve()
    card = next(
        c
        for c in payload["feed"]
        if c.get("type") == "market" and c["market"]["name"].startswith("US Open 2026")
    )
    rows = card["market"]["outcomes"]
    assert [r["name"] for r in rows][:3] == [
        "Belinda Bencic",
        "Maria Sakkari",
        "Coco Gauff",
    ]
    assert rows[0]["probability"] == pytest.approx(0.833)


@pytest.mark.asyncio
async def test_a_market_that_is_its_own_question_is_left_alone():
    """The fold must not eat singletons — the control card still ships."""
    payload = await _serve()
    names = [c["market"]["name"] for c in payload["feed"] if c.get("type") == "market"]
    assert "Will there be at least 1 run scored in the first inning?" in names


@pytest.mark.asyncio
async def test_the_folded_card_keeps_its_pool_rows_sport_and_category():
    """A fabricated sport would file a tennis card under another filter."""
    payload = await _serve()
    card = next(
        c
        for c in payload["feed"]
        if c.get("type") == "market" and c["market"]["name"].startswith("US Open 2026")
    )
    assert card["market"]["sport"] == "tennis"
    assert card["market"]["category"] == "game_prop"


@pytest.mark.asyncio
async def test_the_card_links_to_the_leaders_market_not_the_parents():
    """#4163 — the parent field row prints 0% for this card's leader."""
    payload = await _serve()
    card = next(
        c
        for c in payload["feed"]
        if c.get("type") == "market" and c["market"]["name"].startswith("US Open 2026")
    )
    assert card["market"]["id"] == 1  # Bencic's own market, the 83.3% leader


@pytest.mark.asyncio
async def test_the_fold_is_counted_as_grouping_not_as_leftovers():
    payload = await _serve()
    assert payload["group_counts"]["container_field"] == 2
    assert payload["total_grouped"] >= 2


@pytest.mark.asyncio
async def test_a_pool_with_nothing_to_fold_makes_no_extra_reads():
    """The two fold queries are skipped outright when no group repeats.

    This endpoint was measured at ~1 s before it was cached (LAT-P100); a fix
    for a flood must not tax the pools that never flood.
    """
    solo = [
        _Market(
            42,
            "Will there be at least 1 run scored in the first inning?",
            "polymarket:13338",
            "container_member",
            [_Outcome(4200, "Yes", 0.62)],
            sport="baseball",
        )
    ]
    session = _StubSession([solo])  # one canned read; a second would raise
    payload = await grouped_feed(
        request=_Request(),
        response=_Response(),
        category=None,
        sport=None,
        sports_only=True,
        limit=20,
        db=session,
    )
    assert session.calls == 1
    assert payload["group_counts"]["container_field"] == 0
    assert len(payload["feed"]) == 1


# ── #4203 at the route: a contradicting member never reaches the card ──────


@pytest.mark.asyncio
async def test_a_member_whose_legs_contradict_is_not_served_on_the_card():
    """The production case, end to end.

    Bencic held ``Yes 0.833`` and ``No 1.000`` while the venue had her closed at
    0, and the #4153 fold ranked her 2nd on "To Reach the Final". The route must
    read both legs and drop her — with the fold otherwise intact, which is why
    this asserts the surviving order rather than just her absence.
    """
    payload = await _serve(complements={"Belinda Bencic": 1.000})
    card = next(
        c
        for c in payload["feed"]
        if c.get("type") == "market" and c["market"]["name"].startswith("US Open 2026")
    )
    rows = [r["name"] for r in card["market"]["outcomes"]]
    assert "Belinda Bencic" not in rows
    assert rows[:3] == ["Maria Sakkari", "Coco Gauff", "Elena Rybakina"]


@pytest.mark.asyncio
async def test_the_dropped_members_market_is_not_left_behind_as_its_own_card():
    """Dropping her from the ranking must not resurrect the wall #4153 removed.

    ``market_ids`` covers every member of the group, refused ones included, so
    the leg is still claimed by the folded card and never re-emerges as one of
    the twelve "Will <player> …?" cards.
    """
    payload = await _serve(complements={"Belinda Bencic": 1.000})
    titles = [c["market"]["name"] for c in payload["feed"] if c.get("type") == "market"]
    assert not [t for t in titles if t.startswith("Will ") and "advance" in t]


@pytest.mark.asyncio
async def test_the_membership_read_asks_for_both_legs():
    """The stub answers any statement, so the SQL itself needs pinning.

    Every other #4203 test feeds `complement_probability` in through canned
    rows, which means a revert of the membership query to ``name == 'yes'``
    would leave `_legs_agree` reading `None` for every member — kept, unjudged,
    Bencic back on the card — with all of them still green. This reads the
    third statement the route actually issued.
    """
    session = _StubSession([_pool(), _parents(), _members()])
    await grouped_feed(
        request=_Request(),
        response=_Response(),
        category=None,
        sport=None,
        sports_only=True,
        limit=20,
        db=session,
    )
    sql = str(
        session.statements[2].compile(compile_kwargs={"literal_binds": True})
    ).lower()
    assert "'yes'" in sql and "'no'" in sql
