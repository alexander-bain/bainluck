import { drainAuthorized, handleLogDrain, MAX_DRAIN_BYTES } from '../../../lib/releaseLogDrain.mjs';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function POST(request) {
  const authorization = request.headers.get('authorization');
  const secret = process.env.RELEASE_LOG_DRAIN_TOKEN;
  if (!drainAuthorized(authorization, secret)) {
    return Response.json({ error: 'invalid drain authorization' }, { status: 401 });
  }
  async function forwardCollector(body, loss = false) {
    const configuredOrigin = process.env.RELEASE_LOG_API_ORIGIN;
    if (!configuredOrigin) throw new Error('collector destination is not configured');
    const origin = new URL(configuredOrigin);
    if (origin.protocol !== 'https:' || origin.username || origin.password || origin.search || origin.hash || !['', '/'].includes(origin.pathname)) {
      throw new Error('collector origin is invalid');
    }
    const headers = { Authorization: `Bearer ${secret}`, 'Content-Type': 'application/logplex-1' };
    if (loss) headers['X-Release-Log-Loss'] = '1';
    const response = await fetch(`${origin.origin}/api/release-logs/drain`, {
      method: 'POST', headers, body, signal: AbortSignal.timeout(10000),
    });
    if (response.status !== 202) throw new Error('collector did not accept the batch');
  }
  const chunks = [];
  let total = 0;
  const reader = request.body?.getReader();
  if (reader) {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      total += value.length;
      if (total > MAX_DRAIN_BYTES) {
        await reader.cancel();
        try { await forwardCollector(Buffer.alloc(0), true); } catch {
          return Response.json({ error: 'durable log collector unavailable' }, { status: 503 });
        }
        return Response.json({ error: 'drain body exceeds limit' }, { status: 413 });
      }
      chunks.push(Buffer.from(value));
    }
  }
  const result = await handleLogDrain({
    body: Buffer.concat(chunks), authorization, secret,
    forward: forwardCollector,
  });
  return Response.json(result.body, { status: result.status });
}
