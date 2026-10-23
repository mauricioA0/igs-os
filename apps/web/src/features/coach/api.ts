// Coach-facing endpoints (`/v1/public/*` in services/core). They aren't in the generated
// OpenAPI schema yet, so the shapes are mirrored here from `igs_core.api.v1.public_chat`.
import { ApiError, toApiError } from "@/lib/api/errors";

export type ChatOption = { id?: string; label: string; value?: string };
export type ChatAttachment = { kind: string; url?: string; label?: string };

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
  at: string;
  options: ChatOption[];
  attachments: ChatAttachment[];
};

export type Conversation = {
  conversation_id: string;
  execution_id: string;
  status: string;
  ai_disclosure: string;
};

export type Transcript = { conversation_id: string; status: string; messages: ChatMessage[] };

export type ProposalOpponent = { name: string; city: string; level_score: number; description: string };
export type ProposalItem = {
  slot: "morning" | "afternoon" | "evening";
  kind: string;
  title: string;
  time: string | null;
  opponent: ProposalOpponent | null;
  experience: string | null;
};
export type ProposalDay = { day: number; date: string; items: ProposalItem[] };

export type Proposal = {
  id: string;
  ref: string;
  title: string;
  team: string;
  program: string | null;
  coach_name: string | null;
  sport: string | null;
  gender: string | null;
  level_score: number | null;
  city: string;
  country: string;
  start_date: string;
  end_date: string;
  days: number;
  travelers: number | null;
  price_per_person_usd: number;
  /** IGS terms: non-refundable enrollment fee per traveler (US$95). */
  enrollment_fee_usd: number;
  /** Payment-plan installment per traveler (US$500), due 30 and 90 days after enrollment. */
  installment_usd: number;
  first_installment_due_days: number;
  second_installment_due_days: number;
  /** Final balance, 110 days before departure. */
  balance_due: string;
  valid_until: string;
  status: string;
  summary: string;
  itinerary: ProposalDay[];
  opponents: ProposalOpponent[];
  experiences: string[];
  included: string[];
  not_included: string[];
  enrollment_requested: boolean;
};

export type ReserveRequest = { name: string; email: string; note?: string };
export type ReserveResult = { approval_id: string; status: string; enrollment_fees_usd: number; message: string };

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, {
      ...init,
      headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch (cause) {
    throw toApiError(cause instanceof Error ? cause.message : undefined);
  }
  const body: unknown = await response.json().catch(() => undefined);
  if (!response.ok) throw toApiError(body, response);
  return body as T;
}

/** Calls from the browser go same-origin through the `/api/igs/*` rewrite. */
export const BROWSER_BASE = "/api/igs/v1/public";

export const coachApi = {
  startConversation: (message?: string) =>
    request<Conversation>(`${BROWSER_BASE}/chat/conversations`, {
      method: "POST",
      body: JSON.stringify({ message: message || null, source: "web" }),
    }),
  sendMessage: (conversationId: string, text: string) =>
    request<{ message_id: string; delivered: boolean }>(
      `${BROWSER_BASE}/chat/conversations/${conversationId}/messages`,
      { method: "POST", body: JSON.stringify({ text }) },
    ),
  transcript: (conversationId: string) =>
    request<Transcript>(`${BROWSER_BASE}/chat/conversations/${conversationId}/messages`),
  streamUrl: (conversationId: string) => `${BROWSER_BASE}/chat/conversations/${conversationId}/stream`,
  reserve: (ref: string, body: ReserveRequest) =>
    request<ReserveResult>(`${BROWSER_BASE}/proposals/${encodeURIComponent(ref)}/reserve`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
};

/** Server-side read for the proposal page (Server Component). */
export async function fetchProposal(ref: string): Promise<Proposal | null> {
  const base = (process.env.API_URL ?? "http://localhost:8000").replace(/\/+$/, "");
  try {
    return await request<Proposal>(`${base}/v1/public/proposals/${encodeURIComponent(ref)}`, {
      cache: "no-store",
    });
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

export function usd(value: number): string {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(value);
}

export function formatDate(iso: string, opts: Intl.DateTimeFormatOptions = { month: "short", day: "numeric" }): string {
  // Dates are calendar days at the destination: format in UTC so they never shift by a day.
  return new Intl.DateTimeFormat("en-US", { ...opts, timeZone: "UTC" }).format(new Date(`${iso}T00:00:00Z`));
}
