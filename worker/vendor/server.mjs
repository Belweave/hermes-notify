import {
  createRemoteJWKSet,
  jwtVerify
} from "./chunk-JKIZH22G.mjs";
import "./chunk-7P6ASYW6.mjs";

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

// src/microauth/server/binding.ts
import { randomBytes } from "node:crypto";
function createMicroAuthBinding() {
  return randomBytes(32).toString("base64url");
}
function httpsOrigin(value) {
  const url = new URL(value);
  if (url.protocol !== "https:" || url.username || url.password || url.origin !== value)
    throw new MicroAuthError(
      "INVALID_CONFIG",
      "Configure an exact HTTPS origin without a path or trailing slash."
    );
  return url.origin;
}
function string(value, limit) {
  return typeof value === "string" && value.length > 0 && value.length <= limit;
}
function invalid() {
  throw new MicroAuthError("INVALID_PASS", "The microAuth() pass was not accepted.");
}

// src/microauth/server/identity.ts
function sharedProfile(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return invalid();
  const raw = value;
  const result = {};
  for (const field of ["phone", "timeZone", "pronouns"]) {
    if (raw[field] !== void 0) {
      if (!string(raw[field], 100)) return invalid();
      result[field] = raw[field];
    }
  }
  if (raw.custom !== void 0) {
    if (!Array.isArray(raw.custom) || raw.custom.length > 20) return invalid();
    result.custom = raw.custom.map((value2) => {
      if (!value2 || typeof value2 !== "object" || Array.isArray(value2)) return invalid();
      const field = value2;
      if (!string(field.id, 64) || !/^field_[a-f0-9]{32}$/.test(field.id) || !string(field.label, 80) || !string(field.value, 512))
        return invalid();
      return { id: field.id, label: field.label, value: field.value };
    });
  }
  return result;
}

// src/microauth/server/handshake.ts
import { randomBytes as randomBytes2 } from "node:crypto";
function createMicroAuthServer(config) {
  const issuer = httpsOrigin(config.issuer ?? "https://notify.belweave.ai");
  const origin = httpsOrigin(config.origin);
  if (!string(config.appId, 256))
    throw new MicroAuthError("INVALID_CONFIG", "Set your registered Notify app ID.");
  const keys = config.keys ?? createRemoteJWKSet(new URL("/.well-known/jwks.json", issuer));
  return {
    async begin(binding) {
      if (!validChallenge(binding))
        throw new MicroAuthError("INVALID_BINDING", "Use a random browser-session binding.");
      const challenge = {
        challenge: randomBytes2(32).toString("base64url"),
        expiresAt: Date.now() + 12e4
      };
      await config.store.put(binding, challenge);
      return challenge;
    },
    async complete(token, binding) {
      if (!validChallenge(binding) || !string(token, 32768)) return invalid();
      const pending = await config.store.get(binding);
      if (!pending || !validChallenge(pending.challenge) || !Number.isFinite(pending.expiresAt) || pending.expiresAt <= Date.now())
        return invalid();
      let verified;
      try {
        verified = await jwtVerify(token, keys, {
          algorithms: ["ES256"],
          issuer,
          audience: origin,
          typ: "notify-pass+jwt",
          maxTokenAge: 120,
          clockTolerance: 0,
          requiredClaims: ["iss", "aud", "sub", "iat", "exp", "jti", "app_id", "nonce"]
        });
      } catch {
        return invalid();
      }
      const { payload } = verified;
      if (payload.aud !== origin || payload.app_id !== config.appId || payload.nonce !== pending.challenge || !string(payload.sub, 256) || !string(payload.jti, 128) || typeof payload.iat !== "number" || !Number.isInteger(payload.iat) || typeof payload.exp !== "number" || !Number.isInteger(payload.exp) || payload.exp <= payload.iat || payload.exp - payload.iat > 120)
        return invalid();
      const identity = {
        subject: payload.sub,
        issuer,
        appId: config.appId
      };
      for (const field of ["name", "email"]) {
        if (payload[field] !== void 0) {
          if (!string(payload[field], 320)) return invalid();
          identity[field] = payload[field];
        }
      }
      if (payload.profile !== void 0) identity.profile = sharedProfile(payload.profile);
      if (payload.team_id !== void 0 || payload.team_role !== void 0) {
        if (!string(payload.team_id, 256) || !["owner", "admin", "member"].includes(String(payload.team_role)))
          return invalid();
        identity.team = {
          id: payload.team_id,
          role: payload.team_role
        };
      }
      if (pending.expiresAt <= Date.now() || !await config.store.consume(binding, pending.challenge))
        return invalid();
      return identity;
    }
  };
}
export {
  MicroAuthError,
  createMicroAuthBinding,
  createMicroAuthServer
};
