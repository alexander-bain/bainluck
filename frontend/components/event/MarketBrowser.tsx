"use client";

import { useId, useState, type ReactNode } from "react";

export interface MarketBrowserItem {
  key: string;
  group: string;
  search: string;
  content: ReactNode;
}

/** A bounded window onto a complete collection. Search crosses every family. */
export default function MarketBrowser({
  items,
  label,
  pageSize = 12,
  searchable = true,
}: {
  items: MarketBrowserItem[];
  label: string;
  pageSize?: number;
  searchable?: boolean;
}) {
  const id = useId();
  const [selected, setSelected] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [limit, setLimit] = useState(pageSize);
  const groups = Array.from(new Set(items.map((item) => item.group)));
  const active =
    selected != null && groups.includes(selected) ? selected : groups[0];
  const term = query.trim().toLocaleLowerCase();
  const matches = items.filter((item) =>
    term
      ? item.search.toLocaleLowerCase().includes(term)
      : item.group === active,
  );
  if (!items.length) return null;
  return (
    <div className="min-w-0" aria-label={label}>
      <div className="flex flex-wrap items-center gap-3 mb-3">
        {searchable && (
          <input
            aria-label={`Search ${label.toLowerCase()}`}
            placeholder={`Search ${label.toLowerCase()}`}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setLimit(pageSize);
            }}
            className="w-full sm:w-64 min-h-11 rounded-lg border border-surface-border bg-surface-card px-3 text-sm text-text-primary placeholder:text-text-secondary focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-brand"
          />
        )}
        <div
          className="flex-1 min-w-0 flex gap-1 overflow-x-auto pb-1"
          aria-label={`${label} categories`}
        >
          {groups.map((group) => (
            <button
              key={group}
              type="button"
              aria-pressed={!term && group === active}
              aria-controls={id}
              onClick={() => {
                setSelected(group);
                setQuery("");
                setLimit(pageSize);
              }}
              className={`min-h-11 shrink-0 px-3 rounded-lg text-sm font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-brand ${!term && group === active ? "bg-text-primary text-text-inverse" : "bg-surface-elevated text-text-secondary hover:text-text-primary"}`}
            >
              {group}
            </button>
          ))}
        </div>
      </div>
      <div id={id} className="space-y-2">
        {matches.slice(0, limit).map((item) => (
          <div key={item.key}>{item.content}</div>
        ))}
        {!matches.length && (
          <p role="status" className="py-5 text-sm text-text-secondary">
            No matches. Try a player, team, or market name.
          </p>
        )}
      </div>
      {matches.length > pageSize && (
        <div className="flex items-center justify-between gap-3 mt-3 text-sm">
          <span role="status" className="text-text-secondary">
            {Math.min(limit, matches.length)} of {matches.length}
          </span>
          <button
            type="button"
            onClick={() =>
              setLimit(limit < matches.length ? limit + pageSize : pageSize)
            }
            className="min-h-11 px-3 font-semibold text-text-primary hover:bg-surface-elevated rounded-lg focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-brand"
          >
            {limit < matches.length ? "Show more" : "Show fewer"}
          </button>
        </div>
      )}
    </div>
  );
}
