"use client";

import Link from "next/link";
import { useState } from "react";
import { PriceAgeMark } from "@/components/event/PriceAgeMark";
import { buildRoundupCardModel } from "@/lib/discover/roundupCard";
import type { FeedItem, FeedRoundupContract, FeedThemeCollectionRef } from "@/lib/types";
import { BundleActionBar } from "../BundleActionBar";
import { admitCollectionRef, rememberThemeCollectionReturn } from "../shared";
import { RoundupHeader } from "./RoundupHeader";
import { RoundupRow } from "./RoundupRow";

/**
 * #10357 — the round-up card ("NFL division front-runners"), to Fable's R4
 * reference and Alex's Oct 6 rulings.
 *
 * - The WHOLE card is one target. A tap opens the container served for this
 *   card (`collection_ref`, proved by the server), which holds the same rows in
 *   the same order. Rows are not separate links.
 * - No container, no card: a round-up that cannot open what it shows is not
 *   drawn. Nor is one whose contract is unreadable (`buildRoundupCardModel`).
 * - Nothing inside the card but text and bars: no icons, images, chevrons or
 *   colored text. The product's existing card actions sit OUTSIDE it, below.
 * - Light only; product tokens throughout (R4's Colors table).
 */
export function RoundupCard({
  title,
  contract,
  collectionRef,
  items,
  bundleId,
  storyKey,
  positionIndex,
  nowMs,
  previewOnly = false,
}: {
  title: string;
  contract: FeedRoundupContract | null | undefined;
  collectionRef: FeedThemeCollectionRef | null | undefined;
  items: FeedItem[];
  bundleId: string;
  storyKey?: string | null;
  positionIndex?: number;
  /** Fixed clock for guards; production passes nothing and reads it once. */
  nowMs?: number;
  /** When true (e.g. `/grade/groupings`), renders the card shell without requiring a live collection route or action bar. */
  previewOnly?: boolean;
}) {
  const [clock] = useState(() => nowMs ?? Date.now());
  const now = nowMs ?? clock;
  const { model } = buildRoundupCardModel(title, contract, now);
  const destination = previewOnly ? null : admitCollectionRef(collectionRef);
  if (!model || (!previewOnly && !destination)) return null;

  const label = `${model.title}. ${model.rows
    .map((r) => `${r.label}, ${r.marker === "<" ? "under " : r.marker === ">" ? "over " : ""}${r.digits}%`)
    .join("; ")}.${model.countLine ? ` ${model.countLine}.` : ""} ${model.footer}`;

  const innerContent = (
    <>
      <RoundupHeader
        kicker={model.kicker}
        tag={model.tag}
        title={model.title}
        subtitle={model.subtitle}
        longHeadline={model.longHeadline}
      />
      {model.presentation === "strip" ? (
        <div className="grid grid-cols-3 gap-2.5" data-testid="roundup-rows" data-presentation="strip">
          {model.rows.map((row) => (
            <div
              key={row.marketId}
              className="flex min-w-0 flex-col justify-between rounded-xl border border-surface-border bg-surface-elevated/40 p-2.5"
              data-testid="roundup-row"
              data-market-id={row.marketId}
            >
              <div className="min-w-0" data-testid="roundup-row-label">
                <div className="truncate text-[13px] font-medium leading-[1.25] text-text-primary">
                  {row.opponentLabel ?? row.label}
                </div>
                {row.dateLabel ? (
                  <div className="mt-0.5 truncate text-[11.5px] leading-[1.2] text-text-secondary">
                    {row.dateLabel}
                  </div>
                ) : null}
              </div>
              <div className="mt-2.5">
                <div className="flex items-baseline justify-between gap-1">
                  <span className="font-mono text-[18px] font-bold leading-[1.15] tracking-[-0.03em] text-text-primary tabular-nums">
                    {row.marker}
                    {row.digits}
                    <small className="ml-px text-[0.6em] font-medium tracking-normal text-text-secondary">%</small>
                  </span>
                  {row.rowMark ? (
                    <PriceAgeMark observedAt={row.observedAt} nowMs={now} cadence={row.cadence} scope="row" />
                  ) : null}
                </div>
                <span
                  className="mt-1.5 block h-[5px] overflow-hidden rounded-[3px] bg-surface-elevated"
                  aria-hidden="true"
                >
                  <i
                    className="block h-full min-w-[3px] rounded-r-[3px] bg-[var(--series-1)]"
                    style={{ width: `${Math.max(0, Math.min(1, row.fill)) * 100}%` }}
                    data-testid="roundup-row-bar"
                  />
                </span>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="grid gap-[14px]" data-testid="roundup-rows">
          {model.rows.map((row) => (
            <RoundupRow key={row.marketId} row={row} nowMs={now} />
          ))}
        </div>
      )}
      {model.countLine ? (
        <div className="text-[12px] text-text-secondary" data-testid="roundup-count-line">
          {model.countLine}
        </div>
      ) : null}
      <div
        className="flex items-center justify-between gap-2 border-t border-surface-border pt-[10px] text-[11.5px] text-text-secondary"
        data-testid="roundup-footer"
      >
        <span>{model.footer}</span>
        {model.cardMarkObservedAt ? (
          <PriceAgeMark observedAt={model.cardMarkObservedAt} nowMs={now} cadence={model.cadence} scope="card" />
        ) : null}
      </div>
    </>
  );

  if (previewOnly) {
    return (
      <div data-testid="roundup-card-slot">
        <div
          aria-label={label}
          data-testid="roundup-card"
          data-bundle-id={bundleId}
          className="grid min-w-0 gap-[14px] rounded-2xl border border-surface-border bg-surface-card pb-[13px] pl-[18px] pr-[18px] pt-[18px] text-left"
        >
          {innerContent}
        </div>
      </div>
    );
  }

  return (
    <div data-testid="roundup-card-slot">
      <Link
        href={destination!.href}
        onClick={() => rememberThemeCollectionReturn(bundleId, false)}
        aria-label={label}
        data-testid="roundup-card"
        data-bundle-id={bundleId}
        className="grid min-w-0 gap-[14px] rounded-2xl border border-surface-border bg-surface-card pb-[13px] pl-[18px] pr-[18px] pt-[18px] text-left no-underline focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--series-1)]"
      >
        {innerContent}
      </Link>
      <div className="mt-[10px]">
        <BundleActionBar
          items={items}
          title={model.title}
          sharedQuestion={model.title}
          storyKey={storyKey ?? bundleId}
          positionIndex={positionIndex}
        />
      </div>
    </div>
  );
}
