"use client";

import { useState, useEffect, useCallback } from "react";
import { getAuth } from "firebase/auth";

interface BugReport {
  id: number;
  user_id: number | null;
  session_id: string | null;
  description: string | null;
  has_screenshot: boolean;
  screenshot_base64: string | null;
  app_state: Record<string, string> | null;
  status: string;
  admin_notes: string | null;
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
curl -s "${API}/api/admin/bug-reports/${r.id}/screenshot?secret=cleanup-soccer-2024" -o /tmp/bug_${r.id}.jpg && echo "Screenshot saved to /tmp/bug_${r.id}.jpg"
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
  const [reports, setReports] = useState<BugReport[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("all");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [copied, setCopied] = useState(false);
  const [showPrompt, setShowPrompt] = useState(false);

  const secret =
    typeof window !== "undefined"
      ? new URLSearchParams(window.location.search).get("secret") || ""
      : "";

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

  const selectReport = (id: number) => {
    setSelectedId(id);
    setShowPrompt(false);
    const report = reports.find(r => r.id === id);
    if (report && report.status === "new") {
      updateStatus(id, "reviewed");
    }
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
            <h1 className="text-2xl font-bold mt-1">Bug Reports</h1>
            <p className="text-sm text-gray-500">{reports.length} reports</p>
          </div>
          <div className="flex gap-2">
            {["all", "new", "reviewed", "actioned", "dismissed"].map((s) => (
              <button
                key={s}
                onClick={() => setFilter(s)}
                className={`px-3 py-1.5 rounded-full text-sm font-medium ${
                  filter === s
                    ? "bg-blue-600 text-white"
                    : "bg-white text-gray-600 border hover:bg-gray-50"
                }`}
              >
                {s.charAt(0).toUpperCase() + s.slice(1)}
                {s === "new" && reports.filter(r => r.status === "new").length > 0 && (
                  <span className="ml-1.5 bg-red-500 text-white text-xs rounded-full px-1.5">
                    {reports.filter(r => r.status === "new").length}
                  </span>
                )}
              </button>
            ))}
          </div>
        </div>

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
                          <span className="text-xs text-gray-400">
                            {r.app_state?.user_id ? `user ${r.app_state.user_id}` : "anonymous"}
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
                      {selected.status === "actioned" ? "✓ Added to Backlog" : "Mark as Added to Backlog"}
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
              <div className="lg:col-span-3 bg-white rounded-xl border p-12 text-center text-gray-400">
                Select a report to view details
              </div>
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
