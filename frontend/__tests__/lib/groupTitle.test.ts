// L2-243 Item 1 — the client-synthesized Discover group DISPLAY title. A real
// colon subject is kept; a question fragment is replaced by the category so the
// category pill never shows a truncated question ("Will the U.S.").

import { deriveGroupDisplayTitle } from "@/lib/discover/groupTitle";

describe("deriveGroupDisplayTitle", () => {
  it("keeps a real colon-derived shared subject verbatim", () => {
    expect(
      deriveGroupDisplayTitle("Valero Texas Open: Winner", "golf")
    ).toBe("Valero Texas Open");
  });

  it("keeps a product-spec colon subject verbatim", () => {
    expect(
      deriveGroupDisplayTitle("DDR5 16GB (2GX8): price above $80", "tech")
    ).toBe("DDR5 16GB (2GX8)");
  });

  it("replaces a question fragment with the category", () => {
    // Without this, first-3-words → "Will the U.S." in the category pill.
    expect(
      deriveGroupDisplayTitle("Will the U.S. confirm that aliens exist?", "culture")
    ).toBe("culture");
  });

  it("falls back to a neutral label when there is no colon and no category", () => {
    expect(
      deriveGroupDisplayTitle("Will the Iranian regime fall before 2027?", null)
    ).toBe("Related markets");
  });

  it("treats a colon past 30 chars as no shared subject → category", () => {
    const longName =
      "Some very long market question with no early colon: yes";
    expect(deriveGroupDisplayTitle(longName, "geopolitics")).toBe("geopolitics");
  });

  it("treats a leading colon as no subject → category", () => {
    expect(deriveGroupDisplayTitle(":weird", "economics")).toBe("economics");
  });

  it("empty name with a category → category", () => {
    expect(deriveGroupDisplayTitle("", "weather")).toBe("weather");
  });

  it("empty name and no category → neutral label", () => {
    expect(deriveGroupDisplayTitle("", undefined)).toBe("Related markets");
  });
});
