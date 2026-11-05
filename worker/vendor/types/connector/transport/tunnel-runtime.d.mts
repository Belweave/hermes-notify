import type { ConnectorRouteTarget, ConnectOptions, TunnelSession } from "../types.mjs";
/** Each tunnel owns its transport, credentials, and cleanup scope. */
export declare function defaultTunnelFactory(options: ConnectOptions, routes: Record<string, ConnectorRouteTarget>, fetchImpl: typeof fetch): Promise<TunnelSession>;
