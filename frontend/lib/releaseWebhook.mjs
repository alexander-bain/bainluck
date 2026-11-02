import { createHmac, timingSafeEqual } from 'node:crypto';

// Only the server route imports this module. It never reads a browser env var.
export async function handleReleaseWebhook({ body, signature, secret, dispatch }) {
  if (!secret) return { status: 503, body: { error: 'release relay is not configured' } };
  const expected = createHmac('sha256', secret).update(body).digest();
  const actual = Buffer.from(signature || '', 'base64');
  if (actual.length !== expected.length || !timingSafeEqual(actual, expected)) {
    return { status: 401, body: { error: 'invalid webhook signature' } };
  }
  let event;
  try { event = JSON.parse(body); } catch { return { status: 400, body: { error: 'invalid webhook payload' } }; }
  if (event?.resource !== 'release' || !['create', 'update'].includes(event?.action) ||
      event?.data?.status !== 'succeeded' || event?.data?.app?.name !== 'bainluck') {
    return { status: 202, body: { ignored: true } };
  }
  if (typeof event.id !== 'string' || typeof event.data.id !== 'string' ||
      event.id.length > 128 || event.data.id.length > 128) {
    return { status: 400, body: { error: 'release identity missing' } };
  }
  try {
    await dispatch({ event_type: 'heroku-release', client_payload: {
      provider: 'heroku', candidate_id: event.data.id, event_id: event.id,
    } });
    return { status: 202, body: { accepted: true } };
  } catch {
    // Heroku retries a non-2xx delivery. Never return success on a lost dispatch.
    return { status: 503, body: { error: 'release dispatch failed' } };
  }
}
