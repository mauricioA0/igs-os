import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ExecutionDetail, FlowNode, NodeRun } from "../lib/types";
import { duration, TestPanel, type useTestRun } from "./editor-test-panel";

vi.mock("next/link", () => ({ default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => <a href={href} {...rest}>{children}</a> }));
vi.mock("../actions", () => ({ startTestRun: vi.fn() }));

const at = (s: number) => new Date(Date.UTC(2026, 9, 22, 12, 0, s)).toISOString();
const run = (i: number, node_id: string, node_type: string, status: string, output: unknown, input: unknown = null): NodeRun =>
  ({ id: `r${i}`, node_id, node_type, attempt: 1, status, input, output, error: null, started_at: at(i), finished_at: at(i + 1), duration_ms: 1000 * i }) as NodeRun;

const runs = [
  run(1, "greet", "say", "succeeded", { text: "Hi Dana! I'm the concierge." }),
  run(2, "qualify", "agent", "succeeded", { sport: "soccer" }),
  run(3, "ops_review", "approval", "waiting", null, { title: "Review proposal" }),
];
const nodes = new Map<string, FlowNode>([
  ["greet", { id: "greet", type: "say", name: "Saludo" }],
  ["qualify", { id: "qualify", type: "agent", name: "Calificar la consulta" }],
  ["ops_review", { id: "ops_review", type: "approval", name: "Aprobación de ops" }],
]);

function fakeRun(): ReturnType<typeof useTestRun> {
  const execution = { id: "e1", status: "waiting", node_runs: runs, error: null } as unknown as ExecutionDetail;
  return { executionId: "e1", execution, live: true, starting: false, error: null, start: vi.fn(), statuses: new Map() };
}

describe("TestPanel", () => {
  it("shows what the bot said as chat and every other step as an event, in order", () => {
    const onFocus = vi.fn();
    render(<TestPanel run={fakeRun()} flowKey="inbound-inquiry" nodes={nodes} canRun onFocus={onFocus} onClose={() => {}} />);
    expect(screen.getByText("Hi Dana! I'm the concierge.")).toBeTruthy();
    expect(screen.getByText("Calificar la consulta")).toBeTruthy();
    expect(screen.getByRole("link", { name: /Decidir en Aprobaciones/ }).getAttribute("href")).toBe("/ops/approvals");
    expect(screen.getByRole("link", { name: /Ver ejecución/ }).getAttribute("href")).toBe("/ops/flows/inbound-inquiry/executions/e1");
    fireEvent.click(screen.getByText("Aprobación de ops"));
    expect(onFocus).toHaveBeenCalledWith("ops_review");
  });

  it("explains why it can't run instead of failing", () => {
    const idle = { ...fakeRun(), executionId: null, execution: null };
    render(<TestPanel run={idle} flowKey="k" nodes={nodes} canRun={false} disabledReason="Publicá una versión para probarla." onFocus={() => {}} onClose={() => {}} />);
    expect(screen.getByText("Publicá una versión para probarla.")).toBeTruthy();
    expect((screen.getByRole("button", { name: /Iniciar prueba/ }) as HTMLButtonElement).disabled).toBe(true);
  });
});

describe("duration", () => {
  it("reads like people say it", () => {
    expect([duration(54), duration(1500), duration(869_000), duration(7_200_000)]).toEqual(["54 ms", "1,5 s", "14 min", "2,0 h"]);
  });
});
