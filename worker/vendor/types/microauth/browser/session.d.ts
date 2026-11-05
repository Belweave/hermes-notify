import { type MicroAuthOptions } from "../protocol.js";
export declare function sameOriginPath(path: string): string;
/** Completes a same-origin cookie session handshake; ordinary browsers return unavailable. */
export declare function connectMicroAuth(options: {
    challengePath: string;
    sessionPath: string;
    fields?: MicroAuthOptions["fields"];
    signal?: AbortSignal;
}): Promise<{
    available: false;
} | {
    available: true;
}>;
