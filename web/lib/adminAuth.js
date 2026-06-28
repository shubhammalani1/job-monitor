import crypto from "crypto";

const TOKEN_TTL_MS = 15 * 60 * 1000; // 15 minutes

function hashPin(pin) {
  return crypto.createHmac("sha256", process.env.ADMIN_PIN_SALT).update(pin).digest("hex");
}

function createAdminToken() {
  const expiry = Date.now() + TOKEN_TTL_MS;
  const payload = String(expiry);
  const sig = crypto.createHmac("sha256", process.env.ADMIN_TOKEN_SECRET).update(payload).digest("hex");
  return `${payload}.${sig}`;
}

function verifyAdminToken(token) {
  if (!token || typeof token !== "string" || !token.includes(".")) return false;
  const [payload, sig] = token.split(".");
  const expectedSig = crypto.createHmac("sha256", process.env.ADMIN_TOKEN_SECRET).update(payload).digest("hex");
  const validSig = sig.length === expectedSig.length && crypto.timingSafeEqual(Buffer.from(sig), Buffer.from(expectedSig));
  if (!validSig) return false;
  return Date.now() < parseInt(payload, 10);
}

export { hashPin, createAdminToken, verifyAdminToken };
