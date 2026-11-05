import { test, expect } from '@playwright/test';

const PROJECT = 'release-demo';
const API = `/api/projects/${PROJECT}`;
const SESSION = `/auth/${PROJECT}/session`;

// Private-looking sample content exists only here, never in app/public or the
// static server. Route interception is the only fixture/auth seam.
function fixture(overrides = {}) {
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

async function mock(page, options = {}) {
  let workspace = options.workspace || fixture({ project: options.project || PROJECT });
  let signedIn = options.signedIn ?? true;
  const requests = [];
  const replies = [];
  const project = options.project || PROJECT;
  await page.route('**/*', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.hostname !== '127.0.0.1') throw new Error(`Unexpected external request: ${url.origin}`);
    if (url.pathname === '/auth.js') {
      return route.fulfill({ contentType: 'text/javascript', body: options.authModule || 'export async function connect(project) { return { authenticated: true, project }; }' });
    }
    if (!url.pathname.startsWith('/api/') && !url.pathname.startsWith('/auth/')) return route.continue();
    requests.push({ path: url.pathname, method: request.method() });
    if (url.pathname === `/auth/${project}/session`) {
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

async function open(page, project = PROJECT) {
  await page.goto(`/projects/${project}`);
  await expect(page.locator('#release-name')).toBeVisible();
}

test('public shell and signed-out view contain no release data or fixture bypass', async ({ page, request }, testInfo) => {
  const shell = await (await request.get(`/projects/${PROJECT}?mock=shipped`)).text();
  expect(shell).not.toContain('Pocket release');
  expect(shell).not.toContain('run_phone_01');
  const state = await mock(page, { signedIn: false });
  await page.goto(`/projects/${PROJECT}?mock=shipped&fixture=running`);
  await expect(page.getByRole('heading', { name: 'Your release workspace' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Sign in with Notify' })).toBeVisible();
  expect(state.dataRequests()).toHaveLength(0);
  await expect(page.locator('#workspace')).toBeHidden();
  await page.screenshot({ path: testInfo.outputPath('signed-out-phone.png'), fullPage: true });
});

test('sign-in uses connect(project), then verifies the session before private data', async ({ page }) => {
  const state = await mock(page, { signedIn: false, authModule: 'export async function connect(project) { window.connectedProject = project; }' });
  await page.goto(`/projects/${PROJECT}`);
  await expect(page.getByRole('button', { name: 'Sign in with Notify' })).toBeVisible();
  state.signIn();
  await page.getByRole('button', { name: 'Sign in with Notify' }).click();
  await expect(page.locator('#release-name')).toHaveText('Pocket release');
  expect(await page.evaluate(() => window.connectedProject)).toBe(PROJECT);
  expect(state.requests.map((request) => request.path)).toEqual([SESSION, SESSION, API]);
});

test('unsupported browser sign-in explains the Notify path without exposing private data', async ({ page }) => {
  const state = await mock(page, { signedIn: false, authModule: "export async function connect() { throw new Error('Open this workspace in an updated Notify app on your phone to sign in.'); }" });
  await page.goto(`/projects/${PROJECT}`);
  await page.getByRole('button', { name: 'Sign in with Notify' }).click();
  await expect(page.getByRole('heading', { name: 'Sign-in not completed' })).toBeVisible();
  await expect(page.locator('#gate-message')).toContainText('updated Notify app');
  expect(state.dataRequests()).toHaveLength(0);
});

test('URL project determines both session and data routes; invalid paths never request data', async ({ page }) => {
  const state = await mock(page, { project: 'another-project' });
  await open(page, 'another-project');
  expect(state.requests.map((request) => request.path)).toEqual(['/auth/another-project/session', '/api/projects/another-project']);
  await page.goto('/projects/UPPERCASE');
  await expect(page.getByRole('heading', { name: 'Open a project link' })).toBeVisible();
  expect(state.requests).toHaveLength(2);
});

test('running release shows measured work, read-only checks, notes and safe artifacts', async ({ page }, testInfo) => {
  await mock(page);
  await open(page);
  await expect(page.locator('#release-status')).toHaveText('Running');
  await expect(page.getByRole('progressbar')).toHaveAttribute('value', '0.625');
  await expect(page.locator('#progress-label')).toHaveText('63%');
  await expect(page.locator('#check-count')).toHaveText('2/4 passed');
  await expect(page.getByRole('checkbox')).toHaveCount(0);
  await expect(page.locator('#release-notes')).toContainText('Rollback');
  const artifact = page.getByRole('link', { name: /Release candidate, example.com/ });
  await expect(artifact).toHaveAttribute('href', 'https://example.com/releases/1.4.0');
  await expect(artifact).toHaveAttribute('rel', 'noopener noreferrer');
  await expect(page.getByRole('heading', { name: 'No decision needed' })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath('running-phone.png'), fullPage: true });
});

test('unknown progress stays unmeasured even when checks pass', async ({ page }) => {
  await mock(page, { workspace: fixture({ progress: null, checks: [{ label: 'Build', status: 'passed' }] }) });
  await open(page);
  await expect(page.getByRole('progressbar')).toHaveCount(0);
  await expect(page.getByText('Progress has not been measured.')).toBeVisible();
});

test('native approval is explained and linked; a written approve reply grants no permission', async ({ page }, testInfo) => {
  const state = await mock(page, { workspace: fixture({ status: 'awaiting_approval', stage: 'Release gate', progress: 0.9,
    approval: { requestId: 'host_request_01', digest: 'a'.repeat(64), title: 'Publish version 1.4.0', status: 'pending' },
    summary: 'Preflight checks are complete. Hermes needs your approval for the final release action.',
    checks: fixture().checks.map((check) => ({ ...check, status: check.label === 'Release health check' ? 'pending' : 'passed' })),
  }) });
  await open(page);
  await expect(page.getByRole('heading', { name: 'Publish version 1.4.0' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Open Notify ↗' })).toHaveAttribute('href', 'https://notify.belweave.ai');
  await expect(page.getByRole('button', { name: /approve|deny/i })).toHaveCount(0);
  await expect(page.locator('#native-hint')).toContainText('Written replies here do not approve it.');
  await page.screenshot({ path: testInfo.outputPath('awaiting-approval-phone.png'), fullPage: true });
  await page.getByLabel('Your reply').fill('approve');
  await page.getByRole('button', { name: 'Send reply', exact: true }).click();
  await expect(page.locator('#reply-feedback')).toContainText('Reply saved for this run');
  expect(state.replies).toHaveLength(1);
  expect(Object.keys(state.replies[0]).sort()).toEqual(['id', 'runId', 'text']);
  expect(state.requests.filter((request) => request.method !== 'GET').map((request) => request.path)).toEqual([`${API}/replies`]);
  await expect(page.locator('#release-status')).toHaveText('Awaiting approval');
});

test('approved state waits for an explicit shipped snapshot', async ({ page }) => {
  const state = await mock(page, { workspace: fixture({ status: 'approved' }) });
  await open(page);
  await expect(page.getByRole('heading', { name: 'Approval recorded' })).toBeVisible();
  await expect(page.locator('#release-status')).not.toHaveText('Shipped');
  state.setWorkspace(fixture({ status: 'shipped', revision: 5 }));
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect(page.locator('#release-status')).toHaveText('Shipped');
});

for (const [status, title] of [['shipped', 'Release complete'], ['failed', 'Release needs attention'], ['denied', 'Release denied'], ['canceled', 'Release canceled']]) {
  test(`${status} has a distinct terminal outcome and stops automatic polling`, async ({ page }, testInfo) => {
    await page.clock.install();
    const summaries = {
      shipped: 'Version 1.4.0 is shipped. The release health check passed.',
      failed: 'The release health check failed. Hermes stopped the run. Review the rollback notes before recovery.',
      denied: 'The final release action was denied. This candidate has not been shipped by this run.',
      canceled: 'This release run was canceled. The last reported artifacts are kept for reference.',
    };
    const checks = fixture().checks.map((check) => ({ ...check, status: status === 'failed' && check.label === 'Release health check' ? 'failed' : status === 'shipped' || status === 'failed' ? 'passed' : check.status }));
    const state = await mock(page, { workspace: fixture({ status, summary: summaries[status], checks,
      stage: status === 'shipped' ? 'Complete' : status === 'failed' ? 'Health check' : 'Stopped',
      progress: status === 'shipped' ? 1 : 0.9,
    }) });
    await open(page);
    await expect(page.getByRole('heading', { name: title, exact: true })).toBeVisible();
    if (status === 'failed') await expect(page.locator('#checks li[data-status="failed"]')).toContainText('Release health check');
    await expect(page.locator('#sync-status')).toHaveText('Run ended. Automatic updates stopped.');
    await page.clock.runFor(180_000);
    expect(state.dataRequests()).toHaveLength(1);
    await page.getByRole('button', { name: 'Refresh', exact: true }).click();
    await expect.poll(() => state.dataRequests().length).toBe(2);
    if (status === 'shipped' || status === 'failed') await page.screenshot({ path: testInfo.outputPath(`${status}-phone.png`), fullPage: true });
  });
}

test('uncertain reply retry reuses exact ID, run and text and confirms a saved receipt', async ({ page }) => {
  let releaseReply;
  const blocked = new Promise((resolve) => { releaseReply = resolve; });
  const state = await mock(page, { replyHandler: async (route, reply, count) => {
    if (count === 1) { await blocked; return route.abort('failed'); }
    return route.fulfill({ json: { id: reply.id, cursor: 7, accepted: true } });
  } });
  await open(page);
  await page.getByLabel('Your reply').fill('Please include the rollback notes.');
  await page.getByRole('button', { name: 'Send reply', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Saving reply…' })).toBeDisabled();
  await expect(page.getByLabel('Your reply')).toBeDisabled();
  releaseReply();
  await expect(page.locator('#reply-feedback')).toContainText('Receipt not confirmed');
  await expect(page.getByLabel('Your reply')).toHaveAttribute('readonly', '');
  await page.getByRole('button', { name: 'Retry reply', exact: true }).click();
  await expect(page.locator('#reply-feedback')).toContainText('delivery to the task is not yet confirmed');
  expect(state.replies).toHaveLength(2);
  expect(state.replies[0]).toEqual(state.replies[1]);
  expect(state.replies[0].id).toMatch(/^[a-f0-9-]{36}$/);
  await page.getByRole('button', { name: 'Write another reply' }).click();
  await expect(page.getByLabel('Your reply')).toHaveValue('');
  await expect(page.getByLabel('Your reply')).toBeFocused();
});

test('unverified receipt is not shown as confirmed and preserves retry identity', async ({ page }) => {
  const state = await mock(page, { replyHandler: (route) => route.fulfill({ json: { id: 'wrong_id', cursor: 1, accepted: true } }) });
  await open(page);
  await page.getByLabel('Your reply').fill('Please check the release.');
  await page.getByRole('button', { name: 'Send reply', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Retry reply', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Retry reply', exact: true }).click();
  await expect.poll(() => state.replies.length).toBe(2);
  expect(state.replies[0]).toEqual(state.replies[1]);
});

test('old-run conflict keeps the draft and requires explicit review for the new run', async ({ page }) => {
  const state = await mock(page, { replyHandler: (route, reply, count) => count === 1
    ? route.fulfill({ status: 409, json: { error: 'run_conflict' } })
    : route.fulfill({ json: { id: reply.id, cursor: 1, accepted: true } }) });
  await open(page);
  await page.getByLabel('Your reply').fill('Please include rollback notes.');
  state.setWorkspace(fixture({ revision: 5, runId: 'run_phone_02' }));
  await page.getByRole('button', { name: 'Send reply', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Use draft for current run' })).toBeEnabled();
  await expect(page.getByLabel('Your reply')).toHaveValue('Please include rollback notes.');
  expect(state.replies).toHaveLength(1);
  await page.getByRole('button', { name: 'Use draft for current run' }).click();
  await page.getByRole('button', { name: 'Send reply', exact: true }).click();
  await expect(page.locator('#reply-feedback')).toContainText('Reply saved');
  expect(state.replies[1].runId).toBe('run_phone_02');
  expect(state.replies[1].id).not.toBe(state.replies[0].id);
});

test('session expiry clears private state, drafts and artifact links', async ({ page }) => {
  const state = await mock(page);
  await open(page);
  await page.getByLabel('Your reply').fill('Private draft');
  state.signOut();
  await page.route(`**${API}`, (route) => route.fulfill({ status: 401, json: { error: 'sign_in_required' } }));
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Sign in with Notify' })).toBeVisible();
  expect(await page.locator('body').textContent()).not.toContain('Pocket release');
  expect(await page.locator('body').textContent()).not.toContain('Restore the previous');
  await expect(page.locator('#artifacts a')).toHaveCount(0);
  await expect(page.locator('#reply-text')).toHaveValue('');
});

test('sign-out revokes the cookie session and wipes private DOM', async ({ page }) => {
  const state = await mock(page);
  await open(page);
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await expect(page.locator('#gate-message')).toContainText('You are signed out');
  expect(await page.locator('body').textContent()).not.toContain('Pocket release');
  expect(state.requests.filter((request) => request.method === 'DELETE')).toEqual([{ path: SESSION, method: 'DELETE' }]);
});

for (const [name, patch] of [
  ['cross-project response', { project: 'other-project' }],
  ['unsafe artifact scheme', { artifacts: [{ label: 'Bad link', url: 'javascript:alert(1)' }] }],
  ['credential-bearing artifact', { artifacts: [{ label: 'Bad link', url: 'https://user:password@example.com' }] }],
  ['invalid progress', { progress: 1.5 }],
  ['unknown status', { status: 'ready_to_ship' }],
  ['malformed checks', { checks: [{ label: 'Build', status: 'green' }] }],
  ['missing field', { notes: undefined }],
]) {
  test(`invalid payload fails closed: ${name}`, async ({ page }) => {
    await mock(page, { workspace: fixture(patch) });
    await page.goto(`/projects/${PROJECT}`);
    await expect(page.getByRole('heading', { name: 'Could not load this release' })).toBeVisible();
    await expect(page.locator('#gate-message')).toContainText('could not be verified');
    await expect(page.locator('#workspace')).toBeHidden();
    await expect(page.locator('#artifacts a')).toHaveCount(0);
  });
}

test('workspace strings remain text, never HTML', async ({ page }) => {
  const attack = '<img src=x onerror="window.injected=true">';
  await mock(page, { workspace: fixture({ name: attack, notes: attack, summary: attack,
    checks: [{ label: attack, status: 'passed' }], artifacts: [{ label: attack, url: 'https://example.com/safe' }] }) });
  await open(page);
  await expect(page.locator('#release-name')).toHaveText(attack);
  await expect(page.locator('#release-notes')).toHaveText(attack);
  await expect(page.locator('#workspace img')).toHaveCount(0);
  expect(await page.evaluate(() => window.injected)).toBeUndefined();
});

test('refresh failure preserves a verified snapshot and recovers without losing a draft', async ({ page }) => {
  let broken = false;
  const state = await mock(page, { workspaceHandler: (route, workspace) => broken
    ? route.fulfill({ status: 503, json: { error: 'unavailable' } })
    : route.fulfill({ json: { workspace, revision: workspace.revision } }) });
  await open(page);
  await page.getByLabel('Your reply').fill('Keep my draft.');
  broken = true;
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect(page.locator('#sync-status')).toContainText('Showing the last verified release');
  await expect(page.locator('#release-name')).toHaveText('Pocket release');
  await expect(page.getByLabel('Your reply')).toHaveValue('Keep my draft.');
  broken = false;
  state.setWorkspace(fixture({ revision: 5, progress: 0.75 }));
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect(page.locator('#progress-label')).toHaveText('75%');
  await expect(page.getByLabel('Your reply')).toHaveValue('Keep my draft.');
});

test('polling backs off unchanged snapshots, pauses hidden, and resumes once', async ({ page }) => {
  await page.clock.install();
  const state = await mock(page);
  await open(page);
  await page.clock.runFor(9_000);
  expect(state.dataRequests()).toHaveLength(1);
  await page.clock.runFor(1_100);
  await expect.poll(() => state.dataRequests().length).toBe(2);
  await expect(page.getByRole('button', { name: 'Refresh', exact: true })).toBeEnabled();
  await page.clock.runFor(19_000);
  expect(state.dataRequests()).toHaveLength(2);
  await page.clock.runFor(1_100);
  await expect.poll(() => state.dataRequests().length).toBe(3);
  await page.evaluate(() => {
    Object.defineProperty(document, 'hidden', { configurable: true, value: true });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  await page.clock.runFor(180_000);
  expect(state.dataRequests()).toHaveLength(3);
  await page.evaluate(() => {
    Object.defineProperty(document, 'hidden', { configurable: true, value: false });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  await expect.poll(() => state.dataRequests().length).toBe(4);
});

test('data requests stay serial when a reply is sent during a slow refresh', async ({ page }) => {
  let getCount = 0;
  let finishRefresh;
  const pending = new Promise((resolve) => { finishRefresh = resolve; });
  const state = await mock(page, { workspaceHandler: async (route, workspace) => {
    getCount += 1;
    if (getCount === 2) await pending;
    return route.fulfill({ json: { workspace, revision: workspace.revision } });
  } });
  await open(page);
  await page.getByLabel('Your reply').fill('Check the notes.');
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect.poll(() => getCount).toBe(2);
  await page.getByRole('button', { name: 'Send reply', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Saving reply…' })).toBeDisabled();
  expect(state.replies).toHaveLength(0);
  finishRefresh();
  await expect(page.locator('#reply-feedback')).toContainText('Reply saved');
  expect(state.replies).toHaveLength(1);
});

test('network timeout unlocks refresh and gives an honest connection error', async ({ page }) => {
  await page.clock.install();
  let pendingRoute;
  await mock(page, { workspaceHandler: (route) => { pendingRoute = route; } });
  await page.goto(`/projects/${PROJECT}`);
  await expect.poll(() => Boolean(pendingRoute)).toBe(true);
  await page.clock.runFor(12_100);
  await expect(page.getByRole('heading', { name: 'Could not load this release' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Try again', exact: true })).toBeEnabled();
});

for (const width of [360, 768, 1440]) {
  test(`responsive layout at ${width}px loads Paper Mono and keeps controls usable`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    await mock(page, { workspace: fixture({ name: 'Release workspace for the phone', status: 'awaiting_approval',
      approval: { requestId: 'host_request_01', digest: 'a'.repeat(64), title: 'Publish the release candidate', status: 'pending' },
    }) });
    await open(page);
    await expect(page.getByRole('link', { name: 'Reply ↓', exact: true })).toHaveAttribute('href', '#reply');
    await page.evaluate(() => document.fonts.ready);
    const result = await page.evaluate(() => ({
      overflow: document.documentElement.scrollWidth > window.innerWidth,
      font: getComputedStyle(document.body).fontFamily,
      loaded: [...document.fonts].some((font) => font.family === 'Paper Mono' && font.status === 'loaded'),
      targets: [...document.querySelectorAll('button, a:not(.skip-link), textarea')].filter((node) => node.getClientRects().length).map((node) => ({ text: node.textContent, height: node.getBoundingClientRect().height, width: node.getBoundingClientRect().width })),
      transitions: getComputedStyle(document.querySelector('button')).transitionDuration,
    }));
    expect(result.overflow).toBe(false);
    expect(result.font).toContain('Paper Mono');
    expect(result.loaded).toBe(true);
    expect(result.targets.every((target) => target.height >= 44 && target.width >= 44)).toBe(true);
    expect(result.transitions).toBe('0s');
    const record = await page.locator('.release-record').boundingBox();
    const composer = await page.locator('.reply-column').boundingBox();
    if (width < 880) expect(composer.y).toBeGreaterThan(record.y + record.height - 1);
    else expect(composer.x).toBeGreaterThan(record.x + record.width);
    await page.screenshot({ path: testInfo.outputPath(`workspace-${width}.png`), fullPage: true });
  });
}

test('keyboard navigation exposes visible focus, labels and reply validation', async ({ page }) => {
  await mock(page);
  await open(page);
  await page.keyboard.press('Tab');
  await expect(page.getByRole('link', { name: 'Skip to workspace' })).toBeFocused();
  const focus = await page.locator(':focus').evaluate((node) => ({ style: getComputedStyle(node).outlineStyle, width: getComputedStyle(node).outlineWidth }));
  expect(focus).toEqual({ style: 'solid', width: '3px' });
  await page.keyboard.press('Enter');
  await expect(page.locator('#main')).toBeFocused();
  await expect(page.getByRole('button', { name: 'Send reply', exact: true })).toBeDisabled();
  await page.getByLabel('Your reply').fill('  ');
  await expect(page.getByRole('button', { name: 'Send reply', exact: true })).toBeDisabled();
  await page.getByLabel('Your reply').fill('Context for the release.');
  await expect(page.getByRole('button', { name: 'Send reply', exact: true })).toBeEnabled();
});

test('a pending reply keeps its original run if a queued refresh reveals a new run', async ({ page }) => {
  let reads = 0;
  let finishRefresh;
  const delayed = new Promise((resolve) => { finishRefresh = resolve; });
  const state = await mock(page, { workspaceHandler: async (route, workspace) => {
    reads += 1;
    if (reads === 2) {
      await delayed;
      workspace = fixture({ revision: 5, runId: 'run_phone_02' });
    }
    return route.fulfill({ json: { workspace, revision: workspace.revision } });
  } });
  await open(page);
  await page.getByLabel('Your reply').fill('Context for the original run.');
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect.poll(() => reads).toBe(2);
  await page.getByRole('button', { name: 'Send reply', exact: true }).click();
  finishRefresh();
  await expect(page.locator('#reply-feedback')).toContainText('Reply saved for the previous run');
  expect(state.replies[0].runId).toBe('run_phone_01');
  await expect(page.locator('#revision-label')).toHaveText('Revision 5');
  await expect(page.getByRole('button', { name: 'Use draft for current run' })).toBeHidden();
});

test('drafts are never silently retargeted when a new run is polled', async ({ page }) => {
  const state = await mock(page);
  await open(page);
  await page.getByLabel('Your reply').fill('This is for the original run.');
  state.setWorkspace(fixture({ revision: 5, runId: 'run_phone_02' }));
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect(page.locator('#reply-feedback')).toContainText('Review your draft');
  await expect(page.getByRole('button', { name: 'Send reply', exact: true })).toBeHidden();
  await expect(page.getByRole('button', { name: 'Use draft for current run' })).toBeEnabled();
  expect(state.replies).toHaveLength(0);
});

test('repeated polling failures back off and stop until an explicit refresh', async ({ page }) => {
  await page.clock.install();
  let broken = false;
  const state = await mock(page, { workspaceHandler: (route, workspace) => broken
    ? route.fulfill({ status: 503, json: { error: 'unavailable' } })
    : route.fulfill({ json: { workspace, revision: workspace.revision } }) });
  await open(page);
  broken = true;
  for (const [index, delay] of [10_100, 20_100, 40_100, 60_100, 60_100].entries()) {
    await page.clock.runFor(delay);
    await expect.poll(() => state.dataRequests().length).toBe(index + 2);
    await expect(page.getByRole('button', { name: 'Refresh', exact: true })).toBeEnabled();
  }
  await expect(page.locator('#sync-status')).toContainText('Automatic updates paused');
  await page.clock.runFor(180_000);
  expect(state.dataRequests()).toHaveLength(6);
  broken = false;
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect(page.locator('#sync-status')).toContainText('auto-refresh on');
});

test('offline pauses automatic traffic and reconnect refreshes the current release', async ({ page }) => {
  await page.clock.install();
  const state = await mock(page);
  await open(page);
  await page.evaluate(() => {
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false });
    window.dispatchEvent(new Event('offline'));
  });
  await expect(page.locator('#sync-status')).toContainText('Offline');
  await page.clock.runFor(180_000);
  expect(state.dataRequests()).toHaveLength(1);
  state.setWorkspace(fixture({ revision: 5, progress: 0.75 }));
  await page.evaluate(() => {
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: true });
    window.dispatchEvent(new Event('online'));
  });
  await expect(page.locator('#progress-label')).toHaveText('75%');
  expect(state.dataRequests()).toHaveLength(2);
});

test('an oversized or mislabeled response cannot become workspace data', async ({ page }) => {
  await mock(page, { workspaceHandler: (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ padding: 'x'.repeat(65_537) }) }) });
  await page.goto(`/projects/${PROJECT}`);
  await expect(page.locator('#gate-message')).toContainText('could not be verified');
  await page.route(`**${API}`, (route) => route.fulfill({ contentType: 'text/html', body: JSON.stringify({ workspace: fixture(), revision: 4 }) }));
  await page.getByRole('button', { name: 'Try again', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Could not load this release' })).toBeVisible();
  await expect(page.locator('#workspace')).toBeHidden();
});

test('old revisions and changed bytes at the same revision cannot replace verified content', async ({ page }) => {
  const state = await mock(page);
  await open(page);
  state.setWorkspace(fixture({ revision: 3, name: 'An older release' }));
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect(page.locator('#sync-status')).toContainText('could not be verified');
  await expect(page.locator('#release-name')).toHaveText('Pocket release');
  state.setWorkspace(fixture({ revision: 4, name: 'Unversioned change' }));
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect(page.locator('#release-name')).toHaveText('Pocket release');
});

test('empty contract fields have useful empty states without invented progress', async ({ page }) => {
  await mock(page, { workspace: fixture({ name: '', version: '', stage: '', summary: '', progress: null, notes: '', checks: [], artifacts: [] }) });
  await open(page);
  await expect(page.locator('#release-name')).toHaveText('Release workspace');
  await expect(page.locator('#release-version')).toHaveText('Version not set');
  await expect(page.locator('#release-stage')).toHaveText('Stage not reported');
  await expect(page.locator('#checks-empty')).toBeVisible();
  await expect(page.locator('#artifacts-empty')).toBeVisible();
  await expect(page.locator('#release-notes')).toContainText('No release or rollback notes');
});

test('content at the contract limits reflows at a 320px zoom-equivalent width', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 720 });
  await mock(page, { workspace: fixture({ name: 'N'.repeat(80), version: 'V'.repeat(80), stage: 'S'.repeat(80), summary: 'Summary '.repeat(62),
    notes: 'N'.repeat(8000),
    checks: Array.from({ length: 20 }, () => ({ label: 'C'.repeat(80), status: 'failed' })),
    artifacts: Array.from({ length: 20 }, () => ({ label: 'A'.repeat(80), url: 'https://example.com/artifact' })),
  }) });
  await open(page);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  const textarea = await page.getByLabel('Your reply').boundingBox();
  expect(textarea.width).toBeLessThanOrEqual(280);
  await expect(page.locator('#checks li')).toHaveCount(20);
  await expect(page.locator('#artifacts a')).toHaveCount(20);
});

test('a failed sign-out clears the view but asks for a retry instead of claiming success', async ({ page }) => {
  await mock(page);
  await open(page);
  await page.route(`**${SESSION}`, (route) => route.request().method() === 'DELETE'
    ? route.fulfill({ status: 503, json: { error: 'unavailable' } }) : route.fallback());
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Sign-out needs a retry' })).toBeVisible();
  expect(await page.locator('body').textContent()).not.toContain('Pocket release');
  await expect(page.locator('#sign-in')).toBeHidden();
  await page.route(`**${SESSION}`, (route) => route.fulfill({ json: { ok: true } }));
  await page.getByRole('button', { name: 'Try again', exact: true }).click();
  await expect(page.locator('#gate-message')).toContainText('You are signed out');
});
