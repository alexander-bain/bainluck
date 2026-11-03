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
}) {
  const [clock] = useState(() => nowMs ?? Date.now());
  const now = nowMs ?? clock;
  const { model } = buildRoundupCardModel(title, contract, now);
  const destination = admitCollectionRef(collectionRef);
  if (!model || !destination) return null;

  const label = `${model.title}. ${model.rows
    .map((r) => `${r.label}, ${r.marker === "<" ? "under " : r.marker === ">" ? "over " : ""}${r.digits}%`)
    .join("; ")}. ${model.footer}`;

  return (
    <div data-testid="roundup-card-slot">
      <Link
        href={destination.href}
        onClick={() => rememberThemeCollectionReturn(bundleId, false)}
        aria-label={label}
        data-testid="roundup-card"
        data-bundle-id={bundleId}
        className="grid min-w-0 gap-[14px] rounded-2xl border border-surface-border bg-surface-card pb-[13px] pl-[18px] pr-[18px] pt-[18px] text-left no-underline focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--series-1)]"
      >
        <RoundupHeader kicker={model.kicker} tag={model.tag} title={model.title} longHeadline={model.longHeadline} />
        <div className="grid gap-[14px]" data-testid="roundup-rows">
          {model.rows.map((row) => (
            <RoundupRow key={row.marketId} row={row} nowMs={now} />
          ))}
        </div>
        <div
          className="flex items-center justify-between gap-2 border-t border-surface-border pt-[10px] text-[11.5px] text-text-secondary"
          data-testid="roundup-footer"
        >
          <span>{model.footer}</span>
          {model.cardMarkObservedAt ? (
            <PriceAgeMark observedAt={model.cardMarkObservedAt} nowMs={now} cadence={model.cadence} scope="card" />
          ) : null}
        </div>
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
