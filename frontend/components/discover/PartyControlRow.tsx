"use client";

import Link from "next/link";
import { marketEventKey, eventPath } from "@/lib/eventKey";
import { forYouCue } from "@/lib/discover/forYouCue";
import {
  partyControlRowProps,
  stripVisiblePartyLeadClause,
} from "@/lib/discover/partyControlRow";
import type { FeedFuturesData, FeedItem } from "@/lib/types";
import { FuturesCompactRow } from "./FuturesCard";
import { ForYouChip } from "./shared";
import { feedContextSnippet } from "./utils";

interface PartyControlRowProps {
  member?: FeedItem;
  item?: FeedItem;
  data: FeedFuturesData;
}

/**
 * Option A two-sided party row for the Congress control theme bundle (#9880).
 *
 * Scoped by `ThemeBundleCard` to `story:us_congress_control:<edition>` members.
 * Falls back to `FuturesCompactRow` whenever `partyControlRowProps(data)` returns
 * `null` (resolved rows, missing `rendered_percent`, withheld probabilities,
 * excess-sum pairs, non-party labels, or incomplete boards).
 */
export function PartyControlRow({ member, item, data }: PartyControlRowProps) {
  const feedItem = (member ?? item)!;
  const model = partyControlRowProps(data);
  if (!model) {
    return <FuturesCompactRow item={feedItem} data={data} />;
  }

  const conceptKey = marketEventKey(data);
  const detailHref = conceptKey ? eventPath(conceptKey) : `/futures/${data.id}`;

  const rawContext =
    feedContextSnippet(feedItem) ||
    ((data as { context_summary?: string | null }).context_summary ?? "");
  const caption = stripVisiblePartyLeadClause(rawContext, [
    { name: model.a.name, pct: model.a.percentText },
    { name: model.b.name, pct: model.b.percentText },
  ]);
  const rowCue = forYouCue(feedItem);

  return (
    <Link
      href={detailHref}
      className="block group"
      data-row-kind="two-sided"
      data-testid="party-control-row"
    >
      <div
        className="text-sm font-semibold leading-[1.3] text-text-primary break-words group-hover:text-accent-brand transition-colors"
        data-testid="party-control-row-title"
      >
        {data.name}
      </div>
      <div
        className="mt-1.5"
        data-residual={model.residual.toFixed(4)}
        data-testid="party-control-row-body"
      >
        <div
          className="flex items-end justify-between gap-3"
          data-testid="party-control-sides"
        >
          <div
            className="min-w-0"
            data-slot="left"
            data-testid="party-control-side-left"
          >
            <div className="flex items-center gap-1.5 text-sm font-semibold leading-tight text-text-primary">
              <span
                className="w-2 h-2 rounded-full shrink-0"
                style={{ backgroundColor: model.a.color }}
                data-testid="party-control-dot-left"
              />
              <span
                className="break-words"
                data-testid="party-control-name-left"
              >
                {model.a.name}
              </span>
            </div>
            <div
              className={`font-mono tabular-nums font-bold text-text-primary leading-none mt-1 ${
                model.a.isLeader ? "text-[22px]" : "text-[15px] pb-0.5"
              }`}
              data-probability={model.a.probability}
              data-rendered-percent={model.a.renderedPercent}
              data-leader={model.a.isLeader ? "true" : "false"}
              data-testid="party-control-percent-left"
            >
              {model.a.percentText}
            </div>
          </div>
          <div
            className="min-w-0 text-right"
            data-slot="right"
            data-testid="party-control-side-right"
          >
            <div className="flex items-center justify-end gap-1.5 text-sm font-semibold leading-tight text-text-primary">
              <span
                className="break-words"
                data-testid="party-control-name-right"
              >
                {model.b.name}
              </span>
              <span
                className="w-2 h-2 rounded-full shrink-0"
                style={{ backgroundColor: model.b.color }}
                data-testid="party-control-dot-right"
              />
            </div>
            <div
              className={`font-mono tabular-nums font-bold text-text-primary leading-none mt-1 ${
                model.b.isLeader ? "text-[22px]" : "text-[15px] pb-0.5"
              }`}
              data-probability={model.b.probability}
              data-rendered-percent={model.b.renderedPercent}
              data-leader={model.b.isLeader ? "true" : "false"}
              data-testid="party-control-percent-right"
            >
              {model.b.percentText}
            </div>
          </div>
        </div>
        <div
          className="relative h-2.5 mt-2 rounded-full bg-surface-border overflow-hidden"
          role="img"
          aria-label={`${model.a.name} ${model.a.percentText}, ${model.b.name} ${model.b.percentText}`}
          data-residual={model.residual.toFixed(4)}
          data-testid="party-control-track"
        >
          <div
            className="absolute inset-y-0 left-0"
            style={{
              width: model.a.widthPercent,
              backgroundColor: model.a.color,
            }}
            data-probability={model.a.probability}
            data-testid="party-control-segment-left"
          />
          <div
            className="absolute inset-y-0 right-0"
            style={{
              width: model.b.widthPercent,
              backgroundColor: model.b.color,
            }}
            data-probability={model.b.probability}
            data-testid="party-control-segment-right"
          />
        </div>
        {caption.text && (
          <div
            className="text-xs text-text-muted mt-1.5 leading-[1.35]"
            data-caption-deleted={caption.deleted ?? ""}
            data-testid="party-control-caption"
          >
            {caption.party ? (
              <>
                <b className="font-semibold text-text-secondary">
                  {caption.party}
                </b>
                {caption.rest}
              </>
            ) : (
              caption.text
            )}
          </div>
        )}
        {rowCue && (
          <div className="mt-1">
            <ForYouChip cue={rowCue} />
          </div>
        )}
      </div>
    </Link>
  );
}
