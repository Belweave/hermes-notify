/** Public wire types and URL rules for the Notify connector API. */
export declare const DEFAULT_RELAY_DOMAIN = "clawchest.com";
export declare const APP_PASS_ALGORITHM = "ES256";
export declare const APP_PASS_JWKS_PATH = "/.well-known/jwks.json";
export declare const APP_PASS_JWT_TYPE = "notify-pass+jwt";
export declare const APP_PASS_TTL_SECONDS = 120;
export declare const TEAM_ROLES: readonly ["owner", "admin", "member"];
export declare const CALLBACK_TIMESTAMP_HEADER = "notify-timestamp";
export declare const CALLBACK_SIGNATURE_HEADER = "notify-signature";
export declare const CALLBACK_SIGNATURE_VERSION = "v1";
export declare const CALLBACK_MAX_SKEW_SECONDS = 300;
export interface ConnectorRoute {
    name: string;
    target: string;
    url: string;
    appId?: string;
    enabled?: boolean;
}
export interface ConnectorDto {
    id: string;
    name: string;
    tunnelId: string;
    hostname: string;
    routes: ConnectorRoute[];
    enabled?: boolean;
    status: "online" | "offline" | "unknown";
    lastSeenAt: string | null;
    teamId: string | null;
    oncallGroupId: string | null;
    createdAt: string;
    updatedAt: string;
}
export interface ConnectorCreatedResponse {
    connector: ConnectorDto;
    callbackSecret?: string;
    reused?: boolean;
}
export interface CallbackTarget {
    connectorId: string;
    route: string;
    path: string;
}
export declare function isRouteName(value: unknown): value is string;
export declare function relayApiOrigin(domain?: string): string;
export declare function tunnelHostname(id: string, route?: string, domain?: string): string;
export declare function tunnelOrigin(id: string, route?: string, domain?: string): string;
export declare function resolveCallbackTargetUrl(id: string, target: CallbackTarget, domain?: string): string;
