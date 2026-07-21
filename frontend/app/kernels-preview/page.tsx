"use client";

/**
 * /kernels-preview — internal showcase for the Discover card kernel family
 * (Queue L2-125 Phase 1 → L2-141 the full family). Renders all FIVE kernels —
 * Claim, Quantity, Duel, Field, Container — in their three states, plus one
 * composed mixed feed where every kernel renders as one family. That mixed feed
 * is the design's own acceptance bar (handoff `2f`): density/rhythm judged as a
 * system.
 *
 * Not linked from nav — an internal design-review surface. Sample data mirrors
 * the "Discover Card System" handoff mock (2026-07-15) so this page is the
 * living, pixel-checkable version of that static export. The live feed is
 * unchanged; wiring the kernels into the feed is a later phase.
 */

import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import {
  ClaimKernel,
  DuelKernel,
  FieldKernel,
  QuantityKernel,
  ContainerKernel,
} from "@/components/discover/kernels";

const NYY = "#132448";
const BOS = "#BD3039";

function ColumnLabel({ children }: { children: React.ReactNode }) {
  return <div className="text-[10px] font-semibold uppercase tracking-[0.04em] text-text-muted">{children}</div>;
}

function KernelColumn({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="flex w-[347px] shrink-0 flex-col gap-3.5">
      <div className="text-sm font-semibold text-text-primary">{title}</div>
      {children}
    </div>
  );
}

// ── Claim samples (design card 2a) ──

function claimUpcoming() {
  return (
    <ClaimKernel
      state="upcoming"
      title="Fed cuts rates by September?"
      hook="Powell signaled patience on Friday"
      probability={0.68}
      deltaPoints={4.2}
      stateLabel="Resolves Sep 17"
      timestamp="5m ago"
      angle={{ kind: "mover", label: "Moved 12 pts this week" }}
      categorySlug="politics"
      categoryLabel="Politics"
      categoryEmoji="🏛"
    />
  );
}

function claimLive() {
  return (
    <ClaimKernel
      state="live"
      title="Scheffler wins The Open?"
      hook="Leads by 2 through 54 holes"
      probability={0.41}
      deltaPoints={17}
      liveLabel="R3"
      timestamp="Live"
      angle={{ kind: "resolving_soon", label: "Resolves Sunday" }}
      categorySlug="golf"
      categoryLabel="Golf"
      categoryEmoji="⛳"
    />
  );
}

function claimSettled() {
  return (
    <ClaimKernel
      state="settled"
      title="Fed cuts rates in July?"
      result="No"
      resultSubtitle="Held at 4.25% on Jul 29"
      stateLabel="Resolved"
      timestamp="Final · Jul 29"
      grade={{ correct: false, label: "You said Yes" }}
      categorySlug="politics"
      categoryLabel="Politics"
      categoryEmoji="🏛"
    />
  );
}

// ── Duel samples (design card 2c) ──

function duelUpcoming() {
  return (
    <DuelKernel
      state="upcoming"
      awayTeam="Yankees"
      homeTeam="Red Sox"
      awayColor={NYY}
      homeColor={BOS}
      awayProb={0.54}
      homeProb={0.46}
      stateLabel="Tomorrow 7:05 PM"
      timestamp="8m ago"
      angle={{ kind: "surprise", label: "Near coin flip" }}
      gradientKey="baseball"
      categorySlug="baseball"
      categoryLabel="MLB"
      categoryEmoji="⚾"
    />
  );
}

function duelLive() {
  return (
    <DuelKernel
      state="live"
      awayTeam="Yankees"
      homeTeam="Red Sox"
      awayColor={NYY}
      homeColor={BOS}
      awayScore={4}
      homeScore={3}
      awayProb={0.71}
      homeProb={0.29}
      liveLabel="Bot 6"
      timestamp="Live"
      angle={{ kind: "mover", label: "Flipped 20 pts" }}
      gradientKey="baseball"
      categorySlug="baseball"
      categoryLabel="MLB"
      categoryEmoji="⚾"
    />
  );
}

function duelSettled() {
  return (
    <DuelKernel
      state="settled"
      awayTeam="Yankees"
      homeTeam="Red Sox"
      awayColor={NYY}
      homeColor={BOS}
      awayScore={3}
      homeScore={6}
      winner="home"
      timestamp="Final · 10:12 PM"
      grade={{ correct: true, label: "You said Red Sox" }}
      gradientKey="baseball"
      categorySlug="baseball"
      categoryLabel="MLB"
      categoryEmoji="⚾"
    />
  );
}

// ── Field samples (design card 1f / 2f) ──

function fieldUpcoming() {
  return (
    <FieldKernel
      state="upcoming"
      title="Super Bowl LXI winner"
      entrants={[
        { name: "Buffalo Bills", probability: 0.14, deltaPoints: 1.2 },
        { name: "Kansas City Chiefs", probability: 0.12 },
        { name: "Philadelphia Eagles", probability: 0.11 },
      ]}
      moreCount={28}
      moreProbability={0.63}
      stateLabel="31 entrants · Resolves Feb '27"
      timestamp="2h ago"
      angle={{ kind: "surprise", label: "No favorite above 14%" }}
      categorySlug="football"
      categoryLabel="NFL"
      categoryEmoji="🏈"
    />
  );
}

function fieldLive() {
  return (
    <FieldKernel
      state="live"
      title="The Open winner"
      entrants={[
        { name: "Scottie Scheffler", probability: 0.41, deltaPoints: 17 },
        { name: "Rory McIlroy", probability: 0.27 },
        { name: "Ludvig Åberg", probability: 0.11 },
      ]}
      moreCount={61}
      moreProbability={0.21}
      stateLabel="R3"
      liveLabel="R3"
      timestamp="Live"
      angle={{ kind: "mover", label: "Åberg up 6 pts in R3" }}
      categorySlug="golf"
      categoryLabel="Golf"
      categoryEmoji="⛳"
    />
  );
}

function fieldSettled() {
  return (
    <FieldKernel
      state="settled"
      title="NBA champion 2026"
      entrants={[]}
      winner="Denver Nuggets"
      winnerContext="Entered playoffs at 18%"
      timestamp="Final · Jun 19"
      grade={{ correct: false, label: "Your pick: Celtics" }}
      categorySlug="basketball"
      categoryLabel="NBA"
      categoryEmoji="🏀"
    />
  );
}

// ── Quantity samples (design card 1d / 2f) ──

function quantityUpcoming() {
  return (
    <QuantityKernel
      state="upcoming"
      title="Aaron Judge home runs?"
      stateLabel="Season total"
      rungs={[
        { key: "35", label: "35+", probability: 0.92, value: 35 },
        { key: "40", label: "40+", probability: 0.71, value: 40 },
        { key: "45", label: "45+", probability: 0.38, value: 45 },
        { key: "50", label: "50+", probability: 0.12, value: 50 },
      ]}
      timestamp="32 HRs today · 12m ago"
      angle={{ kind: "for_you", label: "For you" }}
      categorySlug="baseball"
      categoryLabel="MLB"
      categoryEmoji="⚾"
    />
  );
}

function quantityDateBuckets() {
  return (
    <QuantityKernel
      state="upcoming"
      title="Next Fed rate cut by…?"
      stateLabel="By when · cumulative"
      wideLabels
      rungs={[
        { key: "sep", label: "Sep '26", probability: 0.52, value: 1 },
        { key: "nov", label: "Nov '26", probability: 0.74, value: 2 },
        { key: "dec", label: "Dec '26", probability: 0.83, value: 3 },
        { key: "mar", label: "Mar '27", probability: 0.91, value: 4 },
      ]}
      timestamp="1h ago"
      angle={{ kind: "mover", label: "Sep jumped 9 pts" }}
      categorySlug="politics"
      categoryLabel="Politics"
      categoryEmoji="🏛"
    />
  );
}

function quantitySettled() {
  return (
    <QuantityKernel
      state="settled"
      title="Scheffler final-round birdies?"
      stateLabel="Resolved"
      settledRungs={[
        { label: "3+", hit: true },
        { label: "4+", hit: true },
        { label: "5+", hit: true, detail: "6", landed: true },
        { label: "7+", hit: false },
      ]}
      timestamp="Final · Sunday"
      grade={{ correct: true, label: "You said 5+" }}
      categorySlug="golf"
      categoryLabel="Golf"
      categoryEmoji="⛳"
    />
  );
}

// ── Container samples (design card 1h / 2f) ──

function containerUpcoming() {
  return (
    <ContainerKernel
      state="upcoming"
      title="The Open Championship"
      subtitle="Royal Birkdale · Jul 16–19"
      headlinerLabel="Scheffler wins?"
      headlinerProbability={0.24}
      headlinerDeltaPoints={2.1}
      marketCount={12}
      stateLabel="Starts Thursday"
      timestamp="3h ago"
      angle={{ kind: "for_you", label: "For you" }}
      categorySlug="golf"
      categoryLabel="Golf"
      categoryEmoji="⛳"
    />
  );
}

function containerLive() {
  return (
    <ContainerKernel
      state="live"
      title="The Open Championship"
      subtitle="Scheffler leads by 2 · −8 thru 54"
      headlinerLabel="Scheffler wins?"
      headlinerProbability={0.41}
      headlinerDeltaPoints={17}
      marketCount={12}
      marketCountSuffix="4 live"
      liveLabel="Round 3"
      timestamp="Live"
      angle={{ kind: "resolving_soon", label: "Ends Sunday" }}
      categorySlug="golf"
      categoryLabel="Golf"
      categoryEmoji="⛳"
    />
  );
}

function containerSettled() {
  return (
    <ContainerKernel
      state="settled"
      title="The Open Championship"
      subtitle="Ended Sunday · Royal Birkdale"
      headlinerLabel="Scheffler wins?"
      headlinerResult="Scheffler won"
      headlinerCorrect
      marketCount={12}
      marketCountSuffix="settled"
      stateLabel="Ended"
      timestamp="Final"
      grade={{ correct: true, label: "3 of 4 calls right" }}
      categorySlug="golf"
      categoryLabel="Golf"
      categoryEmoji="⛳"
    />
  );
}

// ── The mixed-feed acceptance (design `2f`): all five kernels, one family ──

function MixedFeed() {
  return (
    <div className="flex w-[375px] flex-col gap-2.5 rounded-2xl border border-surface-border bg-surface-deep p-4">
      <div className="flex items-center gap-1.5 px-0.5 pb-1.5">
        <span className="text-base">🍀</span>
        <span className="text-base font-bold tracking-[-0.01em] text-text-primary">Discover</span>
        <span className="ml-auto text-[11px] text-text-muted">42 events · Personalized</span>
      </div>
      {containerLive()}
      {duelLive()}
      {claimUpcoming()}
      {quantityUpcoming()}
      {fieldUpcoming()}
      {quantityDateBuckets()}
      {containerUpcoming()}
      {fieldSettled()}
      {claimSettled()}
    </div>
  );
}

export default function KernelsPreviewPage() {
  usePageTracking({ pageType: "kernels_preview", pageTitle: "Kernel cards preview" });
  useScrollDepth({ pageType: "kernels_preview" });
  useEngagementTime({ pageType: "kernels_preview" });

  return (
    <div className="mx-auto max-w-[1400px] px-6 py-10">
      <header className="mb-2 flex flex-col gap-2">
        <h1 className="text-[28px] font-semibold tracking-[-0.01em] text-text-primary">Discover card kernels — the full family</h1>
        <p className="max-w-[760px] text-sm leading-relaxed text-text-secondary">
          All five kernels — Claim, Quantity, Duel, Field, Container — in their three states, plus the composed mixed
          feed that is the design&apos;s acceptance bar. Unified chrome: header = state + ONE angle (a grade chip
          replaces the angle when settled), footer = league + timestamp. The Field kernel carries the accent top border;
          the Container carries the bundle-count pill. Live feed is unchanged — this is a design-review surface only.
        </p>
      </header>

      {/* Per-kernel columns, each in its three states */}
      <section className="mt-8 flex flex-wrap gap-x-12 gap-y-14">
        <KernelColumn title="Claim · number + delta">
          <ColumnLabel>Upcoming</ColumnLabel>
          {claimUpcoming()}
          <ColumnLabel>Live</ColumnLabel>
          {claimLive()}
          <ColumnLabel>Settled</ColumnLabel>
          {claimSettled()}
        </KernelColumn>

        <KernelColumn title="Quantity · ladder-strip">
          <ColumnLabel>Thresholds · upcoming</ColumnLabel>
          {quantityUpcoming()}
          <ColumnLabel>Date buckets · upcoming</ColumnLabel>
          {quantityDateBuckets()}
          <ColumnLabel>Settled</ColumnLabel>
          {quantitySettled()}
        </KernelColumn>

        <KernelColumn title="Duel · split (logo hero kept)">
          <ColumnLabel>Upcoming</ColumnLabel>
          {duelUpcoming()}
          <ColumnLabel>Live</ColumnLabel>
          {duelLive()}
          <ColumnLabel>Settled</ColumnLabel>
          {duelSettled()}
        </KernelColumn>

        <KernelColumn title="Field · top-3 leaderboard">
          <ColumnLabel>Upcoming</ColumnLabel>
          {fieldUpcoming()}
          <ColumnLabel>Live (in-tournament)</ColumnLabel>
          {fieldLive()}
          <ColumnLabel>Settled</ColumnLabel>
          {fieldSettled()}
        </KernelColumn>

        <KernelColumn title="Container · headliner + count">
          <ColumnLabel>Upcoming</ColumnLabel>
          {containerUpcoming()}
          <ColumnLabel>Live</ColumnLabel>
          {containerLive()}
          <ColumnLabel>Settled</ColumnLabel>
          {containerSettled()}
        </KernelColumn>

        {/* Composed mixed feed — density/rhythm as a system (the acceptance bar) */}
        <div className="flex flex-col gap-3.5">
          <div className="text-sm font-semibold text-text-primary">Mixed feed · the acceptance bar</div>
          <MixedFeed />
        </div>
      </section>
    </div>
  );
}
