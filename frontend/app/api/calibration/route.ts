import { NextResponse } from "next/server";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const maxDuration = 60;

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const secret = searchParams.get("secret");

  if (!secret) {
    return NextResponse.json({ error: "Missing secret" }, { status: 400 });
  }

  try {
    const res = await fetch(
      `${API_URL}/api/admin/calibration-data?secret=${encodeURIComponent(secret)}`,
      { cache: "no-store", signal: AbortSignal.timeout(55000) }
    );

    if (!res.ok) {
      const text = await res.text().catch(() => "");
      return NextResponse.json(
        { error: "Backend error", status: res.status, detail: text.slice(0, 200) },
        { status: res.status }
      );
    }

    const data = await res.json();
    return NextResponse.json(data);
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: "Fetch failed", detail: message }, { status: 502 });
  }
}
