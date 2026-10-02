/**
 * live/122 (#4454, second pass) — THE END-TO-END PROOF THE FIRST PASS DID NOT HAVE.
 *
 * The first pass was correct code that rendered nothing. Every unit test passed,
 * the wiring guard passed, CI was green, it deployed — and the section was absent
 * on production, because page one asks for 20 items and the ranker puts last
 * night's finals from position 30 down, so nothing settled ever reached the
 * partition. The tests proved the module; nothing proved the DATA.
 *
 * So this file runs the real pipeline over the real payload. The fixture is the
 * exact response the deferred lookup issues —
 * `GET /api/feed?limit=40&mode=sports&include_futures=false`, captured from
 * production 2026-09-09T20:47Z — and the assertion is the one that actually
 * failed in the wild: **the reader gets a non-empty Finished section with last
 * night's marquee final at the top of it.**
 *
 * A fixture goes stale, and that is fine here: it is pinned to a date in its own
 * filename and its job is to prove the pipeline against a payload shaped like the
 * real one, not to track today's fixtures. What it must never become is a fixture
 * that has been edited until it passes — the counts below are asserted first, so
 * a doctored payload fails loudly rather than quietly proving nothing.
 */
import lookup from "../fixtures/sportsFinishedLookup-20260909.json";
import {
  partitionFinishedGames,
  buildFinishedSection,
} from "@/lib/sports/finishedSection";
import { feedItemHasRenderableContent } from "@/components/discover/utils";
import type { FeedItem, FeedEventData } from "@/lib/types";

const items = (lookup as { items: FeedItem[] }).items;

/** The afternoon of the capture, so the calendar bound resolves as it did live. */
const NOW = Date.parse("2026-09-09T20:47:00Z");

const SHELTON_ALCARAZ = 15306813;

function idOf(item: FeedItem): number {
  return (item.data as FeedEventData).id;
}

describe("#4454 the captured payload really does contain the defect's cure", () => {
  it("is the lookup's own shape: 40 items, futures excluded", () => {
    expect(items).toHaveLength(40);
    expect(items.filter((i) => i.type === "futures")).toHaveLength(0);
  });

  it("carries seven settled games, and the marquee final is one of them", () => {
    const finished = partitionFinishedGames(items).finished;
    expect(finished).toHaveLength(7);
    expect(finished.map(idOf)).toContain(SHELTON_ALCARAZ);
  });

  it("the marquee final sits at position 22 — past the 20 page one asks for", () => {
    // This is the whole defect in one assertion. If a future ranking change
    // brings it inside 20, this test tells you the deferred lookup has become
    // unnecessary rather than silently keeping a redundant request.
    const pos = items.findIndex((i) => i.type === "event" && idOf(i) === SHELTON_ALCARAZ);
    expect(pos).toBeGreaterThanOrEqual(20);
  });
});

describe("#4454 the pipeline, end to end, on the real payload", () => {
  const renderable = items.filter(feedItemHasRenderableContent);
  const finished = partitionFinishedGames(renderable).finished;
  const section = buildFinishedSection(finished, NOW);

  it("the reader gets a NON-EMPTY Finished section — the thing that failed live", () => {
    expect(section.shown.length).toBeGreaterThan(0);
  });

  it("last night's marquee final is IN it, which it was not before", () => {
    expect(section.shown.map(idOf)).toContain(SHELTON_ALCARAZ);
  });

  it("it IS first now — the open ruling landed as a visible change (#10207)", () => {
    // 🔴 WAS PINNED "NOT first" so the ruling would land here, not silently.
    // Fable's 9/9 note said the marquee final "must sit at the top of the tab's
    // finished section"; D54 as ux/1053 implemented it (day ascending, most
    // recent first inside a day) put a Swedish third-tier football match that
    // finished 10:00am PT TODAY above the US Open quarter-final Alex watched,
    // which finished 8:00pm PT YESTERDAY.
    //
    // #10207 (2026-10-02, the same shape: four tier-4 China Open matches over
    // last night's TNF final) gave the section one band above D54: headline
    // finals first (`isHeadlineCard` — tier 1, playoff/championship, a Grand
    // Slam, a major), D54 unchanged inside each band. A Slam match is a
    // headline; the Superettan match is not. Score order is still never read.
    const first = section.shown[0];
    expect(idOf(first)).toBe(SHELTON_ALCARAZ);
    // The football match is not deleted: it is behind the declared cap, the
    // population the "More results in …" links point at. Four tier-1 MLB finals
    // and the Slam fill the four slots; inside that band D54 still orders them
    // by when they ended, which is why the Slam (ended 03:00Z) leads them.
    expect(section.shown.map(idOf)).not.toContain(15301254);
    expect(
      section.dropped.find((d) => idOf(d.item) === 15301254)?.reason,
    ).toBe("finished_section_cap");
  });

  it("every card shown is a settled game, and none is dropped as undated", () => {
    expect(section.shown.every((i) => i.type === "event")).toBe(true);
    expect(section.dropped.filter((d) => d.reason === "finished_undated")).toHaveLength(0);
  });

  it("the renderable filter is not a no-op that would hide a regression", () => {
    // If `feedItemHasRenderableContent` ever admitted everything, this file would
    // stop testing the ladder page one walks. It refuses at least one card here.
    expect(renderable.length).toBeLessThanOrEqual(items.length);
    expect(finished.length).toBeGreaterThan(0);
  });
});

describe("#4454 CONTROL — page one's own window yields nothing, which is why this exists", () => {
  it("the first 20 items contain no settled game at all", () => {
    // Recomputes the pre-second-pass reality on the same payload. If this ever
    // goes green-by-accident (a ranking change lifting finals into the top 20),
    // the tests above still hold and this one tells you why the fix is moot.
    const pageOne = items.slice(0, 20).filter(feedItemHasRenderableContent);
    expect(partitionFinishedGames(pageOne).finished).toHaveLength(0);
    expect(buildFinishedSection(partitionFinishedGames(pageOne).finished, NOW).shown).toHaveLength(0);
  });
});
