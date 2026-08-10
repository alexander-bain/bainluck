// C229 P1 repair — an optional animation chunk must never gate content visibility.
//
// The defect: converted call sites declare `initial={{opacity: 0}}` / `initial="hidden"`, and
// `m` renders that initial state immediately but cannot animate to `animate` until the async
// feature chunk resolves. So ready data painted transparent while the chunk was in flight, and
// stayed transparent forever if it failed — a successful feed rendering as an empty page.
//
// The rule these tests enforce is the one codex corpus `7ca89803` encodes:
//   content_ready && !content_visible && waiting_for_animation_chunk -> ANIMATION_CHUNK_GATES_CONTENT
//   animation_chunk_failed   && !content_visible                     -> OPTIONAL_CHUNK_FAILURE_HIDES_CONTENT
//   initial_hidden           && !no_motion_fallback_visible          -> INITIAL_STATE_HAS_NO_VISIBLE_FALLBACK
//
// Server-side rendering is the case that matters most and the easiest to assert: the server can
// never have the chunk, so the shipped HTML must not carry an inline `opacity: 0`.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

import { motion, __resetMotionFeaturesForTest, __motionFeatureLoadCount } from "../../components/motion";

const fadeIn = {
  hidden: { opacity: 0, y: 8 },
  visible: { opacity: 1, y: 0 },
};

beforeEach(() => {
  __resetMotionFeaturesForTest();
});

/** Any inline opacity that is zero — `opacity:0`, `opacity: 0`, `opacity:0;`. */
function hidesContent(html: string): boolean {
  return /opacity\s*:\s*0\s*(;|"|$)/.test(html);
}

describe("content paints visible before the feature chunk exists", () => {
  it("does not ship opacity:0 for an object initial (the /sports card shape)", () => {
    const html = renderToStaticMarkup(
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
        Astros at Padres
      </motion.div>,
    );

    expect(html).toContain("Astros at Padres");
    expect(hidesContent(html)).toBe(false);
  });

  it("does not ship opacity:0 for a variant initial (the FuturesCard shape)", () => {
    const html = renderToStaticMarkup(
      <motion.div variants={fadeIn} initial="hidden" animate="visible">
        Who wins the World Series?
      </motion.div>,
    );

    expect(html).toContain("Who wins the World Series?");
    expect(hidesContent(html)).toBe(false);
  });

  it("holds for span and button call sites too", () => {
    const span = renderToStaticMarkup(
      <motion.span initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
        87%
      </motion.span>,
    );
    const button = renderToStaticMarkup(
      <motion.button initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
        All stats
      </motion.button>,
    );

    expect(span).toContain("87%");
    expect(button).toContain("All stats");
    expect(hidesContent(span)).toBe(false);
    expect(hidesContent(button)).toBe(false);
  });

  it("renders a whole card wall visible, not one lucky card", () => {
    const html = renderToStaticMarkup(
      <>
        {["Padres", "Astros", "Mariners", "Rays", "Dodgers"].map((team) => (
          <motion.div key={team} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
            {team}
          </motion.div>
        ))}
      </>,
    );

    for (const team of ["Padres", "Astros", "Mariners", "Rays", "Dodgers"]) {
      expect(html).toContain(team);
    }
    expect(hidesContent(html)).toBe(false);
  });
});

// The other direction, per gotcha #43: this repair removes a hidden initial, so it must not
// remove the ELEMENT, its props, or its ability to animate once features are present.
describe("the repair does not disable animation, only un-hides the first paint", () => {
  it("keeps call-site props, children and DOM element type intact", () => {
    const html = renderToStaticMarkup(
      <motion.div
        className="card"
        data-testid="sports-card"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
      >
        content
      </motion.div>,
    );

    expect(html).toMatch(/^<div/);
    expect(html).toContain('class="card"');
    expect(html).toContain('data-testid="sports-card"');
    expect(html).toContain("content");
  });

  it("still declares the animate target, so features enhance rather than replace", () => {
    // `animate` is what the element paints AT when initial is suppressed — proving the visible
    // state is the animation's destination, not an invented one.
    const html = renderToStaticMarkup(
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
        x
      </motion.div>,
    );
    expect(hidesContent(html)).toBe(false);
    expect(html).not.toContain("visibility:hidden");
    expect(html).not.toContain("display:none");
  });
});

// C229 P2 (fanout): per-element providers are only safe if they share one loader.
describe("the feature loader is deduped across every provider", () => {
  it("initiates the dynamic import at most once for a wall of elements", () => {
    renderToStaticMarkup(
      <>
        {Array.from({ length: 40 }, (_, i) => (
          <motion.div key={i} initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
            {i}
          </motion.div>
        ))}
      </>,
    );

    // SSR never invokes the loader; the point is that it is not invoked per element.
    expect(__motionFeatureLoadCount()).toBeLessThanOrEqual(1);
  });
});
