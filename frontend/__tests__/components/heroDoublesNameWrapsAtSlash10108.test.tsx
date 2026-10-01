/**
 * #10108 — on a doubles match the event hero read "HAR25%": a slash-joined pair
 * ("Harris/Hsieh") had no wrap opportunity, so the side column could not
 * shrink below the whole pair and the centre probability spilled over the
 * crest. The hero names now render through `SlashBreakableName`, which puts a
 * `<wbr>` after each slash.
 *
 * jsdom does no layout, so the overlap itself is proven by the 390px render in
 * the PR; these guards pin the two things that make it go away.
 */
import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "fs";
import { join } from "path";
import SlashBreakableName from "@/components/SlashBreakableName";

describe("#10108 hero doubles names wrap at the slash", () => {
  it("puts a wrap opportunity after every slash and keeps the text identical", () => {
    const html = renderToStaticMarkup(<SlashBreakableName text="Lammons/Withrow" />);
    // The <wbr> follows the slash, so the first line ends "Lammons/".
    expect(html).toBe("Lammons/<wbr/>Withrow");
    expect(html.replace(/<wbr\/>/g, "")).toBe("Lammons/Withrow");
  });

  it("handles a three-part name", () => {
    const html = renderToStaticMarkup(<SlashBreakableName text="A/B/C" />);
    expect(html).toBe("A/<wbr/>B/<wbr/>C");
  });

  it("renders a name with no slash exactly as before (control)", () => {
    expect(renderToStaticMarkup(<SlashBreakableName text="Phillies" />)).toBe("Phillies");
  });

  it("both hero name slots on the event page render through it", () => {
    const page = readFileSync(
      join(__dirname, "..", "..", "app", "events", "[id]", "page.tsx"),
      "utf8",
    );
    expect(page).toContain("<SlashBreakableName text={heroShortNames.home} />");
    expect(page).toContain("<SlashBreakableName text={heroShortNames.away} />");
    // No hero slot prints the bare name any more.
    expect(page).not.toMatch(/>\s*\{heroShortNames\.(home|away)\}\s*<\/TeamNameLink>/);
  });
});
