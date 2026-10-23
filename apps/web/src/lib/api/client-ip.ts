// Server-only: tells the API which browser a proxied request belongs to, so rate limits are per
// visitor instead of per Vercel egress address (shared by everyone). The API trusts the address
// only together with IGS_PROXY_SHARED_SECRET (services/core/src/igs_core/ratelimit.py).

export const CLIENT_IP_HEADER = "x-igs-client-ip";
export const PROXY_SECRET_HEADER = "x-igs-proxy-secret";

/** The visitor's address as Vercel reports it (x-real-ip, else the first x-forwarded-for hop). */
export function visitorIp(headers: Headers): string | undefined {
  const real = headers.get("x-real-ip")?.trim();
  if (real) return real;
  const first = headers.get("x-forwarded-for")?.split(",")[0]?.trim();
  return first || undefined;
}

/** Headers to add on the way to the API; empty when the secret isn't configured. */
export function proxyIdentity(
  incoming: Headers,
  env: Record<string, string | undefined> = process.env,
): Record<string, string> {
  const secret = env.IGS_PROXY_SHARED_SECRET;
  const ip = visitorIp(incoming);
  if (!secret || !ip) return {};
  return { [CLIENT_IP_HEADER]: ip, [PROXY_SECRET_HEADER]: secret };
}
