"use client";

import { useState } from "react";
import { FlaskConical, ExternalLink, Link2, PlusCircle, X } from "lucide-react";
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

function newIssueUrl(cluster: DiscoverFixableInterestCluster) {
  const title = `Fixable Discover card: ${formatTargetName(cluster.fix_type)}`;
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
    `## Example`,
    cluster.examples[0]?.snapshot_name || cluster.examples[0]?.market_name || "Unknown card",
    ``,
    `## Acceptance Criteria`,
    `- Decide whether this is a data, design, or ranking fix.`,
    `- Update the affected card/cluster so future labels no longer produce this feedback.`,
    `- Re-run Discover label evals or verify via admin Review after the fix.`,
  ].join("\n");
  const params = new URLSearchParams({
    title,
    body,
    labels: "area:discover,type:bug,needs-agent",
  });
  return `https://github.com/alexander-bain/bainluck/issues/new?${params}`;
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
        <div className="overflow-x-auto rounded-lg border border-surface-border">
          <table className="w-full text-sm">
            <thead className="bg-surface-elevated text-text-muted text-xs">
              <tr>
                <th className="text-left font-medium p-3">Cluster</th>
                <th className="text-left font-medium p-3">Impact</th>
                <th className="text-left font-medium p-3">Example</th>
                <th className="text-left font-medium p-3">Triage</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-border/60">
              {clusters.map((cluster) => {
                const example = cluster.examples[0];
                const issueUrl = issueUrls[cluster.cluster_id] || "";
                const experimentKey = experimentKeys[cluster.cluster_id] || "";
                const updating = updatingClusterId === cluster.cluster_id;
                return (
                  <tr key={cluster.cluster_id} className="align-top hover:bg-surface-elevated/40">
                    <td className="p-3 min-w-[260px]">
                      <div className="flex items-center gap-2 flex-wrap">
                        <StatusPill tone={statusTone(cluster.status)}>{formatTargetName(cluster.status)}</StatusPill>
                        <StatusPill tone="muted">{formatTargetName(cluster.fix_type)}</StatusPill>
                        {cluster.max_fixable_interest_score !== null && (
                          <StatusPill tone="ok">{`score ${cluster.max_fixable_interest_score}`}</StatusPill>
                        )}
                      </div>
                      <div className="mt-2 font-medium text-text-primary">
                        {cluster.would_be_interesting_if || "No note captured"}
                      </div>
                      <div className="mt-1 text-xs text-text-muted">
                        {cluster.current_entity_or_variant || "current unknown"}
                        {cluster.desired_entity_or_variant ? ` -> ${cluster.desired_entity_or_variant}` : ""}
                      </div>
                      <div className="mt-1 text-[11px] text-text-muted">
                        {cluster.story_key || cluster.group_id || cluster.family_key || cluster.item_key}
                      </div>
                    </td>
                    <td className="p-3 min-w-[180px]">
                      <div className="text-text-primary">{cluster.count} labels</div>
                      <div className="text-xs text-text-muted">
                        {cluster.issue_candidate_count} issue candidates
                      </div>
                      <div className="text-xs text-text-muted">
                        ranks {cluster.affected_ranks.slice(0, 5).join(", ") || "n/a"}
                      </div>
                      <div className="text-xs text-text-muted">
                        markets {cluster.market_ids.slice(0, 4).join(", ") || "n/a"}
                      </div>
                    </td>
                    <td className="p-3 min-w-[260px]">
                      <div className="font-medium text-text-primary">
                        {example?.snapshot_name || example?.market_name || "Unknown card"}
                      </div>
                      <div className="text-xs text-text-muted mt-1">
                        {example ? `#${example.rank_seen ?? "?"} ${example.label}` : "No example"}
                        {example?.score_at_review !== null && example?.score_at_review !== undefined
                          ? `, score ${Math.round(example.score_at_review)}`
                          : ""}
                      </div>
                      {example?.notes && (
                        <div className="text-xs text-text-secondary mt-1">{example.notes}</div>
                      )}
                    </td>
                    <td className="p-3 min-w-[260px]">
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
                      {issueUrl && (
                        <a
                          href={issueUrl}
                          target="_blank"
                          rel="noreferrer"
                          className="mt-2 inline-flex items-center gap-1 text-xs text-accent-brand"
                        >
                          Open issue <ExternalLink className="h-3 w-3" />
                        </a>
                      )}
                      <div className="mt-2 flex gap-2">
                        <a
                          href={newIssueUrl(cluster)}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-1 rounded-lg border border-surface-border bg-surface-elevated px-2.5 py-1.5 text-xs text-text-secondary hover:text-text-primary"
                        >
                          <PlusCircle className="h-3.5 w-3.5" />
                          New issue
                        </a>
                      </div>
                      <div className="mt-2 flex gap-2">
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
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="text-sm text-text-muted">No open fixable-interest clusters yet.</div>
      )}
    </div>
  );
}

export { issueNumberFromUrl };
