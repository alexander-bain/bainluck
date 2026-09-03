"""No writer may hand back an authority id another row already wears (#2693, CERT-784).

## The finding this exists to close

CERT-784 blocked step 2 for a reason the repair itself could not see:

> the repair unstamps 54 same-game twins, while scheduled `backfill_espn_ids`
> runs every six hours and directly reassigns `event.espn_id` to
> completed/closed NULL rows without a holder check, so those twins can
> reacquire the contested id.

That is fatal to the whole ship, not a rough edge. The step-2 repair clears
`espn_id` on 225 rows; six hours later the backfill selects exactly those rows
(`espn_id IS NULL`, completed/closed), name-matches the same ESPN fixture, and
stamps the contested id straight back. The unique index becomes uninstallable
again and `event_links.by_espn` correctly drops the Finished link a second time.

**A repair whose population an active writer refills is not a repair.** So the
writers come first and the data write comes after — this file is the proof that
ordering is real.

## What is asserted

1. **STRUCTURAL** — a census of every place that stamps a non-NULL
   `Event.espn_id`, asserted to be exactly the set that is holder-checked, in
   both directions. A new writer added tomorrow fails here rather than being
   discovered by the next cert.
2. **BEHAVIOURAL** — each converted writer really refuses. A structural claim
   about a call graph is not a claim about behaviour, and #2017's own docstring
   records an allowlist entry that had been inert for its whole life because
   nobody checked the second thing.
3. **THE ROUND TRIP** — the exact sequence the BLOCK describes: repair clears
   the twin, writer runs, twin does NOT reacquire. Red-first: with the guard
   bypassed, the twin gets it back.
"""

from __future__ import annotations

import asyncio

import pytest

from app.services.event_registry import EventClaim, _attach_claim
from app.utils.espn_id_stamp import REFUSED, SKIPPED, STAMPED, stamp_espn_id_if_unheld


class _Event:
    """The two attributes both writers touch."""

    def __init__(self, event_id=None, espn_id=None):
        self.id = event_id
        self.espn_id = espn_id
        self.external_id = None
        self.statpal_fixture_id = None


class _HolderSession:
    """A session whose `events` table is the dict handed to it."""

    def __init__(self, holders: dict[str, int]):
        self._holders = holders
        self.queries = 0

    async def execute(self, statement):
        self.queries += 1
        # The helper's statement is `SELECT events.id WHERE espn_id = :x [AND
        # id != :y] LIMIT 1`. Reading the bound values keeps this double honest
        # about WHICH id was asked for.
        params = statement.compile().params
        wanted = next(
            (v for k, v in params.items() if isinstance(v, str)), None
        )
        excluded = next(
            (v for k, v in params.items() if isinstance(v, int)), None
        )
        holder = self._holders.get(str(wanted))
        rows = [holder] if holder is not None and holder != excluded else []
        return _Scalars(rows)


class _Scalars:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


# ---------------------------------------------------------------------------
# 1. STRUCTURAL — the census, exhaustive in both directions.
# ---------------------------------------------------------------------------


#: Every site that writes a NON-NULL value into `Event.espn_id`, and how each
#: one answers "does another row already hold this?". Asserted exhaustive:
#: a stamp site missing from here fails, and an entry matching no real site
#: fails too, so the map cannot rot into decoration.
HOLDER_CHECKED_STAMPERS = {
    ("app/utils/espn_id_stamp.py", "stamp_espn_id_if_unheld"):
        "The helper itself — it IS the holder check (#2017).",
    ("app/services/event_registry.py", "_attach_claim"):
        "REQUIRED `espn_id_is_held` argument, computed by both production call "
        "sites from `_espn_claim_id_is_held`. Required rather than defaulted "
        "because a permissive default is a guard the next caller forgets.",
    ("app/utils/espn_helpers.py", "write_espn_win_probability"):
        "Inline `espn_id_holder`, because this writer builds a Core UPDATE "
        "payload (gotcha #4) rather than assigning to an ORM object. The CHECK "
        "is imported from the helper, not re-implemented.",
}

#: Sites the census sees that are NOT stamps of `Event.espn_id` — a different
#: column, or a CLEAR. Listed so the exhaustiveness assertion above has a
#: complete partition and cannot be satisfied by a detector that went blind.
NOT_AN_EVENT_STAMP = {
    ("app/routes/admin_providers.py", "sync_espn_teams"): "Team.espn_id",
    ("app/tasks/espn_sync.py", "_backfill_team_logos"): "Team.espn_id",
    ("app/tasks/espn_sync.py", "_cleanup_bad_espn_matches._clear_espn_data"):
        "Team.espn_id, and a CLEAR",
    ("app/utils/espn_helpers.py", "upsert_team"): "Team.espn_id",
    ("app/routes/source_intelligence.py", "cleanup_oscillation"):
        "CLEAR — writing NULL manufactures no identity",
    ("app/tasks/repair_authority_id_collisions.py", "<module>"):
        "CLEAR — the step-2 repair itself",
    ("app/tasks/repair_event_espn_id.py", "<module>"):
        "The attended correction rail; its compare IS its WHERE clause",
}


def _census():
    from tests.test_espn_id_authorization_2049 import (
        _real_app_root,
        census_espn_id_writes,
    )

    return census_espn_id_writes(_real_app_root())


class TestEveryEventStamperIsHolderChecked:
    def test_the_census_is_not_vacuous(self):
        writes = _census()
        assert len(writes) >= 8, (
            f"the census found only {len(writes)} espn_id writes — it has gone "
            "vacuous, and a green board here would mean nothing"
        )

    def test_every_site_is_classified_and_no_classification_is_stale(self):
        seen = {(w.key[0], w.key[1]) for w in _census()}
        classified = set(HOLDER_CHECKED_STAMPERS) | set(NOT_AN_EVENT_STAMP)

        unclassified = sorted(seen - classified)
        assert not unclassified, (
            "a new espn_id write site that no one has said is collision-safe. "
            "Either route it through `stamp_espn_id_if_unheld`, or add it here "
            "with the holder check it performs:\n  " + "\n  ".join(map(str, unclassified))
        )

        stale = sorted(classified - seen)
        assert not stale, (
            "entries matching no real write site — delete them or fix the key. "
            "An allowlist nobody can trust is one nobody reads:\n  "
            + "\n  ".join(map(str, stale))
        )

    def test_the_two_scheduled_refillers_no_longer_stamp_raw(self):
        """`backfill_espn_ids` and `sync_espn_live_events` are the writers
        CERT-784 named. Both now go through the helper, so they vanish from the
        census entirely — that absence IS the fix, and asserting it here is what
        stops a later edit quietly restoring the raw assignment."""
        # Suffix, not equality: the task is `_backfill_espn_ids` and the admin
        # route is `backfill_espn_ids`, and an exact-match arm silently covered
        # only one of them — which a red-check caught.
        raw = {
            (w.key[0], w.key[1]) for w in _census()
            if w.key[1].lstrip("_") in ("backfill_espn_ids", "sync_espn_live_events")
        }
        assert raw == set(), f"a raw espn_id stamp is back in a scheduled writer: {raw}"


# ---------------------------------------------------------------------------
# 2. BEHAVIOURAL — each converted writer really refuses.
# ---------------------------------------------------------------------------


class TestTheHelperRefuses:
    def test_it_stamps_when_nobody_holds_the_id(self):
        event = _Event(event_id=1)
        session = _HolderSession({})
        verdict, holder = asyncio.run(
            stamp_espn_id_if_unheld(session, event, "401816574", context="t")
        )
        assert (verdict, holder) == (STAMPED, None)
        assert event.espn_id == "401816574"

    def test_it_refuses_when_another_row_holds_the_id(self):
        event = _Event(event_id=1)
        session = _HolderSession({"401816574": 999})
        verdict, holder = asyncio.run(
            stamp_espn_id_if_unheld(session, event, "401816574", context="t")
        )
        assert (verdict, holder) == (REFUSED, 999)
        assert event.espn_id is None, "the row must keep its NULL, not a contradicted id"

    def test_the_row_itself_is_excluded_so_a_re_stamp_is_not_a_collision(self):
        event = _Event(event_id=7, espn_id=None)
        session = _HolderSession({"401816574": 7})
        verdict, _ = asyncio.run(
            stamp_espn_id_if_unheld(session, event, "401816574", context="t")
        )
        assert verdict == STAMPED

    def test_the_in_pass_set_catches_a_twin_inside_one_transaction(self):
        """Two halves of a twin pair are stamped in the SAME uncommitted
        transaction, so only the in-pass set sees the first one. This is why
        `backfill_espn_ids` groups by (sport, date) and must pass `claimed`."""
        claimed: set = set()
        first, second = _Event(event_id=1), _Event(event_id=2)
        session = _HolderSession({})
        v1, _ = asyncio.run(stamp_espn_id_if_unheld(
            session, first, "401847094", context="t", claimed=claimed))
        v2, _ = asyncio.run(stamp_espn_id_if_unheld(
            session, second, "401847094", context="t", claimed=claimed))
        assert (v1, v2) == (STAMPED, REFUSED)
        assert second.espn_id is None


class TestTheRegistryClaimRefuses:
    def test_a_held_id_is_not_stamped_on_an_existing_row(self):
        event = _Event(event_id=1)
        attached = _attach_claim(
            event, EventClaim("espn", "401816574"), espn_id_is_held=True
        )
        assert attached is False
        assert event.espn_id is None

    def test_an_unheld_id_still_attaches(self):
        event = _Event(event_id=1)
        assert _attach_claim(
            event, EventClaim("espn", "401816574"), espn_id_is_held=False
        ) is True
        assert event.espn_id == "401816574"

    def test_the_CREATE_path_is_covered_too(self):
        """#2017: 'the duplicate is BORN carrying the collision'. A brand-new
        row has no id to exclude and reaches the same arm."""
        fresh = _Event(event_id=None)
        assert _attach_claim(
            fresh, EventClaim("espn", "401816574"), espn_id_is_held=True
        ) is False
        assert fresh.espn_id is None

    def test_the_argument_is_REQUIRED_so_a_caller_cannot_forget_it(self):
        import inspect

        param = inspect.signature(_attach_claim).parameters["espn_id_is_held"]
        assert param.default is inspect.Parameter.empty, (
            "a permissive default is a guard the next caller forgets, and "
            "forgetting it re-opens #2693"
        )
        assert param.kind is inspect.Parameter.KEYWORD_ONLY

    def test_it_does_not_interfere_with_the_other_providers(self):
        event = _Event(event_id=1)
        assert _attach_claim(
            event, EventClaim("odds_api", "abc"), espn_id_is_held=True
        ) is True
        assert event.external_id == "abc"

    def test_the_holder_probe_ignores_non_espn_claims_entirely(self):
        from app.services.event_registry import _espn_claim_id_is_held

        session = _HolderSession({"abc": 999})
        held = asyncio.run(
            _espn_claim_id_is_held(session, EventClaim("odds_api", "abc"), _Event(1))
        )
        assert held is False
        assert session.queries == 0, "a non-ESPN claim must not cost a query"


# ---------------------------------------------------------------------------
# 3. THE ROUND TRIP — CERT-784's sequence, reproduced.
# ---------------------------------------------------------------------------


class TestTheRepairSurvivesTheNextWriterPass:
    """`401847094` — ESPN's Alabama v Ole Miss, worn by two of our rows.

    Step 2 keeps the id on `14683176` and clears it from `14707075`. Six hours
    later a writer selects `14707075` (now `espn_id IS NULL`), name-matches the
    same ESPN fixture, and offers the id back.
    """

    KEEPER, TWIN, CONTESTED = 14683176, 14707075, "401847094"

    def test_the_cleared_twin_does_NOT_reacquire_the_contested_id(self):
        twin = _Event(event_id=self.TWIN, espn_id=None)  # post-repair state
        session = _HolderSession({self.CONTESTED: self.KEEPER})

        verdict, holder = asyncio.run(stamp_espn_id_if_unheld(
            session, twin, self.CONTESTED, context="espn_id backfill"))

        assert verdict == REFUSED
        assert holder == self.KEEPER
        assert twin.espn_id is None, (
            "the twin took the contested id back — the repair is undone and the "
            "unique index is uninstallable again (CERT-784)"
        )

    def test_RED_FIRST_without_the_guard_the_twin_takes_it_straight_back(self):
        """The shipped defect reproduced, not remembered. This is what the
        scheduled writer did before this change: ask only whether THIS row has
        an id, and stamp."""
        twin = _Event(event_id=self.TWIN, espn_id=None)
        if not twin.espn_id:                       # the old guard, in full
            twin.espn_id = self.CONTESTED
        assert twin.espn_id == self.CONTESTED

    def test_the_keeper_is_untouched_by_the_refusal(self):
        """A refusal must cost the twin its id and nothing else — the keeper is
        not re-examined, re-stamped or cleared."""
        keeper = _Event(event_id=self.KEEPER, espn_id=self.CONTESTED)
        session = _HolderSession({self.CONTESTED: self.KEEPER})
        verdict, _ = asyncio.run(stamp_espn_id_if_unheld(
            session, keeper, self.CONTESTED, context="espn_id backfill"))
        assert verdict == SKIPPED
        assert keeper.espn_id == self.CONTESTED

    def test_the_registry_arm_of_the_same_round_trip_also_holds(self):
        twin = _Event(event_id=self.TWIN, espn_id=None)
        attached = _attach_claim(
            twin, EventClaim("espn", self.CONTESTED), espn_id_is_held=True
        )
        assert attached is False and twin.espn_id is None
