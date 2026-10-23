import { describe, expect, it } from "vitest";
import { actionToText, diffLines, hasChanges } from "../lib/diff";
import { expiryState, formatInZone, formatRemaining } from "../lib/expiry";
import { commandForKey, moveSelection, selectionAfterRemoval } from "../lib/keyboard";
import { applyEdits, editableParams, fingerprint, toPreview } from "../lib/preview";

describe("diffLines", () => {
  it("marks unchanged, removed and added lines in order", () => {
    expect(diffLines("a\nb\nc", "a\nx\nc")).toEqual([
      { kind: "same", text: "a" },
      { kind: "removed", text: "b" },
      { kind: "added", text: "x" },
      { kind: "same", text: "c" },
    ]);
  });

  it("reports no changes for equal text", () => {
    expect(hasChanges(diffLines("hola\nchau", "hola\nchau"))).toBe(false);
  });

  it("diffs an edited email body inside the action", () => {
    const before = { action: "send_email", params: { to: "coach@x.example", body: "Hi\nPrice: 2,890" } };
    const after = applyEdits(before, { body: "Hi\nPrice: 2,790" });
    const lines = diffLines(actionToText(before), actionToText(after));
    expect(lines.filter((l) => l.kind === "removed").map((l) => l.text)).toEqual(["  Price: 2,890"]);
    expect(lines.filter((l) => l.kind === "added").map((l) => l.text)).toEqual(["  Price: 2,790"]);
  });
});

describe("keyboard", () => {
  it("maps J/K/A/R/E and arrows", () => {
    expect(["j", "k", "a", "r", "e", "ArrowDown", "ArrowUp"].map((key) => commandForKey({ key }))).toEqual([
      "next",
      "prev",
      "approve",
      "reject",
      "edit",
      "next",
      "prev",
    ]);
    expect(commandForKey({ key: "A" })).toBe("approve");
    expect(commandForKey({ key: "x" })).toBeNull();
  });

  it("never fires while typing or with modifiers", () => {
    expect(commandForKey({ key: "a", target: { tagName: "TEXTAREA" } })).toBeNull();
    expect(commandForKey({ key: "a", target: { tagName: "input" } })).toBeNull();
    expect(commandForKey({ key: "a", target: { isContentEditable: true } })).toBeNull();
    expect(commandForKey({ key: "a", metaKey: true })).toBeNull();
    expect(commandForKey({ key: "r", ctrlKey: true })).toBeNull();
  });

  it("moves within bounds and picks the neighbour after a decision", () => {
    const ids = ["a", "b", "c"];
    expect(moveSelection(ids, undefined, "next")).toBe("a");
    expect(moveSelection(ids, "a", "prev")).toBe("a");
    expect(moveSelection(ids, "b", "next")).toBe("c");
    expect(moveSelection(ids, "c", "next")).toBe("c");
    expect(moveSelection([], "a", "next")).toBeUndefined();
    expect(selectionAfterRemoval(ids, "b")).toBe("c");
    expect(selectionAfterRemoval(ids, "c")).toBe("b");
    expect(selectionAfterRemoval(["a"], "a")).toBeUndefined();
  });
});

describe("expiry", () => {
  const now = new Date("2026-10-22T18:00:00Z");

  it("distinguishes none, pending, urgent and expired", () => {
    expect(expiryState(null, now)).toEqual({ kind: "none" });
    expect(expiryState("2026-10-22T17:00:00Z", now).kind).toBe("expired");
    const soon = expiryState("2026-10-22T19:30:00Z", now);
    expect(soon.kind === "pending" && soon.urgent).toBe(true);
    const later = expiryState("2026-10-23T18:00:00Z", now);
    expect(later.kind === "pending" && later.urgent).toBe(false);
  });

  it("formats remaining time and the destination's local time", () => {
    expect(formatRemaining(90 * 60_000)).toBe("1 h 30 min");
    expect(formatRemaining(30_000)).toBe("1 min");
    expect(formatRemaining(3 * 24 * 3_600_000)).toBe("3 días");
    // 18:00 UTC is 15:00 in Buenos Aires (UTC−3).
    expect(formatInZone(now, "America/Argentina/Buenos_Aires")).toContain("15:00");
  });
});

describe("preview", () => {
  const approval = {
    execution_id: null,
    proposed_action: { action: "send_whatsapp", params: { to: "Palermo Sports Hotel", body: "Hola, rooming list" } },
    details: {
      flow: "pre-departure-check",
      summary: "El hotel no confirmó.",
      requested_by: "Flow · Antes de la salida",
      payload: [{ label: "Gira", value: "IGS-2711 · Lakeshore University" }],
      preview: { to: "otro", body: "texto viejo" },
    },
  };

  it("shows what will actually be sent, from the action params", () => {
    const p = toPreview(approval, "America/Argentina/Buenos_Aires");
    expect(p.channel).toBe("whatsapp");
    expect(p.to).toBe("Palermo Sports Hotel");
    expect(p.body).toBe("Hola, rooming list");
    expect(p.rows).toEqual([{ label: "Gira", value: "IGS-2711 · Lakeshore University" }]);
    expect(p.onExpiry).toMatch(/flow sigue/);
  });

  it("only exposes string params as editable and leaves the rest untouched", () => {
    const action = { action: "send_email", params: { to: "a@x", body: "b", attachments: ["x.pdf"] } };
    expect(editableParams(action)).toEqual(["to", "body"]);
    expect(applyEdits(action, { body: "new" }).params).toEqual({ to: "a@x", body: "new", attachments: ["x.pdf"] });
  });

  it("shortens the payload hash to a fingerprint", () => {
    expect(fingerprint("sha256:7f3a9c2e1d0b")).toBe("7f3a9c2e");
    expect(fingerprint("abcdef0123")).toBe("abcdef01");
  });
});

describe("effectiveStatus", () => {
  it("treats a pending approval past its expiry as expired", async () => {
    const { effectiveStatus } = await import("../lib/status");
    const now = new Date("2026-10-22T18:00:00Z");
    expect(effectiveStatus({ status: "pending", expires_at: "2026-10-22T17:00:00Z" }, now)).toBe("expired");
    expect(effectiveStatus({ status: "pending", expires_at: "2026-10-23T17:00:00Z" }, now)).toBe("pending");
    expect(effectiveStatus({ status: "pending", expires_at: null }, now)).toBe("pending");
    expect(effectiveStatus({ status: "approved", expires_at: "2026-10-22T17:00:00Z" }, now)).toBe("approved");
  });
});
