"use client";

import { useCallback, useState } from "react";
import useSWR from "swr";
import { AlertTriangle, XCircle, Info, RefreshCw } from "lucide-react";
import { useAdminAuth } from "./AdminAuthProvider";
import { adminFetch } from "@/lib/adminFetch";
import FileThisButton from "@/components/admin/FileThisButton";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface DiagnosisIssue {
  severity: "critical" | "warning" | "info";
  title: string;
  explanation: string;
  claude_prompt: string;
  admin_page: string;
}

interface DiagnosisResponse {
  generated_at: string;
  cached: boolean;
  issues: DiagnosisIssue[];
}

const SEVERITY_CONFIG = {
  critical: { icon: XCircle, color: "text-accent-danger", bg: "bg-accent-danger/5 border-accent-danger/20" },
  warning: { icon: AlertTriangle, color: "text-accent-warning", bg: "bg-accent-warning/5 border-accent-warning/20" },
  info: { icon: Info, color: "text-text-muted", bg: "bg-surface-elevated border-surface-border" },
};

// L2-142 Item 3 — a filable body for a diagnosis: the same diagnosis content,
// now headed to a real filed issue instead of the clipboard. The old
// `claude_prompt` becomes the investigation notes inside the issue.
function diagnosisBody(issue: DiagnosisIssue): string {
  const parts = [issue.explanation];
  if (issue.claude_prompt) {
    parts.push(`\n\n**Investigation notes**\n\n${issue.claude_prompt}`);
  }
  if (issue.admin_page && issue.admin_page !== "/admin") {
    parts.push(`\n\nAdmin page: ${issue.admin_page}`);
  }
  return parts.join("");
}

const _SEVERITY_LABEL: Record<string, string> = {
  critical: "System Diagnosis (critical)",
  warning: "System Diagnosis (warning)",
  info: "System Diagnosis",
};

export default function DiagnosisCard() {
  const { secret } = useAdminAuth();
  const [refreshing, setRefreshing] = useState(false);

  const { data, mutate } = useSWR<DiagnosisResponse>(
    ["llm-diagnosis", secret],
    async () => {
      try {
        const r = await adminFetch("/api/admin/llm-diagnosis", secret);
        if (!r.ok) return null;
        return await r.json();
      } catch {
        return null;
      }
    },
    { revalidateOnFocus: false, refreshInterval: 0, shouldRetryOnError: false }
  );

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    try {
      const res = await adminFetch(
        "/api/admin/llm-diagnosis?force=true",
        secret,
        { method: "POST" }
      );
      const fresh = await res.json();
      mutate(fresh, false);
    } finally {
      setRefreshing(false);
    }
  }, [secret, mutate]);

  if (!data || !data.issues?.length) return null;

  return (
    <div className="bg-surface-card border border-surface-border rounded-xl p-4 mb-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-text-primary">System Diagnosis</span>
          {data.cached && (
            <span className="text-[10px] text-text-muted bg-surface-elevated px-1.5 py-0.5 rounded">cached</span>
          )}
        </div>
        <button
          onClick={handleRefresh}
          disabled={refreshing}
          className="inline-flex items-center gap-1.5 text-xs text-text-muted hover:text-text-secondary transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`w-3 h-3 ${refreshing ? "animate-spin" : ""}`} />
          {refreshing ? "Diagnosing..." : "Refresh"}
        </button>
      </div>
      <div className="space-y-2">
        {data.issues.map((issue, i) => {
          const cfg = SEVERITY_CONFIG[issue.severity] || SEVERITY_CONFIG.info;
          const Icon = cfg.icon;
          return (
            <div key={i} className={`rounded-lg border p-3 ${cfg.bg}`}>
              <div className="flex items-start gap-2">
                <Icon className={`w-4 h-4 mt-0.5 shrink-0 ${cfg.color}`} />
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-text-primary">{issue.title}</div>
                  <p className="text-xs text-text-secondary mt-0.5">{issue.explanation}</p>
                  <div className="flex items-center gap-3 mt-2">
                    {/* L2-142 Item 3 — retired the copy-Claude-prompt blurb. The
                        diagnosis now files a real issue via the rail (the same
                        diagnosis, a real destination) and flips to "filed #N". */}
                    <FileThisButton
                      source="system_diagnosis"
                      itemKey={issue.title}
                      title={`${_SEVERITY_LABEL[issue.severity] ?? "System Diagnosis"}: ${issue.title}`}
                      body={diagnosisBody(issue)}
                      severity={issue.severity}
                    />
                    {issue.admin_page && issue.admin_page !== "/admin" && (
                      <a href={issue.admin_page} className="text-[11px] text-text-muted hover:text-text-secondary">
                        View details →
                      </a>
                    )}
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
      {data.generated_at && (
        <div className="text-[10px] text-text-muted mt-2">
          Last diagnosis: {new Date(data.generated_at).toLocaleString()}
        </div>
      )}
    </div>
  );
}
