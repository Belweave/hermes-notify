// Public document errors contain fixed copy only. API/auth responses keep their
// JSON contract, and no request path, exception detail or project data is echoed.
export const RECOVERY_ASSETS = new Set([
  '/styles.css', '/fonts/PaperMono-Variable.woff2',
  '/logos/nous-research.png', '/logos/notify.svg',
]);

export function secureAsset(response) {
  const secured = new Response(response.body, response);
  secured.headers.set('cache-control', 'no-store');
  secured.headers.set('x-content-type-options', 'nosniff');
  secured.headers.set('referrer-policy', 'no-referrer');
  secured.headers.set('content-security-policy', "default-src 'self'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'");
  return secured;
}

export function isDocument(request) {
  const path = new URL(request.url).pathname;
  return !path.startsWith('/api/') && !path.startsWith('/auth/')
    && (request.headers.get('accept') || '').split(',').some(type => type.trim().split(';')[0] === 'text/html');
}

export function errorPage(status, method) {
  const missing = status === 404;
  const unavailable = status >= 500;
  const title = missing ? 'Page not found' : unavailable ? 'Workspace temporarily unavailable' : 'This workspace cannot be opened';
  const message = missing
    ? 'This page does not exist. Open the current project workspace from Notify, or ask Hermes for a new link.'
    : unavailable
      ? 'Try reloading this page. If it is still unavailable, ask the workspace owner to check the service.'
      : 'Open the current project workspace from Notify. If it still does not open, ask the workspace owner to check the link.';
  const html = `<!doctype html>
<html lang="en"><head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="theme-color" content="#f7f8f5">
  <meta name="referrer" content="no-referrer">
  <title>${title} · Hermes Pocket</title>
  <link rel="icon" href="/logos/nous-research.png" type="image/png">
  <link rel="preload" href="/fonts/PaperMono-Variable.woff2" as="font" type="font/woff2" crossorigin>
  <link rel="stylesheet" href="/styles.css">
</head><body class="document-page">
  <a class="skip-link" href="#main">Skip to workspace</a>
  <div class="page">
    <header class="site-header"><span class="brand"><img class="brand-mark" src="/logos/nous-research.png" width="32" height="32" alt="Nous Research">hermes pocket</span></header>
    <main id="main" tabindex="-1"><section class="gate" aria-labelledby="page-title">
      <h1 id="page-title">${title}</h1>
      <p role="status">${message}</p>
      <div class="gate-actions">
        ${unavailable ? '<a class="button" href="">Reload page</a>' : '<a class="button" href="/">Open workspace home</a>'}
        <a class="text-control provider-control" href="https://notify.belweave.ai" target="_blank" rel="noopener noreferrer"><img src="/logos/notify.svg" width="18" height="22" alt="">Open Notify</a>
      </div>
    </section></main>
    <footer class="site-footer"><span>Release workspace</span><span class="provider-credit"><img src="/logos/notify.svg" width="16" height="20" alt="">Notify integration</span></footer>
  </div>
</body></html>`;
  return secureAsset(new Response(method === 'HEAD' ? null : html, {
    status, headers: { 'content-type': 'text/html; charset=utf-8' },
  }));
}
