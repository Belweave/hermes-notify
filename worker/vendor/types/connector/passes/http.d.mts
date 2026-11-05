import { type PassVerifyOptions, type NotifyPassClaims } from "./verification.mjs";
export interface PassMiddlewareOptions extends PassVerifyOptions {
    /** Required durable, atomic claim shared by every service instance; true only once. */
    consumeJti: (jti: string, expiresAt: number) => Promise<boolean>;
}
type HonoPassContext = {
    req: {
        header: (name: string) => string | undefined;
    };
    set: (k: string, v: unknown) => void;
};
/** Hono middleware. Sets `pass` on the context. */
export declare function honoNotifyPass(options: PassMiddlewareOptions): (c: HonoPassContext, next: () => Promise<void>) => Promise<unknown>;
/** Express middleware. Sets `req.pass`. */
export declare function expressNotifyPass(options: PassMiddlewareOptions): (req: {
    headers: {
        authorization?: string;
    };
    pass?: NotifyPassClaims;
}, res: {
    status: (code: number) => {
        json: (body: unknown) => unknown;
    };
}, next: (error?: unknown) => void) => Promise<void>;
/** Fastify preHandler. Sets `request.pass`. */
export declare function fastifyNotifyPass(options: PassMiddlewareOptions): (request: {
    headers: {
        authorization?: string;
    };
    pass?: NotifyPassClaims;
}, reply: {
    code: (status: number) => {
        send: (body: unknown) => unknown;
    };
}) => Promise<unknown>;
export {};
