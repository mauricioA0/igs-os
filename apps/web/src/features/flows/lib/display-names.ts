// Spanish display names for the ops UI (QA D-07). Stored flow definitions keep their ids and
// English names; the ops team reads Spanish. Unknown flows/nodes fall back to the stored name.

const FLOW_NAMES: Record<string, { name: string; description?: string }> = {
  "inbound-inquiry": {
    name: "Consulta entrante de un coach",
    description:
      "Un coach escribe; el agente califica la gira, crea el lead y un borrador de viaje, y ops aprueba la propuesta antes de enviarla.",
  },
  "pre-departure-check": {
    name: "Control previo a la salida",
    description:
      "Con la gira confirmada, espera hasta 30 días antes de salir, pide confirmación a cada proveedor y escala a ops lo que falte.",
  },
  "post-match-report": {
    name: "Reporte post-partido",
    description: "Cuando un partido se completa, un agente redacta el reporte para el coach con lo que cargó el tour leader.",
  },
};

const NODE_NAMES: Record<string, string> = {
  // inbound-inquiry
  greet: "Saludo",
  qualify: "Calificar la consulta",
  create_lead: "Crear el lead",
  remember_lead: "Guardar el lead",
  draft_trip: "Armar el borrador de gira",
  remember_trip: "Guardar la gira",
  tell_in_review: "Avisar: en revisión",
  ops_review: "Aprobación de ops",
  send_proposal: "Enviar la propuesta",
  tell_sent: "Avisar: propuesta enviada",
  rejected_task: "Seguimiento si se rechaza",
  tell_personal_followup: "Avisar: seguimiento personal",
  expired_task: "Seguimiento si vence",
  handoff_task: "Derivar a una persona",
  tell_handoff: "Avisar: derivado",
  draft_failed: "Falló el borrador",
  done: "Fin",
  // post-match-report
  load_trip: "Cargar la gira",
  opponent_context: "Contexto del rival",
  write_report: "Redactar el reporte",
  email_coach: "Enviar al coach",
  email_failed: "Falló el envío",
  sent: "Enviado",
  handed_to_ops: "Derivado a ops",
  // pre-departure-check
  wait_until_t_minus_30: "Esperar hasta 30 días antes",
  reload_trip: "Recargar la gira",
  still_confirmed: "¿Sigue confirmada?",
  request_confirmations: "Pedir confirmaciones",
  give_providers_48h: "Dar 48 h a proveedores",
  list_unconfirmed: "Listar sin confirmar",
  anything_missing: "¿Falta algo?",
  escalate: "Escalar a ops",
  notify_ops: "Avisar a ops",
  all_confirmed: "Todo confirmado",
  escalated: "Escalado",
  trip_changed: "La gira cambió",
};

export function flowDisplayName(key: string, stored: string): string {
  return FLOW_NAMES[key]?.name ?? stored;
}

export function flowDisplayDescription(key: string, stored: string): string {
  return FLOW_NAMES[key]?.description ?? stored;
}

export function nodeDisplayName(id: string, stored?: string | null): string {
  return NODE_NAMES[id] ?? stored ?? id.replace(/_/g, " ");
}
