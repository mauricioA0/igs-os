import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import {
  ApprovalGateProvider,
  capabilityFor,
  FeatureFlagsProvider,
  PrincipalProvider,
  TrackingProvider,
  withApprovalGate,
  withErrorBoundary,
  withFeatureFlag,
  withPermission,
  withTracking,
  type GatedProps,
  type Principal,
} from ".";

const ops: Principal = { kind: "user", role: "ops" };
const viewer: Principal = { kind: "user", role: "viewer" };
const demo: Principal = { kind: "demo", role: "viewer" };

function Action({ disabled, onClick }: { disabled?: boolean; onClick?: () => void }) {
  return (
    <button type="button" disabled={disabled} onClick={onClick}>
      Do it
    </button>
  );
}

describe("capabilityFor", () => {
  it("never executes external actions from the UI", () => {
    for (const p of [ops, { kind: "user", role: "owner" } as Principal, demo]) {
      expect(capabilityFor(p, "external")).toBe("propose");
    }
    expect(capabilityFor(viewer, "external")).toBe("deny");
  });

  it("keeps the demo and viewers read-only for internal writes", () => {
    expect(capabilityFor(ops, "internal_write")).toBe("allow");
    expect(capabilityFor(viewer, "internal_write")).toBe("deny");
    expect(capabilityFor(demo, "internal_write")).toBe("deny");
    expect(capabilityFor(null, "read")).toBe("allow");
  });
});

describe("withPermission", () => {
  const Hidden = withPermission(Action, { toolClass: "internal_write" });
  const Disabled = withPermission(Action, { toolClass: "internal_write", mode: "disable" });

  it("sets a readable displayName", () => {
    expect(Hidden.displayName).toBe("withPermission(Action)");
  });

  it("hides or disables when denied and renders when allowed", () => {
    const { rerender } = render(
      <PrincipalProvider principal={viewer}>
        <Hidden />
      </PrincipalProvider>,
    );
    expect(screen.queryByRole("button")).toBeNull();
    rerender(
      <PrincipalProvider principal={viewer}>
        <Disabled />
      </PrincipalProvider>,
    );
    expect((screen.getByRole("button") as HTMLButtonElement).disabled).toBe(true);
    rerender(
      <PrincipalProvider principal={ops}>
        <Hidden />
      </PrincipalProvider>,
    );
    expect((screen.getByRole("button") as HTMLButtonElement).disabled).toBe(false);
  });
});

describe("withApprovalGate", () => {
  function SendButton({ onConfirm, pending, approval }: GatedProps & { to: string }) {
    if (approval) return <p>Approval {approval.id}</p>;
    return (
      <button type="button" disabled={pending} onClick={() => void onConfirm?.()}>
        Send
      </button>
    );
  }
  const GatedSend = withApprovalGate(SendButton, {
    describe: (p) => ({ action: "send_proposal", params: { to: p.to }, summary: `Send to ${p.to}` }),
  });

  it("turns an external action into an approval request with the exact params", async () => {
    const propose = vi.fn().mockResolvedValue({ id: "ap-1" });
    const send = vi.fn();
    render(
      <PrincipalProvider principal={demo}>
        <ApprovalGateProvider propose={propose}>
          <GatedSend to="coach@lakeshore.example" onConfirm={send} />
        </ApprovalGateProvider>
      </PrincipalProvider>,
    );
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Send" })));
    expect(propose).toHaveBeenCalledWith({
      action: "send_proposal",
      params: { to: "coach@lakeshore.example" },
      summary: "Send to coach@lakeshore.example",
    });
    expect(send).not.toHaveBeenCalled();
    expect(screen.getByText("Approval ap-1")).toBeTruthy();
  });

  it("runs allowed internal actions directly", async () => {
    const InternalSend = withApprovalGate(SendButton, {
      toolClass: "internal_write",
      describe: () => ({ action: "x", params: {}, summary: "x" }),
    });
    const send = vi.fn();
    const propose = vi.fn();
    render(
      <PrincipalProvider principal={ops}>
        <ApprovalGateProvider propose={propose}>
          <InternalSend to="ops" onConfirm={send} />
        </ApprovalGateProvider>
      </PrincipalProvider>,
    );
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Send" })));
    expect(send).toHaveBeenCalledOnce();
    expect(propose).not.toHaveBeenCalled();
  });
});

describe("withErrorBoundary", () => {
  function Boom({ fail }: { fail: boolean }) {
    if (fail) throw new Error("stream broke");
    return <p>ok</p>;
  }

  it("renders the fallback locally and resets when the reset key changes", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const onError = vi.fn();
    const Safe = withErrorBoundary(Boom, {
      fallback: ({ error }) => <p role="alert">{error.message}</p>,
      onError,
      resetKeys: (p) => [p.fail],
    });
    const { rerender } = render(<Safe fail />);
    expect(screen.getByRole("alert").textContent).toBe("stream broke");
    expect(onError).toHaveBeenCalled();
    rerender(<Safe fail={false} />);
    expect(screen.getByText("ok")).toBeTruthy();
  });
});

describe("withTracking and withFeatureFlag", () => {
  it("tracks the click and still calls the component's handler", () => {
    const track = vi.fn();
    const onClick = vi.fn();
    const Tracked = withTracking(Action, { event: "tour_started", properties: () => ({ step: 1 }) });
    render(
      <TrackingProvider track={track}>
        <Tracked onClick={onClick} />
      </TrackingProvider>,
    );
    fireEvent.click(screen.getByRole("button"));
    expect(track).toHaveBeenCalledWith("tour_started", { step: 1 });
    expect(onClick).toHaveBeenCalledOnce();
  });

  it("renders only when the flag is on", () => {
    const Flagged = withFeatureFlag(Action, "flow-builder-ai", <span>soon</span>);
    const { rerender } = render(
      <FeatureFlagsProvider flags={{}}>
        <Flagged />
      </FeatureFlagsProvider>,
    );
    expect(screen.getByText("soon")).toBeTruthy();
    rerender(
      <FeatureFlagsProvider flags={{ "flow-builder-ai": true }}>
        <Flagged />
      </FeatureFlagsProvider>,
    );
    expect(screen.getByRole("button")).toBeTruthy();
  });
});
