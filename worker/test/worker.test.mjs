import assert from 'node:assert/strict';
import { before, after, test } from 'node:test';
import { build } from 'esbuild';
import { Miniflare, Response as MFResponse } from 'miniflare';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { createHmac, webcrypto } from 'node:crypto';
import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { LIMITS, RETENTION } from '../src/store.js';

const ORIGIN = 'https://pocket.example.test';
const PUBLISH_TOKEN = 'synthetic-publisher-token-for-tests-only-0001';
const WEBHOOK_SECRET = 'synthetic-webhook-secret-for-tests-only-0001';
const OWNER = 'hk_synthetic_owner';
let mf, dir, privateKey, jwk, options;
let number = 0;
const unique = () => `test-${++number}`;
const headers = { authorization: `Bearer ${PUBLISH_TOKEN}`, 'content-type': 'application/json' };
const browserHeaders = (cookie = '') => ({ origin: ORIGIN, 'content-type': 'application/json', cookie });

function workspace(project, revision = 1, extra = {}) {
  return { schemaVersion: 1, project, runId: 'run_synthetic', revision, name: 'Synthetic release',
    version: '1.0.0', status: 'running', stage: 'Checks', summary: 'Only synthetic test content.',
    progress: 0.5, checks: [{ label: 'Tests', status: 'passed' }],
    artifacts: [{ label: 'Notes', url: 'https://example.com/release' }], notes: 'Synthetic notes',
    updatedAt: new Date().toISOString(), appId: 'app_synthetic', approval: null, ...extra };
}
const fetch = (path, init) => mf.dispatchFetch(ORIGIN + path, init);
async function status(response, expected) {
  assert.equal(response.status, expected, await response.clone().text());
  assert.match(response.headers.get('cache-control') ?? '', /no-store/);
  return response;
}
async function publish(w, operationId = unique(), raw) {
  return fetch(`/api/projects/${w.project}`, { method: 'PUT', headers,
    body: raw ?? JSON.stringify({ operationId, expectedRevision: w.revision - 1, workspace: w }) });
}
async function create(extra = {}) {
  const w = workspace(unique(), 1, extra);
  await status(await publish(w), 200);
  return w;
}
async function control(sql, args = [], env) {
  const response = await fetch('/__test/control', { method: 'POST', body: JSON.stringify({ sql, args, env }) });
  assert.equal(response.status, 200);
  return response.json();
}
function cookieFrom(response, name) {
  const values = response.headers.getSetCookie();
  return values.find((value) => value.startsWith(`${name}=`))?.split(';')[0];
}
async function challenge(w) {
  const response = await status(await fetch(`/auth/${w.project}/challenge`, { method: 'POST', headers: browserHeaders(), body: '{}' }), 200);
  const binding = cookieFrom(response, `__Host-hp-binding-${w.project}`);
  assert.ok(binding);
  assert.match(response.headers.get('set-cookie'), /HttpOnly; Secure; SameSite=Strict/);
  return { binding, ...(await response.json()) };
}
async function sign(w, nonce, claims = {}, header = {}) {
  const now = Math.floor(Date.now() / 1000);
  const protectedHeader = { alg: 'ES256', typ: 'notify-pass+jwt', kid: 'synthetic-key', ...header };
  const body = { iss: 'https://notify.belweave.ai', aud: ORIGIN, sub: OWNER, app_id: w.appId,
    nonce, iat: now, exp: now + 120, jti: unique(), ...claims };
  const input = [protectedHeader, body].map((value) => Buffer.from(JSON.stringify(value)).toString('base64url')).join('.');
  const signature = await webcrypto.subtle.sign({ name: 'ECDSA', hash: 'SHA-256' }, privateKey, Buffer.from(input));
  return input + '.' + Buffer.from(signature).toString('base64url');
}
async function exchange(w, c, token, override = {}) {
  return fetch(`/auth/${w.project}/session`, { method: 'POST', headers: { ...browserHeaders(c.binding), ...override }, body: JSON.stringify({ token }) });
}
async function login(w) {
  const c = await challenge(w);
  const response = await status(await exchange(w, c, await sign(w, c.challenge)), 200);
  return cookieFrom(response, `__Host-hp-session-${w.project}`);
}
function envelope(id = unique(), overrides = {}) {
  return { type: 'interaction.answered', interaction: { id: `int_${id}`, title: 'Synthetic question', kind: 'approval', status: 'approved', response: 'approve', respondingDeviceId: 'dev_synthetic', respondedAt: '2026-01-01T00:00:00Z' }, sentAt: '2026-01-01T00:00:01Z', ...overrides };
}
async function deliver(body, delivery = unique(), timestamp = Math.floor(Date.now() / 1000), options = {}) {
  const raw = typeof body === 'string' ? body : JSON.stringify(body);
  const mac = createHmac('sha256', WEBHOOK_SECRET).update(`${timestamp}.`).update(raw).digest('hex');
  return fetch('/api/notify/webhooks', { method: 'POST', body: raw,
    headers: { 'content-type': 'application/json', 'x-notify-delivery-id': delivery,
      'x-notify-signature': `t=${timestamp},v1=${mac}`, ...options } });
}

before(async () => {
  dir = await mkdtemp(join(tmpdir(), 'pocket-runtime-'));
  const pair = await webcrypto.subtle.generateKey({ name: 'ECDSA', namedCurve: 'P-256' }, true, ['sign', 'verify']);
  privateKey = pair.privateKey;
  jwk = { ...(await webcrypto.subtle.exportKey('jwk', pair.publicKey)), kid: 'synthetic-key', alg: 'ES256', use: 'sig' };
  await build({ entryPoints: ['test/entry.js'], outfile: join(dir, 'test-worker.mjs'), bundle: true,
    format: 'esm', platform: 'neutral', external: ['node:*', 'cloudflare:*'], logLevel: 'silent' });
  options = {
    scriptPath: join(dir, 'test-worker.mjs'), modulesRoot: dir, modules: true, compatibilityDate: '2026-07-30',
    compatibilityFlags: ['nodejs_compat'], durableObjects: { POCKET: { className: 'TestPocketStore', useSQLite: true } },
    durableObjectsPersist: join(dir, 'sqlite'),
    bindings: { APP_ORIGIN: ORIGIN, PUBLISH_TOKEN, NOTIFY_WEBHOOK_SECRET: WEBHOOK_SECRET,
      OWNER_SUBJECT: OWNER, SYNTHETIC_JWKS: JSON.stringify({ keys: [jwk] }) },
    outboundService: () => { throw new Error('Network access forbidden in synthetic tests'); },
    serviceBindings: { ASSETS: async (request) => {
      const path = new URL(request.url).pathname;
      if (path === '/index.html') return new MFResponse('<!doctype html><title>Synthetic shell</title>', { headers: { 'content-type': 'text/html' } });
      return new MFResponse('Not found', { status: 404 });
    } },
  };
  mf = new Miniflare(options);
  await mf.ready;
});
after(async () => { await mf?.dispose(); await rm(dir, { recursive: true, force: true }); });

test('health is public; shell has no project data; private routes fail closed', async () => {
  const w = await create();
  assert.deepEqual(await (await status(await fetch('/api/health'), 200)).json(), { service: 'hermes-pocket', schemaVersion: 1 });
  await status(await fetch(`/api/projects/${w.project}`), 401);
  await status(await fetch(`/api/projects/${w.project}/replies`), 401);
  await status(await fetch('/api/events'), 401);
  const config = await (await fetch(`/api/projects/${w.project}/config`)).json();
  assert.deepEqual(config, { project: w.project, appId: w.appId });
  const shell = await status(await fetch(`/projects/${w.project}`), 200);
  assert.ok(!(await shell.text()).includes(w.summary));
  assert.match(shell.headers.get('content-security-policy'), /default-src 'self'/);
  await status(await fetch('/api/no-such-route'), 404);
  await status(await fetch(`/api/projects/${w.project}`, { headers: { authorization: 'Bearer wrong' } }), 401);
  await status(await fetch(`/api/projects/${w.project}`, { headers: { authorization: `Bearer ${PUBLISH_TOKEN} trailing` } }), 401);
});

test('publication is monotonic, byte-idempotent, and atomically conflict-safe', async () => {
  const w = workspace(unique());
  const operation = unique();
  const raw = JSON.stringify({ operationId: operation, expectedRevision: 0, workspace: w });
  const first = await (await status(await publish(w, operation, raw), 200)).text();
  const next = { ...w, revision: 2, summary: 'Next synthetic revision' };
  await status(await publish(next), 200);
  assert.equal(await (await status(await publish(w, operation, raw), 200)).text(), first);
  await status(await publish(w, operation, raw + ' '), 409);
  await status(await publish(w), 409);
  const results = await Promise.all([publish({ ...w, revision: 3 }), publish({ ...w, revision: 3, summary: 'Racing revision' })]);
  assert.deepEqual(results.map((r) => r.status).sort(), [200, 409]);
  const current = await (await fetch(`/api/projects/${w.project}`, { headers })).json();
  assert.equal(current.revision, 3);
  const sameOperation = unique();
  const rawNext = JSON.stringify({ operationId: sameOperation, expectedRevision: 3, workspace: { ...w, revision: 4 } });
  const duplicates = await Promise.all([publish(w, sameOperation, rawNext), publish(w, sameOperation, rawNext)]);
  assert.deepEqual(duplicates.map((r) => r.status), [200, 200]);
  assert.equal(await duplicates[0].text(), await duplicates[1].text());
});

test('publication database failure rolls back both revision and receipt', async () => {
  const w = await create();
  await control("CREATE TRIGGER fail_operation BEFORE INSERT ON operations BEGIN SELECT RAISE(ABORT,'synthetic storage failure'); END");
  const op = unique();
  try { await status(await publish({ ...w, revision: 2 }, op), 503); }
  finally { await control('DROP TRIGGER fail_operation'); }
  const current = await (await fetch(`/api/projects/${w.project}`, { headers })).json();
  assert.equal(current.revision, 1);
  await status(await publish({ ...w, revision: 2 }, op), 200);
});

test('workspace validation and byte limits apply to declared and streamed bodies', async () => {
  const w = workspace(unique());
  const invalid = [
    { schemaVersion: 2 }, { runId: '../bad' }, { progress: 2 }, { status: 'done' },
    { artifacts: [{ label: 'Bad', url: 'http://example.com' }] },
    { artifacts: [{ label: 'Bad', url: 'https://user:password@example.com' }] },
    { artifacts: [{ label: 'Bad', url: 'https://example.com/white space' }] },
    { notes: 'Invisible\u0000control' },
    { checks: Array.from({ length: 21 }, () => ({ label: 'x', status: 'passed' })) },
    { approval: { requestId: 'r', digest: 'd', title: 't', status: 'granted' } },
    { notes: 'a'.repeat(8001) }, { summary: 'x'.repeat(501) }, { appId: '' }, { updatedAt: 'yesterday' },
    { token: 'do-not-store-arbitrary-fields' }, { name: 1 }, { project: 'other' }, { revision: 0 },
  ];
  for (const extra of invalid) await status(await fetch(`/api/projects/${w.project}`, { method: 'PUT', headers,
    body: JSON.stringify({ operationId: unique(), expectedRevision: 0, workspace: { ...w, ...extra } }) }), 400);
  const raw = JSON.stringify({ operationId: unique(), expectedRevision: 0, workspace: w });
  await status(await fetch(`/api/projects/${w.project}`, { method: 'PUT', headers, body: raw + ' '.repeat(65537) }), 413);
  const stream = new ReadableStream({ start(controller) {
    for (let i = 0; i < 5; i++) controller.enqueue(new TextEncoder().encode(' '.repeat(16384)));
    controller.close();
  } });
  await status(await fetch(`/api/projects/${w.project}`, { method: 'PUT', headers, body: stream, duplex: 'half' }), 413);
  await status(await fetch(`/api/projects/${w.project}`, { method: 'PUT', headers, body: '{bad' }), 400);
  await status(await fetch(`/api/projects/${w.project}`, { method: 'PUT', headers: { authorization: headers.authorization }, body: raw }), 415);
  await status(await publish({ ...w, name: '🎉'.repeat(80) }), 200);
});

test('official SDK exchanges an ES256 browser-bound pass with no profile claims', async () => {
  const w = await create();
  const c = await challenge(w);
  const token = await sign(w, c.challenge);
  await status(await exchange(w, { binding: '' }, token), 401);
  await status(await exchange(w, c, token, { origin: 'https://attacker.example' }), 403);
  await status(await exchange(w, c, token, { 'sec-fetch-site': 'cross-site' }), 403);
  const responses = await Promise.all([exchange(w, c, token), exchange(w, c, token)]);
  assert.deepEqual(responses.map((r) => r.status).sort(), [200, 401]);
  const response = responses.find((r) => r.status === 200);
  const session = cookieFrom(response, `__Host-hp-session-${w.project}`);
  assert.ok(session);
  assert.match(response.headers.getSetCookie().find((s) => s.startsWith(session)), /Path=\/; HttpOnly; Secure; SameSite=Strict; Max-Age=3600/);
  await status(await fetch(`/auth/${w.project}/session`, { headers: { cookie: session } }), 200);
  const read = await status(await fetch(`/api/projects/${w.project}`, { headers: { cookie: session } }), 200);
  assert.equal((await read.json()).workspace.notes, w.notes);
  await status(await fetch(`/api/projects/${w.project}`, { headers: { cookie: session, origin: 'https://attacker.example' } }), 403);
  await status(await fetch(`/api/projects/${w.project}/replies`, { headers: { cookie: session } }), 401);
  await status(await fetch('/api/events', { headers: { cookie: session } }), 401);
  const other = await create();
  await status(await fetch(`/api/projects/${other.project}`, { headers: { cookie: session } }), 401);
  await status(await fetch(`/auth/${w.project}/session`, { method: 'DELETE', headers: { cookie: session } }), 403);
  await status(await fetch(`/auth/${w.project}/session`, { method: 'DELETE', headers: browserHeaders(session) }), 200);
  await status(await fetch(`/api/projects/${w.project}`, { headers: { cookie: session } }), 401);
});

test('official verifier rejects claims, wrong owner, wrong key, tampering and expired bindings', async () => {
  const w = await create();
  const now = Math.floor(Date.now() / 1000);
  const cases = [
    [{ iss: 'https://elsewhere.example' }], [{ aud: 'https://elsewhere.example' }],
    [{ aud: [ORIGIN, 'https://elsewhere.example'] }], [{ app_id: 'app_other' }], [{ nonce: 'x'.repeat(43) }],
    [{ iat: now - 121, exp: now - 1 }], [{ iat: now + 60, exp: now + 120 }], [{ exp: now + 121 }],
    [{ jti: '' }], [{ sub: '' }], [{}, { typ: 'JWT' }], [{}, { alg: 'HS256' }], [{}, { kid: 'unknown' }],
  ];
  for (const [claims, header] of cases) {
    const c = await challenge(w);
    await status(await exchange(w, c, await sign(w, c.challenge, claims, header)), 401);
    await fetch(`/auth/${w.project}/session`, { method: 'DELETE', headers: browserHeaders(c.binding) });
  }
  const c = await challenge(w);
  await status(await exchange(w, c, await sign(w, c.challenge, { sub: 'hk_somebody_else' })), 403);
  const changed = await challenge(w);
  const token = await sign(w, changed.challenge);
  const parts = token.split('.');
  parts[2] = (parts[2][0] === 'A' ? 'B' : 'A') + parts[2].slice(1);
  await status(await exchange(w, changed, parts.join('.')), 401);
  await control('UPDATE challenges SET expires=? WHERE project=?', [Date.now() - 1, w.project]);
  await status(await exchange(w, changed, token), 401);
  assert.equal((await control('SELECT count(*) AS n FROM challenges WHERE project=?', [w.project]))[0].n, 0);
});

test('owner configuration, expiry, App changes and jti reuse cannot grant private access', async () => {
  const w = await create();
  const session = await login(w);
  await control(null, [], { OWNER_SUBJECT: '' });
  try {
    await status(await fetch(`/auth/${w.project}/challenge`, { method: 'POST', headers: browserHeaders(), body: '{}' }), 503);
    await status(await fetch(`/api/projects/${w.project}`, { headers: { cookie: session } }), 401);
  } finally { await control(null, [], { OWNER_SUBJECT: OWNER }); }
  const jti = unique();
  for (const expected of [200, 401]) {
    const c = await challenge(w);
    await status(await exchange(w, c, await sign(w, c.challenge, { jti })), expected);
  }
  const pending = await challenge(w);
  await status(await publish({ ...w, revision: 2, appId: 'app_changed' }), 200);
  await status(await exchange(w, pending, await sign(w, pending.challenge)), 401);
  await status(await fetch(`/api/projects/${w.project}`, { headers: { cookie: session } }), 401);
  const changed = { ...w, appId: 'app_changed' };
  const newSession = await login(changed);
  await control('UPDATE sessions SET expires=? WHERE project=?', [Date.now() - 1, w.project]);
  await status(await fetch(`/api/projects/${w.project}`, { headers: { cookie: newSession } }), 401);
  const unregistered = await create({ appId: null });
  await status(await fetch(`/auth/${unregistered.project}/challenge`, { method: 'POST', headers: browserHeaders(), body: '{}' }), 409);
});

test('replies require browser origin and run; retries deduplicate before and after ack', async () => {
  const w = await create();
  const session = await login(w);
  const body = { id: unique(), runId: w.runId, text: 'Include synthetic rollback notes.' };
  const send = (input = body, hs = browserHeaders(session)) => fetch(`/api/projects/${w.project}/replies`, { method: 'POST', headers: hs, body: JSON.stringify(input) });
  await status(await send(body, headers), 403);
  await status(await send(body, browserHeaders()), 401);
  await status(await send(body, { ...browserHeaders(session), origin: 'https://other.example' }), 403);
  await status(await send({ ...body, runId: 'run_old' }), 409);
  await status(await send({ ...body, text: 'x'.repeat(2001) }), 400);
  await status(await send({ ...body, text: ' ' }), 400);
  const responses = await Promise.all([send(), send()]);
  const first = await (await status(responses[0], 200)).json();
  assert.deepEqual(await responses[1].json(), first);
  await status(await send({ ...body, text: 'Changed' }), 409);
  const queue = await (await fetch(`/api/projects/${w.project}/replies?after=0`, { headers })).json();
  assert.equal(queue.replies.length, 1);
  assert.equal(queue.replies[0].runId, w.runId);
  assert.equal(queue.cursor, first.cursor);
  assert.deepEqual((await (await fetch(`/api/projects/${w.project}/replies?after=${queue.cursor}`, { headers })).json()).replies, []);
  const ack = () => fetch(`/api/projects/${w.project}/replies/ack`, { method: 'POST', headers, body: JSON.stringify({ ids: [body.id] }) });
  await status(await ack(), 200); await status(await ack(), 200);
  assert.equal((await control('SELECT text FROM replies WHERE project=? AND id=?', [w.project, body.id]))[0].text, null);
  assert.deepEqual(await (await send()).json(), first);
  await status(await publish({ ...w, revision: 2, runId: 'run_new' }), 200);
  // A retry returns its original receipt without creating input for the new run.
  assert.deepEqual(await (await send()).json(), first);
  await status(await send({ ...body, id: unique() }), 409);
  assert.deepEqual((await (await fetch(`/api/projects/${w.project}/replies`, { headers })).json()).replies, []);
});

for (const [label, text] of [['ASCII', 'x'.repeat(2000)], ['Unicode', '🧪'.repeat(2000)]]) {
test(`long ${label} reply pages pass the Python collector without loss`, async () => {
  const w = await create();
  const session = await login(w);
  const expected = [];
  for (let i = 0; i < 70; i++) {
    const body = { id: unique(), runId: w.runId, text };
    expected.push(body.id);
    await status(await fetch(`/api/projects/${w.project}/replies`, { method: 'POST',
      headers: browserHeaders(session), body: JSON.stringify(body) }), 200);
  }
  // A loopback adapter maps the Python test credential to this synthetic Worker.
  // Exact Worker response bytes reach JsonClient's real 128 KiB read boundary.
  const pages = [];
  const server = createServer(async (request, response) => {
    try {
      assert.equal(request.headers.authorization, 'Bearer dummy');
      const chunks = [];
      for await (const chunk of request) chunks.push(chunk);
      const body = Buffer.concat(chunks);
      const result = await fetch(request.url, { method: request.method, headers,
        ...(body.length ? { body } : {}) });
      const raw = Buffer.from(await result.arrayBuffer());
      if (request.method === 'GET' && request.url.includes('/replies?')) {
        pages.push({ bytes: raw.length, ...JSON.parse(raw) });
      }
      response.writeHead(result.status, { 'content-type': 'application/json' });
      response.end(raw);
    } catch {
      response.writeHead(500); response.end();
    }
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  try {
    const child = spawn(resolve('../.venv/bin/python'), ['test/collect_replies.py',
      `http://127.0.0.1:${server.address().port}`], { stdio: ['pipe', 'pipe', 'pipe'],
      env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1' } });
    let stdout = '', stderr = '';
    child.stdout.on('data', chunk => { stdout += chunk; });
    child.stderr.on('data', chunk => { stderr += chunk; });
    const timeout = setTimeout(() => child.kill(), 20_000);
    try {
      const exited = new Promise((resolve, reject) => {
        child.on('error', reject); child.on('close', resolve);
      });
      child.stdin.end(JSON.stringify({ workspace: w, ids: expected, text }));
      assert.equal(await exited, 0, stderr);
    } finally {
      clearTimeout(timeout);
    }
    assert.deepEqual(JSON.parse(stdout), { received: 70, attributed: true, acknowledged: true });
  } finally {
    await new Promise(resolve => server.close(resolve));
  }
  let cursor = 0;
  const received = [];
  for (const page of pages) {
    assert.ok(page.bytes <= LIMITS.replyPageBytes && page.bytes < 128 * 1024);
    if (!page.replies.length) continue;
    assert.equal(page.cursor, page.replies.at(-1).cursor);
    assert.ok(page.cursor > cursor);
    cursor = page.cursor;
    received.push(...page.replies.map(row => row.id));
  }
  assert.deepEqual(received, expected);
  assert.equal((await (await fetch(`/api/projects/${w.project}/replies?after=0`, { headers })).json()).replies.length, 0);
});
}

test('reply pages and capacities are bounded without losing pending rows', async () => {
  const w = await create();
  const session = await login(w);
  await control(`WITH RECURSIVE n(i) AS (VALUES(1) UNION ALL SELECT i+1 FROM n WHERE i<?)
    INSERT INTO replies(project,id,run_id,text,hash,created) SELECT ?, 'bulk_'||i, ?, 'Synthetic', 'fixture', '2026-01-01T00:00:00Z' FROM n`,
  [LIMITS.projectReplies, w.project, w.runId]);
  const first = await (await fetch(`/api/projects/${w.project}/replies`, { headers })).json();
  assert.equal(first.replies.length, LIMITS.page);
  const second = await (await fetch(`/api/projects/${w.project}/replies?after=${first.cursor}`, { headers })).json();
  assert.equal(second.replies.length, LIMITS.projectReplies - LIMITS.page);
  await status(await fetch(`/api/projects/${w.project}/replies`, { method: 'POST', headers: browserHeaders(session), body: JSON.stringify({ id: unique(), runId: w.runId, text: 'Full' }) }), 503);
  assert.equal((await control('SELECT count(*) AS n FROM replies WHERE project=? AND acked IS NULL', [w.project]))[0].n, LIMITS.projectReplies);
  for (const after of ['-1', 'NaN', '9007199254740992', '1.5']) await status(await fetch(`/api/projects/${w.project}/replies?after=${after}`, { headers }), 400);
  await control('DELETE FROM replies WHERE project=?', [w.project]);
});

test('saved webhooks verify exact raw bytes, timestamps and selected envelope', async () => {
  const body = envelope();
  const timestamp = Math.floor(Date.now() / 1000);
  await status(await deliver(body, unique(), timestamp - 301), 401);
  await status(await deliver(body, unique(), timestamp + 10), 401);
  await status(await deliver(body, unique(), timestamp, { 'x-notify-signature': `t=${timestamp},v1=${'a'.repeat(64)}` }), 401);
  await status(await deliver(body, unique(), timestamp, { 'x-notify-signature': `t=${timestamp},t=${timestamp},v1=${'a'.repeat(64)}` }), 401);
  await status(await deliver(body, '', timestamp), 400);
  await status(await deliver({ type: 'notification.response', interactionId: 'int_bad' }), 400);
  await status(await deliver({ text: 'Slack format' }), 400);
  await status(await deliver(JSON.stringify(body) + ' '.repeat(65536)), 413);
  const raw = JSON.stringify(body);
  const mac = createHmac('sha256', WEBHOOK_SECRET).update(`${timestamp}.${raw}`).digest('hex');
  await status(await deliver(raw + ' ', unique(), timestamp, { 'x-notify-signature': `t=${timestamp},v1=${mac}` }), 401);
  await status(await deliver('{bad'), 400);
  await status(await deliver(body), 200);
  for (const type of ['interaction.expired', 'interaction.canceled']) {
    const event = envelope(unique(), { type });
    event.interaction.status = type.split('.')[1];
    event.interaction.response = null;
    event.interaction.respondedAt = null;
    await status(await deliver(event), 200);
  }
});

test('webhook delivery and outcome dedup survive ack; failures do not acknowledge', async () => {
  const body = envelope();
  const delivery = unique();
  const pair = await Promise.all([deliver(body, delivery), deliver(body, delivery)]);
  assert.deepEqual(pair.map((r) => r.status), [200, 200]);
  const first = await pair[0].json();
  const second = await pair[1].json();
  assert.equal(first.id, second.id); assert.equal(first.cursor, second.cursor);
  assert.equal(Number(first.duplicate) + Number(second.duplicate), 1);
  const otherDelivery = await (await status(await deliver(body), 200)).json();
  assert.equal(otherDelivery.id, first.id); assert.equal(otherDelivery.duplicate, true);
  await status(await deliver({ ...body, sentAt: 'changed' }, delivery), 409);
  const altered = { ...body, interaction: { ...body.interaction, response: 'deny', status: 'denied' } };
  await status(await deliver(altered), 409);
  await status(await fetch('/api/events/ack', { method: 'POST', headers, body: JSON.stringify({ ids: [first.id] }) }), 200);
  assert.equal((await (await deliver(body)).json()).duplicate, true);
  const events = await (await fetch('/api/events', { headers })).json();
  assert.ok(events.events.every((e) => Object.keys(e).sort().join(',') === 'cursor,id,interactionId,type'));
  assert.ok(!events.events.find((e) => e.id === first.id));
  const broken = envelope();
  const brokenDelivery = unique();
  await control("CREATE TRIGGER fail_delivery BEFORE INSERT ON deliveries BEGIN SELECT RAISE(ABORT,'synthetic failure'); END");
  try { await status(await deliver(broken, brokenDelivery), 503); }
  finally { await control('DROP TRIGGER fail_delivery'); }
  assert.equal((await control('SELECT count(*) AS n FROM events WHERE interaction_id=?', [broken.interaction.id]))[0].n, 0);
  assert.equal((await control('SELECT count(*) AS n FROM deliveries WHERE id=?', [brokenDelivery]))[0].n, 0);
  await status(await deliver(broken, brokenDelivery), 200);
});

test('event queue capacity signals retryable failure and returns bounded pages', async () => {
  const old = (await control('SELECT count(*) AS n FROM events WHERE acked IS NULL'))[0].n;
  await control(`WITH RECURSIVE n(i) AS (VALUES(1) UNION ALL SELECT i+1 FROM n WHERE i<?)
    INSERT INTO events(id,interaction_id,type,hash) SELECT 'capacity_'||i, 'int_capacity_'||i, 'interaction.answered', 'fixture' FROM n`, [LIMITS.events - old]);
  const body = envelope();
  const id = unique();
  await status(await deliver(body, id), 503);
  assert.equal((await control('SELECT count(*) AS n FROM deliveries WHERE id=?', [id]))[0].n, 0);
  assert.equal((await (await fetch('/api/events', { headers })).json()).events.length, LIMITS.page);
  await control("DELETE FROM events WHERE id LIKE 'capacity_%'");
  await status(await deliver(body, id), 200);
});

test('history is bounded, expired auth and receipts purge, pending queues remain', async () => {
  const w = workspace(unique());
  const firstOperation = unique();
  const raw = JSON.stringify({ operationId: firstOperation, expectedRevision: 0, workspace: w });
  await status(await publish(w, firstOperation, raw), 200);
  for (let revision = 2; revision <= LIMITS.projectResponses + 1; revision++) await status(await publish({ ...w, revision }), 200);
  assert.equal((await control('SELECT count(*) AS n FROM operations WHERE project=? AND response IS NOT NULL', [w.project]))[0].n, LIMITS.projectResponses);
  await status(await publish(w, firstOperation, raw), 409);
  const pending = (await control('SELECT count(*) AS n FROM events WHERE acked IS NULL'))[0].n;
  await control('UPDATE operations SET created=? WHERE project=?', [Date.now() - RETENTION - 1, w.project]);
  await control('UPDATE deliveries SET expires=?', [Date.now() - 1]);
  await fetch(`/api/projects/${w.project}`, { headers });
  assert.equal((await control('SELECT count(*) AS n FROM operations WHERE project=?', [w.project]))[0].n, 0);
  assert.equal((await control('SELECT count(*) AS n FROM deliveries'))[0].n, 0);
  assert.equal((await control('SELECT count(*) AS n FROM events WHERE acked IS NULL'))[0].n, pending);
  await status(await publish(w, firstOperation, raw), 409);
});

test('SQLite publication, browser session and queues survive runtime restart', async () => {
  const w = await create();
  const session = await login(w);
  const body = envelope();
  const delivery = unique();
  const event = await (await deliver(body, delivery)).json();
  const replyBody = { id: unique(), runId: w.runId, text: 'Persist this synthetic reply.' };
  const receipt = await (await status(await fetch(`/api/projects/${w.project}/replies`, { method: 'POST', headers: browserHeaders(session), body: JSON.stringify(replyBody) }), 200)).json();
  await mf.dispose();
  mf = new Miniflare(options);
  await mf.ready;
  await status(await fetch(`/api/projects/${w.project}`, { headers: { cookie: session } }), 200);
  const duplicate = await (await status(await deliver(body, delivery), 200)).json();
  assert.equal(duplicate.id, event.id); assert.equal(duplicate.duplicate, true);
  const replies = await (await fetch(`/api/projects/${w.project}/replies`, { headers })).json();
  assert.equal(replies.replies[0].text, replyBody.text);
  assert.equal(replies.replies[0].cursor, receipt.cursor);
});

test('authentication capacity and oversized exchanges fail closed', async () => {
  const w = await create();
  for (let i = 0; i < LIMITS.projectChallenges; i++) await challenge(w);
  await status(await fetch(`/auth/${w.project}/challenge`, { method: 'POST', headers: browserHeaders(), body: '{}' }), 429);
  await control('UPDATE challenges SET expires=? WHERE project=?', [Date.now() - 1, w.project]);
  const c = await challenge(w);
  await status(await exchange(w, c, 'x'.repeat(36865)), 413);
  for (let i = 0; i < LIMITS.projectSessions; i++) await login(w);
  const next = await challenge(w);
  await status(await exchange(w, next, await sign(w, next.challenge)), 429);
  assert.equal((await control('SELECT count(*) AS n FROM sessions WHERE project=?', [w.project]))[0].n, LIMITS.projectSessions);
  await control('DELETE FROM sessions WHERE project=?', [w.project]);
  await control('DELETE FROM challenges WHERE project=?', [w.project]);
});

test('aggregate project and publication limits bound storage without changing current data', async () => {
  const w = await create();
  const projects = (await control('SELECT count(*) AS n FROM projects'))[0].n;
  await control(`WITH RECURSIVE n(i) AS (VALUES(1) UNION ALL SELECT i+1 FROM n WHERE i<?)
    INSERT INTO projects(project,revision,body) SELECT 'capacity-project-'||i, 1, '{}' FROM n`, [LIMITS.projects - projects]);
  await status(await publish(workspace(unique())), 503);
  await control("DELETE FROM projects WHERE project LIKE 'capacity-project-%'");
  const operations = (await control('SELECT count(*) AS n FROM operations'))[0].n;
  await control(`WITH RECURSIVE n(i) AS (VALUES(1) UNION ALL SELECT i+1 FROM n WHERE i<?)
    INSERT INTO operations(project,id,hash,created) SELECT 'capacity', 'capacity_'||i, 'fixture', ? FROM n`, [LIMITS.operations - operations, Date.now()]);
  await status(await publish({ ...w, revision: 2 }), 503);
  assert.equal((await (await fetch(`/api/projects/${w.project}`, { headers })).json()).revision, 1);
  await control("DELETE FROM operations WHERE project='capacity'");
  await status(await publish({ ...w, revision: 2 }), 200);
});

test('failed reply persistence and missing publisher or webhook configuration reject safely', async () => {
  const w = await create();
  const session = await login(w);
  const body = { id: unique(), runId: w.runId, text: 'Synthetic durable reply.' };
  const send = () => fetch(`/api/projects/${w.project}/replies`, { method: 'POST', headers: browserHeaders(session), body: JSON.stringify(body) });
  await control("CREATE TRIGGER fail_reply BEFORE INSERT ON replies BEGIN SELECT RAISE(ABORT,'synthetic failure'); END");
  try { await status(await send(), 503); }
  finally { await control('DROP TRIGGER fail_reply'); }
  assert.equal((await control('SELECT count(*) AS n FROM replies WHERE id=?', [body.id]))[0].n, 0);
  await status(await send(), 200);
  await control(null, [], { PUBLISH_TOKEN: '', NOTIFY_WEBHOOK_SECRET: '' });
  try {
    await status(await fetch(`/api/projects/${w.project}`, { headers }), 401);
    await status(await deliver(envelope()), 503);
  } finally { await control(null, [], { PUBLISH_TOKEN, NOTIFY_WEBHOOK_SECRET: WEBHOOK_SECRET }); }
});

test('production entry has no test route or environment verification-key bypass', async () => {
  await mf.dispose();
  await import('../scripts/build.mjs');
  const bundle = await readFile('dist/worker.mjs', 'utf8');
  assert.ok(!bundle.includes('SYNTHETIC_JWKS')); assert.ok(!bundle.includes('/__test/control'));
  const productionOptions = { ...options, scriptPath: resolve('dist/worker.mjs'), modulesRoot: resolve('dist'),
    durableObjects: { POCKET: { className: 'PocketStore', useSQLite: true } }, durableObjectsPersist: join(dir, 'production-sqlite'),
    bindings: { ...options.bindings, APP_ORIGIN: undefined },
    assets: { directory: resolve('dist/public'), binding: 'ASSETS',
      routerConfig: { has_user_worker: true, invoke_user_worker_ahead_of_assets: true },
      assetConfig: { html_handling: 'none', not_found_handling: 'none' } },
  };
  delete productionOptions.bindings.APP_ORIGIN;
  delete productionOptions.serviceBindings;
  mf = new Miniflare(productionOptions);
  await mf.ready;
  await status(await fetch('/api/health'), 200);
  await status(await fetch('/api/events', { headers }), 503);
  const request = (path, init) => mf.dispatchFetch('https://hermes-pocket.example.workers.dev' + path, init);
  const shell = await status(await request('/projects/synthetic'), 200);
  assert.match(await shell.text(), /Sign in with Notify/);
  for (const path of ['/app.js', '/auth.js', '/styles.css', '/vendor/notify/browser.mjs', '/fonts/PaperMono-Variable.woff2', '/fonts/LICENSE.txt']) {
    await status(await request(path), 200);
  }
  await status(await request('/vendor/notify/server.mjs'), 404);
  await status(await request('/src/index.js'), 404);
  await status(await request('/api/no-such-route'), 404);
  await status(await request('/api/events', { headers }), 200);
  const w = workspace(unique());
  await status(await request(`/api/projects/${w.project}`, { method: 'PUT', headers,
    body: JSON.stringify({ operationId: unique(), expectedRevision: 0, workspace: w }) }), 200);
  const cResponse = await status(await request(`/auth/${w.project}/challenge`, { method: 'POST', headers: { ...browserHeaders(), origin: 'https://hermes-pocket.example.workers.dev' }, body: '{}' }), 200);
  const c = await cResponse.json();
  const binding = cookieFrom(cResponse, `__Host-hp-binding-${w.project}`);
  const token = await sign(w, c.challenge, { aud: 'https://hermes-pocket.example.workers.dev' });
  await status(await request(`/auth/${w.project}/session`, { method: 'POST', headers: { ...browserHeaders(binding), origin: 'https://hermes-pocket.example.workers.dev' }, body: JSON.stringify({ token }) }), 401);
  const missing = await request('/__test/control', { method: 'POST', body: '{}' });
  assert.equal(missing.status, 405);
});
