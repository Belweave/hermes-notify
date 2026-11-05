// src/microauth/types.ts
var MICRO_AUTH_FIELDS = [
  "name",
  "email",
  "phone",
  "timeZone",
  "pronouns",
  "custom"
];

// src/microauth/errors.ts
var MicroAuthError = class extends Error {
  constructor(code, message) {
    super(message);
    this.code = code;
    this.name = "MicroAuthError";
  }
  code;
};

// src/microauth/validation.ts
function validChallenge(value) {
  return typeof value === "string" && /^[A-Za-z0-9_-]{43,128}$/.test(value);
}
function validateOptions(options) {
  if (!validChallenge(options?.challenge))
    throw new MicroAuthError("INVALID_CHALLENGE", "Use a fresh challenge from your server.");
  if (options.fields !== void 0 && (!Array.isArray(options.fields) || options.fields.length > 6 || options.fields.some((field) => !MICRO_AUTH_FIELDS.includes(field))))
    throw new MicroAuthError("INVALID_FIELDS", "Choose supported profile fields.");
}

// src/microauth/browser/bridge.ts
function notifyApp() {
  return typeof window === "undefined" ? void 0 : window.notify;
}
function supportsMicroAuth() {
  return typeof notifyApp()?.microAuth === "function";
}
async function microAuth(options) {
  validateOptions(options);
  const bridge = notifyApp();
  if (!bridge?.microAuth)
    throw new MicroAuthError(
      "UNAVAILABLE",
      "Use this site's regular sign-in, or open it in an updated Notify app."
    );
  const token = await bridge.microAuth({
    challenge: options.challenge,
    fields: options.fields ?? []
  });
  if (typeof token !== "string" || token.length > 32768 || token.split(".").length !== 3)
    throw new MicroAuthError("INVALID_RESPONSE", "microAuth() returned an invalid pass.");
  return token;
}
function notifyMini() {
  if (typeof window === "undefined") return void 0;
  const bridge = window.notifyMini;
  return bridge && typeof bridge.storage?.get === "function" && typeof bridge.storage.set === "function" && typeof bridge.storage.remove === "function" ? bridge : void 0;
}

// src/microauth/browser/session.ts
function sameOriginPath(path) {
  const url = new URL(path, window.location.href);
  if (url.origin !== window.location.origin || url.username || url.password || url.hash)
    throw new MicroAuthError("INVALID_ENDPOINT", "microAuth() endpoints must be on this website.");
  return url.href;
}
async function connectMicroAuth(options) {
  if (!supportsMicroAuth()) return { available: false };
  const challengeUrl = sameOriginPath(options.challengePath);
  const sessionUrl = sameOriginPath(options.sessionPath);
  const init = {
    method: "POST",
    credentials: "same-origin",
    redirect: "error",
    cache: "no-store",
    headers: { "content-type": "application/json" },
    signal: options.signal
  };
  const challengeResponse = await fetch(challengeUrl, { ...init, body: "{}" });
  if (!challengeResponse.ok)
    throw new MicroAuthError("CHALLENGE_FAILED", "Your server could not start sign-in.");
  const challenge = await challengeResponse.json();
  if (typeof challenge?.challenge !== "string")
    throw new MicroAuthError("INVALID_CHALLENGE", "Your server did not return a challenge.");
  options.signal?.throwIfAborted();
  const token = await microAuth({
    challenge: challenge.challenge,
    fields: options.fields
  });
  options.signal?.throwIfAborted();
  const sessionResponse = await fetch(sessionUrl, {
    ...init,
    body: JSON.stringify({ token })
  });
  if (!sessionResponse.ok)
    throw new MicroAuthError("SESSION_FAILED", "Your server did not accept sign-in. Try again.");
  return { available: true };
}
export {
  MicroAuthError,
  connectMicroAuth,
  microAuth,
  notifyApp,
  notifyMini,
  sameOriginPath,
  supportsMicroAuth
};
