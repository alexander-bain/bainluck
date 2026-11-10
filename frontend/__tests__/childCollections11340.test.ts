import {
  collectionMemberDomId,
  parseCollection,
  reconcileCollectionContext,
  type CollectionReadingContext,
} from "@/lib/collections";

describe("child collections from an event hub (#11340)", () => {
  const parentPayload = {
    state: "published",
    slug: "midterms-2026",
    revision: 101,
    edition: { kind: "midterms", league: "politics", season: 2026 },
    container: {
      id: 1,
      slug: "midterms-2026",
      name: "Midterms 2026",
      kind: "midterms",
      category: "politics",
      status: "open",
    },
    sections: [
      {
        class: "senate_races",
        title: "Competitive Senate races",
        layout: "table",
        count: 1,
        members: [
          {
            type: "market",
            id: 5001,
            destination: {
              kind: "market",
              id: 5001,
              web: "/futures/5001",
              api: "/api/futures/5001",
            },
            card: {
              id: 5001,
              name: "Georgia Senate Election Winner",
              status: "open",
              top_outcomes: [
                { name: "Democrat", probability: 0.51 },
                { name: "Republican", probability: 0.49 },
              ],
            },
          },
        ],
      },
    ],
    member_count: 1,
    withheld: [],
    withheld_count: 0,
    children: [
      {
        id: 9001,
        slug: "roundup-closest-races",
        name: "Closest races · 2026",
        kind: "roundup",
        category: "politics",
        status: "open",
        publication_state: "published",
        destination: {
          kind: "container",
          slug: "roundup-closest-races",
          web: "/collections/roundup-closest-races",
          api: "/api/containers/roundup-closest-races",
        },
      },
    ],
  };

  const childPayload = {
    state: "published",
    slug: "roundup-closest-races",
    revision: 202,
    edition: null,
    container: {
      id: 9001,
      slug: "roundup-closest-races",
      name: "Closest races · 2026",
      kind: "roundup",
      category: "politics",
      status: "open",
      parent_container_id: 1,
    },
    parent: {
      slug: "midterms-2026",
      name: "Midterms 2026",
      destination: {
        kind: "container",
        slug: "midterms-2026",
        web: "/collections/midterms-2026",
        api: "/api/containers/midterms-2026",
      },
    },
    sections: [
      {
        class: "title",
        title: "Closest races",
        layout: "field",
        count: 1,
        members: [
          {
            type: "market",
            id: 5001,
            destination: {
              kind: "market",
              id: 5001,
              web: "/futures/5001",
              api: "/api/futures/5001",
            },
            card: {
              id: 5001,
              name: "Georgia Senate Election Winner",
              status: "open",
              top_outcomes: [
                { name: "Democrat", probability: 0.51 },
                { name: "Republican", probability: 0.49 },
              ],
            },
          },
        ],
      },
    ],
    member_count: 1,
    withheld: [],
    withheld_count: 0,
    children: [],
  };

  test("parses published child collection on parent hub and parent link on child collection", () => {
    const parentHub = parseCollection(parentPayload, "midterms-2026");
    expect(parentHub.children).toEqual([
      {
        key: "container:roundup-closest-races",
        name: "Closest races · 2026",
        href: "/collections/roundup-closest-races",
      },
    ]);

    const childHub = parseCollection(childPayload, "roundup-closest-races");
    expect(childHub.parent).toEqual({
      slug: "midterms-2026",
      name: "Midterms 2026",
      href: "/collections/midterms-2026",
    });
  });

  test("restores two-step Back navigation (member -> child collection -> parent hub)", () => {
    const parentHub = parseCollection(parentPayload, "midterms-2026");
    const childHub = parseCollection(childPayload, "roundup-closest-races");

    // Step 1: Reader on parent hub clicks child collection link `container:roundup-closest-races`
    const savedParentContext: CollectionReadingContext = {
      slug: "midterms-2026",
      memberKey: "container:roundup-closest-races",
      offset: 184,
      expanded: [],
    };
    expect(collectionMemberDomId("container:roundup-closest-races")).toBe(
      "collection-member-container:roundup-closest-races",
    );

    // Step 2: Reader on child collection clicks member `market:5001`
    const savedChildContext: CollectionReadingContext = {
      slug: "roundup-closest-races",
      memberKey: "market:5001",
      offset: 240,
      expanded: [],
    };

    // Back 1: Member detail -> Child collection restores `market:5001` at offset 240
    const restoredChild = reconcileCollectionContext(savedChildContext, childHub);
    expect(restoredChild).toEqual({
      slug: "roundup-closest-races",
      memberKey: "market:5001",
      offset: 240,
      expanded: [],
    });

    // Back 2: Child collection -> Parent hub restores `container:roundup-closest-races` at offset 184
    const restoredParent = reconcileCollectionContext(savedParentContext, parentHub);
    expect(restoredParent).toEqual({
      slug: "midterms-2026",
      memberKey: "container:roundup-closest-races",
      offset: 184,
      expanded: [],
    });
  });
});
