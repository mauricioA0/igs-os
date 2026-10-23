import { humanDuration, nodeCatalog, nodeTitle, portLabel, portsOf } from "./catalog";
import type { FlowGraph, FlowNode } from "./types";

// "Pasos" view (docs/reviews/ux/v2-flows.md P1): the same graph read top to bottom as numbered
// Spanish sentences, Zapier-style, so an ops person can follow it without the canvas.

export type Step = {
  number: string; // "1", "3.2", "3.2a.1"
  nodeId: string;
  sentence: string;
  branches: Array<{ port: string; label: string; steps: Step[] }>;
  // Already described elsewhere (loop back or a shared continuation).
  jumpTo?: { nodeId: string; number: string };
};

export function stepsOf(flow: FlowGraph): Step[] {
  const byId = new Map(flow.nodes.map((n) => [n.id, n]));
  const out = new Map<string, Array<{ port: string; to: string }>>();
  for (const e of flow.edges) {
    const list = out.get(e.from) ?? [];
    list.push({ port: e.port ?? "next", to: e.to });
    out.set(e.from, list);
  }
  const numbered = new Map<string, string>();

  const walk = (startId: string, prefix: string): Step[] => {
    const steps: Step[] = [];
    let id: string | undefined = startId;
    let i = 1;
    while (id) {
      const node = byId.get(id);
      if (!node) break;
      const number = prefix ? `${prefix}.${i}` : `${i}`;
      const seen = numbered.get(id);
      if (seen) {
        steps.push({ number, nodeId: id, sentence: `Vuelve al paso ${seen}`, branches: [], jumpTo: { nodeId: id, number: seen } });
        break;
      }
      numbered.set(id, number);
      const edges: Array<{ port: string; to: string }> = out.get(id) ?? [];
      const ports = portsOf(node);
      const single = edges.length === 1 && (edges[0].port === "next" || ports.length === 1);
      const step: Step = { number, nodeId: id, sentence: sentenceFor(node), branches: [] };
      steps.push(step);
      if (single) {
        id = edges[0].to;
        i++;
        continue;
      }
      // Each branch gets its own letter (2.3a.1, 2.3b.1) so numbers never repeat.
      step.branches = edges.map((e, b) => ({ port: e.port, label: portLabel(e.port), steps: walk(e.to, `${number}${String.fromCharCode(97 + b)}`) }));
      break;
    }
    return steps;
  };

  return walk(flow.entry, "");
}

function sentenceFor(node: FlowNode): string {
  const c = node.config ?? {};
  const s = (v: unknown) => (typeof v === "string" && v ? v : undefined);
  const title = nodeTitle(node);
  switch (node.type) {
    case "say":
      return `Decir: “${truncate(s(c.text) ?? title)}”`;
    case "capture":
      return `Esperar la respuesta del usuario${s(c.timeout) ? ` (hasta ${humanDuration(s(c.timeout))})` : ""}`;
    case "choice":
      return `Preguntar con opciones: ${title}`;
    case "agent":
      return c.mode === "conversation"
        ? `Conversar con el agente “${title}” hasta completar los datos`
        : `El agente “${title}” resuelve la tarea${Array.isArray(c.tools) && c.tools.length ? ` con ${c.tools.length} herramientas` : ""}`;
    case "extract":
      return `Extraer datos: ${title}`;
    case "classify":
      return `Clasificar: ${title}`;
    case "knowledge_search":
      return `Buscar en la base de conocimiento: ${title}`;
    case "condition":
      return `Si ${s(c.expression) ?? title}`;
    case "switch":
      return `Según el caso: ${title}`;
    case "set":
      return `Guardar ${c.assign && typeof c.assign === "object" ? Object.keys(c.assign).join(", ") : "variables"}`;
    case "map":
      return `Por cada ítem, correr ${s(c.flow) ?? "un sub-flow"}`;
    case "subflow":
      return `Correr el flow ${s(c.flow) ?? title}`;
    case "wait":
      return c.mode === "until" ? `Esperar hasta la fecha calculada (${title})` : `Esperar ${humanDuration(s(c.duration))}`;
    case "end":
      return c.status === "failed" ? `Terminar con error${s(c.reason) ? `: ${s(c.reason)}` : ""}` : "Terminar";
    case "http":
      return `Llamar a ${s(c.url) ?? "una API externa"}`;
    case "action":
      return `Acción: ${s(c.action) ?? title}`;
    case "send_message":
      return `Enviar ${s(c.channel) === "ops_inbox" ? "aviso a la bandeja de ops" : `mensaje por ${s(c.channel) ?? "canal"}`}: ${title}`;
    case "emit_event":
      return `Publicar el evento ${s(c.event) ?? title}`;
    case "approval":
      return `Pedir aprobación a ${roles(c.assignees)}: “${truncate(s(c.title) ?? title)}”${s(c.expiresAfter) ? ` · vence en ${humanDuration(s(c.expiresAfter))}` : ""}`;
    default:
      return `${nodeCatalog[node.type as keyof typeof nodeCatalog]?.label ?? String(node.type)}: ${title}`;
  }
}

function roles(assignees: unknown): string {
  const r = (assignees as { roles?: string[] } | undefined)?.roles;
  return r?.length ? r.join(", ") : "una persona";
}

function truncate(text: string, max = 90): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}
