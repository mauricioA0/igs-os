import { sharedApiKey } from "@/lib/api/server";
import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getFlowByKey, listExecutions } from "@/features/flows/api/queries";
import { FlowEditorContainer } from "@/features/flows/components/editor.container";
import { asGraph } from "@/features/flows/lib/types";
import { flowDisplayName } from "@/features/flows/lib/display-names";

type Params = { params: Promise<{ key: string }> };

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const found = await getFlowByKey((await params).key);
  return { title: found ? `${flowDisplayName(found.flow.key, found.flow.name)} · Flows · IGS OS` : "Flow no encontrado" };
}

export default async function FlowEditorPage({ params }: Params) {
  const { key } = await params;
  const found = await getFlowByKey(key);
  if (!found) notFound();
  const { flow, etag } = found;
  const executions = await listExecutions(flow.id, 10);
  return (
    <FlowEditorContainer
      key={etag}
      flowId={flow.id}
      flowKey={flow.key}
      name={flowDisplayName(flow.key, flow.name)}
      etag={etag}
      publishedVersion={flow.published_version}
      graph={asGraph(flow.draft_graph)}
      executions={executions}
      canWrite={Boolean(sharedApiKey())}
    />
  );
}
