import { timingSafeEqual } from 'node:crypto';

export class HttpError extends Error {
  constructor(status, code) { super(code); this.status = status; }
}
export function fail(status, code) { throw new HttpError(status, code); }
export function json(value, status = 200, headers) {
  const response = Response.json(value, { status, headers });
  response.headers.set('cache-control', 'private, no-store');
  response.headers.set('x-content-type-options', 'nosniff');
  response.headers.set('referrer-policy', 'no-referrer');
  return response;
}
export async function safe(action) {
  try { return await action(); }
  catch (error) {
    const code = error instanceof HttpError ? error.message : 'temporarily_unavailable';
    return json({ error: code, code: code.toUpperCase() }, error instanceof HttpError ? error.status : 503);
  }
}
export async function hash(value) {
  const bytes = typeof value === 'string' ? new TextEncoder().encode(value) : value;
  return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)),
    (x) => x.toString(16).padStart(2, '0')).join('');
}
export async function equalSecret(a, b) {
  // Compare fixed-length digests with the runtime constant-time primitive.
  return timingSafeEqual(new TextEncoder().encode(await hash(a)), new TextEncoder().encode(await hash(b)));
}
export async function publisher(request, env) {
  const token = request.headers.get('authorization')?.match(/^Bearer (\S{1,512})$/)?.[1] ?? '';
  if (typeof env.PUBLISH_TOKEN !== 'string' || env.PUBLISH_TOKEN.length < 32) return false;
  return equalSecret(token, env.PUBLISH_TOKEN);
}
export function originFor(request, env) {
  const incoming = new URL(request.url);
  let expected;
  try { expected = new URL(env.APP_ORIGIN || incoming.origin); } catch { fail(503, 'invalid_origin_config'); }
  if (expected.protocol !== 'https:' || expected.origin !== (env.APP_ORIGIN || incoming.origin)
      || expected.username || expected.password) fail(503, 'invalid_origin_config');
  if (!env.APP_ORIGIN && !expected.hostname.endsWith('.workers.dev')) fail(503, 'configure_app_origin');
  if (incoming.origin !== expected.origin) fail(403, 'wrong_origin');
  return expected.origin;
}
export function sameOrigin(request, origin) {
  if (request.headers.get('origin') !== origin
      || request.headers.get('sec-fetch-site') === 'cross-site') fail(403, 'invalid_origin');
}
export function privateRead(request, origin) {
  const sent = request.headers.get('origin');
  if ((sent && sent !== origin) || request.headers.get('sec-fetch-site') === 'cross-site') fail(403, 'invalid_origin');
}
export async function rawBody(request, limit = 65536) {
  if (Number(request.headers.get('content-length')) > limit) fail(413, 'body_too_large');
  if (request.headers.get('content-encoding') && request.headers.get('content-encoding') !== 'identity') fail(415, 'unsupported_encoding');
  const reader = request.body?.getReader();
  if (!reader) return new Uint8Array();
  const chunks = [];
  let length = 0;
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      length += value.byteLength;
      if (length > limit) { await reader.cancel(); fail(413, 'body_too_large'); }
      chunks.push(value);
    }
  } finally { reader.releaseLock(); }
  const bytes = new Uint8Array(length);
  let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
  return bytes;
}
export function parseJson(bytes) {
  try { return JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes)); }
  catch { fail(400, 'invalid_json'); }
}
export function requireJson(request) {
  if (request.headers.get('content-type')?.split(';')[0].trim().toLowerCase() !== 'application/json') fail(415, 'expected_json');
}
export function cookie(request, name) {
  const matches = (request.headers.get('cookie') || '').split(';').map((s) => s.trim())
    .filter((s) => s.startsWith(`${name}=`));
  if (matches.length !== 1) return null;
  const value = matches[0].slice(name.length + 1);
  return /^[A-Za-z0-9_-]{43}$/.test(value) ? value : null;
}
export function cookieHeader(name, value, ttl) {
  return `${name}=${value}; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=${ttl}`;
}
export function cookieNames(project) {
  return { binding: `__Host-hp-binding-${project}`, session: `__Host-hp-session-${project}` };
}
