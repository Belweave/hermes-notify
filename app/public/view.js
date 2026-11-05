import { decisionFor, STATUS_LABELS } from './model.js';

export const el = (id) => document.getElementById(id);
const set = (id, text) => { el(id).textContent = text; };

function node(tag, className, value) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (value !== undefined) element.textContent = value;
  return element;
}

export function gate({ title, message, signin = false, retry = false, hint = false, tone = '' }) {
  el('workspace').hidden = true;
  el('gate').hidden = false;
  el('gate').dataset.tone = tone;
  set('gate-title', title);
  set('gate-message', message);
  el('sign-in').hidden = !signin;
  el('sign-in').disabled = false;
  el('retry-open').hidden = !retry;
  el('auth-help').hidden = !hint;
  el('gate-hint').hidden = !hint;
}

export function clearPrivate() {
  el('workspace').hidden = true;
  el('private-actions').hidden = true;
  for (const id of ['release-name', 'release-version', 'release-status', 'release-stage', 'release-summary', 'progress-label', 'decision-title', 'decision-body', 'checks', 'check-count', 'artifacts', 'artifact-count', 'release-notes', 'revision-label', 'updated-at', 'reply-receipt', 'reply-feedback', 'sync-status']) el(id).replaceChildren();
  el('reply-text').value = '';
  el('release-progress').value = 0;
  el('updated-at').removeAttribute('datetime');
  document.title = 'Release workspace · Hermes Pocket';
}

export function renderWorkspace(workspace) {
  el('gate').hidden = true;
  el('workspace').hidden = false;
  el('private-actions').hidden = false;
  const name = workspace.name.trim() ? workspace.name : 'Release workspace';
  document.title = `${name} · Hermes Pocket`;
  set('release-name', name);
  set('release-version', workspace.version.trim() ? (/^v/i.test(workspace.version) ? workspace.version : `v${workspace.version}`) : 'Version not set');
  set('release-status', STATUS_LABELS[workspace.status]);
  el('release-status').dataset.status = workspace.status;
  set('release-stage', workspace.stage.trim() ? workspace.stage : 'Stage not reported');
  set('release-summary', workspace.summary);
  el('measurement').hidden = workspace.progress === null;
  el('progress-unmeasured').hidden = workspace.progress !== null;
  if (workspace.progress !== null) {
    // Never infer progress from checks or terminal status.
    el('release-progress').value = workspace.progress;
    set('progress-label', `${Math.round(workspace.progress * 100)}%`);
  }
  const decision = decisionFor(workspace);
  el('decision').dataset.tone = decision.tone;
  set('decision-title', decision.title);
  set('decision-body', decision.body);
  el('native-approval').hidden = !decision.native;
  el('native-hint').hidden = !decision.native;

  const symbols = { passed: '✓', failed: '×', running: '›', pending: '·' };
  const labels = { passed: 'Passed', failed: 'Failed', running: 'Running', pending: 'Pending' };
  const rows = workspace.checks.map((check) => {
    const row = node('li');
    row.dataset.status = check.status;
    const symbol = node('span', 'check-symbol', symbols[check.status]);
    symbol.setAttribute('aria-hidden', 'true');
    row.append(symbol, node('span', 'check-label', check.label.trim() ? check.label : 'Unnamed check'), node('span', 'check-state', labels[check.status]));
    return row;
  });
  el('checks').replaceChildren(...rows);
  set('check-count', workspace.checks.length ? `${workspace.checks.filter((check) => check.status === 'passed').length}/${workspace.checks.length} passed` : '');
  el('checks-empty').hidden = workspace.checks.length !== 0;
  set('release-notes', workspace.notes.trim() ? workspace.notes : 'No release or rollback notes have been published yet.');
  el('release-notes').classList.toggle('muted', !workspace.notes.trim());
  const artifacts = workspace.artifacts.map((artifact) => {
    const item = node('li');
    const link = node('a', 'artifact-link');
    link.href = artifact.url;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    const label = artifact.label.trim() ? artifact.label : 'Release artifact';
    link.setAttribute('aria-label', `${label}, ${new URL(artifact.url).hostname}, opens in a new tab`);
    const arrow = node('span', 'artifact-arrow', '↗');
    arrow.setAttribute('aria-hidden', 'true');
    link.append(node('span', 'artifact-label', label), node('span', 'artifact-host', new URL(artifact.url).hostname), arrow);
    item.append(link);
    return item;
  });
  el('artifacts').replaceChildren(...artifacts);
  set('artifact-count', workspace.artifacts.length ? `${workspace.artifacts.length} ${workspace.artifacts.length === 1 ? 'link' : 'links'}` : '');
  el('artifacts-empty').hidden = workspace.artifacts.length !== 0;
  set('revision-label', `Revision ${workspace.revision}`);
  const date = new Date(workspace.updatedAt);
  set('updated-at', `Updated ${new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZoneName: 'short' }).format(date)}`);
  el('updated-at').dateTime = workspace.updatedAt;
}

export function sync(message, tone = '') {
  set('sync-status', message);
  el('sync-status').dataset.tone = tone;
}

export function renderReply(reply, available) {
  const textarea = el('reply-text');
  const confirmed = reply.phase === 'confirmed';
  const pending = reply.phase === 'pending';
  const stale = reply.phase === 'stale';
  textarea.hidden = confirmed;
  document.querySelector('label[for="reply-text"]').hidden = confirmed;
  el('reply-limit').hidden = confirmed;
  textarea.readOnly = Boolean(reply.attempt) || stale;
  textarea.disabled = !available || pending;
  set('reply-limit', `${textarea.value.length} / 2000`);
  el('reply-receipt').hidden = !confirmed;
  set('reply-receipt', confirmed ? reply.attempt.text : '');
  el('send-reply').hidden = confirmed || stale;
  el('send-reply').disabled = !available || pending || !textarea.value.trim();
  set('send-reply', pending ? 'Saving reply…' : reply.attempt ? 'Retry reply' : 'Send reply');
  el('new-reply').hidden = !confirmed;
  el('new-reply').disabled = !available;
  el('review-reply').hidden = !stale;
  el('review-reply').disabled = !available || reply.needsRefresh;
  el('reply-form').setAttribute('aria-busy', String(pending));
  set('reply-feedback', reply.message || '');
  el('reply-feedback').dataset.tone = confirmed ? 'success' : ['error', 'stale'].includes(reply.phase) ? 'error' : '';
}
