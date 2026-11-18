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

  test("parses automatically discovered Oscars Nominations and The Odyssey child hubs with clean Back restoration", () => {
    const oscarsParentPayload = {
      state: "published",
      slug: "oscars-2027",
      revision: 120,
      reason: null,
      edition: { kind: "theme_edition", subject: "oscars", edition: 2027 },
      container: {
        id: 9901,
        slug: "oscars-2027",
        name: "Oscars 2027",
        kind: "theme",
        category: "entertainment",
        status: "open",
      },
      children: [
        {
          id: 101,
          slug: "oscars-2027-nominations",
          name: "Oscars 2027 · Nominations (73 markets)",
          kind: "roundup",
          category: "entertainment",
          status: "open",
          publication_state: "published",
          member_count: 73,
          cross_listed_in_parent: true,
          destination: {
            kind: "container",
            slug: "oscars-2027-nominations",
            web: "/collections/oscars-2027-nominations",
            api: "/api/containers/oscars-2027-nominations",
          },
        },
        {
          id: 102,
          slug: "oscars-2027-subject-the-odyssey",
          name: "The Odyssey (23 markets)",
          kind: "roundup",
          category: "entertainment",
          status: "open",
          publication_state: "published",
          member_count: 23,
          cross_listed_in_parent: true,
          destination: {
            kind: "container",
            slug: "oscars-2027-subject-the-odyssey",
            web: "/collections/oscars-2027-subject-the-odyssey",
            api: "/api/containers/oscars-2027-subject-the-odyssey",
          },
        },
      ],
      sections: [
        {
          class: "title",
          count: 1,
          members: [
            {
              type: "market",
              id: 6173044,
              destination: {
                kind: "market",
                id: 6173044,
                web: "/futures/6173044",
                api: "/api/futures/6173044",
              },
              card: {
                id: 6173044,
                name: "Oscar Winner: Best Picture",
                status: "open",
                top_outcomes: [{ name: "The Odyssey", probability: 0.54 }],
              },
            },
          ],
        },
      ],
      member_count: 1,
      withheld: [],
      withheld_count: 0,
      counts: { shown_count: 419, inventory_complete: true },
      page: { limit: 100, next_cursor: null },
    };

    const odysseyChildPayload = {
      state: "published",
      slug: "oscars-2027-subject-the-odyssey",
      revision: 88,
      reason: null,
      edition: null,
      container: {
        id: 102,
        slug: "oscars-2027-subject-the-odyssey",
        name: "The Odyssey · Oscars 2027",
        kind: "roundup",
        category: "entertainment",
        status: "open",
        parent_container_id: 9901,
      },
      parent: {
        slug: "oscars-2027",
        name: "Oscars 2027",
        destination: {
          kind: "container",
          slug: "oscars-2027",
          web: "/collections/oscars-2027",
          api: "/api/containers/oscars-2027",
        },
      },
      subtitle: "Cross-listed from Oscars 2027 · 2 open markets",
      children: [],
      sections: [
        {
          class: "title",
          title: "Award Winner Markets",
          layout: "field",
          count: 1,
          members: [
            {
              type: "market",
              id: 6173044,
              destination: {
                kind: "market",
                id: 6173044,
                web: "/futures/6173044",
                api: "/api/futures/6173044",
              },
              card: {
                id: 6173044,
                name: "Oscar Winner: Best Picture",
                status: "open",
                top_outcomes: [{ name: "The Odyssey", probability: 0.54 }],
              },
            },
          ],
        },
        {
          class: "advancement",
          title: "Nomination Markets",
          layout: "field",
          count: 1,
          members: [
            {
              type: "market",
              id: 5165726,
              destination: {
                kind: "market",
                id: 5165726,
                web: "/futures/5165726",
                api: "/api/futures/5165726",
              },
              card: {
                id: 5165726,
                name: "Oscar Nominees: Best Picture",
                status: "open",
                top_outcomes: [{ name: "The Odyssey", probability: 0.98 }],
              },
            },
          ],
        },
      ],
      member_count: 2,
      withheld: [],
      withheld_count: 0,
      assembled: true,
    };

    const oscarsHub = parseCollection(oscarsParentPayload, "oscars-2027");
    expect(oscarsHub.note).toBeNull();
    expect(oscarsHub.children.map((c) => c.href)).toEqual([
      "/collections/oscars-2027-nominations",
      "/collections/oscars-2027-subject-the-odyssey",
    ]);

    const odysseyHub = parseCollection(odysseyChildPayload, "oscars-2027-subject-the-odyssey");
    expect(odysseyHub.note).toBeNull();
    expect(odysseyHub.title).toBe("The Odyssey · Oscars 2027");
    expect(odysseyHub.subtitle).toBe("Cross-listed from Oscars 2027 · 2 open markets");
    expect(odysseyHub.parent).toEqual({
      slug: "oscars-2027",
      name: "Oscars 2027",
      href: "/collections/oscars-2027",
    });
    expect(odysseyHub.sections.map((s) => s.title)).toEqual([
      "Award Winner Markets",
      "Nomination Markets",
    ]);

    const restored = reconcileCollectionContext(
      {
        slug: "oscars-2027",
        memberKey: "container:oscars-2027-subject-the-odyssey",
        offset: 312,
        expanded: [],
      },
      oscarsHub,
    );
    expect(restored.memberKey).toBe("container:oscars-2027-subject-the-odyssey");
    expect(restored.offset).toBe(312);
  });
});
