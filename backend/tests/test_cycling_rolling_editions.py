"""#2482 — cycling concepts must not vanish from Discover when the year turns.

THE SHIP: a reader opening Discover in any future year still sees the Grand Tour
that is actually running. Before this, they saw nothing, permanently.

THE DEFECT, measured before the repair (LAT-P182). `list_cycling_concepts` counted
a market only if its `resolution_date.year` matched the year written into a
hand-maintained config slug (`vuelta-2026` and friends), AND only surfaced the
concept if that resolution was still ahead of `now`. Those two conditions are
jointly unsatisfiable once the configured year is over, so the arm returned:

    clock 2026-09-01, market resolving in 13 days -> 2 concepts
    clock 2026-12-31, market resolving in 13 days -> 0     <- already gone
    clock 2027-01-01                              -> 0
    clock 2027-07-01                              -> 0
    clock 2028-05-01                              -> 0

Production context that sets the due date: all 17 open cycling markets on
2026-09-01 are the Vuelta 2026, the last resolving 2026-09-27. Every edition after
that resolves in a year no config named, so the concept could never have come back.

🔴 WHY THIS FILE MOVES THE CLOCK RATHER THAN NAMING A DATE. The whole class of bug
here is a test that is green today and red at some future instant, so a guard that
asserts against `now` alone cannot see the thing it is guarding. Every assertion
below is evaluated at several instants including ones years out, and the assertion
is INVARIANCE — the answer must not depend on when it is asked. A guard that names
a literal year would be the bug wearing the fix's clothes.
"""

from __future__ import annotations

import datetime as _real_datetime_module
import re
from datetime import datetime, timedelta, timezone

import pytest

import app.utils.event_cycling as ec

# Instants the guards are evaluated at. `+0` is the control that separates a real
# clock bomb from a specimen that is simply broken (LAT-P181's oracle: a bomb is
# green at +0 and red later; an artifact is red at +0 too). The rest cross a year
# boundary, a mid-year point, and a year far past anything a human will hand-edit.
CLOCKS: tuple[datetime, ...] = (
    datetime.now(timezone.utc),
    datetime(2026, 12, 31, 12, 0, tzinfo=timezone.utc),
    datetime(2027, 1, 1, 12, 0, tzinfo=timezone.utc),
    datetime(2027, 7, 1, 12, 0, tzinfo=timezone.utc),
    datetime(2028, 5, 1, 12, 0, tzinfo=timezone.utc),
    datetime(2031, 3, 1, 12, 0, tzinfo=timezone.utc),
)


class _FrozenDateTime(_real_datetime_module.datetime):
    """`event_cycling` does `from datetime import datetime`, so the module holds
    its own reference and patching `ec.datetime` is the honest seam. Subclassing
    the real class keeps `isinstance`/comparison against real datetimes working —
    the arithmetic in `cycling_status` compares this to real resolution dates."""

    _fake: datetime = CLOCKS[0]

    @classmethod
    def now(cls, tz=None):
        return cls._fake.astimezone(tz) if tz is not None else cls._fake.replace(tzinfo=None)


@pytest.fixture
def at_clock(monkeypatch):
    """Run a callable with `event_cycling`'s clock frozen at a chosen instant."""

    def _set(when: datetime):
        monkeypatch.setattr(_FrozenDateTime, "_fake", when, raising=False)
        monkeypatch.setattr(ec, "datetime", _FrozenDateTime)
        # The seam must be PROVEN to have moved, or every assertion below passes
        # vacuously against the real clock (clock_sweep's self-check rule).
        assert ec.datetime.now(timezone.utc) == when, "the clock seam did not take"

    return _set


def _vuelta_rows(now: datetime):
    """Production-shaped `(name, status, resolution_date)` rows — the real open
    Kalshi/Polymarket titles measured on 2026-09-01, with the resolution carried
    RELATIVE to the clock so the specimen describes a Grand Tour in progress at
    whatever instant it is asked about. A literal date here would be the bomb."""
    res = now + timedelta(days=13)
    return [
        ("Vuelta a Espana Winner", "open", res),
        ("Vuelta a Espana: Stage 14 Winner", "open", res),
        ("Vuelta a Espana Team Winner", "open", res),
    ]


# ---------------------------------------------------------------------------
# 1. THE SHIP — the Discover arm survives the year turning
# ---------------------------------------------------------------------------


class TestConceptsSurviveTheYearTurning:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("when", CLOCKS, ids=lambda d: d.date().isoformat())
    async def test_a_race_in_progress_surfaces_at_every_instant(self, at_clock, when):
        """The arm that read 0 from 2026-12-31 onward. This is the ship."""
        at_clock(when)
        got = await ec.list_cycling_concepts(
            None, statuses=("upcoming", "live"), limit=10, rows=_vuelta_rows(when)
        )
        assert got, f"no cycling concept surfaced at {when.isoformat()} — Discover is empty"
        assert got[0]["domain"] == "cycling"
        assert got[0]["entry_count"] == 3

    @pytest.mark.asyncio
    @pytest.mark.parametrize("when", CLOCKS, ids=lambda d: d.date().isoformat())
    async def test_the_concept_key_names_the_markets_own_edition(self, at_clock, when):
        """The edition is DERIVED from the market's resolution year, so the card
        links to a page that can actually resolve those markets."""
        at_clock(when)
        rows = _vuelta_rows(when)
        expected_year = rows[0][2].year
        got = await ec.list_cycling_concepts(
            None, statuses=("upcoming", "live"), limit=10, rows=rows
        )
        assert got[0]["key"] == f"event:cycling:vuelta-{expected_year}"
        assert got[0]["name"] == f"Vuelta a España {expected_year}"

    @pytest.mark.asyncio
    async def test_two_editions_in_flight_stay_two_cards(self, at_clock):
        """A market resolving next year must NOT be folded into this year's card.
        The edition guard is the reason the old config existed; keep it working."""
        when = datetime(2027, 12, 20, 12, 0, tzinfo=timezone.utc)
        at_clock(when)
        rows = [
            ("Vuelta a Espana Winner", "open", datetime(2027, 12, 28, tzinfo=timezone.utc)),
            ("Vuelta a Espana Winner", "open", datetime(2028, 1, 3, tzinfo=timezone.utc)),
        ]
        got = await ec.list_cycling_concepts(
            None, statuses=("upcoming", "live"), limit=10, rows=rows
        )
        assert {c["key"] for c in got} == {
            "event:cycling:vuelta-2027",
            "event:cycling:vuelta-2028",
        }

    @pytest.mark.asyncio
    @pytest.mark.parametrize("when", CLOCKS, ids=lambda d: d.date().isoformat())
    async def test_a_finished_race_is_still_filtered_out(self, at_clock, when):
        """The repair must not resurrect settled races into the upcoming/live feed.
        Asserting the NEGATIVE at the same instants keeps the fix from being 'always
        return something' — that would pass every test above and be wrong."""
        at_clock(when)
        rows = [("Vuelta a Espana Winner", "open", when - timedelta(days=30))]
        got = await ec.list_cycling_concepts(
            None, statuses=("upcoming", "live"), limit=10, rows=rows
        )
        assert got == [], f"a race that resolved 30 days ago surfaced as live at {when}"


# ---------------------------------------------------------------------------
# 2. The concept page the card links to must resolve
# ---------------------------------------------------------------------------


class TestSlugResolutionIsRolling:
    @pytest.mark.parametrize("year", (2026, 2027, 2031, 2099))
    def test_any_year_stamped_edition_resolves(self, year):
        """A card built for `vuelta-2031` is a dead link unless the adapter can
        parse it. No clock involved — a stamped slug means exactly that edition."""
        for stem, display in (
            ("tour-de-france", "Tour de France"),
            ("giro", "Giro d'Italia"),
            ("vuelta", "Vuelta a España"),
        ):
            cfg = ec.parse_cycling_slug(f"{stem}-{year}")
            assert cfg is not None, f"{stem}-{year} did not resolve"
            assert cfg.slug == f"{stem}-{year}"
            assert cfg.display == f"{display} {year}"
            assert ec._slug_year(cfg.slug) == year

    @pytest.mark.parametrize("when", CLOCKS, ids=lambda d: d.date().isoformat())
    def test_a_bare_alias_follows_the_clock(self, at_clock, when):
        """`/event/event:cycling:tdf` used to mean 2026 forever."""
        at_clock(when)
        assert ec.parse_cycling_slug("tdf").slug == f"tour-de-france-{when.year}"
        assert ec.parse_cycling_slug("vuelta").slug == f"vuelta-{when.year}"
        assert ec.parse_cycling_slug("giro").slug == f"giro-{when.year}"

    def test_now_is_an_injectable_seam_not_only_a_patch_point(self):
        assert (
            ec.parse_cycling_slug(
                "tdf", now=datetime(2033, 4, 1, tzinfo=timezone.utc)
            ).slug
            == "tour-de-france-2033"
        )

    @pytest.mark.parametrize(
        "bad", ("nope-2099", "", "  ", "tour-de-france-99", "2027", "-2027", "tourdefrance")
    )
    def test_unknown_stems_are_still_rejected(self, bad):
        """The rolling lookup must not become a slug that matches anything."""
        assert ec.parse_cycling_slug(bad) is None

    def test_every_pre_2482_alias_still_resolves_to_the_same_edition(self):
        """Back-compat, by enumeration. These are the exact strings the old
        hand-written `CYCLING_RACES` registry accepted; a live URL, a bookmark or
        a stored concept key carrying any of them must not 404."""
        legacy = {
            "tour-de-france-2026": "tour-de-france-2026",
            "tour-de-france": "tour-de-france-2026",
            "tdf-2026": "tour-de-france-2026",
            "tdf": "tour-de-france-2026",
            "le-tour-2026": "tour-de-france-2026",
            "giro-2026": "giro-2026",
            "giro-ditalia-2026": "giro-2026",
            "giro": "giro-2026",
            "vuelta-2026": "vuelta-2026",
            "vuelta-a-espana-2026": "vuelta-2026",
            "vuelta": "vuelta-2026",
        }
        at_2026 = datetime(2026, 9, 1, tzinfo=timezone.utc)
        for alias, expected in legacy.items():
            cfg = ec.parse_cycling_slug(alias, now=at_2026)
            assert cfg is not None, f"legacy alias {alias!r} stopped resolving"
            assert cfg.slug == expected, alias

    def test_case_and_whitespace_tolerance_is_preserved(self):
        assert ec.parse_cycling_slug("  TDF-2027  ").slug == "tour-de-france-2027"


# ---------------------------------------------------------------------------
# 3. The search / breadcrumb up-link
# ---------------------------------------------------------------------------


class TestDeriveConceptIsRolling:
    @pytest.mark.parametrize("when", CLOCKS, ids=lambda d: d.date().isoformat())
    def test_a_gc_market_uplinks_to_the_edition_in_play(self, at_clock, when):
        at_clock(when)
        assert ec.derive_cycling_concept("x", "Tour de France Winner", "cycling") == {
            "key": f"event:cycling:tour-de-france-{when.year}",
            "name": f"Tour de France {when.year}",
            "domain": "cycling",
        }

    def test_now_seam(self):
        got = ec.derive_cycling_concept(
            "x", "Vuelta a Espana Winner", "cycling",
            now=datetime(2030, 8, 1, tzinfo=timezone.utc),
        )
        assert got["key"] == "event:cycling:vuelta-2030"

    @pytest.mark.parametrize("when", CLOCKS, ids=lambda d: d.date().isoformat())
    def test_non_gc_markets_still_return_none_at_every_clock(self, at_clock, when):
        """Stage/team/jersey markets must keep falling through to the market page
        rather than up-linking to a concept. The rolling year must not loosen this."""
        at_clock(when)
        for nm in (
            "Tour de France: Stage 3 Winner",
            "Tour de France Team Winner",
            "Tour de France: Green Jersey Winner",
        ):
            assert ec.derive_cycling_concept("x", nm, "cycling") is None, nm
        assert ec.derive_cycling_concept("x", "Tour de France Winner", "golf") is None


# ---------------------------------------------------------------------------
# 4. The registry itself must not be able to reacquire a fuse
# ---------------------------------------------------------------------------


class TestTheRegistryCarriesNoYear:
    def test_no_family_hardcodes_a_year(self):
        """The defect was a YEAR inside the registry. If a future edit puts one
        back — a `vuelta-2027` stem, a `Giro d'Italia 2027` display — the calendar
        has a fuse in it again and this fails the day it is written, not the day
        it detonates."""
        year_re = re.compile(r"20\d{2}")
        for key, fam in ec.CYCLING_RACE_FAMILIES.items():
            for label, value in (
                ("dict key", key),
                ("stem", fam.stem),
                ("display", fam.display),
                ("name_re", fam.name_re.pattern),
                *(("alias_stem", a) for a in fam.alias_stems),
            ):
                assert not year_re.search(value), (
                    f"{fam.stem}: {label} {value!r} carries a hardcoded year — "
                    "editions are derived, families are not dated (#2482)"
                )

    def test_the_old_edition_registry_is_gone(self):
        """A leftover `CYCLING_RACES` dict would be a second, dated source of truth
        that the lister no longer reads — the worst outcome, because it would look
        maintained. `edition_config` replaces it."""
        assert not hasattr(ec, "CYCLING_RACES"), (
            "CYCLING_RACES is back; the lister derives editions and must not have "
            "a hand-written per-year registry beside it"
        )
        assert callable(ec.edition_config)

    def test_edition_config_rejects_an_unknown_family(self):
        assert ec.edition_config("not-a-race", 2027) is None

    def test_edition_config_is_bounded(self):
        """An unbounded module-global keyed by a caller-influenced value is the
        `_canonical_source_names_cache` pattern this lane already tracks."""
        info = ec.edition_config.cache_info()
        assert info.maxsize is not None and info.maxsize <= 1024

    def test_families_still_cover_the_three_grand_tours(self):
        assert set(ec.CYCLING_RACE_FAMILIES) == {"tour-de-france", "giro", "vuelta"}

    def test_every_cycling_key_the_horizon_calendar_declares_resolves(self):
        """🔴 THE CORROBORATION, and the strongest guard in this file — it is the
        repo's own config disagreeing with the repo's own adapter.

        `majors_calendar.yaml` declares `event:cycling:giro-2027` and
        `event:cycling:tour-de-france-2027` as expected concept surfaces, and
        `tasks/horizon_sentinel` page-checks each declared `concept_key` against
        `GET /api/event/{concept_key}`, escalating IN-PROGRESS-WITHOUT-PAGE at P0
        when it 404s. Measured before this repair, BOTH 2027 keys resolved to
        None — a P0 in May 2027 that no amount of market data could have cleared.

        This reads the real yaml rather than a copy, so adding a 2029 edition to
        the calendar without adapter support fails here instead of in production."""
        import pathlib

        yaml_path = (
            pathlib.Path(__file__).resolve().parents[1] / "app" / "config" / "majors_calendar.yaml"
        )
        assert yaml_path.is_file(), f"the horizon calendar moved: {yaml_path}"
        declared = sorted(set(re.findall(r"event:cycling:([a-z0-9-]+)", yaml_path.read_text())))
        # RAISE rather than pass vacuously if the scan finds nothing — a renamed
        # key prefix would otherwise turn this guard green by finding zero work.
        assert len(declared) >= 4, (
            f"only {len(declared)} cycling concept keys found in {yaml_path.name} — "
            "the scan pattern is stale, not the calendar"
        )
        unresolvable = [k for k in declared if ec.parse_cycling_slug(k) is None]
        assert not unresolvable, (
            f"{yaml_path.name} declares cycling concept surfaces the adapter cannot "
            f"build, so horizon_sentinel will file a P0 it cannot clear: {unresolvable}"
        )

    def test_the_competition_registers_aliases_all_resolve(self):
        """The Competition Register in the same yaml lists the standing aliases
        (`tdf`, `le-tour`, `giro`, `vuelta`, `la-vuelta`). A URL carrying one must
        reach the edition in play, not 404."""
        at = datetime(2027, 6, 1, tzinfo=timezone.utc)
        for alias, stem in (
            ("tdf", "tour-de-france"),
            ("le-tour", "tour-de-france"),
            ("giro", "giro"),
            ("giro-ditalia", "giro"),
            ("vuelta", "vuelta"),
            ("la-vuelta", "vuelta"),
            ("vuelta-a-espana", "vuelta"),
        ):
            cfg = ec.parse_cycling_slug(alias, now=at)
            assert cfg is not None, f"register alias {alias!r} does not resolve"
            assert cfg.slug == f"{stem}-2027", alias

    @pytest.mark.parametrize(
        "title,stem",
        (
            ("Vuelta a Espana Winner", "vuelta"),
            ("Vuelta a España: Stage 14 Winner", "vuelta"),
            ("Tour de France Winner", "tour-de-france"),
            ("Giro d'Italia Winner", "giro"),
            ("Giro Winner", "giro"),
        ),
    )
    def test_real_production_titles_still_match_their_family(self, title, stem):
        """The exact open-market titles measured in production on 2026-09-01. The
        regexes moved between dataclasses; prove they still match what Kalshi and
        Polymarket actually send."""
        assert ec.CYCLING_RACE_FAMILIES[stem].name_re.search(title), title
