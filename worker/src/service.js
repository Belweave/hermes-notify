import { createMicroAuthBinding, createMicroAuthServer } from '../vendor/server.mjs';
import { HttpError, cookie, cookieHeader, cookieNames, equalSecret, fail, hash, json,
  originFor, parseJson, privateRead, publisher, rawBody, requireJson, safe, sameOrigin } from './http.js';
import { SLUG, acknowledgement, afterCursor, fields, publication, reply, webhook } from './validate.js';
import { SESSION_TTL, Store } from './store.js';

function configuredOwner(env) { return typeof env.OWNER_SUBJECT === 'string' && /^hk_[A-Za-z0-9_-]{1,253}$/.test(env.OWNER_SUBJECT); }

// Tests supply the official verifier's key resolver here. No HTTP request,
// production binding, flag, or environment variable can select test keys.
export class PocketService {
  constructor(ctx, env, keys) {
    this.env = env;
    this.store = new Store(ctx);
    this.keys = keys;
  }
  async fetch(request) {
    return safe(async () => {
      this.store.purge(Date.now());
      const response = await this.route(request);
      await this.store.schedule();
      return response;
    });
  }
  async alarm() { this.store.purge(Date.now()); await this.store.schedule(); }
  async authorizedBrowser(request, project, origin) {
    privateRead(request, origin);
    const value = cookie(request, cookieNames(project).session);
    const tokenHash = value ? await hash(value) : '';
    const check = () => {
      if (!configuredOwner(this.env) || !tokenHash || !this.store.session(tokenHash, project, origin, this.env.OWNER_SUBJECT, Date.now())) fail(401, 'sign_in_required');
    };
    check();
    return check;
  }
  async route(request) {
    const url = new URL(request.url);
    const origin = originFor(request, this.env);
    const projectMatch = url.pathname.match(/^\/api\/projects\/([a-z0-9-]+)(?:\/(config|replies|replies\/ack))?$/);
    const authMatch = url.pathname.match(/^\/auth\/([a-z0-9-]+)\/(challenge|session)$/);
    if (authMatch && SLUG.test(authMatch[1])) return this.auth(request, authMatch[1], authMatch[2], origin);
    if (projectMatch && SLUG.test(projectMatch[1])) {
      const [, project, route = ''] = projectMatch;
      if (route === 'config' && request.method === 'GET') return json({ project, appId: this.store.requireProject(project).appId });
      if (route === '' && request.method === 'GET') {
        if (!(await publisher(request, this.env))) (await this.authorizedBrowser(request, project, origin))();
        const workspace = this.store.requireProject(project);
        return json({ workspace, revision: workspace.revision });
      }
      if (route === 'replies' && request.method === 'POST') {
        sameOrigin(request, origin);
        const authorize = await this.authorizedBrowser(request, project, origin);
        requireJson(request);
        const body = reply(parseJson(await rawBody(request, 16384)));
        return json(this.store.addReply(project, body, await hash(JSON.stringify([body.runId, body.text])), Date.now(), authorize));
      }
      if (!(await publisher(request, this.env))) fail(401, 'publisher_required');
      if (route === '' && request.method === 'PUT') {
        requireJson(request);
        const raw = await rawBody(request);
        const body = publication(parseJson(raw), project);
        return json(this.store.publish(project, body, await hash(raw), Date.now()));
      }
      if (route === 'replies' && request.method === 'GET') return json(this.store.listReplies(project, afterCursor(url)));
      if (route === 'replies/ack' && request.method === 'POST') {
        requireJson(request);
        return json(this.store.ackReplies(project, acknowledgement(parseJson(await rawBody(request, 16384))), Date.now()));
      }
      fail(405, 'method_not_allowed');
    }
    if (url.pathname === '/api/notify/webhooks' && request.method === 'POST') return this.webhook(request);
    if (url.pathname === '/api/events' || url.pathname === '/api/events/ack') {
      if (!(await publisher(request, this.env))) fail(401, 'publisher_required');
      if (url.pathname === '/api/events' && request.method === 'GET') return json(this.store.listEvents(afterCursor(url)));
      if (url.pathname === '/api/events/ack' && request.method === 'POST') {
        requireJson(request);
        return json(this.store.ackEvents(acknowledgement(parseJson(await rawBody(request, 16384))), Date.now()));
      }
      fail(405, 'method_not_allowed');
    }
    fail(404, 'not_found');
  }
  async auth(request, project, route, origin) {
    const names = cookieNames(project);
    if (route === 'session' && request.method === 'GET') {
      await this.authorizedBrowser(request, project, origin);
      return json({ ok: true, authenticated: true, project });
    }
    if (route === 'session' && request.method === 'DELETE') {
      sameOrigin(request, origin);
      const value = cookie(request, names.session);
      if (value) this.store.sql.exec('DELETE FROM sessions WHERE token=? AND project=?', await hash(value), project);
      const binding = cookie(request, names.binding);
      if (binding) this.store.sql.exec('DELETE FROM challenges WHERE binding=? AND project=?', await hash(binding), project);
      const headers = new Headers();
      headers.append('set-cookie', cookieHeader(names.session, '', 0));
      headers.append('set-cookie', cookieHeader(names.binding, '', 0));
      return json({ ok: true }, 200, headers);
    }
    if (request.method !== 'POST') fail(405, 'method_not_allowed');
    sameOrigin(request, origin);
    if (!configuredOwner(this.env)) fail(503, 'owner_unconfigured');
    const workspace = this.store.requireProject(project);
    if (!workspace.appId) fail(409, 'app_unregistered');
    requireJson(request);
    const body = parseJson(await rawBody(request, 36864));
    if (route === 'challenge') fields(body, []);
    else fields(body, ['token']);
    const binding = route === 'challenge' ? createMicroAuthBinding() : cookie(request, names.binding);
    if (!binding) fail(401, 'sign_in_failed');
    const server = createMicroAuthServer({ origin, appId: workspace.appId,
      store: this.store.challengeStore(project, workspace.appId, origin, await hash(binding)), keys: this.keys });
    if (route === 'challenge') {
      const challenge = await server.begin(binding);
      return json(challenge, 200, { 'set-cookie': cookieHeader(names.binding, binding, 120) });
    }
    let identity;
    try { identity = await server.complete(body.token, binding); }
    catch (error) { if (error instanceof HttpError) throw error; fail(401, 'sign_in_failed'); }
    if (identity.subject !== this.env.OWNER_SUBJECT) fail(403, 'not_owner');
    // Decode only after official signature and claim verification. Retain a hash
    // of jti until expiry in addition to the SDK's atomic nonce consumption.
    const claims = JSON.parse(atob(body.token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')));
    const token = createMicroAuthBinding();
    this.store.createSession(await hash(token), project, workspace.appId, origin, identity.subject,
      await hash(claims.jti), claims.exp * 1000, Date.now());
    const headers = new Headers();
    headers.append('set-cookie', cookieHeader(names.session, token, SESSION_TTL));
    headers.append('set-cookie', cookieHeader(names.binding, '', 0));
    return json({ ok: true, authenticated: true, project }, 200, headers);
  }
  async webhook(request) {
    const secret = this.env.NOTIFY_WEBHOOK_SECRET;
    if (typeof secret !== 'string' || secret.length < 32) fail(503, 'webhook_unconfigured');
    const signature = request.headers.get('x-notify-signature')?.match(/^t=(\d{1,12}),v1=([a-fA-F0-9]{64})$/);
    if (!signature) fail(401, 'invalid_signature');
    const age = Date.now() / 1000 - Number(signature[1]);
    if (age < 0 || age > 300) fail(401, 'stale_signature');
    const delivery = request.headers.get('x-notify-delivery-id');
    if (!delivery || !/^[A-Za-z0-9_-]{1,128}$/.test(delivery)) fail(400, 'invalid_delivery_id');
    requireJson(request);
    const raw = await rawBody(request);
    const prefix = new TextEncoder().encode(`${signature[1]}.`);
    const signed = new Uint8Array(prefix.length + raw.length);
    signed.set(prefix); signed.set(raw, prefix.length);
    const key = await crypto.subtle.importKey('raw', new TextEncoder().encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
    const mac = new Uint8Array(await crypto.subtle.sign('HMAC', key, signed));
    const hex = Array.from(mac, (x) => x.toString(16).padStart(2, '0')).join('');
    if (!(await equalSecret(hex, signature[2].toLowerCase()))) fail(401, 'invalid_signature');
    if (Date.now() / 1000 - Number(signature[1]) > 300) fail(401, 'stale_signature');
    const event = webhook(parseJson(raw));
    return json(this.store.addEvent(delivery, await hash(raw), event, await hash(event.outcome), Date.now()));
  }
}
