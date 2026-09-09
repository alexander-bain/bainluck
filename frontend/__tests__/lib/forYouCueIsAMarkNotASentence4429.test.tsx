/**
 * #4429 — A "FOR YOU" CUE IS A MARK, NOT A SENTENCE.
 *
 * Alex, reading Discover on bainluck.com the morning of 2026-09-09 (Fable-5's
 * 10:05am PT note, item 3): the "A CATEGORY YOU FOLLOW" pill is *"far too big —
 * a small mark, not a badge"*.
 *
 * ═══ WHAT WAS ACTUALLY OVERSIZED ═══
 *
 * Not the type. `ForYouChip` was already `text-[10px] px-1.5 py-0.5` — 10px
 * glyphs and 6px/2px padding is a mark by any measure. What made it read as a
 * badge is that the LABEL was a 21-character sentence, and set `uppercase` with
 * `tracking-[0.04em]` it ran as a bar across the card. Shrinking the type
 * further would have produced an unreadable long line instead of a readable one.
 *
 * ═══ WHY THE WHOLE VOCABULARY AND NOT THE ONE LABEL ═══
 *
 * `A category you follow` is 21 characters and is NOT the longest cue:
 * `A player on one of your teams` is 29 and `A rival of one of your teams` is
 * 28. Fixing only the one Alex happened to see would have left the same bar on
 * the next card, so the guard measures the SET. That is also what the issue
 * asked for in its closing line.
 *
 * ═══ 🔴 THE THING THIS GUARD EXISTS TO STOP ═══
 *
 * The obvious fix — shorten `label` — would have shortened the TOOLTIP too,
 * because the title is built from the label
 * (`In your feed because: ${label.toLowerCase()}`). "In your feed because:
 * following" is a worse answer than the one it replaced, and the standing feed
 * rule is that deterministic explanations are first-class. So a cue carries two
 * forms, and the pair is asserted here in both directions: the chip must print
 * the SHORT one and the title must still carry the WHOLE one. A future
 * "simplification" that collapses them goes red.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { FOR_YOU_VOCABULARY, forYouCue } from "@/lib/discover/forYouCue";
import { ForYouChip } from "@/components/discover/shared";

/** A card with a real net uprank for the given reason tokens. */
const boosted = (reasons: string[]) => ({
  personalized: true,
  multiplier: 1.3,
  personalization_reasons: reasons,
});

/** The longest cue that still reads as a mark rather than a phrase. */
const MAX_MARK_CHARS = 12;
const MAX_MARK_WORDS = 2;

describe("#4429 — every cue in the vocabulary is a mark", () => {
  it("CONTROL: the vocabulary is non-empty and every entry has both forms", () => {
    // Without this, every `it.each` below would iterate nothing and the file
    // would pass while asserting about no cue at all.
    expect(FOR_YOU_VOCABULARY.length).toBeGreaterThanOrEqual(13);
    for (const entry of FOR_YOU_VOCABULARY) {
      expect(entry.mark.length).toBeGreaterThan(0);
      expect(entry.label.length).toBeGreaterThan(0);
    }
  });

  it.each(FOR_YOU_VOCABULARY.map((e) => [e.id, e] as const))(
    "%s is short enough to read as a mark",
    (_id, entry) => {
      expect(entry.mark.length).toBeLessThanOrEqual(MAX_MARK_CHARS);
      expect(entry.mark.split(/\s+/).length).toBeLessThanOrEqual(MAX_MARK_WORDS);
    }
  );

  it.each(FOR_YOU_VOCABULARY.map((e) => [e.id, e] as const))(
    "%s is not a sentence — no leading article, no verb",
    (_id, entry) => {
      // The article is what makes a mark a phrase, and it is never the
      // informative word: "A rival of one of your teams" says "Rival".
      expect(entry.mark).not.toMatch(/^(a|an|the|one|your feed)\b/i);
      expect(entry.mark).not.toMatch(/\b(you|your)\s+(follow|pinned|have|opened|are)\b/i);
    }
  );

  it("🔴 the one Alex named reads as a mark", () => {
    const cue = forYouCue(boosted(["discover_interest:0.22"]));
    expect(cue?.mark).toBe("Following");
    // 21 characters became 9. The claim did not change; its length did.
    expect(cue?.label).toBe("A category you follow");
  });

  it("the longest cue in the set is now shorter than the shortest old sentence", () => {
    // "You pinned this" (15) was the SHORTEST label before this ship. Every mark
    // must beat it, or the bar Alex saw is still reachable on some other card.
    const longest = Math.max(...FOR_YOU_VOCABULARY.map((e) => e.mark.length));
    expect(longest).toBeLessThan("You pinned this".length);
  });
});

describe("#4429 — the sentence did not go away, it moved into the hover", () => {
  const cue = forYouCue(boosted(["roster_player:0.31"]));

  it("CONTROL: this specimen is the vocabulary's longest sentence", () => {
    // Asserted before the claim below, so the arm is exercised on the worst case
    // rather than on whichever cue happened to be first.
    const longest = FOR_YOU_VOCABULARY.reduce((a, b) => (b.label.length > a.label.length ? b : a));
    expect(cue?.label).toBe(longest.label);
    expect(cue?.label).toBe("A player on one of your teams");
  });

  it("🔴 the chip PRINTS the mark", () => {
    const html = renderToStaticMarkup(<ForYouChip cue={cue} />);
    expect(html.replace(/<[^>]*>/g, "").trim()).toBe("Your player");
  });

  it("🔴 and the title still carries the WHOLE sentence", () => {
    const html = renderToStaticMarkup(<ForYouChip cue={cue} />);
    expect(html).toContain("In your feed because: a player on one of your teams");
  });

  it("the two are different strings — a collapsed pair is not a fix", () => {
    // The mutant this catches: `mark: label`. Everything else in this file
    // except the length arms would still pass.
    expect(cue!.mark).not.toBe(cue!.label);
  });
});
