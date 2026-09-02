"""UX-P264 / #2646 — "+N more markets below" names markets that are below.

WHAT THE USER SAW. On `/search?q=Alcaraz` the two "Answers" family cards ended
with `+2 more markets below` and `+6 more markets below`. Beneath them the page
held ONE market, and it was none of the eight. The eight were serialized nowhere
in the response — not in `members` (capped at four), not in the flat `futures`
list. The footer pointed at a region of the page that does not exist.

THE MECHANISM. `_compose_futures_families` reads `deduped_futures` — the full
candidate set, deliberately wider than the ten rows the response ships, because
reading past the flat slice is the thing families ADD. `more_count` was
`len(rest) - 4`: the size of the family, not the size of what the page shows.
The gap between the two IS the false promise.

WHY THE COMPOSER STILL READS THE WIDE SET. #2646 proposed composing from the
shipped ten instead. Measured over ten live payloads on 2026-09-02, that deletes
whole family cards: `Djokovic` and `Sabalenka` each headline their Grand Slam
Tennis family with a market outside the shipped ten, so the restricted input
drops both families under the two-member floor and their markets leave the page
altogether. So the input is unchanged and the COUNT is made honest — it now
counts only overflow members the response actually serializes.

WHY THESE ASSERTIONS ARE AT THE ROUTE. Every ordering/count claim below reads
`body["futures_families"]` and `body["futures"]` off `GET /api/events/search`.
`more_count` is a claim about the relationship between two arrays in one
response, and an assertion on the composer alone cannot see that relationship —
it would be green on a composer that is internally consistent and a route that
ships a different slice, which is exactly the shape of the bug. Same lesson
CERT-718 wrote for #2579.

THE PAGE'S OWN RULE, REPLICATED. `_below_ids` re-implements the web page's
`familyShownIds` filter (`frontend/components/searchFamilyDisplay.ts:44-51`):
the flat list minus every family's headline and shown members. That set is
literally what renders under the family cards, so "is the promise payable" is
`sum(more_count) <= len(_below_ids(body))` and nothing else.

RED-FIRST. Revert `app/routes/events.py` alone; the module imports nothing new,
so there is no dangling-import collection error to mistake for a failure
(gotcha #124). The red arm reports `more_count` 9 against 5 rows below.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.services.database import get_db, get_db_rw

_asyncio = pytest.mark.asyncio

#: The flat `futures` bucket's size (`_SEARCH_FUTURES_PAGE`). Mirrored rather
#: than imported so a change to the constant shows up here as a failure with a
#: readable number instead of silently re-shaping every expectation below.
PAGE = 10

#: Family members seeded, ordered by volume so the rerank is deterministic.
#: Fourteen is chosen to straddle the page: positions 0-9 ship, 10-13 do not.
#:   position 0      -> headline
#:   positions 1-4   -> the four shown members
#:   positions 5-9   -> overflow AND shipped  == the honest `more_count` (5)
#:   positions 10-13 -> overflow, NOT shipped == the four that were being lied about
FAMILY_SIZE = 14
HONEST_MORE = PAGE - 5          # 5 — overflow rows the page actually puts below
INFLATED_MORE = FAMILY_SIZE - 5  # 9 — what `len(rest) - 4` reported

#: Every name contains "Alcaraz", so each is a `_query_name_match` and they group
#: under ONE `entity:alcaraz` family.
#:
#: ⚠️ The first draft of this list said "so each groups under one family" and was
#: wrong: `_story_key` is not only geopolitics. "Grand Slam" and "US Open" both
#: return `story:grand_slam_tennis`, which split the seed into two families and
#: reddened nine assertions for a reason that had nothing to do with the ship.
#: `TestTheSeedIsReal` now pins the single family, and `test_no_name_carries_a_
#: story_key` pins the premise directly, so a future edit to either this list or
#: the story-key vocabulary fails loudly instead of quietly re-shaping the seed.
FAMILY_NAMES = [
    "Carlos Alcaraz: Next Match Played",
    "Carlos Alcaraz: Break points converted",
    "Will Carlos Alcaraz reach the final in Cincinnati",
    "Faria vs Alcaraz",
    "Roman Safiullin vs Carlos Alcaraz: Total Games",
    "Carlos Alcaraz to play in the Laver Cup",
    "Carlos Alcaraz: Sets dropped in round three",
    "Carlos Alcaraz year-end number one",
    "Will Alcaraz or Sinner win more Grand Slams in 2026?",
    "Carlos Alcaraz: Aces in his next match",
    "Carlos Alcaraz: Tiebreaks won in 2026",
    "Carlos Alcaraz to win the Davis Cup",
    "Carlos Alcaraz: Double faults in his next match",
    "Carlos Alcaraz retires before 2030",
]
assert len(FAMILY_NAMES) == FAMILY_SIZE


def _outcome(name, prob, oid):
    return SimpleNamespace(
        id=oid, name=name, probability=prob, current_probability=prob,
        opening_probability=prob, is_winner=None, price=prob,
        probability_change_24h=None, american_odds=None,
        current_american_odds=None, rank=oid % 10, sort_order=oid,
        external_id=f"OUT-{oid}",
    )


def _market(*, mid, name, volume):
    """A futures market shaped as `search_events` reads it (the fields
    `_format_futures_for_search` touches, plus the ones rerank/dedup touch)."""
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=mid,
        name=name,
        external_id=f"KX-{mid}",
        llm_sport_category="tennis",
        category="tennis",
        market_tier=5,
        market_type="prop",
        sport=None,
        sport_id=None,
        source="kalshi",
        volume=volume,
        status="open",
        resolution_date=(now + timedelta(days=20)).date(),
        updated_at=now,
        canonical_market_key=None,
        image_url=None,
        hook_description=None,
        group_id=None,
        event_id=None,
        outcomes=[
            _outcome("Yes", 0.55, mid * 10 + 1),
            _outcome("No", 0.45, mid * 10 + 2),
        ],
    )


def _family(n=FAMILY_SIZE):
    """`n` distinct name-matching markets, strictly descending volume so the
    reranked order is the listed order and the page boundary is predictable."""
    return [
        _market(mid=800_000 + i, name=FAMILY_NAMES[i], volume=float(9_000_000 - i * 1_000))
        for i in range(n)
    ]


def _empty_result():
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    result.scalars.return_value.unique.return_value.all.return_value = []
    result.scalars.return_value.first.return_value = None
    result.scalar_one_or_none.return_value = None
    result.scalar.return_value = None
    result.fetchall.return_value = []
    result.all.return_value = []
    result.first.return_value = None
    result.mappings.return_value.all.return_value = []
    return result


def _seeded_session(window):
    """Answers the futures window with `window` and everything else empty.

    The headline-contender lane is discriminated by `~*`, the only operator that
    lane builds (#2579's harness proved it exact), and is deliberately given
    NOTHING: a promoted row is a separate ship with its own guards, and handing
    it rows here would make the page boundary depend on two mechanisms at once.
    """
    session = AsyncMock()

    async def _execute(stmt, *args, **kwargs):
        result = _empty_result()
        try:
            sql = str(stmt)
        except Exception:  # noqa: BLE001
            return result
        if "futures_markets" not in sql or "SELECT" not in sql.upper():
            return result
        if "~*" in sql:
            return result
        result.scalars.return_value.unique.return_value.all.return_value = list(window)
        result.scalars.return_value.all.return_value = list(window)
        return result

    session.execute = AsyncMock(side_effect=_execute)
    return session


def _app_for(window, monkeypatch):
    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")
    from app.main import app

    session = _seeded_session(window)

    async def _mock_get_db():
        yield session

    async def _mock_get_optional_user():
        return None

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_db_rw] = _mock_get_db
    app.dependency_overrides[get_optional_user] = _mock_get_optional_user
    return app


async def _client(window, monkeypatch):
    app = _app_for(window, monkeypatch)
    with patch("app.main.init_db", new_callable=AsyncMock):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def overflow_client(monkeypatch):
    """The reported case: a family wider than the page it is printed on."""
    async for ac in _client(_family(), monkeypatch):
        yield ac


@pytest_asyncio.fixture
async def fits_client(monkeypatch):
    """CONTROL — a family of five: headline + four shown, no overflow at all.
    `more_count` is 0 here on BOTH arms, and that is the point: it pins that the
    fix did not reach a page it had no business touching."""
    async for ac in _client(_family(5), monkeypatch):
        yield ac


@pytest_asyncio.fixture
async def all_shipped_client(monkeypatch):
    """CONTROL — a family of eight, entirely inside the ten-row page. Every
    overflow member IS below, so the honest count equals the old arithmetic
    (`8 - 1 - 4 = 3`) and this fixture is GREEN ON BOTH ARMS. It separates "the
    count was made truthful" from "the count was made smaller"; a fix that
    simply floored `more_count` at 0, or dropped the footer, fails here."""
    async for ac in _client(_family(8), monkeypatch):
        yield ac


async def _search(client, q="Alcaraz"):
    resp = await client.get(f"/api/events/search?q={q}&debug_timing=true")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _families(body):
    return body.get("futures_families") or []


def _flat_ids(body):
    return [m["id"] for m in (body.get("futures") or [])]


def _shown_ids(body):
    """`familyShownIds` — headline + rendered members, the ids the web page
    filters OUT of the flat list so nothing double-renders."""
    ids = set()
    for fam in _families(body):
        ids.add(fam["headline"]["id"])
        for m in fam["members"]:
            ids.add(m["id"])
    return ids


def _below_ids(body):
    """Exactly the rows that render underneath the family cards."""
    shown = _shown_ids(body)
    return [i for i in _flat_ids(body) if i not in shown]


# ==========================================================================
# The seed. Everything below loops over families; a silent empty seed would
# make every one of those loops vacuously green.
# ==========================================================================


class TestTheSeedIsReal:
    def test_no_name_carries_a_story_key(self):
        """The seed's premise, pinned. A name that trips `_story_key` leaves the
        entity family and forms a second one, which silently changes every count
        below. This caught exactly that during authoring."""
        from app.utils.feed_market_quality import _story_key

        offenders = [n for n in FAMILY_NAMES if _story_key(n, "tennis")]
        assert offenders == [], f"these would split the seed: {offenders}"

    @_asyncio
    async def test_one_family_forms_and_the_page_is_full(self, overflow_client):
        body = await _search(overflow_client)
        fams = _families(body)
        assert len(fams) == 1, f"expected one entity family, got {[f['label'] for f in fams]}"
        assert fams[0]["family_key"] == "entity:alcaraz"
        assert fams[0]["member_count"] == FAMILY_SIZE
        assert len(_flat_ids(body)) == PAGE, "the flat bucket must be saturated"

    @_asyncio
    async def test_the_family_is_wider_than_the_page(self, overflow_client):
        """The precondition for the whole defect. If this stops holding, the
        assertions below are testing a case that no longer occurs."""
        body = await _search(overflow_client)
        assert _families(body)[0]["member_count"] > len(_flat_ids(body))

    @_asyncio
    async def test_five_rows_render_below_the_family(self, overflow_client):
        body = await _search(overflow_client)
        assert len(_below_ids(body)) == HONEST_MORE


# ==========================================================================
# The ship: the footer names markets that exist on the page.
# ==========================================================================


class TestMoreCountIsPayable:
    @_asyncio
    async def test_promise_does_not_exceed_what_is_below(self, overflow_client):
        """🔴 THE DEFECT. Master promises 9 more markets below a page holding 5."""
        body = await _search(overflow_client)
        promised = sum(f["more_count"] for f in _families(body))
        below = _below_ids(body)
        assert promised <= len(below), (
            f'the page says "+{promised} more markets below" and puts '
            f"{len(below)} markets below it"
        )

    @_asyncio
    async def test_promise_is_exact_not_merely_safe(self, overflow_client):
        """Every row below this family IS one of its overflow members, so the
        payable count is not just a bound — it is the number. A fix that zeroed
        `more_count` would satisfy the assertion above and fail this one."""
        body = await _search(overflow_client)
        promised = sum(f["more_count"] for f in _families(body))
        assert promised == len(_below_ids(body)) == HONEST_MORE

    @_asyncio
    async def test_the_inflated_count_is_gone(self, overflow_client):
        body = await _search(overflow_client)
        assert _families(body)[0]["more_count"] != INFLATED_MORE
        assert _families(body)[0]["more_count"] == HONEST_MORE

    @_asyncio
    async def test_every_promised_market_is_actually_serialized(self, overflow_client):
        """The user-facing claim in its strongest form: the response can name a
        distinct market, present in `futures` and not already shown, for every
        unit of `more_count` the page prints."""
        body = await _search(overflow_client)
        below = set(_below_ids(body))
        for fam in _families(body):
            assert fam["more_count"] <= len(below), (
                f'family {fam["label"]!r} promises {fam["more_count"]} below, '
                f"payable rows: {len(below)}"
            )
            below = set(list(below)[fam["more_count"]:])  # each family spends its own

    @_asyncio
    async def test_the_page_is_not_emptied_to_win(self, overflow_client):
        """The counter-case for the rejected fix. Composing from the shipped ten
        would have made the count honest by deleting families; the family must
        still be here, still reading past the flat slice."""
        body = await _search(overflow_client)
        fams = _families(body)
        assert len(fams) == 1
        assert fams[0]["member_count"] == FAMILY_SIZE, (
            "the composer must still read the full deduped set — that width is "
            "what lets a family surface a market the ten-row slice omits"
        )
        assert len(fams[0]["members"]) == 4


# ==========================================================================
# Controls. Both are green on master too, and are labelled as such: their job
# is to pin what must NOT move, not to detect the defect.
# ==========================================================================


class TestControlsGreenOnBothArms:
    @_asyncio
    async def test_family_that_fits_promises_nothing(self, fits_client):
        """GREEN ON MAIN TOO. Five members, four shown, nothing overflows."""
        body = await _search(fits_client)
        fams = _families(body)
        assert len(fams) == 1
        assert fams[0]["member_count"] == 5
        assert fams[0]["more_count"] == 0
        assert _below_ids(body) == []

    @_asyncio
    async def test_family_inside_the_page_keeps_its_old_count(self, all_shipped_client):
        """GREEN ON MAIN TOO, and the most important control in the file. Eight
        members, all shipped: honest arithmetic and the old arithmetic agree at
        3, so this stays green only if the fix narrowed the count to "overflow
        that is below" rather than shrinking or removing it."""
        body = await _search(all_shipped_client)
        fams = _families(body)
        assert len(fams) == 1
        assert fams[0]["member_count"] == 8
        assert fams[0]["more_count"] == 3
        assert len(_below_ids(body)) == 3

    @_asyncio
    async def test_flat_bucket_shape_is_unchanged(self, overflow_client):
        """GREEN ON MAIN TOO. #2646 is a counting fix; the ten rows the response
        ships, and their order, must be byte-for-byte what they were."""
        body = await _search(overflow_client)
        assert _flat_ids(body) == [800_000 + i for i in range(PAGE)]

    @_asyncio
    async def test_member_count_still_describes_the_family(self, overflow_client):
        """GREEN ON MAIN TOO. `member_count` is deliberately NOT narrowed — it is
        a statement about the family, not a promise about the page, and nothing
        renders it. Pinned so a later cleanup does not quietly redefine it."""
        body = await _search(overflow_client)
        assert _families(body)[0]["member_count"] == FAMILY_SIZE


# ==========================================================================
# The composer's own contract. Cheap, and it names the argument that carries
# the rule, so a call site that stops passing it cannot pass silently.
# ==========================================================================


class TestComposerRequiresTheShippedSet:
    def test_serialized_ids_is_required(self):
        """No default. A default would let a new call site re-acquire #2646
        without anyone seeing it happen — the count would silently go back to
        describing the family instead of the page."""
        import inspect

        from app.routes.events import _compose_futures_families

        sig = inspect.signature(_compose_futures_families)
        param = sig.parameters["serialized_ids"]
        assert param.default is inspect.Parameter.empty

    def test_unshipped_overflow_is_not_counted(self):
        from app.routes.events import _compose_futures_families

        markets = _family()
        shipped = {m.id for m in markets[:PAGE]}
        fams = _compose_futures_families(
            markets, [("alcaraz", None)], lambda m: {"id": m.id, "name": m.name}, shipped
        )
        assert len(fams) == 1
        assert fams[0]["more_count"] == HONEST_MORE
        assert fams[0]["member_count"] == FAMILY_SIZE

    def test_nothing_shipped_promises_nothing(self):
        """The degenerate end of the rule: if the response serializes none of the
        overflow, the footer must not appear at all."""
        from app.routes.events import _compose_futures_families

        markets = _family()
        fams = _compose_futures_families(
            markets, [("alcaraz", None)], lambda m: {"id": m.id, "name": m.name}, set()
        )
        assert fams[0]["more_count"] == 0
