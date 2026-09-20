"""#3655: a residual run lock must die before the entry it protects.

**The defect, as an equality nobody wrote down together.** `_LOCK_TTL_SECONDS`
was the literal `180` and `SEARCH_RESPONSE_TTL_SECONDS` is `180`.
`residency_invariant()` compared the lock with the PASS — clause (6),
`budget < lock_ttl`, 70 < 180, passing by 110 s — and never compared it with the
ENTRY. So the ordinary lost release (a walled compare-and-delete, or a
`worker-background` child recycled mid-pass under `--max-memory-per-child`)
suppressed every pass for exactly as long as the entry the passes exist to keep
alive had left to live, and `/search` served its cold path for the whole of it.
Nothing logged a fault: the skips read `lock`, which is the ordinary word for
"another pass has it".

The sibling `typeahead_warmer` shipped the same shape at 120 s against a 65 s
entry and MEASURED it (#3398): the head entirely cold 20.0 % of the wall clock,
five write-gaps over the TTL in 604 s, worst 267.7 s.

**What this file guards, and it is three things rather than one:**

1. the relation itself — `residual_lock_recovery_s() < SEARCH_RESPONSE_TTL_SECONDS`,
   as clause (8), with the shipped `180` refused BY NAME;
2. that the TTL reaching Redis is the DERIVED one and is a whole second
   (`SET ... EX` on a float raises `DataError`, and no fake client will tell you);
3. that shortening the lock did not quietly halve the beat's `expires`, which
   used to be derived from this very constant (#3364).

(3) is the half a reader is most likely to miss, and it is why this is not a
one-line test: the repair and its side effect live in different functions, and
the side effect is invisible from the page it would make slow.
"""

import math

import pytest
from redis.exceptions import DataError

from app.tasks import search_head_warmer as warmer
from app.utils.search_cache import SEARCH_RESPONSE_TTL_SECONDS

#: The literal this repair removed. Written here so the regression input has a
#: name: restoring it is a one-character-class edit that reads like tidying.
SHIPPED_LITERAL_BEFORE_3655 = 180


class TestAResidualLockDiesBeforeTheEntry:
    def test_the_recovery_from_a_lost_release_fits_inside_one_entry_life(self):
        """The whole claim, in the two numbers it is a comparison between."""
        recovery = warmer.residual_lock_recovery_s()
        assert recovery < SEARCH_RESPONSE_TTL_SECONDS, (
            f"a lost release keeps a query cold for {recovery}s against a "
            f"{SEARCH_RESPONSE_TTL_SECONDS}s entry life — the entry dies before the "
            f"warmer is allowed to rewrite it and /search serves the cold path"
        )

    def test_the_shipped_literal_is_refused_by_name(self):
        """WHAT THIS GATE HAS TO SEE TO GO RED: `_LOCK_TTL_SECONDS = 180` restored.

        The value is not merely unfashionable, it is refused, and the refusal
        names the reader's symptom rather than an inequality.
        """
        ok, why = warmer.residency_invariant(lock_ttl_s=SHIPPED_LITERAL_BEFORE_3655)
        assert not ok, (
            f"180s — the pre-#3655 literal, and the exact life of the entry — is "
            f"accepted by the invariant: {why}"
        )
        assert "RESIDUAL LOCK OUTLIVES THE ENTRY" in why
        assert "cold path" in why

    def test_the_clause_is_not_the_naive_comparison_with_the_ttl(self):
        """120s is under the 180s entry life and is still a hole. **The separator.**

        A clause written as `lock_ttl < ttl` would pass this input, and passing it
        is the defect: after the key expires a fire still has to arrive (one beat)
        and the rebuild still has to reach THIS query (the budget, since a
        re-ranked pass can write it last — clause (4)'s argument). 120 + 20 + 70 =
        210 against 180.
        """
        ok, why = warmer.residency_invariant(lock_ttl_s=120)
        assert not ok, "a 120s lock leaves a 30s hole and the invariant accepted it"
        assert "RESIDUAL LOCK OUTLIVES THE ENTRY" in why

    def test_the_recovery_is_the_sum_and_not_the_ttl(self):
        """The three terms are all present, asserted as an identity not a range."""
        assert warmer.residual_lock_recovery_s(
            lock_ttl_s=100, beat_s=20, floor_s=45, budget_s=70
        ) == 190
        # The floor binds instead of the TTL when the TTL is the smaller clock —
        # both run from the same instant, the wedged pass's start.
        assert warmer.residual_lock_recovery_s(
            lock_ttl_s=10, beat_s=20, floor_s=45, budget_s=70
        ) == 135


class TestTheTtlIsSolvedForRatherThanPicked:
    def test_the_shipped_constant_is_the_derived_one(self):
        assert warmer._LOCK_TTL_SECONDS == warmer.derive_lock_ttl_s()

    def test_it_moves_when_the_entry_life_moves(self):
        """A constant that does not move with its inputs is a literal in disguise.

        #3539 contemplated moving the response TTL; at 300s the lock must follow,
        and the direction is the one the arithmetic gives, not the one that keeps
        the old number.
        """
        assert warmer.derive_lock_ttl_s(ttl_s=300) == 140
        assert warmer.derive_lock_ttl_s(ttl_s=300) != warmer.derive_lock_ttl_s()

    def test_both_ends_of_the_window_are_enforced(self):
        """Clause (6) below, clause (8) above — two defects, not two readings.

        Named inputs: a 60s lock is overtaken by its own 70s-budget pass; a 100s
        lock recovers in 190s against a 180s life.
        """
        ok_low, why_low = warmer.residency_invariant(lock_ttl_s=60)
        assert not ok_low and "OUTRUNS ITS OWN LOCK" in why_low
        ok_high, why_high = warmer.residency_invariant(lock_ttl_s=100)
        assert not ok_high and "RESIDUAL LOCK OUTLIVES THE ENTRY" in why_high
        # And the derived value is strictly inside that window.
        assert 70 < warmer._LOCK_TTL_SECONDS < 90

    def test_an_empty_window_is_refused_rather_than_clamped(self):
        """A budget of 80s at a 180s life leaves nothing: (80, 80).

        A derivation that returned the nearest plausible number here would ship a
        lock that is wrong at one end and say nothing about it.
        """
        with pytest.raises(ValueError, match="window is empty"):
            warmer.derive_lock_ttl_s(budget_s=80)
        with pytest.raises(ValueError, match="window is empty"):
            warmer.derive_lock_ttl_s(ttl_s=100)
        for bad in ({"ttl_s": 0}, {"beat_s": -20.0}, {"budget_s": 0}):
            with pytest.raises(ValueError, match="must all be positive"):
                warmer.derive_lock_ttl_s(**bad)

    def test_a_window_with_no_whole_second_is_refused_too(self):
        """`SET ... EX` takes integers, so a window can be non-empty and unusable."""
        with pytest.raises(ValueError, match="no whole second"):
            # (70.2, 70.8): real, open, and containing no integer.
            warmer.derive_lock_ttl_s(ttl_s=161.0, beat_s=20.0, budget_s=70.2)

    def test_the_rounding_spends_the_fraction_on_the_readers_side(self):
        """Floor, not round: below the midpoint costs duplicate warming, above it
        costs a reader a cold page."""
        mid_is_fractional = warmer.derive_lock_ttl_s(ttl_s=181.0)
        assert mid_is_fractional == math.floor((181.0 - 20.0) / 2.0) == 80


class TestWhatRedisIsActuallyGiven:
    """The constant and the call site are two facts, and a fake hides the second."""

    class _TypeCheckingRedis:
        """Rejects an `ex` that redis-py would reject, and nothing else.

        `redis.commands.core.extract_expire_flags` raises
        `DataError("ex must be datetime.timedelta or int")` on a float. A
        derivation returning `80.0` therefore fails EVERY acquire on production
        while a permissive fake — the kind every other test in this module
        uses — records a healthy `SET` and passes.
        """

        def __init__(self):
            self.sets: list[tuple[str, str, int]] = []
            self.store: dict[str, str] = {}

        def set(self, key, value, nx=False, ex=None):
            if not isinstance(ex, int) or isinstance(ex, bool):
                raise DataError("ex must be datetime.timedelta or int")
            if nx and key in self.store:
                return None
            self.store[key] = value
            self.sets.append((key, value, ex))
            return True

    def test_the_derived_ttl_is_what_the_acquire_sends(self, monkeypatch):
        client = self._TypeCheckingRedis()
        monkeypatch.setattr(warmer, "_lock_control_client", lambda: client)

        assert warmer._acquire_blocking("tok-3655") == "tok-3655"

        assert client.sets == [(warmer._LOCK_KEY, "tok-3655", warmer._LOCK_TTL_SECONDS)]
        # Severed from the constant on purpose: the assertion above passes if the
        # call site hardcodes whatever `_LOCK_TTL_SECONDS` happens to be, so the
        # relation the reader cares about is asserted against the ENTRY, here.
        sent_ttl = client.sets[0][2]
        assert (
            warmer.residual_lock_recovery_s(lock_ttl_s=sent_ttl)
            < SEARCH_RESPONSE_TTL_SECONDS
        ), f"the acquire installs a {sent_ttl}s lock, which outlives the entry"

    def test_a_float_ttl_would_have_been_caught_here(self, monkeypatch):
        """The fake earns its keep: prove it rejects what production rejects."""
        client = self._TypeCheckingRedis()
        monkeypatch.setattr(warmer, "_lock_control_client", lambda: client)
        monkeypatch.setattr(warmer, "_LOCK_TTL_SECONDS", 80.0)
        with pytest.raises(DataError):
            warmer._acquire_blocking("tok-float")


class TestTheBeatsDeliveryBoundDidNotMoveWithIt:
    """#3364's repair must survive #3655's. It nearly did not.

    `derive_message_expiry_s` took `lock_ttl_s=_LOCK_TTL_SECONDS`, so shortening
    the lock 180 -> 80 would have cut the beat's `expires` by the same factor —
    on a beat whose delivered-fire ratio #3364 measured to track that exact
    number (300 -> 0.87, 120 -> 0.37, 110 -> 0.23, 20 -> 0.03), and whose
    starvation symptom is the same cold search box this repair is about.
    """

    def test_the_expiry_derives_from_the_entry_life_not_the_lock(self):
        assert warmer.derive_message_expiry_s() == float(SEARCH_RESPONSE_TTL_SECONDS)
        assert warmer.derive_message_expiry_s() != float(warmer._LOCK_TTL_SECONDS)

    def test_the_wired_beat_bound_did_not_move(self):
        """The value is unchanged at 180; only what it is a fact ABOUT changed."""
        from app.tasks import _EXPIRING_WARMER_BEATS

        assert _EXPIRING_WARMER_BEATS["warm-search-head"] == 180
        assert _EXPIRING_WARMER_BEATS["warm-search-head"] == (
            warmer.derive_message_expiry_s()
        )

    def test_the_expiry_still_covers_everything_the_warmer_itself_holds_off(self):
        """The old argument's obligation, discharged against the new bound.

        A message this warmer could be holding off must survive: the longest the
        warmer can withhold a slot is now the residual-lock wedge.
        """
        assert warmer.derive_message_expiry_s() > warmer._LOCK_TTL_SECONDS

    def test_shortening_the_lock_alone_does_not_touch_the_expiry(self):
        """The mutation this class exists for: re-couple the two and go red."""
        assert warmer.derive_message_expiry_s(entry_life_s=180) == 180.0
