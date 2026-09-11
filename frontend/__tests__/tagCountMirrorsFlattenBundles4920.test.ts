/**
 * #4920 / CERT-2589 — the Browse tile count and the category page must agree.
 *
 * The tile's number is produced on the BACKEND (`split_rendered_items` in
 * `app/utils/tag_counts_cache.py`, published by the `tag_counts_warm` beat).
 * The page's number is produced HERE, by `flattenFeedBundles`. Two counts of
 * one population on opposite sides of the wire is exactly how they drift — and
 * they did: the backend folded a bundle to one card and published 9 markets for
 * a tagged production Tennis payload while this page rendered and labelled 11.
 *
 * This file pins THIS side on that payload. The backend mirror is pinned on the
 * identical payload by
 * `test_tag_count_unfolds_bundle_members_like_category_page`. Neither can move
 * without its own red, which is the point: the mirror is not shared code, so
 * the guard has to be the thing that holds them together.
 */

import { flattenFeedBundles, countCards } from "@/lib/feedSections";
import type { FeedItem } from "@/lib/types";

/** The production-shaped Tennis read: 8 futures + one 3-member bundle. */
function tennisPayload(): FeedItem[] {
  const items: FeedItem[] = [];
  for (let i = 0; i < 8; i++) {
    items.push({ type: "futures", data: { id: i } } as unknown as FeedItem);
  }
  items.push({
    type: "bundle",
    data: {
      items: [
        { type: "futures", data: { id: 100 } },
        { type: "futures", data: { id: 101 } },
        { type: "futures", data: { id: 102 } },
      ],
    },
  } as unknown as FeedItem);
  return items;
}

describe("the page's market count, which the Browse tile must match", () => {
  it("unfolds a bundle into its members: 9 feed slots render 11 cards", () => {
    const items = tennisPayload();
    expect(items).toHaveLength(9);

    const flattened = flattenFeedBundles(items);
    const markets = flattened.filter((i) => i.type === "futures").length;

    // 11, not 9: this is the number the backend tile has to publish.
    expect(markets).toBe(11);
    expect(countCards(items)).toBe(11);
  });

  it("counts events and markets off the SAME flattened list", () => {
    const items = [
      {
        type: "bundle",
        data: {
          items: [{ type: "event" }, { type: "futures" }],
        },
      },
    ] as unknown as FeedItem[];

    const flattened = flattenFeedBundles(items);
    expect(flattened.filter((i) => i.type === "event")).toHaveLength(1);
    expect(flattened.filter((i) => i.type === "futures")).toHaveLength(1);
  });

  it("drops a bundle past the depth cap rather than counting the wrapper", () => {
    // One level deeper than the cap, so the innermost bundle is dropped
    // entirely. If this ever became 1, the tile would over-promise by exactly
    // the cards the reader never gets.
    let nested: unknown = {
      type: "bundle",
      data: { items: [{ type: "futures" }] },
    };
    for (let d = 0; d < 3; d++) {
      nested = { type: "bundle", data: { items: [nested] } };
    }
    expect(countCards([nested] as FeedItem[])).toBe(0);
  });

  it.each([
    ["no items key", { type: "bundle", data: {} }],
    ["null items", { type: "bundle", data: { items: null } }],
    ["items is not a list", { type: "bundle", data: "nope" }],
  ])("a malformed bundle (%s) renders nothing", (_why, bundle) => {
    const items = [{ type: "futures" }, bundle] as unknown as FeedItem[];
    expect(countCards(items)).toBe(1);
  });

  // Current behaviour, pinned rather than endorsed. `(item.data as
  // FeedBundleData).items` casts a lie: when `data` is absent or null the cast
  // silences the compiler and the read throws at runtime, so the whole header
  // computation dies rather than counting the other cards.
  //
  // NOT reachable from our own backend today — all four emitters in
  // `discover_bundles.py` set `data` — so this is latent fragility, filed
  // separately and deliberately NOT fixed inside #4920's repair. The backend
  // mirror is more forgiving on purpose: a warmer that raised here would leave
  // the category unmeasured, which is its correct fallback anyway.
  it.each([
    ["absent", { type: "bundle" }],
    ["null", { type: "bundle", data: null }],
  ])("throws when a bundle's data is %s (pinned, see the filed issue)", (_why, bundle) => {
    expect(() => countCards([bundle] as unknown as FeedItem[])).toThrow(
      TypeError,
    );
  });
});
