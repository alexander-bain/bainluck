"""ux/4788 — the futures detail payload serves the field that says who graded a row.

#4788 / #4783 / #1638. `futures_outcomes.is_winner` is `boolean NULL DEFAULT
false`, so an INSERT that merely OMITS the column stores an affirmative graded
**LOSS** on a leg nobody called (CAL-P1004R). Three of the four Polymarket
outcome INSERTs do exactly that: 27,197 legs since 2026-09-07, of which 10,337
sit on 3,308 RESOLVED markets and therefore print a red `Lost` to a reader.

`resolution_source` is the only field that separates "a grader called this a
loser" from "nobody has been here". Measured on production 2026-09-10, before
this fix:

    SELECT is_winner, resolution_source, count(*)      -- market 59700266
      FROM futures_outcomes WHERE market_id = 59700266 GROUP BY 1, 2;
    -- (false, NULL, 24)   <- printed "Lost - 0% - Settled" under "Final Results"
    -- (NULL,  NULL, 51)   <- printed nothing, correctly

    GET /api/futures/59700266 -> outcome keys:
        id, name, probability, american_odds, rank, rank_change_24h,
        probability_change_24h, opening_probability, opening_american_odds,
        is_winner, last_updated
    -- `resolution_source` is not among them.

So the renderer could not have applied the rule even in principle: the field
never travelled. Two of those 24 legs are Jaxon Smith-Njigba 7+ and 8+, which
Kalshi settled `yes` (he caught 8), and our own last recorded price on each was
99% — a confident, wrong verdict presented as settled truth.

These tests pin the CONTRACT (the key is present and carries the stored value),
not any market's grading, which the producer-side issues own.

## Why the frontend fence below lives in a BACKEND test

`outcomeRowVerdict` withholds a verdict on `resolution_source === null` and
deliberately NOT on `undefined`, because Vercel deploys ahead of Heroku: for the
length of every deploy the new bundle runs against the old payload, which has no
such key. Fail-open on ABSENT keeps that window honest.

The cost of that choice is that dropping this key from the serialiser silently
restores the defect — no test fails, no type breaks, the site just quietly prints
red `Lost` marks again. That makes the serialiser key and the `=== null` read one
contract with two halves in two languages, and the half most likely to be
"tidied" is the strict-equality one. So both halves are asserted here, together.
"""

import ast
import inspect
import pathlib
import re
import textwrap

from app.routes import futures as futures_routes


def _outcome_dict_keys(func_src: str) -> list[set[str]]:
    """The key sets of every dict literal in `func_src` that looks like an outcome."""
    # textwrap.dedent, NOT inspect.cleandoc — cleandoc strips the body's own
    # indentation relative to the `def` and the parse dies on the docstring.
    tree = ast.parse(textwrap.dedent(func_src))
    out: list[set[str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        keys = {
            k.value
            for k in node.keys
            if isinstance(k, ast.Constant) and isinstance(k.value, str)
        }
        # The outcome payload is the one that states a verdict.
        if "is_winner" in keys:
            out.append(keys)
    return out


class TestResolutionSourceIsServed:
    def test_the_detail_payload_carries_resolution_source(self):
        """`GET /api/futures/{id}` serves the grading-provenance field.

        Anchored on the AST of the payload dict, not on a substring, so the long
        comment beside the key cannot satisfy it (the containment-guard failure
        class — this module's own docstring mentions the field a dozen times).
        """
        src = inspect.getsource(futures_routes._format_market_detail)
        dicts = _outcome_dict_keys(src)
        assert dicts, "no outcome payload (a dict carrying `is_winner`) found"
        for keys in dicts:
            assert "resolution_source" in keys, (
                "an outcome payload states `is_winner` without "
                "`resolution_source`. The client cannot then tell a graded loss "
                f"from a defaulted one and prints a red `Lost` on both. Keys: {sorted(keys)}"
            )

    def test_it_is_bound_to_the_model_attribute_not_a_literal(self):
        """A `"resolution_source": None` placeholder would pass a key check and
        serve nothing — the same absence-as-truth shape (gotcha #53), and worse
        here, because a served `null` is exactly the value that means UNGRADED.
        A literal would make every row read as ungraded and blank the site's
        genuine `Won` marks."""
        src = inspect.getsource(futures_routes)
        bindings = []
        for node in ast.walk(ast.parse(src)):
            if not isinstance(node, ast.Dict):
                continue
            for k, v in zip(node.keys, node.values):
                if isinstance(k, ast.Constant) and k.value == "resolution_source":
                    assert isinstance(v, ast.Attribute), (
                        f'"resolution_source" is bound to {ast.dump(v)[:80]}, '
                        "not to a model attribute"
                    )
                    assert v.attr == "resolution_source"
                    bindings.append(ast.unparse(v))
        assert bindings, "no payload binds `resolution_source` to the model"


class TestTheFrontendFenceThatMakesTheAbsentCaseSafe:
    """Read from the FRONTEND SOURCE, so this fails when either side moves."""

    def _outcome_row_src(self) -> str:
        here = pathlib.Path(__file__).resolve().parents[2]
        return (
            here / "frontend" / "components" / "futures" / "OutcomeRow.tsx"
        ).read_text()

    def test_the_verdict_withholds_on_strict_null_only(self):
        """`=== null`, never `== null`.

        `== null` is true for `undefined` too, which folds "the old payload has
        no such key" together with "the payload says nobody graded this". During
        every deploy — Vercel ships ahead of Heroku — that would withhold on
        EVERY resolved market and blank genuine `Won` marks site-wide, to fix a
        defect that only ever prints a false `Lost`.
        """
        src = self._outcome_row_src()
        assert re.search(
            r"outcome\.resolution_source\s*===\s*null", src
        ), (
            "`outcomeRowVerdict` no longer withholds on a strict-null "
            "`resolution_source`; the ungraded-prints-no-verdict rule is gone."
        )
        loose = re.search(r"outcome\.resolution_source\s*==\s*null", src)
        assert not loose, (
            "`outcomeRowVerdict` compares `resolution_source` with `==`, which "
            "also matches `undefined`. That blanks every verdict on the site for "
            "the length of each deploy (the old payload omits the key). Use `===`."
        )

    def test_the_retraction_is_refused_and_spelled_the_same_on_both_sides(self):
        """CERT-2517's repair: `4788-DETAIL-RETRACTION-IS-NOT-A-VERDICT`.

        A non-empty `resolution_source` is NOT a grade. Exactly one value is a
        RETRACTION — `ungradeable_result` (CAL-P056, #1852) — which asserts NO
        winner and is written by `repair_kalshi_fabricated_loss.py` while leaving
        `is_winner=false` in place. Trusting it would print a confident red
        `Lost` on precisely the rows this ship exists to rescue, which is the
        reading CERT-2222 blocked on the sibling surface.

        The frontend keeps a mirror of the constant because it cannot import
        Python. A mirror that can drift is a bug waiting on a rename, so the two
        spellings are pinned to each other here — read from the FRONTEND SOURCE,
        so this fails when either side moves.
        """
        from app.utils.kalshi_fabricated_loss import RETRACTION_SOURCE

        src = self._outcome_row_src()
        m = re.search(
            r'RETRACTED_RESOLUTION_SOURCE\s*=\s*"([^"]+)"', src
        )
        assert m, "the frontend no longer names a retracted resolution source"
        assert m.group(1) == RETRACTION_SOURCE, (
            f"frontend mirror {m.group(1)!r} != backend {RETRACTION_SOURCE!r}; "
            "the futures detail page would treat a retraction as a grade."
        )
        assert re.search(
            r"outcome\.resolution_source\s*===\s*RETRACTED_RESOLUTION_SOURCE",
            src,
        ), "`outcomeRowVerdict` no longer refuses the retraction."

    def test_the_retraction_is_still_classified_terminal_no_winner(self):
        """The mirror above is only correct while the backend still treats this
        source as structurally no-winner. If it were ever promoted to an
        authoritative grade, refusing it on the page would start hiding real
        results — so the classification is asserted, not assumed."""
        from app.utils.kalshi_fabricated_loss import RETRACTION_SOURCE
        from app.utils.resolution_authority import (
            AUTHORITATIVE_SOURCES,
            TERMINAL_SOURCES,
        )

        assert RETRACTION_SOURCE in TERMINAL_SOURCES
        assert RETRACTION_SOURCE not in AUTHORITATIVE_SOURCES

    def test_no_verdict_branch_reads_is_winner_directly(self):
        """The four verdict branches — row tint, Won/Lost pill, the
        100%/0%+Settled cell, and the movement suppression — must all go through
        `outcomeRowVerdict`. A branch that restates `isResolved && is_winner ===`
        for itself is the drift this predicate exists to prevent, and it is how
        the defect renders again on one surface while the tests watch another."""
        src = self._outcome_row_src()
        # Strip block comments and line comments: the prose deliberately quotes
        # the banned pattern to explain why it is banned.
        code = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
        code = re.sub(r"^\s*//.*$", "", code, flags=re.M)
        offenders = re.findall(r"isResolved\s*&&\s*outcome\.is_winner", code)
        assert not offenders, (
            f"{len(offenders)} verdict branch(es) still read `is_winner` behind "
            "`isResolved` instead of calling `outcomeRowVerdict`."
        )
