"""What a settlement source ACTUALLY said — and, more importantly, what it did not.

Queue 389 Item 1 (#2077). This module is the correctness core of the settlement-truth
capture sweep, and it exists to answer exactly one question honestly:

    Did the source affirmatively state a settlement, or did something else happen?

**Nothing here grades anything.** There is deliberately no function in this module
that returns a winner for storage on ``futures_outcomes.is_winner``, and no caller
may derive one from a disposition other than :attr:`Disposition.SETTLED`.

THE WHOLE PROBLEM, WHICH IS GOTCHA #53
--------------------------------------

An empty 200 is not an absence — it is a response shape. Both of our settlement
sources answer "there is nothing here" and "I no longer keep this" with bodies that
are byte-identical to "this never settled":

* Kalshi ``GET /events/{ticker}`` answers **200 with ``markets: []``** for an event
  whose markets have been purged past the retention cliff — it does not 404.
* Kalshi ``GET /markets/trades`` answers **200 with ``trades: []``** for a purged
  market exactly as it does for a real market that never traded. (This module never
  consults ``/trades`` for truth, for that reason.)
* Polymarket Gamma ``/markets?condition_ids=`` answers **200 with ``[]``** for a
  condition it does not index, which is not the same claim as "this did not settle".

The failure this prevents is not a crash. It is a **manufactured fact**: a sweep that
reads the emptier response as "the source says no settlement" writes false ground
truth, and false ground truth is indistinguishable from real ground truth forever
after. #683 sat open as a P0 for ten weeks while a backfill recorded SUCCESS every
6h precisely because "500 fetched, 500 empty, 0 created" and "nothing to do" render
identically.

So the type this module returns is a **discriminated disposition**, never an
``Optional[dict]``. ``Optional[dict]`` is the bug: it is a type that cannot express
the difference between "no settlement" and "no answer", so every caller that holds
one is one ``if x is None`` away from inventing a fact. ``KalshiAPIService.get_market``
is the live example — its docstring says "Returns None only for 404" while its body
ends in ``except Exception: return None``, which is gotcha #36 exactly.

WHAT IS AND IS NOT A FACT
-------------------------

Four dispositions are *claims by the source about the market*:
:attr:`Disposition.SETTLED`, :attr:`Disposition.OPEN_NO_SETTLEMENT`,
:attr:`Disposition.SETTLED_NO_VERDICT` and :attr:`Disposition.SETTLED_PER_LEG`.
Everything else is a claim about the **transport or the retention policy**, and
must never be folded into a statement about the market.
:meth:`Disposition.is_source_claim` is the predicate; the capture writer refuses to
persist a settlement payload for anything else.

**BEING A CLAIM AND LICENSING A WRITE ARE DIFFERENT QUESTIONS**, and the two
``settled_*`` members above exist because conflating them is expensive.
``SETTLED_NO_VERDICT`` is a real settlement on a NUMBER — 38% of the settled Kalshi
legs measured for #2077 — and grading it would manufacture ~1,800 false verdicts.
``SETTLED_PER_LEG`` is a real settlement of a MULTI-LEG BOARD, which has no single
winner to name. Neither returns True from :meth:`Disposition.licenses_grading`; the
per-leg licence rides each :class:`LegSettlement` instead.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.utils.kalshi_market_status import (
    KNOWN_STATUSES,
    NON_VERDICT_RESULTS,
    gradeable_winner,
    settled_without_verdict,
)


class Disposition(str, Enum):
    """The only vocabulary a probe may answer in.

    Ordered from "the source told us something about the market" down through "the
    source told us something about itself" to "we learned nothing at all". The
    distinction between the second and third groups is the one that keeps a sweep
    honest about its own coverage; the distinction between the first and everything
    else is the one that keeps it from manufacturing ground truth.
    """

    #: The source affirmatively reported a settled result. **The only disposition
    #: from which a winner may ever be read.**
    SETTLED = "settled"

    #: The source affirmatively reported the market exists and has NOT settled.
    #: A real fact about the market, and a real finding when our DB says resolved.
    OPEN_NO_SETTLEMENT = "open_no_settlement"

    #: The source settled this market **in a language that names no winner** —
    #: Kalshi's ``status=finalized result=scalar``, which settles on a NUMBER
    #: rather than a side, and the ``void``/``cancelled`` family.
    #:
    #: A terminal fact about the market, and the disposition this module was
    #: missing. Both of its neighbours are wrong for it, in opposite and equally
    #: expensive directions: read as :attr:`SETTLED` it writes the literal string
    #: ``"scalar"`` into a winning-outcome column (#1852 — it poisons the
    #: calibration curve), and read as :attr:`OPEN_NO_SETTLEMENT` it leaves a
    #: live-looking price on a question that is over and comes back for a re-probe
    #: that can never answer differently (#7987).
    #:
    #: **It licenses a price-down and NOTHING else.** :meth:`licenses_grading` is
    #: False here deliberately and permanently: 38% of the settled Kalshi legs
    #: measured for #2077 are this shape, so a reader that grades them
    #: manufactures ~1,800 false verdicts — #6619 at roughly three times scale.
    SETTLED_NO_VERDICT = "settled_no_verdict"

    #: The source settled a MULTI-LEG board, and the verdicts are per leg —
    #: carried in :attr:`ProbeOutcome.leg_claims`, never in a single ``claim``.
    #:
    #: Kalshi answers ``GET /events/{ticker}`` with every nested market's own
    #: ticker, status and result. A board has no one winner to report (a 400-rung
    #: threshold ladder settles 216 legs ``yes`` and 184 ``no``), so synthesising
    #: one would be a lie and there is deliberately no way to represent it: this
    #: disposition may not carry a ``claim``.
    #:
    #: **This disposition licenses nothing.** :meth:`licenses_grading` is False —
    #: the licence is per leg, and each :class:`LegSettlement` carries its own
    #: disposition for :func:`assert_grading_licensed` to read. Emitted only when
    #: EVERY leg has declared, so that a board with one leg still trading stays
    #: non-terminal and comes back rather than stranding it.
    SETTLED_PER_LEG = "settled_per_leg"

    #: The source affirmatively reported that it no longer retains this record —
    #: e.g. Kalshi's event exists but ``markets: []`` past the retention cliff.
    #: A fact about RETENTION, not about the market. The settlement is unknowable,
    #: not absent.
    PURGED = "purged"

    #: The source reported no such identifier (a real 404 on the identity lookup,
    #: with no corroborating record). Distinct from :attr:`PURGED`: this is "I never
    #: had this", not "I had this and dropped it". Usually means our external_id is
    #: wrong, which is OUR bug and routes differently.
    NOT_FOUND = "not_found"

    #: A 200 whose body cannot distinguish absence from emptiness, and for which no
    #: second channel resolved it. **This is not a fact.** It is the gotcha #53 shape
    #: recorded under its own name so it can never be silently counted as either
    #: "no settlement" or "purged".
    AMBIGUOUS_EMPTY = "ambiguous_empty"

    #: 429. Not a fact. Retry; never interpret. (gotcha #36: a rate limit that
    #: reads as "not found" is how the Kalshi backfill appeared to "decelerate".)
    RATE_LIMITED = "rate_limited"

    #: Timeout, connection failure, 5xx, or an unparseable body. Not a fact.
    TRANSPORT_ERROR = "transport_error"

    #: The source still HOLDS the record, and the record's form can never yield a
    #: winner — Polymarket's ``no_resolved`` class (C-DEGRADED-FORM-1, ~8k markets,
    #: all 365+ days old): present, closed, and carrying no ``outcomePrices`` at all.
    #:
    #: Distinct from :attr:`AMBIGUOUS_EMPTY` in the way that matters most, which is
    #: **permanence**. Ambiguity is a gap in what we asked; this is a gap in what
    #: exists, and re-probing it forever spends budget to re-learn the same nothing.
    #: Distinct from :attr:`PURGED` too: nothing was lost to retention — Polymarket
    #: has no cliff (0 of 70 records gone across 30 days to 3.66 years) — the record
    #: simply never carried a price. **It belongs OUT of the recoverable denominator,
    #: which is why it gets a name instead of being folded into a failure bucket.**
    PRICE_UNDETERMINABLE = "price_undeterminable"

    #: We declined to probe: the market is older than the provably-purged horizon,
    #: so a call could only waste budget. Recorded rather than skipped silently, so
    #: "we did not look" never reads as "we looked and found nothing".
    NOT_PROBED_BEYOND_HORIZON = "not_probed_beyond_horizon"

    def is_source_claim(self) -> bool:
        """True only when the source made a statement ABOUT THE MARKET.

        The capture writer gates the settlement payload on this. ``PURGED`` is
        excluded deliberately: it is a true statement, but about Kalshi's retention
        policy, and a sweep that counts it as market knowledge would report the
        cliff as good news.
        """
        return self in (
            Disposition.SETTLED,
            Disposition.OPEN_NO_SETTLEMENT,
            Disposition.SETTLED_NO_VERDICT,
            Disposition.SETTLED_PER_LEG,
        )

    def is_retryable(self) -> bool:
        """True when re-probing later could still produce a fact.

        ``PURGED`` is NOT retryable — the window closed, and retrying it forever is
        how a sweep spends its budget on the already-dead instead of the dying
        (gotcha #41's inverse, the CAL-P009 lesson). ``PRICE_UNDETERMINABLE`` is not
        retryable for the mirror-image reason: nothing was lost, and nothing will
        ever arrive.
        """
        return self in (
            Disposition.AMBIGUOUS_EMPTY,
            Disposition.RATE_LIMITED,
            Disposition.TRANSPORT_ERROR,
        )

    def licenses_grading(self) -> bool:
        """The single predicate any future grading consumer must call.

        Deliberately narrower than :meth:`is_source_claim` and deliberately not a
        simple ``== SETTLED`` comparison at the call site: a named predicate is
        greppable, and a future reader widening it has to widen it HERE, in a file
        whose whole subject is why that would be wrong.

        **TWO SETTLED-SOUNDING DISPOSITIONS ARE EXCLUDED, AND NEITHER IS AN
        OVERSIGHT.** This is the widening a reader arrives here intending to make,
        so the answer is written down rather than left to be re-derived:

        * :attr:`SETTLED_NO_VERDICT` — the venue answered, on a number. There is
          no side to write. Admitting it here is the #6619 failure at ~3x scale.
        * :attr:`SETTLED_PER_LEG` — the venue answered, per leg. The board itself
          has no verdict, and :attr:`ProbeOutcome.claim` is structurally None for
          it, so a caller widening this predicate would gain a licence and still
          have nothing to write. **The licence it wants is per leg**: every
          :class:`LegSettlement` carries its own disposition, and passing that to
          :func:`assert_grading_licensed` is the supported path. Per-leg grading
          therefore needed no widening here at all.
        """
        return self is Disposition.SETTLED


# ---------------------------------------------------------------------------
# The non-terminal set, split by WHY it is non-terminal (#2175)
# ---------------------------------------------------------------------------
#
# ``settlement_sweep_query`` splits the vocabulary once, into TERMINAL (the source
# has told us and will not change its mind) and everything else. That split is
# correct and it is not enough, because "everything else" contains two populations
# whose re-probe value differs by orders of magnitude:
#
#   * the CHANNEL failed — we never got an answer, so asking again is the whole
#     point;
#   * the ask COMPLETED and produced a non-answer — the source responded, and it
#     will respond the same way until the world changes.
#
# Fusing them is what livelocked the terminal bucket (#2077). 341 rows carrying
# ``ambiguous_empty`` were the oldest rows in the dying bucket, so a
# terminal-first/oldest-first planner put them at the head of every pass, forever,
# ahead of 227 rows whose only problem was a 429. Measured burn-down across three
# paced passes: 614 -> 594 -> 577 -> 568. Freed 20, then 17, then 9. Decelerating.
#
# THIS IS A PLANNING PARTITION, NOT A TERMINALITY ONE. Nothing here becomes
# terminal and nothing is dropped. Both sets are still re-probed; they are merely
# ordered against each other, inside their deadline bucket, by how much a call is
# worth. Promoting AMBIGUOUS_EMPTY to terminal would have been the easy fix and it
# would be wrong -- it converts "we could not tell" into "we have our answer",
# which is the one conversion this whole module exists to refuse.

#: Non-terminal because the CHANNEL failed. No answer was obtained, so a retry is
#: the entire remedy and these sort FIRST among probed rows.
TRANSIENT_DISPOSITIONS: frozenset[Disposition] = frozenset(
    {Disposition.RATE_LIMITED, Disposition.TRANSPORT_ERROR}
)

#: Non-terminal, but the ask completed and this IS what came back. An immediate
#: re-ask reproduces it. Still retried -- with whatever budget survives the rows
#: that can actually move.
#:
#: ``NOT_PROBED_BEYOND_HORIZON`` belongs here rather than with the transient set
#: even though no request was made: age only increases, so the declination
#: reproduces itself by construction.
STABLE_NONANSWER_DISPOSITIONS: frozenset[Disposition] = frozenset(
    {
        Disposition.AMBIGUOUS_EMPTY,
        Disposition.OPEN_NO_SETTLEMENT,
        Disposition.PRICE_UNDETERMINABLE,
        Disposition.NOT_PROBED_BEYOND_HORIZON,
    }
)

#: String forms, for the SQL layer and for rows read back out of the table. The
#: enum is the source of truth; these are derived so the two can never drift.
TRANSIENT_DISPOSITION_VALUES: frozenset[str] = frozenset(
    d.value for d in TRANSIENT_DISPOSITIONS
)
STABLE_NONANSWER_DISPOSITION_VALUES: frozenset[str] = frozenset(
    d.value for d in STABLE_NONANSWER_DISPOSITIONS
)


def is_stable_nonanswer(disposition: str | Disposition | None) -> bool:
    """True when the source already answered and would answer the same again.

    **An unrecognised disposition is deliberately NOT stable.** A value added to
    the enum later, or read back from a row written under an older protocol
    version, defaults to the more urgent treatment. The asymmetry is the same one
    :func:`settlement_sweep_plan.bucket_for` floors toward: over-including into the
    urgent tier costs a probe, under-including costs the row. The exhaustiveness
    test is what turns "defaulted" into "noticed".
    """
    if disposition is None:
        return False
    value = disposition.value if isinstance(disposition, Disposition) else disposition
    return value in STABLE_NONANSWER_DISPOSITION_VALUES


@dataclass(frozen=True)
class SettlementClaim:
    """The parsed settlement, present ONLY on :attr:`Disposition.SETTLED`.

    ``winning_outcome`` is the source's own label, verbatim and un-normalised. It is
    deliberately not matched against our outcome rows here: name reconciliation is a
    separate, fallible step, and folding it into capture would make a capture failure
    and a matching failure indistinguishable.
    """

    winning_outcome: str
    #: Which HTTP channel actually answered — provenance, not decoration. A claim
    #: from Kalshi's ``/markets`` and one from Polymarket's CLOB have different
    #: reliability and different retention, and the audit needs to know which it has.
    channel: str
    #: Raw settlement fragment as the source returned it (``result``,
    #: ``outcomePrices``, ``tokens``), so a later reader can re-derive the parse.
    evidence: dict[str, Any] = field(default_factory=dict)


#: The only dispositions that may carry per-leg verdicts. See
#: :attr:`ProbeOutcome.leg_claims` for why the partial board is in the set.
_LEG_BEARING_DISPOSITIONS: frozenset[Disposition] = frozenset(
    {Disposition.SETTLED_PER_LEG, Disposition.OPEN_NO_SETTLEMENT}
)


@dataclass(frozen=True)
class LegSettlement:
    """What the venue said about ONE leg of a multi-leg board.

    The per-leg analogue of :class:`SettlementClaim`, and deliberately not that
    class: a leg's honest answer is often "settled, and no winner exists", which
    :class:`SettlementClaim` has no way to express — it has a ``winning_outcome``
    and nothing else.

    ``disposition`` IS THE POINT. It is drawn from the same :class:`Disposition`
    vocabulary as the board, so :func:`assert_grading_licensed` gates a per-leg
    write with no new predicate and no widening of :meth:`Disposition.licenses_grading`.
    Exactly three values ever appear:

    * :attr:`Disposition.SETTLED` — the venue named a side. ``is_winner`` is
      ``True``/``False`` and may be written.
    * :attr:`Disposition.SETTLED_NO_VERDICT` — ``finalized``/``scalar``. Settled,
      no side. ``is_winner`` is ``None`` and MUST NOT be written; this licenses
      taking the stale price down and nothing else (#1852 / #7987).
    * :attr:`Disposition.OPEN_NO_SETTLEMENT` — not declared yet. Nothing to do.

    ``is_winner is None`` therefore never has to be interrogated for its meaning.
    That ambiguity — one ``None`` covering "not answered" and "answered, no side"
    — is the exact defect #7987 was filed for, and splitting it into the
    disposition is what stops it being rebuilt here.
    """

    #: The venue's own per-leg ticker. This is an EXACT string match for
    #: ``futures_outcomes.external_id`` — verified both sides on production rows
    #: (``KXNASDAQ100U-26AUG17H1200-T27999.99``), so the join needs no name
    #: matching and no normalisation.
    external_id: str
    #: The leg's disposition. See the class docstring — this is the grading gate.
    disposition: Disposition
    #: ``True``/``False`` only under :attr:`Disposition.SETTLED`; ``None`` always
    #: otherwise. Enforced in ``__post_init__`` rather than trusted.
    is_winner: bool | None = None
    #: The venue's ``status`` and ``result``, verbatim and un-normalised, so a
    #: later reader can re-derive this parse instead of believing it.
    status: str | None = None
    result: str | None = None

    def __post_init__(self) -> None:
        if self.disposition is Disposition.SETTLED and self.is_winner is None:
            raise ValueError("a SETTLED leg must carry a winner")
        if self.disposition is not Disposition.SETTLED and self.is_winner is not None:
            # The same invariant ProbeOutcome enforces for claims, at leg scale:
            # there is no representable value carrying a verdict without the
            # disposition that licenses one.
            raise ValueError(
                f"only a SETTLED leg may carry a winner; got {self.disposition.value}"
            )


@dataclass(frozen=True)
class ProbeOutcome:
    """The complete, honest record of one probe attempt.

    Every field that could tempt a caller into a shortcut is present, so no caller
    needs to reconstruct anything from the disposition alone.
    """

    disposition: Disposition
    #: Populated iff ``disposition is SETTLED``. Enforced in ``__post_init__``.
    claim: SettlementClaim | None = None
    #: Per-leg verdicts from a multi-leg board. Non-empty only under
    #: :attr:`Disposition.SETTLED_PER_LEG` (every leg declared) and
    #: :attr:`Disposition.OPEN_NO_SETTLEMENT` (some declared, some still trading
    #: — the partial board, which stays non-terminal so the stragglers are asked
    #: again). Both are enforced in ``__post_init__``.
    #:
    #: The second case is why this is not simply keyed to ``SETTLED_PER_LEG``. A
    #: board whose 30 legs have settled and whose 31st has not is BOTH: real
    #: verdicts worth carrying now, and a reason to come back. Dropping the legs
    #: to keep the disposition tidy would re-probe the whole board against a
    #: ticking 74-day retention wall to re-learn what this call already knows.
    leg_claims: tuple[LegSettlement, ...] = ()
    #: Every channel consulted, in order, with its status. This is what makes the
    #: gotcha #53 disambiguation auditable after the fact rather than trusted.
    channels: tuple[tuple[str, int | None], ...] = ()
    #: Free-text reason, always set for non-``SETTLED`` outcomes so a human reading
    #: the table sees WHY, not just WHAT.
    reason: str = ""
    #: Raw bodies keyed by channel, truncated by the writer. Constraint (a) requires
    #: the raw response be recorded, so a wrong parse is recoverable later.
    raw: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.disposition is Disposition.SETTLED and self.claim is None:
            raise ValueError("SETTLED outcome must carry a SettlementClaim")
        if self.disposition is not Disposition.SETTLED and self.claim is not None:
            # The invariant that makes constraint (a) structural rather than
            # aspirational: there is no representable value of this type that
            # carries a settlement without the disposition that licenses it.
            raise ValueError(
                f"only SETTLED may carry a claim; got {self.disposition.value}"
            )
        if self.leg_claims and self.disposition not in _LEG_BEARING_DISPOSITIONS:
            # The board-level mirror of the claim invariant. Without it, per-leg
            # verdicts could ride a PURGED or a TRANSPORT_ERROR — a disposition
            # that means "we learned nothing" arriving with verdicts attached is
            # precisely the manufactured fact this module exists to refuse.
            raise ValueError(
                f"{self.disposition.value} may not carry leg claims; only "
                + " or ".join(sorted(d.value for d in _LEG_BEARING_DISPOSITIONS))
            )
        if self.disposition is Disposition.SETTLED_PER_LEG and not self.leg_claims:
            raise ValueError("SETTLED_PER_LEG outcome must carry leg claims")


# --------------------------------------------------------------------------
# Kalshi
# --------------------------------------------------------------------------
#
# Protocol, per C-WINNER-TRUTH-2 and probe_kalshi_retention.py:
#
#   GET /markets/{ticker}  200 + a result we can name  -> SETTLED
#                          200 + finalized/scalar      -> SETTLED_NO_VERDICT
#                          200 + status open/active    -> OPEN_NO_SETTLEMENT
#                          404                         -> ask the EVENT
#   GET /events/{ticker}   200 + markets == []         -> PURGED  (the cliff)
#                          200 + every leg declared    -> SETTLED_PER_LEG
#                          200 + some legs declared    -> OPEN_NO_SETTLEMENT + legs
#                          200 + no leg readable       -> AMBIGUOUS_EMPTY
#                          404                         -> NOT_FOUND
#
# The second call is the "second signal" gotcha #53 demands. Without it, a 404 on
# the market is unattributable: it could be our bad ticker or Kalshi's retention,
# and those route to completely different owners.
#
# THE EVENT CALL ANSWERS ABOUT THE BOARD, AND THAT IS THE POINT (#2077). Our
# `external_id` is the EVENT ticker on ~96% of rows, so the market 404s and the
# event's nested markets ARE our `futures_outcomes` — matched by exact string
# equality on the ticker. The three event-200 rows above used to be one row
# answering AMBIGUOUS_EMPTY, which discarded a payload naming every leg's verdict.

#: Kalshi reports an unsettled market's result as one of these. An empty string is
#: the common case; the others appear on markets that closed without settling.
#:
#: DERIVED, not typed out. ``scalar`` is the member this set was missing, and it
#: went missing because four modules each wrote their own copy of Kalshi's result
#: vocabulary from memory. The shared constant is the fix; see
#: :data:`~app.utils.kalshi_market_status.NON_VERDICT_RESULTS` for why a denylist
#: here and an allowlist for binary legs are both correct.
_KALSHI_NON_RESULTS = set(NON_VERDICT_RESULTS)


def _grade_kalshi_legs(
    markets: list[Any],
) -> tuple[tuple[LegSettlement, ...], bool, dict[str, int]]:
    """Grade every nested market on a Kalshi event payload.

    Returns the legs we could read, whether the board is COMPLETE (every leg
    declared and joinable), and a tally for the capture's ``reason``.

    Complete is deliberately strict — every leg must carry a declared result AND
    a ticker to join on. A board is terminal only when it is complete, because a
    board marked terminal is never asked again: one straggling leg would be
    stranded permanently, and the straggler is the leg most likely to be the one a
    reader is looking at.
    """
    legs: list[LegSettlement] = []
    tally = {"winner": 0, "no_verdict": 0, "undeclared": 0, "unreadable": 0}
    complete = True

    for leg in markets:
        if not isinstance(leg, dict):
            tally["unreadable"] += 1
            complete = False
            continue

        status = leg.get("status")
        result = leg.get("result")
        ticker = leg.get("ticker")

        # A status outside the measured vocabulary, or a leg with no ticker to
        # join on, is UNREADABLE — not "open". Falling through to a default here
        # is how "do not interpret" stops being reachable.
        if not isinstance(status, str) or status not in KNOWN_STATUSES:
            tally["unreadable"] += 1
            complete = False
            continue
        if not isinstance(ticker, str) or not ticker.strip():
            tally["unreadable"] += 1
            complete = False
            continue

        won = gradeable_winner(status, result)
        if won is not None:
            legs.append(
                LegSettlement(
                    external_id=ticker.strip(),
                    disposition=Disposition.SETTLED,
                    is_winner=won,
                    status=status,
                    result=result,
                )
            )
            tally["winner"] += 1
        elif settled_without_verdict(status, result):
            legs.append(
                LegSettlement(
                    external_id=ticker.strip(),
                    disposition=Disposition.SETTLED_NO_VERDICT,
                    status=status,
                    result=result,
                )
            )
            tally["no_verdict"] += 1
        else:
            legs.append(
                LegSettlement(
                    external_id=ticker.strip(),
                    disposition=Disposition.OPEN_NO_SETTLEMENT,
                    status=status,
                    result=result,
                )
            )
            tally["undeclared"] += 1
            complete = False

    return tuple(legs), complete, tally


def classify_kalshi(
    market_status: int,
    market_body: dict[str, Any] | None,
    event_status: int | None = None,
    event_body: dict[str, Any] | None = None,
    *,
    clip: Callable[[Any], Any] | None = None,
) -> ProbeOutcome:
    """Classify a Kalshi probe from the two raw HTTP answers.

    Pure: takes statuses and bodies, does no I/O, so every branch below is reachable
    from a unit test without a network. ``event_status``/``event_body`` may be omitted
    when the market call already answered.

    ``clip`` IS A STORAGE CONCERN AND MUST NOT TOUCH THE PARSE. Callers hand over
    full bodies and pass their truncator here, so ``raw`` stays small while every
    branch above reads the real payload. Passing a pre-clipped body instead is a
    silent correctness bug, not a size optimisation: a settled Kalshi board
    measured **812,850 characters** against the probe's 20,000-char ceiling
    (``KXNASDAQ100U-26AUG17H1200``, 400 legs, read from the venue 2026-09-22), and
    a clipped body carries no ``markets`` key at all — so the per-leg reader below
    would find nothing and answer AMBIGUOUS_EMPTY on the very boards it exists for.
    Defaults to identity, which is what every pure unit test wants.
    """
    keep = clip if clip is not None else (lambda body: body)
    channels: list[tuple[str, int | None]] = [("kalshi_market", market_status)]
    raw: dict[str, Any] = {}
    if market_body is not None:
        raw["kalshi_market"] = keep(market_body)

    if market_status == 429:
        return ProbeOutcome(
            Disposition.RATE_LIMITED,
            channels=tuple(channels),
            reason="kalshi /markets returned 429",
            raw=raw,
        )
    if market_status >= 500 or market_status < 0:
        return ProbeOutcome(
            Disposition.TRANSPORT_ERROR,
            channels=tuple(channels),
            reason=f"kalshi /markets transport failure (status {market_status})",
            raw=raw,
        )

    if market_status == 200:
        market = (market_body or {}).get("market") or market_body or {}
        if not isinstance(market, dict):
            return ProbeOutcome(
                Disposition.TRANSPORT_ERROR,
                channels=tuple(channels),
                reason="kalshi /markets 200 with unparseable body",
                raw=raw,
            )
        result = (market.get("result") or "").strip()
        if result and result.lower() not in _KALSHI_NON_RESULTS:
            return ProbeOutcome(
                Disposition.SETTLED,
                claim=SettlementClaim(
                    winning_outcome=result,
                    channel="kalshi_market",
                    evidence={"result": result, "status": market.get("status")},
                ),
                channels=tuple(channels),
                raw=raw,
            )
        # SETTLED, BUT ON A NUMBER RATHER THAN A SIDE. Split out before the
        # open-market branch below, because both of the states this reaches are
        # `result` values that branch would have called "not a settlement":
        # `finalized`/`scalar` and the void/cancelled family. They ARE settlements
        # — they just name no winner — and calling them open leaves a stale price
        # on a decided question and re-probes it forever (#7987).
        #
        # Gated on the STATUS as well as the result, so this can only fire where
        # the venue has actually declared. A `closed` market with `result: ""` is
        # still genuinely open below, which is what the measured table says it is.
        if settled_without_verdict(market.get("status"), result):
            return ProbeOutcome(
                Disposition.SETTLED_NO_VERDICT,
                channels=tuple(channels),
                reason=(
                    f"kalshi market settled with no winner to name: "
                    f"result={result!r}, status={market.get('status')!r} — "
                    f"licenses a price-down only, never a verdict"
                ),
                raw=raw,
            )
        # A 200 with no result is a REAL statement: the market exists and Kalshi
        # is not reporting a settlement for it. That is a finding when our row
        # says resolved — it is not an error and must not be retried as one.
        return ProbeOutcome(
            Disposition.OPEN_NO_SETTLEMENT,
            channels=tuple(channels),
            reason=(
                f"kalshi market present, result={result!r}, "
                f"status={market.get('status')!r}"
            ),
            raw=raw,
        )

    if market_status != 404:
        return ProbeOutcome(
            Disposition.TRANSPORT_ERROR,
            channels=tuple(channels),
            reason=f"kalshi /markets unexpected status {market_status}",
            raw=raw,
        )

    # 404 on the market. Alone this means NOTHING attributable — go to the event.
    if event_status is None:
        return ProbeOutcome(
            Disposition.AMBIGUOUS_EMPTY,
            channels=tuple(channels),
            reason=(
                "kalshi /markets 404 and the event was not consulted — a bare 404 "
                "cannot distinguish retention purge from a wrong ticker"
            ),
            raw=raw,
        )

    channels.append(("kalshi_event", event_status))
    if event_body is not None:
        raw["kalshi_event"] = keep(event_body)

    if event_status == 429:
        return ProbeOutcome(
            Disposition.RATE_LIMITED,
            channels=tuple(channels),
            reason="kalshi /events returned 429",
            raw=raw,
        )
    if event_status >= 500 or event_status < 0:
        return ProbeOutcome(
            Disposition.TRANSPORT_ERROR,
            channels=tuple(channels),
            reason=f"kalshi /events transport failure (status {event_status})",
            raw=raw,
        )
    if event_status == 404:
        return ProbeOutcome(
            Disposition.NOT_FOUND,
            channels=tuple(channels),
            reason="kalshi has no such market and no such event — suspect our external_id",
            raw=raw,
        )
    if event_status == 200:
        markets = (event_body or {}).get("markets")
        if isinstance(markets, list) and len(markets) == 0:
            # THE CLIFF, named. Event permanent, markets purged (gotcha #35).
            return ProbeOutcome(
                Disposition.PURGED,
                channels=tuple(channels),
                reason=(
                    "kalshi event exists with markets:[] — retention purge, the "
                    "settlement is unknowable rather than absent"
                ),
                raw=raw,
            )
        # THE EVENT ANSWERED, AND IT ANSWERED PER LEG.
        #
        # This branch used to return AMBIGUOUS_EMPTY — "do not interpret" — and
        # throw away a payload it already held. That was right when the only
        # question was "did THIS market settle": our `external_id` is the EVENT
        # ticker on ~96% of rows (see `probe_kalshi`), so the market call 404s and
        # the event answers about the board, not about the row we asked for.
        #
        # But the board's legs ARE our `futures_outcomes` rows, matched by exact
        # string equality on the ticker, and the payload states each one's status
        # and result. Refusing to read it is not caution — it is discarding the
        # answer at the one moment we hold it, against a retention wall that
        # eventually takes the market records away for good (gotcha #35).
        #
        # No new venue traffic: this is the call `probe_kalshi` already makes.
        if isinstance(markets, list) and markets:
            legs, complete, tally = _grade_kalshi_legs(markets)
            summary = (
                f"{len(markets)} legs: {tally['winner']} with a winner, "
                f"{tally['no_verdict']} settled with no verdict, "
                f"{tally['undeclared']} not yet declared, "
                f"{tally['unreadable']} unreadable"
            )
            if legs and complete:
                return ProbeOutcome(
                    Disposition.SETTLED_PER_LEG,
                    channels=tuple(channels),
                    leg_claims=legs,
                    reason=f"kalshi event settled every leg — {summary}",
                    raw=raw,
                )
            if legs:
                # A PARTIAL BOARD. Keep the verdicts, keep the row re-probable.
                # Terminal here would strand the undeclared legs forever; dropping
                # the legs would re-probe the whole board to re-learn what this
                # call already told us.
                return ProbeOutcome(
                    Disposition.OPEN_NO_SETTLEMENT,
                    channels=tuple(channels),
                    leg_claims=legs,
                    reason=f"kalshi event partially settled — {summary}",
                    raw=raw,
                )
            # Legs present but NONE readable. The original refusal, preserved
            # rather than defaulted into: a payload whose vocabulary we do not
            # recognise is not an open market, it is an unread one.
            return ProbeOutcome(
                Disposition.AMBIGUOUS_EMPTY,
                channels=tuple(channels),
                reason=(
                    "kalshi market 404 but its event still lists markets — "
                    f"neither purged nor missing; do not interpret ({summary})"
                ),
                raw=raw,
            )

        return ProbeOutcome(
            Disposition.AMBIGUOUS_EMPTY,
            channels=tuple(channels),
            reason=(
                "kalshi market 404 but its event still lists markets — neither "
                "purged nor missing; do not interpret"
            ),
            raw=raw,
        )

    return ProbeOutcome(
        Disposition.TRANSPORT_ERROR,
        channels=tuple(channels),
        reason=f"kalshi /events unexpected status {event_status}",
        raw=raw,
    )


# --------------------------------------------------------------------------
# Polymarket
# --------------------------------------------------------------------------
#
# Gamma answers `200 []` for a condition it does not index — the same body it would
# return for a legitimately empty filter. That is unattributable on its own, so the
# CLOB is the second signal: `tokens[].winner` survives after the Gamma record ages
# out (#989 / L2-32), which makes the pair genuinely independent rather than two
# reads of one store.

_PRICE_SETTLED = {("0", "1"), ("1", "0")}

#: The NEAR-FORM threshold, adopted verbatim from C-DEGRADED-FORM-1 (2026-08-21).
#: A decided Polymarket market does not always print exactly ``["0","1"]`` — it
#: prints things like ``["0.0000005","0.9999945"]``. The measured rule is
#: ``min(price) < 0.001``, and the census found the **worst observed spread to be
#: 1.16e-06** — three orders of magnitude inside the threshold, never ambiguous.
#:
#: The margin is the point. A threshold set at the worst observation would be a
#: threshold with no evidence between it and being wrong.
NEAR_FORM_LOSER_MAX = 0.001

#: A near-form winner must also actually look like a winner. If BOTH prices are
#: below the threshold the body is malformed, not decided — refusing costs nothing
#: and emitting would be manufacturing. Not in C-DEGRADED-FORM-1's rule (which
#: describes real decided markets); added as a guard and flagged as an addition.
NEAR_FORM_WINNER_MIN = 0.5


def _parse_outcome_prices(market: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    """Return (winning outcome, evidence) when Gamma reports a decided market.

    Two accepted forms, per C-DEGRADED-FORM-1:

    * **exact** — ``["0","1"]`` / ``["1","0"]``
    * **near** — one side below :data:`NEAR_FORM_LOSER_MAX`, the other above
      :data:`NEAR_FORM_WINNER_MIN`

    Anything else returns ``None``, which the caller turns into a non-fact rather
    than a guess.
    """
    prices = market.get("outcomePrices")
    outcomes = market.get("outcomes")
    if isinstance(prices, str):
        prices = _loads_maybe(prices)
    if isinstance(outcomes, str):
        outcomes = _loads_maybe(outcomes)
    if not isinstance(prices, list) or not isinstance(outcomes, list):
        return None
    if len(prices) != 2 or len(outcomes) != 2:
        return None

    key = (str(prices[0]).strip(), str(prices[1]).strip())
    if key in _PRICE_SETTLED:
        winner = outcomes[1] if key == ("0", "1") else outcomes[0]
        return str(winner), {
            "outcomePrices": list(prices),
            "outcomes": list(outcomes),
            "form": "exact",
        }

    try:
        low, high = float(key[0]), float(key[1])
    except (TypeError, ValueError):
        return None

    loser_first = low < NEAR_FORM_LOSER_MAX <= high and high >= NEAR_FORM_WINNER_MIN
    loser_second = high < NEAR_FORM_LOSER_MAX <= low and low >= NEAR_FORM_WINNER_MIN
    if loser_first:
        return str(outcomes[1]), {
            "outcomePrices": list(prices),
            "outcomes": list(outcomes),
            "form": "near",
            "loser_price": low,
        }
    if loser_second:
        return str(outcomes[0]), {
            "outcomePrices": list(prices),
            "outcomes": list(outcomes),
            "form": "near",
            "loser_price": high,
        }
    return None


def _has_price_field(market: dict[str, Any]) -> bool:
    """Did the record carry an ``outcomePrices`` field AT ALL?

    The distinction between "present but undecided" and "absent entirely" is what
    separates a market that may still resolve from Polymarket's ``no_resolved``
    class, which never will. Collapsing them would put ~8k permanently-undeterminable
    markets back into the recoverable denominator and make the burn-down report a
    debt it can never pay down.
    """
    prices = market.get("outcomePrices")
    if isinstance(prices, str):
        prices = _loads_maybe(prices)
    return isinstance(prices, list) and len(prices) > 0


def _loads_maybe(raw: str) -> Any:
    import json

    try:
        return json.loads(raw)
    except Exception:
        return None


def classify_polymarket(
    gamma_status: int,
    gamma_body: Any,
    clob_status: int | None = None,
    clob_body: dict[str, Any] | None = None,
) -> ProbeOutcome:
    """Classify a Polymarket probe from Gamma plus the CLOB corroborator.

    ``gamma_body`` may be a list (``/markets?condition_ids=``) or a dict
    (``/events/{id}``); both shapes occur in our population and both are handled,
    because normalising them upstream is what would hide the empty-list case.
    """
    channels: list[tuple[str, int | None]] = [("gamma", gamma_status)]
    raw: dict[str, Any] = {}
    if gamma_body is not None:
        raw["gamma"] = gamma_body

    if gamma_status == 429:
        return ProbeOutcome(
            Disposition.RATE_LIMITED,
            channels=tuple(channels),
            reason="gamma returned 429",
            raw=raw,
        )
    if gamma_status >= 500 or gamma_status < 0:
        return ProbeOutcome(
            Disposition.TRANSPORT_ERROR,
            channels=tuple(channels),
            reason=f"gamma transport failure (status {gamma_status})",
            raw=raw,
        )

    gamma_markets: list[dict[str, Any]] = []
    if gamma_status == 200:
        if isinstance(gamma_body, list):
            gamma_markets = [m for m in gamma_body if isinstance(m, dict)]
        elif isinstance(gamma_body, dict):
            nested = gamma_body.get("markets")
            if isinstance(nested, list):
                gamma_markets = [m for m in nested if isinstance(m, dict)]
            else:
                gamma_markets = [gamma_body]

        for market in gamma_markets:
            parsed = _parse_outcome_prices(market)
            if parsed is not None:
                winner, evidence = parsed
                return ProbeOutcome(
                    Disposition.SETTLED,
                    claim=SettlementClaim(
                        winning_outcome=winner,
                        channel="gamma",
                        evidence=evidence,
                    ),
                    channels=tuple(channels),
                    raw=raw,
                )

    # Gamma did not give us a settlement. Before saying ANYTHING about the market,
    # consult the CLOB — this is the "second signal before writing any claim" the
    # gotcha demands, and it is the only reason an empty Gamma answer is ever
    # resolvable at all.
    if clob_status is not None:
        channels.append(("clob", clob_status))
        if clob_body is not None:
            raw["clob"] = clob_body

        if clob_status == 429:
            return ProbeOutcome(
                Disposition.RATE_LIMITED,
                channels=tuple(channels),
                reason="clob returned 429",
                raw=raw,
            )
        if clob_status >= 500 or clob_status < 0:
            return ProbeOutcome(
                Disposition.TRANSPORT_ERROR,
                channels=tuple(channels),
                reason=f"clob transport failure (status {clob_status})",
                raw=raw,
            )
        if clob_status == 200 and isinstance(clob_body, dict):
            tokens = clob_body.get("tokens")
            if isinstance(tokens, list) and tokens:
                winners = [
                    t
                    for t in tokens
                    if isinstance(t, dict) and t.get("winner") is True
                ]
                if len(winners) == 1:
                    outcome = winners[0].get("outcome")
                    if outcome:
                        return ProbeOutcome(
                            Disposition.SETTLED,
                            claim=SettlementClaim(
                                winning_outcome=str(outcome),
                                channel="clob",
                                evidence={"tokens": tokens},
                            ),
                            channels=tuple(channels),
                            raw=raw,
                        )
                if len(winners) > 1:
                    # Two winners is not a settlement we understand. Refusing is
                    # the point: a capture that picks one would be inventing.
                    return ProbeOutcome(
                        Disposition.AMBIGUOUS_EMPTY,
                        channels=tuple(channels),
                        reason=f"clob reported {len(winners)} winning tokens",
                        raw=raw,
                    )
                if clob_body.get("closed") is True:
                    return ProbeOutcome(
                        Disposition.AMBIGUOUS_EMPTY,
                        channels=tuple(channels),
                        reason="clob market closed but no token carries winner=true",
                        raw=raw,
                    )
                return ProbeOutcome(
                    Disposition.OPEN_NO_SETTLEMENT,
                    channels=tuple(channels),
                    reason="clob market open, no winning token",
                    raw=raw,
                )
        if clob_status == 404 and gamma_status == 200 and not gamma_markets:
            # Both independent stores deny the id. That is as close to a real
            # NOT_FOUND as Polymarket gets, and it took two channels to say it.
            return ProbeOutcome(
                Disposition.NOT_FOUND,
                channels=tuple(channels),
                reason="gamma returned an empty list AND clob 404 — id unknown to both stores",
                raw=raw,
            )

    if gamma_status == 404:
        return ProbeOutcome(
            Disposition.NOT_FOUND,
            channels=tuple(channels),
            reason="gamma 404 with no corroborating clob answer",
            raw=raw,
        )

    if gamma_status == 200 and not gamma_markets:
        # THE TRAP, refused by name. `200 []` is the same body Gamma returns for a
        # condition it never indexed and for a filter that matched nothing.
        return ProbeOutcome(
            Disposition.AMBIGUOUS_EMPTY,
            channels=tuple(channels),
            reason=(
                "gamma 200 with an empty result and no clob corroboration — this "
                "body cannot distinguish 'never indexed' from 'nothing matched'"
            ),
            raw=raw,
        )

    if gamma_markets:
        closed = any(m.get("closed") is True for m in gamma_markets)
        if closed:
            if not any(_has_price_field(m) for m in gamma_markets):
                # THE ``no_resolved`` CLASS (C-DEGRADED-FORM-1): closed, held by the
                # source, and carrying no price field at all. There is nothing to
                # wait for, so it leaves the recoverable denominator by name rather
                # than sitting in an ambiguity bucket that implies a future retry.
                return ProbeOutcome(
                    Disposition.PRICE_UNDETERMINABLE,
                    channels=tuple(channels),
                    reason=(
                        "gamma market closed and carries no outcomePrices field at "
                        "all — the no_resolved form, permanently price-undeterminable"
                    ),
                    raw=raw,
                )
            return ProbeOutcome(
                Disposition.AMBIGUOUS_EMPTY,
                channels=tuple(channels),
                reason=(
                    "gamma market closed with an outcomePrices field that is not "
                    "decided — undetermined for now, not undeterminable"
                ),
                raw=raw,
            )
        return ProbeOutcome(
            Disposition.OPEN_NO_SETTLEMENT,
            channels=tuple(channels),
            reason="gamma market present and not closed",
            raw=raw,
        )

    return ProbeOutcome(
        Disposition.TRANSPORT_ERROR,
        channels=tuple(channels),
        reason=f"unhandled gamma status {gamma_status}",
        raw=raw,
    )


# --------------------------------------------------------------------------
# The candidate-pool boundary (constraint (b))
# --------------------------------------------------------------------------

#: Reasons a market may enter the sweep as a CANDIDATE. None of these is evidence.
#: They select what to LOOK AT; only a probe decides what is true.
CANDIDATE_REASONS = frozenset(
    {
        "missing_winner",       # resolved row, no outcome carries is_winner
        "scores_derivable",     # the event has a final score we could derive from
        "audit_sample",         # sampled for verification of an existing winner
    }
)


class UnverifiedGradingRefused(RuntimeError):
    """Raised when something tries to grade from a candidate rather than a capture.

    Constraint (b), made structural. ``scores_derivable`` is the trap this month
    already proved: ``events`` rows keep FROZEN MID-GAME scores on closed events
    (see ``project_events_score_not_ground_truth``), so a score-derived winner is a
    *guess that looks like arithmetic*. It may nominate a market for probing. It may
    never settle one.
    """


def assert_grading_licensed(disposition: Disposition, candidate_reason: str) -> None:
    """Gate every future grading write. Raises unless the SOURCE settled it.

    Deliberately takes the candidate reason too, so the error message names the
    tempting input rather than just the missing licence — the next person to hit
    this will be holding a plausible score and wondering why it is refused.
    """
    if not disposition.licenses_grading():
        raise UnverifiedGradingRefused(
            f"refusing to grade from candidate_reason={candidate_reason!r} with "
            f"disposition={disposition.value!r}: only a SETTLED source probe "
            f"licenses a grading write (queue 389 constraint (b))"
        )
