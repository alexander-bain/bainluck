"use client";

/**
 * /kernels-preview — internal showcase for the Discover card kernel family
 * (Queue L2-125 / Item 0, Phase 1). Renders the Claim + Duel kernels in all
 * three states plus a composed mixed feed, so the family can be judged as a
 * system before it's wired into the live feed (Phase 2).
 *
 * Not linked from nav — an internal design-review surface. Sample data mirrors
 * the "Discover Card System" handoff mock (2026-07-15) so this page is the
 * living, pixel-checkable version of that static export.
 */

import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import { ClaimKernel, DuelKernel } from "@/components/discover/kernels";

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

export default function KernelsPreviewPage() {
  usePageTracking({ pageType: "kernels_preview", pageTitle: "Kernel cards preview" });
  useScrollDepth({ pageType: "kernels_preview" });
  useEngagementTime({ pageType: "kernels_preview" });

  return (
    <div className="mx-auto max-w-[1200px] px-6 py-10">
      <header className="mb-2 flex flex-col gap-2">
        <h1 className="text-[28px] font-semibold tracking-[-0.01em] text-text-primary">Discover card kernels — Phase 1</h1>
        <p className="max-w-[720px] text-sm leading-relaxed text-text-secondary">
          Claim + Duel kernels in all three states, plus a mixed feed. Unified chrome: header = state + ONE angle
          (a grade chip replaces the angle when settled), footer = league + timestamp. Live feed is unchanged —
          this is a design-review surface only.
        </p>
      </header>

      {/* Per-kernel columns, each in its three states */}
      <section className="mt-8 flex flex-wrap gap-12">
        <KernelColumn title="Claim · number + delta">
          <ColumnLabel>Upcoming</ColumnLabel>
          {claimUpcoming()}
          <ColumnLabel>Live</ColumnLabel>
          {claimLive()}
          <ColumnLabel>Settled</ColumnLabel>
          {claimSettled()}
        </KernelColumn>

        <KernelColumn title="Duel · split (logo hero kept)">
          <ColumnLabel>Upcoming</ColumnLabel>
          {duelUpcoming()}
          <ColumnLabel>Live</ColumnLabel>
          {duelLive()}
          <ColumnLabel>Settled</ColumnLabel>
          {duelSettled()}
        </KernelColumn>

        {/* Composed mixed feed — density/rhythm as a system */}
        <KernelColumn title="Mixed feed">
          {duelLive()}
          {claimUpcoming()}
          {duelUpcoming()}
          {claimLive()}
          {duelSettled()}
          {claimSettled()}
        </KernelColumn>
      </section>
    </div>
  );
}
