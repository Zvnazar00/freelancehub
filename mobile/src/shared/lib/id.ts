import * as Crypto from 'expo-crypto';

/**
 * RFC 4122 v4 UUID from the platform's cryptographically secure generator (expo-crypto:
 * SecRandomCopyBytes on iOS, SecureRandom on Android, crypto.getRandomValues on web).
 *
 * Used for client-generated time-entry IDs and Idempotency-Keys, where a collision would make the
 * server treat two different actions as one — so Math.random is deliberately not used.
 */
export function uuidV4(): string {
  return Crypto.randomUUID();
}
