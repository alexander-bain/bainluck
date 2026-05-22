"use client";

import { CheckCircle2, AlertTriangle, XCircle, Loader2 } from "lucide-react";

interface PageHeaderProps {
  question: string;
  status: "good" | "warning" | "critical" | "loading";
  summary: string;
  ideal: string;
  subtitle?: string;
}

const STATUS_CONFIG = {
  good: {
    icon: CheckCircle2,
    color: "text-accent-live",
    bg: "bg-accent-live/10",
    label: "Healthy",
  },
  warning: {
    icon: AlertTriangle,
    color: "text-accent-warning",
    bg: "bg-accent-warning/10",
    label: "Needs attention",
  },
  critical: {
    icon: XCircle,
    color: "text-accent-danger",
    bg: "bg-accent-danger/10",
    label: "Critical",
  },
  loading: {
    icon: Loader2,
    color: "text-text-muted",
    bg: "bg-surface-elevated",
    label: "Loading",
  },
};

export default function PageHeader({
  question,
  status,
  summary,
  ideal,
  subtitle,
}: PageHeaderProps) {
  const cfg = STATUS_CONFIG[status];
  const Icon = cfg.icon;

  return (
    <div className="mb-6">
      <h1 className="text-lg font-bold text-text-primary">{question}</h1>
      {subtitle && (
        <p className="text-xs text-text-muted mt-0.5">{subtitle}</p>
      )}
      <div className="flex items-center gap-2 mt-2">
        <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${cfg.bg} ${cfg.color}`}>
          <Icon className={`w-3.5 h-3.5 ${status === "loading" ? "animate-spin" : ""}`} />
          {cfg.label}
        </span>
        <span className="text-sm text-text-secondary">{summary}</span>
      </div>
      <p className="text-xs text-text-muted mt-1.5">
        Target: {ideal}
      </p>
    </div>
  );
}
