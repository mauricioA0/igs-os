# Flow engine — specification

Status: draft v1 · Schema: [`packages/flow-schema/flow.schema.json`](../../packages/flow-schema/flow.schema.json) · Examples: [`packages/flow-schema/examples/`](../../packages/flow-schema/examples/)

The flow engine lets the IGS ops team describe *how work happens* — a coach conversation, a pre-departure check, a post-match report — as a versioned graph that runs durably on Temporal. It borrows **concepts** from Voiceflow (conversational design) and n8n (automation). No code, schemas or assets from either product are reused; n8n is distributed under the Sustainable Use License and Voiceflow is proprietary.

## 1. Principles

1. **One graph model for conversations and automations.** A chat with a coach and a cron job differ only in their trigger and in whether they pause for user input.
2. **Durable by default.** Every execution is a Temporal workflow. Waiting two days for an approval or a year until departure costs nothing and survives deploys and crashes.
3. **Published versions are immutable.** An execution runs the exact version it started with, start to finish.
4. **Side effects happen once.** Every side effect carries an idempotency key derived from the execution, node and iteration.
5. **Safe expressions.** Users write expressions, never code. The expression language cannot loop forever, touch the network, or read secrets.
6. **Everything is observable.** Each node run records input, output, status, attempts and timing; conversations keep a transcript.

## 2. Concept mapping

| Voiceflow | n8n | IGS OS | Notes |
|---|---|---|---|
| Project / workflow canvas | Workflow | **Flow** | One trigger per flow. A process with several entry points becomes several flows that share sub-flows. |
| Block / step | Node | **Node** | Steps are not grouped into blocks; the canvas can group nodes visually without semantic meaning. |
| Line between steps | Connection (main output n → input) | **Edge** with a source **port** | Ports are named (`next`, `true`, `approved`...), not numbered. |
| Start block | Trigger node | **Trigger** + `entry` | The trigger is not a node; `entry` names the first node. |
| Speak / Text step | — | `say` | |
| Capture step (raw input → variable) | — | `capture` | Optional `extract` schema turns the reply into structured data (slot filling). |
| Buttons / Choice step | — | `choice` | Free text can be classified onto an option. |
| Intents, global intents | — | `classify`, `settings.conversation.interrupts` | Interrupts are checked on every user message (e.g. "talk to a human"). |
| Agent step / LLM steps | AI Agent node, LLM chains | `agent` (task / conversation), `extract`, `classify` | Agents use tools from the same registry the MCP server exposes. |
| Knowledge base | Vector store nodes | `knowledge_search` + `agent.knowledgeBases` | Backed by the RAG service (hybrid search + rerank). |
| Variables (global / flow) | Expressions over `$json`, `$node` | `vars`, `nodes.<id>.output`, `trigger`, `execution` | Read-only scopes plus `vars` written by `set`. |
| Condition step | IF / Switch | `condition`, `switch` | |
| Set step | Edit Fields (Set) | `set` | |
| Component / flow reference | Execute Workflow (sub-workflow) | `subflow`, `map` | Child executions, pinned to a version at start. |
| — | Loop Over Items, item lists | `map` | Iteration happens through child executions, so each item is retried and logged on its own. |
| — | Wait node (time / webhook resume) | `wait`, `capture`, `approval` | Resumption is a Temporal timer or signal; there are no resume URLs. |
| API step, Function step | HTTP Request, Code | `http`, `action` | **No code node.** Domain logic is a registered, tested `action`. |
| — | Error workflow + Error Trigger | `settings.errorFlow` | Runs the latest published error flow with execution context. |
| — | Retry On Fail, On Error (stop / continue / error output) | `retry`, `onError: fail \| continue \| branch` | Same three behaviours, plus Temporal-grade backoff. |
| — | Stop And Error | `end` with `status: failed` | |
| Draft vs published version, environments | Save / Activate, workflow history | **Draft → publish → version N** | One published pointer per flow; environments are out of scope for v1. |
| Transcripts | Executions list + execution data | **Executions** + **transcripts** | |
| — | Pinned data (test with frozen node output) | Test runs with **pinned outputs** | Editor-only; never stored in a published version. |
| — | Retry execution (original vs current version) | **Retry from node** | Always on the original version (see §11.6). |

## 3. Graph model

A flow definition (validated by `flow.schema.json`) contains:

| Field | Meaning |
|---|---|
| `id` | Stable slug, unique per tenant. |
| `version` | `null` while draft; assigned by the server on publish (1, 2, 3...). |
| `trigger` | What starts an execution (§5). |
| `entry` | Id of the first node. |
| `variables` | Declared flow variables with type, default and `sensitive` flag. |
| `nodes` | Up to 200 nodes. Each has `id`, `type`, `config` and optional `retry`, `timeout`, `onError`, `disabled`, `position`, `notes`. |
| `edges` | `{from, port, to}`. `port` defaults to `next`. |
| `settings` | Timeout, step limit, error flow, concurrency, dedupe, conversation settings, retention. |

### 3.1 Ports and routing

A node finishes by choosing **exactly one** output port. The engine follows the edge for that port. If the chosen port has no edge, the execution ends `completed` when the port is `next`, and `failed` (with error `unrouted_port`) otherwise. This makes a missing branch a visible failure instead of a silent stop.

There is no parallel fan-out over edges. A port has at most one outgoing edge. Parallelism is explicit through `map` and `subflow` with `wait: false`, which keeps execution order deterministic and easy to read in the viewer.

Cycles are allowed (for example re-asking after a failed `capture`). They are bounded by `settings.maxSteps`.

### 3.2 Data scopes available to expressions

| Scope | Content | Writable |
|---|---|---|
| `trigger` | Trigger payload (chat message, webhook body, event payload). Events always include `eventId`. | No |
| `vars` | Declared flow variables. | Only through `set` (and `capture.variable`) |
| `nodes.<id>.output` | Output of the **latest** run of that node. | No |
| `nodes.<id>.error` | `{class, message, attempts}` of the latest failed run. | No |
| `execution` | `id`, `flowId`, `flowVersion`, `startedAt`, `now`, `conversationId`, `channel`, `step`. | No |

`execution.now` is the Temporal workflow time at the moment the node starts. It is deterministic on replay. There is deliberately no `now()` function.

Secrets are not a scope. Nodes that need credentials take a `secretRef`, and the engine resolves it inside the activity.

## 4. Versioning and lifecycle

```
draft ──validate──► publishable ──publish──► version N (immutable) ◄── executions pin N
  ▲                                              │
  └─────────────── edit (new draft) ◄────────────┘
```

- **Draft.** Mutable and autosaved. Can be test-run from the editor with *pinned outputs*: frozen outputs for chosen nodes, so an LLM call or an HTTP request doesn't have to run again on every test. Pinned outputs live only on the draft.
- **Publish.** Validates the draft (§13), resolves references and stores an immutable snapshot `flow_versions(flow_id, version, definition, content_hash, published_by, published_at)`. The flow's `published_version` pointer moves to it. Triggers start using it immediately.
- **Pinning.** The API resolves the published version when the execution starts and passes the full version snapshot to the workflow **as its input**. The workflow never loads a flow version itself, so replays never reread mutable state. `subflow` and `map` with `version: "published"` resolve to a concrete number when the **parent** starts. The whole tree is therefore consistent.
- **Rollback.** "Publish version K again" creates a new version N+1 with K's content. History only moves forward.
- **In-flight executions** are never migrated. They finish on their version. Long waits (for example a flow waiting until 30 days before departure) re-check current domain state after waking up, as `pre-departure-check` does with `reload_trip`.
- **Engine code changes** (the interpreter itself) use Temporal worker versioning and `patched()` markers, so executions already in flight replay with the code that started them.

## 5. Triggers

| Type | Starts when | Payload (`trigger`) | Notes |
|---|---|---|---|
| `manual` | Someone runs it from the panel or via MCP | Validated against `input` | Useful for back-office tools. |
| `chat` | First message of a new conversation on an allowed channel | `{message, channel, conversationId, user}` | Later messages in the same conversation are delivered to the running execution (§9). |
| `webhook` | `POST /hooks/{tenant}/{path}` | Body validated against `input` | `hmac` / `bearer` auth by `secretRef`. `respond: on_end` waits up to 30 s for the `end` output, otherwise answers 202. |
| `schedule` | Cron in `timezone` | `{scheduledAt}` | Implemented with Temporal Schedules (overlap policy follows `settings.concurrency`). |
| `event` | A domain event is published and `filter` is true | Event payload + `eventId` | Events come from the domain layer through an outbox table, so they are only emitted after the database transaction commits. |

Domain events available in v1: `lead.created`, `lead.status_changed`, `trip.created`, `trip.status_changed`, `trip_item.status_changed`, `approval.decided`, `document.ingested`. Flows may emit `custom.*` events with `emit_event` and subscribe to them. They cannot forge domain events.

## 6. Expressions

### 6.1 Choice: CEL

Expressions use **[CEL (Common Expression Language)](https://cel.dev)** inside `{{ }}` placeholders.

| Option | Why not / why |
|---|---|
| JavaScript (what n8n does) | Turing-complete, so it needs a real sandbox. Escaping an expression sandbox is a recurring class of vulnerability in workflow tools. Not deterministic by default. Rejected. |
| Jinja2 sandbox | Template language first; logic is awkward, the sandbox is Python-specific and has a history of escapes. Rejected. |
| JSONata | Good at reshaping JSON, but harder for non-engineers to read and has limited typing. A reasonable second choice. |
| **CEL** | Not Turing-complete; evaluation is linear in expression size with cost limits. No side effects or I/O. Typed. Familiar C-like syntax (`a == 'x' && size(list) > 0`). Has implementations in Go, Java, C++, JS and Python, so the editor (TS) and the worker (Python) can both check expressions. Used in production by Google Cloud IAM, Kubernetes and Envoy. **Chosen.** |

### 6.2 Rules

- A string that is **exactly one placeholder** (`"{{ nodes.x.output }}"`) evaluates to the expression's typed value (object, list, number...). Any other string with placeholders renders each one as text and concatenates.
- Fields documented as `expression` (`condition`, `switch` cases, trigger `filter`) are raw CEL without braces and must return `bool`.
- Available functions: the CEL standard library plus macros (`has`, `map`, `filter`, `exists`, `all`), `timestamp()`, `duration()`, string extensions (`join`, `split`, `lowerAscii`, `trim`...), and a small engine library to be agreed in implementation (date formatting, `default(x, fallback)`).
- Limits: 4,000 characters per expression, cost budget per evaluation, and rendered templates capped at 64 KB.
- Expressions are **compiled at publish time** against the declared scopes. Syntax errors and unknown top-level scopes block publishing. Field-level type checking is best effort in v1, because node outputs are not all statically typed.
- Runtime evaluation errors have class `expression`, which is never retried (§11).

## 7. Node catalog

Ports in **bold** are the ones the node picks on success. Every node also has an `error` port, used only when `onError: branch`.

### 7.1 AI

| Type | Purpose | Config (key fields) | Output | Ports |
|---|---|---|---|---|
| `agent` (`mode: task`) | Autonomous run on one work item with tools | `instructions`, `input`, `tools[]`, `knowledgeBases[]`, `model`, `effort`, `maxIterations`, `output` (JSON Schema), `approvalRequiredFor[]` | `output` schema if given, else `{text}`; always `toolCalls[]`, `usage` | **next** |
| `agent` (`mode: conversation`) | Talks with the user across turns until it can fill `exit.output` (Voiceflow-style agent step) | as above + `exit {description, output, maxTurns, handoffWhen}` | `exit.output` object; `transcript` | **completed**, **handoff** |
| `extract` | Structured data from text | `input`, `schema`, `instructions`, `model` | Object matching `schema` | **next** |
| `classify` | Route by meaning | `input`, `classes[{id, description, examples}]` | `{class, confidence}` | one port per class id, **default** |
| `knowledge_search` | RAG retrieval | `query`, `knowledgeBases[]`, `topK`, `filters`, `rerank`, `minScore` | `{hits[{content, title, source, score, docId}]}` | **next** |

Model selection: `model` is a provider-neutral role reference, `{"role": "agent" | "fast" | "reasoning"}`. It is resolved to a concrete model id from configuration (`IGS_LLM_MODELS`), so flows never name a provider or model version. `effort` is `low | medium | high`.

Agent behaviour: the model runs the tool loop inside one long-running activity that sends heartbeats. Each tool call is recorded as a child step of the node run. Tools listed in `approvalRequiredFor` raise an `approval` mid-run (same semantics as §10), and the activity hands control back to the workflow while it waits. Structured outputs use the API's structured output / strict tool features, and invalid outputs are retried once with the validation error. A model refusal produces error class `refused`.

### 7.2 Conversation

| Type | Purpose | Config | Output | Ports |
|---|---|---|---|---|
| `say` | Send a message | `text`, `variants[]`, `attachments[]` | `{messageId}` | **next** |
| `capture` | Wait for the user's next message and store it | `prompt`, `variable`, `extract`, `reprompt`, `maxAttempts`, `waitFor` | `{text}` or the extracted object | **next**, **timeout** |
| `choice` | Ask with options | `prompt`, `options[{id, label, synonyms}]`, `freeText`, `waitFor` | `{option, text}` | one port per option id, **no_match**, **timeout** |

### 7.3 Logic and control

| Type | Purpose | Config | Output | Ports |
|---|---|---|---|---|
| `condition` | Boolean branch | `expression` | `{value}` | **true**, **false** |
| `switch` | First matching case | `cases[{id, expression}]` | `{case}` | case ids, **default** |
| `set` | Assign variables | `assign {var: template}` | assigned values | **next** |
| `map` | Run a sub-flow per list item | `items`, `flow`, `version`, `itemInput`, `inputs`, `concurrency ≤ 20`, `failFast` | `{results[], failed[]}` | **next** |
| `subflow` | Call another flow | `flow`, `version`, `inputs`, `wait` | child `end` output, or `{executionId}` when `wait: false` | **next** |
| `wait` | Durable timer | `mode: duration \| until`, `duration` / `until` | `{resumedAt}` | **next** |
| `end` | Finish the execution | `status`, `output`, `reason` | — | none |

`condition`, `switch`, `set` and `say` rendering are **pure**: they run inside workflow code (deterministic CEL evaluation, no activity), so they are cheap and don't add history events beyond the node record. Every other node runs as one or more Temporal activities.

### 7.4 Integration

| Type | Purpose | Config | Output | Ports |
|---|---|---|---|---|
| `http` | Call an external API | `method`, `url`, `headers`, `query`, `body`, `auth{secretRef}`, `successStatus`, `sendIdempotencyKey` | `{status, headers, body}` | **next** |
| `action` | Call a registered domain action | `action`, `inputs` | action-specific (below) | **next** |
| `send_message` | Email / chat / ops inbox / WhatsApp (later) | `channel`, `to`, `subject`, `body`, `attachments` | `{messageId}` | **next** |
| `emit_event` | Publish a `custom.*` event | `event`, `payload` | `{eventId}` | **next** |

`http` targets must be in the tenant's egress allowlist. Requests to private IP ranges and metadata endpoints are blocked after DNS resolution (SSRF protection).

Domain action registry (v1). Each action has an input and output JSON Schema, checked at publish time and again at runtime:

| Action | Input | Output |
|---|---|---|
| `create_lead` | `{lead: LeadInput, conversationId?}` | `{id}` |
| `update_lead_status` | `{leadId, status}` | `{id, status}` |
| `draft_trip` | `{leadId}` | `TripView` |
| `get_trip` | `{tripId}` | `TripView` |
| `list_trip_items` | `{tripId, statuses?, withProvider?}` | `{items: TripItemView[]}` |
| `update_trip_item` | `{itemId, status?, notes?}` | `TripItemView` |
| `swap_opponent` | `{itemId, opponentId}` | `TripItemView` |
| `set_trip_status` | `{tripId, status}` | `{id, status}` |
| `request_provider_confirmations` | `{tripId, onlyStatuses?, replyBy}` | `{requested: [{itemId, providerId}]}` |
| `send_proposal` | `{tripId, to, note?}` | `{messageId, url}` |
| `create_ops_task` | `{title, leadId?, tripId?, conversationId?, priority?, dueAt?, ...context}` | `{taskId}` |
| `check_trip_readiness` | `{tripId}` | `{ready, travelers, travelersReady, openItems, overdueItems, blockers, nextDueOn, notReady: [{name, missing, overdue}], summary}` — read-only; rules in `igs_common/readiness/rules/` |

### 7.5 Human

| Type | Purpose | Config | Output | Ports |
|---|---|---|---|---|
| `approval` | Pause until a person decides | `title`, `description`, `links[]`, `assignees{roles, users}`, `form`, `expiresAfter`, `remindEvery` | `{decision, by, decidedAt, comment, form}` | **approved**, **rejected**, **expired** |

## 8. Execution model on Temporal

- **One workflow per execution**: `FlowExecutionWorkflow(executionId, flowId, version, trigger)`. Its workflow id is `exec-{executionId}`; conversations use `conv-{conversationId}`, so a message for a conversation can always be routed with Signal-With-Start.
- **Interpreter loop**: the version snapshot arrives as the workflow input. The workflow runs nodes one at a time: evaluate `config` templates, run the node (inline or as an activity), record the node run, pick the port, follow the edge. Stop at `end`, an unrouted port, `maxSteps`, or the execution timeout.
- **Workers and task queues**: workers run on GKE Autopilot, one Deployment per task queue, scaled by KEDA on queue backlog (Cloud Run doesn't fit long-polling workers). Today the worker serves two queues, `flows` and `ingestion`. Splitting LLM, I/O and action activities into their own queues (`flows-llm`, `flows-io`, `flows-actions`) is planned for when their scaling needs diverge.
- **Signals**: `user_message`, `approval_decision`, `cancel`. **Queries**: `state` (current node, waiting reason) for the panel.
- **Timers**: `wait`, `capture.waitFor`, `approval.expiresAfter`, `remindEvery`, conversation idle timeout.
- **Child workflows**: `subflow` and `map` items, with `ParentClosePolicy` = terminate for `wait: true` and abandon for `wait: false`.
- **History size**: the workflow calls **continue-as-new** after 2,000 node runs or 10 MB of history, carrying `vars`, the latest output of each node, and the waiting state. Long conversations and long-lived flows stay within Temporal's limits.
- **Large payloads**: node inputs and outputs over 256 KB are stored in GCS and passed by reference (a payload codec), so history stays small.
- **Node run records**: every node run is written to Postgres `flow_node_runs (execution_id, node_id, iteration, attempt, status, input, output, error, started_at, ended_at)` by a lightweight activity, in batches when several pure nodes run back to back. The execution viewer reads from Postgres, never from Temporal history.

## 9. Conversational semantics

- **One active execution per conversation.** The trigger starts it; `settings.concurrency.key = execution.conversationId` with `mode: reject` keeps it single.
- **Turns.** Messages produced by `say` nodes (and agent replies) are **buffered** and flushed to the channel when the execution reaches a turn boundary: `capture`, `choice`, a conversation-mode `agent` waiting for input, an `approval`, a `wait`, or `end`. The user therefore sees one coherent reply per turn, as with Voiceflow's response traces.
- **Inbound messages** arrive as the `user_message` signal:
  1. They are appended to the transcript.
  2. `interrupts` are checked first (a cheap classifier). A match jumps to `goTo`; with `resume: true` the execution returns to the waiting node after the interrupt path reaches an `end`.
  3. Otherwise the message satisfies the waiting node.
  4. Messages that arrive while the execution is busy (not waiting) are queued in order and consumed by the next waiting node, never dropped.
- **Idle timeout.** `conversation.idleTimeout` with no user message while waiting ends the execution `completed` with reason `idle`. The next message starts a fresh execution, which receives the previous transcript summary in `trigger.history`.
- **Slot filling.** `capture.extract` parses the reply into the schema and re-prompts (`reprompt`) for missing required fields, up to `maxAttempts`, then leaves through `timeout`.

## 10. Human approval

1. On entry the node creates an `approvals` row (`id, execution_id, node_id, title, description, links, assignees, form, expires_at, status`) and notifies assignees (ops inbox; email optional). It then waits for the `approval_decision` signal or the `expiresAfter` timer, whichever comes first.
2. A decision can come from the panel, from the MCP tool `decide_approval`, or from an agent tool call **only if** that agent acts on behalf of a user with the right role. The API checks role or user assignment and that the approval is still `pending`, writes the decision (first writer wins, using a conditional update), and then signals the workflow.
3. `remindEvery` re-notifies while pending.
4. The output records who decided, when, the comment and the form data, which gives an audit trail.
5. The `expired` port fires on timeout. Decisions after expiry are rejected by the API with `409`.

## 11. Error handling

### 11.1 Error classes

| Class | Examples | Retried by default |
|---|---|---|
| `upstream` | 5xx, network errors, LLM overloaded | yes |
| `rate_limited` | 429 | yes (honours `retry-after`) |
| `timeout` | Activity attempt exceeded `timeout` | yes |
| `conflict` | Optimistic concurrency failure | yes |
| `validation` | Inputs fail the action schema, output fails `output` schema twice | **never** |
| `expression` | CEL evaluation error | **never** |
| `auth` | 401/403, missing secret | no |
| `not_found` | 404, unknown id | no |
| `refused` | Model refusal | no |

### 11.2 Retry

Per node: `retry {maxAttempts, initialInterval, backoffCoefficient, maxInterval, nonRetryable[]}`. The default is 3 attempts with exponential backoff from 1 s up to 1 min. These map directly to the Temporal activity `RetryPolicy`. Pure nodes do not retry: their only failures are `expression` errors.

### 11.3 After retries are exhausted (`onError`)

| Mode | Behaviour |
|---|---|
| `fail` (default) | The execution fails with that node as the cause. |
| `continue` | Output becomes `{error}` and the node leaves through its success port (`next`, or the first success port). Use it only for optional steps such as notifications. |
| `branch` | Leaves through the `error` port; `nodes.<id>.error` is available downstream. |

### 11.4 Error flow

When an execution ends `failed`, the latest published version of `settings.errorFlow` starts with `trigger = {execution, flow, failedNode, error}`. Error flows cannot themselves have an `errorFlow`, which prevents loops.

### 11.5 Execution-level failures

These are `maxSteps exceeded`, `execution timeout`, `unrouted_port` and an `end` with `status: failed`. They all end `failed` and trigger the error flow.

### 11.6 Manual recovery

From the viewer, ops can **retry from node X** on a failed execution. This starts a new execution of the **same version**, with `resumeFrom = X` and every completed node run before X replayed as pinned output, so side effects are not repeated (n8n's "retry with original workflow" plus pinned data). Retrying on a newer version is deliberately not offered, because the graph may have changed shape. The same applies to **cancel**.

## 12. Idempotency

| Level | Mechanism |
|---|---|
| Trigger | `settings.dedupe.key` (default: `trigger.eventId` for events, the `Idempotency-Key` header for webhooks) is stored with a TTL `window`. Duplicates return the existing execution id. Temporal workflow-id reuse policy is the second line of defence. |
| Concurrency | `settings.concurrency {key, mode}`: `queue` (serialize), `reject` (refuse while one runs), `replace` (cancel the running one, then start). |
| Node side effects | Key = `{executionId}:{nodeId}:{iteration}`, identical across retries of the same node run. `action` passes it to the domain layer, which stores it next to the write in one transaction. `http` sends it as `Idempotency-Key`. `send_message` dedupes on it in the outbox. |
| Delivery | Activities are at-least-once, so every side-effect implementation must be idempotent under that key. This is a requirement for adding an action to the registry. |

## 13. Publish-time validation

The JSON Schema covers structure. Publishing also checks:

1. Node ids are unique; `entry`, edge endpoints, `interrupts[].goTo` and `errorFlow` exist.
2. Every edge port is valid for its source node type (and mode); each port has at most one edge.
3. Every node is reachable from `entry` or an interrupt; every non-`end` node has at least one outgoing edge.
4. Every CEL expression compiles; scopes referenced exist; `nodes.<id>` references point to nodes that can run before the reference (best effort over the graph).
5. `tools`, `knowledgeBases`, `action`, `secretRef`, `subflow` / `map` flows exist for the tenant; action `inputs` keys match the action's input schema.
6. Conversation nodes (`say`, `capture`, `choice`, conversation-mode `agent`) only appear in flows with a `chat` trigger, or in sub-flows called only from such flows.
7. `errorFlow` is not the flow itself and has no `errorFlow` of its own.
8. Limits in §14.

## 14. Limits (v1 defaults)

| Limit | Value |
|---|---|
| Nodes per flow / edges per flow | 200 / 400 |
| Steps per execution (`maxSteps`) | 500 default, 5,000 max |
| Execution timeout | 30 days default (`settings.timeout`); waits up to 400 days |
| Node output stored inline | 256 KB (above → GCS reference) |
| Expression length / rendered template | 4,000 chars / 64 KB |
| `map` items / concurrency | 1,000 / 20 |
| Sub-flow nesting depth | 5 |
| Agent iterations / conversation turns | 50 / 100 |
| HTTP timeout per attempt | 30 s default, 120 s max |
| Concurrent executions per tenant | Configurable quota, 1,000 default |

## 15. Observability

- `flow_executions`: status, version, trigger, timings, cost (LLM tokens × price), error.
- `flow_node_runs`: one row per node run and attempt, which drives the n8n-style viewer (per-node status, I/O inspector, timings).
- Conversation transcripts: message log with channel delivery status.
- OpenTelemetry spans: execution → node → activity → LLM/tool call, exported to Cloud Trace, with the execution id as trace attribute.
- Variables marked `sensitive` and secret values are redacted before anything is persisted or exported.

## 16. Security

- No code node. Logic beyond CEL goes into reviewed, tested domain actions.
- Secrets live only in Secret Manager; they are referenced by name and resolved inside activities.
- `http` has an egress allowlist and SSRF guard. Webhook triggers require `hmac` or `bearer` unless explicitly set to `none` (publishing a `none` webhook raises a warning).
- Tenant isolation: every flow, version, execution, approval and node run row carries `tenant_id`; Temporal namespaces per environment and search attributes per tenant.
- LLM nodes treat user messages and retrieved documents as data. Tool permissions come from the node config, never from model output.

## 17. Demo flows

| File | Shows |
|---|---|
| `inbound-inquiry.json` | Chat trigger, conversation-mode agent with tools, global interrupt to a human, domain actions, `onError: branch`, human approval with all three outcomes |
| `pre-departure-check.json` | Event trigger with filter, durable `wait` until a computed date, re-reading state after waking, dedupe/`replace` concurrency, escalation |
| `post-match-report.json` | Event trigger, RAG lookup with `onError: continue`, task-mode agent with structured output, retries + error branch on email |

All three validate against the schema. They were also checked for reference integrity, valid ports, reachability and CEL syntax (with `cel-python`), as a preview of §13.

## 18. Open questions

1. **Match completion status.** `trip_items.status` has no `completed` value and there is no `result` field. `post-match-report` assumes `confirmed` + `result`. Add `completed` and a `result` column to the domain model?
2. **Error flow.** All demo flows reference `notify-ops-on-failure`, which does not exist yet. Should it ship as a fourth built-in flow?
3. **Agent tool approvals.** Should `approvalRequiredFor` pause the whole execution (Temporal signal) or only the agent activity? The spec assumes pausing the execution.
4. **CEL engine library.** Which date-formatting and `default()` helpers to add, given they must exist with identical behaviour in both the Python (worker) and TypeScript (editor) implementations.
5. **Environments.** v1 has one published pointer per flow. Is a staging pointer (Voiceflow-style environments) needed for the demo?
6. **Multiple triggers per flow.** v1 allows one, to keep pinning and dedupe simple. Revisit if the editor feels limited.
7. **Edge-level fan-out.** v1 forbids several edges per port. Confirm that `map` / `subflow` are enough for the parallelism we need.
