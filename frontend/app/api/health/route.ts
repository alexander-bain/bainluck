import { NextResponse } from "next/server";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function GET() {
  try {
    const res = await fetch(`${API_URL}/docs`, {
      cache: "no-store",
      signal: AbortSignal.timeout(10000),
    });
    return NextResponse.json({
      backend_status: res.status,
      api_url: API_URL,
      timestamp: new Date().toISOString(),
    });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    return NextResponse.json({
      error: message,
      api_url: API_URL,
      timestamp: new Date().toISOString(),
    });
  }
}
