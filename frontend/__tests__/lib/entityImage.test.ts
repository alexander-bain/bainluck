// L2-199 — identity-guarded image resolution for grouped-feed avatars. The gate
// is the framework-free primitive that makes "a late lookup for entity A can
// never land on entity B" deterministic and unit-testable in the repo's node
// test env (no jsdom/RTL) — same convention as TypeaheadRequestGate (L2-198).

import { EntityImageGate } from "@/lib/entityImage";

describe("EntityImageGate", () => {
  it("owns the identity it began with", () => {
    const gate = new EntityImageGate();
    gate.begin("LeBron James");
    expect(gate.owns("LeBron James")).toBe(true);
  });

  it("does not own an identity it never began", () => {
    const gate = new EntityImageGate();
    expect(gate.owns("Stephen Curry")).toBe(false);
  });

  it("drops a late result for a superseded identity (A cannot land on B)", () => {
    const gate = new EntityImageGate();
    // A lookup opens for player A...
    gate.begin("Player A");
    // ...then the row is recycled for player B before A's lookup resolves.
    gate.begin("Player B");
    // A's late .then must be dropped; B's must apply.
    expect(gate.owns("Player A")).toBe(false);
    expect(gate.owns("Player B")).toBe(true);
  });

  it("cancel() drops every in-flight result (unmount)", () => {
    const gate = new EntityImageGate();
    gate.begin("Team A");
    gate.cancel();
    expect(gate.owns("Team A")).toBe(false);
  });

  it("re-beginning the same identity keeps ownership (same entity, same face)", () => {
    const gate = new EntityImageGate();
    gate.begin("Team A");
    gate.begin("Team A");
    expect(gate.owns("Team A")).toBe(true);
  });

  it("models the wrong-face publish contract end to end", () => {
    // Simulate two overlapping lookups whose results arrive out of order,
    // exactly as the useEntityImage effect applies them.
    const gate = new EntityImageGate();
    const applied: string[] = [];
    const apply = (identity: string, image: string) => {
      if (!gate.owns(identity)) return; // the guard inside the .then
      applied.push(image);
    };

    gate.begin("A"); // A's lookup starts
    gate.begin("B"); // identity flips to B before A resolves

    apply("A", "A-face.png"); // A resolves late — must be dropped
    apply("B", "B-face.png"); // B resolves — must be applied

    expect(applied).toEqual(["B-face.png"]);
  });
});
