// Spanish labels for API enums used across the ops panel.

export type Tone = "neutral" | "info" | "success" | "warning" | "danger" | "live";

export const COUNTRY: Record<string, { label: string; dot: string; strip: string }> = {
  Argentina: { label: "Argentina", dot: "bg-argentina", strip: "from-argentina/70" },
  Brazil: { label: "Brasil", dot: "bg-brazil-green", strip: "from-brazil-green/70" },
  "Costa Rica": { label: "Costa Rica", dot: "bg-costa-rica", strip: "from-costa-rica/70" },
  Spain: { label: "España", dot: "bg-spain", strip: "from-spain/70" },
};

export function country(name: string) {
  return COUNTRY[name] ?? { label: name, dot: "bg-muted-foreground", strip: "from-muted" };
}

export const SPORT: Record<string, string> = {
  soccer: "Fútbol",
  rugby: "Rugby",
  field_hockey: "Hockey",
  volleyball: "Vóley",
  basketball: "Básquet",
};

export const GENDER: Record<string, string> = { men: "masc.", women: "fem.", mixed: "mixto" };

export const TRIP_STATUS: Record<string, { label: string; tone: Tone }> = {
  draft: { label: "Borrador", tone: "neutral" },
  proposed: { label: "Propuesta", tone: "info" },
  confirmed: { label: "Confirmada", tone: "success" },
  in_progress: { label: "En curso", tone: "live" },
  completed: { label: "Finalizada", tone: "neutral" },
  cancelled: { label: "Cancelada", tone: "danger" },
};

export const ITEM_STATUS: Record<string, { label: string; tone: Tone }> = {
  pending: { label: "Pendiente", tone: "warning" },
  requested: { label: "Solicitado", tone: "info" },
  confirmed: { label: "Confirmado", tone: "success" },
  completed: { label: "Completado", tone: "neutral" },
  cancelled: { label: "Cancelado", tone: "danger" },
};

export const ITEM_KIND: Record<string, string> = {
  arrival: "Llegada",
  departure: "Salida",
  match: "Partido",
  training: "Entrenamiento",
  experience: "Experiencia",
  free: "Libre",
};

export const SLOT: Record<string, string> = { morning: "Mañana", afternoon: "Tarde", evening: "Noche" };
export const SLOT_ORDER = ["morning", "afternoon", "evening"];

export const HEALTH: Record<string, { label: string; tone: Tone }> = {
  green: { label: "Saludable", tone: "success" },
  amber: { label: "Atención", tone: "warning" },
  red: { label: "En riesgo", tone: "danger" },
};

export const ACCOUNT_STATUS: Record<string, string> = {
  prospect: "Prospecto",
  active: "Activo",
  past: "Pasado",
  churned: "Perdido",
};

export const ACCOUNT_KIND: Record<string, string> = {
  university: "Universidad",
  club: "Club",
  high_school: "Colegio",
  family_group: "Grupo familiar",
};

export const ROLE: Record<string, string> = {
  decision_maker: "Decide",
  champion: "Promotor",
  athletic_director: "Director deportivo",
  coach: "Coach",
  assistant_coach: "Asistente",
  compliance: "Compliance",
  travel_coordinator: "Viajes",
  finance: "Finanzas",
  parent_liaison: "Enlace padres",
  other: "Otro",
};

// Who decides first, then who influences.
export const ROLE_ORDER = [
  "decision_maker",
  "athletic_director",
  "champion",
  "coach",
  "finance",
  "compliance",
  "travel_coordinator",
  "assistant_coach",
  "parent_liaison",
  "other",
];

export const SENTIMENT: Record<string, { label: string; tone: Tone }> = {
  positive: { label: "Positivo", tone: "success" },
  neutral: { label: "Neutral", tone: "neutral" },
  negative: { label: "Negativo", tone: "danger" },
  unknown: { label: "Sin datos", tone: "neutral" },
};

export const FACT_KIND: Record<string, { label: string; tone: Tone }> = {
  risk: { label: "Riesgo", tone: "danger" },
  commitment: { label: "Compromiso", tone: "info" },
  decision: { label: "Decisión", tone: "success" },
  budget: { label: "Presupuesto", tone: "neutral" },
  preference: { label: "Preferencia", tone: "neutral" },
  status: { label: "Estado", tone: "neutral" },
};

export const CHANNEL: Record<string, string> = {
  email: "Email",
  call: "Llamada",
  meeting: "Reunión",
  chat: "Chat",
  whatsapp: "WhatsApp",
  note: "Nota",
};

export const RISK_CLASS: Record<string, { label: string; tone: Tone }> = {
  read: { label: "Lectura", tone: "neutral" },
  internal_write: { label: "Interna", tone: "info" },
  external: { label: "Externa", tone: "warning" },
};

const PROGRAM_GENDER: Record<string, string> = { womens: "fem.", mens: "masc.", girls: "fem.", boys: "masc." };

/** "womens_soccer" → "Fútbol fem.", "boys_soccer_u17" → "Fútbol masc. U17". */
export function programLabel(slug: string): string {
  const parts = slug.split("_");
  const gender = PROGRAM_GENDER[parts[0]];
  const rest = gender ? parts.slice(1) : parts;
  const age = rest.at(-1)?.match(/^u\d+$/i) ? rest.pop()!.toUpperCase() : undefined;
  const sport = rest.join("_");
  return [SPORT[sport] ?? sport.replace(/_/g, " "), gender, age].filter(Boolean).join(" ");
}
