import { build } from 'esbuild';
import { cp, mkdir, readdir, readFile, rm } from 'node:fs/promises';
import { join } from 'node:path';

await rm('dist', { recursive: true, force: true });
await mkdir('dist/public/vendor/notify', { recursive: true });
// Copy only the App-owned public directory. Dotfiles, test fixtures, server
// implementation, and configuration have no route into public assets.
async function copyPublic(from, to) {
  await mkdir(to, { recursive: true });
  for (const item of await readdir(from, { withFileTypes: true })) {
    if (item.name.startsWith('.') || item.isSymbolicLink()) throw new Error('Unexpected hidden file or symlink in public assets');
    if (item.isDirectory()) await copyPublic(join(from, item.name), join(to, item.name));
    else if (item.isFile()) await cp(join(from, item.name), join(to, item.name));
  }
}
await copyPublic('../app/public', 'dist/public');
// The official browser entry is standalone. Keep the entire SDK with licenses
// in source, but expose only its browser entry and licensing material publicly.
for (const name of ['browser.mjs', 'LICENSE', 'THIRD-PARTY-NOTICES.txt']) {
  await cp(`vendor/${name}`, `dist/public/vendor/notify/${name}`);
}
await cp('vendor/licenses', 'dist/public/vendor/notify/licenses', { recursive: true });
const html = await readFile('dist/public/index.html', 'utf8');
if (!html.includes('type="module"') && !html.includes("type='module'")) throw new Error('App shell must load a module');
await build({ entryPoints: ['src/index.js'], outfile: 'dist/worker.mjs', bundle: true,
  format: 'esm', platform: 'neutral', target: 'es2022', external: ['node:*', 'cloudflare:*'],
  legalComments: 'eof', sourcemap: false, logLevel: 'info' });
console.log('Built Worker and public App assets locally. No Wrangler command was run.');
