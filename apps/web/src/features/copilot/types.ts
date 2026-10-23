// Wire types for POST /v1/copilot/turns (services/core/src/igs_core/agent/routes.py) and the
// UI state built from them. Keep in sync with igs_core.agent.runtime (TurnRequest, AgentEvent).

export type ContextKind = "trip" | "trip_day" | "lead" | "account" | "flow" | "execution";

export type ContextChip = {
  kind: ContextKind;
  id: string;
  label?: string;
  day?: number;
};

export type TurnRequest = {
  message: string;
  conversation_id?: string;
  context: ContextChip[];
};

export type ApprovalProposal = {
  status: "approval_required";
  approval_id: string;
  title: string;
  payload_hash: string;
  review_url: string;
  message: string;
};

export type CopilotEvent =
  | { type: "start"; run_id: string; conversation_id: string }
  | { type: "text"; delta: string }
  | { type: "tool_start"; call_id: string; name: string; input: unknown }
  | {
      type: "tool_end";
      call_id: string;
      name: string;
      output: unknown;
      is_error: boolean;
      ms: number;
    }
  | ({ type: "approval_required" } & Omit<ApprovalProposal, "status"> & { status?: string })
  | {
      type: "done";
      run_id: string;
      conversation_id: string;
      stop_reason: string;
      cost_usd?: string;
    }
  | { type: "error"; code: string; message: string };

export type ToolStep = {
  callId: string;
  name: string;
  input: unknown;
  status: "running" | "ok" | "error" | "approval";
  ms?: number;
  output?: unknown;
};

/** A passage the answer can cite: an Account 360 interaction or a knowledge-base chunk. */
export type CitationSource = {
  n: number;
  kind: "interaction" | "document";
  /** Chip text, e.g. "Email · 15 oct · Karen Liu". */
  label: string;
  /** Accessible name, e.g. "Fuente 2: email del 15 de octubre de Karen Liu". */
  ariaLabel: string;
  title?: string;
  snippet: string;
  sourceId?: string;
};

export type TurnStatus = "streaming" | "done" | "error";

export type Turn = {
  id: string;
  question: string;
  steps: ToolStep[];
  text: string;
  citations: CitationSource[];
  approvals: ApprovalProposal[];
  status: TurnStatus;
  error?: { code: string; message: string };
};

/** Anything that can run one turn and yield its events (real SSE, fake, test stub). */
export type CopilotTransport = (
  request: TurnRequest,
  signal: AbortSignal,
) => AsyncIterable<CopilotEvent>;
