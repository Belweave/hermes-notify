import assert from 'node:assert/strict';
import { before, after, test } from 'node:test';
import { resolve } from 'node:path';
import { build } from 'esbuild';

let connect;
const originalFetch = globalThis.fetch;
const originalWindow = globalThis.window;
before(async () => {
  const result = await build({ entryPoints: ['../app/public/auth.js'], bundle: true, format: 'esm', write: false,
    plugins: [{ name: 'official-browser-sdk', setup(builder) {
      builder.onResolve({ filter: /^\/vendor\/notify\/browser\.mjs$/ }, () => ({ path: resolve('vendor/browser.mjs') }));
    } }], logLevel: 'silent' });
  ({ connect } = await import(`data:text/javascript;base64,${Buffer.from(result.outputFiles[0].text).toString('base64')}`));
});
after(() => { globalThis.fetch = originalFetch; globalThis.window = originalWindow; });

test('ordinary browser and invalid links show safe fallback without fake authentication', async () => {
  globalThis.window = { location: { href: 'https://pocket.example.test/projects/demo', origin: 'https://pocket.example.test' } };
  globalThis.fetch = () => { throw new Error('Unexpected network request'); };
  await assert.rejects(connect('demo'), /updated Notify app on your phone/);
  await assert.rejects(connect('../admin'), /project link is invalid/);
});

test('connect uses official challenge exchange, no profile fields, then checks the session', async () => {
  const requests = [];
  globalThis.window = { location: { href: 'https://pocket.example.test/projects/demo', origin: 'https://pocket.example.test' },
    notify: { microAuth: async (options) => {
      assert.deepEqual(options, { challenge: 'a'.repeat(43), fields: [] });
      return 'synthetic.signed.pass';
    } } };
  globalThis.fetch = async (url, init) => {
    const path = new URL(url, window.location.href).pathname;
    requests.push([path, init]);
    if (path.endsWith('/config')) return Response.json({ project: 'demo', appId: 'app_synthetic' });
    if (path.endsWith('/challenge')) return Response.json({ challenge: 'a'.repeat(43) });
    return Response.json({ ok: true, authenticated: true, project: 'demo' });
  };
  assert.deepEqual(await connect('demo'), { authenticated: true, project: 'demo' });
  assert.deepEqual(requests.map(([path, init]) => [path, init.method ?? 'GET']), [
    ['/api/projects/demo/config', 'GET'], ['/auth/demo/challenge', 'POST'],
    ['/auth/demo/session', 'POST'], ['/auth/demo/session', 'GET'],
  ]);
  for (const [, init] of requests) assert.equal(init.credentials, 'same-origin');
  assert.equal(requests[2][1].body, JSON.stringify({ token: 'synthetic.signed.pass' }));
});

test('connect does not expose native errors or report success for a rejected session', async () => {
  globalThis.window.notify.microAuth = async () => { throw new Error('sensitive native error detail'); };
  await assert.rejects(connect('demo'), (error) => error.message.includes('Sign-in was not completed') && !error.message.includes('sensitive'));
  globalThis.window.notify.microAuth = async () => 'synthetic.signed.pass';
  globalThis.fetch = async (url) => {
    const path = new URL(url, window.location.href).pathname;
    if (path.endsWith('/config')) return Response.json({ appId: 'app_synthetic' });
    if (path.endsWith('/challenge')) return Response.json({ challenge: 'b'.repeat(43) });
    return Response.json({ error: 'not_owner' }, { status: 403 });
  };
  await assert.rejects(connect('demo'), /Sign-in was not completed/);
});
