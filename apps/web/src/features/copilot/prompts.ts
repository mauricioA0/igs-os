import type { Screen } from "./context";

/** The demo's anchor question (docs/design/demo-script.md, reviews/ux v4 P3). */
export const LAKESHORE_QUESTION = "¿Cómo está Lakeshore y qué falta para que firmen?";

// Suggested prompts per screen (docs/design/copilot.md §6). The same strings seed the evals.
const PROMPTS: Record<Screen, string[]> = {
  today: [
    LAKESHORE_QUESTION,
    "¿Qué necesita mi atención hoy?",
    "¿Qué proveedores no confirmaron para las salidas de esta semana?",
  ],
  trips: [
    "¿Qué giras salen en los próximos 30 días con ítems sin confirmar?",
    LAKESHORE_QUESTION,
  ],
  trip: [
    "Resumime esta gira y lo que falta confirmar.",
    "¿Qué rival alternativo hay para el partido del día 6?",
    "Prepará el mensaje para pedir confirmación al proveedor de transporte.",
  ],
  accounts: [
    "¿Qué clientes están en rojo y por qué?",
    LAKESHORE_QUESTION,
  ],
  account: [
    LAKESHORE_QUESTION,
    "¿Quién decide en este cliente y cuándo hablamos por última vez?",
    "¿Qué compromisos tenemos abiertos con este cliente?",
  ],
  approvals: [
    "¿Qué aprobaciones vencen hoy?",
    "Explicame qué pasa si apruebo la primera pendiente.",
  ],
  flows: ["¿Qué flows fallaron esta semana?", "¿Qué automatizaciones están esperando a una persona?"],
  flow: ["¿Qué hace este flow, paso a paso?", "¿Por qué falló la última ejecución?"],
  leads: ["¿Qué leads no tuvieron respuesta en 3 días?", LAKESHORE_QUESTION],
  other: [LAKESHORE_QUESTION, "¿Qué necesita mi atención hoy?"],
};

export function promptsFor(screen: Screen): string[] {
  return PROMPTS[screen] ?? PROMPTS.other;
}
