import { expect } from '@playwright/test';

export const PROJECT = 'release-demo';
export const API = `/api/projects/${PROJECT}`;
export const SESSION = `/auth/${PROJECT}/session`;

// Private-looking sample content exists only here, never in app/public or the
// static server. Route interception is the only fixture/auth seam.
export function fixture(overrides = {}) {
  return {
    schemaVersion: 1, project: PROJECT, runId: 'run_phone_01', revision: 4,
    name: 'Pocket release', version: '1.4.0', status: 'running', stage: 'Verification',
    summary: 'The candidate is built. Checking the phone flow before the release.',
    progress: 0.625,
    checks: [
      { label: 'Build & type checks', status: 'passed' },
      { label: 'Session and reply tests', status: 'passed' },
      { label: 'Phone layout review', status: 'running' },
      { label: 'Release health check', status: 'pending' },
    ],
    artifacts: [
      { label: 'Release candidate', url: 'https://example.com/releases/1.4.0' },
      { label: 'Verification report', url: 'https://example.com/reports/phone' },
    ],
    notes: 'Release\nKeeps the current decision and release evidence together on your phone. Replies return to the original run.\n\nRollback\nRestore the previous release artifact and verify the health check before reopening traffic.',
    updatedAt: '2026-11-04T22:14:00Z', appId: 'app_phone_demo', approval: null,
    ...overrides,
  };
}

export async function mock(page, options = {}) {
  let workspace = options.workspace || fixture({ project: options.project || PROJECT });
  let signedIn = options.signedIn ?? true;
  const requests = [];
  const replies = [];
  const project = options.project || PROJECT;
  await page.route('**/*', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.hostname !== '127.0.0.1') throw new Error(`Unexpected external request: ${url.origin}`);
    if (url.pathname === '/auth.js' && !options.realAuth) {
      return route.fulfill({ contentType: 'text/javascript', body: options.authModule || 'export async function connect(project) { return { authenticated: true, project }; }' });
    }
    if (!url.pathname.startsWith('/api/') && !url.pathname.startsWith('/auth/')) return route.continue();
    requests.push({ path: url.pathname, method: request.method() });
    if (url.pathname === `/auth/${project}/session`) {
      if (options.sessionHandler) return options.sessionHandler(route);
      if (request.method() === 'DELETE') { signedIn = false; return route.fulfill({ json: { ok: true } }); }
      return route.fulfill({ status: signedIn ? 200 : 401, json: signedIn ? { ok: true, authenticated: true, project } : { error: 'sign_in_required' } });
    }
    if (url.pathname === `/api/projects/${project}/replies` && request.method() === 'POST') {
      const reply = request.postDataJSON();
      replies.push(reply);
      if (options.replyHandler) return options.replyHandler(route, reply, replies.length);
      return route.fulfill({ json: { id: reply.id, cursor: replies.length, accepted: true } });
    }
    if (url.pathname === `/api/projects/${project}` && request.method() === 'GET') {
      if (options.workspaceHandler) return options.workspaceHandler(route, workspace);
      return route.fulfill({ json: { workspace, revision: workspace.revision } });
    }
    throw new Error(`Unexpected API request: ${request.method()} ${url.pathname}`);
  });
  return {
    requests, replies,
    setWorkspace: (next) => { workspace = next; },
    signIn: () => { signedIn = true; },
    signOut: () => { signedIn = false; },
    dataRequests: () => requests.filter((request) => request.path === `/api/projects/${project}`),
  };
}

export async function open(page, project = PROJECT) {
  await page.goto(`/projects/${project}`);
  await expect(page.locator('#release-name')).toBeVisible();
}

