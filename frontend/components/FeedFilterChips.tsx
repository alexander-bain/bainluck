"use client";

import { useRef, useCallback } from "react";

export interface FeedChip {
  label: string;
  tags: string[];
  emoji: string;
}

const FEED_CHIPS: FeedChip[] = [
  { label: "Live", tags: ["status:live"], emoji: "\uD83D\uDD34" },
  { label: "Playoffs", tags: ["importance:playoff"], emoji: "\uD83C\uDFC6" },
  { label: "Upsets", tags: ["signal:upset"], emoji: "\uD83D\uDE31" },
  { label: "Close Games", tags: ["signal:close_matchup"], emoji: "\uD83E\uDD1D" },
  { label: "Line Moving", tags: ["signal:line_moving"], emoji: "\uD83D\uDCC8" },
  { label: "Starting Soon", tags: ["timing:starting_soon"], emoji: "\u23F0" },
];

interface FeedFilterChipsProps {
  activeTags: string[] | null;
  onTagChange: (tags: string[] | null) => void;
  onTrack?: (chip: FeedChip, action: "select" | "deselect") => void;
}

export default function FeedFilterChips({
  activeTags,
  onTagChange,
  onTrack,
}: FeedFilterChipsProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  const handleClick = useCallback(
    (chip: FeedChip) => {
      const isActive =
        activeTags !== null &&
        chip.tags.every((t) => activeTags.includes(t));

      if (isActive) {
        onTagChange(null);
        onTrack?.(chip, "deselect");
      } else {
        onTagChange(chip.tags);
        onTrack?.(chip, "select");
      }
    },
    [activeTags, onTagChange, onTrack]
  );

  return (
    <div
      ref={scrollRef}
      className="flex gap-2 overflow-x-auto pb-1 scrollbar-hide -mx-1 px-1"
    >
      {FEED_CHIPS.map((chip) => {
        const isActive =
          activeTags !== null &&
          chip.tags.every((t) => activeTags.includes(t));

        return (
          <button
            key={chip.label}
            onClick={() => handleClick(chip)}
            className={`
              flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium
              whitespace-nowrap transition-colors shrink-0
              ${
                isActive
                  ? "bg-text-primary text-surface-deep"
                  : "bg-surface-elevated text-text-secondary hover:bg-surface-border"
              }
            `}
          >
            <span className="text-sm leading-none">{chip.emoji}</span>
            {chip.label}
          </button>
        );
      })}
    </div>
  );
}
