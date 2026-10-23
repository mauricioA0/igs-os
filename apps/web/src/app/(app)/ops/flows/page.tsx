import type { Metadata } from "next";
import { connection } from "next/server";
import { getFlowByKey, listExecutions, listFlows } from "@/features/flows/api/queries";
import { FlowsList, type FlowCard } from "@/features/flows/components/flows-list";
import { runsByDay } from "@/features/flows/lib/runs-strip";
import { asGraph } from "@/features/flows/lib/types";

export const metadata: Metadata = { title: "Flows · IGS OS" };

export default async function FlowsPage() {
  await connection();
  const flows = await listFlows();
  const cards: FlowCard[] = await Promise.all(
    flows.map(async (summary) => {
      const [detail, executions] = await Promise.all([getFlowByKey(summary.key), listExecutions(summary.id, 50)]);
      return { summary, graph: detail ? asGraph(detail.flow.draft_graph) : null, executions, days: runsByDay(executions) };
    }),
  );
  return <FlowsList flows={cards} />;
}
