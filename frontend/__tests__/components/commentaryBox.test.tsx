// Same-day live feature (2026-07-19): The Open live AI commentary box. Honest-
// empty — renders nothing when not live or no text, so a failed generation
// degrades to no box (never a broken/empty box).

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import CommentaryBox from "../../components/event/CommentaryBox";

describe("CommentaryBox (The Open live commentary)", () => {
  test("renders the commentary text when live", () => {
    const html = renderToStaticMarkup(
      <CommentaryBox
        commentary={{ text: "Cameron Young's win probability jumped 4.3 points to 5%." }}
        live
      />,
    );
    expect(html).toContain("Cameron Young");
    expect(html).toContain("Live commentary");
  });

  test("renders nothing when not live (even with text)", () => {
    const html = renderToStaticMarkup(
      <CommentaryBox commentary={{ text: "some text" }} live={false} />,
    );
    expect(html).toBe("");
  });

  test("renders nothing when commentary is null/absent", () => {
    expect(renderToStaticMarkup(<CommentaryBox commentary={null} live />)).toBe("");
    expect(
      renderToStaticMarkup(<CommentaryBox commentary={undefined} live />),
    ).toBe("");
  });

  test("renders nothing when text is empty/whitespace", () => {
    expect(
      renderToStaticMarkup(<CommentaryBox commentary={{ text: "   " }} live />),
    ).toBe("");
  });
});
