"""#4264 / CERT-2358 — the drain for the six disease rows the poller cannot reach.

CERT-2358 blocked the code-only ship on exactly one thing: the classifier fix is
correct, but `16630403` — "Hantavirus pandemic in 2026?", page one slot 5 — is one
of six rows the Polymarket poller has not re-seen in 1 to 83 days, so the reader
kept seeing the sun-and-cloud chip. This module is the required repair, and these
are its catching tests.

THE PLAN FUNCTION IS PURE, ON PURPOSE. `build_plan(rows) -> (plan, counts)` takes
the rows and returns the decision, so every case below drives the real decision
logic with no database and no mocking of the thing under test. What the tests here
do NOT cover is the SQL, which is asserted by shape in the apply/restore tests.

THE SPECIMENS ARE THE PRODUCTION ROWS, measured 2026-09-09 via db-query — the six
stale ones by id, and the genuine-weather control population by title.
"""

import pytest

from app.tasks.repair_weather_shelf_disease import (
    APPLY_CAP,
    NON_SPORT_DESTINATIONS,
    SOURCE,
    SUSPECT_CATEGORY,
    build_plan,
    plan_hash_for,
    undo_identity_for,
)


def row(
    mid,
    name,
    *,
    shelf="weather",
    category="weather",
    tags=("weather",),
    group_id=None,
):
    """One `futures_markets` row as `_select_population` returns it."""
    return {
        "id": mid,
        "name": name,
        "category": category,
        "llm_sport_category": shelf,
        "category_tags": list(tags) if tags is not None else [],
        "group_id": group_id,
        "external_id": str(mid),
    }


# --------------------------------------------------------------------------
# The six stale rows — the population CERT-2358 named
# --------------------------------------------------------------------------

# ids and titles are the production rows. `25196375` is the tagless CHILD; its
# parent `25196374` carries the tags and both share `polymarket:511422`.
STALE_PARENTS = [
    (16630403, "Hantavirus pandemic in 2026?"),
    (113563, "Measles cases in U.S. in 2026?"),
    (16630404, "Hantavirus vaccine in 2026?"),
    (21221338, "Ebola pandemic in 2026?"),
    (25196374, "Which countries will have an Ebola case in 2026?"),
]


@pytest.mark.parametrize("mid,name", STALE_PARENTS)
def test_each_stale_parent_is_planned_off_the_weather_shelf(mid, name):
    plan, counts = build_plan([row(mid, name)])
    assert len(plan) == 1, f"{name} was not planned: {counts}"
    assert plan[0]["id"] == mid
    assert plan[0]["from_shelf"] == "weather"
    assert plan[0]["to_shelf"] == "health"
    assert plan[0]["kind"] == "parent"


def test_the_page_one_card_is_in_the_plan():
    """`16630403` is the whole reason this repair exists.

    CERT-2358: "the named page-one Hantavirus row 16630403 is one of six stale
    rows … so that reader still sees the weather chip."
    """
    plan, _ = build_plan([row(16630403, "Hantavirus pandemic in 2026?")])
    assert [p["id"] for p in plan] == [16630403]
    assert plan[0]["to_shelf"] == "health"
    assert plan[0]["to_category"] == "health"


def test_all_six_stale_rows_move_in_one_pass():
    """The denominator, not a spot check.

    A per-row test goes green if five of six move and the reader still sees a sun
    over a pandemic on the row that did not.
    """
    rows = [row(mid, name) for mid, name in STALE_PARENTS]
    rows.append(
        row(
            25196375,
            "Will Uganda have an Ebola case in 2026?",
            category="game_prop",
            tags=[],
            group_id="polymarket:511422",
        )
    )
    rows[4]["group_id"] = "polymarket:511422"  # the child's parent

    plan, counts = build_plan(rows)
    assert counts["examined"] == 6
    assert len(plan) == 6, f"only {len(plan)} of 6 planned: {counts}"
    assert {p["id"] for p in plan} == {
        16630403, 113563, 16630404, 21221338, 25196374, 25196375
    }
    assert all(p["to_shelf"] == "health" for p in plan)


# --------------------------------------------------------------------------
# Children inherit and are NEVER classified alone
# --------------------------------------------------------------------------


def _ebola_group():
    """The real group: one tagged parent, thirteen tagless children."""
    parent = row(
        25196374,
        "Which countries will have an Ebola case in 2026?",
        group_id="polymarket:511422",
    )
    children = [
        row(
            mid,
            f"Will {country} have an Ebola case in 2026?",
            category="game_prop",
            tags=[],
            group_id="polymarket:511422",
        )
        for mid, country in [
            (25196375, "Uganda"), (25196376, "South Sudan"), (25196377, "Rwanda"),
            (25196378, "Burundi"), (25196379, "the United States"), (25196380, "Canada"),
            (25196381, "Kenya"), (25196382, "India"), (25196383, "the Republic of the Congo"),
            (25196384, "Nigeria"), (25196385, "Ethiopia"), (25196386, "Somalia"),
            (25196387, "China"),
        ]
    ]
    return [parent] + children


def test_the_whole_ebola_group_moves_together():
    plan, counts = build_plan(_ebola_group())
    assert len(plan) == 14
    assert counts["children_inheriting"] == 13
    assert all(p["to_shelf"] == "health" for p in plan)


def test_a_child_takes_its_parents_answer_not_its_own_title():
    """The load-bearing distinction.

    `_tags_to_category([])` returns no category, which drops a row into cascade
    arms 1 and 2 — the table-tennis group heuristic and the title/league fallback
    — with a `group_names` list this repair cannot reconstruct. A child classified
    alone could be relabelled `table_tennis`. So the child's plan entry must be an
    INHERIT, keyed to the parent that decided it.
    """
    plan, _ = build_plan(_ebola_group())
    child = next(p for p in plan if p["id"] == 25196375)
    assert child["kind"] == "child"
    assert child["arm"] == "inherit:25196374"
    assert child["to_shelf"] == "health"


def test_a_child_keeps_its_own_market_shape():
    """`category` on a child is its SHAPE (`game_prop`), not its subject shelf.

    The poller does not rewrite a sub-market's `category` from its parent, so
    neither does this repair — writing `health` there would corrupt the shape.
    """
    plan, _ = build_plan(_ebola_group())
    child = next(p for p in plan if p["id"] == 25196375)
    assert child["from_category"] == "game_prop"
    assert child["to_category"] == "game_prop"


def test_an_orphan_child_is_refused_and_counted_never_guessed():
    orphan = row(
        99999, "Will Somewhere have an Ebola case in 2026?",
        category="game_prop", tags=[], group_id="polymarket:does-not-exist",
    )
    plan, counts = build_plan([orphan])
    assert plan == []
    assert counts["refused_no_tags_no_parent"] == 1


def test_a_child_whose_parent_does_not_move_does_not_move():
    """A parent the cascade leaves on `weather` must not drag its children off it."""
    parent = row(
        7001, "How many named storms in the 2026 Atlantic season?",
        group_id="polymarket:7001",
    )
    child = row(
        7002, "Will storm #3 make landfall?",
        category="game_prop", tags=[], group_id="polymarket:7001",
    )
    plan, counts = build_plan([parent, child])
    assert plan == []
    assert counts["refused_unchanged"] == 2


# --------------------------------------------------------------------------
# THE CONTROL — 982 open markets sit on `weather` legitimately
# --------------------------------------------------------------------------
#
# The easy over-correction is a blanket "the weather shelf is suspect" sweep, and
# it is a bigger regression than the bug. These are real production titles.

GENUINELY_WEATHER = [
    "Will the world pass 2 degrees Celsius over pre-industrial levels?",
    "Will a supervolcano erupt before 2050?",
    "Will there be an at least 8.0 magnitude earthquake in 2026?",
    "EU meets its 2030 climate goals?",
    "India meets its 2030 climate goals?",
    "Arctic sea ice extent below 4 million km2 in 2026?",
    "Will El Nino conditions return before 2027?",
    "Vail ski resort opening date 2026?",
    "White Christmas in NYC in 2026?",
    "Highest temperature in Phoenix in July?",
    "How many named storms in the 2026 Atlantic season?",
    "Major volcano eruption (VEI 6 or above) in 2026?",
]


@pytest.mark.parametrize("name", GENUINELY_WEATHER)
def test_a_genuine_weather_market_is_never_planned(name):
    plan, counts = build_plan([row(9000, name)])
    assert plan == [], f"the control moved: {name} -> {plan}"
    assert counts["refused_unchanged"] == 1


def test_the_control_population_survives_a_mixed_pass():
    """Bug rows and control rows in ONE selection, which is how it runs live.

    A repair that is only ever handed its own bug rows has not been shown to
    discriminate.
    """
    rows = [row(9000 + i, n) for i, n in enumerate(GENUINELY_WEATHER)]
    rows += [row(mid, name) for mid, name in STALE_PARENTS]

    plan, counts = build_plan(rows)
    assert {p["id"] for p in plan} == {mid for mid, _ in STALE_PARENTS}
    assert counts["refused_unchanged"] == len(GENUINELY_WEATHER)
    assert len(plan) == 5


# --------------------------------------------------------------------------
# Refusals — every zero state gets its own terminal (gotcha #53)
# --------------------------------------------------------------------------


def test_a_sport_promotion_is_refused_not_written():
    """Arm 3 can promote a market to a SPORT. That is out of scope here.

    This repair moves rows between non-sport shelves; a sport answer means
    something else is going on and is counted rather than written.
    """
    plan, counts = build_plan(
        [row(9500, "Who will win the 2027 NBA Championship?")]
    )
    assert plan == []
    assert counts["refused_sport"] == 1


def test_word_bingo_stays_put():
    plan, counts = build_plan([row(9600, "Will Trump say 'Ebola' this week?")])
    assert plan == []
    assert counts["refused_unchanged"] == 1


def test_counts_account_for_every_examined_row():
    """No row may be silently dropped between `examined` and the terminals."""
    rows = _ebola_group() + [row(9000 + i, n) for i, n in enumerate(GENUINELY_WEATHER)]
    plan, counts = build_plan(rows)
    accounted = (
        counts["planned"]
        + counts["refused_unchanged"]
        + counts["refused_other"]
        + counts["refused_sport"]
        + counts["refused_no_tags_no_parent"]
    )
    assert accounted == counts["examined"] == len(rows)


# --------------------------------------------------------------------------
# Plan addressing and the undo identity
# --------------------------------------------------------------------------


def test_the_plan_hash_changes_when_a_transition_changes():
    a, _ = build_plan([row(16630403, "Hantavirus pandemic in 2026?")])
    b, _ = build_plan([row(21221338, "Ebola pandemic in 2026?")])
    assert plan_hash_for(a) != plan_hash_for(b)


def test_the_plan_hash_is_stable_for_the_same_plan():
    a, _ = build_plan([row(mid, n) for mid, n in STALE_PARENTS])
    b, _ = build_plan([row(mid, n) for mid, n in STALE_PARENTS])
    assert plan_hash_for(a) == plan_hash_for(b)


def test_two_applies_of_the_same_plan_get_different_undo_identities():
    """Otherwise the second apply's record overwrites the first one's and the
    earlier rows become unrestorable — the failure mode named in
    `repair_authority_id_collisions` ("planning MLB destroyed MLS's undo").
    """
    from datetime import datetime, timezone

    at = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)
    one = undo_identity_for("abc123", at=at, invocation="aaaaaaaaaaaa")
    two = undo_identity_for("abc123", at=at, invocation="bbbbbbbbbbbb")
    assert one != two


# --------------------------------------------------------------------------
# Module contract
# --------------------------------------------------------------------------


def test_the_repair_is_registered_under_a_name_the_dispatcher_can_route():
    from app.routes.admin_repairs import _REPAIRS

    assert _REPAIRS["weather-shelf-disease"] == (
        "app.tasks.repair_weather_shelf_disease",
        "repair",
    )


def test_the_repair_signature_declares_the_params_it_documents():
    """The dispatcher forwards ONLY params a repair's signature declares, silently.

    `test_repair_polymarket_sport_category_q496.py` exists because a comment named
    `after_commence`, FastAPI dropped it, and an operator re-read page one forever
    while the response looked busy. `undo_identity` is this repair's D51 contract;
    if the signature stops declaring it, the restore silently becomes a re-apply.
    """
    import inspect

    from app.tasks.repair_weather_shelf_disease import repair as fn

    params = inspect.signature(fn).parameters
    assert "undo_identity" in params
    assert "limit" in params


def test_it_is_not_wired_to_a_beat():
    """"A drain with an end state, not a standing job." Also gotcha #12's list."""
    from app.tasks import celery_app

    schedule = celery_app.conf.beat_schedule or {}
    assert schedule, "no beat schedule loaded — this guard would pass vacuously"
    for name, entry in schedule.items():
        assert "weather_shelf_disease" not in str(entry.get("task", "")), name


def test_module_constants_are_what_the_ship_describes():
    assert SUSPECT_CATEGORY == "weather"
    assert SOURCE == "polymarket"
    assert "health" in NON_SPORT_DESTINATIONS
    assert APPLY_CAP == 60
