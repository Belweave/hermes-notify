import { type ConnectorDto, type ConnectorRoute } from "./protocol.js";
import { TunnelFactory } from "./types.js";
export declare function runConnect(input: {
    token: string;
    apiUrl?: string;
    port: number;
    name: string;
    host?: string;
    proxyProtocol?: "v1" | "v2";
    teamId?: string;
    oncallGroupId?: string;
    relayDomain?: string;
    signal?: AbortSignal;
    fetch?: typeof fetch;
    tunnel?: TunnelFactory;
}): Promise<{
    body: {
        connector: ConnectorDto;
        routes: ConnectorRoute[];
        callbackSecret?: string;
        reused: boolean;
    };
    exitCode: number;
}>;
