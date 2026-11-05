import { API, RequestError } from './api.js';
import { InvalidData, projectFromPath, validateWorkspace, validateSession, validateReceipt, TERMINAL } from './model.js';
import { el, gate, clearPrivate, renderWorkspace, renderReply, sync } from './view.js';

const project = projectFromPath(location.pathname);
const api = new API();
const projectPath = project ? `/api/projects/${project}` : null;
const sessionPath = project ? `/auth/${project}/session` : null;
const emptyReply = () => ({ phase: 'idle', attempt: null, draftRunId: null, message: '', needsRefresh: false });
let reply = emptyReply();
let workspace = null;
let authenticated = false;
let authBusy = false;
let loading = false;
let generation = 0;
let timer = null;
let failures = 0;
let unchanged = 0;
let lastChecked = null;
let logoutUnconfirmed = false;

function stopPolling() { clearTimeout(timer); timer = null; }

function controls() {
  el('refresh').disabled = loading || reply.phase === 'pending' || authBusy;
  el('sign-out').disabled = authBusy;
  renderReply(reply, authenticated && Boolean(workspace));
}

function forgetPrivate() {
  generation += 1;
  stopPolling();
  authenticated = false;
  workspace = null;
  loading = false;
  lastChecked = null;
  failures = 0;
  unchanged = 0;
  reply = emptyReply();
  clearPrivate();
  controls();
}

function signedOut(message = 'Sign in to see this project, its release artifacts, and the current decision.') {
  forgetPrivate();
  gate({ title: 'Your release workspace', message, signin: true, hint: true });
}

function expired() { signedOut('Your sign-in has expired or access changed. Sign in again to reopen this workspace.'); }

function isAuthError(error) { return error instanceof RequestError && [401, 403].includes(error.status); }

function schedulePoll() {
  stopPolling();
  if (!authenticated || !workspace || TERMINAL.has(workspace.status) || loading || authBusy || reply.phase === 'pending' || document.hidden || !navigator.onLine || failures >= 5) return;
  const delay = Math.min(60_000, 10_000 * (2 ** (failures || Math.min(unchanged, 3))));
  timer = setTimeout(() => loadWorkspace(), delay);
}

function showFreshness() {
  if (!workspace) return;
  if (!navigator.onLine) { sync('Offline. Showing the last verified release. Reconnect to refresh.', 'error'); return; }
  if (TERMINAL.has(workspace.status)) { sync('Run ended. Automatic updates stopped.'); return; }
  const checked = new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' }).format(lastChecked);
  sync(`Checked ${checked} · auto-refresh on.`);
}

async function loadWorkspace({ manual = false } = {}) {
  if (!authenticated || loading || authBusy || reply.phase === 'pending' || (!manual && document.hidden)) return;
  stopPolling();
  if (manual) failures = 0;
  const current = generation;
  loading = true;
  controls();
  if (workspace) sync('Checking for updates…');
  try {
    const result = await api.request(projectPath);
    if (current !== generation) return;
    const next = validateWorkspace(result, project);
    if (workspace && (next.revision < workspace.revision || (next.revision === workspace.revision && JSON.stringify(next) !== JSON.stringify(workspace)))) throw new InvalidData();
    unchanged = workspace?.revision === next.revision ? unchanged + 1 : 0;
    const newRun = workspace && workspace.runId !== next.runId;
    workspace = next;
    lastChecked = new Date();
    failures = 0;
    reply.needsRefresh = false;
    if (newRun && reply.phase !== 'pending') {
      if (reply.phase === 'confirmed') {
        reply = emptyReply();
        el('reply-text').value = '';
        reply.message = 'A new release run started. You can leave a new reply.';
      } else if (el('reply-text').value.trim()) {
        reply.phase = 'stale';
        reply.message = reply.attempt
          ? 'A new run started. The earlier reply may have been saved for the previous run. Review its text before using it here.'
          : 'A new run started. Review your draft before sending it to the current run.';
      } else { reply = emptyReply(); }
    }
    renderWorkspace(workspace);
    showFreshness();
  } catch (error) {
    if (current !== generation) return;
    if (isAuthError(error)) { expired(); return; }
    failures += 1;
    let message = error instanceof InvalidData
      ? 'The workspace data could not be verified. Try refreshing.'
      : error instanceof RequestError && error.status === 404
        ? 'No release has been published for this project. Ask Hermes to publish one, then refresh this page.'
        : 'Could not reach the workspace. Check your connection and try again.';
    if (workspace) {
      message += failures >= 5 ? ' Automatic updates paused. Refresh to retry.' : ' Showing the last verified release.';
      sync(message, 'error');
    } else {
      const missing = error instanceof RequestError && error.status === 404;
      gate({ title: missing ? 'No release published' : 'Could not load this release', message, retry: true, tone: missing ? '' : 'error' });
    }
  } finally {
    if (current === generation) {
      loading = false;
      controls();
      schedulePoll();
    }
  }
}

async function openWorkspace() {
  if (!project || authBusy) return;
  const current = generation;
  authBusy = true;
  gate({ title: 'Opening workspace', message: 'Checking your sign-in…' });
  try {
    const result = await api.request(sessionPath);
    if (current !== generation) return;
    if (!validateSession(result, project)) { signedOut(); return; }
    authenticated = true;
    el('private-actions').hidden = false;
    gate({ title: 'Opening workspace', message: 'Loading the latest release…' });
  } catch (error) {
    if (current !== generation) return;
    if (isAuthError(error)) signedOut();
    else gate({ title: 'Could not check sign-in', message: 'Check your connection, then try opening this workspace again.', retry: true, tone: 'error' });
  } finally {
    authBusy = false;
    controls();
  }
  if (authenticated && current === generation) await loadWorkspace({ manual: true });
}

async function signIn() {
  if (!project || authBusy) return;
  authBusy = true;
  const current = generation;
  gate({ title: 'Continue in Notify', message: 'Complete sign-in in Notify, then return to this workspace.', hint: true });
  try {
    await api.exclusive(async () => {
      const { connect } = await import('./auth.js');
      await connect(project);
    });
    if (current !== generation) return;
    // Recheck the server cookie. The connector's return value is not authority
    // to fetch private data, and no identity pass is kept by this module.
    authenticated = validateSession(await api.request(sessionPath), project);
    if (!authenticated) throw new RequestError(401);
    el('private-actions').hidden = false;
    gate({ title: 'Opening workspace', message: 'Loading the latest release…' });
  } catch (error) {
    if (current !== generation) return;
    authenticated = false;
    const safeMessages = new Set([
      'Open this workspace in an updated Notify app on your phone to sign in.',
      'Sign-in was not completed. Check this project is registered and try again in Notify.',
      'This project link is invalid.',
    ]);
    gate({ title: 'Sign-in not completed', message: safeMessages.has(error.message) ? error.message : 'Sign-in could not be confirmed. Open this workspace in Notify and try again.', signin: true, hint: true, tone: 'error' });
  } finally {
    authBusy = false;
    controls();
  }
  if (authenticated && current === generation) await loadWorkspace({ manual: true });
}

async function signOut() {
  if (authBusy || !project) return;
  authBusy = true;
  forgetPrivate();
  gate({ title: 'Signing out', message: 'Clearing this workspace and ending your session…' });
  try {
    await api.request(sessionPath, { method: 'DELETE' });
    logoutUnconfirmed = false;
    signedOut('You are signed out. Sign in with Notify to reopen this project.');
  } catch (error) {
    if (isAuthError(error)) {
      logoutUnconfirmed = false;
      signedOut('You are signed out. Sign in with Notify to reopen this project.');
    } else {
      logoutUnconfirmed = true;
      gate({ title: 'Sign-out needs a retry', message: 'This view is cleared, but the server session could not be ended. Retry to finish signing out.', retry: true, tone: 'error' });
    }
  } finally { authBusy = false; controls(); }
}

async function sendReply(event) {
  event.preventDefault();
  if (!authenticated || !workspace || authBusy || ['pending', 'confirmed', 'stale'].includes(reply.phase)) return;
  const text = el('reply-text').value.trim();
  if (!text || text.length > 2000) return;
  if (reply.draftRunId && reply.draftRunId !== workspace.runId) return;
  stopPolling();
  if (!reply.attempt) {
    if (typeof crypto.randomUUID !== 'function') {
      reply.phase = 'error';
      reply.message = 'This browser cannot create a safe reply ID. Open the workspace in an updated browser.';
      controls();
      schedulePoll();
      return;
    }
    reply.attempt = Object.freeze({ id: crypto.randomUUID(), runId: workspace.runId, text });
  }
  const attempt = reply.attempt;
  const current = generation;
  reply.phase = 'pending';
  reply.message = 'Saving this reply. Waiting for a receipt…';
  el('reply-text').value = attempt.text;
  controls();
  let refreshAfter = false;
  try {
    const result = await api.request(`${projectPath}/replies`, { method: 'POST', body: attempt });
    if (current !== generation) return;
    validateReceipt(result, attempt.id);
    reply.phase = 'confirmed';
    reply.message = attempt.runId === workspace?.runId
      ? 'Reply saved for this run. Hermes can collect it; delivery to the task is not yet confirmed.'
      : 'Reply saved for the previous run. It was not sent to this new run. Delivery to the task is not yet confirmed.';
  } catch (error) {
    if (current !== generation) return;
    if (isAuthError(error)) { expired(); return; }
    reply.phase = 'error';
    if (error instanceof RequestError && error.status === 409) {
      reply.phase = 'stale';
      reply.needsRefresh = true;
      reply.message = 'The release or reply changed. Refresh and review this draft before sending it again.';
      refreshAfter = true;
    } else if (error instanceof RequestError && [400, 413, 422].includes(error.status)) {
      reply.attempt = null;
      reply.message = 'The reply was not accepted. Edit the text and try again.';
    } else {
      reply.message = 'Receipt not confirmed. Retry safely with the same reply ID and text.';
    }
  } finally {
    if (current === generation) {
      controls();
      if (refreshAfter) await loadWorkspace({ manual: true });
      else schedulePoll();
    }
  }
}

el('sign-in').addEventListener('click', signIn);
el('sign-out').addEventListener('click', signOut);
el('refresh').addEventListener('click', () => loadWorkspace({ manual: true }));
el('retry-open').addEventListener('click', () => {
  if (logoutUnconfirmed) signOut();
  else if (authenticated) loadWorkspace({ manual: true });
  else openWorkspace();
});
el('reply-form').addEventListener('submit', sendReply);
el('reply-text').addEventListener('input', () => {
  if (reply.attempt || reply.phase === 'stale') return;
  reply.phase = 'idle';
  reply.message = '';
  reply.draftRunId = el('reply-text').value.trim() ? workspace?.runId : null;
  controls();
});
el('new-reply').addEventListener('click', () => {
  reply = emptyReply();
  el('reply-text').value = '';
  controls();
  el('reply-text').focus();
});
el('review-reply').addEventListener('click', () => {
  if (!workspace || reply.needsRefresh) return;
  reply = { ...emptyReply(), draftRunId: workspace.runId, message: 'Review the text, then send it to the current run.' };
  controls();
  el('reply-text').focus();
});
document.addEventListener('visibilitychange', () => {
  stopPolling();
  if (!document.hidden && authenticated && !TERMINAL.has(workspace?.status)) loadWorkspace();
});
window.addEventListener('offline', () => { stopPolling(); showFreshness(); });
window.addEventListener('online', () => {
  if (authenticated && !document.hidden && !TERMINAL.has(workspace?.status)) loadWorkspace();
});
window.addEventListener('pagehide', forgetPrivate);
window.addEventListener('pageshow', (event) => { if (event.persisted) openWorkspace(); });

if (project) {
  el('project-label').textContent = `projects / ${project}`;
  openWorkspace();
} else {
  clearPrivate();
  gate({ title: 'Open a project link', message: 'Open a project workspace from Notify, or ask Hermes to publish a release and share its link.', help: true });
}
