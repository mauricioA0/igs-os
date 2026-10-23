// Same-origin proxy to the core copilot (see features/copilot/server/proxy.ts): the browser never
// sees the API host or a key.
export { POST } from "@/features/copilot/server/proxy";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
