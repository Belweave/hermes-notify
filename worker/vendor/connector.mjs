import {
  createRemoteJWKSet,
  jwtVerify
} from "./chunk-JKIZH22G.mjs";
import {
  APP_PASS_ALGORITHM,
  APP_PASS_JWKS_PATH,
  APP_PASS_JWT_TYPE,
  APP_PASS_TTL_SECONDS,
  CALLBACK_MAX_SKEW_SECONDS,
  CALLBACK_SIGNATURE_HEADER,
  CALLBACK_SIGNATURE_VERSION,
  CALLBACK_TIMESTAMP_HEADER,
  DEFAULT_RELAY_DOMAIN,
  TEAM_ROLES,
  authorizeRelayCreate,
  installRelayCreateAuth,
  isRouteName,
  relayApiOrigin,
  resolveCallbackTargetUrl,
  secureControlOrigin,
  tunnelHostname,
  tunnelOrigin
} from "./chunk-T3XQKAKJ.mjs";
import "./chunk-7P6ASYW6.mjs";

// src/runtime/node.mjs
var floors = /* @__PURE__ */ new Map([[22, [23, 4]], [24, [22, 1]], [26, [12, 1]]]);
function isSupportedNodeVersion(version) {
  if (typeof version !== "string" || !/^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/.test(version))
    return false;
  const [major, minor, patch] = version.split(".").map(Number);
  if (![major, minor, patch].every(Number.isSafeInteger)) return false;
  const minimum = floors.get(major);
  return !!minimum && (minor > minimum[0] || minor === minimum[0] && patch >= minimum[1]);
}
function assertSupportedNode(version = process.versions.node) {
  if (!isSupportedNodeVersion(version))
    throw new Error(`Node.js ${version} is unsupported. Use Node.js 22.23.4+, 24.22.1+ or 26.12.1+ within those supported major lines.`);
}

// src/connector/transport/notify.ts
async function notifyRequest(apiUrl, token, path, init, fetchImpl) {
  const response = await fetchImpl(new URL(path, apiUrl).href, {
    ...init,
    headers: {
      authorization: `Bearer ${token}`,
      accept: "application/json",
      "content-type": "application/json",
      ...init.headers ?? {}
    }
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(body.error ?? `Notify request failed (${response.status})`);
  }
  return { status: response.status, body };
}

// src/connector/transport/tunnel.ts
async function defaultTunnelFactory(options, routes, fetchImpl) {
  const runtime = await import("./tunnel-runtime-P7WIFCYW.mjs");
  return runtime.defaultTunnelFactory(options, routes, fetchImpl);
}

// src/connector/gateway.ts
import { randomBytes } from "node:crypto";
import {
  createServer,
  request as httpRequest
} from "node:http";
import { request as httpsRequest } from "node:https";

// src/connector/proxy-protocol.ts
import { Agent as HttpAgent } from "node:http";
import { Agent as HttpsAgent } from "node:https";
import { connect, isIP } from "node:net";
import { connect as connectTls } from "node:tls";
var SIGNATURE = Buffer.from("\r\n\r\n\0\r\nQUIT\n");
var MAX_V2 = 16 + 36 + 3 + 255;
function proxyHeaderLength(bytes, version) {
  if (version === "v1") {
    const prefix = Buffer.from("PROXY ");
    if (!bytes.subarray(0, Math.min(bytes.length, prefix.length)).equals(prefix.subarray(0, Math.min(bytes.length, prefix.length))))
      throw Error("Invalid PROXY signature");
    const end = bytes.indexOf("\r\n");
    if (end < 0) {
      if (bytes.length >= 107) throw Error("PROXY header too long");
      return;
    }
    if (end + 2 > 107) throw Error("PROXY header too long");
    const line = bytes.subarray(0, end).toString("ascii");
    if (!bytes.subarray(0, end).equals(Buffer.from(line))) throw Error("Invalid PROXY text");
    if (line !== "PROXY UNKNOWN") {
      const parts = line.split(" ");
      const family = parts[1] === "TCP4" ? 4 : parts[1] === "TCP6" ? 6 : 0;
      if (parts.length !== 6 || !family || isIP(parts[2] ?? "") !== family || parts[3] !== (family === 4 ? "0.0.0.0" : "::") || !/^\d{1,5}$/.test(parts[4] ?? "") || Number(parts[4]) > 65535 || parts[5] !== "443")
        throw Error("Invalid PROXY address");
    }
    return end + 2;
  }
  const signatureSize = Math.min(bytes.length, SIGNATURE.length);
  if (!bytes.subarray(0, signatureSize).equals(SIGNATURE.subarray(0, signatureSize)))
    throw Error("Invalid PROXY signature");
  if (bytes.length < 16) return;
  const size = 16 + bytes.readUInt16BE(14);
  if (size > MAX_V2) throw Error("PROXY header too long");
  const addressSize = bytes[12] === 32 && bytes[13] === 0 ? 0 : bytes[12] === 33 && bytes[13] === 17 ? 12 : bytes[12] === 33 && bytes[13] === 33 ? 36 : -1;
  if (addressSize < 0 || size < 16 + addressSize) throw Error("Invalid PROXY family");
  if (bytes.length < size) return;
  if (addressSize) {
    const ipSize = addressSize === 12 ? 4 : 16;
    if (bytes.subarray(16 + ipSize, 16 + ipSize * 2).some((byte) => byte !== 0) || bytes.readUInt16BE(16 + addressSize - 2) !== 443)
      throw Error("Invalid PROXY destination");
  }
  const tlv = 16 + addressSize;
  if (size !== tlv) {
    if (size < tlv + 3 || bytes[tlv] !== 2 || bytes.readUInt16BE(tlv + 1) < 1 || bytes.readUInt16BE(tlv + 1) > 255 || tlv + 3 + bytes.readUInt16BE(tlv + 1) !== size || !/^[a-zA-Z0-9.-]+$/.test(bytes.subarray(tlv + 3, size).toString("utf8")))
      throw Error("Invalid PROXY authority");
  }
  return size;
}
function consumeProxyHeader(socket, version, ready) {
  let pending = Buffer.alloc(0);
  const timer = setTimeout(() => socket.destroy(), 5e3);
  timer.unref();
  const cleanup = () => {
    clearTimeout(timer);
    socket.off("data", onData);
    socket.off("close", cleanup);
  };
  const onData = (chunk) => {
    const take = Math.min(chunk.length, MAX_V2 - pending.length);
    const candidate = Buffer.concat([pending, chunk.subarray(0, take)]);
    try {
      const size = proxyHeaderLength(candidate, version);
      if (size === void 0) {
        pending = candidate;
        if (take < chunk.length || pending.length >= MAX_V2) throw Error("PROXY header too long");
        return;
      }
      socket.pause();
      cleanup();
      const rest = Buffer.concat([candidate.subarray(size), chunk.subarray(take)]);
      if (rest.length) socket.unshift(rest);
      ready(Buffer.from(candidate.subarray(0, size)));
      socket.resume();
    } catch {
      cleanup();
      socket.destroy();
    }
  };
  socket.on("data", onData);
  socket.once("close", cleanup);
}
function proxyUpstreamAgent(target, header) {
  const secure = target.protocol === "https:";
  const agent = secure ? new HttpsAgent({ keepAlive: false }) : new HttpAgent({ keepAlive: false });
  agent.createConnection = (_options, callback) => {
    const host = target.hostname.replace(/^\[|\]$/g, "");
    const socket = connect({ host, port: Number(target.port || (secure ? 443 : 80)) });
    let settled = false;
    const finish = (error, stream) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      if (error) socket.destroy();
      callback?.(error, stream ?? socket);
    };
    const timer = setTimeout(() => finish(Error("Upstream connection timed out")), 5e3);
    timer.unref();
    socket.once("error", (error) => finish(error));
    socket.once("connect", () => {
      socket.write(header, (error) => {
        if (error) return finish(error);
        if (!secure) return finish(null, socket);
        const tls = connectTls({ socket, host, servername: isIP(host) ? void 0 : host });
        tls.once("error", (error2) => finish(error2));
        tls.once("secureConnect", () => finish(null, tls));
      });
    });
    return void 0;
  };
  return agent;
}

// src/connector/gateway.ts
var COOKIE = "__Host-notify_session";
var EXCHANGE = "/.notify/session";
var CALLBACK = "/.notify/callback";
var MAX_SESSIONS = 1024;
var FORWARDING_HEADERS = /* @__PURE__ */ new Set([
  "forwarded",
  "via",
  "x-real-ip",
  "client-ip",
  "x-client-ip",
  "x-cluster-client-ip",
  "x-originating-ip",
  "x-remote-ip",
  "x-remote-addr",
  "true-client-ip",
  "cf-connecting-ip"
]);
var FORWARDING_PREFIXES = ["x-forwarded-", "x-original-forwarded-", "cf-"];
function signInPage(nonce) {
  return `<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Connect with Notify</title></head><body><main><h1>Connect with Notify</h1><p>This app requires your Notify identity. Continue to share your app-specific identity and current workspace membership with this service.</p><button id="connect">Connect with Notify</button><p id="status" role="status"></p></main><script nonce="${nonce}">document.getElementById('connect').onclick=async function(){this.disabled=true;try{if(!window.notify||typeof window.notify.getToken!=='function')throw Error('Open this app inside Notify to connect.');const pass=await window.notify.getToken();const r=await fetch('${EXCHANGE}',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pass}),credentials:'same-origin'});if(!r.ok)throw Error('Access could not be verified. Reopen the app in Notify and try again.');location.reload();}catch(e){document.getElementById('status').textContent=e.message;this.disabled=false;}};</script></body></html>`;
}
function parseTarget(value) {
  const target = new URL(value.includes("://") ? value : `http://${value}`);
  if (!["http:", "https:"].includes(target.protocol) || target.username || target.password || target.pathname !== "/" || target.search || target.hash) {
    throw new Error("Connector targets must be HTTP(S) origins or host:port");
  }
  return target;
}
function cookieSession(req) {
  const values = (req.headers.cookie ?? "").split(";").map((s) => s.trim()).filter((s) => s.startsWith(`${COOKIE}=`));
  if (values.length !== 1) return void 0;
  const value = values[0]?.slice(COOKIE.length + 1) ?? "";
  return /^[A-Za-z0-9_-]{43}$/.test(value) ? value : void 0;
}
function cleanHeaders(req, target, origin, identity, upgrade) {
  const headers = {};
  const hop = /* @__PURE__ */ new Set([
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
    ...(req.headers.connection ?? "").toLowerCase().split(",").map((s) => s.trim())
  ]);
  for (const [key, value] of Object.entries(req.headers)) {
    if (hop.has(key) || key.startsWith("x-notify-") || FORWARDING_HEADERS.has(key) || FORWARDING_PREFIXES.some((prefix) => key.startsWith(prefix)) || ["authorization", "host", "cookie"].includes(key))
      continue;
    headers[key] = value;
  }
  const cookies = (req.headers.cookie ?? "").split(";").map((s) => s.trim()).filter((s) => s && !s.startsWith("__Host-notify_") && !s.startsWith("notify_"));
  if (cookies.length) headers.cookie = cookies.join("; ");
  headers.host = target.host;
  headers["x-forwarded-host"] = origin.host;
  headers["x-forwarded-proto"] = "https";
  headers["x-notify-subject"] = identity.subject;
  headers["x-notify-app-id"] = identity.appId;
  if (identity.teamId) headers["x-notify-team-id"] = identity.teamId;
  if (identity.teamRole) headers["x-notify-team-role"] = identity.teamRole;
  if (upgrade) {
    headers.connection = "Upgrade";
    headers.upgrade = "websocket";
  }
  return headers;
}
function validateIdentity(value) {
  if (!value || typeof value.subject !== "string" || !value.subject || typeof value.appId !== "string" || !value.appId || !Number.isSafeInteger(value.expiresAt) || value.expiresAt <= Date.now() / 1e3 || ![value.subject, value.appId, value.teamId ?? "", value.teamRole ?? ""].every(
    (s) => typeof s === "string" && !/[\r\n]/.test(s)
  ))
    throw new Error("Access denied");
  return value;
}
async function createAccessGateway(options) {
  const target = parseTarget(options.target);
  if (options.proxyProtocol !== void 0 && options.proxyProtocol !== "v1" && options.proxyProtocol !== "v2")
    throw Error("Invalid proxyProtocol");
  const proxyHeaders = /* @__PURE__ */ new WeakMap();
  const upstreamAgent = (req) => {
    if (!options.proxyProtocol) return void 0;
    const header = proxyHeaders.get(req.socket);
    if (!header) throw Error("Missing verified PROXY header");
    return proxyUpstreamAgent(target, header);
  };
  const sessions = /* @__PURE__ */ new Map();
  let pendingExchanges = 0;
  let nextSessionSweep = 0;
  const pruneSessions = (force = false) => {
    const now = Date.now();
    if (!force && now < nextSessionSweep) return;
    nextSessionSweep = now + 5e3;
    for (const [id, session] of sessions)
      if (session.identity.expiresAt <= now / 1e3) sessions.delete(id);
  };
  const sockets = /* @__PURE__ */ new Set();
  let origin;
  const authorize = async (pass, consume) => validateIdentity(await options.authorize(pass, consume));
  const revalidate = (session) => {
    if (session.invalidated || session.identity.expiresAt <= Date.now() / 1e3)
      return Promise.reject(new Error("Access denied"));
    if (session.checking) return session.checking;
    session.checking = authorize(session.pass, false).then((next) => {
      if (session.invalidated || session.identity.expiresAt <= Date.now() / 1e3 || next.subject !== session.identity.subject || next.appId !== session.identity.appId || next.teamId !== session.identity.teamId || next.teamRole !== session.identity.teamRole || next.expiresAt > session.identity.expiresAt)
        throw new Error("Access denied");
    }).catch(() => {
      session.invalidated = true;
      throw new Error("Access denied");
    }).finally(() => {
      session.checking = void 0;
    });
    return session.checking;
  };
  const getSession = async (req) => {
    pruneSessions();
    if (!origin || req.headers.host !== origin.host) throw new Error("Access denied");
    const id = cookieSession(req);
    const session = id ? sessions.get(id) : void 0;
    if (!session) throw new Error("Access denied");
    try {
      await revalidate(session);
      return session;
    } catch {
      if (id) sessions.delete(id);
      throw new Error("Access denied");
    }
  };
  const watched = /* @__PURE__ */ new Map();
  const watch = (session, stream) => {
    let state = watched.get(session);
    if (!state) {
      const streams = /* @__PURE__ */ new Set();
      const destroy = () => {
        for (const { stream: active } of streams) active.destroy();
      };
      state = {
        streams,
        expiry: setTimeout(destroy, Math.max(0, session.identity.expiresAt * 1e3 - Date.now())),
        timer: setInterval(
          () => {
            void revalidate(session).catch(destroy);
          },
          Math.min(options.recheckMs ?? 15e3, 15e3)
        )
      };
      state.expiry.unref();
      state.timer.unref();
      watched.set(session, state);
    }
    const entry = state;
    const subscription = { stream };
    entry.streams.add(subscription);
    const cleanup = () => {
      stream.off("close", cleanup);
      if (!entry.streams.delete(subscription)) return;
      if (entry.streams.size === 0) {
        clearTimeout(entry.expiry);
        clearInterval(entry.timer);
        watched.delete(session);
      }
    };
    stream.once("close", cleanup);
    return cleanup;
  };
  const server = createServer((req, res) => {
    void handleRequest(req, res).catch(() => {
      console.error("Connector request failed");
      if (!res.headersSent) res.writeHead(502).end("Connector error");
      else res.destroy();
    });
  });
  const handleRequest = async (req, res) => {
    res.setHeader("cache-control", "no-store");
    res.setHeader("referrer-policy", "no-referrer");
    res.setHeader("x-content-type-options", "nosniff");
    res.setHeader("x-frame-options", "SAMEORIGIN");
    res.setHeader("strict-transport-security", "max-age=31536000");
    if (!origin || req.headers.host !== origin.host) {
      res.writeHead(503).end("Connector unavailable");
      return;
    }
    const isDocumentNavigation = ["GET", "HEAD"].includes(req.method ?? "") && (!req.headers["sec-fetch-dest"] || req.headers["sec-fetch-dest"] === "document") && (req.headers.accept ?? "").includes("text/html");
    if (req.headers.origin && req.headers.origin !== origin.origin || !isDocumentNavigation && ["same-site", "cross-site"].includes(String(req.headers["sec-fetch-site"]))) {
      res.writeHead(403).end("Cross-origin access denied");
      return;
    }
    if (!req.url?.startsWith("/") || req.url.startsWith("//")) {
      res.writeHead(400).end();
      return;
    }
    const path = req.url.split("?")[0];
    if (path === CALLBACK) {
      const timestamp = req.headers[CALLBACK_TIMESTAMP_HEADER];
      const signature = req.headers[CALLBACK_SIGNATURE_HEADER];
      if (req.url !== CALLBACK || req.method !== "POST" || req.headers.origin !== void 0 || req.headers["content-type"]?.split(";")[0] !== "application/json" || req.headers["content-encoding"] || typeof timestamp !== "string" || !/^\d{10,16}$/.test(timestamp) || typeof signature !== "string" || !/^v1=[a-f0-9]{64}$/i.test(signature) || req.headers.authorization !== void 0 || !options.authorizeCallback) {
        res.writeHead(403).end("Callback access denied");
        return;
      }
      try {
        const chunks = [];
        let size = 0;
        for await (const chunk of req) {
          const bytes2 = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
          size += bytes2.length;
          if (size > 65536) throw new Error("Callback body too large");
          chunks.push(bytes2);
        }
        const bytes = Buffer.concat(chunks);
        const body = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
        const json = JSON.parse(body);
        if (!json || typeof json !== "object" || Array.isArray(json))
          throw new Error("Invalid callback body");
        const approved = await options.authorizeCallback({ body, timestamp, signature });
        if (!approved || typeof approved.path !== "string" || approved.path.length > 2048 || !/^\/[A-Za-z0-9._~!$&'()*+,;=:@%/-]*$/.test(approved.path) || approved.path.startsWith("//")) {
          throw new Error("Invalid callback destination");
        }
        const headers = {
          host: target.host,
          "content-type": "application/json",
          "content-length": bytes.length,
          [CALLBACK_TIMESTAMP_HEADER]: timestamp,
          [CALLBACK_SIGNATURE_HEADER]: signature
        };
        const upstream2 = (target.protocol === "https:" ? httpsRequest : httpRequest)(
          {
            hostname: target.hostname,
            agent: upstreamAgent(req),
            port: target.port,
            method: "POST",
            path: approved.path,
            headers,
            signal: AbortSignal.timeout(5e3)
          },
          (response) => {
            const delivered = (response.statusCode ?? 500) >= 200 && (response.statusCode ?? 500) < 300;
            response.destroy();
            res.writeHead(delivered ? 204 : 502).end();
          }
        );
        upstream2.on("error", () => {
          if (!res.headersSent) res.writeHead(502).end("Callback delivery failed");
        });
        res.once("close", () => upstream2.destroy());
        upstream2.end(bytes);
      } catch {
        res.writeHead(401).end("Callback access denied");
      }
      return;
    }
    if (path === EXCHANGE) {
      if (req.method !== "POST" || req.headers.origin !== origin.origin || req.headers["content-type"]?.split(";")[0] !== "application/json") {
        res.writeHead(403).end();
        return;
      }
      let reserved = false;
      try {
        let body = "";
        for await (const chunk of req) {
          body += chunk.toString();
          if (Buffer.byteLength(body) > 16384) throw new Error("Too large");
        }
        const { pass } = JSON.parse(body);
        if (typeof pass !== "string" || pass.length > 12e3) throw new Error("Invalid pass");
        pruneSessions(true);
        if (sessions.size + pendingExchanges >= MAX_SESSIONS) {
          res.setHeader("retry-after", "5");
          res.writeHead(503).end("Connector session capacity reached");
          return;
        }
        pendingExchanges++;
        reserved = true;
        const identity = await authorize(pass, true);
        const id = randomBytes(32).toString("base64url");
        sessions.set(id, { pass, identity });
        res.setHeader(
          "set-cookie",
          `${COOKIE}=${id}; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=${Math.max(0, Math.floor(identity.expiresAt - Date.now() / 1e3))}`
        );
        res.writeHead(204).end();
      } catch {
        res.writeHead(401).end("Access denied");
      } finally {
        if (reserved) pendingExchanges--;
      }
      return;
    }
    if (!["GET", "HEAD", "OPTIONS"].includes(req.method ?? "") && req.headers.origin !== origin.origin) {
      res.writeHead(403).end();
      return;
    }
    let session;
    try {
      session = await getSession(req);
    } catch {
      if (req.method === "GET" && isDocumentNavigation) {
        const nonce = randomBytes(18).toString("base64url");
        res.setHeader(
          "content-security-policy",
          `default-src 'none'; script-src 'nonce-${nonce}'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'`
        );
        res.setHeader("content-type", "text/html; charset=utf-8");
        res.writeHead(401).end(signInPage(nonce));
      } else res.writeHead(401).end("Access denied");
      return;
    }
    const upstream = (target.protocol === "https:" ? httpsRequest : httpRequest)(
      {
        hostname: target.hostname,
        agent: upstreamAgent(req),
        port: target.port,
        path: req.url,
        method: req.method,
        headers: cleanHeaders(req, target, origin, session.identity, false)
      },
      (response) => {
        let failed = false;
        const fail = () => {
          if (failed) return;
          failed = true;
          console.error("Connector upstream response failed");
          if (!res.headersSent) res.writeHead(502).end("Connector error");
          else res.destroy();
          response.destroy();
        };
        response.once("aborted", fail);
        response.once("error", fail);
        try {
          const headers = { ...response.headers, "cache-control": "no-store" };
          const csp = response.headers["content-security-policy"];
          const hasFrameAncestors = /(?:^|;)\s*frame-ancestors(?:\s|$)/i.test(
            Array.isArray(csp) ? csp.join(";") : csp ?? ""
          );
          res.removeHeader("x-frame-options");
          if (headers["x-frame-options"] === void 0 && !hasFrameAncestors)
            headers["x-frame-options"] = "SAMEORIGIN";
          if (headers["strict-transport-security"] === void 0)
            headers["strict-transport-security"] = "max-age=31536000";
          delete headers["set-cookie"];
          const cookies = response.headers["set-cookie"]?.filter(
            (s) => !/^\s*(?:__Host-notify_|notify_)/i.test(s)
          );
          if (cookies?.length) headers["set-cookie"] = cookies;
          res.writeHead(response.statusCode ?? 502, headers);
          response.pipe(res);
        } catch {
          fail();
        }
      }
    );
    upstream.on("error", () => {
      if (!res.headersSent) res.writeHead(502).end("Upstream unavailable");
      else res.destroy();
    });
    const stopWatch = watch(session, req.socket);
    res.once("close", () => {
      stopWatch();
      upstream.destroy();
    });
    req.pipe(upstream);
  };
  server.on("upgrade", (req, socket, head) => {
    void handleUpgrade(req, socket, head).catch(() => {
      console.error("Connector WebSocket upgrade failed");
      if (!socket.destroyed)
        socket.end("HTTP/1.1 502 Bad Gateway\r\nConnection: close\r\n\r\n", () => socket.destroy());
    });
  });
  const handleUpgrade = async (req, socket, head) => {
    socket.on("error", () => socket.destroy());
    if (!origin || req.headers.host !== origin.host || req.headers.origin !== origin.origin || req.headers.upgrade?.toLowerCase() !== "websocket" || !req.url?.startsWith("/") || req.url.startsWith("//") || [EXCHANGE, CALLBACK].includes(req.url.split("?")[0] ?? "")) {
      socket.end("HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n");
      return;
    }
    let session;
    try {
      session = await getSession(req);
    } catch {
      socket.end("HTTP/1.1 401 Unauthorized\r\nConnection: close\r\n\r\n");
      return;
    }
    if (socket.destroyed) return;
    watch(session, socket);
    const upstream = (target.protocol === "https:" ? httpsRequest : httpRequest)({
      hostname: target.hostname,
      agent: upstreamAgent(req),
      port: target.port,
      method: "GET",
      path: req.url,
      headers: cleanHeaders(req, target, origin, session.identity, true)
    });
    upstream.on("upgrade", (response, remote, remoteHead) => {
      if (socket.destroyed || session.identity.expiresAt <= Date.now() / 1e3) {
        remote.destroy();
        socket.destroy();
        return;
      }
      remote.on("error", () => socket.destroy());
      socket.once("close", () => remote.destroy());
      remote.once("close", () => socket.destroy());
      const safe = Object.entries(response.headers).filter(
        ([name]) => [
          "upgrade",
          "connection",
          "sec-websocket-accept",
          "sec-websocket-protocol",
          "sec-websocket-extensions"
        ].includes(name)
      );
      socket.write(
        `HTTP/1.1 101 Switching Protocols\r
${safe.map(([k, v]) => `${k}: ${v}`).join("\r\n")}\r
\r
`
      );
      if (remoteHead.length) socket.write(remoteHead);
      if (head.length) remote.write(head);
      remote.pipe(socket);
      socket.pipe(remote);
    });
    upstream.on("response", (response) => {
      response.resume();
      socket.end("HTTP/1.1 502 Bad Gateway\r\nConnection: close\r\n\r\n");
    });
    upstream.on("error", () => socket.destroy());
    socket.once("close", () => upstream.destroy());
    upstream.end();
  };
  const proxyProtocol = options.proxyProtocol;
  if (proxyProtocol) {
    const httpListeners = server.listeners("connection");
    server.removeAllListeners("connection");
    server.on("connection", (socket) => {
      socket.on("error", () => socket.destroy());
      consumeProxyHeader(socket, proxyProtocol, (header) => {
        proxyHeaders.set(socket, header);
        for (const listener of httpListeners) listener.call(server, socket);
      });
    });
  }
  server.on("connection", (socket) => {
    sockets.add(socket);
    socket.once("close", () => sockets.delete(socket));
  });
  server.maxConnections = 256;
  server.headersTimeout = 1e4;
  server.requestTimeout = 3e4;
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });
  const address = server.address();
  if (!address || typeof address === "string") throw new Error("Gateway failed to listen");
  return {
    target: `127.0.0.1:${address.port}`,
    setOrigin: (value) => {
      const parsed = new URL(value);
      if (parsed.protocol !== "https:" || parsed.origin !== value)
        throw new Error("Route requires an exact HTTPS origin");
      origin = parsed;
    },
    close: async () => {
      sessions.clear();
      for (const socket of sockets) socket.destroy();
      await new Promise((resolve) => server.close(() => resolve()));
    }
  };
}

// src/connector/lifecycle.ts
var DEFAULT_API = "https://notify.belweave.ai";
async function connectInternal(options) {
  assertSupportedNode();
  for (const name of Object.keys(options.routes)) {
    if (!isRouteName(name)) {
      throw new Error(`Invalid route name: ${name}`);
    }
  }
  const fetchImpl = options.fetch ?? globalThis.fetch;
  const warn = options.onWarning ?? ((message) => console.warn(message));
  const apiUrl = `${(options.apiUrl ?? DEFAULT_API).replace(/\/$/, "")}/`;
  secureControlOrigin(apiUrl);
  if (options.relayApi) secureControlOrigin(options.relayApi);
  const domain = options.relayDomain ?? DEFAULT_RELAY_DOMAIN;
  const factory = options.tunnel ?? {
    connect: (routes, nextFetch) => defaultTunnelFactory(options, routes, nextFetch)
  };
  const gateways = [];
  let connectorId;
  let session;
  try {
    const protectedRoutes = {};
    for (const [routeName, value] of Object.entries(options.routes)) {
      const { target, proxyProtocol } = typeof value === "string" ? { target: value } : value;
      if (typeof target !== "string" || proxyProtocol !== void 0 && proxyProtocol !== "v1" && proxyProtocol !== "v2") {
        throw new Error("Routes require a target and optional proxyProtocol v1 or v2");
      }
      const gateway = await createAccessGateway({
        target,
        proxyProtocol,
        routeName,
        authorizeCallback: async (input) => {
          if (!connectorId) throw new Error("Connector is not ready");
          const result = await notifyRequest(
            apiUrl,
            options.token,
            `/api/agent/connectors/${connectorId}/callback-access`,
            {
              method: "POST",
              body: JSON.stringify({ routeName, ...input }),
              signal: AbortSignal.timeout(5e3)
            },
            fetchImpl
          );
          return result.body;
        },
        authorize: async (pass, consume) => {
          if (!connectorId) throw new Error("Connector is not ready");
          const result = await notifyRequest(
            apiUrl,
            options.token,
            `/api/agent/connectors/${connectorId}/access`,
            {
              method: "POST",
              body: JSON.stringify({ routeName, pass, consume }),
              signal: AbortSignal.timeout(5e3)
            },
            fetchImpl
          );
          return result.body.identity;
        }
      });
      gateways.push(gateway);
      protectedRoutes[routeName] = proxyProtocol ? { target: gateway.target, proxyProtocol } : gateway.target;
    }
    const activeSession = await factory.connect(protectedRoutes, fetchImpl);
    session = activeSession;
    const hostname = activeSession.hostname.replace(/\.$/, "");
    const declared = Object.entries(options.routes).map(([name, target]) => ({
      name,
      target: typeof target === "string" ? target : target.target,
      url: tunnelOrigin(activeSession.id, name, domain)
    }));
    const created = await notifyRequest(
      apiUrl,
      options.token,
      "/api/agent/connectors",
      {
        method: "POST",
        body: JSON.stringify({
          name: options.name,
          tunnelId: activeSession.id,
          hostname,
          routes: declared,
          ...options.teamId ? { teamId: options.teamId } : {},
          ...options.oncallGroupId ? { oncallGroupId: options.oncallGroupId } : {}
        })
      },
      fetchImpl
    );
    connectorId = created.body.connector.id;
    gateways.forEach((gateway, index) => {
      const route = declared[index];
      if (!route) throw new Error("Missing gateway route");
      gateway.setOrigin(route.url);
    });
    const routes = [...created.body.connector.routes];
    if (options.registerApps !== false) {
      for (const route of routes) {
        try {
          const app = await notifyRequest(
            apiUrl,
            options.token,
            "/api/agent/apps",
            {
              method: "POST",
              body: JSON.stringify({
                name: route.name === "@" ? options.name : `${options.name} / ${route.name}`,
                url: route.url,
                ...options.teamId ? { teamId: options.teamId } : {}
              })
            },
            fetchImpl
          );
          route.appId = app.body.app.id;
        } catch {
          warn(`Could not register Notify app for route ${route.name}; access remains denied.`);
        }
      }
      if (routes.some((route) => route.appId)) {
        try {
          await notifyRequest(
            apiUrl,
            options.token,
            `/api/agent/connectors/${created.body.connector.id}`,
            { method: "PATCH", body: JSON.stringify({ routes }) },
            fetchImpl
          );
        } catch (error) {
          warn(
            `Could not save app ids on connector ${created.body.connector.id}: ${error instanceof Error ? error.message : String(error)}`
          );
        }
      }
    }
    const heartbeatMs = options.heartbeatMs ?? 3e4;
    let heartbeat;
    const timer = setInterval(() => {
      if (heartbeat) return;
      heartbeat = notifyRequest(
        apiUrl,
        options.token,
        `/api/agent/connectors/${created.body.connector.id}/heartbeat`,
        {
          method: "POST",
          // Registration saves metadata; heartbeats report liveness only.
          body: JSON.stringify({ status: "online" }),
          signal: AbortSignal.timeout(5e3)
        },
        fetchImpl
      ).then(
        () => void 0,
        () => void 0
      ).finally(() => {
        heartbeat = void 0;
      });
    }, heartbeatMs);
    timer.unref();
    let shutdown;
    const close = () => shutdown ??= (async () => {
      clearInterval(timer);
      await heartbeat;
      await notifyRequest(
        apiUrl,
        options.token,
        `/api/agent/connectors/${created.body.connector.id}/heartbeat`,
        {
          method: "POST",
          body: JSON.stringify({ status: "offline", graceful: true }),
          signal: AbortSignal.timeout(5e3)
        },
        fetchImpl
      ).catch(() => void 0);
      try {
        await activeSession.close();
      } finally {
        await Promise.all(gateways.map((gateway) => gateway.close()));
      }
    })();
    return {
      connector: { ...created.body.connector, routes },
      callbackSecret: created.body.callbackSecret,
      reused: created.body.reused === true || created.status === 200,
      routes,
      close,
      removeTunnel: async () => {
        await close();
        if (!activeSession.remove)
          throw new Error("This tunnel factory does not support explicit removal");
        await activeSession.remove();
      }
    };
  } catch (error) {
    await session?.close().catch(() => void 0);
    await Promise.all(gateways.map((gateway) => gateway.close()));
    throw error;
  }
}

// src/connector/command.ts
async function runConnect(input) {
  if (!isRouteName(input.name)) {
    throw new Error("--name must be a DNS label or @");
  }
  const target = `${input.host ?? "127.0.0.1"}:${input.port}`;
  const handle = await connectInternal({
    token: input.token,
    apiUrl: input.apiUrl,
    name: input.name,
    routes: { [input.name]: input.proxyProtocol ? { target, proxyProtocol: input.proxyProtocol } : target },
    teamId: input.teamId,
    oncallGroupId: input.oncallGroupId,
    relayDomain: input.relayDomain,
    fetch: input.fetch,
    tunnel: input.tunnel
  });
  const closed = new Promise((resolve) => {
    if (!input.signal) return;
    if (input.signal.aborted) {
      void handle.close().then(resolve);
      return;
    }
    input.signal.addEventListener(
      "abort",
      () => {
        void handle.close().then(resolve);
      },
      { once: true }
    );
  });
  if (input.signal) await closed;
  return {
    body: {
      connector: handle.connector,
      routes: handle.routes,
      callbackSecret: handle.callbackSecret,
      reused: handle.reused
    },
    exitCode: 0
  };
}

// src/connector/callbacks/signature.ts
import { createHmac, timingSafeEqual } from "node:crypto";
function signCallbackBody(secret, timestamp, body) {
  return createHmac("sha256", secret).update(`${timestamp}.${body}`, "utf8").digest("hex");
}
function verifyCallbackSignature(input) {
  if (!input.timestamp || !input.signature) return false;
  if (!/^\d{10,16}$/.test(input.timestamp)) return false;
  const prefix = `${CALLBACK_SIGNATURE_VERSION}=`;
  if (!input.signature.startsWith(prefix)) return false;
  if (!/^[a-fA-F0-9]{64}$/.test(input.signature.slice(prefix.length))) return false;
  const expected = signCallbackBody(input.secret, input.timestamp, input.body);
  const expectedBuf = Buffer.from(expected, "hex");
  const providedBuf = Buffer.from(input.signature.slice(prefix.length), "hex");
  if (expectedBuf.length === 0 || expectedBuf.length !== providedBuf.length) return false;
  if (!timingSafeEqual(expectedBuf, providedBuf)) return false;
  const nowSec = Math.floor((input.now ?? Date.now()) / 1e3);
  const skew = input.maxSkewSeconds ?? CALLBACK_MAX_SKEW_SECONDS;
  const age = nowSec - Number(input.timestamp);
  return age >= 0 && age <= skew;
}

// src/connector/passes/verification.ts
var jwksCache = /* @__PURE__ */ new Map();
function jwks(issuer) {
  const url = `${issuer}${APP_PASS_JWKS_PATH}`;
  let keys = jwksCache.get(url);
  if (!keys) {
    keys = createRemoteJWKSet(new URL(url));
    jwksCache.set(url, keys);
  }
  return keys;
}
async function verifyNotifyPass(token, options) {
  const issuer = (options.issuer ?? "https://notify.belweave.ai").replace(/\/$/, "");
  const issuerUrl = new URL(issuer);
  if (issuerUrl.origin !== issuer || issuerUrl.username || issuerUrl.password || issuerUrl.protocol !== "https:" && !(issuerUrl.protocol === "http:" && ["127.0.0.1", "[::1]"].includes(issuerUrl.hostname))) {
    throw new Error(
      "Notify issuer must be an exact HTTPS origin (HTTP loopback is allowed for local tests)"
    );
  }
  const { payload, protectedHeader } = await jwtVerify(token, jwks(issuer), {
    issuer,
    audience: options.audience,
    algorithms: [APP_PASS_ALGORITHM],
    requiredClaims: ["exp", "iat", "sub", "jti", "app_id"]
  });
  if (protectedHeader.typ !== APP_PASS_JWT_TYPE) {
    throw new Error("Invalid Notify pass type");
  }
  if (payload.aud !== options.audience || new URL(options.audience).origin !== options.audience || typeof payload.sub !== "string" || !payload.sub || typeof payload.jti !== "string" || !payload.jti || typeof payload.app_id !== "string" || !payload.app_id || typeof payload.exp !== "number" || !Number.isSafeInteger(payload.exp) || typeof payload.iat !== "number" || !Number.isSafeInteger(payload.iat) || payload.iat > Math.floor(Date.now() / 1e3) || payload.exp <= payload.iat || payload.exp - payload.iat > APP_PASS_TTL_SECONDS || payload.team_id === void 0 && payload.team_role !== void 0 || options.appId !== void 0 && payload.app_id !== options.appId || options.teamId !== void 0 && (payload.team_id ?? null) !== options.teamId || payload.team_id !== void 0 && (typeof payload.team_id !== "string" || !payload.team_id || typeof payload.team_role !== "string" || !TEAM_ROLES.includes(payload.team_role))) {
    throw new Error("Invalid Notify pass claims");
  }
  return payload;
}

// src/connector/passes/http.ts
async function consumePass(token, options) {
  if (typeof options.consumeJti !== "function") throw new Error("Durable replay store required");
  const claims = await verifyNotifyPass(token, options);
  const key = `${claims.iss}:${claims.jti}`;
  if (!await options.consumeJti(key, claims.exp)) throw new Error("Pass already used");
  return claims;
}
function bearer(authorization) {
  const match = authorization?.match(/^Bearer\s+(\S+)$/i);
  return match?.[1];
}
function honoNotifyPass(options) {
  return async (c, next) => {
    const token = bearer(c.req.header("authorization"));
    if (!token) return Response.json({ error: "Unauthorized" }, { status: 401 });
    try {
      c.set("pass", await consumePass(token, options));
    } catch {
      return Response.json({ error: "Unauthorized" }, { status: 401 });
    }
    await next();
  };
}
function expressNotifyPass(options) {
  return async (req, res, next) => {
    const token = bearer(req.headers.authorization);
    if (!token) {
      res.status(401).json({ error: "Unauthorized" });
      return;
    }
    try {
      req.pass = await consumePass(token, options);
    } catch {
      res.status(401).json({ error: "Unauthorized" });
      return;
    }
    next();
  };
}
function fastifyNotifyPass(options) {
  return async (request, reply) => {
    const token = bearer(request.headers.authorization);
    if (!token) {
      return reply.code(401).send({ error: "Unauthorized" });
    }
    try {
      request.pass = await consumePass(token, options);
    } catch {
      return reply.code(401).send({ error: "Unauthorized" });
    }
  };
}
export {
  DEFAULT_RELAY_DOMAIN,
  authorizeRelayCreate,
  connectInternal,
  expressNotifyPass,
  fastifyNotifyPass,
  honoNotifyPass,
  installRelayCreateAuth,
  relayApiOrigin,
  resolveCallbackTargetUrl,
  runConnect,
  signCallbackBody,
  tunnelHostname,
  tunnelOrigin,
  verifyCallbackSignature,
  verifyNotifyPass
};
