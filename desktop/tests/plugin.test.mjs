import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { stripTypeScriptTypes } from 'node:module';
import test from 'node:test';
import vm from 'node:vm';

const entry = new URL('../plugin.js', import.meta.url);
const upstream = new URL('../.local/hermes-source/', entry);
const source = readFileSync(entry, 'utf8');
const readUpstream = path => readFileSync(new URL(path, upstream), 'utf8');
const sdkNames = [...source.match(/import\s*\{([^}]+)\}\s*from '@hermes\/plugin-sdk'/s)[1].matchAll(/\b[A-Za-z]\w*\b/g)].map(match => match[0]);

async function harness() {
  let profile = 'alpha';
  let connection = 'local';
  let epoch = 1;
  let gateway = 'open';
  let queryState = { data: null, isError: false, isPending: false, isFetching: false, refetch() {} };
  const queries = [], cleanup = [], contributions = [], cancellations = [], removals = [], restCalls = [], opened = [], navigated = [];
  const host = {
    state: { profile: { get: () => profile }, gateway: { get: () => gateway } },
    activeConnectionId: () => connection,
    notify() {}, navigate(path) { navigated.push(path); }
  };
  const sdk = {
    host, useValue: atom => atom.get(), useQuery(options) { queries.push(options); return queryState; },
    queryClient: { cancelQueries(options) { cancellations.push(options); return Promise.resolve(); }, removeQueries(options) { removals.push(options); } },
    gatewayActivationEpoch: () => epoch, useGatewayActivationEpoch: () => epoch,
    ROUTES_AREA: 'routes', SIDEBAR_NAV_AREA: 'sidebarNav'
  };
  const context = vm.createContext({ URL, Date, console, setTimeout, clearTimeout });
  const h = (type, props, ...children) => ({ type, props: { ...props, children } });
  const mocks = {
    '@hermes/plugin-sdk': new vm.SyntheticModule(sdkNames, function () {
      for (const name of sdkNames) this.setExport(name, sdk[name]);
    }, { context }),
    'react': new vm.SyntheticModule(['createElement'], function () { this.setExport('createElement', h); }, { context })
  };
  const module = new vm.SourceTextModule(source + '\nexport { scope, readStatus, safeUrl, needsRefresh, registeredApps };', { context });
  await module.link(specifier => {
    assert.ok(mocks[specifier], `Unexpected import ${specifier}`);
    return mocks[specifier];
  });
  await module.evaluate();
  const ctx = {
    registerMany(values) { contributions.push(...values); },
    onDispose(fn) { cleanup.push(fn); },
    async rest(path, options) { restCalls.push({ path, options }); return emptySnapshot(); },
    os: { async openExternal(url) { opened.push(url); return true; } }
  };
  const render = node => {
    if (!node || typeof node !== 'object') return node;
    if (Array.isArray(node)) return node.map(render);
    if (typeof node.type === 'function') return render(node.type(node.props));
    return { ...node, props: { ...node.props, children: node.props.children.map(render) } };
  };
  module.namespace.default.register(ctx);
  return {
    exports: module.namespace, ctx, cleanup, contributions, queries, cancellations, removals, restCalls, opened, navigated,
    render: () => render(contributions[0].render()),
    setQuery(value) { queryState = { ...queryState, ...value }; },
    switchScope(next) { profile = next.profile ?? profile; connection = next.connection ?? connection; epoch++; },
    disconnect() { gateway = 'closed'; }
  };
}

const emptySnapshot = () => ({ schemaVersion: 1, configured: true, runs: [], pending: [], deliveries: [], updatedAt: '2026-11-05T01:00:00Z' });
function nodes(tree, predicate) {
  if (Array.isArray(tree)) return tree.flatMap(child => nodes(child, predicate));
  if (!tree || typeof tree !== 'object') return [];
  return [...(predicate(tree) ? [tree] : []), ...tree.props.children.flatMap(child => nodes(child, predicate))];
}
function text(tree) {
  if (Array.isArray(tree)) return tree.map(text).join(' ');
  if (typeof tree === 'string') return tree;
  if (!tree || typeof tree !== 'object' || tree.type === 'style') return '';
  return text(tree.props.children);
}

test('imports exist in the real pinned SDK and pass its actual loader allowlist', () => {
  const sdkSource = readUpstream('apps/desktop/src/sdk/index.ts');
  const exports = new Set();
  for (const block of sdkSource.matchAll(/export\s*\{([^}]+)\}/gs)) {
    const declarations = block[1].replace(/\/\*[\s\S]*?\*\//g, '').split(',');
    for (const declaration of declarations) {
      const name = declaration.trim().split(/\s+as\s+/).at(-1);
      if (/^\w+$/.test(name)) exports.add(name);
    }
  }
  for (const match of sdkSource.matchAll(/export\s+(?:const|function|class)\s+(\w+)/g)) exports.add(match[1]);
  for (const name of sdkNames) assert.ok(exports.has(name), `SDK does not export ${name}`);

  // Run the real loader's import scanner, not a substitute regex check.
  const loader = readUpstream('apps/desktop/src/contrib/runtime-loader.ts');
  const scanner = loader.slice(loader.indexOf('const importSpecifierRe'), loader.indexOf('export function unloadRuntimePlugin'));
  const compiled = stripTypeScriptTypes(scanner, { mode: 'strip' });
  const scan = vm.runInNewContext(`${compiled}; unsupportedImports`, {
    sdkImportMap: () => ({ '@hermes/plugin-sdk': 'sdk', react: 'react', 'react/jsx-runtime': 'jsx' })
  });
  assert.deepEqual([...scan(source)], []);
  assert.deepEqual([...scan("import x from './not-allowed.js'")], ['./not-allowed.js']);
});

test('registers opt-in SDK contributions without any reads at registration', async () => {
  const app = await harness();
  assert.equal(app.exports.default.id, 'hermes-notify');
  assert.equal(app.exports.default.defaultEnabled, false);
  assert.deepEqual(app.contributions.map(item => item.area), ['panes', 'routes', 'sidebarNav']);
  assert.equal(app.restCalls.length, 0);
  app.render();
  const options = app.queries.at(-1);
  assert.deepEqual([...options.queryKey], ['hermes-notify:status:v1', 'alpha', 'local', 1]);
  await options.queryFn({ signal: new AbortController().signal });
  assert.equal(app.restCalls[0].path, '/status');
  assert.equal(app.restCalls[0].options.timeoutMs, 8000);
  assert.equal(options.gcTime, 0);
  assert.equal(options.retry, false);
});

test('rejects a late read after profile, connection, or same-route reactivation', async () => {
  for (const change of [{ profile: 'beta' }, { connection: 'other-server' }, {}]) {
    const app = await harness();
    let complete;
    app.ctx.rest = () => new Promise(resolve => { complete = resolve; });
    app.render();
    const oldKey = [...app.queries.at(-1).queryKey];
    const read = app.queries.at(-1).queryFn({ signal: new AbortController().signal });
    app.switchScope(change);
    complete(emptySnapshot());
    await assert.rejects(read, /Profile changed/);
    app.render();
    assert.notDeepEqual([...app.queries.at(-1).queryKey], oldKey);
  }
});

test('unload clears cached queries and prevents an in-flight publication', async () => {
  const app = await harness();
  let complete;
  app.ctx.rest = () => new Promise(resolve => { complete = resolve; });
  app.render();
  const read = app.queries.at(-1).queryFn({ signal: new AbortController().signal });
  for (const dispose of app.cleanup) dispose();
  complete(emptySnapshot());
  await assert.rejects(read, /Profile changed/);
  assert.equal(app.cancellations.length, 1);
  assert.equal(app.removals.length, 1);
});

test('aborted query cannot republish data even if the host REST request finishes', async () => {
  const app = await harness();
  let complete;
  app.ctx.rest = () => new Promise(resolve => { complete = resolve; });
  app.render();
  const abort = new AbortController();
  const read = app.queries.at(-1).queryFn({ signal: abort.signal });
  abort.abort();
  complete(emptySnapshot());
  await assert.rejects(read, /Profile changed/);
});

test('inactive, disabled and failed states do not poll', async () => {
  const app = await harness();
  app.render();
  const interval = app.queries.at(-1).refetchInterval;
  const state = data => ({ state: { status: 'success', data } });
  assert.equal(interval(state(emptySnapshot())), false);
  const active = { ...emptySnapshot(), runs: [{ status: 'running' }] };
  assert.equal(interval(state(active)), 15000);
  assert.equal(interval(state({ ...active, configured: false })), false);
  assert.equal(interval({ state: { status: 'error', data: active } }), false);
  assert.equal(interval(state({ ...emptySnapshot(), pending: [{ status: 'pending' }] })), 15000);
  app.disconnect(); app.render();
  assert.equal(app.queries.at(-1).enabled, false);
});

test('missing backend and disabled setup are explicit; old data is hidden on an error', async () => {
  const app = await harness();
  app.setQuery({ isError: true, data: { ...emptySnapshot(), deliveries: [{ project: 'stale-project', state: 'accepted', message: '' }] } });
  let tree = app.render();
  assert.match(text(tree), /backend may be missing, disabled/);
  assert.doesNotMatch(text(tree), /stale-project/);
  app.setQuery({ isError: false, data: { ...emptySnapshot(), configured: false } });
  tree = app.render();
  assert.match(text(tree), /not configured or sending is disabled/);
  assert.equal(nodes(tree, node => node.type === 'button').some(node => /approve|deny/i.test(text(node))), false);
});

test('only explicit HTTPS artifact links can open, without userinfo or script URLs', async () => {
  const app = await harness();
  for (const bad of ['javascript:alert(1)', 'file:///etc/passwd', 'http://example.com', 'https://user:pass@example.com', 'https://example.com/\nsecret', 'https:\\example.com']) {
    assert.equal(app.exports.safeUrl(bad), null);
  }
  assert.equal(app.exports.safeUrl('https://example.com/release'), 'https://example.com/release');
  const run = { project: 'demo', runId: 'one', name: 'Release', appId: 'app_demo', revision: 2, artifacts: [{ label: 'Notes', url: 'https://example.com/release' }], checks: [], progress: null };
  app.setQuery({ data: { ...emptySnapshot(), runs: [run] } });
  const tree = app.render();
  assert.equal(nodes(tree, node => node.type === 'progress').length, 0);
  const anchor = nodes(tree, node => node.type === 'a')[0];
  assert.equal(app.opened.length, 0);
  anchor.props.onClick({ preventDefault() {} });
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(app.opened, ['https://example.com/release']);
  assert.equal(app.exports.registeredApps([run, { ...run, revision: 1 }])[0].revision, 2);
  assert.equal(app.exports.registeredApps([
    { ...run, revision: 99, updatedAt: '2026-11-01T00:00:00Z' },
    { ...run, revision: 1, updatedAt: '2026-11-04T00:00:00Z' }
  ])[0].revision, 1);
});

test('embedded Paper Mono is identical to the official vendored file', () => {
  const encoded = source.match(/const FONT_DATA = '([^']+)';/)[1];
  const original = readFileSync(new URL('../assets/PaperMono-Variable.woff2', import.meta.url));
  assert.deepEqual(Buffer.from(encoded, 'base64'), original);
  assert.match(source, /font-weight:100 800/);
});

test('pending questions, jobs and delivery times are shown honestly', async () => {
  const app = await harness();
  const job = { schemaVersion: 1, project: 'hermes', runId: 'job_1', revision: 2, name: 'Test suite', version: 'job', kind: 'job',
    status: 'running', stage: 'Running tests', summary: '', progress: null, checks: [], artifacts: [], notes: '',
    updatedAt: '2026-11-12T10:00:00Z', appId: null, approval: null };
  app.setQuery({ isError: false, data: { ...emptySnapshot(), runs: [job],
    pendingQuestions: [{ interactionId: 'int_1', project: 'hermes', kind: 'yes_no', title: 'Restart workers?', deadline: 1794477600 }],
    deliveries: [{ project: 'hermes', state: 'accepted', message: 'Notify receipt recorded', at: '2026-11-12T10:00:00Z' }] } });
  const out = text(app.render());
  assert.match(out, /Pending decisions \(1\)/);
  assert.match(out, /Restart workers\?/);
  assert.match(out, /Yes or no: waiting for a phone answer/);
  assert.match(out, /hermes \/ job/);
  assert.doesNotMatch(out, /revision 2/);
  assert.match(out, /Notify is set up for this profile/);
  assert.match(out, /At /);
  const interval = app.queries.at(-1).refetchInterval;
  assert.equal(interval({ state: { status: 'success', data: { ...emptySnapshot(), pendingQuestions: [{}] } } }), 15000);
});
