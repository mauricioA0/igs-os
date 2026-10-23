import { describe, expect, it } from "vitest";
import { TOUR_START_URL, TOUR_STEPS, parseStep, stepUrl } from "./steps";

describe("tour steps", () => {
  it("has six steps with unique anchors", () => {
    expect(TOUR_STEPS).toHaveLength(6);
    expect(new Set(TOUR_STEPS.map((s) => s.anchor)).size).toBe(6);
  });

  it("parses only valid step numbers", () => {
    expect(parseStep("1")).toBe(1);
    expect(parseStep("6")).toBe(6);
    for (const bad of [null, "", "0", "7", "1.5", "abc"]) expect(parseStep(bad)).toBeNull();
  });

  it("keeps a step's own query and adds the tour param", () => {
    expect(TOUR_START_URL).toBe("/ops?tour=1");
    const url = new URL(stepUrl(4), "http://x");
    expect(url.pathname).toBe("/ops/approvals");
    expect(url.searchParams.get("id")).toBeTruthy();
    expect(url.searchParams.get("tour")).toBe("4");
  });
});
