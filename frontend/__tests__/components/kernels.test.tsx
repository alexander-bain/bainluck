// Queue L2-125 / Item 0 Phase 1: the Discover card kernel family.
// Covers pickAngle's deterministic priority + the Claim/Duel kernels rendering
// the right glance-form per state, and the settled-grade-replaces-angle rule.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

import { pickAngle, MOVER_THRESHOLD_POINTS } from "../../components/discover/kernels/AngleBadge";
import { ClaimKernel } from "../../components/discover/kernels/ClaimKernel";
import { DuelKernel } from "../../components/discover/kernels/DuelKernel";

describe("pickAngle — one angle per card, priority order", () => {
  test("a big move wins over everything (mover is the strongest why-now)", () => {
    const a = pickAngle({ deltaPoints: 12, resolvesSoon: true, personalized: true, noClearFavorite: true });
    expect(a?.kind).toBe("mover");
    expect(a?.label).toContain("up"); // positive delta → up
  });

  test("negative movement reads as down", () => {
    const a = pickAngle({ deltaPoints: -8 });
    expect(a?.kind).toBe("mover");
    expect(a?.label).toContain("down");
  });

  test("movement below threshold does not earn the mover angle", () => {
    const a = pickAngle({ deltaPoints: MOVER_THRESHOLD_POINTS - 1, personalized: true });
    expect(a?.kind).toBe("for_you");
  });

  test("resolving_soon beats surprise/stakes/for_you when there's no big move", () => {
    expect(pickAngle({ resolvesSoon: true, noClearFavorite: true, personalized: true })?.kind).toBe("resolving_soon");
  });

  test("surprise beats stakes and for_you", () => {
    expect(pickAngle({ noClearFavorite: true, highStakes: true, personalized: true })?.kind).toBe("surprise");
  });

  test("stakes beats for_you", () => {
    expect(pickAngle({ highStakes: true, personalized: true })?.kind).toBe("stakes");
  });

  test("for_you beats banter", () => {
    expect(pickAngle({ personalized: true, banter: true })?.kind).toBe("for_you");
  });

  test("a calm card gets no badge", () => {
    expect(pickAngle({})).toBeNull();
    expect(pickAngle({ deltaPoints: 0 })).toBeNull();
  });

  test("custom label overrides are honored", () => {
    const a = pickAngle({ noClearFavorite: true, labels: { surprise: "No favorite above 14%" } });
    expect(a?.label).toBe("No favorite above 14%");
  });
});

describe("ClaimKernel — number+delta glance-form", () => {
  const base = {
    title: "Fed cuts rates by September?",
    categorySlug: "politics",
    categoryLabel: "Politics",
    categoryEmoji: "🏛",
  } as const;

  test("upcoming shows the probability, delta, bar, and angle", () => {
    const html = renderToStaticMarkup(
      <ClaimKernel {...base} state="upcoming" probability={0.68} deltaPoints={4.2} hook="Powell signaled patience" angle={{ kind: "mover", label: "Moved 12 pts" }} stateLabel="Resolves Sep 17" />
    );
    expect(html).toContain("68%");
    expect(html).toContain("↑ 4.2");
    expect(html).toContain("Powell signaled patience");
    expect(html).toContain("Moved 12 pts");
    expect(html).toContain('data-kernel-state="upcoming"');
    // one progress bar present
    expect(html).toContain("width:68%");
  });

  test("live state renders the LIVE indicator", () => {
    const html = renderToStaticMarkup(
      <ClaimKernel {...base} state="live" probability={0.41} deltaPoints={17} liveLabel="R3" />
    );
    expect(html).toContain("LIVE");
    expect(html).toContain("R3");
    expect(html).toContain('data-kernel-state="live"');
  });

  test("settled shows the result + grade chip, drops the bar, hides the angle", () => {
    const html = renderToStaticMarkup(
      <ClaimKernel {...base} state="settled" result="No" resultSubtitle="Held at 4.25% on Jul 29" grade={{ correct: false, label: "You said Yes" }} angle={{ kind: "mover", label: "SHOULD NOT SHOW" }} />
    );
    expect(html).toContain(">No<");
    expect(html).toContain("Held at 4.25% on Jul 29");
    expect(html).toContain("You said Yes");
    expect(html).toContain('data-grade="miss"');
    // the angle is replaced by the grade when settled
    expect(html).not.toContain("SHOULD NOT SHOW");
    // no progress bar in settled
    expect(html).not.toContain("width:");
  });
});

describe("DuelKernel — split with the logo hero kept", () => {
  const base = {
    awayTeam: "Yankees",
    homeTeam: "Red Sox",
    awayColor: "#132448",
    homeColor: "#BD3039",
    gradientKey: "baseball",
    categorySlug: "baseball",
    categoryLabel: "MLB",
    categoryEmoji: "⚾",
  } as const;

  test("upcoming renders a hero crest and the win-prob split", () => {
    const html = renderToStaticMarkup(
      <DuelKernel {...base} state="upcoming" awayProb={0.54} homeProb={0.46} stateLabel="Tomorrow 7:05 PM" angle={{ kind: "surprise", label: "Near coin flip" }} />
    );
    expect(html).toContain("Yankees @ Red Sox");
    expect(html).toContain("54%");
    expect(html).toContain("46%");
    expect(html).toContain("Near coin flip");
    // color-initial crest (no logo) uses the team color
    expect(html).toContain("#132448");
    expect(html).toContain("Win Probability");
  });

  test("live shows scores on the hero + LIVE + angle", () => {
    const html = renderToStaticMarkup(
      <DuelKernel {...base} state="live" awayScore={4} homeScore={3} awayProb={0.71} homeProb={0.29} liveLabel="Bot 6" angle={{ kind: "mover", label: "Flipped 20 pts" }} />
    );
    expect(html).toContain("LIVE");
    expect(html).toContain("Bot 6");
    expect(html).toContain("Flipped 20 pts");
    expect(html).toContain(">4<");
    expect(html).toContain(">3<");
  });

  test("settled infers the winner from score, shows the grade, uses 'vs'", () => {
    const html = renderToStaticMarkup(
      <DuelKernel {...base} state="settled" awayScore={3} homeScore={6} grade={{ correct: true, label: "You said Red Sox" }} />
    );
    expect(html).toContain("Yankees vs Red Sox");
    expect(html).toContain("Sox won");
    expect(html).toContain("You said Red Sox");
    expect(html).toContain('data-grade="hit"');
    // no live win-probability split on a settled card
    expect(html).not.toContain("Win Probability");
  });

  test("explicit winner overrides score inference", () => {
    const html = renderToStaticMarkup(
      <DuelKernel {...base} state="settled" awayScore={6} homeScore={3} winner="home" />
    );
    expect(html).toContain("Sox won");
  });
});
