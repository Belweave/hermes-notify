import { fail } from './http.js';

export const SLUG = /^[a-z0-9][a-z0-9-]{0,63}$/;
export const ID = /^[A-Za-z0-9_-]{1,128}$/;
export const APP_ID = /^app_[A-Za-z0-9_-]{1,128}$/;
export function record(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) fail(400, 'invalid_document');
  return value;
}
export function fields(value, names) {
  record(value);
  if (Object.keys(value).length !== names.length || names.some((key) => !Object.hasOwn(value, key))) fail(400, 'invalid_fields');
}
export function string(value, max, min = 0) {
  if (typeof value !== 'string' || [...value].length < min || [...value].length > max) fail(400, 'invalid_string');
  if (/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/u.test(value)) fail(400, 'invalid_string');
}
export function id(value) { if (typeof value !== 'string' || !ID.test(value)) fail(400, 'invalid_id'); }
function choice(value, allowed) { if (!allowed.includes(value)) fail(400, 'invalid_status'); }
function integer(value) { if (!Number.isSafeInteger(value) || value < 0) fail(400, 'invalid_revision'); }
export function publication(body, project) {
  fields(body, ['operationId', 'expectedRevision', 'workspace']);
  id(body.operationId); integer(body.expectedRevision);
  const w = body.workspace;
  fields(w, ['schemaVersion', 'project', 'runId', 'revision', 'name', 'version', 'status', 'stage', 'summary', 'progress', 'checks', 'artifacts', 'notes', 'updatedAt', 'appId', 'approval']);
  if (w.schemaVersion !== 1 || w.project !== project) fail(400, 'invalid_project');
  id(w.runId); integer(w.revision);
  if (w.revision !== body.expectedRevision + 1) fail(400, 'invalid_revision');
  for (const key of ['name', 'version', 'stage']) string(w[key], 80);
  string(w.summary, 500); string(w.notes, 8000);
  choice(w.status, ['preparing', 'running', 'awaiting_approval', 'approved', 'shipped', 'denied', 'failed', 'canceled']);
  if (w.progress !== null && (typeof w.progress !== 'number' || !Number.isFinite(w.progress) || w.progress < 0 || w.progress > 1)) fail(400, 'invalid_progress');
  if (!Array.isArray(w.checks) || w.checks.length > 20 || !Array.isArray(w.artifacts) || w.artifacts.length > 20) fail(400, 'invalid_items');
  for (const check of w.checks) {
    fields(check, ['label', 'status']); string(check.label, 80);
    choice(check.status, ['pending', 'running', 'passed', 'failed']);
  }
  for (const artifact of w.artifacts) {
    fields(artifact, ['label', 'url']); string(artifact.label, 80); string(artifact.url, 2048, 1);
    let url; try { url = new URL(artifact.url); } catch { fail(400, 'invalid_artifact'); }
    if (url.protocol !== 'https:' || url.username || url.password || /[\s\\]/u.test(artifact.url)) fail(400, 'invalid_artifact');
  }
  string(w.updatedAt, 40, 1);
  if (!/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?(?:Z|[+-]\d\d:\d\d)$/.test(w.updatedAt) || !Number.isFinite(Date.parse(w.updatedAt))) fail(400, 'invalid_timestamp');
  if (w.appId !== null && (typeof w.appId !== 'string' || !APP_ID.test(w.appId))) fail(400, 'invalid_app_id');
  if (w.approval !== null) {
    fields(w.approval, ['requestId', 'digest', 'title', 'status']);
    string(w.approval.requestId, 128, 1); string(w.approval.digest, 256, 1); string(w.approval.title, 80, 1);
    choice(w.approval.status, ['pending', 'approved', 'denied', 'expired', 'canceled']);
  }
  return body;
}
export function reply(body) {
  fields(body, ['id', 'runId', 'text']); id(body.id); id(body.runId); string(body.text, 2000, 1);
  if (!body.text.trim()) fail(400, 'empty_reply');
  return body;
}
export function acknowledgement(body) {
  fields(body, ['ids']);
  if (!Array.isArray(body.ids) || body.ids.length > 100) fail(400, 'invalid_ids');
  body.ids.forEach(id);
  return [...new Set(body.ids)];
}
export function afterCursor(url) {
  const value = url.searchParams.get('after') ?? '0';
  if (!/^\d{1,16}$/.test(value) || !Number.isSafeInteger(Number(value))) fail(400, 'invalid_cursor');
  return Number(value);
}
export function webhook(body) {
  record(body); record(body.interaction);
  const i = body.interaction;
  choice(body.type, ['interaction.answered', 'interaction.expired', 'interaction.canceled']);
  id(i.id);
  if (!i.id.startsWith('int_')) fail(400, 'invalid_interaction');
  choice(i.kind, ['approval', 'yes_no', 'reply']);
  if (body.type === 'interaction.answered') {
    const statuses = { approval: ['approved', 'denied'], yes_no: ['yes', 'no'], reply: ['replied'] };
    choice(i.status, statuses[i.kind]);
    string(i.response, 8000, 1);
  } else if (i.status !== body.type.slice('interaction.'.length)) fail(400, 'invalid_status');
  return { interactionId: i.id, type: body.type,
    outcome: JSON.stringify([body.type, i.id, i.kind, i.status, i.response ?? null, i.respondedAt ?? null]) };
}
