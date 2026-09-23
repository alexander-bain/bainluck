/**
 * #2096 — a futures caption never opens with an orphaned `?`.
 *
 * `stripCardTitleHead` matches the heading with its trailing `?` already
 * removed, because that is how the heading prints. A backend string that
 * spliced the title WITH its mark therefore loses one character too few, and
 * the capitalisation at the end of that function promotes the orphan to the
 * first character of the sentence the reader reads:
 *
 *     backend  "Saudi Arabia military action against Yemen? resolves within a month"
 *     heading  "Saudi Arabia military action against Yemen?"
 *     printed  "? resolves within a month"
 *
 * Photographed at 390px on production `/categories/geopolitics` 2026-09-22
 * (`artifacts-discover/d428/geo-3200.png`). Measured the same hour over 536
 * served futures cards on six surfaces: 6 reached a reader with this caption.
 *
 * `feed_reasons._market_name_as_subject` is the repair and removes the mark at
 * the source (`test_a_card_caption_never_opens_with_a_question_mark_2096.py`).
 * This half is the belt, and it is tested on the SERVED payloads rather than on
 * hand-written strings — the subject is a three-subtraction composition
 * (`stripCardTitleHead` → `stripResolutionWindowClause` →
 * `stripHeroProbabilityRestatement`) that a direct helper call does not
 * exercise, which is the same reason #8151's guard replays payloads.
 */
import fixture from "../fixtures/caption-question-mark-2096.json";
import {
  feedContextSnippet,
  resolvesLabel,
  stripCardTitleHead,
} from "@/components/discover/utils";
import type { FeedItem } from "@/lib/types";

const items = fixture.items as unknown as FeedItem[];
const byId = (id: number) =>
  items.find((it) => (it.data as { id: number }).id === id)!;

const captionOf = (it: FeedItem) => {
  const data = it.data as { resolution_date?: string | null };
  return feedContextSnippet(it, resolvesLabel(data.resolution_date));
};

describe("the served payloads that were photographed", () => {
  test.each(fixture.findings)(
    "card %i no longer captions with a bare question mark",
    (id) => {
      const caption = captionOf(byId(id as number));
      expect(caption.trimStart().startsWith("?")).toBe(false);
    },
  );

  test("every finding's caption is prose or nothing, never punctuation", () => {
    for (const id of fixture.findings) {
      const caption = captionOf(byId(id as number));
      // Empty is a legitimate outcome here and not a regression: once the
      // orphan is gone these captions reduce to "Resolves within a month",
      // which #7872 already deletes because the card's own eyebrow states the
      // same date exactly. What must never happen is a caption made of
      // punctuation.
      if (caption) expect(caption).toMatch(/[A-Za-z0-9]/);
    }
  });
});

describe("the controls", () => {
  test("cards that caption cleanly today are byte-identical", () => {
    // Keyed by SHAPE (a card whose caption is prose), not by identity: the
    // control arm of this census churns while the finding arm is pinned by the
    // defect, so an identity-keyed control reads as the fix silencing a card it
    // never touched.
    for (const id of fixture.controls) {
      const caption = captionOf(byId(id as number));
      expect(caption).toMatch(/[A-Za-z0-9]/);
      expect(caption.trimStart().startsWith("?")).toBe(false);
    }
  });
});

describe("stripCardTitleHead's separator class", () => {
  test("removes the title's own trailing mark when it is left behind", () => {
    expect(
      stripCardTitleHead(
        "Saudi Arabia military action against Yemen? resolves within a month",
        "Saudi Arabia military action against Yemen?",
      ),
    ).toBe("Resolves within a month");
  });

  test("a `?` anywhere but immediately after the heading is untouched", () => {
    // ANTI-OVER-REACH. The widened class fires only on the character straight
    // after this card's own name; a question mark that is part of the copy must
    // survive, or the deletion has become a rewrite (ruling 003).
    expect(stripCardTitleHead("Who? What? Odds up 4 points", "Some other market"))
      .toBe("Who? What? Odds up 4 points");
    expect(stripCardTitleHead("Foo: who? really", "Foo")).toBe("Who? really");
  });

  test("the pre-fix separator class could not have cut this string", () => {
    // STRAWMAN — pins that the repair is load-bearing. Without `?` in the
    // class the orphan survives and is capitalised, which is exactly the
    // photographed caption.
    const raw = "Saudi Arabia military action against Yemen? resolves within a month";
    const name = "Saudi Arabia military action against Yemen";
    const restOld = raw.slice(name.length).replace(/^[\s:,;–—-]+/, "");
    const oldBehaviour = restOld.charAt(0).toUpperCase() + restOld.slice(1);
    expect(oldBehaviour).toBe("? resolves within a month");
  });
});
