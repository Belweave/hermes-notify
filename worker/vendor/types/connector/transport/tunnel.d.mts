import type { ConnectorRouteTarget, ConnectOptions, TunnelSession } from "../types.mjs";
/** Load the relay runtime only when a connection is requested. */
export declare function defaultTunnelFactory(options: ConnectOptions, routes: Record<string, ConnectorRouteTarget>, fetchImpl: typeof fetch): Promise<TunnelSession>;
