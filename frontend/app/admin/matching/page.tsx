"use client";

import { useAdminAuth } from "@/components/admin/AdminAuthProvider";
import PageHeader from "@/components/admin/PageHeader";

import { useState, useCallback } from "react";
import useSWR, { mutate } from "swr";
import {
  usePageTracking,
  useScrollDepth,
  useEngagementTime,
} from "@/hooks";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const LEAGUES = [
  { slug: "nba", label: "NBA" },
  { slug: "nhl", label: "NHL" },
  { slug: "ncaa-basketball", label: "NCAAB" },
];

interface SourceProbs {
  [source: string]: number;
}

interface SourceDetail {
  probability: number;
  market_name: string;
  market_id: number | null;
}

interface Divergence {
  team: string;
  column: string;
  spread: number;
  sources: SourceProbs;
  source_details?: { [source: string]: SourceDetail };
  status: string;
}

interface SparseTeam {
  team: string;
  filled_columns: number;
  total_columns: number;
  championship_prob: number | null;
  status: string;
}

interface Override {
  id: number;
  type: string;
  source_name: string;
  target_name: string | null;
  decision: string;
  context: Record<string, unknown> | null;
  created_at: string | null;
}

interface ReviewData {
  league: string;
  total_teams: number;
  total_columns: number;
  columns: string[];
  overrides: Override[];
  divergences: Divergence[];
  divergence_count: number;
  sparse_teams: SparseTeam[];
  sparse_count: number;
}

async function fetchReview(league: string, secret: string = secret): Promise<ReviewData> {
  const res = await fetch(
    `${API_URL}/api/admin/matching-review/${league}?secret=${encodeURIComponent(secret)}`
  );
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

async function postOverride(
  league: string,
  body: {
    override_type: string;
    source_name: string;
    target_name?: string;
    decision?: string;
    reason?: string;
  }
) {
  const params = new URLSearchParams({
    secret: secret,
    override_type: body.override_type,
    source_name: body.source_name,
  });
  if (body.target_name) params.set("target_name", body.target_name);
  if (body.decision) params.set("decision", body.decision);
  if (body.reason) params.set("reason", body.reason);
  const res = await fetch(
    `${API_URL}/api/admin/matching-review/${league}/override?${params}`,
    { method: "POST" }
  );
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

async function deleteOverride(league: string, id: number) {
  const res = await fetch(
    `${API_URL}/api/admin/matching-review/${league}/override/${id}?secret=${encodeURIComponent(secret)}`,
    { method: "DELETE" }
  );
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

// ─── Components ──────────────────────────────────────────────────────────────

function LeagueTabs({
  selected,
  onSelect,
}: {
  selected: string;
  onSelect: (slug: string) => void;
}) {
  return (
    <div style={{ display: "flex", gap: 8, marginBottom: 24 }}>
      {LEAGUES.map((l) => (
        <button
          key={l.slug}
          onClick={() => onSelect(l.slug)}
          style={{
            padding: "8px 20px",
            borderRadius: 8,
            border: selected === l.slug ? "2px solid #3b82f6" : "2px solid #333",
            background: selected === l.slug ? "#1e3a5f" : "#1a1a2e",
            color: selected === l.slug ? "#93c5fd" : "#888",
            fontWeight: 600,
            fontSize: 14,
            cursor: "pointer",
          }}
        >
          {l.label}
        </button>
      ))}
    </div>
  );
}

function StatCard({ label, value, color }: { label: string; value: string | number; color?: string }) {
  return (
    <div
      style={{
        background: "#1a1a2e",
        borderRadius: 10,
        padding: "14px 18px",
        minWidth: 120,
        textAlign: "center",
      }}
    >
      <div style={{ fontSize: 28, fontWeight: 700, color: color || "#e2e8f0" }}>
        {value}
      </div>
      <div style={{ fontSize: 12, color: "#888", marginTop: 4 }}>{label}</div>
    </div>
  );
}

function DivergenceCard({
  d,
  league,
  onAction,
}: {
  d: Divergence;
  league: string;
  onAction: () => void;
}) {
  const [acting, setActing] = useState(false);

  const handleExclude = async () => {
    setActing(true);
    try {
      await postOverride(league, {
        override_type: "team_exclude",
        source_name: d.team,
        reason: `cross_source_divergence: ${d.column} spread=${(d.spread * 100).toFixed(1)}%`,
      });
      onAction();
    } finally {
      setActing(false);
    }
  };

  const handleDismiss = async () => {
    setActing(true);
    try {
      await postOverride(league, {
        override_type: "dismiss",
        source_name: `${d.team}:${d.column}`,
        reason: `Reviewed divergence: ${(d.spread * 100).toFixed(1)}% spread acceptable`,
      });
      onAction();
    } finally {
      setActing(false);
    }
  };

  const sourceEntries = Object.entries(d.sources);
  const maxSource = sourceEntries.reduce((a, b) => (a[1] > b[1] ? a : b));

  return (
    <div
      style={{
        background: "#1a1a2e",
        borderRadius: 10,
        padding: 16,
        borderLeft: `4px solid ${d.spread > 0.3 ? "#ef4444" : d.spread > 0.2 ? "#f59e0b" : "#3b82f6"}`,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <div>
          <span style={{ fontWeight: 700, fontSize: 16, color: "#e2e8f0", textTransform: "capitalize" }}>
            {d.team}
          </span>
          <span
            style={{
              marginLeft: 8,
              padding: "2px 8px",
              borderRadius: 4,
              fontSize: 11,
              fontWeight: 600,
              background: "#2d2d4e",
              color: "#93c5fd",
            }}
          >
            {d.column.replace(/_/g, " ")}
          </span>
        </div>
        <span
          style={{
            fontWeight: 700,
            fontSize: 18,
            color: d.spread > 0.3 ? "#ef4444" : d.spread > 0.2 ? "#f59e0b" : "#3b82f6",
          }}
        >
          {(d.spread * 100).toFixed(1)}% spread
        </span>
      </div>

      <div style={{ display: "flex", gap: 16, marginBottom: 10 }}>
        {sourceEntries.map(([source, prob]) => {
          const detail = d.source_details?.[source];
          return (
            <div key={source} style={{ flex: 1 }}>
              <div style={{ fontSize: 11, color: "#888", textTransform: "capitalize", marginBottom: 2 }}>
                {source}
              </div>
              <div style={{ position: "relative", height: 24, background: "#0f0f23", borderRadius: 6, overflow: "hidden" }}>
                <div
                  style={{
                    width: `${Math.min(prob * 100, 100)}%`,
                    height: "100%",
                    background:
                      source === maxSource[0]
                        ? "linear-gradient(90deg, #3b82f6, #60a5fa)"
                        : "linear-gradient(90deg, #475569, #64748b)",
                    borderRadius: 6,
                    transition: "width 0.3s",
                  }}
                />
                <span
                  style={{
                    position: "absolute",
                    right: 6,
                    top: 3,
                    fontSize: 12,
                    fontWeight: 600,
                    color: "#e2e8f0",
                  }}
                >
                  {(prob * 100).toFixed(1)}%
                </span>
              </div>
              {detail?.market_name && (
                <div style={{ fontSize: 10, color: "#64748b", marginTop: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {detail.market_name}
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
        <button
          onClick={handleDismiss}
          disabled={acting}
          style={{
            padding: "5px 14px",
            borderRadius: 6,
            border: "1px solid #64748b",
            background: "transparent",
            color: "#94a3b8",
            fontSize: 12,
            fontWeight: 600,
            cursor: acting ? "wait" : "pointer",
            opacity: acting ? 0.5 : 1,
          }}
        >
          Dismiss
        </button>
        <button
          onClick={handleExclude}
          disabled={acting}
          style={{
            padding: "5px 14px",
            borderRadius: 6,
            border: "1px solid #ef4444",
            background: "transparent",
            color: "#ef4444",
            fontSize: 12,
            fontWeight: 600,
            cursor: acting ? "wait" : "pointer",
            opacity: acting ? 0.5 : 1,
          }}
        >
          Exclude Team
        </button>
      </div>
    </div>
  );
}

function SparseTeamRow({
  s,
  league,
  onAction,
}: {
  s: SparseTeam;
  league: string;
  onAction: () => void;
}) {
  const [acting, setActing] = useState(false);

  const handleExclude = async () => {
    setActing(true);
    try {
      await postOverride(league, {
        override_type: "team_exclude",
        source_name: s.team,
        reason: `sparse_data: ${s.filled_columns}/${s.total_columns} columns filled`,
      });
      onAction();
    } finally {
      setActing(false);
    }
  };

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "10px 14px",
        background: "#1a1a2e",
        borderRadius: 8,
      }}
    >
      <div>
        <span style={{ fontWeight: 600, color: "#e2e8f0", textTransform: "capitalize" }}>
          {s.team}
        </span>
        <span style={{ marginLeft: 10, fontSize: 12, color: "#888" }}>
          {s.filled_columns}/{s.total_columns} columns filled
        </span>
        {s.championship_prob !== null && (
          <span style={{ marginLeft: 10, fontSize: 12, color: "#64748b" }}>
            championship: {(s.championship_prob * 100).toFixed(1)}%
          </span>
        )}
      </div>
      <button
        onClick={handleExclude}
        disabled={acting}
        style={{
          padding: "4px 12px",
          borderRadius: 6,
          border: "1px solid #ef4444",
          background: "transparent",
          color: "#ef4444",
          fontSize: 12,
          fontWeight: 600,
          cursor: acting ? "wait" : "pointer",
          opacity: acting ? 0.5 : 1,
        }}
      >
        Exclude
      </button>
    </div>
  );
}

function OverrideRow({
  o,
  league,
  onDelete,
}: {
  o: Override;
  league: string;
  onDelete: () => void;
}) {
  const [deleting, setDeleting] = useState(false);

  const handleDelete = async () => {
    setDeleting(true);
    try {
      await deleteOverride(league, o.id);
      onDelete();
    } finally {
      setDeleting(false);
    }
  };

  const typeColors: Record<string, string> = {
    team_alias: "#22c55e",
    team_exclude: "#ef4444",
    team_include: "#3b82f6",
    dismiss: "#64748b",
    market_column: "#f59e0b",
    source_trust: "#8b5cf6",
  };

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "10px 14px",
        background: "#1a1a2e",
        borderRadius: 8,
        borderLeft: `3px solid ${typeColors[o.type] || "#888"}`,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <span
          style={{
            padding: "2px 8px",
            borderRadius: 4,
            fontSize: 11,
            fontWeight: 700,
            background: "#2d2d4e",
            color: typeColors[o.type] || "#888",
          }}
        >
          {o.type.replace(/_/g, " ")}
        </span>
        <span style={{ fontWeight: 600, color: "#e2e8f0" }}>{o.source_name}</span>
        {o.target_name && (
          <>
            <span style={{ color: "#64748b" }}>&rarr;</span>
            <span style={{ fontWeight: 600, color: "#93c5fd" }}>{o.target_name}</span>
          </>
        )}
        <span
          style={{
            padding: "2px 6px",
            borderRadius: 4,
            fontSize: 10,
            background: o.decision === "approved" ? "#14532d" : "#7f1d1d",
            color: o.decision === "approved" ? "#4ade80" : "#fca5a5",
          }}
        >
          {o.decision}
        </span>
      </div>
      <button
        onClick={handleDelete}
        disabled={deleting}
        style={{
          padding: "4px 10px",
          borderRadius: 6,
          border: "1px solid #475569",
          background: "transparent",
          color: "#94a3b8",
          fontSize: 12,
          cursor: deleting ? "wait" : "pointer",
          opacity: deleting ? 0.5 : 1,
        }}
      >
        Remove
      </button>
    </div>
  );
}

function AddOverrideForm({
  league,
  onAdded,
}: {
  league: string;
  onAdded: () => void;
}) {
  const [type, setType] = useState("team_alias");
  const [sourceName, setSourceName] = useState("");
  const [targetName, setTargetName] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!sourceName.trim()) return;
    setSubmitting(true);
    try {
      await postOverride(league, {
        override_type: type,
        source_name: sourceName.trim(),
        target_name: (type === "team_alias" || type === "market_column") ? targetName.trim() || undefined : undefined,
      });
      setSourceName("");
      setTargetName("");
      onAdded();
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
      <select
        value={type}
        onChange={(e) => setType(e.target.value)}
        style={{
          padding: "6px 10px",
          borderRadius: 6,
          border: "1px solid #333",
          background: "#0f0f23",
          color: "#e2e8f0",
          fontSize: 13,
        }}
      >
        <option value="team_alias">Alias (merge names)</option>
        <option value="team_exclude">Exclude team</option>
        <option value="team_include">Include team</option>
        <option value="market_column">Reassign market column</option>
        <option value="dismiss">Dismiss (mark reviewed)</option>
      </select>
      <input
        value={sourceName}
        onChange={(e) => setSourceName(e.target.value)}
        placeholder="Source name (e.g. uconn)"
        style={{
          padding: "6px 10px",
          borderRadius: 6,
          border: "1px solid #333",
          background: "#0f0f23",
          color: "#e2e8f0",
          fontSize: 13,
          width: 180,
        }}
      />
      {(type === "team_alias" || type === "market_column") && (
        <>
          <span style={{ color: "#64748b" }}>&rarr;</span>
          <input
            value={targetName}
            onChange={(e) => setTargetName(e.target.value)}
            placeholder="Target name (e.g. connecticut huskies)"
            style={{
              padding: "6px 10px",
              borderRadius: 6,
              border: "1px solid #333",
              background: "#0f0f23",
              color: "#e2e8f0",
              fontSize: 13,
              width: 220,
            }}
          />
        </>
      )}
      <button
        type="submit"
        disabled={submitting || !sourceName.trim()}
        style={{
          padding: "6px 16px",
          borderRadius: 6,
          border: "none",
          background: "#3b82f6",
          color: "#fff",
          fontSize: 13,
          fontWeight: 600,
          cursor: submitting ? "wait" : "pointer",
          opacity: submitting || !sourceName.trim() ? 0.5 : 1,
        }}
      >
        Add
      </button>
    </form>
  );
}

// ─── Main Page ───────────────────────────────────────────────────────────────

export default function MatchingReviewPage() {
  usePageTracking({ pageType: "admin_matching", pageTitle: "Admin: Matching Review" });
  useScrollDepth({ pageType: "admin_matching" });
  useEngagementTime({ pageType: "admin_matching" });

  const { secret } = useAdminAuth();
  const [league, setLeague] = useState("nba");

  const swrKey = `matching-review-${league}-${secret}`;
  const { data, error, isLoading } = useSWR(swrKey, () => fetchReview(league, secret), {
    refreshInterval: 0,
    revalidateOnFocus: false,
  });

  const refresh = useCallback(() => {
    if (swrKey) mutate(swrKey);
  }, [swrKey]);



  return (
    <div
      style={{
        maxWidth: 900,
        margin: "0 auto",
        padding: "32px 16px",
        fontFamily: "system-ui, -apple-system, sans-serif",
        color: "#e2e8f0",
        minHeight: "100vh",
        background: "#09090b",
      }}
    >
      <div style={{ marginBottom: 24 }}>
<PageHeader
          question="Do sources agree on team probabilities?"
          status={isLoading ? "loading" : data && data.divergences.length > 0 ? "warning" : "good"}
          summary={isLoading ? "Loading..." : data ? `${data.divergences.length} divergences across ${data.stats.team_count} teams` : "No data"}
          ideal="Zero cross-source divergences above 15pp."
        />
        <p style={{ color: "#64748b", fontSize: 13, margin: "4px 0 0" }}>
          Review and correct cross-source matching for championship grids
        </p>
      </div>

      <LeagueTabs selected={league} onSelect={setLeague} />

      {isLoading && (
        <div style={{ textAlign: "center", padding: 40, color: "#64748b" }}>Loading...</div>
      )}

      {error && (
        <div style={{ textAlign: "center", padding: 40, color: "#ef4444" }}>
          Failed to load: {error.message}
        </div>
      )}

      {data && (
        <>
          {/* Stats */}
          <div style={{ display: "flex", gap: 12, marginBottom: 28, flexWrap: "wrap" }}>
            <StatCard label="Teams in Grid" value={data.total_teams} />
            <StatCard label="Columns" value={data.total_columns} />
            <StatCard
              label="Divergences"
              value={data.divergence_count}
              color={data.divergence_count > 0 ? "#f59e0b" : "#4ade80"}
            />
            <StatCard
              label="Sparse Teams"
              value={data.sparse_count}
              color={data.sparse_count > 0 ? "#f59e0b" : "#4ade80"}
            />
            <StatCard label="Overrides" value={data.overrides.length} color="#93c5fd" />
          </div>

          {/* Active Overrides */}
          <section style={{ marginBottom: 32 }}>
            <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 10, color: "#93c5fd" }}>
              Active Overrides ({data.overrides.length})
            </h2>
            {data.overrides.length === 0 ? (
              <div style={{ color: "#64748b", fontSize: 13, padding: "8px 0" }}>
                No overrides set. Use the form below or action buttons to create them.
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {data.overrides.map((o) => (
                  <OverrideRow key={o.id} o={o} league={league} onDelete={refresh} />
                ))}
              </div>
            )}
            <div style={{ marginTop: 12 }}>
              <AddOverrideForm league={league} onAdded={refresh} />
            </div>
          </section>

          {/* Cross-Source Divergences */}
          {data.divergences.length > 0 && (
            <section style={{ marginBottom: 32 }}>
              <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 10, color: "#f59e0b" }}>
                Cross-Source Divergences ({data.divergences.length})
              </h2>
              <p style={{ color: "#64748b", fontSize: 12, marginBottom: 10 }}>
                Teams where sources disagree by &gt;15%. Red = &gt;30%, orange = &gt;20%, blue = &gt;15%.
              </p>
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {data.divergences.map((d, i) => (
                  <DivergenceCard key={`${d.team}-${d.column}-${i}`} d={d} league={league} onAction={refresh} />
                ))}
              </div>
            </section>
          )}

          {/* Sparse Teams */}
          {data.sparse_teams.length > 0 && (
            <section style={{ marginBottom: 32 }}>
              <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 10, color: "#94a3b8" }}>
                Sparse Teams ({data.sparse_teams.length})
              </h2>
              <p style={{ color: "#64748b", fontSize: 12, marginBottom: 10 }}>
                Teams with data in 2 or fewer columns. Might not belong in this league&apos;s grid.
              </p>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {data.sparse_teams.map((s) => (
                  <SparseTeamRow key={s.team} s={s} league={league} onAction={refresh} />
                ))}
              </div>
            </section>
          )}

          {/* All clear */}
          {data.divergences.length === 0 && data.sparse_teams.length === 0 && (
            <div
              style={{
                textAlign: "center",
                padding: 40,
                background: "#1a1a2e",
                borderRadius: 12,
                color: "#4ade80",
              }}
            >
              <div style={{ fontSize: 32, marginBottom: 8 }}>All clear</div>
              <div style={{ color: "#64748b", fontSize: 14 }}>
                No divergences or sparse teams detected for {league.toUpperCase()}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
