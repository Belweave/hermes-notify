// Loopback-only test host for the built production Worker. Private API/session
// fixtures are Playwright route interceptions, never production routes or data.
import { createServer } from 'node:http';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';
import { spawnSync } from 'node:child_process';

const root = fileURLToPath(new URL('../../', import.meta.url));
const require = createRequire(new URL('../../worker/package.json', import.meta.url));
const { Miniflare } = require('miniflare');
const build = spawnSync(process.execPath, [resolve(root, 'worker/scripts/isolated.mjs'), 'build'], { stdio: 'inherit' });
if (build.status !== 0) throw new Error('Production Worker build failed');
const storage = await mkdtemp(join(tmpdir(), 'pocket-browser-'));
const port = Number(process.env.APP_TEST_PORT || 4179);
const origin = 'https://hermes-pocket.example.workers.dev';
const mf = new Miniflare({
  cf: false, scriptPath: resolve(root, 'worker/dist/worker.mjs'), modulesRoot: resolve(root, 'worker/dist'), modules: true,
  compatibilityDate: '2026-07-30', compatibilityFlags: ['nodejs_compat'],
  durableObjects: { POCKET: { className: 'PocketStore', useSQLite: true } }, durableObjectsPersist: join(storage, 'sqlite'),
  outboundService: () => { throw new Error('Outbound network is forbidden in browser tests'); },
  assets: { directory: resolve(root, 'worker/dist/public'), binding: 'ASSETS',
    routerConfig: { has_user_worker: true, invoke_user_worker_ahead_of_assets: true },
    assetConfig: { html_handling: 'none', not_found_handling: 'none' } },
});
await mf.ready;
const server = createServer(async (request, response) => {
  try {
    // This adapter-only path exercises the production configuration-error page.
    // It is absent from app/public and the production Worker bundle.
    const url = request.url === '/__design/service-error'
      ? 'https://unconfigured.example.test/' : new URL(request.url, origin).href;
    const result = await mf.dispatchFetch(url, { method: request.method, headers: { accept: request.headers.accept || '*/*' } });
    response.writeHead(result.status, Object.fromEntries(result.headers));
    response.end(Buffer.from(await result.arrayBuffer()));
  } catch {
    response.writeHead(500, { 'content-type': 'text/plain' }).end('Browser test host failed');
  }
});
server.listen(port, '127.0.0.1', () => process.stdout.write(`Production Worker test host: http://127.0.0.1:${port}\n`));
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, async () => {
  server.closeAllConnections();
  await new Promise(resolve => server.close(resolve));
  await mf.dispose();
  await rm(storage, { recursive: true, force: true });
  process.exit(0);
});
