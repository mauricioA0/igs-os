import { describe, expect, it } from "vitest";
import { flowDisplayDescription, flowDisplayName, nodeDisplayName } from "./display-names";

describe("flow display names (QA D-07)", () => {
  it("shows the demo flows and nodes in Spanish", () => {
    expect(flowDisplayName("inbound-inquiry", "Inbound coach inquiry")).toBe("Consulta entrante de un coach");
    expect(nodeDisplayName("ops_review", null)).toBe("Aprobación de ops");
    expect(nodeDisplayName("qualify", "Qualify the inquiry")).toBe("Calificar la consulta");
  });

  it("falls back to the stored name for unknown flows and nodes", () => {
    expect(flowDisplayName("custom-flow", "My flow")).toBe("My flow");
    expect(flowDisplayDescription("custom-flow", "desc")).toBe("desc");
    expect(nodeDisplayName("send_sms", "Send SMS")).toBe("Send SMS");
    expect(nodeDisplayName("send_sms", undefined)).toBe("send sms");
  });
});
