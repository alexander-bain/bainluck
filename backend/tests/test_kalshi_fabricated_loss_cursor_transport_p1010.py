"""The drain's cursor must survive the ONE thing the rail tells you to do with it.

CAL-P1010-R (CERT-1892). The rail's own refusal text says:

    "?offset= is gone … Drain with ?after_date=&after_id= from the previous
     call's next_cursor."

Following that instruction exactly was the failing path. `keyset_after` emitted
``2026-06-16T12:27:30.636456+00:00``; pasted literally into a query string, the
``+`` is ``application/x-www-form-urlencoded`` for a SPACE, so Starlette handed
the route ``2026-06-16T12:27:30.636456 00:00`` and the parse refused it by name.
Page two could not be reached by the documented round trip.

The previous presentation's test could not see it: it passed
``cursor["after_date"]`` into ``parse_cursor_date`` directly, and a params
*dictionary* is not a query *string* — the transport that eats the character was
never in the path. So these tests go through the real ASGI route with the cursor
**appended to the URL as text**, which is what an operator's terminal does.

Two ends are fixed and both are pinned here:

* the emitted cursor now carries ``Z``, so nothing in it is rewritable;
* the parse still repairs an eaten ``+``, because a cursor an operator already
  holds — in a captured response, a scrollback, a ticket — must keep working.

The session double answers the query it is HANDED: it filters on the bound
``after_date``/``after_id`` and raises the way asyncpg does if handed a string.
A double that ignored its bounds could not tell page one from page two, which is
the entire question.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes import admin_repairs
from app.tasks import repair_kalshi_fabricated_loss as rail
from app.utils.repair_apply_plan import keyset_after, url_safe_isoformat

RESOLVED = datetime(2026, 6, 16, 12, 27, 30, 636456, tzinfo=timezone.utc)

#: Two markets, one day apart, so "page two" is a different row and not a
#: re-read of page one wearing a different name.
_MARKETS = [
    SimpleNamespace(
        market_id=100,
        event_ticker="KX-A",
        mutex=True,
        sport="baseball",
        our_status="resolved",
        resolution_date=RESOLVED,
        age_days=10.0,
    ),
    SimpleNamespace(
        market_id=200,
        event_ticker="KX-B",
        mutex=True,
        sport="baseball",
        our_status="resolved",
        resolution_date=RESOLVED + timedelta(days=1),
        age_days=9.0,
    ),
]


class _Rows:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return self._rows


class _WorkSession:
    """Answers the query it was HANDED, and rejects a string the way asyncpg does.

    Both halves are load-bearing. If it ignored the bound cursor it would return
    page one for every request and every assertion below would pass for the
    wrong reason; if it accepted a `str` for the timestamp it would be greener
    than the driver and hide the defect this file exists for.
    """

    def __init__(self):
        self.bound: list[dict] = []

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if "statement_timeout" in sql:
            return _Rows([])
        if "SELECT fm.id AS market_id" in sql:
            self.bound.append(dict(params or {}))
            return _Rows(self._select(params or {}))
        return _Rows([])

    @staticmethod
    def _select(params):
        after_date, after_id = params.get("after_date"), params.get("after_id")
        rows = sorted(_MARKETS, key=lambda r: (r.resolution_date, r.market_id))
        if after_date is not None:
            if not isinstance(after_date, datetime):
                raise TypeError(
                    "invalid input for query argument: expected a "
                    f"datetime.datetime instance, got {type(after_date).__name__!r}"
                )
            rows = [
                r
                for r in rows
                if (r.resolution_date, r.market_id) > (after_date, after_id)
            ]
        if params.get("sport") is not None:
            rows = [r for r in rows if r.sport == params["sport"]]
        return rows[: params.get("lim") or len(rows)]

    async def rollback(self):
        pass


class _SilentVenue:
    """The venue answers nothing, so every market is a named exclusion.

    Which rows were SELECTED is the question here; what the venue said about
    them is a different file's. A silent venue keeps this one honest about that.
    """

    async def get_markets(self, **kwargs):
        return [], None

    async def close(self):
        pass


@pytest.fixture
def client(monkeypatch):
    import app.services.kalshi_api as kalshi_api

    monkeypatch.setattr(kalshi_api, "KalshiAPIService", _SilentVenue)
    monkeypatch.setattr(
        admin_repairs, "_check_admin_secret", lambda secret, **kw: secret == "ok"
    )

    async def _save(plan):
        return True, "ok"

    monkeypatch.setattr(rail, "_save_plan", _save)

    session = _WorkSession()
    app = FastAPI()
    app.include_router(admin_repairs.router)

    async def _override():
        return session

    app.dependency_overrides[admin_repairs.get_db_rw] = _override
    return TestClient(app), session


def _page(client, query=""):
    """One dry-run through the REAL route, with `query` appended as TEXT.

    Never a params dict: the dict is what hid the defect, because it is
    re-encoded on the way out and the character is never eaten.
    """
    url = "/repairs/kalshi-fabricated-loss?secret=ok&apply=false&limit=1" + query
    response = client.post(url)
    assert response.status_code == 200, response.text
    return response.json()["result"]


class TestTheCursorSurvivesTheQueryString:
    def test_the_emitted_cursor_carries_nothing_a_query_string_rewrites(self):
        """`+` is a space in a query string. `Z` is the same instant and is not."""
        cursor = keyset_after(_MARKETS, examined=1)

        assert cursor["after_date"] == "2026-06-16T12:27:30.636456Z"
        assert "+" not in cursor["after_date"]
        assert url_safe_isoformat(RESOLVED) == cursor["after_date"]

    def test_page_two_is_reached_by_pasting_the_cursor_into_the_url(self, client):
        """THE CATCHING TEST. The documented round trip, followed literally."""
        api, session = client

        one = _page(api)
        assert one["window"]["returned"] == 1
        assert one["next_cursor"] == {"after_date": _emitted_cursor(), "after_id": 100}

        two = _page(
            api,
            f"&after_id={one['next_cursor']['after_id']}"
            f"&after_date={one['next_cursor']['after_date']}",
        )

        assert two.get("refused") != "CURSOR_DATE_UNPARSEABLE", two.get("reason")
        assert two["window"]["returned"] == 1
        # The row page one did NOT return — a resume, not a re-read.
        assert session.bound[-1]["after_date"] == RESOLVED
        assert isinstance(session.bound[-1]["after_date"], datetime)
        assert two["examined"] == 1
        assert two["next_cursor"]["after_id"] == 200

    def test_a_cursor_in_the_old_plus_form_still_works_from_the_url(self, client):
        """An operator holding a cursor from before this fix is not stranded.

        This is the exact string the route received and refused: `isoformat()`'s
        `+00:00` with the `+` already eaten by the query string.
        """
        api, session = client

        out = _page(api, f"&after_id=100&after_date={RESOLVED.isoformat()}")

        assert out.get("refused") != "CURSOR_DATE_UNPARSEABLE", out.get("reason")
        assert session.bound[-1]["after_date"] == RESOLVED
        assert out["next_cursor"]["after_id"] == 200

    def test_a_genuinely_broken_cursor_is_still_refused_by_name(self, client):
        """The repair may not become a shrug. Refused, not ignored: a cursor
        dropped to None re-reads page one and reports it as a resume."""
        api, session = client

        out = _page(api, "&after_id=100&after_date=page%20two%20please")

        assert out["refused"] == "CURSOR_DATE_UNPARSEABLE"
        assert out["measured"] is False
        assert session.bound == [], "a refusal that had already queried"

    def test_half_a_cursor_is_still_refused(self, client):
        """The pre-existing guarantee, held: half a keyset is a different walk."""
        api, _ = client

        out = _page(api, f"&after_date={keyset_after(_MARKETS, 1)['after_date']}")

        assert out["refused"] == "PARTIAL_CURSOR"

    def test_the_refusal_advertises_a_cursor_that_actually_works(self, client):
        """The rail's own instruction is part of the rail.

        CERT-1892 was found by following the refusal text literally. The example
        it prints must therefore be the form `next_cursor` really hands back,
        and must itself survive being pasted into the URL — an example in the
        old `+00:00` form is the same defect wearing prose.
        """
        api, session = client

        assert "+" not in rail._CURSOR_EXAMPLE
        assert rail._CURSOR_EXAMPLE.endswith("Z")

        out = _page(api, f"&after_id=1&after_date={rail._CURSOR_EXAMPLE}")

        assert out.get("refused") != "CURSOR_DATE_UNPARSEABLE", out.get("reason")
        assert session.bound[-1]["after_date"] == datetime.fromisoformat(
            rail._CURSOR_EXAMPLE.replace("Z", "+00:00")
        )

    def test_the_double_would_reject_a_string_the_way_the_driver_does(self):
        """The over-reach control on the fixture itself.

        If `_WorkSession` tolerated a `str` it would be greener than asyncpg and
        every assertion above would pass over the shipped defect.
        """
        with pytest.raises(TypeError):
            _WorkSession._select(
                {"after_date": RESOLVED.isoformat(), "after_id": 100, "lim": 1}
            )


def _emitted_cursor() -> str:
    """What `keyset_after` emits for the first market — asked, not restated."""
    return keyset_after(_MARKETS, examined=1)["after_date"]
