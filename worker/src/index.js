import { createRemoteJWKSet } from '../vendor/chunk-JKIZH22G.mjs';
import { PocketService } from './service.js';
import { fail, json, originFor, safe } from './http.js';
import { SLUG } from './validate.js';

// This is a fixed official public key endpoint, never an operator or user URL.
const notifyKeys = createRemoteJWKSet(new URL('https://notify.belweave.ai/.well-known/jwks.json'));

export class PocketStore {
  constructor(ctx, env) { this.service = new PocketService(ctx, env, notifyKeys); }
  fetch(request) { return this.service.fetch(request); }
  alarm() { return this.service.alarm(); }
}

export async function route(request, env) {
  const url = new URL(request.url);
  if (url.pathname === '/api/health' && request.method === 'GET') return json({ service: 'hermes-pocket', schemaVersion: 1 });
  originFor(request, env);
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/auth/')) {
    return env.POCKET.get(env.POCKET.idFromName('hermes-pocket-v1')).fetch(request);
  }
  if (!['GET', 'HEAD'].includes(request.method)) fail(405, 'method_not_allowed');
  const project = url.pathname.match(/^\/projects\/([^/]+)\/?$/)?.[1];
  if (project) {
    if (!SLUG.test(project)) fail(404, 'not_found');
    url.pathname = '/index.html';
  }
  // Restrict assets to public outputs; unknown API paths can never fall through
  // to an SPA document. The build copies no server source or credentials.
  const response = await env.ASSETS.fetch(new Request(url, { method: request.method }));
  const secured = new Response(response.body, response);
  secured.headers.set('cache-control', 'no-store');
  secured.headers.set('x-content-type-options', 'nosniff');
  secured.headers.set('referrer-policy', 'no-referrer');
  secured.headers.set('content-security-policy', "default-src 'self'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'");
  return secured;
}

export default { fetch: (request, env) => safe(() => route(request, env)) };
