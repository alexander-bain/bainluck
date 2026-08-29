/**
 * #2239 — the render-level half. A pure decision function that the page never
 * calls is a guard that stays green while the user keeps reading the lie, so the
 * words themselves are asserted here, out of the real component's real markup.
 *
 * `testEnvironment: 'node'`, no jsdom — `renderToStaticMarkup` is the rig the
 * capture tests already use (`__tests__/capture/propRailCapture.test.tsx`).
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

import SearchDegradedState from "@/components/SearchDegradedState";

const html = (node: React.ReactElement) => renderToStaticMarkup(node);

describe("SearchDegradedState", () => {
  it("never tells the person the thing does not exist", () => {
    // The exact copy the zero-state prints, and the exact reason #2239's user
    // retyped `patriots` four times: the page asserted absence.
    const markup = html(<SearchDegradedState query="patriots" onRetry={() => {}} />);
    expect(markup).not.toMatch(/No results for/i);
    expect(markup).not.toMatch(/couldn.t find any/i);
  });

  it("says what actually happened and offers the retry", () => {
    const markup = html(<SearchDegradedState query="patriots" onRetry={() => {}} />);
    // Apostrophes come back HTML-escaped (`didn&#x27;t`), so the assertions
    // straddle them rather than matching a literal that only holds in one
    // escaping mode.
    expect(markup).toMatch(/finish searching/i);
    expect(markup).toMatch(/ran out of time/i);
    expect(markup).toMatch(/Try again/i);
  });

  it("escapes the query rather than interpolating it into markup", () => {
    // The query is user input and it is printed back. React escapes by default;
    // this pins that nobody reaches for dangerouslySetInnerHTML to style it.
    const markup = html(
      <SearchDegradedState query={'<img src=x onerror="alert(1)">'} onRetry={() => {}} />,
    );
    expect(markup).not.toContain("<img src=x");
    expect(markup).toContain("&lt;img");
  });

  it("renders without a query", () => {
    expect(() => html(<SearchDegradedState query="" onRetry={() => {}} />)).not.toThrow();
  });
});
