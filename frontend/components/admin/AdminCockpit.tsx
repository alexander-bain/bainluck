"use client";

import { useState } from "react";
import Link from "next/link";
import useSWR from "swr";
import { useAdminAuth } from "@/components/admin/AdminAuthProvider";
import { adminFetch, adminFetchJSON } from "@/lib/adminFetch";
import { trackEvent } from "@/lib/analytics";
import FileThisButton from "@/components/admin/FileThisButton";

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

// L2-140 Item 1 — the data-quality watchdog RED tile (display half). The server
// half (#218 Item 3) mirrors _flow_sentinel_group(): it persists the P0/P1
// watchdog results and shapes them into this `data_quality_watchdog` group on
// the cockpit payload — one row per FAILING check with its severity, the action
// sentence (message), and the auto-filed GitHub issue link. This tile renders
// them so an "email-only P0" can no longer hide: a firing alert is RED and
// on-screen. Absent key (server half not deployed yet) → the card simply
// doesn't render.
interface DataQualityWatchdogCheck {
  name: string;
  severity: string; // "P0" | "P1"
  message: string; // the action sentence
  value: number | null;
  threshold: number | null;
  status: "green" | "amber" | "red";
  issue: number | null;
  issue_url: string | null;
}

interface DataQualityWatchdogData {
  status: "green" | "amber" | "red" | "unknown";
  detail?: string | null;
  checks_run?: number | null;
  checks_passed?: number | null;
  alerts_fired?: number | null;
  last_run?: string | null;
  // Set when the watchdog itself errored (monitor unreliable → amber).
  self_error?: boolean | string | null;
  per_check: DataQualityWatchdogCheck[];
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
  data_quality_watchdog?: DataQualityWatchdogData;
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

// L2-128 Item 2c — THE ACTION RULE: no non-green tile is allowed to be a dead
// end. Every amber/red/unknown tile gets a sentence — what it means + what to do
// + the tracked issue if one exists. An untracked RED sub-signal is the true
// four-alarm state and says so; "needs attention" with no pointer is banned.
function tileAction(t: HealthTile): { text: string; tone: "danger" | "warn" | "muted" } | null {
  if (t.status === "green") return null;
  const ctx = t.context ?? [];
  const tracked = ctx.filter((c) => c.kind === "tracked");
  const untracked = ctx.filter((c) => c.kind === "untracked");
  if (t.status === "unknown") {
    return { text: `No data yet — open ${t.label} to confirm the source is reporting.`, tone: "muted" };
  }
  if (untracked.length > 0) {
    return {
      text: `Untracked: ${untracked.map((c) => `${c.label} ${c.value}`).join(", ")} — investigate and file an issue. This isn't explained yet.`,
      tone: "danger",
    };
  }
  if (tracked.length > 0) {
    const refs = tracked.map((c) => c.ref).filter(Boolean).join(", ");
    return {
      text: `Being worked${refs ? ` — see ${refs} above` : " — see the tracked issue above"}.`,
      tone: "warn",
    };
  }
  return {
    text: `${t.detail ? `${t.detail} — ` : ""}Open ${t.label} to investigate.`,
    tone: t.status === "red" ? "danger" : "warn",
  };
}

// A red/amber tile "lacking a linked issue" (L2-142 Item 1) = one with no
// tracked context badge. Those get the one-tap File-this rail; tiles already
// tracked link to their open issue instead.
function tileHasIssue(t: HealthTile): boolean {
  return (t.context ?? []).some((c) => c.kind === "tracked" && !!c.ref);
}

function tileSeverity(status: string): string {
  return status === "red" ? "P1" : "P2";
}

// Body for a one-tap filing from a health tile — the tile's own action sentence
// is the best first line of "what to do".
function tileFileBody(t: HealthTile): string {
  const a = tileAction(t);
  return [
    `**${t.label}** is ${t.status.toUpperCase()} — ${t.value}.`,
    t.detail ? `\n${t.detail}` : "",
    a ? `\n\n${a.text}` : "",
    `\n\nSurfaced by the Alex cockpit (${t.href}).`,
  ].join("");
}

export default function AdminCockpit() {
  const { secret } = useAdminAuth();
  const { data, error, isLoading, mutate } = useSWR<CockpitData>(
    secret ? ["admin-cockpit", secret] : null,
    () => adminFetchJSON<CockpitData>("/api/admin/cockpit", secret),
    { refreshInterval: 300000 }
  );

  const [busyId, setBusyId] = useState<number | null>(null);

  async function submitVerdict(
    item: EvalSample,
    verdict: "accept" | "reject" | "skip",
  ) {
    if (!secret) return;
    setBusyId(item.id);
    try {
      await adminFetch("/api/admin/label-pass/verdict", secret, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision_id: item.id, verdict, features: {} }),
      });
      // Cockpit (Alex-ops) funnel (measurement_spec §2). `applied:false` until
      // #222 wires Accept to a real Discover-scoring term — the event ships now
      // so verdict volume is measured from day one.
      trackEvent("eval_verdict", {
        verdict,
        decision_id: item.id,
        proposal: item.decision.replace("llm_proposed_", ""),
        item_name: item.item_name ?? undefined,
        category: item.category ?? undefined,
        applied: false,
        surface: "cockpit",
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
  const dqw = data.data_quality_watchdog;

  // L2-142 Item 2 — reds-with-actions first. Everything that needs someone's
  // attention (non-green tiles + firing watchdog checks + failing flows) is
  // hoisted into ONE strip at the very top so the first screenful answers
  // "what needs attention." Green tiles and full detail stay below.
  const attentionTiles = data.health.filter((t) => t.status === "red" || t.status === "amber");
  const firingChecks = (dqw?.per_check ?? []).filter((c) => c.status === "red");
  const failingFlows = (fs?.per_flow ?? []).filter((f) => f.status === "red" && !f.skipped);
  const attentionCount = attentionTiles.length + firingChecks.length + failingFlows.length;

  return (
    <div className="space-y-4">
      <div className="flex items-baseline justify-between">
        <h2 className="text-lg font-bold text-text-primary">Cockpit</h2>
        <span className="text-micro text-text-muted">
          {data.cached ? "cached" : "fresh"} · {new Date(data.generated_at).toLocaleTimeString()}
        </span>
      </div>

      {/* Needs attention (L2-142 Item 2) — reds-with-actions, first. */}
      <div
        className={
          "rounded-xl border p-4 " +
          (attentionCount > 0
            ? "border-accent-danger/40 bg-accent-danger/5"
            : "border-green-500/20 bg-green-500/5")
        }
      >
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-semibold text-text-primary">Needs attention</h3>
          <span
            className={
              "text-micro font-medium " + (attentionCount > 0 ? "text-accent-danger" : "text-green-600")
            }
          >
            {attentionCount > 0 ? `${attentionCount} to handle` : "all clear"}
          </span>
        </div>
        {attentionCount === 0 ? (
          <div className="text-sm text-text-muted">
            Nothing red or amber — the site is doing what it&apos;s supposed to.
          </div>
        ) : (
          <ul className="space-y-2">
            {attentionTiles.map((t) => {
              const a = tileAction(t);
              const tracked = (t.context ?? []).find((c) => c.kind === "tracked" && !!c.ref);
              return (
                <li key={`tile-${t.key}`} className="flex items-start gap-2 text-sm">
                  <span className={"h-2 w-2 rounded-full shrink-0 mt-1.5 " + dotBg(t.status)} />
                  <span className="flex-1 min-w-0">
                    <Link href={t.href} className="text-text-primary font-medium hover:underline">
                      {t.label}: {t.value}
                    </Link>
                    {a && <span className="text-micro text-text-muted block leading-relaxed">{a.text}</span>}
                  </span>
                  {tracked ? (
                    <a
                      href={tracked.url ?? "#"}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-accent-brand hover:underline shrink-0 text-micro mt-0.5"
                    >
                      {tracked.ref}
                    </a>
                  ) : (
                    <FileThisButton
                      compact
                      source="cockpit_tile"
                      itemKey={t.key}
                      title={`${t.label} ${t.status.toUpperCase()}: ${t.value}`}
                      body={tileFileBody(t)}
                      severity={tileSeverity(t.status)}
                      labels={["area:infra"]}
                    />
                  )}
                </li>
              );
            })}
            {firingChecks.map((c) => (
              <li key={`check-${c.name}`} className="flex items-start gap-2 text-sm">
                <span className="h-2 w-2 rounded-full shrink-0 mt-1.5 bg-accent-danger" />
                <span className="flex-1 min-w-0">
                  <span className="text-text-primary font-medium block">
                    {c.severity} · {c.name.replace(/_/g, " ")}
                  </span>
                  <span className="text-micro text-text-muted block leading-relaxed">{c.message}</span>
                </span>
                {c.issue_url ? (
                  <a
                    href={c.issue_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-accent-brand hover:underline shrink-0 text-micro mt-0.5"
                  >
                    #{c.issue}
                  </a>
                ) : (
                  <FileThisButton
                    compact
                    source="watchdog_check"
                    itemKey={c.name}
                    title={`[${c.severity}] ${c.name.replace(/_/g, " ")}`}
                    body={c.message}
                    severity={c.severity}
                    labels={["area:data"]}
                  />
                )}
              </li>
            ))}
            {failingFlows.map((f) => (
              <li key={`flow-${f.flow}`} className="flex items-start gap-2 text-sm">
                <span className="h-2 w-2 rounded-full shrink-0 mt-1.5 bg-accent-danger" />
                <span className="flex-1 min-w-0">
                  <span className="text-text-primary font-medium block">
                    Flow failing · {f.flow.replace(/_/g, " ")}
                  </span>
                  <span className="text-micro text-text-muted block leading-relaxed">
                    {f.failing} failing of {f.checked ?? "?"} checked.
                  </span>
                </span>
                {f.issue_url ? (
                  <a
                    href={f.issue_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-accent-brand hover:underline shrink-0 text-micro mt-0.5"
                  >
                    #{f.issue}
                  </a>
                ) : (
                  <FileThisButton
                    compact
                    source="flow_sentinel"
                    itemKey={f.flow}
                    title={`Flow failing: ${f.flow.replace(/_/g, " ")}`}
                    body={`${f.failing} failing of ${f.checked ?? "?"} checked in the ${f.flow} flow.`}
                    severity="P1"
                    labels={["area:infra"]}
                  />
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Detail strip: all health tiles */}
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
            {/* THE ACTION RULE (L2-128 Item 2c): non-green tiles always carry an action sentence. */}
            {(() => {
              const a = tileAction(t);
              if (!a) return null;
              const cls =
                a.tone === "danger"
                  ? "text-accent-danger"
                  : a.tone === "warn"
                    ? "text-yellow-600"
                    : "text-text-muted";
              return <div className={"mt-2 text-micro leading-relaxed " + cls}>{a.text}</div>;
            })()}
            {/* L2-142 Item 1 — a red/amber tile with no linked issue gets the
                one-tap rail. Tiles already tracked show their issue badge above. */}
            {(t.status === "red" || t.status === "amber") && !tileHasIssue(t) && (
              <div className="mt-2">
                <FileThisButton
                  compact
                  source="cockpit_tile"
                  itemKey={t.key}
                  title={`${t.label} ${t.status.toUpperCase()}: ${t.value}`}
                  body={tileFileBody(t)}
                  severity={tileSeverity(t.status)}
                  labels={["area:infra"]}
                />
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
        <div className="flex items-center justify-between mb-1">
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
        {/* L2-142 Item 4 — honest copy until #222 (the eval-promote build) lands.
            Every verdict already trains the interestingness scorer; Accept does
            not yet steer Discover ranking. Flips to the "promotes + trains"
            wording (and applied:true) the moment #222 ships. */}
        <p className="text-micro text-text-muted mb-2 leading-relaxed">
          Verdicts train the ranking scorer. Applying them live in Discover is
          rolling out (#222).
        </p>

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
                    onClick={() => submitVerdict(item, "accept")}
                    disabled={busyId === item.id}
                    className="px-2 py-1 rounded-md text-micro font-medium bg-green-500/10 text-green-600 hover:bg-green-500/20 disabled:opacity-50"
                  >
                    Accept
                  </button>
                  <button
                    onClick={() => submitVerdict(item, "reject")}
                    disabled={busyId === item.id}
                    className="px-2 py-1 rounded-md text-micro font-medium bg-accent-danger/10 text-accent-danger hover:bg-accent-danger/20 disabled:opacity-50"
                  >
                    Reject
                  </button>
                  <button
                    onClick={() => submitVerdict(item, "skip")}
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

      {/* Data-quality watchdog (L2-140 Item 1): P0/P1 alerts as a RED tile with
          the action sentence + filed-issue link. A firing alert can no longer
          be an "email-only P0" — it's on-screen and RED. Card is loud when
          alerting (danger border), quiet green when all checks pass. */}
      {dqw && (
        <div
          className={
            "rounded-xl border p-4 " +
            (dqw.status === "red"
              ? "border-accent-danger/40 bg-accent-danger/10"
              : "border-surface-border bg-surface-card")
          }
        >
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
              <span className={"h-2 w-2 rounded-full shrink-0 " + dotBg(dqw.status)} />
              Data-quality watchdog
            </h3>
            <span className={"text-micro font-medium " + statusText(dqw.status)}>
              {dqw.status === "red"
                ? `${dqw.alerts_fired ?? dqw.per_check.filter((c) => c.status === "red").length} alert${
                    (dqw.alerts_fired ?? dqw.per_check.length) === 1 ? "" : "s"
                  } firing`
                : dqw.checks_run != null
                ? `${dqw.checks_passed ?? 0}/${dqw.checks_run} checks passing`
                : dqw.status === "unknown"
                ? "no run cached"
                : "all clear"}
            </span>
          </div>
          {dqw.self_error && (
            <div className="mb-2 text-micro text-yellow-600 leading-relaxed">
              ⚠ Watchdog self-error — the monitor may be unreliable right now.
              Treat GREEN with suspicion until this clears.
            </div>
          )}
          {dqw.per_check.length === 0 ? (
            <div className="text-sm text-text-muted">
              {dqw.detail ||
                (dqw.status === "unknown"
                  ? "No watchdog run cached yet — it runs every 2h."
                  : "All data-quality checks passing.")}
            </div>
          ) : (
            <ul className="space-y-1.5">
              {dqw.per_check.map((c) => (
                <li
                  key={c.name}
                  className="flex items-start gap-2 text-sm py-1 border-b border-surface-border last:border-0"
                >
                  <span
                    className={
                      "shrink-0 mt-0.5 rounded px-1.5 py-0.5 text-micro font-bold " +
                      (c.severity === "P0"
                        ? "bg-accent-danger/15 text-accent-danger"
                        : "bg-yellow-500/15 text-yellow-600")
                    }
                  >
                    {c.severity}
                  </span>
                  <span className="flex-1 min-w-0">
                    <span className="text-text-primary block truncate">
                      {c.name.replace(/_/g, " ")}
                    </span>
                    {/* THE ACTION SENTENCE — what's wrong, from the check's message. */}
                    <span className="text-micro text-text-muted leading-relaxed block">
                      {c.message}
                    </span>
                  </span>
                  {c.issue_url ? (
                    <a
                      href={c.issue_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-accent-brand hover:underline shrink-0 mt-0.5"
                    >
                      #{c.issue}
                    </a>
                  ) : (
                    /* L2-142 Item 1 — was a dead "no issue" label; now the one-tap
                       rail so an email-only P0 becomes a filed issue in front of Alex. */
                    <span className="shrink-0 mt-0.5">
                      <FileThisButton
                        compact
                        source="watchdog_check"
                        itemKey={c.name}
                        title={`[${c.severity}] ${c.name.replace(/_/g, " ")}`}
                        body={c.message}
                        severity={c.severity}
                        labels={["area:data"]}
                      />
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

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
