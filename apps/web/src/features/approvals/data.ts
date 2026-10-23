// Server-only: called from the route's Server Component (uses `serverApi`, which throws in the browser).
import { unwrap } from "@/lib/api";
import { serverApi } from "@/lib/api/server";
import type { ApprovalDetail, ApprovalSummary, Me } from "./types";

// `now` is captured with the data so server and client render the same countdowns.
export type InboxData = { items: ApprovalSummary[]; me: Me; selected?: ApprovalDetail; now: number };

// One page of the newest approvals is enough for the inbox; resolved ones are history.
export async function loadInbox(selectedId?: string): Promise<InboxData> {
  const api = serverApi();
  const [page, me] = await Promise.all([
    unwrap(api.GET("/v1/approvals", { params: { query: { limit: 100 } } })),
    unwrap(api.GET("/v1/me")),
  ]);
  const items = page.items;
  const get = (id: string) =>
    unwrap(api.GET("/v1/approvals/{approval_id}", { params: { path: { approval_id: id } } })).catch(() => undefined);
  const now = Date.now();
  const decidable = (a: ApprovalSummary) =>
    a.status === "pending" && (!a.expires_at || new Date(a.expires_at).getTime() > now);
  const firstPending = (items.find(decidable) ?? items.find((a) => a.status === "pending"))?.id;
  // An unknown or stale ?id= (old link) falls back to the first pending approval.
  let selected = selectedId ? await get(selectedId) : undefined;
  if (!selected && firstPending) selected = await get(firstPending);
  return { items, me, selected, now };
}
