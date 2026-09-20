"""#7432 — the one section count `/entertainment` shows a reader names its rows.

THE DEFECT. The Tech & Culture sidebar drew

    Tech & Culture                    49 MARKETS
    Net worth, social media, and platform bets
    [ 15 rows ]

`themes.tech_culture.count` was `len(themed["social_media"])`. That dict is
filled by the loop in `get_entertainment`, which applies only
`should_exclude_from_featured` before it appends. `_market_row` and
`_is_interesting` run later, inside `_build_list`, and they run BEFORE its
`[:15]`. So the bucket length is a PRE-GATE pool: it counts rows this route
itself then refuses for reading settled, stale or uninteresting, and there is no
"show more", so nothing a reader can do reaches them.

WHICH FAMILY IT IS IN, because the two nearby fixes want opposite repairs.
#7423 (`/weather`'s map said "336 markets", `allCities.length * 8`) was an
INVENTED literal — nothing counted anything. This is #6978's defect instead:
"those heroes were `len(all_markets)`, the PRE-GATE pool, so they called rows
active that the route had already dropped". A real pool, and the wrong one.
Measured on the served bank 2026-09-20 13:47Z: **49** printed over **15**
rendered — and the issue banked **50** six hours earlier, so it drifts, which is
how you can tell a live bucket from a literal without reading the code.

WHY THE REPAIR IS HERE AND NOT IN THE JSX. #7392's note in the route says this
field is rendered "in a single place (line 1301, `TechCultureSidebar`)". That is
true of the web page and not of the field:

  * `frontend/app/entertainment/page.tsx:1301` — `{data.count} markets`, over 15
  * `ios/Bain Luck/Bain Luck/Views/EntertainmentView.swift:630` —
    `SectionTitle(title: "Platform bets & social", count: data.count)`, over
    `markets.prefix(10)`

So the app printed 49 over 10, a 4.9x over-claim against the web's 3.3x. A
`data.markets.length` in the JSX would have been true by construction on the web
and left the app lying, needing a second lane's ship to finish. Deriving the
number in the payload is the only repair that reaches both readers, and it is
why this file is an integration test of the route rather than a jest render.

  ⚠️ ONE RESIDUAL IS DELIBERATELY NOT FIXED HERE. With `count` = 15 the iPhone
  still prints 15 over the 10 rows its own `prefix(10)` draws. That cap is in
  `ios/**`, which is native's under notice 41, so it is filed and routed rather
  than reached into from this lane. This file cannot see it — no pytest arm can
  — which is exactly why it is said here in words.

WHAT WOULD MAKE THIS FILE VACUOUS. Every arm below rests on the served list
being SHORTER than the bucket it came from. `TestTheFixtureActuallyDropsSomething`
recomputes that gap from the fixture and fails loudly if a later edit closes it,
because with bucket == served the ship and the formula it replaced agree and
nothing here is measuring anything. The three candidate values are kept distinct
for the same reason (6 / 9 / 15): a fixture on which two of them tie cannot say
which one the route is running.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.routes import entertainment as entertainment_module


# ---------------------------------------------------------------------------
# Mocks — the shared idiom from
# test_entertainment_hero_counts_what_the_page_reaches_7392
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


def _market(*, market_id, name, probability=0.35, volume_24h=1000):
    """A single-outcome entertainment market.

    ``probability`` is on the 0-1 scale the column uses and `_market_row`
    multiplies it by 100, so the two gates read it on different scales:

    * ``should_exclude_from_featured`` sees the RAW leader and drops it outside
      ``(0.02, 0.98)``.
    * ``_is_interesting`` sees the PERCENT and drops
      ``outcome_count <= 2 and prob > 95``.

    0.97 therefore clears the first and is dropped by the second. That is the
    only mechanism by which the social_media bucket can be larger than the
    social_media rows served, so it is the mechanism this whole file rests on.
    """
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=market_id,
        name=name,
        external_id=f"mock{market_id}",
        source="kalshi",
        category="news",
        llm_sport_category="entertainment",
        outcomes=[
            SimpleNamespace(
                id=market_id * 10,
                name="Yes",
                current_probability=probability,
                probability_change_24h=0,
                rank=1,
                is_winner=None,
                resolution_source=None,
            )
        ],
        market_metadata=None,
        resolution_date=now + timedelta(days=30),
        updated_at=now,
        volume_24h=volume_24h,
        image_url=None,
        hook_description=None,
        status="open",
    )


# Every name here is checked against the real `_classify_theme` by
# `TestTheFixtureLandsWhereItClaims` before any count is asserted. The regex
# list is ORDERED and social_media sits sixth, so a name carrying an earlier
# token ("album", "film", "streaming", "Emmy") would be filed somewhere else and
# quietly shrink the bucket these arms measure. None of these do.
_SOCIAL_SERVED = [
    "How many YouTube subscribers will the channel have?",
    "Will the TikTok follower count pass 50 million?",
    "Will the Twitch streamer hit one million concurrents?",
    "Will Elon Musk tweet about the merger before October?",
    "Will the podcast reach ten million downloads?",
    "Will the influencer launch a brand this year?",
]

_SOCIAL_DROPPED_LATE = [
    "Will Instagram keep its reels tab?",
    "How many views will the upload get in week one?",
    "Will MrBeast post again before Friday?",
]


def _fixture():
    """Nine social_media markets, three of which the route accepts and refuses.

    The three at 0.97 clear `should_exclude_from_featured` and are dropped by
    `_is_interesting`, so the bucket is 9 and the served list is 6. One music
    row rides along so the payload is not a single-section degenerate that only
    exercises the sidebar's own early return.
    """
    rows = [
        _market(market_id=400 + i, name=name)
        for i, name in enumerate(_SOCIAL_SERVED)
    ]
    rows += [
        _market(market_id=420 + i, name=name, probability=0.97)
        for i, name in enumerate(_SOCIAL_DROPPED_LATE)
    ]
    rows.append(
        _market(market_id=440, name="Which album will debut at #1 on the Billboard chart?")
    )
    return rows


def _over_cap_fixture():
    """Eighteen servable social_media markets, so `_build_list`'s `[:15]` bites.

    This is the arm that separates `len(the served list)` from `len(the bucket)`
    a second time, at the other end: here the two differ by 3 rather than by 3
    dropped rows, and a `count` that read the bucket would print 18 over 15.
    """
    return [
        _market(
            market_id=500 + i,
            name=f"Will the YouTube channel pass {i + 1} million subscribers?",
        )
        for i in range(SM_BUCKET_OVER_CAP)
    ]


# The three candidate values, kept distinct on purpose.
SM_BUCKET = 9           # `len(themed["social_media"])` — the retired formula
SM_SERVED = 6           # what the sidebar actually renders — the ship
SM_CAP = 15             # `_build_list`'s limit, a tempting constant to print
SM_BUCKET_OVER_CAP = 18  # the second fixture's bucket, > the cap


async def _payload(client, mock_db, markets=None):
    mock_db.execute.return_value = _MockResult(
        _fixture() if markets is None else markets
    )
    resp = await client.get("/api/entertainment")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "themes" in body, (
        "the route fell through to its timeout/error shape, so every count "
        f"below would be vacuous: {body}"
    )
    return body["themes"]["tech_culture"]


def _social_bucket(markets):
    """Recompute the pre-gate bucket from the fixture, through the real classifier.

    Recomputed rather than remembered: a hard-coded 9 would still pass if a
    later regex edit moved three of these rows into `celebrity` and left the
    arms below comparing two numbers that had both quietly changed.
    """
    return [
        m for m in markets
        if entertainment_module._classify_theme(m) == "social_media"
    ]


class TestTheFixtureLandsWhereItClaims:
    """Before any count means anything, the rows have to be in the bucket."""

    def test_every_named_row_classifies_as_social_media(self):
        markets = _fixture()
        bucket = _social_bucket(markets)
        assert len(bucket) == SM_BUCKET, (
            f"expected {SM_BUCKET} rows in the social_media bucket, got "
            f"{len(bucket)}. `_THEME_BY_NAME` is ordered and social_media is "
            "sixth, so a name carrying an earlier token has been filed "
            "elsewhere and every arm in this file is now measuring a bucket it "
            "did not build: "
            + repr([
                (m.name, entertainment_module._classify_theme(m))
                for m in markets
                if entertainment_module._classify_theme(m) != "social_media"
            ])
        )

    def test_the_three_candidate_values_are_distinct(self):
        assert len({SM_BUCKET, SM_SERVED, SM_CAP}) == 3, (
            "two of the bucket size, the served size and the cap have become "
            "equal, so an arm asserting the count is one of them can no longer "
            "say it is not another."
        )


class TestTheFixtureActuallyDropsSomething:
    """Without this gap the ship and the formula it replaced agree."""

    async def test_the_bucket_is_strictly_larger_than_the_rows_served(
        self, client, mock_db
    ):
        markets = _fixture()
        tc = await _payload(client, mock_db, markets)
        bucket = len(_social_bucket(markets))
        served = len(tc["markets"])
        assert served < bucket, (
            f"the fixture is not discriminating: the route served {served} of "
            f"{bucket} classified rows, so an assertion that the count equals "
            "the served rows would also hold for the pre-gate bucket and this "
            "file would pass against the defect it was written for. The three "
            "0.97 rows are supposed to clear the featured gate and be dropped "
            "by `_is_interesting`."
        )
        assert served == SM_SERVED
        assert bucket == SM_BUCKET


class TestTheCountNamesTheRowsItSitsOver:
    """The ship."""

    async def test_the_count_equals_the_served_list(self, client, mock_db):
        tc = await _payload(client, mock_db)
        assert tc["count"] == len(tc["markets"]), (
            f"the sidebar publishes {tc['count']} over {len(tc['markets'])} "
            "rows. This is the only section count `/entertainment` shows a "
            "reader, on the web and in the app, and there is no 'show more' "
            "behind it."
        )
        assert tc["count"] == SM_SERVED

    async def test_the_count_is_not_the_pre_gate_bucket(self, client, mock_db):
        markets = _fixture()
        tc = await _payload(client, mock_db, markets)
        bucket = len(_social_bucket(markets))
        assert tc["count"] != bucket, (
            "the sidebar publishes `len(themed['social_media'])` again — the "
            "raw `_classify_theme` bucket, counted before `_market_row` and "
            "`_is_interesting` have refused anything. That is #6978's defect "
            "and it printed 49 over 15 on production."
        )
        assert tc["count"] < bucket

    async def test_the_count_is_not_the_cap(self, client, mock_db):
        tc = await _payload(client, mock_db)
        assert tc["count"] != SM_CAP, (
            f"the sidebar publishes `_build_list`'s limit ({SM_CAP}) rather "
            "than the length of what it returned. The list is shorter than the "
            "cap whenever the gate leaves fewer survivors, which is precisely "
            "the thin day on which an honest count matters most."
        )


class TestAtTheCapTheCountIsStillTheRowsServed:
    """The other end: bucket 18, cap 15, and the count must be 15."""

    async def test_a_bucket_over_the_cap_publishes_the_cap_not_the_bucket(
        self, client, mock_db
    ):
        markets = _over_cap_fixture()
        tc = await _payload(client, mock_db, markets)
        bucket = len(_social_bucket(markets))
        assert bucket == SM_BUCKET_OVER_CAP, (
            f"the over-cap fixture put {bucket} rows in the bucket, not "
            f"{SM_BUCKET_OVER_CAP}, so it no longer exceeds the cap and this "
            "arm is measuring nothing."
        )
        assert len(tc["markets"]) == SM_CAP, (
            f"`_build_list` returned {len(tc['markets'])} rows from a bucket of "
            f"{bucket}; this arm needs the cap to bite."
        )
        assert tc["count"] == len(tc["markets"]) == SM_CAP, (
            f"the sidebar publishes {tc['count']} over {len(tc['markets'])} "
            "rendered rows when the bucket overflows the cap."
        )
        assert tc["count"] != bucket


class TestTheEmptyCaseStillPublishesZero:
    """`frontend` early-returns on an empty list and the app renders no section;
    the payload still has to agree with itself rather than advertise a bucket
    that reached nobody. `test_route_category_pages` asserts the 0 from the
    other side, on a route with no markets at all; this one has a bucket."""

    async def test_a_bucket_whose_every_row_is_refused_counts_zero(
        self, client, mock_db
    ):
        markets = [
            _market(market_id=600 + i, name=name, probability=0.97)
            for i, name in enumerate(_SOCIAL_SERVED)
        ]
        tc = await _payload(client, mock_db, markets)
        assert len(_social_bucket(markets)) == len(_SOCIAL_SERVED)
        assert tc["markets"] == []
        assert tc["count"] == 0, (
            f"every row in the bucket was refused by `_is_interesting` and the "
            f"sidebar still publishes {tc['count']} markets."
        )
