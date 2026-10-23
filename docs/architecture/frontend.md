# Frontend architecture — patterns and state

Scope: `apps/web` (today `src/`). Next.js 16 App Router, React 19, Server Components by default.

## 1. Container / presentational

Maps directly onto the App Router:

| Layer | Where | Does | Never |
|---|---|---|---|
| **Container** | Server Component (`page.tsx`, `*.container.tsx`) | Fetches from `services/core` (typed client), checks permissions, picks what to render, passes plain props | Hold client state, import browser APIs |
| **Client container** | `"use client"` `*.container.tsx` | Wires interactive state (stores, server actions, SSE) to presentational components | Render markup beyond composition |
| **Presentational** | `src/components/**`, `_components/**` | Pure UI from props: layout, a11y, styling | Fetch, read stores, know about routes or the API |

```
app/ops/trips/[id]/page.tsx              ← server container: getTrip(), getApprovals()
  └─ TripTimelineContainer ("use client") ← store + server actions
       └─ TripTimeline / DayColumn / ItemRow (presentational, props only)
```

Rule of thumb: if a component imports the API client, a store or a server action, it is a container. Presentational components are what `/design` shows and what tests render without mocks.

## 2. Controlled and uncontrolled components

Every stateful primitive in `src/components/ui` supports **both** modes with the same API shape:

```tsx
<Tabs defaultValue="itinerary" />                         // uncontrolled
<Tabs value={tab} onValueChange={setTab} />                // controlled
```

- Props: `value` / `defaultValue` / `on{Value}Change` (and `open` / `defaultOpen` / `onOpenChange` for overlays).
- One shared hook implements it, so behavior is identical everywhere:

```ts
// src/components/ui/use-controllable-state.ts
export function useControllableState<T>({ value, defaultValue, onChange }: {
  value?: T; defaultValue: T; onChange?: (v: T) => void;
}) {
  const [internal, setInternal] = useState(defaultValue);
  const isControlled = value !== undefined;
  const current = isControlled ? value : internal;
  const set = useCallback((next: T) => {
    if (!isControlled) setInternal(next);
    onChange?.(next);
  }, [isControlled, onChange]);
  return [current, set] as const;
}
```

- **Use uncontrolled** by default (forms with server actions + `FormData`, tabs nobody else reads).
- **Use controlled** when state is shared (URL filters, the flow editor selection, approval drafts) — the owner is a container or a store.
- Inputs inside forms stay uncontrolled + native validation; `useActionState` handles submit state.

Today `tabs.tsx` already does this by hand; migrate it, `dialog`, `select` and `tooltip` to the shared hook.

## 3. Higher-order components (HOCs)

HOCs are used for **cross-cutting concerns at a component boundary**, where a wrapper is clearer than repeating a hook in every component. Logic reuse inside components stays in hooks; composition of UI stays in children/slots.

| HOC | Wraps | Purpose |
|---|---|---|
| `withPermission(Component, { toolClass })` | Actions/buttons that trigger tools | Hides or disables by the user's role and the tool class (`read` / `internal_write` / `external`) from security.md |
| `withErrorBoundary(Component, { fallback })` | Panels that stream (copilot, execution viewer, chat) | Isolates failures to the panel, reports to telemetry |
| `withApprovalGate(Component)` | Write actions on external/destructive tools | Turns `onConfirm` into "create approval" + shows the approval card instead of executing |
| `withTracking(Component, { event })` | Demo-tour steps, key CTAs | Analytics event without PII |
| `withFeatureFlag(Component, flag)` | Unfinished screens | Off in the demo tenant |

Conventions:

```tsx
export function withPermission<P extends object>(
  Component: ComponentType<P>,
  opts: { toolClass: ToolClass; mode?: "hide" | "disable" },
) {
  function WithPermission(props: P) {
    const allowed = useCan(opts.toolClass);
    if (!allowed && opts.mode !== "disable") return null;
    return <Component {...props} {...(!allowed && { disabled: true, "aria-disabled": true })} />;
  }
  WithPermission.displayName = `withPermission(${Component.displayName ?? Component.name})`;
  return WithPermission;
}
```

- Client-only (`"use client"`): an HOC can't wrap a Server Component across the boundary — server-side checks happen in the container (and always again in the API; the HOC is UX, not security).
- Always set `displayName`, forward refs (React 19 passes `ref` as a prop), and keep props pass-through typed with generics.
- Max two HOCs stacked on one component; beyond that, use a container.

## 4. State: where it lives

| State | Tool |
|---|---|
| Server data (trips, approvals, executions) | Server Components + server actions + `revalidatePath`/`revalidateTag`; client refresh via `router.refresh()` |
| Live server data (execution progress, copilot steps, chat stream) | SSE from `services/core` into a store |
| URL-shaped state (filters, tabs, selected trip) | Search params (`useSearchParams` + `router.replace`) — shareable links for the demo |
| Local UI state | `useState` / uncontrolled components |
| Cross-component client state | **Zustand** (see below) |
| Forms | Uncontrolled inputs + `useActionState` |

## 5. Zustand — verdict: yes, scoped

**Use it** where several distant client components share fast-changing state:

1. **Flow editor** — nodes, edges, selection, draft dirty flag, validation problems, undo/redo. React Flow itself is built on Zustand and recommends it for app state around the canvas.
2. **Copilot panel** — conversation, streaming steps, pending approval cards, context chips, open/closed across navigations.
3. **Execution viewer** — live node-run updates from SSE, selected node, timeline cursor.
4. **Chat (coach)** — streaming messages and quick replies.

**Don't use it** for server data (that's RSC + server actions) or URL state.

Rules:

- **One store per feature, created per instance** (`createStore` + React context provider), not module-level singletons — Next.js shares module scope across requests on the server, and two flow editors must not share state.
- Containers own the store; presentational components receive values via props (or tiny selector hooks colocated with the feature, never imported by `src/components/ui`).
- Always select narrowly (`useEditor(s => s.selectedId)`), `useShallow` for objects.
- Middleware: `devtools` in development, `immer` for the flow graph, `persist` only for UI prefs (panel open/closed), never for domain data.
- Undo/redo for the editor with `zundo` (temporal middleware) — evaluate when building phase 5.

Alternatives considered: React Context + `useReducer` (fine for small trees, re-renders everything below on each change — bad for the canvas and streaming); Jotai (good, but React Flow already ships Zustand and atoms add little for these feature stores); Redux Toolkit (more ceremony than this app needs).

## 6. Folder conventions

```
src/
  components/ui/          presentational primitives (controlled + uncontrolled)
  components/hoc/         withPermission, withErrorBoundary, withApprovalGate, withTracking, withFeatureFlag
  features/<feature>/
    *.container.tsx       containers (server or client)
    components/           presentational pieces of the feature
    store.ts              Zustand store factory + provider + selector hooks
    actions.ts            server actions
  app/                    routes: thin, delegate to features/*
```

## 7. Applying it to the prototypes

The current prototypes (`src/app/(prototype)/**`) mix data, state and markup in route files and use private styles in places. In phase 5 they move to `features/*` following this doc:

- `flows` → `features/flow-editor` (Zustand store, React Flow canvas as client container, panels presentational) and `features/executions`.
- `ops` → `features/trips`, `features/approvals` (approval card wrapped with `withApprovalGate` / `withPermission`), `features/leads`.
- `chat` → `features/coach-chat` (Zustand stream store).
- Private CSS in `flows.css` and arbitrary brand values in the proposal → design tokens from `globals.css`.
