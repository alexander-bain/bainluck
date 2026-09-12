"""The Discover hook prompt: authored examples, and facts the model is allowed to state. Pure.

T11-1 (#5461), presentation two, repairing CERT-2691's required repair
`5461-FEED-TIME-STAMPED-EVIDENCE-INTO-THE-HOOK`.

## What presentation one got right, and kept

`enrich_market_hooks` used to sample three blurbs per market out of the newsletter corpus under
``app/data/`` — fifty sentences lifted verbatim from the Polymarket newsletter — and paste them into
the production prompt as "Examples of great hooks", with a hard-coded fallback triple written in the
same voice. D138 forbids it: the newsletters teach the SHAPE of a good description — named subject,
explicit timing, consequence — never their sentences. So the prompt carries abstract criteria and
three examples authored here, and it is deterministic, because the old random draw meant no trace
could reproduce the instructions a given hook was written from. (The corpus filename is deliberately
not written in either module; a guard scans both for it.)

## What presentation one got WRONG, and this fixes

The prompt told the model to *"State ONE specific development — what happened, or what is about to"*
while handing it nothing but a market name, a category, a leaderboard of probabilities, a resolution
date and a volume. **There is no development in that input.** The model could only invent one, or
reach for whatever its training data remembers about a 2026 question — and the sentence goes on a
card as if we stood behind it. An original sentence that is not fact-grounded is not an improvement
on a borrowed one; it is the same TRUTH failure with better provenance.

So the prompt now has an **EVIDENCE block**: a bounded list of dated, sourced facts, and an
instruction that nothing outside that list may appear in the sentence. Two things make it a real
constraint rather than a decoration:

* the evidence is built from fields we actually hold, each carrying the date it was true and who
  says so (:func:`build_hook_evidence`);
* when there is no dated evidence, the task **does not call the model at all**
  (:func:`should_generate_hook`), and when the model answers that the evidence supports nothing
  worth saying, its ``NO_HOOK`` reply is honoured (:func:`accept_hook_output`). A card with no
  hook is a supported state on both clients and is what notice 34 asks for: if a thing cannot be
  said honestly, leave the space empty.

## What presentation TWO got wrong, and this fixes

Two things, both found by generating 30 real lines instead of 30 prompts — the output half
CERT-2691 asked for and presentation two did not bank.

1. **The prompt forbade invention and demanded it in the same breath.** It asked for "WHY a reader
   should care RIGHT NOW" while the evidence was a settlement date. The model resolved the
   contradiction the only way it could: *"ahead of a critical debate scheduled for next month"* on
   the 2028 election, *"early voting just around the corner"* on Maine Senate. Neither had any
   debate or voting date in evidence. Worse, both phrases are near-copies of the authored example
   about a debate before early voting — the examples, listed on their own, were read as material.
   So the demand is gone, the momentum vocabulary is named and banned, and every example is shown
   **beside the evidence line it is entailed by**, one of them declining.
2. **A settlement date cannot carry a sentence by itself.** With invention removed, 26 of 30 lines
   became "The question 'X' is settled no later than DATE" — true, entailed, and exactly the grey
   diagnostic prose standing notice 34 struck off the US Open page, off a date that is usually the
   padded latest-possible settlement (#2644). :func:`should_generate_hook` now gates on the KIND of
   evidence, so those markets are not asked about at all.

**What this deliberately does NOT do.** It adds no news source. The evidence we hold is a linked
fixture's schedule and a settlement date, so the honest hook is a short, timed sentence, not a
story — and where we hold neither, there is no hook. Real reporting behind a hook is #870's ship,
and #4066's. This one makes the sentence answerable for.

**The cost, stated plainly.** Measured 2026-09-12: all 1,076 open markets currently serving a hook
have no linked fixture, so the gate empties every one of them as they age past the seven-day serve
window, and fills only fixture-linked markets. That is a real reduction in how many cards carry a
context line, taken deliberately: the lines it removes are invented or jargon, and notice 34 says
an empty space beats an explained one. Widening the evidence — a leaderboard leader is also a dated
fact we hold — is the obvious next rung and is not attempted here.

**Why the venue's resolution date is cited as a resolution date and never as "when this happens".**
Measured 2026-09-12: Kalshi's `expiration_time`, which is what we store, is the LATEST POSSIBLE
settlement — on the US Open singles markets it read Sep 27/28 while the finals were Sep 12/13
(#2644). Evidence lines say what the field means, not what we wish it meant, and a linked fixture's
start time is preferred over it whenever we have one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Sequence

__all__ = [
    "HookEvidence",
    "HOOK_STYLE_CRITERIA",
    "HOOK_EXAMPLES",
    "NO_HOOK_SENTINEL",
    "build_hook_evidence",
    "build_hook_prompt",
    "should_generate_hook",
    "accept_hook_output",
]


#: What the model must reply when the evidence supports nothing worth a reader's time. It is a
#: first-class answer, not a failure: `accept_hook_output` turns it into "no hook", the card keeps
#: its deterministic copy, and nothing unsupported reaches a reader.
NO_HOOK_SENTINEL = "NO_HOOK"


#: A settlement date is a fact about OUR mechanics, not about the world: it says when a question
#: stops being open. It is cited so a sentence built on something else may anchor against it, but on
#: its own it can only produce "the question X is settled no later than DATE" — see
#: :func:`should_generate_hook` for the measurement that retired that sentence.
SETTLEMENT_EVIDENCE = "settlement"

#: Something that actually happens on a date: a fixture's scheduled start. This is what a hook can
#: be made of.
EVENT_EVIDENCE = "event"


@dataclass(frozen=True)
class HookEvidence:
    """One fact the hook is allowed to state, with the date it holds and who says so.

    `fact` is written as a sentence rather than a field dump so the model has no reason to
    re-describe it; `as_of` and `source` are printed beside it so an unsupported claim is
    visible by comparing the output against the block.

    `kind` is not shown to the model. It exists so the caller can ask whether this block contains
    anything a reader would want, which is a different question from whether it contains anything
    true.
    """

    fact: str
    as_of: str
    source: str
    kind: str = EVENT_EVIDENCE

    def render(self) -> str:
        return f"- [{self.as_of} · {self.source}] {self.fact}"


#: The shape a good hook has, stated so it applies to a subject the model has not seen.
#:
#: Presentation three rewrote four of these against measured output. Presentation two asked for
#: "only what EVIDENCE supports" and then, in the same breath, for a reason to care; on 11 production
#: markets the model resolved that contradiction by inventing the reason — "ahead of a critical
#: debate scheduled for next month" on a 2028 election question whose only evidence was a settlement
#: date. An instruction that forbids invention in general, while demanding a specific thing the
#: evidence cannot supply, is an instruction to invent. So the demands the evidence cannot meet are
#: gone, and the three failure classes the run actually produced are named outright.
HOOK_STYLE_CRITERIA: tuple[str, ...] = (
    "State ONLY what an EVIDENCE line supports. If it is not in EVIDENCE, you may not write it — "
    "not as a detail, not as background, not as a hedge.",
    "Name the subject plainly, the way a headline names it.",
    "Anchor the sentence in time using the dated evidence: a day, a date, or a bounded window.",
    "Do NOT explain why it matters, what is at stake, what it could influence, or what comes next. "
    "A reason-to-care that no EVIDENCE line states is invented, and inventing one is the single "
    "most common way this goes wrong.",
    "Do NOT describe momentum or a mood: no race heating up, no shifting standings, no contenders "
    "preparing, no window closing, no pivotal or crucial moment. None of that is in EVIDENCE.",
    "Name no person, team, place, contest or event that does not appear in an EVIDENCE line.",
    "A short true sentence beats a long suggestive one. Write for someone who has not been "
    "following: no insider shorthand, no unexplained names.",
    f"If the evidence supports nothing worth a reader's time, reply exactly {NO_HOOK_SENTINEL} and "
    "nothing else. That is a correct answer, not a failure.",
)


#: Examples authored for this file, each shown BESIDE the evidence it was written from.
#:
#: Presentation two listed three rich narrative sentences on their own, and the model read them as
#: material: "the only debate either has agreed to ... before early voting opens" came back on the
#: 2028 election card as "ahead of a critical debate ... as early voting approaches", and on the
#: Maine Senate card as "early voting just around the corner". Neither had any debate or any voting
#: date in evidence. An example detached from its evidence teaches the padding it is supposed to
#: prevent, so each example now carries the line it is entailed by, and one of them declines.
#:
#: The subjects are invented outright — no real club, person or contest — so nothing here can be
#: lifted as a fact about the world even if it is copied wholesale.
HOOK_EXAMPLE_PAIRS: tuple[tuple[str, str], ...] = (
    (
        "- [Sep 13, 2026 · our fixture schedule] Northgate vs Riverside is scheduled for "
        "Sep 13, 2026.",
        "Northgate and Riverside meet on September 13.",
    ),
    (
        "- [Mar 04, 2027 · settlement rules] The question 'Which party controls the chamber?' is "
        "settled no later than Mar 04, 2027. It may be decided earlier.",
        "Control of the chamber is settled by March 4, 2027, and may be decided before then.",
    ),
    (
        "- [Jan 01, 2028 · settlement rules] The question 'Who wins the prize?' is settled no "
        "later than Jan 01, 2028. It may be decided earlier.",
        NO_HOOK_SENTINEL,
    ),
)

#: The example sentences alone. Guards assert each one reaches the prompt and obeys the rules it
#: teaches; the pairing above is what the model is actually shown.
HOOK_EXAMPLES: tuple[str, ...] = tuple(sentence for _, sentence in HOOK_EXAMPLE_PAIRS)


_EXAMPLES_PREAMBLE = (
    "Examples of the SHAPE, not the material — each shown under the EVIDENCE it was written from. "
    "They are written as illustrations and describe no real event: copy their structure, never "
    "their subjects, wording or facts. Note what the sentences do NOT contain: no reason the "
    "reader should care, no stakes, no momentum, and nothing the evidence line above them does not "
    "say. The third declines, because a bare settlement date a year out is worth nobody's time."
)

_EVIDENCE_PREAMBLE = (
    "EVIDENCE — the ONLY facts you may state. Each line carries the date it holds and who says so. "
    "A sentence containing anything not traceable to a line below is a wrong answer, even if it is "
    "true in the world."
)

_NO_EVIDENCE_BLOCK = (
    "EVIDENCE — none. There is no dated, sourced fact for this question, so there is nothing you "
    f"are permitted to state. Reply exactly {NO_HOOK_SENTINEL}."
)


def _as_of(value: Optional[datetime]) -> Optional[str]:
    return value.strftime("%b %d, %Y") if value else None


def _aware(value: datetime) -> datetime:
    """Naive datetimes arrive from some writers; compare them as UTC rather than raising."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def build_hook_evidence(
    *,
    market_name: str,
    resolution_date: Optional[datetime] = None,
    resolution_source: Optional[str] = None,
    event_commence_time: Optional[datetime] = None,
    event_home_team: Optional[str] = None,
    event_away_team: Optional[str] = None,
    now: Optional[datetime] = None,
) -> tuple[HookEvidence, ...]:
    """The bounded set of dated, sourced facts a hook for this market may state.

    Bounded on purpose: two kinds of fact, both of which we hold with a date and a provenance. A
    fixture's scheduled start comes first because it is the thing that actually happens; the venue's
    resolution date is cited *as a resolution date*, never as the event's timing, because it is
    frequently a padded latest-possible settlement (#2644).

    **A fixture already under way is dropped rather than described.** Measured on production while
    building this: `US Open ATP: Karen Khachanov vs Alexander Blockx` settles Sep 16 but its linked
    fixture started Sep 09 — cited unconditionally, the evidence line would have told the model a
    match played three days ago "is scheduled". We know when it was due to start; we do not know
    here whether it finished or how, so the honest move is to say nothing about it and let the
    settlement line stand alone.

    Returns an empty tuple when we hold neither — the fail-closed case.
    """
    evidence: list[HookEvidence] = []
    if now is None:
        now = datetime.now(timezone.utc)

    upcoming = event_commence_time is not None and _aware(event_commence_time) > _aware(now)
    kickoff = _as_of(event_commence_time) if upcoming else None
    if kickoff and event_home_team and event_away_team:
        evidence.append(
            HookEvidence(
                # "is scheduled for" rather than a verb that has to agree with its subject:
                # this line carries club names ("Arsenal") and individual players
                # ("Alexander Blockx") from the same field, and no single conjugation is
                # right for both.
                fact=f"{event_away_team} vs {event_home_team} is scheduled for {kickoff}.",
                as_of=kickoff,
                source="our fixture schedule",
            )
        )
    elif kickoff:
        evidence.append(
            HookEvidence(
                fact=f"The fixture behind this question is scheduled for {kickoff}.",
                as_of=kickoff,
                source="our fixture schedule",
            )
        )

    settles = _as_of(resolution_date)
    if settles:
        evidence.append(
            HookEvidence(
                fact=(
                    f"The question {market_name!r} is settled no later than {settles}. "
                    "It may be decided earlier."
                ),
                as_of=settles,
                # Provenance for the trace. Deliberately NOT the venue's name: the standing
                # rules forbid naming a venue in the sentence, so its name is not put in
                # front of the model in the first place.
                source=(f"{resolution_source} settlement rules" if resolution_source else "settlement rules"),
                kind=SETTLEMENT_EVIDENCE,
            )
        )

    return tuple(evidence)


def should_generate_hook(evidence: Sequence[HookEvidence]) -> bool:
    """Fail closed unless something a reader would care about actually happens on a date.

    The caller skips the model entirely on False — not "generate and hope", not "generate and
    filter". An unspent call cannot produce an unsupported claim.

    **Why a settlement date alone is not enough, measured rather than assumed.** Presentation
    three asked on any dated evidence and reviewed all 30 lines that came back from the real model
    on the 30 highest-volume production markets. Nothing was unsupported — and 26 of the 30 read
    "The question 'Ren vs KHOMUTSIANSKAYA' is settled no later than September 26, 2026." Three
    things are wrong with putting that on a card, and none of them is fixable by better wording:

    * it is the settlement mechanic described to the reader, which is the grey diagnostic prose
      standing notice 34 removed from the US Open page;
    * the date is routinely the padded latest-possible settlement (#2644) — the men's singles line
      said Sep 28 while the final was Sep 13 — so the one fact it states is misleading;
    * it quotes the market name back, and the card already prints the market name directly above.

    The four lines built on a linked fixture were good ("The Philadelphia Phillies are set to face
    the Atlanta Braves on September 12, 2026"), because a fixture is a thing that happens. So the
    gate is the KIND of evidence, not its presence: a settlement date may support a sentence, but
    it may not be the only thing under it. A card with no hook is a supported state on both
    clients, and notice 34 is explicit that an empty space beats an explained one.
    """
    return any(e.kind != SETTLEMENT_EVIDENCE for e in evidence)


def accept_hook_output(raw: Optional[str]) -> Optional[str]:
    """Normalise the model's reply, honouring ``NO_HOOK`` as a real answer.

    Returns None when the model declined, when the reply is empty, or when it is the sentinel
    wearing punctuation or quotes — all of which mean the same thing: write no hook.
    """
    if raw is None:
        return None
    cleaned = raw.strip().strip('"').strip("'").strip()
    if not cleaned:
        return None
    if cleaned.rstrip(".!").strip().upper() == NO_HOOK_SENTINEL:
        return None
    return cleaned


def build_hook_prompt(
    *,
    market_name: str,
    category: str,
    leaderboard_lines: list[str],
    resolve_str: str = "",
    volume_str: str = "",
    evidence: Sequence[HookEvidence] = (),
) -> str:
    """Compose the hook-generation prompt for one market.

    Pure and deterministic: the same arguments always produce byte-identical output, so a
    generation-input trace can be reproduced after the fact. Nothing here reads a file.

    The leaderboard and volume are CONTEXT — they tell the model which question it is looking at and
    how much attention it carries. They are not evidence and the prompt says so: the standing rules
    forbid printing a probability or naming a venue in the sentence.
    """
    criteria_block = "\n".join(f"- {c}" for c in HOOK_STYLE_CRITERIA)
    example_block = "\n\n".join(
        f"{evidence_line}\n  -> {sentence}" for evidence_line, sentence in HOOK_EXAMPLE_PAIRS
    )
    leaderboard_block = "\n".join(leaderboard_lines)
    if evidence:
        evidence_block = _EVIDENCE_PREAMBLE + "\n" + "\n".join(e.render() for e in evidence)
    else:
        evidence_block = _NO_EVIDENCE_BLOCK

    return (
        "Write ONE plain sentence (max 250 chars) stating what the EVIDENCE below says. "
        "Write it the way a newspaper states a fact, not the way a market describes itself. "
        "This is not a pitch: a reader who wants to know why it matters can read the page. "
        "NEVER include specific percentages or probability numbers — those are shown "
        "separately and go stale. "
        "NEVER reference prediction markets, Polymarket, Kalshi, odds, traders, betting, or "
        "gambling — write as pure news context.\n\n"
        f"What a good hook does:\n{criteria_block}\n\n"
        f"{evidence_block}\n\n"
        "CONTEXT — which question this is and how much attention it carries. It is NOT evidence "
        "and NOT material: do not state it, do not summarise it, do not name anything that appears "
        "only here, and do not characterise the standings or how they have moved. It is printed so "
        "you know which question you are looking at, and for no other reason.\n"
        f"Market: {market_name}\n"
        f"Category: {category}\n"
        f"Leaderboard:\n{leaderboard_block}\n"
        f"{resolve_str}\n"
        f"{volume_str}\n\n"
        f"{_EXAMPLES_PREAMBLE}\n{example_block}\n\n"
        "Your hook:"
    )
