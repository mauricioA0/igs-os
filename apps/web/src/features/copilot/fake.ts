import type { CopilotEvent, CopilotTransport, TurnRequest } from "./types";

// Dev-only scripted stream (NEXT_PUBLIC_COPILOT_FAKE=1 or ?copilot=fake): lets the drawer be
// built and demoed without a model or the API. Mirrors the real event schema exactly.

// Mirrors the seeded Lakeshore story (packages/py-common/fixtures/accounts.yaml, int-lak-07/10).
// Dates are relative to now, like the seed (igs_common.seed.anchor), so the demo never goes stale.
const daysAgo = (n: number) => new Date(Date.now() - n * 86_400_000).toISOString();

const LAKESHORE_HISTORY = [
  {
    id: "int-lak-07",
    channel: "email",
    direction: "inbound",
    occurred_at: daysAgo(6),
    subject: "RE: Enrollment invoice — payment delayed",
    excerpt:
      "The US$2,280 in enrollment fees did not go out on the due date. The purchase order has to be re-approved by Robert Haines.",
    stakeholder: "Marcus Feld",
  },
  {
    id: "int-lak-10",
    channel: "email",
    direction: "inbound",
    occurred_at: daysAgo(1),
    subject: "Spring tour — decision by October 31",
    excerpt:
      "We also received a quote from another operator at USD 2,750 per person. I will decide right after the budget meeting.",
    stakeholder: "Robert Haines",
  },
];

const ANSWER =
  "Lakeshore está en **rojo**: los fees de inscripción del equipo (24 × US$95 = US$2.280) vencieron hace una semana " +
  "y no llegaron, porque la PO tiene que volver a aprobarla Robert Haines [1]. El hotel libera el bloqueo de la gira en 9 días. " +
  "Haines decide ese mismo día y tiene una cotización rival de USD 2.750 por persona [2]. " +
  "Para que firmen falta: 1) enviarle la propuesta formal IGS-2711 antes de la reunión de presupuesto (en 6 días), " +
  "2) que la PO salga junto con la inscripción. Dejé el envío pendiente de tu aprobación.";

export function fakeEvents(request: TurnRequest): CopilotEvent[] {
  const accountId =
    request.context.find((c) => c.kind === "account")?.id ?? "acc-lakeshore";
  const events: CopilotEvent[] = [
    { type: "start", run_id: "run-fake", conversation_id: request.conversation_id ?? "conv-fake" },
    { type: "tool_start", call_id: "c1", name: "get_account_brief", input: { account_id: accountId } },
    {
      type: "tool_end",
      call_id: "c1",
      name: "get_account_brief",
      output: { health: "red", reason: "Riesgo abierto: fees de inscripción vencidos (24 × US$95)" },
      is_error: false,
      ms: 180,
    },
    {
      type: "tool_start",
      call_id: "c2",
      name: "search_account_history",
      input: { account_id: accountId, query: "inscripción PO decisión" },
    },
    {
      type: "tool_end",
      call_id: "c2",
      name: "search_account_history",
      output: LAKESHORE_HISTORY,
      is_error: false,
      ms: 240,
    },
    {
      type: "tool_start",
      call_id: "c3",
      name: "send_proposal",
      input: { trip_id: "t-2711", to: "Dana Whitfield", cc: "Robert Haines" },
    },
    {
      type: "tool_end",
      call_id: "c3",
      name: "send_proposal",
      output: {
        status: "approval_required",
        approval_id: "a-fake-1",
        title: "Enviar la propuesta IGS-2711 a Dana Whitfield (copia a Robert Haines)",
        payload_hash: "sha256:fake",
        review_url: "/ops/approvals?id=a-fake-1",
        message: "Nothing was done yet. A person must approve this exact action in IGS OS.",
      },
      is_error: false,
      ms: 95,
    },
    {
      type: "approval_required",
      approval_id: "a-fake-1",
      title: "Enviar la propuesta IGS-2711 a Dana Whitfield (copia a Robert Haines)",
      payload_hash: "sha256:fake",
      review_url: "/ops/approvals?id=a-fake-1",
      message: "Nothing was done yet. A person must approve this exact action in IGS OS.",
    },
  ];
  for (const word of ANSWER.match(/\S+\s*/g) ?? []) events.push({ type: "text", delta: word });
  events.push({
    type: "done",
    run_id: "run-fake",
    conversation_id: request.conversation_id ?? "conv-fake",
    stop_reason: "end_turn",
  });
  return events;
}

export function fakeTransport(delayMs = 35): CopilotTransport {
  return async function* run(request, signal) {
    for (const event of fakeEvents(request)) {
      if (signal.aborted) throw new DOMException("Aborted", "AbortError");
      if (delayMs) await new Promise((r) => setTimeout(r, event.type === "text" ? delayMs : delayMs * 6));
      yield event;
    }
  };
}
