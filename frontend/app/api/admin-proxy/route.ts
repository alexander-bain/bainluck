import { NextResponse } from "next/server";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const maxDuration = 60;

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const path = searchParams.get("path");
  const secret = searchParams.get("secret");

  if (!secret || !path) {
    return NextResponse.json({ error: "Missing secret or path" }, { status: 400 });
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
  const secret = searchParams.get("secret");

  if (!secret || !path) {
    return NextResponse.json({ error: "Missing secret or path" }, { status: 400 });
  }

  const allowed = ["/api/admin/backfill-winners"];
  if (!allowed.includes(path)) {
    return NextResponse.json({ error: "Path not allowed" }, { status: 403 });
  }

  // Forward all remaining query params (excluding path and secret)
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
