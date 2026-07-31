import { NextResponse } from "next/server";

import { frontendBuildMarker } from "@/lib/buildInfo";

/**
 * Public, non-secret frontend build marker — L2-221 Item 2.
 *
 * `GET /api/frontend-build` → `{ "commit": "<40-hex>" | null, "env": "production" | null }`
 *
 * The path is `frontend-build`, not `build`, on purpose: `frontend/.gitignore`
 * carries a `build/` rule for build output, which silently swallowed
 * `app/api/build/` — the route would have been absent in production and the
 * audit rail would have failed closed on a missing marker. It also reads more
 * honestly: this is the FRONTEND's build, distinct from the backend's /health.
 *
 * This is the frontend deployment authority the browser-audit rail polls
 * before it will run. It exposes a commit sha of a public repository and
 * nothing else: no env dump, no secrets, no build config.
 *
 * `force-dynamic` + `no-store` are load-bearing. A cached or statically
 * inlined answer would let the marker report a build that is no longer
 * serving, which is the exact failure this route exists to prevent.
 */
export const dynamic = "force-dynamic";
export const revalidate = 0;

export async function GET() {
  const marker = frontendBuildMarker();
  return NextResponse.json(marker, {
    status: 200,
    headers: {
      "cache-control": "no-store, max-age=0, must-revalidate",
    },
  });
}
