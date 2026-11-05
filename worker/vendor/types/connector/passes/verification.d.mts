import { type JWTPayload } from "../../jose/index.mjs";
export interface PassVerifyOptions {
    /** Notify origin that publishes JWKS (the pass `iss`). */
    issuer?: string;
    /** Route origin the pass is bound to (`aud`). */
    audience: string;
    /** Expected registered app and workspace, when known by the service. */
    appId?: string;
    teamId?: string | null;
}
export interface NotifyPassClaims extends JWTPayload {
    app_id: string;
    sub: string;
    jti: string;
    exp: number;
    iat: number;
    team_id?: string;
    team_role?: string;
}
export declare function verifyNotifyPass(token: string, options: PassVerifyOptions): Promise<NotifyPassClaims>;
