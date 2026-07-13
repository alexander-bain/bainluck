"use client";

import { useState } from "react";
import Link from "next/link";
import useSWR from "swr";
import { useAdminAuth } from "@/components/admin/AdminAuthProvider";
import { adminFetch, adminFetchJSON } from "@/lib/adminFetch";

// --- Types (matches GET /api/admin/cockpit) ---

interface TileContext {
  label: string;
  value: string;
  kind: "tracked" | "artifact" | "untracked";
  note: string | null;
  ref: string | null;
  url: string | null;
}

interface HealthTile {
  key: string;
  label: string;
  value: string;
  numeric: number | null;
  status: "green" | "amber" | "red" | "unknown";
  detail?: string | null;
  context?: TileContext[];
  href: string;
}

interface WaitingItem {
  ref: string;
  title: string;
  action: string;
  url: string;
}

interface EvalSample {
  id: number;
  item_name: string | null;
  category: string | null;
  decision: string;
  created_at: string | null;
}

interface FlowSentinelFlow {
  flow: string;
  passed: boolean;
  skipped: boolean;
  checked: number | null;
  failing: number | null;
  status: "green" | "amber" | "red";
  issue: number | null;
  issue_url: string | null;
}

interface FlowSentinelData {
  status: "green" | "amber" | "red" | "unknown";
  mode?: string | null;
  flows_total?: number | null;
  flows_passed?: number | null;
  flows_failed?: number | null;
  duration_seconds?: number | null;
  detail?: string | null;
  per_flow: FlowSentinelFlow[];
}

interface CockpitData {
  generated_at: string;
  cached: boolean;
  health: HealthTile[];
  waiting_on_you: { source: string; items: WaitingItem[] };
  eval_queue: {
    pending_eval_count: number;
    pending_eval_sample: EvalSample[];
    new_bug_reports: number;
    verdict_endpoint: string;
    eval_href: string;
    bug_reports_href: string;
  };
  flow_sentinel?: FlowSentinelData;
}

// --- Status → design-system colors ---

function statusText(status: string): string {
  switch (status) {
    case "green": return "text-green-600";
    case "amber": return "text-yellow-500";
    case "red": return "text-accent-danger";
    default: return "text-text-muted";
  }
}

function statusBg(status: string): string {
  switch (status) {
    case "green": return "bg-green-500/10 border-green-500/20";
    case "amber": return "bg-yellow-500/10 border-yellow-500/20";
    case "red": return "bg-accent-danger/10 border-accent-danger/20";
    default: return "bg-surface-card border-surface-border";
  }
}

function dotBg(status: string): string {
  switch (status) {
    case "green": return "bg-green-500";
    case "amber": return "bg-yellow-500";
    case "red": return "bg-accent-danger";
    default: return "bg-text-muted";
  }
}

// L2-104 honesty pass: a RED sub-signal reads as one of three things. Tracked =
// there's an open issue (link it). Artifact = a known/expected zero (label it,
// muted). Untracked = neither → the ONLY true four-alarm state, made visually
// distinct (danger ring + ⚠) so it can't hide among explained REDs.
function ContextBadge({ c }: { c: TileContext }) {
  if (c.kind === "tracked") {
    return (
      <a
        href={c.url ?? "#"}
        target="_blank"
        rel="noopener noreferrer"
        title={c.note ?? undefined}
        className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-micro font-medium bg-yellow-500/10 text-yellow-600 hover:bg-yellow-500/20"
      >
        {c.label} {c.value} — tracked {c.ref}
      </a>
    );
  }
  if (c.kind === "artifact") {
    return (
      <span
        title={c.note ?? undefined}
        className="inline-flex items-center rounded-md px-1.5 py-0.5 text-micro font-medium bg-surface-elevated text-text-muted"
      >
        {c.label} {c.value} — {c.note ?? "expected"}
      </span>
    );
  }
  // untracked — the true four-alarm state
  return (
    <span className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-micro font-bold bg-accent-danger/15 text-accent-danger ring-1 ring-accent-danger/40">
      ⚠ {c.label} {c.value} — untracked
    </span>
  );
}

export default function AdminCockpit() {
  const { secret } = useAdminAuth();
  const { data, error, isLoading, mutate } = useSWR<CockpitData>(
    secret ? ["admin-cockpit", secret] : null,
    () => adminFetchJSON<CockpitData>("/api/admin/cockpit", secret),
    { refreshInterval: 300000 }
  );

  const [busyId, setBusyId] = useState<number | null>(null);

  async function submitVerdict(decisionId: number, verdict: "accept" | "reject" | "skip") {
    if (!secret) return;
    setBusyId(decisionId);
    try {
      await adminFetch("/api/admin/label-pass/verdict", secret, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision_id: decisionId, verdict, features: {} }),
      });
      await mutate();
    } catch {
      // Non-fatal: leave the row; next refresh reconciles.
    } finally {
      setBusyId(null);
    }
  }

  if (error) {
    return (
      <div className="rounded-xl border border-accent-danger/20 bg-accent-danger/10 p-4 text-sm text-accent-danger">
        Cockpit failed to load: {error.message}
      </div>
    );
  }

  if (isLoading || !data) {
    return (
      <div className="rounded-xl border border-surface-border bg-surface-card p-4 text-sm text-text-muted animate-pulse">
        Loading cockpit…
      </div>
    );
  }

  const evalQ = data.eval_queue;
  const fs = data.flow_sentinel;

  return (
    <div className="space-y-4">
      <div className="flex items-baseline justify-between">
        <h2 className="text-lg font-bold text-text-primary">Cockpit</h2>
        <span className="text-micro text-text-muted">
          {data.cached ? "cached" : "fresh"} · {new Date(data.generated_at).toLocaleTimeString()}
        </span>
      </div>

      {/* Top strip: health tiles */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {data.health.map((t) => (
          <div key={t.key} className={"rounded-xl border p-4 " + statusBg(t.status)}>
            {/* Card headline navigates to the drill-in; context badges below are
                their own links, so the card is NOT a single anchor (nested <a>). */}
            <Link href={t.href} className="block transition-colors hover:brightness-105">
              <div className="text-micro text-text-muted uppercase tracking-wider">{t.label}</div>
              <div className={"text-2xl font-bold mt-1 " + statusText(t.status)}>{t.value}</div>
              {t.detail && <div className="text-micro text-text-muted mt-1 leading-relaxed">{t.detail}</div>}
            </Link>
            {t.context && t.context.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1">
                {t.context.map((c) => (
                  <ContextBadge key={c.label} c={c} />
                ))}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Middle: waiting on you */}
      <div className="rounded-xl border border-surface-border bg-surface-card p-4">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-semibold text-text-primary">Waiting on you</h3>
          <span className="text-micro text-text-muted">
            {data.waiting_on_you.source === "github" ? "live from GitHub" : "standing items"}
          </span>
        </div>
        {data.waiting_on_you.items.length === 0 ? (
          <div className="text-sm text-text-muted">Nothing waiting — you&apos;re clear.</div>
        ) : (
          <ul className="space-y-2">
            {data.waiting_on_you.items.map((w) => (
              <li key={w.ref} className="flex items-start gap-2 text-sm">
                <span className="text-micro font-mono text-text-muted mt-0.5 shrink-0">{w.ref}</span>
                <span className="text-text-secondary flex-1">{w.action}</span>
                {w.url && (
                  <a
                    href={w.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-accent-brand hover:underline shrink-0"
                  >
                    open
                  </a>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Bottom: quick eval queue */}
      <div className="rounded-xl border border-surface-border bg-surface-card p-4">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-semibold text-text-primary">Quick eval queue</h3>
          <div className="flex gap-3 text-micro">
            <Link href={evalQ.eval_href} className="text-accent-brand hover:underline">
              {evalQ.pending_eval_count} pending
            </Link>
            <Link href={evalQ.bug_reports_href} className="text-accent-brand hover:underline">
              {evalQ.new_bug_reports} new bugs
            </Link>
          </div>
        </div>

        {evalQ.pending_eval_sample.length === 0 ? (
          <div className="text-sm text-text-muted">No LLM proposals waiting for your call.</div>
        ) : (
          <ul className="space-y-1.5">
            {evalQ.pending_eval_sample.map((item) => (
              <li
                key={item.id}
                className="flex items-center gap-2 text-sm py-1.5 border-b border-surface-border last:border-0"
              >
                <span className="flex-1 min-w-0">
                  <span className="text-text-primary truncate block">
                    {item.item_name || `#${item.id}`}
                  </span>
                  <span className="text-micro text-text-muted">
                    {item.decision.replace("llm_proposed_", "proposed ")}
                    {item.category ? ` · ${item.category}` : ""}
                  </span>
                </span>
                <div className="flex gap-1 shrink-0">
                  <button
                    onClick={() => submitVerdict(item.id, "accept")}
                    disabled={busyId === item.id}
                    className="px-2 py-1 rounded-md text-micro font-medium bg-green-500/10 text-green-600 hover:bg-green-500/20 disabled:opacity-50"
                  >
                    Accept
                  </button>
                  <button
                    onClick={() => submitVerdict(item.id, "reject")}
                    disabled={busyId === item.id}
                    className="px-2 py-1 rounded-md text-micro font-medium bg-accent-danger/10 text-accent-danger hover:bg-accent-danger/20 disabled:opacity-50"
                  >
                    Reject
                  </button>
                  <button
                    onClick={() => submitVerdict(item.id, "skip")}
                    disabled={busyId === item.id}
                    className="px-2 py-1 rounded-md text-micro font-medium text-text-muted hover:bg-surface-elevated disabled:opacity-50"
                  >
                    Skip
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Flow Sentinel scorecard (per-flow pass/fail; click → filed issue) */}
      {fs && (
        <div className="rounded-xl border border-surface-border bg-surface-card p-4">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-semibold text-text-primary">Flow Sentinel</h3>
            <span className={"text-micro font-medium " + statusText(fs.status)}>
              {fs.flows_total != null
                ? `${fs.flows_passed ?? 0}/${fs.flows_total} flows passing`
                : "no run cached"}
            </span>
          </div>
          {fs.per_flow.length === 0 ? (
            <div className="text-sm text-text-muted">
              {fs.detail || "No Flow Sentinel run cached yet."}
            </div>
          ) : (
            <ul className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1.5">
              {fs.per_flow.map((f) => (
                <li key={f.flow} className="flex items-center gap-2 text-sm py-0.5">
                  <span className={"h-2 w-2 rounded-full shrink-0 " + dotBg(f.status)} />
                  <span className="text-text-secondary flex-1 truncate">
                    {f.flow.replace(/_/g, " ")}
                    {f.skipped ? " (skipped)" : ""}
                  </span>
                  <span className="text-micro text-text-muted shrink-0">
                    {f.failing
                      ? `${f.failing} failing`
                      : f.checked != null
                      ? `${f.checked} ok`
                      : ""}
                  </span>
                  {f.issue_url && (
                    <a
                      href={f.issue_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-accent-brand hover:underline shrink-0"
                    >
                      #{f.issue}
                    </a>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
