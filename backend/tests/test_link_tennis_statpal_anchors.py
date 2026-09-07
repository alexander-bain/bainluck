"""#2867 / D59 step 4 — the tennis link's two decisions that need no database.

Two things are settled before a single row is written, and both are settled here
because both are wrong in a way a database round trip would not show:

1. **Which sport name qualifies a StatPal tennis anchor key.** D55 says the key
   is `(provider, sport, id)`. `statpal_id_space` decides what "sport" means for
   a provider whose id space is coarser than our `sports.key` vocabulary, and
   getting it wrong does not produce an error — it produces two valid-looking
   keys for one match and a collision check that never fires.
2. **Whether the banked map may be applied at all.** The map is real data,
   vendored into the repo, and it is NOT 1:1: 221 rows against 212 distinct
   events. Which subset is safe is a property of that file, so it is asserted
   against that file rather than against a fabricated one.

The apply/rollback round trip is a real-Postgres gate and lives in
`integration/test_link_tennis_statpal_real_postgres.py`.
"""

from __future__ import annotations

import csv
import importlib.util
import sys
from collections import Counter
from pathlib import Path

import pytest

from app.utils.provider_anchor_keys import (
    SOURCE_STATPAL,
    STATPAL_ID_SPACE_TENNIS,
    statpal_anchor_key,
    statpal_id_space,
)

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load_script():
    """Import the script by path — `scripts/` is not a package."""
    path = SCRIPTS / "link_tennis_statpal_anchors_2867.py"
    spec = importlib.util.spec_from_file_location("link_tennis_statpal_2867", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


script = _load_script()


# --- 1. the id space -----------------------------------------------------------


class TestTheQualifierIsTheProvidersIdSpace:
    """`statpal_id_space` maps our key onto the namespace StatPal actually uses."""

    #: Every tennis `sports.key` shape in production on 2026-09-03, plus two
    #: tournament keys that do not exist yet. The future ones are the point: an
    #: enumeration of today's keys would pass this test by luck and mis-space
    #: the next Slam we mint.
    TENNIS_KEYS = (
        "tennis_atp",
        "tennis_wta",
        "tennis_other",
        "tennis_itf",
        "tennis_atp_us_open",
        "tennis_wta_us_open",
        "tennis_atp_wimbledon",
        "tennis_wta_wimbledon",
        "tennis_wta_french_open",
        "tennis_atp_aus_open_singles",
        "tennis_wta_aus_open_singles",
        "tennis_atp_shanghai_masters",  # not minted yet
        "tennis_mixed_united_cup",  # not minted yet
    )

    #: Keys whose StatPal id space is 1:1 with our own, so the qualifier is the
    #: key itself. `soccer_epl` was here until authority/062 measured soccer's
    #: feed and found the tennis shape a second time — 113 leagues numbered
    #: from one sequence — so soccer now collapses too and its claims live in
    #: `test_statpal_soccer_id_spaces_3366.py`. It is not dropped from this
    #: class: the cross-sport distinctness property below still covers it.
    NON_TENNIS_KEYS = (
        "baseball_mlb",
        "americanfootball_nfl",
        "americanfootball_ncaaf",
        "basketball_nba",
        "icehockey_nhl",
        "golf_pga",
    )

    @pytest.mark.parametrize("sport_key", TENNIS_KEYS)
    def test_every_tennis_key_collapses_onto_one_space(self, sport_key):
        assert statpal_id_space(sport_key) == STATPAL_ID_SPACE_TENNIS

    def test_the_collapse_is_the_whole_point_one_fixture_yields_one_key(self):
        """The property, not a specimen: one match, one anchor key, always.

        This is the failure mode that has no error message. With the raw
        `sports.key` as the qualifier, our generic row and our tournament row
        for the SAME StatPal match produce two different `source_id` values,
        the unique index accepts both, and the `COLLISION` that is the only
        proof we hold that two rows are one game never fires.
        """
        fixture_id = "2631673"
        keys = {
            statpal_anchor_key(fixture_id, statpal_id_space(k)).source_id
            for k in self.TENNIS_KEYS
        }
        assert keys == {f"{STATPAL_ID_SPACE_TENNIS}:{fixture_id}"}, (
            "one StatPal match must yield exactly one anchor key across every "
            f"tennis sport key; got {sorted(keys)}"
        )

    def test_the_control_the_raw_sport_key_would_fragment_it(self):
        """The arm that shows this test can fail.

        Without `statpal_id_space`, the same sweep produces one key per tennis
        `sports.key`. If a future edit makes the function a pass-through, the
        test above starts failing and this one starts passing — the two move in
        opposite directions on purpose.
        """
        fixture_id = "2631673"
        raw = {statpal_anchor_key(fixture_id, k).source_id for k in self.TENNIS_KEYS}
        assert len(raw) == len(self.TENNIS_KEYS)

    @pytest.mark.parametrize("sport_key", NON_TENNIS_KEYS)
    def test_every_other_sport_passes_through_unchanged(self, sport_key):
        """MLB's live `baseball_mlb:` anchors and the #2879 re-key must not move."""
        assert statpal_id_space(sport_key) == sport_key

    def test_no_two_sports_share_a_key_for_one_fixture(self):
        """D55's actual property, still true with tennis collapsed.

        Collapsing WITHIN a provider sport is safe; collapsing ACROSS them is
        the defect #2879 fixed. Two collapsed buckets — `tennis` and, since
        authority/062, `soccer` — plus the untouched pass-through must still
        give every distinct sport a distinct key. Both collapsed sports are
        listed here precisely because a bucket is where an over-broad prefix
        would first swallow a neighbour.
        """
        spaces = [statpal_id_space(k) for k in self.NON_TENNIS_KEYS]
        spaces.append(statpal_id_space("tennis_atp_us_open"))
        spaces.append(statpal_id_space("soccer_epl"))
        assert len(set(spaces)) == len(spaces)

    def test_none_stays_none_and_blank_stays_blank(self):
        """A caller with no sport still has no sport.

        `statpal_anchor_key` distinguishes `None` (legacy bridge) from a present
        but empty qualifier (refuse). This must not turn either into the other.
        """
        assert statpal_id_space(None) is None
        assert statpal_id_space("") == ""
        assert statpal_id_space("   ") == ""

    def test_a_blank_qualifier_still_refuses_to_produce_a_key(self):
        assert statpal_anchor_key("2631673", statpal_id_space("")) is None

    def test_the_tennis_space_is_anchorable_which_it_was_not_before_d55(self):
        """The regression this whole step rests on.

        Tennis fixture ids are 7 digits and matched neither digit regex, so the
        pre-D55 key function refused them outright. If the legacy branch is ever
        restored, this fails and nothing else in the tennis path would.
        """
        key = statpal_anchor_key("2631673", STATPAL_ID_SPACE_TENNIS)
        assert key is not None
        assert (key.source, key.source_id, key.id_kind) == (
            SOURCE_STATPAL,
            "tennis:2631673",
            "game",
        )
        assert key.may_anchor_absorption is True
        assert statpal_anchor_key("2631673") is None, (
            "unqualified, a 7-digit tennis id is still unanchorable — the legacy "
            "bridge must not have learned to guess it"
        )


# --- 2. the banked map ---------------------------------------------------------


class TestTheBankedMapIsAppliedOnlyWhereItIsUnambiguous:
    """Assertions about the REAL vendored file, not a fabricated one.

    The numbers below are the sweep's, measured 2026-09-03 and banked as
    `ARTIFACT-M-20260903-I-map.csv`. If the vendored copy is ever re-cut, these
    fail rather than silently applying a different population.
    """

    def test_the_map_ships_with_the_script(self):
        assert script.DEFAULT_MAP.exists(), (
            f"{script.DEFAULT_MAP} must be vendored — `.claude/handoff/` is not "
            "deployed, so a map that lives only there applies zero rows on the dyno "
            "and reports a clean run"
        )

    def test_the_raw_map_is_not_one_to_one_which_is_why_the_check_exists(self):
        with script.DEFAULT_MAP.open(newline="") as fh:
            rows = list(csv.DictReader(fh))
        assert len(rows) == 221
        by_event = Counter(r["our_event_id"] for r in rows)
        collisions = {k: n for k, n in by_event.items() if n > 1}
        assert len(collisions) == 9, (
            "the banked map really does hold 9 events claimed by two StatPal "
            f"matches; got {collisions}"
        )

    def test_every_collision_involves_a_low_confidence_row(self):
        """Why excluding LOW is a fix and not a coincidence."""
        with script.DEFAULT_MAP.open(newline="") as fh:
            rows = list(csv.DictReader(fh))
        by_event: dict[str, list[dict]] = {}
        for r in rows:
            by_event.setdefault(r["our_event_id"], []).append(r)
        for event_id, group in by_event.items():
            if len(group) > 1:
                assert any(r["confidence"] == "low" for r in group), (
                    f"event {event_id} is claimed twice with no LOW row involved — "
                    "dropping LOW would not disambiguate it"
                )

    def test_the_default_selection_is_one_to_one_and_is_204_rows(self):
        selected = script.load_map(script.DEFAULT_MAP, {"high", "medium"})
        assert len(selected) == 204
        assert len({r["our_event_id"] for r in selected}) == 204
        assert len({r["statpal_id"] for r in selected}) == 204

    def test_the_default_confidence_is_high_and_medium(self):
        """Alex's addendum, 2026-09-03, pinned rather than paraphrased."""
        assert script.DEFAULT_CONFIDENCE == "high,medium"

    def test_including_low_aborts_the_whole_run(self):
        """The refusal is total, not per-row.

        A partial apply over an ambiguous map would write whichever of the two
        candidate fixtures the CSV happened to list first — an answer decided by
        row order.
        """
        with pytest.raises(script.MapError) as exc:
            script.load_map(script.DEFAULT_MAP, {"high", "medium", "low"})
        assert "not 1:1" in str(exc.value)

    def test_a_missing_map_raises_rather_than_applying_nothing(self):
        with pytest.raises(script.MapError) as exc:
            script.load_map(SCRIPTS / "data" / "no-such-map.csv", {"high"})
        assert "not found" in str(exc.value)

    def test_a_confidence_nobody_used_raises_rather_than_applying_nothing(self):
        """A typo'd `--confidence hgih` must not read as a clean zero-row run."""
        with pytest.raises(script.MapError) as exc:
            script.load_map(script.DEFAULT_MAP, {"hgih"})
        assert "no rows at confidence" in str(exc.value)

    def test_every_selected_fixture_id_yields_a_tennis_anchor_key(self):
        """No row in the applied set can silently produce `None` and vanish."""
        for r in script.load_map(script.DEFAULT_MAP, {"high", "medium"}):
            key = statpal_anchor_key(r["statpal_id"], STATPAL_ID_SPACE_TENNIS)
            assert key is not None, r
            assert key.source_id == f"tennis:{r['statpal_id']}"
