"""#6081 — a leg the venue settled NO serves 0%, not the "we cannot say" null.

WHAT A READER SAW. `https://bainluck.com/futures/261` ("Boston pro baseball wins
this season?") renders the same seven-rung ladder twice, and the two blocks
disagreed about the same two rungs:

    leg          `#+ WINS` block     `All Outcomes` table
    100+ wins    0%                  -
    105+ wins    0%                  -

A dash means "we have no price". We had one. Both rows store
`current_probability = 0.000000` with `resolution_source = 'api_settlement'`,
`is_winner = false` and a `yes_bid 0.0000 / yes_ask 1.0000` book: Kalshi has
settled them NO, Boston cannot reach 100 wins, and the table printed a shrug next
to a block printing the truth.

THE CAUSE IS ONE IDIOM AND THE PAYLOAD REFUTES ITSELF. Every served outcome in
`app/routes/futures.py` was built with a TRUTH test —
`float(o.current_probability) if o.current_probability else None` — and
`Decimal('0.000000')` is falsy. So a genuine 0% was serialized as `null`, the
same value the payload uses for "withheld". `/api/futures/261` served
`prices_withheld: 0` beside two null prices: nothing withheld them, the
serializer erased them.

WHY THIS IS NOT THE WITHHOLDING RAIL. `app.utils.futures_unsupported_price`
(#5611/#5876) is the deliberate rule for "a price no book and no trade
supports" — it reads bid/ask and snapshots, nulls `WITHHELD_PRICE_FIELDS`, and
counts the row in `prices_withheld`. The falsy test was an accidental SECOND
withholding rule whose only evidence was that the number happened to be zero,
which is exactly the value a settled-NO leg must carry. Measured on production
2026-09-14: 4,200 zero-priced legs sit on 815 markets still `status='open'`, and
3,738 of them (89%) are a definite venue NO.

WHAT THESE TESTS PIN, AND WHY IN BOTH DIRECTIONS (gotcha #43). A one-way
assertion here is worthless: "0 serves 0" passes trivially on a serializer that
has stopped nulling ANYTHING, which would republish every fossil the
`futures_unsupported_price` rail exists to withhold. So each direction is
asserted against the same serializer in the same test class —

  * a stored 0 travels as 0.0,
  * a stored NULL still travels as None,
  * a row the rail withholds is STILL None and is STILL counted, and
  * the key is always PRESENT (`undefined !== null` in the client; #5539).

AND THE ONE SITE DELIBERATELY LEFT ALONE. Line ~882's lambda is an INPUT TO
`drop_incoherent_near_certain`, not a served value; feeding it 0.0 where it has
always seen None changes which rows that predicate DELETES, and its own comment
warns that getting it wrong "deletes the result from a settled market". The
source ratchet below therefore asserts exactly nine converted served sites and
that the predicate input is still the falsy form — so a later sweep that
"finishes the job" has to come and argue with this test rather than silently
change the dropper.
"""

import inspect
from types import SimpleNamespace

import pytest

from app.routes import futures as futures_routes


def _outcome(oid, prob, **over):
    """One ladder rung. `prob` is the STORED `current_probability`."""
    base = dict(
        id=oid,
        name=f"{oid}+ wins",
        external_id=f"KXMLBWINS-BOS-26-{oid}",
        current_probability=prob,
        current_american_odds=None,
        rank=oid,
        rank_change_24h=None,
        probability_change_24h=None,
        opening_probability=0.15,
        opening_american_odds=567,
        is_winner=False,
        resolution_source="api_settlement",
        last_updated=None,
    )
    base.update(over)
    return SimpleNamespace(**base)


def _market(outcomes):
    """Market 261's shape: OPEN, with rungs the venue has already settled."""
    return SimpleNamespace(
        id=261,
        name="Boston pro baseball wins this season?",
        description=None,
        category="championship",
        source="kalshi",
        external_id="KXMLBWINS-BOS-26",
        status="open",
        sport=None,
        sport_id=None,
        event_id=None,
        market_type="field",
        market_tier=5,
        llm_sport_category="baseball",
        mutually_exclusive=False,
        commence_time=None,
        resolution_date=None,
        created_at=None,
        updated_at=None,
        group_id="kalshi:KXMLBWINS-BOS-26",
        canonical_market_key=None,
        hook_description=None,
        image_url=None,
        category_tags=["baseball"],
        market_metadata=None,
        outcomes=outcomes,
    )


def _by_name(payload):
    return {o["name"]: o for o in payload["outcomes"]}


class TestTheDetailSerializerTellsZeroFromUnknown:
    """`_format_market_detail` — the specimen surface, `/api/futures/261`."""

    @staticmethod
    def _detail(market, **kw):
        return futures_routes._format_market_detail(market, **kw)

    def test_a_settled_no_leg_serves_zero_not_null(self):
        """The defect, stated as the reader met it."""
        market = _market([_outcome(90, 0.185), _outcome(100, 0), _outcome(105, 0)])
        rows = _by_name(self._detail(market))

        for name in ("100+ wins", "105+ wins"):
            assert "probability" in rows[name], "the key must be PRESENT (#5539)"
            assert rows[name]["probability"] == 0.0, (
                f"{name} stores 0.000000 — a price Kalshi settled — and the payload "
                f"served {rows[name]['probability']!r}. A null here is "
                "indistinguishable from 'withheld', and the `#+ WINS` block on the "
                "same page prints 0% for this very rung."
            )

    def test_an_unpriced_leg_still_serves_null(self):
        """The other direction, without which the test above is vacuous."""
        market = _market([_outcome(90, 0.185), _outcome(100, None)])
        rows = _by_name(self._detail(market))

        assert "probability" in rows["100+ wins"], "PRESENT and null, never omitted"
        assert rows["100+ wins"]["probability"] is None, (
            "a leg we have never priced must still serve null — 0.0 here would "
            "invent a venue claim that Boston certainly cannot reach 100 wins"
        )

    def test_the_deliberate_withholding_rail_still_nulls_and_still_counts(self):
        """#5611/#5876's rail is the rule that IS allowed to hide a price."""
        market = _market([_outcome(90, 0.185), _outcome(100, 0), _outcome(105, 0.99)])
        payload = self._detail(market, unsupported_price_outcome_ids={105})
        rows = _by_name(payload)

        assert rows["105+ wins"]["probability"] is None, (
            "a row the unsupported-price rail withheld must stay withheld — "
            "#6081 removes the ACCIDENTAL null, never the evidence-based one"
        )
        assert payload["prices_withheld"] == 1, (
            "the withheld row must still be counted; the count is how the page "
            "knows the absence was deliberate"
        )
        assert rows["100+ wins"]["probability"] == 0.0, (
            "and a zero the rail did NOT withhold still travels"
        )

    def test_zero_does_not_become_the_leader(self):
        """A 0% rung must not be crowned by the fix that makes it visible."""
        market = _market([_outcome(90, 0.185), _outcome(100, 0), _outcome(105, 0)])
        payload = self._detail(market)
        leader = payload.get("leader") or payload.get("leading_outcome")
        if leader is not None:
            name = leader.get("name") if isinstance(leader, dict) else leader
            assert name == "90+ wins", f"a zero-priced rung was crowned: {name!r}"


class TestTheSummarySerializerAgreesWithTheDetail:
    """A card and the page it opens must not disagree about one leg."""

    def test_a_settled_no_leg_serves_zero_on_the_summary_too(self):
        market = _market([_outcome(90, 0.185), _outcome(100, 0)])
        summary = futures_routes._format_market_summary(market)
        rows = {o["name"]: o for o in summary["top_outcomes"]}

        assert rows["100+ wins"]["probability"] == 0.0, (
            "the summary served a null where the detail serves 0.0 — the "
            "list/detail split this fix exists to close"
        )

    def test_the_summary_still_nulls_an_unpriced_leg(self):
        market = _market([_outcome(90, 0.185), _outcome(100, None)])
        summary = futures_routes._format_market_summary(market)
        rows = {o["name"]: o for o in summary["top_outcomes"]}

        assert rows["100+ wins"]["probability"] is None


def _conditional_probability_reads(module):
    """Every `float(o.current_probability) if <test> else None` in the module.

    AST, NOT a substring count, and the first draft of this guard proved why: a
    text scan counted the PROSE of the comment that documents the exclusion and
    reported two falsy sites where the code has one. A guard that its own
    explanation can redden is a guard that will be deleted rather than read.

    Returns `(kind, lineno)` per site, `kind` in {"falsy", "strict"}.
    """
    import ast

    tree = ast.parse(inspect.getsource(module))
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.IfExp):
            continue
        if not (isinstance(node.orelse, ast.Constant) and node.orelse.value is None):
            continue

        test = node.test
        # `if o.current_probability` — the falsy form.
        if (
            isinstance(test, ast.Attribute)
            and test.attr == "current_probability"
        ):
            found.append(("falsy", node.lineno))
            continue
        # `if o.current_probability is not None` — the strict form.
        if (
            isinstance(test, ast.Compare)
            and isinstance(test.left, ast.Attribute)
            and test.left.attr == "current_probability"
            and len(test.ops) == 1
            and isinstance(test.ops[0], ast.IsNot)
            and isinstance(test.comparators[0], ast.Constant)
            and test.comparators[0].value is None
        ):
            found.append(("strict", node.lineno))
    return found


class TestTheIdiomDoesNotComeBack:
    """A ratchet on the file, because the defect is one token wide.

    This is a structural scan and it is deliberately NOT the only guard here —
    the behavioural tests above are what prove the payload. Its job is the half
    they cannot see: that a later sweep does not reintroduce the falsy form at a
    tenth site nobody wrote a fixture for, and does not quietly convert the
    predicate input that was excluded on purpose.
    """

    def test_exactly_one_falsy_read_survives(self):
        falsy = [ln for kind, ln in _conditional_probability_reads(futures_routes) if kind == "falsy"]
        assert len(falsy) == 1, (
            f"expected exactly ONE falsy `current_probability` read left in "
            f"routes/futures.py (the `drop_incoherent_near_certain` predicate "
            f"input, excluded on purpose), found {len(falsy)} at lines {falsy}. "
            "A new one serves a genuine 0% as 'no price'; converting the last "
            "one changes which rows the coherence dropper deletes."
        )

    def test_every_served_site_uses_the_strict_form(self):
        """#7284 lowered this 9 -> 8, and the deletion is the reason.

        The site that went was `get_probability_timeline`'s participant table,
        which re-derived `current_probability` with its own copy of the strict
        idiom. It now reads `served["probability"]` from `_format_market_detail`
        — one of the eight that remain, and itself on the strict form — so the
        timeline did not lose the #6081 behaviour, it INHERITED it. A genuine
        `Decimal('0.000000')` still serves as `0.0` there, not as `None`.

        That is why a count going DOWN is not automatically a regression here,
        and equally why it must not be lowered on sight: the question to answer
        before touching this number is whether the payload the deleted site
        served still comes from a strict site, or from nowhere.
        """
        strict = [ln for kind, ln in _conditional_probability_reads(futures_routes) if kind == "strict"]
        assert len(strict) == 8, (
            f"expected 8 served sites on the strict form, found {len(strict)} "
            f"at lines {strict}. If a served site was added, give it the strict "
            "form and raise this number; if one was deleted, lower it with the "
            "payload it served."
        )

    def test_the_surviving_falsy_read_is_the_predicate_input(self):
        """Pin WHICH site kept the falsy form, not merely how many did.

        Read from the AST too: the falsy read must sit inside the call to
        `drop_incoherent_near_certain`, so a payload site converted back cannot
        satisfy the count test above by coincidence.
        """
        import ast

        tree = ast.parse(inspect.getsource(futures_routes))
        inside_the_dropper = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
            if name != "drop_incoherent_near_certain":
                continue
            for sub in ast.walk(node):
                if (
                    isinstance(sub, ast.IfExp)
                    and isinstance(sub.test, ast.Attribute)
                    and sub.test.attr == "current_probability"
                ):
                    inside_the_dropper.append(sub.lineno)

        assert len(inside_the_dropper) == 1, (
            "the one surviving falsy read is no longer the "
            "`drop_incoherent_near_certain` predicate input. Either it moved, or "
            "a payload site was converted back while the predicate input was "
            f"converted forward. Found inside the dropper: {inside_the_dropper}"
        )


@pytest.mark.parametrize("stored,expected", [(0, 0.0), (0.0, 0.0), (None, None)])
def test_the_contract_in_one_line(stored, expected):
    """Zero is a price; absent is not. The whole issue, as a table."""
    market = _market([_outcome(90, 0.185), _outcome(100, stored)])
    rows = _by_name(futures_routes._format_market_detail(market))
    assert rows["100+ wins"]["probability"] == expected or (
        expected is None and rows["100+ wins"]["probability"] is None
    )
