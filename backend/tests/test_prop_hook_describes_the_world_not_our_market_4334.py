"""#4334 (standing notice 34, #4125 item 1) — a prop card's hook states a fact
about the tennis, never how our card was built.

Production, `https://www.bainluck.com/tournaments/us-open`, 390x844, anonymous,
Wed 2026-09-09 ~07:10am PT.  `GET /api/tournaments/us-open` serves exactly five
`hook` strings and I read each one out of the LIVE DOM — every one rendered
`<p class="mt-1 text-[11.5px] leading-snug text-text-secondary">`,
`rgb(107, 114, 128)`, 11.5px.  **Four of the five described our own market:**

    Will an American reach the men's final?
      "The market asks about the American men as a group, not one at a time."

    Can three American women reach the quarterfinals?
      "One market for the whole American contingent, with a rung for one
       right through seven."

    Can Sabalenka go back-to-back?
      "She won here last year — and with the US Open the last major of 2026,
       this market is now exactly that question."   <- closing clause only

That is the grey text Alex named at 4pm on 2026-09-08 ("all the grey text is
madness, and shouldn't be user-facing at all"), and notice 34 is the rule: a
method note goes in the PR, the artifact, or a tooltip — never the page body.

🔴 A FIFTH SENTENCE MATCHES THE BAN AND IS STAYING.  `second-major` reads
*"Both already have one in 2026. These are two separate questions — they could
both do it, or neither."*, and #4334 asked for the second clause to go.  It does
not go: **ruling 143 clause 4** decided that exact sentence on the merits (two
independent binaries that must not sum to 100, under a title Alex wrote as a
race) and called the hook *"load-bearing rather than decorative"*, and Alex's
own #4125 item 1 enumeration does not list it.  A later general notice does not
silently overturn an earlier specific ruling, so the conflict is recorded as a
NAMED exemption a test pins, and referred to Alex as a lettered call.

🔴 THE BAN IS ON STRUCTURE, NOT ON THE WORD "MARKET", and that is the whole
difficulty of the class.  What a market SAYS is legitimate reader content, and
the register is full of it — *"the market still calls it close to a coin
flip"*, *"Even the market cannot separate it."*  A guard keyed on "market"
would delete those, so `test_a_hook_that_reports_what_a_market_says_survives`
is a control that must PASS while the four above FAIL, and it is the assertion
that makes this file worth more than a diff.

🔴 THE DATA HALF IS NOT THE FIX.  `populate_tournament_props.py` rewrites the
register from its curation maps, so deleting the sentences from the committed
JSON alone would restore them on the next run.  Hence
`test_the_script_refuses_a_construction_hook_at_runtime`, which drives `main()`
rather than reading its source — a source scan cannot tell a live refusal from
a commented-out one.
"""

import json
from pathlib import Path

import pytest

from app.utils.tournament_register import (
    HOOK_BANS_EXEMPT_BY_RULING,
    describes_our_market,
    load_register,
    us_open_2026_contract,
    validate_register,
)
from scripts.populate_tournament_props import (
    CURATION,
    FAMILY_CURATION,
    main as populate_main,
)

#: Verbatim from production the morning of the fix.  Each is a real sentence a
#: reader saw, not an invented specimen — a guard whose controls are made up
#: proves the predicate matches its own author's imagination.
SENTENCES_A_READER_SAW = (
    "The market asks about the American men as a group, not one at a time.",
    "One market for the whole American contingent, with a rung for one right through seven.",
    "Both already have one in 2026. These are two separate questions — they could both do it, or neither.",
    # ^ caught by the PHRASE, exempt by its prop KEY. Both halves are asserted.
    "She won here last year — and with the US Open the last major of 2026, this market is now exactly that question.",
)

#: Hooks that mention a market and are FINE, because they report what it says.
#: Three are live in the register today; the fourth is the one hook of the five
#: that needed no change at all.
WHAT_A_MARKET_SAYS = (
    "The men's favourite, and the market still calls it close to a coin flip.",
    "The women's favourite. Even the market cannot separate it.",
    "Perennially close to a first major. The market has him at even money.",
    "A withdrawal reshapes the entire men's board.",
)

REGISTER = Path(__file__).resolve().parents[1] / "data" / "tournament_registers"


def _committed_props() -> list[dict]:
    register = load_register("us-open", "2026", directory=REGISTER)
    assert register is not None, "the committed US Open register must be readable"
    props = register.get("props") or []
    # gotcha #53: an empty list would pass every assertion below by vacuity, so
    # the population is asserted before it is filtered.
    assert len(props) == 5, f"expected the 5 curated props, found {len(props)}"
    return props


# ── THE SHIP ────────────────────────────────────────────────────────────────


def test_no_committed_hook_describes_our_market():
    offenders = [
        (p.get("key"), p.get("hook"), describes_our_market(p.get("hook"), key=p.get("key")))
        for p in _committed_props()
        if describes_our_market(p.get("hook"), key=p.get("key"))
    ]
    assert offenders == [], (
        "a committed prop hook explains how the card is built, which notice 34 "
        f"bans from the page body: {offenders}"
    )


def test_the_curation_maps_the_script_writes_from_are_clean_too():
    """The register is an OUTPUT.  Guarding only the output guards one run."""
    offenders = [
        (spec.get("key"), spec.get("hook"))
        for spec in list(CURATION.values()) + list(FAMILY_CURATION.values())
        if describes_our_market(spec.get("hook"), key=spec.get("key"))
    ]
    assert offenders == [], f"a curation map still carries a construction hook: {offenders}"


def test_the_four_sentences_a_reader_saw_are_each_caught():
    """Red-first, against production text.

    Without this the ship's assertion could pass on a predicate that catches
    nothing — the shape that let `test_g7`-style guards ride green for months.
    """
    missed = [s for s in SENTENCES_A_READER_SAW if not describes_our_market(s)]
    assert missed == [], f"the predicate does not catch what a reader actually saw: {missed}"


def test_a_hook_that_reports_what_a_market_says_survives():
    """🔴 The control that decides whether this ban is usable at all."""
    wrongly_caught = [
        (h, describes_our_market(h)) for h in WHAT_A_MARKET_SAYS if describes_our_market(h)
    ]
    assert wrongly_caught == [], (
        "the ban is over-broad — it deletes hooks that report a market's PRICE, "
        f"which is legitimate reader content: {wrongly_caught}"
    )


def test_an_absent_hook_is_a_legal_prop_end_to_end():
    """Two of the four had no world-fact to keep, so the field had to go away.

    `hook` must therefore be optional at every reader: the validator, the
    register on disk, and the slate serializer's `prop.get("hook")`.
    """
    hookless = [p.get("key") for p in _committed_props() if "hook" not in p]
    assert sorted(hookless) == ["usa-men-final-berth", "usa-women-quarterfinal-count"]

    register = load_register("us-open", "2026", directory=REGISTER)
    findings = validate_register(register, us_open_2026_contract())
    assert findings == [], f"a hookless prop must still validate: {findings}"


@pytest.mark.parametrize("sentence", SENTENCES_A_READER_SAW)
def test_the_script_refuses_a_construction_hook_at_runtime(tmp_path, capsys, sentence):
    """Drive `main()`, do not read its source.

    A source scan cannot distinguish a live refusal from one behind an early
    return or a comment.  This plants each production sentence back into the
    curation map and asserts the writer stops with exit 1 before anything is
    written — which is the property that stops the next run restoring them.
    """
    register_dir = tmp_path / "registers"
    register_dir.mkdir()
    committed = (REGISTER / "us-open-2026.json").read_text()
    register_path = register_dir / "us-open-2026.json"
    register_path.write_text(committed)

    dump = tmp_path / "dump.json"
    dump.write_text(json.dumps({
        "columns": ["market_id", "market_ext", "source", "market_name",
                    "status", "outcome_id", "outcome_name", "current_probability"],
        "rows": [[1, "KXATPCOMPETE-26USOSIN", "kalshi", "Sinner to compete",
                  "open", 11, "Yes", 0.9]],
    }))

    spec = CURATION["KXATPCOMPETE-26USOSIN"]
    original = spec.get("hook")
    spec["hook"] = sentence
    argv = [
        "populate_tournament_props.py",
        "--register", str(register_path),
        "--dump", str(dump),
        "--observed-at", "2026-09-09T14:00:00+00:00",
        "--version", "99", "--supersedes-version", "98",
    ]
    try:
        import sys
        saved, sys.argv = sys.argv, argv
        try:
            code = populate_main()
        finally:
            sys.argv = saved
    finally:
        spec["hook"] = original

    err = capsys.readouterr().err
    assert code == 1, f"the writer accepted a construction hook: {sentence!r}"
    assert "describes our market" in err, err
    # and it stopped BEFORE writing — the register on disk is untouched.
    assert register_path.read_text() == committed


# ── THE EXEMPTION, PINNED IN BOTH DIRECTIONS ────────────────────────────────


def test_exactly_one_hook_is_exempt_and_a_ruling_names_it():
    """An exemption nobody can add quietly.

    Widening this set is the one way to reintroduce the class without any test
    going red, so the set is asserted by value and each entry has to carry the
    ruling it rests on.
    """
    assert set(HOOK_BANS_EXEMPT_BY_RULING) == {"second-major"}
    assert "ruling 143" in HOOK_BANS_EXEMPT_BY_RULING["second-major"]


def test_the_exempt_hook_is_caught_by_the_phrase_and_spared_only_by_its_key():
    """The exemption is a decision, not a gap in the predicate.

    If the phrase list ever stopped matching this sentence the exemption would
    become invisible, and the next sweep would have nothing to read.
    """
    prop = next(p for p in _committed_props() if p["key"] == "second-major")
    assert describes_our_market(prop["hook"]) == "separate questions"
    assert describes_our_market(prop["hook"], key="second-major") is None


def test_the_ruling_143_sentence_is_still_on_the_card():
    """Notice 34 sweeps come round again; this one is not theirs to take."""
    prop = next(p for p in _committed_props() if p["key"] == "second-major")
    assert "two separate questions" in prop["hook"]
    assert "both do it, or neither" in prop["hook"]
