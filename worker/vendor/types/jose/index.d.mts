export { compactDecrypt } from './jwe/compact/decrypt.mjs';
export type { CompactDecryptGetKey } from './jwe/compact/decrypt.mjs';
export { flattenedDecrypt } from './jwe/flattened/decrypt.mjs';
export type { FlattenedDecryptGetKey } from './jwe/flattened/decrypt.mjs';
export { generalDecrypt } from './jwe/general/decrypt.mjs';
export type { GeneralDecryptGetKey } from './jwe/general/decrypt.mjs';
export { GeneralEncrypt } from './jwe/general/encrypt.mjs';
export type { Recipient } from './jwe/general/encrypt.mjs';
export { compactVerify } from './jws/compact/verify.mjs';
export type { CompactVerifyGetKey } from './jws/compact/verify.mjs';
export { flattenedVerify } from './jws/flattened/verify.mjs';
export type { FlattenedVerifyGetKey } from './jws/flattened/verify.mjs';
export { generalVerify } from './jws/general/verify.mjs';
export type { GeneralVerifyGetKey } from './jws/general/verify.mjs';
export { jwtVerify } from './jwt/verify.mjs';
export type { JWTVerifyOptions, JWTVerifyGetKey } from './jwt/verify.mjs';
export { jwtDecrypt } from './jwt/decrypt.mjs';
export type { JWTDecryptOptions, JWTDecryptGetKey } from './jwt/decrypt.mjs';
export { CompactEncrypt } from './jwe/compact/encrypt.mjs';
export { FlattenedEncrypt } from './jwe/flattened/encrypt.mjs';
export { CompactSign } from './jws/compact/sign.mjs';
export { FlattenedSign } from './jws/flattened/sign.mjs';
export { GeneralSign } from './jws/general/sign.mjs';
export type { Signature } from './jws/general/sign.mjs';
export { SignJWT } from './jwt/sign.mjs';
export { EncryptJWT } from './jwt/encrypt.mjs';
export { calculateJwkThumbprint, calculateJwkThumbprintUri } from './jwk/thumbprint.mjs';
export { EmbeddedJWK } from './jwk/embedded.mjs';
export { createLocalJWKSet } from './jwks/local.mjs';
export { createRemoteJWKSet, jwksCache, customFetch } from './jwks/remote.mjs';
export type { RemoteJWKSetOptions, JWKSCacheInput, ExportedJWKSCache, FetchImplementation, } from './jwks/remote.mjs';
export { UnsecuredJWT } from './jwt/unsecured.mjs';
export type { UnsecuredResult } from './jwt/unsecured.mjs';
export { exportPKCS8, exportSPKI, exportJWK } from './key/export.mjs';
export { importSPKI, importPKCS8, importX509, importJWK } from './key/import.mjs';
export type { KeyImportOptions } from './key/import.mjs';
export { decodeProtectedHeader } from './util/decode_protected_header.mjs';
export { decodeJwt } from './util/decode_jwt.mjs';
export type { ProtectedHeaderParameters } from './util/decode_protected_header.mjs';
import * as errors from './util/errors.mjs';
export { errors };
export { generateKeyPair } from './key/generate_key_pair.mjs';
export type { GenerateKeyPairResult, GenerateKeyPairOptions } from './key/generate_key_pair.mjs';
export { generateSecret } from './key/generate_secret.mjs';
export type { GenerateSecretOptions } from './key/generate_secret.mjs';
import * as base64url from './util/base64url.mjs';
export { base64url };
export type { CompactDecryptResult, CompactJWEHeaderParameters, CompactJWSHeaderParameters, CompactVerifyResult, CritOption, CryptoKey, DecryptOptions, EncryptOptions, FlattenedDecryptResult, FlattenedJWE, FlattenedJWS, FlattenedJWSInput, FlattenedVerifyResult, GeneralDecryptResult, GeneralJWE, GeneralJWS, GeneralJWSInput, GeneralVerifyResult, GetKeyFunction, JoseHeaderParameters, JSONWebKeySet, JWEHeaderParameters, JWEKeyManagementHeaderParameters, JWK_EC_Private, JWK_EC_Public, JWK_oct, JWK_OKP_Private, JWK_OKP_Public, JWK_RSA_Private, JWK_RSA_Public, JWK, JWKParameters, JWSHeaderParameters, JWTClaimVerificationOptions, JWTDecryptResult, JWTHeaderParameters, JWTPayload, JWTVerifyResult, KeyObject, ProduceJWT, ResolvedKey, SignOptions, VerifyOptions, } from './types.d.ts';
/**
 * In prior releases this indicated whether a Node.js-specific build was loaded, this is now fixed
 * to `"WebCryptoAPI"`
 *
 * @deprecated
 */
export declare const cryptoRuntime = "WebCryptoAPI";
