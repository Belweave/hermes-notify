// Static test host only. All authenticated responses are Playwright route
// interceptions. This server never simulates a session or serves private data.
import { createServer } from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { resolve, extname, sep } from 'node:path';

const root = fileURLToPath(new URL('../public/', import.meta.url));
const port = Number(process.env.APP_TEST_PORT || 4179);
const types = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.woff2': 'font/woff2', '.svg': 'image/svg+xml', '.txt': 'text/plain; charset=utf-8' };
const server = createServer(async (request, response) => {
  try {
    const path = decodeURIComponent(new URL(request.url, 'http://127.0.0.1').pathname);
    if (request.method !== 'GET' || path.startsWith('/api/') || path.startsWith('/auth/')) {
      response.writeHead(404).end();
      return;
    }
    const relative = path === '/' || path.startsWith('/projects/') ? 'index.html' : path.slice(1);
    const file = resolve(root, relative);
    if (!file.startsWith(root.endsWith(sep) ? root : root + sep) || !(await stat(file)).isFile()) {
      response.writeHead(404).end();
      return;
    }
    response.writeHead(200, {
      'Content-Type': types[extname(file)] || 'application/octet-stream',
      'Cache-Control': 'no-store',
      'X-Content-Type-Options': 'nosniff',
      'Content-Security-Policy': "default-src 'none'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'",
    });
    response.end(await readFile(file));
  } catch { response.writeHead(404).end(); }
});
server.listen(port, '127.0.0.1', () => process.stdout.write(`Static app test host: http://127.0.0.1:${port}\n`));
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => server.close(() => process.exit(0)));
