// Generated from packages/flow-schema/flow.schema.json by scripts/gen.sh. Do not edit.

export type Slug = string;

/** A string that may contain {{ CEL expression }} placeholders. A string that is exactly one placeholder evaluates to the expression's typed value; otherwise placeholders are rendered and concatenated as text. */
export type Template = string;

/** A CEL expression without the {{ }} delimiters. Must evaluate to the type the field documents. */
export type Expression = string;

/** ISO 8601 duration, e.g. PT30S, PT15M, P2D. */
export type IsoDuration = string;

/** Named inputs; each value is a template (typed when it is a single placeholder) or a literal. */
export type ValueMap = Record<string, unknown>;

/** Name of a secret in the tenant's secret store. Secrets are never readable from expressions. */
export type SecretRef = string;

/** Provider-neutral model reference. The tenant's model registry maps each role to a concrete provider model id, so flows never hardcode vendor model names. */
export type ModelRef = {
  /** agent = tool-using default; fast = cheap extraction/classification; reasoning = hardest planning tasks. */
  role: "agent" | "fast" | "reasoning";
};

/** An embedded JSON Schema (object type) describing structured data the node must produce or accept. */
export type JsonSchemaObject = {
  type: "object";
};

export type Variable = {
  name: string;
  type: "string" | "number" | "integer" | "boolean" | "object" | "array" | "timestamp";
  default?: unknown;
  description?: string;
  /** Redacted in execution logs and transcripts. */
  sensitive?: boolean;
};

export type Edge = {
  id?: Slug;
  /** Source node id. */
  from: Slug;
  /** Output port of the source node. Valid ports depend on the node type (see the spec). */
  port?: string;
  /** Target node id. */
  to: Slug;
};

export type Settings = {
  /** Hard limit for the whole execution, including waits. Default P30D. */
  timeout?: IsoDuration;
  maxSteps?: number;
  /** Flow started (latest published version) when an execution fails. */
  errorFlow?: Slug;
  concurrency?: {
    /** Executions with the same rendered key are serialized or rejected. */
    key: Template;
    mode?: "queue" | "reject" | "replace";
  };
  dedupe?: {
    /** Trigger-level idempotency key; a second trigger with the same key within the window starts nothing. */
    key: Template;
    window?: IsoDuration;
  };
  conversation?: {
    idleTimeout?: IsoDuration;
    /** Global intents checked on every user message before it reaches the waiting node (Voiceflow-style global intents). */
    interrupts?: Array<{
      id: Slug;
      description: string;
      examples?: Array<string>;
      goTo: Slug;
      /** After the interrupt path reaches an end node, return to the node that was waiting. */
      resume?: boolean;
    }>;
  };
  /** How long execution data is kept. Default P90D. */
  retention?: IsoDuration;
};

export type Trigger = ManualTrigger | ChatTrigger | WebhookTrigger | ScheduleTrigger | EventTrigger;

export type ManualTrigger = {
  type: "manual";
  input?: JsonSchemaObject;
};

export type ChatTrigger = {
  type: "chat";
  channels?: Array<"web" | "whatsapp" | "email">;
};

export type WebhookTrigger = {
  type: "webhook";
  path: Slug;
  auth: {
    mode: "hmac" | "bearer" | "none";
    secret?: SecretRef;
  };
  input?: JsonSchemaObject;
  /** immediately = 202 with the execution id; on_end = wait (max 30 s) and return the end node's output. */
  respond?: "immediately" | "on_end";
};

export type ScheduleTrigger = {
  type: "schedule";
  cron: string;
  timezone?: string;
};

export type EventTrigger = {
  type: "event";
  event: "lead.created" | "lead.status_changed" | "trip.created" | "trip.status_changed" | "trip_item.status_changed" | "approval.decided" | "document.ingested";
  /** CEL boolean over `trigger`; the flow starts only when true. */
  filter?: Expression;
};

export type Retry = {
  maxAttempts?: number;
  initialInterval?: IsoDuration;
  backoffCoefficient?: number;
  maxInterval?: IsoDuration;
  /** Error classes that skip remaining attempts. validation and expression are always non-retryable. */
  nonRetryable?: Array<"validation" | "expression" | "auth" | "not_found" | "conflict" | "rate_limited" | "timeout" | "upstream" | "refused">;
};

export type NodeBase = {
  id: Slug;
  type: string;
  name?: string;
  notes?: string;
  /** Disabled nodes pass their input through the `next` port. */
  disabled?: boolean;
  retry?: Retry;
  /** Per-attempt timeout for the node's activity. */
  timeout?: IsoDuration;
  /** After retries are exhausted: fail the execution, continue through `next` with output {error}, or route to the `error` port. */
  onError?: "fail" | "continue" | "branch";
  position?: {
    x: number;
    y: number;
  };
};

export type Node = AgentNode | ExtractNode | ClassifyNode | KnowledgeSearchNode | SayNode | CaptureNode | ChoiceNode | ConditionNode | SwitchNode | SetNode | MapNode | SubflowNode | WaitNode | EndNode | HttpNode | ActionNode | SendMessageNode | EmitEventNode | ApprovalNode;

export type AgentNode = NodeBase & {
  type: "agent";
  config: {
    /** task = one autonomous run on `input`; conversation = talks with the user across turns until `exit` is satisfied. */
    mode: "task" | "conversation";
    instructions: Template;
    /** task mode: the work item handed to the agent. */
    input?: Template;
    /** Names from the tool registry (the same tools the MCP server exposes). */
    tools?: Array<string>;
    knowledgeBases?: Array<Slug>;
    model?: ModelRef;
    /** Provider-neutral reasoning effort; the LLM layer maps it to the provider setting. */
    effort?: "low" | "medium" | "high";
    maxIterations?: number;
    /** task mode: structured result the agent must return. */
    output?: JsonSchemaObject;
    /** conversation mode: the agent leaves through `completed` once it can fill `output`. */
    exit?: {
      description?: string;
      output: JsonSchemaObject;
      maxTurns?: number;
      /** When the agent should leave through `handoff` (e.g. the user asks for a human). */
      handoffWhen?: string;
    };
    /** Tools whose calls pause for human approval before running. */
    approvalRequiredFor?: Array<string>;
  };
};

export type ExtractNode = NodeBase & {
  type: "extract";
  config: {
    input: Template;
    instructions?: Template;
    schema: JsonSchemaObject;
    model?: ModelRef;
  };
};

export type ClassifyNode = NodeBase & {
  type: "classify";
  config: {
    input: Template;
    instructions?: Template;
    classes: Array<{
      id: Slug;
      description: string;
      examples?: Array<string>;
    }>;
    model?: ModelRef;
  };
};

export type KnowledgeSearchNode = NodeBase & {
  type: "knowledge_search";
  config: {
    query: Template;
    knowledgeBases: Array<Slug>;
    topK?: number;
    /** Payload filters, e.g. {"country": "{{ vars.country }}"}. */
    filters?: ValueMap;
    rerank?: boolean;
    minScore?: number;
  };
};

export type SayNode = NodeBase & {
  type: "say";
  config: {
    text: Template;
    /** Alternative phrasings; one is picked deterministically per execution. */
    variants?: Array<Template>;
    attachments?: Array<{
      kind: "link" | "image" | "file";
      url: Template;
      title?: Template;
    }>;
  };
};

export type CaptureNode = NodeBase & {
  type: "capture";
  config: {
    /** Optional message sent before waiting (saves a separate say node). */
    prompt?: Template;
    variable: string;
    /** If set, the reply is parsed into this structure (LLM-backed slot filling); missing required fields re-prompt. */
    extract?: JsonSchemaObject;
    reprompt?: Template;
    maxAttempts?: number;
    waitFor?: IsoDuration;
  };
};

export type ChoiceNode = NodeBase & {
  type: "choice";
  config: {
    prompt: Template;
    options: Array<{
      id: Slug;
      label: Template;
      synonyms?: Array<string>;
    }>;
    /** classify = map free text to an option with an LLM; no_match = route to the no_match port. */
    freeText?: "classify" | "no_match";
    waitFor?: IsoDuration;
  };
};

export type ConditionNode = NodeBase & {
  type: "condition";
  config: {
    expression: Expression;
  };
};

export type SwitchNode = NodeBase & {
  type: "switch";
  config: {
    cases: Array<{
      id: Slug;
      expression: Expression;
    }>;
  };
};

export type SetNode = NodeBase & {
  type: "set";
  config: {
    assign: ValueMap;
  };
};

export type MapNode = NodeBase & {
  type: "map";
  config: {
    /** Must evaluate to a list (max 1000 items). */
    items: Template;
    /** Sub-flow run once per item (child execution). */
    flow: Slug;
    /** `published` is resolved to a number when the parent execution starts. */
    version?: "published" | number;
    itemInput?: string;
    inputs?: ValueMap;
    concurrency?: number;
    failFast?: boolean;
  };
};

export type SubflowNode = NodeBase & {
  type: "subflow";
  config: {
    flow: Slug;
    version?: "published" | number;
    inputs?: ValueMap;
    /** false = fire and forget (output is the child execution id). */
    wait?: boolean;
  };
};

export type WaitNode = NodeBase & {
  type: "wait";
  config: {
    mode: "duration" | "until";
    duration?: IsoDuration;
    /** Must evaluate to a timestamp. A time in the past continues immediately. */
    until?: Template;
  };
};

export type EndNode = NodeBase & {
  type: "end";
  config?: {
    status?: "completed" | "failed";
    output?: ValueMap;
    reason?: Template;
  };
};

export type HttpNode = NodeBase & {
  type: "http";
  config: {
    method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
    /** Host must be in the tenant egress allowlist. */
    url: Template;
    headers?: ValueMap;
    query?: ValueMap;
    /** Template string, or an object whose string leaves are templates. */
    body?: unknown;
    auth?: {
      mode: "bearer" | "basic" | "header" | "hmac";
      secret: SecretRef;
      header?: string;
    };
    successStatus?: Array<number>;
    /** Adds Idempotency-Key: <execution>:<node>:<iteration> to non-GET requests. */
    sendIdempotencyKey?: boolean;
  };
};

export type ActionNode = NodeBase & {
  type: "action";
  config: {
    /** Domain action from the action registry. Inputs are validated against the action's own schema at publish time. */
    action: "create_lead" | "update_lead_status" | "draft_trip" | "get_trip" | "list_trip_items" | "update_trip_item" | "swap_opponent" | "set_trip_status" | "request_provider_confirmations" | "send_proposal" | "create_ops_task" | "check_trip_readiness";
    inputs?: ValueMap;
  };
};

export type SendMessageNode = NodeBase & {
  type: "send_message";
  config: {
    channel: "email" | "chat" | "ops_inbox" | "whatsapp";
    to: Template;
    subject?: Template;
    body: Template;
    attachments?: Array<Template>;
  };
};

export type EmitEventNode = NodeBase & {
  type: "emit_event";
  config: {
    /** Flows may only emit custom.* events; domain events come from the domain layer. */
    event: string;
    payload?: ValueMap;
  };
};

export type ApprovalNode = NodeBase & {
  type: "approval";
  config: {
    title: Template;
    description?: Template;
    links?: Array<{
      label: string;
      url: Template;
    }>;
    assignees: {
      roles?: Array<"ops" | "sales" | "admin">;
      users?: Array<string>;
    };
    /** Extra fields the approver fills (e.g. a discount, a comment). */
    form?: JsonSchemaObject;
    expiresAfter: IsoDuration;
    remindEvery?: IsoDuration;
  };
};

/** A versioned directed graph of nodes started by one trigger. See docs/architecture/flow-engine.md. Structural rules that JSON Schema cannot express (unique ids, edge endpoints, valid ports per node type, reachability, expression syntax) are enforced by the publish-time validator. */
export type FlowDefinition = {
  $schema?: string;
  schemaVersion: "1";
  /** Stable flow id, unique per tenant. */
  id: Slug;
  name: string;
  description?: string;
  /** Assigned by the server on publish (1, 2, 3...). null while the definition is a draft. */
  version?: number | null;
  trigger: Trigger;
  /** Id of the first node executed after the trigger fires. */
  entry: Slug;
  variables?: Array<Variable>;
  nodes: Array<Node>;
  edges: Array<Edge>;
  settings?: Settings;
};

export type FlowNode = Node;
export type FlowNodeType = FlowNode["type"];
export type FlowTrigger = Trigger;
