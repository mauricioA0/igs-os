import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { collectCitations, splitAnswer } from "../citations";
import { chipsFromPath, screenFromPath } from "../context";
import { CopilotDrawer } from "../CopilotDrawer";
import { fakeEvents } from "../fake";
import { LAKESHORE_QUESTION } from "../prompts";
import { readSse, sseTransport } from "../sse";
import type { CopilotEvent, TurnRequest } from "../types";

vi.mock("next/navigation", () => ({ usePathname: () => "/ops/accounts/acc-lakeshore" }));

const encoder = new TextEncoder();

/** Serializes events exactly like sse-starlette, split into awkward chunks. */
function sseBody(events: CopilotEvent[]): ReadableStream<Uint8Array> {
  const text =
    ": ping\r\n\r\n" +
    events.map(({ type, ...data }) => `event: ${type}\r\ndata: ${JSON.stringify(data)}\r\n\r\n`).join("");
  const chunks = text.match(/[\s\S]{1,37}/g) ?? [];
  return new ReadableStream({
    start(controller) {
      for (const c of chunks) controller.enqueue(encoder.encode(c));
      controller.close();
    },
  });
}

function mockFetch(response: () => Response) {
  const spy = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(async () => response());
  vi.stubGlobal("fetch", spy);
  return spy;
}

afterEach(() => vi.unstubAllGlobals());

describe("SSE parsing", () => {
  it("reassembles frames split across chunks and skips pings", async () => {
    const request: TurnRequest = { message: "x", context: [] };
    const frames = [];
    for await (const f of readSse(sseBody(fakeEvents(request)))) frames.push(f);
    expect(frames[0]).toEqual({ event: "start", data: expect.stringContaining("run-fake") });
    expect(frames.at(-1)?.event).toBe("done");
    expect(frames).toHaveLength(fakeEvents(request).length);
  });

  it("maps 503 to an unavailable error", async () => {
    mockFetch(() => Response.json({ detail: "The copilot is not configured." }, { status: 503 }));
    const run = sseTransport("/api/copilot/turns")({ message: "x", context: [] }, new AbortController().signal);
    await expect(run[Symbol.asyncIterator]().next()).rejects.toThrow("not configured");
  });
});

describe("citations", () => {
  it("labels interaction passages with channel, date and person", () => {
    const [c] = collectCitations([], [
      {
        id: "i1",
        channel: "email",
        occurred_at: "2026-10-15T14:02:00Z",
        subject: "Balance",
        excerpt: "We can't release the balance.",
        stakeholder: "Karen Liu",
      },
    ]);
    expect(c.label).toBe("Email · 15 oct · Karen Liu");
    expect(c.ariaLabel).toBe("Fuente 1: email del 15 de octubre de Karen Liu");
  });

  it("only turns markers with a known source into citations", () => {
    expect(splitAnswer("A [1] b [3] c [1, 2]", 2)).toEqual([
      { kind: "text", text: "A " },
      { kind: "cite", n: 1 },
      { kind: "text", text: " b [3] c " },
      { kind: "cite", n: 1 },
      { kind: "cite", n: 2 },
    ]);
  });
});

describe("route context", () => {
  it("derives chips and screens from ops routes", () => {
    expect(chipsFromPath("/ops/trips/t-2711", { "t-2711": "Lakeshore" })).toEqual([
      { kind: "trip", id: "t-2711", label: "Lakeshore" },
    ]);
    expect(chipsFromPath("/ops/flows/inbound-inquiry/executions/ex-7f3a").map((c) => c.kind)).toEqual([
      "flow",
      "execution",
    ]);
    expect(screenFromPath("/ops")).toBe("today");
    expect(screenFromPath("/ops/accounts/acc-1")).toBe("account");
  });
});

describe("CopilotDrawer", () => {
  it("opens with ⌘J, streams the Lakeshore turn and shows steps, citations and the approval", async () => {
    const fetchSpy = mockFetch(
      () =>
        new Response(sseBody(fakeEvents({ message: LAKESHORE_QUESTION, context: [] })), {
          headers: { "content-type": "text/event-stream" },
        }),
    );
    render(<CopilotDrawer labels={{ "acc-lakeshore": "Lakeshore University" }} />);

    act(() => {
      fireEvent.keyDown(window, { key: "j", metaKey: true });
    });
    const panel = screen.getByRole("complementary", { name: "Copiloto" });
    expect(within(panel).getByText("Lakeshore University")).toBeTruthy(); // context chip

    fireEvent.click(within(panel).getByRole("button", { name: LAKESHORE_QUESTION }));

    const review = await within(panel).findByRole("link", { name: "Revisar y aprobar" });
    expect(review.getAttribute("href")).toBe("/ops/approvals?id=a-fake-1");
    await waitFor(() => expect(within(panel).getByText(/está en/)).toBeTruthy());
    expect(within(panel).getByText("Leyendo la ficha del cliente")).toBeTruthy();
    expect(
      within(panel).getAllByRole("button", { description: /Fuente 1: email del \d+ de \S+ de Marcus Feld/ }).length,
    ).toBeGreaterThan(0);

    const body = JSON.parse(String(fetchSpy.mock.calls[0][1]?.body)) as TurnRequest;
    expect(body.message).toBe(LAKESHORE_QUESTION);
    expect(body.context).toEqual([{ kind: "account", id: "acc-lakeshore", label: "Lakeshore University" }]);
  });

  it("shows the unavailable state when the API has no model (503)", async () => {
    mockFetch(() => Response.json({ detail: "The copilot is not configured." }, { status: 503 }));
    render(<CopilotDrawer defaultOpen />);
    const panel = screen.getByRole("complementary", { name: "Copiloto" });
    fireEvent.click(within(panel).getByRole("button", { name: LAKESHORE_QUESTION }));
    expect(await within(panel).findByText("El copiloto no está disponible")).toBeTruthy();
  });

  it("shows the MCP connection command", () => {
    render(<CopilotDrawer defaultOpen mcpUrl="https://api.example.dev/mcp" />);
    fireEvent.click(screen.getByRole("tab", { name: "MCP" }));
    expect(
      screen.getByText(/claude mcp add --transport http igs-os https:\/\/api\.example\.dev\/mcp/),
    ).toBeTruthy();
  });

  it("has no floating open button: the ops header pill and ⌘J open it", () => {
    render(<CopilotDrawer transport={async function* () {}} />);
    expect(screen.queryByRole("button", { name: /copiloto/i })).toBeNull();
    act(() => {
      window.dispatchEvent(new KeyboardEvent("keydown", { key: "j", metaKey: true }));
    });
    expect(screen.getByRole("complementary", { name: "Copiloto" })).toBeTruthy();
  });

  it("runs the scripted mode in production with ?copilot=fake, without calling the API", async () => {
    vi.stubEnv("NODE_ENV", "production");
    window.history.replaceState(null, "", "/ops/accounts/acc-lakeshore?copilot=fake");
    const fetchSpy = mockFetch(() => new Response(null, { status: 500 }));
    try {
      render(<CopilotDrawer defaultOpen />);
      const panel = screen.getByRole("complementary", { name: "Copiloto" });
      expect(within(panel).getByText("modo guion")).toBeTruthy();
      fireEvent.click(within(panel).getByRole("button", { name: LAKESHORE_QUESTION }));
      await within(panel).findByText("Leyendo la ficha del cliente", {}, { timeout: 3000 });
      expect(fetchSpy).not.toHaveBeenCalled();
    } finally {
      vi.unstubAllEnvs();
      window.history.replaceState(null, "", "/");
    }
  });

  it("shows no scripted badge with the real transport", () => {
    render(<CopilotDrawer defaultOpen transport={async function* () {}} />);
    expect(screen.queryByText("modo guion")).toBeNull();
  });
});
