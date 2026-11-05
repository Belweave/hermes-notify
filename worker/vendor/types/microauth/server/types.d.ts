import { type SharedProfile } from "../protocol.js";
export interface MicroAuthChallenge {
    challenge: string;
    expiresAt: number;
}
/** Implement against a shared durable store. consume must compare-and-delete atomically. */
export interface MicroAuthChallengeStore {
    put(binding: string, challenge: MicroAuthChallenge): Promise<void>;
    get(binding: string): Promise<MicroAuthChallenge | null>;
    consume(binding: string, challenge: string): Promise<boolean>;
}
export interface MicroAuthIdentity {
    subject: string;
    issuer: string;
    appId: string;
    name?: string;
    /** Account email, not an assertion that the address was independently verified. */
    email?: string;
    profile?: SharedProfile;
    team?: {
        id: string;
        role: "owner" | "admin" | "member";
    };
}
