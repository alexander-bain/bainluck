"use client";

import EmbedAwareLink from "@/components/EmbedAwareLink";

const LIVE_RANGE_EXAMPLES = [
  {
    domain: "Tonight's game",
    subject: "Lions vs Patriots",
    chance: "58%",
    widthPct: 58,
  },
  {
    domain: "Election",
    subject: "Senate majority",
    chance: "74%",
    widthPct: 74,
  },
  {
    domain: "The Oscars",
    subject: "One Battle After Another",
    chance: "29%",
    widthPct: 29,
  },
  {
    domain: "The Fed",
    subject: "December rate cut",
    chance: "72%",
    widthPct: 72,
  },
] as const;

export default function AboutPage189() {
  return (
    <div
      data-testid="about-page-189"
      className="max-w-3xl mx-auto px-4 sm:px-6 pt-3 pb-10 space-y-6 sm:space-y-8"
    >
      {/* Hero — Decision 189 paired headline + plain second line + lead copy */}
      <section className="bg-surface-card rounded-2xl border border-surface-border shadow-card p-6 sm:p-8 space-y-5">
        <div className="inline-flex items-center rounded-full bg-surface-deep border border-surface-border px-3 py-1">
          <span className="text-micro font-semibold uppercase tracking-wider text-accent-brand">
            About Bain Luck
          </span>
        </div>

        <div className="space-y-2">
          <h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-text-primary leading-[1.08]">
            The real score for everything.
          </h1>
          <p className="text-lg sm:text-xl font-medium text-text-secondary leading-snug">
            What the world thinks will happen, as one clear percentage.
          </p>
        </div>

        <p className="text-body text-text-secondary leading-relaxed">
          A scoreboard tells you who&apos;s ahead. It doesn&apos;t tell you who&apos;s going to win.
          Bain Luck does: for tonight&apos;s game, next year&apos;s election, the Oscars, the
          weather, the Fed.
        </p>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 pt-1">
          {LIVE_RANGE_EXAMPLES.map((item) => (
            <div
              key={item.domain}
              className="rounded-xl border border-surface-border bg-surface-deep p-3 flex flex-col justify-between gap-2"
            >
              <div className="space-y-0.5">
                <div className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">
                  {item.domain}
                </div>
                <div className="text-xs font-semibold text-text-primary leading-snug">
                  {item.subject}
                </div>
              </div>
              <div className="relative overflow-hidden rounded-md border border-surface-border bg-surface-card px-2 py-1 flex items-center justify-end">
                <span
                  aria-hidden="true"
                  className="pointer-events-none absolute inset-y-0 left-0 bg-accent-brand/15"
                  style={{ width: `${item.widthPct}%` }}
                />
                <span className="relative font-mono text-sm font-bold tabular-nums text-accent-brand">
                  {item.chance}
                </span>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Body grid — 1 column on phone (390 px), 2 columns on desktop */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 sm:gap-5">
        {/* 1. One number */}
        <section className="bg-surface-card rounded-2xl border border-surface-border shadow-card p-6 flex flex-col justify-between gap-4">
          <div className="space-y-2.5">
            <h2 className="text-title-2 font-bold text-text-primary">One number.</h2>
            <p className="text-body text-text-secondary leading-relaxed">
              Every day, thousands of people commit to what they expect will happen. We read the
              prediction markets and the sportsbooks and blend them into a single chance for each
              outcome.
            </p>
          </div>

          <div
            aria-hidden="true"
            className="rounded-xl border border-surface-border bg-surface-deep px-3.5 py-2.5 flex items-center justify-between gap-2 text-xs text-text-secondary"
          >
            <div className="flex items-center gap-1.5 font-medium">
              <span>Prediction markets</span>
              <span className="text-text-muted">+</span>
              <span>Sportsbooks</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="text-text-muted">&rarr;</span>
              <span className="rounded-md bg-accent-brand/15 px-2 py-0.5 font-mono font-bold text-accent-brand tabular-nums">
                64%
              </span>
            </div>
          </div>
        </section>

        {/* 2. How to read it */}
        <section className="bg-surface-card rounded-2xl border border-surface-border shadow-card p-6 flex flex-col justify-between gap-4">
          <div className="space-y-2.5">
            <div className="flex items-baseline justify-between gap-3">
              <h2 className="text-title-2 font-bold text-text-primary">How to read it.</h2>
              <span className="font-mono text-2xl font-extrabold tabular-nums text-accent-brand">
                64%
              </span>
            </div>
            <p className="text-body text-text-secondary leading-relaxed">
              64% means it happens about two times in three. It&apos;s the world&apos;s best guess,
              not a promise. Watch it move; the movement is the story.
            </p>
          </div>

          <div
            aria-hidden="true"
            className="rounded-xl border border-surface-border bg-surface-deep p-3 space-y-2"
          >
            <div className="grid grid-cols-3 gap-1.5">
              <div className="h-2.5 rounded-full bg-accent-brand" />
              <div className="h-2.5 rounded-full bg-accent-brand" />
              <div className="h-2.5 rounded-full bg-surface-border" />
            </div>
            <div className="flex items-center justify-between text-[11px] font-medium text-text-muted">
              <span>About 2 times in 3</span>
              <span className="font-mono tabular-nums text-accent-brand">52% &rarr; 64% (+12 pts)</span>
            </div>
          </div>
        </section>

        {/* 3. Not betting */}
        <section className="bg-surface-card rounded-2xl border border-surface-border shadow-card p-6 flex flex-col justify-between gap-4">
          <div className="space-y-2.5">
            <div className="flex items-center gap-2">
              <svg
                aria-hidden="true"
                viewBox="0 0 24 24"
                className="w-5 h-5 text-accent-brand shrink-0"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M6 3.75h12A1.25 1.25 0 0 1 19.25 5v15.25L12 16.25l-7.25 4V5A1.25 1.25 0 0 1 6 3.75Z"
                />
              </svg>
              <h2 className="text-title-2 font-bold text-text-primary">Not betting.</h2>
            </div>
            <p className="text-body text-text-secondary leading-relaxed">
              No odds to decode, no bets to place, nothing to buy.
            </p>
          </div>
        </section>

        {/* 4. We keep score on ourselves */}
        <section className="bg-surface-card rounded-2xl border border-surface-border shadow-card p-6 flex flex-col justify-between gap-4">
          <div className="space-y-2.5">
            <h2 className="text-title-2 font-bold text-text-primary">
              We keep score on ourselves.
            </h2>
            <p className="text-body text-text-secondary leading-relaxed">
              Every finished game and settled market is checked against what we showed.{" "}
              <EmbedAwareLink
                href="/calibration"
                className="font-semibold text-accent-brand hover:underline"
              >
                See how we&apos;ve done.
              </EmbedAwareLink>
            </p>
          </div>

          <div
            aria-hidden="true"
            className="rounded-xl border border-surface-border bg-surface-deep px-3.5 py-2.5 flex items-center justify-between gap-3"
          >
            <svg viewBox="0 0 120 40" className="w-28 h-9 text-accent-brand shrink-0" fill="none">
              <line
                x1="8"
                y1="34"
                x2="112"
                y2="6"
                stroke="currentColor"
                strokeOpacity="0.28"
                strokeWidth="1.5"
                strokeDasharray="3 3"
              />
              <polyline
                points="8,33 29,28 50,21 71,17 92,11 112,6"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              <circle cx="29" cy="28" r="2" fill="currentColor" />
              <circle cx="71" cy="17" r="2" fill="currentColor" />
              <circle cx="112" cy="6" r="2" fill="currentColor" />
            </svg>
            <span className="text-[11px] font-medium text-text-muted text-right leading-snug">
              Forecast % vs what happened
            </span>
          </div>
        </section>
      </div>

      {/* Primary CTA */}
      <div className="pt-2 text-center">
        <EmbedAwareLink
          href="/discover"
          className="inline-flex items-center justify-center rounded-full bg-text-primary text-surface-deep px-8 py-3.5 text-body-strong hover:bg-text-primary/90 transition-colors"
        >
          Start exploring
        </EmbedAwareLink>
      </div>

      {/* Final bottom row of the About page (Ruling 195-A + Fable #12735: last row in page flow, never a pinned bar) */}
      <div
        data-testid="about-bottom-links-row"
        className="border-t border-surface-border pt-5 text-center text-caption text-text-muted flex flex-wrap items-center justify-center gap-x-2.5 gap-y-1"
      >
        <a href="mailto:bugs@bainluck.com" className="hover:text-text-primary hover:underline">
          bugs@bainluck.com
        </a>
        <span aria-hidden="true">&middot;</span>
        <EmbedAwareLink href="/privacy" className="hover:text-text-primary hover:underline">
          Privacy Policy
        </EmbedAwareLink>
        <span aria-hidden="true">&middot;</span>
        <EmbedAwareLink href="/picture-credits" className="hover:text-text-primary hover:underline">
          Picture credits
        </EmbedAwareLink>
      </div>
    </div>
  );
}
