"""#6826 — a finished prop group with no verdict under it stops saying "chance of hitting".

`bainluck://events/15297724` — Manchester United 0–1 Manchester City, FINAL,
played Sep 13.  The hero is correct, and the Additional Markets card two rows
down already says `settled — any percentage is a last quote`.  Between them the
Player Props card said:

    TEAM CORNERS   chance of hitting
      6+  [-----------------]  99%

Present tense, four days after the whistle, with no actual value and no ✓/– on
either rung.  Served payload for both rungs:

    {"outcome_name": "Manchester City: 6+", "over_probability": 0.99,
     "actual": null, "hit": null,
     "is_winner": true, "resolution_source": "clean_resolution"}

The number is right and stays; the caption's tense is the whole defect.

WHY THE FIX IS PER-GROUP AND NOT PER-EVENT
------------------------------------------
The issue asked for "a finished EVENT with zero gradeable rungs".  Measured on
production 2026-09-17 over 6 finished events carrying priced prop groups
(`/api/events/{id}/game-markets`, grouped the way the card groups them — by
player × market name — and filtered to priced ladders, which are the only ones
that draw a caption):

    297 priced groups, 259 graded, 38 with no verdict on any rung
    5 of the 6 events are MIXED; only the filed soccer one is uniformly ungraded
    36 of the 38 ungraded groups sit on an event that ALSO carries graded groups

An event-scoped predicate would therefore have repaired the filed specimen's 2
rungs and left 95% of the class on the screen — a fix that photographs as
delivered.  So the flag is scoped to the group the caption sits on.

WHY A BACKEND GUARD EXISTS FOR AN iOS CAPTION
----------------------------------------------
Two holes the Swift test cannot cover, both of which leave it green while the
defect is back on the screen:

1. **CI compiles no Swift (#4302).**  The Swift test runs only on a lane's
   machine when someone remembers.  This file runs in CI on every push.

2. **The Swift test asserts on the pure helper, not on the view.**  Every
   assertion in `SuspendedProjectionTests` passes if `statGroupView` hands
   `hasGradedRung: true` as a literal, or stops reading `verdict(for:)`, or
   scopes the answer to the event again — and the caption is wrong again on all
   38 groups.  The helper's claim to describe the real card rests entirely on
   the view computing that argument from the same verdict the ✓/– is drawn
   from; this file is what makes that enforceable.

Anchored per site, never by count (CERT-550's lesson on
`test_ios_missing_probability_render.py`): a global count of a token cannot say
WHICH site carries it, so one site can be un-wired while another is added and
the total holds.
"""

import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parents[2]
VIEW = REPO / "ios/Bain Luck/Bain Luck/Components/PlayerPropsCardView.swift"
STATE = REPO / "ios/Bain Luck/Bain Luck/Utilities/EventState.swift"

# The two strings the card is allowed to caption a rung with. Neither is a new
# wording call: "last quoted chance" is the phrase Alex ruled for #4018 / D120
# ("keep the numbers, change three words") and is already shipping on the
# abandoned arm.
PAST_TENSE = "last quoted chance"
PRESENT_TENSE = "chance of hitting"


def _strip_comments(text: str) -> str:
    """Source with comments removed.

    Both files DOCUMENT this fix at length — the doc comment on
    `propsChanceCaption` quotes both captions and names the rejected
    `!canStillBeGraded` widening — so a guard reading raw bytes would match its
    own explanation and could be silenced by deleting a comment rather than by
    repairing the view.
    """
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("//")
    )


def _call_block(src: str, opening: str) -> str:
    """The call beginning on `opening`, plus the lines that continue it.

    Walked line by line rather than matched with one regex spanning the call:
    the obvious pattern for "a call and everything up to its closing paren"
    puts an alternation inside a star and backtracks exponentially, which
    CodeQL correctly refuses (2 high-severity alerts cost `df3f40b37` a rewrite
    on #6681).  A linear walk is also the clearer statement of the intent.
    """
    lines = src.splitlines()
    for index, line in enumerate(lines):
        if opening not in line:
            continue
        block = [line]
        depth = line.count("(") - line.count(")")
        for following in lines[index + 1:]:
            if depth <= 0:
                break
            block.append(following)
            depth += following.count("(") - following.count(")")
        return "\n".join(block)
    return ""


def test_the_caption_render_asks_the_group_whether_anything_is_graded():
    """The view must PASS the fact, not assume it."""
    block = _call_block(_strip_comments(VIEW.read_text(encoding="utf-8")),
                        "EventState.propsChanceCaption(")
    assert block, (
        "The `EventState.propsChanceCaption(` call is gone from "
        "PlayerPropsCardView. If the caption moved, move this guard with it."
    )

    assert "hasGradedRung:" in block, (
        "The props caption no longer passes `hasGradedRung:`. Without it the "
        "caption is decided by the event status alone and a finished group "
        "with no ✓/– under it says 'chance of hitting' again (#6826)."
    )

    for literal in ("hasGradedRung: true", "hasGradedRung: false"):
        assert literal not in block, (
            f"The caption is passed a hard-coded `{literal}`. The argument has "
            "to be computed from the rungs; a literal makes every Swift "
            "assertion pass while the screen is wrong."
        )


def test_the_graded_flag_is_computed_from_the_same_verdict_that_draws_the_mark():
    """One grading rule for the mark and the caption, or they can contradict.

    `verdict(for:)` is the server-first, fail-closed resolver (#4959): a served
    `hit` wins, a served `actual` never manufactures one, and the box score is
    the only fallback.  If the caption were computed from anything else — most
    dangerously `is_winner` / `resolution_source`, which CERT-3024 BLOCKed and
    CERT-3025 refined — the card could caption a rung as graded while drawing
    no mark beside it, which is the #6826 defect with the two halves swapped.
    """
    src = _strip_comments(VIEW.read_text(encoding="utf-8"))

    match = re.search(
        r"let hasGradedRung\s*=\s*group\.rungs\.contains\s*\{(.*?)\}",
        src,
        flags=re.DOTALL,
    )
    assert match, (
        "`hasGradedRung` is no longer derived from `group.rungs.contains { … }`. "
        "The caption must be answered on the rungs beneath it."
    )

    body = match.group(1)
    assert "verdict(for:" in body, (
        "`hasGradedRung` stopped reading `verdict(for:)`. The caption and the "
        "✓/– must come from one grading rule (#4959), never two."
    )
    assert ".hit != nil" in body, (
        "`hasGradedRung` no longer tests `.hit != nil`. A served `actual` "
        "without a `hit` is a number with no claim attached — counting it as "
        "graded would re-tense the caption on rungs that draw no mark."
    )

    for forbidden in ("isWinner", "is_winner", "resolutionSource", "resolution_source"):
        assert forbidden not in body, (
            f"`hasGradedRung` reads `{forbidden}`. `clean_resolution` is written "
            "by `SET is_winner = (fo.current_probability >= 0.95)`, so the "
            "'venue's word' and the price are one signal — CERT-3024 BLOCKed "
            "typing a verdict from it and this caption is not the back door."
        )


def test_the_helper_tenses_a_finished_group_only_when_nothing_is_graded():
    """The predicate itself, read off EventState.

    Guarded here as well as in Swift because this is the assertion that fails
    if someone "simplifies" the helper back to the status — the change is one
    line and it looks like a tidy-up.
    """
    src = _strip_comments(STATE.read_text(encoding="utf-8"))
    block = _call_block(src, "static func propsChanceCaption(")
    assert block, "`propsChanceCaption` is gone or renamed"

    assert "hasGradedRung: Bool" in block, (
        "`propsChanceCaption` no longer takes `hasGradedRung`. A caption that "
        "cannot see the rungs can only guess at their tense (#6826)."
    )
    assert "= true" not in block and "= false" not in block, (
        "`hasGradedRung` grew a default value. A default is a caller silently "
        "opting out of the question, which is exactly how the second props "
        "surface would ship with the defect intact."
    )

    body = src[src.index(block) + len(block):]
    body = body[: body.index("\n    }") + 6] if "\n    }" in body else body

    assert f"isFinished(status) && !hasGradedRung" in body, (
        "The finished arm no longer reads `isFinished(status) && !hasGradedRung`. "
        "Widening it to `!canStillBeGraded` — the tempting one-liner — would "
        "re-tense all 259 graded groups too, on a ruling that covered abandoned "
        "games."
    )
    assert PAST_TENSE in body and PRESENT_TENSE in body, (
        "One of the two captions is gone. Both strings are ruled wording "
        "(#4018 / D120); this is not the place to invent a third."
    )


def test_the_abandoned_arm_is_still_answered_first():
    """#4021's clause survives the #6826 edit.

    Event 416569 sat at `status='suspended'` four days BEFORE kick-off.  The
    suspended arm reads `isSuspendedAndStarted`, and it has to be consulted
    before the graded arm: an abandoned game that somehow carried a verdict is
    still abandoned, and a fixture nobody has played is still a chance.
    """
    src = _strip_comments(STATE.read_text(encoding="utf-8"))
    block = _call_block(src, "static func propsChanceCaption(")
    tail = src[src.index(block) + len(block):]
    tail = tail[: tail.index("\n    }") + 6] if "\n    }" in tail else tail

    suspended_at = tail.find("isSuspendedAndStarted")
    finished_at = tail.find("isFinished(status)")
    assert suspended_at != -1, (
        "The suspended arm reads the bare status again. `isSuspended` alone "
        "captions a fixture suspended before kick-off 'last quoted chance' "
        "about a game nobody has played (#4021)."
    )
    assert finished_at != -1, "The #6826 finished arm is gone"
    assert suspended_at < finished_at, (
        "The finished arm now runs before the abandoned one. D120 ruled on the "
        "game stopping, not on the grade; reordering these lets a graded "
        "abandoned group print the present tense."
    )
