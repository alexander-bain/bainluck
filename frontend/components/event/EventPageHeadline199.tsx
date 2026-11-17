"use client";

import React, { useEffect, useRef } from "react";
import {
  TournamentPlayerFace,
  servedParticipantImage,
} from "@/components/event/TournamentExtensions";
import { PinIcon } from "@/components/PinButton";
import SlashBreakableName from "@/components/SlashBreakableName";
import TeamNameLink from "@/components/TeamNameLink";
import {
  headlineDisplayAttributes,
  type HeadlineDisplayIdentity,
} from "@/lib/displayIdentity";
import {
  HEADLINE_STYLE_199,
  type HeadlineColumnRole199,
  type HeadlineCompetitorRow199,
  type HeadlineModel199,
} from "@/lib/headlineModel199";
import { espnTeamLogoByName } from "@/lib/images";
import { resolveLiveSummarySideInk } from "@/components/EventCard183A";
import { shippableCrestBadge } from "@/lib/teamShortName";
import type { EventDetailResponse, TeamData } from "@/lib/types";

const CUE_MS = 320;

function heroCrestImage199(
  teamData: TeamData | undefined,
  teamName: string,
  sportKey?: string | null,
): string | undefined {
  return (
    teamData?.logo_large ||
    espnTeamLogoByName(teamName, sportKey) ||
    teamData?.logo_small ||
    undefined
  );
}

function useHeadlineChangeCue(
  target: string,
  enabled: boolean,
): React.RefObject<HTMLDivElement> {
  const container = useRef<HTMLDivElement>(null);
  const previous = useRef<string>(target);
  const running = useRef<Animation[]>([]);

  useEffect(() => {
    const from = previous.current;
    previous.current = target;
    if (!enabled || !from || !target || from === target) return;
    if (
      typeof window !== "undefined" &&
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
    ) {
      return;
    }
    const root = container.current;
    if (!root) return;
    for (const a of running.current) a.cancel();
    running.current = [];
    root.querySelectorAll<HTMLElement>("[data-hero-digits]").forEach((el) => {
      if (typeof el.animate !== "function") return;
      running.current.push(
        el.animate([{ opacity: 0.55 }, { opacity: 1 }], {
          duration: CUE_MS,
          easing: "ease-out",
        }),
      );
    });
  }, [target, enabled]);

  useEffect(
    () => () => {
      for (const a of running.current) a.cancel();
    },
    [],
  );

  return container;
}

export function columnMinWidthPx199(
  role: HeadlineColumnRole199,
  phase: HeadlineModel199["phase"],
  colCount: number,
): number {
  switch (role) {
    case "setScore":
      if (colCount >= 7) return 19;
      if (colCount === 6) return 21;
      return 24;
    case "gamePoints":
      return colCount >= 7 ? 30 : 32;
    case "score":
      return colCount >= 5 ? 34 : 38;
    case "projected":
      return phase === "before" ? 46 : 44;
    case "pregame":
      return colCount >= 4 ? 48 : 56;
    case "finalResult":
      return 66;
    case "chance":
      return 78;
    case "now":
      if (colCount >= 7) return 58;
      if (colCount === 6) return 64;
      if (colCount === 5) return 70;
      if (colCount === 4) return 78;
      // Extra breathing room before `Now` during play (Fable note on #12771).
      return 90;
  }
}

export function pxToRem199(px: number): string {
  return `${Number((px / 16).toFixed(4))}rem`;
}

export function primaryHeadlineCellFontPx199(colCount: number): number {
  if (colCount >= 7) return 17;
  if (colCount === 6) return 18.5;
  if (colCount === 5) return 20.5;
  if (colCount === 4) return 23;
  return 26;
}

export function secondaryHeadlineCellFontPx199(colCount: number): number {
  if (colCount >= 7) return 13.5;
  return colCount >= 5 ? 15 : 17;
}

export function columnMinWidthCss199(
  role: HeadlineColumnRole199,
  phase: HeadlineModel199["phase"],
  colCount: number,
): string {
  const basePx = columnMinWidthPx199(role, phase, colCount);
  if (role === "now" || role === "chance") {
    return `max(${basePx}px, ${pxToRem199(3.45 * primaryHeadlineCellFontPx199(colCount))})`;
  }
  if (role === "finalResult") {
    return `max(${basePx}px, ${pxToRem199(3.35 * (colCount >= 5 ? 19.5 : 22))})`;
  }
  if (role === "score" || role === "projected" || role === "pregame") {
    return `max(${basePx}px, ${pxToRem199(2.25 * secondaryHeadlineCellFontPx199(colCount))})`;
  }
  return `${basePx}px`;
}

export function liveSummaryFontPx199(fullLength: number): number {
  if (fullLength <= 38) return 12;
  if (fullLength <= 46) return 11;
  return 10;
}

function useFitSingleLineSummary(basePx: number, depKey: string): React.RefObject<HTMLDivElement> {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const fit = () => {
      const target = ref.current;
      if (!target || target.clientWidth <= 0) return;
      target.style.fontSize = pxToRem199(basePx);
      let currentPx =
        (typeof window !== "undefined"
          ? parseFloat(window.getComputedStyle(target).fontSize)
          : NaN) || basePx;
      if (target.scrollWidth <= target.clientWidth + 1) return;
      while (currentPx > 7.5 && target.scrollWidth > target.clientWidth + 1) {
        currentPx = Math.max(7.5, Number((currentPx - 0.5).toFixed(1)));
        target.style.fontSize = `${currentPx}px`;
      }
    };
    fit();
    const ro = typeof ResizeObserver !== "undefined" ? new ResizeObserver(fit) : null;
    if (ro) ro.observe(el);
    window.addEventListener("resize", fit);
    return () => {
      ro?.disconnect();
      window.removeEventListener("resize", fit);
    };
  }, [basePx, depKey]);
  return ref;
}

export function sharedCompetitorNameFontPx199(
  rows: HeadlineCompetitorRow199[],
  colCount: number,
): number {
  const maxLen = rows.reduce((m, r) => Math.max(m, r.shortName.length), 0);
  if (colCount >= 5) {
    if (maxLen <= 9) return 15.5;
    if (maxLen <= 12) return 13.5;
    if (maxLen <= 16) return 12.5;
    return 11.5;
  }
  if (colCount >= 3) {
    if (maxLen <= 10) return 15.5;
    if (maxLen <= 13) return 14;
    if (maxLen <= 17) return 13;
    return 12;
  }
  if (maxLen <= 11) return 15.5;
  if (maxLen <= 15) return 14;
  if (maxLen <= 19) return 13;
  return 12;
}

export interface EventPageHeadline199Props {
  event: EventDetailResponse;
  model: HeadlineModel199;
  isPinned: boolean;
  pinDisabled: boolean;
  onPinToggle: () => void;
  animate?: boolean;
  homeProbForDataAttr?: number | null;
  settledHero?: boolean;
  settledWinnerName?: string | null;
  displayIdentity?: HeadlineDisplayIdentity | null;
  venueSettled?: boolean;
  stoppageLabel?: string | null;
  atlasMode?: boolean;
  onOpenAtlasDetails?: () => void;
  ekgControl?: React.ReactNode;
}

export default function EventPageHeadline199({
  event,
  model,
  isPinned,
  pinDisabled,
  onPinToggle,
  animate = false,
  homeProbForDataAttr,
  settledHero,
  settledWinnerName,
  displayIdentity = null,
  venueSettled = false,
  stoppageLabel = null,
  atlasMode = false,
  onOpenAtlasDetails,
  ekgControl = null,
}: EventPageHeadline199Props) {
  const colCount = model.columns.length;
  const manyCols = colCount >= 5;
  const colGapPx = colCount >= 7 ? 3 : manyCols ? 4 : 8;
  const crestSize = manyCols ? 24 : model.rows.length >= 3 ? 28 : 30;
  const nameFontPx = sharedCompetitorNameFontPx199(model.rows, colCount);

  const primarySignature = model.rows
    .map((r) => r.cells[r.cells.length - 1] ?? "")
    .join("|");
  const isSettledHero =
    settledHero !== undefined
      ? settledHero
      : event.status === "completed" || event.status === "closed";
  const homeRow = model.rows.find((r) => r.role === "home") ?? null;
  const homeProb =
    homeProbForDataAttr !== undefined
      ? homeProbForDataAttr
      : !isSettledHero
        ? (homeRow?.rawProbability ?? null)
        : null;
  const winnerRow = model.rows.find((r) => r.won === true) ?? null;
  const resolvedWinnerName =
    settledWinnerName !== undefined && settledWinnerName !== null
      ? settledWinnerName
      : winnerRow && winnerRow.role !== "draw"
        ? winnerRow.fullName
        : "";
  const cueRef = useHeadlineChangeCue(primarySignature, animate);
  const summaryBasePx = liveSummaryFontPx199(
    model.livePregameSummary?.fullText.length ?? 0,
  );
  const summaryFitRef = useFitSingleLineSummary(
    summaryBasePx,
    model.livePregameSummary?.fullText ?? "",
  );
  const nameKey = `${colCount}:${model.rows.map((r) => r.shortName).join("|")}`;
  useEffect(() => {
    const root = cueRef.current;
    if (!root) return;
    const fitNames = () => {
      const container = cueRef.current;
      if (!container) return;
      const spans = Array.from(
        container.querySelectorAll<HTMLElement>("[data-headline-name]"),
      );
      if (spans.length === 0) return;
      const hasLaidOutBox = spans.some((sp) => (sp.parentElement ?? sp).clientWidth > 0);
      if (!hasLaidOutBox) return;
      const baseRem = pxToRem199(nameFontPx);
      for (const sp of spans) sp.style.fontSize = baseRem;
      let px =
        (typeof window !== "undefined"
          ? parseFloat(window.getComputedStyle(spans[0]).fontSize)
          : NaN) || nameFontPx;
      const anyClipped = () =>
        spans.some((sp) => {
          const box = sp.parentElement ?? sp;
          return box.clientWidth > 0 && box.scrollWidth > box.clientWidth + 1;
        });
      while (px > 10.5 && anyClipped()) {
        px = Math.max(10.5, Number((px - 0.5).toFixed(1)));
        for (const sp of spans) sp.style.fontSize = `${px}px`;
      }
    };
    fitNames();
    const ro = typeof ResizeObserver !== "undefined" ? new ResizeObserver(fitNames) : null;
    if (ro) ro.observe(root);
    window.addEventListener("resize", fitNames);
    return () => {
      ro?.disconnect();
      window.removeEventListener("resize", fitNames);
    };
  }, [cueRef, nameFontPx, nameKey]);

  const rowTint = (role: HeadlineCompetitorRow199["role"]): string => {
    if (role === "away") return model.colors.away;
    if (role === "home") return model.colors.home;
    return model.colors.drawText;
  };

  const renderCrest = (row: HeadlineCompetitorRow199, tint: string) => {
    if (row.role === "draw") {
      return (
        <div
          aria-hidden="true"
          className="shrink-0 rounded-full flex items-center justify-center"
          style={{
            width: crestSize,
            height: crestSize,
            backgroundColor: "rgba(148, 163, 184, 0.14)",
          }}
        >
          <span
            className="block rounded-full"
            style={{
              width: Math.round(crestSize * 0.42),
              height: 2.2,
              backgroundColor: HEADLINE_STYLE_199.drawTextInk,
            }}
          />
        </div>
      );
    }

    const side = row.role === "home" ? "home" : "away";
    const teamData = side === "home" ? event.home_team_data : event.away_team_data;
    const sportForLogo = event.sport_key ?? event.sport;
    const crestUrl = heroCrestImage199(teamData, row.fullName, sportForLogo);
    const servedImg =
      side === "home"
        ? servedParticipantImage(event.home_image_url, event.home_flag_url)
        : servedParticipantImage(event.away_image_url, event.away_flag_url);
    const badgeLetters = shippableCrestBadge(
      row.fullName,
      sportForLogo,
      row.abbreviation,
    );

    const fallbackCrest = (
      <div
        className="shrink-0 rounded-full flex items-center justify-center overflow-hidden"
        style={{
          width: crestSize,
          height: crestSize,
          backgroundColor: `${tint}1A`,
        }}
      >
        {crestUrl ? (
          <img
            src={crestUrl}
            alt=""
            width={crestSize - 4}
            height={crestSize - 4}
            loading="lazy"
            className="object-contain"
            style={{ width: crestSize - 4, height: crestSize - 4 }}
            onError={(e) => {
              (e.target as HTMLImageElement).style.display = "none";
              (e.target as HTMLImageElement).nextElementSibling?.classList.remove("hidden");
            }}
          />
        ) : null}
        <span
          className={`font-extrabold tracking-tight leading-none ${crestUrl ? "hidden" : ""}`}
          style={{
            fontSize: crestSize <= 24 ? 9.5 : 10.5,
            color: tint,
          }}
        >
          {badgeLetters}
        </span>
      </div>
    );

    return (
      <TournamentPlayerFace
        eventId={event.id}
        sportKey={event.sport}
        homeName={event.home_team}
        awayName={event.away_team}
        side={side}
        size={crestSize}
        servedImage={servedImg}
        fallback={fallbackCrest}
      />
    );
  };

  const wrapHeroHook = (children: React.ReactNode) =>
    isSettledHero ? (
      <div
        data-testid="event-hero-settled"
        data-winner={resolvedWinnerName}
        className="space-y-2"
      >
        {children}
      </div>
    ) : (
      <div
        data-testid="event-hero-probability"
        data-probability={homeProb ?? ""}
        {...headlineDisplayAttributes(homeProb === null ? null : displayIdentity)}
        className="space-y-2"
      >
        {children}
      </div>
    );

  return (
    <div
      ref={cueRef}
      data-testid="event-page-headline-199"
      data-phase={model.phase}
      data-atlas-mode={atlasMode ? "true" : undefined}
      className="rounded-2xl bg-surface-card px-3.5 py-3 space-y-2.5"
      style={{
        border: "1px solid rgba(15, 23, 42, 0.08)",
        boxShadow: "0 1px 2px rgba(15, 23, 42, 0.04)",
      }}
    >
      {/* Top Meta Bar */}
      <div className="flex items-center justify-between gap-2 min-w-0">
        <div className="flex items-center gap-2 min-w-0 flex-wrap">
          {model.liveBadgeText ? (
            <>
              <span
                data-testid="event-hero-live-pill"
                className="inline-flex items-center gap-[5px] rounded-full px-2 py-[3.5px] shrink-0"
                style={{ backgroundColor: HEADLINE_STYLE_199.livePillBg }}
              >
                <span className="w-1.5 h-1.5 rounded-full bg-white shrink-0" />
                <span className="text-[11px] font-semibold text-white tabular-nums leading-none whitespace-nowrap">
                  {model.liveBadgeText}
                </span>
              </span>
              <span
                className="text-[12px] font-medium leading-tight truncate"
                style={{ color: HEADLINE_STYLE_199.quietInk }}
              >
                {model.leagueLabel}
              </span>
            </>
          ) : (
            <span
              data-testid={
                model.isStoppedOrNoResult
                  ? "event-hero-suspended"
                  : model.phase === "before"
                    ? "event-hero-start"
                    : undefined
              }
              data-venue-settled={venueSettled ? "true" : undefined}
              data-stoppage={stoppageLabel ?? undefined}
              className="text-[12px] font-medium tabular-nums leading-tight"
              style={{ color: HEADLINE_STYLE_199.quietInk }}
            >
              {model.plainMetaText}
              {model.broadcastText ? (
                <>
                  {" · "}
                  <span data-testid="event-hero-broadcast">{model.broadcastText}</span>
                </>
              ) : null}
            </span>
          )}
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
          {ekgControl}
          {atlasMode && onOpenAtlasDetails ? (
            <button
              type="button"
              onClick={onOpenAtlasDetails}
              data-testid="event-atlas-headline-info-button"
              aria-label="About this game's probabilities and result"
              title="Details"
              className="inline-flex h-5 w-5 items-center justify-center rounded-full border border-surface-border bg-surface-elevated text-[11px] font-semibold text-text-secondary transition-colors hover:border-text-muted hover:text-text-primary"
            >
              i
            </button>
          ) : null}
          <button
            type="button"
            onClick={onPinToggle}
            disabled={pinDisabled}
            className={`p-1 rounded-full transition-all focus:outline-none ${
              isPinned
                ? "text-amber-500"
                : "text-text-muted/50 hover:text-text-secondary"
            } ${pinDisabled ? "cursor-not-allowed opacity-30" : ""}`}
            title={isPinned ? "Unpin event" : pinDisabled ? "Maximum 6 pins" : "Pin event"}
            aria-label={isPinned ? "Unpin event" : "Pin event"}
          >
            <PinIcon filled={isPinned} className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Unified Column-Header + Competitor-Rows Table */}
      {wrapHeroHook(
        <>
        {model.hasAnyColumnValue && model.columns.length > 0 ? (
          <div
            aria-hidden="true"
            className="flex items-baseline justify-end"
            style={{ gap: colGapPx }}
          >
            {model.columns.map((col, idx) => (
              <span
                key={`${col.role}-${col.setIndex ?? idx}`}
                className="font-semibold leading-none text-right whitespace-nowrap shrink-0"
                style={{
                  minWidth: columnMinWidthCss199(col.role, model.phase, colCount),
                  fontSize: pxToRem199(11),
                  color: HEADLINE_STYLE_199.quietInk,
                }}
              >
                {col.header}
              </span>
            ))}
          </div>
        ) : null}

        <div>
          {model.rows.map((row, rowIdx) => {
            const tint = rowTint(row.role);
            const isLoser = row.won === false;
            const nameColor =
              row.role === "draw" && row.won !== true
                ? HEADLINE_STYLE_199.drawTextInk
                : HEADLINE_STYLE_199.primaryInk;

            return (
              <React.Fragment key={row.role}>
                {rowIdx > 0 ? (
                  <div
                    aria-hidden="true"
                    className="my-1.5"
                    style={{
                      height: 0.5,
                      backgroundColor: "rgba(15, 23, 42, 0.06)",
                    }}
                  />
                ) : null}
                <div
                  data-testid={`headline-12472-${row.role}-row`}
                  className="flex items-center justify-between gap-2 min-w-0 max-[359px]:flex-wrap"
                >
                  <div className="flex items-center gap-2 min-w-0 flex-1 max-[359px]:basis-full">
                    {renderCrest(row, tint)}
                    <div className="flex flex-col min-w-0">
                      {row.role === "draw" ? (
                        <span
                          data-headline-name=""
                          className={`${isLoser ? "font-semibold" : "font-bold"} leading-tight truncate`}
                          style={{
                            fontSize: pxToRem199(nameFontPx),
                            color: nameColor,
                            opacity: isLoser && row.role !== "draw" ? HEADLINE_STYLE_199.loserOpacity : 1,
                          }}
                        >
                          {row.shortName}
                        </span>
                      ) : (
                        <TeamNameLink
                          name={row.fullName}
                          sportKey={event.sport}
                          className={`${isLoser ? "font-semibold" : "font-bold"} leading-tight truncate hover:underline`}
                        >
                          <span
                            data-headline-name=""
                            style={{
                              fontSize: pxToRem199(nameFontPx),
                              color: nameColor,
                              opacity: isLoser ? HEADLINE_STYLE_199.loserOpacity : 1,
                            }}
                          >
                            <SlashBreakableName text={row.shortName} />
                          </span>
                        </TeamNameLink>
                      )}
                      {row.record ? (
                        <span
                          className="font-medium tabular-nums leading-tight truncate mt-[1px]"
                          style={{
                            fontSize: pxToRem199(12),
                            color: HEADLINE_STYLE_199.quietInk,
                          }}
                        >
                          {row.record}
                        </span>
                      ) : null}
                    </div>
                  </div>

                  {model.columns.length > 0 ? (
                    <div
                      className="flex items-baseline shrink-0 max-[359px]:ml-auto"
                      style={{ gap: colGapPx }}
                    >
                      {model.columns.map((col, colIdx) => {
                        const text = colIdx < row.cells.length ? row.cells[colIdx] : "";
                        const minWidth = columnMinWidthCss199(col.role, model.phase, colCount);
                        const primaryFontPx = primaryHeadlineCellFontPx199(colCount);
                        const secondaryFontPx = secondaryHeadlineCellFontPx199(colCount);

                        if (col.role === "now" || col.role === "chance") {
                          return (
                            <span
                              key={`${col.role}-${colIdx}`}
                              data-headline-cell={col.role}
                              data-hero-digits={text ? "" : undefined}
                              className="font-black tabular-nums leading-none text-right whitespace-nowrap tracking-[-0.02em] shrink-0"
                              style={{
                                minWidth,
                                fontSize: pxToRem199(primaryFontPx),
                                color: tint,
                              }}
                            >
                              {text}
                            </span>
                          );
                        }

                        if (col.role === "score" || col.role === "projected") {
                          return (
                            <span
                              key={`${col.role}-${colIdx}`}
                              data-headline-cell={col.role}
                              data-projected-cell={
                                col.role === "projected" && text ? row.role : undefined
                              }
                              data-score-cell={
                                col.role === "score" && text ? row.role : undefined
                              }
                              className="font-semibold tabular-nums leading-none text-right whitespace-nowrap shrink-0"
                              style={{
                                minWidth,
                                fontSize: pxToRem199(secondaryFontPx),
                                color: HEADLINE_STYLE_199.primaryInk,
                              }}
                            >
                              {text}
                            </span>
                          );
                        }

                        if (col.role === "pregame") {
                          return (
                            <span
                              key={`${col.role}-${colIdx}`}
                              data-headline-cell={col.role}
                              className="font-semibold tabular-nums leading-none text-right whitespace-nowrap shrink-0"
                              style={{
                                minWidth,
                                fontSize: pxToRem199(secondaryFontPx),
                                color: HEADLINE_STYLE_199.quietInk,
                              }}
                            >
                              {text}
                            </span>
                          );
                        }

                        if (col.role === "setScore") {
                          const emph = row.emphasizedColumns.includes(colIdx);
                          return (
                            <span
                              key={`${col.role}-${col.setIndex ?? colIdx}`}
                              data-headline-cell={col.role}
                              className={`${emph ? "font-extrabold" : "font-semibold"} tabular-nums leading-none text-right whitespace-nowrap shrink-0`}
                              style={{
                                minWidth,
                                fontSize: pxToRem199(emph ? secondaryFontPx + 1.5 : secondaryFontPx),
                                color: emph
                                  ? HEADLINE_STYLE_199.primaryInk
                                  : HEADLINE_STYLE_199.quietInk,
                              }}
                            >
                              {text}
                            </span>
                          );
                        }

                        if (col.role === "gamePoints") {
                          return (
                            <span
                              key={`${col.role}-${colIdx}`}
                              data-headline-cell={col.role}
                              className="inline-flex justify-end shrink-0 whitespace-nowrap"
                              style={{ minWidth }}
                            >
                              {text ? (
                                <span
                                  className="font-semibold tabular-nums leading-none rounded-[5px] px-1.5 py-[2px]"
                                  style={{
                                    fontSize: pxToRem199(colCount >= 5 ? 13.5 : 14.5),
                                    color: HEADLINE_STYLE_199.primaryInk,
                                    backgroundColor: "rgba(15, 23, 42, 0.06)",
                                  }}
                                >
                                  {text}
                                </span>
                              ) : null}
                            </span>
                          );
                        }

                        // `finalResult`
                        if (row.won === true) {
                          return (
                            <span
                              key={`${col.role}-${colIdx}`}
                              data-headline-cell={col.role}
                              className="inline-flex items-baseline justify-end gap-[3px] whitespace-nowrap shrink-0"
                              style={{ minWidth }}
                            >
                              {text ? (
                                <span
                                  className="font-extrabold tabular-nums leading-none"
                                  style={{
                                    fontSize: pxToRem199(colCount >= 5 ? 19.5 : 22),
                                    color: HEADLINE_STYLE_199.primaryInk,
                                  }}
                                >
                                  {text}
                                </span>
                              ) : null}
                              <span
                                className="font-extrabold leading-none"
                                style={{
                                  fontSize: pxToRem199(colCount >= 5 ? 16 : 18),
                                  color: HEADLINE_STYLE_199.winnerTickInk,
                                }}
                              >
                                ✓
                              </span>
                            </span>
                          );
                        }

                        return (
                          <span
                            key={`${col.role}-${colIdx}`}
                            data-headline-cell={col.role}
                            className="font-semibold tabular-nums leading-none text-right whitespace-nowrap shrink-0"
                            style={{
                              minWidth,
                              fontSize: pxToRem199(secondaryFontPx),
                              color:
                                row.role === "draw"
                                  ? HEADLINE_STYLE_199.drawTextInk
                                  : row.won === false
                                    ? "rgba(15, 23, 42, 0.65)"
                                    : HEADLINE_STYLE_199.primaryInk,
                            }}
                          >
                            {text}
                          </span>
                        );
                      })}
                    </div>
                  ) : null}
                </div>
              </React.Fragment>
            );
          })}
        </div>
        </>,
      )}

      {/* Segmented Probability Bar (`before` & `during` only; never `after`) */}
      {model.bottomBar ? (
        model.bottomBar.kind === "twoWay" ? (
          (() => {
            const total = Math.max(
              model.bottomBar.awayShare + model.bottomBar.homeShare,
              0.0001,
            );
            const awayPct = Math.min(
              100,
              Math.max(0, (model.bottomBar.awayShare / total) * 100),
            );
            const marker = model.bottomBar.pregameAwayMarker;
            const showMarker = marker !== null && marker > 0 && marker < 1;
            return (
              <div
                aria-hidden="true"
                className="relative flex items-center"
                style={{ height: 10 }}
              >
                <div className="w-full h-[6px] rounded-full overflow-hidden flex">
                  <div
                    style={{
                      width: `${awayPct}%`,
                      minWidth: awayPct > 0 ? 2 : 0,
                      backgroundColor: model.colors.away,
                    }}
                  />
                  <div
                    className="flex-1"
                    style={{ backgroundColor: model.colors.home }}
                  />
                </div>
                {showMarker ? (
                  <span
                    className="absolute rounded-[1px]"
                    style={{
                      width: 2,
                      height: 10,
                      left: `clamp(2px, calc(${(marker * 100).toFixed(2)}% - 1px), calc(100% - 4px))`,
                      backgroundColor: "rgba(15, 23, 42, 0.85)",
                    }}
                  />
                ) : null}
              </div>
            );
          })()
        ) : (
          (() => {
            const total = Math.max(
              model.bottomBar.homeShare +
                model.bottomBar.drawShare +
                model.bottomBar.awayShare,
              0.0001,
            );
            const hPct = Math.min(100, Math.max(0, (model.bottomBar.homeShare / total) * 100));
            const dPct = Math.min(100, Math.max(0, (model.bottomBar.drawShare / total) * 100));
            return (
              <div
                aria-hidden="true"
                className="flex items-center"
                style={{ height: 8 }}
              >
                <div className="w-full h-[6px] rounded-full overflow-hidden flex gap-[1.5px]">
                  <div
                    style={{
                      width: `${hPct}%`,
                      minWidth: hPct > 0 ? 2 : 0,
                      backgroundColor: model.colors.home,
                    }}
                  />
                  <div
                    style={{
                      width: `${dPct}%`,
                      minWidth: dPct > 0 ? 2 : 0,
                      backgroundColor: model.colors.drawBar,
                    }}
                  />
                  <div
                    className="flex-1"
                    style={{ backgroundColor: model.colors.away }}
                  />
                </div>
              </div>
            );
          })()
        )
      ) : null}

      {/* Rulings 200-B & 214-A1 Single Non-Wrapping Grey Pregame Summary (`during` only, numbers in team colour) */}
      {model.livePregameSummary ? (
        <div
          ref={summaryFitRef}
          data-testid="headline-12472-pregame-summary"
          className="leading-tight tabular-nums whitespace-nowrap overflow-hidden"
          style={{
            fontSize: pxToRem199(summaryBasePx),
            color: HEADLINE_STYLE_199.liveSummaryQuietInk,
          }}
        >
          <span className="font-semibold">{model.livePregameSummary.leadWord}</span>
          {"  "}
          {model.livePregameSummary.namedText != null ||
          model.livePregameSummary.firstProjText != null ? (
            <>
              {model.livePregameSummary.namedText != null && (
                <span
                  className="font-semibold"
                  style={{
                    color:
                      model.livePregameSummary.namedSide === "away"
                        ? resolveLiveSummarySideInk(model.colors.away)
                        : model.livePregameSummary.namedSide === "home"
                          ? resolveLiveSummarySideInk(model.colors.home)
                          : HEADLINE_STYLE_199.slateTeamTextInk,
                  }}
                  data-testid="headline-pregame-named"
                >
                  {model.livePregameSummary.namedText}
                </span>
              )}
              {model.livePregameSummary.firstProjText != null &&
                model.livePregameSummary.secondProjText != null && (
                  <>
                    <span>
                      {model.livePregameSummary.namedText != null
                        ? " · projected "
                        : "projected "}
                    </span>
                    <span
                      className="font-semibold"
                      style={{
                        color:
                          model.livePregameSummary.firstProjSide === "away"
                            ? resolveLiveSummarySideInk(model.colors.away)
                            : resolveLiveSummarySideInk(model.colors.home),
                      }}
                      data-testid="headline-pregame-proj-first"
                    >
                      {model.livePregameSummary.firstProjText}
                    </span>
                    <span>–</span>
                    <span
                      className="font-semibold"
                      style={{
                        color:
                          model.livePregameSummary.secondProjSide === "away"
                            ? resolveLiveSummarySideInk(model.colors.away)
                            : resolveLiveSummarySideInk(model.colors.home),
                      }}
                      data-testid="headline-pregame-proj-second"
                    >
                      {model.livePregameSummary.secondProjText}
                    </span>
                  </>
                )}
            </>
          ) : (
            <span className="font-medium">{model.livePregameSummary.bodyText}</span>
          )}
        </div>
      ) : null}
    </div>
  );
}
