"use client";

import { useState } from "react";
import { ChevronDown, CheckCircle2, AlertTriangle, XCircle } from "lucide-react";

interface MetricSectionProps {
  question: string;
  status: "good" | "warning" | "critical" | "loading";
  summary: string;
  ideal: string;
  action?: string;
  actionHref?: string;
  defaultExpanded?: boolean;
  children: React.ReactNode;
}

const STATUS_DOT = {
  good: "bg-accent-live",
  warning: "bg-accent-warning",
  critical: "bg-accent-danger",
  loading: "bg-text-muted animate-pulse",
};

const STATUS_ICON = {
  good: CheckCircle2,
  warning: AlertTriangle,
  critical: XCircle,
  loading: null,
};

export default function MetricSection({
  question,
  status,
  summary,
  ideal,
  action,
  actionHref,
  defaultExpanded,
  children,
}: MetricSectionProps) {
  const autoExpand = defaultExpanded ?? (status === "warning" || status === "critical");
  const [expanded, setExpanded] = useState(autoExpand);

  const Icon = STATUS_ICON[status];

  return (
    <div className="bg-surface-card border border-surface-border rounded-xl overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-surface-elevated/40 transition-colors"
      >
        <span className={`w-2 h-2 rounded-full shrink-0 ${STATUS_DOT[status]}`} />
        <span className="flex-1 min-w-0">
          <span className="text-sm font-medium text-text-primary">{question}</span>
          <span className="ml-2 text-sm text-text-secondary">{summary}</span>
        </span>
        {Icon && <Icon className={`w-4 h-4 shrink-0 ${status === "good" ? "text-accent-live" : status === "warning" ? "text-accent-warning" : "text-accent-danger"}`} />}
        <ChevronDown className={`w-4 h-4 text-text-muted shrink-0 transition-transform ${expanded ? "rotate-180" : ""}`} />
      </button>

      {expanded && (
        <div className="px-4 pb-4 border-t border-surface-border/60">
          <p className="text-xs text-text-muted mt-2 mb-3">Target: {ideal}</p>
          {children}
          {action && (
            <div className="mt-3 rounded-lg bg-surface-elevated p-2.5 text-xs text-text-secondary">
              {actionHref ? (
                <a href={actionHref} className="text-accent-brand hover:underline">{action}</a>
              ) : (
                action
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
