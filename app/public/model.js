export const TERMINAL = new Set(['shipped', 'failed', 'denied', 'canceled']);
const STATUSES = new Set(['preparing', 'running', 'awaiting_approval', 'approved', ...TERMINAL]);
const CHECKS = new Set(['pending', 'running', 'passed', 'failed']);
const APPROVALS = new Set(['pending', 'approved', 'denied', 'expired', 'canceled']);
const PROJECT = /^[a-z0-9][a-z0-9-]{0,63}$/;
const ID = /^[a-zA-Z0-9_-]{1,128}$/;

export class InvalidData extends Error {
  constructor() { super('Workspace data could not be verified.'); }
}

function require(condition) {
  if (!condition) throw new InvalidData();
}

function record(value) {
  require(value !== null && typeof value === 'object' && !Array.isArray(value));
  return value;
}

function text(value, max, empty = false) {
  require(typeof value === 'string' && [...value].length <= max);
  require(empty || value.trim().length > 0);
  // Newlines and tabs are useful in notes. Other controls are never display text.
  require(!/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/u.test(value));
  return value;
}

function choice(value, choices) {
  require(choices.has(value));
  return value;
}

function integer(value, minimum) {
  require(Number.isSafeInteger(value) && value >= minimum);
  return value;
}

function appId(value) {
  require(value === null || (typeof value === 'string' && /^app_[a-zA-Z0-9_-]{1,128}$/.test(value)));
  return value;
}

export function projectFromPath(path) {
  const match = /^\/projects\/([a-z0-9][a-z0-9-]{0,63})\/?$/.exec(path);
  return match ? match[1] : null;
}

export function safeArtifactURL(value) {
  text(value, 2048);
  require(!/[\s\\]/u.test(value));
  let url;
  try { url = new URL(value); } catch { throw new InvalidData(); }
  require(url.protocol === 'https:' && !url.username && !url.password && Boolean(url.hostname));
  return url.href;
}

export function validateWorkspace(payload, project) {
  record(payload);
  const source = record(payload.workspace);
  require(source.schemaVersion === 1 && PROJECT.test(source.project) && source.project === project);
  require(typeof source.runId === 'string' && ID.test(source.runId));
  const revision = integer(source.revision, 1);
  require(payload.revision === revision);
  require(source.progress === null || (typeof source.progress === 'number' && Number.isFinite(source.progress) && source.progress >= 0 && source.progress <= 1));
  require(Array.isArray(source.checks) && source.checks.length <= 20);
  require(Array.isArray(source.artifacts) && source.artifacts.length <= 20);
  const updatedAt = text(source.updatedAt, 40);
  require(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$/.test(updatedAt) && Number.isFinite(Date.parse(updatedAt)));
  let approval = null;
  if (source.approval !== null) {
    const item = record(source.approval);
    approval = {
      requestId: text(item.requestId, 128),
      digest: text(item.digest, 256),
      title: text(item.title, 80),
      status: choice(item.status, APPROVALS),
    };
  }
  // Only this validated projection reaches the view. Unknown server properties
  // cannot become markup, attributes, storage, or an outbound destination.
  return {
    schemaVersion: 1,
    project,
    runId: source.runId,
    revision,
    name: text(source.name, 80, true),
    version: text(source.version, 80, true),
    status: choice(source.status, STATUSES),
    stage: text(source.stage, 80, true),
    summary: text(source.summary, 500, true),
    progress: source.progress,
    checks: source.checks.map((item) => {
      record(item);
      return { label: text(item.label, 80, true), status: choice(item.status, CHECKS) };
    }),
    artifacts: source.artifacts.map((item) => {
      record(item);
      return { label: text(item.label, 80, true), url: safeArtifactURL(item.url) };
    }),
    notes: text(source.notes, 8000, true),
    updatedAt,
    appId: appId(source.appId),
    approval,
  };
}

export function validateSession(payload, project) {
  record(payload);
  require(typeof payload.authenticated === 'boolean');
  if (payload.project !== undefined) require(payload.project === project);
  return payload.authenticated;
}

export function validateReceipt(payload, id) {
  record(payload);
  require(payload.id === id && payload.accepted === true);
  integer(payload.cursor, 1);
  return { id, cursor: payload.cursor, accepted: true };
}

export function decisionFor(workspace) {
  const { status, approval } = workspace;
  if (status === 'shipped') return { title: 'Release complete', body: 'Hermes recorded a successful release. The artifacts and rollback notes remain here.', tone: 'success' };
  if (status === 'failed') return { title: 'Release needs attention', body: 'Review the checks and rollback notes. Send Hermes any context needed for recovery.', tone: 'danger' };
  if (status === 'denied') return { title: 'Release denied', body: 'The requested action was denied. This run has ended. A reply can explain what should change next.', tone: 'danger' };
  if (status === 'canceled') return { title: 'Release canceled', body: 'This run has ended. Its last reported checks, notes, and artifacts are kept below.', tone: 'neutral' };
  if (approval?.status === 'pending') return { title: approval.title, body: 'Hermes is waiting for a decision in Notify. Review the exact action there before you answer.', tone: 'warning', native: true };
  if (status === 'awaiting_approval') {
    if (approval && approval.status !== 'pending') return { title: `Approval ${approval.status}`, body: 'Waiting for Hermes to report the next release state. No additional permission can be granted here.', tone: 'warning' };
    return { title: 'Waiting for native approval', body: 'Hermes has paused this release. Check Notify for the current approval request.', tone: 'warning', native: true };
  }
  if (status === 'approved') return { title: 'Approval recorded', body: 'Hermes still needs to report the release result. Approval alone does not mean this version has shipped.', tone: 'success' };
  return { title: 'No decision needed', body: status === 'preparing' ? 'Hermes is preparing this release. Checks and artifacts will appear as they are reported.' : 'Work is in progress. You can add context below while Hermes completes the release.', tone: 'neutral' };
}

export const STATUS_LABELS = {
  preparing: 'Preparing', running: 'Running', awaiting_approval: 'Awaiting approval',
  approved: 'Approved, continuing', shipped: 'Shipped', denied: 'Denied', failed: 'Failed', canceled: 'Canceled',
};
