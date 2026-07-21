"use client";

import { useState } from "react";
import { useAdminAuth } from "@/components/admin/AdminAuthProvider";
import { adminFetchJSON } from "@/lib/adminFetch";

// L2-142 Item 1/3 — the one-tap "File this" rail affordance. Any red/amber
// cockpit signal (a tile with no linked issue, a firing watchdog check, a
// System Diagnosis blurb) gets this button. Tapping it POSTs to the on-demand
// rail (/api/admin/file-issue), which files (or dedup-comments) a real GitHub
// issue, then the button flips to "filed #N → handled". RED becomes a state
// that resolves itself in front of Alex.

interface FileThisButtonProps {
  /** Where the tap came from — part of the dedup key. */
  source: string;
  /** Stable identifier for the underlying signal (tile key / check name / title). */
  itemKey: string;
  title: string;
  body?: string;
  /** P0..P3, or the diagnosis vocab (critical/warning/info). */
  severity?: string | null;
  labels?: string[];
  /** Compact = the inline tile variant; default is the diagnosis-row variant. */
  compact?: boolean;
  onFiled?: (issue: number, url: string) => void;
}

interface FileIssueResponse {
  status: string;
  issue: number;
  url: string;
}

export default function FileThisButton({
  source,
  itemKey,
  title,
  body,
  severity,
  labels,
  compact,
  onFiled,
}: FileThisButtonProps) {
  const { secret } = useAdminAuth();
  const [state, setState] = useState<"idle" | "filing" | "filed" | "error">("idle");
  const [filed, setFiled] = useState<{ number: number; url: string } | null>(null);

  async function file() {
    if (!secret || state === "filing") return;
    setState("filing");
    try {
      const res = await adminFetchJSON<FileIssueResponse>("/api/admin/file-issue", secret, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source,
          key: itemKey,
          title,
          body: body ?? "",
          severity: severity ?? null,
          labels: labels ?? [],
        }),
      });
      setFiled({ number: res.issue, url: res.url });
      setState("filed");
      onFiled?.(res.issue, res.url);
    } catch {
      setState("error");
    }
  }

  if (state === "filed" && filed) {
    return (
      <a
        href={filed.url}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-1 shrink-0 text-micro font-medium text-green-600 hover:underline"
        title="Issue filed on the project board Inbox"
      >
        filed #{filed.number} → handled
      </a>
    );
  }

  const base = compact
    ? "inline-flex items-center shrink-0 rounded-md px-1.5 py-0.5 text-micro font-medium"
    : "inline-flex items-center gap-1 text-[11px] font-medium";
  const tone =
    state === "error"
      ? "bg-accent-danger/15 text-accent-danger hover:bg-accent-danger/25"
      : "bg-accent-brand/10 text-accent-brand hover:bg-accent-brand/20";

  return (
    <button
      onClick={file}
      disabled={state === "filing" || !secret}
      className={`${base} ${tone} disabled:opacity-50`}
      title={secret ? "File a GitHub issue for this — one tap" : "Enter admin secret to file"}
    >
      {state === "filing" ? "Filing…" : state === "error" ? "Retry file" : "File this"}
    </button>
  );
}
