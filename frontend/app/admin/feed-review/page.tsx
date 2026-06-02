"use client";

import { useState, useEffect, useCallback } from "react";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import { useAdminAuth } from "@/components/admin/AdminAuthProvider";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface FeedItem {
  type: string;
  score: number;
  reason: string;
  headline: string;
  data: {
    id: number;
    name?: string;
    external_id?: string;
    source?: string;
    sport?: string;
    sport_name?: string;
    home_team?: string;
    away_team?: string;
    status?: string;
    llm_sport_category?: string;
    category?: string;
    image_url?: string;
    hook_description?: string;
  };
}

type Verdict = "boost" | "demote" | null;

export default function FeedReviewPage() {
  const { adminSecret } = useAdminAuth();
  usePageTracking({ pageType: "admin", pageTitle: "Feed Review" });
  useScrollDepth({ pageType: "admin" });
  useEngagementTime({ pageType: "admin" });

  const [items, setItems] = useState<FeedItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [verdicts, setVerdicts] = useState<Record<number, Verdict>>({});
  const [submitting, setSubmitting] = useState<Set<number>>(new Set());
  const [submitted, setSubmitted] = useState(0);

  useEffect(() => {
    if (!adminSecret) return;
    setLoading(true);
    fetch(`${API_URL}/api/feed?limit=100&event_pct=0.15`)
      .then((r) => r.json())
      .then((d) => {
        setItems(d.items || []);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [adminSecret]);

  const sendSignal = useCallback(
    async (item: FeedItem, signal: "boost" | "demote") => {
      const id = item.data.id;
      setSubmitting((prev) => new Set([...prev, id]));

      const source = item.data.source || "";
      let url = "";
      if (item.type === "futures") {
        if (source === "kalshi") {
          url = `https://kalshi.com/markets/${(item.data.external_id || "").toLowerCase()}`;
        } else if (source === "polymarket") {
          url = `https://polymarket.com/event/${item.data.external_id || ""}`;
        } else {
          url = `bainluck://market/${item.data.id}`;
        }
      } else {
        url = `bainluck://event/${item.data.id}`;
      }

      try {
        await fetch(
          `${API_URL}/api/admin/ranking-judgments/curation-signal?secret=${adminSecret}`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ url, signal, source_device: "web_review" }),
          }
        );
        setVerdicts((prev) => ({ ...prev, [id]: signal }));
        setSubmitted((prev) => prev + 1);
      } finally {
        setSubmitting((prev) => {
          const next = new Set(prev);
          next.delete(id);
          return next;
        });
      }
    },
    [adminSecret]
  );

  if (!adminSecret) {
    return (
      <div className="p-8 text-center text-text-secondary">
        Enter admin secret to access feed review.
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto px-4 py-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">Feed Review</h1>
          <p className="text-sm text-text-secondary mt-1">
            Top 100 Discover items. Boost what should rank higher, demote what shouldn&apos;t be here.
          </p>
        </div>
        <div className="text-sm text-text-muted">
          {submitted > 0 && (
            <span className="bg-emerald-100 text-emerald-700 px-3 py-1 rounded-full font-medium">
              {submitted} signals sent
            </span>
          )}
        </div>
      </div>

      {loading ? (
        <div className="text-center py-12 text-text-secondary">Loading feed...</div>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-surface-border text-left text-text-muted">
              <th className="py-2 w-10">#</th>
              <th className="py-2 w-14">Score</th>
              <th className="py-2">Market</th>
              <th className="py-2 w-24">Category</th>
              <th className="py-2 w-20">Source</th>
              <th className="py-2 w-36 text-center">Verdict</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item, idx) => {
              const id = item.data.id;
              const verdict = verdicts[id];
              const isSubmitting = submitting.has(id);
              const name =
                item.type === "event"
                  ? `${item.data.away_team || "?"} at ${item.data.home_team || "?"}`
                  : item.data.name || "?";
              const cat =
                item.data.llm_sport_category ||
                item.data.category ||
                item.data.sport_name ||
                "";
              const source = item.data.source || (item.type === "event" ? "event" : "?");

              return (
                <tr
                  key={`${item.type}-${id}-${idx}`}
                  className={`border-b border-surface-border/50 hover:bg-surface-elevated/50 ${
                    verdict === "boost"
                      ? "bg-emerald-50"
                      : verdict === "demote"
                      ? "bg-red-50"
                      : ""
                  }`}
                >
                  <td className="py-2 text-text-muted">{idx + 1}</td>
                  <td className="py-2 font-mono font-bold">{item.score}</td>
                  <td className="py-2">
                    <div className="font-medium text-text-primary truncate max-w-md">
                      {name}
                    </div>
                    {item.headline && (
                      <div className="text-xs text-text-muted truncate">
                        {item.headline} — {item.reason}
                      </div>
                    )}
                  </td>
                  <td className="py-2 text-text-secondary">{cat}</td>
                  <td className="py-2 text-text-muted">{source}</td>
                  <td className="py-2 text-center">
                    {verdict ? (
                      <span
                        className={`px-3 py-1 rounded-full text-xs font-bold ${
                          verdict === "boost"
                            ? "bg-emerald-100 text-emerald-700"
                            : "bg-red-100 text-red-700"
                        }`}
                      >
                        {verdict === "boost" ? "👍" : "👎"}
                      </span>
                    ) : (
                      <div className="flex gap-1 justify-center">
                        <button
                          onClick={() => sendSignal(item, "boost")}
                          disabled={isSubmitting}
                          className="px-2 py-1 rounded bg-emerald-600 text-white text-xs font-bold hover:bg-emerald-700 disabled:opacity-50"
                        >
                          👍
                        </button>
                        <button
                          onClick={() => sendSignal(item, "demote")}
                          disabled={isSubmitting}
                          className="px-2 py-1 rounded bg-red-600 text-white text-xs font-bold hover:bg-red-700 disabled:opacity-50"
                        >
                          👎
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
