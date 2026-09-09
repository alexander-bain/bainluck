"""A NAMESAKE MUST NOT BLOCK THE PLAYER'S OWN MATCH. #4411, CERT-2392's repair.

`4411-SINNER-NAMESAKE-DOES-NOT-BLOCK-LAST-MATCH`.

WHAT THE FIRST PASS OF #4411 GOT WRONG, and why every test in
`tests/test_typeahead_leads_with_the_entity_4411.py` stayed green through it.
That file ranks a HAND-BUILT pool, so it can only prove that a pool containing
Jannik's match orders it first. It cannot see the two production facts that
together made the ship false for `sinner`:

  1. There is a Counter-Strike roster called **Sinners**, and `_fold_token`
     strips the plural, so `tokens("Sinners")` is `("sinner",)`. The promotion
     test therefore said the query `sinner` NAMED the esports rows, and their
     live fixtures were promoted over the player's match.

  2. The or-last arm was triggered by `if not _ta_rows` — the emptiness of the
     raw pool. Those same two esports rows made the pool non-empty, so the arm
     that fetches Jannik's completed match never ran. The pool was full of
     somebody else, which for this purpose is exactly as empty as nothing.

MEASURED ON PRODUCTION, 2026-09-09 11:50 PT, `GET /api/events/typeahead?q=sinner`
(the pre-#4411 ordering, and the raw pool the fixture below reproduces):

    futures  Counter-Strike: NIP vs Sinners - Map 1 Winner
    futures  Counter-Strike: NIP vs Sinners - Map 2 Winner
    event    Saint Sinners at Spirit Academy
    event    NIP at Sinners
    futures  US Open Men's Singles Winner
    futures  2026 Men's US Open Winner (Tennis)
    futures  ATP 1000 Montreal: Winner

and by db-query, the two live rows behind those events:

    15307787  Spirit Academy  vs  Saint Sinners  live  esports
    15307786  Sinners         vs  NIP            live  esports

WHY THIS IS A ROUTE TEST AND NOT ANOTHER CASE IN THE UNIT FILE. Both defects
live in the POOL ASSEMBLY — one in which rows are fetched, one in which are
promoted. A unit test that hands the ranker a pool has already made both
decisions itself, which is precisely how the first pass shipped with 33 green
tests and the reported bug intact.

THE PLURAL IS THE CONTROL, not a footnote. `sinners` must still promote the
esports roster and must NOT run the or-last arm: if the fix were "never promote
anything containing `sinner`" both arms of this file would go green while the
rule had been broken for the team that really is called Sinners.

WHY THE COMPLETED MATCH BELOW IS SEEDED, AND WHY THAT IS NOT A DODGE. Jannik is
not playing this US Open. Measured 2026-09-09: the semi-final field on
"US Open Men's Singles Winner" is Zverev .435 / Shelton .375 / Tiafoe .095 /
Khachanov .045, he is a residual outcome at .010, he has no 2026 US Open match
market of any kind, and his most recent event row is 2026-07-18 — outside the
arm's own 30-day floor. His Kecmanovic / Shapovalov / Tien props are March and
July matches and all four ARE attached to their events, so this is an absence,
not a matching gap, and nothing is filed for it.

What that means for the ship is worth stating plainly, because it is easy to
read this file as proving more than it does: on production TODAY, `sinner`
answers with his props, because there is no match of his to lead with and we
have no player entity page to offer instead. The repair still changes that page
— it stops a Counter-Strike fixture being served as "the answer" for Jannik —
and the leading half is exercised for real by `shelton` and `alcaraz`, who have
matches. The seed here is what lets the arm be tested at all; re-seed it from
production the next time he is in a draw.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.services.database import get_db, get_db_rw
from tests.integration.test_route_typeahead_headline_slot_2579 import (
    _empty_result,
    _market,
    _outcome,
)

_asyncio = pytest.mark.asyncio

_NOW = datetime.now(timezone.utc)

#: Production's two live Counter-Strike rows, by name. The roster is plural.
ESPORTS_A = "Saint Sinners at Spirit Academy"
ESPORTS_B = "NIP at Sinners"
#: The player's own match. Completed, inside the 30-day floor, so the or-last
#: arm can reach it once its trigger is right.
JANNIK = "Miomir Kecmanovic at Jannik Sinner"


def _event(*, eid, home, away, status, commence, sport="esports"):
    """An Event shaped as the typeahead's pool assembly reads it.

    `home_team`/`away_team` are None on purpose — the route already guards them
    for logos, and a fake logo would add a field this file does not measure.
    """
    return SimpleNamespace(
        id=eid,
        home_team_name=home,
        away_team_name=away,
        status=status,
        commence_time=commence,
        sport=SimpleNamespace(key=sport),
        home_team=None,
        away_team=None,
    )


def _live_esports():
    """The two rows that made the pool non-empty without answering the query."""
    return [
        _event(
            eid=15_307_787,
            home="Spirit Academy",
            away="Saint Sinners",
            status="live",
            commence=_NOW - timedelta(minutes=45),
        ),
        _event(
            eid=15_307_786,
            home="Sinners",
            away="NIP",
            status="live",
            commence=_NOW - timedelta(minutes=45),
        ),
    ]


def _jannik_last_match():
    """One completed match, five days old — inside `_LAST_MATCH_LOOKBACK_DAYS`."""
    return [
        _event(
            eid=15_300_001,
            home="Jannik Sinner",
            away="Miomir Kecmanovic",
            status="completed",
            commence=_NOW - timedelta(days=5),
            sport="tennis_atp_us_open",
        )
    ]


#: His props, by production's own names. Every one is MC1 on `sinner`, which is
#: what makes them beat a plain `event` and lose to a promoted one.
SINNER_PROPS = [
    "Jannik Sinner: Total Games",
    "Jannik Sinner vs Miomir Kecmanovic: Set 1 Winner",
    "Counter-Strike: NIP vs Sinners - Map 1 Winner",
    "Denis Shapovalov vs Jannik Sinner: Exact Match Score",
]


def _props():
    return [
        _market(
            mid=940_000 + i,
            name=name,
            volume=5_000.0,
            outcomes=[
                _outcome("Yes", 0.52, (940_000 + i) * 10 + 1),
                _outcome("No", 0.48, (940_000 + i) * 10 + 2),
            ],
        )
        for i, name in enumerate(SINNER_PROPS)
    ]


def _is_event_select(sql: str) -> bool:
    return "FROM events" in sql and "SELECT" in sql.upper()


def _is_last_match_select(sql: str) -> bool:
    """The or-last arm, told apart from the upcoming pool by its own clauses.

    Both select events; only this one asks for finished rows newest-first. Keyed
    on the two clauses that define it rather than on a variable name, so it
    still recognises the arm after a rename or a reflow.
    """
    lowered = sql.lower()
    return (
        _is_event_select(sql)
        and "desc" in lowered
        and "status" in lowered
    )


class _Recorder:
    """A session that seeds the three lanes and records which ones ran.

    `last_match_calls` is the observable for "the fallback was REACHED". Reading
    it from the session rather than from a patch means the test cannot pass by
    the arm being called somewhere that does not feed the dropdown.
    """

    def __init__(self, *, upcoming, last_match, futures):
        self.upcoming = upcoming
        self.last_match = last_match
        self.futures = futures
        self.last_match_calls = 0
        self.session = AsyncMock()
        self.session.execute = AsyncMock(side_effect=self._execute)

    async def _execute(self, stmt, *args, **kwargs):
        result = _empty_result()
        try:
            sql = str(stmt)
        except Exception:  # noqa: BLE001
            return result
        if _is_last_match_select(sql):
            self.last_match_calls += 1
            rows = self.last_match
        elif _is_event_select(sql):
            rows = self.upcoming
        elif "futures_markets" in sql and "SELECT" in sql.upper():
            rows = self.futures
        else:
            return result
        result.scalars.return_value.all.return_value = list(rows)
        result.scalars.return_value.unique.return_value.all.return_value = list(rows)
        return result


def _app_for(recorder, monkeypatch):
    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")
    from app.main import app

    async def _mock_get_db():
        yield recorder.session

    async def _mock_get_optional_user():
        return None

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_db_rw] = _mock_get_db
    app.dependency_overrides[get_optional_user] = _mock_get_optional_user
    return app


async def _client(recorder, monkeypatch):
    app = _app_for(recorder, monkeypatch)
    with patch("app.main.init_db", new_callable=AsyncMock):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def namesake(monkeypatch):
    """The reported shape: two live namesakes upcoming, the player's match past."""
    rec = _Recorder(
        upcoming=_live_esports(),
        last_match=_jannik_last_match(),
        futures=_props(),
    )
    async for ac in _client(rec, monkeypatch):
        yield ac, rec


async def _suggest(client, q):
    resp = await client.get(f"/api/events/typeahead?q={q}")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _texts(body):
    return [s.get("text") for s in body["suggestions"]]


def _index(texts, needle):
    for i, t in enumerate(texts):
        if needle.lower() in (t or "").lower():
            return i
    return None


# ==========================================================================
@_asyncio
class TestTheSeedIsReal:
    """If these fail, every ordering assertion below is vacuous."""

    async def test_the_dropdown_is_not_empty(self, namesake):
        client, _ = namesake
        assert _texts(await _suggest(client, "sinner"))

    async def test_the_namesake_rows_are_in_the_pool(self, namesake):
        """The whole defect needs them PRESENT. A seed that drops them tests
        the empty-pool path, which was never broken."""
        client, _ = namesake
        texts = _texts(await _suggest(client, "sinner"))
        assert _index(texts, "Spirit Academy") is not None
        assert _index(texts, "NIP") is not None

    async def test_his_props_are_in_the_pool(self, namesake):
        client, _ = namesake
        texts = _texts(await _suggest(client, "sinner"))
        assert _index(texts, "Total Games") is not None


# ==========================================================================
@_asyncio
class TestTheRepair:
    """The three clauses CERT-2392 named, each independently observable."""

    async def test_the_fallback_is_REACHED(self, namesake):
        """Defect 2. A non-empty pool must not switch the arm off.

        This is the assertion that fails on the shipped `if not _ta_rows`, and
        it fails for the right reason: the count is zero, not the order wrong.
        """
        client, rec = namesake
        await _suggest(client, "sinner")
        assert rec.last_match_calls == 1, (
            "the or-last arm did not run — a pool full of namesakes suppressed "
            "it exactly as an empty pool would have been served by it"
        )

    async def test_jannik_leads(self, namesake):
        """Defect 1 and 2 together, as the reader sees them."""
        client, _ = namesake
        texts = _texts(await _suggest(client, "sinner"))
        assert texts[0] == JANNIK, f"q=sinner still leads with {texts[0]!r}"

    async def test_the_namesake_is_not_promoted(self, namesake):
        """Defect 1 alone, and NOT restated as `texts[0]`.

        A promoted esports row is `entity_event` (2) and would outrank every
        prop (3); an unpromoted one is a plain `event` (4) and sorts below them.
        So "did the plural fold" is readable off the page without an internal:
        both namesakes must sit BELOW every prop.
        """
        client, _ = namesake
        texts = _texts(await _suggest(client, "sinner"))
        last_prop = max(
            i for i, t in enumerate(texts)
            if any(p.lower() in (t or "").lower() for p in ("total games", "set 1 winner"))
        )
        for row in ("Spirit Academy", "NIP"):
            at = _index(texts, row)
            assert at is not None and at > last_prop, (
                f"{row!r} was promoted over the props — the plural folded and "
                f"the namesake is being read as the player: {texts}"
            )

    async def test_every_prop_sorts_below_his_match(self, namesake):
        """Alex's rule reaches past rank 0: "then its games, then props"."""
        client, _ = namesake
        texts = _texts(await _suggest(client, "sinner"))
        jannik = _index(texts, "Jannik Sinner at") or _index(texts, "Kecmanovic")
        first_prop = min(
            i for i, t in enumerate(texts)
            if any(p.lower() in (t or "").lower() for p in ("total games", "set 1 winner"))
        )
        assert jannik < first_prop, f"a prop outranked his match: {texts}"


# ==========================================================================
@_asyncio
class TestThePluralControl:
    """`sinners` is a real team. The fix must not have cost it its own row."""

    @pytest_asyncio.fixture
    async def plural(self, monkeypatch):
        rec = _Recorder(
            upcoming=_live_esports(),
            last_match=_jannik_last_match(),
            futures=_props(),
        )
        async for ac in _client(rec, monkeypatch):
            yield ac, rec

    async def test_the_roster_leads_when_the_plural_is_typed(self, plural):
        """The other side of the boundary. If this goes red the repair
        degenerated into "never promote a row containing `sinner`"."""
        client, _ = plural
        texts = _texts(await _suggest(client, "sinners"))
        assert _index(texts, "NIP") == 0 or _index(texts, "Spirit Academy") == 0, (
            f"q=sinners no longer leads with the roster's own match: {texts}"
        )

    async def test_the_fallback_does_NOT_run_when_a_participant_is_named(self, plural):
        """The trigger, pinned in its OFF direction.

        `if True:` — running the arm unconditionally — passes every test in the
        class above. This is the one it fails.
        """
        client, rec = plural
        await _suggest(client, "sinners")
        assert rec.last_match_calls == 0, (
            "the or-last arm ran although the upcoming pool already held a row "
            "the query named — the trigger is not reading the promotion"
        )


# ==========================================================================
@_asyncio
class TestTheArmSurvivesTheTruncation:
    """A crowded namesake pool. The arm can be REACHED and still not be SEEN.

    `_ta_events[:_EVENT_POOL_SIZE]` cuts the pool to four BEFORE anything is
    scored, so admitting the player's match and then queueing it behind four
    live namesakes drops it on the way to the scorer. The dropdown then looks
    exactly as it does with the arm switched off, and every assertion in
    `TestTheRepair` passes on the two-row fixture above because two rows plus
    one leaves room.

    Production supports the crowded shape: `%sinner%` returns eleven esports
    rows in the last week, four of them dated 2026-09-06 or later.
    """

    @pytest_asyncio.fixture
    async def crowded(self, monkeypatch):
        rec = _Recorder(
            upcoming=[
                _event(
                    eid=15_307_780 + i,
                    home=home,
                    away=away,
                    status="live",
                    commence=_NOW - timedelta(minutes=45),
                )
                for i, (home, away) in enumerate(
                    [
                        ("Spirit Academy", "Saint Sinners"),
                        ("Sinners", "NIP"),
                        ("Sinners", "Team Nemesis"),
                        ("K27", "Sinners"),
                        ("BBL", "Sinners"),
                    ]
                )
            ],
            last_match=_jannik_last_match(),
            futures=_props(),
        )
        async for ac in _client(rec, monkeypatch):
            yield ac, rec

    async def test_his_match_still_reaches_the_scorer(self, crowded):
        """Appending instead of prepending fails here and nowhere else."""
        client, rec = crowded
        texts = _texts(await _suggest(client, "sinner"))
        assert rec.last_match_calls == 1
        # The EXACT event text, never a surname substring: two of his props are
        # also named after this opponent ("Jannik Sinner vs Miomir Kecmanovic:
        # Set 1 Winner"), so a `"Kecmanovic" in texts` probe passes on a page
        # that dropped the match entirely. Caught by mutation, not by review.
        assert JANNIK in texts, (
            "his match was admitted and then truncated away before scoring — "
            f"the arm ran and the reader still cannot see it: {texts}"
        )

    async def test_and_it_still_leads(self, crowded):
        client, _ = crowded
        texts = _texts(await _suggest(client, "sinner"))
        assert texts[0] == JANNIK, f"q=sinner leads with {texts[0]!r}"


# ==========================================================================
class TestTheRuleUnderneath:
    """The predicate itself, singular against plural, with no route in the way."""

    def test_the_singular_does_not_name_the_plural_roster(self):
        from app.utils.search_match_class import query_names_participant

        assert not query_names_participant("sinner", ["Sinners", "NIP"])

    def test_the_plural_does_name_it(self):
        from app.utils.search_match_class import query_names_participant

        assert query_names_participant("sinners", ["Sinners", "NIP"])

    def test_the_player_is_still_named_by_his_surname(self):
        """The repair must not have made the promotion stricter than the ship."""
        from app.utils.search_match_class import query_names_participant

        assert query_names_participant(
            "sinner", ["Jannik Sinner", "Miomir Kecmanovic"]
        )

    def test_accents_still_fold_because_they_never_merge_two_entities(self):
        """`_name_tokens` drops the plural strip and KEEPS accent folding. A
        repair that threw out both would break `espana` for a Spanish name."""
        from app.utils.search_match_class import query_names_participant

        assert query_names_participant("espana", ["España", "Portugal"])


# ==========================================================================
#: Production's real futures for `sinner` on 2026-09-09, by their own names. The
#: two Counter-Strike rows are the namesake; the tennis field is the player, and
#: it carries him ONLY in its outcomes — which is the whole difficulty, because
#: an outcome-only match is MC4 and a name match is MC1.
CS_MAP_1 = "Counter-Strike: NIP vs Sinners - Map 1 Winner"
CS_MAP_2 = "Counter-Strike: NIP vs Sinners - Map 2 Winner"
US_OPEN_FIELD = "US Open Men's Singles Winner"


def _no_jannik_match_futures():
    return [
        _market(
            mid=60_362_846,
            name=CS_MAP_1,
            volume=5_000.0,
            outcomes=[_outcome("Yes", 0.605, 1), _outcome("No", 0.395, 2)],
        ),
        _market(
            mid=60_369_233,
            name=CS_MAP_2,
            volume=5_000.0,
            outcomes=[_outcome("Yes", 0.605, 3), _outcome("No", 0.395, 4)],
        ),
        _market(
            mid=34_277_822,
            name=US_OPEN_FIELD,
            volume=50_000.0,
            outcomes=[
                _outcome("Alexander Zverev", 0.435, 5),
                _outcome("Ben Shelton", 0.375, 6),
                _outcome("Jannik Sinner", 0.010, 7),
            ],
        ),
    ]


@_asyncio
class TestTheNamesakeMarketsInTheRealNoMatchState:
    """CERT-2399's finding, and the state production is ACTUALLY in.

    The repair before this one fixed the two EVENT defects — the plural fold in
    the promotion, and an or-last trigger that read emptiness instead of absence.
    Both were real. Neither touched what the reader actually sees for `sinner`,
    because Jannik has no match inside the 30-day floor at all, so the dropdown
    is futures the whole way down and the ordering is decided by `match_class`:

        "…NIP vs Sinners - Map 1 Winner"   name match, plural-folded  -> MC1
        "US Open Men's Singles Winner"     outcome "Jannik Sinner"    -> MC4

    Class comes first and is inviolable, so the namesake roster won every time.
    Measured on production at 19:44Z: the two Counter-Strike rows were ranks 0
    and 1, and his own field was rank 2.

    These tests seed exactly that — no Jannik event anywhere — so they fail
    against the previous repair and pass against this one.
    """

    @pytest_asyncio.fixture
    async def no_match(self, monkeypatch):
        rec = _Recorder(
            upcoming=_live_esports(),
            last_match=[],  # he is not in this US Open; there is nothing to find
            futures=_no_jannik_match_futures(),
        )
        async for ac in _client(rec, monkeypatch):
            yield ac, rec

    async def test_the_seed_is_real(self, no_match):
        """Vacuity guard: all three futures must actually reach the dropdown."""
        client, _ = no_match
        texts = _texts(await _suggest(client, "sinner"))
        for needle in ("Map 1", "Map 2", "US Open"):
            assert _index(texts, needle) is not None, (
                f"{needle} never reached the dropdown, so the ordering "
                f"assertions below would be vacuous: {texts}"
            )

    async def test_his_own_field_leads_the_namesake_markets(self, no_match):
        """THE SHIP. Typing `sinner` answers with the tennis he is in, not with
        a Counter-Strike map."""
        client, _ = no_match
        texts = _texts(await _suggest(client, "sinner"))
        field = _index(texts, "US Open")
        for needle in ("Map 1", "Map 2"):
            assert field < _index(texts, needle), (
                f"the {needle} namesake still outranks his own field: {texts}"
            )

    async def test_the_namesake_markets_are_downranked_not_dropped(self, no_match):
        """`refuse/downrank` is a REORDER, never a filter.

        A scorer that also filters can empty a result set while claiming to have
        ordered it — the module says so in as many words. Somebody who really did
        want that Counter-Strike map must still be able to find it.
        """
        client, _ = no_match
        texts = _texts(await _suggest(client, "sinner"))
        assert _index(texts, "Map 1") is not None
        assert _index(texts, "Map 2") is not None

    async def test_the_plural_preserves_them(self, no_match):
        """The other side of the boundary, on the MARKET half this time.

        `sinners` names the roster exactly, so nothing is demoted and the
        Counter-Strike rows lead. A repair that degenerated into "always bury a
        row containing `sinner`" fails here.
        """
        client, _ = no_match
        texts = _texts(await _suggest(client, "sinners"))
        lead = _index(texts, "Map 1")
        assert lead is not None and lead < _index(texts, "US Open"), (
            f"q=sinners no longer leads with the roster's own markets: {texts}"
        )


# ==========================================================================
class TestTheSetLevelRuleUnderneath:
    """The plural-namesake rule as a rule, away from the route.

    It is deliberately NOT expressible per-candidate: `yankee` against "New York
    Yankees" is the same shape as `sinner` against "Sinners", and demoting it
    would break "typing a team name finds the team". What separates them is the
    RESULT SET — whether anything in it really is called what was typed.
    """

    def test_the_gate_is_what_saves_the_yankees(self):
        from app.utils.search_match_class import Evidence, rank

        team = Evidence(name="New York Yankees", kind="team",
                        sport_key="baseball_mlb")
        market = Evidence(name="Yankees World Series Winner", kind="futures",
                          sport_key="baseball_mlb")
        # Nothing in the set is called "yankee", so the fold is doing honest
        # recall work and the rule must not fire at all.
        for q in ("yank", "yankee", "yankees"):
            assert rank(q, [(team, "team"), (market, "market")]) == [
                "market", "team",
            ], f"q={q} was reordered by a rule that should not have fired"
        # ...and with the gate OPEN, the plural namesake goes below.
        player = Evidence(name="Some Market", outcomes=("Ron Yankee",),
                          kind="futures")
        out = rank("yankee", [(team, "team"), (market, "market"),
                              (player, "player")])
        assert out[0] == "player", (
            f"an exact whole-token match did not lead its own namesakes: {out}"
        )

    def test_a_closed_gate_changes_nothing_at_all(self):
        """The safety property. With no exact match anywhere in the set, the
        order must be byte-for-byte what it was before #4411's set-level rule."""
        from app.utils.search_match_class import Evidence, rank, rank_key

        evs = [
            Evidence(name="Stalybridge Celtic FC", kind="futures"),
            Evidence(name="Celtic Park Tours", kind="market"),
            Evidence(name="Boston Celts", kind="team"),
        ]
        pairs = [(ev, i) for i, ev in enumerate(evs)]
        expected = [
            i for _, i in sorted(
                ((rank_key("celtics", ev), i) for ev, i in pairs),
                key=lambda r: r[0],
            )
        ]
        assert rank("celtics", pairs) == expected
