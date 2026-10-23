import type { NextConfig } from "next";

const API_URL = (process.env.API_URL ?? "http://localhost:8000").replace(/\/+$/, "");

// QA D-11 / security review S-10. Next renders inline bootstrap scripts, so script-src keeps
// 'unsafe-inline' (no nonces yet); dev also needs 'unsafe-eval' for React refresh. Everything else
// is same-origin: the browser talks to the API only through /api/igs (rewrite below).
const isDev = process.env.NODE_ENV !== "production";
const csp = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  `connect-src 'self'${isDev ? " ws: http://localhost:*" : ""}`,
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "object-src 'none'",
].join("; ");

const securityHeaders = [
  { key: "Content-Security-Policy", value: csp },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
  { key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" },
];

const nextConfig: NextConfig = {
  poweredByHeader: false,
  // Unmatched URLs have no route-group root layout; app/global-not-found.tsx renders them.
  experimental: { globalNotFound: true },
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
  // Browser calls go same-origin to /api/igs/* (src/lib/api/browser.ts); the API host stays
  // server-side and SSE streams pass through the proxy.
  async rewrites() {
    return [{ source: "/api/igs/:path*", destination: `${API_URL}/:path*` }];
  },
  // Tailwind v4 runs as a Turbopack CSS loader (from the create-next-app scaffold).
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
