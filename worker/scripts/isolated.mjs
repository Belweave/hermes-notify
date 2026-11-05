import { mkdtemp, mkdir, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';

// Give every child a new, empty home and an allowlisted environment. In particular,
// do not inherit Cloudflare tokens, npm configuration, or another project's home.
const root = fileURLToPath(new URL('../', import.meta.url));
const isolated = await mkdtemp(join(tmpdir(), 'hermes-pocket-'));
await mkdir(join(isolated, 'config'));
const env = {
  PATH: process.env.PATH,
  HOME: isolated,
  XDG_CONFIG_HOME: join(isolated, 'config'),
  XDG_CACHE_HOME: join(isolated, 'cache'),
  TMPDIR: isolated,
  HERMES_HOME: join(isolated, 'hermes'),
  WRANGLER_HOME: join(isolated, 'wrangler'),
  WRANGLER_SEND_METRICS: 'false',
  WRANGLER_LOG: 'error',
  CI: 'true',
  GOMAXPROCS: '2',
  NODE_OPTIONS: '--max-old-space-size=512',
  npm_config_cache: join(isolated, 'npm-cache'),
  npm_config_userconfig: join(isolated, 'npmrc'),
  npm_config_globalconfig: join(isolated, 'global-npmrc'),
  npm_config_audit: 'false',
  npm_config_fund: 'false',
  npm_config_update_notifier: 'false',
};
const commands = {
  install: ['npm', ['install', '--ignore-scripts', '--no-audit', '--no-fund']],
  ci: ['npm', ['ci', '--ignore-scripts', '--no-audit', '--no-fund']],
  build: [process.execPath, ['scripts/build.mjs']],
  test: [process.execPath, ['--test', '--test-concurrency=1', 'test/worker.test.mjs', 'test/browser.test.mjs']],
  check: [process.execPath, ['scripts/check.mjs']],
};
const command = commands[process.argv[2]];
if (!command) throw new Error('Choose install, ci, build, test, or check.');
try {
  const child = spawn(command[0], command[1], { cwd: root, env, stdio: 'inherit' });
  process.exitCode = await new Promise((resolve, reject) => {
    child.on('error', reject);
    child.on('exit', (code) => resolve(code ?? 1));
  });
} finally {
  await rm(isolated, { recursive: true, force: true });
}
