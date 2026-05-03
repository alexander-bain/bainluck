"use client";

import { useState, useEffect, useCallback } from "react";

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

const API = process.env.NEXT_PUBLIC_API_URL || "https://api.bainluck.com";

export default function BugReportsPage() {
  const [reports, setReports] = useState<BugReport[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("new");
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const secret =
    typeof window !== "undefined"
      ? new URLSearchParams(window.location.search).get("secret") || ""
      : "";

  const loadReports = useCallback(async () => {
    if (!secret) return;
    setLoading(true);
    try {
      const statusParam = filter === "all" ? "" : `&status=${filter}`;
      const res = await fetch(
        `${API}/api/admin/bug-reports?secret=${secret}${statusParam}&limit=100`
      );
      const data = await res.json();
      setReports(data.reports || []);
    } catch {
      setReports([]);
    }
    setLoading(false);
  }, [secret, filter]);

  useEffect(() => {
    loadReports();
  }, [loadReports]);

  const updateStatus = async (id: number, newStatus: string) => {
    await fetch(
      `${API}/api/admin/bug-reports/${id}?secret=${secret}&status=${newStatus}`,
      { method: "PATCH" }
    );
    loadReports();
  };

  const selected = reports.find((r) => r.id === selectedId);

  if (!secret) {
    return (
      <div className="p-8 text-center text-gray-500">
        Add ?secret=YOUR_ADMIN_TOKEN to the URL
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-7xl mx-auto px-4 py-6">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold">Bug Reports (Rage Shake)</h1>
          <div className="flex gap-2">
            {["new", "reviewed", "actioned", "dismissed", "all"].map((s) => (
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
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* List */}
            <div className="space-y-3">
              {reports.map((r) => (
                <div
                  key={r.id}
                  onClick={() => setSelectedId(r.id)}
                  className={`p-4 rounded-xl border cursor-pointer transition-all ${
                    selectedId === r.id
                      ? "border-blue-500 bg-blue-50 shadow-md"
                      : "border-gray-200 bg-white hover:border-gray-300"
                  }`}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-sm truncate">
                        {r.description || "(no description)"}
                      </p>
                      <div className="flex items-center gap-2 mt-1">
                        <StatusBadge status={r.status} />
                        <span className="text-xs text-gray-400">
                          {r.created_at
                            ? new Date(r.created_at).toLocaleString()
                            : ""}
                        </span>
                        {r.app_state?.platform && (
                          <span className="text-xs text-gray-400">
                            {r.app_state.platform}
                          </span>
                        )}
                      </div>
                    </div>
                    {r.has_screenshot && (
                      <div className="w-12 h-12 rounded bg-gray-100 flex items-center justify-center text-gray-400 text-xs ml-3">
                        📷
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>

            {/* Detail */}
            {selected ? (
              <div className="bg-white rounded-xl border p-6 sticky top-6 space-y-4">
                <div className="flex items-center justify-between">
                  <h2 className="font-bold">Bug Report #{selected.id}</h2>
                  <StatusBadge status={selected.status} />
                </div>

                <p className="text-sm">
                  {selected.description || "(no description)"}
                </p>

                {selected.screenshot_base64 && (
                  <img
                    src={`data:image/jpeg;base64,${selected.screenshot_base64}`}
                    alt="Bug screenshot"
                    className="rounded-lg border max-h-96 w-full object-contain bg-gray-50"
                  />
                )}

                {selected.app_state && (
                  <div className="text-xs space-y-1">
                    <p className="font-semibold text-gray-500 uppercase tracking-wider">
                      App State
                    </p>
                    {Object.entries(selected.app_state).map(([k, v]) => (
                      <div key={k} className="flex justify-between">
                        <span className="text-gray-400">{k}</span>
                        <span className="text-gray-700 font-mono">{v}</span>
                      </div>
                    ))}
                  </div>
                )}

                <div className="flex gap-2 pt-2">
                  {["new", "reviewed", "actioned", "dismissed"].map((s) => (
                    <button
                      key={s}
                      onClick={() => updateStatus(selected.id, s)}
                      disabled={selected.status === s}
                      className={`px-3 py-1.5 rounded text-xs font-medium ${
                        selected.status === s
                          ? "bg-gray-200 text-gray-400"
                          : "bg-gray-100 text-gray-600 hover:bg-gray-200"
                      }`}
                    >
                      {s.charAt(0).toUpperCase() + s.slice(1)}
                    </button>
                  ))}
                </div>

                <div className="text-xs text-gray-400">
                  User: {selected.user_id || "anonymous"} · Session:{" "}
                  {selected.session_id?.slice(0, 8) || "?"}
                </div>
              </div>
            ) : (
              <div className="bg-white rounded-xl border p-12 text-center text-gray-400">
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
    <span
      className={`px-2 py-0.5 rounded-full text-xs font-medium ${
        colors[status] || colors.new
      }`}
    >
      {status}
    </span>
  );
}
