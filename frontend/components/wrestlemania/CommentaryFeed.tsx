"use client";

import type { WMCommentaryEntry } from "@/lib/types";

interface CommentaryFeedProps {
  entries: WMCommentaryEntry[];
}

function timeAgo(timestamp: string): string {
  const diff = Date.now() - new Date(timestamp).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  return `${hours}h ago`;
}

export default function CommentaryFeed({ entries }: CommentaryFeedProps) {
  if (entries.length === 0) return null;

  return (
    <div className="wm-commentary-feed">
      <div className="wm-commentary-feed-title">📣 Commentary</div>
      {entries.map((entry, i) => (
        <div key={i} className="wm-commentary-feed-item">
          <span className="wm-commentary-feed-time">{timeAgo(entry.timestamp)}</span>
          <span className="wm-commentary-feed-text">{entry.text}</span>
        </div>
      ))}
    </div>
  );
}
