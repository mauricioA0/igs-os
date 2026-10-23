import type { FlowNode, FlowNodeType } from "./types";
import { nodeDisplayName } from "./display-names";

export type Category = "ai" | "conversation" | "logic" | "integration" | "human";

// Category is told apart by shape and glyph; color is reserved for run/validation state
// (docs/reviews/ux/v5-visual-system.md P3).
export const categories: Record<Category, { label: string; shape: string; mark: string }> = {
  ai: { label: "IA", shape: "rounded-xl", mark: "✦" },
  conversation: { label: "Conversación", shape: "rounded-2xl rounded-bl-sm", mark: "❝" },
  logic: { label: "Lógica", shape: "rounded-none", mark: "◇" },
  integration: { label: "Integración", shape: "rounded-sm border-l-4", mark: "⇄" },
  human: { label: "Persona", shape: "rounded-md outline outline-2 outline-offset-2 outline-border", mark: "✋" },
};

type Spec = {
  category: Category;
  label: string;
  glyph: string;
  description: string;
  ports: (node: FlowNode) => string[];
};

const next = () => ["next"];
const ids = (v: unknown) => ((v as Array<{ id: string }> | undefined) ?? []).map((x) => x.id);

// Mirrors docs/architecture/flow-engine.md §7. `error` is added when onError = branch.
export const nodeCatalog: Record<FlowNodeType, Spec> = {
  agent: {
    category: "ai",
    label: "Agente",
    glyph: "✦",
    description: "Modelo con herramientas y conocimiento, como tarea o conversación",
    ports: (n) => (n.config?.mode === "conversation" ? ["completed", "handoff"] : ["next"]),
  },
  extract: { category: "ai", label: "Extraer", glyph: "⌗", description: "Datos estructurados a partir de texto", ports: next },
  classify: {
    category: "ai",
    label: "Clasificar",
    glyph: "⑂",
    description: "Elegir un camino según el significado",
    ports: (n) => [...ids(n.config?.classes), "default"],
  },
  knowledge_search: { category: "ai", label: "Conocimiento", glyph: "⌕", description: "Búsqueda en la base de conocimiento", ports: next },
  say: { category: "conversation", label: "Decir", glyph: "❝", description: "Enviar un mensaje", ports: next },
  capture: { category: "conversation", label: "Capturar", glyph: "✎", description: "Esperar la respuesta del usuario", ports: () => ["next", "timeout"] },
  choice: {
    category: "conversation",
    label: "Opciones",
    glyph: "☰",
    description: "Preguntar con opciones",
    ports: (n) => [...ids(n.config?.options), "no_match", "timeout"],
  },
  condition: { category: "logic", label: "Condición", glyph: "◇", description: "Bifurcación sí/no (CEL)", ports: () => ["true", "false"] },
  switch: {
    category: "logic",
    label: "Switch",
    glyph: "⋔",
    description: "El primer caso que coincide",
    ports: (n) => [...ids(n.config?.cases), "default"],
  },
  set: { category: "logic", label: "Variables", glyph: "≔", description: "Asignar variables", ports: next },
  map: { category: "logic", label: "Por cada uno", glyph: "⟳", description: "Correr un sub-flow por ítem", ports: next },
  subflow: { category: "logic", label: "Sub-flow", glyph: "⧉", description: "Llamar a otro flow", ports: next },
  wait: { category: "logic", label: "Esperar", glyph: "◷", description: "Timer durable", ports: next },
  end: { category: "logic", label: "Fin", glyph: "■", description: "Terminar la ejecución", ports: () => [] },
  http: { category: "integration", label: "HTTP", glyph: "⇄", description: "Llamar a una API habilitada", ports: next },
  action: { category: "integration", label: "Acción", glyph: "▶", description: "Acción del dominio registrada", ports: next },
  send_message: { category: "integration", label: "Mensaje", glyph: "✉", description: "Email, chat o bandeja de ops", ports: next },
  emit_event: { category: "integration", label: "Evento", glyph: "⚑", description: "Publicar un evento", ports: next },
  approval: {
    category: "human",
    label: "Aprobación",
    glyph: "✋",
    description: "Pausar hasta que una persona decida",
    ports: () => ["approved", "rejected", "expired"],
  },
};

export const portLabels: Record<string, string> = {
  next: "sigue",
  true: "sí",
  false: "no",
  approved: "aprobado",
  rejected: "rechazado",
  expired: "vencido",
  timeout: "sin respuesta",
  no_match: "no coincide",
  default: "otro",
  completed: "completó",
  handoff: "derivar",
  error: "error",
};

export const portLabel = (p: string) => portLabels[p] ?? p;

export function portsOf(node: FlowNode): string[] {
  const ports = nodeCatalog[node.type]?.ports(node) ?? ["next"];
  return node.onError === "branch" ? [...ports, "error"] : ports;
}

export function nodeTitle(node: FlowNode): string {
  return nodeDisplayName(node.id, node.name);
}

// Short summary of the node's main setting for the canvas card.
export function nodeSummary(node: FlowNode): string | undefined {
  const c = node.config ?? {};
  const str = (v: unknown) => (typeof v === "string" ? v : undefined);
  switch (node.type) {
    case "say":
      return str(c.text);
    case "agent": {
      const model = c.model && typeof c.model === "object" ? (c.model as { role?: string }).role : str(c.model);
      return [model && `modelo: ${model}`, Array.isArray(c.tools) ? `${c.tools.length} herramientas` : undefined].filter(Boolean).join(" · ");
    }
    case "action":
      return str(c.action);
    case "condition":
      return str(c.expression);
    case "wait":
      return c.mode === "until" ? `hasta ${str(c.until)}` : `durante ${humanDuration(str(c.duration))}`;
    case "approval":
      return str(c.title);
    case "send_message":
      return [str(c.channel), str(c.subject)].filter(Boolean).join(" · ");
    case "knowledge_search":
      return Array.isArray(c.knowledgeBases) ? `KB: ${c.knowledgeBases.join(", ")}` : undefined;
    case "set":
      return c.assign && typeof c.assign === "object" ? Object.keys(c.assign).join(", ") : undefined;
    case "end":
      return str(c.reason);
    default:
      return undefined;
  }
}

// ISO-8601 durations as people say them: PT48H → "48 h", P2D → "2 días".
export function humanDuration(iso: string | undefined): string {
  if (!iso) return "—";
  const m = /^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$/.exec(iso);
  if (!m) return iso;
  const [, d, h, min, s] = m.map((x) => (x ? Number(x) : 0));
  const parts = [d && `${d} ${d === 1 ? "día" : "días"}`, h && `${h} h`, min && `${min} min`, s && `${s} s`].filter(Boolean);
  return parts.length ? parts.join(" ") : iso;
}

export const paletteGroups: Array<{ category: Category; types: FlowNodeType[] }> = [
  { category: "ai", types: ["agent", "extract", "classify", "knowledge_search"] },
  { category: "conversation", types: ["say", "capture", "choice"] },
  { category: "logic", types: ["condition", "switch", "set", "wait", "map", "subflow", "end"] },
  { category: "integration", types: ["action", "http", "send_message", "emit_event"] },
  { category: "human", types: ["approval"] },
];

export function triggerLabel(trigger: { type: string } & Record<string, unknown>): string {
  switch (trigger.type) {
    case "chat":
      return `Mensaje de chat (${(trigger.channels as string[] | undefined)?.join(", ") ?? "cualquier canal"})`;
    case "event":
      return `Evento · ${String(trigger.event)}`;
    case "cron":
      return `Programado · ${String(trigger.schedule ?? trigger.cron ?? "")}`;
    case "webhook":
      return "Webhook";
    default:
      return "Manual";
  }
}

export function defaultConfig(type: FlowNodeType): Record<string, unknown> {
  switch (type) {
    case "agent":
      return { mode: "task", instructions: "", input: "", tools: [], model: { role: "agent" }, effort: "low" };
    case "say":
      return { text: "" };
    case "condition":
      return { expression: "true" };
    case "wait":
      return { mode: "duration", duration: "PT1H" };
    case "action":
      return { action: "create_ops_task", inputs: { title: "" } };
    case "approval":
      return { title: "", assignees: { roles: ["ops"] }, expiresAfter: "P2D" };
    case "send_message":
      return { channel: "ops_inbox", to: "ops", body: "" };
    case "knowledge_search":
      return { query: "", knowledgeBases: ["policies"], topK: 4 };
    default:
      return {};
  }
}
