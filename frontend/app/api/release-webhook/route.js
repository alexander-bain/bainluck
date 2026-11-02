import { handleReleaseWebhook } from '../../../lib/releaseWebhook.mjs';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function POST(request) {
  // App release payloads are small; reject unexpected bodies before HMAC/JSON.
  if (Number(request.headers.get('content-length') || 0) > 65536) {
    return Response.json({ error: 'webhook payload too large' }, { status: 413 });
  }
  const body = await request.text();
  if (Buffer.byteLength(body) > 65536) {
    return Response.json({ error: 'webhook payload too large' }, { status: 413 });
  }
  const result = await handleReleaseWebhook({
    body,
    signature: request.headers.get('heroku-webhook-hmac-sha256'),
    secret: process.env.HEROKU_RELEASE_WEBHOOK_SECRET,
    dispatch: async (event) => {
      const token = process.env.RELEASE_DISPATCH_TOKEN;
      if (!token) throw new Error('release dispatch is not configured');
      const response = await fetch('https://api.github.com/repos/alexander-bain/bainluck/dispatches', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          Accept: 'application/vnd.github+json',
          'X-GitHub-Api-Version': '2022-11-28',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(event),
        signal: AbortSignal.timeout(10000),
      });
      if (response.status !== 204) throw new Error('release dispatch failed');
    },
  });
  return Response.json(result.body, { status: result.status });
}
