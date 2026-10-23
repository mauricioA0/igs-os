// Server-side reads for Account 360.
import { unwrap } from "@/lib/api/client";
import { toApiError } from "@/lib/api/errors";
import { serverApi } from "@/lib/api/server";
import type { components } from "@/lib/api/schema";

export type AccountSummary = components["schemas"]["AccountSummary"];
export type AccountDetail = Omit<components["schemas"]["AccountDetail"], "recent_interactions"> & {
  recent_interactions: InteractionSummary[];
};
export type Stakeholder = components["schemas"]["Stakeholder"];
export type AccountFact = components["schemas"]["AccountFact"];
// `excerpt` (first lines of the body) arrives in wave 4; optional until the API types include it.
export type InteractionSummary = components["schemas"]["InteractionSummary"] & { excerpt?: string | null };
export type Brief = components["schemas"]["BriefOut"];
export type Citation = components["schemas"]["CitationOut"];
export type AskAnswer = components["schemas"]["AskOut"];

export async function listAccounts(): Promise<AccountSummary[]> {
  const page = await unwrap(serverApi().GET("/v1/accounts", { params: { query: { limit: 100 } } }));
  return page.items;
}

export async function getAccount(id: string): Promise<AccountDetail | null> {
  const { data, error, response } = await serverApi().GET("/v1/accounts/{account_id}", {
    params: { path: { account_id: id } },
  });
  if (response.status === 404 || response.status === 422) return null; // unknown or malformed id
  if (!data) throw toApiError(error, response);
  return data;
}

/**
 * The cited brief needs the LLM; when it isn't configured (or fails) the page still renders from
 * structured data, so this returns the error instead of throwing.
 */
export async function getBrief(id: string): Promise<{ brief: Brief } | { error: unknown }> {
  try {
    const brief = await unwrap(
      serverApi().GET("/v1/accounts/{account_id}/brief", { params: { path: { account_id: id } } }),
    );
    return { brief };
  } catch (error) {
    return { error };
  }
}
