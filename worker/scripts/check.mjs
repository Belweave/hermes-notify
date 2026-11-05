import { spawnSync } from 'node:child_process';
import { readFile, readdir } from 'node:fs/promises';
import { join } from 'node:path';
import { createHash } from 'node:crypto';

async function check(dir) {
  for (const item of await readdir(dir, { withFileTypes: true })) {
    const path = join(dir, item.name);
    if (item.isDirectory()) await check(path);
    else if (/\.[cm]?js$/.test(item.name)) {
      if ((await readFile(path, 'utf8')).includes('\u2014')) throw new Error(`Unexpected punctuation: ${path}`);
      const result = spawnSync(process.execPath, ['--check', path], { stdio: 'inherit' });
      if (result.status) process.exit(result.status);
    }
  }
}
for (const path of ['src', 'scripts', 'test']) await check(path);
const result = spawnSync(process.execPath, ['--check', '../app/public/auth.js'], { stdio: 'inherit' });
if (result.status) process.exit(result.status);
const provenance = JSON.parse(await readFile('sdk-provenance.json', 'utf8'));
for (const [path, expected] of Object.entries(provenance.files)) {
  const actual = createHash('sha256').update(await readFile(join('vendor', path))).digest('hex');
  if (actual !== expected) throw new Error(`Vendored SDK differs from official release: ${path}`);
}
console.log('Auth adapter and Worker syntax passed; official SDK file hashes match.');
