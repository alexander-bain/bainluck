// Queue L2-125 / Item 0 Phase 1: the Discover card kernel family.
// Covers pickAngle's deterministic priority + the Claim/Duel kernels rendering
// the right glance-form per state, and the settled-grade-replaces-angle rule.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

import { pickAngle, MOVER_THRESHOLD_POINTS } from "../../components/discover/kernels/AngleBadge";
import { ClaimKernel } from "../../components/discover/kernels/ClaimKernel";
import { DuelKernel } from "../../components/discover/kernels/DuelKernel";
import { FieldKernel } from "../../components/discover/kernels/FieldKernel";
import { QuantityKernel } from "../../components/discover/kernels/QuantityKernel";
import { ContainerKernel } from "../../components/discover/kernels/ContainerKernel";

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

describe("FieldKernel — top-3 leaderboard glance-form", () => {
  const base = {
    title: "Super Bowl LXI winner",
    categorySlug: "football",
    categoryLabel: "NFL",
    categoryEmoji: "🏈",
  } as const;

  test("upcoming shows the top 3 entrants, the leader delta, and the +N more line", () => {
    const html = renderToStaticMarkup(
      <FieldKernel
        {...base}
        state="upcoming"
        entrants={[
          { name: "Buffalo Bills", probability: 0.14, deltaPoints: 1.2 },
          { name: "Kansas City Chiefs", probability: 0.12 },
          { name: "Philadelphia Eagles", probability: 0.11 },
          { name: "Should Not Render", probability: 0.09 },
        ]}
        moreCount={28}
        moreProbability={0.63}
        stateLabel="31 entrants · Resolves Feb '27"
        angle={{ kind: "surprise", label: "No favorite above 14%" }}
      />
    );
    expect(html).toContain("Buffalo Bills");
    expect(html).toContain("Kansas City Chiefs");
    expect(html).toContain("Philadelphia Eagles");
    expect(html).toContain("14%");
    expect(html).toContain("↑1.2%"); // leader delta
    expect(html).toContain("+28 more");
    expect(html).toContain("63%");
    expect(html).toContain("No favorite above 14%");
    // only the top 3 render — the 4th entrant is folded into "+N more"
    expect(html).not.toContain("Should Not Render");
  });

  test("only the leader row carries a delta", () => {
    const html = renderToStaticMarkup(
      <FieldKernel
        {...base}
        state="upcoming"
        entrants={[
          { name: "Alpha", probability: 0.3, deltaPoints: 5 },
          { name: "Beta", probability: 0.2, deltaPoints: 9 }, // ignored — not the leader
        ]}
      />
    );
    expect(html).toContain("↑5.0%");
    expect(html).not.toContain("↑9.0%");
  });

  test("settled names the winner + context + grade, drops the leaderboard", () => {
    const html = renderToStaticMarkup(
      <FieldKernel
        {...base}
        state="settled"
        entrants={[]}
        winner="Denver Nuggets"
        winnerContext="Entered playoffs at 18%"
        grade={{ correct: false, label: "Your pick: Celtics" }}
        angle={{ kind: "mover", label: "SHOULD NOT SHOW" }}
      />
    );
    expect(html).toContain("Denver Nuggets");
    expect(html).toContain("✓ Won");
    expect(html).toContain("Entered playoffs at 18%");
    expect(html).toContain("Your pick: Celtics");
    expect(html).toContain('data-grade="miss"');
    expect(html).not.toContain("SHOULD NOT SHOW");
    expect(html).toContain('data-kernel-state="settled"');
  });
});

describe("QuantityKernel — ladder-strip glance-form", () => {
  const base = {
    title: "Aaron Judge home runs?",
    categorySlug: "baseball",
    categoryLabel: "MLB",
    categoryEmoji: "⚾",
  } as const;

  test("upcoming renders the ladder rungs sorted ascending and capped", () => {
    const html = renderToStaticMarkup(
      <QuantityKernel
        {...base}
        state="upcoming"
        stateLabel="Season total"
        rungs={[
          { key: "50", label: "50+", probability: 0.12, value: 50 },
          { key: "35", label: "35+", probability: 0.92, value: 35 },
          { key: "40", label: "40+", probability: 0.71, value: 40 },
          { key: "45", label: "45+", probability: 0.38, value: 45 },
        ]}
        angle={{ kind: "for_you", label: "For you" }}
      />
    );
    // sorted ascending → the 35+ label appears before 50+
    expect(html.indexOf("35+")).toBeLessThan(html.indexOf("50+"));
    expect(html).toContain("92%");
    expect(html).toContain("12%");
    expect(html).toContain("Season total");
    expect(html).toContain("For you");
  });

  test("wideLabels widens the date-bucket label track", () => {
    const html = renderToStaticMarkup(
      <QuantityKernel
        {...base}
        title="Next Fed rate cut by…?"
        state="upcoming"
        stateLabel="By when · cumulative"
        wideLabels
        rungs={[{ key: "sep", label: "Sep '26", probability: 0.52, value: 1 }]}
      />
    );
    expect(html).toContain("Sep &#x27;26"); // apostrophe HTML-escaped in static markup
    expect(html).toContain("w-[52px]"); // wide label track
  });

  test("settled shows Hit/Miss with the landed rung highlighted, no bars", () => {
    const html = renderToStaticMarkup(
      <QuantityKernel
        {...base}
        title="Scheffler final-round birdies?"
        state="settled"
        settledRungs={[
          { label: "3+", hit: true },
          { label: "5+", hit: true, detail: "6", landed: true },
          { label: "7+", hit: false },
        ]}
        grade={{ correct: true, label: "You said 5+" }}
      />
    );
    expect(html).toContain("Hit");
    expect(html).toContain("Miss");
    expect(html).toContain("· 6"); // landed detail
    expect(html).toContain("You said 5+");
    expect(html).toContain('data-grade="hit"');
  });
});

describe("ContainerKernel — headliner + bundle count", () => {
  const base = {
    title: "The Open Championship",
    categorySlug: "golf",
    categoryLabel: "Golf",
    categoryEmoji: "⛳",
  } as const;

  test("upcoming shows the headliner probability + delta and the markets pill", () => {
    const html = renderToStaticMarkup(
      <ContainerKernel
        {...base}
        state="upcoming"
        subtitle="Royal Birkdale · Jul 16–19"
        headlinerLabel="Scheffler wins?"
        headlinerProbability={0.24}
        headlinerDeltaPoints={2.1}
        marketCount={12}
        stateLabel="Starts Thursday"
        angle={{ kind: "for_you", label: "For you" }}
      />
    );
    expect(html).toContain("The Open Championship");
    expect(html).toContain("Royal Birkdale · Jul 16–19");
    expect(html).toContain("Scheffler wins?");
    expect(html).toContain("24%");
    expect(html).toContain("↑ 2.1");
    expect(html).toContain("12 markets");
    expect(html).toContain("For you");
  });

  test("live count pill carries the suffix", () => {
    const html = renderToStaticMarkup(
      <ContainerKernel
        {...base}
        state="live"
        subtitle="Scheffler leads by 2 · −8 thru 54"
        headlinerLabel="Scheffler wins?"
        headlinerProbability={0.41}
        marketCount={12}
        marketCountSuffix="4 live"
        liveLabel="Round 3"
      />
    );
    expect(html).toContain("LIVE");
    expect(html).toContain("Round 3");
    expect(html).toContain("12 markets · 4 live");
  });

  test("settled resolves the headliner and carries the bundle grade", () => {
    const html = renderToStaticMarkup(
      <ContainerKernel
        {...base}
        state="settled"
        subtitle="Ended Sunday · Royal Birkdale"
        headlinerLabel="Scheffler wins?"
        headlinerResult="Scheffler won"
        headlinerCorrect
        marketCount={12}
        marketCountSuffix="settled"
        grade={{ correct: true, label: "3 of 4 calls right" }}
      />
    );
    expect(html).toContain("Scheffler won");
    expect(html).toContain("3 of 4 calls right");
    expect(html).toContain("12 markets · settled");
    expect(html).toContain('data-grade="hit"');
    // singular market label when count is 1
    const single = renderToStaticMarkup(
      <ContainerKernel {...base} state="upcoming" headlinerLabel="X?" headlinerProbability={0.5} marketCount={1} />
    );
    expect(single).toContain("1 market");
    expect(single).not.toContain("1 markets");
  });
});
