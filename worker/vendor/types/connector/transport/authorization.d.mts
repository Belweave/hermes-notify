export declare function secureControlOrigin(url: string): string;
/** Add credentials only to this relay's exact tunnel-creation endpoint. */
export declare function authorizeRelayCreate(relayApi: string, token: string, send?: typeof fetch): typeof fetch;
/** @deprecated Pass authorizeRelayCreate() to your tunnel factory instead. */
export declare function installRelayCreateAuth(relayApi: string, token: string): () => void;
