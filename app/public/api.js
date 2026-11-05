import { InvalidData } from './model.js';

const BODY_LIMIT = 64 * 1024;
const REQUEST_TIMEOUT = 12_000;

export class RequestError extends Error {
  constructor(status = 0) {
    super(status ? `Request failed (${status}).` : 'The connection could not be confirmed.');
    this.status = status;
  }
}

// One queue covers session reads/writes, the auth connector, snapshots, and
// replies. A failed task does not poison subsequent tasks.
export class API {
  #tail = Promise.resolve();

  exclusive(task) {
    const result = this.#tail.then(task);
    this.#tail = result.catch(() => {});
    return result;
  }

  request(path, { method = 'GET', body } = {}) {
    return this.exclusive(async () => {
      const url = new URL(path, location.origin);
      if (url.origin !== location.origin) throw new RequestError();
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT);
      try {
        const response = await fetch(url, {
          method,
          credentials: 'same-origin',
          cache: 'no-store',
          redirect: 'error',
          headers: { Accept: 'application/json', ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
          body: body === undefined ? undefined : JSON.stringify(body),
          signal: controller.signal,
        });
        if (!response.ok) {
          await response.body?.cancel();
          throw new RequestError(response.status);
        }
        if (response.status === 204) return null;
        if (!/^application\/json(?:\s*;|$)/i.test(response.headers.get('content-type') || '')) {
          await response.body?.cancel();
          throw new InvalidData();
        }
        if (!response.body) throw new InvalidData();
        const reader = response.body.getReader();
        const chunks = [];
        let length = 0;
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          length += value.byteLength;
          if (length > BODY_LIMIT) {
            await reader.cancel();
            throw new InvalidData();
          }
          chunks.push(value);
        }
        const bytes = new Uint8Array(length);
        let offset = 0;
        for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
        try { return JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes)); }
        catch { throw new InvalidData(); }
      } catch (error) {
        if (error instanceof RequestError || error instanceof InvalidData) throw error;
        throw new RequestError();
      } finally { clearTimeout(timeout); }
    });
  }
}
