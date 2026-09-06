import { createHash, timingSafeEqual } from "node:crypto";

export function isAuthorized(header: string | null, expectedToken: string | undefined): boolean {
  if (!header || !expectedToken || !header.startsWith("Bearer ")) return false;
  const supplied = Buffer.from(header.slice(7));
  const expected = Buffer.from(expectedToken);
  if (supplied.length !== expected.length) return false;
  return timingSafeEqual(supplied, expected);
}

export function isAuthorizedDigest(header: string | null, expectedSha256Hex: string): boolean {
  if (!header || !header.startsWith("Bearer ")) return false;
  if (!/^[0-9a-f]{64}$/i.test(expectedSha256Hex)) return false;
  const suppliedDigest = createHash("sha256").update(header.slice(7)).digest();
  const expectedDigest = Buffer.from(expectedSha256Hex, "hex");
  return suppliedDigest.length === expectedDigest.length && timingSafeEqual(suppliedDigest, expectedDigest);
}
