"""Q495 — the drain half of Q493. Guards for `repair_polymarket_sport_category`.

WHAT THESE GUARD, AND WHY THEY ARE SHAPED THIS WAY
==================================================

Q493 fixed the classifier; Q495 drives it over rows the poller never re-fetches.
The risk is therefore NOT "does the classifier work" (CERT-663 already graded
that, and production confirmed 44/44). The risk is that this rail quietly
becomes a SECOND classifier that disagrees with the shipped one, or that it
relabels the whole bucket to a single wrong answer and reports a big `changed`
count as success.

So the oracle here is the PRODUCTION RESULT, pinned:

  * a real US Open ATP event payload must come back `tennis`;
  * a real Setka payload must come back `table_tennis` — the control that rode
    the same code path on production and did not move.

`test_rail_contains_no_sport_rules_of_its_own` is the one that matters most: it
fails if anyone adds a sport keyword to this module, which is exactly how the
"second classifier" failure would arrive. It is written to RAISE if it cannot
find the module source rather than pass vacuously (the getsource lesson).
"""

from __future__ import annotations

import inspect

import pytest

from app.tasks import repair_polymarket_sport_category as rail


# ---------------------------------------------------------------------------
# Payload fixtures — shaped like the real Gamma `/events/{id}` response.
# ---------------------------------------------------------------------------

#: Market names below are the REAL stored names, read off production event
#: `924377` and Setka event `945534` on 2026-09-01. Invented ones would not
#: exercise the mechanism: `detect_game_prop_sport` only parses the
#: "Matchup: Stat" form, so a bare "Total Games O/U 4.5" returns None and the
#: whole gate goes untested while the test still passes.
#:
#: CRUCIALLY, BOTH GROUPS TRIP `detect_table_tennis_group` (verified: True for
#: each). That is deliberate and is Q493's own guard design — if only the Setka
#: group tripped it, the US Open assertion would pass whether the tag gate works
#: or not. Because both trip it, **only the tag can tell them apart**, so these
#: two tests genuinely drive the gate rather than the heuristic.

#: A real US Open ATP event: tagged "Tennis", carrying the per-SET games prop
#: whose total (8.5) sits BELOW the table-tennis threshold. That child is
#: exactly what tripped the unguarded arm 1 and relabelled the main draw.
US_OPEN_EVENT = {
    "id": "924377",
    "title": "US Open ATP: Jiri Lehecka vs Pablo Carreno Busta",
    "tags": [{"label": "Tennis"}, {"label": "Sports"}, {"label": "Games"}],
    "markets": [
        {"question": "US Open ATP: Jiri Lehecka vs Pablo Carreno Busta"},
        {"question": "Lehecka vs. Busta: Set 2 Games O/U 8.5"},
        {"question": "Lehecka vs. Busta: Match O/U 36.5"},
        {"question": "Jiri Lehecka vs. Pablo Carreno Busta: Total Sets O/U 3.5"},
    ],
}

#: A real Setka/TT-Cup event: tagged "Table Tennis" + "Setka", with the bare
#: "Player vs. Player" title that used to route to baseball.
SETKA_EVENT = {
    "id": "945534",
    "title": "Salaru Nicolae vs. Urechean Vadim",
    "tags": [{"label": "Table Tennis"}, {"label": "Setka"}, {"label": "Sports"}],
    "markets": [
        {"question": "Salaru Nicolae vs. Urechean Vadim"},
        {"question": "Salaru Nicolae vs. Urechean Vadim: Total Games O/U 4.5"},
        {"question": "Game Handicap: Urechean Vadim (-1.5) vs Salaru Nicolae (+1.5)"},
    ],
}


def test_both_fixtures_trip_the_heuristic_so_only_the_tag_can_decide():
    """Pin the premise the two oracle tests rest on.

    If a future edit makes the US Open fixture stop tripping
    `detect_table_tennis_group`, `test_us_open_event_classifies_as_tennis`
    would still pass — but it would no longer be testing the gate. This asserts
    the fixtures keep their discriminating power.
    """
    from app.utils.futures_categorization import detect_table_tennis_group

    for label, ev in (("US Open", US_OPEN_EVENT), ("Setka", SETKA_EVENT)):
        names = [ev["title"]] + [m["question"] for m in ev["markets"]]
        assert detect_table_tennis_group(names) is True, (
            f"the {label} fixture no longer trips the table-tennis heuristic, "
            f"so the tag gate is no longer the thing under test"
        )


# ---------------------------------------------------------------------------
# The oracle: reproduce the production migration.
# ---------------------------------------------------------------------------


def test_us_open_event_classifies_as_tennis():
    """The 44/44 production migration, pinned as a unit assertion."""
    category, llm = rail.classify_event_payload(US_OPEN_EVENT)
    assert llm == "tennis", (
        "a US Open ATP event tagged 'Tennis' must classify as tennis — this is "
        "the exact migration graded on production at 3ab15b20 (327/17 -> 283/61)"
    )
    assert category == "championship"


def test_setka_event_stays_table_tennis():
    """The control. Setka rode the same path on production and did not move."""
    category, llm = rail.classify_event_payload(SETKA_EVENT)
    assert llm == "table_tennis", (
        "Setka event 945534 held at table_tennis on production post-deploy; a "
        "rail that moves it has broken the #1230 half of Q493"
    )
    assert category == "championship"


def test_bare_string_tags_are_accepted_as_well_as_objects():
    """Gamma returns tag OBJECTS; older shapes and fixtures use bare strings.

    Assuming one shape would make the rail silently classify every event as
    untagged — which routes to the fallback arm and could re-introduce the very
    bug Q493 fixed. Both shapes must give the same answer.
    """
    as_strings = dict(US_OPEN_EVENT, tags=["Tennis", "Sports", "Games"])
    assert rail.classify_event_payload(as_strings) == rail.classify_event_payload(
        US_OPEN_EVENT
    )


def test_untagged_event_does_not_come_back_table_tennis_by_accident():
    """An event with NO usable tag falls to arm 1 — which is correct for Setka.

    Kept as an explicit case so the gate's two sides are both driven: with a
    usable tag the tag wins (above), without one the heuristic is still allowed
    to rescue Setka. A rail that answered `table_tennis` for the tagged US Open
    event AND for this one would pass a weaker test that only checked this side.
    """
    untagged = dict(SETKA_EVENT, tags=[])
    _category, llm = rail.classify_event_payload(untagged)
    assert llm == "table_tennis"


def test_untagged_us_open_would_fall_to_the_heuristic():
    """The honest limit of this rail, pinned rather than left implicit.

    Strip the "Tennis" tag from a real US Open event and arm 1 reclaims it as
    `table_tennis` — because that group genuinely does trip the heuristic. The
    rail is only as good as the venue's tags, and an event the venue leaves
    untagged is NOT repairable by this path. Recording it as a test rather than
    a comment so nobody later reads a stubborn row as a rail defect.
    """
    untagged = dict(US_OPEN_EVENT, tags=[])
    _category, llm = rail.classify_event_payload(untagged)
    assert llm == "table_tennis", (
        "if this ever returns tennis the rail has gained a name-based rule — "
        "see test_rail_contains_no_sport_rules_of_its_own"
    )


# ---------------------------------------------------------------------------
# The anti-drift guard — the one that matters most.
# ---------------------------------------------------------------------------


def test_rail_contains_no_sport_rules_of_its_own():
    """This module must never learn a sport rule; it must ASK the shipped one.

    The failure this guards is a maintainer "helpfully" adding a name-based
    shortcut (`if "US Open" in name: return "tennis"`) so the rail can skip the
    venue call. That would be a second classifier, free to drift from
    `app/tasks/polymarket.py`, and nothing else in the suite would notice.

    RAISES rather than skipping if the source cannot be read — a source-scan
    guard that cannot see its subject must fail loudly, not pass vacuously.
    """
    try:
        src = inspect.getsource(rail)
    except (OSError, TypeError) as exc:  # pragma: no cover — defensive
        raise AssertionError(
            f"cannot read the rail's source, so this guard cannot check "
            f"anything: {exc}"
        ) from exc
    assert len(src) > 2000, "source unexpectedly short — guard would be vacuous"

    # Prose legitimately discusses tennis at length — the docstrings explain WHY
    # the rail exists and the comments name Setka as the control. The guard is
    # about EXECUTABLE rules, so strip both and scan only what runs. Done with
    # the tokenizer rather than a regex, because a regex over Python source is
    # how a guard like this quietly stops seeing half its subject.
    import io
    import tokenize

    code_bits: list[str] = []
    prev_type = None
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == tokenize.COMMENT:
            continue
        # A STRING that is the whole of its logical line is a docstring.
        if tok.type == tokenize.STRING and prev_type in (
            None,
            tokenize.INDENT,
            tokenize.DEDENT,
            tokenize.NEWLINE,
            tokenize.NL,
        ):
            prev_type = tok.type
            continue
        if tok.type not in (tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT):
            code_bits.append(tok.string)
        prev_type = tok.type
    body = " ".join(code_bits)

    # Non-vacuity: the stripped body must still contain the code we expect,
    # or the tokenizer walk silently removed everything and the scan below
    # would pass on an empty string.
    assert "classify_event_payload" in body, (
        "the comment/docstring strip removed the executable code too — this "
        "guard would pass vacuously"
    )

    # `table_tennis` is permitted, as the named population constant.
    forbidden = ["us open", "atp", "wta", "setka", "wimbledon"]
    lowered = body.lower()
    found = [tok for tok in forbidden if tok in lowered]
    assert not found, (
        f"the rail has grown sport rules of its own: {found}. Every sport rule "
        f"must live in app/tasks/polymarket.py and reach this module only "
        f"through classify_event_payload()."
    )
    # And the ONLY sport literal permitted in executable code is the population
    # constant itself.
    assert lowered.count("table_tennis") <= 2, (
        "table_tennis appears more than as the SUSPECT_CATEGORY constant and "
        "its one comparison — a second literal is the start of a rule table"
    )


def test_classify_delegates_to_the_shipped_cascade():
    """`classify_event_payload` must call the poller's two functions, by name.

    A containment check on the source, because the behavioural tests above
    would still pass if someone reimplemented the cascade inline and happened
    to get these two fixtures right.
    """
    src = inspect.getsource(rail.classify_event_payload)
    for anchor in ("_tags_to_category", "resolve_event_category"):
        assert anchor in src, (
            f"anchor lost: {anchor!r} is no longer called by "
            f"classify_event_payload — either it was renamed in "
            f"app/tasks/polymarket.py (update both) or the cascade was "
            f"reimplemented here, which is the drift this guard exists to stop"
        )
    assert "from app.tasks.polymarket import" in src


def test_classify_really_calls_the_poller_at_runtime(monkeypatch):
    """Behavioural proof of delegation — the source scan above is not enough.

    A containment check passes on a module that imports the poller's functions
    and then ignores them, or that reimplements the cascade inline while the
    import sits unused. Monkeypatching the poller and demanding the rail's
    answer change is the only version of this assertion a reimplementation
    cannot satisfy.
    """
    import app.tasks.polymarket as poller

    sentinel = "sentinel_sport"
    calls: list[tuple] = []

    def _fake_resolve(category, llm, title, group_names):
        calls.append((category, llm, title, tuple(group_names)))
        return "championship", sentinel, "fake"

    monkeypatch.setattr(poller, "resolve_event_category", _fake_resolve)

    _category, llm = rail.classify_event_payload(US_OPEN_EVENT)
    assert llm == sentinel, (
        "the rail did not use the poller's resolve_event_category — it has "
        "reimplemented the cascade instead of delegating to it"
    )
    assert calls, "resolve_event_category was never called"
    # And it must be fed the event's real group names, not just the title:
    # arm 1 reads the CHILD questions, so passing only the title would silently
    # disable the very mechanism Q493 fixed.
    _c, _l, _t, group_names = calls[0]
    assert "Lehecka vs. Busta: Set 2 Games O/U 8.5" in group_names, (
        "child questions are not being passed to the cascade"
    )


# ---------------------------------------------------------------------------
# Never-write contracts.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status_code,expected",
    [(404, "not_at_venue"), (429, "indeterminate"), (500, "indeterminate"), (503, "indeterminate")],
)
@pytest.mark.asyncio
async def test_venue_failures_are_named_not_collapsed(status_code, expected):
    """404 and 429 need OPPOSITE handling and must never share a return.

    Gotcha #36: a catch-all that returned None for both would let a rate limit
    be recorded as a category verdict.
    """

    class _Resp:
        def __init__(self, code):
            self.status_code = code

        def json(self):  # pragma: no cover — not reached for these codes
            return {}

    class _Client:
        async def get(self, *_a, **_k):
            return _Resp(status_code)

    status, payload = await rail._fetch_event(_Client(), "1")
    assert status == expected
    assert payload is None, "no payload may be returned for a failed fetch"


@pytest.mark.asyncio
async def test_transport_exception_is_indeterminate_not_a_verdict():
    class _Client:
        async def get(self, *_a, **_k):
            raise TimeoutError("boom")

    status, payload = await rail._fetch_event(_Client(), "1")
    assert status == "indeterminate"
    assert payload is None


def test_repair_is_registered_and_attended_only():
    """Registered in BOTH the map and the docstring list (the drift the file warns about).

    And absent from the beat schedule: this is a drain with an end state, and
    wiring it to a beat would put an unbounded venue-fetch loop on the clock.
    """
    from app.routes.admin_repairs import _REPAIRS as REPAIRS

    assert REPAIRS["polymarket-sport-category-census"] == (
        "app.tasks.repair_polymarket_sport_category",
        "census",
    )
    assert REPAIRS["polymarket-sport-category"] == (
        "app.tasks.repair_polymarket_sport_category",
        "repair",
    )

    import app.routes.admin_repairs as mod

    doc = mod.__doc__ or ""
    assert "polymarket-sport-category" in doc, (
        "the module docstring's repair list has drifted from the registry "
        "again — it explicitly asks you to add it in the same commit"
    )

    from app.tasks import celery_app  # noqa: PLC0415

    schedule = celery_app.conf.beat_schedule
    assert schedule, "beat schedule empty — this assertion would be vacuous"
    for name, entry in schedule.items():
        assert "repair_polymarket_sport_category" not in str(entry.get("task", "")), (
            f"beat entry {name!r} schedules an ATTENDED-ONLY repair"
        )


def test_cursor_param_is_one_the_dispatcher_actually_passes():
    """A keyset the route cannot supply is a cursor that silently never pages.

    The dispatcher forwards only params it declares AND the repair's signature
    names. `after_commence` would have been dropped on the floor and every call
    would have re-read page one — a drain that looks busy and never finishes.
    """
    params = inspect.signature(rail.repair).parameters
    assert "after_date" in params and "after_id" in params

    import app.routes.admin_repairs as mod

    dispatch_src = inspect.getsource(mod)
    for anchor in ('("after_id", after_id)', '("after_date", after_date)'):
        assert anchor in dispatch_src, (
            f"anchor lost: {anchor} — the dispatcher no longer forwards this "
            f"repair's cursor, so paging is broken"
        )
