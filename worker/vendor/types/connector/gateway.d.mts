import { type ProxyProtocol } from "./proxy-protocol.mjs";
export interface AccessIdentity {
    subject: string;
    appId: string;
    teamId: string | null;
    teamRole: string | null;
    expiresAt: number;
}
export interface GatewayOptions {
    target: string;
    proxyProtocol?: ProxyProtocol;
    routeName: string;
    authorize: (pass: string, consume: boolean) => Promise<AccessIdentity>;
    /** Dedicated signed machine delivery, never an alternate user authentication path. */
    authorizeCallback?: (input: {
        body: string;
        timestamp: string;
        signature: string;
    }) => Promise<{
        path: string;
    }>;
    /** Used by tests only; production checks at most 15 seconds apart. */
    recheckMs?: number;
}
export interface AccessGateway {
    target: string;
    setOrigin: (origin: string) => void;
    close: () => Promise<void>;
}
/** Every tunnel factory receives this loopback gateway, never the raw upstream. */
export declare function createAccessGateway(options: GatewayOptions): Promise<AccessGateway>;
