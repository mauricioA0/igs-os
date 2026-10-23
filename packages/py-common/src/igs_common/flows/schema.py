# Generated from packages/flow-schema/flow.schema.json by scripts/gen.sh. Do not edit.
# ruff: noqa: E501
# pyright: reportAssignmentType=false, reportIncompatibleVariableOverride=false

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, StringConstraints


class Slug(RootModel[str]):
    root: Annotated[str, Field(pattern="^[a-z][a-z0-9_-]{0,62}$")]


class Template(RootModel[str]):
    root: Annotated[
        str,
        Field(
            description="A string that may contain {{ CEL expression }} placeholders. A string that is exactly one placeholder evaluates to the expression's typed value; otherwise placeholders are rendered and concatenated as text.",
            max_length=20000,
        ),
    ]


class Expression(RootModel[str]):
    root: Annotated[
        str,
        Field(
            description="A CEL expression without the {{ }} delimiters. Must evaluate to the type the field documents.",
            max_length=4000,
            min_length=1,
        ),
    ]


class IsoDuration(RootModel[str]):
    model_config = ConfigDict(
        regex_engine="python-re",
    )
    root: Annotated[
        str,
        Field(
            description="ISO 8601 duration, e.g. PT30S, PT15M, P2D.",
            pattern="^P(?!$)(\\d+Y)?(\\d+M)?(\\d+W)?(\\d+D)?(T(?=\\d)(\\d+H)?(\\d+M)?(\\d+(\\.\\d+)?S)?)?$",
        ),
    ]


class ValueMap(
    RootModel[
        dict[
            Annotated[str, StringConstraints(pattern=r"^[a-zA-Z_][a-zA-Z0-9_]{0,62}$")],
            Any,
        ]
    ]
):
    root: Annotated[
        dict[
            Annotated[str, StringConstraints(pattern=r"^[a-zA-Z_][a-zA-Z0-9_]{0,62}$")],
            Any,
        ],
        Field(
            description="Named inputs; each value is a template (typed when it is a single placeholder) or a literal.",
            title="ValueMap",
        ),
    ]


class SecretRef(RootModel[str]):
    root: Annotated[
        str,
        Field(
            description="Name of a secret in the tenant's secret store. Secrets are never readable from expressions.",
            pattern="^[a-z][a-z0-9-]{0,62}$",
        ),
    ]


class ModelRef(BaseModel):
    """
    Provider-neutral model reference. The tenant's model registry maps each role to a concrete provider model id, so flows never hardcode vendor model names.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    role: Annotated[
        Literal["agent", "fast", "reasoning"],
        Field(
            description="agent = tool-using default; fast = cheap extraction/classification; reasoning = hardest planning tasks."
        ),
    ]


class JsonSchemaObject(BaseModel):
    """
    An embedded JSON Schema (object type) describing structured data the node must produce or accept.
    """

    model_config = ConfigDict(
        extra="allow",
    )
    type: Literal["object"]


class Variable(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[str, Field(pattern="^[a-zA-Z_][a-zA-Z0-9_]{0,62}$")]
    type: Literal["string", "number", "integer", "boolean", "object", "array", "timestamp"]
    default: Any | None = None
    description: Annotated[str | None, Field(max_length=500)] = None
    sensitive: Annotated[
        bool | None, Field(description="Redacted in execution logs and transcripts.")
    ] = False


class Edge(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Slug | None = None
    from_: Annotated[Slug, Field(alias="from", description="Source node id.")]
    port: Annotated[
        str | None,
        Field(
            description="Output port of the source node. Valid ports depend on the node type (see the spec).",
            pattern="^[a-z][a-z0-9_-]{0,62}$",
        ),
    ] = "next"
    to: Annotated[Slug, Field(description="Target node id.")]


class SettingsConcurrency(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    key: Annotated[
        Template,
        Field(description="Executions with the same rendered key are serialized or rejected."),
    ]
    mode: Literal["queue", "reject", "replace"] | None = "queue"


class SettingsDedupe(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    key: Annotated[
        Template,
        Field(
            description="Trigger-level idempotency key; a second trigger with the same key within the window starts nothing."
        ),
    ]
    window: Annotated[IsoDuration | None, Field(validate_default=True)] = "P1D"


class SettingsConversationInterruptsItem(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Slug
    description: Annotated[str, Field(max_length=500, min_length=1)]
    examples: Annotated[list[str] | None, Field(max_length=20)] = None
    goTo: Slug
    resume: Annotated[
        bool | None,
        Field(
            description="After the interrupt path reaches an end node, return to the node that was waiting."
        ),
    ] = False


class SettingsConversation(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    idleTimeout: Annotated[IsoDuration | None, Field(validate_default=True)] = "PT30M"
    interrupts: Annotated[
        list[SettingsConversationInterruptsItem] | None,
        Field(
            description="Global intents checked on every user message before it reaches the waiting node (Voiceflow-style global intents).",
            max_length=20,
        ),
    ] = None


class Settings(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    timeout: Annotated[
        IsoDuration | None,
        Field(description="Hard limit for the whole execution, including waits. Default P30D."),
    ] = None
    maxSteps: Annotated[int | None, Field(ge=1, le=5000)] = 500
    errorFlow: Annotated[
        Slug | None,
        Field(description="Flow started (latest published version) when an execution fails."),
    ] = None
    concurrency: Annotated[SettingsConcurrency | None, Field(title="SettingsConcurrency")] = None
    dedupe: Annotated[SettingsDedupe | None, Field(title="SettingsDedupe")] = None
    conversation: Annotated[SettingsConversation | None, Field(title="SettingsConversation")] = None
    retention: Annotated[
        IsoDuration | None,
        Field(description="How long execution data is kept. Default P90D."),
    ] = None


class ManualTrigger(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["manual"]
    input: JsonSchemaObject | None = None


class ChatTrigger(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["chat"]
    channels: Annotated[list[Literal["web", "whatsapp", "email"]] | None, Field(min_length=1)] = [
        "web"
    ]


class WebhookTriggerAuth(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    mode: Literal["hmac", "bearer", "none"]
    secret: SecretRef | None = None


class WebhookTrigger(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["webhook"]
    path: Slug
    auth: Annotated[WebhookTriggerAuth, Field(title="WebhookTriggerAuth")]
    input: JsonSchemaObject | None = None
    respond: Annotated[
        Literal["immediately", "on_end"] | None,
        Field(
            description="immediately = 202 with the execution id; on_end = wait (max 30 s) and return the end node's output."
        ),
    ] = "immediately"


class ScheduleTrigger(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["schedule"]
    cron: Annotated[str, Field(max_length=120, min_length=9)]
    timezone: str | None = "America/Argentina/Buenos_Aires"


class EventTrigger(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["event"]
    event: Literal[
        "lead.created",
        "lead.status_changed",
        "trip.created",
        "trip.status_changed",
        "trip_item.status_changed",
        "approval.decided",
        "document.ingested",
    ]
    filter: Annotated[
        Expression | None,
        Field(description="CEL boolean over `trigger`; the flow starts only when true."),
    ] = None


class Retry(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    maxAttempts: Annotated[int | None, Field(ge=1, le=20)] = 3
    initialInterval: Annotated[IsoDuration | None, Field(validate_default=True)] = "PT1S"
    backoffCoefficient: Annotated[float | None, Field(ge=1.0, le=10.0)] = 2
    maxInterval: Annotated[IsoDuration | None, Field(validate_default=True)] = "PT1M"
    nonRetryable: Annotated[
        list[
            Literal[
                "validation",
                "expression",
                "auth",
                "not_found",
                "conflict",
                "rate_limited",
                "timeout",
                "upstream",
                "refused",
            ]
        ]
        | None,
        Field(
            description="Error classes that skip remaining attempts. validation and expression are always non-retryable."
        ),
    ] = None


class NodeBasePosition(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    x: float
    y: float


class NodeBase(BaseModel):
    id: Slug
    type: str
    name: Annotated[str | None, Field(max_length=120)] = None
    notes: Annotated[str | None, Field(max_length=2000)] = None
    disabled: Annotated[
        bool | None,
        Field(description="Disabled nodes pass their input through the `next` port."),
    ] = False
    retry: Retry | None = None
    timeout: Annotated[
        IsoDuration | None,
        Field(description="Per-attempt timeout for the node's activity."),
    ] = None
    onError: Annotated[
        Literal["fail", "continue", "branch"] | None,
        Field(
            description="After retries are exhausted: fail the execution, continue through `next` with output {error}, or route to the `error` port."
        ),
    ] = "fail"
    position: Annotated[NodeBasePosition | None, Field(title="NodeBasePosition")] = None


class Tool(RootModel[str]):
    root: Annotated[str, Field(pattern="^[a-z][a-z0-9_]{0,62}$")]


class AgentExit(BaseModel):
    """
    conversation mode: the agent leaves through `completed` once it can fill `output`.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    description: Annotated[str | None, Field(max_length=1000)] = None
    output: JsonSchemaObject
    maxTurns: Annotated[int | None, Field(ge=1, le=100)] = 20
    handoffWhen: Annotated[
        str | None,
        Field(
            description="When the agent should leave through `handoff` (e.g. the user asks for a human).",
            max_length=1000,
        ),
    ] = None


class ApprovalRequiredForItem(RootModel[str]):
    root: Annotated[str, Field(pattern="^[a-z][a-z0-9_]{0,62}$")]


class AgentConfig(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    mode: Annotated[
        Literal["task", "conversation"],
        Field(
            description="task = one autonomous run on `input`; conversation = talks with the user across turns until `exit` is satisfied."
        ),
    ]
    instructions: Template
    input: Annotated[
        Template | None,
        Field(description="task mode: the work item handed to the agent."),
    ] = None
    tools: Annotated[
        list[Tool] | None,
        Field(
            description="Names from the tool registry (the same tools the MCP server exposes).",
            max_length=30,
        ),
    ] = None
    knowledgeBases: list[Slug] | None = None
    model: Annotated[ModelRef | None, Field(validate_default=True)] = {"role": "agent"}
    effort: Annotated[
        Literal["low", "medium", "high"] | None,
        Field(
            description="Provider-neutral reasoning effort; the LLM layer maps it to the provider setting."
        ),
    ] = "medium"
    maxIterations: Annotated[int | None, Field(ge=1, le=50)] = 12
    output: Annotated[
        JsonSchemaObject | None,
        Field(description="task mode: structured result the agent must return."),
    ] = None
    exit: Annotated[
        AgentExit | None,
        Field(
            description="conversation mode: the agent leaves through `completed` once it can fill `output`.",
            title="AgentExit",
        ),
    ] = None
    approvalRequiredFor: Annotated[
        list[ApprovalRequiredForItem] | None,
        Field(description="Tools whose calls pause for human approval before running."),
    ] = None


class AgentNode(NodeBase):
    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["agent"]
    config: Annotated[AgentConfig, Field(title="AgentConfig")]


class ExtractConfig(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    input: Template
    instructions: Template | None = None
    schema_: Annotated[JsonSchemaObject, Field(alias="schema")]
    model: Annotated[ModelRef | None, Field(validate_default=True)] = {"role": "fast"}


class ExtractNode(NodeBase):
    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["extract"]
    config: Annotated[ExtractConfig, Field(title="ExtractConfig")]


class ClassifyClassesItem(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Slug
    description: Annotated[str, Field(max_length=500, min_length=1)]
    examples: Annotated[list[str] | None, Field(max_length=20)] = None


class ClassifyConfig(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    input: Template
    instructions: Template | None = None
    classes: Annotated[list[ClassifyClassesItem], Field(max_length=30, min_length=2)]
    model: Annotated[ModelRef | None, Field(validate_default=True)] = {"role": "fast"}


class ClassifyNode(NodeBase):
    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["classify"]
    config: Annotated[ClassifyConfig, Field(title="ClassifyConfig")]


class KnowledgeSearchConfig(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    query: Template
    knowledgeBases: Annotated[list[Slug], Field(min_length=1)]
    topK: Annotated[int | None, Field(ge=1, le=50)] = 5
    filters: Annotated[
        ValueMap | None,
        Field(description='Payload filters, e.g. {"country": "{{ vars.country }}"}.'),
    ] = None
    rerank: bool | None = True
    minScore: Annotated[float | None, Field(ge=0.0, le=1.0)] = None


class KnowledgeSearchNode(NodeBase):
    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["knowledge_search"]
    config: Annotated[KnowledgeSearchConfig, Field(title="KnowledgeSearchConfig")]


class SayAttachmentsItem(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    kind: Literal["link", "image", "file"]
    url: Template
    title: Template | None = None


class SayConfig(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    text: Template
    variants: Annotated[
        list[Template] | None,
        Field(
            description="Alternative phrasings; one is picked deterministically per execution.",
            max_length=10,
        ),
    ] = None
    attachments: Annotated[list[SayAttachmentsItem] | None, Field(max_length=10)] = None


class SayNode(NodeBase):
    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["say"]
    config: Annotated[SayConfig, Field(title="SayConfig")]


class CaptureConfig(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    prompt: Annotated[
        Template | None,
        Field(description="Optional message sent before waiting (saves a separate say node)."),
    ] = None
    variable: Annotated[str, Field(pattern="^[a-zA-Z_][a-zA-Z0-9_]{0,62}$")]
    extract: Annotated[
        JsonSchemaObject | None,
        Field(
            description="If set, the reply is parsed into this structure (LLM-backed slot filling); missing required fields re-prompt."
        ),
    ] = None
    reprompt: Template | None = None
    maxAttempts: Annotated[int | None, Field(ge=1, le=5)] = 2
    waitFor: Annotated[IsoDuration | None, Field(validate_default=True)] = "PT30M"


class CaptureNode(NodeBase):
    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["capture"]
    config: Annotated[CaptureConfig, Field(title="CaptureConfig")]


class ChoiceOptionsItem(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Slug
    label: Template
    synonyms: Annotated[list[str] | None, Field(max_length=20)] = None


class ChoiceConfig(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    prompt: Template
    options: Annotated[list[ChoiceOptionsItem], Field(max_length=10, min_length=2)]
    freeText: Annotated[
        Literal["classify", "no_match"] | None,
        Field(
            description="classify = map free text to an option with an LLM; no_match = route to the no_match port."
        ),
    ] = "classify"
    waitFor: Annotated[IsoDuration | None, Field(validate_default=True)] = "PT30M"


class ChoiceNode(NodeBase):
    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["choice"]
    config: Annotated[ChoiceConfig, Field(title="ChoiceConfig")]


class ConditionConfig(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    expression: Expression


class ConditionNode(NodeBase):
    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["condition"]
    config: Annotated[ConditionConfig, Field(title="ConditionConfig")]


class SwitchCasesItem(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Slug
    expression: Expression


class SwitchConfig(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    cases: Annotated[list[SwitchCasesItem], Field(max_length=30, min_length=1)]


class SwitchNode(NodeBase):
    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["switch"]
    config: Annotated[SwitchConfig, Field(title="SwitchConfig")]


class ValueMap1(
    RootModel[
        dict[
            Annotated[str, StringConstraints(pattern=r"^[a-zA-Z_][a-zA-Z0-9_]{0,62}$")],
            Any,
        ]
    ]
):
    root: Annotated[
        dict[
            Annotated[str, StringConstraints(pattern=r"^[a-zA-Z_][a-zA-Z0-9_]{0,62}$")],
            Any,
        ],
        Field(
            description="Named inputs; each value is a template (typed when it is a single placeholder) or a literal.",
            min_length=1,
            title="ValueMap",
        ),
    ]


class SetConfig(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    assign: Annotated[
        ValueMap1,
        Field(
            description="Named inputs; each value is a template (typed when it is a single placeholder) or a literal.",
            title="ValueMap",
        ),
    ]


class SetNode(NodeBase):
    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["set"]
    config: Annotated[SetConfig, Field(title="SetConfig")]


class VersionNumber(RootModel[int]):
    root: Annotated[
        int,
        Field(
            description="`published` is resolved to a number when the parent execution starts.",
            ge=1,
            title="VersionNumber",
        ),
    ] = "published"


class MapConfig(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    items: Annotated[Template, Field(description="Must evaluate to a list (max 1000 items).")]
    flow: Annotated[Slug, Field(description="Sub-flow run once per item (child execution).")]
    version: Annotated[
        Literal["published"] | VersionNumber | None,
        Field(
            description="`published` is resolved to a number when the parent execution starts.",
            validate_default=True,
        ),
    ] = "published"
    itemInput: Annotated[str | None, Field(pattern="^[a-zA-Z_][a-zA-Z0-9_]{0,62}$")] = "item"
    inputs: ValueMap | None = None
    concurrency: Annotated[int | None, Field(ge=1, le=20)] = 5
    failFast: bool | None = False


class MapNode(NodeBase):
    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["map"]
    config: Annotated[MapConfig, Field(title="MapConfig")]


class VersionNumber1(RootModel[int]):
    root: Annotated[int, Field(ge=1, title="VersionNumber")] = "published"


class SubflowConfig(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    flow: Slug
    version: Annotated[
        Literal["published"] | VersionNumber1 | None, Field(validate_default=True)
    ] = "published"
    inputs: ValueMap | None = None
    wait: Annotated[
        bool | None,
        Field(description="false = fire and forget (output is the child execution id)."),
    ] = True


class SubflowNode(NodeBase):
    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["subflow"]
    config: Annotated[SubflowConfig, Field(title="SubflowConfig")]


class WaitConfig(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    mode: Literal["duration", "until"]
    duration: IsoDuration | None = None
    until: Annotated[
        Template | None,
        Field(
            description="Must evaluate to a timestamp. A time in the past continues immediately."
        ),
    ] = None


class WaitNode(NodeBase):
    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["wait"]
    config: Annotated[WaitConfig, Field(title="WaitConfig")]


class EndConfig(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    status: Literal["completed", "failed"] | None = "completed"
    output: ValueMap | None = None
    reason: Template | None = None


class EndNode(NodeBase):
    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["end"]
    config: Annotated[EndConfig | None, Field(title="EndConfig")] = None


class HttpAuth(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    mode: Literal["bearer", "basic", "header", "hmac"]
    secret: SecretRef
    header: Annotated[str | None, Field(max_length=100)] = None


class SuccessStatu(RootModel[int]):
    root: Annotated[int, Field(ge=100, le=599)]


class HttpConfig(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
    url: Annotated[Template, Field(description="Host must be in the tenant egress allowlist.")]
    headers: ValueMap | None = None
    query: ValueMap | None = None
    body: Annotated[
        Any | None,
        Field(description="Template string, or an object whose string leaves are templates."),
    ] = None
    auth: Annotated[HttpAuth | None, Field(title="HttpAuth")] = None
    successStatus: Annotated[list[SuccessStatu] | None, Field(validate_default=True)] = [
        200,
        201,
        202,
        204,
    ]
    sendIdempotencyKey: Annotated[
        bool | None,
        Field(
            description="Adds Idempotency-Key: <execution>:<node>:<iteration> to non-GET requests."
        ),
    ] = True


class HttpNode(NodeBase):
    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["http"]
    config: Annotated[HttpConfig, Field(title="HttpConfig")]


class ActionConfig(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    action: Annotated[
        Literal[
            "create_lead",
            "update_lead_status",
            "draft_trip",
            "get_trip",
            "list_trip_items",
            "update_trip_item",
            "swap_opponent",
            "set_trip_status",
            "request_provider_confirmations",
            "send_proposal",
            "create_ops_task",
            "check_trip_readiness",
        ],
        Field(
            description="Domain action from the action registry. Inputs are validated against the action's own schema at publish time."
        ),
    ]
    inputs: ValueMap | None = None


class ActionNode(NodeBase):
    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["action"]
    config: Annotated[ActionConfig, Field(title="ActionConfig")]


class SendMessageConfig(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    channel: Literal["email", "chat", "ops_inbox", "whatsapp"]
    to: Template
    subject: Template | None = None
    body: Template
    attachments: Annotated[list[Template] | None, Field(max_length=10)] = None


class SendMessageNode(NodeBase):
    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["send_message"]
    config: Annotated[SendMessageConfig, Field(title="SendMessageConfig")]


class EmitEventConfig(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    event: Annotated[
        str,
        Field(
            description="Flows may only emit custom.* events; domain events come from the domain layer.",
            pattern="^custom\\.[a-z][a-z0-9_.]{0,62}$",
        ),
    ]
    payload: ValueMap | None = None


class EmitEventNode(NodeBase):
    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["emit_event"]
    config: Annotated[EmitEventConfig, Field(title="EmitEventConfig")]


class ApprovalLinksItem(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    label: str
    url: Template


class ApprovalAssignees(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    roles: list[Literal["ops", "sales", "admin"]] | None = None
    users: list[str] | None = None


class ApprovalConfig(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    title: Template
    description: Template | None = None
    links: Annotated[list[ApprovalLinksItem] | None, Field(max_length=10)] = None
    assignees: Annotated[ApprovalAssignees, Field(title="ApprovalAssignees")]
    form: Annotated[
        JsonSchemaObject | None,
        Field(description="Extra fields the approver fills (e.g. a discount, a comment)."),
    ] = None
    expiresAfter: IsoDuration
    remindEvery: IsoDuration | None = None


class ApprovalNode(NodeBase):
    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["approval"]
    config: Annotated[ApprovalConfig, Field(title="ApprovalConfig")]


class Trigger(
    RootModel[ManualTrigger | ChatTrigger | WebhookTrigger | ScheduleTrigger | EventTrigger]
):
    root: Annotated[
        ManualTrigger | ChatTrigger | WebhookTrigger | ScheduleTrigger | EventTrigger,
        Field(discriminator="type"),
    ]


class Node(
    RootModel[
        AgentNode
        | ExtractNode
        | ClassifyNode
        | KnowledgeSearchNode
        | SayNode
        | CaptureNode
        | ChoiceNode
        | ConditionNode
        | SwitchNode
        | SetNode
        | MapNode
        | SubflowNode
        | WaitNode
        | EndNode
        | HttpNode
        | ActionNode
        | SendMessageNode
        | EmitEventNode
        | ApprovalNode
    ]
):
    root: Annotated[
        AgentNode
        | ExtractNode
        | ClassifyNode
        | KnowledgeSearchNode
        | SayNode
        | CaptureNode
        | ChoiceNode
        | ConditionNode
        | SwitchNode
        | SetNode
        | MapNode
        | SubflowNode
        | WaitNode
        | EndNode
        | HttpNode
        | ActionNode
        | SendMessageNode
        | EmitEventNode
        | ApprovalNode,
        Field(discriminator="type"),
    ]


class FlowDefinition(BaseModel):
    """
    A versioned directed graph of nodes started by one trigger. See docs/architecture/flow-engine.md. Structural rules that JSON Schema cannot express (unique ids, edge endpoints, valid ports per node type, reachability, expression syntax) are enforced by the publish-time validator.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    field_schema: Annotated[str | None, Field(alias="$schema")] = None
    schemaVersion: Literal["1"]
    id: Annotated[Slug, Field(description="Stable flow id, unique per tenant.")]
    name: Annotated[str, Field(max_length=120, min_length=1)]
    description: Annotated[str | None, Field(max_length=2000)] = None
    version: Annotated[
        int | None,
        Field(
            description="Assigned by the server on publish (1, 2, 3...). null while the definition is a draft.",
            ge=1,
        ),
    ] = None
    trigger: Trigger
    entry: Annotated[
        Slug,
        Field(description="Id of the first node executed after the trigger fires."),
    ]
    variables: Annotated[list[Variable] | None, Field(max_length=100)] = None
    nodes: Annotated[list[Node], Field(max_length=200, min_length=1)]
    edges: Annotated[list[Edge], Field(max_length=400)]
    settings: Settings | None = None
