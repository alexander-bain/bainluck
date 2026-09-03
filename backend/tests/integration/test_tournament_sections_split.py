"""latency/135: the hub answers the first screen without the other 76% of itself.

Alex, 2026-09-03, on the felt table: the US Open hub is the slowest tab of every
tab we measure — p50 0.93 s, worst 1.69 s — and *"the first screen needs the
slate + live rows; grids/bracket/results can arrive second"*.

MEASURED ON PRODUCTION THE SAME AFTERNOON, one response decomposed by top-level
key (902,423 bytes uncompressed / 86,838 gzipped, `x-timing-split` wall 847 ms
cold / 30 ms warm):

    grids    377,074  41.8%   the Bracket TAB — nothing until a reader taps it
    results  315,108  34.9%   260 finished matches, below the day's card
    boards   126,665  14.0%   the chart, which IS the first element
    slate     59,989   6.6%   the day's matches
    the rest  23,587   2.6%

`?sections=first` is the top-and-bottom-of-that-list split: 207,193 bytes
(19,822 gzipped) against 902,423 — 77.2% off the wire — and 356 of the register's
692 pinned outcome ids instead of all of them.

═══ WHAT THIS FILE IS FOR, WHICH IS NOT "THE SPLIT WORKS" ═══

A payload split has exactly one catastrophic failure mode and it is silent: a
key that belongs to neither half. The full response is the contract every other
caller on the site is already on — the native app, `/by-event/{id}`, every
existing test — and a section that quietly stopped being emitted would show up
as a blank strip on somebody's page weeks later, with two green suites behind
it. So the load-bearing test here is `test_the_split_is_exhaustive`: the default
payload must carry the union of both fragments' keys, asserted against the
fragments themselves rather than against a list somebody remembered to update.

The second failure mode is the merge. `event_links` is the one key BOTH halves
write — `by_matchup` addresses the day's card, `by_espn` the finished list — and
a plain `dict.update` would drop whichever channel landed first. That is
`test_the_full_payload_carries_both_link_channels`, and it is red against an
overwrite.
"""

import inspect

import pytest

from app.routes import tournaments
from app.utils.tournament_register import TournamentRegister, load_register

SLUG = "us-open"
URL = f"/api/tournaments/{SLUG}"


@pytest.fixture
def memory_cache(monkeypatch):
    """An in-memory stand-in for the per-group Redis cache.

    Local rather than "whatever Redis the test box has": these tests assert
    which group was BUILT, and a real cache shared with another test file would
    make that a function of collection order.
    """
    store: dict[str, dict] = {}

    async def _get(slug, group=tournaments.SECTION_FIRST):
        return store.get(f"{slug}:{group}")

    async def _set(slug, payload, group=tournaments.SECTION_FIRST):
        store[f"{slug}:{group}"] = payload

    monkeypatch.setattr(tournaments, "_cache_get", _get)
    monkeypatch.setattr(tournaments, "_cache_set", _set)
    return store


@pytest.fixture(autouse=True)
def _no_shared_cache(monkeypatch):
    """Every test in this file builds. Nothing here may be answered by a cache
    another test — or another process — happened to warm."""

    async def _miss(slug, group=tournaments.SECTION_FIRST):
        return None

    async def _noop(slug, payload, group=tournaments.SECTION_FIRST):
        return None

    monkeypatch.setattr(tournaments, "_cache_get", _miss)
    monkeypatch.setattr(tournaments, "_cache_set", _noop)


def _register_ids() -> dict[str, set[int]]:
    """The committed register's own id sets — the population this route bounds
    itself by. Read from the file, never restated here, so the numbers in the
    docstring above cannot drift away from the thing they describe."""
    register = load_register(SLUG, "2026")
    assert register is not None, (
        "the committed 2026 register did not load. This guard cannot check what "
        "the build loads if it cannot read what the build reads — a failure, "
        "not a skip."
    )
    reg = TournamentRegister(register)
    board = {
        block["outcome_id"]
        for player in reg.players
        for block in (player.get("sources") or [])
        if isinstance(block, dict) and isinstance(block.get("outcome_id"), int)
    }
    return {
        "board": board,
        "slate": set(reg.matchup_outcome_ids()),
        "props": set(reg.prop_outcome_ids()),
        "reach": set(reg.reach_outcome_ids()),
    }


class TestTheRegisterIsReadable:
    """The control. Without it every id assertion below is vacuously true."""

    def test_the_committed_register_pins_all_four_id_sets(self):
        ids = _register_ids()
        for name, values in ids.items():
            assert values, f"{name} outcome ids came back empty"
        # The saving this ship claims is the reach set, so it must be the big
        # one. If a register edit ever makes the grid cheap, this ship's premise
        # is gone and the test says so rather than passing quietly.
        assert len(ids["reach"]) > len(ids["board"])


class TestWhatEachHalfCarries:
    async def test_first_is_the_slate_the_chart_and_no_grid(self, client):
        body = (await client.get(f"{URL}?sections=first")).json()
        for key in ("slug", "title", "boards", "slate", "props", "bracket",
                    "broadcasts", "draw_released", "event_links"):
            assert key in body, key
        for key in tournaments.REST_SECTION_KEYS:
            assert key not in body, (
                f"{key} is 76% of the reason this split exists and it came back "
                "on the first-screen request"
            )
        # The day's card must be able to link on the FIRST request, or the split
        # trades bytes for a page full of dead rows.
        assert "by_matchup" in body["event_links"]

    async def test_rest_is_the_grid_and_the_finished_list(self, client):
        body = (await client.get(f"{URL}?sections=rest")).json()
        for key in tournaments.REST_SECTION_KEYS:
            assert key in body, key
        for key in ("boards", "slate", "props", "bracket"):
            assert key not in body, f"{key} belongs to the first screen"
        # Self-describing when served alone: a body that cannot say which
        # tournament it is is not one a client can safely merge.
        assert body["slug"] == SLUG
        assert body["generated_at"]
        # The finished list's own link channel travels WITH the finished list.
        assert "by_espn" in body["event_links"]

    async def test_no_parameter_is_the_payload_this_route_always_served(self, client):
        """The compatibility floor: the native app and `/by-event/{id}` never
        ask for a section and must not notice this change."""
        body = (await client.get(URL)).json()
        for key in ("slug", "title", "subtitle", "tournament", "season",
                    "register_version", "draw_released", "boards", "slate",
                    "props", "bracket", "grids", "results", "broadcasts",
                    "render_findings", "generated_at", "event_links",
                    "auto_linked_matchups"):
            assert key in body, key

    async def test_the_split_is_exhaustive(self, client):
        """NO KEY MAY BELONG TO NEITHER HALF.

        The one silent failure of a payload split. Asserted against the two
        fragments themselves, so a section added to the full build and forgotten
        by both groups is caught here rather than by a reader looking at a blank
        strip.
        """
        full = set((await client.get(URL)).json())
        first = set((await client.get(f"{URL}?sections=first")).json())
        rest = set((await client.get(f"{URL}?sections=rest")).json())
        assert full == first | rest, {
            "dropped": sorted(full - (first | rest)),
            "invented": sorted((first | rest) - full),
        }

    async def test_the_full_payload_carries_both_link_channels(self, client):
        """`event_links` is the one key both halves write.

        Red against a plain overwrite: whichever fragment merged second would
        take the whole key, and the page would lose either its day-card links or
        its finished-list links depending on which order the caches expired in.
        """
        links = (await client.get(URL)).json()["event_links"]
        # `slate_linked` (ux/1048) is the eighth: it rides `first`, alongside the
        # rows it counts, while the `by_espn` block rides `rest`. The default
        # payload must still carry all eight or a caller that never asked for a
        # split loses a channel to it.
        for key in ("by_event", "by_matchup", "linked", "unresolved",
                    "by_espn", "espn_linked", "espn_unresolved", "slate_linked"):
            assert key in links, key


class TestWhatEachHalfLOADS:
    """Bytes are half the ship; the cold build is the other half.

    A split that still loaded every price would move the 1.3 s response to the
    second request and call it a win. These pin the loads, which is the only
    place the saving actually is.
    """

    @staticmethod
    def _spy_prices(monkeypatch) -> list[list[int]]:
        seen: list[list[int]] = []

        async def _load(session, outcome_ids, *, now=None):
            seen.append(list(outcome_ids))
            return {}

        monkeypatch.setattr(tournaments, "_load_prices", _load)
        return seen

    async def test_first_never_prices_the_grid(self, client, monkeypatch):
        seen = self._spy_prices(monkeypatch)
        await client.get(f"{URL}?sections=first")
        assert seen, "the build never loaded a price at all"
        loaded = set(seen[0])
        ids = _register_ids()
        assert not (loaded & ids["reach"]), (
            f"{len(loaded & ids['reach'])} of the grid's reach ids were priced "
            "for a request that does not serve the grid"
        )
        # And it still prices everything the first screen renders.
        assert ids["slate"] <= loaded
        assert ids["board"] <= loaded

    async def test_rest_prices_the_grid_and_the_finished_list(self, client, monkeypatch):
        seen = self._spy_prices(monkeypatch)
        await client.get(f"{URL}?sections=rest")
        loaded = set(seen[0])
        ids = _register_ids()
        assert ids["reach"] <= loaded
        # The board's own rows key the grid, and a decided result prints the
        # opening probability off its matchup. Both are second-request costs
        # too — the split is not free and the guard says so out loud.
        assert ids["board"] <= loaded
        assert ids["slate"] <= loaded

    async def test_first_asks_for_every_price_in_ONE_statement(self, client, monkeypatch):
        """The bound that was here before the split stays: one `IN (...)`, not
        one query per section."""
        seen = self._spy_prices(monkeypatch)
        await client.get(f"{URL}?sections=first")
        assert len(seen) == 1, f"{len(seen)} price loads for one request"

    async def test_rest_draws_no_trend_line_so_it_runs_no_series_query(
        self, client, monkeypatch
    ):
        """`build_playoff_grid` reads a board row's identity, rank and blended
        number — never its `trend`. Pinned in both directions: the grid builder
        must not learn to read one, and this request must not load one."""
        assert "trend" not in inspect.getsource(
            __import__("app.utils.tournament_grid", fromlist=["build_playoff_grid"])
            .build_playoff_grid
        )

        calls: list[int] = []

        async def _load_series(session, outcome_ids, *, now):
            calls.append(len(outcome_ids))
            return {}

        monkeypatch.setattr(tournaments, "_load_series", _load_series)
        await client.get(f"{URL}?sections=rest")
        assert calls == [], f"a rest-only build ran {len(calls)} series queries"

    async def test_first_still_loads_the_trend_the_chart_draws(
        self, client, monkeypatch
    ):
        """The control for the test above — without it, deleting the series
        query entirely would pass."""
        calls: list[int] = []

        async def _load_series(session, outcome_ids, *, now):
            calls.append(len(outcome_ids))
            return {}

        monkeypatch.setattr(tournaments, "_load_series", _load_series)
        await client.get(f"{URL}?sections=first")
        assert len(calls) == 1 and calls[0] > 0

    async def test_rest_does_not_resolve_the_day_cards_events(
        self, client, monkeypatch
    ):
        """`resolve_matchup_events` addresses slate rows. A request that serves
        no slate must not pay for it."""
        called: list[int] = []

        async def _resolve(db, register):
            called.append(1)
            return {"by_event": {}, "by_matchup": {}, "reason_counts": {}}

        monkeypatch.setattr(tournaments, "resolve_matchup_events", _resolve)
        await client.get(f"{URL}?sections=rest")
        assert called == []
        await client.get(f"{URL}?sections=first")
        assert called == [1], "the first screen stopped addressing its own rows"


class TestTodaysRowsStillOpenAfterTheSplit:
    """🔴 THE DEFECT THIS SPLIT CAN INTRODUCE, AND THE ONLY ONE THAT IS SILENT.

    ux/1048 gave today's card its `events` row: the slate walks the order of
    play, so a second-round match reaches the card the ceremony register could
    never hold, and before ux/1048 every one of those rows carried
    `event_id: None` — 40 rows, 8 in play, 0 linked on the live scoreboard. The
    reader was shown the live match they were watching and then refused the tap.

    ux/1048 resolved that channel inside `_hub_payload`, next to the FINISHED
    list, because before this ship there was only one body. This ship puts the
    slate in `first` and the finished list in `rest`. **Leaving the resolve where
    ux/1048 left it would mean a `sections=first` request — the phone request
    this entire ship exists to create — never stamped today's rows**, and ux/1048
    would be dead for exactly the readers it was shipped for.

    Nothing else catches it. The rows still render, the payload still validates,
    every byte-count and load-bound guard above still passes, and the page just
    quietly stops opening. These pin the wiring instead.
    """

    @staticmethod
    def _capture(monkeypatch):
        """Record the id list the ESPN channel is asked about, per request."""
        seen: list[list] = []

        async def _resolve(db, comp_ids, sport_keys):
            seen.append(list(comp_ids))
            return {"by_espn": {}, "unresolved": {}, "reason_counts": {}}

        monkeypatch.setattr(
            tournaments, "resolve_espn_competition_events", _resolve
        )
        return seen

    async def test_the_first_screen_stamps_todays_rows(self, client, monkeypatch):
        """RED if the stamping stays inside the `rest` half."""
        stamped: list = []

        def _apply(slate, by_espn=None):
            stamped.append(slate)
            return 0

        self._capture(monkeypatch)
        monkeypatch.setattr(tournaments, "apply_espn_event_links", _apply)

        body = (await client.get(f"{URL}?sections=first")).json()
        assert len(stamped) == 1, (
            "the first screen did not stamp its slate — today's rows ship with "
            "event_id: None and the card does not open (ux/1048)"
        )
        # The object stamped must be the object served. Stamping a copy is the
        # same bug wearing a passing test.
        assert stamped[0] is not None
        assert stamped[0].get("count") == body["slate"]["count"]

    async def test_the_first_screen_asks_about_the_cards_own_ids(
        self, client, monkeypatch
    ):
        """The slate's competition ids reach the resolver on a first-only build.

        Sentinel-driven rather than fixture-driven: the mock database serves an
        empty slate, so asserting on real ids here would pass whether the wiring
        existed or not.
        """
        seen = self._capture(monkeypatch)
        monkeypatch.setattr(
            tournaments, "slate_competition_ids", lambda slate: ["SLATE-SENTINEL"]
        )

        await client.get(f"{URL}?sections=first")
        assert seen and "SLATE-SENTINEL" in seen[0], (
            "the day's card was not in the population the ESPN channel resolved"
        )

    async def test_a_rest_only_request_does_not_pay_for_the_card(
        self, client, monkeypatch
    ):
        """The other direction of the same bound — `rest` serves no slate."""
        seen = self._capture(monkeypatch)
        monkeypatch.setattr(
            tournaments, "slate_competition_ids", lambda slate: ["SLATE-SENTINEL"]
        )

        await client.get(f"{URL}?sections=rest")
        assert seen, "the finished list stopped resolving its own links"
        assert "SLATE-SENTINEL" not in seen[0]

    async def test_the_full_payload_resolves_the_channel_exactly_once(
        self, client, monkeypatch
    ):
        """ux/1048's rule survives the split: one id list, not two calls.

        Two round trips would buy nothing but a second chance to disagree with
        the first about which event a fixture is — and the default request is the
        one every existing caller still makes.
        """
        seen = self._capture(monkeypatch)
        await client.get(URL)
        assert len(seen) == 1, f"{len(seen)} resolver calls on one request"

    async def test_each_half_reports_the_links_it_carries(self, client):
        """`slate_linked` rides `first`; the `by_espn` block rides `rest`.

        Disjoint on purpose — that is what makes `_merge_fragment`'s shallow
        merge of `event_links` correct rather than lossy.
        """
        first = (await client.get(f"{URL}?sections=first")).json()["event_links"]
        rest = (await client.get(f"{URL}?sections=rest")).json()["event_links"]
        assert "slate_linked" in first
        assert "by_espn" in rest and "espn_linked" in rest
        assert set(first) & set(rest) == set(), (
            f"the two halves both claim {sorted(set(first) & set(rest))} — a "
            "shallow merge will drop one of them"
        )


class TestTheParameterRefusesRatherThanShrugs:
    async def test_an_unknown_section_is_a_400(self, client):
        """Not a silent full payload. A typo'd section that served everything
        would measure as a working split while shipping none of the saving —
        gotcha #53, a response shape that cannot say "I do not have that"."""
        for value in ("grids", "everything", "", "first,grids"):
            resp = await client.get(f"{URL}?sections={value}")
            assert resp.status_code == 400, (value, resp.status_code)

    async def test_both_named_explicitly_is_the_full_payload(self, client):
        body = (await client.get(f"{URL}?sections=first,rest")).json()
        assert "slate" in body and "grids" in body

    async def test_order_does_not_change_the_answer(self, client):
        a = set((await client.get(f"{URL}?sections=first,rest")).json())
        b = set((await client.get(f"{URL}?sections=rest,first")).json())
        assert a == b

    async def test_an_unregistered_slug_is_still_a_404_whatever_it_asks_for(
        self, client
    ):
        """#1793's floor is not weakened by a new parameter."""
        assert (await client.get("/api/tournaments/wimbledon?sections=first")).status_code == 404


class TestTheCacheIsPerGroup:
    async def test_a_first_request_does_not_warm_the_rest(self, client, memory_cache):
        await client.get(f"{URL}?sections=first")
        assert set(memory_cache) == {f"{SLUG}:{tournaments.SECTION_FIRST}"}

    async def test_a_full_request_after_a_first_request_is_still_whole(
        self, client, memory_cache
    ):
        """The half-cache case, which is the one a real reader creates every
        time: the page asks for `first`, then something asks for everything.
        A shell that returned the warm fragment and stopped would serve a
        gridless payload to the native app."""
        await client.get(f"{URL}?sections=first")
        body = (await client.get(URL)).json()
        assert "grids" in body and "results" in body and "slate" in body
        assert set(memory_cache) == {
            f"{SLUG}:{tournaments.SECTION_FIRST}",
            f"{SLUG}:{tournaments.SECTION_REST}",
        }

    async def test_a_warm_first_fragment_keeps_its_own_stamp(
        self, client, memory_cache
    ):
        """Both fragments carry `generated_at`. The reader's numbers are in
        `first`, so `first`'s stamp is the one that survives the merge — never a
        fresher one describing a section below the fold."""
        await client.get(f"{URL}?sections=first")
        warm = memory_cache[f"{SLUG}:{tournaments.SECTION_FIRST}"]["generated_at"]
        body = (await client.get(URL)).json()
        assert body["generated_at"] == warm

    async def test_by_event_still_gets_the_grid(self):
        """`/by-event/{id}` slices `payload["grids"]` for its advancement strip.
        It never passes `groups`, so the default must stay both — asserted on
        the signature, because the failure is a default value nobody looks at."""
        default = inspect.signature(tournaments._hub_payload).parameters["groups"].default
        assert default == tournaments.SECTION_GROUPS
        assert "grids" in inspect.getsource(tournaments.get_event_tournament)
