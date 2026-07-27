"use client";

// L2-153 — the Sentinels card. r236 found the flow + grid sentinels sitting at
// `no_run_cached` ~6h after their beats with NOTHING surfacing it: the guards had
// no guard. Standing doctrine is that no alert class may be email/Sentry-only —
// board + cockpit RED or it isn't alerting. This card gives the sentinel FAMILY a
// cockpit presence by reading the three existing `/last` endpoints directly and,
// critically, treating a silent sentinel (no_run_cached, or a run older than
// ~1.5× its beat interval) as RED "sentinel silent" — the exact state r236 caught
// invisibly.
//
// Frontend-only: no backend touched. The verdict/age extraction is a pure,
// exported function (`evaluateSentinel`) so the three states — fresh-green,
// red-verdict, silent-red — are unit-tested deterministically.

import useSWR from "swr";
import { useAdminAuth } from "@/components/admin/AdminAuthProvider";
import { adminFetchJSON } from "@/lib/adminFetch";

// Silence rule: a sentinel that last ran longer ago than this multiple of its
// beat interval can no longer be trusted, so its cached verdict is overridden to
// a RED "silent" — a stale GREEN is worse than an honest RED.
export const SILENCE_MULTIPLIER = 1.5;

export interface SentinelSpec {
  key: "flow" | "grid" | "settled" | "board";
  label: string;
  endpoint: string;
  beatLabel: string; // human-readable beat, e.g. "daily 07:10Z"
  beatIntervalHours: number; // 24 for the daily beats
}

// Beat intervals from CLAUDE.md / the task schedules: flow 07:10Z, grid 07:25Z,
// settled-concept 07:45Z, board 07:50Z — all daily (24h).
export const SENTINELS: SentinelSpec[] = [
  {
    key: "flow",
    label: "Flow Sentinel",
    endpoint: "/api/admin/flow-sentinel/last",
    beatLabel: "daily 07:10Z",
    beatIntervalHours: 24,
  },
  {
    key: "grid",
    label: "Grid Sentinel",
    endpoint: "/api/admin/grid-sentinel/last",
    beatLabel: "daily 07:25Z",
    beatIntervalHours: 24,
  },
  {
    key: "settled",
    label: "Settled-Concept Sentinel",
    endpoint: "/api/admin/settled-concept-sentinel/last",
    beatLabel: "daily 07:45Z",
    beatIntervalHours: 24,
  },
  {
    key: "board",
    label: "Board Sentinel",
    endpoint: "/api/admin/board-sentinel/last",
    beatLabel: "daily 07:50Z",
    beatIntervalHours: 24,
  },
];

export type SentinelStatus = "green" | "red" | "amber";

export interface SentinelView {
  status: SentinelStatus; // row color
  headline: string; // verdict chip: GREEN / RED / SILENT / UNREACHABLE
  detail: string; // one-line context
  ageText: string; // "ran 2h ago" / "no run cached" / "unreachable"
}

// Last-run timestamp. As of #232 all three sentinels persist `generated_at`
// (ISO) in their cached `/last` payload, so real ages ("ran 6h ago") + the
// >1.5×-beat stale-RED check below apply uniformly to flow, grid, and settled.
// The null return is a defensive fallback for the deploy-transition window
// (a pre-#232 payload with no timestamp) — it degrades to "age unknown", never
// a false RED. Returns ms or null.
function lastRunMs(payload: Record<string, unknown> | null): number | null {
  if (!payload) return null;
  const gen = payload["generated_at"];
  if (typeof gen === "string") {
    const t = Date.parse(gen);
    if (!Number.isNaN(t)) return t;
  }
  const asOf = payload["as_of"]; // date-only fallback (less precise)
  if (typeof asOf === "string") {
    const t = Date.parse(asOf);
    if (!Number.isNaN(t)) return t;
  }
  return null;
}

function humanizeAge(ms: number): string {
  const hrs = ms / 3_600_000;
  if (hrs < 1) return `ran ${Math.max(1, Math.round(ms / 60_000))}m ago`;
  if (hrs < 48) return `ran ${Math.round(hrs)}h ago`;
  return `ran ${Math.round(hrs / 24)}d ago`;
}

// Pull the per-sentinel verdict (real defects) + a one-line detail out of the
// raw scorecard. Returns { red, detail } where red=true means a REAL finding.
function extractVerdict(
  key: SentinelSpec["key"],
  p: Record<string, unknown>,
): { red: boolean; detail: string; amber?: boolean } {
  if (key === "flow") {
    const sc = (p["scorecard"] as Record<string, unknown>) ?? {};
    const total = Number(sc["flows_total"] ?? 0);
    const failed = Number(sc["flows_failed"] ?? 0);
    const passed = Number(sc["flows_passed"] ?? total - failed);
    if (failed > 0) {
      const per = (sc["per_flow"] as Array<Record<string, unknown>>) ?? [];
      const names = per
        .filter((f) => f["passed"] === false && f["skipped"] !== true)
        .map((f) => String(f["flow"]).replace(/_/g, " "));
      return {
        red: true,
        detail: `${failed} of ${total} flows failing${names.length ? `: ${names.join(", ")}` : ""}`,
      };
    }
    return { red: false, detail: `${passed}/${total} flows passing` };
  }

  if (key === "grid") {
    const sc = (p["scorecard"] as Record<string, unknown>) ?? {};
    const total = Number(sc["leagues_total"] ?? 0);
    const redCt = Number(sc["leagues_red"] ?? 0);
    const green = Number(sc["leagues_green"] ?? total - redCt);
    if (redCt > 0) {
      const per = (sc["per_league"] as Array<Record<string, unknown>>) ?? [];
      const names = per
        .filter((l) => l["verdict"] === "red")
        .map((l) => String(l["league"]));
      return {
        red: true,
        detail: `${redCt} of ${total} leagues RED${names.length ? `: ${names.join(", ")}` : ""}`,
      };
    }
    return { red: false, detail: `${green}/${total} leagues green` };
  }

  if (key === "board") {
    // Queue #258: verdict ∈ {red, green, unknown}. UNKNOWN (couldn't fully
    // measure — e.g. the board column read failed) reads AMBER, never GREEN and
    // never a false RED.
    const verdict = String(p["verdict"] ?? "");
    const real = (p["real"] as Array<Record<string, unknown>>) ?? [];
    const counts = (p["counts"] as Record<string, unknown>) ?? {};
    const scanned = Number(counts["open_alert_intake"] ?? 0);
    if (verdict === "red" || real.length > 0) {
      const kinds = [...new Set(real.map((f) => String(f["check"])))];
      return {
        red: true,
        detail: `${real.length} board-hygiene defect(s)${kinds.length ? `: ${kinds.join(", ")}` : ""}`,
      };
    }
    if (verdict === "unknown") {
      const unk = (p["unknown"] as unknown[]) ?? [];
      return {
        red: false,
        amber: true,
        detail: `could not fully measure the board (${unk.length} unknown) — not asserting clean`,
      };
    }
    return { red: false, detail: `board clean · ${scanned} alert-intake scanned` };
  }

  // settled-concept
  const targets = Number(p["targets"] ?? p["checked_settled"] ?? 0);
  const redCt = Number(p["red"] ?? 0);
  const green = Number(p["green"] ?? 0);
  if (redCt > 0) {
    const concepts = (p["concepts"] as Array<Record<string, unknown>>) ?? [];
    const names = concepts
      .filter((c) => c["verdict"] === "RED")
      .map((c) => String(c["name"] ?? c["concept_key"]));
    return {
      red: true,
      detail: `${redCt} RED of ${targets} concepts${names.length ? `: ${names.join(", ")}` : ""}`,
    };
  }
  return { red: false, detail: `${targets} targets · ${green} green · 0 red` };
}

/**
 * Pure evaluation of one sentinel's cached run into a display row. Injecting
 * `nowMs` keeps it deterministic and testable.
 * - fetchError → amber "unreachable" (never hidden; not a false RED)
 * - payload.status === "no_run_cached" → RED "silent" (the r236 state)
 * - populated + last-run older than SILENCE_MULTIPLIER × beat → RED "silent"
 * - populated + real finding → RED (verdict)
 * - populated + clean + fresh → GREEN
 */
export function evaluateSentinel(
  spec: SentinelSpec,
  payload: Record<string, unknown> | null,
  fetchError: boolean,
  nowMs: number,
): SentinelView {
  if (fetchError) {
    return {
      status: "amber",
      headline: "UNREACHABLE",
      detail: `Endpoint error — can't confirm the sentinel ran (beat: ${spec.beatLabel}).`,
      ageText: "unreachable",
    };
  }

  if (!payload || payload["status"] === "no_run_cached") {
    return {
      status: "red",
      headline: "SILENT",
      detail: `No run cached — the sentinel has not run (beat: ${spec.beatLabel}). A silent guard is a RED, not a pass.`,
      ageText: "no run cached",
    };
  }

  const ranMs = lastRunMs(payload);
  const ageMs = ranMs != null ? nowMs - ranMs : null;
  const silenceThresholdMs = spec.beatIntervalHours * SILENCE_MULTIPLIER * 3_600_000;

  const { red, detail, amber } = extractVerdict(spec.key, payload);

  // A run older than 1.5× its beat can't be trusted — override to silent-RED.
  if (ageMs != null && ageMs > silenceThresholdMs) {
    return {
      status: "red",
      headline: "SILENT",
      detail: `Last ran ${humanizeAge(ageMs)} — older than 1.5× the ${spec.beatLabel} beat, so its verdict may be stale.`,
      ageText: humanizeAge(ageMs),
    };
  }

  // Post-#232 all carry generated_at, so ageMs is normally set; the "age unknown"
  // fallback only shows during the deploy-transition window.
  const ageText = ageMs != null ? humanizeAge(ageMs) : "age unknown";
  if (red) {
    return { status: "red", headline: "RED", detail, ageText };
  }
  // Board Sentinel UNKNOWN (couldn't fully measure) → AMBER, distinct from GREEN.
  if (amber) {
    return { status: "amber", headline: "UNKNOWN", detail, ageText };
  }
  return { status: "green", headline: "GREEN", detail, ageText };
}

// --- Presentational bits (design-system tokens; light-mode only) ---

function chipClass(status: SentinelStatus): string {
  switch (status) {
    case "green":
      return "bg-green-500/10 text-green-600";
    case "red":
      return "bg-accent-danger/15 text-accent-danger";
    default:
      return "bg-yellow-500/15 text-yellow-600";
  }
}

function dotClass(status: SentinelStatus): string {
  switch (status) {
    case "green":
      return "bg-green-500";
    case "red":
      return "bg-accent-danger";
    default:
      return "bg-yellow-500";
  }
}

function SentinelRowView({ spec }: { spec: SentinelSpec }) {
  const { secret } = useAdminAuth();
  const { data, error } = useSWR<Record<string, unknown>>(
    secret ? [`sentinel-${spec.key}`, secret] : null,
    () => adminFetchJSON<Record<string, unknown>>(spec.endpoint, secret),
    { refreshInterval: 300000 },
  );

  const loading = !!secret && data === undefined && !error;
  const view = evaluateSentinel(
    spec,
    (data as Record<string, unknown>) ?? null,
    !!error,
    Date.now(),
  );

  return (
    <li className="flex items-start gap-2 text-sm py-2 border-b border-surface-border last:border-0">
      <span className={"h-2 w-2 rounded-full shrink-0 mt-1.5 " + dotClass(view.status)} />
      <span className="flex-1 min-w-0">
        <span className="flex items-center gap-2 flex-wrap">
          <span className="text-text-primary font-medium">{spec.label}</span>
          <span
            className={
              "rounded px-1.5 py-0.5 text-micro font-bold shrink-0 " + chipClass(view.status)
            }
          >
            {loading ? "…" : view.headline}
          </span>
          <span className="text-micro text-text-muted">
            {loading ? "loading…" : view.ageText}
          </span>
        </span>
        <span className="text-micro text-text-muted block leading-relaxed mt-0.5">
          {loading ? `Reading ${spec.endpoint}…` : view.detail}
        </span>
      </span>
    </li>
  );
}

/**
 * The Sentinels card — one row per sentinel (Flow / Grid / Settled-Concept /
 * Board), each showing verdict chip, last-run age, and a one-line detail. A silent
 * sentinel reads RED so the guard-of-the-guards can't itself go dark unnoticed.
 */
export default function SentinelsCard() {
  return (
    <div className="rounded-xl border border-surface-border bg-surface-card p-4">
      <div className="flex items-center justify-between mb-1">
        <h3 className="text-sm font-semibold text-text-primary">Sentinels</h3>
        <span className="text-micro text-text-muted">guard-of-the-guards</span>
      </div>
      <p className="text-micro text-text-muted mb-2 leading-relaxed">
        Daily reliability guards. A silent sentinel (no run cached, or a run older
        than 1.5× its beat) is RED — a guard that goes dark can&apos;t be a pass.
      </p>
      <ul>
        {SENTINELS.map((s) => (
          <SentinelRowView key={s.key} spec={s} />
        ))}
      </ul>
    </div>
  );
}
