#!/usr/bin/env python3
"""Emit the CERT-430 comparison specimen, built by the PRODUCTION rule.

WHY THIS SCRIPT EXISTS (CERT-433, 2026-08-29 16:19Z, `BLOCK — TOKEN WITHHELD`).

CERT-430 found a card that published one man's number under a two-man question:
the register declared `second-major` across TWO markets, Alcaraz's leg had no
reading, Sinner's was fresh at .555, and the card came back `price_state='live'`
because only PRICED outcomes voted on freshness.  UX-P156 repaired it on both
sides — `build_props` grades such a card dark and names the missing leg, and
`propIncompleteComparison` prints every declared subject and says which one is
absent.

CERT-433 then killed the repair's PROOF, not its behaviour:

    deleting `if len(declared) > 1 and unpriced_legs: contributors.append(None)`
    from `app/utils/tournament_slate.py` makes the backend specimen fail, but
    the frontend CERT-430 specimen still passes, because its fixture hardcodes
    the repaired payload.

THE ROOT IS ONE LAYER DEEPER THAN THE CERT'S WORDING, and it is the part worth
carrying.  A hardcoded fixture was the symptom.  The cause is that the two
layers are **REDUNDANT, NOT COUPLED**: they reach the same verdict from
DIFFERENT fields.  The backend grades the card from its declared legs and their
readings and publishes `price_state`; the renderer ignores `price_state` for
that decision entirely and re-derives completeness from `legs` plus the null
probabilities (`tournamentProps.ts:307`, `propIsPresentedAsLive`).  So no
fixture change alone could have satisfied CERT-433's G1 — even a perfectly
backend-produced payload leaves the renderer green when the backend rule is
deleted, because the renderer never reads the field that changed.

Two rules that agree today and share no input can drift apart tomorrow with
nothing going red.  That is what this script closes: it lets a Jest test assert
the two layers AGREE, on a payload the backend actually produced, rather than on
one a human typed out after reading the backend's answer.

WHAT IT GUARANTEES
------------------

* **It runs the production function.**  `build_props` is imported from
  `app.utils.tournament_slate`; nothing here restates the rule.  Delete the
  contributor line and this script's output changes, which is the whole point.
* **It is deterministic.**  A fixed `now`, a fixed register, fixed prices.  Same
  input in, byte-identical JSON out — the requirement `generate_grid_register.py`
  states for any file a diff gate is allowed to judge.  There is no clock read,
  no database, no network and no third-party import, so it runs under a bare
  `python3` on a CI runner that never installed our requirements.
* **It emits BOTH directions.**  `incomplete` is the specimen; `complete` is the
  control that stops a producer which always returns dark from faking the kill.

USAGE

    PYTHONPATH=backend python3 backend/scripts/emit_comparison_specimen.py

Consumed by `frontend/__tests__/components/tournamentReskin.test.tsx` (the
CERT-430 block) and guarded by `backend/tests/test_comparison_specimen.py`.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

from app.utils.tournament_register import SCHEMA_VERSION
from app.utils.tournament_slate import build_props

#: The specimen's clock.  A literal, never `utcnow()`: gotcha #44 — an anchor
#: that branches on the real clock is not an anchor, and a producer whose output
#: moves with the wall clock cannot be compared across two runs.
NOW = datetime(2026, 8, 25, 21, 30, tzinfo=timezone.utc)

#: The two Kalshi legs CERT-430 executed against, by their external ids.
ALCARAZ_LEG = "KXGRANDSLAM-CALC26"
SINNER_LEG = "KXGRANDSLAM-JSIN26"

#: Their outcome ids, which is what `prices` is keyed by.
ALCARAZ_OUTCOME = 848773
SINNER_OUTCOME = 848769

#: Sinner's reading in the executed specimen: fresh, and high enough that
#: printing it alone looks like a confident answer rather than an obvious gap.
SINNER_PROBABILITY = 0.555
ALCARAZ_PROBABILITY = 0.25

CASES = ("incomplete", "complete")


def specimen_prop() -> dict[str, Any]:
    """The register entry: ONE question, TWO declared markets.

    `markets` is what makes this a comparison rather than a field — see the
    `legs` note in `build_props`.  Both legs are declared whether or not a price
    ever arrives for them, which is exactly the property the rule under test
    depends on.
    """
    return {
        "key": "second-major",
        "title": "Who wins a second major this year?",
        "hook": None,
        "draw": None,
        "source": "kalshi",
        "markets": [
            {"market_id": 53796, "market_external_id": ALCARAZ_LEG},
            {"market_id": 53795, "market_external_id": SINNER_LEG},
        ],
        "outcomes": [
            {
                "entity_key": "second-major:carlos-alcaraz",
                "display_name": "Carlos Alcaraz",
                "outcome_id": ALCARAZ_OUTCOME,
                "market_external_id": ALCARAZ_LEG,
            },
            {
                "entity_key": "second-major:jannik-sinner",
                "display_name": "Jannik Sinner",
                "outcome_id": SINNER_OUTCOME,
                "market_external_id": SINNER_LEG,
            },
        ],
    }


def specimen_register() -> dict[str, Any]:
    """A minimal valid register carrying only the specimen prop.

    No players and no matchups: `build_props` reads `props` and nothing else,
    and a register carrying the rest of a real tournament would make the
    emitted JSON move whenever that tournament did.
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "tournament": "us-open",
        "season": "2026",
        "version": 2,
        "generated_at": NOW.isoformat(),
        "draw_released": False,
        "players": [],
        "matchups": [],
        "props": [specimen_prop()],
    }


def specimen_prices(case: str) -> dict[int, dict[str, Any]]:
    """Readings for one case.

    `incomplete` is CERT-430's executed specimen — Alcaraz's leg produced
    nothing at all, so it is ABSENT from this map rather than present with a
    null.  `complete` is the control: the same card with both legs quoted, which
    must come back live.  A rule that darkened every comparison would satisfy
    the specimen and destroy the section, so the control is not optional.
    """
    if case not in CASES:
        raise ValueError(f"unknown case {case!r}; expected one of {CASES}")
    observed = NOW - timedelta(minutes=5)
    prices: dict[int, dict[str, Any]] = {
        SINNER_OUTCOME: {"probability": SINNER_PROBABILITY, "observed_at": observed},
    }
    if case == "complete":
        prices[ALCARAZ_OUTCOME] = {
            "probability": ALCARAZ_PROBABILITY,
            "observed_at": observed,
        }
    return prices


def build_specimen(case: str) -> dict[str, Any]:
    """The card the PRODUCTION rule publishes for one case."""
    cards = build_props(specimen_register(), prices=specimen_prices(case), now=NOW)
    if len(cards) != 1:
        raise RuntimeError(
            f"the specimen register must yield exactly one card, got {len(cards)}"
        )
    return cards[0]


def payload() -> dict[str, Any]:
    """Everything the consumer needs, and a statement of where it came from.

    `produced_by` is not decoration: it is what lets the consuming test assert
    it is reading a backend-built payload rather than a banked one, and what
    tells whoever finds a stale copy on disk which command reproduces it.
    """
    return {
        "$comment": [
            "GENERATED — do not hand-edit. Reproduce with:",
            "  PYTHONPATH=backend python3 backend/scripts/emit_comparison_specimen.py",
            "Every card below is the output of the production build_props().",
            "CERT-430 finding 1 / CERT-433 G1 — see this script's docstring.",
        ],
        "produced_by": "backend/app/utils/tournament_slate.py:build_props",
        "now": NOW.isoformat(),
        "legs": {"alcaraz": ALCARAZ_LEG, "sinner": SINNER_LEG},
        "cases": {case: build_specimen(case) for case in CASES},
    }


def main(argv: list[str]) -> int:
    if len(argv) > 1:
        sys.stderr.write(f"{argv[0]}: takes no arguments\n")
        return 2
    json.dump(payload(), sys.stdout, indent=2, sort_keys=True, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised via subprocess
    raise SystemExit(main(sys.argv))
