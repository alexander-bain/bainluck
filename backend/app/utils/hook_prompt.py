"""The Discover hook prompt, composed from originally authored material only. Pure.

T11-1 (#5461). Until this module, `enrich_market_hooks` sampled three blurbs per market out
of the newsletter corpus under ``app/data/`` — fifty sentences lifted verbatim from the
Polymarket newsletter — and pasted them into the production prompt as "Examples of great
hooks". A fourth, hard-coded fallback triple was written in the same voice. (The corpus
filename is deliberately not written in either module; a guard scans both for it.)

D138 is the rule that forbids it: the newsletters are POSITIVE EXAMPLES OF EDITORIAL
SELECTION, never a target to converge on, and **their prose never enters production
generation, retrieval examples, training sets, cards or analytics logs**. A Discover
reproducible from the newsletters is a failed eval. What we are allowed to learn from them
is the SHAPE of a good description — named subject, specific development, explicit timing,
consequence, understandable question, evidence strength — not their sentences.

So this module carries two things and nothing else:

* :data:`HOOK_STYLE_CRITERIA` — that shape, stated as criteria the model can apply to a
  subject it has never seen. Criteria generalise; sentences are copied.
* :data:`HOOK_EXAMPLES` — three examples written here, for this file, demonstrating the
  criteria. They name no real development and quote no source, and the prompt tells the
  model so in as many words: they are the shape, not the material.

**Why the examples are deliberately unsourced.** A few-shot example carrying a concrete
real-world claim teaches two things at once — the shape, and that inventing a checkable
fact is what a hook does. The second lesson is the one this codebase spends most of its
guards undoing. These three show structure over subjects that cannot be mistaken for
reporting, and the prompt's own rules (no probabilities, no venue, no narration) still bind
the output.

The other half of T11-1 is that this is now **deterministic**. The old prompt drew a random
sample per market, so two markets scored the same way got different instructions and no
trace could reproduce either. Same inputs in, same prompt out —
``test_hook_prompt_has_no_newsletter_prose_5461.py`` pins it, along with the absence of
every shingle of the corpus.
"""

from __future__ import annotations

__all__ = [
    "HOOK_STYLE_CRITERIA",
    "HOOK_EXAMPLES",
    "build_hook_prompt",
]


#: The shape a good hook has, stated so it applies to a subject the model has not seen.
#: Each line is a criterion, not an instance — this is the half of the newsletters we are
#: permitted to learn from (D138).
HOOK_STYLE_CRITERIA: tuple[str, ...] = (
    "Name the subject plainly, the way a headline names it.",
    "State ONE specific development — what happened, or what is about to — never a summary of the topic.",
    "Say WHEN: a day, a date, or a bounded window. A hook with no time in it is a description, not news.",
    "Say what turns on it — the consequence a reader could restate in their own words.",
    "Prefer what is known to what is expected. If the evidence is thin, say less; a short true sentence beats a long suggestive one.",
    "Write for someone who has not been following. No insider shorthand, no unexplained names.",
)


#: Three examples authored for this file. They demonstrate the criteria above over subjects
#: that name no real event, so nothing here can be mistaken for reporting or reused as a
#: fact. The prompt states that explicitly where they appear.
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


def build_hook_prompt(
    *,
    market_name: str,
    category: str,
    leaderboard_lines: list[str],
    resolve_str: str = "",
    volume_str: str = "",
) -> str:
    """Compose the hook-generation prompt for one market.

    Pure and deterministic: the same arguments always produce byte-identical output, so a
    generation-input trace can be reproduced after the fact. Nothing here reads a file.
    """
    criteria_block = "\n".join(f"- {c}" for c in HOOK_STYLE_CRITERIA)
    example_block = "\n".join(f'- "{e}"' for e in HOOK_EXAMPLES)
    leaderboard_block = "\n".join(leaderboard_lines)

    return (
        "Write 1-2 sentences (max 250 chars) explaining WHY a reader should care about this "
        "topic RIGHT NOW. Write like a journalist, not a market description. Focus on what "
        "happened, what changed, or why this matters. "
        "NEVER include specific percentages or probability numbers — those are shown "
        "separately and go stale. "
        "NEVER reference prediction markets, Polymarket, Kalshi, odds, traders, betting, or "
        "gambling — write as pure news context.\n\n"
        f"What a good hook does:\n{criteria_block}\n\n"
        f"Market: {market_name}\n"
        f"Category: {category}\n"
        f"Leaderboard:\n{leaderboard_block}\n"
        f"{resolve_str}\n"
        f"{volume_str}\n\n"
        f"{_EXAMPLES_PREAMBLE}\n{example_block}\n\n"
        "Your hook:"
    )
