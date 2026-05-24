"use client";

import { useState, type ReactNode } from "react";
import {
  AlertTriangle,
  ArrowRight,
  Bug,
  Database,
  ExternalLink,
  FlaskConical,
  GitPullRequestArrow,
  ImageIcon,
  Link2,
  PlusCircle,
  SlidersHorizontal,
  Sparkles,
  X,
} from "lucide-react";
import type { DiscoverFixableInterestCluster } from "./types";
import { StatusPill } from "./ui";
import { formatTargetName } from "./utils";

function issueNumberFromUrl(value: string) {
  const match = value.match(/\/issues\/(\d+)/);
  return match ? Number(match[1]) : undefined;
}

function statusTone(status: string) {
  if (status === "open") return "ok";
  if (status === "linked" || status === "experiment") return "muted";
  return "warn";
}

function issueLabels(cluster: DiscoverFixableInterestCluster) {
  const isBug = cluster.fix_type === "data_bug";
  return ["area:discover-ranking", isBug ? "type:bug" : "type:quality", "needs-agent"].join(",");
}

function newIssueUrl(cluster: DiscoverFixableInterestCluster) {
  const title = `Fixable Discover card: ${formatTargetName(cluster.fix_type)}`;
  const example = cluster.examples[0];
  const snapshot = example?.card_snapshot || {};
  const body = [
    `Parent: #587`,
    ``,
    `## Fixable-interest cluster`,
    `Cluster: \`${cluster.cluster_id}\``,
    `Fix type: \`${cluster.fix_type}\``,
    `Story/group: \`${cluster.story_key || cluster.group_id || cluster.family_key || cluster.item_key}\``,
    ``,
    `## Feedback`,
    cluster.would_be_interesting_if || "No feedback text captured.",
    ``,
    `Current: ${cluster.current_entity_or_variant || "unknown"}`,
    `Desired: ${cluster.desired_entity_or_variant || "unknown"}`,
    ``,
    `Labels: ${cluster.count}`,
    `Issue candidates: ${cluster.issue_candidate_count}`,
    `Max fixable score: ${cluster.max_fixable_interest_score ?? "n/a"}`,
    `Affected ranks: ${cluster.affected_ranks.join(", ") || "n/a"}`,
    `Market IDs: ${cluster.market_ids.join(", ") || "n/a"}`,
    ``,
    `## Representative card`,
    snapshotText(snapshot, "name") || example?.snapshot_name || example?.market_name || "Unknown card",
    `Rank: ${snapshotNumber(snapshot, "rank") ?? example?.rank_seen ?? "n/a"}`,
    `Source/category: ${[snapshotText(snapshot, "source"), snapshotText(snapshot, "category")].filter(Boolean).join(" / ") || "n/a"}`,
    `Headline: ${snapshotText(snapshot, "headline") || "n/a"}`,
    `Context: ${snapshotText(snapshot, "context") || snapshotText(snapshot, "reason") || snapshotText(snapshot, "hook_description") || "n/a"}`,
    `Quality reasons: ${snapshotStringList(snapshot, "reasons").join(", ") || "n/a"}`,
    ``,
    `## Acceptance Criteria`,
    `- Decide whether this is a data, design, or ranking fix.`,
    `- Update the affected card/cluster so future labels no longer produce this feedback.`,
    `- Re-run Discover label evals or verify via admin Review after the fix.`,
  ].join("\n");
  const params = new URLSearchParams({
    title,
    body,
    labels: issueLabels(cluster),
  });
  return `https://github.com/alexander-bain/bainluck/issues/new?${params}`;
}

function snapshotText(snapshot: Record<string, unknown>, key: string) {
  const value = snapshot[key];
  return typeof value === "string" && value.trim() ? value : null;
}

function snapshotNumber(snapshot: Record<string, unknown>, key: string) {
  const value = snapshot[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function snapshotBoolean(snapshot: Record<string, unknown>, key: string) {
  const value = snapshot[key];
  return typeof value === "boolean" ? value : null;
}

function snapshotStringList(snapshot: Record<string, unknown>, key: string) {
  const value = snapshot[key];
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function snapshotOutcomes(snapshot: Record<string, unknown>) {
  const value = snapshot.top_outcomes;
  if (!Array.isArray(value)) return [];
  return value
    .filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object" && !Array.isArray(item))
    .slice(0, 3);
}

function formatScore(value: number | null | undefined) {
  return value === null || value === undefined ? "n/a" : Math.round(value).toString();
}

function formatProbability(value: unknown) {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  const percentage = value <= 1 ? value * 100 : value;
  return `${Math.round(percentage)}%`;
}

function compactList<T>(items: T[], limit: number, empty = "n/a") {
  if (!items.length) return empty;
  const suffix = items.length > limit ? ` +${items.length - limit}` : "";
  return `${items.slice(0, limit).join(", ")}${suffix}`;
}

function clusterContext(cluster: DiscoverFixableInterestCluster) {
  return cluster.story_key || cluster.group_id || cluster.family_key || cluster.item_key;
}

function isBetterVariantFix(cluster: DiscoverFixableInterestCluster) {
  return Boolean(
    cluster.desired_entity_or_variant ||
      ["wrong_entity_rank", "wrong_market_variant", "duplicate_variant", "category_mismatch"].includes(cluster.fix_type)
  );
}

function SignalChip({
  tone,
  icon,
  label,
}: {
  tone: "bug" | "rule" | "variant" | "candidate" | "muted";
  icon: ReactNode;
  label: string;
}) {
  const classes =
    tone === "bug"
      ? "border-accent-danger/30 bg-accent-danger/10 text-accent-danger"
      : tone === "rule"
        ? "border-accent-brand/30 bg-accent-brand/10 text-accent-brand"
        : tone === "variant"
          ? "border-accent-live/30 bg-accent-live/10 text-accent-live"
          : tone === "candidate"
            ? "border-accent-futures/30 bg-accent-futures/10 text-accent-futures"
            : "border-surface-border bg-surface-elevated text-text-muted";

  return (
    <span className={`inline-flex items-center gap-1 rounded-md border px-2 py-1 text-[11px] font-medium ${classes}`}>
      {icon}
      {label}
    </span>
  );
}

export default function FixableInterestPanel({
  clusters,
  total,
  onDismiss,
  onLinkIssue,
  onMarkExperiment,
  updatingClusterId,
}: {
  clusters: DiscoverFixableInterestCluster[];
  total: number;
  onDismiss: (clusterId: string) => void;
  onLinkIssue: (clusterId: string, issueUrl: string) => void;
  onMarkExperiment: (clusterId: string, experimentKey: string) => void;
  updatingClusterId: string | null;
}) {
  const [issueUrls, setIssueUrls] = useState<Record<string, string>>({});
  const [experimentKeys, setExperimentKeys] = useState<Record<string, string>>({});

  return (
    <div className="bg-surface-card border border-surface-border rounded-lg p-4 space-y-3">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h2 className="text-sm font-semibold text-text-primary">Fixable Interest</h2>
          <p className="text-xs text-text-muted mt-1">
            Clusters from “would be interesting if...” labels, grouped by fix type and story context.
          </p>
        </div>
        <StatusPill tone={total ? "ok" : "muted"}>{`${total} open clusters`}</StatusPill>
      </div>

      {clusters.length ? (
        <div className="rounded-lg border border-surface-border overflow-hidden">
          <div className="hidden lg:grid grid-cols-[minmax(300px,1.25fr)_minmax(340px,1.45fr)_minmax(300px,1fr)] gap-3 bg-surface-elevated px-3 py-2 text-xs font-medium text-text-muted">
            <div>Cluster and signals</div>
            <div>Representative card</div>
            <div>Triage</div>
          </div>
          <div className="divide-y divide-surface-border/60">
            {clusters.map((cluster) => {
              const example = cluster.examples[0];
              const snapshot = example?.card_snapshot || {};
              const issueUrl = issueUrls[cluster.cluster_id] || "";
              const experimentKey = experimentKeys[cluster.cluster_id] || "";
              const updating = updatingClusterId === cluster.cluster_id;
              const imageUrl = snapshotText(snapshot, "image_url");
              const title = snapshotText(snapshot, "name") || example?.snapshot_name || example?.market_name || "Unknown card";
              const rank = snapshotNumber(snapshot, "rank") ?? example?.rank_seen;
              const score = snapshotNumber(snapshot, "score") ?? example?.score_at_review;
              const outcomes = snapshotOutcomes(snapshot);
              const context =
                snapshotText(snapshot, "context") ||
                snapshotText(snapshot, "reason") ||
                snapshotText(snapshot, "hook_description");
              const reasons = snapshotStringList(snapshot, "reasons");
              const hasHook = snapshotBoolean(snapshot, "has_hook");
              const hasImage = snapshotBoolean(snapshot, "has_image");
              const explanationOk = snapshotBoolean(snapshot, "explanation_ok");

              return (
                <div
                  key={cluster.cluster_id}
                  className="grid gap-3 p-3 hover:bg-surface-elevated/40 lg:grid-cols-[minmax(300px,1.25fr)_minmax(340px,1.45fr)_minmax(300px,1fr)]"
                >
                  <section className="min-w-0 space-y-2">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <StatusPill tone={statusTone(cluster.status)}>{formatTargetName(cluster.status)}</StatusPill>
                      <StatusPill tone="muted">{formatTargetName(cluster.fix_type)}</StatusPill>
                      {cluster.max_fixable_interest_score !== null && (
                        <StatusPill tone="ok">{`fix ${cluster.max_fixable_interest_score}`}</StatusPill>
                      )}
                    </div>

                    <div className="text-sm font-medium leading-snug text-text-primary">
                      {cluster.would_be_interesting_if || "No note captured"}
                    </div>

                    <div className="flex flex-wrap gap-1.5">
                      {cluster.issue_candidate_count > 0 && (
                        <SignalChip
                          tone="candidate"
                          icon={<GitPullRequestArrow className="h-3 w-3" />}
                          label={`${cluster.issue_candidate_count} issue candidate${cluster.issue_candidate_count === 1 ? "" : "s"}`}
                        />
                      )}
                      {cluster.fix_type === "data_bug" && (
                        <SignalChip tone="bug" icon={<Bug className="h-3 w-3" />} label="Data bug" />
                      )}
                      {cluster.fix_type === "ranking_rule" && (
                        <SignalChip tone="rule" icon={<SlidersHorizontal className="h-3 w-3" />} label="Ranking rule" />
                      )}
                      {isBetterVariantFix(cluster) && (
                        <SignalChip tone="variant" icon={<Sparkles className="h-3 w-3" />} label="Better variant" />
                      )}
                      {cluster.fix_type !== "data_bug" && cluster.fix_type !== "ranking_rule" && !isBetterVariantFix(cluster) && (
                        <SignalChip tone="muted" icon={<AlertTriangle className="h-3 w-3" />} label="Needs triage" />
                      )}
                    </div>

                    {(cluster.current_entity_or_variant || cluster.desired_entity_or_variant) && (
                      <div className="flex min-w-0 items-center gap-2 rounded-md border border-surface-border bg-surface-elevated px-2 py-1.5 text-xs">
                        <span className="truncate text-text-muted">{cluster.current_entity_or_variant || "current unknown"}</span>
                        <ArrowRight className="h-3.5 w-3.5 shrink-0 text-text-muted" />
                        <span className="truncate font-medium text-text-primary">
                          {cluster.desired_entity_or_variant || "desired unknown"}
                        </span>
                      </div>
                    )}

                    <div className="grid grid-cols-4 gap-2 text-xs">
                      <div>
                        <div className="font-semibold text-text-primary">{cluster.count}</div>
                        <div className="text-[11px] text-text-muted">labels</div>
                      </div>
                      <div>
                        <div className="font-semibold text-text-primary">{compactList(cluster.affected_ranks, 3)}</div>
                        <div className="text-[11px] text-text-muted">ranks</div>
                      </div>
                      <div>
                        <div className="font-semibold text-text-primary">{cluster.market_ids.length}</div>
                        <div className="text-[11px] text-text-muted">markets</div>
                      </div>
                      <div>
                        <div className="font-semibold text-text-primary">{cluster.categories.slice(0, 2).map(formatTargetName).join(", ") || "n/a"}</div>
                        <div className="text-[11px] text-text-muted">category</div>
                      </div>
                    </div>

                    <div className="truncate text-[11px] text-text-muted" title={clusterContext(cluster)}>
                      {clusterContext(cluster)}
                    </div>
                  </section>

                  <section className="min-w-0">
                    <div className="flex gap-3 rounded-md border border-surface-border bg-surface-card p-2">
                      <div className="relative h-20 w-24 shrink-0 overflow-hidden rounded-md border border-surface-border bg-surface-elevated">
                        {imageUrl ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img src={imageUrl} alt="" className="h-full w-full object-cover" />
                        ) : (
                          <div className="flex h-full w-full items-center justify-center text-text-muted">
                            <ImageIcon className="h-5 w-5" />
                          </div>
                        )}
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-text-muted">
                          <span>{rank ? `#${rank}` : "rank n/a"}</span>
                          <span>{snapshotText(snapshot, "source") || "source n/a"}</span>
                          <span>{formatTargetName(snapshotText(snapshot, "category") || "uncategorized")}</span>
                          <span>{`score ${formatScore(score)}`}</span>
                        </div>
                        <div className="mt-1 line-clamp-2 text-sm font-medium leading-snug text-text-primary">{title}</div>
                        {context && <div className="mt-1 line-clamp-2 text-xs leading-snug text-text-secondary">{context}</div>}
                        <div className="mt-2 flex flex-wrap gap-1.5">
                          {outcomes.map((outcome, index) => {
                            const name = typeof outcome.name === "string" && outcome.name ? outcome.name : `Outcome ${index + 1}`;
                            const probability = formatProbability(outcome.probability ?? outcome.current_probability);
                            return (
                              <span
                                key={`${name}-${index}`}
                                className="inline-flex items-center gap-1 rounded-md bg-surface-elevated px-1.5 py-0.5 text-[11px] text-text-secondary"
                              >
                                <span className="max-w-[120px] truncate">{name}</span>
                                {probability && <span className="font-medium text-text-primary">{probability}</span>}
                              </span>
                            );
                          })}
                          {reasons.slice(0, 2).map((reason) => (
                            <span
                              key={reason}
                              className="inline-flex items-center rounded-md bg-surface-elevated px-1.5 py-0.5 text-[11px] text-text-muted"
                            >
                              {formatTargetName(reason)}
                            </span>
                          ))}
                        </div>
                        <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-text-muted">
                          <span>{hasHook === null ? "hook n/a" : hasHook ? "hook yes" : "hook no"}</span>
                          <span>{hasImage === null ? "image n/a" : hasImage ? "image yes" : "image no"}</span>
                          <span>{explanationOk === null ? "explanation n/a" : explanationOk ? "explanation ok" : "explanation weak"}</span>
                        </div>
                      </div>
                    </div>
                    {example?.notes && (
                      <div className="mt-2 rounded-md bg-surface-elevated px-2 py-1.5 text-xs text-text-secondary">
                        {example.notes}
                      </div>
                    )}
                  </section>

                  <section className="min-w-0 space-y-2">
                    <div className="flex gap-2">
                      <input
                        type="url"
                        value={issueUrl}
                        onChange={(event) => setIssueUrls((prev) => ({
                          ...prev,
                          [cluster.cluster_id]: event.target.value,
                        }))}
                        placeholder="GitHub issue URL"
                        className="min-w-0 flex-1 rounded-lg border border-surface-border bg-surface-card px-3 py-2 text-xs text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-accent-brand/40"
                      />
                      <button
                        type="button"
                        disabled={!issueUrl.trim() || updating}
                        onClick={() => onLinkIssue(cluster.cluster_id, issueUrl.trim())}
                        className="inline-flex items-center justify-center rounded-lg border border-surface-border bg-surface-elevated p-2 text-text-secondary hover:text-text-primary disabled:opacity-50"
                        title="Link issue"
                      >
                        <Link2 className="h-4 w-4" />
                      </button>
                      <button
                        type="button"
                        disabled={updating}
                        onClick={() => onDismiss(cluster.cluster_id)}
                        className="inline-flex items-center justify-center rounded-lg border border-surface-border bg-surface-elevated p-2 text-text-secondary hover:text-accent-danger disabled:opacity-50"
                        title="Dismiss cluster"
                      >
                        <X className="h-4 w-4" />
                      </button>
                    </div>

                    <div className="flex flex-wrap items-center gap-2">
                      <a
                        href={newIssueUrl(cluster)}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 rounded-lg border border-surface-border bg-surface-elevated px-2.5 py-1.5 text-xs text-text-secondary hover:text-text-primary"
                        title={`New GitHub issue with ${issueLabels(cluster)}`}
                      >
                        <PlusCircle className="h-3.5 w-3.5" />
                        New issue
                      </a>
                      {issueUrl && (
                        <a
                          href={issueUrl}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-1 text-xs text-accent-brand"
                        >
                          Open issue <ExternalLink className="h-3 w-3" />
                        </a>
                      )}
                      <span className="inline-flex items-center gap-1 text-[11px] text-text-muted">
                        <Database className="h-3 w-3" />
                        {issueLabels(cluster)}
                      </span>
                    </div>

                    <div className="flex gap-2">
                      <input
                        type="text"
                        value={experimentKey}
                        onChange={(event) => setExperimentKeys((prev) => ({
                          ...prev,
                          [cluster.cluster_id]: event.target.value,
                        }))}
                        placeholder="Experiment key"
                        className="min-w-0 flex-1 rounded-lg border border-surface-border bg-surface-card px-3 py-2 text-xs text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-accent-brand/40"
                      />
                      <button
                        type="button"
                        disabled={!experimentKey.trim() || updating}
                        onClick={() => onMarkExperiment(cluster.cluster_id, experimentKey.trim())}
                        className="inline-flex items-center justify-center rounded-lg border border-surface-border bg-surface-elevated p-2 text-text-secondary hover:text-text-primary disabled:opacity-50"
                        title="Mark experiment"
                      >
                        <FlaskConical className="h-4 w-4" />
                      </button>
                    </div>
                  </section>
                </div>
              );
            })}
          </div>
        </div>
      ) : (
        <div className="text-sm text-text-muted">No open fixable-interest clusters yet.</div>
      )}
    </div>
  );
}

export { issueNumberFromUrl };
