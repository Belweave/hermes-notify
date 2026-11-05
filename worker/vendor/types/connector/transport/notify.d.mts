export declare function notifyRequest<T>(apiUrl: string, token: string, path: string, init: RequestInit, fetchImpl: typeof fetch): Promise<{
    status: number;
    body: T;
}>;
