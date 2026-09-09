"""#4096, the survivor — standing notice 33 over the coverage census's own prose.

WHY THIS FILE EXISTS, AND WHY IT IS SCOPED TO A PAYLOAD RATHER THAN A MODULE.

#4067 (ux/1141) swept the reader surfaces and both clients' label maps.
#4096's backend half (`0ea85e20`, CERT-2320) then swept the *published* prose and
the generated source names, and its guard is genuinely shape-based: it walks the
imported module and picks up every constant whose name ends `_RULE_TEXT`, so a
rule text added to that module next month is covered without anyone remembering
the guard exists.

It still missed one, and the way it missed is the whole lesson. The survivor —
:data:`OBSERVATION_UNIT_RULE` — lives in a DIFFERENT module
(``app.utils.calibration_coverage_bridge``) under a DIFFERENT naming convention
(``_RULE``, not ``_RULE_TEXT``), and is published on ``/api/calibration`` at
``calibration_coverage_census.units.published_curve_observations.rule``. A scan
scoped to one module's naming convention is a ban on one module's naming
convention, exactly as a word-ban guard scoped to ``ios/`` was a ban on one
client. Measured on production at 03:38Z 2026-09-09 (commit ``d8a63c57``): six
payload paths carried the word, five belonged to the certed sweep, and this was
the sixth.

So the scope here is **the object the census actually publishes**. Every string
anywhere inside the built payload is walked, at any depth, whatever the
constant behind it is called and whatever module it came from. A new rung, a new
reachability tier, a new unit, a new nested block — all covered on the day they
are added, because the guard never enumerates names.
"""

import re
from typing import Any, Iterator

from app.utils.calibration_coverage_bridge import (
    COVERAGE_UNIT_RULE,
    EXCLUSION_RUNGS,
    OBSERVATION_UNIT_RULE,
    REACHABILITY_TIER_KEYS,
    RESOLVED_UNIT_RULE,
    build_coverage_census,
    unavailable_census,
)

#: Identical semantics to the pattern in ``test_calibration_source_vocabulary``,
#: deliberately restated rather than imported: this guard must keep biting even
#: if that file is refactored, and a shared import would let one edit silently
#: widen both. ``\b`` in both directions means the approved word "sportsbook(s)"
#: (D91) is never matched — there is no word boundary inside it — while the
#: possessive "the books' number" IS, because an apostrophe is a boundary.
_BANNED_SUPPLIER_WORD = re.compile(r"\bbookmakers?\b|\bbooks?['’]?\b", re.IGNORECASE)


def _strings(node: Any, path: str = "") -> Iterator[tuple[str, str]]:
    """Every string in the payload, with the path a reader's client would read it at."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _strings(value, f"{path}.{key}")
    elif isinstance(node, (list, tuple)):
        for i, value in enumerate(node):
            yield from _strings(value, f"{path}[{i}]")
    elif isinstance(node, str):
        yield path, node


def _census(**kw: Any) -> dict[str, Any]:
    """The MAXIMAL census — every rung and every reachability tier known.

    The counts are arbitrary but must reconcile, or the builder emits violation
    codes instead of the cells whose prose is the thing under test. The
    reachability tiers are supplied deliberately: without them the bridge
    publishes its "unavailable" shape and :data:`RESOLVED_UNIT_RULE` and every
    tier rule never enter the payload at all — so a scan run against the
    default shape would silently cover less prose than it appears to.
    """
    rungs = {"plotted_on_curve": 10, **{k: 0 for k in EXCLUSION_RUNGS}}
    kw.setdefault(
        "reachability_tier_counts", {key: 7 for key in REACHABILITY_TIER_KEYS}
    )
    return build_coverage_census(
        rung_counts=rungs,
        sportsbook_curve_legs=5,
        published_curve_observations=15,
        published_outcomes_crosscheck=10,
        population_version="v-test",
        **kw,
    )


class TestTheCensusPublishesNoBannedSupplierWord:
    def test_the_walk_reaches_the_prose_it_claims_to_cover(self):
        """The denominator, asserted — or a clean PASS means nothing.

        A recursive scan that silently reaches nothing is the classic vacuous
        green. This pins that the walk really does arrive at the three unit
        rules and a healthy body of rung prose, so the assertion below is made
        against a populated set rather than an empty one.
        """
        found = dict(_strings(_census()))
        assert len(found) >= 20, sorted(found)

        values = set(found.values())
        assert OBSERVATION_UNIT_RULE in values
        assert COVERAGE_UNIT_RULE in values
        assert RESOLVED_UNIT_RULE in values

        # And the specific published path the survivor was found at, by path
        # rather than by value, so a rename of the constant cannot slip the net.
        assert (
            found[".units.published_curve_observations.rule"] == OBSERVATION_UNIT_RULE
        )

    def test_no_string_the_census_publishes_says_book_or_bookmaker(self):
        """The ship. Every string, any depth, whatever its constant is called."""
        offenders = [
            f"{path} = {text!r}"
            for path, text in _strings(_census())
            if _BANNED_SUPPLIER_WORD.search(text)
        ]
        assert offenders == []

    def test_the_unavailable_census_is_covered_too(self):
        """The degraded shape publishes its own prose and is a separate code path."""
        offenders = [
            f"{path} = {text!r}"
            for path, text in _strings(unavailable_census(reason="probe"))
            if _BANNED_SUPPLIER_WORD.search(text)
        ]
        assert offenders == []

    def test_machine_keys_are_exempt_and_the_pattern_is_what_exempts_them(self):
        """Notice 33's clarification: wire keys are out of scope, structurally.

        ``_`` is a word character, so there is no boundary before "bookmaker" in
        ``odds_api_bookmaker`` and the pattern cannot see it. Asserted rather
        than assumed, so a future tightening has to argue with this line instead
        of quietly reddening every source key in the codebase.
        """
        assert not _BANNED_SUPPLIER_WORD.search("odds_api_bookmaker")
        assert not _BANNED_SUPPLIER_WORD.search("bookmaker_count")
        assert not _BANNED_SUPPLIER_WORD.search("sportsbook_curve_legs")
        # The approved word survives the ban it is the remedy for.
        assert not _BANNED_SUPPLIER_WORD.search("the sportsbooks moved first")

    def test_the_pattern_still_catches_the_shapes_that_got_through_before(self):
        """The negative control — a ban nothing can trip is not a ban.

        Every one of these is a spelling that actually shipped: the singulars
        are what #4067's `books|bookmaker` grep walked past, and the hyphenated
        form is how the survivor here was written.
        """
        for shipped in (
            "from a real book",
            "grades half a book",
            "a fabricated wide-book midpoint",
            "the per-bookmaker curve",
            "totals, per-bookmaker moneyline)",
            "the books' number",
            "seven bookmakers",
        ):
            assert _BANNED_SUPPLIER_WORD.search(shipped), shipped
