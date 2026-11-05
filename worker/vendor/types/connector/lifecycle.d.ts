import type { ConnectOptions, ConnectorHandle } from "./types.js";
export declare const DEFAULT_API = "https://notify.belweave.ai";
export declare function connectInternal(options: ConnectOptions): Promise<ConnectorHandle>;
