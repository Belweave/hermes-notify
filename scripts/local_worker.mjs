// Synthetic integration adapter. Never bundled with the production Worker.
import { createRequire } from 'node:module';
import { createServer } from 'node:http';
import { createInterface } from 'node:readline';
import { webcrypto, randomUUID } from 'node:crypto';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';

const root = fileURLToPath(new URL('../', import.meta.url));
const require = createRequire(new URL('../worker/package.json', import.meta.url));
const { build } = require('esbuild');
const { Miniflare } = require('miniflare');
const directory = process.argv[2];
if (!directory) throw new Error('An isolated scratch directory is required.');
const origin = 'https://pocket.example.com';
const publisher = 'synthetic-publisher-token-for-local-rehearsal-only';
const owner = 'hk_synthetic_owner';
const headers = { authorization: `Bearer ${publisher}`, 'content-type': 'application/json' };
const pair = await webcrypto.subtle.generateKey({ name: 'ECDSA', namedCurve: 'P-256' }, true, ['sign', 'verify']);
const jwk = { ...await webcrypto.subtle.exportKey('jwk', pair.publicKey), kid: 'rehearsal', alg: 'ES256', use: 'sig' };
await build({ entryPoints: [resolve(root, 'worker/test/entry.js')], outfile: join(directory, 'test-worker.mjs'),
  bundle: true, format: 'esm', platform: 'neutral', external: ['node:*', 'cloudflare:*'], logLevel: 'silent' });
const mf = new Miniflare({
  cf: false,
  scriptPath: join(directory, 'test-worker.mjs'), modulesRoot: directory, modules: true,
  compatibilityDate: '2026-07-30', compatibilityFlags: ['nodejs_compat'],
  durableObjects: { POCKET: { className: 'TestPocketStore', useSQLite: true } },
  durableObjectsPersist: join(directory, 'sqlite'),
  bindings: { APP_ORIGIN: origin, PUBLISH_TOKEN: publisher, OWNER_SUBJECT: owner,
    SYNTHETIC_JWKS: JSON.stringify({ keys: [jwk] }) },
  outboundService: () => { throw new Error('Outbound network is forbidden in this rehearsal.'); },
  assets: { directory: resolve(root, 'worker/dist/public'), binding: 'ASSETS',
    routerConfig: { has_user_worker: true, invoke_user_worker_ahead_of_assets: true },
    assetConfig: { html_handling: 'none', not_found_handling: 'none' } },
});
await mf.ready;
const fetch = (path, init) => mf.dispatchFetch(origin + path, init);
async function expect(response, code = 200) {
  assert.equal(response.status, code, await response.clone().text());
  return response;
}
const cookie = (response, name) => response.headers.getSetCookie().find(value => value.startsWith(name + '='))?.split(';')[0];

async function phoneReply(project) {
  const w = (await (await expect(await fetch(`/api/projects/${project}`, { headers }))).json()).workspace;
  await expect(await fetch(`/api/projects/${project}`), 401);
  const browserHeaders = { origin, 'content-type': 'application/json' };
  const challengeResponse = await expect(await fetch(`/auth/${project}/challenge`, { method: 'POST', headers: browserHeaders, body: '{}' }));
  const { challenge } = await challengeResponse.json();
  const now = Math.floor(Date.now() / 1000);
  const claims = { iss: 'https://notify.belweave.ai', aud: origin, sub: owner, app_id: w.appId,
    nonce: challenge, iat: now, exp: now + 120, jti: randomUUID() };
  const input = [{ alg: 'ES256', typ: 'notify-pass+jwt', kid: 'rehearsal' }, claims]
    .map(value => Buffer.from(JSON.stringify(value)).toString('base64url')).join('.');
  const signature = await webcrypto.subtle.sign({ name: 'ECDSA', hash: 'SHA-256' }, pair.privateKey, Buffer.from(input));
  const token = input + '.' + Buffer.from(signature).toString('base64url');
  const sessionResponse = await expect(await fetch(`/auth/${project}/session`, { method: 'POST',
    headers: { ...browserHeaders, cookie: cookie(challengeResponse, `__Host-hp-binding-${project}`) }, body: JSON.stringify({ token }) }));
  const browserSession = { ...browserHeaders, cookie: cookie(sessionResponse, `__Host-hp-session-${project}`) };
  const privateRead = await expect(await fetch(`/api/projects/${project}`, { headers: browserSession }));
  assert.equal((await privateRead.json()).workspace.runId, w.runId);
  const reply = { id: randomUUID(), runId: w.runId, text: 'Keep the rollback notes with this release.' };
  const receipt = await (await expect(await fetch(`/api/projects/${project}/replies`, {
    method: 'POST', headers: browserSession, body: JSON.stringify(reply),
  }))).json();
  const duplicate = await (await expect(await fetch(`/api/projects/${project}/replies`, {
    method: 'POST', headers: browserSession, body: JSON.stringify(reply),
  }))).json();
  assert.equal(duplicate.cursor, receipt.cursor);
  return { authenticated: true, duplicateDeduplicated: true, receipt };
}

// Python's test client accepts only Bearer dummy over loopback. This adapter maps
// it to the synthetic Worker token; production authentication stays unchanged.
const server = createServer(async (request, response) => {
  try {
    if (request.headers.authorization !== 'Bearer dummy' && request.url !== '/api/health') {
      response.writeHead(401); response.end(); return;
    }
    if (!request.url.startsWith('/api/') || request.url.startsWith('//')) {
      response.writeHead(404); response.end(); return;
    }
    const chunks = []; let length = 0;
    for await (const chunk of request) {
      length += chunk.length;
      if (length > 65536) throw new Error('Oversized test request');
      chunks.push(chunk);
    }
    const body = Buffer.concat(chunks);
    const result = await fetch(request.url, { method: request.method, headers,
      ...(body.length ? { body } : {}) });
    response.writeHead(result.status, { 'content-type': 'application/json' });
    response.end(Buffer.from(await result.arrayBuffer()));
  } catch {
    response.writeHead(500, { 'content-type': 'application/json' });
    response.end(JSON.stringify({ error: 'Local Worker adapter failed' }));
  }
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
process.stdout.write(JSON.stringify({ url: `http://127.0.0.1:${server.address().port}` }) + '\n');

try {
  for await (const line of createInterface({ input: process.stdin })) {
    try {
      const command = JSON.parse(line);
      if (command.action === 'close') break;
      assert.match(command.project, /^[a-z0-9][a-z0-9-]{0,63}$/);
      let result;
      if (command.action === 'reply') result = await phoneReply(command.project);
      else if (command.action === 'workspace') result = await (await expect(await fetch(`/api/projects/${command.project}`, { headers }))).json();
      else throw new Error('Unknown rehearsal command');
      process.stdout.write(JSON.stringify({ ok: true, result }) + '\n');
    } catch {
      process.stdout.write(JSON.stringify({ ok: false, error: 'Local integration assertion failed' }) + '\n');
    }
  }
} finally {
  await new Promise(resolve => server.close(resolve));
  await mf.dispose();
}
