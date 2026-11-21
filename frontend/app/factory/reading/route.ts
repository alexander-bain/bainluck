import { loadFactoryReading } from "../displayReading";

export const dynamic = "force-dynamic";

export async function GET() {
  return Response.json(await loadFactoryReading(), {
    headers: { "Cache-Control": "no-store" },
  });
}
