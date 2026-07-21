import { NextResponse } from "next/server";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const maxDuration = 60;

/**
 * Extract the admin secret from the Authorization header only.
 *
 * The old `?secret=` query-param path was removed (#L2-137): query strings are
 * written verbatim to Vercel/edge request logs, so passing the admin token in
 * the URL leaked it into log storage. Callers MUST send `Authorization: Bearer
 * <secret>` instead (see lib/adminFetch.ts). Returns null when absent/malformed.
 */
function extractSecret(request: Request): string | null {
  const header = request.headers.get("authorization") || "";
  const match = header.match(/^Bearer\s+(.+)$/i);
  return match ? match[1].trim() || null : null;
}

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const path = searchParams.get("path");
  const secret = extractSecret(request);

  if (!secret || !path) {
    return NextResponse.json({ error: "Missing Authorization header or path" }, { status: 400 });
  }

  const allowed = [
    "/api/admin/backfill-winners/status",
    "/api/admin/calibration-data",
    "/api/calibration",
  ];
  if (!allowed.includes(path)) {
    return NextResponse.json({ error: "Path not allowed" }, { status: 403 });
  }

  try {
    const res = await fetch(`${API_URL}${path}`, {
      cache: "no-store",
      signal: AbortSignal.timeout(55000),
      headers: { Authorization: `Bearer ${secret}` },
    });
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      return NextResponse.json({ error: "Backend error", status: res.status, detail: text.slice(0, 300) }, { status: res.status });
    }
    return NextResponse.json(await res.json());
  } catch (err: unknown) {
    return NextResponse.json({ error: "Fetch failed", detail: err instanceof Error ? err.message : String(err) }, { status: 502 });
  }
}

export async function POST(request: Request) {
  const { searchParams } = new URL(request.url);
  const path = searchParams.get("path");
  const secret = extractSecret(request);

  if (!secret || !path) {
    return NextResponse.json({ error: "Missing Authorization header or path" }, { status: 400 });
  }

  const allowed = ["/api/admin/backfill-winners"];
  if (!allowed.includes(path)) {
    return NextResponse.json({ error: "Path not allowed" }, { status: 403 });
  }

  // Forward all remaining query params (excluding path; secret is no longer a
  // query param — it arrives via the Authorization header).
  const params = new URLSearchParams();
  for (const [key, value] of searchParams.entries()) {
    if (key !== "path" && key !== "secret") {
      params.set(key, value);
    }
  }

  const queryString = params.toString();
  const url = queryString ? `${API_URL}${path}?${queryString}` : `${API_URL}${path}`;

  try {
    const res = await fetch(url, {
      method: "POST",
      cache: "no-store",
      signal: AbortSignal.timeout(55000),
      headers: { Authorization: `Bearer ${secret}` },
    });
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      return NextResponse.json({ error: "Backend error", status: res.status, detail: text.slice(0, 300) }, { status: res.status });
    }
    return NextResponse.json(await res.json());
  } catch (err: unknown) {
    return NextResponse.json({ error: "Fetch failed", detail: err instanceof Error ? err.message : String(err) }, { status: 502 });
  }
}
