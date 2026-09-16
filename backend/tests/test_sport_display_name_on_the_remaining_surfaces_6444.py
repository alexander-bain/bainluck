"""#6444 — the other four reader surfaces stop serving a sport's key as its name.

#5657 gave the server a word for the 15 `sports` rows whose `name` IS their
`key`, and spent it on the two surfaces Alex actually met on his phone: the
search facet and `_format_event`.  The same rows reach readers through four
more serializers, and they were still printing the machine key.  Reproduced on
production v4601, 2026-09-16 ~03:0xZ:

    GET /api/futures/61182733          ->  "sport_name": "tennis_other"
    GET /api/teams/alabama-state-hornets -> "sport_name": "basketball_other"

Those are not edge rows.  `soccer_other` alone carries 147,044 futures markets
and `tennis_other` 57,456 (measured, same session), so the futures serializers
are the widest exposure of this defect anywhere in the app.

WHY THE SERVER, AGAIN.  The web guards this client-side — `getSportLabel` asks
`servedSportNameIsRaw` and falls back to its own `getLeagueDisplay` — so the web
team page already reads "Other Basketball".  Native has no such guard and prints
what it is given.  The server is the only place the two tiers can be made to
agree, which is the same reasoning #5657 recorded and the same reason its parity
guard reads `frontend/lib/sportCategories.ts` instead of restating it.

SCOPE, AND THE TWO SURFACES DELIBERATELY LEFT RAW.  `feed.py` and `sports.py`
are NOT converted here, each for a measured reason, and each has a tripwire
below that fails the day someone "finishes the job" without reading it.  The
coverage guard at the bottom is what stops a SIXTH surface being added raw.

BOTH ARMS, EVERY GUARD.  A test that only asserts "no underscore in the output"
passes for a serializer reduced to serving `None`; one that only asserts "the
brand survived" passes for a serializer that changed nothing.  Every test below
carries the positive and its control.
"""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.models import Sport, Team
from app.routes.events import _format_futures_for_search
from app.routes.futures import _format_market_detail, _format_market_summary
from app.routes.teams import _format_team
from tests.test_sport_display_name_never_serves_raw_key_5657 import RAW_NAMED_KEYS

ROUTES = Path(__file__).resolve().parents[1] / "app" / "routes"


def _sport(key: str, name: str | None) -> Sport:
    return Sport(id=1, key=key, name=name)


def _team(key: str, name: str | None) -> Team:
    team = Team(
        id=10636,
        slug="alabama-state-hornets",
        name="Alabama State Hornets",
        abbreviation=None,
        sport_id=1,
    )
    team.sport = _sport(key, name)
    return team


def _market(key: str | None, name: str | None):
    """The `/api/futures/61182733` specimen, reduced to what the two
    serializers read.  A `SimpleNamespace` rather than the ORM model because
    both serializers touch ~30 attributes and none of them are the subject."""
    return SimpleNamespace(
        id=61182733,
        name="Gabriele Thomas Brancatelli vs. Emirhan Bulut: Total Sets O/U 2.5",
        description=None,
        category="prop",
        source="polymarket",
        external_id="815313",
        status="open",
        sport=None if key is None else _sport(key, name),
        sport_id=1,
        event_id=None,
        market_type=None,
        market_tier=3,
        llm_sport_category="tennis",
        mutually_exclusive=True,
        commence_time=None,
        resolution_date=None,
        created_at=None,
        updated_at=None,
        group_id=None,
        canonical_market_key=None,
        hook_description=None,
        image_url=None,
        category_tags=[],
        market_metadata=None,
        outcomes=[],
    )


# ── the ship: a raw key never leaves these serializers ──────────────────────


@pytest.mark.parametrize("key", RAW_NAMED_KEYS)
def test_the_team_page_never_reads_a_machine_key_back_to_a_reader(key):
    served = _format_team(_team(key, key))["sport_name"]

    assert served != key, f"/api/teams still serves the raw key for {key}"
    assert "_" not in served, f"{served!r} is still a key fragment"
    assert served.strip(), "the fix must not empty the field"


@pytest.mark.parametrize("key", RAW_NAMED_KEYS)
def test_the_futures_detail_never_reads_a_machine_key_back_to_a_reader(key):
    served = _format_market_detail(_market(key, key), None, set())["sport_name"]

    assert served != key, f"/api/futures/{{id}} still serves the raw key for {key}"
    assert "_" not in served, f"{served!r} is still a key fragment"
    assert served.strip(), "the fix must not empty the field"


@pytest.mark.parametrize("key", RAW_NAMED_KEYS)
def test_the_futures_summary_never_reads_a_machine_key_back_to_a_reader(key):
    served = _format_market_summary(_market(key, key))["sport_name"]

    assert served != key, f"the futures list still serves the raw key for {key}"
    assert "_" not in served, f"{served!r} is still a key fragment"
    assert served.strip(), "the fix must not empty the field"


@pytest.mark.parametrize("key", RAW_NAMED_KEYS)
def test_the_search_futures_arm_never_reads_a_machine_key_back_to_a_reader(key):
    """The arm #5657 missed.  Its facet chips and its events arm were fixed;
    the futures list in the SAME response still answered the raw key."""
    served = _format_futures_for_search(_market(key, key))["sport_name"]

    assert served != key, f"search futures still serves the raw key for {key}"
    assert "_" not in served, f"{served!r} is still a key fragment"
    assert served.strip(), "the fix must not empty the field"


def test_the_three_production_specimens_read_as_words():
    """Alex's own defect, on the three URLs that reproduce it today."""
    assert _format_market_detail(
        _market("tennis_other", "tennis_other"), None, set()
    )["sport_name"] == "Other Tennis"
    assert (
        _format_team(_team("basketball_other", "basketball_other"))["sport_name"]
        == "Other Basketball"
    )
    # `GET /api/events/search?q=Red Sox` -> futures[0], production 2026-09-16.
    assert (
        _format_futures_for_search(_market("baseball_other", "baseball_other"))[
            "sport_name"
        ]
        == "Other Baseball"
    )


# ── the control: a real brand is not "corrected" ────────────────────────────


@pytest.mark.parametrize(
    "key,brand",
    [
        ("baseball_mlb", "MLB"),
        ("soccer_epl", "EPL"),
        ("icehockey_shl", "SHL"),
        ("tennis_atp_queens", "ATP Queen's Club Championships"),
    ],
)
def test_a_real_brand_passes_through_every_serializer_byte_for_byte(key, brand):
    assert _format_team(_team(key, brand))["sport_name"] == brand
    assert (
        _format_market_detail(_market(key, brand), None, set())["sport_name"] == brand
    )
    assert _format_market_summary(_market(key, brand))["sport_name"] == brand


def test_a_sportless_row_still_serves_none_rather_than_inventing_one():
    """The `if market.sport else None` arm is load-bearing: a market with no
    sport must keep serving nothing, not a word derived from nothing."""
    assert _format_market_detail(_market(None, None), None, set())["sport_name"] is None
    assert _format_market_summary(_market(None, None))["sport_name"] is None


def test_a_nameless_sport_is_left_absent_not_derived():
    """#5657's contract: an ABSENT stored name stays absent so clients keep
    falling back to their own maps.  Only the key-as-name is rejected."""
    assert _format_team(_team("basketball_other", None))["sport_name"] is None
    assert (
        _format_market_detail(_market("tennis_other", None), None, set())["sport_name"]
        is None
    )


# ── market_moves: inline in an async route, so guarded at the source ────────


def test_both_market_moves_serve_sites_route_through_the_helper():
    """`get_market_was_wrong` builds its two payloads inline, so there is no
    serializer to call.  Assert on its source instead — and assert the site
    COUNT too, so a third payload added later cannot pass by not existing."""
    source = (ROUTES / "market_moves.py").read_text()
    tree = ast.parse(source)

    sites = [
        value
        for node in ast.walk(tree)
        if isinstance(node, ast.Dict)
        for key, value in zip(node.keys, node.values)
        if isinstance(key, ast.Constant) and key.value == "sport_name"
    ]

    assert len(sites) == 2, (
        f"market_moves.py now has {len(sites)} sport_name payload sites, not 2 — "
        "a new one was added; route it through sport_display_name and update this count"
    )
    for value in sites:
        assert "sport_display_name" in ast.dump(value), (
            "a market_moves payload serves sport.name raw again "
            f"(line {value.lineno})"
        )


# ── 🔴 the two surfaces that must STAY raw, each for its own reason ─────────


def test_the_feed_still_serves_the_raw_name_because_ranking_reads_it():
    """🔴 Do not "finish" this one either. Read this before you touch feed.py.

    `_review_decision_scope_keys` builds a manual-review scope key out of the
    very field these serializers write:

        category = data.get("llm_sport_category") or data.get("sport_name") or …
        keys.append(f"category:{str(category).lower()}")

    and the `data` it reads is the dict `_score_events` / `_score_futures` /
    `_score_sports_mode_futures` produce.  Humanising `sport_name` there silently
    re-keys every stored review decision from `category:tennis_other` to
    `category:other tennis` — they stop matching, and the only symptom is
    suppressed cards quietly coming back.

    That is a ranking change, which is a REVIEWED class under jkl=A, and it
    needs the scope key repointed at the machine `sport` key in the same ship.
    #6444 deliberately stayed out of it.  If you are doing that ship: repoint
    the scope key, then change this test on purpose.
    """
    source = (ROUTES / "feed.py").read_text()

    assert "_review_decision_scope_keys" in source, (
        "the consumer this guard is about has gone — re-read the guard, then "
        "decide whether feed.py can now be converted"
    )
    assert 'data.get("sport_name")' in source, (
        "the review scope key no longer reads sport_name. If it now reads the "
        "machine `sport` key, feed.py is safe to convert — do it, and delete this."
    )
    assert "sport_display_name" not in source, (
        "feed.py now humanises sport_name while _review_decision_scope_keys "
        "still keys on it: stored manual review decisions will stop matching."
    )


def test_the_sports_detail_route_is_still_the_5657_exemption():
    """The `group` trap (#5657) is unchanged; its own guard states the case.
    Restated here only so the coverage guard below has an honest exemption."""
    source = (ROUTES / "sports.py").read_text()
    assert "sport_display_name" not in source, (
        "see test_the_sports_detail_route_still_signals_raw in the #5657 suite"
    )


# ── anti-drift: no SIXTH surface gets added raw ─────────────────────────────

#: Every route module allowed to serve `sport_name` without the helper, with the
#: measured reason.  Adding a name here is a decision, not a formality.
EXEMPT = {
    # ranking reads this field as a scope key — see the tripwire above.
    "feed.py": "_review_decision_scope_keys keys on sport_name",
    # serves `group` too, which web only corrects while the name reads raw.
    "sports.py": "#5657's group trap",
}


def _raw_sport_name_sites(path: Path) -> list[int]:
    """Lines where a payload binds `sport_name` to a bare `.name` attribute."""
    tree = ast.parse(path.read_text())
    out: list[int] = []

    def bare(value: ast.AST) -> bool:
        dumped = ast.dump(value)
        return "attr='name'" in dumped and "sport_display_name" not in dumped

    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if (
                    isinstance(key, ast.Constant)
                    and key.value == "sport_name"
                    and bare(value)
                ):
                    out.append(value.lineno)
        elif isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg == "sport_name" and bare(kw.value):
                    out.append(kw.value.lineno)
    return out


def test_no_route_serves_a_bare_sport_name_outside_the_named_exemptions():
    offenders = {
        path.name: lines
        for path in sorted(ROUTES.glob("*.py"))
        if path.name not in EXEMPT and (lines := _raw_sport_name_sites(path))
    }

    assert not offenders, (
        f"these routes serve `sport_name` straight off the ORM: {offenders}. "
        "Route them through sport_display_name, or add the module to EXEMPT "
        "with the measured reason it must stay raw."
    )


def test_the_coverage_guard_can_actually_see_a_raw_site():
    """Anti-vacuity: the scan must find the sites we know are still raw.
    Without this, an AST walk that matches nothing would pass forever."""
    assert _raw_sport_name_sites(ROUTES / "feed.py"), (
        "the scan found no raw site in feed.py, which has three — the matcher "
        "is broken and the guard above is vacuous"
    )


def test_the_converted_routes_read_as_converted_to_the_same_scan():
    """The other half of the anti-vacuity pair: the scan must also go quiet on
    the files this ship fixed, or it is matching something other than the fix."""
    for name in ("teams.py", "futures.py", "market_moves.py", "events.py"):
        assert not _raw_sport_name_sites(ROUTES / name), f"{name} regressed"
