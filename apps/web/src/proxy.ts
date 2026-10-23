import { NextResponse, type NextRequest } from "next/server";

import { CLIENT_IP_HEADER, PROXY_SECRET_HEADER, proxyIdentity } from "@/lib/api/client-ip";

// Runs before the /api/igs/* rewrite (next.config.ts): strips any identity headers the browser
// sent and adds the visitor's address plus the shared secret, so the API rate-limits per visitor.
export function proxy(request: NextRequest) {
  const headers = new Headers(request.headers);
  headers.delete(CLIENT_IP_HEADER);
  headers.delete(PROXY_SECRET_HEADER);
  for (const [name, value] of Object.entries(proxyIdentity(request.headers))) {
    headers.set(name, value);
  }
  return NextResponse.next({ request: { headers } });
}

export const config = { matcher: "/api/igs/:path*" };
