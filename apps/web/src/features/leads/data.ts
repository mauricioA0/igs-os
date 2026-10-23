// Board model + sample leads. The board runs on `GET /v1/leads` (see ./api.ts); the samples are
// only a fallback for an API without the leads endpoint, and the page says so on screen.

export type LeadStage = "new" | "qualified" | "proposal_sent" | "won" | "lost";

export type Lead = {
  id: string;
  organization: string;
  program: string;
  coach: string;
  sport: string;
  gender: string;
  ageGroup: string;
  levelScore: number;
  groupSize: number;
  country: string;
  travelWindow: string;
  valueUsd: number;
  source: "chat" | "web" | "email" | "referral";
  stage: LeadStage;
  lostReason?: string | null;
  lastActivity: string; // ISO datetime
  agentSummary: string;
  nextStep: string;
};

export const LEAD_STAGE: Record<LeadStage, string> = {
  new: "Nuevo",
  qualified: "Calificado",
  proposal_sent: "Propuesta enviada",
  won: "Ganado",
  lost: "Perdido",
};

export const leads: Lead[] = [
  {
    id: "l-501", organization: "Brookfield University", program: "Women's Soccer", coach: "Coach Sarah Okafor",
    sport: "soccer", gender: "women", ageGroup: "college", levelScore: 7, groupSize: 25, country: "Argentina",
    travelWindow: "Marzo 2027 · 10 días", valueUsd: 72250, source: "chat", stage: "qualified",
    lastActivity: "2026-10-22T09:41:00-03:00",
    agentSummary: "D1, quiere 3 partidos exigentes y 1 accesible. Pidió foco en video análisis. Presupuesto USD 2.900 pp.",
    nextStep: "Propuesta lista, esperando aprobación de ops",
  },
  {
    id: "l-502", organization: "Cedar Ridge HS", program: "Boys Varsity Soccer", coach: "Coach Diego Alvarez",
    sport: "soccer", gender: "men", ageGroup: "U17", levelScore: 5, groupSize: 30, country: "Costa Rica",
    travelWindow: "Junio 2027 · 8 días", valueUsd: 66000, source: "web", stage: "new",
    lastActivity: "2026-10-22T08:05:00-03:00",
    agentSummary: "Formulario web. Faltan fechas exactas y presupuesto. Pregunta por seguro médico para menores.",
    nextStep: "El agente pidió fechas y presupuesto por mail",
  },
  {
    id: "l-503", organization: "Maple Grove College", program: "Men's Rugby", coach: "Coach Liam O'Connor",
    sport: "rugby", gender: "men", ageGroup: "college", levelScore: 7, groupSize: 34, country: "Argentina",
    travelWindow: "Agosto 2027 · 12 días", valueUsd: 98600, source: "referral", stage: "new",
    lastActivity: "2026-10-21T18:30:00-03:00",
    agentSummary: "Referido por Northfield. Quiere jugar contra clubes de zona norte. Grupo grande: 2 buses.",
    nextStep: "Calificar nivel y confirmar fechas",
  },
  {
    id: "l-504", organization: "Eastview University", program: "Women's Basketball", coach: "Coach Nia Brooks",
    sport: "basketball", gender: "women", ageGroup: "college", levelScore: 6, groupSize: 15, country: "Argentina",
    travelWindow: "Mayo 2027 · 9 días", valueUsd: 37500, source: "email", stage: "qualified",
    lastActivity: "2026-10-21T15:12:00-03:00",
    agentSummary: "Catálogo de rivales femeninos de básquet limitado en BA. Sugerir 2 partidos + clínica.",
    nextStep: "Ops valida rivales disponibles",
  },
  {
    id: "l-505", organization: "Westbrook College", program: "Women's Field Hockey", coach: "Coach Emma Lawson",
    sport: "field_hockey", gender: "women", ageGroup: "college", levelScore: 6, groupSize: 20, country: "Argentina",
    travelWindow: "Marzo 2027 · 10 días", valueUsd: 52800, source: "chat", stage: "proposal_sent",
    lastActivity: "2026-10-20T11:00:00-03:00",
    agentSummary: "Propuesta IGS-2720 enviada. La coach abrió el link 3 veces. Preguntó por visa (no requiere).",
    nextStep: "Seguimiento automático en 2 días",
  },
  {
    id: "l-506", organization: "Harbor State University", program: "Women's Volleyball", coach: "Coach Priya Natarajan",
    sport: "volleyball", gender: "women", ageGroup: "college", levelScore: 6, groupSize: 16, country: "Argentina",
    travelWindow: "Mayo 2027 · 10 días", valueUsd: 39680, source: "web", stage: "proposal_sent",
    lastActivity: "2026-10-19T16:45:00-03:00",
    agentSummary: "Propuesta IGS-2726 enviada. Pidió opción con 3 partidos en lugar de 2.",
    nextStep: "Ajustar itinerario y reenviar",
  },
  {
    id: "l-507", organization: "Pine Valley College", program: "Men's Soccer", coach: "Coach Tom Becker",
    sport: "soccer", gender: "men", ageGroup: "college", levelScore: 5, groupSize: 23, country: "Costa Rica",
    travelWindow: "Enero 2027 · 9 días", valueUsd: 54050, source: "email", stage: "proposal_sent",
    lastActivity: "2026-10-18T10:20:00-03:00",
    agentSummary: "Borrador IGS-2723 en armado. Quiere día de servicio comunitario.",
    nextStep: "Completar itinerario",
  },
  {
    id: "l-508", organization: "Lakeshore University", program: "Women's Soccer", coach: "Coach Dana Whitfield",
    sport: "soccer", gender: "women", ageGroup: "college", levelScore: 7, groupSize: 24, country: "Argentina",
    travelWindow: "Noviembre 2026", valueUsd: 69360, source: "referral", stage: "won",
    lastActivity: "2026-09-30T12:00:00-03:00",
    agentSummary: "Inscripción y primeras cuotas recibidas. Gira IGS-2711.", nextStep: "Control pre-salida en curso",
  },
  {
    id: "l-509", organization: "Riverside FC Academy", program: "U17 Boys", coach: "Coach Marcus Hale",
    sport: "soccer", gender: "men", ageGroup: "U17", levelScore: 7, groupSize: 22, country: "Brazil",
    travelWindow: "Diciembre 2026", valueUsd: 69960, source: "chat", stage: "won",
    lastActivity: "2026-09-12T09:00:00-03:00",
    agentSummary: "Inscripción recibida. Gira IGS-2715.", nextStep: "Saldo vence 21 oct",
  },
  {
    id: "l-510", organization: "Northfield College", program: "Men's Soccer", coach: "Coach Ryan Mitchell",
    sport: "soccer", gender: "men", ageGroup: "college", levelScore: 6, groupSize: 26, country: "Argentina",
    travelWindow: "Octubre 2026", valueUsd: 72540, source: "web", stage: "won",
    lastActivity: "2026-08-02T09:00:00-03:00",
    agentSummary: "Pagado al 100%. Gira en curso IGS-2709.", nextStep: "—",
  },
  {
    id: "l-511", organization: "Granite Bay Rugby Club", program: "U19 Men", coach: "Coach Ben Carter",
    sport: "rugby", gender: "men", ageGroup: "U19", levelScore: 6, groupSize: 28, country: "Argentina",
    travelWindow: "Julio 2026", valueUsd: 75600, source: "email", stage: "lost",
    lastActivity: "2026-06-10T09:00:00-03:00",
    agentSummary: "Eligió un tour en Nueva Zelanda por fechas. Reactivar para 2027.", nextStep: "Recordatorio en enero",
  },
];
