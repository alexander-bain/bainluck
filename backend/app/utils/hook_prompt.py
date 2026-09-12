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

**What this deliberately does NOT do.** It adds no news source. For most futures markets the
evidence we hold is a date and, where the market is linked to a fixture, that fixture's schedule —
so the honest hook is a short, timed sentence, not a story. Real reporting behind a hook is #870's
ship, and #4066's. This one makes the sentence answerable for.

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


@dataclass(frozen=True)
class HookEvidence:
    """One fact the hook is allowed to state, with the date it holds and who says so.

    `fact` is written as a sentence rather than a field dump so the model has no reason to
    re-describe it; `as_of` and `source` are printed beside it so an unsupported claim is
    visible by comparing the output against the block.
    """

    fact: str
    as_of: str
    source: str

    def render(self) -> str:
        return f"- [{self.as_of} · {self.source}] {self.fact}"


#: The shape a good hook has, stated so it applies to a subject the model has not seen. Rewritten
#: for presentation two: every line is now something the EVIDENCE block can actually support, and
#: the demand for an unevidenced "specific development" is gone.
HOOK_STYLE_CRITERIA: tuple[str, ...] = (
    "State ONLY what an EVIDENCE line supports. If it is not in EVIDENCE, you may not write it — "
    "not as a detail, not as background, not as a hedge.",
    "Name the subject plainly, the way a headline names it.",
    "Anchor the sentence in time using the dated evidence: a day, a date, or a bounded window.",
    "Say what turns on it only where an EVIDENCE line carries the consequence; otherwise stop early.",
    "A short true sentence beats a long suggestive one. Write for someone who has not been "
    "following: no insider shorthand, no unexplained names.",
    f"If the evidence supports nothing worth a reader's time, reply exactly {NO_HOOK_SENTINEL} and "
    "nothing else. That is a correct answer, not a failure.",
)


#: Three examples authored for this file. They demonstrate the criteria over subjects that name no
#: real event, so nothing here can be mistaken for reporting or reused as a fact — the prompt says
#: so where they appear. Each one states only what its own imagined evidence line would carry.
HOOK_EXAMPLES: tuple[str, ...] = (
    "The two finalists meet Thursday in the only debate either has agreed to, "
    "the last time voters will see them side by side before early voting opens.",
    "A judge set a hearing for the first week of next month on whether the deal can close — "
    "the first fixed date on the calendar since the review began in spring.",
    "The defending champion withdrew before the quarter-final with a shoulder injury, "
    "leaving the bottom half of the draw without a former winner for the first time in a decade.",
)


_EXAMPLES_PREAMBLE = (
    "Three examples of the SHAPE, not the material. They are written as illustrations and "
    "describe no real event: copy their structure, never their subjects, wording or facts."
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
            )
        )

    return tuple(evidence)


def should_generate_hook(evidence: Sequence[HookEvidence]) -> bool:
    """Fail closed: with no dated evidence there is nothing a hook could honestly say.

    The caller skips the model entirely on False — not "generate and hope", not "generate and
    filter". An unspent call cannot produce an unsupported claim.
    """
    return bool(evidence)


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
    example_block = "\n".join(f'- "{e}"' for e in HOOK_EXAMPLES)
    leaderboard_block = "\n".join(leaderboard_lines)
    if evidence:
        evidence_block = _EVIDENCE_PREAMBLE + "\n" + "\n".join(e.render() for e in evidence)
    else:
        evidence_block = _NO_EVIDENCE_BLOCK

    return (
        "Write 1-2 sentences (max 250 chars) explaining WHY a reader should care about this "
        "topic RIGHT NOW. Write like a journalist, not a market description. "
        "NEVER include specific percentages or probability numbers — those are shown "
        "separately and go stale. "
        "NEVER reference prediction markets, Polymarket, Kalshi, odds, traders, betting, or "
        "gambling — write as pure news context.\n\n"
        f"What a good hook does:\n{criteria_block}\n\n"
        f"{evidence_block}\n\n"
        "CONTEXT — which question this is and how much attention it carries. NOT evidence: you may "
        "not state any of it, and the rules above still forbid printing a probability.\n"
        f"Market: {market_name}\n"
        f"Category: {category}\n"
        f"Leaderboard:\n{leaderboard_block}\n"
        f"{resolve_str}\n"
        f"{volume_str}\n\n"
        f"{_EXAMPLES_PREAMBLE}\n{example_block}\n\n"
        "Your hook:"
    )
