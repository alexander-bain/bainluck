"use client";

import { useState, useCallback } from "react";
import useSWR from "swr";
import { useAdminAuth } from "@/components/admin/AdminAuthProvider";
import { adminFetch } from "@/lib/adminFetch";
import PageHeader from "@/components/admin/PageHeader";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface CohortRow {
  source: string;
  league_category: string;
  market_type: string;
  probability_band?: string | null;
  band_idx?: number | null;
  week?: string | null;
  n: number;
  independent_questions: number;
  graded_share?: number | null;
  ece: number;
  signed_error: number;
  verdict: string;
}

interface CohortPayload {
  rows: number;
  cohorts: number;
  sufficient: number;
  by_ece: CohortRow[];
  by_band?: CohortRow[];
  by_band_worst?: CohortRow[];
  weekly_by_cohort?: Record<string, CohortRow[]>;
  weekly?: CohortRow[];
  generated_at?: number;
  status?: string;
  message?: string;
}

function verdictClass(v: string) {
  if (v.startsWith("GREEN")) return "bg-green-900 text-green-200 border-green-700";
  if (v.startsWith("RED")) return "bg-red-900 text-red-200 border-red-700";
  return "bg-yellow-900 text-yellow-200 border-yellow-700";
}

export default function CohortViewsPage() {
  const { secret } = useAdminAuth();
  const [autoRefresh, setAutoRefresh] = useState(true);

  const fetcher = useCallback(async (url: string) => {
    const res = await adminFetch(url, secret);
    if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
    return res.json() as Promise<CohortPayload>;
  }, [secret]);

  const { data, error, isLoading, mutate } = useSWR<CohortPayload>(
    secret ? "/api/admin/cohort-market-type" : null,
    fetcher,
    { refreshInterval: autoRefresh ? 60000 : 0, revalidateOnFocus: false }
  );

  const rows: CohortRow[] = (data?.by_band_worst || data?.by_band || data?.by_ece || []).slice(0, 100);
  const weekly = data?.weekly_by_cohort || {};

  return (
    <div className="p-6 space-y-6">
      <PageHeader
        question="Cohort Views — is every cell provable?"
        status={isLoading ? "loading" : error ? "critical" : "good"}
        summary="ECE by source × league × type × band × week, sorted desc by ECE. Graded share <50% ⇒ NOT-PROVABLE-selection-biased."
        ideal="Every cell GREEN (≤5pp) or NOT-PROVABLE with a plan; no RED"
        subtitle="Band = 0-10%..90-100% (4th axis). Weekly for Monday scoreboard. Auto-refreshes every 60s."
      />
      <div className="flex items-center gap-4 text-sm">
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={autoRefresh} onChange={(e) => setAutoRefresh(e.target.checked)} />
          Auto-refresh every 60s
        </label>
        <button onClick={() => mutate()} className="px-3 py-1 rounded border border-zinc-700 hover:bg-zinc-800">
          Refresh now
        </button>
        {data?.generated_at && (
          <span className="text-zinc-400">Generated {new Date(data.generated_at * 1000).toLocaleString()}</span>
        )}
        <a href={`${API_URL}/api/admin/cohort-views`} target="_blank" rel="noreferrer" className="text-blue-400 underline">
          Open backend HTML
        </a>
      </div>

      {isLoading && <div className="text-zinc-400">Loading heavy table… (first build ~90s, enqueued via POST /build)</div>}
      {error && <div className="text-red-400">Error: {(error as Error).message}</div>}
      {data?.status && <div className="text-yellow-300">{data.message}</div>}

      {rows.length > 0 && (
        <div className="overflow-auto border border-zinc-800 rounded">
          <table className="w-full text-xs border-collapse">
            <thead className="bg-zinc-900 sticky top-0">
              <tr>
                <th className="p-2 text-left">rank</th>
                <th className="p-2 text-left">source</th>
                <th className="p-2 text-left">league</th>
                <th className="p-2 text-left">type</th>
                <th className="p-2 text-left">band</th>
                <th className="p-2 text-right">n</th>
                <th className="p-2 text-right">q</th>
                <th className="p-2 text-right">graded_share</th>
                <th className="p-2 text-right">ECE</th>
                <th className="p-2 text-right">gap pp</th>
                <th className="p-2 text-left">verdict</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((c, i) => (
                <tr key={`${c.source}|${c.league_category}|${c.market_type}|${c.band_idx}-${i}`} className={i % 2 === 0 ? "bg-zinc-950" : "bg-zinc-900"}>
                  <td className="p-2">{i + 1}</td>
                  <td className="p-2">{c.source}</td>
                  <td className="p-2">{c.league_category}</td>
                  <td className="p-2">{c.market_type}</td>
                  <td className="p-2">{c.probability_band || (c.band_idx != null ? `${c.band_idx * 10}-${(c.band_idx + 1) * 10}%` : "—")}</td>
                  <td className="p-2 text-right">{c.n}</td>
                  <td className="p-2 text-right">{c.independent_questions}</td>
                  <td className="p-2 text-right">{c.graded_share != null ? `${(c.graded_share * 100).toFixed(1)}%` : "—"}</td>
                  <td className="p-2 text-right">{(c.ece * 100).toFixed(2)}</td>
                  <td className="p-2 text-right">{(c.signed_error * 100).toFixed(2)}</td>
                  <td className="p-2"><span className={`px-2 py-0.5 rounded border text-[10px] ${verdictClass(c.verdict)}`}>{c.verdict}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div>
        <h2 className="text-lg font-semibold mt-6 mb-2">Weekly — last 6 weeks per cohort (is it improving?)</h2>
        <p className="text-xs text-zinc-400 mb-2">Monday scoreboard can quote `weekly_by_cohort[cohort].map(week→ECE)`. Below: first 20 cohorts.</p>
        {Object.keys(weekly).length === 0 ? (
          <div className="text-zinc-400 text-sm">No weekly data yet (heavy build pending)</div>
        ) : (
          <div className="overflow-auto border border-zinc-800 rounded">
            <table className="w-full text-xs border-collapse">
              <thead className="bg-zinc-900">
                <tr><th className="p-2 text-left">cohort</th><th className="p-2 text-left">weekly ECE (last 6)</th></tr>
              </thead>
              <tbody>
                {Object.entries(weekly).slice(0, 20).map(([k, series]) => (
                  <tr key={k} className="border-t border-zinc-800">
                    <td className="p-2 font-mono">{k}</td>
                    <td className="p-2">{(series as CohortRow[]).map((s) => `${s.week}:${(s.ece * 100).toFixed(1)}`).join(" → ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
