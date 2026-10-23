import { categories, nodeCatalog } from "../lib/catalog";
import type { Step } from "../lib/steps";
import type { FlowNode, NodeVisualStatus } from "../lib/types";
import { statusStyle } from "./flow-node";
import { StepIcon } from "./step-icon";

type Props = {
  steps: Step[];
  nodes: Map<string, FlowNode>;
  selectedId: string | null;
  onSelect: (id: string) => void;
  issueOf?: (id: string) => "error" | "warning" | undefined;
  statusOf?: (id: string) => NodeVisualStatus | undefined;
};

// The graph as numbered sentences; branches nest under the step that forks.
export function StepsView(props: Props) {
  return (
    <div className="h-full overflow-y-auto bg-background px-4 py-5 sm:px-8">
      <p className="eyebrow">Pasos · se lee de arriba hacia abajo</p>
      <ol className="mt-3 max-w-3xl space-y-1.5">
        <StepList {...props} />
      </ol>
    </div>
  );
}

function StepList({ steps, nodes, selectedId, onSelect, issueOf, statusOf }: Props) {
  return (
    <>
      {steps.map((step) => {
        const node = nodes.get(step.nodeId);
        const spec = node ? nodeCatalog[node.type] : undefined;
        const issue = step.jumpTo ? undefined : issueOf?.(step.nodeId);
        const status = step.jumpTo ? undefined : statusOf?.(step.nodeId);
        return (
          <li key={`${step.number}-${step.nodeId}`}>
            <button
              type="button"
              onClick={() => onSelect(step.jumpTo?.nodeId ?? step.nodeId)}
              aria-current={selectedId === step.nodeId ? "step" : undefined}
              className={`flex w-full items-start gap-3 rounded-lg border px-3 py-2 text-left font-body text-sm transition-colors hover:border-line-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                selectedId === step.nodeId ? "border-foreground bg-raised" : "border-line bg-card"
              } ${issue === "error" ? "border-danger" : issue === "warning" ? "border-warning" : ""} ${step.jumpTo ? "border-dashed text-muted-foreground" : ""}`}
            >
              <span className="display min-w-10 shrink-0 whitespace-nowrap text-lg leading-6 tabular-nums">{step.number}</span>
              {spec && node && !step.jumpTo && (
                <span title={categories[spec.category].label} className="-my-0.5 shrink-0">
                  <StepIcon type={node.type} />
                </span>
              )}
              <span className="min-w-0 flex-1 leading-6">{step.sentence}</span>
              {status && (
                <span className="inline-flex shrink-0 items-center gap-1 text-xs text-muted-foreground">
                  <span className={`h-2 w-2 rounded-full ${statusStyle[status].dot}`} />
                  {statusStyle[status].label}
                </span>
              )}
              {issue && <span className={`shrink-0 text-xs font-semibold ${issue === "error" ? "text-danger" : "text-warning"}`}>{issue === "error" ? "Error" : "Revisar"}</span>}
            </button>
            {step.branches.length > 0 && (
              <ul className="mt-1.5 space-y-2 border-l-2 border-line pl-4 sm:ml-10">
                {step.branches.map((b) => (
                  <li key={b.port}>
                    <p className="eyebrow mb-1">Si {b.label}</p>
                    <ol className="space-y-1.5">
                      <StepList {...{ steps: b.steps, nodes, selectedId, onSelect, issueOf, statusOf }} />
                    </ol>
                  </li>
                ))}
              </ul>
            )}
          </li>
        );
      })}
    </>
  );
}
