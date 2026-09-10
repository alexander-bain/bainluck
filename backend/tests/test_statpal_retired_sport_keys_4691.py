"""#4691 — a sport key StatPal cannot serve is retired from the map, with its reason.

`golf_pga` sat in `STATPAL_SPORT_MAPPING` claiming StatPal coverage for PGA golf.
It had no `sports` row and never has, so all three StatPal consumers dropped it
before any fetch: `sync_statpal_schedules` and `sync_statpal_standings` resolve
OUR key to a row and `continue` on `sport_not_found`, and `sync_statpal_live_scores`
reaches its sports by JOINING `Sport` to a live `Event`, which needs the same row.

That last one is why the config's old wording — *"`golf_pga` and the seven soccer
leagues are livescore-only ON PURPOSE"* — was not a small inaccuracy. Golf was not
livescore-only. It was unreachable on every path at once, through doors that were
all shut for one reason.

**This is not the rule "every mapped key has a `sports` row."** That is not an
invariant and a test for it would be wrong: `sports` rows are minted by ingest on
first event, so a key legitimately has no row until something creates one under it.
Golf differs in kind — `schedule_sentinel` had already declared PGA under
`declared NOT COVERED`, *field event — no per-game schedule to reconcile* — because
StatPal's fixture shape is two-sided (`_fixture_match_key(home, away)`) and a golf
tournament is a field. A `sports` row would not have fixed it.

So the guard here is between the two records the repo now keeps, not against
production data: the map and the retirement list must stay disjoint, and a retired
key's reason must stay the sentinel's own.
"""

import pytest

from app.utils.sport_keys import RETIRED_STATPAL_SPORT_KEYS, STATPAL_SPORT_MAPPING


class TestGolfIsRetiredNotMapped:
    def test_golf_pga_is_not_mapped_and_is_recorded_as_retired(self):
        """The regression itself, asserted in both directions.

        Absence alone would also pass if someone deleted the line and wrote
        nothing down, which is the outcome this ship exists to avoid — the next
        person to notice golf missing re-adds the key. The reason has to be
        findable from the key.
        """
        assert "golf_pga" not in STATPAL_SPORT_MAPPING
        assert "golf_pga" in RETIRED_STATPAL_SPORT_KEYS
        assert RETIRED_STATPAL_SPORT_KEYS["golf_pga"].strip()

    def test_the_two_records_are_disjoint(self):
        """A key cannot be both mapped and retired.

        The failure this catches is a re-add: someone maps `golf_pga` again
        without reading the note, and the map and the record now disagree about
        whether we ask StatPal for golf.
        """
        both = sorted(set(STATPAL_SPORT_MAPPING) & set(RETIRED_STATPAL_SPORT_KEYS))
        assert both == [], both

    def test_every_retirement_carries_a_reason(self):
        """A retirement without a reason is a deletion wearing a record's clothes."""
        blank = sorted(k for k, why in RETIRED_STATPAL_SPORT_KEYS.items() if not why.strip())
        assert blank == [], blank


class TestTheRecordsDoNotDrift:
    def test_a_retired_key_carries_the_sentinels_own_reason(self):
        """The two places that say why golf is not reconciled must say the same thing.

        `schedule_sentinel.SCHEDULE_LEAGUES` held the disposition first. Copying
        the sentence into `sport_keys` creates a second copy that can drift, so
        it is pinned to the original by equality rather than left to prose.

        Only keys the sentinel actually names are checked: retiring a key the
        sentinel says nothing about is allowed, and must not fail here.
        """
        from app.tasks.schedule_sentinel import SCHEDULE_LEAGUES

        sentinel_reason: dict[str, str] = {}
        for spec in SCHEDULE_LEAGUES:
            if spec.uncovered_reason:
                for key in spec.sport_keys:
                    sentinel_reason[key] = spec.uncovered_reason

        checked = 0
        for key, why in RETIRED_STATPAL_SPORT_KEYS.items():
            if key in sentinel_reason:
                assert why == sentinel_reason[key], key
                checked += 1

        # The eligible denominator. Without this the loop passes vacuously the
        # day the sentinel stops naming PGA, which is exactly the drift it is
        # here to catch.
        assert checked >= 1
        assert sentinel_reason.get("golf_pga") == "field event — no per-game schedule to reconcile"

    def test_the_map_still_holds_the_sports_that_do_work(self):
        """Control arm: the retirement removed one key, not the map.

        A mutant that empties `STATPAL_SPORT_MAPPING` satisfies every assertion
        above — golf would be absent from it too — and takes NFL, NBA, MLB and
        NHL off StatPal entirely.
        """
        for key in ("americanfootball_nfl", "basketball_nba", "baseball_mlb", "icehockey_nhl"):
            assert STATPAL_SPORT_MAPPING[key]

        assert len(STATPAL_SPORT_MAPPING) == 13
        assert not any(k.startswith("golf") for k in STATPAL_SPORT_MAPPING)


class TestAskingForGolfIsRefusedByName:
    @pytest.mark.asyncio
    async def test_the_schedule_sync_refuses_golf_before_the_network(self, monkeypatch):
        """`_sync_statpal_schedules("golf_pga")` now names the refusal.

        The three readings this call has given for golf, in order: `complete`
        before #2907 (a pass that asked nobody, wearing a healthy pass's word),
        `no_work` after it (honest, but silent about why), and now a refusal
        that names the key and the map it is missing from. Each step says more
        than the last, and the last one is actionable without a probe.

        The second assertion is the one with teeth: the refusal happens before a
        client is constructed, so a retired key costs no network call.
        """
        import app.services.statpal_api as statpal_api
        from app.tasks.statpal_sync import _sync_statpal_schedules

        monkeypatch.setattr(statpal_api, "is_available", lambda: True)

        class _Service:  # pragma: no cover - must never be constructed
            def __init__(self, *a, **k):
                raise AssertionError(
                    "a retired sport key must be refused before the client is built"
                )

        monkeypatch.setattr(statpal_api, "StatPalAPIService", _Service)

        result = await _sync_statpal_schedules("golf_pga")

        assert result["terminal"] == "skipped"
        assert result["skipped"] is True
        assert "golf_pga" in result["reason"]
        assert "STATPAL_SPORT_MAPPING" in result["reason"]

    @pytest.mark.asyncio
    async def test_a_mapped_sport_is_not_refused_by_the_same_gate(self, monkeypatch):
        """The over-fire control.

        Widening the refusal to every key would pass the test above and silently
        stop all four beat sports. This one proves the gate is keyed on the map
        and not on the call: NFL gets past it and reaches the client.

        Stopped AT the client rather than run through: construction is the first
        thing past the gate and the last thing before the database, so raising
        here proves the gate opened without the test needing a session. A plain
        recording double would instead run the whole task and fail on Postgres,
        which would look like this assertion failing.
        """
        import app.services.statpal_api as statpal_api
        from app.tasks.statpal_sync import _sync_statpal_schedules

        monkeypatch.setattr(statpal_api, "is_available", lambda: True)

        class _PastTheGate(Exception):
            pass

        class _Service:
            def __init__(self, *a, **k):
                raise _PastTheGate()

        monkeypatch.setattr(statpal_api, "StatPalAPIService", _Service)

        with pytest.raises(_PastTheGate):
            await _sync_statpal_schedules("americanfootball_nfl")
