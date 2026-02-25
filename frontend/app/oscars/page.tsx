"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { fetchOscarsData, fetchFuturesHistory } from "@/lib/api";
import type {
  OscarsResponse,
  OscarsCategory,
  OscarsNominee,
  OscarsFilmData,
  OscarsBiggestMover,
  FuturesOutcomeHistory,
} from "@/lib/types";
import {
  MAJOR_CATEGORIES,
  PERSON_CATEGORIES,
  CATEGORY_EMOJI,
  CATEGORY_DESCRIPTIONS,
  CEREMONY_ORDER,
} from "@/lib/oscarsData";
import {
  searchMovie,
  searchPerson,
  getTrailers,
  posterUrl,
  headshotUrl,
} from "@/lib/tmdb";
import { FuturesChart } from "@/components/FuturesChart";
import OscarsModal from "@/components/OscarsModal";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";

// ============================================================================
// Types
// ============================================================================

interface NomineeImage {
  url: string;
  type: "poster" | "headshot";
  tmdbId: number;
}

interface NomineeTrailer {
  youtubeKey: string;
}

// ============================================================================
// Main Page
// ============================================================================

export default function OscarsPage() {
  usePageTracking({ pageType: 'oscars', pageTitle: '98th Academy Awards Odds' });
  useScrollDepth({ pageType: 'oscars' });
  useEngagementTime({ pageType: 'oscars' });

  const [data, setData] = useState<OscarsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [images, setImages] = useState<Record<string, NomineeImage>>({});
  const [trailers, setTrailers] = useState<Record<string, NomineeTrailer>>({});
  const [modalCategory, setModalCategory] = useState<OscarsCategory | null>(
    null
  );
  const [historyByCategory, setHistoryByCategory] = useState<
    Record<string, FuturesOutcomeHistory[]>
  >({});

  // Phase 1: Fetch odds data
  useEffect(() => {
    async function load() {
      try {
        setLoading(true);
        const result = await fetchOscarsData();
        setData(result);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to load Oscars data"
        );
      } finally {
        setLoading(false);
      }
    }
    load();

    // If ceremony_status is "live", poll more frequently
    const interval = setInterval(
      () => {
        fetchOscarsData()
          .then(setData)
          .catch(() => {});
      },
      data?.ceremony_status === "live" ? 30_000 : 120_000
    );
    return () => clearInterval(interval);
  }, []);

  // Phase 2: Progressive TMDB enrichment
  useEffect(() => {
    if (!data) return;

    async function enrichImages() {
      const searches: Promise<void>[] = [];

      for (const cat of data!.categories) {
        const isPerson = PERSON_CATEGORIES.has(cat.key);
        const topN = MAJOR_CATEGORIES.has(cat.key) ? cat.nominees.length : 3;

        for (const nominee of cat.nominees.slice(0, topN)) {
          const cacheKey = `${cat.key}_${nominee.name}`;

          if (isPerson) {
            searches.push(
              searchPerson(nominee.name).then((result) => {
                if (result?.profile_path) {
                  setImages((prev) => ({
                    ...prev,
                    [cacheKey]: {
                      url: headshotUrl(result.profile_path)!,
                      type: "headshot",
                      tmdbId: result.id,
                    },
                  }));
                }
              })
            );
          } else {
            const movieName = nominee.name.split(/\s+[-\u2013]\s+/)[0].trim();
            searches.push(
              searchMovie(movieName, 2025).then(async (result) => {
                if (!result) {
                  const retry = await searchMovie(movieName);
                  if (retry?.poster_path) {
                    setImages((prev) => ({
                      ...prev,
                      [cacheKey]: {
                        url: posterUrl(retry.poster_path)!,
                        type: "poster",
                        tmdbId: retry.id,
                      },
                    }));
                  }
                  return;
                }
                if (result.poster_path) {
                  setImages((prev) => ({
                    ...prev,
                    [cacheKey]: {
                      url: posterUrl(result.poster_path)!,
                      type: "poster",
                      tmdbId: result.id,
                    },
                  }));
                }
                if (cat.key === "best_picture") {
                  const vids = await getTrailers(result.id);
                  if (vids.length > 0) {
                    setTrailers((prev) => ({
                      ...prev,
                      [cacheKey]: { youtubeKey: vids[0].key },
                    }));
                  }
                }
              })
            );
          }
        }
      }

      await Promise.allSettled(searches);
    }

    enrichImages();
  }, [data]);

  // Phase 3: Fetch history data for major categories
  useEffect(() => {
    if (!data) return;

    const majorCats = data.categories.filter((c) => c.is_major);
    for (const cat of majorCats) {
      if (cat.market_ids[0] && !historyByCategory[cat.key]) {
        fetchFuturesHistory(cat.market_ids[0], 168)
          .then((h) => {
            if (h?.outcomes) {
              setHistoryByCategory((prev) => ({
                ...prev,
                [cat.key]: h.outcomes,
              }));
            }
          })
          .catch(() => {});
      }
    }
  }, [data]);

  // Derived data
  const bestPicture = data?.categories.find((c) => c.key === "best_picture");
  const majorCategories =
    data?.categories.filter((c) => c.is_major && c.key !== "best_picture") ||
    [];
  const craftCategories = data?.categories.filter((c) => !c.is_major) || [];

  // Ceremony mode helpers
  const ceremonyStatus = data?.ceremony_status ?? "pre";
  const isLive = ceremonyStatus === "live";
  const isPost = ceremonyStatus === "post";

  // Post-ceremony scorecard
  const scorecard = isPost
    ? (() => {
        let correct = 0;
        let total = 0;
        for (const cat of data?.categories ?? []) {
          const winner = cat.nominees.find((n) => n.is_winner);
          if (winner) {
            total++;
            if (winner.rank === 1) correct++;
          }
        }
        return { correct, total, accuracy: total > 0 ? Math.round((correct / total) * 100) : 0 };
      })()
    : null;

  // Frontrunner trailer for Best Picture
  const bpFrontrunner = bestPicture?.nominees[0];
  const bpTrailerKey = bpFrontrunner
    ? trailers[`best_picture_${bpFrontrunner.name}`]?.youtubeKey
    : undefined;

  return (
    <div className="min-h-screen">
      {/* Hero */}
      <div className="relative overflow-hidden bg-gradient-to-b from-[#1a1408] via-surface-deep to-surface-deep">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,_rgba(212,175,55,0.08)_0%,_transparent_70%)]" />
        <div className="relative max-w-4xl mx-auto px-4 pt-8 pb-6 text-center">
          <Link
            href="/"
            className="text-sm text-text-secondary hover:text-text-primary transition-colors mb-4 inline-block"
          >
            &larr; Back to feed
          </Link>
          <div className="text-4xl mb-3">&#x1F3C6;</div>
          <h1 className="text-3xl sm:text-4xl font-bold text-[#D4AF37] tracking-tight">
            98th Academy Awards
          </h1>
          <p className="text-text-secondary mt-2 text-lg">
            {isLive
              ? "LIVE NOW"
              : isPost
                ? "Ceremony Complete"
                : "March 2, 2026"}
          </p>

          {!isLive && !isPost && (
            <Countdown targetDate="2026-03-02T20:00:00-05:00" />
          )}

          <p className="text-xs text-text-muted mt-4">
            Odds from Polymarket &amp; Kalshi
          </p>
        </div>
      </div>

      {/* Content */}
      <div className="max-w-4xl mx-auto px-4 py-6 space-y-10">
        {loading && (
          <div className="text-center py-16 text-text-secondary">
            Loading Oscars data...
          </div>
        )}

        {error && (
          <div className="text-center py-16 text-red-400">{error}</div>
        )}

        {data && !loading && data.categories.length === 0 && (
          <div className="text-center py-16">
            <p className="text-lg text-text-secondary">
              No Oscar markets found yet.
            </p>
            <p className="text-sm text-text-muted mt-1">
              Markets typically appear on Polymarket and Kalshi a few weeks
              before the ceremony.
            </p>
          </div>
        )}

        {/* Post-ceremony scorecard */}
        {isPost && scorecard && scorecard.total > 0 && (
          <div className="bg-surface-card rounded-xl border border-[#D4AF37]/30 p-5 text-center">
            <Tooltip text="How often the market frontrunner won">
              <div className="text-3xl font-mono font-bold text-[#D4AF37]">
                {scorecard.correct}/{scorecard.total}
              </div>
            </Tooltip>
            <div className="text-sm text-text-secondary mt-1">
              predictions correct &mdash; {scorecard.accuracy}% accuracy
            </div>
          </div>
        )}

        {/* Biggest Movers Strip (Feature #4) */}
        {data && data.biggest_movers && data.biggest_movers.length > 0 && (
          <BiggestMoversStrip
            movers={data.biggest_movers}
            summary={data.llm_previews?.biggest_movers}
          />
        )}

        {/* Best Picture Spotlight (Feature #2 + #9 + #10) */}
        {bestPicture && (
          <BestPictureSection
            category={bestPicture}
            images={images}
            trailers={trailers}
            trailerKey={bpTrailerKey}
            onCategoryClick={() => setModalCategory(bestPicture)}
          />
        )}

        {/* Major Awards (Features #1, #3, #5, #6, #10) */}
        {majorCategories.length > 0 && (
          <section>
            <h2 className="text-title-2 text-text-primary mb-4">
              Major Awards
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {majorCategories.map((cat) => (
                <MajorCategoryCard
                  key={cat.key}
                  category={cat}
                  images={images}
                  historyData={historyByCategory[cat.key]}
                  llmPreview={data?.llm_previews?.[cat.key]}
                  ceremonyStatus={ceremonyStatus}
                  onClick={() => setModalCategory(cat)}
                />
              ))}
            </div>
          </section>
        )}

        {/* Film-Centric View (Feature #7) */}
        {data &&
          data.film_nominations &&
          data.film_nominations.length > 0 && (
            <FilmCentricSection
              films={data.film_nominations}
              images={images}
              isPost={isPost}
            />
          )}

        {/* Craft Awards (Feature #6 — modal trigger) */}
        {craftCategories.length > 0 && (
          <section>
            <h2 className="text-title-2 text-text-primary mb-4">
              Craft Awards
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {craftCategories.map((cat) => (
                <CraftCategoryCard
                  key={cat.key}
                  category={cat}
                  ceremonyStatus={ceremonyStatus}
                  onClick={() => setModalCategory(cat)}
                />
              ))}
            </div>
          </section>
        )}

        {/* Trivia / Beyond the Awards */}
        {data && data.trivia.length > 0 && (
          <section>
            <h2 className="text-title-2 text-text-primary mb-4">
              Beyond the Awards
            </h2>
            <div className="space-y-3">
              {data.trivia.map((market) => (
                <div
                  key={market.id}
                  className="bg-surface-card rounded-xl border border-surface-border p-4"
                >
                  <h3 className="text-body-strong text-text-primary mb-3">
                    {market.name}
                  </h3>
                  <div className="space-y-2">
                    {market.top_outcomes.map(
                      (
                        outcome: {
                          name: string;
                          probability: number | null;
                        },
                        idx: number
                      ) => (
                        <div
                          key={idx}
                          className="flex items-center justify-between gap-3"
                        >
                          <span className="text-sm text-text-secondary truncate">
                            {outcome.name}
                          </span>
                          <span className="text-sm font-mono font-bold text-text-primary flex-shrink-0">
                            {outcome.probability
                              ? `${Math.round(outcome.probability * 100)}%`
                              : "-"}
                          </span>
                        </div>
                      )
                    )}
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Footer attribution */}
        {data && data.categories.length > 0 && (
          <div className="text-center text-xs text-text-muted pt-4 pb-8">
            Odds powered by Polymarket &amp; Kalshi &middot; Not betting advice
          </div>
        )}
      </div>

      {/* Modal (Feature #6) */}
      {modalCategory && (
        <OscarsModal
          isOpen={!!modalCategory}
          onClose={() => setModalCategory(null)}
          category={modalCategory}
          images={images}
          historyData={historyByCategory[modalCategory.key]}
          llmPreview={data?.llm_previews?.[modalCategory.key]}
        />
      )}
    </div>
  );
}

// ============================================================================
// Countdown Timer
// ============================================================================

function Countdown({ targetDate }: { targetDate: string }) {
  const [timeLeft, setTimeLeft] = useState<{
    days: number;
    hours: number;
    minutes: number;
  } | null>(null);

  useEffect(() => {
    const target = new Date(targetDate).getTime();

    function update() {
      const now = Date.now();
      const diff = target - now;
      if (diff <= 0) {
        setTimeLeft(null);
        return;
      }
      setTimeLeft({
        days: Math.floor(diff / (1000 * 60 * 60 * 24)),
        hours: Math.floor((diff / (1000 * 60 * 60)) % 24),
        minutes: Math.floor((diff / (1000 * 60)) % 60),
      });
    }

    update();
    const interval = setInterval(update, 60_000);
    return () => clearInterval(interval);
  }, [targetDate]);

  if (!timeLeft) return null;

  return (
    <div className="flex items-center justify-center gap-4 mt-4">
      {[
        { value: timeLeft.days, label: "days" },
        { value: timeLeft.hours, label: "hrs" },
        { value: timeLeft.minutes, label: "min" },
      ].map(({ value, label }) => (
        <div key={label} className="text-center">
          <div className="text-2xl sm:text-3xl font-mono font-bold text-[#D4AF37]">
            {String(value).padStart(2, "0")}
          </div>
          <div className="text-xs text-text-muted uppercase tracking-wider">
            {label}
          </div>
        </div>
      ))}
    </div>
  );
}

// ============================================================================
// Biggest Movers Strip (Feature #4)
// ============================================================================

function BiggestMoversStrip({
  movers,
  summary,
}: {
  movers: OscarsBiggestMover[];
  summary?: string;
}) {
  return (
    <section className="bg-surface-card rounded-xl border border-surface-border p-4">
      <h3 className="text-body-strong text-text-primary mb-3 flex items-center gap-2">
        <span>&#x1F4C8;</span> Biggest Movers (24h)
      </h3>
      <div className="flex gap-3 overflow-x-auto pb-1 scrollbar-hide">
        {movers.map((mover, idx) => {
          const pctChange = Math.round(Math.abs(mover.movement_24h) * 100);
          const isUp = mover.movement_24h > 0;
          const isBig = Math.abs(mover.movement_24h) >= 0.05;
          const icon = isUp
            ? isBig
              ? "\uD83D\uDD25"
              : "\u2B06\uFE0F"
            : isBig
              ? "\u2744\uFE0F"
              : "\u2B07\uFE0F";

          return (
            <div
              key={idx}
              className="flex-shrink-0 bg-surface-elevated rounded-lg px-3 py-2 min-w-[140px]"
              title={`${mover.name} in ${mover.category_name}`}
            >
              <div className="flex items-center gap-1.5 mb-0.5">
                <Tooltip
                  text={
                    isUp
                      ? isBig
                        ? "Surging in odds"
                        : "Rising in odds"
                      : isBig
                        ? "Fading fast"
                        : "Slipping in odds"
                  }
                >
                  <span className="text-sm">{icon}</span>
                </Tooltip>
                <span
                  className={`text-sm font-mono font-bold ${
                    isUp ? "text-green-500" : "text-red-400"
                  }`}
                >
                  {isUp ? "+" : "-"}
                  {pctChange}%
                </span>
              </div>
              <div className="text-xs text-text-primary truncate font-medium">
                {mover.name}
              </div>
              <div className="text-micro text-text-muted truncate">
                {mover.category_name}
              </div>
            </div>
          );
        })}
      </div>
      {summary && (
        <p className="text-xs text-text-secondary italic mt-2">{summary}</p>
      )}
    </section>
  );
}

// ============================================================================
// Best Picture Spotlight (Feature #2 poster race, #9 trailer, #10 gold shimmer)
// ============================================================================

function BestPictureSection({
  category,
  images,
  trailers,
  trailerKey,
  onCategoryClick,
}: {
  category: OscarsCategory;
  images: Record<string, NomineeImage>;
  trailers: Record<string, NomineeTrailer>;
  trailerKey?: string;
  onCategoryClick: () => void;
}) {
  return (
    <section>
      <div className="flex items-center gap-2 mb-4">
        <h2 className="text-title-2 text-[#D4AF37]">Best Picture</h2>
        <button
          onClick={onCategoryClick}
          className="text-xs text-text-muted hover:text-text-secondary transition-colors ml-auto"
        >
          Deep dive &rarr;
        </button>
      </div>

      {/* Trailer embed (Feature #9) */}
      {trailerKey && (
        <div className="mb-4 rounded-xl overflow-hidden aspect-video max-w-xl mx-auto border border-[#D4AF37]/20">
          <iframe
            src={`https://www.youtube.com/embed/${trailerKey}?autoplay=0&rel=0`}
            className="w-full h-full"
            allowFullScreen
            title="Frontrunner trailer"
          />
        </div>
      )}

      {/* Poster race — pyramid on desktop, scroll on mobile (Feature #2) */}
      <div className="flex gap-3 overflow-x-auto pb-2 -mx-4 px-4 md:mx-0 md:px-0 md:flex-wrap md:justify-center md:items-end">
        {category.nominees.map((nominee) => {
          const cacheKey = `best_picture_${nominee.name}`;
          const img = images[cacheKey];
          const trailer = trailers[cacheKey];
          const pct = Math.round(nominee.probability * 100);
          const isFrontrunner = nominee.rank === 1;
          const isTop3 = nominee.rank <= 3;

          // Pyramid sizing
          const widthClass = isFrontrunner
            ? "w-[160px] md:w-[180px]"
            : isTop3
              ? "w-[130px] md:w-[150px]"
              : "w-[110px] md:w-[120px]";

          return (
            <div
              key={nominee.name}
              className={`flex-shrink-0 ${widthClass} group ${
                !isFrontrunner && !isTop3 ? "md:opacity-85" : ""
              } ${isTop3 && !isFrontrunner ? "md:opacity-95" : ""}`}
            >
              {/* Poster */}
              <div
                className={`relative aspect-[2/3] rounded-lg overflow-hidden bg-surface-elevated transition-all duration-200 group-hover:scale-[1.03] ${
                  isFrontrunner
                    ? "border-2 border-[#D4AF37] shadow-lg shadow-[#D4AF37]/10"
                    : "border border-surface-border group-hover:border-[#D4AF37]/50"
                }`}
              >
                {img ? (
                  <Image
                    src={img.url}
                    alt={nominee.name}
                    fill
                    className="object-cover transition-opacity duration-500"
                    sizes="180px"
                    unoptimized
                  />
                ) : (
                  <div className="absolute inset-0 flex items-center justify-center text-text-muted">
                    <span className="text-3xl">&#x1F3AC;</span>
                  </div>
                )}

                {/* Gold shimmer on frontrunner (Feature #10) */}
                {isFrontrunner && (
                  <div className="gold-shimmer absolute inset-0 pointer-events-none rounded-lg" />
                )}

                {/* Rank badge */}
                {nominee.rank <= 3 && (
                  <div
                    className="absolute top-1.5 left-1.5 bg-black/70 backdrop-blur-sm text-[#D4AF37] text-xs font-bold px-1.5 py-0.5 rounded"
                    title={
                      nominee.rank === 1
                        ? "Frontrunner"
                        : nominee.rank === 2
                          ? "Runner-up"
                          : "Top 3 contender"
                    }
                  >
                    #{nominee.rank}
                  </div>
                )}

                {/* Winner badge (ceremony mode) */}
                {nominee.is_winner && (
                  <div
                    className="absolute top-1.5 right-1.5 bg-green-600/90 text-white text-xs font-bold px-1.5 py-0.5 rounded"
                    title="Academy Award winner"
                  >
                    WINNER
                  </div>
                )}

                {/* Trailer button */}
                {trailer && (
                  <a
                    href={`https://www.youtube.com/watch?v=${trailer.youtubeKey}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="absolute bottom-1.5 right-1.5 bg-black/70 backdrop-blur-sm text-white text-xs px-2 py-1 rounded hover:bg-black/90 transition-colors"
                    onClick={(e) => e.stopPropagation()}
                  >
                    &#x25B6; Trailer
                  </a>
                )}
              </div>

              {/* Probability */}
              <div className="mt-2 text-center">
                <div className="text-prob-md font-mono text-text-primary">
                  {pct}%
                </div>
                <div className="text-xs text-text-secondary mt-0.5 line-clamp-2 leading-tight">
                  {nominee.name}
                </div>
                <MovementBadge movement={nominee.movement_24h} />
                <SourceDisplay sources={nominee.sources} />
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

// ============================================================================
// Major Category Card (Features #1, #3, #5, #10)
// ============================================================================

function ordinal(n: number): string {
  const s = ["th", "st", "nd", "rd"];
  const v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
}

function MajorCategoryCard({
  category,
  images,
  historyData,
  llmPreview,
  ceremonyStatus,
  onClick,
}: {
  category: OscarsCategory;
  images: Record<string, NomineeImage>;
  historyData?: FuturesOutcomeHistory[];
  llmPreview?: string;
  ceremonyStatus: string;
  onClick: () => void;
}) {
  const emoji = CATEGORY_EMOJI[category.key] || "";
  const top2 = category.nominees.slice(0, 2);
  const isH2H =
    top2.length === 2 &&
    Math.abs(top2[0].probability - top2[1].probability) <= 0.1;

  // Ceremony mode: check if this category has a winner
  const winner = category.nominees.find((n) => n.is_winner);
  const hasWinner = !!winner;
  const frontrunnerPredicted = hasWinner && winner.rank === 1;

  return (
    <div
      onClick={onClick}
      className={`group bg-surface-card rounded-xl border border-l-4 p-4 hover:shadow-card-hover hover:border-[#D4AF37]/30 transition-all cursor-pointer h-full ${
        hasWinner
          ? "border-green-500/40 border-l-green-500"
          : "border-surface-border border-l-[#D4AF37]"
      }`}
    >
      <div className="flex items-center gap-2 mb-2">
        <span className="text-lg">{emoji}</span>
        <h3 className="text-body-strong text-text-primary">{category.name}</h3>
        {hasWinner && (
          <Tooltip
            text={
              frontrunnerPredicted
                ? "Markets correctly predicted the winner"
                : "Winner was not the market frontrunner"
            }
            align="right"
          >
            <span
              className={`text-xs px-1.5 py-0.5 rounded font-medium ml-auto ${
                frontrunnerPredicted
                  ? "bg-green-500/15 text-green-400"
                  : "bg-red-500/15 text-red-400"
              }`}
            >
              {frontrunnerPredicted ? "Predicted" : "Upset!"}
            </span>
          </Tooltip>
        )}
        {!hasWinner && (
          <Tooltip
            text={`Presented ${ordinal(category.ceremony_order)} during the ceremony`}
            align="right"
          >
            <span className="text-xs text-text-muted ml-auto cursor-default">
              #{category.ceremony_order}
            </span>
          </Tooltip>
        )}
      </div>

      {/* LLM preview (Phase 7) */}
      {llmPreview && (
        <p className="text-xs text-text-secondary italic mb-2 line-clamp-2">
          {llmPreview}
        </p>
      )}

      {/* Head-to-Head when top 2 are within 10% (Feature #5) */}
      {isH2H && !hasWinner && (
        <HeadToHead
          nominee1={top2[0]}
          nominee2={top2[1]}
          categoryKey={category.key}
          images={images}
        />
      )}

      {/* Nominee list */}
      <div className="space-y-2.5">
        {category.nominees.slice(0, 5).map((nominee) => {
          const cacheKey = `${category.key}_${nominee.name}`;
          const img = images[cacheKey];
          const pct = Math.round(nominee.probability * 100);
          const isLeader = nominee.rank === 1;
          const isWinner = nominee.is_winner;

          return (
            <div
              key={nominee.name}
              className={`flex items-center gap-3 relative ${
                isWinner ? "bg-green-500/5 rounded-lg px-1 -mx-1" : ""
              }`}
            >
              {/* Gold shimmer on frontrunner (Feature #10) */}
              {isLeader && !hasWinner && (
                <div className="gold-shimmer absolute inset-0 pointer-events-none rounded-lg" />
              )}

              {/* Headshot / initial */}
              <div className="w-8 h-8 rounded-full overflow-hidden bg-surface-elevated flex-shrink-0 flex items-center justify-center relative z-[1]">
                {img ? (
                  <Image
                    src={img.url}
                    alt={nominee.name}
                    width={32}
                    height={32}
                    className="object-cover w-full h-full"
                    unoptimized
                  />
                ) : (
                  <span className="text-xs text-text-muted font-bold">
                    {nominee.name.charAt(0)}
                  </span>
                )}
              </div>

              {/* Name + bar */}
              <div className="flex-1 min-w-0 relative z-[1]">
                <div className="flex items-center justify-between gap-2 mb-0.5">
                  <span
                    className={`text-sm truncate ${
                      isLeader || isWinner
                        ? "text-text-primary font-semibold"
                        : "text-text-secondary"
                    }`}
                  >
                    {nominee.name}
                    {isWinner && (
                      <span className="ml-1 text-green-500 text-xs">
                        &#x2713;
                      </span>
                    )}
                  </span>
                  <span className="text-sm font-mono font-bold text-text-primary flex-shrink-0">
                    {pct}%
                  </span>
                </div>
                <div className="h-1.5 bg-surface-elevated rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all duration-500"
                    style={{
                      width: `${Math.min(pct, 100)}%`,
                      background: isWinner
                        ? "linear-gradient(90deg, #16a34a, #22c55e)"
                        : isLeader
                          ? "linear-gradient(90deg, #B8860B, #D4AF37, #FFD700)"
                          : "#475569",
                    }}
                  />
                </div>
              </div>

              <div className="relative z-[1]">
                <MovementBadge movement={nominee.movement_24h} />
              </div>
            </div>
          );
        })}
      </div>

      {/* Source badges + disagreement callout (Feature #3) */}
      {category.nominees[0] && (
        <div className="mt-3 pt-2 border-t border-surface-border">
          <SourceDisplay sources={category.nominees[0].sources} />
        </div>
      )}

      {/* Inline trend chart (Feature #1) */}
      {historyData && historyData.length > 0 && (
        <div className="mt-3">
          <div className="text-[10px] text-text-muted mb-1 uppercase tracking-wider">
            7-day odds trend
          </div>
          <FuturesChart historyData={historyData} mini goldTheme height={80} />
        </div>
      )}

      {/* Tap for details hint */}
      <div className="mt-2 text-[10px] text-text-muted text-center opacity-0 group-hover:opacity-60 transition-opacity">
        Click for full breakdown
      </div>
    </div>
  );
}

// ============================================================================
// Head-to-Head Matchup (Feature #5)
// ============================================================================

function HeadToHead({
  nominee1,
  nominee2,
  categoryKey,
  images,
}: {
  nominee1: OscarsNominee;
  nominee2: OscarsNominee;
  categoryKey: string;
  images: Record<string, NomineeImage>;
}) {
  const img1 = images[`${categoryKey}_${nominee1.name}`];
  const img2 = images[`${categoryKey}_${nominee2.name}`];
  const pct1 = Math.round(nominee1.probability * 100);
  const pct2 = Math.round(nominee2.probability * 100);

  return (
    <div className="flex items-center gap-2 mb-3 bg-surface-elevated/50 rounded-lg p-2.5">
      {/* Left side */}
      <div className="flex-1 text-center">
        <div className="w-10 h-10 rounded-full overflow-hidden bg-surface-elevated mx-auto mb-1 flex items-center justify-center">
          {img1 ? (
            <Image
              src={img1.url}
              alt={nominee1.name}
              width={40}
              height={40}
              className="object-cover w-full h-full"
              unoptimized
            />
          ) : (
            <span className="text-sm font-bold text-text-muted">
              {nominee1.name.charAt(0)}
            </span>
          )}
        </div>
        <div className="text-lg font-mono font-bold text-[#D4AF37]">
          {pct1}%
        </div>
        <div className="text-xs text-text-secondary truncate">
          {nominee1.name}
        </div>
      </div>

      {/* VS divider */}
      <Tooltip text={`Only ${Math.abs(pct1 - pct2)}% apart \u2014 a tight race`}>
        <div className="flex-shrink-0 text-xs font-bold text-[#D4AF37]/60 uppercase">
          vs
        </div>
      </Tooltip>

      {/* Right side */}
      <div className="flex-1 text-center">
        <div className="w-10 h-10 rounded-full overflow-hidden bg-surface-elevated mx-auto mb-1 flex items-center justify-center">
          {img2 ? (
            <Image
              src={img2.url}
              alt={nominee2.name}
              width={40}
              height={40}
              className="object-cover w-full h-full"
              unoptimized
            />
          ) : (
            <span className="text-sm font-bold text-text-muted">
              {nominee2.name.charAt(0)}
            </span>
          )}
        </div>
        <div className="text-lg font-mono font-bold text-text-primary">
          {pct2}%
        </div>
        <div className="text-xs text-text-secondary truncate">
          {nominee2.name}
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// Film-Centric Cross-Category View (Feature #7)
// ============================================================================

function FilmCentricSection({
  films,
  images,
  isPost,
}: {
  films: OscarsFilmData[];
  images: Record<string, NomineeImage>;
  isPost: boolean;
}) {
  return (
    <section>
      <h2 className="text-title-2 text-text-primary mb-1">By Film</h2>
      <p className="text-sm text-text-secondary mb-4">
        How many Oscars could each film win?
      </p>
      <div className="space-y-3">
        {films.slice(0, 10).map((film) => {
          const posterKey = `best_picture_${film.film_name}`;
          const img = images[posterKey];

          return (
            <div
              key={film.film_name}
              className="bg-surface-card rounded-xl border border-surface-border hover:border-[#D4AF37]/30 p-3 flex gap-3 transition-colors"
            >
              {/* Small poster */}
              <div className="w-12 h-16 rounded overflow-hidden bg-surface-elevated flex-shrink-0">
                {img ? (
                  <Image
                    src={img.url}
                    alt={film.film_name}
                    width={48}
                    height={64}
                    className="object-cover w-full h-full"
                    unoptimized
                  />
                ) : (
                  <div className="w-full h-full flex items-center justify-center text-text-muted text-lg">
                    &#x1F3AC;
                  </div>
                )}
              </div>

              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between gap-2 mb-1.5">
                  <h3 className="text-sm font-semibold text-text-primary truncate">
                    {film.film_name}
                  </h3>
                  <div className="text-right flex-shrink-0">
                    <Tooltip
                      text="Sum of win probabilities across all nominations"
                      align="right"
                    >
                      <div className="text-sm font-mono font-bold text-[#D4AF37]">
                        {film.expected_wins.toFixed(1)}
                      </div>
                    </Tooltip>
                    <div className="text-micro text-text-muted">
                      {isPost ? "actual" : "expected"} wins
                    </div>
                  </div>
                </div>

                {/* Category chips */}
                <div className="flex flex-wrap gap-1.5">
                  {film.nominations.map((nom) => {
                    const catEmoji = CATEGORY_EMOJI[nom.category_key] || "";
                    const pct = Math.round(nom.probability * 100);
                    const isLeader = nom.rank === 1;
                    // Short label: "Picture", "Director", "Editing", etc.
                    const shortLabel = nom.category_name
                      .replace(/^Best\s+/i, "")
                      .replace(/^Achievement in\s+/i, "")
                      .replace(/\s+Film$/, "")
                      .replace(/Motion Picture.*/, "Picture")
                      .replace(/Performance by an?\s+/i, "")
                      .replace(/Actor in a Leading Role/, "Actor")
                      .replace(/Actress in a Leading Role/, "Actress")
                      .replace(/Actor in a Supporting Role/, "Supp. Actor")
                      .replace(/Actress in a Supporting Role/, "Supp. Actress")
                      .replace(/Original Screenplay/, "Orig. Screenplay")
                      .replace(/Adapted Screenplay/, "Adpt. Screenplay")
                      .replace(/International Feature/, "Int'l Feature")
                      .replace(/Animated Feature/, "Animated")
                      .replace(/Documentary Feature/, "Documentary")
                      .replace(/Documentary Short/, "Doc. Short")
                      .replace(/Animated Short/, "Anim. Short")
                      .replace(/Live Action Short/, "Live Short")
                      .replace(/Production Design/, "Prod. Design")
                      .replace(/Makeup and Hairstyling/, "Makeup")
                      .replace(/Visual Effects/, "VFX")
                      .replace(/Film Editing/, "Editing")
                      .replace(/Costume Design/, "Costumes")
                      .replace(/Original Score/, "Score")
                      .replace(/Original Song/, "Song");

                    return (
                      <Tooltip
                        key={nom.category_key}
                        text={`${nom.category_name}: ${pct}% to win${isLeader ? " (frontrunner)" : ""}`}
                        position="bottom"
                      >
                        <span
                          className={`inline-flex items-center gap-1 text-micro px-2 py-0.5 rounded cursor-default ${
                            isLeader
                              ? "bg-[#D4AF37]/15 text-[#D4AF37] font-medium"
                              : "bg-surface-elevated text-text-secondary"
                          }`}
                        >
                          <span>{catEmoji}</span>
                          <span className="truncate max-w-[80px]">
                            {shortLabel}
                          </span>
                          <span className="font-mono font-bold">{pct}%</span>
                        </span>
                      </Tooltip>
                    );
                  })}
                </div>

                <div className="text-micro text-text-muted mt-1">
                  {film.total_nominations} nomination
                  {film.total_nominations !== 1 ? "s" : ""}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

// ============================================================================
// Craft Category Card (Feature #6 — modal trigger)
// ============================================================================

function CraftCategoryCard({
  category,
  ceremonyStatus,
  onClick,
}: {
  category: OscarsCategory;
  ceremonyStatus: string;
  onClick: () => void;
}) {
  const emoji = CATEGORY_EMOJI[category.key] || "";
  const winner = category.nominees.find((n) => n.is_winner);
  const hasWinner = !!winner;

  return (
    <div
      onClick={onClick}
      className={`bg-surface-card rounded-xl border p-3 hover:shadow-card-hover hover:border-[#D4AF37]/30 transition-all cursor-pointer h-full ${
        hasWinner
          ? "border-green-500/30"
          : "border-surface-border"
      }`}
    >
      <div className="flex items-center gap-2 mb-2">
        <Tooltip text={CATEGORY_DESCRIPTIONS[category.key] || category.name}>
          <span>{emoji}</span>
        </Tooltip>
        <h3 className="text-caption-strong text-text-primary">
          {category.name}
        </h3>
        {hasWinner ? (
          <Tooltip text="Academy Award winner announced" align="right">
            <span className="text-micro text-green-400 ml-auto">&#x2713;</span>
          </Tooltip>
        ) : (
          <Tooltip
            text={`Presented ${ordinal(category.ceremony_order)} during the ceremony`}
            align="right"
          >
            <span className="text-micro text-text-muted ml-auto cursor-default">
              #{category.ceremony_order}
            </span>
          </Tooltip>
        )}
      </div>

      <div className="space-y-1.5">
        {category.nominees.slice(0, 5).map((nominee) => {
          const pct = Math.round(nominee.probability * 100);
          const isLeader = nominee.rank === 1;
          const isWinner = nominee.is_winner;

          return (
            <div
              key={nominee.name}
              className="flex items-center gap-2"
              title={`${nominee.name}: ${pct}% chance to win`}
            >
              <span
                className={`text-xs truncate flex-1 ${
                  isLeader || isWinner
                    ? "text-text-primary font-medium"
                    : "text-text-secondary"
                }`}
              >
                {nominee.name}
                {isWinner && (
                  <span className="ml-1 text-green-500">&#x2713;</span>
                )}
              </span>

              {/* Mini bar */}
              <div className="w-16 h-1.5 bg-surface-elevated rounded-full overflow-hidden flex-shrink-0">
                <div
                  className="h-full rounded-full"
                  style={{
                    width: `${Math.min(pct, 100)}%`,
                    background: isWinner
                      ? "linear-gradient(90deg, #16a34a, #22c55e)"
                      : isLeader
                        ? "linear-gradient(90deg, #B8860B, #D4AF37)"
                        : "#475569",
                  }}
                />
              </div>

              <span className="text-xs font-mono font-bold text-text-primary w-8 text-right flex-shrink-0">
                {pct}%
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ============================================================================
// Shared Components
// ============================================================================

function Tooltip({
  text,
  children,
  position = "top",
  align = "center",
}: {
  text: string;
  children: React.ReactNode;
  position?: "top" | "bottom";
  align?: "center" | "left" | "right";
}) {
  const alignClass =
    align === "left"
      ? "left-0"
      : align === "right"
        ? "right-0"
        : "left-1/2 -translate-x-1/2";

  return (
    <span className="group/tip relative inline-flex items-center">
      {children}
      <span
        className={`pointer-events-none absolute ${alignClass} px-2 py-1 rounded-md bg-surface-deep border border-surface-border shadow-lg text-[11px] text-text-primary whitespace-nowrap opacity-0 group-hover/tip:opacity-100 transition-opacity duration-150 z-50 leading-tight ${
          position === "top" ? "bottom-full mb-2" : "top-full mt-2"
        }`}
      >
        {text}
      </span>
    </span>
  );
}

function MovementBadge({ movement }: { movement: number | null }) {
  if (!movement || Math.abs(movement) < 0.005) return null;

  const isUp = movement > 0;
  const pct = Math.abs(Math.round(movement * 100));
  const isBig = Math.abs(movement) >= 0.05;
  const icon = isUp
    ? isBig
      ? "\uD83D\uDD25"
      : ""
    : isBig
      ? "\u2744\uFE0F"
      : "";

  return (
    <Tooltip
      text={`${isUp ? "Up" : "Down"} ${pct}% in the last 24 hours`}
    >
      <span
        className={`text-micro font-mono ${
          isUp ? "text-green-500" : "text-red-400"
        }`}
      >
        {icon}
        {isUp ? "+" : "-"}
        {pct}%
      </span>
    </Tooltip>
  );
}

function SourceDisplay({ sources }: { sources: Record<string, number> }) {
  const sourceNames = Object.keys(sources);
  if (sourceNames.length === 0) return null;

  const SOURCE_FULL_NAMES: Record<string, string> = {
    polymarket: "Polymarket",
    kalshi: "Kalshi",
  };

  // Source disagreement callout (Feature #3)
  const pm = sources["polymarket"];
  const kl = sources["kalshi"];
  if (
    pm !== undefined &&
    kl !== undefined &&
    Math.abs(pm - kl) > 0.05
  ) {
    return (
      <Tooltip text="Polymarket and Kalshi disagree by more than 5%">
        <span className="text-xs text-amber-400">
          &#x26A0;&#xFE0F; Markets split: PM {Math.round(pm * 100)}% vs KL{" "}
          {Math.round(kl * 100)}%
        </span>
      </Tooltip>
    );
  }

  // Normal source dots with tooltips
  return (
    <div className="flex items-center gap-1.5 mt-1">
      {sourceNames.map((src) => (
        <Tooltip
          key={src}
          text={`${SOURCE_FULL_NAMES[src] || src}: ${Math.round(sources[src] * 100)}%`}
        >
          <span className="text-micro-xs text-text-muted uppercase cursor-default">
            {src === "polymarket"
              ? "PM"
              : src === "kalshi"
                ? "KL"
                : src.toUpperCase().slice(0, 2)}
          </span>
        </Tooltip>
      ))}
    </div>
  );
}
