"use client";

import { useState, useEffect, useCallback } from "react";
import { getAuth } from "firebase/auth";
import { usePageTracking } from "@/hooks/usePageTracking";
import { useScrollDepth } from "@/hooks/useScrollDepth";
import { useEngagementTime } from "@/hooks/useEngagementTime";
import { useAdminAuth } from "@/components/admin/AdminAuthProvider";
import PageHeader from "@/components/admin/PageHeader";

interface BugReport {
  id: number;
  user_id: number | null;
  session_id: string | null;
  description: string | null;
  has_screenshot: boolean;
  screenshot_base64: string | null;
  app_state: Record<string, string> | null;
  status: string;
  category: string | null;
  admin_notes: string | null;
  backlog_ref: string | null;
  resolution_summary: string | null;
  created_at: string | null;
}

interface LLMAnalysis {
  severity: string;
  severityColor: string;
  likelyFix: string;
  rootCause: string;
  prompt: string;
}

const API = process.env.NEXT_PUBLIC_API_URL || "https://api.bainluck.com";

const SEVERITY_COLORS: Record<string, string> = {
  P0: "bg-red-600 text-white",
  P1: "bg-orange-500 text-white",
  P2: "bg-yellow-400 text-gray-900",
  P3: "bg-gray-200 text-gray-600",
};

function analyzeBug(r: BugReport): LLMAnalysis {
  const desc = (r.description || "").toLowerCase();
  const platform = r.app_state?.platform || "unknown";

  let severity = "P2";
  if (/crash|broken|can't|cannot|500|error|blank|missing|won't load/i.test(desc)) severity = "P1";
  if (/data loss|wrong data|incorrect|duplicate|security/i.test(desc)) severity = "P0";
  if (/ugly|weird|minor|typo|color|font|spacing|alignment/i.test(desc)) severity = "P3";

  let rootCause = "UI/display issue";
  if (/odds|probability|percent|%|number/i.test(desc)) rootCause = "Data display / aggregation issue";
  if (/chart|graph|axis|line/i.test(desc)) rootCause = "Chart rendering issue";
  if (/load|slow|spinner|blank/i.test(desc)) rootCause = "Performance / loading issue";
  if (/twice|duplicate|repeated/i.test(desc)) rootCause = "Duplicate data rendering";
  if (/source|attribution|kalshi|polymarket|espn/i.test(desc)) rootCause = "Source display / attribution issue";
  if (/layout|overlap|cut off|truncat/i.test(desc)) rootCause = "Layout / responsive issue";

  const likelyFix = `Check ${platform} rendering for: ${rootCause.toLowerCase()}. Review the relevant component in the ${platform === "ios" ? "iOS Views/" : platform === "macos" ? "iOS Views/" : "frontend/components/"} directory.`;

  const appStateStr = r.app_state
    ? Object.entries(r.app_state).map(([k, v]) => `- ${k}: ${v}`).join("\n")
    : "(no app state)";

  const prompt = `## Bug Report #${r.id}

**Description:** ${r.description || "(no description)"}

**Platform:** ${r.app_state?.platform || "unknown"} (${r.app_state?.device_model || "?"}, OS ${r.app_state?.os_version || "?"})
**Current Page:** ${r.app_state?.current_page || r.app_state?.current_tab || "?"}
**User:** ${r.app_state?.user_name || r.app_state?.user_id || "anonymous"}
**Network:** ${r.app_state?.network || "?"}
**Submitted:** ${r.created_at ? new Date(r.created_at).toLocaleString() : "?"}
**Severity:** ${severity}
**Root Cause (estimated):** ${rootCause}

**Full App State:**
${appStateStr}

${r.has_screenshot ? `**Screenshot:** Run this to download and view it:
\`\`\`
curl -s "${API}/api/admin/bug-reports/${r.id}/screenshot?secret=$ADMIN_TOKEN" -o /tmp/bug_${r.id}.jpg && echo "Screenshot saved to /tmp/bug_${r.id}.jpg"
\`\`\`
Then read the image: \`/tmp/bug_${r.id}.jpg\` (user marked up the issue area with red marker)
` : ""}
### Task
This report may contain MULTIPLE issues. For each distinct issue:
1. Identify it as a separate problem
2. Find the relevant code
3. Diagnose the root cause
4. Write a fix
5. Add a test if it touches backend logic

After fixing, run: \`cd backend && python3 -m pytest tests/test_startup.py -v\`

For each issue, note whether it should be a separate backlog item.`;

  return {
    severity,
    severityColor: SEVERITY_COLORS[severity] || SEVERITY_COLORS.P2,
    likelyFix,
    rootCause,
    prompt,
  };
}

export default function BugReportsPage() {
  usePageTracking({ pageType: "bug_reports", pageTitle: "Bug Reports" });
  useScrollDepth({ pageType: "bug_reports" });
  useEngagementTime({ pageType: "bug_reports" });

  const [reports, setReports] = useState<BugReport[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("all");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [copied, setCopied] = useState(false);
  const [showPrompt, setShowPrompt] = useState(false);
  const [showAnalytics, setShowAnalytics] = useState(true);

  const { secret } = useAdminAuth();

  const getAuthHeaders = useCallback(async (): Promise<Record<string, string>> => {
    try {
      const auth = getAuth();
      const user = auth.currentUser;
      if (user) {
        const token = await user.getIdToken();
        return { Authorization: `Bearer ${token}` };
      }
    } catch {}
    return {};
  }, []);

  const loadReports = useCallback(async () => {
    setLoading(true);
    try {
      const headers = await getAuthHeaders();
      const statusParam = filter === "all" ? "" : `&status=${filter}`;
      const secretParam = secret ? `&secret=${secret}` : "";
      const res = await fetch(
        `${API}/api/admin/bug-reports?limit=100${statusParam}${secretParam}`,
        { headers }
      );
      if (!res.ok) {
        setReports([]);
        setLoading(false);
        return;
      }
      const data = await res.json();
      setReports(data.reports || []);
    } catch {
      setReports([]);
    }
    setLoading(false);
  }, [secret, filter, getAuthHeaders]);

  useEffect(() => {
    loadReports();
  }, [loadReports]);

  const updateStatus = async (id: number, newStatus: string) => {
    const headers = await getAuthHeaders();
    const secretParam = secret ? `&secret=${secret}` : "";
    await fetch(
      `${API}/api/admin/bug-reports/${id}?status=${newStatus}${secretParam}`,
      { method: "PATCH", headers }
    );
    loadReports();
  };

  const updateField = async (id: number, field: string, value: string) => {
    const headers = await getAuthHeaders();
    const secretParam = secret ? `&secret=${secret}` : "";
    const param = encodeURIComponent(value);
    await fetch(
      `${API}/api/admin/bug-reports/${id}?${field}=${param}${secretParam}`,
      { method: "PATCH", headers }
    );
    setReports(prev =>
      prev.map(r => (r.id === id ? { ...r, [field]: value || null } : r))
    );
  };

  const selectReport = async (id: number) => {
    setSelectedId(id);
    setShowPrompt(false);
    const report = reports.find(r => r.id === id);
    if (report && report.status === "new") {
      setReports(prev => prev.map(r => r.id === id ? { ...r, status: "reviewed" } : r));
      updateStatusSilent(id, "reviewed");
    }
    if (report?.has_screenshot && !report.screenshot_base64) {
      try {
        const headers = await getAuthHeaders();
        const secretParam = secret ? `?secret=${secret}` : "";
        const resp = await fetch(`${API}/api/admin/bug-reports/${id}/screenshot${secretParam}`, { headers });
        if (resp.ok) {
          const blob = await resp.blob();
          const reader = new FileReader();
          reader.onload = () => {
            const base64 = (reader.result as string).split(",")[1];
            setReports(prev => prev.map(r => r.id === id ? { ...r, screenshot_base64: base64 } : r));
          };
          reader.readAsDataURL(blob);
        }
      } catch { }
    }
  };

  const updateStatusSilent = async (id: number, newStatus: string) => {
    const headers = await getAuthHeaders();
    const secretParam = secret ? `&secret=${secret}` : "";
    await fetch(
      `${API}/api/admin/bug-reports/${id}?status=${newStatus}${secretParam}`,
      { method: "PATCH", headers }
    );
  };

  const copyPrompt = (prompt: string) => {
    navigator.clipboard.writeText(prompt);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const selected = reports.find((r) => r.id === selectedId);
  const analysis = selected ? analyzeBug(selected) : null;

  // No gate — auth is checked server-side via Firebase token or secret

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-7xl mx-auto px-4 py-6">
        <div className="flex items-center justify-between mb-6">
          <div>
            <a href={`/admin?secret=${secret}`} className="text-sm text-blue-600 hover:underline">&larr; Admin Dashboard</a>
            <PageHeader
              question="What bugs have users reported?"
              status={reports.length === 0 ? "good" : reports.some(r => r.status === "new") ? "warning" : "good"}
              summary={`${reports.filter(r => r.status === "new").length} new · ${reports.length} total`}
              ideal="Zero unreviewed reports. All bugs triaged within 24h."
            />
            <p className="text-sm text-gray-500">{reports.length} reports</p>
          </div>
          <div className="flex gap-2">
            {["all", "new", "reviewed", "actioned", "dismissed"].map((s) => {
              const count = s === "all" ? reports.length : reports.filter(r => r.status === s).length;
              return (
                <button
                  key={s}
                  onClick={() => { setFilter(s); setSelectedId(null); }}
                  className={`px-3 py-1.5 rounded-full text-sm font-medium ${
                    filter === s
                      ? "bg-blue-600 text-white"
                      : "bg-white text-gray-600 border hover:bg-gray-50"
                  }`}
                >
                  {s.charAt(0).toUpperCase() + s.slice(1)}
                  {count > 0 && (
                    <span className={`ml-1.5 text-xs rounded-full px-1.5 ${
                      filter === s ? "bg-blue-500 text-white" :
                      s === "new" ? "bg-red-500 text-white" :
                      "bg-gray-200 text-gray-600"
                    }`}>
                      {count}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </div>

        {/* Analytics Section — burndown chart + summary stats */}
        {!loading && reports.length > 0 && (
          <div className="mb-6">
            <button
              onClick={() => setShowAnalytics(!showAnalytics)}
              className="flex items-center gap-2 text-sm text-gray-500 hover:text-gray-700 mb-3"
            >
              <span className="text-xs">{showAnalytics ? "▼" : "▶"}</span>
              Analytics
            </button>
            {showAnalytics && (
              <div className="space-y-4">
                <SummaryStats reports={reports} />
                <BurndownChart reports={reports} />
              </div>
            )}
          </div>
        )}

        {loading ? (
          <div className="text-center py-12 text-gray-400">Loading...</div>
        ) : reports.length === 0 ? (
          <div className="text-center py-12 text-gray-400">
            No bug reports{filter !== "all" ? ` with status "${filter}"` : ""}
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
            {/* List — 2 cols */}
            <div className="lg:col-span-2 space-y-3">
              {reports.map((r) => {
                const a = analyzeBug(r);
                return (
                  <div
                    key={r.id}
                    onClick={() => selectReport(r.id)}
                    className={`p-4 rounded-xl border cursor-pointer transition-all ${
                      selectedId === r.id
                        ? "border-blue-500 bg-blue-50 shadow-md"
                        : "border-gray-200 bg-white hover:border-gray-300"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${a.severityColor}`}>{a.severity}</span>
                          <StatusBadge status={r.status} />
                        </div>
                        <p className="font-medium text-sm line-clamp-2">
                          {r.description || "(no description)"}
                        </p>
                        <div className="flex items-center gap-2 mt-1">
                          <span className="text-xs text-gray-400">
                            {r.created_at ? timeAgo(r.created_at) : ""}
                          </span>
                          {r.app_state?.platform && (
                            <span className="text-xs text-gray-400 bg-gray-100 px-1.5 py-0.5 rounded">
                              {r.app_state.platform}
                            </span>
                          )}
                          {r.category && (
                            <span className="text-xs text-blue-500 bg-blue-50 px-1.5 py-0.5 rounded">
                              {r.category.replace(/_/g, " ")}
                            </span>
                          )}
                          <span className="text-xs text-gray-400">
                            {r.app_state?.user_name && r.app_state.user_name !== "anonymous"
                              ? r.app_state.user_name
                              : r.app_state?.user_id ? `user ${r.app_state.user_id}` : "anonymous"}
                          </span>
                        </div>
                      </div>
                      {r.has_screenshot && (
                        <div className="w-10 h-10 rounded bg-gray-100 flex items-center justify-center text-gray-400 text-xs shrink-0">
                          📷
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Detail — 3 cols */}
            {selected && analysis ? (
              <div className="lg:col-span-3 space-y-4">
                {/* Header + Description */}
                <div className="bg-white rounded-xl border p-5">
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-3">
                      <h2 className="font-bold text-lg">Bug #{selected.id}</h2>
                      <span className={`px-2 py-0.5 rounded text-xs font-bold ${analysis.severityColor}`}>{analysis.severity}</span>
                      <StatusBadge status={selected.status} />
                    </div>
                    <div className="text-xs text-gray-400">
                      {selected.app_state?.user_name && selected.app_state.user_name !== "anonymous"
                        ? <span className="font-medium text-gray-600 mr-2">{selected.app_state.user_name}</span>
                        : null}
                      {selected.created_at ? new Date(selected.created_at).toLocaleString() : ""}
                    </div>
                  </div>
                  <p className="text-sm leading-relaxed">{selected.description || "(no description)"}</p>
                </div>

                {/* Analysis + Copy Prompt — prominent, right after description */}
                <div className="bg-blue-50 rounded-xl border border-blue-200 p-5 space-y-3">
                  <div className="flex items-center justify-between">
                    <h3 className="font-semibold text-sm text-blue-700 uppercase tracking-wider">Diagnosis</h3>
                    <span className={`px-2 py-0.5 rounded text-xs font-bold ${analysis.severityColor}`}>{analysis.severity}</span>
                  </div>
                  <div className="grid grid-cols-2 gap-4 text-sm">
                    <div>
                      <span className="text-blue-400 text-xs">Likely Root Cause</span>
                      <p className="font-medium text-blue-900">{analysis.rootCause}</p>
                    </div>
                    <div>
                      <span className="text-blue-400 text-xs">Where to Look</span>
                      <p className="font-medium text-blue-900">{analysis.likelyFix}</p>
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={() => copyPrompt(analysis.prompt)}
                      className="flex-1 py-3 rounded-lg bg-gray-900 text-white text-sm font-semibold hover:bg-gray-800 transition-colors flex items-center justify-center gap-2"
                    >
                      {copied ? (
                        <><span>✓</span> Copied — paste into Claude CLI</>
                      ) : (
                        <><span>📋</span> Copy Claude Prompt</>
                      )}
                    </button>
                    <button
                      onClick={() => setShowPrompt(!showPrompt)}
                      className="px-4 py-3 rounded-lg bg-gray-200 text-gray-700 text-sm font-medium hover:bg-gray-300 transition-colors"
                    >
                      {showPrompt ? "Hide" : "Preview"}
                    </button>
                  </div>
                  {showPrompt && (
                    <pre className="mt-2 p-3 bg-gray-900 text-gray-100 text-xs rounded-lg overflow-x-auto whitespace-pre-wrap max-h-64 overflow-y-auto font-mono">
                      {analysis.prompt}
                    </pre>
                  )}
                </div>

                {/* Screenshot */}
                {selected.screenshot_base64 && (
                  <div className="bg-white rounded-xl border p-4">
                    <img
                      src={`data:image/jpeg;base64,${selected.screenshot_base64}`}
                      alt="Bug screenshot"
                      className="rounded-lg border max-h-[500px] w-full object-contain bg-gray-50"
                    />
                  </div>
                )}

                {/* App State */}
                {selected.app_state && (
                  <div className="bg-white rounded-xl border p-5">
                    <h3 className="font-semibold text-sm text-gray-500 uppercase tracking-wider mb-2">App State</h3>
                    <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-xs">
                      {Object.entries(selected.app_state).map(([k, v]) => (
                        <div key={k} className="flex justify-between py-0.5">
                          <span className="text-gray-400">{k.replace(/_/g, " ")}</span>
                          <span className="text-gray-700 font-mono">{v}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Category & Lifecycle */}
                <div className="bg-white rounded-xl border p-5 space-y-4">
                  <h3 className="font-semibold text-sm text-gray-500 uppercase tracking-wider">Triage</h3>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs text-gray-500 mb-1">Category</label>
                      <select
                        value={selected.category || ""}
                        onChange={e => updateField(selected.id, "category", e.target.value)}
                        className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-300"
                      >
                        <option value="">Uncategorized</option>
                        <option value="ui">UI</option>
                        <option value="data_quality">Data Quality</option>
                        <option value="performance">Performance</option>
                        <option value="feature_request">Feature Request</option>
                        <option value="ios">iOS</option>
                        <option value="other">Other</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-xs text-gray-500 mb-1">Backlog Ref</label>
                      <input
                        type="text"
                        placeholder="e.g. BR42"
                        defaultValue={selected.backlog_ref || ""}
                        onBlur={e => {
                          const val = e.target.value.trim();
                          if (val !== (selected.backlog_ref || "")) {
                            updateField(selected.id, "backlog_ref", val);
                          }
                        }}
                        className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
                      />
                    </div>
                  </div>
                  <div>
                    <label className="block text-xs text-gray-500 mb-1">Resolution Summary</label>
                    <textarea
                      placeholder="How was this resolved?"
                      rows={2}
                      defaultValue={selected.resolution_summary || ""}
                      onBlur={e => {
                        const val = e.target.value.trim();
                        if (val !== (selected.resolution_summary || "")) {
                          updateField(selected.id, "resolution_summary", val);
                        }
                      }}
                      className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300 resize-none"
                    />
                  </div>
                </div>

                {/* Actions */}
                <div className="bg-white rounded-xl border p-5 space-y-3">
                  <div className="flex items-center gap-3">
                    <button
                      onClick={() => updateStatus(selected.id, "actioned")}
                      className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                        selected.status === "actioned"
                          ? "bg-green-100 text-green-700 ring-1 ring-green-300"
                          : "bg-green-50 text-green-700 hover:bg-green-100 border border-green-200"
                      }`}
                    >
                      {selected.status === "actioned" ? "Added to Backlog" : "Mark as Added to Backlog"}
                    </button>
                    <button
                      onClick={() => updateStatus(selected.id, "dismissed")}
                      className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                        selected.status === "dismissed"
                          ? "bg-gray-200 text-gray-500 ring-1 ring-gray-300"
                          : "bg-gray-50 text-gray-500 hover:bg-gray-100 border border-gray-200"
                      }`}
                    >
                      {selected.status === "dismissed" ? "Dismissed" : "Dismiss"}
                    </button>
                  </div>
                </div>
              </div>
            ) : (
              <BugDashboard reports={reports} allReports={reports} />
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    new: "bg-red-100 text-red-700",
    reviewed: "bg-yellow-100 text-yellow-700",
    actioned: "bg-green-100 text-green-700",
    dismissed: "bg-gray-100 text-gray-500",
  };
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${colors[status] || colors.new}`}>
      {status}
    </span>
  );
}

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

function BugDashboard({ reports, allReports }: { reports: BugReport[]; allReports: BugReport[] }) {
  const statusCounts = {
    new: allReports.filter(r => r.status === "new").length,
    reviewed: allReports.filter(r => r.status === "reviewed").length,
    actioned: allReports.filter(r => r.status === "actioned").length,
    dismissed: allReports.filter(r => r.status === "dismissed").length,
  };
  const total = allReports.length;
  const open = statusCounts.new + statusCounts.reviewed;
  const resolved = statusCounts.actioned + statusCounts.dismissed;

  const severityCounts = { P0: 0, P1: 0, P2: 0, P3: 0 };
  for (const r of allReports) {
    const a = analyzeBug(r);
    severityCounts[a.severity as keyof typeof severityCounts]++;
  }

  // Reporter leaderboard
  const reporterMap = new Map<string, { count: number; latest: string }>();
  for (const r of allReports) {
    const name = r.app_state?.user_name && r.app_state.user_name !== "anonymous"
      ? r.app_state.user_name
      : r.app_state?.user_id ? `User ${r.app_state.user_id}` : "Anonymous";
    const existing = reporterMap.get(name);
    if (existing) {
      existing.count++;
      if (r.created_at && r.created_at > existing.latest) existing.latest = r.created_at;
    } else {
      reporterMap.set(name, { count: 1, latest: r.created_at || "" });
    }
  }
  const reporters = [...reporterMap.entries()]
    .sort((a, b) => b[1].count - a[1].count)
    .slice(0, 5);

  if (total === 0) {
    return (
      <div className="lg:col-span-3 bg-white rounded-xl border p-12 text-center">
        <div className="text-4xl mb-3">📱</div>
        <h3 className="font-bold text-lg mb-1">No bug reports yet</h3>
        <p className="text-sm text-gray-500">Shake your phone to file the first one!</p>
      </div>
    );
  }

  return (
    <div className="lg:col-span-3 space-y-4">
      {/* Stats Row */}
      <div className="grid grid-cols-4 gap-3">
        <StatCard label="Total" value={total} color="text-gray-900" bg="bg-white" />
        <StatCard label="Open" value={open} color="text-red-700" bg="bg-red-50" />
        <StatCard label="Backlogged" value={statusCounts.actioned} color="text-green-700" bg="bg-green-50" />
        <StatCard label="Dismissed" value={statusCounts.dismissed} color="text-gray-500" bg="bg-gray-50" />
      </div>

      {/* Progress Bar */}
      <div className="bg-white rounded-xl border p-4">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-semibold text-gray-700">Triage Progress</h3>
          <span className="text-xs text-gray-400">{resolved} of {total} resolved</span>
        </div>
        <div className="h-3 rounded-full bg-gray-100 overflow-hidden flex">
          {statusCounts.actioned > 0 && (
            <div className="h-full bg-green-500 transition-all" style={{ width: `${(statusCounts.actioned / total) * 100}%` }} />
          )}
          {statusCounts.dismissed > 0 && (
            <div className="h-full bg-gray-300 transition-all" style={{ width: `${(statusCounts.dismissed / total) * 100}%` }} />
          )}
          {statusCounts.reviewed > 0 && (
            <div className="h-full bg-yellow-400 transition-all" style={{ width: `${(statusCounts.reviewed / total) * 100}%` }} />
          )}
          {statusCounts.new > 0 && (
            <div className="h-full bg-red-400 transition-all" style={{ width: `${(statusCounts.new / total) * 100}%` }} />
          )}
        </div>
        <div className="flex gap-4 mt-2">
          <Legend color="bg-green-500" label="Backlogged" />
          <Legend color="bg-gray-300" label="Dismissed" />
          <Legend color="bg-yellow-400" label="Reviewed" />
          <Legend color="bg-red-400" label="New" />
        </div>
      </div>

      {/* Severity Breakdown */}
      <div className="bg-white rounded-xl border p-4">
        <h3 className="text-sm font-semibold text-gray-700 mb-3">By Severity</h3>
        <div className="space-y-2">
          {(["P0", "P1", "P2", "P3"] as const).map(sev => {
            const count = severityCounts[sev];
            const pct = total > 0 ? (count / total) * 100 : 0;
            const colors = { P0: "bg-red-500", P1: "bg-orange-400", P2: "bg-yellow-400", P3: "bg-gray-300" };
            return (
              <div key={sev} className="flex items-center gap-3">
                <span className={`text-xs font-bold w-6 ${SEVERITY_COLORS[sev]} px-1 py-0.5 rounded text-center`}>{sev}</span>
                <div className="flex-1 h-2 rounded-full bg-gray-100 overflow-hidden">
                  <div className={`h-full rounded-full ${colors[sev]} transition-all`} style={{ width: `${pct}%` }} />
                </div>
                <span className="text-xs text-gray-500 w-6 text-right">{count}</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Reporter Leaderboard */}
      <div className="bg-white rounded-xl border p-4">
        <h3 className="text-sm font-semibold text-gray-700 mb-3">Top Bug Reporters</h3>
        {reporters.length === 0 ? (
          <p className="text-xs text-gray-400">No reports yet</p>
        ) : (
          <div className="space-y-2">
            {reporters.map(([name, data], i) => (
              <div key={name} className="flex items-center gap-3">
                <span className="text-sm w-6 text-center">
                  {i === 0 ? "🏆" : i === 1 ? "🥈" : i === 2 ? "🥉" : `${i + 1}.`}
                </span>
                <div className="flex-1 min-w-0">
                  <span className="text-sm font-medium">{name}</span>
                  <span className="text-xs text-gray-400 ml-2">{data.latest ? timeAgo(data.latest) : ""}</span>
                </div>
                <span className="text-sm font-bold text-gray-700">{data.count}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Recent Reports */}
      <div className="bg-white rounded-xl border p-4">
        <h3 className="text-sm font-semibold text-gray-700 mb-3">Recent Reports</h3>
        <div className="space-y-2">
          {allReports.slice(0, 5).map(r => (
            <div key={r.id} className="flex items-start gap-2 text-xs">
              <span className={`px-1 py-0.5 rounded text-[10px] font-bold shrink-0 ${SEVERITY_COLORS[analyzeBug(r).severity]}`}>
                {analyzeBug(r).severity}
              </span>
              <span className="text-gray-700 line-clamp-1 flex-1">{r.description || "(no description)"}</span>
              <StatusBadge status={r.status} />
              <span className="text-gray-400 shrink-0">{r.created_at ? timeAgo(r.created_at) : ""}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ---------- Analytics Components ----------

const CLOSED_STATUSES = ["actioned", "dismissed", "fixed", "wont_fix"];

function SummaryStats({ reports }: { reports: BugReport[] }) {
  const total = reports.length;
  const open = reports.filter(r => !CLOSED_STATUSES.includes(r.status)).length;
  const fixed = reports.filter(r => r.status === "actioned" || r.status === "fixed").length;

  // Approximate average resolution time: for closed reports with created_at,
  // since we don't track status-change timestamps, we estimate using the
  // time between the oldest and newest report proportionally. For a rough
  // approximation we use the spread of created_at dates among closed reports.
  let avgResolutionLabel = "--";
  const closedWithDate = reports.filter(
    r => CLOSED_STATUSES.includes(r.status) && r.created_at
  );
  if (closedWithDate.length > 0) {
    // Without a status-change timestamp, we estimate resolution time as the
    // average age of closed reports (time from creation to now). This is an
    // upper-bound approximation but the best we can do without change logs.
    const now = Date.now();
    const totalMs = closedWithDate.reduce((sum, r) => {
      return sum + (now - new Date(r.created_at!).getTime());
    }, 0);
    const avgMs = totalMs / closedWithDate.length;
    const avgDays = Math.round(avgMs / (1000 * 60 * 60 * 24));
    if (avgDays < 1) {
      const avgHrs = Math.round(avgMs / (1000 * 60 * 60));
      avgResolutionLabel = `~${avgHrs}h`;
    } else {
      avgResolutionLabel = `~${avgDays}d`;
    }
  }

  return (
    <div className="grid grid-cols-4 gap-3">
      <div className="bg-white rounded-xl border p-4 text-center">
        <div className="text-2xl font-bold text-gray-900">{total}</div>
        <div className="text-xs text-gray-500 mt-0.5">Total Filed</div>
      </div>
      <div className="bg-red-50 rounded-xl border p-4 text-center">
        <div className="text-2xl font-bold text-red-700">{open}</div>
        <div className="text-xs text-gray-500 mt-0.5">Open</div>
      </div>
      <div className="bg-green-50 rounded-xl border p-4 text-center">
        <div className="text-2xl font-bold text-green-700">{fixed}</div>
        <div className="text-xs text-gray-500 mt-0.5">Fixed / Actioned</div>
      </div>
      <div className="bg-blue-50 rounded-xl border p-4 text-center">
        <div className="text-2xl font-bold text-blue-700">{avgResolutionLabel}</div>
        <div className="text-xs text-gray-500 mt-0.5">Avg Resolution</div>
      </div>
    </div>
  );
}

function BurndownChart({ reports }: { reports: BugReport[] }) {
  // Build a 30-day burndown: for each day, count reports that were open
  // (created_at <= day AND status NOT in closed statuses).
  // Since we lack status-change timestamps, we approximate: currently-closed
  // reports are assumed to have been closed "recently" and are treated as open
  // for all days up to the day before today. Currently-open reports are open
  // for all days from their creation onward.
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const days: Date[] = [];
  for (let i = 29; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(d.getDate() - i);
    days.push(d);
  }

  // For each report, determine when it was filed
  const reportDates = reports
    .filter(r => r.created_at)
    .map(r => ({
      createdAt: new Date(r.created_at!),
      isOpen: !CLOSED_STATUSES.includes(r.status),
    }));

  // Compute open count per day
  const openCounts = days.map(day => {
    const endOfDay = new Date(day);
    endOfDay.setHours(23, 59, 59, 999);
    let count = 0;
    for (const r of reportDates) {
      if (r.createdAt <= endOfDay) {
        // Report existed by this day
        if (r.isOpen) {
          // Still open now, so it was open on this day too
          count++;
        } else {
          // Closed now. We assume it was resolved "today" (current day).
          // So it was open on all past days but not today.
          const isBeforeToday = day < today;
          if (isBeforeToday) count++;
        }
      }
    }
    return count;
  });

  const maxCount = Math.max(...openCounts, 1);

  // SVG dimensions
  const W = 600;
  const H = 160;
  const padL = 32;
  const padR = 12;
  const padT = 12;
  const padB = 28;
  const chartW = W - padL - padR;
  const chartH = H - padT - padB;

  // Build polyline points
  const points = openCounts.map((count, i) => {
    const x = padL + (i / (days.length - 1)) * chartW;
    const y = padT + chartH - (count / maxCount) * chartH;
    return `${x},${y}`;
  });
  const polyline = points.join(" ");

  // Build area fill path
  const areaPath = [
    `M ${padL},${padT + chartH}`,
    ...openCounts.map((count, i) => {
      const x = padL + (i / (days.length - 1)) * chartW;
      const y = padT + chartH - (count / maxCount) * chartH;
      return `L ${x},${y}`;
    }),
    `L ${padL + chartW},${padT + chartH}`,
    "Z",
  ].join(" ");

  // Y-axis labels (0, mid, max)
  const yMid = Math.round(maxCount / 2);
  const yLabels = [
    { value: maxCount, y: padT },
    { value: yMid, y: padT + chartH / 2 },
    { value: 0, y: padT + chartH },
  ];

  // X-axis labels — show ~5 evenly spaced dates
  const xLabelIndices = [0, 7, 14, 21, 29].filter(i => i < days.length);

  return (
    <div className="bg-white rounded-xl border p-4">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-semibold text-gray-700">Open Bugs (Last 30 Days)</h3>
        <span className="text-xs text-gray-400">{openCounts[openCounts.length - 1]} open now</span>
      </div>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full"
        style={{ maxHeight: 180 }}
      >
        {/* Grid lines */}
        {yLabels.map(yl => (
          <line
            key={yl.value}
            x1={padL}
            y1={yl.y}
            x2={padL + chartW}
            y2={yl.y}
            stroke="#e5e7eb"
            strokeWidth="1"
          />
        ))}

        {/* Area fill */}
        <path d={areaPath} fill="#dbeafe" opacity="0.6" />

        {/* Line */}
        <polyline
          points={polyline}
          fill="none"
          stroke="#2563eb"
          strokeWidth="2"
          strokeLinejoin="round"
          strokeLinecap="round"
        />

        {/* Data points */}
        {openCounts.map((count, i) => {
          const x = padL + (i / (days.length - 1)) * chartW;
          const y = padT + chartH - (count / maxCount) * chartH;
          return (
            <circle
              key={i}
              cx={x}
              cy={y}
              r="2.5"
              fill="#2563eb"
              stroke="white"
              strokeWidth="1"
            />
          );
        })}

        {/* Y-axis labels */}
        {yLabels.map(yl => (
          <text
            key={`y-${yl.value}`}
            x={padL - 6}
            y={yl.y + 3}
            textAnchor="end"
            fill="#9ca3af"
            fontSize="10"
          >
            {yl.value}
          </text>
        ))}

        {/* X-axis labels */}
        {xLabelIndices.map(idx => {
          const x = padL + (idx / (days.length - 1)) * chartW;
          const d = days[idx];
          const label = `${d.getMonth() + 1}/${d.getDate()}`;
          return (
            <text
              key={`x-${idx}`}
              x={x}
              y={H - 4}
              textAnchor="middle"
              fill="#9ca3af"
              fontSize="10"
            >
              {label}
            </text>
          );
        })}
      </svg>
    </div>
  );
}

function StatCard({ label, value, color, bg }: { label: string; value: number; color: string; bg: string }) {
  return (
    <div className={`${bg} rounded-xl border p-4 text-center`}>
      <div className={`text-2xl font-bold ${color}`}>{value}</div>
      <div className="text-xs text-gray-500 mt-0.5">{label}</div>
    </div>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <div className="flex items-center gap-1">
      <div className={`w-2 h-2 rounded-full ${color}`} />
      <span className="text-[10px] text-gray-400">{label}</span>
    </div>
  );
}
