// Server-side reads for leads. `GET /v1/leads` arrived in wave 4 and isn't in the generated API
// types yet, so the response is read defensively and mapped to the board model.
import { apiUrl, sharedApiKey } from "@/lib/api/server";
import { type Lead, type LeadStage, leads as sampleLeads } from "./data";

type ApiLead = {
  id: string;
  account_name?: string | null;
  contact?: { name: string; organization?: string | null } | null;
  trip_code?: string | null;
  program?: string | null;
  sport?: string;
  gender?: string;
  age_group?: string;
  level_score?: number;
  group_size?: number;
  destination_country?: string;
  travel_start?: string | null;
  duration_days?: number | null;
  budget_per_person_usd?: number | null;
  goals?: string | null;
  summary?: string | null;
  next_step?: string | null;
  source?: string | null;
  status: string;
  lost_reason?: string | null;
  updated_at?: string | null;
  created_at?: string | null;
};

const STAGES: LeadStage[] = ["new", "qualified", "proposal_sent", "won", "lost"];
const SOURCES: Lead["source"][] = ["chat", "web", "email", "referral"];
const MONTHS = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"];

export type LeadsResult = { leads: Lead[]; live: boolean };

export async function listLeads(): Promise<LeadsResult> {
  const headers = new Headers({ accept: "application/json" });
  const key = sharedApiKey();
  if (key) headers.set("authorization", `Bearer ${key}`);
  const res = await fetch(`${apiUrl()}/v1/leads?limit=100`, { headers, cache: "no-store" });
  if (res.status === 404) return { leads: sampleLeads, live: false }; // API without the endpoint
  if (!res.ok) throw new Error(`GET /v1/leads → HTTP ${res.status}`);
  const body = (await res.json()) as { items?: ApiLead[] } | ApiLead[];
  const items = Array.isArray(body) ? body : (body.items ?? []);
  return { leads: items.map(toLead), live: true };
}

export function toLead(l: ApiLead): Lead {
  const stage = (STAGES as string[]).includes(l.status) ? (l.status as LeadStage) : "new";
  const source = (SOURCES as string[]).includes(l.source ?? "") ? (l.source as Lead["source"]) : "web";
  const groupSize = l.group_size ?? 0;
  return {
    id: l.id,
    organization: l.account_name ?? l.contact?.organization ?? "Sin organización",
    program: l.program ?? [l.sport, l.gender, l.age_group].filter(Boolean).join(" · "),
    coach: l.contact?.name ?? "",
    sport: l.sport ?? "",
    gender: l.gender ?? "",
    ageGroup: l.age_group ?? "",
    levelScore: l.level_score ?? 0,
    groupSize,
    country: l.destination_country ?? "",
    travelWindow: travelWindow(l.travel_start, l.duration_days),
    valueUsd: (l.budget_per_person_usd ?? 0) * groupSize,
    source,
    stage,
    lostReason: l.lost_reason,
    lastActivity: l.updated_at ?? l.created_at ?? new Date(0).toISOString(),
    agentSummary: l.summary ?? l.goals ?? "Sin resumen del agente todavía.",
    nextStep: l.next_step ?? (l.trip_code ? `${NEXT_STEP[stage]} · ${l.trip_code}` : NEXT_STEP[stage]),
  };
}

const NEXT_STEP: Record<LeadStage, string> = {
  new: "Calificar la consulta",
  qualified: "Armar la propuesta",
  proposal_sent: "Seguimiento con el coach",
  won: "Pasar a operaciones",
  lost: "Registrar aprendizaje",
};

function travelWindow(start?: string | null, days?: number | null): string {
  if (!start) return "Fechas a definir";
  const [y, m] = start.split("-").map(Number);
  const month = MONTHS[(m ?? 1) - 1] ?? "";
  return `${month} ${y}${days ? ` · ${days} días` : ""}`;
}
