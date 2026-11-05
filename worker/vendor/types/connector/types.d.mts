import type { TunnelStorage } from "./storage.mjs";
export type { TunnelIdentity, TunnelPendingIdentity, TunnelStorage } from "./storage.mjs";
import { type ConnectorDto, type ConnectorRoute } from "./protocol.mjs";
export type ProxyProtocol = "v1" | "v2";
export type ConnectorRouteTarget = string | {
    target: string;
    proxyProtocol?: ProxyProtocol;
};
export interface TunnelSession {
    id: string;
    hostname: string;
    close: () => Promise<void>;
    /** Explicitly delete the remote tunnel and saved identity after closing. */
    remove?: () => Promise<void>;
}
export interface TunnelFactory {
    connect: (routes: Record<string, ConnectorRouteTarget>, fetchImpl: typeof fetch) => Promise<TunnelSession>;
}
export interface ConnectOptions {
    token: string;
    name: string;
    routes: Record<string, ConnectorRouteTarget>;
    apiUrl?: string;
    relayDomain?: string;
    relayApi?: string;
    teamId?: string;
    oncallGroupId?: string;
    fetch?: typeof fetch;
    tunnel?: TunnelFactory;
    /** Profile label isolated by credential, workspace and original route configuration. */
    tunnelProfile?: string;
    /** Private persistent XDG storage by default; custom Promise-based stores may be ephemeral. */
    tunnelStorage?: TunnelStorage;
    heartbeatMs?: number;
    registerApps?: boolean;
    onWarning?: (message: string) => void;
}
export interface ConnectorHandle {
    connector: ConnectorDto;
    callbackSecret?: string;
    reused: boolean;
    routes: ConnectorRoute[];
    close: () => Promise<void>;
    /** Offline and close, then delete the remote tunnel and local credentials. */
    removeTunnel: () => Promise<void>;
}
