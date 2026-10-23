import { sharedApiKey } from "@/lib/api/server";
import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getExecution, getFlowByKey, getVersion, pendingApprovalFor } from "@/features/flows/api/queries";
import { ExecutionViewerContainer, type PendingApproval } from "@/features/flows/components/execution-viewer.container";
import { asGraph } from "@/features/flows/lib/types";

type Params = { params: Promise<{ key: string; id: string }> };

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { id } = await params;
  return { title: `Ejecución ${id.slice(0, 8)} · IGS OS` };
}

export default async function ExecutionPage({ params }: Params) {
  const { key, id } = await params;
  const [found, execution] = await Promise.all([getFlowByKey(key), getExecution(id)]);
  if (!found || !execution || execution.flow_id !== found.flow.id) notFound();
  // The execution is pinned to a version: draw that graph, not the current draft.
  const version = await getVersion(found.flow.id, execution.version);
  const graph = asGraph(version?.graph ?? found.flow.draft_graph);
  const approval = await pendingApprovalFor(execution.id);
  return (
    <ExecutionViewerContainer
      flow={graph}
      flowKey={key}
      initial={execution}
      approval={(approval as PendingApproval | null) ?? null}
      canWrite={Boolean(sharedApiKey())}
      streamUrl={`/ops/flows/${key}/executions/${id}/stream`}
    />
  );
}
