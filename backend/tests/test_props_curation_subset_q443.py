"""Q443 — a curated question may pin ONE leg of a market, and the women's tab
has cards.

WHY THIS FILE EXISTS, in the two failures it guards
---------------------------------------------------

**1. A pinned leg nothing can refresh darks the whole card.** The props card's
freshness is the AND over its priced outcomes, which is correct — a stale
member of a published artifact must not be presented as current. What was
missing is the other half: an outcome the price rail is *forbidden or unable*
to refresh is not a stale reading, it is a permanent one, and pinning it is
pinning a contributor that can only ever be dark.

Both shapes were live on `sinner-second-major`, measured against Kalshi on
2026-08-29:

* ``KXGRANDSLAM-JSIN26-1`` is graded (``is_winner`` TRUE; venue ``finalized`` /
  ``result: yes``) and ``futures_price_refresh._write_prices`` selects
  ``WHERE is_winner IS NOT TRUE`` — gotcha #21, re-pricing a settled book can
  only corrupt resolved state. The refusal is right; pinning the row anyway is
  what was wrong.
* ``KXGRANDSLAM-JSIN26-3`` was **delisted**. The venue event carried three legs
  when the curation was written and carries two now, so the ticker can never
  appear in a price payload again and the row is frozen at a 2026-07-24 1%.

Neither leg is printed — an answer card prints its answer — so both bought a
permanent dark contributor and no information, while the answer leg itself was
forty minutes old. This is the producer/renderer lockstep #2199 fixed on the
CLOCK, one level down on the POPULATION.

**2. The women's tab had never had a card.** Not because no women's market
exists but because the Day-1 census was a nine-ticker lookup, and the
nationality series were reachable by exactly the query nobody ran. A count is
not a guard, so the guard here is the property Alex asked for: the committed
register curates a non-advance question for BOTH draws.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from app.utils.tournament_register import (
    load_register,
    us_open_2026_contract,
    validate_register,
)

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/populate_tournament_props.py"

DUMP_COLUMNS = [
    "market_id", "market_ext", "source", "market_name", "status",
    "outcome_id", "outcome_name", "current_probability",
]


def _run(tmp_path, dump_rows):
    dump = {"columns": DUMP_COLUMNS, "rows": dump_rows, "truncated": False}
    (tmp_path / "dump.json").write_text(json.dumps(dump))
    register = json.loads(
        (ROOT / "data/tournament_registers/us-open-2026.json").read_text()
    )
    (tmp_path / "reg.json").write_text(json.dumps(register))

    result = subprocess.run(
        [sys.executable, str(SCRIPT),
         "--register", str(tmp_path / "reg.json"),
         "--dump", str(tmp_path / "dump.json"),
         "--observed-at", "2026-08-29T21:00:00+00:00",
         "--version", "3", "--supersedes-version", "2",
         "--out", str(tmp_path / "out.json")],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    out = (
        json.loads((tmp_path / "out.json").read_text())
        if (tmp_path / "out.json").exists() else None
    )
    return result, out


# ═══ RE-POINTED AT THE UX-P151/P154 UNION, AND WHY THE PROPERTY IS UNCHANGED ══
#
# Q443 proved the subset pin on `sinner-second-major`, pinning the answer leg of
# `KXGRANDSLAM-JSIN26` and leaving its graded `1+` and delisted `3+` unpinned.
# That card no longer exists: UX-P151 retired the two separate `*-second-major`
# cards into one combined card, and UX-P154 made the grouping automatic — the
# two grand-slam markets are now detected as the template family
# `"{} grand slam wins in 2026"`, and a family names ONE `compare_outcome` per
# member, so the ladder's unrefreshable rungs cannot be pinned by construction.
#
# The subset mechanism itself is untouched and still load-bearing — on Q443's
# OWN women's cards. `sabalenka-title-defence` pins one contender out of the
# whole `KXWTAGRANDSLAM-26` field, which is the same shape the Sinner ladder
# tested (one named leg kept, every sibling dropped) on a card the union
# actually has. So the assertions move markets and keep their property.
#
# WHAT WOULD HAVE HAPPENED IF THEY HAD SIMPLY BEEN DELETED: the union would have
# shipped `sabalenka-title-defence` and `usa-women-quarterfinal-count`, both of
# which pin a subset, with nothing at all guarding the pin.

#: The grand-slam family, as the venue and our database hold it. Every dump
#: below carries it because UX-P154's staleness guard REFUSES a curated family
#: that the dump does not contain — correctly: a curated family nobody quotes
#: any more is a decision to re-make, not a card to skip. The production dump
#: always holds both members (see this script's module docstring), so a fixture
#: without them was never a shape the pass runs against.
_GRAND_SLAM_FAMILY = [
    [53796, "KXGRANDSLAM-CALC26", "kalshi",
     "Carlos Alcaraz: Grand Slam wins in 2026", "open",
     848773, "2+ Grand Slam wins", "0.27"],
    [53796, "KXGRANDSLAM-CALC26", "kalshi",
     "Carlos Alcaraz: Grand Slam wins in 2026", "open",
     848772, "3+ Grand Slam wins", "0.02"],
    [53795, "KXGRANDSLAM-JSIN26", "kalshi",
     "Jannik Sinner: Grand Slam wins in 2026", "open",
     848769, "2+ Grand Slam wins", "0.01"],
    [53795, "KXGRANDSLAM-JSIN26", "kalshi",
     "Jannik Sinner: Grand Slam wins in 2026", "open",
     848768, "3+ Grand Slam wins", "0.01"],
]

#: The WTA grand-slam FIELD. `sabalenka-title-defence` pins exactly one of these
#: legs; the other two exist so "only the legs it names" has something to drop.
_WTA_FIELD = [
    [194, "KXWTAGRANDSLAM-26", "kalshi",
     "Who will win a WTA Grand Slam in 2026?", "open",
     1181, "Aryna Sabalenka", "0.235"],
    [194, "KXWTAGRANDSLAM-26", "kalshi",
     "Who will win a WTA Grand Slam in 2026?", "open",
     1182, "Iga Swiatek", "0.210"],
    [194, "KXWTAGRANDSLAM-26", "kalshi",
     "Who will win a WTA Grand Slam in 2026?", "open",
     1183, "Coco Gauff", "0.160"],
]


def test_a_curation_pins_only_the_legs_it_names(tmp_path):
    """The subset is honoured: three legs in the dump, one on the card.

    RED BEFORE THIS CHANGE: the writer emitted every row of the market, so the
    card carried the graded `1+` and the delisted `3+` as freshness
    contributors that nothing is allowed or able to refresh.
    """
    result, out = _run(tmp_path, _GRAND_SLAM_FAMILY + _WTA_FIELD)
    assert result.returncode == 0, result.stderr

    card = next(p for p in out["props"] if p["key"] == "sabalenka-title-defence")
    assert [o["display_name"] for o in card["outcomes"]] == ["Aryna Sabalenka"]
    assert [o["outcome_id"] for o in card["outcomes"]] == [1181]
    # And the one leg it kept is still the leg that answers the question.
    assert [o["is_answer"] for o in card["outcomes"]] == [True]

    # THE OTHER HALF OF THE SAME PROPERTY, which is now the family's to keep:
    # the combined card names ONE outcome per member market, so the rungs
    # nothing can refresh (Sinner's graded `1+`, his delisted `3+`) are not
    # pinned either. This is the assertion that would have caught a family
    # card built by dumping every leg of both markets.
    combined = next(p for p in out["props"] if p["key"] == "second-major")
    assert sorted(o["outcome_id"] for o in combined["outcomes"]) == [848769, 848773]


def test_a_subset_naming_an_outcome_the_market_does_not_have_is_refused(tmp_path):
    """A curation that no longer matches its market is a decision to re-make.

    The silent alternative is the whole defect class: the venue renames or
    delists a leg, the pin quietly matches nothing, and the card ships a leg
    short with every test green.

    The assertion distinguishes the SUBSET refusal from the older ANSWER
    refusal — "curated outcome" against "curated answer" — because a renamed
    answer trips both, so an exit-code assertion here would be green on both
    sides of this change and prove nothing about the pin. The rest of the
    sentence is shared on purpose: one class of refusal, one wording.
    """
    renamed = _GRAND_SLAM_FAMILY + [
        [194, "KXWTAGRANDSLAM-26", "kalshi",
         "Who will win a WTA Grand Slam in 2026?", "open",
         1181, "A. Sabalenka", "0.235"],
    ]
    result, out = _run(tmp_path, renamed)

    assert result.returncode == 1, result.stdout
    assert "REFUSED" in result.stderr
    assert "curated outcome 'Aryna Sabalenka'" in result.stderr, result.stderr
    assert "is not an outcome of this market" in result.stderr
    # Refused means REFUSED: nothing was written.
    assert out is None


def test_an_unpinned_curation_still_writes_every_leg(tmp_path):
    """THE CONTROL. `outcomes` is optional and its absence changes nothing.

    A guard that only proves the new path works cannot tell a subset feature
    from a silent truncation of every card. `sinner-competes` names no subset
    and must keep the shape it has always had.
    """
    result, out = _run(tmp_path, _GRAND_SLAM_FAMILY + [
        [59172808, "KXATPCOMPETE-26USOSIN", "kalshi", "Sinner competes", "open",
         219796782, "Yes", "0.01"],
        [59172808, "KXATPCOMPETE-26USOSIN", "kalshi", "Sinner competes", "open",
         219796783, "No", "0.99"],
    ])
    assert result.returncode == 0, result.stderr

    card = next(p for p in out["props"] if p["key"] == "sinner-competes")
    assert sorted(o["display_name"] for o in card["outcomes"]) == ["No", "Yes"]


def test_the_subset_pass_writes_a_register_that_still_validates(tmp_path):
    result, out = _run(tmp_path, _GRAND_SLAM_FAMILY + _WTA_FIELD)
    assert result.returncode == 0, result.stderr
    assert validate_register(out, us_open_2026_contract()) == []


# ── The ship: both draws have a question ─────────────────────────────────────

def test_the_committed_register_curates_a_question_for_both_draws():
    """Alex, 2026-08-28: the women's tab gets non-advance questions of its own.

    RED BEFORE THIS CHANGE: every prop in the committed register was
    `mens-singles`, so `propsForDraw(markets, "womens-singles")` returned an
    empty list and the tab rendered its honest-empty state — for a curation
    reason, not a pricing one.

    Asserted as a PROPERTY of each draw rather than as a count, because a count
    is satisfied by adding anything and this is satisfied only by adding a
    question the draw's own audience would ask.
    """
    register = load_register("us-open", "2026")
    props = register.get("props") or []
    assert props, "the props population pass has not run"

    by_draw: dict[str | None, list[str]] = {}
    for prop in props:
        by_draw.setdefault(prop.get("draw"), []).append(prop["key"])

    for draw in ("mens-singles", "womens-singles"):
        # A tournament-wide prop (`draw: None`) shows under both pills, so it
        # counts for either — the same rule `propsForDraw` applies.
        eligible = by_draw.get(draw, []) + by_draw.get(None, [])
        assert eligible, (
            f"no curated question for {draw}: the tab renders its empty state. "
            f"Draws present: {sorted(k or 'tournament-wide' for k in by_draw)}"
        )


def test_no_committed_prop_key_reads_as_an_advance_to_round_question():
    """A key ending in a round name is rotated out by the render, silently.

    `lib/tournamentProps.advanceRound` routes any prop whose key ends in
    `-quarterfinals` / `-semifinals` / `-final` / `-round-of-N` to the Bracket
    tab (UX-P139, ruling 3), because those are grid cells. The nationality
    questions are ABOUT reaching a round without being per-player grid cells,
    so they are legitimate props with keys that must not trip that rule — and
    "how many Americans reach the final" is one careless rename away from
    doing so, which would empty the card with no error anywhere.
    """
    suffixes = (
        "-round-of-128", "-round-of-64", "-round-of-32", "-round-of-16",
        "-quarterfinals", "-quarter-finals", "-semifinals", "-semi-finals",
        "-final",
    )
    register = load_register("us-open", "2026")
    for prop in register.get("props") or []:
        key = prop["key"].lower()
        offender = next((s for s in suffixes if key.endswith(s)), None)
        assert offender is None, (
            f"prop {prop['key']} ends in {offender!r}, so `advanceRound` routes "
            "it to the Bracket tab and the card never renders here"
        )
