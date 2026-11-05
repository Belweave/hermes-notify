export declare function signCallbackBody(secret: string, timestamp: string, body: string): string;
export declare function verifyCallbackSignature(input: {
    secret: string;
    body: string;
    timestamp: string | null | undefined;
    signature: string | null | undefined;
    now?: number;
    maxSkewSeconds?: number;
}): boolean;
