import { NextResponse } from "next/server";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const maxDuration = 60;

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const secret = searchParams.get("secret");

  if (!secret) {
    return NextResponse.json({ error: "Missing secret" }, { status: 400 });
  }

  const url = `${API_URL}/api/admin/calibration-data?secret=${encodeURIComponent(secret)}`;

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 55000);

  try {
    const res = await fetch(url, {
      cache: "no-store",
      signal: controller.signal,
    });
    clearTimeout(timeout);

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
    clearTimeout(timeout);
    const message = err instanceof Error ? err.message : String(err);
    return NextResponse.json(
      { error: "Fetch failed", detail: message, url: API_URL },
      { status: 502 }
    );
  }
}
