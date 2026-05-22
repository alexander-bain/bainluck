"use client";

import { useState } from "react";
import { BarChart3, ExternalLink } from "lucide-react";
import { mutate } from "swr";
import type {
  DiscoverEngagementResponse,
  DiscoverEngagementReviewItem,
  DiscoverRuntimeConfig,
  DiscoverLaunchHealthItem,
  DiscoverLaunchHealthTrend,
  DiscoverReviewDecision,
} from "./types";
import { StatusPill } from "./ui";
import { updateDiscoverRuntimeConfig, submitDiscoverReviewDecision } from "./api";
import { rateText, formatTargetName, itemHref } from "./utils";
import ScoreBucketList from "./ScoreBucketList";
import RuntimeActionButton from "./RuntimeActionButton";
import LaunchHealthList from "./LaunchHealthList";
import EngagementList from "./EngagementList";
import LaunchHealthTrendPanel from "./LaunchHealthTrendPanel";

export default function EngagementPanel({
  data,
  secret,
  engagementDays,
  launchHealthTrends,
}: {
  data: DiscoverEngagementResponse;
  secret: string;
  engagementDays: number;
  launchHealthTrends: DiscoverLaunchHealthTrend[];
}) {
  const [savingConfig, setSavingConfig] = useState<string | null>(null);
  const [reviewingKey, setReviewingKey] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  const applyRuntimeConfig = async (
    label: string,
    config: Partial<DiscoverRuntimeConfig>
  ) => {
    setSavingConfig(label);
    setActionMessage(null);
    try {
      await updateDiscoverRuntimeConfig(secret, config);
      await mutate(["discover-engagement", secret, engagementDays]);
      setActionMessage(`${label} applied`);
    } catch (error) {
      setActionMessage(error instanceof Error ? error.message : "Runtime config update failed");
    } finally {
      setSavingConfig(null);
    }
  };

  const strongestOpens = data.groups
    .filter((row) => row.impressions >= 5)
    .sort((a, b) => b.open_rate - a.open_rate)
    .slice(0, 5);
  const highDismiss = data.groups
    .filter((row) => row.impressions >= 5)
    .sort((a, b) => b.dismiss_rate - a.dismiss_rate)
    .slice(0, 5);
  const shareSignals = data.groups
    .filter((row) => row.impressions >= 5)
    .sort((a, b) => b.share_rate - a.share_rate)
    .slice(0, 5);
  const contextSignals = data.groups
    .filter((row) => row.impressions >= 5)
    .sort((a, b) => (b.context_expand_rate ?? 0) - (a.context_expand_rate ?? 0))
    .slice(0, 5);

  const reviewKey = (item: DiscoverEngagementReviewItem, decision: string) =>
    `${item.surface}:${item.auth_segment}:${item.item_type}:${item.item_id}:${decision}`;

  return (
    <div className="bg-surface-card border border-surface-border rounded-lg p-4 space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-text-primary">Engagement</h2>
          <p className="text-xs text-text-muted mt-1">
            First-party Discover behavior from web and native over {data.days} day{data.days === 1 ? "" : "s"}.
          </p>
        </div>
        <BarChart3 className="w-4 h-4 text-text-muted" />
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div>
          <div className="text-xs text-text-muted">Impressions</div>
          <div className="text-lg font-semibold text-text-primary">{data.totals.impressions.toLocaleString()}</div>
        </div>
        <div>
          <div className="text-xs text-text-muted">Open rate</div>
          <div className="text-lg font-semibold text-text-primary">{rateText(data.totals.open_rate)}</div>
        </div>
        <div>
          <div className="text-xs text-text-muted">Dismiss rate</div>
          <div className="text-lg font-semibold text-text-primary">{rateText(data.totals.dismiss_rate)}</div>
        </div>
        <div>
          <div className="text-xs text-text-muted">Share rate</div>
          <div className="text-lg font-semibold text-text-primary">{rateText(data.totals.share_rate)}</div>
        </div>
        <div>
          <div className="text-xs text-text-muted">Context expands</div>
          <div className="text-lg font-semibold text-text-primary">{(data.totals.context_expands ?? 0).toLocaleString()}</div>
          <div className="text-[11px] text-text-muted">{rateText(data.totals.context_expand_rate ?? 0)}</div>
        </div>
        <div>
          <div className="text-xs text-text-muted">Challenge starts</div>
          <div className="text-lg font-semibold text-text-primary">{(data.totals.challenge_starts ?? 0).toLocaleString()}</div>
        </div>
        <div>
          <div className="text-xs text-text-muted">Challenge completes</div>
          <div className="text-lg font-semibold text-text-primary">{(data.totals.challenge_completes ?? 0).toLocaleString()}</div>
          <div className="text-[11px] text-text-muted">{rateText(data.totals.challenge_completion_rate ?? 0)}</div>
        </div>
        <div>
          <div className="text-xs text-text-muted">Actions</div>
          <div className="text-lg font-semibold text-text-primary">{data.totals.actions.toLocaleString()}</div>
        </div>
      </div>

      <div className="grid md:grid-cols-3 gap-3 rounded-lg border border-surface-border bg-surface-elevated/40 p-3">
        <div>
          <div className="text-xs text-text-muted">Repeat rate</div>
          <div className="text-lg font-semibold text-text-primary">{rateText(data.launch_health?.repeat_rate ?? 0)}</div>
          <div className="text-[11px] text-text-muted">
            {(data.launch_health?.repeat_extra_impressions ?? 0).toLocaleString()} extra impressions across {(data.launch_health?.repeat_sessions ?? 0).toLocaleString()} sessions
          </div>
        </div>
        <div>
          <div className="text-xs text-text-muted">Stale impression rate</div>
          <div className="text-lg font-semibold text-text-primary">{rateText(data.launch_health?.stale_rate ?? 0)}</div>
          <div className="text-[11px] text-text-muted">
            {(data.launch_health?.stale_impressions ?? 0).toLocaleString()} impressions on currently stale cards
          </div>
        </div>
        <div>
          <div className="text-xs text-text-muted">Runtime controls</div>
          <div className="text-sm font-semibold text-text-primary">
            {data.runtime_config?.interaction_suppression_enabled ? "Suppression on" : "Suppression off"}
          </div>
          <div className="text-[11px] text-text-muted">
            Seen {data.runtime_config?.seen_suppression_hours ?? "-"}h, dismiss {data.runtime_config?.dismiss_suppression_days ?? "-"}d, stale {data.runtime_config?.stale_no_movement_days ?? "-"}d
          </div>
        </div>
      </div>

      {data.score_buckets?.length > 0 && (
        <ScoreBucketList rows={data.score_buckets} />
      )}

      <LaunchHealthTrendPanel rows={launchHealthTrends} />

      <div className="rounded-lg border border-surface-border bg-surface-elevated/40 p-3 space-y-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="text-xs font-medium text-text-primary">Action Console</div>
            <div className="text-[11px] text-text-muted mt-1">
              Use these for launch guardrails. Use the Human Review Queue below for card-level promote/downrank decisions.
            </div>
          </div>
          {actionMessage && (
            <StatusPill tone={actionMessage.includes("failed") ? "warn" : "ok"}>
              {actionMessage}
            </StatusPill>
          )}
        </div>
        <div className="grid md:grid-cols-3 gap-2">
          <RuntimeActionButton
            title="Suppress Repeats"
            description="Hide seen cards for 72h and dismissed cards for 21d."
            busy={savingConfig === "Suppress repeats"}
            onClick={() =>
              applyRuntimeConfig("Suppress repeats", {
                interaction_suppression_enabled: true,
                seen_suppression_hours: 72,
                dismiss_suppression_days: 21,
              })
            }
          />
          <RuntimeActionButton
            title="Tighten Stale Filter"
            description="Reduce no-movement and no-resolution stale windows."
            busy={savingConfig === "Tighten stale filter"}
            onClick={() =>
              applyRuntimeConfig("Tighten stale filter", {
                stale_no_movement_days: 1,
                no_resolution_stale_days: 3,
              })
            }
          />
          <RuntimeActionButton
            title="Restore Defaults"
            description="Return launch guardrails to the checked-in defaults."
            busy={savingConfig === "Restore defaults"}
            onClick={() =>
              applyRuntimeConfig("Restore defaults", {
                interaction_suppression_enabled: true,
                seen_suppression_hours: 48,
                dismiss_suppression_days: 14,
                stale_no_movement_days: 2,
                no_resolution_stale_days: 5,
              })
            }
          />
        </div>
      </div>

      {((data.launch_health?.top_repeat_items?.length ?? 0) > 0 || (data.launch_health?.top_stale_items?.length ?? 0) > 0) && (
        <div className="grid md:grid-cols-2 gap-3">
          <LaunchHealthList title="Repeated Cards" rows={data.launch_health?.top_repeat_items || []} metric="extra_impressions" />
          <LaunchHealthList title="Currently Stale Cards" rows={data.launch_health?.top_stale_items || []} metric="impressions" />
        </div>
      )}

      {data.totals.impressions === 0 ? (
        <div className="text-sm text-text-muted rounded-lg border border-surface-border bg-surface-elevated/40 p-3">
          No first-party engagement captured yet. Open `/discover` on web or native after this deploy to start populating this panel.
        </div>
      ) : (
        <div className="grid lg:grid-cols-4 gap-3">
          <EngagementList title="Strong Opens" rows={strongestOpens} metric="open_rate" />
          <EngagementList title="High Dismiss" rows={highDismiss} metric="dismiss_rate" warn />
          <EngagementList title="Share Signals" rows={shareSignals} metric="share_rate" />
          <EngagementList title="Context Expands" rows={contextSignals} metric="context_expand_rate" />
        </div>
      )}

      {data.review_queue?.length > 0 && (
        <div>
          <div className="flex items-center justify-between gap-3 mb-2">
            <div>
              <div className="text-xs font-medium text-text-primary">Human Review Queue</div>
              <div className="text-[11px] text-text-muted">
                Card-level candidates segmented by surface and auth state. Promote/downrank decisions apply a bounded feed score nudge.
              </div>
            </div>
            <StatusPill tone="muted">{data.review_queue.length} candidates</StatusPill>
          </div>
          <div className="space-y-2">
            {data.review_queue.slice(0, 12).map((item) => (
              <div
                key={`${item.kind}-${item.surface}-${item.auth_segment}-${item.item_type}-${item.item_id}`}
                className="rounded-lg border border-surface-border bg-surface-elevated/40 p-3"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-sm font-semibold text-text-primary truncate">
                      {item.item_name || `${item.item_type} #${item.item_id}`}
                    </div>
                    <div className="text-xs text-text-secondary mt-1">{item.recommendation}</div>
                  </div>
                  <StatusPill tone={item.kind === "promote" ? "ok" : item.kind === "downrank" ? "warn" : "muted"}>
                    {item.kind}
                  </StatusPill>
                </div>
                <div className="flex flex-wrap gap-1 mt-2">
                  <StatusPill tone="muted">{item.surface}</StatusPill>
                  <StatusPill tone="muted">{item.auth_segment}</StatusPill>
                  <StatusPill tone="muted">{item.category || "other"}</StatusPill>
                  <StatusPill tone="muted">{formatTargetName(item.archetype)}</StatusPill>
                  <StatusPill tone="muted">{formatTargetName(item.family_key)}</StatusPill>
                </div>
                {itemHref(item.item_type, item.item_id) && (
                  <div className="mt-2">
                    <a
                      href={itemHref(item.item_type, item.item_id) || "#"}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 text-xs font-medium text-accent-brand hover:underline"
                    >
                      Open card detail
                      <ExternalLink className="h-3 w-3" />
                    </a>
                  </div>
                )}
                <div className="grid grid-cols-2 md:grid-cols-6 gap-2 mt-3 text-xs">
                  <div>
                    <div className="text-text-muted">Impressions</div>
                    <div className="font-semibold text-text-primary">{item.impressions}</div>
                  </div>
                  <div>
                    <div className="text-text-muted">Dismiss</div>
                    <div className="font-semibold text-text-primary">{rateText(item.dismiss_rate)}</div>
                  </div>
                  <div>
                    <div className="text-text-muted">Open</div>
                    <div className="font-semibold text-text-primary">{rateText(item.open_rate)}</div>
                  </div>
                  <div>
                    <div className="text-text-muted">Share</div>
                    <div className="font-semibold text-text-primary">{rateText(item.share_rate)}</div>
                  </div>
                  <div>
                    <div className="text-text-muted">Context</div>
                    <div className="font-semibold text-text-primary">{rateText(item.context_expand_rate)}</div>
                  </div>
                  <div>
                    <div className="text-text-muted">Avg rank</div>
                    <div className="font-semibold text-text-primary">{item.avg_rank ?? "-"}</div>
                  </div>
                </div>
                <div className="flex flex-wrap gap-2 mt-3">
                  {[
                    ["accepted_promote", "Promote in feed"],
                    ["accepted_downrank", "Downrank in feed"],
                    ["needs_design_fix", "Design fix"],
                    ["needs_data_fix", "Data fix"],
                    ["ignored", "Ignore"],
                  ].map(([decision, label]) => (
                    <button
                      key={decision}
                      type="button"
                      onClick={async () => {
                        const key = reviewKey(item, decision);
                        setReviewingKey(key);
                        setActionMessage(null);
                        try {
                          await submitDiscoverReviewDecision(secret, item, decision);
                          await mutate(["discover-engagement", secret, engagementDays]);
                          setActionMessage(`${label} saved`);
                        } catch (error) {
                          setActionMessage(error instanceof Error ? error.message : "Review decision failed");
                        } finally {
                          setReviewingKey(null);
                        }
                      }}
                      disabled={reviewingKey !== null}
                      className="px-2 py-1 rounded-md border border-surface-border bg-surface-card text-[11px] text-text-secondary hover:text-text-primary disabled:opacity-60"
                    >
                      {reviewingKey === reviewKey(item, decision) ? "Saving..." : label}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {data.recent_review_decisions?.length > 0 && (
        <div>
          <div className="text-xs font-medium text-text-primary mb-2">Recent Review Decisions</div>
          <div className="space-y-1">
            {data.recent_review_decisions.slice(0, 8).map((decision) => (
              <div key={decision.id} className="flex items-center justify-between gap-3 text-xs rounded-md border border-surface-border bg-surface-elevated/30 px-3 py-2">
                <span className="truncate text-text-secondary">{decision.item_name || `${decision.item_type} #${decision.item_id}`}</span>
                <StatusPill tone="muted">{formatTargetName(decision.decision)}</StatusPill>
              </div>
            ))}
          </div>
        </div>
      )}

      {data.opportunities.length > 0 && (
        <div>
          <div className="flex items-center justify-between gap-3 mb-2">
            <div>
              <div className="text-xs font-medium text-text-primary">Ranking Opportunities</div>
              <div className="text-[11px] text-text-muted">
                Aggregate patterns only. Use the Human Review Queue for card-level ranking changes.
              </div>
            </div>
          </div>
          <div className="grid md:grid-cols-2 gap-2">
            {data.opportunities.slice(0, 6).map((item) => (
              <div key={`${item.kind}-${item.label}-${item.metric}`} className="rounded-lg border border-surface-border bg-surface-elevated/40 p-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-xs font-semibold text-text-primary truncate">{item.label}</div>
                    <div className="text-xs text-text-secondary mt-1">{item.recommendation}</div>
                  </div>
                  <StatusPill tone={item.kind === "investigate" ? "warn" : item.kind === "promote" ? "ok" : "muted"}>
                    {item.kind}
                  </StatusPill>
                </div>
                <div className="flex flex-wrap gap-1 mt-2">
                  <StatusPill tone="muted">{formatTargetName(item.metric)}</StatusPill>
                  <StatusPill tone="muted">{rateText(item.value)}</StatusPill>
                  <StatusPill tone="muted">{`${item.impressions} impressions`}</StatusPill>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {data.top_items.length > 0 && (
        <div>
          <div className="text-xs font-medium text-text-primary mb-2">Top Actioned Items</div>
          <div className="grid md:grid-cols-2 gap-2">
            {data.top_items.slice(0, 6).map((item) => (
              <div key={`${item.item_type}-${item.item_id}`} className="rounded-lg border border-surface-border bg-surface-elevated/40 p-2">
                <div className="flex items-center justify-between gap-3 text-xs">
                  <span className="text-text-primary font-medium truncate">
                    {item.item_name || `${item.item_type} #${item.item_id}`}
                  </span>
                  <span className="text-text-muted shrink-0">{item.actions} actions</span>
                </div>
                <div className="flex flex-wrap gap-1 mt-2">
                  <StatusPill tone="muted">{item.surface || "unknown"}</StatusPill>
                  <StatusPill tone="muted">{item.category || "other"}</StatusPill>
                  <StatusPill tone="muted">{item.item_type}</StatusPill>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
