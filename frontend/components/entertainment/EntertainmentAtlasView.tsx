"use client";

import React, { useState } from "react";
import type {
  EntertainmentData,
  EntMarketRow,
  EntThresholdGroup,
} from "@/lib/api";
import { formatAtlasTimestampPT } from "@/components/atlas/atlasStateCopy";
import {
  BinaryRow,
  BucketDistribution,
  FieldBoard,
  ThresholdLadderCard,
  type AtlasCategoryOutcome,
  type AtlasMarketMeta,
} from "@/components/atlas/CategoryAtlasComponents";

type FilterKey = "all" | "music" | "movies" | "tv" | "internet";

const FILTERS: { key: FilterKey; label: string }[] = [
  { key: "all", label: "All" },
  { key: "music", label: "Music & Charts" },
  { key: "movies", label: "Movies & Box Office" },
  { key: "tv", label: "TV & Awards" },
  { key: "internet", label: "Culture & Tech" },
];

function parseLeadingNumber(label: string): number | null {
  const cleaned = (label || "").replace(/,/g, "");
  const m = /(-?\d+(?:\.\d+)?)/.exec(cleaned);
  if (!m) return null;
  const n = Number(m[1]);
  return Number.isFinite(n) ? n : null;
}

function isThresholdLabel(label: string): boolean {
  return /^(above|over|at least|under|below|more than|less than|before)\b/i.test(
    (label || "").trim()
  ) || /\+$/.test((label || "").trim());
}

function isRangeBucketLabel(label: string): boolean {
  return /(\d[\d,.]*\s*[–-]\s*\$?\d|<\s*\$?\d|>\s*\$?\d|\bto\b)/i.test(label || "");
}

type ExtendedEntMarketRow = EntMarketRow & {
  leader?: string | null;
  status?: string | null;
  settled_winner?: string | null;
};

function toOrderedOutcomes(
  outcomes: { name: string; prob: number }[],
  orderNumeric: boolean,
  settledWinner?: string | null
): AtlasCategoryOutcome[] {
  const items = outcomes.map((o, idx) => ({
    o,
    idx,
    num: parseLeadingNumber(o.name),
  }));
  const sorted =
    orderNumeric && items.filter((x) => x.num !== null).length >= 2
      ? [...items].sort((a, b) => {
          if (a.num !== null && b.num !== null && a.num !== b.num) {
            return a.num - b.num;
          }
          if (a.num !== null && b.num === null) return -1;
          if (a.num === null && b.num !== null) return 1;
          return a.idx - b.idx;
        })
      : items;

  const winnerNorm = (settledWinner || "").trim().toLowerCase();
  return sorted.map(({ o }, idx): AtlasCategoryOutcome => {
    const won =
      Boolean(winnerNorm) && o.name.trim().toLowerCase() === winnerNorm;
    const lost = Boolean(winnerNorm) && !won;
    return {
      id: `${o.name}-${idx}`,
      label: o.name,
      probability: o.prob / 100,
      renderedPercent: Math.round(o.prob),
      isSettled: Boolean(winnerNorm),
      isWinner: won ? true : lost ? false : null,
      settledResult: won ? "won" : lost ? "lost" : null,
    };
  });
}

function renderEntMarketByShape(
  row: ExtendedEntMarketRow,
  kickerOverride?: string
) {
  const outcomes = row.lead_outcomes?.length ? row.lead_outcomes : row.top_outcomes ?? [];
  const meta: AtlasMarketMeta = {
    marketId: row.market_id,
    marketTitle: row.q,
    kicker: kickerOverride ?? row.kind?.toUpperCase() ?? null,
    resolutionDate: row.resolution_date,
    source: row.src,
    externalId: row.external_id,
  };
  const settledWinner = row.settled_winner ?? null;

  if (outcomes.length <= 1 || row.kind === "binary") {
    const lead = outcomes[0];
    const prob = lead ? lead.prob : row.prob;
    const won =
      Boolean(settledWinner) &&
      (settledWinner?.toLowerCase() === "yes" ||
        settledWinner?.toLowerCase() === lead?.name?.toLowerCase() ||
        settledWinner?.toLowerCase() === row.leader?.toLowerCase());
    const lost = Boolean(settledWinner) && !won;
    return (
      <BinaryRow
        key={row.market_id}
        meta={meta}
        outcome={{
          id: row.market_id,
          label: lead?.name && !/^(yes|no)$/i.test(lead.name) ? lead.name : row.q,
          probability: prob / 100,
          renderedPercent: Math.round(prob),
          isSettled: Boolean(settledWinner),
          isWinner: won ? true : lost ? false : null,
          settledResult: won ? "won" : lost ? "lost" : null,
        }}
      />
    );
  }

  const thresholdCount = outcomes.filter((o) => isThresholdLabel(o.name)).length;
  if (row.ladder || row.kind === "rt" || thresholdCount >= 2) {
    return (
      <ThresholdLadderCard
        key={row.market_id}
        meta={meta}
        rungs={toOrderedOutcomes(outcomes, true, settledWinner)}
      />
    );
  }

  const rangeCount = outcomes.filter((o) => isRangeBucketLabel(o.name)).length;
  const numericCount = outcomes.filter((o) => parseLeadingNumber(o.name) !== null).length;
  if (rangeCount >= 2 || (numericCount === outcomes.length && outcomes.length >= 3)) {
    return (
      <BucketDistribution
        key={row.market_id}
        meta={meta}
        buckets={toOrderedOutcomes(outcomes, true, settledWinner)}
      />
    );
  }

  return (
    <FieldBoard
      key={row.market_id}
      meta={meta}
      outcomes={toOrderedOutcomes(outcomes, false, settledWinner)}
    />
  );
}

function renderThresholdGroup(
  group: EntThresholdGroup,
  kicker: string,
  shape: "ladder" | "buckets" = "ladder"
) {
  const sorted = [...(group.thresholds ?? [])].sort((a, b) => {
    const na = parseLeadingNumber(a.label);
    const nb = parseLeadingNumber(b.label);
    if (na !== null && nb !== null && na !== nb) return na - nb;
    return 0;
  });
  const outcomes: AtlasCategoryOutcome[] = sorted.map((t, idx) => ({
    id: t.market_id ?? `${t.label}-${idx}`,
    label: t.label,
    probability: t.prob / 100,
    renderedPercent: Math.round(t.prob),
  }));
  const firstMarketId = sorted[0]?.market_id ?? null;

  if (shape === "buckets") {
    return (
      <BucketDistribution
        key={group.title}
        meta={{
          marketId: firstMarketId,
          kicker,
          marketTitle: group.title,
        }}
        buckets={outcomes}
      />
    );
  }

  return (
    <ThresholdLadderCard
      key={group.title}
      meta={{
        marketId: firstMarketId,
        kicker,
        marketTitle: group.title,
      }}
      rungs={outcomes}
    />
  );
}

export default function EntertainmentAtlasView({
  data,
}: {
  data: EntertainmentData;
}) {
  const [filter, setFilter] = useState<FilterKey>("all");
  const show = (key: FilterKey) => filter === "all" || filter === key;
  const updatedPT = formatAtlasTimestampPT(data.updated_at);

  const music = data.themes?.music;
  const moviesTv = data.themes?.movies_tv;
  const techCulture = data.themes?.tech_culture;

  return (
    <div
      data-testid="entertainment-atlas-view"
      className="max-w-[1120px] mx-auto px-4 md:px-6 py-8 space-y-10"
    >
      {/* Hero */}
      <section data-section="HERO" className="space-y-3">
        <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">
          ENTERTAINMENT &amp; CULTURE · PROBABILITY FIRST
        </p>
        <h1 className="text-3xl md:text-4xl font-semibold text-text-primary tracking-tight">
          What the world thinks will happen in pop culture
        </h1>
        <p className="text-sm text-text-secondary max-w-2xl">
          Live probabilities on charts, box office, reality TV, and cultural
          milestones — one calibrated reading per market.
        </p>
        {updatedPT && (
          <p className="font-mono text-xs text-text-muted">
            Last reading {updatedPT}
          </p>
        )}
      </section>

      {/* Filter pills */}
      <div className="flex flex-wrap gap-2">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            type="button"
            onClick={() => setFilter(f.key)}
            className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${
              filter === f.key
                ? "bg-text-primary text-surface-card border-text-primary"
                : "bg-surface-card text-text-secondary border-surface-border hover:text-text-primary"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* Trending Now */}
      {data.trending && data.trending.length > 0 && (
        <section data-section="TRENDING" className="space-y-4">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">
              TRENDING NOW
            </p>
            <h2 className="text-xl font-semibold text-text-primary mt-0.5">
              Lead pop-culture markets
            </h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {data.trending.map((row) => renderEntMarketByShape(row, "TRENDING"))}
          </div>
        </section>
      )}

      {/* Music & Charts */}
      {show("music") && music && (
        <section data-section="MUSIC" className="space-y-6">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">
              MUSIC &amp; CHARTS
            </p>
            <h2 className="text-xl font-semibold text-text-primary mt-0.5">
              Billboard, Spotify &amp; releases
            </h2>
          </div>

          {/* Billboard Watch */}
          {((music.billboard_groups?.length ?? 0) > 0 ||
            (music.billboard_watch?.length ?? 0) > 0) && (
            <div className="space-y-3" data-testid="atlas-billboard-watch">
              <div className="flex items-center justify-between text-xs font-mono uppercase tracking-wider text-text-muted">
                <span>SONG / CHART WEEK</span>
                <span>CHANCE</span>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {music.billboard_groups?.map((g) =>
                  renderThresholdGroup(g, "BILLBOARD · SONG / CHART WEEK", "ladder")
                )}
                {music.billboard_watch?.map((row) =>
                  renderEntMarketByShape(row, "BILLBOARD · SONG / CHART WEEK")
                )}
              </div>
            </div>
          )}

          {/* Spotify, Album drops, Artist streaming, Side markets */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {music.spotify_race?.map((row) =>
              renderEntMarketByShape(row, "SPOTIFY CHARTS")
            )}
            {music.album_drops?.map((row) =>
              renderEntMarketByShape(row, "ALBUM RELEASES")
            )}
            {music.artist_streaming?.map((row) =>
              renderEntMarketByShape(row, "STREAMING")
            )}
            {music.side_markets?.map((row) =>
              renderEntMarketByShape(row, "MUSIC")
            )}
          </div>
        </section>
      )}

      {/* Movies, Box Office, Rotten Tomatoes & Reality TV */}
      {(show("movies") || show("tv")) && moviesTv && (
        <section data-section="MOVIES_TV" className="space-y-6">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">
              MOVIES, BOX OFFICE &amp; TV
            </p>
            <h2 className="text-xl font-semibold text-text-primary mt-0.5">
              Rotten Tomatoes, box office &amp; awards
            </h2>
          </div>

          {/* Rotten Tomatoes */}
          {((moviesTv.rt_groups?.length ?? 0) > 0 ||
            (moviesTv.rt_markets?.length ?? 0) > 0) && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {moviesTv.rt_groups?.map((g) =>
                renderThresholdGroup(g, "ROTTEN TOMATOES", "ladder")
              )}
              {moviesTv.rt_markets?.map((row) =>
                renderEntMarketByShape(row, "ROTTEN TOMATOES")
              )}
            </div>
          )}

          {/* Box Office */}
          {((moviesTv.box_office_groups?.length ?? 0) > 0 ||
            (moviesTv.box_office?.length ?? 0) > 0) && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {moviesTv.box_office_groups?.map((g) =>
                renderThresholdGroup(g, "BOX OFFICE", "buckets")
              )}
              {moviesTv.box_office?.map((row) =>
                renderEntMarketByShape(row, "BOX OFFICE")
              )}
            </div>
          )}

          {/* Reality TV & Awards */}
          {((moviesTv.reality_tv?.length ?? 0) > 0 ||
            (moviesTv.side_markets?.length ?? 0) > 0) && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {moviesTv.reality_tv?.map((row) =>
                renderEntMarketByShape(row, "TV & AWARDS")
              )}
              {moviesTv.side_markets?.map((row) =>
                renderEntMarketByShape(row, "MOVIES & TV")
              )}
            </div>
          )}
        </section>
      )}

      {/* Cultural Moments & Tech/Culture */}
      {(show("internet") || filter === "all") &&
        ((data.cultural_moments?.length ?? 0) > 0 ||
          (techCulture?.markets?.length ?? 0) > 0) && (
          <section data-section="CULTURE" className="space-y-4">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">
                CULTURE &amp; TECH
              </p>
              <h2 className="text-xl font-semibold text-text-primary mt-0.5">
                Cultural moments
              </h2>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
              {data.cultural_moments?.map((row) =>
                renderEntMarketByShape(row, "CULTURAL MOMENT")
              )}
              {techCulture?.markets?.map((row) =>
                renderEntMarketByShape(row, "TECH & CULTURE")
              )}
            </div>
          </section>
        )}
    </div>
  );
}
