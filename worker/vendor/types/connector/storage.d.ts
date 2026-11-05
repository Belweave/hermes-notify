/** Complete reusable tunnel credential bundle. Treat every field as private. */
export interface TunnelIdentity {
    readonly id: string;
    readonly hostname: string;
    readonly token: string;
    readonly privateKey: string;
    readonly certificate: string;
    readonly chain: string;
    readonly certificateExpiry: Date;
}
/** Durable CSR bundle retained until a completed identity is safely saved. */
export interface TunnelPendingIdentity {
    readonly id: string;
    readonly hostname: string;
    readonly token: string;
    readonly privateKey: string;
    readonly csr: string;
}
/**
 * Optional dependency-free identity store. Promise rejection denies startup/removal.
 * Persist pending credentials before issuance; retain them until save is durable.
 * Custom stores own confidentiality, atomicity and recovery of these credentials.
 */
export interface TunnelStorage {
    readonly profiles: () => Promise<ReadonlyArray<string>>;
    readonly load: (profile: string) => Promise<TunnelIdentity | undefined>;
    readonly save: (profile: string, identity: TunnelIdentity) => Promise<void>;
    readonly loadPending: (profile: string) => Promise<TunnelPendingIdentity | undefined>;
    readonly savePending: (profile: string, identity: TunnelPendingIdentity) => Promise<void>;
    readonly remove: (profile: string) => Promise<void>;
    readonly list: () => Promise<ReadonlyArray<{
        readonly profile: string;
        readonly tunnel: TunnelIdentity;
    }>>;
}
