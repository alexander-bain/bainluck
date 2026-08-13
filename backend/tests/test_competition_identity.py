"""UX-P065 (#1744 step 2a) — the competition identity register.

Two kinds of test live here and they are not interchangeable:

* **Config invariants** run against the REAL `majors_calendar.yaml`. They are the
  reason a new edition cannot be added without an assigned parent, and they fail
  by NAME so the message is the fix.
* **Behaviour** runs against temp YAML written per-test. That matters more than
  usual here: an assertion written against the twenty-one rows that exist today
  would pass for a resolver that inferred the parent from the slug text, which is
  precisely the implementation this module exists to refuse (gotcha #121 — a test
  whose oracle moves with the implementation cannot detect the implementation
  changing). So the doctrine gets a mutation test AND a source-inspection test.

Clocks are frozen constants, never `now()`-relative (gotcha #44): the calendar
carries real dates of its own, so any relative anchor would be picking a date to
start failing on.
"""

from __future__ import annotations

import inspect
import json
import re
from datetime import datetime, timezone

import pytest

from app.utils import competition_identity as ci

# Frozen, deliberately: between the 2026 and 2027 editions of nearly everything.
NOW = datetime(2026, 8, 12, 17, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Config invariants — against the real file
# ---------------------------------------------------------------------------


def test_every_edition_assigns_a_competition_that_exists():
    from app.utils.majors_calendar import load_calendar

    known = {c["slug"] for c in ci.load_competitions()}
    assert known, "the competition register is empty — did the YAML key get renamed?"
    orphans = [
        (e.get("slug"), e.get("competition"))
        for e in load_calendar()
        if str(e.get("competition") or "") not in known
    ]
    assert not orphans, (
        "every majors_calendar row must ASSIGN a competition that exists in the "
        f"register (assigned, never inferred). Offenders: {orphans}"
    )


def test_every_competition_has_at_least_one_edition():
    barren = [c["slug"] for c in ci.load_competitions() if not ci.editions_of(c["slug"])]
    assert not barren, f"register rows with no edition in the calendar: {barren}"


def test_slugs_and_aliases_are_globally_unique_and_disjoint():
    rows = ci.load_competitions()
    slugs = [c["slug"] for c in rows]
    assert len(slugs) == len(set(slugs)), "duplicate competition slug"
    seen: dict[str, str] = {}
    for row in rows:
        for alias in row.get("aliases") or []:
            assert alias not in slugs, f"alias {alias!r} collides with a slug"
            assert alias not in seen, (
                f"alias {alias!r} claimed by both {seen[alias]!r} and {row['slug']!r} — "
                "an ambiguous alias resolves by accident of ordering"
            )
            seen[alias] = row["slug"]


def test_the_masters_resolves_to_its_2027_edition():
    """The queue's payoff case, on the real config."""
    block = ci.competition_block("event:golf:the-masters", NOW)
    assert block is not None
    assert block["slug"] == "the-masters"
    assert block["next_edition"]["start"] == "2027-04-08"
    assert block["next_edition"]["end"] == "2027-04-11"


def test_block_carries_absolute_dates_and_never_a_countdown():
    """The envelope is mirrored for 24h; a baked countdown would be stale by design."""
    block = ci.competition_block("event:golf:the-masters", NOW)
    flat = str(block)
    assert "days" not in flat and "countdown" not in flat
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", block["next_edition"]["start"])


# ---------------------------------------------------------------------------
# The doctrine: ASSIGNED, never inferred
# ---------------------------------------------------------------------------

_YAML = """
majors:
  - name: "The Masters 2027"
    slug: masters-2027
    competition: {parent}
    concept_key: "event:golf:masters-2027"
    domain: golf
    start: 2027-04-08
    end: 2027-04-11
    archetype: winner_field
    marquee: true
  - name: "Some Other Thing 2026"
    slug: other-2026
    competition: sausage-festival
    concept_key: "event:food:other-2026"
    domain: food
    start: 2026-05-01
    end: 2026-05-02
    archetype: single_event
    marquee: false

competitions:
  - slug: the-masters
    name: "The Masters"
    domain: golf
    archetype: winner_field
    aliases: ["augusta"]
    standing_concept_key: "event:golf:the-masters"
  - slug: sausage-festival
    name: "The Sausage Festival"
    domain: food
    archetype: single_event
    aliases: []
    standing_concept_key: null
"""


def _write(tmp_path, parent: str = "the-masters"):
    p = tmp_path / "cal.yaml"
    p.write_text(_YAML.format(parent=parent), encoding="utf-8")
    return p


def test_reassigning_the_parent_moves_the_resolution(tmp_path):
    """The mutation test (gotcha #121).

    `masters-2027` LOOKS like it belongs to `the-masters` — and a resolver that
    stripped the year suffix would agree, and would pass every other test in this
    file. Reassign the row to a competition it shares no letters with: a resolver
    reading the ASSIGNED field follows, and one inferring from the slug does not.
    """
    honest = _write(tmp_path, parent="the-masters")
    assert ci.competition_of("event:golf:masters-2027", honest)["slug"] == "the-masters"

    mutated = _write(tmp_path, parent="sausage-festival")
    moved = ci.competition_of("event:golf:masters-2027", mutated)
    assert moved["slug"] == "sausage-festival", (
        "resolution did not follow the assigned parent — the module is inferring "
        "identity from the slug text, which is the exact defect it exists to remove"
    )
    assert "masters-2027" in [e["slug"] for e in ci.editions_of("sausage-festival", mutated)]
    assert ci.editions_of("the-masters", mutated) == []


def test_no_year_inference_anywhere_in_the_module():
    """Source inspection, because behaviour alone cannot police a doctrine.

    Twenty-one of twenty-one rows currently agree with what a `-(\\d{4})` strip
    would guess, so inference would be invisible in output today and wrong the
    first time a competition is renamed or an edition is numbered (super-bowl-61,
    wrestlemania-43) rather than dated.
    """
    src = inspect.getsource(ci)
    # Strip the module docstring — it necessarily *describes* the inference it
    # refuses, so leaving it in would make this test assert against its own prose.
    body = src.replace(ci.__doc__ or "", "")
    body = "\n".join(
        line for line in body.splitlines() if not line.lstrip().startswith("#")
    )
    for smell in (r"\d{4}", "[0-9]{4}", "rsplit(", "removesuffix(", "import re"):
        assert smell not in body, (
            f"{smell!r} appears in competition_identity — a parent must be READ "
            "from the assigned field, never derived from the shape of a slug"
        )


# ---------------------------------------------------------------------------
# Resolution behaviour
# ---------------------------------------------------------------------------


def test_resolves_by_slug_and_by_alias_but_never_fuzzily(tmp_path):
    cal = _write(tmp_path)
    assert ci.resolve_competition("the-masters", cal)["name"] == "The Masters"
    assert ci.resolve_competition("AUGUSTA", cal)["name"] == "The Masters"
    assert ci.resolve_competition("  augusta  ", cal)["name"] == "The Masters"
    # A near-miss must be None, not a best guess. The tennis adapter's tolerant
    # matching is why event:tennis:us-open-2026 served "Cincinnati Open" in
    # production on 2026-08-12; a register that guesses is worse than one that
    # admits it does not know.
    assert ci.resolve_competition("masters-2027", cal) is None
    assert ci.resolve_competition("the master", cal) is None
    assert ci.resolve_competition("", cal) is None


def test_standing_key_and_edition_key_reach_the_same_competition(tmp_path):
    cal = _write(tmp_path)
    by_standing = ci.competition_of("event:golf:the-masters", cal)
    by_edition = ci.competition_of("event:golf:masters-2027", cal)
    assert by_standing["slug"] == by_edition["slug"] == "the-masters"
    assert ci.competition_of("event:golf:not-a-thing", cal) is None
    assert ci.competition_of("", cal) is None


@pytest.mark.parametrize(
    "day,expect_next",
    [
        (datetime(2027, 4, 7, tzinfo=timezone.utc), True),  # day before start
        (datetime(2027, 4, 9, tzinfo=timezone.utc), True),  # mid-tournament
        (datetime(2027, 4, 11, 23, tzinfo=timezone.utc), True),  # the finish DAY
        (datetime(2027, 4, 12, tzinfo=timezone.utc), False),  # the day after
    ],
)
def test_next_edition_includes_the_finish_day(tmp_path, day, expect_next):
    """Inclusive of the end day, matching `marquee_pin_state` — an edition
    finishing today is the current edition, not a past one."""
    cal = _write(tmp_path)
    nxt = ci.next_edition("the-masters", day, cal)
    assert (nxt is not None) is expect_next
    last = ci.last_edition("the-masters", day, cal)
    assert (last is not None) is (not expect_next)


def test_block_is_none_when_the_key_maps_to_nothing(tmp_path):
    assert ci.competition_block("event:golf:unmapped", NOW, _write(tmp_path)) is None


def test_block_is_none_when_the_competition_has_no_edition_left(tmp_path):
    """Honest-empty (ruling 027): naming a competition with nothing to say about
    it is chrome. After its only edition passes, the strip disappears rather than
    announcing a competition that returns at an unknown time."""
    cal = _write(tmp_path)
    past = datetime(2030, 1, 1, tzinfo=timezone.utc)
    block = ci.competition_block("event:golf:the-masters", past, cal)
    assert block is not None  # last_edition still says something true
    assert block["next_edition"] is None
    assert block["last_edition"]["slug"] == "masters-2027"


# ---------------------------------------------------------------------------
# Purity / defensiveness — a bad config must never crash a page build
# ---------------------------------------------------------------------------


def test_missing_and_malformed_files_degrade_to_empty(tmp_path):
    missing = tmp_path / "nope.yaml"
    assert ci.load_competitions(missing) == []
    assert ci.resolve_competition("the-masters", missing) is None
    assert ci.competition_block("event:golf:the-masters", NOW, missing) is None

    junk = tmp_path / "junk.yaml"
    junk.write_text("competitions: not-a-list\nmajors: 7\n", encoding="utf-8")
    assert ci.load_competitions(junk) == []
    assert ci.editions_of("the-masters", junk) == []
    assert ci.competition_block("event:golf:the-masters", NOW, junk) is None


def test_rows_without_a_slug_are_dropped_not_crashed(tmp_path):
    p = tmp_path / "partial.yaml"
    p.write_text(
        "competitions:\n  - name: 'No Slug'\n  - slug: ok\n    name: 'OK'\n",
        encoding="utf-8",
    )
    assert [c["slug"] for c in ci.load_competitions(p)] == ["ok"]


# ---------------------------------------------------------------------------
# The envelope — tested through what a CONSUMER receives, not what the helper
# returned. Attaching in `build_and_cache` means the block also has to survive
# stripping, quality-taking and stamping, and only the stored payload proves it.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_stored_envelope_carries_the_competition_block():
    from unittest.mock import AsyncMock, patch

    from app.utils import event_concept_cache as cache_mod

    class _Rc:
        def __init__(self):
            self.store: dict[str, bytes] = {}

        def set(self, k, v, nx=False, ex=None):
            self.store[k] = v.encode() if isinstance(v, str) else v
            return True

        def setex(self, k, ttl, v):
            self.store[k] = v.encode() if isinstance(v, str) else v

        def delete(self, k):
            self.store.pop(k, None)

    class _Adapter:
        build_event = AsyncMock(return_value={"event": {"name": "The Masters"}})

    rc = _Rc()
    with patch.object(cache_mod, "compute_watermark", AsyncMock(return_value=None)):
        built = await cache_mod.build_and_cache(
            "event:golf:the-masters", db=None, rc=rc, adapter=_Adapter()
        )

    assert built["competition"]["slug"] == "the-masters"
    stored = json.loads(rc.store[cache_mod.cache_keys("event:golf:the-masters").primary])
    assert stored["competition"]["next_edition"]["start"] == "2027-04-08", (
        "the block reached the return value but not the STORED payload — every "
        "reader after the first TTL would see a page with no next edition"
    )


@pytest.mark.asyncio
async def test_an_unmapped_key_gets_no_competition_key_at_all():
    """Absent, not null: an empty block is chrome the client has to special-case.

    UX-P069 (Alex ruling 2026-08-12, item 2) — THE KEY IN THIS TEST WAS THE BUG.

    It read `event:mma:ufc-320`. There is no `mma` namespace; live cards are
    `event:ufc:<card>`. That made the assertion **unfalsifiable rather than merely
    wrong**: `mma` will never be mapped into the competition register, so
    "competition is absent" is true here by construction, forever, no matter what
    the register does. The test could not fail, which is indistinguishable from a
    test that passes.

    The same key shape was also written into UX-P065's owed production check, where
    it did real damage: `GET /api/event/event:mma:26aug15` returns **HTTP 404** with
    a `{"detail": ...}` body, and `"competition" not in body` is **True** of that
    body. An absence assertion against a nonexistent resource passes for the wrong
    reason. It read as a check nobody had got round to running; it was a check that
    could never have reported anything. See gotcha #127.

    So the key is now a REAL one — `event:ufc:26aug15` resolves in production (a
    33-child card, `330: Makhachev vs Garry`) and is legitimately unmapped today.
    That is what makes this assertion able to fail: if UFC cards are ever given a
    competition mapping, this test goes red and asks to be updated, which is
    precisely the service it was supposed to be providing all along.
    """
    from unittest.mock import AsyncMock, patch

    from app.utils import event_concept_cache as cache_mod
    from app.utils.competition_identity import competition_block

    real_but_unmapped = "event:ufc:26aug15"

    # The precondition, asserted rather than assumed: this key must be UNMAPPED for
    # the test below to be about anything. Without this line a typo'd namespace
    # silently restores the vacuous version.
    assert competition_block(real_but_unmapped, None) is None, (
        "precondition failed: this key is now MAPPED, so the assertion below would "
        "pass vacuously. Re-point it at a genuinely unmapped key."
    )

    class _Adapter:
        build_event = AsyncMock(return_value={"event": {"name": "330: Makhachev vs Garry"}})

    with patch.object(cache_mod, "compute_watermark", AsyncMock(return_value=None)):
        built = await cache_mod.build_and_cache(
            real_but_unmapped, db=None, rc=None, adapter=_Adapter()
        )
    assert "competition" not in built


@pytest.mark.asyncio
async def test_a_broken_register_cannot_fail_a_page_build():
    """Purity guarantee. The page is the product; the strip is a nicety."""
    from unittest.mock import AsyncMock, patch

    from app.utils import event_concept_cache as cache_mod

    class _Adapter:
        build_event = AsyncMock(return_value={"event": {"name": "The Masters"}})

    with patch.object(cache_mod, "compute_watermark", AsyncMock(return_value=None)), patch(
        "app.utils.competition_identity.competition_block",
        side_effect=RuntimeError("register on fire"),
    ):
        built = await cache_mod.build_and_cache(
            "event:golf:the-masters", db=None, rc=None, adapter=_Adapter()
        )
    assert built["event"]["name"] == "The Masters"
    assert "competition" not in built
