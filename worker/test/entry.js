// This module is only bundled by the test harness, never by Wrangler or build.
import { PocketService } from '../src/service.js';
import { route } from '../src/index.js';
import { safe } from '../src/http.js';

export class TestPocketStore {
  constructor(ctx, env) {
    const jwk = JSON.parse(env.SYNTHETIC_JWKS).keys[0];
    const keys = async (header) => {
      if (header.kid !== jwk.kid) throw new Error('Unknown synthetic key');
      return crypto.subtle.importKey('jwk', jwk, { name: 'ECDSA', namedCurve: 'P-256' }, false, ['verify']);
    };
    this.service = new PocketService(ctx, { ...env }, keys);
  }
  async fetch(request) {
    if (new URL(request.url).pathname === '/__test/control') {
      const { sql, args = [], env } = await request.json();
      if (env) Object.assign(this.service.env, env);
      return Response.json(sql ? this.service.store.rows(sql, ...args) : {});
    }
    return this.service.fetch(request);
  }
  alarm() { return this.service.alarm(); }
}
export default {
  fetch(request, env) {
    if (new URL(request.url).pathname === '/__test/control') {
      return env.POCKET.get(env.POCKET.idFromName('hermes-pocket-v1')).fetch(request);
    }
    return safe(() => route(request, env));
  },
};
