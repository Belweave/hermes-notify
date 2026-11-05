import { fail } from './http.js';

export const LIMITS = Object.freeze({
  projects: 128, operations: 4096, responses: 256, projectResponses: 32,
  replies: 1024, projectReplies: 128, replyReceipts: 4096,
  events: 1024, eventReceipts: 4096, deliveries: 8192,
  challenges: 256, projectChallenges: 16, sessions: 128, projectSessions: 8,
  passes: 512, page: 100, replyPageBytes: 96 * 1024,
});
const encoder = new TextEncoder();
export const DAY = 86400000;
export const RETENTION = 7 * DAY;
export const SESSION_TTL = 3600;

// All multi-statement transitions run synchronously inside transactionSync.
// A single named object also bounds aggregate storage across projects.
export class Store {
  constructor(ctx) {
    this.ctx = ctx;
    this.sql = ctx.storage.sql;
    this.sql.exec(`
      CREATE TABLE IF NOT EXISTS projects (project TEXT PRIMARY KEY, revision INTEGER NOT NULL, body TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS operations (project TEXT NOT NULL, id TEXT NOT NULL, hash TEXT NOT NULL,
        response TEXT, created INTEGER NOT NULL, PRIMARY KEY(project,id));
      CREATE INDEX IF NOT EXISTS operations_age ON operations(created);
      CREATE TABLE IF NOT EXISTS replies (cursor INTEGER PRIMARY KEY AUTOINCREMENT, project TEXT NOT NULL,
        id TEXT NOT NULL, run_id TEXT NOT NULL, text TEXT, hash TEXT NOT NULL, created TEXT NOT NULL,
        acked INTEGER, UNIQUE(project,id));
      CREATE INDEX IF NOT EXISTS replies_pending ON replies(project,acked,cursor);
      CREATE TABLE IF NOT EXISTS events (cursor INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
        interaction_id TEXT NOT NULL, type TEXT NOT NULL, hash TEXT NOT NULL, acked INTEGER,
        UNIQUE(type,interaction_id));
      CREATE INDEX IF NOT EXISTS events_pending ON events(acked,cursor);
      CREATE TABLE IF NOT EXISTS deliveries (id TEXT PRIMARY KEY, hash TEXT NOT NULL, event_id TEXT NOT NULL,
        cursor INTEGER NOT NULL, expires INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS challenges (binding TEXT PRIMARY KEY, project TEXT NOT NULL, app_id TEXT NOT NULL,
        origin TEXT NOT NULL, nonce TEXT NOT NULL, expires INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, project TEXT NOT NULL, app_id TEXT NOT NULL,
        origin TEXT NOT NULL, subject TEXT NOT NULL, expires INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS passes (id TEXT PRIMARY KEY, expires INTEGER NOT NULL);
    `);
  }
  rows(query, ...args) { return [...this.sql.exec(query, ...args)]; }
  one(query, ...args) { return this.rows(query, ...args)[0] ?? null; }
  count(table, condition = '1', args = []) {
    return this.one(`SELECT count(*) AS n FROM ${table} WHERE ${condition}`, ...args).n;
  }
  tx(action) { return this.ctx.storage.transactionSync(action); }
  purge(now) {
    this.tx(() => {
      for (const table of ['challenges', 'sessions', 'passes', 'deliveries']) this.sql.exec(`DELETE FROM ${table} WHERE expires <= ?`, now);
      this.sql.exec('DELETE FROM operations WHERE created <= ?', now - RETENTION);
      this.sql.exec('DELETE FROM replies WHERE acked <= ?', now - RETENTION);
      this.sql.exec('DELETE FROM events WHERE acked <= ?', now - RETENTION);
    });
  }
  async schedule() {
    // Alarm ceases after the last expiring record, so idle projects do not poll.
    // Scalar subqueries avoid the runtime's five-term compound SELECT limit.
    const row = this.one(`SELECT
      (SELECT min(expires) FROM challenges) AS challenge,
      (SELECT min(expires) FROM sessions) AS session,
      (SELECT min(expires) FROM passes) AS pass,
      (SELECT min(expires) FROM deliveries) AS delivery,
      (SELECT min(created) + ${RETENTION} FROM operations) AS operation,
      (SELECT min(acked) + ${RETENTION} FROM replies) AS reply,
      (SELECT min(acked) + ${RETENTION} FROM events) AS event`);
    const deadlines = Object.values(row).filter((value) => value !== null);
    if (deadlines.length) await this.ctx.storage.setAlarm(Math.max(Date.now() + 1000, Math.min(...deadlines)));
    else await this.ctx.storage.deleteAlarm();
  }
  project(project) {
    const row = this.one('SELECT body FROM projects WHERE project = ?', project);
    return row ? JSON.parse(row.body) : null;
  }
  requireProject(project) {
    const w = this.project(project);
    if (!w) fail(404, 'project_not_found');
    return w;
  }
  publish(project, body, digest, now) {
    return this.tx(() => {
      const previous = this.one('SELECT hash,response FROM operations WHERE project = ? AND id = ?', project, body.operationId);
      if (previous) {
        if (previous.hash !== digest) fail(409, 'operation_conflict');
        if (previous.response === null) fail(409, 'operation_response_expired');
        return JSON.parse(previous.response);
      }
      const old = this.project(project);
      if ((old?.revision ?? 0) !== body.expectedRevision) fail(409, 'revision_conflict');
      if (!old && this.count('projects') >= LIMITS.projects) fail(503, 'project_capacity');
      if (this.count('operations') >= LIMITS.operations) fail(503, 'operation_capacity');
      const response = { workspace: body.workspace, revision: body.workspace.revision, unchanged: false };
      this.sql.exec('INSERT INTO projects(project,revision,body) VALUES(?,?,?) ON CONFLICT(project) DO UPDATE SET revision=excluded.revision, body=excluded.body', project, body.workspace.revision, JSON.stringify(body.workspace));
      this.sql.exec('INSERT INTO operations(project,id,hash,response,created) VALUES(?,?,?,?,?)', project, body.operationId, digest, JSON.stringify(response), now);
      this.sql.exec(`UPDATE operations SET response=NULL WHERE project=? AND response IS NOT NULL AND rowid NOT IN
        (SELECT rowid FROM operations WHERE project=? AND response IS NOT NULL ORDER BY rowid DESC LIMIT ?)`, project, project, LIMITS.projectResponses);
      this.sql.exec(`UPDATE operations SET response=NULL WHERE response IS NOT NULL AND rowid NOT IN
        (SELECT rowid FROM operations WHERE response IS NOT NULL ORDER BY rowid DESC LIMIT ?)`, LIMITS.responses);
      if (old && old.appId !== body.workspace.appId) {
        this.sql.exec('DELETE FROM sessions WHERE project=?', project);
        this.sql.exec('DELETE FROM challenges WHERE project=?', project);
      }
      return response;
    });
  }
  addReply(project, body, digest, now, authorize) {
    return this.tx(() => {
      authorize();
      const current = this.requireProject(project);
      const existing = this.one('SELECT cursor,hash FROM replies WHERE project=? AND id=?', project, body.id);
      if (existing) {
        if (existing.hash !== digest) fail(409, 'reply_conflict');
        return { id: body.id, cursor: existing.cursor, accepted: true };
      }
      if (current.runId !== body.runId) fail(409, 'old_run');
      if (this.count('replies', 'acked IS NULL') >= LIMITS.replies
          || this.count('replies', 'project=? AND acked IS NULL', [project]) >= LIMITS.projectReplies
          || this.count('replies') >= LIMITS.replies + LIMITS.replyReceipts) fail(503, 'reply_capacity');
      const row = this.one('INSERT INTO replies(project,id,run_id,text,hash,created) VALUES(?,?,?,?,?,?) RETURNING cursor',
        project, body.id, body.runId, body.text, digest, new Date(now).toISOString());
      return { id: body.id, cursor: row.cursor, accepted: true };
    });
  }
  listReplies(project, after) {
    this.requireProject(project);
    const rows = this.rows(`SELECT id,cursor,run_id AS runId,text,created AS createdAt FROM replies
      WHERE project=? AND acked IS NULL AND cursor>? ORDER BY cursor LIMIT ?`, project, after, LIMITS.page);
    const replies = [];
    // Leave room for the envelope and largest safe integer cursor. The Python
    // client caps responses at 128 KiB; valid long replies must still paginate.
    let bytes = 64;
    for (const row of rows) {
      const size = encoder.encode(JSON.stringify(row)).byteLength + 1;
      if (bytes + size > LIMITS.replyPageBytes) break;
      replies.push(row);
      bytes += size;
    }
    return { replies, cursor: replies.at(-1)?.cursor ?? after };
  }
  ackReplies(project, ids, now) {
    this.requireProject(project);
    return this.tx(() => {
      const targets = ids.filter((id) => this.one('SELECT id FROM replies WHERE project=? AND id=? AND acked IS NULL', project, id));
      if (this.count('replies', 'acked IS NOT NULL') + targets.length > LIMITS.replyReceipts) fail(503, 'reply_receipt_capacity');
      for (const id of targets) this.sql.exec('UPDATE replies SET acked=?,text=NULL WHERE project=? AND id=?', now, project, id);
      return { acknowledged: ids };
    });
  }
  addEvent(delivery, bodyHash, event, outcomeHash, now) {
    return this.tx(() => {
      const seen = this.one('SELECT hash,event_id,cursor FROM deliveries WHERE id=?', delivery);
      if (seen) {
        if (seen.hash !== bodyHash) fail(409, 'delivery_conflict');
        return { accepted: true, duplicate: true, id: seen.event_id, cursor: seen.cursor };
      }
      if (this.count('deliveries') >= LIMITS.deliveries) fail(503, 'delivery_capacity');
      const existing = this.one('SELECT id,cursor,hash FROM events WHERE type=? AND interaction_id=?', event.type, event.interactionId);
      if (existing && existing.hash !== outcomeHash) fail(409, 'outcome_conflict');
      if (!existing && (this.count('events', 'acked IS NULL') >= LIMITS.events
          || this.count('events') >= LIMITS.events + LIMITS.eventReceipts)) fail(503, 'event_capacity');
      const row = existing ?? this.one('INSERT INTO events(id,interaction_id,type,hash) VALUES(?,?,?,?) RETURNING id,cursor',
        `evt_${crypto.randomUUID()}`, event.interactionId, event.type, outcomeHash);
      this.sql.exec('INSERT INTO deliveries(id,hash,event_id,cursor,expires) VALUES(?,?,?,?,?)', delivery, bodyHash, row.id, row.cursor, now + RETENTION);
      return { accepted: true, duplicate: Boolean(existing), id: row.id, cursor: row.cursor };
    });
  }
  listEvents(after) {
    const events = this.rows('SELECT id,cursor,interaction_id AS interactionId,type FROM events WHERE acked IS NULL AND cursor>? ORDER BY cursor LIMIT ?', after, LIMITS.page);
    return { events, cursor: events.at(-1)?.cursor ?? after };
  }
  ackEvents(ids, now) {
    return this.tx(() => {
      const targets = ids.filter((id) => this.one('SELECT id FROM events WHERE id=? AND acked IS NULL', id));
      if (this.count('events', 'acked IS NOT NULL') + targets.length > LIMITS.eventReceipts) fail(503, 'event_receipt_capacity');
      for (const id of targets) this.sql.exec('UPDATE events SET acked=? WHERE id=?', now, id);
      return { acknowledged: ids };
    });
  }
  challengeStore(project, appId, origin, bindingHash) {
    return {
      put: async (_binding, value) => this.tx(() => {
        if (this.requireProject(project).appId !== appId) fail(409, 'app_changed');
        if (this.count('challenges') >= LIMITS.challenges
            || this.count('challenges', 'project=?', [project]) >= LIMITS.projectChallenges) fail(429, 'sign_in_capacity');
        this.sql.exec('INSERT INTO challenges(binding,project,app_id,origin,nonce,expires) VALUES(?,?,?,?,?,?)', bindingHash, project, appId, origin, value.challenge, value.expiresAt);
      }),
      get: async () => {
        const row = this.one('SELECT nonce AS challenge,expires AS expiresAt FROM challenges WHERE binding=? AND project=? AND app_id=? AND origin=?', bindingHash, project, appId, origin);
        return row;
      },
      consume: async (_binding, nonce) => this.rows('DELETE FROM challenges WHERE binding=? AND project=? AND app_id=? AND origin=? AND nonce=? AND expires>? RETURNING nonce',
        bindingHash, project, appId, origin, nonce, Date.now()).length === 1,
    };
  }
  session(tokenHash, project, origin, owner, now) {
    const row = this.one('SELECT subject,app_id FROM sessions WHERE token=? AND project=? AND origin=? AND expires>?', tokenHash, project, origin, now);
    return row && row.subject === owner && row.app_id === this.project(project)?.appId;
  }
  createSession(tokenHash, project, appId, origin, subject, jtiHash, expires, now) {
    this.tx(() => {
      if (this.requireProject(project).appId !== appId) fail(409, 'app_changed');
      if (this.one('SELECT id FROM passes WHERE id=?', jtiHash)) fail(401, 'sign_in_failed');
      if (this.count('sessions') >= LIMITS.sessions
          || this.count('sessions', 'project=?', [project]) >= LIMITS.projectSessions
          || this.count('passes') >= LIMITS.passes) fail(429, 'sign_in_capacity');
      this.sql.exec('INSERT INTO passes(id,expires) VALUES(?,?)', jtiHash, expires);
      this.sql.exec('INSERT INTO sessions(token,project,app_id,origin,subject,expires) VALUES(?,?,?,?,?,?)', tokenHash, project, appId, origin, subject, now + SESSION_TTL * 1000);
    });
  }
}
