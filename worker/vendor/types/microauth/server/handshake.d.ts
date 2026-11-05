import { MicroAuthChallengeStore, MicroAuthChallenge, MicroAuthIdentity } from "./types.js";
import { type JWTVerifyGetKey } from "jose";
export declare function createMicroAuthServer(config: {
    origin: string;
    appId: string;
    store: MicroAuthChallengeStore;
    issuer?: string;
    /** Trusted server configuration only, e.g. a pinned JWKS for isolated tests. */
    keys?: JWTVerifyGetKey;
}): {
    begin(binding: string): Promise<MicroAuthChallenge>;
    complete(token: string, binding: string): Promise<MicroAuthIdentity>;
};
