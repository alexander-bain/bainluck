// UX-P055 (#1722's class) — one bad section must not take the whole event page.
//
// WHAT THIS SUITE CAN AND CANNOT PROVE, stated up front because the staged
// acceptance asked for something this environment cannot deliver.
//
// The queue asked for a test that "reproduces the #1722 shape rather than a
// synthetic throw". That is NOT achievable here, for two independent reasons,
// and the honest record is worth more than a test that looks like the ask:
//
//   1. Error boundaries only recover during CLIENT rendering. React does not
//      call `getDerivedStateFromError` under `renderToStaticMarkup` — the throw
//      propagates and the render dies. Recovery needs a DOM renderer.
//   2. `jest.config.js` runs `testEnvironment: 'node'`, and neither
//      `jest-environment-jsdom` nor `react-test-renderer` is installed. The npm
//      registry is unreachable from this sandbox, so neither can be added here.
//
//   3. And the payload itself no longer throws: #1722 fixed the cause, so the
//      crashing rows from event 15191146 now render fine. There is no longer a
//      production data shape that produces the error to catch.
//
// So this suite pins the boundary's REAL contract by driving the real class
// methods directly — the same code React calls, invoked without a renderer —
// plus a structural guard that every heavy section is actually wrapped. Live
// recovery is the browser rail's job, not jest's.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "fs";
import path from "path";
import ErrorBoundary from "../../components/ErrorBoundary";
import SectionErrorBoundary from "../../components/SectionErrorBoundary";

/** The verbatim production error from #1722, so the test names the real thing. */
const PRODUCTION_ERROR = "Cannot read properties of undefined (reading 'threshold')";

/** SectionErrorBoundary is a function component; calling it yields the element it delegates to. */
function delegatedElement(props: Parameters<typeof SectionErrorBoundary>[0]) {
  return SectionErrorBoundary(props) as React.ReactElement;
}

describe("SectionErrorBoundary — delegation", () => {
  test("delegates to the single ErrorBoundary rather than catching itself", () => {
    // The #1620 drift this lane has filed nine times: two components that both
    // implement catching WILL diverge. There must be exactly one catcher.
    const el = delegatedElement({ children: <p>ok</p> });
    expect(el.type).toBe(ErrorBoundary);
  });

  test("forwards resetKey to the boundary so a failed section can recover", () => {
    const el = delegatedElement({ children: <p>ok</p>, resetKey: "payload-1" });
    expect(el.props.resetKey).toBe("payload-1");
  });

  test("renders its children untouched when nothing throws", () => {
    // Gotcha #43's other direction: a healthy page must look exactly as it did.
    const wrapped = renderToStaticMarkup(
      <SectionErrorBoundary label="Player props">
        <p>62% chance</p>
      </SectionErrorBoundary>,
    );
    const bare = renderToStaticMarkup(<p>62% chance</p>);
    expect(wrapped).toBe(bare);
  });
});

describe("SectionErrorBoundary — what a caught section actually shows", () => {
  test("catching the production TypeError renders the section fallback, not the route alarm", () => {
    const el = delegatedElement({ children: <p>props</p>, label: "Player props" });
    const boundary = new ErrorBoundary(el.props);
    // Exactly the state React puts the boundary in when the child throws.
    boundary.state = ErrorBoundary.getDerivedStateFromError(new Error(PRODUCTION_ERROR));

    const html = renderToStaticMarkup(boundary.render() as React.ReactElement);

    expect(html).toContain("Player props");
    expect(html).toContain("couldn");
    expect(html).toContain("The rest of the page is unaffected.");
    // It must NOT borrow the route-level language — that string is what the
    // reader saw yesterday INSTEAD of the entire page.
    expect(html).not.toContain("This page encountered an error");
  });

  test("an unlabelled section stays generic instead of guessing", () => {
    const el = delegatedElement({ children: <p>x</p> });
    const boundary = new ErrorBoundary(el.props);
    boundary.state = ErrorBoundary.getDerivedStateFromError(new Error("boom"));
    expect(renderToStaticMarkup(boundary.render() as React.ReactElement)).toContain(
      "This section couldn",
    );
  });

  test("the fallback never fabricates a plausible empty state", () => {
    // A boundary must not become a way to hide a broken section behind
    // something that reads like "there is simply nothing here".
    const el = delegatedElement({ children: <p>x</p>, label: "Matchups" });
    const boundary = new ErrorBoundary(el.props);
    boundary.state = ErrorBoundary.getDerivedStateFromError(new Error("boom"));
    const html = renderToStaticMarkup(boundary.render() as React.ReactElement);
    expect(html).not.toMatch(/no (data|markets|props) (available|yet)/i);
  });
});

describe("ErrorBoundary — the latch, and its release", () => {
  test("getDerivedStateFromError records the error", () => {
    const err = new Error(PRODUCTION_ERROR);
    expect(ErrorBoundary.getDerivedStateFromError(err)).toEqual({ hasError: true, error: err });
  });

  test("a changed resetKey clears the error so the next payload gets a chance", () => {
    const boundary = new ErrorBoundary({ children: null, resetKey: "payload-2" });
    boundary.state = { hasError: true, error: new Error(PRODUCTION_ERROR) };
    const setStateCalls: unknown[] = [];
    boundary.setState = ((s: unknown) => setStateCalls.push(s)) as never;

    boundary.componentDidUpdate({ children: null, resetKey: "payload-1" });

    expect(setStateCalls).toEqual([{ hasError: false, error: null }]);
  });

  test("an unchanged resetKey does NOT clear it — no render loop", () => {
    const boundary = new ErrorBoundary({ children: null, resetKey: "payload-1" });
    boundary.state = { hasError: true, error: new Error(PRODUCTION_ERROR) };
    const setStateCalls: unknown[] = [];
    boundary.setState = ((s: unknown) => setStateCalls.push(s)) as never;

    boundary.componentDidUpdate({ children: null, resetKey: "payload-1" });

    expect(setStateCalls).toEqual([]);
  });

  test("a healthy boundary never resets, however the key moves", () => {
    const boundary = new ErrorBoundary({ children: null, resetKey: "b" });
    boundary.state = { hasError: false, error: null };
    const setStateCalls: unknown[] = [];
    boundary.setState = ((s: unknown) => setStateCalls.push(s)) as never;

    boundary.componentDidUpdate({ children: null, resetKey: "a" });

    expect(setStateCalls).toEqual([]);
  });

  test("existing callers that pass no resetKey keep their old latching behaviour", () => {
    // 15 pages already use ErrorBoundary. `undefined !== undefined` is false, so
    // none of them silently gained a reset.
    const boundary = new ErrorBoundary({ children: null });
    boundary.state = { hasError: true, error: new Error("boom") };
    const setStateCalls: unknown[] = [];
    boundary.setState = ((s: unknown) => setStateCalls.push(s)) as never;

    boundary.componentDidUpdate({ children: null });

    expect(setStateCalls).toEqual([]);
  });
});

describe("the event page actually wraps its sections", () => {
  const source = fs.readFileSync(
    path.join(__dirname, "../../app/events/[id]/page.tsx"),
    "utf8",
  );

  test("every heavy section is inside its own boundary", () => {
    // These are the independently-renderable sections that shared ONE boundary
    // until UX-P055. If a section is added later and is not wrapped, this is
    // the test that should be extended — not deleted.
    const labels = [
      "The score and probability",
      "The win probability chart",
      "The score differential chart",
      "The market maps",
      "Player props",
      "Matchups",
      "Special markets",
      "The script",
      "The series picture",
      "Related futures",
      "Related content",
    ];
    for (const label of labels) {
      expect(source).toContain(`<SectionErrorBoundary label="${label}"`);
    }
    const opened = source.match(/<SectionErrorBoundary/g) ?? [];
    const closed = source.match(/<\/SectionErrorBoundary>/g) ?? [];
    expect(opened).toHaveLength(labels.length);
    expect(closed).toHaveLength(labels.length);
  });

  test("the route-level boundary survives as the last resort", () => {
    // Per-section boundaries REDUCE what the route boundary has to catch; they
    // do not replace it. Something outside every section can still throw.
    expect(source).toContain("<ErrorBoundary fallback={");
    expect(source).toContain("This page encountered an error");
  });

  test("the props dashboard memo depends on the field it reads", () => {
    // #1722 follow-up: the memo reads data.other twice; omitting it from the
    // deps serves a stale card when a refetch changes only that field.
    //
    // UX-P056: the memo body moved to `lib/playerPropsGrouping.ts`, but the
    // DEPS array is still the dashboard's — a stale card is a caller bug, not a
    // module one — so this stays pointed here, matched on the array itself
    // rather than on the closing punctuation the extraction reformatted.
    const dashboard = fs.readFileSync(
      path.join(__dirname, "../../components/PlayerPropsDashboard.tsx"),
      "utf8",
    );
    const deps = dashboard.match(/\[data\.player_props[^\]]*\]/);
    expect(deps).not.toBeNull();
    expect(deps![0]).toContain("data.other");
  });
});
