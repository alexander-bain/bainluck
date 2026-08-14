"""#1829 — recency decay + weight cap on the point-in-time hero (Alex, 08-13).

UX-P071 measured the defect and pinned it as a ratchet; this is the fix and its
evidence. The specimen, once more, because every test below is a claim about it:

    Event 15192596, Red Sox @ Blue Jays, top of the 9th, Toronto trailing 0-5
    (final 0-7). The header read **87 - 13** for Boston. `betting` was frozen at
    0.1347 — every bookmaker had PULLED the moneyline once the game was out of
    reach, so the writer's `all_home_probs` went empty and the key simply stopped
    being rewritten — while mlb, espn and stat_model were seconds fresh and all
    three said ~0. The weighted median landed ON the frozen number, because
    `betting` held 42% of the weight and could straddle the midpoint alone.

NO WALL CLOCK ANYWHERE, and not by discipline — by construction. The decay ages
each source against the FRESHEST STAMP ON THE SAME EVENT, never against `now()`,
so there is no anchor for gotcha #44 to rot. Every timestamp below is a literal.
`backend/scripts/clock_sweep.py` has nothing to find here and that is the point.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.aggregation import (
    HERO_MIN_STALENESS_MULTIPLIER,
    HERO_RELATIVE_DECAY_SECONDS,
    HERO_RELATIVE_GRACE_SECONDS,
    MAX_SOURCE_WEIGHT_SHARE,
    MIN_SOURCES_FOR_WEIGHT_CAP,
    SOURCE_WEIGHTS,
    _relative_staleness_multiplier,
    cap_weight_shares,
    compute_aggregate_probability,
    compute_current_aggregate,
    parse_source_entry,
    stamp_source_reading,
    wps_numeric_sql,
)

# ── The specimen, as production held it (home = Blue Jays) ───────────────────

SPECIMEN_VALUES = {
    "mlb": 0.001,
    "espn": 0.008,
    "kalshi": 0.565,
    "betting": 0.1347,
    "stat_model": 0.001,
}

# Write times measured from production, NOT invented:
#   - `betting`  21:08:36 — the last moment any book still quoted a moneyline
#     (`odds_snapshots.valid_until`, single remaining book: rebet)
#   - mlb / espn / stat_model from `win_prob_snapshots.captured_at`
#   - kalshi's linked market last moved the PREVIOUS DAY
SPECIMEN_STAMPED = {
    "mlb": {"value": 0.001, "updated_at": "2026-08-13T21:24:34+00:00"},
    "espn": {"value": 0.008, "updated_at": "2026-08-13T21:07:34+00:00"},
    "stat_model": {"value": 0.001, "updated_at": "2026-08-13T21:33:34+00:00"},
    "betting": {"value": 0.1347, "updated_at": "2026-08-13T21:08:36+00:00"},
    "kalshi": {"value": 0.565, "updated_at": "2026-08-12T20:41:19+00:00"},
}

T0 = datetime(2026, 8, 13, 21, 33, 34, tzinfo=timezone.utc)


class _FakeEvent:
    def __init__(self, sources, status="live"):
        self.win_probability_sources = sources
        self.status = status
        self.espn_win_prob_home = None
        self.opening_home_probability = None


def _stamped(**kwargs):
    """`_stamped(betting=(0.9, 0), espn=(0.1, 3600))` — value, seconds behind T0."""
    return {
        key: {
            "value": value,
            "updated_at": (T0 - timedelta(seconds=behind)).isoformat(),
        }
        for key, (value, behind) in kwargs.items()
    }


# ── Alex's header, before and after ──────────────────────────────────────────


class TestTheSpecimenIsFixed:
    def test_the_header_no_longer_reads_87_13(self):
        home = compute_aggregate_probability(_FakeEvent(SPECIMEN_STAMPED))
        assert round((1 - home) * 100) == 99
        assert round(home * 100) == 1

    def test_the_hero_is_no_longer_the_betting_source_verbatim(self):
        """The whole defect in one assertion: the median must stop landing ON
        the frozen sportsbook number."""
        home = compute_aggregate_probability(_FakeEvent(SPECIMEN_STAMPED))
        assert home != pytest.approx(SPECIMEN_VALUES["betting"], abs=1e-6)
        # It lands on a source that was actually watching the game.
        assert home == pytest.approx(SPECIMEN_VALUES["espn"], abs=1e-9)

    def test_the_three_live_aware_models_now_carry_the_answer(self):
        """They agreed on ~0 and were out-voted. Now they are not."""
        home = compute_aggregate_probability(_FakeEvent(SPECIMEN_STAMPED))
        assert home <= 0.01

    def test_either_half_fixes_it_alone(self):
        """Decay and cap are independent, and each is sufficient here.

        Recorded because it is the difference between one mechanism with a
        backup and two mechanisms that only work together — and because the
        cap is live on deploy while the decay waits for the writers to re-poll.
        """
        # Cap only: the unstamped shape production holds TODAY.
        cap_only = compute_aggregate_probability(_FakeEvent(dict(SPECIMEN_VALUES)))
        assert cap_only == pytest.approx(0.008, abs=1e-9)

        # Decay only: same stamps, cap disabled by dropping below its gate is not
        # possible at 5 sources, so verify against hand-computed decayed weights.
        weights = []
        stamps = {
            k: datetime.fromisoformat(v["updated_at"])
            for k, v in SPECIMEN_STAMPED.items()
        }
        freshest = max(stamps.values())
        for key in SPECIMEN_VALUES:
            mult = _relative_staleness_multiplier(
                (freshest - stamps[key]).total_seconds()
            )
            weights.append(SOURCE_WEIGHTS[key] * mult)
        from app.utils.aggregation import _weighted_median

        decay_only = _weighted_median(list(SPECIMEN_VALUES.values()), weights)
        assert decay_only == pytest.approx(0.008, abs=1e-9)

    def test_a_cap_of_0_40_would_NOT_have_fixed_it(self):
        """The constant's derivation, executable.

        `betting` stops straddling the midpoint only below a 0.379 share, so
        "0.4 is a rounder number" is a regression waiting to be committed.
        """
        assert MAX_SOURCE_WEIGHT_SHARE <= 0.379
        weights = [SOURCE_WEIGHTS[k] for k in SPECIMEN_VALUES]
        loose = cap_weight_shares(weights)  # with the real cap
        from app.utils.aggregation import _weighted_median

        assert _weighted_median(list(SPECIMEN_VALUES.values()), loose) < 0.01

        # And the counterfactual, computed rather than asserted.
        others = sum(SOURCE_WEIGHTS[k] for k in SPECIMEN_VALUES if k != "betting")
        b_at_040 = 0.40 * others / 0.60
        alt = [
            b_at_040 if k == "betting" else SOURCE_WEIGHTS[k] for k in SPECIMEN_VALUES
        ]
        assert _weighted_median(
            list(SPECIMEN_VALUES.values()), alt
        ) == pytest.approx(0.1347, abs=1e-9)


# ── Monotonicity: the guarantee that makes this safe to deploy ───────────────


class TestMonotoneOnUnstampedData:
    """An entry with no `updated_at` keeps FULL weight.

    This is the deploy safety argument. The writers stamp going forward, but
    every row already in the table is unstamped, and those rows must compute
    what they compute today — with the single, ruled exception of the cap.
    """

    def test_no_stamps_anywhere_means_no_decay_at_all(self):
        bare = {"betting": 0.9, "espn": 0.1, "mlb": 0.2}
        as_dicts = {k: {"value": v} for k, v in bare.items()}
        assert compute_aggregate_probability(
            _FakeEvent(bare)
        ) == compute_aggregate_probability(_FakeEvent(as_dicts))

    def test_an_unstamped_source_is_not_decayed_by_a_stamped_sibling(self):
        """Mixed shapes are the ROLLOUT state and will exist for hours.

        The unstamped source must not be punished for the silence it cannot
        prove it did not have.
        """
        mixed = {
            "betting": 0.9,  # bare float, no stamp
            "espn": {"value": 0.1, "updated_at": T0.isoformat()},
            "mlb": {"value": 0.2, "updated_at": T0.isoformat()},
        }
        all_fresh = {
            "betting": {"value": 0.9, "updated_at": T0.isoformat()},
            "espn": {"value": 0.1, "updated_at": T0.isoformat()},
            "mlb": {"value": 0.2, "updated_at": T0.isoformat()},
        }
        assert compute_aggregate_probability(
            _FakeEvent(mixed)
        ) == compute_aggregate_probability(_FakeEvent(all_fresh))

    def test_uniformly_old_is_not_stale(self):
        """Every source an hour behind: cadence, not staleness. Unchanged.

        This is the single most important property of making the decay
        RELATIVE. An absolute rule would have zeroed every pre-game event in
        the table, because a scheduled game is polled every 15 minutes to two
        hours and is supposed to be.
        """
        fresh = _stamped(betting=(0.9, 0), espn=(0.1, 0), mlb=(0.2, 0))
        old = _stamped(betting=(0.9, 3600), espn=(0.1, 3600), mlb=(0.2, 3600))
        assert compute_aggregate_probability(
            _FakeEvent(fresh)
        ) == compute_aggregate_probability(_FakeEvent(old))

    def test_malformed_timestamps_degrade_to_full_weight_and_never_raise(self):
        for junk in ("", "   ", "not-a-date", "2026-13-45T99:99:99", 12345, None, []):
            sources = {
                "betting": {"value": 0.9, "updated_at": junk},
                "espn": {"value": 0.1, "updated_at": T0.isoformat()},
                "mlb": {"value": 0.2, "updated_at": T0.isoformat()},
            }
            got = compute_aggregate_probability(_FakeEvent(sources))
            assert got is not None
            # Identical to the same event with the stamp simply absent.
            without = dict(sources)
            without["betting"] = {"value": 0.9}
            assert got == compute_aggregate_probability(_FakeEvent(without))

    def test_a_naive_datetime_is_read_as_utc_not_rejected(self):
        sources = {
            "betting": {"value": 0.9, "updated_at": "2026-08-13T20:00:00"},
            "espn": {"value": 0.1, "updated_at": "2026-08-13T21:00:00+00:00"},
            "mlb": {"value": 0.2, "updated_at": "2026-08-13T21:00:00Z"},
        }
        # betting is an hour behind -> decayed to the floor, so it cannot carry
        # the median against two fresh sources.
        assert compute_aggregate_probability(_FakeEvent(sources)) != pytest.approx(0.9)


# ── The decay curve ──────────────────────────────────────────────────────────


class TestRelativeDecayCurve:
    def test_grace_then_linear_then_floor(self):
        assert _relative_staleness_multiplier(0) == 1.0
        assert _relative_staleness_multiplier(HERO_RELATIVE_GRACE_SECONDS) == 1.0
        mid = HERO_RELATIVE_GRACE_SECONDS + HERO_RELATIVE_DECAY_SECONDS / 2
        assert _relative_staleness_multiplier(mid) == pytest.approx(0.5, abs=1e-9)
        end = HERO_RELATIVE_GRACE_SECONDS + HERO_RELATIVE_DECAY_SECONDS
        assert _relative_staleness_multiplier(end) == HERO_MIN_STALENESS_MULTIPLIER
        assert (
            _relative_staleness_multiplier(end * 100) == HERO_MIN_STALENESS_MULTIPLIER
        )

    def test_the_curve_is_monotone_non_increasing(self):
        prev = 1.1
        for age in range(0, 7200, 30):
            got = _relative_staleness_multiplier(age)
            assert got <= prev + 1e-12, f"decay went UP at {age}s"
            prev = got

    def test_the_floor_demotes_rather_than_deletes(self):
        """A fully-decayed source still exists — it just cannot carry a median.

        If decay reached zero, a source could vanish from the envelope entirely,
        and "we stopped hearing from Kalshi" would render as "Kalshi never had
        an opinion".
        """
        assert HERO_MIN_STALENESS_MULTIPLIER > 0
        ancient = _stamped(betting=(0.9, 86400 * 7), espn=(0.1, 0))
        assert compute_aggregate_probability(_FakeEvent(ancient)) is not None

    def test_weights_can_never_all_collapse(self):
        """The freshest source always holds multiplier 1.0, by definition of the
        reference. So the blend can never become undefined through decay."""
        for behind in (0, 60, 3600, 86400):
            sources = _stamped(betting=(0.9, behind), espn=(0.1, behind + 99999))
            assert compute_aggregate_probability(_FakeEvent(sources)) is not None

    def test_a_stale_source_cannot_out_vote_fresh_ones(self):
        """The ruling, stated as a test — and isolated to the DECAY.

        Two sources, so the cap is out of the picture by its own gate: betting
        (3.0) beats espn (1.5) on weight while both are fresh, and must lose the
        moment it is an hour behind. Written with three sources first, which
        proved nothing, because the cap had already flipped it.
        """
        fresh = _stamped(betting=(0.9, 0), espn=(0.1, 0))
        assert compute_aggregate_probability(_FakeEvent(fresh)) == pytest.approx(0.9)

        stale_book = _stamped(betting=(0.9, 3600), espn=(0.1, 0))
        assert compute_aggregate_probability(_FakeEvent(stale_book)) == pytest.approx(
            0.1
        )

    def test_decay_and_cap_compound_on_three_sources(self):
        """With three sources both mechanisms bite, and the ORDER matters:
        decay first, then cap the decayed weights. Capping first would let a
        source be re-inflated relative to a sibling that later decayed."""
        fresh = _stamped(betting=(0.9, 0), espn=(0.1, 0), mlb=(0.12, 0))
        assert compute_aggregate_probability(_FakeEvent(fresh)) == pytest.approx(0.12)
        stale_book = _stamped(betting=(0.9, 3600), espn=(0.1, 0), mlb=(0.12, 0))
        assert compute_aggregate_probability(_FakeEvent(stale_book)) < 0.5

    def test_a_future_stamp_is_just_the_freshest_and_breaks_nothing(self):
        """Clock skew between writers must not produce a negative age.

        There is no `now()` to be ahead OF, so the worst a skewed writer can do
        is become the reference — which is exactly what "freshest" means.
        """
        skewed = _stamped(betting=(0.9, -600), espn=(0.1, 0), mlb=(0.12, 0))
        got = compute_aggregate_probability(_FakeEvent(skewed))
        assert got is not None and 0.0 <= got <= 1.0


# ── The weight cap ───────────────────────────────────────────────────────────


class TestWeightCap:
    def test_no_source_exceeds_the_share_after_capping(self):
        for weights in (
            [3.0, 1.5, 1.0, 0.8, 0.8],
            [5.0, 0.1, 0.1],
            [1.0, 1.0, 1.0],
            [9.0, 9.0, 0.1],
            [0.5, 0.5, 0.5, 0.5],
        ):
            capped = cap_weight_shares(weights)
            total = sum(capped)
            for w in capped:
                assert w / total <= MAX_SOURCE_WEIGHT_SHARE + 1e-9, capped

    def test_two_sources_are_never_capped(self):
        """The gate. Any cap below 0.5 would hand every two-source event to the
        lighter source; on 2026-08-13 that was 95 scheduled + 125 completed + 6
        live events, virtually all `betting` + one model."""
        assert MIN_SOURCES_FOR_WEIGHT_CAP == 3
        assert cap_weight_shares([3.0, 1.5]) == [3.0, 1.5]
        assert cap_weight_shares([100.0, 0.1]) == [100.0, 0.1]
        two = {"betting": 0.9, "espn": 0.1}
        assert compute_aggregate_probability(_FakeEvent(two)) == pytest.approx(0.9)

    def test_capping_never_raises_a_weight(self):
        for weights in ([3.0, 1.5, 1.0], [1.0, 1.0, 1.0], [8.0, 1.0, 1.0, 1.0]):
            for before, after in zip(weights, cap_weight_shares(weights)):
                assert after <= before + 1e-12

    def test_it_holds_when_TWO_sources_are_over(self):
        """The case the first implementation got wrong, and got wrong quietly.

        "Cap the biggest, repeat" oscillates: reducing one source lowers the
        total, which raises the other's share. Bounded at a handful of passes it
        returned a 0.58 share against a 0.35 cap with no error. Not exotic —
        `betting` + `espn` + one market reaches it on the second pass.
        """
        for weights in ([10.0, 10.0, 0.5], [9.0, 9.0, 0.1], [3.0, 1.5, 0.8]):
            capped = cap_weight_shares(weights)
            total = sum(capped)
            assert all(
                w / total <= MAX_SOURCE_WEIGHT_SHARE + 1e-9 for w in capped
            ), f"{weights} -> {capped}"

    def test_it_holds_when_the_only_cappable_source_faces_exempt_mass(self):
        """Found by fuzzing, not by reading: with one cappable source and two
        exempt ones the solver never tried "cap everything cappable" and
        returned the weights untouched."""
        capped = cap_weight_shares([7.036, 2.322, 8.978], exempt=[False, True, True])
        total = sum(capped)
        assert capped[0] / total <= MAX_SOURCE_WEIGHT_SHARE + 1e-9

    def test_fuzz_the_cap_never_violates_and_never_raises_a_weight(self):
        """A deterministic sweep, because both bugs above were invisible to
        every hand-written case and obvious to a few thousand random ones."""
        import random

        rng = random.Random(7)
        for _ in range(5000):
            n = rng.randint(3, 7)
            weights = [round(rng.uniform(0.001, 10), 3) for _ in range(n)]
            exempt = [rng.random() < 0.15 for _ in range(n)]
            capped = cap_weight_shares(weights, exempt=exempt)
            total = sum(capped)
            assert total > 0
            for i, w in enumerate(capped):
                assert w <= weights[i] + 1e-12, (weights, exempt, capped)
                if not exempt[i]:
                    assert w / total <= MAX_SOURCE_WEIGHT_SHARE + 1e-9, (
                        weights,
                        exempt,
                        capped,
                    )

    def test_final_result_is_exempt(self):
        """Settled means settled. Capping the graded outcome would let live
        market noise out-vote the actual result on a finished game."""
        weights = [SOURCE_WEIGHTS["final_result"], 3.0, 1.5]
        exempt = [True, False, False]
        capped = cap_weight_shares(weights, exempt=exempt)
        assert capped[0] == SOURCE_WEIGHTS["final_result"]

        settled = {"final_result": 1.0, "betting": 0.35, "espn": 0.4}
        assert compute_aggregate_probability(
            _FakeEvent(settled, status="completed")
        ) == pytest.approx(1.0)

    def test_final_result_does_not_decay_either(self):
        """It is an outcome, not a reading. Age is meaningless to it."""
        sources = {
            "final_result": {"value": 1.0, "updated_at": "2026-08-01T00:00:00+00:00"},
            "betting": {"value": 0.35, "updated_at": T0.isoformat()},
            "espn": {"value": 0.4, "updated_at": T0.isoformat()},
        }
        assert compute_aggregate_probability(
            _FakeEvent(sources, status="completed")
        ) == pytest.approx(1.0)


# ── The writer half ──────────────────────────────────────────────────────────


class TestStampSourceReading:
    def test_it_writes_value_and_updated_at(self):
        out = stamp_source_reading({}, "betting", 0.42, now=T0)
        assert out["betting"]["value"] == 0.42
        assert out["betting"]["updated_at"] == T0.isoformat()

    def test_it_does_not_mutate_the_input(self):
        """These dicts come off a live ORM row; mutating one is gotcha #4 bait."""
        original = {"espn": 0.5}
        out = stamp_source_reading(original, "betting", 0.42, now=T0)
        assert original == {"espn": 0.5}
        assert out is not original

    def test_siblings_pass_through_untouched_in_whatever_shape_they_had(self):
        before = {
            "espn": 0.5,
            "mlb": {"value": 0.4, "updated_at": "2026-08-13T20:00:00+00:00"},
            "statpal_plays": [{"a": 1}],
        }
        out = stamp_source_reading(before, "betting", 0.42, now=T0)
        assert out["espn"] == 0.5
        assert out["mlb"] == before["mlb"]
        assert out["statpal_plays"] == [{"a": 1}]

    def test_none_input_is_accepted(self):
        assert stamp_source_reading(None, "mlb", 0.3, now=T0)["mlb"]["value"] == 0.3

    def test_a_naive_now_is_stamped_as_utc(self):
        out = stamp_source_reading({}, "mlb", 0.3, now=datetime(2026, 8, 13, 21, 0))
        assert out["mlb"]["updated_at"].endswith("+00:00")

    def test_round_trips_through_the_reader(self):
        out = stamp_source_reading({}, "betting", 0.42, now=T0)
        value, updated_at = parse_source_entry(out["betting"])
        assert value == 0.42
        assert updated_at == T0


class TestParseSourceEntry:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            (0.5, 0.5),
            (1, 1.0),
            ({"value": 0.5}, 0.5),
            ({"value": 0.5, "updated_at": "2026-08-13T21:00:00+00:00"}, 0.5),
            ({"value": None}, None),
            ({"no_value": 1}, None),
            ("0.5", None),
            (None, None),
            ([0.5], None),
            (True, None),
            ({"value": True}, None),
        ],
    )
    def test_shapes(self, raw, expected):
        assert parse_source_entry(raw)[0] == expected

    def test_booleans_are_not_probabilities(self):
        """`isinstance(True, int)` is True in Python, so this needs saying."""
        assert parse_source_entry(True) == (None, None)
        assert parse_source_entry({"value": False}) == (None, None)


# ── The invariant the whole thing exists to serve ────────────────────────────


def _source_sets():
    keys = ["mlb", "espn", "kalshi", "betting", "stat_model"]
    values = [0.0, 0.001, 0.05, 0.1347, 0.5, 0.565, 0.92, 1.0]
    out = []
    for i in range(len(values)):
        for j in range(1, len(keys) + 1):
            subset = keys[:j]
            out.append({k: values[(i + n) % len(values)] for n, k in enumerate(subset)})
    return out


class TestSameNumberInvariantStillHolds:
    """UX-P071's sweep, re-run against the new algorithm.

    The cap and the decay both change WHICH source the median lands on. Neither
    may change the fact that it lands on one, that it is a probability, or that
    it stays inside the envelope of its own inputs.
    """

    @pytest.mark.parametrize("sources", _source_sets())
    def test_deterministic_probability(self, sources):
        first = compute_aggregate_probability(_FakeEvent(sources))
        second = compute_aggregate_probability(_FakeEvent(dict(sources)))
        assert first == second
        assert first is None or 0.0 <= first <= 1.0

    @pytest.mark.parametrize("sources", _source_sets())
    def test_inside_its_own_envelope(self, sources):
        home = compute_aggregate_probability(_FakeEvent(sources))
        if home is None:
            return
        assert min(sources.values()) - 1e-9 <= home <= max(sources.values()) + 1e-9

    @pytest.mark.parametrize("sources", _source_sets())
    def test_envelope_holds_with_stamps_too(self, sources):
        """Same sweep, but every source aged differently. A decay that could
        push the blend outside its inputs would be inventing a number."""
        stamped = {
            k: {
                "value": v,
                "updated_at": (T0 - timedelta(seconds=600 * i)).isoformat(),
            }
            for i, (k, v) in enumerate(sources.items())
        }
        home = compute_aggregate_probability(_FakeEvent(stamped))
        if home is None:
            return
        assert min(sources.values()) - 1e-9 <= home <= max(sources.values()) + 1e-9

    def test_a_single_source_is_still_rendered_verbatim(self):
        for value in (0.0, 0.37, 1.0):
            assert compute_aggregate_probability(
                _FakeEvent({"espn": value})
            ) == pytest.approx(value)


class TestOneRuleAcrossAllThreeBlendPaths:
    """gotcha #128: a rule living in two consumers acquires two verdicts.

    The hero and the chart answer the SAME question, so a cap on one and not
    the other rebuilds the 87-13-header-vs-~0-chart contradiction from the
    other direction.
    """

    def test_compute_current_aggregate_caps_too(self):
        readings = {
            "mlb": (0.001, T0),
            "espn": (0.008, T0),
            "stat_model": (0.001, T0),
            "betting": (0.1347, T0),
            "kalshi": (0.565, T0),
        }
        assert compute_current_aggregate(readings, now=T0) == pytest.approx(0.008)

    def test_the_time_series_path_caps_too(self):
        from app.utils.aggregation import (
            TimestampedProb,
            compute_aggregated_probability,
        )

        series = {
            key: [TimestampedProb(timestamp=T0, home_probability=value)]
            for key, value in SPECIMEN_VALUES.items()
        }
        out = compute_aggregated_probability(series, bucket_seconds=30)
        assert out, "expected at least one bucket"
        assert out[-1].home_probability == pytest.approx(0.008, abs=1e-6)

    def test_hero_and_series_agree_on_the_specimen(self):
        """The same-number rule, on the exact payload that broke it."""
        from app.utils.aggregation import (
            TimestampedProb,
            compute_aggregated_probability,
        )

        hero = compute_aggregate_probability(_FakeEvent(dict(SPECIMEN_VALUES)))
        series = compute_aggregated_probability(
            {
                key: [TimestampedProb(timestamp=T0, home_probability=value)]
                for key, value in SPECIMEN_VALUES.items()
            },
            bucket_seconds=30,
        )
        assert hero == pytest.approx(series[-1].home_probability, abs=1e-6)


# ── Wire shape: the half that would have taken iOS down ──────────────────────


class TestWireShapeIsNormalised:
    """`_format_event` must emit `value` as a NUMBER.

    iOS types this `[String: WinProbValue]?` and `WinProbValue` THROWS on
    anything that is not a Double or a String. A throw inside `decodeIfPresent`
    propagates, so one object-shaped member fails `ESPNData`, which fails the
    whole `Event`. Stamping the column without normalising the serializer would
    have blanked the iOS event and search surfaces on every event that has
    sources — which is all of them.
    """

    def test_the_serializer_unwraps_the_stamped_shape(self):
        import inspect

        from app.routes import events as events_route

        src = inspect.getsource(events_route._format_event)
        assert "parse_source_entry" in src, (
            "_format_event must normalise win_probability_sources entries; "
            "assigning the raw entry double-nests it as {'value': {'value': x}}"
        )
        assert '"value": src_value' not in src, "raw entry is being passed through"

    def test_updated_at_is_a_sibling_key_never_nested_under_value(self):
        import inspect

        from app.routes import events as events_route

        src = inspect.getsource(events_route._format_event)
        idx = src.index('["updated_at"] = updated_at.isoformat()')
        assert idx > 0, "the write time should be exposed alongside value"


# ── The SQL-shape residual, pinned rather than remembered ────────────────────


class TestSqlShapeRatchet:
    """`(win_probability_sources->>'src')::float` RAISES on the stamped shape.

    `->>` on an object member yields the object's JSON text, and casting that to
    float dies — the neighbouring `IS NOT NULL` guard does not save it. This
    ratchet keeps the naive form out of anything that runs, and records the four
    dead one-off repair scripts that still contain it as a KNOWN, BOUNDED
    residual: none is imported, scheduled, or referenced by CI, and each now
    carries a `#1829 SHAPE WARNING` header pointing at `wps_numeric_sql`.

    If this test fails on a NEW file, do not add it to the allowlist — use
    `wps_numeric_sql()`.
    """

    ALLOWED = {
        "scripts/fix_1112_poly_inversion.py",
        "scripts/fix_207_peer_inversions.py",
        "scripts/fix_209_mlb_series_flip.py",
        "scripts/fix_wrong_game_scores.py",
    }

    # The module that DEFINES the safe helper necessarily contains the unsafe
    # form: once in the generated CASE's own number branch, once in the
    # docstring that shows what not to write.
    DEFINING_MODULE = "app/utils/aggregation.py"

    def test_no_new_naive_casts(self):
        """A cast is fine when a `jsonb_typeof` guard picks the branch for it.

        So the check is contextual, not textual — the FIRST draft matched the
        raw cast anywhere and reddened `source_intelligence._BETTING_CTE`, which
        is the correct, production-proven form this whole helper was modelled
        on. A ratchet that flags the fix as the bug gets deleted by the next
        person in a hurry.
        """
        import pathlib
        import re

        root = pathlib.Path(__file__).resolve().parents[1]
        pattern = re.compile(
            r"win_probability_sources->>\s*'[a-z_]+'\s*\)?\s*::\s*(float|numeric)"
        )
        offenders = set()
        for path in list(root.glob("app/**/*.py")) + list(root.glob("scripts/**/*.py")):
            rel = path.relative_to(root).as_posix()
            if rel == self.DEFINING_MODULE:
                continue
            try:
                text = path.read_text()
            except (OSError, UnicodeDecodeError):
                continue
            for match in pattern.finditer(text):
                window = text[max(0, match.start() - 400) : match.end() + 400]
                if "jsonb_typeof" not in window:
                    offenders.add(rel)
                    break
        assert offenders <= self.ALLOWED, (
            f"naive JSONB cast in {sorted(offenders - self.ALLOWED)} — use "
            f"app.utils.aggregation.wps_numeric_sql()"
        )

    def test_the_ratchet_is_not_vacuous(self):
        """It must still fire on an unguarded cast, or it guards nothing."""
        import re

        pattern = re.compile(
            r"win_probability_sources->>\s*'[a-z_]+'\s*\)?\s*::\s*(float|numeric)"
        )
        naive = "WHERE (win_probability_sources->>'betting')::float > 0.5"
        assert pattern.search(naive)
        assert "jsonb_typeof" not in naive

    def test_the_allowlisted_scripts_all_carry_the_warning(self):
        """An allowlist entry with no warning in the file is a rot vector."""
        import pathlib

        root = pathlib.Path(__file__).resolve().parents[1]
        for rel in sorted(self.ALLOWED):
            text = (root / rel).read_text()
            assert "#1829 SHAPE WARNING" in text, rel
            assert "wps_numeric_sql" in text, rel

    def test_wps_numeric_sql_handles_both_shapes(self):
        sql = wps_numeric_sql("betting")
        assert "jsonb_typeof" in sql
        assert "'number'" in sql and "'object'" in sql
        assert "->>'betting'" in sql
        assert "->'betting'->>'value'" in sql

    def test_wps_numeric_sql_refuses_an_unknown_source(self):
        """It interpolates, so the guard is the API, not a docstring plea."""
        with pytest.raises(ValueError):
            wps_numeric_sql("betting'; DROP TABLE events; --")
        with pytest.raises(ValueError):
            wps_numeric_sql("not_a_source")


# ── Every writer of the column goes through the stamper ──────────────────────


class TestEveryWriterStamps:
    """A writer that bypasses `stamp_source_reading` keeps its source at full
    weight forever, and looks exactly like a source that is simply always fresh.

    That is the invisible failure mode, so it gets a test rather than a note.
    """

    WRITERS = [
        ("app/tasks/odds_polling.py", 2),
        ("app/tasks/mlb_sync.py", 1),
        ("app/tasks/prediction_market_matching.py", 2),
        ("app/tasks/espn_sync.py", 1),
        ("app/tasks/backfill_combat_wps.py", 1),
        ("app/utils/espn_helpers.py", 3),
        ("app/routes/admin_matching.py", 1),
        ("app/routes/admin_providers.py", 2),
    ]

    @pytest.mark.parametrize("rel,expected", WRITERS)
    def test_writer_uses_the_stamper(self, rel, expected):
        import pathlib

        root = pathlib.Path(__file__).resolve().parents[1]
        text = (root / rel).read_text()
        assert "stamp_source_reading" in text, f"{rel} writes the column unstamped"

    def test_no_writer_assigns_a_bare_number_into_the_column(self):
        """The shape that bypasses the stamper, as a pattern rather than a list."""
        import pathlib
        import re

        root = pathlib.Path(__file__).resolve().parents[1]
        # `_wps["betting"] = round(x, 4)` and friends.
        naive = re.compile(
            r"\[[\"'](betting|espn|stat_model|mlb|kalshi|polymarket|final_result)"
            r"[\"']\]\s*=\s*(?!.*stamp_source_reading)"
        )
        offenders = []
        for rel, _ in self.WRITERS:
            for i, line in enumerate((root / rel).read_text().splitlines(), 1):
                if naive.search(line) and "updated_at" not in line:
                    offenders.append(f"{rel}:{i}: {line.strip()}")
        assert not offenders, "unstamped source assignment:\n" + "\n".join(offenders)
