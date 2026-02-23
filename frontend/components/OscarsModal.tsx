"use client";

import { useEffect } from "react";
import Image from "next/image";
import Link from "next/link";
import type { OscarsCategory } from "@/lib/types";
import type { FuturesOutcomeHistory } from "@/lib/types";
import { FuturesChart } from "@/components/FuturesChart";
import { CATEGORY_EMOJI } from "@/lib/oscarsData";

interface NomineeImage {
  url: string;
  type: "poster" | "headshot";
  tmdbId: number;
}

interface OscarsModalProps {
  isOpen: boolean;
  onClose: () => void;
  category: OscarsCategory;
  images: Record<string, NomineeImage>;
  historyData?: FuturesOutcomeHistory[];
  llmPreview?: string;
}

export default function OscarsModal({
  isOpen,
  onClose,
  category,
  images,
  historyData,
  llmPreview,
}: OscarsModalProps) {
  // Lock body scroll when open
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = "hidden";
      return () => {
        document.body.style.overflow = "";
      };
    }
  }, [isOpen]);

  // Close on Escape
  useEffect(() => {
    if (!isOpen) return;
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const emoji = CATEGORY_EMOJI[category.key] || "";

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/60 z-[90] animate-fade-in"
        onClick={onClose}
      />

      {/* Panel */}
      <div className="fixed inset-x-4 top-8 bottom-8 z-[100] flex items-start justify-center pointer-events-none">
        <div
          className="pointer-events-auto w-full max-w-2xl max-h-full overflow-y-auto rounded-2xl bg-surface-card border border-[#D4AF37]/30 shadow-2xl animate-modal-in"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Sticky header */}
          <div className="sticky top-0 z-10 bg-surface-card/90 backdrop-blur-sm border-b border-surface-border px-5 py-4 flex items-center gap-3">
            <span className="text-xl">{emoji}</span>
            <h2 className="text-lg font-bold text-text-primary flex-1">
              {category.name}
            </h2>
            <span className="text-xs text-text-muted mr-2">
              #{category.ceremony_order}
            </span>
            <button
              onClick={onClose}
              className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-surface-elevated transition-colors text-text-secondary"
            >
              <svg
                className="w-5 h-5"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </button>
          </div>

          {/* Content */}
          <div className="px-5 py-4 space-y-5">
            {/* LLM narrative */}
            {llmPreview && (
              <p className="text-sm text-text-secondary italic leading-relaxed border-l-2 border-[#D4AF37]/40 pl-3">
                {llmPreview}
              </p>
            )}

            {/* Chart */}
            {historyData && historyData.length > 0 && (
              <FuturesChart
                historyData={historyData}
                goldTheme
                height={150}
              />
            )}

            {/* All nominees */}
            <div className="space-y-2">
              {category.nominees.map((nominee) => {
                const cacheKey = `${category.key}_${nominee.name}`;
                const img = images[cacheKey];
                const pct = Math.round(nominee.probability * 100);
                const isLeader = nominee.rank === 1;

                return (
                  <div
                    key={nominee.name}
                    className={`flex items-center gap-3 p-3 rounded-lg ${
                      isLeader
                        ? "bg-[#D4AF37]/5 border border-[#D4AF37]/20"
                        : "bg-surface-elevated/50"
                    }`}
                  >
                    {/* Image / initial */}
                    <div className="w-10 h-10 rounded-full overflow-hidden bg-surface-elevated flex-shrink-0 flex items-center justify-center">
                      {img ? (
                        <Image
                          src={img.url}
                          alt={nominee.name}
                          width={40}
                          height={40}
                          className="object-cover w-full h-full"
                          unoptimized
                        />
                      ) : (
                        <span className="text-sm text-text-muted font-bold">
                          {nominee.name.charAt(0)}
                        </span>
                      )}
                    </div>

                    {/* Name + bar */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between gap-2 mb-0.5">
                        <span
                          className={`text-sm truncate ${
                            isLeader
                              ? "text-text-primary font-semibold"
                              : "text-text-secondary"
                          }`}
                        >
                          {nominee.rank}. {nominee.name}
                          {nominee.is_winner && (
                            <span className="ml-1 text-green-500 text-xs">
                              Winner
                            </span>
                          )}
                        </span>
                        <span className="text-sm font-mono font-bold text-text-primary flex-shrink-0">
                          {pct}%
                        </span>
                      </div>
                      <div className="h-1 bg-surface-elevated rounded-full overflow-hidden">
                        <div
                          className="h-full rounded-full transition-all duration-500"
                          style={{
                            width: `${Math.min(pct, 100)}%`,
                            backgroundColor: isLeader ? "#D4AF37" : "#475569",
                          }}
                        />
                      </div>
                    </div>

                    {/* Movement */}
                    {nominee.movement_24h !== null &&
                      Math.abs(nominee.movement_24h) >= 0.005 && (
                        <span
                          className={`text-xs font-mono flex-shrink-0 ${
                            nominee.movement_24h > 0
                              ? "text-green-500"
                              : "text-red-400"
                          }`}
                        >
                          {nominee.movement_24h > 0 ? "+" : ""}
                          {Math.round(nominee.movement_24h * 100)}%
                        </span>
                      )}
                  </div>
                );
              })}
            </div>

            {/* Source breakdown for leader */}
            {category.nominees[0] && (
              <div className="text-xs text-text-muted flex items-center gap-2">
                <span>Sources:</span>
                {Object.entries(category.nominees[0].sources).map(
                  ([src, prob]) => (
                    <span key={src} className="uppercase">
                      {src === "polymarket"
                        ? "PM"
                        : src === "kalshi"
                          ? "KL"
                          : src.slice(0, 2).toUpperCase()}{" "}
                      {Math.round(prob * 100)}%
                    </span>
                  )
                )}
              </div>
            )}

            {/* Opening odds comparison */}
            {category.nominees[0]?.opening_probability != null && (
              <div className="text-xs text-text-muted">
                Frontrunner opened at{" "}
                {Math.round(category.nominees[0].opening_probability * 100)}%,
                now at{" "}
                {Math.round(category.nominees[0].probability * 100)}%
              </div>
            )}

            {/* Full market link */}
            {category.market_ids[0] && (
              <div className="pt-2 border-t border-surface-border">
                <Link
                  href={`/futures/${category.market_ids[0]}`}
                  className="text-sm text-[#D4AF37] hover:text-[#B8860B] transition-colors"
                  onClick={onClose}
                >
                  Full market details &rarr;
                </Link>
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
