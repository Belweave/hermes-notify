import { Agent as HttpAgent } from "node:http";
import { type Socket } from "node:net";
export type ProxyProtocol = "v1" | "v2";
/** Accept only the bounded TCP/UNKNOWN preambles produced by the SDK. */
export declare function proxyHeaderLength(bytes: Buffer, version: ProxyProtocol): number | undefined;
/** Parse before HTTP sees the socket; never infer a peer from request headers. */
export declare function consumeProxyHeader(socket: Socket, version: ProxyProtocol, ready: (header: Buffer) => void): void;
/** A fresh non-pooling agent binds exactly one verified peer to one connection. */
export declare function proxyUpstreamAgent(target: URL, header: Buffer): HttpAgent;
