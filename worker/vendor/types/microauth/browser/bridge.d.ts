import { type MicroAuthOptions } from "../protocol.js";
export interface NotifyAppBridge {
    readonly version: number;
    microAuth?: (options: MicroAuthOptions) => Promise<string>;
    getToken?: () => Promise<string>;
    close?: () => void;
    capabilities?: () => Promise<Record<string, unknown>>;
    haptics?: (style: "light" | "medium" | "heavy" | "soft" | "rigid" | "success" | "warning" | "error") => Promise<unknown>;
    share?: (data: {
        title?: string;
        text?: string;
        url?: string;
    }) => Promise<{
        ok: boolean;
    }>;
    openSettings?: () => Promise<unknown>;
}
/** Feature detection only. Importing the SDK never starts sign-in or changes the page. */
export declare function notifyApp(): NotifyAppBridge | undefined;
export declare function supportsMicroAuth(): boolean;
/** Returns a credential for your server. A returned token is not a browser session. */
export declare function microAuth(options: MicroAuthOptions): Promise<string>;
export interface NotifyMiniBridge {
    readonly storage: {
        get(key: string): Promise<string | null>;
        set(key: string, value: string): Promise<null>;
        remove(key: string): Promise<null>;
    };
}
/** Detects the optional packaged-app storage broker without calling it or authenticating. */
export declare function notifyMini(): NotifyMiniBridge | undefined;
