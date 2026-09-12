"""#5661 — the observation-time rule holds at EVERY stamp site, not the one we tested.

#4028 fixed `_phase2_persist_group_reading` and guarded it by driving that
function. The rule it established is general — *a re-stamp is only honest when
it records a re-OBSERVATION* — but the guard was specific, so when a second
`stamp_source_reading` call forty lines away kept defaulting its own clock,
nothing went red.

WHAT THE READER SAW (lane1b/193, 2026-09-12 15:55Z). Bournemouth 2-2 Brentford,
LIVE at 78 minutes, `/events/15297674`: our page served **Polymarket 40.5%**
stamped `15:46:41Z`, while Gamma the same minute had the market `active`,
`closed: false` and quoting **0.215**. Our `futures_outcomes` rows for it were
all `last_updated 13:08:06Z` — **52 minutes before the 14:00Z kickoff.** The
condition ids matched Gamma's exactly, so nothing was mislinked. A price that
died before the game started was being served as a live one, three quarters of
the way through the match.

WHY THE SECOND SITE LOOKED DEFENSIBLE, WHICH IS WHY IT SURVIVED. Unlike the
15-minute matcher, `_poll_live_prediction_market_prices` genuinely DOES
re-observe the venue — it calls Kalshi `/markets` and Polymarket Gamma. On that
reading its own `now()` is an honest assertion. But it re-observes in an earlier
PHASE, and the stamping loop then runs over the re-queried live population
WHOLE: every market whose fetch was skipped, errored, or never reached because
the pass threw partway is stamped too. That task was failing 72 of 79 starts on
an asyncpg deadlock when this was measured. **Re-observing sometimes is not
re-observing**, and a writer cannot tell which rows it refreshed from the fact
that it refreshed some.

═══ WHY THIS GUARD IS STRUCTURAL AND WHAT THAT COSTS ═══

It is an AST scan, and a source scan is ordinarily the weaker kind of test — it
proves a call is WRITTEN, never that it RUNS. That trade is taken deliberately
here, because the defect class is not "this call site is wrong", it is **"a call
site was missed"**, and a behavioural test of site two cannot fail for site
three. #4028's guard was behavioural, thorough, and did not stop this.

So the two are complements and both are kept: `test_observation_stamp_ghost_
freshness_4028.py` proves the mechanism end to end on one path, and this proves
no path was forgotten. Neither subsumes the other.

The scan resolves import ALIASES rather than matching a literal name, because
both known call sites are aliased (`_stamp` and `_stamp2`) and a guard keyed on
the spelling `stamp_source_reading(` would have matched neither of them — it
would have passed on a file with zero compliant calls, which is the vacuous
guard this file exists to avoid being.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]

#: The function whose `now=` is the observation-time contract.
STAMPER = "stamp_source_reading"

#: The only admissible source of that `now=`. Composite-safe by construction —
#: it takes the SEQUENCE of contributing rows and returns the oldest, so the
#: single-market case is the one-element case rather than a separate rule
#: (CERT-2745).
OBSERVER = "oldest_observation_time"

#: Modules that write `win_probability_sources` from rows they may not have
#: re-observed. Enumerated rather than globbed: a new writer should have to
#: appear here by a human decision, which is itself the review this file wants.
GUARDED = ("app/tasks/prediction_market_matching.py",)


def _aliases_of(tree: ast.AST, name: str) -> set[str]:
    """Every local name bound to ``name`` by an import in this module.

    Both real call sites import it aliased, so resolving the alias is not
    thoroughness — it is the difference between this guard working and this
    guard matching nothing at all.
    """
    found = {name}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for a in node.names:
                if a.name == name:
                    found.add(a.asname or a.name)
    return found


def _stamp_calls(tree: ast.AST, names: set[str]) -> list[ast.Call]:
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        called = getattr(func, "id", None) or getattr(func, "attr", None)
        if called in names:
            out.append(node)
    return out


@pytest.mark.parametrize("rel", GUARDED)
def test_every_stamp_site_passes_an_observation_time(rel):
    path = BACKEND / rel
    tree = ast.parse(path.read_text())
    names = _aliases_of(tree, STAMPER)

    calls = _stamp_calls(tree, names)
    # Non-vacuity. If the aliases stop resolving, or the calls move to another
    # module, this file must fail LOUDLY rather than pass over an empty set —
    # "no call sites" and "no bad call sites" are the same green otherwise.
    assert len(calls) >= 2, (
        f"expected at least the two known {STAMPER} call sites in {rel}, found "
        f"{len(calls)} (resolved names: {sorted(names)}). If they moved, move "
        "this guard; do not let it pass on an empty scan."
    )

    offenders = [
        c.lineno
        for c in calls
        if not any(kw.arg == "now" for kw in c.keywords)
    ]
    assert offenders == [], (
        f"{rel}: {len(offenders)} {STAMPER} call(s) at line(s) {offenders} do "
        "not pass `now=`. A writer that defaults its own clock is asserting it "
        "observed the venue at that instant. If it merely re-read a row it "
        "already had, that is a frozen price served as fresh (#4028, #5661) — "
        "and because the hero's decay is RELATIVE to the freshest stamp on the "
        "event, the dead source then decays the honest one. Pass "
        f"`now={OBSERVER}(<every row the number came from>)`; it is inert when "
        "those rows are healthy."
    )


def test_the_observation_time_comes_from_every_contributing_row():
    """`now=` must be an observation of the ROWS, not any convenient datetime.

    `now=datetime.now(timezone.utc)` satisfies the assertion above while
    changing nothing — the mutation that makes this guard look green and the
    product still wrong. CERT-767's lesson also rides here: the argument is the
    ORIGINATING outcome, not the group's primary, because the group's primary
    can be a different market that is still being quoted.

    IT IS THE COMPOSITE-SAFE HELPER, NOT THE SINGLE-ROW ONE (CERT-2745). The
    first cut of #5661 passed `source_observation_time(reading.outcome)` and was
    refused: a devigged reading is the mean of two separately-fetched markets,
    so a fresh 70% primary averaged with a stale 60% sibling published 65%
    stamped at the PRIMARY's time. `oldest_observation_time` takes the sequence
    and returns its minimum, so requiring it here is what makes the single-row
    case and the composite case one rule instead of two. Passing the single-row
    primitive at a stamp site is now the offence, and that is deliberate: the
    primitive is correct for one row and silently wrong for a devig, which is
    exactly the shape that got through the first time.
    """
    path = BACKEND / GUARDED[0]
    tree = ast.parse(path.read_text())
    names = _aliases_of(tree, STAMPER)
    obs_names = _aliases_of(tree, OBSERVER)

    bad = []
    for call in _stamp_calls(tree, names):
        for kw in call.keywords:
            if kw.arg != "now":
                continue
            inner = kw.value
            called = None
            if isinstance(inner, ast.Call):
                called = getattr(inner.func, "id", None) or getattr(
                    inner.func, "attr", None
                )
            if called not in obs_names:
                bad.append((call.lineno, ast.dump(inner)[:60]))

    assert bad == [], (
        f"every `now=` handed to the stamper must be `{OBSERVER}(...)` over "
        "every contributing row — not the single-row primitive, which dates a "
        f"devig by its freshest half (CERT-2745); offenders: {bad}"
    )
