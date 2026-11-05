/** Put this random binding in an HttpOnly, Secure, SameSite cookie; never read it from a request body. */
export declare function createMicroAuthBinding(): string;
export declare function httpsOrigin(value: string): string;
export declare function string(value: unknown, limit: number): value is string;
export declare function invalid(): never;
