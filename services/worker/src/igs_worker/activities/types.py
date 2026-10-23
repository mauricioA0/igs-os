"""Workflow ↔ activity payloads. Plain dataclasses so the default converter handles them."""

from dataclasses import dataclass, field
from typing import Any

# Internal ports an activity returns to ask the workflow to pause; never edges in a flow.
PORT_NEEDS_APPROVAL = "__needs_approval__"
PORT_AWAIT_USER = "__await_user__"


@dataclass
class OutputRef:
    """Pointer to a node output stored outside Temporal (Postgres row or GCS object)."""

    uri: str
    size_bytes: int
    preview: str = ""


@dataclass
class NodeTask:
    execution_id: str
    flow_id: str
    version: int
    node_id: str
    node_type: str
    iteration: int
    config: dict[str, Any]  # already rendered by the workflow
    tenant_id: str | None = None
    trigger_type: str = "manual"
    # Resume state for multi-activity nodes (agent tool approvals, conversation turns).
    state: dict[str, Any] | None = None


@dataclass
class NodeOutcome:
    port: str
    output: Any = None
    output_ref: OutputRef | None = None


@dataclass
class NodeRunRecord:
    execution_id: str
    node_id: str
    node_type: str
    iteration: int
    status: str  # completed | failed | waiting | skipped
    port: str | None
    started_at: str
    ended_at: str | None
    output: Any = None
    output_ref: OutputRef | None = None
    error: dict[str, Any] | None = None


@dataclass
class ApprovalRequest:
    execution_id: str
    node_id: str
    iteration: int
    title: str
    description: str | None
    assignees: dict[str, Any]
    expires_at: str
    links: list[dict[str, Any]] = field(default_factory=list)
    # What exactly gets approved (tool call / action and its inputs); hashed by the store.
    proposed_action: dict[str, Any] | None = None
    # Distinguishes several approvals raised by one node run (agent tool calls).
    seq: int = 0


@dataclass
class FlowVersionRef:
    flow_id: str
    version: int | None  # None = latest published


@dataclass
class UserMessage:
    """A reply from the person on the other side of a conversational flow."""

    text: str
    message_id: str = ""
    received_at: str = ""


@dataclass
class OutgoingMessage:
    """Something a conversational node says (say, capture/choice prompts, agent turns)."""

    execution_id: str
    node_id: str
    iteration: int
    seq: int
    text: str
    channel: str = "chat"
    tenant_id: str | None = None
    options: list[dict[str, str]] = field(default_factory=list)  # quick replies
    attachments: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class CaptureParse:
    """Slot filling for ``capture`` with ``extract``: parse a reply into a structure."""

    text: str
    schema: dict[str, Any]
    instructions: str | None = None
    previous: dict[str, Any] = field(default_factory=dict)


@dataclass
class CaptureParsed:
    values: dict[str, Any]
    missing: list[str] = field(default_factory=list)


@dataclass
class ChoiceClassify:
    text: str
    options: list[dict[str, Any]]


@dataclass
class MapChildResult:
    index: int
    status: str
    output: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
