import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { GUIDE_COPY, GuideWidget } from "./GuideWidget";
import { PocBadge } from "./poc-badge";
import { fakeGuideTransport } from "./transport";
import type { GuideEvent, GuideTransport, GuideTurnRequest } from "./types";

vi.mock("next/navigation", () => ({ usePathname: () => "/ops/approvals" }));

afterEach(cleanup);

/** A transport that replays `events`, recording the requests it got. */
function scripted(events: GuideEvent[], seen: GuideTurnRequest[] = []): GuideTransport {
  return async function* run(request) {
    seen.push(request);
    for (const e of events) {
      await Promise.resolve();
      yield e;
    }
  };
}

const ANSWER: GuideEvent[] = [
  { type: "start", run_id: "r1", conversation_id: "c1" },
  { type: "text", delta: "Esto es un POC " },
  { type: "text", delta: "con datos ficticios." },
  {
    type: "tool_end",
    call_id: "t1",
    name: "suggest_route",
    output: { path: "/ops/approvals", label: "Ver aprobaciones" },
    is_error: false,
    ms: 1,
  },
  {
    type: "tool_end",
    call_id: "t2",
    name: "suggest_route",
    output: { path: "https://evil.example", label: "Malo" },
    is_error: false,
    ms: 1,
  },
  { type: "done", run_id: "r1", conversation_id: "c1", stop_reason: "end_turn" },
];

describe("GuideWidget", () => {
  it("shows the POC banner in Spanish on ops and English on the site", () => {
    const { unmount } = render(<GuideWidget locale="es" placement="ops" defaultOpen transport={scripted([])} />);
    expect(screen.getByTestId("guide-poc-banner").textContent).toContain(GUIDE_COPY.es.banner);
    expect(GUIDE_COPY.es.banner).toMatch(/POC · Datos ficticios/);
    unmount();
    render(<GuideWidget locale="en" defaultOpen transport={scripted([])} />);
    expect(screen.getByTestId("guide-poc-banner").textContent).toContain(
      "POC · Fictional data, no real IGS information · Real-time AI chat",
    );
  });

  it("opens from the floating button", () => {
    render(<GuideWidget locale="es" transport={scripted([])} />);
    expect(screen.queryByRole("dialog")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Asistente/ }));
    expect(screen.getByRole("dialog", { name: GUIDE_COPY.es.title })).toBeTruthy();
  });

  it("streams the answer and renders only same-site route pills", async () => {
    const seen: GuideTurnRequest[] = [];
    render(<GuideWidget locale="es" defaultOpen transport={scripted(ANSWER, seen)} />);
    fireEvent.click(screen.getByRole("button", { name: GUIDE_COPY.es.suggestions[0] }));
    await waitFor(() =>
      expect(screen.getByText("Esto es un POC con datos ficticios.")).toBeTruthy(),
    );
    const pill = screen.getByRole("link", { name: /Ver aprobaciones/ });
    expect(pill.getAttribute("href")).toBe("/ops/approvals");
    expect(screen.queryByRole("link", { name: /Malo/ })).toBeNull();
    expect(seen[0]).toMatchObject({ message: GUIDE_COPY.es.suggestions[0], page: "/ops/approvals" });
  });

  it("shows the typing indicator until the first token, and a stop button while busy", async () => {
    let release!: () => void;
    const gate = new Promise<void>((r) => (release = r));
    const slow: GuideTransport = async function* () {
      yield { type: "start", run_id: "r", conversation_id: "c" };
      await gate;
      yield { type: "text", delta: "Listo." };
      yield { type: "done", run_id: "r", conversation_id: "c", stop_reason: "end_turn" };
    };
    render(<GuideWidget locale="es" defaultOpen transport={slow} />);
    fireEvent.change(screen.getByPlaceholderText(GUIDE_COPY.es.placeholder), { target: { value: "hola" } });
    fireEvent.click(screen.getByRole("button", { name: "Enviar" }));
    expect(await screen.findByText(GUIDE_COPY.es.typing)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Detener" })).toBeTruthy();
    release();
    expect(await screen.findByText("Listo.")).toBeTruthy();
    expect(screen.queryByText(GUIDE_COPY.es.typing)).toBeNull();
  });

  it("the scripted fallback streams a fictional-data answer with a route", async () => {
    const events: GuideEvent[] = [];
    for await (const e of fakeGuideTransport("es", 0)({ message: "x" }, new AbortController().signal)) {
      events.push(e);
    }
    const text = events.flatMap((e) => (e.type === "text" ? [e.delta] : [])).join("");
    expect(text).toMatch(/datos ficticios/);
    expect(events.some((e) => e.type === "tool_end" && e.name === "suggest_route")).toBe(true);
  });
});

describe("PocBadge", () => {
  it("says it's a POC with fictional data", () => {
    render(<PocBadge />);
    expect(screen.getByText("POC · datos ficticios")).toBeTruthy();
  });
});
