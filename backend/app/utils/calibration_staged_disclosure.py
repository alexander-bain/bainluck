"""#2007 — the served calibration payload dates its own inputs.

**Publishing is not freshness. An artifact that does not date its inputs is
undated, whatever its timestamp says.** (Doctrine, CAL-P076; ruling 095 arriving
from the opposite direction — there a freeze with no expiry, here a republish
with no as-of.)

The defect this closes, measured 2026-08-19
-------------------------------------------
``/api/calibration`` served ``availability: fresh``, ``producer.beats_missed:
0``, ``producer.stalled: false`` and a ``generated_at`` two minutes old — over a
futures curve that had not been re-read in **six hours**:

===============================================  =========================
``durable_state_snapshots['calibration:main']``  ``2026-08-19T23:17:13Z``
``…['calibration:main:staged_futures']``         ``2026-08-19T17:16:31Z``
``staged:units_banked`` / ``units_this_beat``    ``128`` / **0**
``staged:units_drifted`` of ``…_drift_checkable`` **115** of ``127``
===============================================  =========================

The staged bank is complete, so ``is_complete(cursor, chunks)`` — ``planned ==
committed`` over SLOT keys, every slot planned every beat — is ``True``
*forever*; and CAL-P016 deliberately removed the generation fingerprint from the
invalidation list, without which the build never converges. So every beat
re-serialises the same 128 banked units under a brand-new ``generated_at``.
Nothing here proposes changing either of those: the census is a coherent read of
a slightly older population, which is the documented CAL-P016 trade-off. What
was missing is that **the payload never said so**.

Why that is worse than the stale instrument it replaced: the previous failure
(#1680) was stale *and announced it* — ``availability: degraded``, ``generated_at``
visibly pinned. This one reads green in every field a consumer has. It is gotcha
#53's shape — one observable standing in for two different facts, resolving to
the reassuring reading by default — on the product's most-cited number. And it
is not merely cosmetic: an attended #1912 apply writes rows the frozen bank never
re-reads, so a grader reading ``/api/calibration`` sees no movement and concludes
the apply did nothing (hence CAL-P076 ruling (c): the #1912 wave grades DB-direct).

What this module decides, and what it deliberately does not
-----------------------------------------------------------
Fable's fix order (CAL-P076 ruling (b)) is **disclosure first, mechanism second**:
the payload carries ``staged_at`` and ``units_drifted`` and availability reflects
them; the bounded incremental re-stage of drifted units per beat is a separate,
later change. So this module is read-side only. It touches no writer, no cursor,
no fingerprint — ``precompute_calibration.py`` stays frozen under ruling 009 and
``_main_input_fingerprint()`` does not move, so the bank this discloses is not
destroyed by the act of disclosing it.

Everything here is pure. The two durable rows are read by the caller and passed
in, because the decision — *may this be called fresh?* — is testable and the read
is not.

The availability rule, and why it is this one
---------------------------------------------
``fresh`` is refused when the bank is **frozen over drift**::

    frozen_over_drift = (units_this_beat == 0) and not drift_known_zero
    drift_known_zero  = (units_drifted == 0 and units_drift_unknown == 0)

Three properties were wanted and no threshold satisfies all three, so none is
invented:

* **It is satisfiable by the ruled fix.** Once the bounded incremental re-stage
  lands, a beat with drift re-stages some of it, ``units_this_beat > 0``, and
  ``fresh`` renders again. A census-age bound could not do this: the bank takes
  ~13 beats to build, so any age bound tight enough to catch a 6-hour freeze
  would also condemn a healthy just-completed bank.
* **It fires today and clears itself.** No operator has to pick a drift
  percentage that is "too much", and nobody has to re-tune it when the partition
  count changes.
* **Unknown is never the reassuring reading.** ``units_drift_uncheckable`` counts
  banked units carrying no digest — CAL-P069's find, where 6 unmeasurable units
  published as ``units_drifted: 0``. A zero drift reading only earns
  ``drift_known_zero`` when every banked unit was actually checkable, and an
  unreadable disclosure refuses ``fresh`` outright (``measured: false``).

``stale``, not ``degraded``, is the word: what is served is a *whole, coherent*
copy of the pool whose only compromise is age (ruling 025's definition). Nothing
is partial and nothing is substituted.

One honesty note that the field names carry deliberately: ``units_drifted`` is
itself as-of ``staged_at``, not as-of the publish. The ledger re-records it every
beat, but it reads it off the cursor, whose ``roster_drift_units`` was measured at
the start of the beat that last WROTE the cursor. So a frozen bank freezes its own
drift counter too, and the real drift is ``>=`` the number published. That is why
``units_drifted_as_of`` exists and equals ``staged_at`` rather than
``generated_at``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from app.utils.availability_envelope import AVAILABILITY_STALE

#: Top-level payload key. One block, so a consumer reads the as-of and the drift
#: from the same place it reads ``producer``.
STAGED_FIELD = "staged"

#: Gauge names, owned by ``app.tasks.calibration_main_build`` and re-stated here
#: because this module has to read them. Greppable in both directions on purpose:
#: a rename that misses one of these sites shows up as ``measured: false``, which
#: refuses ``fresh`` — the safe direction.
GAUGE_UNITS_BANKED = "staged:units_banked"
GAUGE_UNITS_THIS_BEAT = "staged:units_this_beat"
GAUGE_UNITS_DRIFTED = "staged:units_drifted"
GAUGE_UNITS_DRIFT_CHECKABLE = "staged:units_drift_checkable"
GAUGE_UNITS_DRIFT_UNCHECKABLE = "staged:units_drift_uncheckable"

# -- CAL-P078: the SERVING bank's own gauges ----------------------------------
# After the rolling re-stage there are two banks, and every gauge above this
# line describes the one being BUILT. The block this module publishes is about
# the one being SERVED, so where these are present they take precedence — see
# :func:`build_disclosure` for the two readings that had to change with them.
GAUGE_SERVED_UNITS = "staged:served_units"
GAUGE_SERVED_DRIFTED = "staged:served_drifted"
GAUGE_SERVED_DRIFT_UNCHECKABLE = "staged:served_drift_uncheckable"
GAUGE_SERVED_AT = "staged:served_at"


def unmeasured(reason: str) -> dict[str, Any]:
    """The disclosure for "this could not be read".

    Never an empty dict and never a zeroed one. An absent block and a healthy
    block must not look alike to a consumer, and a zero drift figure invented by
    a failed read is the exact empty-200 mistake this whole module is about.
    """
    return {"measured": False, "reason": str(reason)}


def _int_gauge(stages: Mapping[str, Any], name: str) -> Optional[int]:
    """A ledger gauge as an int, or ``None`` — never a defaulted zero.

    Gauges are written by ``PhaseLedger.record_gauge`` as ints, but the value
    makes a round trip through JSONB and back, and a payload written by an older
    build may not carry the key at all. ``bool`` is excluded explicitly: it is an
    ``int`` subclass and would silently rate ``True`` as 1.
    """
    value = stages.get(name)
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def _iso(moment: Optional[datetime]) -> Optional[str]:
    if not isinstance(moment, datetime):
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).isoformat()


def build_disclosure(
    *,
    ledger_stages: Any,
    staged_generated_at: Any,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """The ``staged`` block for one served payload. Pure.

    ``ledger_stages`` is ``calibration:main:phase_ledger``'s ``payload["stages"]``
    and ``staged_generated_at`` is the ``generated_at`` of the
    ``calibration:main:staged_futures`` durable row — the instant the bank last
    advanced, which is the whole point of the block.

    Either input being unusable yields :func:`unmeasured`, because a disclosure
    that has to guess at half of itself is not a disclosure. The two are reported
    as separate reasons so an operator can tell a missing bank from a missing
    ledger without going to the database.
    """
    if not isinstance(ledger_stages, Mapping):
        return unmeasured("ledger_stages_unreadable")

    # -- CAL-P078: prefer the SERVING bank, and say so in every field ---------
    # Two readings had to change with the rolling re-stage, and BOTH of them
    # would otherwise have re-manufactured #2007 in a new shape:
    #
    # 1. ``staged_generated_at`` — the durable row's write time — used to be the
    #    instant the bank last advanced, because a beat that banked nothing never
    #    rewrote the row. Now every beat re-stages units, so it advances every
    #    beat while the SERVED census may be five beats old. Using it would put
    #    a fresh timestamp back on a stale curve, which is the exact bug.
    # 2. ``bank_advanced_this_beat`` used to be evidence that the served census
    #    had moved. It no longer is: the BUILDER always advances now. So the
    #    freeze verdict below is computed from the served bank's own drift, and
    #    the builder's progress is published beside it under its own name.
    served_units = _int_gauge(ledger_stages, GAUGE_SERVED_UNITS)
    served_at_epoch = _int_gauge(ledger_stages, GAUGE_SERVED_AT)
    serving = served_units is not None

    banked = _int_gauge(ledger_stages, GAUGE_UNITS_BANKED)
    if serving:
        banked = served_units
    if banked is None:
        # The convergence reader records ``staged:convergence_reason:<status>``
        # when it cannot read the cursor. Surface it rather than reporting a
        # generic absence: the distinction between "nothing banked" and "the
        # reader broke" is the one CAL-P028 was written to stop collapsing.
        for key in ledger_stages:
            if isinstance(key, str) and key.startswith("staged:convergence_reason:"):
                return unmeasured(key)
        return unmeasured("units_banked_absent")

    staged_dt = staged_generated_at
    if serving:
        if served_at_epoch is None:
            # A serving bank that has not been dated yet — promoted, not yet
            # stamped, or stamped by a build that died between the two. It is
            # UNMEASURED rather than fall back to the durable row's write time,
            # which after CAL-P078 is the publish clock wearing the census's
            # name. That substitution IS #2007.
            return unmeasured("served_at_absent")
        staged_dt = datetime.fromtimestamp(served_at_epoch, tz=timezone.utc)

    staged_at = _iso(staged_dt)
    if staged_at is None:
        return unmeasured("staged_at_absent")

    reference = now or datetime.now(timezone.utc)
    if staged_dt.tzinfo is None:
        staged_dt = staged_dt.replace(tzinfo=timezone.utc)
    staged_age_s = round((reference - staged_dt).total_seconds())

    this_beat = _int_gauge(ledger_stages, GAUGE_UNITS_THIS_BEAT)
    drifted = _int_gauge(ledger_stages, GAUGE_UNITS_DRIFTED)
    checkable = _int_gauge(ledger_stages, GAUGE_UNITS_DRIFT_CHECKABLE)
    uncheckable = _int_gauge(ledger_stages, GAUGE_UNITS_DRIFT_UNCHECKABLE)
    if serving:
        drifted = _int_gauge(ledger_stages, GAUGE_SERVED_DRIFTED)
        uncheckable = _int_gauge(ledger_stages, GAUGE_SERVED_DRIFT_UNCHECKABLE)
        # There is no served analogue of ``units_drift_checkable``; the
        # uncheckable count is recorded directly, so the derived one below must
        # not be computed from a checkable figure that describes the OTHER bank.
        checkable = None if uncheckable is None else max(0, banked - uncheckable)

    # Two independent expressions of the same gap, and they can disagree: the
    # uncheckable gauge is written only when the cursor carries a digest map at
    # all. Take the larger, because under-reporting how much is unmeasurable is
    # the direction that manufactures a reassuring zero.
    derived_unknown = None if checkable is None else max(0, banked - checkable)
    if derived_unknown is None:
        unknown = uncheckable
    elif uncheckable is None:
        unknown = derived_unknown
    else:
        unknown = max(derived_unknown, uncheckable)

    drift_known_zero = drifted == 0 and unknown == 0
    # ``units_this_beat`` absent is not zero. A beat that never reached the
    # recording site tells us nothing about whether the bank advanced, so it must
    # not be read as "it did not" — but it equally must not be read as "it did".
    # ``advanced`` stays ``None`` and the freeze verdict below refuses to claim
    # either way, which lands on "not fresh" via ``measured`` staying honest.
    advanced = None if this_beat is None else this_beat > 0
    if serving:
        # The builder advances every beat now, so its progress says NOTHING
        # about whether the census being served has moved. The served bank is
        # honest exactly when it has no drift; that is the whole verdict.
        frozen_over_drift = not drift_known_zero
    else:
        frozen_over_drift = (advanced is not True) and not drift_known_zero

    block = {
        "measured": True,
        # The instant the futures bank last advanced. NOT the publish time.
        # Under CAL-P078 this is the instant the SERVED census was completed,
        # which is the only reading a consumer can compute a row age from.
        "staged_at": staged_at,
        "staged_age_s": staged_age_s,
        "units_banked": banked,
        "units_this_beat": this_beat,
        "units_drifted": drifted,
        "units_drift_checkable": checkable,
        "units_drift_unknown": unknown,
        # Drift is measured off the cursor, so it ages with the cursor, not with
        # the publish. Stated rather than left for a reader to deduce.
        "units_drifted_as_of": staged_at,
        "bank_advanced_this_beat": advanced,
        "frozen_over_drift": frozen_over_drift,
    }
    if serving:
        # Published beside the served figures rather than folded into them: a
        # reader who wants to know the rebuild is ALIVE needs a different number
        # from the one that says how old the curve is, and collapsing the two is
        # how "the build is fine" came to stand in for "the curve is current".
        block["rebuild_units_this_beat"] = this_beat
        block["rebuild_units_banked"] = _int_gauge(ledger_stages, GAUGE_UNITS_BANKED)
        block["rolling_restage"] = True
    return block


def availability_floor(disclosure: Any) -> Optional[str]:
    """The weakest word the staged bank permits, or ``None`` for no opinion.

    ``None`` means this module is not asking for a downgrade — never that it
    approves of one. Callers clamp with ``never_stronger``, so this can only ever
    move a declaration down.
    """
    if not isinstance(disclosure, Mapping):
        return AVAILABILITY_STALE
    if disclosure.get("measured") is not True:
        # Ruling (b), literally: ``fresh`` may not render while drift is
        # undisclosed. An unreadable disclosure is undisclosed drift.
        return AVAILABILITY_STALE
    if disclosure.get("frozen_over_drift"):
        return AVAILABILITY_STALE
    return None
