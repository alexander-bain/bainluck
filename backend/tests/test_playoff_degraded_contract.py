"""UX-P175 — the playoff grid's degradation signals are a CROSS-LAYER contract.

`/api/playoffs/{slug}` publishes three honesty signals and `/playoffs/[sport]`
now renders all three. Nothing imports across Python and TypeScript, so the two
layers can only agree by convention — and CERT-433's lesson is that two layers
which agree today from two SOURCES drift apart later with nothing going red.
A frontend fixture that hardcodes the repaired payload stays green when someone
deletes the producer.

So the frontend fixtures under `frontend/__tests__/fixtures/uxp175_*` are
GENERATED from the functions below, and this module fails if they ever stop
matching what those functions produce. The frontend reads the fixture; the
backend proves the fixture is still what the backend makes. One source.

Regenerate (from `backend/`) after a deliberate change:

    python3 -c "
    import json,sys; sys.path.insert(0,'.')
    from app.routes.playoffs import degraded_grid_detail
    json.dump({'slug':'la-liga','detail':degraded_grid_detail('la-liga'),'status':503},
              open('../frontend/__tests__/fixtures/uxp175_playoffs_503_detail.json','w'),indent=1)"
"""

import json
from pathlib import Path

import pytest

from app.routes.playoffs import _mark_last_good, degraded_grid_detail

FIXTURES = (
    Path(__file__).resolve().parents[2] / "frontend" / "__tests__" / "fixtures"
)

DETAIL_503 = FIXTURES / "uxp175_playoffs_503_detail.json"
CONTROL = FIXTURES / "uxp175_playoffs_nba_control.json"
DEGRADED = FIXTURES / "uxp175_playoffs_nba_degraded.json"
STALE = FIXTURES / "uxp175_playoffs_epl_stale.json"

PLAYOFFS_SRC = Path(__file__).resolve().parents[1] / "app" / "routes" / "playoffs.py"
PAGE_SRC = (
    Path(__file__).resolve().parents[2]
    / "frontend"
    / "app"
    / "playoffs"
    / "[sport]"
    / "page.tsx"
)


def _load(p: Path) -> dict:
    return json.loads(p.read_text())


class TestTheFixturesAreStillWhatTheBackendProduces:
    """If these fail, the frontend is asserting against a payload we no longer
    serve — which is precisely the state CERT-433 caught."""

    def test_503_sentence_is_generated_by_the_shipped_function(self):
        fx = _load(DETAIL_503)
        assert fx["detail"] == degraded_grid_detail(fx["slug"])
        assert fx["status"] == 503

    def test_the_sentence_keeps_the_clause_that_carries_its_meaning(self):
        # The page renders this verbatim in place of "Failed to load". Losing
        # this clause silently returns the reader to blaming the league — the
        # same false claim UX-P173 removed from the empty state.
        assert "not an empty league" in degraded_grid_detail("epl")
        assert "'epl'" in degraded_grid_detail("epl")

    def test_degraded_fixture_is_the_control_run_through_the_producer(self):
        control = _load(CONTROL)
        degraded = _load(DEGRADED)

        # Reproduce the fixture from the control using the SHIPPED marker.
        rebuilt = _mark_last_good(json.loads(json.dumps(control)), "timeout", degraded=True)
        assert rebuilt == degraded, (
            "uxp175_playoffs_nba_degraded.json is no longer what "
            "_mark_last_good(..., 'timeout', degraded=True) produces"
        )

    def test_control_carries_none_of_the_flags(self):
        control = _load(CONTROL)
        for key in ("stale", "stale_reason", "degraded", "degraded_reason"):
            assert key not in control, f"control fixture is contaminated with {key}"

    def test_control_and_degraded_differ_in_exactly_the_four_marker_keys(self):
        # The frontend asserts the same delta. Both sides checking it is the
        # point: it is what makes the frontend's "CONTROL" panel meaningful —
        # the two payloads are the same production body and nothing else moved.
        control, degraded = _load(CONTROL), _load(DEGRADED)
        assert set(degraded) - set(control) == {
            "stale",
            "stale_reason",
            "degraded",
            "degraded_reason",
        }
        assert set(control) - set(degraded) == set()

    def test_stale_fixture_is_a_real_routine_last_good_serve(self):
        # Curled from production, which had already stamped it. Not simulated.
        stale = _load(STALE)
        assert stale["stale"] is True
        assert stale["stale_reason"] == "cache_miss"
        assert "degraded" not in stale, (
            "a routine between-warms serve must not be marked degraded"
        )


class TestTheTwoSeveritiesStayDistinct:
    """`_mark_last_good`'s docstring is explicit that a routine cache_miss and a
    failed rebuild must not share a severity. The frontend now renders them
    differently, so a change here is a reader-visible change."""

    def test_cache_miss_marks_stale_but_never_degraded(self):
        out = _mark_last_good({"teams": []}, "cache_miss", degraded=False)
        assert out["stale"] is True
        assert out["stale_reason"] == "cache_miss"
        assert "degraded" not in out
        assert "degraded_reason" not in out

    def test_timeout_marks_both(self):
        out = _mark_last_good({"teams": []}, "timeout", degraded=True)
        assert out["stale"] is True
        assert out["degraded"] is True
        assert out["degraded_reason"] == "timeout"

    def test_marker_is_additive_and_touches_nothing_else(self):
        payload = {"teams": [1, 2], "columns": ["a"], "team_count": 2}
        out = _mark_last_good(dict(payload), "timeout", degraded=True)
        for k, v in payload.items():
            assert out[k] == v

    @pytest.mark.parametrize("bad", [None, [], "x", 3])
    def test_non_dict_payload_passes_through_unharmed(self, bad):
        assert _mark_last_good(bad, "timeout", degraded=True) == bad


class TestBothLayersAreStillWired:
    """Non-vacuity. A contract nobody reads is not a contract — the failure mode
    is a pure-lib guard staying green after someone deletes the CALL."""

    def test_the_route_raises_with_the_shared_producer(self):
        src = PLAYOFFS_SRC.read_text()
        assert "detail=degraded_grid_detail(league_slug)" in src, (
            "the 503 no longer raises through degraded_grid_detail(), so the "
            "sentence this module pins is not the sentence readers get"
        )

    def test_the_page_reads_the_fields_the_backend_publishes(self):
        # Narrow and named, with a non-vacuity clause — not a blunt
        # source-level `not in` sweep, which fails on correct files.
        page = PAGE_SRC.read_text()
        for field in ("degraded", "stale", "last_updated"):
            assert field in page, f"the grid page stopped reading `{field}`"
        assert "gridErrorMessage" in page, (
            "the page stopped deriving its error copy from the server's detail"
        )
        # The generic line must survive as the FALLBACK, not vanish: a server
        # that sends no reason still needs something to say.
        assert "Failed to load championship grid" in page

    def test_the_page_pins_a_timezone_on_the_stamp_it_renders(self):
        # An unpinned toLocaleString is invisible under CI's TZ=UTC. The
        # frontend suite drives the real render under three zones; this asserts
        # the pin exists at all, where a reviewer will look for it.
        page = PAGE_SRC.read_text()
        assert 'timeZone: "UTC"' in page
