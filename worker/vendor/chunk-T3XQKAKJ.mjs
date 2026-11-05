// src/connector/protocol.ts
var DEFAULT_RELAY_DOMAIN = "clawchest.com";
var APP_PASS_ALGORITHM = "ES256";
var APP_PASS_JWKS_PATH = "/.well-known/jwks.json";
var APP_PASS_JWT_TYPE = "notify-pass+jwt";
var APP_PASS_TTL_SECONDS = 120;
var TEAM_ROLES = ["owner", "admin", "member"];
var CALLBACK_TIMESTAMP_HEADER = "notify-timestamp";
var CALLBACK_SIGNATURE_HEADER = "notify-signature";
var CALLBACK_SIGNATURE_VERSION = "v1";
var CALLBACK_MAX_SKEW_SECONDS = 300;
function isRouteName(value) {
  return typeof value === "string" && /^(@|[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)$/.test(value.trim());
}
var normalizeDomain = (domain) => domain.trim().toLowerCase().replace(/^\.+|\.+$/g, "");
function relayApiOrigin(domain = DEFAULT_RELAY_DOMAIN) {
  return `https://api.${normalizeDomain(domain)}`;
}
function tunnelHostname(id, route, domain = DEFAULT_RELAY_DOMAIN) {
  const labels = [id.trim().toLowerCase(), normalizeDomain(domain)];
  if (route && route !== "@") labels.unshift(route.trim().toLowerCase());
  return labels.join(".");
}
function tunnelOrigin(id, route, domain = DEFAULT_RELAY_DOMAIN) {
  return `https://${tunnelHostname(id, route, domain)}`;
}
function resolveCallbackTargetUrl(id, target, domain = DEFAULT_RELAY_DOMAIN) {
  const pathname = target.path.startsWith("/") ? target.path : `/${target.path}`;
  return tunnelOrigin(id, target.route, domain) + pathname;
}

// src/connector/transport/authorization.ts
function secureControlOrigin(url) {
  const parsed = new URL(url);
  const loopback = ["127.0.0.1", "[::1]"].includes(parsed.hostname);
  if (parsed.username || parsed.password || parsed.protocol !== "https:" && !(parsed.protocol === "http:" && loopback)) {
    throw new Error(
      "Notify and relay control URLs require HTTPS (HTTP is allowed only on loopback)"
    );
  }
  return parsed.origin;
}
function authorizeRelayCreate(relayApi, token, send = globalThis.fetch) {
  const allowedOrigin = secureControlOrigin(relayApi);
  return (input, init) => {
    const source = input instanceof Request ? input : void 0;
    const address = source?.url ?? String(input);
    const method = (init?.method ?? source?.method ?? "GET").toUpperCase();
    let target;
    try {
      target = new URL(address);
    } catch {
    }
    const path = target?.pathname.replace(/\/+/g, "/").replace(/\/+$/, "") || "/";
    if (method !== "POST" || target?.origin !== allowedOrigin || path !== "/api/tunnel" || target.username || target.password)
      return send(input, init);
    const headers = new Headers(init?.headers ?? source?.headers);
    if (!headers.has("authorization")) headers.set("authorization", `Bearer ${token}`);
    return source ? send(new Request(source, { ...init, headers })) : send(input, { ...init, headers });
  };
}
function installRelayCreateAuth(relayApi, token) {
  const previous = globalThis.fetch;
  globalThis.fetch = authorizeRelayCreate(relayApi, token, previous);
  return () => {
    globalThis.fetch = previous;
  };
}

export {
  DEFAULT_RELAY_DOMAIN,
  APP_PASS_ALGORITHM,
  APP_PASS_JWKS_PATH,
  APP_PASS_JWT_TYPE,
  APP_PASS_TTL_SECONDS,
  TEAM_ROLES,
  CALLBACK_TIMESTAMP_HEADER,
  CALLBACK_SIGNATURE_HEADER,
  CALLBACK_SIGNATURE_VERSION,
  CALLBACK_MAX_SKEW_SECONDS,
  isRouteName,
  relayApiOrigin,
  tunnelHostname,
  tunnelOrigin,
  resolveCallbackTargetUrl,
  secureControlOrigin,
  authorizeRelayCreate,
  installRelayCreateAuth
};
